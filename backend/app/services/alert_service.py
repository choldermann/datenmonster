"""Auswertung der Unternehmenswarnungen (Business Alerts).

Die Trennung, die im ganzen Produkt gilt, gilt hier besonders streng:

    Das SQL (ein ganz normales Mapping) liefert die Zahlen.
    Die Regel entscheidet nur, ab wann daraus eine Warnung wird.
    Die KI darf die fertige Warnung später erklären – nie sie erzeugen.

Es wird deshalb NICHTS gerechnet, was nicht aus einer Mapping-Spalte kommt:
Anzahl (Zeilen), Summe einer Wertspalte, Vergleich zweier Spalten einer
Kennzahlenzeile. Keine Hochrechnung, keine Schätzung, keine Heuristik.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import or_
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Wie viele Regel-Abfragen gleichzeitig gegen die Quell-DB laufen. Bewusst
# identisch gedrosselt wie der Formular-Lauf: eine produktive JTL-Wawi soll von
# einem Warnungs-Lauf nichts merken.
ALERT_CONCURRENCY = 5

# Reihenfolge = Dringlichkeit. Die Ampelfarbe ist dieselbe Sprache wie im
# bestehenden tasklist-Widget, damit die Oberfläche einheitlich bleibt.
SEVERITY_ORDER = {"kritisch": 0, "warnung": 1, "hinweis": 2, "info": 3, "positiv": 4}
SEVERITY_AMPEL = {"kritisch": "rot", "warnung": "orange", "hinweis": "gelb",
                  "info": "gelb", "positiv": "gruen"}

_OPS = {
    ">":  lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _num(v):
    """Zahl aus einem Zellwert – oder None. Akzeptiert auch deutsche Schreibweise."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace("%", "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_de(v, decimals: int = 0) -> str:
    n = _num(v)
    if n is None:
        return "–" if v in (None, "") else str(v)
    s = f"{n:,.{decimals}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


# ── Mapping-Auflösung und -Lauf ──────────────────────────────────────────────

def _resolve_mapping(db, project_id, mapping_id=None, mapping_name=None):
    """Mapping über ID oder – der Regelfall – über den Namen im Projekt finden.

    Warnungen setzen auf Mappings anderer Templates auf (GF-, Lager-, Einkaufs-
    Cockpit). Deren IDs unterscheiden sich je Installation, die Namen nicht:
    der Template-Installer legt Mappings namensgleich an bzw. verwendet
    vorhandene wieder.
    """
    from app.models.mapping import Mapping
    if mapping_id:
        m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
        if m:
            return m
    if mapping_name:
        q = db.query(Mapping).filter(Mapping.name == mapping_name)
        if project_id is not None:
            m = q.filter(Mapping.project_id == project_id).first()
            if m:
                return m
        return q.first()
    return None


def _run_mapping(mapping_id: int, run_params: dict, preview_rows: int = 500) -> dict:
    """Read-only Lauf eines Mappings mit eigener DB-Session (thread-sicher)."""
    from app.core.database import SessionLocal
    from app.models.mapping import Mapping
    from app.services.mapping_service import MappingContext, execute_mapping
    db = SessionLocal()
    try:
        m = db.query(Mapping).filter(Mapping.id == mapping_id).first()
        if not m:
            return {"rows": [], "columns": [], "error": f"Mapping {mapping_id} nicht gefunden"}
        ctx = MappingContext.from_orm(m)
        ctx.run_params = dict(run_params)
        if not ctx.targets:
            return {"rows": [], "columns": [], "error": "Mapping hat keine Ziele"}
        t_fields = ctx.targets[0].get("fields") or []
        res = execute_mapping(**ctx.to_execute_kwargs(t_fields, preview_rows),
                              row_cap=preview_rows)
        rows = res.get("rows", [])
        errs = [str(e) for e in (res.get("errors") or []) if str(e).strip()]
        return {"rows": rows, "columns": res.get("columns", []),
                "error": ("; ".join(errs) if (errs and not rows) else None)}
    except Exception as e:
        return {"rows": [], "columns": [], "error": str(e)[:300]}
    finally:
        db.close()


# ── Bedingungen ──────────────────────────────────────────────────────────────

def _threshold(cond: dict, thresholds: dict):
    """Rechte Seite eines Vergleichs: fester Wert oder Schwellwert aus der
    Projektkonfiguration (value_config gewinnt, damit der Anwender steuern kann)."""
    ckey = cond.get("value_config")
    if ckey and ckey in thresholds:
        return _num(thresholds[ckey])
    return _num(cond.get("value"))


def _matches(row: dict, bedingung: dict, thresholds: dict) -> bool:
    """Ein einzelnes Zeilenkriterium – vergleicht NUR gelieferte Spaltenwerte."""
    links = _num(row.get(bedingung.get("column")))
    if links is None:
        return False
    rechts = _threshold(bedingung, thresholds)
    if rechts is None:
        return False
    op = _OPS.get(bedingung.get("op", ">="))
    return bool(op(links, rechts)) if op else False


def _filter_rows(rows: list, cond: dict, thresholds: dict) -> list:
    """row_filter grenzt eine vorhandene Ergebnisliste weiter ein (z.B. „nur
    Bestellungen mit mehr als X Tagen Verzug"). Gerechnet wird dabei nichts –
    es werden ausschließlich schon vorhandene Spaltenwerte verglichen, damit der
    Schwellwert konfigurierbar bleibt, ohne dass jede Regel ein eigenes SQL braucht."""
    rf = cond.get("row_filter")
    if not rf:
        return rows
    kriterien = rf if isinstance(rf, list) else [rf]
    return [r for r in rows if all(_matches(r, k, thresholds) for k in kriterien)]


def _rechte_seite(row: dict, cond: dict, thresholds: dict):
    """Vergleichswert einer KPI-Bedingung: entweder eine zweite Spalte derselben
    Zeile (z.B. Vorjahr, optional um X % oder einen Festbetrag verschoben) oder
    ein Schwellwert aus der Projektkonfiguration."""
    if not cond.get("compare_column"):
        return _threshold(cond, thresholds)

    rechts = _num(row.get(cond["compare_column"]))
    if rechts is None:
        return None

    # Faktor aus der Konfiguration: "5 % unter Vorjahr" bleibt so einstellbar.
    faktor = float(cond.get("factor", 1) or 1)
    fkey = cond.get("factor_config")
    if fkey and fkey in thresholds:
        prozent = _num(thresholds[fkey]) or 0
        modus = cond.get("factor_mode", "minus_percent")
        faktor = (1 - prozent / 100.0) if modus == "minus_percent" else (1 + prozent / 100.0)
    rechts *= faktor

    offset = _num(cond.get("offset"))
    if offset is not None:
        rechts += offset
    return rechts


def _eval_kpi(rows: list, cond: dict, thresholds: dict):
    """Vergleich innerhalb EINER Kennzahlenzeile.
    Rückgabe: (ausgeloest, metrikwert) – der Metrikwert wandert in Titel und
    Eskalation, damit die Zahl im Text aus derselben Quelle stammt wie die Prüfung."""
    if not rows:
        return False, None
    row = rows[0]
    left = _num(row.get(cond.get("column")))
    if left is None:
        return False, None

    right = _rechte_seite(row, cond, thresholds)
    if right is None:
        return False, left

    op = _OPS.get(cond.get("op", "<"))
    return (bool(op(left, right)) if op else False), left


def _severity_for(rule, metrics: dict) -> str:
    """Eskalationsstufen: erster Treffer gewinnt, sonst die Standard-Severity."""
    for lvl in (rule.severity_levels or []):
        value = _num(metrics.get(lvl.get("metric", "anzahl")))
        bound = _num(lvl.get("value"))
        op = _OPS.get(lvl.get("op", ">="))
        if value is None or bound is None or not op:
            continue
        if op(value, bound):
            return lvl.get("severity") or rule.severity
    return rule.severity or "warnung"


def _facts(rule, row: dict, extra: dict) -> list:
    """Nachvollziehbare Fakten hinter der Warnung. Ohne diese Liste ist eine
    Warnung nur eine Behauptung."""
    out = []
    for f in (rule.facts or []):
        col = f.get("column")
        val = extra.get(col) if col in extra else (row or {}).get(col)
        if val is None:
            continue
        out.append({"label": f.get("label") or col,
                    "wert": _fmt_de(val, int(f.get("decimals", 0))) if _num(val) is not None else str(val),
                    "einheit": f.get("unit", "")})
    return out


def _title(rule, values: dict) -> str:
    tpl = rule.title_template or rule.name
    try:
        return tpl.format(**values)
    except (KeyError, IndexError, ValueError):
        return rule.name


def _drilldown(rule, db, project_id) -> Optional[dict]:
    dd = rule.drilldown or {}
    if not dd:
        return None
    m = _resolve_mapping(db, project_id, dd.get("mapping_id"), dd.get("mapping_name"))
    if not m:
        return None
    # Weitere Ebenen (z.B. Artikelliste → aktuelle Beschreibung) werden mit
    # aufgelöst; nicht installierte Ziel-Mappings fallen still weg, die erste
    # Ebene bleibt trotzdem klickbar.
    levels = []
    for lvl in dd.get("levels") or []:
        lm = _resolve_mapping(db, project_id, lvl.get("mapping_id"), lvl.get("mapping_name"))
        if not lm:
            break
        levels.append({"mapping_id": lm.id, "title": lvl.get("title") or lm.name,
                       "key_column": lvl.get("key_column"), "param": lvl.get("param"),
                       "hidden_columns": lvl.get("hidden_columns") or []})
    return {"mapping_id": m.id, "title": dd.get("title") or rule.name,
            "hidden_columns": dd.get("hidden_columns") or [],
            "param": dd.get("param"), "levels": levels}


# ── Auswertung einer Regel ───────────────────────────────────────────────────

def _evaluate_rule(rule_data: dict, base_params: dict, thresholds: dict) -> dict:
    """Läuft im Thread: führt das Regel-Mapping aus und wertet die Bedingung aus.
    Bekommt nur einfache Daten (kein ORM-Objekt, keine Session)."""
    cond = rule_data.get("condition") or {}
    mode = cond.get("mode", "count")
    params = {**base_params, **(rule_data.get("params") or {})}
    limit = int(cond.get("limit", 200) or 200)
    # Die Listen-Mappings der Cockpits tragen ein hartes TOP N im SQL; row_cap hebt
    # es an (siehe _apply_row_cap). Wird der Deckel trotzdem erreicht, ist die
    # Anzahl eine Untergrenze – das wird im Text ausgewiesen, nicht verschwiegen.
    cap = limit if mode == "rows" else 500

    res = _run_mapping(rule_data["mapping_id"], params, preview_rows=cap)
    if res.get("error"):
        return {"status": "error", "error": res["error"]}

    roh = res.get("rows") or []
    gedeckelt = len(roh) >= cap
    rows = _filter_rows(roh, cond, thresholds)
    value_col = cond.get("value_column")
    summe = None
    if value_col:
        werte = [_num(r.get(value_col)) for r in rows]
        werte = [w for w in werte if w is not None]
        summe = sum(werte) if werte else 0.0

    if mode == "kpi":
        ausgeloest, metrik = _eval_kpi(rows, cond, thresholds)
        return {"status": "alert" if ausgeloest else "ok",
                "rows": rows[:1], "anzahl": 1 if ausgeloest else 0,
                "wert": metrik, "summe": summe, "gedeckelt": False}

    if mode == "rows":
        treffer = rows[:limit]
        return {"status": "alert" if treffer else "ok", "rows": treffer,
                "anzahl": len(treffer), "wert": summe, "summe": summe,
                "gedeckelt": gedeckelt}

    # mode "count": die Abfrage selbst definiert das Problem – jede Zeile zählt.
    min_count = int(cond.get("min_count", 1) or 1)
    return {"status": "alert" if len(rows) >= min_count else "ok",
            "rows": rows[: int(cond.get("sample_rows", 3) or 3)],
            "anzahl": len(rows), "wert": summe, "summe": summe,
            # Auch mit row_filter bleibt die Zahl eine Untergrenze, wenn die
            # Rohliste den Deckel erreicht hat – das darf der Text nicht verschweigen.
            "gedeckelt": gedeckelt}


def evaluate(db, project_id: Optional[int], params: Optional[dict] = None,
             include_ok: bool = False, rule_keys: Optional[list] = None,
             persist: bool = True, cockpits: Optional[list] = None) -> dict:
    """Führt alle aktiven Regeln des Projekts aus und liefert die Warnungen.

    include_ok=True gibt zusätzlich die nicht ausgelösten und die nicht
    verfügbaren Regeln zurück (Reiter „Alle Prüfungen").
    """
    from app.models.alert import AlertRule, AlertRun
    from app.services.business_config_service import apply_config
    from app.services.article_exclusion_service import apply_article_exclusions

    t0 = time.perf_counter()
    q = db.query(AlertRule).filter(AlertRule.active.is_(True))
    q = q.filter(AlertRule.project_id == project_id) if project_id is not None \
        else q.filter(AlertRule.project_id.is_(None))
    # rule_keys und cockpits wirken ODER-verknüpft: ein Cockpit zeigt „seine"
    # Regeln (cockpits) und darf einzelne fremde dazunehmen (rule_keys), ohne dass
    # eine Regel doppelt definiert werden muss. Ohne beides laufen alle Regeln.
    if rule_keys or cockpits:
        von_keys = AlertRule.rule_key.in_(rule_keys) if rule_keys else None
        von_cock = AlertRule.cockpit.in_(cockpits) if cockpits else None
        if von_keys is not None and von_cock is not None:
            q = q.filter(or_(von_keys, von_cock))
        else:
            q = q.filter(von_keys if von_keys is not None else von_cock)
    rules = q.order_by(AlertRule.sort.asc(), AlertRule.id.asc()).all()

    base_params = apply_config(params or {}, project_id, db)
    base_params = apply_article_exclusions(base_params, project_id, db)
    thresholds = {k[4:]: v for k, v in base_params.items() if k.startswith("cfg_")}

    # Regeln in einfache Dicts übersetzen (Threads bekommen keine ORM-Objekte)
    vorbereitet, nicht_verfuegbar = [], []
    for r in rules:
        m = _resolve_mapping(db, project_id, r.mapping_id, r.mapping_name)
        if not m:
            fehlend = r.mapping_name or r.mapping_id
            nicht_verfuegbar.append({
                "rule_key": r.rule_key, "name": r.name, "kategorie": r.category,
                "cockpit": r.cockpit, "status": "nicht_verfuegbar",
                "hinweis": f"Auswertung „{fehlend}“ ist in diesem Projekt nicht installiert.",
            })
            continue
        vorbereitet.append((r, {"mapping_id": m.id, "condition": r.condition or {},
                                "params": r.params or {}}))

    ergebnisse: dict = {}
    if vorbereitet:
        with ThreadPoolExecutor(max_workers=ALERT_CONCURRENCY) as ex:
            futs = {ex.submit(_evaluate_rule, data, base_params, thresholds): rule.rule_key
                    for rule, data in vorbereitet}
            for fut in as_completed(futs):
                try:
                    ergebnisse[futs[fut]] = fut.result()
                except Exception as e:  # eine kaputte Regel darf den Lauf nicht kippen
                    ergebnisse[futs[fut]] = {"status": "error", "error": str(e)[:300]}

    alerts, ok_rules, fehler = [], [], []
    for rule, _data in vorbereitet:
        res = ergebnisse.get(rule.rule_key) or {"status": "error", "error": "kein Ergebnis"}
        if res["status"] == "error":
            fehler.append({"rule_key": rule.rule_key, "name": rule.name,
                           "error": res.get("error")})
            continue

        anzahl = res.get("anzahl") or 0
        wert = res.get("wert")
        summe = res.get("summe")
        first_row = (res.get("rows") or [{}])[0] if res.get("rows") else {}
        metrics = {"anzahl": anzahl, "wert": wert, "summe": summe}
        werte_fuer_text = {
            "anzahl": ("mindestens " + _fmt_de(anzahl)) if res.get("gedeckelt") else _fmt_de(anzahl),
            "wert": _fmt_de(wert, 0) if wert is not None else "–",
            "summe": _fmt_de(summe, 0) if summe is not None else "–",
            **{k: v for k, v in (first_row or {}).items()},
        }

        if res["status"] != "alert":
            if include_ok:
                ok_rules.append({"rule_key": rule.rule_key, "name": rule.name,
                                 "kategorie": rule.category, "cockpit": rule.cockpit,
                                 "status": "ok", "anzahl": anzahl})
            continue

        severity = _severity_for(rule, metrics)
        alerts.append({
            "rule_key":   rule.rule_key,
            "name":       rule.name,
            "kategorie":  rule.category,
            "cockpit":    rule.cockpit,
            "severity":   severity,
            "Ampel":      SEVERITY_AMPEL.get(severity, "gelb"),
            "status":     "alert",
            "titel":      _title(rule, werte_fuer_text),
            "untertitel": rule.subtitle or "",
            "Anzahl":     anzahl,
            "wert":       wert,
            "summe":      summe,
            "gedeckelt":  bool(res.get("gedeckelt")),
            "fakten":     _facts(rule, first_row, metrics),
            "beispiele":  res.get("rows") or [],
            "drilldown":  _drilldown(rule, db, project_id),
            "action_kind": rule.action_kind,
            "sort":       rule.sort or 100,
        })

    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9),
                               -(_num(a.get("summe")) or _num(a.get("wert")) or 0),
                               a["sort"]))

    dauer = (time.perf_counter() - t0) * 1000.0
    lauf = {
        "project_id": project_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round(dauer, 1),
        "params": {k: v for k, v in (params or {}).items()},
        "alerts": alerts,
        "checked": len(vorbereitet),
        "triggered": len(alerts),
        "errors": fehler,
        "unavailable": nicht_verfuegbar,
        "ok": ok_rules,
    }

    if persist:
        try:
            run = AlertRun(project_id=project_id, duration_ms=round(dauer, 1),
                           params=lauf["params"], alerts=alerts,
                           checked=len(vorbereitet), triggered=len(alerts),
                           errors=fehler)
            db.add(run)
            db.commit()
            lauf["run_id"] = run.id
            _cleanup_runs(db, project_id)
        except Exception as e:
            db.rollback()
            logger.warning("AlertRun konnte nicht gespeichert werden: %s", e)

    return lauf


def _cleanup_runs(db, project_id, keep: int = 30):
    """Nur die letzten Läufe behalten – der Verlauf ist Diagnose, kein Archiv."""
    from app.models.alert import AlertRun
    q = db.query(AlertRun)
    q = q.filter(AlertRun.project_id == project_id) if project_id is not None \
        else q.filter(AlertRun.project_id.is_(None))
    alte = q.order_by(AlertRun.started_at.desc()).offset(keep).all()
    if not alte:
        return
    for r in alte:
        db.delete(r)
    db.commit()


def latest_run(db, project_id) -> Optional[dict]:
    from app.models.alert import AlertRun
    q = db.query(AlertRun)
    q = q.filter(AlertRun.project_id == project_id) if project_id is not None \
        else q.filter(AlertRun.project_id.is_(None))
    run = q.order_by(AlertRun.started_at.desc()).first()
    if not run:
        return None
    return {"run_id": run.id, "project_id": run.project_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "duration_ms": run.duration_ms, "params": run.params or {},
            "alerts": run.alerts or [], "checked": run.checked,
            "triggered": run.triggered, "errors": run.errors or []}

"""Erklärseite für ein Dashboard-Formular ("Was zeigt dieses Cockpit?").

Hybrid aus zwei Quellen:
  * Handgeschrieben: `schema["doku"]` im Template — der Einleitungstext, der sagt,
    WOZU das Cockpit da ist. Den kann keine Ableitung erfinden.
  * Abgeleitet: Reiter, Widgets und Quelltabellen werden bei jedem Aufruf aus dem
    Formular und seinen Mappings gelesen. Damit veraltet der technische Teil nicht,
    wenn jemand einen Reiter umbenennt oder eine Kennzahl ergänzt.

Die vorhandenen `config.info`-Texte der Widgets werden wörtlich übernommen — sie
erklären bereits die Feinheiten ("Momentaufnahme aus dbo.tlagerbestand …") und
sollen nicht ein zweites Mal woanders gepflegt werden.
"""
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.mapping import Mapping

# FROM/JOIN gefolgt von einem (ggf. schema-qualifizierten, ggf. eckig geklammerten) Namen.
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(\[?[A-Za-z_][\w]*\]?(?:\s*\.\s*\[?[A-Za-z_][\w]*\]?)?)",
    re.IGNORECASE,
)
# CTE-Namen: "WITH x AS (" und ", y AS (" — die sind KEINE Quelltabellen.
_CTE_RE = re.compile(r"(?:\bWITH\b|,)\s*(\[?[A-Za-z_][\w]*\]?)\s+AS\s*\(", re.IGNORECASE)

_WIDGET_LABELS = {
    "kpi": ("Kennzahl", "Kennzahlen"),
    "table": ("Tabelle", "Tabellen"),
    "bar": ("Balkendiagramm", "Balkendiagramme"),
    "line": ("Liniendiagramm", "Liniendiagramme"),
    "pie": ("Kreisdiagramm", "Kreisdiagramme"),
    "ai_summary": ("KI-Analyse", "KI-Analysen"),
    "inventur": ("Inventur-Werkzeug", "Inventur-Werkzeuge"),
    "kunden_ausschluss": ("Ausschlussliste", "Ausschlusslisten"),
}

# Systemkataloge sind Technik, keine Datenquelle im Sinne des Anwenders.
_KEIN_INHALT = ("sys.", "information_schema.", "tempdb.")


def _clean(name: str) -> str:
    return name.replace("[", "").replace("]", "").replace(" ", "").strip()


def _tables_from_sql(sql: str) -> set:
    """Quelltabellen aus einer SQL-Abfrage, ohne die selbst definierten CTEs."""
    if not sql:
        return set()
    ctes = {_clean(m).lower() for m in _CTE_RE.findall(sql)}
    out = set()
    for raw in _TABLE_RE.findall(sql):
        name = _clean(raw)
        if not name or name.lower() in ctes:
            continue
        # Nur echte Tabellen: entweder schema-qualifiziert (dbo.x) oder JTL-Konvention
        # (tArtikel, vRechnung). Alles andere ist meist ein Alias oder Unterabfrage.
        if name.lower().startswith(_KEIN_INHALT):
            continue
        if "." in name or re.match(r"^[tv][A-Z]", name):
            out.add(name)
    return out


def _mapping_ids(schema: dict) -> list:
    ids = []
    for a in schema.get("actions") or []:
        mid = a.get("mapping_id")
        if mid and mid not in ids:
            ids.append(mid)
    return ids


def _nodes(m: Mapping, attr: str) -> list:
    import json
    raw = getattr(m, attr, None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return raw if isinstance(raw, list) else []


def _zaehle(typen: dict) -> list:
    """{'kpi': 32, 'table': 16} -> ['32 Kennzahlen', '16 Tabellen'] (deutsch, mit Plural)."""
    out = []
    for typ, n in sorted(typen.items(), key=lambda kv: -kv[1]):
        ein, viele = _WIDGET_LABELS.get(typ, (typ, typ))
        out.append(f"{n} {ein if n == 1 else viele}")
    return out


def build_doku(form, db: Session) -> dict:
    schema = form.schema or {}
    doku = schema.get("doku") or {}
    widgets = schema.get("widgets") or []
    actions = {a.get("id"): a for a in (schema.get("actions") or [])}

    # ── Quelltabellen aus allen Mappings des Formulars ────────────────────────
    mids = _mapping_ids(schema)
    tabellen = set()
    if mids:
        for m in db.query(Mapping).filter(Mapping.id.in_(mids)).all():
            for n in _nodes(m, "sql_nodes"):
                if isinstance(n, dict):
                    tabellen |= _tables_from_sql(n.get("sql") or "")
            for n in _nodes(m, "canvas_nodes"):
                if isinstance(n, dict) and n.get("dataset_name"):
                    tabellen.add(str(n["dataset_name"]))

    # ── Widgets je Action, damit sie den Reitern zugeordnet werden können ─────
    je_action = {}
    for w in widgets:
        je_action.setdefault(w.get("action_id"), []).append(w)

    # ── Reiter ────────────────────────────────────────────────────────────────
    reiter = []
    verwendete_actions = set()
    for tab in schema.get("result_tabs") or []:
        typen, infos = {}, []
        for aid in tab.get("action_ids") or []:
            verwendete_actions.add(aid)
            for w in je_action.get(aid, []):
                typen[w.get("type")] = typen.get(w.get("type"), 0) + 1
                info = (w.get("config") or {}).get("info")
                if info and info not in infos:
                    infos.append(info)
        reiter.append({
            "label": tab.get("label") or tab.get("id"),
            "inhalt": _zaehle(typen),
            "hinweise": infos,
        })

    # Widgets ausserhalb der Reiter (Formulare ohne result_tabs)
    ohne_reiter = {}
    for w in widgets:
        if w.get("action_id") not in verwendete_actions:
            ohne_reiter[w.get("type")] = ohne_reiter.get(w.get("type"), 0) + 1

    return {
        "form_id": form.id,
        "name": form.name,
        # Handgeschrieben (aus dem Template); fehlt bei Formularen ohne doku-Abschnitt.
        "intro": doku.get("intro"),
        "hinweise": doku.get("hinweise") or [],
        "quellen": {
            "tabellen": sorted(tabellen),
            "auswertungen": len(mids),
        },
        "reiter": reiter,
        "ohne_reiter": _zaehle(ohne_reiter),
        "widgets_gesamt": len(widgets),
        "filter": [
            {"label": f.get("label") or f.get("name"), "typ": f.get("type")}
            for f in (schema.get("fields") or [])
        ],
    }

"""Die Werkzeuge, die ein Bauvorhaben zusammensetzen.

**Der Grundsatz dieses Moduls:** Die KI erfindet keine Schemata, sie füllt die
Eingaben vorhandener Erzeuger aus. Jedes Werkzeug ruft Code, den es in dieser
Plattform schon gibt – den Abfrage-Generator, den Report-Baukasten, den
Zustellplan, die Warnungen, die Portal-Veröffentlichung. Damit erbt die Werkbank
deren Prüfungen, statt sie nachzubauen und dabei zu verlieren:

* Der Abfrage-Generator nimmt **nur Katalogschlüssel** entgegen, nie SQL. Der
  Weg über ihn ist strukturell injektionssicher, egal was das Modell schreibt.
* `report_catalog.assemble` vergibt bei kollidierenden Aktions-IDs den
  `f<form_id>_`-Präfix. Ohne ihn zeigt eine Kachel die Zahlen einer anderen –
  das ist real passiert.
* `assemble` kopiert auch die **Filterfelder** mit. Ein fehlendes `:plattform`
  macht die Abfrage nicht unbeschränkt, sondern stumm leer.

Jedes Werkzeug liefert seine Ergebnisse als Artefakt-Angaben zurück; das
Stempeln und Speichern macht `bauen.py`, das Löschen `rueckbau.py`.
"""
import logging
import re
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class WerkzeugFehler(ValueError):
    """Die Eingabe eines Werkzeugs ist unbrauchbar. Der Text geht an den Anwender."""


# Die Zeitraum-Vorgaben kommen aus `services/zeitraum.py` und werden hier NICHT
# noch einmal aufgeschrieben. Eine Vorgabe, die dort nicht existiert, öffnet den
# Report stumm ohne Zeitraum – und eine zweite Liste wäre die sichere Art, dass
# beide irgendwann auseinanderlaufen.
def _zeitraeume() -> list:
    from app.services.zeitraum import PRESETS
    return list(PRESETS.items())


def _zeitraum_keys() -> set:
    from app.services.zeitraum import PRESETS
    return set(PRESETS)

# Takte, die ein Anwender in Worten beschreibt. Cron selbst schreiben zu lassen
# ist unnötiges Risiko – aus „jeden Montag" wurde beim Ausprobieren schon
# „0 0 * * 0" (Sonntag).
TAKTE = [
    ("0 6 * * 1",  "Jeden Montag um 6:00"),
    ("0 6 * * 2",  "Jeden Dienstag um 6:00"),
    ("0 6 * * *",  "Täglich um 6:00"),
    ("0 6 1 * *",  "Am 1. jedes Monats um 6:00"),
    ("0 7 * * 1-5", "Werktags um 7:00"),
]
TAKT_KEYS = {k for k, _ in TAKTE}


def _schluessel(text: str, fallback: str = "vorhaben") -> str:
    s = (text or "").lower()
    s = s.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:40] or fallback


# ─────────────────────────────────────────────────────────────────────────────
# 1 · Abfrage
# ─────────────────────────────────────────────────────────────────────────────

def _abfrage_zusammenfassung(eingabe: dict) -> str:
    from app.services.query_builder import katalog
    d = eingabe.get("definition") or {}
    kname = d.get("koernung") or "kunde"
    k = katalog.KOERNUNGEN.get(kname) or {}
    teile = [f"Körnung {k.get('label', kname)}"]
    anzahl = _bedingungen_zaehlen(d.get("zeilenfilter"))
    if anzahl:
        teile.append(f"{anzahl} Bedingung(en)")
    kz = d.get("kennzahlen") or []
    if kz:
        namen = [(katalog.kennzahl(kname, x) or {}).get("label", x) for x in kz]
        teile.append(", ".join(namen[:3]) + ("…" if len(namen) > 3 else ""))
    if _bedingungen_zaehlen(d.get("kennzahlfilter")):
        teile.append("mit Kennzahlfilter")
    return " · ".join(teile)


def _bedingungen_zaehlen(knoten) -> int:
    if not isinstance(knoten, dict):
        return 0
    if "op" in knoten:
        return sum(_bedingungen_zaehlen(k) for k in (knoten.get("kinder") or []))
    return 1 if knoten.get("key") else 0


def _abfrage_vorschau(db, ctx: dict, eingabe: dict, bisher: dict) -> dict:
    from app.services.query_builder import ausfuehren, sql_bauer

    definition = eingabe.get("definition") or {}
    von, bis = _zeitfenster(eingabe.get("zeitraum_preset"))
    try:
        erg = ausfuehren.rechnen(db, definition, ctx["mandant_id"], von=von, bis=bis)
    except sql_bauer.AbfrageFehler as e:
        raise WerkzeugFehler(str(e))
    except ausfuehren.LaufFehler as e:
        raise WerkzeugFehler(str(e))

    # Null Zeilen ist ein Befund, kein Ergebnis. Der Baumodus hat dieselbe
    # Regel: ein Mapping, das nichts liefert, ist meist falsch gebaut und nicht
    # etwa ein leerer Datenbestand – der Anwender soll es entscheiden.
    if erg["anzahl"] == 0:
        erg["befund"] = ("Die Abfrage läuft fehlerfrei, liefert aber keine einzige "
                         "Zeile. Meist stimmt eine Bedingung nicht oder der "
                         "Zeitraum ist zu eng.")
    return erg


def _abfrage_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.report import AdHocQuery
    from app.services.query_builder import erzeugen, sql_bauer

    name = (eingabe.get("name") or "").strip()
    if not name:
        raise WerkzeugFehler("Die Abfrage braucht einen Namen.")
    definition = eingabe.get("definition") or {}

    try:
        gebaut = erzeugen.speichern(db, name, definition,
                                    ctx["project_id"], ctx["mandant_id"])
    except sql_bauer.AbfrageFehler as e:
        raise WerkzeugFehler(str(e))
    db.flush()

    q = AdHocQuery(
        name=name, beschreibung=eingabe.get("beschreibung"),
        project_id=ctx["project_id"],
        koernung=definition.get("koernung") or "kunde",
        definition=definition,
        mapping_id=gebaut["mapping"].id,
        verlauf_mapping_id=gebaut.get("verlauf_mapping_id"),
        form_id=gebaut["form"].id,
        widget_ids=gebaut["widget_ids"], created_by=ctx.get("user_id"),
    )
    db.add(q)
    db.flush()

    # Was die folgenden Schritte davon brauchen.
    bisher.setdefault("bausteine", []).extend(
        {"form_id": gebaut["form"].id, "widget_id": w} for w in gebaut["widget_ids"])
    bisher.setdefault("mapping_namen", []).append(gebaut["mapping"].name)
    bisher.setdefault("mapping_ids", []).append(gebaut["mapping"].id)
    bisher["letzte_abfrage"] = {"name": name, "mapping_id": gebaut["mapping"].id,
                                "spalten": gebaut["spalten"]}

    return [
        {"art": "adhoc_query", "ziel_id": q.id, "erzeugt": True,
         "label": f"Auswertung „{name}“ mit {len(gebaut['widget_ids'])} Baustein(en)"},
        # Das Sammelformular ist geteilte Infrastruktur: Es ist der Ort, an dem
        # die nächste Auswertung landet – auch wenn dieses Vorhaben es angelegt
        # hat. erzeugt=False heißt: der Rückbau räumt nur unsere Bausteine daraus.
        {"art": "form", "ziel_id": gebaut["form"].id, "erzeugt": False,
         "label": f"Sammelformular „{gebaut['form'].name}“ (bleibt stehen)"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 2 · Report
# ─────────────────────────────────────────────────────────────────────────────

def _report_entries(eingabe: dict, bisher: dict) -> list:
    """Die Bausteine des Reports: die eben gebauten plus ausdrücklich gewählte."""
    entries = list(bisher.get("bausteine") or [])
    for e in (eingabe.get("bausteine") or []):
        paar = {"form_id": int(e["form_id"]), "widget_id": e["widget_id"]}
        if paar not in entries:
            entries.append(paar)
    return entries


def _report_zusammenfassung(eingabe: dict) -> str:
    n = len(eingabe.get("bausteine") or [])
    zr = dict(_zeitraeume()).get(eingabe.get("zeitraum_preset") or "months_12", "Zeitraum")
    extra = f" + {n} weitere(r) Baustein(e)" if n else ""
    return f"Bausteine der Abfrage{extra} · {zr}"


def _report_vorschau(db, ctx: dict, eingabe: dict, bisher: dict) -> dict:
    entries = _report_entries(eingabe, bisher)
    return {"bausteine": len(entries),
            "hinweis": "Der Report entsteht als ganz normales Formular und erbt "
                       "damit Vorschau, PDF, Portal, Drilldown und KI-Analyse."}


def _report_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.form import Form
    from app.services import report_catalog

    name = (eingabe.get("name") or "").strip()
    if not name:
        raise WerkzeugFehler("Der Report braucht einen Namen.")
    entries = _report_entries(eingabe, bisher)
    if not entries:
        raise WerkzeugFehler("Für den Report gibt es keine Bausteine. Er braucht "
                             "entweder einen Abfrage-Schritt davor oder eine "
                             "ausdrückliche Auswahl aus den Cockpits.")
    preset = eingabe.get("zeitraum_preset") or "months_12"
    if preset not in _zeitraum_keys():
        raise WerkzeugFehler(f"Unbekannte Zeitraum-Vorgabe „{preset}“.")

    try:
        gebaut = report_catalog.assemble(db, name, entries,
                                         zeitraum_preset=preset,
                                         project_id=ctx["project_id"])
    except ValueError as e:
        raise WerkzeugFehler(str(e))

    f = Form(name=name, project_id=gebaut["project_id"], schema=gebaut["schema"],
             created_by=ctx.get("user_id"))
    db.add(f)
    db.flush()

    bisher["report_form_id"] = f.id
    bisher["report_name"] = name
    return [{"art": "form", "ziel_id": f.id, "erzeugt": True,
             "label": f"Report „{name}“ mit {len(gebaut['schema']['widgets'])} Baustein(en)"}]


# ─────────────────────────────────────────────────────────────────────────────
# 3 · Zustellplan
# ─────────────────────────────────────────────────────────────────────────────

def _ziel_formular(eingabe: dict, bisher: dict) -> int:
    fid = eingabe.get("form_id") or bisher.get("report_form_id")
    if not fid:
        raise WerkzeugFehler("Es gibt kein Formular, das zugestellt werden könnte – "
                             "der Schritt braucht einen Report davor.")
    return int(fid)


def _zustellplan_zusammenfassung(eingabe: dict) -> str:
    takt = dict(TAKTE).get(eingabe.get("cron_expr") or "0 6 * * 1", eingabe.get("cron_expr"))
    zr = dict(_zeitraeume()).get(eingabe.get("zeitraum_preset") or "last_month", "")
    an = eingabe.get("email_to") or "(Empfänger fehlt)"
    return f"{takt} · {zr} · an {an}"


def _zustellplan_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.report import ReportSchedule

    fid = _ziel_formular(eingabe, bisher)
    cron = eingabe.get("cron_expr") or "0 6 * * 1"
    if cron not in TAKT_KEYS:
        raise WerkzeugFehler(f"Unbekannter Takt „{cron}“.")
    preset = eingabe.get("zeitraum_preset") or "last_month"
    if preset not in _zeitraum_keys():
        raise WerkzeugFehler(f"Unbekannte Zeitraum-Vorgabe „{preset}“.")
    empfaenger = (eingabe.get("email_to") or "").strip()
    if not empfaenger:
        raise WerkzeugFehler("Für den Zustellplan fehlt der Empfänger.")

    s = ReportSchedule(
        name=eingabe.get("name") or bisher.get("report_name") or "Zustellplan",
        form_id=fid, project_id=ctx["project_id"],
        # Ohne Mandant fiele der Nachtlauf auf den Projekt-Standard zurück und
        # rechnete Woche für Woche stumm den falschen Betrieb.
        mandant_id=ctx["mandant_id"],
        cron_expr=cron, active=bool(eingabe.get("aktiv", True)),
        zeitraum_preset=preset,
        params={}, sections=[],
        email_to=empfaenger, email_subject=eingabe.get("email_subject") or None,
        created_by=ctx.get("user_id"),
    )
    db.add(s)
    db.flush()

    bisher["schedule_id"] = s.id
    return [{"art": "report_schedule", "ziel_id": s.id, "erzeugt": True,
             "label": f"Zustellplan {_zustellplan_zusammenfassung(eingabe)}"}]


# ─────────────────────────────────────────────────────────────────────────────
# 4 · Warnung
# ─────────────────────────────────────────────────────────────────────────────

def _warnung_zusammenfassung(eingabe: dict) -> str:
    ab = eingabe.get("schwelle") or 1
    return f"Meldung ab {ab} Treffer · Dringlichkeit {eingabe.get('severity') or 'warnung'}"


def _warnung_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.alert import AlertRule

    # Die Warnung setzt auf dem Mapping der Abfrage auf – **per Name**, wie alle
    # Regeln in dieser Plattform, weil dieselbe Auswertung in jeder Installation
    # eine andere ID hat.
    mapping_name = eingabe.get("mapping_name") or (bisher.get("mapping_namen") or [None])[0]
    if not mapping_name:
        raise WerkzeugFehler("Die Warnung braucht eine Abfrage, die sie überwachen "
                             "kann – ein Abfrage-Schritt muss davor stehen.")
    try:
        schwelle = max(1, int(eingabe.get("schwelle") or 1))
    except (TypeError, ValueError):
        raise WerkzeugFehler("Die Schwelle muss eine ganze Zahl sein.")

    severity = eingabe.get("severity") or "warnung"
    if severity not in {"kritisch", "warnung", "hinweis", "info", "positiv"}:
        severity = "warnung"

    name = eingabe.get("name") or f"{mapping_name}"
    rule_key = f"werkbank_{ctx['vorhaben_id']}_{_schluessel(name, 'regel')}"

    r = AlertRule(
        project_id=ctx["project_id"], rule_key=rule_key, name=name,
        description=eingabe.get("beschreibung") or None,
        category=eingabe.get("kategorie") or "Eigene Auswertungen",
        cockpit="KI-Werkbank", severity=severity, severity_levels=[],
        mapping_name=mapping_name, params={},
        condition={"mode": "count", "min_count": schwelle},
        facts=[],
        title_template=eingabe.get("titel") or "{anzahl} Treffer in „" + name + "“",
        subtitle=eingabe.get("hinweis") or None,
        drilldown={"mapping_name": mapping_name, "title": name},
        active=True, sort=200,
    )
    db.add(r)
    db.flush()

    return [{"art": "alert_rule", "ziel_id": r.id, "ziel_key": rule_key, "erzeugt": True,
             "label": f"Warnung „{name}“ ab {schwelle} Treffer"}]


# ─────────────────────────────────────────────────────────────────────────────
# 5 · Veröffentlichen
# ─────────────────────────────────────────────────────────────────────────────

def _portal_zusammenfassung(eingabe: dict) -> str:
    n = len(eingabe.get("allowed_users") or [])
    wer = f"{n} Benutzer" if n else "alle Portal-Benutzer"
    return f"Im Portal sichtbar für {wer}"


def _portal_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.api.forms import unique_slug
    from app.models.form import Form

    fid = _ziel_formular(eingabe, bisher)
    f = db.query(Form).filter(Form.id == fid).first()
    if not f:
        raise WerkzeugFehler("Das zu veröffentlichende Formular gibt es nicht mehr.")

    # Zustand VOR der Änderung sichern – der Rückbau stellt genau ihn wieder her.
    # Das Formular kann schon vorher veröffentlicht gewesen sein; dann darf der
    # Rückbau es nicht einfach unsichtbar machen.
    vorher = {"published": bool(f.published), "slug": f.slug,
              "portal_config": dict(f.portal_config or {})}

    cfg = dict(f.portal_config or {})
    cfg["description"] = eingabe.get("beschreibung") or cfg.get("description") or ""
    if eingabe.get("allowed_users") is not None:
        cfg["allowed_users"] = eingabe.get("allowed_users") or []
    cfg.setdefault("allow_download", True)
    cfg.setdefault("allow_manual_run", True)

    f.slug = f.slug or unique_slug(db, f.name, exclude_id=f.id)
    f.published = True
    f.portal_config = cfg
    db.flush()

    bisher["portal_slug"] = f.slug
    return [{"art": "portal", "ziel_id": f.id, "erzeugt": False, "vorher": vorher,
             "label": f"Veröffentlicht unter /app/{f.slug}"}]


# ─────────────────────────────────────────────────────────────────────────────
# 6 · Erst nachsehen, ob es das schon gibt
# ─────────────────────────────────────────────────────────────────────────────

def vorhandenes_suchen(db, project_id, text: str, grenze: int = 6) -> list:
    """Bausteine installierter Cockpits, die zur Frage passen könnten.

    Die beste Antwort auf „zeig mir den Umsatz nach Monat" ist oft „das kann
    dein GF-Cockpit schon" – gebaut wird dann gar nichts.
    """
    from app.services import report_catalog

    woerter = {w for w in re.split(r"[^\wäöüß]+", (text or "").lower()) if len(w) > 3}
    if not woerter:
        return []
    treffer = []
    for cockpit in report_catalog.build_catalog(db, project_id):
        for reiter in cockpit["reiter"]:
            for e in reiter["eintraege"]:
                label = (e["label"] or "").lower()
                punkte = sum(1 for w in woerter if w in label)
                if punkte:
                    treffer.append({**e, "cockpit": cockpit["name"],
                                    "reiter": reiter["label"], "punkte": punkte})
    treffer.sort(key=lambda t: -t["punkte"])
    return treffer[:grenze]


def _nachsehen_vorschau(db, ctx: dict, eingabe: dict, bisher: dict) -> dict:
    treffer = vorhandenes_suchen(db, ctx["project_id"], eingabe.get("suchtext") or "")
    return {"treffer": treffer,
            "hinweis": ("Diese vorhandenen Bausteine passen zur Frage. Wer sie "
                        "übernimmt, spart den Bau." if treffer else
                        "Nichts Passendes gefunden – Neubau ist hier richtig.")}


def _nachsehen_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    # Legt nichts an. Gewählte Treffer wandern als Bausteine in den Report.
    for e in (eingabe.get("uebernehmen") or []):
        bisher.setdefault("bausteine", []).append(
            {"form_id": int(e["form_id"]), "widget_id": e["widget_id"]})
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 7 · Freie Abfrage (SQL von der KI)
#
# Der Rückfall, wenn der Katalog des Abfrage-Generators die Frage nicht abdeckt.
# Das SQL entsteht schon beim Planen, nicht beim Bauen: es durchläuft dort die
# Prüfkette aus `sql_werkstatt` (gegen die echte Verbindung ausführen, bis zu
# zwei Reparaturläufe, Leer- und Join-Befund). Was hier ankommt, ist geprüft –
# und ein Befund daran ist sichtbar, statt stillschweigend mitzureisen.
# ─────────────────────────────────────────────────────────────────────────────

def _sql_zusammenfassung(eingabe: dict) -> str:
    spalten = eingabe.get("spalten") or []
    teile = [f"Freies SQL · {len(spalten)} Spalte(n)"]
    if eingabe.get("fehler"):
        teile.append("FEHLERHAFT")
    elif eingabe.get("leer"):
        teile.append("liefert keine Zeilen")
    elif eingabe.get("warnung"):
        teile.append("Join fraglich")
    return " · ".join(teile)


def _sql_ausfuehren(mandant_id: int, sql: str, von: str, bis: str, limit: int = 50) -> list:
    """Das freie SQL zur Ansicht laufen lassen – gedeckelt, mit Zeitfenster."""
    from sqlalchemy import text as _text

    from app.services.sql_helpers import _get_sql_engine, _resolve_sql_run_params

    fertig, gebunden = _resolve_sql_run_params(sql, {"von": von, "bis": bis})
    eng = _get_sql_engine(mandant_id)
    with eng.connect() as con:
        # fetchmany statt fetchall: eine Abfrage ohne TOP kann Hunderttausende
        # Zeilen liefern, und für die Ansicht reichen die ersten.
        return [dict(r) for r in con.execute(_text(fertig), gebunden).mappings().fetchmany(limit)]


def _sql_vorschau(db, ctx: dict, eingabe: dict, bisher: dict) -> dict:
    sql = (eingabe.get("sql") or "").strip()
    if not sql:
        raise WerkzeugFehler("Für diesen Schritt gibt es noch kein SQL.")
    if eingabe.get("fehler"):
        raise WerkzeugFehler(f"Die Datenbank lehnt das erzeugte SQL ab: {eingabe['fehler']}")

    von, bis = _zeitfenster(eingabe.get("zeitraum_preset"))
    try:
        zeilen = _sql_ausfuehren(ctx["mandant_id"], sql, von, bis)
    except Exception as e:
        raise WerkzeugFehler(f"Abfrage fehlgeschlagen: {str(e)[:300]}")

    spalten = [{"name": c} for c in (eingabe.get("spalten") or [])] or \
              [{"name": k} for k in (zeilen[0].keys() if zeilen else [])]
    erg = {"zeilen": zeilen, "spalten": spalten, "anzahl": len(zeilen),
           "gedeckelt": len(zeilen) >= 50, "sql": sql,
           "zeitraum": {"von": von, "bis": bis}}
    if not zeilen:
        erg["befund"] = ("Das SQL läuft, liefert aber keine Zeile. Bei freiem SQL ist "
                         "das fast immer ein Join über zwei Schlüssel, die nicht "
                         "zusammengehören – oder ein zu enger Zeitraum.")
    else:
        tote = _tote_kennzahlen(zeilen)
        if tote:
            erg["befund"] = (
                f"Die Abfrage liefert Zeilen, aber {', '.join(tote)} "
                f"{'ist' if len(tote) == 1 else 'sind'} in jeder davon 0 oder leer. "
                f"Das heißt meist: die Spalte trägt in dieser Datenbank nicht die "
                f"Zahl, nach der gesucht wird.")
        elif eingabe.get("warnung"):
            erg["befund"] = eingabe["warnung"]
    return erg


def _tote_kennzahlen(zeilen: list, grenze: int = 3) -> list:
    """Zahlenspalten, die in JEDER Zeile 0 oder leer sind.

    Der dritte blinde Fleck des freien SQL, den die Prüfkette nicht abdeckt: Die
    Abfrage läuft, liefert Zeilen und hat plausible Joins – aber sie zieht die
    falsche Spalte, und die ist in dieser Datenbank durchweg 0. „Die 20 Artikel
    mit dem höchsten Lagerwert" kam so mit lauter Nullen zurück, weil der
    Bestand nicht in `tArtikel` steht. Das ist kein Fehler, den die Datenbank
    melden könnte – nur einer, den man an den Zahlen sieht.
    """
    if len(zeilen) < 2:
        return []
    from decimal import Decimal

    def zahl(w) -> bool:
        # MSSQL liefert DECIMAL als decimal.Decimal, nicht als float – ohne diesen
        # Fall übersieht die Prüfung ausgerechnet die Geldspalten.
        return isinstance(w, (int, float, Decimal)) and not isinstance(w, bool)

    tote = []
    for spalte in zeilen[0].keys():
        werte = [z.get(spalte) for z in zeilen]
        if not any(zahl(w) for w in werte):
            continue
        if not all(w is None or (zahl(w) and w == 0) for w in werte):
            continue
        tote.append(f"„{spalte}“")
    # Sind ALLE Zahlenspalten leer, ist die Meldung wertlos ausführlich; und
    # Schlüsselspalten (kArtikel, kKunde) sind nie 0, also stören sie hier nicht.
    return tote[:grenze]


def _bausteine_anlegen(db, project_id, name: str, mapping, spalten: list) -> dict:
    """Aktion und Tabellen-Baustein im Sammelformular – wie beim Abfrage-Generator.

    Ohne Baustein wäre das Mapping im Report-Baukasten unsichtbar und der
    Report-Schritt fände nichts zum Zusammenstellen.
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.query_builder import erzeugen

    f = erzeugen._sammelformular(db, project_id)
    schema = dict(f.schema or {})
    schema.setdefault("actions", [])
    schema.setdefault("widgets", [])
    schema.setdefault("result_tabs", [])

    basis = erzeugen._schluessel(name)
    aid, w_tab = f"act_sql_{basis}", f"w_sql_{basis}_tab"
    schema["widgets"] = [w for w in schema["widgets"] if w.get("id") != w_tab]
    schema["actions"] = [a for a in schema["actions"] if a.get("id") != aid]

    schema["actions"].append({"id": aid, "type": "run_mapping", "mapping_id": mapping.id,
                              "pipeline_id": None, "label": name})
    schema["widgets"].append({"id": w_tab, "type": "table", "label": name,
                              "action_id": aid,
                              "config": {"width": 12, "full_rows": True}})

    tab = next((t for t in schema["result_tabs"] if t.get("id") == "tab_eigene"), None)
    if not tab:
        tab = {"id": "tab_eigene", "label": erzeugen.SAMMELFORMULAR, "action_ids": []}
        schema["result_tabs"].append(tab)
    if aid not in tab["action_ids"]:
        tab["action_ids"].append(aid)

    f.schema = schema
    flag_modified(f, "schema")
    db.flush()
    return {"form": f, "action_id": aid, "widget_ids": [w_tab]}


def _sql_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.services.query_builder import erzeugen

    name = (eingabe.get("name") or "").strip()
    if not name:
        raise WerkzeugFehler("Die freie Abfrage braucht einen Namen.")
    sql = (eingabe.get("sql") or "").strip()
    if not sql:
        raise WerkzeugFehler("Für diesen Schritt gibt es kein SQL.")
    if eingabe.get("fehler"):
        raise WerkzeugFehler("Das erzeugte SQL läuft nicht und wird nicht gebaut: "
                             + str(eingabe["fehler"])[:200])

    spalten = [{"name": c, "typ": "text"} for c in (eingabe.get("spalten") or [])]
    if not spalten:
        raise WerkzeugFehler("Die Abfrage hat keine geprüften Spalten – ohne sie "
                             "bliebe das Mapping in der Oberfläche leer.")

    m = erzeugen.mapping_bauen(db, name, ctx["project_id"], ctx["mandant_id"],
                               {"sql": sql, "spalten": spalten})
    db.flush()
    gebaut = _bausteine_anlegen(db, ctx["project_id"], name, m, spalten)

    bisher.setdefault("bausteine", []).extend(
        {"form_id": gebaut["form"].id, "widget_id": w} for w in gebaut["widget_ids"])
    bisher.setdefault("mapping_namen", []).append(m.name)
    bisher.setdefault("mapping_ids", []).append(m.id)

    return [
        {"art": "mapping", "ziel_id": m.id, "erzeugt": True,
         "label": f"Mapping „{name}“ aus freiem SQL ({len(spalten)} Spalten)"},
        {"art": "widget", "ziel_id": gebaut["form"].id,
         "ziel_key": ",".join(gebaut["widget_ids"]), "erzeugt": True,
         "eltern_art": "form", "eltern_id": gebaut["form"].id,
         "label": f"Baustein „{name}“ im Sammelformular"},
        {"art": "form", "ziel_id": gebaut["form"].id, "erzeugt": False,
         "label": f"Sammelformular „{gebaut['form'].name}“ (bleibt stehen)"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 8 · Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _pipeline_zusammenfassung(eingabe: dict) -> str:
    takt = dict(TAKTE).get(eingabe.get("cron_expr") or "0 6 * * 1",
                           eingabe.get("cron_expr") or "manuell")
    n = len(eingabe.get("mapping_ids") or [])
    ziel = f"{n} Mapping(s)" if n else "die Mappings dieses Vorhabens"
    mail = f" · Meldung an {eingabe['email_to']}" if eingabe.get("email_to") else ""
    return f"{takt} · {ziel}{mail}"


def _pipeline_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.mapping import Mapping
    from app.models.pipeline import Pipeline

    name = (eingabe.get("name") or "").strip()
    if not name:
        raise WerkzeugFehler("Die Pipeline braucht einen Namen.")
    cron = eingabe.get("cron_expr") or "0 6 * * 1"
    if cron not in TAKT_KEYS:
        raise WerkzeugFehler(f"Unbekannter Takt „{cron}“.")

    ids = [int(i) for i in (eingabe.get("mapping_ids") or bisher.get("mapping_ids") or [])]
    if not ids:
        raise WerkzeugFehler("Die Pipeline hat nichts auszuführen – sie braucht einen "
                             "Abfrage-Schritt davor oder ausdrücklich gewählte Mappings.")
    vorhanden = {m.id: m for m in db.query(Mapping).filter(Mapping.id.in_(ids)).all()}
    fehlend = [i for i in ids if i not in vorhanden]
    if fehlend:
        raise WerkzeugFehler(f"Mapping(s) nicht gefunden: {fehlend}")

    schluessel = _schluessel(name, "pipeline")
    knoten = [{"id": f"trg_{schluessel}", "type": "trigger", "x": 120, "y": 140,
               "config": {"trigger_mode": "schedule", "cron": cron}}]
    verbindungen = []
    vorher = knoten[0]["id"]
    for i, mid in enumerate(ids):
        nid = f"map_{schluessel}_{i}"
        knoten.append({"id": nid, "type": "mapping", "x": 440 + i * 320, "y": 140,
                       "config": {"mapping_id": mid, "on_error": "stop"}})
        verbindungen.append({"from_node": vorher, "from_port": "out",
                             "to_node": nid, "to_port": "in"})
        vorher = nid

    if eingabe.get("email_to"):
        nid = f"eml_{schluessel}"
        knoten.append({"id": nid, "type": "email", "x": 440 + len(ids) * 320, "y": 140,
                       "config": {"to": eingabe["email_to"],
                                  "subject": f"{name}: Lauf abgeschlossen",
                                  "body": f"Die Pipeline „{name}“ wurde ausgeführt.\n"
                                          f"Zeilen und etwaige Fehler stehen im "
                                          f"Monitoring von Datenmonster.",
                                  "send_on": eingabe.get("send_on") or "always"}})
        verbindungen.append({"from_node": vorher, "from_port": "out",
                             "to_node": nid, "to_port": "in"})

    p = Pipeline(name=name, project_id=ctx["project_id"],
                 active=bool(eingabe.get("aktiv", True)),
                 nodes=knoten, connections=verbindungen)
    db.add(p)
    db.flush()

    # Ohne diesen Aufruf steht die Pipeline zwar da, läuft aber nie: der
    # Cron-Job entsteht erst beim Abgleich mit dem Scheduler.
    from app.api.pipelines import _sync_pipeline_scheduler
    _sync_pipeline_scheduler(p)

    bisher["pipeline_id"] = p.id
    return [{"art": "pipeline", "ziel_id": p.id, "erzeugt": True,
             "label": f"Pipeline „{name}“ – {_pipeline_zusammenfassung(eingabe)}"}]


# ─────────────────────────────────────────────────────────────────────────────
# 9 · App (Formular mit Eingabefeldern)
#
# Der Sprung von „anzeigen" zu „bedienen": Der Anwender gibt etwas ein, und die
# Abfrage antwortet darauf. Technisch ist das ein ganz normales Formular mit
# `fields`, einem Knopf und einer Tabelle – die Plattform kann das längst, es
# fehlte nur der Weg dorthin über einen Satz.
#
# **Der Knackpunkt sind die Parameter.** Jedes Eingabefeld setzt einen
# Laufzeitwert `:name`, und jeder `:name` im SQL MUSS durch ein Feld gedeckt
# sein. Fehlt die Deckung, bleibt der Platzhalter ungebunden und die Abfrage
# schlägt fehl – oder, bei einem Listenparameter, liefert stumm null Zeilen.
# Deshalb werden Felder und SQL zusammen geplant und hier gegeneinander geprüft.
# ─────────────────────────────────────────────────────────────────────────────

FELDTYPEN = {
    "text":      {"label": "Text", "ziel": "string"},
    "number":    {"label": "Zahl", "ziel": "float"},
    "date":      {"label": "Datum", "ziel": "string"},
    "dropdown":  {"label": "Auswahl", "ziel": "string"},
    "daterange": {"label": "Zeitraum", "ziel": "string"},
}


def _app_felder(eingabe: dict) -> list:
    """Die Eingabefelder, auf gültige Typen und Namen beschnitten."""
    raus, gesehen = [], set()
    for f in (eingabe.get("felder") or []):
        name = _schluessel(f.get("name") or f.get("label") or "", "")
        typ = f.get("typ") if f.get("typ") in FELDTYPEN else "text"
        if not name or name in gesehen:
            continue
        gesehen.add(name)
        raus.append({"name": name, "typ": typ,
                     "label": f.get("label") or name,
                     "pflicht": bool(f.get("pflicht")),
                     "beispiel": f.get("beispiel"),
                     "optionen": [o for o in (f.get("optionen") or []) if str(o).strip()]})
    return raus


def _app_parameter(felder: list) -> set:
    """Welche `:namen` die Felder abdecken. Ein Zeitraum deckt zwei ab."""
    raus = set()
    for f in felder:
        if f["typ"] == "daterange":
            raus |= {"von", "bis"}
        else:
            raus.add(f["name"])
    return raus


def _sql_parameter(sql: str) -> set:
    """Alle `:namen` im SQL – ohne die automatisch mitgebundenen `_empty`-Flags."""
    gefunden = set(re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", sql or ""))
    return {p for p in gefunden if not p.endswith("_empty")}


def _app_zusammenfassung(eingabe: dict) -> str:
    felder = _app_felder(eingabe)
    teile = [f"{len(felder)} Eingabefeld(er)"]
    if felder:
        teile.append(", ".join(f["label"] for f in felder[:3])
                     + ("…" if len(felder) > 3 else ""))
    if eingabe.get("fehler"):
        teile.append("SQL FEHLERHAFT")
    return " · ".join(teile)


def _app_pruefen(eingabe: dict) -> list:
    """Deckungslücken zwischen SQL-Parametern und Feldern – als Klartext."""
    felder = _app_felder(eingabe)
    gedeckt = _app_parameter(felder)
    gebraucht = _sql_parameter(eingabe.get("sql") or "")
    fehlend = sorted(gebraucht - gedeckt)
    unbenutzt = sorted(gedeckt - gebraucht - {"von", "bis"})
    befunde = []
    if fehlend:
        befunde.append("Das SQL erwartet " + ", ".join(f"„:{p}“" for p in fehlend)
                       + ", aber kein Eingabefeld liefert das. Ungebunden bleibt die "
                         "Abfrage stehen oder liefert stumm nichts.")
    if unbenutzt:
        befunde.append("Die Felder " + ", ".join(f"„{p}“" for p in unbenutzt)
                       + " werden im SQL nicht verwendet – sie hätten keine Wirkung.")
    return befunde


def _app_vorschau(db, ctx: dict, eingabe: dict, bisher: dict) -> dict:
    sql = (eingabe.get("sql") or "").strip()
    if not sql:
        raise WerkzeugFehler("Für die App gibt es noch kein SQL.")
    if eingabe.get("fehler"):
        raise WerkzeugFehler(f"Die Datenbank lehnt das erzeugte SQL ab: {eingabe['fehler']}")

    felder = _app_felder(eingabe)
    luecken = _app_pruefen(eingabe)
    von, bis = _zeitfenster(eingabe.get("zeitraum_preset"))

    # Mit den Beispielwerten rechnen: eine Maske ohne Eingabe liefert
    # naturgemäß nichts, und „null Zeilen" wäre dann kein Befund, sondern der
    # Normalfall. Erst mit plausiblen Werten sagt die Vorschau etwas aus.
    werte = {"von": von, "bis": bis}
    for f in felder:
        if f["typ"] == "daterange":
            continue
        if f.get("beispiel") not in (None, ""):
            werte[f["name"]] = f["beispiel"]

    zeilen, lauffehler = [], None
    try:
        from sqlalchemy import text as _text

        from app.services.sql_helpers import _get_sql_engine, _resolve_sql_run_params
        fertig, gebunden = _resolve_sql_run_params(sql, werte)
        eng = _get_sql_engine(ctx["mandant_id"])
        with eng.connect() as con:
            zeilen = [dict(r) for r in con.execute(_text(fertig), gebunden)
                      .mappings().fetchmany(30)]
    except Exception as e:
        lauffehler = str(e)[:300]

    erg = {"zeilen": zeilen, "anzahl": len(zeilen), "sql": sql,
           "spalten": [{"name": c} for c in (eingabe.get("spalten") or [])]
                      or [{"name": k} for k in (zeilen[0].keys() if zeilen else [])],
           "felder": [{"label": f["label"], "typ": FELDTYPEN[f["typ"]]["label"],
                       "name": f["name"], "beispiel": f.get("beispiel")} for f in felder],
           "beispielwerte": {k: v for k, v in werte.items() if k not in ("von", "bis")},
           "zeitraum": {"von": von, "bis": bis}}

    if luecken:
        erg["befund"] = " ".join(luecken)
    elif lauffehler:
        erg["befund"] = f"Probelauf mit den Beispielwerten fehlgeschlagen: {lauffehler}"
    elif not zeilen:
        erg["befund"] = ("Mit den Beispielwerten kommt nichts zurück. Das kann am "
                         "Beispiel liegen und muss kein Fehler sein – prüfe es mit "
                         "einem Wert, den es in den Daten wirklich gibt.")
    return erg


def _app_bauen(db, ctx: dict, eingabe: dict, bisher: dict) -> list:
    from app.models.form import Form
    from app.services.query_builder import erzeugen

    name = (eingabe.get("name") or "").strip()
    if not name:
        raise WerkzeugFehler("Die App braucht einen Namen.")
    sql = (eingabe.get("sql") or "").strip()
    if not sql:
        raise WerkzeugFehler("Für die App gibt es kein SQL.")
    if eingabe.get("fehler"):
        raise WerkzeugFehler("Das erzeugte SQL läuft nicht und wird nicht gebaut: "
                             + str(eingabe["fehler"])[:200])
    luecken = _app_pruefen(eingabe)
    if any("erwartet" in l for l in luecken):
        # Ein ungedeckter Parameter ist kein Schönheitsfehler: die App wäre
        # unbedienbar und meldete es beim Anwender, nicht hier.
        raise WerkzeugFehler(luecken[0])

    spalten = [{"name": c, "typ": "text"} for c in (eingabe.get("spalten") or [])]
    if not spalten:
        raise WerkzeugFehler("Die Abfrage hat keine geprüften Spalten – ohne sie "
                             "bliebe die App leer.")

    m = erzeugen.mapping_bauen(db, name, ctx["project_id"], ctx["mandant_id"],
                               {"sql": sql, "spalten": spalten})
    db.flush()

    felder = _app_felder(eingabe)
    aid = f"act_app_{_schluessel(name, 'app')}"
    schema_felder, zeile = [], 0
    for i, f in enumerate(felder):
        if f["typ"] == "daterange":
            eintrag = {"id": f"f_{f['name']}", "type": "daterange", "name": f["name"],
                       "label": f["label"], "action_ids": [aid],
                       "config": {"param_from": "von", "param_to": "bis",
                                  "default": eingabe.get("zeitraum_preset") or "months_12",
                                  "auto_run": False}}
        else:
            eintrag = {"id": f"f_{f['name']}", "type": f["typ"], "name": f["name"],
                       "label": f["label"], "required": f["pflicht"],
                       "default": "", "placeholder": "",
                       "options": [{"value": o, "label": o} for o in f["optionen"]]}
        eintrag["row"] = i // 3
        eintrag["colSpan"] = 4
        zeile = eintrag["row"]
        schema_felder.append(eintrag)

    schema_felder.append({"id": "f_knopf", "type": "button", "row": zeile + 1,
                          "colSpan": 4, "label": eingabe.get("knopf") or "Anzeigen",
                          "action_id": aid})

    schema = {
        "fields": schema_felder, "layout": [],
        "actions": [{"id": aid, "type": "run_mapping", "mapping_id": m.id,
                     "pipeline_id": None, "label": eingabe.get("knopf") or "Anzeigen"}],
        "widgets": [{"id": "w_app_tab", "type": "table", "label": name,
                     "action_id": aid, "config": {"width": 12, "full_rows": True}}],
        "result_tabs": [{"id": "tab_app", "label": name, "action_ids": [aid]}],
        "show_ai_assistant": False,
    }

    f = Form(name=name, project_id=ctx["project_id"], schema=schema,
             created_by=ctx.get("user_id"))
    db.add(f)
    db.flush()

    bisher["app_form_id"] = f.id
    bisher.setdefault("mapping_ids", []).append(m.id)
    bisher.setdefault("mapping_namen", []).append(m.name)
    # Eine App ist ein eigenes Formular – sie wandert NICHT ins Sammelformular
    # und ist damit auch keine Quelle für den Report-Schritt.
    return [
        {"art": "mapping", "ziel_id": m.id, "erzeugt": True,
         "label": f"Mapping „{name}“ ({len(spalten)} Spalten, "
                  f"{len(felder)} Parameter)"},
        {"art": "form", "ziel_id": f.id, "erzeugt": True,
         "label": f"App „{name}“ mit {len(felder)} Eingabefeld(ern)"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

WERKZEUGE = {
    "nachsehen": {
        "key": "nachsehen", "label": "Vorhandenes prüfen",
        "wofuer": ("Nachsehen, ob ein installiertes Cockpit die Frage schon "
                   "beantwortet. Steht immer ganz vorn, wenn die Frage nach einer "
                   "Standard-Kennzahl klingt (Umsatz, Lager, Retouren, Offene Posten)."),
        "baut_objekte": False,
        "zusammenfassung": lambda e: f"Suche nach „{e.get('suchtext') or ''}“",
        "vorschau": _nachsehen_vorschau,
        "bauen": _nachsehen_bauen,
    },
    "abfrage": {
        "key": "abfrage", "label": "Abfrage über Verkaufsdaten",
        "wofuer": ("Listen und Zählungen über Kunden, Aufträge, Auftragspositionen, "
                   "Rechnungen und Rechnungspositionen mit Bedingungen. Die Körnung "
                   "„Kunde“ findet als einzige auch Nullfälle – Kunden ohne Rechnung, "
                   "ohne Auftrag, ohne Umsatz."),
        "baut_objekte": True,
        "zusammenfassung": _abfrage_zusammenfassung,
        "vorschau": _abfrage_vorschau,
        "bauen": _abfrage_bauen,
    },
    "mapping_frei": {
        "key": "mapping_frei", "label": "Freie Abfrage (SQL)",
        "wofuer": ("Der Rückfall, wenn „abfrage“ die Frage nicht abdeckt: alles "
                   "außerhalb von Kunden, Aufträgen und Rechnungen – Artikel, Lager, "
                   "Bestellungen, Retouren, Zahlungen. Die KI schreibt SQL, das gegen "
                   "die echte Datenbank geprüft und bei Fehlern repariert wird. "
                   "NIEMALS zusätzlich zu „abfrage“ für dieselbe Frage."),
        "baut_objekte": True,
        "zusammenfassung": _sql_zusammenfassung,
        "vorschau": _sql_vorschau,
        "bauen": _sql_bauen,
    },
    "app": {
        "key": "app", "label": "App mit Eingabefeldern",
        "wofuer": ("Eine Maske, in die der Anwender etwas eingibt und die darauf "
                   "antwortet: „gib mir eine Kundennummer und zeig alle Rechnungen "
                   "dazu“. Nur wenn im Wunsch eine EINGABE vorkommt – suchen, "
                   "eingeben, auswählen, nachschlagen. Eine reine Auswertung ohne "
                   "Eingabe ist „abfrage“ oder „mapping_frei“."),
        "baut_objekte": True,
        "zusammenfassung": _app_zusammenfassung,
        "vorschau": _app_vorschau,
        "bauen": _app_bauen,
    },
    "report": {
        "key": "report", "label": "Report zusammenstellen",
        "wofuer": ("Aus den Bausteinen ein eigenes Formular bauen, das man ansehen, "
                   "als PDF erzeugen und veröffentlichen kann. Braucht einen "
                   "Abfrage-Schritt davor oder ausdrücklich gewählte Cockpit-Bausteine."),
        "baut_objekte": True,
        "zusammenfassung": _report_zusammenfassung,
        "vorschau": _report_vorschau,
        "bauen": _report_bauen,
    },
    "zustellplan": {
        "key": "zustellplan", "label": "Per Mail zustellen",
        "wofuer": ("Den Report regelmäßig rechnen und per Mail verschicken – "
                   "Kennzahlen im Text, PDF im Anhang. Immer dann, wenn im Wunsch "
                   "ein Takt vorkommt: täglich, montags, monatlich."),
        "baut_objekte": True,
        "zusammenfassung": _zustellplan_zusammenfassung,
        "vorschau": None,
        "bauen": _zustellplan_bauen,
    },
    "pipeline": {
        "key": "pipeline", "label": "Als Pipeline einplanen",
        "wofuer": ("Die Mappings regelmäßig laufen lassen – für Datenwege, die "
                   "etwas schreiben oder exportieren, nicht bloß anzeigen. Für einen "
                   "Report, der per Mail kommen soll, ist „zustellplan“ richtig, "
                   "nicht dieses Werkzeug."),
        "baut_objekte": True,
        "zusammenfassung": _pipeline_zusammenfassung,
        "vorschau": None,
        "bauen": _pipeline_bauen,
    },
    "warnung": {
        "key": "warnung", "label": "Als Warnung überwachen",
        "wofuer": ("Erst melden, wenn die Abfrage Treffer hat – die Warnung "
                   "erscheint im Monitor und im Warnungs-Baustein. Für „sag mir "
                   "Bescheid, wenn …“."),
        "baut_objekte": True,
        "zusammenfassung": _warnung_zusammenfassung,
        "vorschau": None,
        "bauen": _warnung_bauen,
    },
    "veroeffentlichen": {
        "key": "veroeffentlichen", "label": "Im Portal veröffentlichen",
        "wofuer": ("Den Report unter einer eigenen Adresse für Kollegen ohne "
                   "Editor-Rechte sichtbar machen."),
        "baut_objekte": True,
        "zusammenfassung": _portal_zusammenfassung,
        "vorschau": None,
        "bauen": _portal_bauen,
    },
}

# Reihenfolge, in der Schritte sinnvoll aufeinander folgen. Der Planer darf
# Werkzeuge weglassen, aber nicht umsortieren – ein Zustellplan vor dem Report
# hätte nichts zuzustellen.
REIHENFOLGE = ["nachsehen", "abfrage", "mapping_frei", "app", "report",
               "veroeffentlichen", "zustellplan", "warnung", "pipeline"]


def sortiert(schritte: list) -> list:
    """Bringt die Schritte in die einzig lauffähige Reihenfolge."""
    return sorted(schritte, key=lambda s: REIHENFOLGE.index(s["werkzeug"])
                  if s.get("werkzeug") in REIHENFOLGE else 99)


def get(key: str) -> dict:
    w = WERKZEUGE.get(key)
    if not w:
        raise WerkzeugFehler(f"Unbekanntes Werkzeug „{key}“.")
    return w


def katalog_fuer_ki() -> list:
    """Was die KI über die Werkzeuge wissen muss – ohne Code, ohne Schemata."""
    return [{"key": w["key"], "label": w["label"], "wofuer": w["wofuer"]}
            for k in REIHENFOLGE for w in [WERKZEUGE[k]]]


def zusammenfassen(werkzeug: str, eingabe: dict) -> str:
    """Ein Satz Klartext für den Bauzettel."""
    try:
        fn = get(werkzeug).get("zusammenfassung")
        return fn(eingabe or {}) if fn else ""
    except Exception:                                    # nie den Bauzettel sprengen
        return ""


def _zeitfenster(preset: str | None) -> tuple:
    """Von/bis für eine Vorschau. Bewusst dieselbe Liste wie im Report."""
    from app.services import zeitraum as zr_service

    preset = preset if preset in _zeitraum_keys() else "months_12"
    try:
        z = zr_service.berechne(preset)
        return z["von"], z["bis"]
    except Exception:
        # Der Zeitraum-Dienst ist die Wahrheit; fällt er aus, lieber ein
        # nachvollziehbares Jahresfenster als gar keine Vorschau.
        heute = date.today()
        return (heute - timedelta(days=365)).isoformat(), heute.isoformat()

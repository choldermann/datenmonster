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
REIHENFOLGE = ["nachsehen", "abfrage", "report", "veroeffentlichen",
               "zustellplan", "warnung"]


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

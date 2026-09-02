"""Report-Baukasten: Katalog aller vorhandenen Auswertungs-Bausteine und der
Zusammenbau einer Auswahl zu einem eigenen Formular.

Warum kein neues Report-Format: Ein zusammengeklickter Report IST ein Formular.
Damit erbt er ohne eine Zeile Zusatzarbeit den FormRunner, den PDF-Report, die
Portal-Veröffentlichung, die Drilldowns und die KI-Analyse. Ein eigener Typ
müsste all das nachbauen.

Der Katalog erfindet nichts: Er liest die Widgets der bereits installierten
Cockpits aus der Live-Datenbank. Was dort steht, kann der Anwender wählen.
"""
import copy
import logging
from typing import Optional

from app.models.form import Form

logger = logging.getLogger(__name__)


# Widgets, die an eigener Bedien-Logik hängen und einen Umzug nicht überleben:
# sie bringen eigene Eingabemasken, Unterformulare oder Schreibpfade mit, die
# außerhalb ihres Cockpits ins Leere greifen. Sie werden im Katalog trotzdem
# gezeigt – nur eben gesperrt, damit niemand sie vergeblich sucht.
NICHT_UEBERNEHMBAR = {
    "ean_research":         "Braucht die Recherche-Maske des Stammdaten-Cockpits",
    "hersteller_navigator": "Braucht den Hersteller-Navigator des Stammdaten-Cockpits",
    "kostenstruktur":       "Pflegt die Fixkosten und gehört an ihren Platz",
    "preisautomatik":       "Steuert Preisläufe und gehört an ihren Platz",
}

# Grobe Einteilung für den Typ-Filter der Übersicht.
TYP_GRUPPE = {
    "kpi":        "kachel",
    "table":      "tabelle",
    "bar":        "grafik",
    "line":       "grafik",
    "pie":        "grafik",
    "ai_summary": "analyse",
    "alerts":     "analyse",
    "tasklist":   "analyse",
}

TYP_LABEL = {
    "kpi": "Kachel", "table": "Tabelle", "bar": "Balken", "line": "Verlauf",
    "pie": "Kreis", "ai_summary": "KI-Analyse", "alerts": "Warnungen",
    "tasklist": "Aufgabenliste",
}


def _tab_je_action(schema: dict) -> dict:
    """Ordnet jeder Action-ID den Reiter zu, in dem sie angezeigt wird."""
    zuordnung = {}
    for tab in schema.get("result_tabs") or []:
        for aid in tab.get("action_ids") or []:
            zuordnung.setdefault(aid, {"id": tab.get("id"), "label": tab.get("label")})
    return zuordnung


def build_catalog(db, project_id: Optional[int] = None) -> list:
    """Alle wählbaren Bausteine, gruppiert nach Cockpit und Reiter."""
    q = db.query(Form)
    if project_id is not None:
        q = q.filter(Form.project_id == project_id)

    cockpits = []
    for f in q.order_by(Form.id).all():
        schema = f.schema or {}
        widgets = schema.get("widgets") or []
        if not widgets:
            continue
        # Fertige Reports sind keine Quelle. Sonst stünde jede übernommene
        # Kachel zweimal im Katalog – einmal im Cockpit, einmal im Report – und
        # eine Auswahl daraus zöge eine Kopie der Kopie nach sich.
        if schema.get("report_builder"):
            continue

        actions = {a.get("id"): a for a in (schema.get("actions") or [])}
        tabs = _tab_je_action(schema)

        # Reiter in der Reihenfolge des Cockpits, damit die Übersicht so aussieht
        # wie das Cockpit, aus dem der Anwender die Zahlen kennt.
        gruppen, reihenfolge = {}, []
        for w in widgets:
            typ = w.get("type") or ""
            aid = w.get("action_id")
            tab = tabs.get(aid) or {"id": "_ohne", "label": "Ohne Reiter"}
            key = tab["id"] or "_ohne"
            if key not in gruppen:
                gruppen[key] = {"id": key, "label": tab["label"] or "Ohne Reiter",
                                "eintraege": []}
                reihenfolge.append(key)

            sperre = NICHT_UEBERNEHMBAR.get(typ)
            action = actions.get(aid) or {}
            gruppen[key]["eintraege"].append({
                "form_id":      f.id,
                "widget_id":    w.get("id"),
                "label":        w.get("label") or w.get("id") or "(ohne Titel)",
                "type":         typ,
                "type_label":   TYP_LABEL.get(typ, typ),
                "gruppe":       TYP_GRUPPE.get(typ, "sonstige"),
                "action_id":    aid,
                "mapping_id":   action.get("mapping_id"),
                "uebernehmbar": sperre is None,
                "grund":        sperre,
            })

        cockpits.append({
            "form_id":    f.id,
            "name":       f.name,
            "project_id": f.project_id,
            "reiter":     [gruppen[k] for k in reihenfolge],
            "anzahl":     len(widgets),
        })

    return cockpits


# ── Zusammenbau ──────────────────────────────────────────────────────────────

def _zeitraum_feld(preset: str) -> dict:
    """Der Datumsfilter, den jeder zusammengeklickte Report bekommt.

    auto_run bleibt AUS: sonst startet der Report schon beim Öffnen einen Lauf
    über sämtliche gewählten Mappings, und der Anwender wartet, bevor er
    überhaupt einen Zeitraum gewählt hat.
    """
    return {
        "id": "f_zeitraum",
        "type": "daterange",
        "row": 0,
        "colSpan": 12,
        "label": "Zeitraum",
        "name": "zeitraum",
        "action_ids": [],
        "config": {
            "param_from": "von",
            "param_to": "bis",
            # Der Schlüssel heißt "default" – unter "default_preset" liest ihn
            # die Oberfläche nicht und der Report öffnete ohne Zeitraum.
            "default": preset or "this_month",
            "auto_run": False,
        },
    }


def standardparameter(schema: dict) -> dict:
    """Die Laufparameter, die ein Formular ohne Bedienung mitbringt.

    Der Browser füllt die Filterfelder beim Öffnen mit ihren Vorgaben; ein
    Zeitplan tut das nicht und schickte sonst eine Abfrage ohne ihren
    Plattform- oder Lieferantenfilter los. Deren SQL bindet den Filter über das
    Muster »(:x_empty = 1 OR spalte IN (:x))« – fehlt :x ganz, bleibt der
    Platzhalter ungebunden und die Abfrage liefert **stumm null Zeilen**.
    Genau so verschwanden im ersten Anlauf alle Kennzahlen aus der Montagsmail.

    Mehrfachauswahl ohne Vorgabe heißt „alles" und wird zur leeren Liste.
    Einfachauswahl ohne Vorgabe (z. B. ein Artikel für die Preishistorie) bleibt
    weg – dort ist „nichts gewählt" die richtige Antwort.
    """
    params = {}
    for f in schema.get("fields") or []:
        if f.get("type") == "daterange":
            continue
        pname = f.get("name")
        if not pname:
            continue
        cfg = f.get("config") or {}
        if f.get("default") not in (None, ""):
            params[pname] = f.get("default")
        elif cfg.get("multiple"):
            params[pname] = []
    return params


def assemble(db, name: str, entries: list, zeitraum_preset: str = "this_month",
             project_id: Optional[int] = None, bestehend: Optional[dict] = None) -> dict:
    """Baut aus gewählten Katalog-Einträgen ein Formular-Schema.

    entries: [{form_id, widget_id}, …] in der Reihenfolge, in der der Anwender
    sie gewählt hat.

    bestehend: das Schema eines Reports, der nachbearbeitet wird. Bausteine, die
    darin schon stecken und weiterhin gewählt sind, werden **aus dem Report
    übernommen, nicht neu aus dem Cockpit geholt**. Sonst verlöre der Anwender
    bei jeder Änderung der Auswahl alles, was er am Report von Hand nachgezogen
    hat – umbenannte Beschriftungen, angepasste Nachkommastellen, Hinweistexte.

    Gibt {schema, project_id, uebersprungen} zurück; das Speichern macht der
    Aufrufer, damit diese Funktion testbar bleibt.
    """
    if not entries:
        raise ValueError("Keine Einträge gewählt")

    # Quell-Formulare einmal laden statt je Eintrag.
    form_ids = {int(e["form_id"]) for e in entries}
    quellen = {f.id: f for f in db.query(Form).filter(Form.id.in_(form_ids)).all()}
    fehlend = form_ids - set(quellen)
    if fehlend:
        raise ValueError(f"Cockpit(s) nicht gefunden: {sorted(fehlend)}")

    # Ein Report darf nicht aus zwei Projekten stammen: die Mappings hingen dann
    # an verschiedenen Verbindungen und der Report zeigte stumm die Zahlen zweier
    # Betriebe nebeneinander.
    projekte = {quellen[i].project_id for i in form_ids}
    if len(projekte) > 1:
        raise ValueError("Einträge aus verschiedenen Projekten lassen sich nicht "
                         "zu einem Report verbinden")
    ziel_projekt = project_id if project_id is not None else next(iter(projekte))

    # Was der bestehende Report schon hat, nach Herkunft aufgeschlüsselt.
    alt_widgets: dict = {}       # (form_id, quell_widget_id) -> widget-dict
    alt_actions: dict = {}       # ziel_action_id -> action-dict
    if bestehend:
        for h in (bestehend.get("report_builder") or {}).get("entries") or []:
            wid_im_report = h.get("ziel_widget_id")
            treffer = next((w for w in (bestehend.get("widgets") or [])
                            if w.get("id") == wid_im_report), None)
            if treffer:
                alt_widgets[(int(h["form_id"]), h["widget_id"])] = treffer
        alt_actions = {a.get("id"): a for a in (bestehend.get("actions") or [])}

    neue_actions: dict = {}      # ziel_action_id -> action-dict
    herkunft: dict = {}          # ziel_action_id -> (form_id, quell_action_id)
    id_map: dict = {}            # (form_id, quell_action_id) -> ziel_action_id
    tabs: dict = {}              # form_id -> tab-dict
    tab_reihenfolge: list = []
    widgets: list = []
    herkunft_liste: list = []
    uebersprungen: list = []

    for e in entries:
        fid, wid = int(e["form_id"]), e["widget_id"]
        f = quellen[fid]
        schema = f.schema or {}
        w = next((x for x in (schema.get("widgets") or []) if x.get("id") == wid), None)
        if not w:
            uebersprungen.append({"form_id": fid, "widget_id": wid,
                                  "grund": "Baustein nicht mehr vorhanden"})
            continue
        if w.get("type") in NICHT_UEBERNEHMBAR:
            uebersprungen.append({"form_id": fid, "widget_id": wid,
                                  "grund": NICHT_UEBERNEHMBAR[w["type"]]})
            continue

        # Die Herkunft steht immer im Quell-Cockpit: im Report zeigt action_id
        # bereits auf die (womöglich umbenannte) Ziel-ID und taugt hier nicht.
        quell_aid = w.get("action_id")
        action = next((a for a in (schema.get("actions") or [])
                       if a.get("id") == quell_aid), None)

        # Die im Report gepflegte Fassung schlägt die Vorlage aus dem Cockpit –
        # sonst wären von Hand nachgezogene Beschriftungen bei jeder
        # Auswahländerung wieder weg.
        vorhanden = alt_widgets.get((fid, wid))
        w = copy.deepcopy(vorhanden if vorhanden is not None else w)

        if action:
            ziel_aid = quell_aid
            # Gleiche Action-ID aus einem ANDEREN Cockpit: umbenennen. Ohne das
            # überschriebe die zweite die erste und der Report zeigte unter dem
            # Namen der einen Kachel die Zahlen der anderen – genau der Fehler,
            # der schon einmal Einkaufszahlen in die GF-Kacheln geschrieben hat.
            if ziel_aid in herkunft and herkunft[ziel_aid] != (fid, quell_aid):
                ziel_aid = f"f{fid}_{quell_aid}"
            if ziel_aid not in neue_actions:
                a = copy.deepcopy(action)
                a["id"] = ziel_aid
                neue_actions[ziel_aid] = a
                herkunft[ziel_aid] = (fid, quell_aid)
            id_map[(fid, quell_aid)] = ziel_aid
            w["action_id"] = ziel_aid
        else:
            ziel_aid = quell_aid

        # Widget-IDs müssen im Zielformular eindeutig sein.
        basis_wid = w.get("id") or "w"
        ziel_wid = basis_wid
        if any(x.get("id") == ziel_wid for x in widgets):
            ziel_wid = f"f{fid}_{basis_wid}"
        w["id"] = ziel_wid

        # Kacheln aus verschiedenen Cockpits fluchten nur, wenn sie dieselbe
        # Breite haben – im Bestand stehen dort 3 und 4 nebeneinander.
        cfg = w.setdefault("config", {})
        if w.get("type") == "kpi":
            cfg["width"] = 3
        elif not cfg.get("width"):
            cfg["width"] = 12

        widgets.append(w)
        # Herkunft festhalten: nur damit lässt sich der Baukasten später mit der
        # bisherigen Auswahl wieder öffnen. Aus dem fertigen Schema allein wäre
        # sie nicht mehr abzuleiten (Widget-IDs werden bei Kollision umbenannt).
        herkunft_liste.append({"form_id": fid, "widget_id": wid,
                               "ziel_widget_id": ziel_wid})

        if fid not in tabs:
            tabs[fid] = {"id": f"tab_f{fid}", "label": f.name or f"Cockpit {fid}",
                         "action_ids": []}
            tab_reihenfolge.append(fid)
        if ziel_aid and ziel_aid not in tabs[fid]["action_ids"]:
            tabs[fid]["action_ids"].append(ziel_aid)

    if not widgets:
        raise ValueError("Kein übernehmbarer Baustein in der Auswahl")

    # Die Filterfelder der Quell-Cockpits müssen mitwandern. Ohne den
    # Plattform- oder Lieferantenfilter bleibt sein Platzhalter im SQL
    # ungebunden und die Kachel zeigt stumm nichts an.
    felder = [_zeitraum_feld(zeitraum_preset)]
    bekannte_namen = set()
    for fid in tab_reihenfolge:
        for feld in (quellen[fid].schema or {}).get("fields") or []:
            if feld.get("type") == "daterange":
                continue          # den Zeitraum stellt der Report selbst
            pname = feld.get("name")
            if not pname or pname in bekannte_namen:
                continue          # gleicher Parameter aus zwei Cockpits: einmal reicht
            bekannte_namen.add(pname)
            feld = copy.deepcopy(feld)
            feld["id"] = f"f{fid}_{feld.get('id') or pname}"
            # Neu anordnen: die Felder stammen aus verschiedenen Cockpits und
            # trügen sonst alle dieselbe Zeilennummer mit Spaltenbreiten, die
            # zusammen über die Zeile hinauslaufen. Drei pro Zeile.
            i = len(felder) - 1
            feld["row"] = 1 + i // 3
            feld["colSpan"] = 4
            # Verweise auf Actions umschreiben; was nicht mitgewandert ist, fliegt raus.
            if feld.get("action_ids"):
                feld["action_ids"] = [id_map[(fid, a)] for a in feld["action_ids"]
                                      if (fid, a) in id_map]
            # Reiter-Sichtbarkeit bezog sich auf die Reiter des Quell-Cockpits,
            # die es hier nicht gibt – sonst wäre das Feld nie sichtbar.
            (feld.get("config") or {}).pop("visible_tabs", None)
            felder.append(feld)

    schema = {
        "fields":      felder,
        "layout":      [],
        "actions":     list(neue_actions.values()),
        "widgets":     widgets,
        "result_tabs": [tabs[fid] for fid in tab_reihenfolge],
        "show_ai_assistant": False,
        # Der Bauzettel: Herkunft jedes Bausteins plus die Zeitraum-Vorgabe.
        # Damit kann der Baukasten den Report später zum Nachbessern öffnen,
        # ohne dass der Anwender je den Formular-Designer sehen muss.
        "report_builder": {
            "entries": herkunft_liste,
            "zeitraum_preset": zeitraum_preset or "this_month",
        },
    }
    return {"schema": schema, "project_id": ziel_projekt,
            "uebersprungen": uebersprungen}

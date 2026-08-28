"""Ergänzt das GF-Cockpit um die Rechnungskorrekturen (echte Gutschriften).

Bisher zog das Cockpit nur stornierte Rechnungen ab (dad97ce). Echte
Gutschriften – der Kunde bekommt Geld zurück, der Beleg bleibt gültig – standen
weiterhin ungekürzt im Umsatz. Das sind rund 0,5 % Umsatz.

Wie beim Storno bleibt die Hauptkennzahl unangetastet und bekommt zwei Kacheln
daneben: „davon gutgeschrieben" und „Umsatz nach Korrekturen". So bleibt der
Abgleich mit JTLs Statistik möglich und die kaufmännisch richtige Zahl ist
trotzdem sichtbar.

PERIODENZUORDNUNG WIE JTL: Eine Korrektur zählt in den Zeitraum der
BEZUGSRECHNUNG, nicht in den ihrer eigenen Erstellung. Gegen PPS 2026 geprüft –
JTL meldet 3.519,71, unsere Abfrage 3.526,72; die Differenz von 7,01 ist eine
einzelne Gutschriftposition ohne Rechnungsbezug, die JTL nicht mitzählt. Wir
zählen sie mit: über alle Jahre summieren sich diese bezugslosen Positionen bei
HaKo auf −24.355 € (Skonto-Gegenbuchungen), sie wegzulassen würde die
Gutschriften deutlich zu hoch ausweisen.

Warum `Rechnung.tRechnung` und nicht `vRechnung`: der Storno-Filter-Patch
(doku/storno_filter_patch.py) schreibt jede vRechnung-Bindung um und würde die
Bezugsrechnung in eine gefilterte Unterabfrage einschließen – dann fiele eine
Korrektur zu einer stornierten Rechnung auf ihr eigenes Datum zurück statt
herauszufallen. Der Storno-Ausschluss steht hier bewusst von Hand im WHERE.

Anwenden:
    docker cp backend/korrektur_kachel.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/korrektur_kachel.py --anwenden
    python3 backend/korrektur_kachel.py --template templates/jtl_gf_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"

# `ISNULL(GR.nStorno,0) = 0` erledigt zwei Dinge auf einmal: es lässt Korrekturen
# zu stornierten Rechnungen heraus (die Rechnung steckt ohnehin nicht im Umsatz)
# und trifft dank ISNULL trotzdem die Gutschriften ohne Bezugsrechnung – die
# gibt es (je 6 Stück in beiden Datenbanken), sie fallen auf ihr eigenes Datum
# und ihre eigene Plattform zurück.
_RUMPF = """
     FROM dbo.tgutschrift G{pos}
     LEFT JOIN Rechnung.tRechnung GR ON GR.kRechnung = G.kRechnung
     WHERE ISNULL(G.nStorno, 0) = 0
       AND ISNULL(G.nStornoTyp, 0) <> 1   /* nStornoTyp = 1 ist die Storno-Gutschrift, die hängt am Storno */
       AND ISNULL(GR.nStorno, 0) = 0
       AND (:plattform_empty = 1 OR COALESCE(GR.kPlattform, G.kPlattform) IN (SELECT nPlattform FROM dbo.tPlattform WHERE nTyp IN (:plattform)))
       AND COALESCE(GR.dErstellt, G.dErstellt) >= {von}
       AND COALESCE(GR.dErstellt, G.dErstellt) < {bis}"""

POS_JOIN = "\n     JOIN dbo.tGutschriftPos GP ON GP.tGutschrift_kGutschrift = G.kGutschrift"
JETZT   = {"von": ":von", "bis": "DATEADD(DAY, 1, :bis)"}
VORJAHR = {"von": "DATEADD(YEAR, -1, :von)",
           "bis": "DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis))"}

def _teil(auswahl, zeitraum, pos_join, alias):
    return (f"    (SELECT {auswahl}"
            + _RUMPF.format(pos=pos_join, **zeitraum)
            + f") AS {alias}")

_SUMME = "CAST(ISNULL(SUM(GP.nAnzahl * GP.fVKNetto), 0) AS DECIMAL(18,2))"
KORREKTUR_SQL = ",\n" + ",\n".join([
    _teil(_SUMME, JETZT,   POS_JOIN, "KorrekturWert"),
    _teil(_SUMME, VORJAHR, POS_JOIN, "KorrekturWertVJ"),
    _teil("COUNT(DISTINCT G.kGutschrift)", JETZT, "", "KorrekturAnzahl"),
])

# Die Differenz muss eine Ebene höher gebildet werden - ein Alias aus demselben
# SELECT ist in SQL Server nicht referenzierbar.
HUELLE_KOPF = """SELECT k.*,
    CAST(k.Umsatz   - k.KorrekturWert   AS DECIMAL(18,2)) AS UmsatzNachKorrektur,
    CAST(k.UmsatzVJ - k.KorrekturWertVJ AS DECIMAL(18,2)) AS UmsatzNachKorrekturVJ
FROM (
"""
HUELLE_FUSS = "\n) k"

NEUE_FELDER = [("KorrekturWert", "float"), ("KorrekturWertVJ", "float"),
               ("KorrekturAnzahl", "int"),
               ("UmsatzNachKorrektur", "float"), ("UmsatzNachKorrekturVJ", "float")]

# b28d913 hat die Storno-Felder hier nicht nachgetragen; da die Liste ohnehin
# angefasst wird, kommt sie gleich vollständig in Ordnung.
FEHLENDE_OUTPUT_FELDER = ["StornoWert", "StornoWertVJ", "StornoAnzahl"]

_HINWEIS_KORREKTUR = (
    "Echte Gutschriften ohne Storno – der Beleg bleibt gültig, der Kunde bekommt "
    "Geld zurück. Im Umsatz oben noch NICHT abgezogen. Eine Korrektur zählt in den "
    "Zeitraum der Rechnung, auf die sie sich bezieht, nicht in den ihrer eigenen "
    "Erstellung – so rechnet JTL auch.")
_HINWEIS_NETTO = (
    "Umsatz abzüglich der Rechnungskorrekturen: die kaufmännisch belastbare Zahl. "
    "Der Umsatz oben entspricht der Zahl aus JTLs Statistik (abzüglich Storno).")

KACHELN = [
    {
        "id": "w_kpi_korrektur",
        "type": "kpi",
        "label": "davon gutgeschrieben",
        "action_id": "act_overview_kpi",
        "config": {
            "width": 4,
            "column": "KorrekturWert",
            "aggregation": "first",
            "prefix": "€ ",
            "suffix": "",
            "decimals": 2,
            "compare_column": "KorrekturWertVJ",
            "compare_label": "Vorjahr",
            # Mehr Gutschriften sind schlechter – ohne invert_delta färbte ein
            # Anstieg grün.
            "invert_delta": True,
            "breakdown": [{"label": "Rechnungskorrekturen", "column": "KorrekturAnzahl"}],
            "hint": _HINWEIS_KORREKTUR,
        },
    },
    {
        "id": "w_kpi_umsatz_netto",
        "type": "kpi",
        "label": "Umsatz nach Korrekturen",
        "action_id": "act_overview_kpi",
        "config": {
            "width": 4,
            "column": "UmsatzNachKorrektur",
            "aggregation": "first",
            "prefix": "€ ",
            "suffix": "",
            "decimals": 2,
            "compare_column": "UmsatzNachKorrekturVJ",
            "compare_label": "Vorjahr",
            "invert_delta": False,
            "hint": _HINWEIS_NETTO,
        },
    },
]


def sql_ergaenzen(sql: str) -> str:
    if "KorrekturWert" in sql:
        return sql                                  # schon vorhanden
    anker = ") AS StornoAnzahl"
    if anker not in sql:
        raise SystemExit("Anker ') AS StornoAnzahl' nicht gefunden – erst kachel.py anwenden")
    return HUELLE_KOPF + sql.replace(anker, anker + KORREKTUR_SQL, 1) + HUELLE_FUSS


def felder_ergaenzen(fields: list) -> list:
    hat = {f.get("target_field") for f in fields}
    for name, typ in NEUE_FELDER:
        if name in hat:
            continue
        fields.append({"source_field": name, "target_field": name, "target_type": typ,
                       "source_dataset_id": "__sql__sql1",
                       "transformer": {"type": "direct", "source_field": name}})
    return fields


def output_felder_ergaenzen(node: dict) -> None:
    of = node.get("output_fields")
    if not of:
        return                                      # leer heißt „alle Spalten"
    for name in FEHLENDE_OUTPUT_FELDER + [n for n, _ in NEUE_FELDER]:
        if name not in of:
            of.append(name)


def widgets_ergaenzen(widgets: list) -> list:
    # Hinter „davon storniert": Storno, Gutschrift und der bereinigte Umsatz
    # stehen damit als Dreiergruppe in einer Zeile – die Brücke zur JTL-Zahl
    # liest sich von links nach rechts.
    idx = next((i for i, w in enumerate(widgets) if w.get("id") == "w_kpi_storno"), None)
    stelle = idx + 1 if idx is not None else len(widgets)
    for kachel in KACHELN:
        if any(w.get("id") == kachel["id"] for w in widgets):
            continue
        widgets.insert(stelle, json.loads(json.dumps(kachel)))
        stelle += 1
    return widgets


def mapping_patchen(nodes: list, targets: list) -> None:
    nodes[0]["sql"] = sql_ergaenzen(nodes[0]["sql"])
    output_felder_ergaenzen(nodes[0])
    targets[0]["fields"] = felder_ergaenzen(targets[0].get("fields") or [])


def bericht(nodes, targets, widgets, wo):
    print(f"{wo}: KorrekturWert im SQL: {'KorrekturWert' in nodes[0]['sql']}, "
          f"{len(targets[0]['fields'])} Zielfelder, {len(widgets)} Widgets, "
          f"Kacheln: {[k['id'] for k in KACHELN if any(w.get('id') == k['id'] for w in widgets)]}")


def datenbank(anwenden: bool):
    c = sqlite3.connect(DB)
    sn, tg = c.execute("select sql_nodes, targets from mappings where id=1").fetchone()
    nodes, targets = json.loads(sn), json.loads(tg)
    mapping_patchen(nodes, targets)

    sch = json.loads(c.execute("select schema from forms where id=1").fetchone()[0])
    sch["widgets"] = widgets_ergaenzen(sch.get("widgets") or [])
    bericht(nodes, targets, sch["widgets"], "Mapping 1 / Formular 1")

    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    c.execute("update mappings set sql_nodes=?, targets=? where id=1",
              (json.dumps(nodes, ensure_ascii=False), json.dumps(targets, ensure_ascii=False)))
    c.execute("update forms set schema=? where id=1", (json.dumps(sch, ensure_ascii=False),))
    c.commit()
    print("\ngeschrieben.")


def template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    m = next(x for x in t["mappings"] if x["name"] == "Cockpit – Kennzahlen")
    mapping_patchen(m["sql_nodes"], m["targets"])
    form = t["forms"][0]
    form["schema"]["widgets"] = widgets_ergaenzen(form["schema"].get("widgets") or [])
    t["version"] = "2.7"
    bericht(m["sql_nodes"], m["targets"], form["schema"]["widgets"], pfad)

    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("\ngeschrieben.")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        datenbank(anwenden)

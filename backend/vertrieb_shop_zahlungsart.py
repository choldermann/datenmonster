"""Vertriebs-Cockpit: Onlineshop-Aufträge nach Zahlungsart, mit Drilldown.

Neue Tabelle im Reiter „Auftragseingang". Klick auf eine Zahlungsart → die Kunden,
die so im Shop bestellt haben → deren Aufträge → Positionen.

Onlineshop = Plattform vom Typ 2 (tPlattform.nTyp), nicht eine feste Plattform-
nummer – so greift es auch in anderen Wawis. Werte wie im übrigen Auftragseingang:
netto aus tAuftragEckdaten, ohne Stornos, Zeitraum und Plattform-Filter des Formulars.

Die Drilldown-Ebenen bekommen nur den Schlüssel ihrer eigenen Zeile, nicht den der
Ebene davor. Die Kundenzeile trägt deshalb „kKunde|kZahlungsart", sonst zeigte der
zweite Klick alle Shop-Aufträge des Kunden statt nur die mit dieser Zahlungsart.

Anwenden:
    docker compose cp backend/drilldown_werkzeug.py backend:/tmp/
    docker compose cp backend/vertrieb_drilldowns.py backend:/tmp/
    docker compose cp backend/vertrieb_shop_zahlungsart.py backend:/tmp/
    docker compose exec backend python /tmp/vertrieb_shop_zahlungsart.py --anwenden
    python3 backend/vertrieb_shop_zahlungsart.py --template templates/jtl_vertrieb_cockpit.json --anwenden
"""
import sys, json, sqlite3
sys.path.insert(0, "/tmp")
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import drilldown_werkzeug as dw
from drilldown_werkzeug import mit_sammelzeile, widgets_verdrahten
from vertrieb_drilldowns import PLATTFORM, AUFTRAG_FELDER, auftraege

FORM_ID = 3
TAB_ID = "tab_ve_eingang"
NACH_ACTION = "act_ve_plattform"
ACTION_ID = "act_ve_shop_zahlart"
WIDGET_ID = "w_ve_tbl_shop_zahlart"
TITEL = "Onlineshop-Aufträge nach Zahlungsart"

SHOP = "A.kPlattform IN (SELECT nPlattform FROM dbo.tPlattform WHERE nTyp = 2)"
ZAHLART = "ISNULL(Z.cName, '(ohne Zahlungsart)')"
BASIS = f"""FROM Verkauf.tAuftrag A
JOIN Verkauf.tAuftragEckdaten E ON E.kAuftrag = A.kAuftrag
LEFT JOIN dbo.tZahlungsart Z ON Z.kZahlungsart = A.kZahlungsart
WHERE A.nType = 1 AND A.nStorno = 0 AND {SHOP}
  AND A.dErstellt >= :von AND A.dErstellt < DATEADD(DAY, 1, :bis)
  AND {PLATTFORM}"""

BASIS_KUNDE = BASIS.replace("WHERE", """LEFT JOIN Verkauf.vAuftragRechnungsadresse RA ON RA.kAuftrag = A.kAuftrag
LEFT JOIN dbo.tKunde K ON K.kKunde = A.kKunde
WHERE""", 1)

UEBERSICHT_FELDER = ["Zahlungsart", "Auftraege", "Kunden", "Auftragseingang",
                     "Anteil", "AvgAuftrag"]
KUNDEN_FELDER = ["Sortierung", "KundenNr", "Kunde", "Auftraege", "Wert",
                 "LetzterAuftrag", "Schluessel"]

KUNDENNAME = """LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''),
            ISNULL(RA.cVorname, '') + ' ' + ISNULL(RA.cName, ''))))"""

NEUE_MAPPINGS = {
    "m_ve_shop_zahlart": {
        "name": "Vertrieb – Onlineshop-Aufträge nach Zahlungsart",
        "felder": UEBERSICHT_FELDER,
        "sql": f"""SELECT {ZAHLART} AS Zahlungsart,
    COUNT(*) AS Auftraege,
    COUNT(DISTINCT A.kKunde) AS Kunden,
    CAST(ISNULL(SUM(E.fWertNetto), 0) AS DECIMAL(18,2)) AS Auftragseingang,
    CAST(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0) AS DECIMAL(5,1)) AS Anteil,
    CAST(ISNULL(AVG(E.fWertNetto), 0) AS DECIMAL(18,2)) AS AvgAuftrag
{BASIS}
GROUP BY {ZAHLART}
ORDER BY COUNT(*) DESC""",
    },
    "m_ve_shop_zahlart_kunden": {
        "name": "Vertrieb – Shop-Kunden der Zahlungsart (Detail)",
        "felder": KUNDEN_FELDER,
        "sql": f"""WITH kunde AS (
    SELECT ISNULL(A.kKunde, 0) AS kKunde, ISNULL(A.kZahlungsart, 0) AS kZahlungsart,
        MAX(K.cKundenNr) AS KundenNr,
        MAX({KUNDENNAME}) AS Kunde,
        COUNT(*) AS Auftraege, SUM(E.fWertNetto) AS Wert, MAX(A.dErstellt) AS Letzter,
        ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, SUM(E.fWertNetto) DESC) AS rn
    {BASIS_KUNDE}
      AND {ZAHLART} = :zahlungsart
    GROUP BY ISNULL(A.kKunde, 0), ISNULL(A.kZahlungsart, 0)
)
""" + mit_sammelzeile(
            "kunde",
            """KundenNr, Kunde, Auftraege, CAST(Wert AS DECIMAL(18,2)) AS Wert,
    CONVERT(char(10), Letzter, 104) AS LetzterAuftrag,
    CAST(kKunde AS VARCHAR(20)) + '|' + CAST(kZahlungsart AS VARCHAR(20)) AS Schluessel""",
            """'', CONCAT('… ', COUNT(*), ' weitere Kunden'), SUM(Auftraege),
    CAST(SUM(Wert) AS DECIMAL(18,2)), '', ''""",
            "Auftraege DESC, Wert DESC"),
    },
    "m_ve_shop_zahlart_auftraege": {
        "name": "Vertrieb – Shop-Aufträge des Kunden je Zahlungsart (Detail)",
        "felder": AUFTRAG_FELDER,
        "sql": auftraege(
            f"A.nType = 1 AND A.nStorno = 0 AND {SHOP}",
            """ISNULL(A.kKunde, 0) = TRY_CONVERT(INT, LEFT(:schluessel, CHARINDEX('|', :schluessel) - 1))
      AND ISNULL(A.kZahlungsart, 0) = TRY_CONVERT(INT, SUBSTRING(:schluessel, CHARINDEX('|', :schluessel) + 1, 20))"""),
    },
}

BESTEHENDE = {"m_auftrag_pos": "Cockpit – Auftragspositionen (Detail)"}
EBENE2 = None
DRILLDOWNS = {
    WIDGET_ID: ("m_ve_shop_zahlart_kunden", "Zahlungsart", "zahlungsart",
                "Shop-Kunden mit dieser Zahlungsart", [
                    {"mapping": "m_ve_shop_zahlart_auftraege", "param": "schluessel",
                     "key_column": "Schluessel", "title": "Shop-Aufträge des Kunden"},
                    {"mapping": "m_auftrag_pos", "param": "kAuftrag",
                     "key_column": "kAuftrag", "title": "Positionen des Auftrags"},
                ]),
}


def einhaengen(schema: dict, uebersicht_id) -> bool:
    """Action, Widget und Reiter-Eintrag ergänzen. False, wenn schon alles da ist."""
    geaendert = False
    actions = schema["actions"]
    if not any(a["id"] == ACTION_ID for a in actions):
        pos = next(i for i, a in enumerate(actions) if a["id"] == NACH_ACTION) + 1
        actions.insert(pos, {"id": ACTION_ID, "type": "run_mapping",
                             "mapping_id": uebersicht_id, "pipeline_id": None,
                             "label": TITEL})
        geaendert = True
    widgets = schema["widgets"]
    if not any(w["id"] == WIDGET_ID for w in widgets):
        pos = next(i for i, w in enumerate(widgets) if w.get("action_id") == NACH_ACTION) + 1
        widgets.insert(pos, {"id": WIDGET_ID, "type": "table", "label": TITEL,
                             "action_id": ACTION_ID, "config": {"width": 6}})
        geaendert = True
    tab = next(t for t in schema["result_tabs"] if t["id"] == TAB_ID)
    if ACTION_ID not in tab["action_ids"]:
        tab["action_ids"].insert(tab["action_ids"].index(NACH_ACTION) + 1, ACTION_ID)
        geaendert = True
    return geaendert


def ids_aus_db(c) -> dict:
    ids = {k: c.execute("select id from mappings where name=?", (d["name"],)).fetchone()
           for k, d in NEUE_MAPPINGS.items()}
    ids.update({k: c.execute("select id from mappings where name=?", (n,)).fetchone()
                for k, n in BESTEHENDE.items()})
    return {k: v[0] for k, v in ids.items() if v}


def main():
    anwenden = "--anwenden" in sys.argv
    mod = sys.modules[__name__]
    if "--template" in sys.argv:
        pfad = sys.argv[sys.argv.index("--template") + 1]
        with open(pfad, encoding="utf-8") as f:
            t = json.load(f)
        if einhaengen(t["forms"][0]["schema"], "m_ve_shop_zahlart"):
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
            print(f"{pfad}: Action/Widget ergänzt")
        # Mappings, Drilldown und Versionssprung macht das Werkzeug.
        dw.anwenden_template(mod, pfad, anwenden)
        if anwenden:
            # In der Vorlage heißt das Positions-Mapping m_ve_pos_detail;
            # „m_auftrag_pos" gibt es dort nicht (traf auch die Drilldowns aus
            # vertrieb_drilldowns.py – bei einer Neuinstallation waren sie tot).
            with open(pfad, encoding="utf-8") as f:
                roh = f.read()
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(roh.replace('"m_auftrag_pos"', '"m_ve_pos_detail"'))
        return
    dw.anwenden_db(mod, FORM_ID, anwenden)
    if not anwenden:
        return
    c = sqlite3.connect(dw.DB)
    ids = ids_aus_db(c)
    sch = json.loads(c.execute("select schema from forms where id=?", (FORM_ID,)).fetchone()[0])
    einhaengen(sch, ids["m_ve_shop_zahlart"])
    n = widgets_verdrahten(sch["widgets"], DRILLDOWNS, None, lambda k: ids[k])
    c.execute("update forms set schema=? where id=?",
              (json.dumps(sch, ensure_ascii=False), FORM_ID))
    c.commit()
    print(f"Formular {FORM_ID}: Widget eingehängt, {n} Drilldown gesetzt")


if __name__ == "__main__":
    main()

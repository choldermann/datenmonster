"""Räumt den Auftragsbestand im Vertriebs-Cockpit auf.

Geprüft am 2026-08-29 an PPS und HaKo. Die Storno-Frage war unbegründet –
`nStorno = 0` ist gesetzt und `Verkauf.tAuftragStorno` bestätigt es (alle 111
Stornos tragen auch nStorno=1). Vier andere Dinge stimmten nicht:

1. Die Legende der Spalte „Lieferstatus" (5/3/0) traf die echten Werte nicht.
   In offenen Aufträgen kommen nur 1, 2 und 4 vor – alle fielen in den
   ELSE-Zweig, die Spalte zeigte für ALLE 260 Zeilen „in Bearbeitung".
   Den Wert 0 gibt es gar nicht, und 3 heißt nicht „teilgeliefert", sondern
   zu 100 % kommissioniert. Bedeutungen aus den Daten abgeleitet
   (Versanddatum + Anteil gelieferter Menge je Status).

2. „OffenerWert" ist der offene ZAHLBETRAG (= fWertBrutto - fZahlung -
   fGutschrift, stimmt bei 16.946 von 16.946 Aufträgen), nicht die offene
   Lieferung. Neben „Wert" in einer Liste „Offene Aufträge" liest sich das
   als Restlieferwert. Jetzt ehrlich benannt, plus der echte offene
   Warenwert aus tAuftragPositionEckdaten.fAnzahlOffen.

3. 53 MUSTER-Vorgänge (kVorgangsstatus = 2, siehe Verkauf.tVorgangsstatus)
   zählten mit – alle mit Auftragswert 0,00. PPS: 260 statt 207 Aufträge.

4. Der Bestand ist überwiegend Altbestand: nur 9 von 260 PPS-Aufträgen sind
   jünger als 30 Tage, 141 sind 1–3 Jahre alt. „Überfällig" (Alert
   vertrieb_backlog, kritisch) zeigte auf Liefertermine bis zurück zu 2022.
   Laufend/Altbestand/ohne Termin werden jetzt getrennt ausgewiesen, und
   „Überfällig" zählt nur noch Termine aus den letzten 12 Monaten.

Anwenden – Template UND Live-DB, sonst kehrt der alte Stand bei der nächsten
Installation zurück (siehe backend/firmenzusatz.py, gleiches Muster):

    python backend/auftragsbestand.py --templates --generatoren
    python backend/auftragsbestand.py --templates --generatoren --anwenden

    docker cp backend/auftragsbestand.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/auftragsbestand.py --live
    docker exec datenmonster-backend python /tmp/auftragsbestand.py --live --anwenden
"""
import argparse
import glob
import json
import os
import sqlite3

DB = "/app/uploads/datenmonster.db"

BACKLOG_WHERE = "A.nType = 1 AND A.nStorno = 0 AND A.nKomplettAusgeliefert = 0"
# Einzeilig: im Drilldown-Generator steht das WHERE in einem einzeiligen
# Python-String – ein Zeilenumbruch zerreißt ihn (compile() fängt das ab).
MUSTER = " AND ISNULL(A.kVorgangsstatus, 1) <> 2"

LIEFERSTATUS_ALT = ("CASE E.nLieferstatus WHEN 5 THEN 'komplett geliefert' WHEN 3 THEN 'teilgeliefert'\n"
                    "         WHEN 0 THEN 'offen' ELSE 'in Bearbeitung' END AS Lieferstatus")
# Bedeutungen aus den Daten abgeleitet: Versanddatum vorhanden? welcher Anteil
# der Menge ist geliefert? Der Wert 0 kommt in der Wawi nicht vor.
LIEFERSTATUS_NEU = ("CASE E.nLieferstatus\n"
                    "         WHEN 1 THEN 'nichts geliefert'\n"
                    "         WHEN 2 THEN 'teilgeliefert, nicht versendet'\n"
                    "         WHEN 3 THEN 'kommissioniert, nicht versendet'\n"
                    "         WHEN 4 THEN 'teilversendet'\n"
                    "         WHEN 5 THEN 'komplett versendet'\n"
                    "         WHEN 6 THEN 'komplett geliefert'\n"
                    "         WHEN 7 THEN 'abgeschlossen (Sonderfall)'\n"
                    "         ELSE 'unbekannt (' + CAST(E.nLieferstatus AS VARCHAR(10)) + ')'\n"
                    "    END AS Lieferstatus")

OFFEN_ALT = "CAST(ISNULL(E.fOffenerWert, 0) AS DECIMAL(18,2)) AS OffenerWert"
# fOffenerWert ist der offene Zahlbetrag; der offene Warenwert kommt aus den
# Positionen und ist das, was man in einer Liste „Offene Aufträge" erwartet.
OFFEN_NEU = ("CAST(ISNULL(P.OffenerWarenwert, 0) AS DECIMAL(18,2)) AS OffenerWarenwert,\n"
             "    CAST(ISNULL(E.fOffenerWert, 0) AS DECIMAL(18,2)) AS OffenerZahlbetrag")

RA_JOIN = "LEFT JOIN Verkauf.vAuftragRechnungsadresse RA ON RA.kAuftrag = A.kAuftrag"
POS_JOIN = RA_JOIN + """
LEFT JOIN (
    SELECT PE.kAuftrag, SUM(PE.fAnzahlOffen * POS.fVkNetto) AS OffenerWarenwert
    FROM Verkauf.tAuftragPositionEckdaten PE
    JOIN Verkauf.tAuftragPosition POS ON POS.kAuftragPosition = PE.kAuftragPosition
    WHERE PE.fAnzahlOffen > 0
    GROUP BY PE.kAuftrag
) P ON P.kAuftrag = A.kAuftrag"""

M63_SQL = """SELECT
    COUNT(*) AS OffeneAuftraege,
    CAST(ISNULL(SUM(E.fWertNetto), 0) AS DECIMAL(18,2)) AS Auftragsbestand,
    CAST(ISNULL(AVG(CAST(DATEDIFF(DAY, A.dErstellt, GETDATE()) AS FLOAT)), 0) AS DECIMAL(18,1)) AS AvgAlterTage,
    -- „Überfällig" zählt nur laufende Vorgänge. Ein Liefertermin, der über ein
    -- Jahr zurückliegt, ist eine Karteileiche und kein Alarm – sonst meldet die
    -- Regel vertrieb_backlog auf ewig dieselben Altfälle (HaKo: alle 6 davon).
    SUM(CASE WHEN A.dVoraussichtlichesLieferdatum < GETDATE()
              AND A.dVoraussichtlichesLieferdatum >= DATEADD(YEAR, -1, GETDATE())
             THEN 1 ELSE 0 END) AS Ueberfaellig,
    SUM(CASE WHEN A.dVoraussichtlichesLieferdatum < DATEADD(YEAR, -1, GETDATE())
             THEN 1 ELSE 0 END) AS UeberfaelligAlt,
    SUM(CASE WHEN A.dVoraussichtlichesLieferdatum IS NULL THEN 1 ELSE 0 END) AS OhneLiefertermin,
    SUM(CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 90 THEN 1 ELSE 0 END) AS AuftraegeLaufend,
    CAST(ISNULL(SUM(CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) <= 90
        THEN E.fWertNetto END), 0) AS DECIMAL(18,2)) AS BestandLaufend,
    SUM(CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) > 90 THEN 1 ELSE 0 END) AS AuftraegeAlt,
    CAST(ISNULL(SUM(CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) > 90
        THEN E.fWertNetto END), 0) AS DECIMAL(18,2)) AS BestandAlt,
    CAST(ISNULL(SUM(CASE WHEN DATEDIFF(DAY, A.dErstellt, GETDATE()) > 30
        THEN E.fWertNetto END), 0) AS DECIMAL(18,2)) AS WertAelter30
FROM Verkauf.tAuftrag A
JOIN Verkauf.tAuftragEckdaten E ON E.kAuftrag = A.kAuftrag
WHERE A.nType = 1 AND A.nStorno = 0 AND A.nKomplettAusgeliefert = 0
      AND ISNULL(A.kVorgangsstatus, 1) <> 2"""


def patche(sql):
    """Liefert (neues_sql, liste_der_angewandten_schritte)."""
    if not isinstance(sql, str) or "Verkauf.tAuftrag" not in sql:
        return sql, []
    schritte = []

    # Das Backlog-KPI-Mapping wird ganz ersetzt – es bekommt neue Kennzahlen.
    if "AS OffeneAuftraege" in sql and BACKLOG_WHERE in sql:
        return M63_SQL, ["KPIs neu (laufend/Alt/ohne Termin, Überfällig gedeckelt)"]

    if BACKLOG_WHERE in sql and "kVorgangsstatus" not in sql:
        sql = sql.replace(BACKLOG_WHERE, BACKLOG_WHERE + MUSTER)
        schritte.append("MUSTER ausgeschlossen")
    if LIEFERSTATUS_ALT in sql:
        sql = sql.replace(LIEFERSTATUS_ALT, LIEFERSTATUS_NEU)
        schritte.append("Lieferstatus-Legende")
    if OFFEN_ALT in sql and "OffenerWarenwert" not in sql:
        sql = sql.replace(OFFEN_ALT, OFFEN_NEU)
        sql = sql.replace(RA_JOIN, POS_JOIN, 1)
        schritte.append("offener Warenwert + Zahlbetrag getrennt")
    return sql, schritte


def durchlaufen(knoten, treffer):
    if isinstance(knoten, str):
        neu, s = patche(knoten)
        treffer.extend(s)
        return neu
    if isinstance(knoten, list):
        return [durchlaufen(x, treffer) for x in knoten]
    if isinstance(knoten, dict):
        return {k: durchlaufen(v, treffer) for k, v in knoten.items()}
    return knoten


def templates(anwenden):
    wurzel = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "templates")
    gesamt = 0
    for pfad in sorted(glob.glob(os.path.join(wurzel, "*.json"))):
        doc = json.load(open(pfad, encoding="utf-8"))
        treffer = []
        doc = durchlaufen(doc, treffer)
        if not treffer:
            continue
        gesamt += len(treffer)
        print(f"  {os.path.basename(pfad)}")
        for t in treffer:
            print(f"      - {t}")
        if anwenden:
            with open(pfad, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
    return gesamt


def generatoren(anwenden):
    hier = os.path.dirname(os.path.abspath(__file__))
    gesamt = 0
    for pfad in sorted(glob.glob(os.path.join(hier, "*_drilldowns.py"))):
        roh = open(pfad, encoding="utf-8").read()
        neu, s = patche(roh)
        if not s:
            continue
        compile(neu, pfad, "exec")
        gesamt += len(s)
        print(f"  {os.path.basename(pfad)}: {', '.join(s)}")
        if anwenden:
            open(pfad, "w", encoding="utf-8").write(neu)
    return gesamt


def live(anwenden):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    gesamt = 0
    for r in c.execute("SELECT id, name, sql_nodes FROM mappings").fetchall():
        if not r["sql_nodes"]:
            continue
        treffer = []
        knoten = durchlaufen(json.loads(r["sql_nodes"]), treffer)
        if not treffer:
            continue
        gesamt += len(treffer)
        print(f"  M{r['id']:<4} {(r['name'] or '')[:52]:52} {', '.join(treffer)}")
        if anwenden:
            c.execute("UPDATE mappings SET sql_nodes = ? WHERE id = ?",
                      (json.dumps(knoten, ensure_ascii=False), r["id"]))
    if anwenden:
        c.commit()
    c.close()
    return gesamt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--templates", action="store_true")
    p.add_argument("--generatoren", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--anwenden", action="store_true")
    a = p.parse_args()
    if not (a.templates or a.generatoren or a.live):
        p.error("--templates, --generatoren und/oder --live angeben")
    n = 0
    if a.templates:
        print("== Templates ==")
        n += templates(a.anwenden)
    if a.generatoren:
        print("== Drilldown-Generatoren ==")
        n += generatoren(a.anwenden)
    if a.live:
        print("== Live-Mappings ==")
        n += live(a.anwenden)
    print(f"\n{n} Änderungen {'angewandt' if a.anwenden else 'gefunden (Trockenlauf)'}")

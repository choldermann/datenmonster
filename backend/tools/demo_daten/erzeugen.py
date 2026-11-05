"""Synthetische Demo-DB komplett neu erzeugen.

    python -m tools.demo_daten.erzeugen --pruefen   # nur Spaltennamen prüfen
    python -m tools.demo_daten.erzeugen             # leeren, erzeugen, JTL rechnen lassen

Zufall mit festem Startwert: jeder Lauf ergibt dieselbe Firma.
"""
import random
import sys
import time

from tools.demo_daten import bewegungen, leeren, stammdaten
from tools.demo_daten.schreiber import Schreiber

SAAT = 20261105

REIHENFOLGE = [
    "dbo.tWarenLagerEingang", "dbo.tLieferantenBestellung", "dbo.tLieferantenBestellungPos",
    "dbo.tEingangsrechnung", "dbo.tEingangsrechnungPos",
    "Verkauf.tAuftrag", "Verkauf.tAuftragAdresse", "Verkauf.tAuftragPosition", "Verkauf.tAuftragStorno",
    "dbo.tLieferschein", "dbo.tLieferscheinPos", "dbo.tLieferscheinEckdaten", "dbo.tVersand",
    "dbo.tWarenLagerAusgang",
    "Rechnung.tRechnung", "Rechnung.tRechnungAdresse", "Rechnung.tRechnungPosition", "Verkauf.tAuftragRechnung",
    "dbo.tgutschrift", "dbo.tGutschriftPos", "dbo.tRMRetoureAbholAdresse", "dbo.tRMRetoure", "dbo.tRMRetourePos", "dbo.tRMStatusVerlauf",
    "dbo.tZahlung",
]


def fremdverweise_umbiegen(w):
    """JTL liest Benutzer aus der Hauptdatenbank "eazybusiness" (fest im Code von
    57 Views/Prozeduren). Auf dem Testserver ist das eine ECHTE Datenbank – die
    Demo hätte dort fremde Mitarbeiternamen eingelesen. In unserer Demo-DB zeigen
    die Objekte deshalb auf die eigene dbo.tBenutzer."""
    import re
    muster = re.compile(r"(\[?eazybusiness\]?)\.(\[?dbo\]?)\.", re.I)
    objekte = w.cur.execute(
        "SELECT o.object_id, SCHEMA_NAME(o.schema_id) + '.' + o.name, m.definition FROM sys.sql_modules m "
        "JOIN sys.objects o ON o.object_id = m.object_id WHERE m.definition LIKE '%eazybusiness%'").fetchall()
    ok, fehler = 0, []
    for _oid, name, d in objekte:
        if not muster.search(d):
            continue
        # erstes CREATE VIEW/PROC/FUNCTION/TRIGGER – davor stehen manchmal Kommentare
        neu = re.sub(r"\bCREATE\s+(VIEW|PROC|PROCEDURE|FUNCTION|TRIGGER)\b", r"CREATE OR ALTER \1",
                     muster.sub(r"\2.", d), count=1, flags=re.I)
        try:
            w.cur.execute(neu); w.con.commit(); ok += 1
        except Exception as e:
            w.con.rollback(); fehler.append(f"{name}: {str(e)[:120]}")
    print(f"   {ok} Objekte auf dbo.tBenutzer umgebogen" + (f", {len(fehler)} nicht: " + "; ".join(fehler[:5]) if fehler else ""))
    rest = w.cur.execute("SELECT COUNT(*) FROM sys.sql_expression_dependencies WHERE referenced_database_name = 'eazybusiness'").fetchone()[0]
    print(f"   verbleibende Verweise auf die Datenbank eazybusiness: {rest}")


def jtl_rechnen(w):
    """Abgeleitete Werte so berechnen, wie JTL es selbst tut."""
    schritte = [
        ("Lagerbestand", "DECLARE @a dbo.TYPE_spUpdateLagerbestand; INSERT @a SELECT kArtikel FROM dbo.tArtikel; "
                         "EXEC dbo.spUpdateLagerbestand @Artikel = @a"),
        ("Artikelhistorie", "EXEC dbo.spArtikelHistoryNachrechnen @kArtikel = 0, @nNurOhneLagerbesand = 0"),
        ("Gutschrift-Eckdaten", "DECLARE @g dbo.TYPE_spGutschriftEckdatenBerechnen; INSERT @g SELECT kGutschrift FROM dbo.tgutschrift; "
                                "EXEC dbo.spGutschriftEckdatenBerechnen @Gutschriften = @g"),
        ("Rechnungs-Eckdaten", "DECLARE @r Rechnung.TYPE_spRechnungEckdatenBerechnen; INSERT @r SELECT kRechnung FROM Rechnung.tRechnung; "
                               "EXEC Rechnung.spRechnungEckdatenBerechnen @Rechnungen = @r"),
        ("Auftrags-Eckdaten", "DECLARE @o Verkauf.TYPE_spAuftragEckdatenBerechnen; INSERT @o SELECT kAuftrag FROM Verkauf.tAuftrag; "
                              "EXEC Verkauf.spAuftragEckdatenBerechnen @Auftrag = @o"),
    ]
    # Zahlungen auf den Cent an JTLs Rundung angleichen (JTL rundet je Position),
    # danach Rechnungen und Aufträge noch einmal rechnen lassen.
    schritte.append(("Zahlungen auf JTL-Brutto angleichen",
                     "UPDATE z SET z.fBetrag = e.fVkBruttoGesamt FROM dbo.tZahlung z "
                     "JOIN Rechnung.tRechnungEckdaten e ON e.kRechnung = z.kRechnung "
                     "WHERE z.fBetrag > 0 AND ABS(z.fBetrag - e.fVkBruttoGesamt) < 0.10"))
    schritte += [s for s in schritte if s[0] in ("Rechnungs-Eckdaten", "Auftrags-Eckdaten")]
    # Lagerbestand zuletzt: "in Aufträgen" stammt aus den Auftrags-Eckdaten
    schritte.append(schritte[0])
    for name, sql in schritte:
        t0 = time.time()
        try:
            w.cur.execute("SET NOCOUNT ON; " + sql)
            while w.cur.nextset():
                pass
            w.con.commit()
            print(f"   JTL rechnet {name}: {time.time() - t0:.0f}s")
        except Exception as e:
            w.con.rollback()
            print(f"   ⚠ {name} fehlgeschlagen: {str(e)[:300]}")


def main():
    pruefen = "--pruefen" in sys.argv
    if not pruefen:
        print("1) leeren"); leeren.main(True)
    w = Schreiber(nur_pruefen=pruefen)
    r = random.Random(SAAT)
    t0 = time.time()
    print("2) Stammdaten"); s = stammdaten.anlegen(w, r)
    print("3) Simulation"); sim = bewegungen.Sim(w, r, s); rows = sim.lauf()
    print(f"   {time.time() - t0:.0f}s, " + ", ".join(f"{t.split('.')[-1]} {len(v):,}" for t, v in rows.items()))
    print("4) schreiben")
    for t in REIHENFOLGE + [t for t in rows if t not in REIHENFOLGE]:
        if rows.get(t):
            t1 = time.time()
            w.schreiben(t, rows[t])
            if not pruefen:
                print(f"   {t}: {len(rows[t]):,} ({time.time() - t1:.0f}s)")
    if pruefen:
        print("\n".join(w.fehler) or "Spalten: keine Fehler"); return
    if sim.inaktiv:
        w.sql("UPDATE dbo.tArtikel SET cAktiv = 'N' WHERE kArtikel IN (" + ",".join(map(str, sim.inaktiv)) + ")")
    # EK am Artikel wie in JTL fortschreiben: Durchschnitt des Restbestands,
    # letzter EK aus dem jüngsten Wareneingang (sonst sähe man die Sprünge nie)
    w.sql("""UPDATE A SET A.fLetzterEK = ISNULL(x.ek, A.fLetzterEK), A.fEKNetto = ISNULL(y.ek, A.fEKNetto)
             FROM dbo.tArtikel A
             OUTER APPLY (SELECT TOP 1 W.fEKEinzel AS ek FROM dbo.tWarenLagerEingang W
                          WHERE W.kArtikel = A.kArtikel AND W.kBuchungsart = 10 ORDER BY W.dErstellt DESC) x
             OUTER APPLY (SELECT SUM(W.fAnzahlAktuell * W.fEKEinzel) / NULLIF(SUM(W.fAnzahlAktuell), 0) AS ek
                          FROM dbo.tWarenLagerEingang W WHERE W.kArtikel = A.kArtikel AND W.fAnzahlAktuell > 0) y""")
    # Pflegefehler "VK unter EK" erst nach dem Fortschreiben setzen
    w.sql("UPDATE dbo.tArtikel SET fVKNetto = ROUND(fEKNetto * 0.85, 2) WHERE kArtikel = ?", s["unter_ek"])
    print("5) Fremdverweise"); fremdverweise_umbiegen(w)
    print("6) JTL rechnen"); jtl_rechnen(w)
    print(f"fertig nach {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

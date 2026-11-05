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
    "dbo.tgutschrift", "dbo.tGutschriftPos", "dbo.tRMRetoure", "dbo.tRMRetourePos",
    "dbo.tZahlung",
]


def jtl_rechnen(w):
    """Abgeleitete Werte so berechnen, wie JTL es selbst tut."""
    schritte = [
        ("Lagerbestand", "DECLARE @a dbo.TYPE_spUpdateLagerbestand; INSERT @a SELECT kArtikel FROM dbo.tArtikel; "
                         "EXEC dbo.spUpdateLagerbestand @Artikel = @a"),
        ("Artikelhistorie", "EXEC dbo.spArtikelHistoryNachrechnen @kArtikel = NULL, @nNurOhneLagerbesand = 0"),
        ("Gutschrift-Eckdaten", "DECLARE @g dbo.TYPE_spGutschriftEckdatenBerechnen; INSERT @g SELECT kGutschrift FROM dbo.tgutschrift; "
                                "EXEC dbo.spGutschriftEckdatenBerechnen @Gutschriften = @g"),
        ("Rechnungs-Eckdaten", "DECLARE @r Rechnung.TYPE_spRechnungEckdatenBerechnen; INSERT @r SELECT kRechnung FROM Rechnung.tRechnung; "
                               "EXEC Rechnung.spRechnungEckdatenBerechnen @Rechnungen = @r"),
        ("Auftrags-Eckdaten", "DECLARE @o Verkauf.TYPE_spAuftragEckdatenBerechnen; INSERT @o SELECT kAuftrag FROM Verkauf.tAuftrag; "
                              "EXEC Verkauf.spAuftragEckdatenBerechnen @Auftrag = @o"),
    ]
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
    print("5) JTL rechnen"); jtl_rechnen(w)
    print(f"fertig nach {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

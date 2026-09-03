"""Projektwissen für Lexware Office. Aufruf:
   docker compose cp doku/lexware_wissen_seed.py backend:/tmp/lx.py
   docker compose exec backend python /tmp/lx.py
"""
from app.core.database import SessionLocal
from app.models.ai_memory import AiMemoryKnowledge as K

EINTRAEGE = [
 ("table", "Lexware Office – Belegliste (voucherlist) als Datenquelle",
  "Lexware Office hat KEINE Datenbank, nur eine REST-Schnittstelle "
  "(https://api.lexware.io, Bearer-Token, 2 Anfragen je Sekunde). Die einzige "
  "Massenabfrage ist /v1/voucherlist; sie VERLANGT die Parameter voucherType und "
  "voucherStatus – 'any' für beide liefert alles (die Dokumentation nennt sie "
  "fälschlich freiwillig). Antwortpfad ist 'content', Seiten zählen ab 0 mit "
  "'page'/'size'. In Datenmonster liegt die Liste als Dataset 'Lexware Belegliste'; "
  "Auswertungen laufen als Transform-SQL darauf und damit in SQLITE-Dialekt, nicht "
  "T-SQL: kein TOP, sondern LIMIT; Datumsteile mit substr(voucherDate,1,10); "
  "Tagesdifferenzen mit julianday(). Spalten: id, voucherType, voucherStatus, "
  "voucherNumber, voucherDate, createdDate, updatedDate, contactId, contactName, "
  "totalAmount, currency, archived, dueDate, openAmount."),

 ("rule", "Lexware Office – Belegarten, Status und die drei Fallen",
  "voucherType: invoice (Ausgangsrechnung), purchaseinvoice (Eingangsrechnung, "
  "also AUSGABEN), quotation (Angebot), orderconfirmation (Auftragsbestätigung), "
  "deliverynote (Lieferschein). voucherStatus: draft, open, paid, paidoff, overdue, "
  "voided, accepted, rejected, sepadebit.\\n"
  "FALLE 1: voucherStatus='voided' ist STORNIERT und muss aus jeder Summe heraus – "
  "dieselbe Klasse Fehler wie ISNULL(nStorno,0)=0 bei JTL. Ohne den Ausschluss war "
  "der gemessene Umsatz 97.078,90 statt 88.838,96 EUR.\\n"
  "FALLE 2: deliverynote trägt totalAmount 0 und verwässert jeden Durchschnitt – "
  "Belegarten immer ausdrücklich filtern, nie über alle summieren.\\n"
  "FALLE 3: openAmount kommt fertig mit, aber NUR bei invoice und purchaseinvoice; "
  "bei Angeboten und Lieferscheinen ist es leer. Offene Posten kennen bewusst kein "
  "Zeitfenster: eine Forderung von 2024 ist heute offen, auch wenn der "
  "Berichtszeitraum der laufende Monat ist.\\n"
  "Einnahmen-Ausgaben-Rechnung ist möglich, weil purchaseinvoice mitgeliefert wird: "
  "Umsatz = SUM(totalAmount) über invoice, Ausgaben = dasselbe über purchaseinvoice, "
  "beide ohne 'voided'."),
]

db = SessionLocal()
neu = akt = 0
for kategorie, titel, inhalt in EINTRAEGE:
    row = db.query(K).filter(K.title == titel).first()
    if row:
        row.content, row.category, row.enabled = inhalt, kategorie, True
        akt += 1
    else:
        db.add(K(scope="global", scope_id=None, category=kategorie, title=titel,
                 content=inhalt, enabled=True, always_include=False))
        neu += 1
db.commit()
print(f"Lexware-Wissen: {neu} neu, {akt} aktualisiert")

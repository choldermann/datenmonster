"""
ZUGFeRD-Ausgang: Prüfung, XML, Einbetten und der Lauf über tInvoice.

Die Quelltabellen liegen hier in SQLite statt auf dem SQL-Server, das FTP-Ziel
ist eine Attrappe. Geprüft wird, was beim Kunden Geld oder Ärger kostet:
falsche Summen werden abgewiesen, ein FTP-Ausfall lässt die Rechnung auf NEU,
ENTWURF wird nie angefasst.

Gegen den offiziellen Validator (Mustang: PDF/A-3 + EN-16931-Schematron) wurden
die Belegarten RECHNUNG, STORNO, KORREKTUR, Reverse Charge und EU-Lieferung
am 16.10.2026 von Hand geprüft – alle gültig.

Lauf:  docker compose exec -T backend python tests/test_zugferd.py
"""
import datetime as dt
import io
import sys
import tempfile
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, "/app")

import sqlalchemy as sa                                   # noqa: E402
from lxml import etree                                    # noqa: E402
from reportlab.pdfgen import canvas                       # noqa: E402
from sqlalchemy.orm import sessionmaker                   # noqa: E402

from app.core.portal_zugriff import portal_darf           # noqa: E402
from app.models.business_config import BusinessConfig     # noqa: E402
from app.models.zugferd import ZugferdAusgang, ZugferdBeleg  # noqa: E402
from app.services import business_config_service as cfg   # noqa: E402
from app.services import zugferd_pdf as zp                # noqa: E402
from app.services import zugferd_service as dienst        # noqa: E402
from app.services import zugferd_xml as zx                # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def pdf_bytes():
    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.drawString(72, 750, "Rechnung")
    c.save()
    return b.getvalue()


V = dict(name="EGP Test GmbH", strasse="Musterweg 1", plz="12345", ort="Musterstadt", land="DE",
         ustid="DE123456789", iban="DE02120300000000202051", bic="BYLADEM1001",
         zahlungsbedingungen="Zahlbar innerhalb 14 Tagen.")
KOPF = dict(InvoiceId=1, InvoiceNumber="RE-1", InvoiceType="RECHNUNG",
            InvoiceDate=dt.date(2026, 10, 16), BuyerName="Kunde AG", BuyerCity="Köln",
            BuyerZip="50667", BuyerStreet="Domplatz 1", BuyerCountry="DE",
            TotalNet=D("85.90"), TotalTax=D("12.00"), TotalGross=D("97.90"))
POS = [dict(LineNumber=1, Name="Papier", Quantity=D("10"), Unit="Stk", UnitPrice=D("4.99"),
            LineNet=D("49.90"), VatCategory="S", VatRate=D("19")),
       dict(LineNumber=2, Name="Buch", Quantity=D("2"), Unit="Stk", UnitPrice=D("20"),
            LineNet=D("36.00"), VatCategory="S", VatRate=D("7"))]
# 49,90 × 19 % = 9,481 → 9,48 ; 36 × 7 % = 2,52 → 12,00


def fehler_von(kopf, pos, v=V):
    try:
        zx.pruefen(kopf, pos, v)
        return []
    except zx.ZugferdFehler as e:
        return e.fehler


print("── Prüfen und rechnen")
b = zx.pruefen(KOPF, POS, V)
pruefe("Rechnung geht durch", b.brutto == D("97.90") and b.typcode == "380")
pruefe("Stk → H87", b.positionen[0].einheit == "H87")
pruefe("Steuer je Satz", [str(g.steuer) for g in b.steuern] == ["9.48", "2.52"],
       [str(g.steuer) for g in b.steuern])

f = fehler_von(dict(KOPF, TotalTax=D("12.01"), TotalGross=D("97.91")), POS)
pruefe("Cent-Abweichung der Steuer wird abgewiesen", any("je Steuersatz" in x for x in f), f)

f = fehler_von(KOPF, [dict(POS[0], VatCategory="AE", VatRate=D("0"))] , )
pruefe("Reverse Charge ohne Kunden-USt-IdNr. abgewiesen",
       any("BuyerVatId" in x for x in f), f)

kk = dict(KOPF, BuyerCountry="FR", BuyerVatId="FR12345678901",
          TotalNet=D("49.90"), TotalTax=D("0"), TotalGross=D("49.90"))
kp = [dict(POS[0], VatCategory="K", VatRate=D("0"))]
f = fehler_von(kk, kp)
pruefe("EU-Lieferung ohne Lieferdatum abgewiesen", any("DeliveryDate" in x for x in f), f)
pruefe("EU-Lieferung mit Lieferdatum geht durch",
       fehler_von(dict(kk, DeliveryDate=dt.date(2026, 10, 15)), kp) == [])

f = fehler_von(KOPF, [dict(POS[0], Unit="Gebinde"), POS[1]])
pruefe("unbekannte Einheit wird nicht geraten", any("Einheit" in x for x in f), f)

f = fehler_von(dict(KOPF, InvoiceType="STORNO"), POS)
pruefe("Storno ohne Bezug abgewiesen", any("PrecedingInvoiceNumber" in x for x in f), f)

st = [dict(p, Quantity=-p["Quantity"], LineNet=-p["LineNet"]) for p in POS]
b = zx.pruefen(dict(KOPF, InvoiceType="STORNO", PrecedingInvoiceNumber="RE-1",
                    TotalNet=D("-85.90"), TotalTax=D("-12.00"), TotalGross=D("-97.90")), st, V)
pruefe("negatives Storno → 381 mit positiven Beträgen",
       b.typcode == "381" and b.brutto == D("97.90") and b.vorzeichen_gedreht)

rab = [POS[0], POS[1], dict(LineNumber=3, Name="Rabatt", Quantity=D("1"), Unit="psch",
                            UnitPrice=D("-5"), LineNet=D("-5"), VatCategory="S", VatRate=D("19"))]
b = zx.pruefen(dict(KOPF, TotalNet=D("80.90"), TotalTax=D("11.05"), TotalGross=D("91.95")), rab, V)
pruefe("negativer Preis → negative Menge (BR-27)",
       b.positionen[2].preis == D("5") and b.positionen[2].menge == D("-1"))

f = fehler_von(KOPF, POS, dict(V, iban=""))
pruefe("Überweisung ohne IBAN abgewiesen", any("IBAN" in x for x in f), f)

V2 = dict(V, weitere_ustids="ATU12345678, FR12345678901")
b = zx.pruefen(dict(KOPF, SellerVatId="fr 12345678901"), POS, V2)
pruefe("SellerVatId aus der Liste wird genommen", b.verkaeufer["ustid"] == "FR12345678901")
pruefe("… und steht im XML", b"FR12345678901" in zx.baue_xml(b) and b"DE123456789" not in zx.baue_xml(b))
pruefe("ohne SellerVatId gilt die Standardnummer",
       zx.pruefen(KOPF, POS, V2).verkaeufer["ustid"] == "DE123456789")
f = fehler_von(dict(KOPF, SellerVatId="NL999999999B01"), POS, V2)
pruefe("fremde SellerVatId wird abgewiesen", any("SellerVatId" in x for x in f), f)

print("── XML und PDF")
b = zx.pruefen(KOPF, POS, V)
xml = zx.baue_xml(b)
root = etree.fromstring(xml)
ns = zx.NS
pruefe("Profil EN 16931", root.findtext(".//ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
                                        namespaces=ns) == zx.PROFIL_EN16931)
pruefe("Bruttosumme im XML", root.findtext(".//ram:GrandTotalAmount", namespaces=ns) == "97.90")
pdf, warn = zp.einbetten(pdf_bytes(), xml, titel="Rechnung RE-1", autor="EGP")
pruefe("XML steckt als factur-x.xml in der PDF", zp.xml_aus_pdf(pdf) == xml)
pruefe("nicht eingebettete Schrift wird gemeldet", any("Schriften" in w for w in warn), warn)
try:
    zp.einbetten(b"kein pdf", xml, titel="t", autor="a")
    pruefe("Nicht-PDF wird abgewiesen", False)
except zp.PdfFehler:
    pruefe("Nicht-PDF wird abgewiesen", True)
pruefe("Dateiname bereinigt", dienst.dateiname("{nummer}_{kunde}.pdf",
                                               zx.pruefen(dict(KOPF, InvoiceNumber="RE/1",
                                                               CustomerNumber="K 7"), POS, V))
       == "RE_1_K 7.pdf")

print("── Lauf über tInvoice")
quelle = sa.create_engine("sqlite://")
with quelle.begin() as c:
    spalten = ", ".join(f"{s} TEXT" for s in dienst.KOPF_SPALTEN
                        if s not in ("InvoiceId", "PdfFile", "Status", "ZugferdFile"))
    c.execute(sa.text(f"CREATE TABLE tInvoice (InvoiceId INTEGER PRIMARY KEY, {spalten}, "
                      f"PdfFile BLOB, Status TEXT DEFAULT 'ENTWURF')"))
    pspalten = ", ".join(f"{s} TEXT" for s in dienst.POS_SPALTEN if s != "PositionId")
    c.execute(sa.text(f"CREATE TABLE tInvoicePositions (PositionId INTEGER PRIMARY KEY, {pspalten})"))


def rechnung(inv_id, nummer, status, steuer="12.00", brutto="97.90"):
    with quelle.begin() as c:
        k = dict(KOPF, InvoiceId=inv_id, InvoiceNumber=nummer, Status=status,
                 TotalTax=steuer, TotalGross=brutto, PdfFile=pdf_bytes())
        k = {s: (str(v) if isinstance(v, (D, dt.date)) else v) for s, v in k.items()}
        c.execute(sa.text(f"INSERT INTO tInvoice ({', '.join(k)}) VALUES "
                          f"({', '.join(':' + s for s in k)})"), k)
        for p in POS:
            p = {s: str(v) for s, v in dict(p, InvoiceId=inv_id).items()}
            c.execute(sa.text(f"INSERT INTO tInvoicePositions ({', '.join(p)}) VALUES "
                              f"({', '.join(':' + s for s in p)})"), p)


def status(inv_id):
    with quelle.connect() as c:
        return c.execute(sa.text("SELECT Status, StatusMessage, OutputFileName FROM tInvoice "
                                 "WHERE InvoiceId = :i"), {"i": inv_id}).first()


class Ziel:
    def __init__(self, kaputt=False):
        self.dateien, self.kaputt = {}, kaputt

    def ablegen(self, name, daten):
        if self.kaputt:
            raise dienst._ZielFehler("FTP: Verbindung verloren")
        self.dateien[name] = daten


dmdb = sa.create_engine("sqlite://")
for m in (BusinessConfig, ZugferdAusgang, ZugferdBeleg):
    m.__table__.create(dmdb, checkfirst=True)
db = sessionmaker(bind=dmdb)()
dienst.ABLAGE = Path(tempfile.mkdtemp())
a = ZugferdAusgang(id=1, connection_id=10, project_id=10, tabelle_kopf="tInvoice",
                   tabelle_positionen="tInvoicePositions", dateiname_muster="{nummer}.pdf")
db.add(a)
db.commit()

rechnung(1, "RE-1", "NEU")
e = dienst.verarbeiten(db, a, ausloeser="test", engine=quelle, ziel=Ziel())
pruefe("ohne Firmendaten startet kein Lauf", not e["ok"] and "Firmendaten" in e["meldung"], e)
pruefe("… und die Rechnung bleibt NEU", status(1)[0] == "NEU")

for k, v in V.items():
    cfg.set_value(10, db, "zugferd", k, v, 10)
rechnung(2, "RE-2", "NEU", steuer="12.01", brutto="97.91")
rechnung(3, "RE-3", "ENTWURF")
z = Ziel()
e = dienst.verarbeiten(db, a, ausloeser="test", engine=quelle, ziel=z)
pruefe("Lauf: 1 erzeugt, 1 abgewiesen", e["erzeugt"] == 1 and e["fehler"] == 1, e)
pruefe("RE-1 steht auf OK mit Dateiname", tuple(status(1))[::2] == ("OK", "RE-1.pdf"), status(1))
pruefe("RE-1 liegt auf dem FTP mit XML", zp.xml_aus_pdf(z.dateien.get("RE-1.pdf", b"")) is not None)
pruefe("RE-2 FEHLER mit Grund", status(2)[0] == "FEHLER" and "Steuer" in (status(2)[1] or ""),
       status(2))
pruefe("ENTWURF bleibt unangetastet", status(3)[0] == "ENTWURF")
prot = db.query(ZugferdBeleg).order_by(ZugferdBeleg.id).all()
pruefe("Protokoll: ok + fehler", [p.status for p in prot] == ["ok", "fehler"],
       [p.status for p in prot])
pruefe("Kopie im Volume", prot[0].pfad and Path(prot[0].pfad).is_file())

# in Access korrigiert, dann wieder eingereiht
with quelle.begin() as c:
    c.execute(sa.text("UPDATE tInvoice SET TotalTax='12.00', TotalGross='97.90' WHERE InvoiceId=2"))
pruefe("abgewiesene Rechnung wieder einreihen", dienst.erneut_einreihen(quelle, "tInvoice", 2)
       and status(2)[0] == "NEU")
e = dienst.verarbeiten(db, a, ausloeser="test", engine=quelle, ziel=Ziel(kaputt=True))
pruefe("FTP weg → Lauf bricht ab", not e["ok"] and "FTP" in e["meldung"], e)
pruefe("… und die Rechnung geht zurück auf NEU", status(2)[0] == "NEU", status(2))
e = dienst.verarbeiten(db, a, ausloeser="test", engine=quelle, ziel=Ziel())
pruefe("nach der Korrektur geht sie durch", status(2)[0] == "OK", status(2))

print("── Sicherheit")
try:
    dienst.tabelle_pruefen("tInvoice; DROP TABLE x")
    pruefe("Tabellenname mit SQL abgewiesen", False)
except dienst.LaufFehler:
    pruefe("Tabellenname mit SQL abgewiesen", True)
pruefe("Portal erreicht das Widget", portal_darf("GET", "/api/zugferd/belege"))

print()
print("FEHLGESCHLAGEN: " + ", ".join(FEHLER) if FEHLER else "Alle Prüfungen bestanden.")
sys.exit(1 if FEHLER else 0)

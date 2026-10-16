"""ZUGFeRD-/Factur-X-XML (Profil EN 16931) aus Rechnungsdaten bauen.

Eingang sind zwei Zeilenarten, wie sie eine Fremdanwendung (bei EGP: Access) in
tInvoice/tInvoicePositions ablegt, plus die eigenen Firmendaten aus Datenmonster.
Ausgang ist das CII-XML, das in die PDF eingebettet wird (zugferd_pdf.py).

⭐ Rechtlich gilt im Zweifel das XML, nicht das Druckbild. Deshalb rechnet dieses
Modul die Summen selbst nach EN 16931 nach (Steuer je Steuersatz gerundet, nicht
je Position) und vergleicht sie centgenau mit dem, was Access gedruckt hat. Weicht
etwas ab, wird die Rechnung abgewiesen statt verschickt - eine E-Rechnung, deren
XML andere Beträge trägt als die PDF, ist schlimmer als gar keine.

Fehler werden gesammelt, nicht beim ersten abgebrochen: wer in Access nachbessert,
soll alle Ursachen auf einmal sehen.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional

from lxml import etree

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}
PROFIL_EN16931 = "urn:cen.eu:en16931:2017"

# Belegart in tInvoice.InvoiceType → UNTDID 1001
BELEGARTEN = {
    "RECHNUNG": "380",
    "STORNO": "381",        # Gutschrift/Storno: positive Beträge, Bezug auf die Rechnung
    "KORREKTUR": "384",     # Rechnungskorrektur: Bezug auf die Rechnung, Beträge mit Vorzeichen
}

# Steuerkategorien (UNTDID 5305), die wir ausstellen. "O" (nicht steuerbar) fehlt
# bewusst: sie darf mit keiner anderen Kategorie gemischt werden und verbietet die
# eigene USt-IdNr. - bei EGP kommt sie nicht vor, und halb unterstützt wäre sie eine Falle.
KATEGORIEN = {"S", "Z", "E", "AE", "K", "G"}
OHNE_STEUER = {"Z", "E", "AE", "K", "G"}
# Nur diese tragen einen Befreiungsgrund; bei S und Z ist er sogar verboten (BR-S-10, BR-Z-10).
MIT_GRUND = {"E", "AE", "K", "G"}

# Befreiungsgrund, wenn Access keinen eigenen mitgibt. "E" hat keinen: welcher
# Paragraf greift, weiß nur der Aussteller.
BEFREIUNG = {
    "AE": ("VATEX-EU-AE", "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)"),
    "K": ("VATEX-EU-IC", "Steuerfreie innergemeinschaftliche Lieferung"),
    "G": ("VATEX-EU-G", "Steuerfreie Ausfuhrlieferung"),
}

# Gängige Schreibweisen aus Warenwirtschaften → UN/ECE Rec. 20/21.
# Unbekanntes wird NICHT geraten: eine falsche Einheit (Stunde statt Stück)
# steht sonst rechtsgültig in der Rechnung.
EINHEITEN = {
    "stk": "H87", "st": "H87", "stck": "H87", "stück": "H87", "stueck": "H87",
    "pcs": "H87", "pc": "H87", "piece": "H87",
    "x": "C62", "einheit": "C62", "eh": "C62",
    "h": "HUR", "std": "HUR", "stunde": "HUR", "stunden": "HUR",
    "min": "MIN", "minute": "MIN", "minuten": "MIN",
    "tag": "DAY", "tage": "DAY", "d": "DAY",
    "woche": "WEE", "wochen": "WEE", "monat": "MON", "monate": "MON",
    "jahr": "ANN", "jahre": "ANN",
    "kg": "KGM", "g": "GRM", "t": "TNE", "to": "TNE",
    "m": "MTR", "lfm": "MTR", "km": "KMT", "cm": "CMT", "mm": "MMT",
    "m2": "MTK", "m²": "MTK", "qm": "MTK", "m3": "MTQ", "m³": "MTQ", "cbm": "MTQ",
    "l": "LTR", "ltr": "LTR", "liter": "LTR",
    "psch": "LS", "pauschal": "LS", "pausch": "LS",
    "satz": "SET", "set": "SET", "paar": "PR", "pr": "PR",
    "pal": "XPX", "palette": "XPX", "paletten": "XPX",
    "karton": "XCT", "ktn": "XCT", "krt": "XCT",
    "rolle": "XRO", "rollen": "XRO", "rl": "XRO",
    "kiste": "XBX", "box": "XBX", "paket": "XPK", "pak": "XPK", "pkt": "XPK",
    "bogen": "XST", "blatt": "XST",
}

CENT = Decimal("0.01")


class ZugferdFehler(Exception):
    """Die Rechnung lässt sich so nicht als E-Rechnung ausstellen."""

    def __init__(self, fehler: list[str]):
        self.fehler = fehler
        super().__init__("; ".join(fehler))


@dataclass
class Position:
    nr: str
    name: str
    menge: Decimal
    einheit: str
    preis: Decimal
    basismenge: Decimal
    netto: Decimal
    kategorie: str
    satz: Decimal
    artikelnummer: str = ""
    kunden_artikelnummer: str = ""
    beschreibung: str = ""
    befreiungsgrund: str = ""
    nachlass: Decimal = Decimal("0")     # >0 Abschlag, <0 Zuschlag (aus Menge×Preis − Netto)


@dataclass
class Steuergruppe:
    kategorie: str
    satz: Decimal
    basis: Decimal
    steuer: Decimal
    grund: str = ""
    grund_code: str = ""


@dataclass
class Beleg:
    """Geprüfte, gerechnete Rechnung – alles, was ins XML geht."""
    nummer: str
    art: str
    typcode: str
    datum: _dt.date
    waehrung: str
    kopf: dict
    verkaeufer: dict
    positionen: list[Position]
    steuern: list[Steuergruppe]
    summe_positionen: Decimal
    steuer_gesamt: Decimal
    brutto: Decimal
    anzahlung: Decimal
    zahlbetrag: Decimal
    vorzeichen_gedreht: bool = False
    warnungen: list[str] = field(default_factory=list)


# ── kleine Helfer ─────────────────────────────────────────────────────────────

def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _dez(v, feld: str, fehler: list[str], pflicht: bool = True) -> Optional[Decimal]:
    if v is None or _s(v) == "":
        if pflicht:
            fehler.append(f"{feld} fehlt")
        return None
    try:
        # Access/ODBC liefert Decimal oder float; Text mit Komma kommt aus
        # Eigenbau-Tabellen auch vor.
        return Decimal(str(v).replace(",", ".")) if not isinstance(v, Decimal) else v
    except (InvalidOperation, ValueError):
        fehler.append(f"{feld}: '{v}' ist keine Zahl")
        return None


def _datum(v, feld: str, fehler: list[str], pflicht: bool = False) -> Optional[_dt.date]:
    if v is None or _s(v) == "":
        if pflicht:
            fehler.append(f"{feld} fehlt")
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    t = _s(v)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.datetime.strptime(t[:19], fmt).date()
        except ValueError:
            continue
    fehler.append(f"{feld}: '{v}' ist kein Datum")
    return None


def runden(b: Decimal) -> Decimal:
    """Kaufmännisch auf Cent – so rechnet auch die Steuer nach EN 16931."""
    return b.quantize(CENT, rounding=ROUND_HALF_UP)


def einheit_code(roh: str) -> Optional[str]:
    t = _s(roh)
    if not t:
        return "H87"
    if t.lower() in EINHEITEN:
        return EINHEITEN[t.lower()]
    # Steht schon ein Code da (C62, HUR, XPX …), nehmen wir ihn, wie er ist.
    if 2 <= len(t) <= 3 and t.isalnum() and t.upper() == t:
        return t
    return None


def ustid_liste(roh) -> list[str]:
    """„ATU123, FR456; NL789“ → ['ATU123', 'FR456', 'NL789']"""
    return [t.replace(" ", "").upper() for t in re.split(r"[,;\n]+", _s(roh)) if t.strip()]


def euro(b: Decimal) -> str:
    return f"{b:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def _ustid_ok(v: str) -> bool:
    t = v.replace(" ", "")
    return len(t) >= 4 and t[:2].isalpha() and t[2:].isalnum()


# ── Prüfen und rechnen ────────────────────────────────────────────────────────

def pruefen(kopf: dict, positionen: list[dict], verkaeufer: dict) -> Beleg:
    """Prüft eine Rechnung gegen EN 16931 und rechnet sie nach.

    kopf/positionen: Zeilen aus tInvoice/tInvoicePositions (Spaltennamen wie im
    SQL-Skript), verkaeufer: Firmendaten aus Datenmonster.
    """
    f: list[str] = []
    w: list[str] = []
    k = dict(kopf)

    nummer = _s(k.get("InvoiceNumber"))
    if not nummer:
        f.append("InvoiceNumber fehlt")
    art = _s(k.get("InvoiceType")).upper() or "RECHNUNG"
    typcode = BELEGARTEN.get(art)
    if not typcode:
        f.append(f"InvoiceType '{art}' unbekannt – erlaubt: {', '.join(BELEGARTEN)}")
        typcode = "380"
    datum = _datum(k.get("InvoiceDate"), "InvoiceDate", f, pflicht=True)
    waehrung = (_s(k.get("Currency")) or "EUR").upper()
    if len(waehrung) != 3 or not waehrung.isalpha():
        f.append(f"Currency '{waehrung}' ist kein ISO-Währungscode")

    # Verkäufer: Pflicht nach EN 16931 (BR-06, BR-08, BR-09) - ohne sie ist
    # nicht einmal klar, wer die Rechnung stellt.
    for schl, label in (("name", "Firmenname"), ("strasse", "Straße"),
                        ("plz", "PLZ"), ("ort", "Ort"), ("land", "Land")):
        if not _s(verkaeufer.get(schl)):
            f.append(f"Firmendaten: {label} fehlt (im Formular „Firmendaten“ pflegen)")
    v_ustid = _s(verkaeufer.get("ustid")).replace(" ", "").upper()
    v_stnr = _s(verkaeufer.get("steuernummer"))

    # Mehrere Registrierungen (EGP hat je Land eine eigene USt-IdNr.): welche gilt,
    # weiß nur Access - das Land des Kunden allein entscheidet es nicht. Access
    # gibt sie je Rechnung in SellerVatId mit; wir nehmen nur Nummern, die in den
    # Firmendaten stehen, damit kein Tippfehler auf die Rechnung kommt.
    eigene = sorted({v_ustid} | set(ustid_liste(verkaeufer.get("weitere_ustids"))) - {""})
    gewaehlt = _s(k.get("SellerVatId")).replace(" ", "").upper()
    if gewaehlt:
        if gewaehlt not in eigene:
            f.append(f"SellerVatId {gewaehlt} ist keine der eigenen USt-IdNrn. in den Firmendaten"
                     + (f" ({', '.join(eigene)})" if eigene else ""))
        else:
            v_ustid = gewaehlt
    verkaeufer = dict(verkaeufer, ustid=v_ustid)

    # Käufer
    if not _s(k.get("BuyerName")):
        f.append("BuyerName fehlt")
    k_land = (_s(k.get("BuyerCountry")) or "DE").upper()
    if len(k_land) != 2:
        f.append(f"BuyerCountry '{k_land}' ist kein ISO-Ländercode (DE, AT, FR …)")
    if not _s(k.get("BuyerCity")):
        f.append("BuyerCity fehlt")
    k_ustid = _s(k.get("BuyerVatId")).replace(" ", "")
    if k_ustid and not _ustid_ok(k_ustid):
        f.append(f"BuyerVatId '{k_ustid}' sieht nicht wie eine USt-IdNr. aus (Länderkürzel + Nummer)")

    if art in ("STORNO", "KORREKTUR") and not _s(k.get("PrecedingInvoiceNumber")):
        f.append(f"{art.title()} ohne PrecedingInvoiceNumber – auf welche Rechnung bezieht sie sich?")

    if not positionen:
        f.append("Keine Positionen in tInvoicePositions")

    # Positionen
    pos: list[Position] = []
    for i, p in enumerate(positionen, 1):
        wo = f"Position {_s(p.get('LineNumber')) or i}"
        pf: list[str] = []
        menge = _dez(p.get("Quantity"), f"{wo}: Quantity", pf)
        preis = _dez(p.get("UnitPrice"), f"{wo}: UnitPrice", pf)
        netto = _dez(p.get("LineNet"), f"{wo}: LineNet", pf)
        basis = _dez(p.get("PriceBaseQuantity"), f"{wo}: PriceBaseQuantity", pf, pflicht=False) \
            or Decimal("1")
        satz = _dez(p.get("VatRate"), f"{wo}: VatRate", pf)
        kat = (_s(p.get("VatCategory")) or "S").upper()
        if kat not in KATEGORIEN:
            pf.append(f"{wo}: VatCategory '{kat}' unbekannt – erlaubt: {', '.join(sorted(KATEGORIEN))}")
        einheit = einheit_code(p.get("Unit"))
        if einheit is None:
            pf.append(f"{wo}: Einheit '{_s(p.get('Unit'))}' unbekannt – UN/ECE-Code eintragen "
                      f"(H87 Stück, HUR Stunde, KGM kg, LS pauschal …)")
        name = _s(p.get("Name"))
        if not name:
            pf.append(f"{wo}: Name fehlt")
        if basis is not None and basis <= 0:
            pf.append(f"{wo}: PriceBaseQuantity muss größer als 0 sein")
        f.extend(pf)
        if pf:
            continue

        if kat == "S" and satz <= 0:
            f.append(f"{wo}: Kategorie S (normal besteuert) braucht einen Steuersatz über 0")
        if kat in OHNE_STEUER and satz != 0:
            f.append(f"{wo}: Kategorie {kat} verlangt Steuersatz 0, eingetragen ist {satz}")

        # Ein negativer Preis ist in EN 16931 verboten (BR-27). Eine Rabattzeile
        # „1 × −50 €“ wird deshalb zu „−1 × 50 €“ - gleicher Betrag, gültige Form.
        if preis < 0:
            preis, menge = -preis, -menge

        netto = runden(netto)
        roh = runden(menge * preis / basis)
        pos.append(Position(
            nr=_s(p.get("LineNumber")) or str(i), name=name, menge=menge, einheit=einheit,
            preis=preis, basismenge=basis, netto=netto, kategorie=kat, satz=satz,
            artikelnummer=_s(p.get("ArticleNumber")),
            kunden_artikelnummer=_s(p.get("BuyerArticleNumber")),
            beschreibung=_s(p.get("Description")),
            befreiungsgrund=_s(p.get("ExemptionReason")),
            nachlass=roh - netto,
        ))

    # Kopfsummen laut Access
    a_netto = _dez(k.get("TotalNet"), "TotalNet", f)
    a_steuer = _dez(k.get("TotalTax"), "TotalTax", f)
    a_brutto = _dez(k.get("TotalGross"), "TotalGross", f)
    anzahlung = _dez(k.get("Prepaid"), "Prepaid", f, pflicht=False) or Decimal("0")

    if f:
        raise ZugferdFehler(f)

    # ⭐ Storno als Gutschrift (381) trägt POSITIVE Beträge - das Minus steckt in
    # der Belegart. Access druckt Stornos oft negativ; dann drehen wir alles um,
    # statt die Rechnung abzuweisen. Gemischt (Summe negativ, aber einzelne
    # Positionen positiv) bleibt gemischt, nur eben gespiegelt.
    gedreht = False
    if typcode == "381" and a_brutto < 0:
        gedreht = True
        for p in pos:
            p.menge, p.netto, p.nachlass = -p.menge, -p.netto, -p.nachlass
        a_netto, a_steuer, a_brutto, anzahlung = -a_netto, -a_steuer, -a_brutto, -anzahlung
        w.append("Storno kam mit negativen Beträgen – als Gutschrift (381) mit positiven Beträgen ausgestellt")

    # Steuer je Kategorie und Satz (BR-CO-17: Basis × Satz, gerundet)
    gruppen: dict[tuple, Steuergruppe] = {}
    for p in pos:
        sch = (p.kategorie, p.satz)
        g = gruppen.get(sch)
        if g is None:
            code, text = BEFREIUNG.get(p.kategorie, ("", ""))
            g = gruppen[sch] = Steuergruppe(p.kategorie, p.satz, Decimal("0"), Decimal("0"),
                                            text, code)
        g.basis += p.netto
        if p.befreiungsgrund:
            g.grund = p.befreiungsgrund
    for g in gruppen.values():
        g.steuer = runden(g.basis * g.satz / Decimal(100))
        if g.kategorie == "E" and not g.grund:
            f.append("Steuerbefreite Positionen (E) brauchen einen Befreiungsgrund in "
                     "ExemptionReason, z. B. „Steuerfrei nach § 4 Nr. 14 UStG“")

    summe = sum((p.netto for p in pos), Decimal("0"))
    steuer = sum((g.steuer for g in gruppen.values()), Decimal("0"))
    brutto = summe + steuer

    # ⭐ Der Abgleich mit dem Druckbild. Häufigste Ursache einer Abweichung:
    # Access rechnet die Steuer je Position und summiert - EN 16931 rechnet sie
    # je Steuersatz. Das kann einen Cent ausmachen.
    if runden(a_netto) != summe:
        f.append(f"Nettosumme: Access {euro(a_netto)}, Summe der Positionen {euro(summe)}")
    if runden(a_steuer) != steuer:
        je = ", ".join(f"{g.satz.normalize()} %: {euro(g.steuer)}" for g in gruppen.values())
        f.append(f"Steuer: Access {euro(a_steuer)}, nach EN 16931 je Steuersatz gerundet "
                 f"{euro(steuer)} ({je}). Access muss die Steuer je Steuersatz statt je "
                 f"Position runden")
    if runden(a_brutto) != brutto:
        f.append(f"Bruttosumme: Access {euro(a_brutto)}, gerechnet {euro(brutto)}")

    kats = {g.kategorie for g in gruppen.values()}
    # BR-S-02 & Co.: wer Umsatzsteuer ausweist, muss sich steuerlich ausweisen.
    if kats & {"S", "Z", "E"} and not (v_ustid or v_stnr):
        f.append("Firmendaten: USt-IdNr. oder Steuernummer fehlt")
    if kats & {"AE", "K", "G"} and not v_ustid:
        f.append("Firmendaten: eigene USt-IdNr. fehlt – Pflicht bei Reverse Charge, "
                 "EU-Lieferung und Ausfuhr")
    if "AE" in kats and not k_ustid:
        f.append("Reverse Charge (AE) ohne BuyerVatId – die USt-IdNr. des Kunden ist Pflicht")
    if "K" in kats:
        if not k_ustid:
            f.append("Innergemeinschaftliche Lieferung (K) ohne BuyerVatId – "
                     "die USt-IdNr. des Kunden ist Pflicht")
        elif k_ustid[:2].upper() in ("DE",) and _s(verkaeufer.get("land")).upper() == "DE":
            w.append(f"EU-Lieferung an eine deutsche USt-IdNr. ({k_ustid}) – bitte prüfen")
        if not (_datum(k.get("DeliveryDate"), "", [])
                or _datum(k.get("PeriodStart"), "", [])):
            f.append("Innergemeinschaftliche Lieferung (K) braucht DeliveryDate oder "
                     "PeriodStart/PeriodEnd")
        ziel = (_s(k.get("ShipToCountry")) or k_land).upper()
        if ziel == (_s(verkaeufer.get("land")) or "DE").upper():
            f.append(f"Innergemeinschaftliche Lieferung (K), aber Lieferland ist {ziel} – "
                     f"ShipToCountry bzw. BuyerCountry prüfen")
    if "G" in kats and k_land in ("DE",):
        w.append("Ausfuhrlieferung (G) an einen Kunden in DE – bitte Lieferland prüfen")

    zahlbetrag = brutto - anzahlung
    if zahlbetrag > 0 and typcode != "381" and not (
            _s(k.get("DueDate")) or _s(k.get("PaymentTerms"))
            or _s(verkaeufer.get("zahlungsbedingungen"))):
        f.append("Weder DueDate noch PaymentTerms – und in den Firmendaten ist keine "
                 "Standard-Zahlungsbedingung hinterlegt (BR-CO-25)")
    zahlart = _s(k.get("PaymentMeans")) or _s(verkaeufer.get("zahlungsart")) or "58"
    if typcode != "381" and zahlart in ("58", "30") and not _s(verkaeufer.get("iban")):
        f.append("Firmendaten: IBAN fehlt (Pflicht bei Überweisung)")
    if typcode != "381" and zahlart == "59" and not _s(k.get("BuyerIban")):
        f.append("Lastschrift (59) ohne BuyerIban")

    for d in ("DeliveryDate", "DueDate", "PeriodStart", "PeriodEnd", "PrecedingInvoiceDate"):
        _datum(k.get(d), d, f)

    if f:
        raise ZugferdFehler(f)

    return Beleg(
        nummer=nummer, art=art, typcode=typcode, datum=datum, waehrung=waehrung,
        kopf=k, verkaeufer=verkaeufer, positionen=pos,
        steuern=sorted(gruppen.values(), key=lambda g: (g.kategorie, -g.satz)),
        summe_positionen=summe, steuer_gesamt=steuer, brutto=brutto,
        anzahlung=anzahlung, zahlbetrag=zahlbetrag, vorzeichen_gedreht=gedreht,
        warnungen=w,
    )


# ── XML ───────────────────────────────────────────────────────────────────────

def _el(parent, tag: str, text=None, **attrib):
    pfx, name = tag.split(":")
    e = etree.SubElement(parent, f"{{{NS[pfx]}}}{name}")
    for a, v in attrib.items():
        e.set(a, v)
    if text is not None:
        e.text = str(text)
    return e


def _betrag(b: Decimal) -> str:
    return str(runden(b))


def _zahl(b: Decimal, min_stellen: int = 2, max_stellen: int = 4) -> str:
    """Mengen und Preise: so genau wie nötig, mindestens zwei Stellen."""
    q = b.quantize(Decimal(1).scaleb(-max_stellen), rounding=ROUND_HALF_UP)
    t = f"{q:f}"
    if "." in t:
        ganz, nach = t.split(".")
        nach = nach.rstrip("0").ljust(min_stellen, "0")
        t = f"{ganz}.{nach}"
    return t


def _datum102(parent, tag: str, d: _dt.date, qdt: bool = False):
    e = _el(parent, tag)
    _el(e, "qdt:DateTimeString" if qdt else "udt:DateTimeString",
        d.strftime("%Y%m%d"), format="102")


def _adresse(parent, plz, zeile1, zeile2, ort, land):
    a = _el(parent, "ram:PostalTradeAddress")
    if _s(plz):
        _el(a, "ram:PostcodeCode", _s(plz))
    if _s(zeile1):
        _el(a, "ram:LineOne", _s(zeile1))
    if _s(zeile2):
        _el(a, "ram:LineTwo", _s(zeile2))
    if _s(ort):
        _el(a, "ram:CityName", _s(ort))
    _el(a, "ram:CountryID", (_s(land) or "DE").upper())


def baue_xml(b: Beleg) -> bytes:
    """CII-XML zu einem geprüften Beleg. Reihenfolge der Elemente = XSD-Sequenz."""
    k, v = b.kopf, b.verkaeufer
    root = etree.Element(f"{{{NS['rsm']}}}CrossIndustryInvoice", nsmap=NS)

    ctx = _el(root, "rsm:ExchangedDocumentContext")
    _el(_el(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", PROFIL_EN16931)

    doc = _el(root, "rsm:ExchangedDocument")
    _el(doc, "ram:ID", b.nummer)
    _el(doc, "ram:TypeCode", b.typcode)
    _datum102(doc, "ram:IssueDateTime", b.datum)
    if _s(k.get("Note")):
        _el(_el(doc, "ram:IncludedNote"), "ram:Content", _s(k.get("Note")))
    # Pflichtangaben nach § 14 UStG / HGB, die EN 16931 nicht als eigenes Feld kennt
    # (Geschäftsführer, Registergericht): als Hinweis mit Code REG.
    if _s(v.get("rechtliches")):
        n = _el(doc, "ram:IncludedNote")
        _el(n, "ram:Content", _s(v.get("rechtliches")))
        _el(n, "ram:SubjectCode", "REG")

    tx = _el(root, "rsm:SupplyChainTradeTransaction")

    for p in b.positionen:
        li = _el(tx, "ram:IncludedSupplyChainTradeLineItem")
        _el(_el(li, "ram:AssociatedDocumentLineDocument"), "ram:LineID", p.nr)
        prod = _el(li, "ram:SpecifiedTradeProduct")
        if p.artikelnummer:
            _el(prod, "ram:SellerAssignedID", p.artikelnummer)
        if p.kunden_artikelnummer:
            _el(prod, "ram:BuyerAssignedID", p.kunden_artikelnummer)
        _el(prod, "ram:Name", p.name)
        if p.beschreibung:
            _el(prod, "ram:Description", p.beschreibung)
        agr = _el(li, "ram:SpecifiedLineTradeAgreement")
        np_ = _el(agr, "ram:NetPriceProductTradePrice")
        _el(np_, "ram:ChargeAmount", _zahl(p.preis))
        if p.basismenge != 1:
            _el(np_, "ram:BasisQuantity", _zahl(p.basismenge), unitCode=p.einheit)
        _el(_el(li, "ram:SpecifiedLineTradeDelivery"), "ram:BilledQuantity",
            _zahl(p.menge), unitCode=p.einheit)
        st = _el(li, "ram:SpecifiedLineTradeSettlement")
        tax = _el(st, "ram:ApplicableTradeTax")
        _el(tax, "ram:TypeCode", "VAT")
        _el(tax, "ram:CategoryCode", p.kategorie)
        _el(tax, "ram:RateApplicablePercent", _zahl(p.satz))
        if p.nachlass != 0:
            # Was zwischen Menge × Preis und dem gedruckten Zeilenbetrag liegt, ist
            # ein Positionsrabatt (oder -zuschlag) - so geht die Zeile im XML auf.
            ac = _el(st, "ram:SpecifiedTradeAllowanceCharge")
            _el(_el(ac, "ram:ChargeIndicator"), "udt:Indicator",
                "false" if p.nachlass > 0 else "true")
            _el(ac, "ram:ActualAmount", _betrag(abs(p.nachlass)))
            _el(ac, "ram:Reason", "Rabatt" if p.nachlass > 0 else "Zuschlag")
        _el(_el(st, "ram:SpecifiedTradeSettlementLineMonetarySummation"),
            "ram:LineTotalAmount", _betrag(p.netto))

    # ── Vereinbarung: Verkäufer, Käufer, Referenzen
    agr = _el(tx, "ram:ApplicableHeaderTradeAgreement")
    if _s(k.get("BuyerReference")):
        _el(agr, "ram:BuyerReference", _s(k.get("BuyerReference")))

    sp = _el(agr, "ram:SellerTradeParty")
    _el(sp, "ram:Name", _s(v.get("name")))
    if _s(v.get("register")):
        _el(_el(sp, "ram:SpecifiedLegalOrganization"), "ram:ID", _s(v.get("register")))
    if any(_s(v.get(x)) for x in ("kontakt", "telefon", "email")):
        c = _el(sp, "ram:DefinedTradeContact")
        if _s(v.get("kontakt")):
            _el(c, "ram:PersonName", _s(v.get("kontakt")))
        if _s(v.get("telefon")):
            _el(_el(c, "ram:TelephoneUniversalCommunication"), "ram:CompleteNumber",
                _s(v.get("telefon")))
        if _s(v.get("email")):
            _el(_el(c, "ram:EmailURIUniversalCommunication"), "ram:URIID", _s(v.get("email")))
    _adresse(sp, v.get("plz"), v.get("strasse"), v.get("adresszusatz"), v.get("ort"), v.get("land"))
    if _s(v.get("email")):
        _el(_el(sp, "ram:URIUniversalCommunication"), "ram:URIID", _s(v.get("email")),
            schemeID="EM")
    if _s(v.get("ustid")):
        _el(_el(sp, "ram:SpecifiedTaxRegistration"), "ram:ID",
            _s(v.get("ustid")).replace(" ", ""), schemeID="VA")
    if _s(v.get("steuernummer")):
        _el(_el(sp, "ram:SpecifiedTaxRegistration"), "ram:ID",
            _s(v.get("steuernummer")), schemeID="FC")

    bp = _el(agr, "ram:BuyerTradeParty")
    if _s(k.get("CustomerNumber")):
        _el(bp, "ram:ID", _s(k.get("CustomerNumber")))
    _el(bp, "ram:Name", _s(k.get("BuyerName")))
    if _s(k.get("BuyerContact")):
        _el(_el(bp, "ram:DefinedTradeContact"), "ram:PersonName", _s(k.get("BuyerContact")))
    _adresse(bp, k.get("BuyerZip"), k.get("BuyerStreet"), k.get("BuyerAddress2"),
             k.get("BuyerCity"), k.get("BuyerCountry"))
    if _s(k.get("BuyerEmail")):
        _el(_el(bp, "ram:URIUniversalCommunication"), "ram:URIID", _s(k.get("BuyerEmail")),
            schemeID="EM")
    if _s(k.get("BuyerVatId")):
        _el(_el(bp, "ram:SpecifiedTaxRegistration"), "ram:ID",
            _s(k.get("BuyerVatId")).replace(" ", ""), schemeID="VA")
    if _s(k.get("OrderReference")):
        _el(_el(agr, "ram:BuyerOrderReferencedDocument"), "ram:IssuerAssignedID",
            _s(k.get("OrderReference")))

    # ── Lieferung
    dl = _el(tx, "ram:ApplicableHeaderTradeDelivery")
    kats = {g.kategorie for g in b.steuern}
    lieferland = _s(k.get("ShipToCountry"))
    if _s(k.get("ShipToName")) or lieferland or "K" in kats:
        # Bei der EU-Lieferung ist das Lieferland Pflicht (BR-IC-12); fehlt eine
        # eigene Lieferanschrift, ist es die des Käufers.
        st = _el(dl, "ram:ShipToTradeParty")
        _el(st, "ram:Name", _s(k.get("ShipToName")) or _s(k.get("BuyerName")))
        if _s(k.get("ShipToName")) or lieferland:
            _adresse(st, k.get("ShipToZip"), k.get("ShipToStreet"), None,
                     k.get("ShipToCity"), lieferland or k.get("BuyerCountry"))
        else:
            _adresse(st, k.get("BuyerZip"), k.get("BuyerStreet"), k.get("BuyerAddress2"),
                     k.get("BuyerCity"), k.get("BuyerCountry"))
    lieferdatum = _datum(k.get("DeliveryDate"), "", [])
    if lieferdatum:
        _datum102(_el(dl, "ram:ActualDeliverySupplyChainEvent"), "ram:OccurrenceDateTime",
                  lieferdatum)

    # ── Abrechnung
    se = _el(tx, "ram:ApplicableHeaderTradeSettlement")
    zahlart = _s(k.get("PaymentMeans")) or _s(v.get("zahlungsart")) or "58"
    if zahlart == "59" and _s(v.get("glaeubiger_id")):
        _el(se, "ram:CreditorReferenceID", _s(v.get("glaeubiger_id")))
    _el(se, "ram:PaymentReference", b.nummer)
    _el(se, "ram:InvoiceCurrencyCode", b.waehrung)
    # Bei der Gutschrift zahlt nicht der Kunde - eine Überweisung auf unser Konto
    # wäre die falsche Anweisung. Ohne Zahlungsanweisung ist sie in EN 16931 gültig.
    if b.typcode != "381":
        pm = _el(se, "ram:SpecifiedTradeSettlementPaymentMeans")
        _el(pm, "ram:TypeCode", zahlart)
        if zahlart == "59":
            _el(_el(pm, "ram:PayerPartyDebtorFinancialAccount"), "ram:IBANID",
                _s(k.get("BuyerIban")).replace(" ", ""))
        elif zahlart in ("58", "30", "31", "42") and _s(v.get("iban")):
            acc = _el(pm, "ram:PayeePartyCreditorFinancialAccount")
            _el(acc, "ram:IBANID", _s(v.get("iban")).replace(" ", ""))
            if _s(v.get("kontoinhaber")):
                _el(acc, "ram:AccountName", _s(v.get("kontoinhaber")))
            if _s(v.get("bic")):
                _el(_el(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID",
                    _s(v.get("bic")).replace(" ", ""))

    for g in b.steuern:
        t = _el(se, "ram:ApplicableTradeTax")
        _el(t, "ram:CalculatedAmount", _betrag(g.steuer))
        _el(t, "ram:TypeCode", "VAT")
        if g.kategorie in MIT_GRUND and g.grund:
            _el(t, "ram:ExemptionReason", g.grund)
        _el(t, "ram:BasisAmount", _betrag(g.basis))
        _el(t, "ram:CategoryCode", g.kategorie)
        if g.kategorie in MIT_GRUND and g.grund_code:
            _el(t, "ram:ExemptionReasonCode", g.grund_code)
        _el(t, "ram:RateApplicablePercent", _zahl(g.satz))

    von = _datum(k.get("PeriodStart"), "", [])
    bis = _datum(k.get("PeriodEnd"), "", [])
    if von or bis:
        per = _el(se, "ram:BillingSpecifiedPeriod")
        if von:
            _datum102(per, "ram:StartDateTime", von)
        if bis:
            _datum102(per, "ram:EndDateTime", bis)

    bedingung = _s(k.get("PaymentTerms")) or _s(v.get("zahlungsbedingungen"))
    skonto_tage = _s(k.get("SkontoDays"))
    skonto_proz = _s(k.get("SkontoPercent"))
    if skonto_tage and skonto_proz:
        # Skonto maschinenlesbar nach der XRechnung-Konvention - Empfänger wie
        # DATEV Unternehmen online lesen genau diese Zeile.
        proz = Decimal(str(skonto_proz).replace(",", "."))
        zeile = f"#SKONTO#TAGE={int(Decimal(skonto_tage))}#PROZENT={_zahl(proz)}#"
        bedingung = f"{bedingung}\n{zeile}\n" if bedingung else f"{zeile}\n"
    faellig = _datum(k.get("DueDate"), "", [])
    mandat = _s(k.get("DirectDebitMandate"))
    if bedingung or faellig or mandat or b.typcode == "381" and b.zahlbetrag > 0:
        pt = _el(se, "ram:SpecifiedTradePaymentTerms")
        if not bedingung and b.typcode == "381":
            bedingung = "Der Betrag wird erstattet bzw. verrechnet."
        if bedingung:
            _el(pt, "ram:Description", bedingung)
        if faellig:
            _datum102(pt, "ram:DueDateDateTime", faellig)
        if mandat and zahlart == "59":
            _el(pt, "ram:DirectDebitMandateID", mandat)

    ms = _el(se, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    _el(ms, "ram:LineTotalAmount", _betrag(b.summe_positionen))
    _el(ms, "ram:TaxBasisTotalAmount", _betrag(b.summe_positionen))
    _el(ms, "ram:TaxTotalAmount", _betrag(b.steuer_gesamt), currencyID=b.waehrung)
    _el(ms, "ram:GrandTotalAmount", _betrag(b.brutto))
    if b.anzahlung:
        _el(ms, "ram:TotalPrepaidAmount", _betrag(b.anzahlung))
    _el(ms, "ram:DuePayableAmount", _betrag(b.zahlbetrag))

    if _s(k.get("PrecedingInvoiceNumber")):
        ref = _el(se, "ram:InvoiceReferencedDocument")
        _el(ref, "ram:IssuerAssignedID", _s(k.get("PrecedingInvoiceNumber")))
        vd = _datum(k.get("PrecedingInvoiceDate"), "", [])
        if vd:
            _datum102(ref, "ram:FormattedIssueDateTime", vd, qdt=True)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)

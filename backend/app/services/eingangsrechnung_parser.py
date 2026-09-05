"""
Parser für elektronische Eingangsrechnungen.

Unterstützt:
  - ZUGFeRD / Factur-X : PDF/A-3 mit eingebettetem CII-XML (factur-x.xml o.ä.)
  - XRechnung / reines XML : UN/CEFACT CII  (CrossIndustryInvoice)
                             oder UBL       (Invoice)

Ergebnis: ein `ERKopfInput` (inkl. `ERPositionInput`-Liste), das direkt vom
EingangsrechnungWriter weiterverarbeitet werden kann – inklusive der
Bestellreferenz (BuyerOrderReferencedDocument / OrderReference), die das
Bestell-Matching treffsicher macht.

Bewusst namespace-robust über local-name()-XPath, damit ZUGFeRD 2.x, Factur-X
und XRechnung mit ihren unterschiedlichen Namespace-URIs alle funktionieren.
Nur lxml + pypdf – keine Zusatz-Abhängigkeiten.
"""
from __future__ import annotations

import datetime
import io
from typing import Optional

from lxml import etree

from app.services.jtl_eingangsrechnung_writer import (
    ERKopfInput, ERPositionInput, ERZusatzkostenInput)


class ERechnungParseError(Exception):
    pass


# ── Einstieg ─────────────────────────────────────────────────────────────────────
def parse_erechnung(data: bytes, filename: str = "") -> ERKopfInput:
    """Erkennt PDF vs. XML, extrahiert ggf. das eingebettete XML und parst es."""
    if _is_pdf(data, filename):
        xml_bytes = extract_xml_from_pdf(data)
    else:
        xml_bytes = data
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as e:
        raise ERechnungParseError(f"XML nicht parsebar: {e}") from e

    ln = etree.QName(root).localname
    if ln == "CrossIndustryInvoice":
        return _parse_cii(root)
    if ln == "Invoice":
        return _parse_ubl(root)
    raise ERechnungParseError(
        f"Unbekanntes Wurzelelement '{ln}' – weder CII (CrossIndustryInvoice) noch UBL (Invoice)")


def _is_pdf(data: bytes, filename: str) -> bool:
    if filename.lower().endswith(".pdf"):
        return True
    if filename.lower().endswith(".xml"):
        return False
    return data[:5].startswith(b"%PDF")


def extract_xml_from_pdf(pdf_bytes: bytes) -> bytes:
    """Zieht das eingebettete ZUGFeRD/Factur-X-XML aus einem PDF/A-3."""
    from pypdf import PdfReader
    # Beschaedigte oder halb hochgeladene Dateien scheitern schon hier – ohne
    # diesen Fang kaeme beim Anwender ein "Internal Server Error" an statt der
    # Auskunft, dass die Datei nicht lesbar ist.
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise ERechnungParseError(
            f"Datei lässt sich nicht als PDF öffnen – beschädigt oder unvollständig ({e})") from e
    try:
        attachments = dict(reader.attachments or {})
    except Exception as e:
        raise ERechnungParseError(f"PDF-Anhänge nicht lesbar: {e}") from e
    if not attachments:
        raise ERechnungParseError("Kein eingebettetes XML im PDF (kein ZUGFeRD/Factur-X?)")

    preferred = ["factur-x.xml", "zugferd-invoice.xml", "xrechnung.xml", "cii.xml", "order-x.xml"]
    lower = {k.lower(): k for k in attachments}
    chosen = next((lower[p] for p in preferred if p in lower), None)
    if chosen is None:
        chosen = next((k for k in attachments if k.lower().endswith(".xml")), None)
    if chosen is None:
        raise ERechnungParseError(f"PDF enthält Anhänge, aber kein XML: {list(attachments)}")

    content = attachments[chosen]
    if isinstance(content, list):        # pypdf gibt bei Namensdubletten eine Liste
        content = content[0]
    return content


# ── XPath-Helfer (namespace-agnostisch) ──────────────────────────────────────────
def _txt(node, local_path: str) -> Optional[str]:
    """Erstes Textergebnis eines local-name()-XPath (oder None)."""
    if node is None:
        return None
    res = node.xpath(local_path)
    if not res:
        return None
    v = res[0]
    s = v if isinstance(v, str) else (v.text or "")
    s = (s or "").strip()
    return s or None


def _num(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _cii_date(s: Optional[str]) -> Optional[datetime.datetime]:
    """CII-DateTimeString, Format 102 = YYYYMMDD (Fallback: ISO)."""
    if not s:
        return None
    s = s.strip()
    if len(s) == 8 and s.isdigit():
        return datetime.datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
    try:
        return datetime.datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def _iso_date(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.strip()[:19])
    except ValueError:
        return None


# ── CII (UN/CEFACT, ZUGFeRD/Factur-X) ────────────────────────────────────────────
def _parse_cii(root) -> ERKopfInput:
    inv_no = _txt(root, ".//*[local-name()='ExchangedDocument']/*[local-name()='ID']")
    dBeleg = _cii_date(_txt(root,
        ".//*[local-name()='ExchangedDocument']//*[local-name()='DateTimeString']"))

    sellers = root.xpath(".//*[local-name()='SellerTradeParty']")
    seller = sellers[0] if sellers else None
    name = _txt(seller, "./*[local-name()='Name']")
    vat = (_txt(seller, ".//*[local-name()='SpecifiedTaxRegistration']/*[local-name()='ID'][@schemeID='VA']")
           or _txt(seller, ".//*[local-name()='SpecifiedTaxRegistration']/*[local-name()='ID']"))
    addr = (seller.xpath(".//*[local-name()='PostalTradeAddress']") if seller is not None else [])
    addr = addr[0] if addr else None
    strasse = _txt(addr, "./*[local-name()='LineOne']")
    plz = _txt(addr, "./*[local-name()='PostcodeCode']")
    ort = _txt(addr, "./*[local-name()='CityName']")
    land = _txt(addr, "./*[local-name()='CountryID']")
    mail = _txt(seller, ".//*[local-name()='URIUniversalCommunication']/*[local-name()='URIID']")

    order = _txt(root, ".//*[local-name()='ApplicableHeaderTradeAgreement']"
                       "/*[local-name()='BuyerOrderReferencedDocument']/*[local-name()='IssuerAssignedID']")
    dZiel = _cii_date(_txt(root, ".//*[local-name()='SpecifiedTradePaymentTerms']"
                                 "/*[local-name()='DueDateDateTime']/*[local-name()='DateTimeString']"))

    positionen = []
    for li in root.xpath(".//*[local-name()='IncludedSupplyChainTradeLineItem']"):
        pname = _txt(li, ".//*[local-name()='SpecifiedTradeProduct']/*[local-name()='Name']")
        buyer_id = _txt(li, ".//*[local-name()='SpecifiedTradeProduct']/*[local-name()='BuyerAssignedID']")
        seller_id = _txt(li, ".//*[local-name()='SpecifiedTradeProduct']/*[local-name()='SellerAssignedID']")
        qty = _num(_txt(li, ".//*[local-name()='BilledQuantity']"))
        price = _num(_txt(li, ".//*[local-name()='NetPriceProductTradePrice']/*[local-name()='ChargeAmount']"))
        tax = _num(_txt(li, ".//*[local-name()='ApplicableTradeTax']/*[local-name()='RateApplicablePercent']"))
        line_order = _txt(li, ".//*[local-name()='BuyerOrderReferencedDocument']"
                              "/*[local-name()='IssuerAssignedID']")
        positionen.append(ERPositionInput(
            cName=pname or "", fMenge=qty or 0.0, fEKNetto=price or 0.0, fMwSt=tax or 0.0,
            cArtNr=buyer_id, cLieferantenArtNr=seller_id,
            cLieferantenBezeichnung=pname, bestellnummer=line_order))

    # Rechnungssummen (für Summen-Abgleich)
    ms = ".//*[local-name()='SpecifiedTradeSettlementHeaderMonetarySummation']"
    netto = _num(_txt(root, ms + "/*[local-name()='TaxBasisTotalAmount']"))
    steuer = _num(_txt(root, ms + "/*[local-name()='TaxTotalAmount']"))
    brutto = _num(_txt(root, ms + "/*[local-name()='GrandTotalAmount']"))

    # Zusatzkosten auf Dokumentebene (Fracht/Zuschläge/Rabatte)
    zusatz = []
    for ac in root.xpath(".//*[local-name()='ApplicableHeaderTradeSettlement']"
                         "/*[local-name()='SpecifiedTradeAllowanceCharge']"):
        ind = _txt(ac, ".//*[local-name()='ChargeIndicator']/*[local-name()='Indicator']")
        betrag = _num(_txt(ac, "./*[local-name()='ActualAmount']"))
        reason = _txt(ac, "./*[local-name()='Reason']")
        mwst = _num(_txt(ac, ".//*[local-name()='CategoryTradeTax']/*[local-name()='RateApplicablePercent']"))
        if betrag is None:
            continue
        ist_zuschlag = (ind == "true")
        zusatz.append(ERZusatzkostenInput(
            cName=reason or ("Zuschlag" if ist_zuschlag else "Rabatt"),
            betrag=betrag, fMwSt=mwst or 0.0, ist_zuschlag=ist_zuschlag))

    return ERKopfInput(
        cFremdbelegnummer=inv_no or "",
        dBelegdatum=dBeleg or datetime.datetime.now(),
        dZahlungsziel=dZiel, positionen=positionen,
        ustIdNr=vat, lieferantName=name,
        cLieferant=name, cStrasse=strasse, cPLZ=plz, cOrt=ort, cLandISO=land, cMail=mail,
        bestellnummer=order,
        nettoSumme=netto, steuerSumme=steuer, bruttoSumme=brutto, zusatzkosten=zusatz)


# ── UBL (XRechnung UBL) ───────────────────────────────────────────────────────────
def _parse_ubl(root) -> ERKopfInput:
    inv_no = _txt(root, "./*[local-name()='ID']")
    dBeleg = _iso_date(_txt(root, "./*[local-name()='IssueDate']"))
    dZiel = _iso_date(_txt(root, "./*[local-name()='DueDate']"))
    order = _txt(root, "./*[local-name()='OrderReference']/*[local-name()='ID']")

    parties = root.xpath(".//*[local-name()='AccountingSupplierParty']/*[local-name()='Party']")
    seller = parties[0] if parties else None
    name = (_txt(seller, ".//*[local-name()='PartyLegalEntity']/*[local-name()='RegistrationName']")
            or _txt(seller, ".//*[local-name()='PartyName']/*[local-name()='Name']"))
    vat = _txt(seller, ".//*[local-name()='PartyTaxScheme']/*[local-name()='CompanyID']")
    addr = (seller.xpath(".//*[local-name()='PostalAddress']") if seller is not None else [])
    addr = addr[0] if addr else None
    strasse = _txt(addr, "./*[local-name()='StreetName']")
    plz = _txt(addr, "./*[local-name()='PostalZone']")
    ort = _txt(addr, "./*[local-name()='CityName']")
    land = _txt(addr, ".//*[local-name()='IdentificationCode']")
    mail = _txt(seller, ".//*[local-name()='Contact']/*[local-name()='ElectronicMail']")

    positionen = []
    for li in root.xpath("./*[local-name()='InvoiceLine']"):
        qty = _num(_txt(li, "./*[local-name()='InvoicedQuantity']"))
        item = li.xpath("./*[local-name()='Item']")
        item = item[0] if item else None
        pname = _txt(item, "./*[local-name()='Name']")
        buyer_id = _txt(item, ".//*[local-name()='BuyersItemIdentification']/*[local-name()='ID']")
        seller_id = _txt(item, ".//*[local-name()='SellersItemIdentification']/*[local-name()='ID']")
        tax = _num(_txt(item, ".//*[local-name()='ClassifiedTaxCategory']/*[local-name()='Percent']"))
        price = _num(_txt(li, "./*[local-name()='Price']/*[local-name()='PriceAmount']"))
        line_order = _txt(li, ".//*[local-name()='OrderLineReference']"
                              "//*[local-name()='OrderReference']/*[local-name()='ID']")
        positionen.append(ERPositionInput(
            cName=pname or "", fMenge=qty or 0.0, fEKNetto=price or 0.0, fMwSt=tax or 0.0,
            cArtNr=buyer_id, cLieferantenArtNr=seller_id,
            cLieferantenBezeichnung=pname, bestellnummer=line_order))

    lmt = ".//*[local-name()='LegalMonetaryTotal']"
    netto = _num(_txt(root, lmt + "/*[local-name()='TaxExclusiveAmount']"))
    brutto = _num(_txt(root, lmt + "/*[local-name()='TaxInclusiveAmount']"))
    steuer = _num(_txt(root, ".//*[local-name()='TaxTotal']/*[local-name()='TaxAmount']"))

    zusatz = []
    for ac in root.xpath("./*[local-name()='AllowanceCharge']"):
        ind = _txt(ac, "./*[local-name()='ChargeIndicator']")
        betrag = _num(_txt(ac, "./*[local-name()='Amount']"))
        reason = _txt(ac, "./*[local-name()='AllowanceChargeReason']")
        mwst = _num(_txt(ac, ".//*[local-name()='TaxCategory']/*[local-name()='Percent']"))
        if betrag is None:
            continue
        ist_zuschlag = (ind is not None and ind.lower() == "true")
        zusatz.append(ERZusatzkostenInput(
            cName=reason or ("Zuschlag" if ist_zuschlag else "Rabatt"),
            betrag=betrag, fMwSt=mwst or 0.0, ist_zuschlag=ist_zuschlag))

    return ERKopfInput(
        cFremdbelegnummer=inv_no or "",
        dBelegdatum=dBeleg or datetime.datetime.now(),
        dZahlungsziel=dZiel, positionen=positionen,
        ustIdNr=vat, lieferantName=name,
        cLieferant=name, cStrasse=strasse, cPLZ=plz, cOrt=ort, cLandISO=land, cMail=mail,
        bestellnummer=order,
        nettoSumme=netto, steuerSumme=steuer, bruttoSumme=brutto, zusatzkosten=zusatz)

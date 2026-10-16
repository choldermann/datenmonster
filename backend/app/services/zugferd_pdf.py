"""Das ZUGFeRD-XML in eine vorhandene PDF einbetten (PDF/A-3, Factur-X).

Die PDF kommt fertig aus der Fremdanwendung (bei EGP: Access) - Layout, Logo und
Texte bleiben genau so, wie der Kunde sie kennt. Hier kommt nur dazu, was eine
ZUGFeRD-Datei ausmacht:

  - das XML als Anhang „factur-x.xml“ mit AFRelationship /Alternative,
  - der Verweis darauf im Katalog (/AF),
  - ein sRGB-Ausgabeprofil (OutputIntent), falls die PDF keins mitbringt,
  - XMP-Metadaten mit PDF/A-3-Kennung und der Factur-X-Erweiterung,
  - ein Info-Verzeichnis, das zu diesen Metadaten passt (PDF/A verlangt beides gleich).

Was sich NICHT nachträglich heilen lässt, sind nicht eingebettete Schriften. Die
werden als Warnung gemeldet: das XML bleibt gültig, die Datei ist dann aber kein
sauberes PDF/A. Abhilfe in Access: beim PDF-Export „PDF/A-kompatibel“ ankreuzen.
"""
from __future__ import annotations

import datetime as _dt
import io
import re
from typing import Optional
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           NameObject, NumberObject, TextStringObject)

XML_DATEINAME = "factur-x.xml"
FX_NS = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"


class PdfFehler(Exception):
    pass


def _pdf_datum(d: _dt.datetime) -> str:
    off = d.utcoffset() or _dt.timedelta(0)
    m = int(off.total_seconds() // 60)
    vz = "+" if m >= 0 else "-"
    return d.strftime("D:%Y%m%d%H%M%S") + f"{vz}{abs(m) // 60:02d}'{abs(m) % 60:02d}'"


def _xmp_datum(d: _dt.datetime) -> str:
    return d.isoformat(timespec="seconds")


def _lies_pdf_datum(t) -> Optional[_dt.datetime]:
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Z+\-])?(\d{2})?'?(\d{2})?",
                 str(t or ""))
    if not m:
        return None
    j, mo, ta, h, mi, s, vz, oh, om = m.groups()
    try:
        tz = _dt.timezone.utc
        if vz in ("+", "-"):
            off = _dt.timedelta(hours=int(oh or 0), minutes=int(om or 0))
            tz = _dt.timezone(off if vz == "+" else -off)
        return _dt.datetime(int(j), int(mo or 1), int(ta or 1), int(h or 0), int(mi or 0),
                            int(s or 0), tzinfo=tz)
    except ValueError:
        return None


def _srgb_profil() -> bytes:
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _xmp(titel: str, autor: str, betreff: str, produzent: str, werkzeug: str,
         erstellt: _dt.datetime, geaendert: _dt.datetime, stufe: str) -> bytes:
    e = escape
    beschr = (f"<dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">{e(betreff)}"
              f"</rdf:li></rdf:Alt></dc:description>") if betreff else ""
    return f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">
   <dc:format>application/pdf</dc:format>
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e(titel)}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{e(autor)}</rdf:li></rdf:Seq></dc:creator>
   {beschr}
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdf:Producer>{e(produzent)}</pdf:Producer>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:CreatorTool>{e(werkzeug)}</xmp:CreatorTool>
   <xmp:CreateDate>{_xmp_datum(erstellt)}</xmp:CreateDate>
   <xmp:ModifyDate>{_xmp_datum(geaendert)}</xmp:ModifyDate>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/"
    xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#"
    xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#">
   <pdfaExtension:schemas>
    <rdf:Bag>
     <rdf:li rdf:parseType="Resource">
      <pdfaSchema:schema>Factur-X PDFA Extension Schema</pdfaSchema:schema>
      <pdfaSchema:namespaceURI>{FX_NS}</pdfaSchema:namespaceURI>
      <pdfaSchema:prefix>fx</pdfaSchema:prefix>
      <pdfaSchema:property>
       <rdf:Seq>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>DocumentFileName</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>name of the embedded XML invoice file</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>DocumentType</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>INVOICE</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>Version</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>The actual version of the Factur-X XML schema</pdfaProperty:description>
        </rdf:li>
        <rdf:li rdf:parseType="Resource">
         <pdfaProperty:name>ConformanceLevel</pdfaProperty:name>
         <pdfaProperty:valueType>Text</pdfaProperty:valueType>
         <pdfaProperty:category>external</pdfaProperty:category>
         <pdfaProperty:description>The conformance level of the embedded Factur-X data</pdfaProperty:description>
        </rdf:li>
       </rdf:Seq>
      </pdfaSchema:property>
     </rdf:li>
    </rdf:Bag>
   </pdfaExtension:schemas>
  </rdf:Description>
  <rdf:Description rdf:about="" xmlns:fx="{FX_NS}">
   <fx:DocumentType>INVOICE</fx:DocumentType>
   <fx:DocumentFileName>{XML_DATEINAME}</fx:DocumentFileName>
   <fx:Version>1.0</fx:Version>
   <fx:ConformanceLevel>{e(stufe)}</fx:ConformanceLevel>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>""".encode("utf-8")


def _nicht_eingebettete_schriften(reader: PdfReader) -> list[str]:
    fehlend: set[str] = set()
    gesehen: set = set()

    def pruefe(font):
        font = font.get_object()
        if id(font) in gesehen:
            return
        gesehen.add(id(font))
        sub = font.get("/Subtype")
        if sub == "/Type3":
            return
        if sub == "/Type0":
            for d in font.get("/DescendantFonts", []):
                pruefe(d)
            return
        desc = font.get("/FontDescriptor")
        desc = desc.get_object() if desc is not None else None
        if desc is None or not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
            fehlend.add(str(font.get("/BaseFont", "?")).lstrip("/"))

    # Nur Schriften zählen, die im Inhalt auch benutzt werden („/F1 12 Tf“):
    # viele Erzeuger deklarieren eine Standardschrift, die nie gezeichnet wird,
    # und PDF/A stört sich daran nicht.
    def benutzt(daten: bytes) -> set[str]:
        return {"/" + m.decode("latin-1")
                for m in re.findall(rb"/([^\s/\[\]()<>{}%]+)\s+[-\d.]+\s+Tf", daten or b"")}

    def durch(res, inhalt: bytes, tiefe=0):
        if res is None or tiefe > 8:
            return
        res = res.get_object()
        namen = benutzt(inhalt)
        fonts = res.get("/Font")
        if fonts is not None:
            for schl, f in fonts.get_object().items():
                if schl in namen:
                    pruefe(f)
        xo = res.get("/XObject")
        if xo is not None:
            for x in xo.get_object().values():
                x = x.get_object()
                if x.get("/Subtype") == "/Form":
                    try:
                        daten = x.get_data()
                    except Exception:                         # noqa: BLE001
                        daten = b""
                    durch(x.get("/Resources"), daten, tiefe + 1)

    for seite in reader.pages:
        try:
            # Nicht „if seite.get_contents()“: der ContentStream ist ein Dictionary
            # und gilt ohne Schlüssel als leer.
            inhalt = seite.get_contents()
            inhalt = inhalt.get_data() if inhalt is not None else b""
        except Exception:                                     # noqa: BLE001
            inhalt = b""
        durch(seite.get("/Resources"), inhalt)
    return sorted(fehlend)


def einbetten(pdf: bytes, xml: bytes, *, titel: str, autor: str, betreff: str = "",
              stufe: str = "EN 16931", jetzt: Optional[_dt.datetime] = None) -> tuple[bytes, list[str]]:
    """Gibt (ZUGFeRD-PDF, Warnungen) zurück."""
    if not pdf or not pdf.lstrip()[:5].startswith(b"%PDF"):
        raise PdfFehler("Die mitgelieferte Datei ist keine PDF")
    try:
        reader = PdfReader(io.BytesIO(pdf))
    except Exception as e:                                    # noqa: BLE001
        raise PdfFehler(f"PDF lässt sich nicht lesen: {e}")
    if reader.is_encrypted:
        raise PdfFehler("Die PDF ist verschlüsselt bzw. kennwortgeschützt – "
                        "PDF/A erlaubt das nicht")

    warnungen: list[str] = []
    fehlend = _nicht_eingebettete_schriften(reader)
    if fehlend:
        warnungen.append("PDF/A: Schriften nicht eingebettet (" + ", ".join(fehlend[:5])
                         + ") – in Access beim PDF-Export „PDF/A-kompatibel“ aktivieren")

    writer = PdfWriter(clone_from=reader)
    kat = writer._root_object
    jetzt = jetzt or _dt.datetime.now().astimezone()

    # ── der Anhang
    ef = DecodedStreamObject()
    ef.set_data(xml)
    ef.update({
        NameObject("/Type"): NameObject("/EmbeddedFile"),
        NameObject("/Subtype"): NameObject("/text/xml"),
        NameObject("/Params"): DictionaryObject({
            NameObject("/ModDate"): TextStringObject(_pdf_datum(jetzt)),
            NameObject("/Size"): NumberObject(len(xml)),
        }),
    })
    ef_ref = writer._add_object(ef)
    fs = DictionaryObject({
        NameObject("/Type"): NameObject("/Filespec"),
        NameObject("/F"): TextStringObject(XML_DATEINAME),
        NameObject("/UF"): TextStringObject(XML_DATEINAME),
        NameObject("/Desc"): TextStringObject("Factur-X/ZUGFeRD-Rechnung"),
        NameObject("/AFRelationship"): NameObject("/Alternative"),
        NameObject("/EF"): DictionaryObject({NameObject("/F"): ef_ref,
                                             NameObject("/UF"): ef_ref}),
    })
    fs_ref = writer._add_object(fs)

    namen = kat.get("/Names")
    namen = namen.get_object() if namen is not None else DictionaryObject()
    # Bringt die PDF schon einen Anhang mit (eine ältere ZUGFeRD-Fassung derselben
    # Rechnung), ersetzen wir ihn: zwei Rechnungs-XML in einer Datei wären mehrdeutig.
    namen[NameObject("/EmbeddedFiles")] = DictionaryObject({
        NameObject("/Names"): ArrayObject([TextStringObject(XML_DATEINAME), fs_ref])})
    kat[NameObject("/Names")] = writer._add_object(namen) if "/Names" not in kat else namen
    kat[NameObject("/AF")] = ArrayObject([fs_ref])
    # Viewer klappen dann die Anhangsleiste auf - wer die Datei öffnet, sieht das XML.
    kat[NameObject("/PageMode")] = NameObject("/UseAttachments")

    # ── Ausgabeprofil
    if "/OutputIntents" not in kat:
        icc = DecodedStreamObject()
        icc.set_data(_srgb_profil())
        icc.update({NameObject("/N"): NumberObject(3)})
        oi = DictionaryObject({
            NameObject("/Type"): NameObject("/OutputIntent"),
            NameObject("/S"): NameObject("/GTS_PDFA1"),
            NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
            NameObject("/DestOutputProfile"): writer._add_object(icc),
        })
        kat[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(oi)])

    # ── Anmerkungen müssen druckbar sein (PDF/A: Print-Flag, nicht versteckt)
    for seite in writer.pages:
        for a in seite.get("/Annots", []) or []:
            a = a.get_object()
            fl = int(a.get("/F", 0))
            a[NameObject("/F")] = NumberObject((fl | 4) & ~(1 | 2 | 32))

    # ── Metadaten: Info und XMP aus EINER Quelle, sonst ist es kein PDF/A
    alt = reader.metadata or {}
    erstellt = _lies_pdf_datum(alt.get("/CreationDate")) or jetzt
    werkzeug = str(alt.get("/Creator") or "Microsoft Access")
    produzent = "Datenmonster ZUGFeRD"
    writer.add_metadata({
        "/Title": titel, "/Author": autor, "/Subject": betreff,
        "/Creator": werkzeug, "/Producer": produzent,
        "/CreationDate": _pdf_datum(erstellt), "/ModDate": _pdf_datum(jetzt),
    })
    info = writer._info.get_object() if writer._info is not None else None
    if info is not None:
        for schl in ("/Keywords", "/Trapped"):
            info.pop(NameObject(schl), None)
        if not betreff:
            info.pop(NameObject("/Subject"), None)
    meta = DecodedStreamObject()
    meta.set_data(_xmp(titel, autor, betreff, produzent, werkzeug, erstellt, jetzt, stufe))
    meta.update({NameObject("/Type"): NameObject("/Metadata"),
                 NameObject("/Subtype"): NameObject("/XML")})
    kat[NameObject("/Metadata")] = writer._add_object(meta)

    # PDF/A will eine Dateikennung im Trailer.
    writer.generate_file_identifiers()
    aus = io.BytesIO()
    writer.write(aus)
    return aus.getvalue(), warnungen


def xml_aus_pdf(pdf: bytes) -> Optional[bytes]:
    """Für Tests und die Anzeige im Protokoll: das eingebettete XML wieder auslesen."""
    reader = PdfReader(io.BytesIO(pdf))
    for name, inhalt in (reader.attachments or {}).items():
        if name == XML_DATEINAME:
            return inhalt[0] if isinstance(inhalt, list) else inhalt
    return None

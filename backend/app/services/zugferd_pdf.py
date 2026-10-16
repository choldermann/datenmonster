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


# ── Was Microsoft Access beim PDF-Export falsch macht (gemessen an EGP-Rechnungen,
#    16.10.2026) und hier repariert wird, ohne das Druckbild anzufassen.

def _bilder_ohne_interpolate(writer: PdfWriter) -> int:
    """PDF/A 6.2.8: Bilder dürfen kein /Interpolate true tragen. Access setzt es."""
    n = 0
    for obj in writer._objects:
        try:
            o = obj.get_object() if obj is not None else None
        except Exception:                                     # noqa: BLE001
            continue
        if isinstance(o, DictionaryObject) and o.get("/Subtype") == "/Image" \
                and "/Interpolate" in o:
            del o["/Interpolate"]
            n += 1
    return n


def _glyph_fuer_code(tt, code: int, symbolisch: bool = False) -> Optional[str]:
    """Code einer einfachen TrueType-Schrift → Glyphenname, wie ihn ein Viewer sucht.

    Reihenfolge nach ISO 32000-1, 9.6.6.4: nicht-symbolische Schriften (Access,
    WinAnsi) über Unicode in der (3,1)-Tabelle, symbolische (z. B. reportlab-
    Subsets) über (3,0) bzw. (1,0) mit dem Code selbst.
    """
    cmap = tt["cmap"] if "cmap" in tt else None
    if cmap is None:
        return None
    try:
        uni = ord(bytes([code]).decode("cp1252"))
    except (UnicodeDecodeError, ValueError):
        uni = None
    wege = ([((3, 0), 0xF000 + code), ((3, 0), code), ((1, 0), code), ((3, 1), uni)] if symbolisch
            else [((3, 1), uni), ((1, 0), code), ((3, 0), 0xF000 + code)])
    for (pid, eid), schl in wege:
        if schl is None:
            continue
        t = cmap.getcmap(pid, eid)
        if t is not None and schl in t.cmap:
            return t.cmap[schl]
    return None


def _breiten_angleichen(writer: PdfWriter) -> int:
    """PDF/A 6.2.11.5: Breiten in /Widths bzw. /W und im Schriftprogramm müssen passen.

    Access rundet die Breiten im PDF (Verdana „i“: 272 statt 274,41). Wir ändern
    das SCHRIFTPROGRAMM auf die Werte der PDF, nicht umgekehrt: dann bleibt jede
    Zeile exakt dort stehen, wo Access sie gesetzt hat.
    """
    from fontTools.ttLib import TTFont

    def anpassen(desc, soll: dict) -> bool:
        """soll: Glyphenname/GID → Breite in 1/1000 em."""
        ff = desc.get("/FontFile2") if desc is not None else None
        if ff is None or not soll:
            return False
        strom = ff.get_object()
        tt = TTFont(io.BytesIO(strom.get_data()))
        upem = tt["head"].unitsPerEm
        hmtx = tt["hmtx"]
        reihenfolge = tt.getGlyphOrder()
        geaendert = False
        for g, breite in soll.items():
            name = reihenfolge[g] if isinstance(g, int) and g < len(reihenfolge) else g
            if name not in hmtx.metrics:
                continue
            ist, lsb = hmtx.metrics[name]
            if abs(ist * 1000 / upem - float(breite)) > 0.5:
                hmtx.metrics[name] = (int(round(float(breite) * upem / 1000)), lsb)
                geaendert = True
        if geaendert:
            aus = io.BytesIO()
            tt.save(aus)
            daten = aus.getvalue()
            neu = DecodedStreamObject()
            neu.set_data(daten)
            for k, v in strom.items():
                if k not in ("/Length", "/Filter", "/DecodeParms", "/Length1"):
                    neu[NameObject(k)] = v
            neu[NameObject("/Length1")] = NumberObject(len(daten))
            desc[NameObject("/FontFile2")] = writer._add_object(neu)
        return geaendert

    n = 0
    for obj in list(writer._objects):
        try:
            f = obj.get_object() if obj is not None else None
            if not isinstance(f, DictionaryObject) or f.get("/Type") != "/Font":
                continue
            if f.get("/Subtype") == "/TrueType" and "/Widths" in f:
                desc = f.get("/FontDescriptor")
                desc = desc.get_object() if desc is not None else None
                if desc is None or "/FontFile2" not in desc:
                    continue
                tt = TTFont(io.BytesIO(desc["/FontFile2"].get_object().get_data()))
                erst = int(f.get("/FirstChar", 0))
                symbolisch = bool(int(desc.get("/Flags", 0)) & 4)
                soll, strittig = {}, set()
                for i, w in enumerate(f["/Widths"]):
                    # Access schreibt 0 für ungenutzte Codes - und manche davon
                    # (z. B. das geschützte Leerzeichen) zeigen auf dieselbe Glyphe
                    # wie ein benutztes Zeichen. Die 0 darf die echte Breite nicht
                    # überschreiben; widersprüchliche Werte lassen die Glyphe in Ruhe.
                    if float(w) == 0:
                        continue
                    g = _glyph_fuer_code(tt, erst + i, symbolisch)
                    if not g:
                        continue
                    if g in soll and abs(soll[g] - float(w)) > 0.5:
                        strittig.add(g)
                    soll[g] = float(w)
                n += anpassen(desc, {g: w for g, w in soll.items() if g not in strittig})
            elif f.get("/Subtype") == "/Type0":
                for d in f.get("/DescendantFonts", []):
                    d = d.get_object()
                    if d.get("/Subtype") != "/CIDFontType2":
                        continue
                    karte = d.get("/CIDToGIDMap")
                    if karte is not None and karte != "/Identity":
                        continue                              # eigene Zuordnung: nicht anfassen
                    soll, w = {}, list(d.get("/W", []))
                    i = 0
                    while i < len(w):
                        start = int(w[i])
                        nxt = w[i + 1].get_object() if hasattr(w[i + 1], "get_object") else w[i + 1]
                        if isinstance(nxt, (list, ArrayObject)):
                            for j, breite in enumerate(nxt):
                                if float(breite) != 0:
                                    soll[start + j] = float(breite)
                            i += 2
                        else:
                            for cid in range(start, int(nxt) + 1):
                                if float(w[i + 2]) != 0:
                                    soll[cid] = float(w[i + 2])
                            i += 3
                    desc = d.get("/FontDescriptor")
                    n += anpassen(desc.get_object() if desc is not None else None, soll)
        except Exception:                                     # noqa: BLE001
            # Eine Schrift, die fontTools nicht lesen kann, bleibt wie sie ist -
            # das XML ist davon nicht berührt, nur die PDF/A-Prüfung meckert.
            continue
    return n


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

    _bilder_ohne_interpolate(writer)
    _breiten_angleichen(writer)

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

# -*- coding: utf-8 -*-
"""Lieferantenrechnungen aus gewöhnlichen PDFs lesen (ohne ZUGFeRD/XRechnung).

Warum überhaupt: eine Stichprobe von neun echten Lieferantenrechnungen der HaKo
enthielt **keine einzige** E-Rechnung. Der strukturierte Weg
(`eingangsrechnung_parser`) bleibt der bessere — er ist exakt —, greift in der
Praxis aber bislang nie.

**Der Kniff: nicht alles der KI überlassen.** In acht der neun Rechnungen stand
die JTL-Bestellnummer im Klartext, und alle acht führten zu einer echten
Bestellung. Damit ist der heikelste Teil — welcher Lieferant, welche Bestellung —
kein Ratespiel, sondern ein Datenbankzugriff:

    Text → Nummernkandidaten → in tLieferantenBestellung nachschlagen
         → Lieferant + Bestellpositionen stehen fest

Die KI liest anschließend nur noch, was wirklich unstrukturiert ist:
Rechnungsnummer, Datum, Summen, Positionszeilen. Und selbst dabei bekommt sie die
Bestellpositionen als Vorlage, sodass Artikelnummern und Preise abgeglichen statt
erfunden werden. Was sie liefert, geht durch dieselbe Summenprüfung und dieselbe
Vier-Augen-Freigabe wie eine echte E-Rechnung.

Die Nummernerkennung rät bewusst kein Format: sie sammelt großzügig Kandidaten
und lässt die **Datenbank** entscheiden, welcher davon eine Bestellnummer ist.
Damit funktioniert sie auch bei Kunden, deren Nummernkreis nicht „BST-" heißt.
"""
from __future__ import annotations

import datetime
import io
import json
import re
from typing import Optional

from sqlalchemy import create_engine, text

from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str
from app.services.eingangsrechnung_parser import ERechnungParseError
from app.services.jtl_eingangsrechnung_writer import ERKopfInput, ERPositionInput, \
    ERZusatzkostenInput

# So viel Rechnungstext geht höchstens in den Prompt. Die längste Rechnung der
# Stichprobe hatte flach 16.000 Zeichen (zwei Seiten plus AGB-Rückseite); mit
# Layout kommen Ausrichtungs-Leerzeichen dazu, deshalb großzügiger bemessen.
MAX_TEXT = 32000

# Kandidaten für eine Bestellnummer: Buchstabenpräfix mit Ziffern (BST-202614044,
# PO 12345) oder eine längere reine Ziffernfolge. Bewusst großzügig – die
# Datenbank sortiert aus, nicht dieser Ausdruck.
#
# KEINE Wortgrenzen: aus PDFs kommt der Text oft ohne Leerzeichen heraus
# ("ReferenzBST-202614044Lieferscheinnummer:5116"). Ein \b hinter den Ziffern
# würde dort nicht greifen, weil auf eine Ziffer direkt ein Buchstabe folgt –
# genau daran scheiterte eine der neun Testrechnungen. Stattdessen wird nur
# ausgeschlossen, dass links oder rechts weitere Ziffern stehen, damit lange
# Zahlen nicht in der Mitte angeschnitten werden.
_NUMMER = re.compile(r"(?<![0-9])(?:[A-Za-z]{1,6}[-_/ ]?)?[0-9]{5,14}(?![0-9])")


def pdf_text(data: bytes, layout: bool = True) -> str:
    """Textebene eines PDFs. Leer bei reinen Scans (dann hilft nur OCR).

    **Mit Layout**, nicht flach. Der Unterschied entscheidet über die ganze
    Auslesung: flach gezogen verschmilzt eine Rechnungszeile zu
    „…41906 30.07.2611 517728.07.26 BST-202614007 DDP 31" – da ist selbst für
    einen Menschen nicht mehr zu erkennen, welche Zahl die Rechnungsnummer ist.
    Mit Layout bleiben Spalten und Beschriftungen nebeneinander stehen.

    Gemessen: mit flachem Text lasen zwei verschiedene Modelle nur 2 von 6
    Rechnungen richtig, und das stärkere war nicht besser als das schwächere —
    ein sicheres Zeichen, dass die Information schon vor dem Modell verloren ging.

    Nur nachlaufende Leerzeichen werden entfernt; die führenden TRAGEN die
    Spalteninformation und müssen bleiben.
    """
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    seiten = []
    for seite in reader.pages:
        roh = None
        if layout:
            try:
                roh = seite.extract_text(extraction_mode="layout")
            except Exception:
                roh = None                      # ältere pypdf-Fassung o. ä.
        seiten.append(roh if roh else (seite.extract_text() or ""))
    txt = "\n".join(seiten)
    # Leerzeilenketten eindampfen: sie kosten Platz im Prompt und tragen nichts.
    zeilen, ausgabe, leer = txt.splitlines(), [], 0
    for z in zeilen:
        z = z.rstrip()
        leer = leer + 1 if not z else 0
        if leer <= 1:
            ausgabe.append(z)
    return "\n".join(ausgabe)


def nummer_kandidaten(txt: str, grenze: int = 1500) -> list[str]:
    """Alles, was eine Belegnummer sein könnte – ohne Formatannahme.

    Der Buchstabenpräfix wird in allen Längen durchprobiert, statt sich auf die
    Gier des Ausdrucks zu verlassen. Grund: in Text ohne Leerzeichen verschmilzt
    das Präfix mit dem Wort davor – aus „ReferenzBST-202614044" holt der Ausdruck
    „enzBST-202614044", und der Vergleich mit „BST-202614044" schlägt fehl.
    Erzeugt werden deshalb die reine Ziffernfolge und jede Endung des Präfixes;
    welche davon eine Bestellnummer ist, entscheidet weiterhin die Datenbank.
    """
    gesehen: list[str] = []

    def merken(k: str) -> None:
        if k and k not in gesehen:
            gesehen.append(k)

    for m in _NUMMER.finditer(txt or ""):
        roh = m.group(0).strip()
        ziffern = re.sub(r"\D", "", roh)
        buchstaben = re.sub(r"[^A-Za-z]", "", roh)
        merken(roh)
        merken(ziffern)
        for i in range(1, len(buchstaben) + 1):
            merken(buchstaben[-i:] + ziffern)
        if len(gesehen) >= grenze:
            break
    return gesehen


def finde_bestellung(conn, kandidaten: list[str]) -> Optional[dict]:
    """Welcher Kandidat ist eine echte Lieferantenbestellung?

    Die Datenbank entscheidet. Gibt es mehrere Treffer, gewinnt die jüngste –
    und die übrigen wandern als Hinweis mit, damit im Formular sichtbar ist,
    dass es nicht eindeutig war.
    """
    if not kandidaten:
        return None
    treffer = []
    # In Blöcken abfragen: eine Rechnung kann hunderte Zahlen enthalten.
    for i in range(0, len(kandidaten), 100):
        block = kandidaten[i:i + 100]
        platzhalter = ", ".join(f":n{j}" for j in range(len(block)))
        rows = conn.execute(text(f"""
            SELECT b.kLieferantenBestellung, b.cEigeneBestellnummer, b.kLieferant,
                   l.cFirma, b.dErstellt
            FROM dbo.tLieferantenBestellung b
            LEFT JOIN dbo.tlieferant l ON l.kLieferant = b.kLieferant
            WHERE ISNULL(b.nDeleted,0) = 0
              AND REPLACE(REPLACE(b.cEigeneBestellnummer,'-',''),' ','')
                  IN ({platzhalter})
        """), {f"n{j}": re.sub(r"[-_/ ]", "", k) for j, k in enumerate(block)}).mappings().all()
        treffer.extend(rows)
    if not treffer:
        return None
    treffer.sort(key=lambda r: r["dErstellt"] or datetime.datetime.min, reverse=True)
    best = treffer[0]
    return {
        "kLieferantenBestellung": int(best["kLieferantenBestellung"]),
        "cEigeneBestellnummer": best["cEigeneBestellnummer"],
        "kLieferant": int(best["kLieferant"] or 0),
        "cFirma": best["cFirma"],
        "weitere": [r["cEigeneBestellnummer"] for r in treffer[1:5]],
    }


def bestellpositionen(conn, kBestellung: int) -> list[dict]:
    """Die Positionen der erkannten Bestellung – Vorlage für die KI und
    Gegenprobe für das, was sie ausliest."""
    rows = conn.execute(text("""
        SELECT bp.kLieferantenBestellungPos, bp.kArtikel, a.cArtNr,
               bp.cName, bp.fMenge, ISNULL(bp.fMengeGeliefert,0) AS geliefert,
               bp.fEKNetto, bp.fUST
        FROM dbo.tLieferantenBestellungPos bp
        LEFT JOIN dbo.tArtikel a ON a.kArtikel = bp.kArtikel
        WHERE bp.kLieferantenBestellung = :k
        ORDER BY bp.kLieferantenBestellungPos
    """), {"k": kBestellung}).mappings().all()
    return [{"cArtNr": r["cArtNr"] or "", "cName": (r["cName"] or "")[:80],
             "menge": float(r["fMenge"] or 0), "geliefert": float(r["geliefert"] or 0),
             "ekNetto": float(r["fEKNetto"] or 0), "mwst": float(r["fUST"] or 0)}
            for r in rows]


# Was die KI liefern soll. Bewusst flach und klein gehalten: je enger das Schema,
# desto weniger Spielraum zum Fabulieren.
#
# Streng nach den Regeln für strukturierte Ausgaben: JEDES Objekt setzt
# additionalProperties=false und listet ALLE Eigenschaften unter required. Der
# Gateway (OpenAI) weist ein Schema sonst mit „Invalid schema for response_format"
# ab; Ollama ist toleranter, aber dasselbe Schema muss für beide Anbieter passen.
# Optionale Werte gibt es damit nicht — nicht gefundene Felder kommen als leerer
# Text bzw. 0 zurück, was der Aufrufer ohnehin so behandelt.
def _objekt(eigenschaften: dict) -> dict:
    return {"type": "object", "properties": eigenschaften,
            "required": list(eigenschaften), "additionalProperties": False}


SCHEMA = _objekt({
    "rechnungsnummer": {"type": "string"},
    "belegdatum":      {"type": "string", "description": "JJJJ-MM-TT"},
    "zahlungsziel":    {"type": "string", "description": "JJJJ-MM-TT, sonst leerer Text"},
    "nettoSumme":      {"type": "number"},
    "steuerSumme":     {"type": "number"},
    "bruttoSumme":     {"type": "number"},
    "positionen": {"type": "array", "items": _objekt({
        "artikelnummer":    {"type": "string"},
        "bezeichnung":      {"type": "string"},
        "menge":            {"type": "number"},
        "einzelpreisNetto": {"type": "number"},
        "mwstProzent":      {"type": "number"},
    })},
    "zusatzkosten": {"type": "array", "items": _objekt({
        "bezeichnung": {"type": "string"},
        "betragNetto": {"type": "number", "description": "negativ bei Rabatt/Gutschrift"},
        "mwstProzent": {"type": "number"},
    })},
})

SYSTEM = (
    "Du liest Lieferantenrechnungen und gibst die Werte als JSON zurück. "
    "Regeln, die ohne Ausnahme gelten:\n"
    "1. Übernimm ausschließlich Zahlen, die WÖRTLICH im Text stehen. Rechne nichts "
    "aus, schätze nichts, ergänze nichts.\n"
    "2. Findest du einen Wert nicht, lass das Feld leer bzw. 0 – ein fehlender Wert "
    "ist harmlos, ein erfundener richtet Schaden an.\n"
    "3. rechnungsnummer ist die Nummer, die der LIEFERANT seiner Rechnung gegeben "
    "hat: 'Rechnungs-Nr.', 'Rechnungsnummer', 'Invoice No.', 'Beleg-Nr.', 'N°'. "
    "Sie ist AUSDRÜCKLICH NICHT die Bestellnummer (BST-…, 'Ihre Bestellung', "
    "'Customer PO', 'Referenz'), nicht die Kundennummer, nicht die "
    "Lieferscheinnummer und nicht die Auftragsnummer. Die unten mitgelieferte "
    "Bestellung dient nur dem Abgleich der Positionen – ihre Nummer darf niemals "
    "als rechnungsnummer erscheinen.\n"
    "4. belegdatum ist das Rechnungsdatum, nicht das Lieferdatum, nicht das "
    "Bestelldatum und nicht das Druckdatum.\n"
    "5. Alle Beträge NETTO je Stück, ohne Währungszeichen, Punkt als Dezimaltrenner. "
    "Deutsche Schreibweise 1.234,56 bedeutet 1234.56.\n"
    "6. positionen sind nur die gelieferten Waren, jede Zeile GENAU EINMAL. Fracht, "
    "Zuschläge, Rabatte, Skonto und Pfand gehören NICHT zu den Positionen, sondern "
    "unter zusatzkosten (Rabatte und Gutschriften mit negativem Betrag).\n"
    "7. Übernimm keine Zwischensummen, Übertragszeilen oder Wiederholungen aus "
    "einem Seitenkopf als Position. Zeilen mit Betrag 0,00 (etwa 'Freight: 0,00') "
    "gehören nirgendwohin – weglassen.\n"
    "8. menge mal einzelpreisNetto muss den Zeilenbetrag der Rechnung ergeben. "
    "Rechnet der Lieferant je Gebinde ab (z. B. '24 Kartons à 20,80'), nimm dessen "
    "Menge und dessen Preis – nicht die Stückzahl im Karton.\n"
    "9. Die mitgelieferte Bestellung ist die Vorlage: passt eine Rechnungszeile "
    "dazu, übernimm deren Artikelnummer unverändert. Erfinde keine Artikelnummer "
    "und übertrage keine Menge oder Preise aus der Bestellung, die nicht auf der "
    "Rechnung stehen."
)


def artikel_aus_bestellung(vorlage: list[dict], menge: float, ek: float,
                           bezeichnung: str) -> Optional[str]:
    """Unsere eigene Artikelnummer aus der erkannten Bestellung holen.

    Lieferanten drucken ihre eigenen Artikelnummern auf die Rechnung („06353"),
    nicht unsere („A-100101"). Die KI kann daraus nichts machen, und in
    `tliefartikel` steht die Zuordnung längst nicht immer. Da die Bestellung aber
    feststeht, ist der Artikel bereits bekannt — er muss nur zugeordnet werden.

    Zugeordnet wird nur bei **eindeutigem** Treffer: gleicher Einzelpreis, sonst
    gleicher Preis UND gleiche Menge. Bleiben mehrere Kandidaten oder passt der
    Preis nicht, wird nichts gesetzt — dann fragt das Formular. Raten wäre hier
    besonders schädlich, weil eine falsche Artikelnummer den Wareneingang der
    falschen Bestellposition zuordnet.
    """
    if not vorlage:
        return None
    genau = [v for v in vorlage if v["cArtNr"] and abs(v["ekNetto"] - ek) < 0.005]
    if len(genau) == 1:
        return genau[0]["cArtNr"]
    if len(genau) > 1:
        mit_menge = [v for v in genau if abs(v["menge"] - menge) < 1e-9]
        if len(mit_menge) == 1:
            return mit_menge[0]["cArtNr"]
    return None


def _zahl(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip().replace("€", "").replace(" ", "")
    if not s:
        return 0.0
    # 1.234,56 → 1234.56 ; 1,234.56 → 1234.56
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _datum(v) -> Optional[datetime.datetime]:
    s = str(v or "").strip()
    for f in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            continue
    return None


async def lese_pdf_rechnung(data: bytes, filename: str, connection_id: int,
                            db, modell: Optional[str] = None) -> tuple[ERKopfInput, dict]:
    """Ein gewöhnliches PDF in einen ERKopfInput übersetzen.

    Gibt zusätzlich einen Befund zurück (erkannte Bestellung, Hinweise), damit
    das Formular zeigen kann, worauf die Auslesung beruht.
    """
    txt = pdf_text(data)
    if len(txt.strip()) < 200:
        raise ERechnungParseError(
            "Das PDF enthält keine Textebene (vermutlich ein Scan). Für solche "
            "Belege bräuchte es eine Texterkennung – bitte von Hand erfassen.")

    conn_row = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    if not conn_row:
        raise ERechnungParseError(f"Verbindung {connection_id} gibt es nicht")
    engine = create_engine(get_engine_str(conn_row), pool_pre_ping=True)

    befund: dict = {"quelle": "pdf_ki", "zeichen": len(txt)}
    with engine.connect() as conn:
        bestellung = finde_bestellung(conn, nummer_kandidaten(txt))
        positionen_vorlage = []
        if bestellung:
            positionen_vorlage = bestellpositionen(
                conn, bestellung["kLieferantenBestellung"])
    befund["bestellung"] = bestellung
    befund["bestellpositionen"] = len(positionen_vorlage)

    from app.services.ai_service import build_ai_service
    svc = build_ai_service(db)
    if svc is None:
        raise ERechnungParseError(
            "Für PDF-Rechnungen ohne E-Rechnungsdaten wird die KI-Auslesung "
            "gebraucht, die KI-Integration ist aber ausgeschaltet "
            "(Systemeinstellungen → KI).")

    teile = [f"RECHNUNGSTEXT:\n{txt[:MAX_TEXT]}"]
    if bestellung:
        teile.append(
            f"\nZUGEHÖRIGE BESTELLUNG (nur zum Abgleich der Positionen – die "
            f"Bestellnummer {bestellung['cEigeneBestellnummer']} ist NICHT die "
            f"Rechnungsnummer) bei {bestellung['cFirma']}:\n"
            + json.dumps(positionen_vorlage, ensure_ascii=False, indent=1))
    antwort = await svc.complete_json(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": "\n".join(teile)}],
        json_schema=SCHEMA, temperature=0.0, model=modell)

    positionen = []
    for p in (antwort.get("positionen") or []):
        menge = _zahl(p.get("menge"))
        if menge == 0:
            continue
        gelesene_nr = (p.get("artikelnummer") or "").strip() or None
        ek = _zahl(p.get("einzelpreisNetto"))
        bezeichnung = (p.get("bezeichnung") or "").strip()[:255] or "Position"
        eigene = artikel_aus_bestellung(positionen_vorlage, menge, ek, bezeichnung)
        positionen.append(ERPositionInput(
            cName=bezeichnung,
            fMenge=menge,
            fEKNetto=ek,
            fMwSt=_zahl(p.get("mwstProzent")),
            # Unsere Nummer aus der Bestellung, sonst die gelesene versuchen.
            cArtNr=eigene or gelesene_nr,
            # Die gelesene Nummer ist meist die des LIEFERANTEN – so kann der
            # Writer notfalls über tliefartikel auflösen.
            cLieferantenArtNr=gelesene_nr,
            bestellnummer=bestellung["cEigeneBestellnummer"] if bestellung else None,
        ))
    if not positionen:
        raise ERechnungParseError(
            "Aus dem PDF ließen sich keine Rechnungspositionen lesen.")

    zusatz = []
    for z in (antwort.get("zusatzkosten") or []):
        betrag = _zahl(z.get("betragNetto"))
        if abs(betrag) < 0.005:
            continue          # Nullzeilen wie „Freight: 0,00" sind keine Kosten
        zusatz.append(ERZusatzkostenInput(
            cName=(z.get("bezeichnung") or "Zusatzkosten").strip()[:120],
            betrag=abs(betrag), fMwSt=_zahl(z.get("mwstProzent")),
            ist_zuschlag=betrag > 0))

    belegdatum = _datum(antwort.get("belegdatum"))
    if belegdatum is None:
        raise ERechnungParseError(
            "Im PDF war kein Belegdatum lesbar – ohne Datum keine Buchung.")

    kopf = ERKopfInput(
        cFremdbelegnummer=(antwort.get("rechnungsnummer") or "").strip()[:50],
        dBelegdatum=belegdatum,
        dZahlungsziel=_datum(antwort.get("zahlungsziel")),
        positionen=positionen,
        zusatzkosten=zusatz,
        nettoSumme=_zahl(antwort.get("nettoSumme")) or None,
        steuerSumme=_zahl(antwort.get("steuerSumme")) or None,
        bruttoSumme=_zahl(antwort.get("bruttoSumme")) or None,
        kLieferant=bestellung["kLieferant"] if bestellung else None,
        bestellnummer=bestellung["cEigeneBestellnummer"] if bestellung else None,
        quelle="pdf_ki",
    )
    if not kopf.cFremdbelegnummer:
        raise ERechnungParseError(
            "Im PDF war keine Rechnungsnummer lesbar – ohne sie greift die "
            "Dublettenprüfung nicht.")
    return kopf, befund

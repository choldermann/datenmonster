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

# So oft wird die Auslesung wiederholt, solange die gelesenen Zeilen nicht die
# Nettosumme der Rechnung ergeben (siehe lese_pdf_rechnung).
VERSUCHE = 3

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
    # Zolldaten stehen auf Auslandsrechnungen oft je Position dabei („Customs
    # Code", „Origin", „Unitary Weight"). Sie werden NICHT gebucht, sondern nur
    # vorgehalten, falls der Anwender aus dem Beleg heraus einen neuen Artikel
    # anlegt — dann muss er sie nicht abtippen.
    #
    # Bewusst ein eigener Block und nicht drei Felder je Position: die
    # Positionszeilen hängen an der Summenprüfung, die diese Auslesung
    # verlässlich macht. Was hier danebengeht, kann dort nichts kaputtmachen.
    "stammdaten": {"type": "array", "items": _objekt({
        "artikelnummer":  {"type": "string", "description": "wie in der Position"},
        "warennummer":    {"type": "string", "description": "Zolltarif-/Customs-Code, sonst leer"},
        "herkunftsland":  {"type": "string", "description": "Ursprungsland, sonst leer"},
        "gewichtKg":      {"type": "number", "description": "Stückgewicht in kg, sonst 0"},
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
    "7. Eine Position ist NUR eine Zeile mit eigenem Zeilenbetrag ganz rechts. "
    "Artikelbeschreibungen laufen oft über mehrere Zeilen weiter; solche "
    "Fortsetzungszeilen gehören zur Position darüber, auch wenn am Zeilenanfang "
    "eine Zahl steht (Positionsnummer, Verpackungseinheit, interne Nummer). Lege "
    "dafür KEINE zweite Position an. Ebenso wenig für Zwischensummen, "
    "Übertragszeilen, Seitenkopf-Wiederholungen oder Zeilen mit Betrag 0,00.\n"
    "8. Prüfe zum Schluss: die Summe deiner Positionen plus der Zusatzkosten muss "
    "die Nettosumme der Rechnung ergeben. Stimmt das nicht, hast du eine Zeile "
    "doppelt gezählt oder eine Fortsetzungszeile als Position genommen.\n"
    "9. menge mal einzelpreisNetto muss den Zeilenbetrag der Rechnung ergeben. "
    "Rechnet der Lieferant je Gebinde ab (z. B. '24 Kartons à 20,80'), nimm dessen "
    "Menge und dessen Preis – nicht die Stückzahl im Karton.\n"
    "10. Der Prozentsatz NEBEN einem Zuschlag ist dessen eigener Satz (z. B. "
    "'LOGISTIKZUSCHLAG 4,70 % 4,41'), NICHT die Mehrwertsteuer. Zusatzkosten "
    "tragen denselben Mehrwertsteuersatz wie die Ware, solange die Rechnung nicht "
    "ausdrücklich einen anderen ausweist.\n"
    "11. Die mitgelieferte Bestellung ist die Vorlage: passt eine Rechnungszeile "
    "dazu, übernimm deren Artikelnummer unverändert. Erfinde keine Artikelnummer "
    "und übertrage keine Menge oder Preise aus der Bestellung, die nicht auf der "
    "Rechnung stehen.\n"
    "12. artikelnummer nur, wenn in der Zeile wirklich eine steht. Reine "
    "Kostenzeilen ('TOOLING COSTS', 'Verpackung') tragen oft keine – dann bleibt "
    "das Feld leer. Leite niemals eine Nummer aus der Positionsnummer, aus "
    "Nachbarzeilen oder aus einem Muster ab.\n"
    "13. stammdaten NUR füllen, wenn der Beleg die Angaben ausdrücklich nennt "
    "('Customs Code', 'Zolltarifnummer', 'Origin', 'Ursprungsland', 'Unitary "
    "Weight', 'Gewicht'). Steht nichts da, lass den Block leer – rate kein "
    "Ursprungsland aus dem Firmensitz des Lieferanten und kein Gewicht aus der "
    "Art der Ware."
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


# Zeilen, an denen ein Positionsblock endet: ab hier geht es um den ganzen Beleg,
# nicht mehr um die einzelne Ware. Bewusst großzügig – lieber ein Ausschnitt zu
# kurz als einer, der die Rechnungssummen mit in die Position zieht.
_FUSSZEILE = re.compile(
    r"nettobetrag|bruttobetrag|mwst|mehrwertsteuer|gesamtbetrag|rechnungsbetrag"
    r"|zwischensumme|gesamtsumme|zahlungsbedingung|zahlungsziel|umsatzsteuer"
    r"|endbetrag|total|versandart|lieferbedingung", re.I)

# So viele Zeilen umfasst ein Ausschnitt hoechstens. Drei Folgezeilen decken das
# ab, was bei den Testrechnungen wirklich zur Position gehört (Zwischensumme,
# Rabatt, Chargen-/Größenzeile).
MAX_BLOCKZEILEN = 4


def _spaltenkopf(zeilen: list[str], erste_position: int) -> Optional[str]:
    """Die Spaltenzeile der Positionstabelle, oberhalb der ersten Position.

    Einfach "die Zeile darüber" zu nehmen reicht nicht: bei Voormann stehen
    dort erst eine Trennlinie aus Gleichheitszeichen und eine Zustellnotiz, die
    Überschrift kommt vier Zeilen höher. Erkennbar ist sie daran, was eine
    Überschrift ausmacht — mehrere Beschriftungen nebeneinander, getrennt durch
    Spaltenabstände. Fließtext und Trennlinien haben das nicht. Findet sich
    keine, kommt lieber nichts zurueck als die falsche Zeile.
    """
    for i in range(erste_position - 1, max(erste_position - 9, -1), -1):
        gruppen = [g for g in re.split(r"\s{2,}", zeilen[i].strip()) if g]
        if len(gruppen) >= 3:
            return zeilen[i].rstrip()
    return None


def belegblock_je_position(txt: str, positionen: list) -> Optional[str]:
    """Jeder Position den Wortlaut mitgeben, aus dem sie gelesen wurde.

    Anlass ist die Atlas-Rechnung 4581692. Sie führt Konfektionsgroessen als
    SPALTEN:

        Art.-Nr.  Bezeichnung          40  41  42  43  44  45  46  47  Mg  Preis
        23200     SL 26 green ESD                               3       3  69,10

    Die Ware ist Größe 46 – erkennbar allein daran, unter welcher Überschrift
    die 3 steht. In der Rechnung heißt der Artikel 23200, bei uns 23200-46. Wer
    im Formular nur die ausgelesenen Felder sieht, kann diese Zuordnung nicht
    treffen; mit dem Originalausschnitt ist sie offensichtlich.

    Gesucht wird über Anker, die schon feststehen (gelesene Artikelnummer,
    Preis, Bezeichnung) – die KI wird dafuer nicht noch einmal gefragt. Der
    Ausschnitt ist eine Lesehilfe und wird nirgends gebucht; findet sich eine
    Zeile nicht wieder, bleibt sie eben ohne. Zurueck kommt die Spaltenzeile der
    Tabelle, denn die gehört zum Beleg und nicht zu einer einzelnen Position.
    """
    zeilen = txt.splitlines()
    flach = [_ohne_leerraum(z) for z in zeilen]

    def finde(anker: str, ab: int) -> Optional[int]:
        a = _ohne_leerraum(anker)
        if len(a) < 3:
            return None                     # zu kurz, trifft ueberall
        for i in range(ab, len(zeilen)):
            if a in flach[i]:
                return i
        return None

    # Der Reihe nach suchen: Positionen stehen im Beleg in derselben Reihenfolge
    # wie in der Auslesung, und so kann keine Zeile den Anker einer spaeteren
    # an sich ziehen (bei gleichen Preisen sonst leicht moeglich).
    anker_index: dict[int, int] = {}
    ab = 0
    for n, p in enumerate(positionen):
        for anker in (p.cLieferantenArtNr, p.cArtNr,
                      f"{p.fEKNetto:.2f}".replace(".", ","), (p.cName or "")[:24]):
            if not anker:
                continue
            i = finde(str(anker), ab)
            if i is not None:
                anker_index[n] = i
                ab = i + 1
                break
    if not anker_index:
        return None

    grenzen = sorted(anker_index.values())
    tabellenkopf = _spaltenkopf(zeilen, grenzen[0])

    for n, p in enumerate(positionen):
        i = anker_index.get(n)
        if i is None:
            continue
        naechste = next((g for g in grenzen if g > i), len(zeilen))
        block: list[str] = []
        for z in zeilen[i:min(i + MAX_BLOCKZEILEN, naechste, len(zeilen))]:
            # Eine Leerzeile beendet den Block: was dahinter steht, gehört nicht
            # mehr zur Ware (bei Voormann folgt dort der Palettenhinweis).
            if block and (not z.strip() or _FUSSZEILE.search(z)):
                break
            block.append(z.rstrip())
        while block and not block[-1].strip():
            block.pop()
        p.belegtext = "\n".join(block)
    return tabellenkopf


def ordne_ueber_menge_zu(positionen: list, vorlage: list[dict]) -> int:
    """Zeilen ohne Preistreffer über die MENGE zuordnen.

    Anlass war die Eurostat-Rechnung INV57645: der Lieferant rechnet Ware und
    Veredelung getrennt ab (Kittel 17,04 + Logodruck 4,50 + Tooling 50,00 auf
    37 Stück), die Bestellung führt beides in einem Preis zusammen (22,89 — das
    ist genau 17,04 + 4,50 + 50,00/37). Kein einziger Preis passte, also blieb
    jede Zeile ohne Artikel, obwohl die Bestellung eindeutig feststand.

    Die Menge ist der zweite belastbare Anker: sie steht auf beiden Seiten und
    wird unterwegs nicht umgerechnet. Sie ist aber schwächer als der Preis —
    viele Zeilen haben Menge 1 —, deshalb wird sie nur benutzt, wenn die
    Zuordnung von BEIDEN Seiten eindeutig ist: genau eine noch offene
    Bestellposition mit dieser Menge und genau eine noch offene Rechnungszeile
    mit dieser Menge. Damit kann keine Zeile die Bestellposition einer anderen
    an sich ziehen; bleibt es mehrdeutig, wird nichts gesetzt und das Formular
    fragt. Jede so entstandene Zuordnung wird als Hinweis an IHRER Zeile
    ausgewiesen, denn sie beruht auf weniger Belegen als ein Preistreffer.
    Zurück kommt nur, wie viele Zeilen so zugeordnet wurden.
    """
    if not vorlage or not positionen:
        return 0
    # Aus der Bestellung stammt eine Nummer genau dann, wenn sie dort vorkommt.
    # Alles andere in cArtNr ist die vom Lieferanten gedruckte Nummer.
    aus_bestellung = {v["cArtNr"] for v in vorlage if v["cArtNr"]}
    vergeben = {p.cArtNr for p in positionen if p.cArtNr in aus_bestellung}
    offen_best = [v for v in vorlage
                  if v["cArtNr"] and v["cArtNr"] not in vergeben]
    offen_pos = [p for p in positionen if p.cArtNr not in aus_bestellung]
    getroffen = 0
    for pos in offen_pos:
        passend = [v for v in offen_best if abs(v["menge"] - pos.fMenge) < 1e-9]
        konkurrenz = [q for q in offen_pos if abs(q.fMenge - pos.fMenge) < 1e-9]
        if len(passend) == 1 and len(konkurrenz) == 1:
            pos.cArtNr = passend[0]["cArtNr"]
            offen_best.remove(passend[0])
            pos.leser_hinweise.append(
                f"Über die Menge zugeordnet ({pos.fMenge:g} Stück), nicht über den "
                f"Preis → {pos.cArtNr}. Der Rechnungspreis weicht vom Bestellpreis "
                f"ab – bitte gegenprüfen.")
            getroffen += 1
    return getroffen


def _ohne_leerraum(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


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

    sichtbarer_text = txt[:MAX_TEXT]
    txt_flach = _ohne_leerraum(sichtbarer_text)
    teile = [f"RECHNUNGSTEXT:\n{sichtbarer_text}"]
    if bestellung:
        teile.append(
            f"\nZUGEHÖRIGE BESTELLUNG (nur zum Abgleich der Positionen – die "
            f"Bestellnummer {bestellung['cEigeneBestellnummer']} ist NICHT die "
            f"Rechnungsnummer) bei {bestellung['cFirma']}:\n"
            + json.dumps(positionen_vorlage, ensure_ascii=False, indent=1))
    # Die Auslesung streut von Lauf zu Lauf – dreimal derselbe Beleg ergab
    # dreimal ein anderes Ergebnis. Statt das hinzunehmen, nutzen wir eine Probe,
    # die die Rechnung selbst mitliefert: die Summe ihrer Positionen und
    # Zusatzkosten MUSS die ausgewiesene Nettosumme ergeben. Geht sie nicht auf,
    # ist mindestens eine Zeile falsch gelesen — dann wird neu gefragt.
    #
    # Das ist keine Schönfärberei: geprüft wird gegen eine Zahl aus dem Beleg,
    # nicht gegen eine Erwartung von uns. Und geht es nach drei Versuchen nicht
    # auf, wird der beste Versuch weitergereicht — die Summenkontrolle im Writer
    # blockiert ihn dann ohnehin, aber der Mensch sieht, woran es lag.
    async def ein_versuch() -> tuple[list, list, dict]:
        antwort = await svc.complete_json(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": "\n".join(teile)}],
            json_schema=SCHEMA, temperature=0.0, model=modell)

        pos_liste = []
        for p in (antwort.get("positionen") or []):
            menge = _zahl(p.get("menge"))
            if menge == 0:
                continue
            gelesene_nr = (p.get("artikelnummer") or "").strip() or None
            # Was der Lieferant nicht gedruckt hat, kann die KI nicht gelesen
            # haben. Anlass: die Zeile „TOOLING COSTS" trägt gar keine Nummer,
            # die KI lieferte trotzdem eine – in drei Wiederholungsläufen drei
            # verschiedene. Folgenlos, weil sie nirgends auflöst, aber eine
            # erfundene Nummer gehört nicht in ein Buchungsformular. Geprüft
            # wird gegen den Text, den die KI gesehen hat, ohne Leerraum: PDFs
            # zerlegen Nummern gern durch Ausrichtungsabstände.
            if gelesene_nr and _ohne_leerraum(gelesene_nr) not in txt_flach:
                gelesene_nr = None
            ek = _zahl(p.get("einzelpreisNetto"))
            bezeichnung = (p.get("bezeichnung") or "").strip()[:255] or "Position"
            eigene = artikel_aus_bestellung(positionen_vorlage, menge, ek, bezeichnung)
            pos_liste.append(ERPositionInput(
                cName=bezeichnung, fMenge=menge, fEKNetto=ek,
                fMwSt=_zahl(p.get("mwstProzent")),
                # Unsere Nummer aus der Bestellung, sonst die gelesene versuchen.
                cArtNr=eigene or gelesene_nr,
                # Die gelesene Nummer ist meist die des LIEFERANTEN – so kann der
                # Writer notfalls über tliefartikel auflösen.
                cLieferantenArtNr=gelesene_nr,
                bestellnummer=bestellung["cEigeneBestellnummer"] if bestellung else None,
            ))

        zk_liste = []
        for z in (antwort.get("zusatzkosten") or []):
            betrag = _zahl(z.get("betragNetto"))
            if abs(betrag) < 0.005:
                continue      # Nullzeilen wie „Freight: 0,00" sind keine Kosten
            zk_liste.append(ERZusatzkostenInput(
                cName=(z.get("bezeichnung") or "Zusatzkosten").strip()[:120],
                betrag=abs(betrag), fMwSt=_zahl(z.get("mwstProzent")),
                ist_zuschlag=betrag > 0))
        return pos_liste, zk_liste, antwort

    def netto_summe(pos_liste, zk_liste) -> float:
        w = sum(p.fMenge * p.fEKNetto for p in pos_liste)
        w += sum((z.betrag if z.ist_zuschlag else -z.betrag) for z in zk_liste)
        return round(w, 2)

    hinweise: list[str] = []
    bester = None
    for versuch in range(1, VERSUCHE + 1):
        positionen, zusatz, antwort = await ein_versuch()
        if not positionen:
            continue
        soll = _zahl(antwort.get("nettoSumme"))
        abweichung = abs(netto_summe(positionen, zusatz) - soll) if soll else None
        if bester is None or (abweichung is not None and bester[0] is not None
                              and abweichung < bester[0]):
            bester = (abweichung, positionen, zusatz, antwort)
        if abweichung is None or abweichung < 0.02:
            if versuch > 1:
                hinweise.append(
                    f"Die Auslesung ging erst im {versuch}. Versuch mit der "
                    f"Rechnungssumme zusammen – die vorherigen Versuche wichen ab.")
            break
    if bester is None:
        raise ERechnungParseError(
            "Aus dem PDF ließen sich keine Rechnungspositionen lesen.")
    abweichung, positionen, zusatz, antwort = bester
    if abweichung is not None and abweichung >= 0.02:
        hinweise.append(
            f"Auch nach {VERSUCHE} Versuchen ergeben die gelesenen Zeilen nicht die "
            f"Nettosumme der Rechnung (Abweichung {abweichung:.2f}). Mindestens eine "
            f"Zeile ist falsch gelesen – bitte am Beleg prüfen.")

    # Was der Preisabgleich offen gelassen hat, jetzt über die Menge versuchen.
    # Bewusst erst hier, auf dem gewählten Versuch: die Zuordnung schaut auf alle
    # Zeilen zugleich und braucht deshalb die endgültige Liste.
    # Der Hinweis dazu hängt jetzt an der jeweiligen Zeile, nicht am Kopf: er
    # betrifft genau eine Position, und in der Sammelliste am Fuß des Formulars
    # musste der Anwender die gemeinte Zeile erst wieder suchen.
    ordne_ueber_menge_zu(positionen, positionen_vorlage)

    # Jeder Zeile den Wortlaut mitgeben, aus dem sie stammt. Erst danach, damit
    # der Ausschnitt zu der Zuordnung passt, die am Ende im Formular steht.
    tabellenkopf = belegblock_je_position(sichtbarer_text, positionen)

    # Zolldaten je Lieferanten-Artikelnummer ablegen. Sie werden nirgends
    # gebucht – das Formular greift nur danach, wenn jemand aus einer nicht
    # zuordenbaren Zeile heraus einen neuen Artikel anlegt.
    befund["stammdaten"] = {
        nr: {"warennummer": (s.get("warennummer") or "").strip(),
             "herkunftsland": (s.get("herkunftsland") or "").strip(),
             "gewichtKg": _zahl(s.get("gewichtKg")) or None}
        for s in (antwort.get("stammdaten") or [])
        if (nr := (s.get("artikelnummer") or "").strip())
    }

    # Steuersatz der Zusatzkosten notfalls aus der Rechnungssumme herleiten.
    # Kein Raten: es wird nur übernommen, wenn die vom Lieferanten selbst
    # ausgewiesene Endsumme damit exakt aufgeht. Anlass war ein Zuschlag, neben
    # dem „4,70 %" stand – dessen eigener Satz, nicht die Steuer; ausgelesen
    # wurden 0 %, und der Beleg fehlte um genau die 19 % darauf.
    brutto_rechnung = _zahl(antwort.get("bruttoSumme"))
    if zusatz and brutto_rechnung:
        def brutto_mit(zk_saetze: list[float]) -> float:
            w = sum(p.fMenge * p.fEKNetto * (1 + p.fMwSt / 100) for p in positionen)
            for z, satz in zip(zusatz, zk_saetze):
                w += (z.betrag if z.ist_zuschlag else -z.betrag) * (1 + satz / 100)
            return round(w, 2)
        ist = [z.fMwSt for z in zusatz]
        if abs(brutto_mit(ist) - brutto_rechnung) >= 0.02:
            saetze = {p.fMwSt for p in positionen if p.fMwSt}
            if len(saetze) == 1:
                waren_satz = saetze.pop()
                versuch = [waren_satz if not z.fMwSt else z.fMwSt for z in zusatz]
                if abs(brutto_mit(versuch) - brutto_rechnung) < 0.02:
                    for z, satz in zip(zusatz, versuch):
                        z.fMwSt = satz
                    hinweise.append(
                        f"Der Steuersatz der Zusatzkosten war nicht ablesbar. Mit "
                        f"{waren_satz:g} % (dem Satz der Ware) geht die vom Lieferanten "
                        f"ausgewiesene Endsumme {brutto_rechnung:.2f} exakt auf – "
                        f"deshalb übernommen. Bitte am Beleg gegenprüfen.")

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
        leser_hinweise=hinweise,
        belegtabellenkopf=tabellenkopf,
    )
    if not kopf.cFremdbelegnummer:
        raise ERechnungParseError(
            "Im PDF war keine Rechnungsnummer lesbar – ohne sie greift die "
            "Dublettenprüfung nicht.")
    return kopf, befund

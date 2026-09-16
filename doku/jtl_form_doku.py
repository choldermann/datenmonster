#!/usr/bin/env python3
"""Schreibt den handgeschriebenen `doku`-Abschnitt in die Formulare der Templates.

Der Abschnitt ergänzt die automatische Ableitung (`app/services/form_doku.py`):
dort kommen Reiter, Widgets und Quelltabellen her, hier das WOZU — das kann keine
Ableitung erfinden.

    python3 doku/jtl_form_doku.py --pruefen   # Trockenlauf (Standard)
    python3 doku/jtl_form_doku.py --schreiben # schreibt templates/*.json + hebt die Version

Vorbild: doku/jtl_template_wissen.py (gleiche Aufrufform, gleiche Versionslogik).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# ── Die Texte ────────────────────────────────────────────────────────────────
# Je Formularname: intro (Fliesstext, 3-5 Saetze) und hinweise (Stolpersteine,
# die ein Anwender kennen muss, bevor er den Zahlen vertraut).
DOKU = {
    "Geschäftsführer-Cockpit": {
        "intro": (
            "Die Gesamtsicht auf das Unternehmen in einem Bild: Umsatz und Rohertrag mit "
            "Vorjahresvergleich, das Betriebsergebnis nach Abzug der hinterlegten Fixkosten, "
            "wie sich der Kundenstamm entwickelt und wie viel Kapital im Lager gebunden ist. "
            "Gedacht für den wöchentlichen Blick der Geschäftsführung, nicht für die Tagesarbeit. "
            "Jede Kennzahl lässt sich anklicken und bis auf die einzelne Rechnung aufschlüsseln."
        ),
        "hinweise": [
            "Umsatz zählt hier ausgestellte Rechnungen, nicht Auftragseingänge — für die Vertriebssicht "
            "ist das Vertriebs-Cockpit zuständig.",
            "Stornorechnungen sind gegengerechnet. Das kann von der JTL-eigenen Statistik abweichen, "
            "die Stornos teilweise mitzählt.",
        ],
    },
    "Kostenstruktur": {
        "intro": (
            "Hier werden die Fixkosten gepflegt, mit denen das Geschäftsführer-Cockpit das "
            "Betriebsergebnis und den Break-even rechnet. Personal, Miete, Fahrzeuge, Versicherungen "
            "und Sonstiges lassen sich je Monat erfassen. Ohne gepflegte Werte zeigt das "
            "Geschäftsführer-Cockpit den Rohertrag, aber kein Ergebnis."
        ),
        "hinweise": [],
    },
    "Vertriebs-Cockpit": {
        "intro": (
            "Der Vertrieb wird am Auftragseingang gemessen, nicht an der Rechnung — deshalb steht hier "
            "der eingegangene Auftrag im Mittelpunkt, dazu der offene Auftragsbestand, die Angebote mit "
            "Nachfass-Liste sowie die Entwicklung nach Kunden, Artikeln und Mitarbeitern. "
            "Damit lässt sich beantworten, was im Zulauf ist, bevor es sich im Umsatz zeigt."
        ),
        "hinweise": [
            "Aufträge mit dem Kennzeichen MUSTER bleiben außen vor.",
            "Der Mitarbeiterbezug kommt aus dem Erfasser des Auftrags, nicht aus einer "
            "Provisionszuordnung.",
        ],
    },
    "Einkaufs-Cockpit": {
        "intro": (
            "Die Einkaufssicht: Bestellvolumen je Lieferant, welche Bestellungen überfällig sind, wie "
            "termintreu die Lieferanten tatsächlich liefern und welche Verbindlichkeiten offen stehen. "
            "Die Termintreue wird aus echten Wareneingangsbuchungen gerechnet, nicht aus zugesagten "
            "Terminen — sie zeigt also, was passiert ist, nicht was versprochen war."
        ),
        "hinweise": [
            "Teillieferungen zählen erst als pünktlich, wenn die Bestellposition vollständig zugebucht ist.",
        ],
    },
    "Versand-Cockpit": {
        "intro": (
            "Wie schnell und wie zuverlässig die Ware rausgeht: Sendungsaufkommen je Versandart, die "
            "Durchlaufzeit vom Auftrag bis zum Versand, die Qualität der Trackingnummern und der "
            "Rückstand an Lieferscheinen, die noch nicht versendet wurden. Der Rückstand ist die "
            "Zahl, die morgens zählt."
        ),
        "hinweise": [
            "Die Durchlaufzeit misst Kalendertage, nicht Arbeitstage — Wochenenden sind enthalten.",
        ],
    },
    "Stammdaten-Health-Check": {
        "intro": (
            "Sucht die Lücken und Widersprüche in den Artikel- und Kundenstammdaten, die später teuer "
            "werden: fehlende EAN, Gewichte oder Einkaufspreise, Verkaufspreise unter dem Einkaufspreis, "
            "fehlende Warentarifnummer und Herkunftsland für den Zoll, doppelte EANs sowie Kunden ohne "
            "E-Mail und Dubletten. Jede Prüfung hat eine Ampel, damit sich die Arbeit priorisieren lässt."
        ),
        "hinweise": [
            "HIBC-codierte Artikel aus dem Medizinbereich haben bewusst keine klassische EAN und werden "
            "nicht als Fehler gezählt.",
            "Gesperrte und ausgelaufene Artikel sind ausgeblendet, sonst dominieren Altlasten die Listen.",
        ],
    },
    "Lager-Cockpit": {
        "intro": (
            "Der Lagerwert zum Stichtag und im Verlauf, bewertet zum damals gültigen Einkaufspreis, dazu "
            "Disposition mit Fehlmengen und Zulauf, Umschlag und Reichweite sowie die Ladenhüter mit dem "
            "darin gebundenen Kapital. Der Verlauf wird aus der Buchungshistorie rekonstruiert — das "
            "Cockpit kann also auch rückwirkend sagen, was im Lager lag, was JTL selbst nicht beantwortet."
        ),
        "hinweise": [
            "Reservierungen und Zulauf gibt es nur als aktuellen Stand, nicht in der Historie. Auf dem "
            "Reiter Disposition wirkt der Zeitraumfilter deshalb nicht.",
            "Vaterartikel von Variationen werden nicht doppelt gezählt.",
        ],
    },
    "Unternehmensmonitor": {
        "intro": (
            "Die operative Startseite: Was ist heute wichtig, wo besteht Handlungsbedarf? Die Warnungen "
            "werden aus den Auswertungen der übrigen Cockpits abgeleitet und sind deterministisch — "
            "gleiche Daten, gleiche Warnung, keine KI-Interpretation. Die Schwellwerte sind je Projekt "
            "einstellbar, damit die Ampel zum eigenen Betrieb passt."
        ),
        "hinweise": [
            "Der Monitor rechnet nichts Eigenes, er bewertet die Ergebnisse der anderen Cockpits. "
            "Fehlt ein Cockpit, fehlt die zugehörige Warnung.",
        ],
    },
    "Preis- & Marge-Cockpit": {
        "intro": (
            "Zeigt, wo der Ertrag verloren geht: die Rohertragsmarge im Zeitverlauf, Artikel mit "
            "schleichendem Margenverfall samt Ursache, Verkäufe unter Einkaufspreis, die Kalkulation "
            "gegen die hinterlegte Mindestmarge, gestiegene Einkaufspreise und die Marge je Kunde. "
            "Der Nutzen liegt in der Ursache: nicht nur dass die Marge fällt, sondern ob der Einkauf "
            "teurer oder der Verkauf billiger wurde."
        ),
        "hinweise": [
            "Die Marge rechnet mit dem Einkaufspreis zum Zeitpunkt des Verkaufs, nicht mit dem heutigen.",
        ],
    },
    "Intrastat Zeitraum": {
        "intro": (
            "Erzeugt die Intrastat-Meldung für den gewählten Monat — Ausfuhr und Einfuhr, wahlweise als "
            "eSTATISTIK.core-XML für die Online-Meldung oder als Destatis-CSV. Grundlage sind die "
            "Rechnungen mit Warentarifnummer und Herkunftsland aus der JTL-Wawi."
        ),
        "hinweise": [
            "Artikel ohne Warentarifnummer oder Herkunftsland fehlen in der Meldung — der "
            "Stammdaten-Health-Check findet sie vorab.",
            "Bestimmte Artikel lassen sich dauerhaft von der Meldung ausnehmen.",
        ],
    },
    "DATEV-Export": {
        "intro": (
            "Erzeugt aus der JTL-Wawi einen DATEV-Buchungsstapel im offiziellen EXTF-Format (Version 700) "
            "für Ausgangs- und Eingangsrechnungen. Berater- und Mandantennummer sowie die Sachkonten "
            "werden je Mandant gepflegt, damit der Stapel ohne Nacharbeit in die Kanzlei geht."
        ),
        "hinweise": [
            "Eingangsrechnungen kann die JTL-Wawi selbst nicht exportieren — dieser Weg schließt die Lücke.",
        ],
    },
    "Eingangsrechnungs-Import": {
        "intro": (
            "Liest Eingangsrechnungen als E-Rechnung ein (ZUGFeRD/Factur-X und XRechnung), gleicht sie "
            "gegen die Lieferantenbestellung ab, lässt sie im Vier-Augen-Prinzip freigeben und schreibt "
            "sie in die JTL-Wawi. Reine PDF-Rechnungen ohne XML werden ausgelesen, müssen aber geprüft "
            "werden."
        ),
        "hinweise": [
            "Ab 2027 verlangen erste Großkunden den Empfang über Peppol — das betrifft den Transportweg, "
            "nicht dieses Format.",
        ],
    },
}


def bump(version: str) -> str:
    """1.7 -> 1.8, 2.15 -> 2.16."""
    m = re.match(r"^(\d+)\.(\d+)$", str(version or "1.0"))
    if not m:
        return "1.1"
    return f"{m.group(1)}.{int(m.group(2)) + 1}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schreiben", action="store_true", help="Änderungen speichern")
    ap.add_argument("--pruefen", action="store_true", help="Trockenlauf (Standard)")
    args = ap.parse_args()
    schreiben = args.schreiben

    getroffen = set()
    for pfad in sorted(TEMPLATES.glob("*.json")):
        text = pfad.read_text(encoding="utf-8")
        data = json.loads(text)
        formulare = data.get("forms") or []
        if not formulare:
            continue

        geaendert = []
        for form in formulare:
            name = form.get("name")
            eintrag = DOKU.get(name)
            if not eintrag:
                continue
            getroffen.add(name)
            schema = form.setdefault("schema", {})
            if schema.get("doku") == eintrag:
                continue
            schema["doku"] = eintrag
            geaendert.append(name)

        if not geaendert:
            continue

        alt = data.get("version")
        data["version"] = bump(alt)
        print(f"{pfad.name}: {', '.join(geaendert)}  (Version {alt} -> {data['version']})")
        if schreiben:
            # Einrückung der Datei MESSEN, nicht raten: die Vorlagen sind mit 1, 2
            # und 4 Leerzeichen eingerückt. Ein falscher Wert formatiert die ganze
            # Datei um und macht aus einem Dreizeiler einen 5000-Zeilen-Diff.
            m = re.search(r'^\{\n( +)"', text)
            einzug = len(m.group(1)) if m else 2
            ende = "\n" if text.endswith("\n") else ""
            pfad.write_text(
                json.dumps(data, ensure_ascii=False, indent=einzug) + ende,
                encoding="utf-8",
            )

    fehlend = set(DOKU) - getroffen
    if fehlend:
        print("\nWARNUNG – Text geschrieben, aber kein Formular gefunden:", ", ".join(sorted(fehlend)))

    if not schreiben:
        print("\nTrockenlauf. Mit --schreiben wirklich speichern.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

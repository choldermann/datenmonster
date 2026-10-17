"""Fertige Fragen für die Händler-Ansicht (Phase 3).

Jede Frage ist ein fertiger Bauzettel für den Abfrage-Generator – dieselbe
Definition, die man dort von Hand zusammenklicken würde. Damit gelten dieselben
Sicherheitsregeln (nur Schlüssel aus dem Katalog, Werte gebunden) und das
Ergebnis lässt sich wie jede eigene Abfrage speichern.

Die Zahlen in den Bedingungen (90 Tage, 20 %, 180 Tage) sind bewusst einfache
Vorgaben; wer andere will, passt die Frage im Satzbaukasten an (`satz` = dieselbe
Frage als Satz, siehe satz.py) oder öffnet den Abfrage-Generator.
"""

def _und(*kinder):
    return {"op": "UND", "kinder": list(kinder)}


def _b(key, vergleich, wert=None):
    return {"key": key, "vergleich": vergleich, "wert": wert}


FRAGEN = [
    # ── Kunden ──────────────────────────────────────────────────────────────
    {"key": "kunden_inaktiv_90", "satz": {"koernung": "kunde", "bedingung": "inaktiv", "n": 90, "sortierung": "umsatz", "zeitraum": "12_monate"}, "gruppe": "Kunden",
     "titel": "Kunden ohne Bestellung seit 90 Tagen",
     "text": "Kunden, die schon gekauft haben, deren letzte Rechnung aber über 90 Tage zurückliegt – nach Umsatz der letzten zwölf Monate.",
     "zeitraum": "12_monate",
     "definition": {"koernung": "kunde", "kennzahlen": ["umsatz", "letzte_rechnung", "tage_seit_rechnung"],
                    "kennzahlfilter": _und(_b("tage_seit_rechnung", ">", 90), _b("umsatz", ">", 0)),
                    "sortierung": {"key": "umsatz", "richtung": "desc"}, "limit": 500}},
    {"key": "kunden_top", "gruppe": "Kunden",
     "titel": "Die 50 umsatzstärksten Kunden",
     "text": "Umsatz und Anzahl Rechnungen im gewählten Zeitraum.",
     "zeitraum": "dieses_jahr",
     "definition": {"koernung": "kunde", "kennzahlen": ["umsatz", "rechnungen"],
                    "kennzahlfilter": _und(_b("umsatz", ">", 0)),
                    "sortierung": {"key": "umsatz", "richtung": "desc"}, "limit": 50}},
    {"key": "kunden_ware_ohne_rechnung", "satz": {"koernung": "kunde", "bedingung": "ware_ohne_rechnung", "sortierung": "umsatz", "zeitraum": "12_monate"}, "gruppe": "Kunden",
     "titel": "Kunden mit Lieferungen, aber ohne Rechnung",
     "text": "Ware ist rausgegangen, berechnet wurde im Zeitraum nichts.",
     "zeitraum": "12_monate",
     "definition": {"koernung": "kunde", "kennzahlen": ["lieferscheine", "rechnungen", "letzte_lieferung"],
                    "kennzahlfilter": _und(_b("lieferscheine", ">", 0), _b("rechnungen", "=", 0)),
                    "sortierung": {"key": "lieferscheine", "richtung": "desc"}, "limit": 500}},

    # ── Artikel ─────────────────────────────────────────────────────────────
    {"key": "artikel_nachbestellen", "satz": {"koernung": "artikel", "bedingung": "fehlmenge", "sortierung": "auftraege", "zeitraum": "12_monate"}, "gruppe": "Artikel",
     "titel": "Nachbestellen: Bestand reicht nicht für offene Aufträge",
     "text": "Lagerartikel, bei denen in offenen Aufträgen mehr steht als am Lager liegt – mit Zulauf.",
     "zeitraum": "12_monate",
     "definition": {"koernung": "artikel", "kennzahlen": ["menge"],
                    "zeilenfilter": _und(_b("artikel.lagerartikel", "=", 1), _b("artikel.fehlmenge", ">", 0)),
                    "sortierung": {"key": "in_auftraegen", "richtung": "desc"}, "limit": 500}},
    {"key": "artikel_ladenhueter", "satz": {"koernung": "artikel", "bedingung": "ladenhueter", "n": 180, "sortierung": "tage", "zeitraum": "12_monate"}, "gruppe": "Artikel",
     "titel": "Ladenhüter: seit 180 Tagen nicht verkauft",
     "text": "Artikel mit Bestand, die seit mindestens 180 Tagen nicht verkauft wurden (oder nie).",
     "zeitraum": "12_monate",
     "definition": {"koernung": "artikel", "kennzahlen": ["tage_ohne_verkauf", "letzter_verkauf"],
                    "zeilenfilter": _und(_b("artikel.bestand", ">", 0)),
                    "kennzahlfilter": _und(_b("tage_ohne_verkauf", ">", 180)),
                    "sortierung": {"key": "tage_ohne_verkauf", "richtung": "desc"}, "limit": 500}},
    {"key": "artikel_marge_niedrig", "satz": {"koernung": "artikel", "bedingung": "marge_unter", "n": 20, "sortierung": "umsatz", "zeitraum": "dieses_jahr"}, "gruppe": "Artikel",
     "titel": "Artikel unter 20 % Marge",
     "text": "Verkaufte Artikel, deren Marge im Zeitraum unter 20 % lag – die umsatzstärksten zuerst.",
     "zeitraum": "dieses_jahr",
     "definition": {"koernung": "artikel", "kennzahlen": ["umsatz", "rohertrag", "marge"],
                    "kennzahlfilter": _und(_b("marge", "<", 20)),
                    "sortierung": {"key": "umsatz", "richtung": "desc"}, "limit": 500}},
    {"key": "artikel_renner", "gruppe": "Artikel",
     "titel": "Die 50 meistverkauften Artikel",
     "text": "Nach verkaufter Menge im Zeitraum, mit Umsatz und aktuellem Bestand.",
     "zeitraum": "dieses_jahr",
     "definition": {"koernung": "artikel", "kennzahlen": ["menge", "umsatz"],
                    "kennzahlfilter": _und(_b("menge", ">", 0)),
                    "sortierung": {"key": "menge", "richtung": "desc"}, "limit": 50}},

    # ── Aufträge ────────────────────────────────────────────────────────────
    {"key": "auftraege_gross", "satz": {"koernung": "auftrag", "bedingung": "wert_ueber", "n": 1000, "sortierung": "wert", "zeitraum": "letzte_30"}, "gruppe": "Aufträge",
     "titel": "Aufträge über 1.000 € netto",
     "text": "Alle größeren Aufträge im Zeitraum, die wertvollsten zuerst.",
     "zeitraum": "letzte_30",
     "definition": {"koernung": "auftrag",
                    "zeilenfilter": _und(_b("auftrag.wert", ">", 1000)),
                    "sortierung": {"key": "auftrag_wert", "richtung": "desc"}, "limit": 500}},

    # ── Einkauf ─────────────────────────────────────────────────────────────
    {"key": "bestellungen_ueberfaellig", "satz": {"koernung": "lieferantenbestellung", "bedingung": "ueberfaellig", "sortierung": "wert"}, "gruppe": "Einkauf",
     "titel": "Überfällige Lieferanten-Bestellungen",
     "text": "Offene Bestellungen, deren Liefertermin verstrichen ist – nach offenem Wert.",
     "zeitraum": None,
     "definition": {"koernung": "lieferantenbestellung",
                    "zeilenfilter": _und(_b("bestellung.offen", "=", 1), _b("bestellung.verzug", ">", 0)),
                    "sortierung": {"key": "bestellung_offener_wert", "richtung": "desc"}, "limit": 500}},
    {"key": "bestellungen_ohne_termin", "satz": {"koernung": "lieferantenbestellung", "bedingung": "ohne_termin", "sortierung": "wert"}, "gruppe": "Einkauf",
     "titel": "Offene Bestellungen ohne Liefertermin",
     "text": "Bestellungen, bei denen die Wawi keinen Termin kennt – oft vergessene Altfälle.",
     "zeitraum": None,
     "definition": {"koernung": "lieferantenbestellung",
                    "zeilenfilter": _und(_b("bestellung.offen", "=", 1), _b("bestellung.liefertermin", "leer")),
                    "sortierung": {"key": "bestellung_offener_wert", "richtung": "desc"}, "limit": 500}},
    {"key": "bestellungen_je_lieferant", "gruppe": "Einkauf",
     "titel": "Offener Bestellwert je Lieferant",
     "text": "Wie viel bei welchem Lieferanten noch aussteht.",
     "zeitraum": None,
     "definition": {"koernung": "lieferantenbestellung", "gruppierung": "lieferant",
                    "kennzahlen": ["anzahl", "offener_wert", "max_verzug"],
                    "zeilenfilter": _und(_b("bestellung.offen", "=", 1)),
                    "sortierung": {"key": "offener_wert", "richtung": "desc"}, "limit": 200}},
]

ZEITRAEUME = {
    "letzte_30": "Letzte 30 Tage",
    "dieses_jahr": "Dieses Jahr",
    "12_monate": "Letzte 12 Monate",
}


def frage(key: str):
    return next((f for f in FRAGEN if f["key"] == key), None)

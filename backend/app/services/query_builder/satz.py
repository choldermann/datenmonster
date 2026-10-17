"""Satzbaukasten der Händler-Ansicht (Phase 4).

„Zeige mir [Objekt], die [Bedingung], sortiert nach [Sortierung].“

Jeder Baustein übersetzt sich in Schlüssel des Abfrage-Generators – der Satz ist
eine bedienbare Oberfläche über demselben Bauzettel, keine zweite Abfragesprache.
Der Wortschatz ist bewusst klein und fest: er ist zugleich das, worauf die KI
eine frei getippte Frage abbilden darf (siehe api/start.py, satz_verstehen).
"""
from . import sql_bauer


def _und(*kinder):
    return {"op": "UND", "kinder": [k for k in kinder if k]}


def _b(key, vergleich, wert=None):
    return {"key": key, "vergleich": vergleich, "wert": wert}


# Jede Bedingung: text (mit {n}, wenn sie eine Zahl braucht), n_vorgabe/einheit,
# und `teil(n)` → Bestandteile der Definition (zeilenfilter, kennzahlfilter, kennzahlen).
OBJEKTE = {
    "kunde": {
        "plural": "Kunden", "zeitraum": True,
        "bedingungen": {
            "gekauft": {"text": "im Zeitraum gekauft haben", "stichworte": "Kunden mit Umsatz, beste Kunden, Top-Kunden",
                        "teil": lambda n: {"kennzahlen": ["umsatz", "rechnungen"],
                                           "kennzahlfilter": _und(_b("umsatz", ">", 0))}},
            "inaktiv": {"text": "seit mehr als {n} Tagen nicht bestellt haben", "stichworte": "eingeschlafen, inaktiv, lange nicht gekauft, verloren", "n": 90, "einheit": "Tage",
                        "teil": lambda n: {"kennzahlen": ["umsatz", "letzte_rechnung", "tage_seit_rechnung"],
                                           "kennzahlfilter": _und(_b("tage_seit_rechnung", ">", n))}},
            "umsatz_ueber": {"text": "im Zeitraum mehr als {n} € Umsatz hatten", "stichworte": "große Kunden, Umsatz über", "n": 10000, "einheit": "€",
                             "teil": lambda n: {"kennzahlen": ["umsatz", "rechnungen"],
                                                "kennzahlfilter": _und(_b("umsatz", ">", n))}},
            "ware_ohne_rechnung": {"text": "Ware bekommen, aber keine Rechnung erhalten haben", "stichworte": "geliefert aber nicht berechnet, fehlende Rechnung",
                                   "teil": lambda n: {"kennzahlen": ["lieferscheine", "rechnungen", "letzte_lieferung", "umsatz"],
                                                      "kennzahlfilter": _und(_b("lieferscheine", ">", 0),
                                                                             _b("rechnungen", "=", 0))}},
        },
        "sortierungen": {
            "umsatz": {"text": "Umsatz", "key": "umsatz", "richtung": "desc", "braucht": "umsatz"},
            "letzte_rechnung": {"text": "letzter Rechnung", "key": "letzte_rechnung", "richtung": "desc",
                                "braucht": "letzte_rechnung"},
            "name": {"text": "Name", "key": "name", "richtung": "asc"},
        },
    },
    "artikel": {
        "plural": "Artikel", "zeitraum": True,
        "bedingungen": {
            "verkauft": {"text": "im Zeitraum verkauft wurden", "stichworte": "Renner, Bestseller, meistverkauft, Absatz",
                         "teil": lambda n: {"kennzahlen": ["menge", "umsatz"],
                                            "kennzahlfilter": _und(_b("menge", ">", 0))}},
            "fehlmenge": {"text": "nicht genug Bestand für offene Aufträge haben", "ohne_zeitraum": True, "stichworte": "nachbestellen, Fehlmenge, Bestand reicht nicht, ausverkauft, Engpass",
                          "teil": lambda n: {"kennzahlen": ["menge"],
                                             "zeilenfilter": _und(_b("artikel.lagerartikel", "=", 1),
                                                                  _b("artikel.fehlmenge", ">", 0))}},
            "ladenhueter": {"text": "seit mehr als {n} Tagen nicht verkauft wurden", "ohne_zeitraum": True, "stichworte": "Ladenhüter, Penner, liegt rum, totes Kapital", "n": 180, "einheit": "Tage",
                            "teil": lambda n: {"kennzahlen": ["tage_ohne_verkauf", "letzter_verkauf"],
                                               "zeilenfilter": _und(_b("artikel.bestand", ">", 0)),
                                               "kennzahlfilter": _und(_b("tage_ohne_verkauf", ">", n))}},
            "marge_unter": {"text": "mit weniger als {n} % Marge verkauft wurden", "stichworte": "schlechte Marge, wenig Gewinn, Rohertrag niedrig", "n": 20, "einheit": "%",
                            "teil": lambda n: {"kennzahlen": ["umsatz", "rohertrag", "marge"],
                                               "kennzahlfilter": _und(_b("marge", "<", n))}},
        },
        "sortierungen": {
            "umsatz": {"text": "Umsatz", "key": "umsatz", "richtung": "desc", "braucht": "umsatz"},
            "menge": {"text": "verkaufter Menge", "key": "menge", "richtung": "desc", "braucht": "menge"},
            "tage": {"text": "Tagen ohne Verkauf", "key": "tage_ohne_verkauf", "richtung": "desc",
                     "braucht": "tage_ohne_verkauf"},
            "auftraege": {"text": "Menge in offenen Aufträgen", "key": "in_auftraegen", "richtung": "desc"},
            "nr": {"text": "Artikelnummer", "key": "nr", "richtung": "asc"},
        },
    },
    "auftrag": {
        "plural": "Aufträge", "zeitraum": True,
        "bedingungen": {
            "eingegangen": {"text": "im Zeitraum eingegangen sind", "stichworte": "Auftragseingang, neue Aufträge", "teil": lambda n: {}},
            "wert_ueber": {"text": "mehr als {n} € netto wert sind", "stichworte": "große Aufträge, Aufträge über", "n": 1000, "einheit": "€",
                           "teil": lambda n: {"zeilenfilter": _und(_b("auftrag.wert", ">", n))}},
        },
        "sortierungen": {
            "wert": {"text": "Auftragswert", "key": "auftrag_wert", "richtung": "desc"},
            "datum": {"text": "Datum", "key": "auftrag_datum", "richtung": "desc"},
        },
    },
    "lieferantenbestellung": {
        "plural": "Lieferanten-Bestellungen", "zeitraum": False,
        "bedingungen": {
            "offen": {"text": "noch offen sind", "stichworte": "offene Bestellungen, ausstehende Lieferungen",
                      "teil": lambda n: {"zeilenfilter": _und(_b("bestellung.offen", "=", 1))}},
            "ueberfaellig": {"text": "überfällig sind", "stichworte": "Verzug, verspätet, Lieferant liefert nicht",
                             "teil": lambda n: {"zeilenfilter": _und(_b("bestellung.offen", "=", 1),
                                                                     _b("bestellung.verzug", ">", 0))}},
            "ohne_termin": {"text": "keinen Liefertermin haben", "stichworte": "ohne Termin, kein Lieferdatum",
                            "teil": lambda n: {"zeilenfilter": _und(_b("bestellung.offen", "=", 1),
                                                                    _b("bestellung.liefertermin", "leer"))}},
            "teilgeliefert": {"text": "nur teilweise geliefert sind", "stichworte": "Teillieferung, Rest offen",
                              "teil": lambda n: {"zeilenfilter": _und(_b("bestellung.offen", "=", 1),
                                                                      _b("bestellung.teilgeliefert", "=", 1))}},
        },
        "sortierungen": {
            "wert": {"text": "offenem Wert", "key": "bestellung_offener_wert", "richtung": "desc"},
            "verzug": {"text": "Tagen Verzug", "key": "bestellung_verzug", "richtung": "desc"},
            "datum": {"text": "Bestelldatum", "key": "bestellung_datum", "richtung": "asc"},
        },
    },
}

ZEITRAEUME = {"letzte_30": "in den letzten 30 Tagen", "dieses_jahr": "in diesem Jahr",
              "12_monate": "in den letzten 12 Monaten"}
# Zeitraum-Vorgabe des Zustellplans bzw. Berichts (computeDatePreset-IDs)
ZEITRAUM_PRESET = {"letzte_30": "days_30", "dieses_jahr": "this_year", "12_monate": "months_12"}

N_GRENZEN = (0, 10_000_000)


def wortschatz() -> dict:
    """Was die Oberfläche (und die KI) zur Auswahl hat – ohne Bauanleitung."""
    return {
        "objekte": [{
            "key": k, "plural": o["plural"], "zeitraum": o["zeitraum"],
            "bedingungen": [{"key": bk, "text": b["text"], "n": b.get("n"), "einheit": b.get("einheit"),
                             "stichworte": b.get("stichworte"),
                             # Bestand und „Tage ohne Verkauf“ hängen nicht am Zeitraum
                             "zeitraum": o["zeitraum"] and not b.get("ohne_zeitraum")}
                            for bk, b in o["bedingungen"].items()],
            "sortierungen": [{"key": sk, "text": s["text"]} for sk, s in o["sortierungen"].items()],
        } for k, o in OBJEKTE.items()],
        "zeitraeume": [{"key": k, "text": v} for k, v in ZEITRAEUME.items()],
    }


def pruefen(auswahl: dict) -> dict:
    """Vervollständigt und prüft eine Auswahl. Wirft AbfrageFehler bei Unsinn."""
    koernung = auswahl.get("koernung")
    o = OBJEKTE.get(koernung)
    if not o:
        raise sql_bauer.AbfrageFehler("Unbekanntes Objekt im Satz.")
    bed = auswahl.get("bedingung") or next(iter(o["bedingungen"]))
    if bed not in o["bedingungen"]:
        raise sql_bauer.AbfrageFehler("Diese Bedingung passt nicht zum gewählten Objekt.")
    b = o["bedingungen"][bed]
    n = auswahl.get("n")
    if "{n}" in b["text"]:
        try:
            n = float(n if n not in (None, "") else b["n"])
        except (TypeError, ValueError):
            raise sql_bauer.AbfrageFehler("Bitte eine Zahl angeben.")
        if not (N_GRENZEN[0] <= n <= N_GRENZEN[1]):
            raise sql_bauer.AbfrageFehler("Die Zahl liegt außerhalb des sinnvollen Bereichs.")
        n = int(n) if n == int(n) else n
    else:
        n = None
    sort = auswahl.get("sortierung") or next(iter(o["sortierungen"]))
    if sort not in o["sortierungen"]:
        raise sql_bauer.AbfrageFehler("Nach diesem Merkmal kann hier nicht sortiert werden.")
    mit_zeitraum = o["zeitraum"] and not b.get("ohne_zeitraum")
    zeitraum = auswahl.get("zeitraum") if mit_zeitraum else None
    if mit_zeitraum and zeitraum not in ZEITRAEUME:
        zeitraum = "12_monate"
    return {"koernung": koernung, "bedingung": bed, "n": n, "sortierung": sort, "zeitraum": zeitraum}


def bauen(auswahl: dict) -> dict:
    """Auswahl → {definition, zeitraum, titel, satz}."""
    a = pruefen(auswahl)
    o = OBJEKTE[a["koernung"]]
    b = o["bedingungen"][a["bedingung"]]
    s = o["sortierungen"][a["sortierung"]]

    teil = b["teil"](a["n"])
    kennzahlen = list(teil.get("kennzahlen") or [])
    # Sortiert werden kann nur nach einer Spalte, die es gibt.
    if s.get("braucht") and s["braucht"] not in kennzahlen:
        kennzahlen.append(s["braucht"])
    definition = {"koernung": a["koernung"], "kennzahlen": kennzahlen,
                  "sortierung": {"key": s["key"], "richtung": s["richtung"]}, "limit": 500}
    for schluessel in ("zeilenfilter", "kennzahlfilter"):
        if teil.get(schluessel):
            definition[schluessel] = teil[schluessel]
    # Kennzahlen der Zeilen-Körnungen gibt es nur gruppiert – ohne Gruppierung
    # sind dort die Felder selbst die Ausgabe.
    if a["koernung"] in ("auftrag", "lieferantenbestellung"):
        definition.pop("kennzahlen")

    bed_text = b["text"].replace("{n}", f"{a['n']:,}".replace(",", ".") if a["n"] is not None else "")
    satz = f"{o['plural']}, die {bed_text}, sortiert nach {s['text']}"
    titel = satz[0].upper() + satz[1:]
    return {"auswahl": a, "definition": definition, "zeitraum": a["zeitraum"],
            "titel": titel[:120], "satz": satz}

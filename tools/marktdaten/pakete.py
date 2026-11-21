"""Branchenpakete „Marktlage …“ – erzeugt je Paket eine Vorlage templates/markt_<id>.json.

Ein Paket ist ERP-unabhängig: es braucht keine Datenbankverbindung, nur die Lizenz (Umfelddaten
kommen vom monstersuite-Datendienst). Inhalt je Paket:
  - Dataset „<Name> – Reihen“ (file_type „umfeld“, Aufbau lang, 6 Jahre)
  - Mapping „Lage“: je Reihe letzter Wert, Wert ein Jahr davor, Veränderung (SQL über das Dataset)
  - Mapping „Verlauf“: eine Zeile je Monat, eine Spalte je Reihe (Beschriftung = Klartext)
  - Formular mit Lagetabelle und je Thema einer Kurve (Rubrik „Marktlage“)

Lauf:  python3 tools/marktdaten/pakete.py
Reihen-Codes stammen aus dem Datenkatalog (Büro › Marktdaten, GET /api/umfeld/datenkatalog).
"""
import json
import os

VERSION = "1.0"
HIER = os.path.dirname(os.path.abspath(__file__))
ZIEL = os.path.normpath(os.path.join(HIER, "..", "..", "templates"))

# (Klartext, Größe, Region, Thema, Prozent-Veränderung sinnvoll?)
PAKETE = {
    "papier_hygiene": {
        "name": "Marktlage Papier, Hygiene & Verpackung",
        "beschreibung": ("Einkaufs- und Verkaufspreise, Nachfrage, Transportkosten und Insolvenzen der Kundenbranchen "
                         "für den Handel mit Hygienepapier, Reinigungsmitteln und Verpackung – aus amtlichen Quellen, "
                         "monatlich aktuell, ohne eigenes Konto."),
        # Vorschläge für die Einstellungen der vorhandenen Cockpits (Widget „Mit Cockpits verknüpfen“)
        "profil": {
            "preisindex": {"key": "preise_grosshandel", "region": "WZ08-46442",
                           "label": "Großhandel: Großh.m. Wasch-, Putz- und Reinigungsmitteln"},
            "branche": {"code": "G464", "label": "Großhandel mit Gebrauchs- und Verbrauchsgütern"},
            "kundenbranchen": [{"code": "WZ08-56", "label": "Gastronomie"}, {"code": "WZ08-55", "label": "Beherbergung"},
                               {"code": "WZ08-812", "label": "Reinigung von Gebäuden, Straßen, Verkehrsmitteln"},
                               {"code": "WZ08-86", "label": "Gesundheitswesen"},
                               {"code": "WZ08-87", "label": "Heime (ohne Erholungs- und Ferienheime)"}],
            "erzeugerpreise": [{"code": "GP19-172211", "label": "Toilettenpapier, Taschen-, Abschmink-, Handtücher"},
                               {"code": "GP19-1721", "label": "Wellpapier und -pappe, Verpackungsmittel"},
                               {"code": "GP19-2222", "label": "Verpackungsmittel aus Kunststoffen"},
                               {"code": "GP19-2041", "label": "Seifen, Wasch-, Reinigungs- und Poliermittel"}],
        },
        "reihen": [
            ("Hygienepapier (Toilettenpapier, Handtücher)", "erzeugerpreise", "GP19-172211", "Einkaufspreise der Hersteller", True),
            ("Wellpappe-Verpackungen", "erzeugerpreise", "GP19-1721", "Einkaufspreise der Hersteller", True),
            ("Kunststoffverpackungen", "erzeugerpreise", "GP19-2222", "Einkaufspreise der Hersteller", True),
            ("Seifen, Wasch- & Reinigungsmittel", "erzeugerpreise", "GP19-2041", "Einkaufspreise der Hersteller", True),
            ("Großhandel Papier & Bürobedarf", "preise_grosshandel", "WZ08-46494", "Verkaufspreise", True),
            ("Großhandel Wasch- & Reinigungsmittel", "preise_grosshandel", "WZ08-46442", "Verkaufspreise", True),
            ("Verbraucherpreise insgesamt", "preise_verbraucher", "Deutschland", "Verkaufspreise", True),
            ("Umsatz Großhandel Gebrauchs- & Verbrauchsgüter (real)", "umsatz_handel_real", "G464", "Nachfrage", True),
            ("Umsatz Gastgewerbe (nominal)", "umsatz_gastgewerbe", "Deutschland", "Nachfrage", True),
            ("Diesel (€/l)", "kraftstoff", "Diesel", "Transportkosten", True),
            ("Insolvenzen Gastronomie", "insolvenzen", "WZ08-56", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Beherbergung", "insolvenzen", "WZ08-55", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Gebäudereinigung", "insolvenzen", "WZ08-812", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Gesundheitswesen & Heime", "insolvenzen", "WZ08-86", "Insolvenzen der Kundenbranchen", True),
            ("Wirtschaftsklima (ESI, Ø = 100)", "stimmung", "BS-ESI-I", "Stimmung", False),
            ("Dienstleister-Vertrauen (Saldo)", "stimmung", "BS-SCI-BAL", "Stimmung", False),
        ],
    },
    "onlinehandel": {
        "name": "Marktlage Online- & Einzelhandel",
        "beschreibung": ("Umsatz im Versand- und Internethandel, Verbraucherstimmung, Preise, Wechselkurse für den "
                         "Import, Transportkosten und Insolvenzen im Handel – aus amtlichen Quellen, monatlich aktuell, "
                         "ohne eigenes Konto."),
        # Kundenbranchen/Erzeugerpreise hängen vom Sortiment ab – bewusst kein Vorschlag
        "profil": {
            "preisindex": {"key": "preise_verbraucher", "region": "Deutschland",
                           "label": "Verbraucherpreise insgesamt (für Einzelhandel/Shop)"},
            "branche": {"code": "G4791", "label": "Versand- und Internet-Einzelhandel"},
        },
        "reihen": [
            ("Versand- & Internethandel (nominal)", "umsatz_handel_ka", "G4791", "Nachfrage (Index 2021 = 100, kalenderbereinigt)", True),
            ("Versand- & Internethandel (real)", "umsatz_handel_real_ka", "G4791", "Nachfrage (Index 2021 = 100, kalenderbereinigt)", True),
            ("Einzelhandel ohne Lebensmittel (real)", "umsatz_handel_real_ka", "G47_NFOOD_X_G473", "Nachfrage (Index 2021 = 100, kalenderbereinigt)", True),
            ("Verbraucher-Vertrauen (Saldo)", "stimmung", "BS-CSMCI-BAL", "Stimmung", False),
            ("Einzelhandel-Vertrauen (Saldo)", "stimmung", "BS-RCI-BAL", "Stimmung", False),
            ("Verbraucherpreise insgesamt", "preise_verbraucher", "Deutschland", "Preise", True),
            ("US-Dollar je Euro", "wechselkurse", "USD", "Wechselkurse (Einkauf im Ausland)", True),
            ("Chinesische Yuan je Euro", "wechselkurse", "CNY", "Wechselkurse (Einkauf im Ausland)", True),
            ("Diesel (€/l)", "kraftstoff", "Diesel", "Transportkosten", True),
            ("Insolvenzen Versand- & Internethandel", "insolvenzen", "WZ08-4791", "Insolvenzen im Handel", True),
            ("Insolvenzen Einzelhandel gesamt", "insolvenzen", "WZ08-47", "Insolvenzen im Handel", True),
            ("Temperatur Deutschland (°C)", "temperatur", "Deutschland", "Wetter", False),
        ],
    },
    "gastro_bedarf": {
        "name": "Marktlage Gastronomie-Bedarf",
        "beschreibung": ("Einkaufspreise für Einweg- und Lebensmittelverpackungen und Grundzutaten, Verkaufspreise im "
                         "Lebensmittel-Großhandel, Nachfrage im Gastgewerbe, Transportkosten und Insolvenzen bei "
                         "Restaurants, Imbissen und Caterern – aus amtlichen Quellen, monatlich aktuell, ohne eigenes Konto."),
        "profil": {
            "preisindex": {"key": "preise_grosshandel", "region": "WZ08-463",
                           "label": "Großhandel: Großh.m. Nahrungs-,Genussm.,Getränken u.Tabakwaren"},
            "branche": {"code": "G463", "label": "Großhandel mit Nahrungs- und Genussmitteln, Getränken und Tabakwaren"},
            "kundenbranchen": [{"code": "WZ08-561", "label": "Restaurants, Gaststätten, Imbissstuben, Cafes u.Ä."},
                               {"code": "WZ08-562", "label": "Caterer und sonstige Verpflegungsdienstleistungen"},
                               {"code": "WZ08-563", "label": "Ausschank von Getränken"},
                               {"code": "WZ08-55", "label": "Beherbergung"}],
            "erzeugerpreise": [{"code": "GP19-172114", "label": "Faltschachteln, -kartons, aus Papier oder Pappe"},
                               {"code": "GP19-2222", "label": "Verpackungsmittel aus Kunststoffen"},
                               {"code": "GP19-244225", "label": "Folien, dünne Bänder, aus Aluminium"},
                               {"code": "GP19-106121", "label": "Mehl von Weizen oder Mengkorn"}],
        },
        "reihen": [
            ("Faltschachteln & Kartons (z. B. Pizzakartons)", "erzeugerpreise", "GP19-172114", "Einkaufspreise Verpackung", True),
            ("Papiertüten & -beutel", "erzeugerpreise", "GP19-172112", "Einkaufspreise Verpackung", True),
            ("Kunststoffverpackungen", "erzeugerpreise", "GP19-2222", "Einkaufspreise Verpackung", True),
            ("Alufolie & dünne Aluminiumbänder", "erzeugerpreise", "GP19-244225", "Einkaufspreise Verpackung", True),
            ("Kunststoffgeschirr & Hygieneartikel", "erzeugerpreise", "GP19-222923", "Einkaufspreise Verpackung", True),
            ("Weizenmehl", "erzeugerpreise", "GP19-106121", "Einkaufspreise Lebensmittel", True),
            ("Käse & Quark", "erzeugerpreise", "GP19-10514", "Einkaufspreise Lebensmittel", True),
            ("Speiseöle & -fette", "erzeugerpreise", "GP19-1041", "Einkaufspreise Lebensmittel", True),
            ("Großhandel Nahrungs- & Genussmittel", "preise_grosshandel", "WZ08-463", "Verkaufspreise", True),
            ("Großhandel Papier & Pappe", "preise_grosshandel", "WZ08-46494", "Verkaufspreise", True),
            ("Verbraucherpreise insgesamt", "preise_verbraucher", "Deutschland", "Verkaufspreise", True),
            ("Umsatz Gastgewerbe (nominal)", "umsatz_gastgewerbe", "Deutschland", "Nachfrage", True),
            ("Umsatz Großhandel Nahrungsmittel (real)", "umsatz_handel_real", "G463", "Nachfrage", True),
            ("Übernachtungen Deutschland", "uebernachtungen", "Deutschland", "Nachfrage", True),
            ("Diesel (€/l)", "kraftstoff", "Diesel", "Transportkosten", True),
            ("Insolvenzen Restaurants & Imbisse", "insolvenzen", "WZ08-561", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Caterer", "insolvenzen", "WZ08-562", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Beherbergung", "insolvenzen", "WZ08-55", "Insolvenzen der Kundenbranchen", True),
            ("Dienstleister-Vertrauen (Saldo)", "stimmung", "BS-SCI-BAL", "Stimmung", False),
            ("Verbraucher-Vertrauen (Saldo)", "stimmung", "BS-CSMCI-BAL", "Stimmung", False),
        ],
    },
    "medizin_bedarf": {
        "name": "Marktlage Medizin- & Praxisbedarf",
        "beschreibung": ("Einkaufspreise für Medizinprodukte, Verbrauchsmaterial, Desinfektion und Arzneimittel, "
                         "Verkaufspreise im medizinischen Großhandel, Nachfrage, Transportkosten und Insolvenzen bei "
                         "Praxen, Kliniken und Pflegeheimen – aus amtlichen Quellen, monatlich aktuell, ohne eigenes Konto."),
        "profil": {
            "preisindex": {"key": "preise_grosshandel", "region": "WZ08-46462",
                           "label": "Großhandel: Großh.m. med.,orthopäd.Art.,Dental- u.Laborbedarf"},
            "branche": {"code": "G464", "label": "Großhandel mit Gebrauchs- und Verbrauchsgütern"},
            "kundenbranchen": [{"code": "WZ08-862", "label": "Arzt- und Zahnarztpraxen"},
                               {"code": "WZ08-861", "label": "Krankenhäuser"},
                               {"code": "WZ08-871", "label": "Pflegeheime"},
                               {"code": "WZ08-75", "label": "Veterinärwesen"}],
            "erzeugerpreise": [{"code": "GP19-325", "label": "Medizinische und zahnmed. Apparate und Materialien"},
                               {"code": "GP19-325013", "label": "Spritzen, Nadeln, Katheter, Geräte für med. Zwecke"},
                               {"code": "GP19-202014", "label": "Desinfektionsmittel"},
                               {"code": "GP19-329911", "label": "Sicherheitshandschuhe, Sicherheitskopfbedeckungen"}],
        },
        "reihen": [
            ("Medizinische & zahnmed. Apparate und Materialien", "erzeugerpreise", "GP19-325", "Einkaufspreise der Hersteller", True),
            ("Spritzen, Kanülen, Katheter", "erzeugerpreise", "GP19-325013", "Einkaufspreise der Hersteller", True),
            ("Andere Waren für medizinische Zwecke", "erzeugerpreise", "GP19-325050", "Einkaufspreise der Hersteller", True),
            ("Arzneimittel (pharmazeutische Spezialitäten)", "erzeugerpreise", "GP19-2120", "Einkaufspreise der Hersteller", True),
            ("Desinfektionsmittel", "erzeugerpreise", "GP19-202014", "Einkaufspreise der Hersteller", True),
            ("Schutzhandschuhe & -kopfbedeckungen", "erzeugerpreise", "GP19-329911", "Einkaufspreise der Hersteller", True),
            ("Hygienepapier (Toilettenpapier, Handtücher)", "erzeugerpreise", "GP19-172211", "Einkaufspreise der Hersteller", True),
            ("Großhandel Medizin-, Dental- & Laborbedarf", "preise_grosshandel", "WZ08-46462", "Verkaufspreise", True),
            ("Großhandel Arzneimittel", "preise_grosshandel", "WZ08-46461", "Verkaufspreise", True),
            ("Verbraucherpreise insgesamt", "preise_verbraucher", "Deutschland", "Verkaufspreise", True),
            ("Umsatz Großhandel Gebrauchs- & Verbrauchsgüter (real)", "umsatz_handel_real", "G464", "Nachfrage", True),
            ("Diesel (€/l)", "kraftstoff", "Diesel", "Transportkosten", True),
            ("Insolvenzen Arzt- & Zahnarztpraxen", "insolvenzen", "WZ08-862", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Krankenhäuser", "insolvenzen", "WZ08-861", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Pflegeheime", "insolvenzen", "WZ08-871", "Insolvenzen der Kundenbranchen", True),
            ("Insolvenzen Veterinärwesen", "insolvenzen", "WZ08-75", "Insolvenzen der Kundenbranchen", True),
            ("Dienstleister-Vertrauen (Saldo)", "stimmung", "BS-SCI-BAL", "Stimmung", False),
            ("Wirtschaftsklima (ESI, Ø = 100)", "stimmung", "BS-ESI-I", "Stimmung", False),
        ],
    },
    "verpackung_grosshandel": {
        "name": "Marktlage Verpackung & Großhandel",
        "beschreibung": ("Rohstoff- und Einkaufspreise für Papier-, Kunststoff- und Aluminiumverpackungen, Verkaufspreise "
                         "im Großhandel, Nachfrage in Groß- und Einzelhandel, Wechselkurse, Transportkosten und Insolvenzen "
                         "in Handel und Herstellung – aus amtlichen Quellen, monatlich aktuell, ohne eigenes Konto."),
        "profil": {
            "preisindex": {"key": "preise_grosshandel", "region": "WZ08-464",
                           "label": "Großhandel: Großh.m. Gebrauchs- und Verbrauchsgütern"},
            "branche": {"code": "G464", "label": "Großhandel mit Gebrauchs- und Verbrauchsgütern"},
            "kundenbranchen": [{"code": "WZ08-47", "label": "Einzelhandel (ohne Handel mit Kraftfahrzeugen)"},
                               {"code": "WZ08-10", "label": "Herstellung von Nahrungs- und Futtermitteln"},
                               {"code": "WZ08-56", "label": "Gastronomie"}],
            "erzeugerpreise": [{"code": "GP19-1721", "label": "Wellpapier und -pappe, Verpackungsmittel"},
                               {"code": "GP19-2222", "label": "Verpackungsmittel aus Kunststoffen"},
                               {"code": "GP19-2016", "label": "Kunststoffe, in Primärformen"},
                               {"code": "GP19-1711", "label": "Holz- und Zellstoff"}],
        },
        "reihen": [
            ("Holz- & Zellstoff", "erzeugerpreise", "GP19-1711", "Rohstoffe", True),
            ("Wellpappenrohpapier", "erzeugerpreise", "GP19-17123", "Rohstoffe", True),
            ("Altpapier (Sekundärrohstoff)", "erzeugerpreise", "GP19-383232", "Rohstoffe", True),
            ("Kunststoffe in Primärformen", "erzeugerpreise", "GP19-2016", "Rohstoffe", True),
            ("Wellpappe-Verpackungen", "erzeugerpreise", "GP19-1721", "Einkaufspreise Verpackung", True),
            ("Kartons aus Wellpappe", "erzeugerpreise", "GP19-172113", "Einkaufspreise Verpackung", True),
            ("Kunststoffverpackungen", "erzeugerpreise", "GP19-2222", "Einkaufspreise Verpackung", True),
            ("Kunststofffolien & -platten", "erzeugerpreise", "GP19-22213", "Einkaufspreise Verpackung", True),
            ("Alufolie & dünne Aluminiumbänder", "erzeugerpreise", "GP19-244225", "Einkaufspreise Verpackung", True),
            ("Großhandel Gebrauchs- & Verbrauchsgüter", "preise_grosshandel", "WZ08-464", "Verkaufspreise", True),
            ("Großhandel Papier & Pappe", "preise_grosshandel", "WZ08-46494", "Verkaufspreise", True),
            ("Großhandel sonstige Halbwaren", "preise_grosshandel", "WZ08-4676", "Verkaufspreise", True),
            ("Umsatz Großhandel insgesamt (real)", "umsatz_handel_real", "G46", "Nachfrage", True),
            ("Umsatz Großhandel Gebrauchs- & Verbrauchsgüter (real)", "umsatz_handel_real", "G464", "Nachfrage", True),
            ("Umsatz Einzelhandel (real)", "umsatz_handel_real", "G47_X_G473", "Nachfrage", True),
            ("US-Dollar je Euro", "wechselkurse", "USD", "Wechselkurse & Transport", True),
            ("Chinesische Yuan je Euro", "wechselkurse", "CNY", "Wechselkurse & Transport", True),
            ("Diesel (€/l)", "kraftstoff", "Diesel", "Wechselkurse & Transport", True),
            ("Insolvenzen Großhandel", "insolvenzen", "WZ08-46", "Insolvenzen", True),
            ("Insolvenzen Einzelhandel", "insolvenzen", "WZ08-47", "Insolvenzen", True),
            ("Insolvenzen Papier- & Pappeherstellung", "insolvenzen", "WZ08-17", "Insolvenzen", True),
            ("Insolvenzen Kunststoffwaren", "insolvenzen", "WZ08-22", "Insolvenzen", True),
            ("Industrie-Vertrauen (Saldo)", "stimmung", "BS-ICI-BAL", "Stimmung", False),
            ("Wirtschaftsklima (ESI, Ø = 100)", "stimmung", "BS-ESI-I", "Stimmung", False),
        ],
    },
}


# Größe → Widget-Typ in den Cockpits, der dieselbe Größe neben den eigenen Zahlen zeigt (Sprung „Im Cockpit“)
ZIEL_WIDGET = {
    "erzeugerpreise": "erzeugerpreise", "wechselkurse": "waehrungen", "kraftstoff": "energie",
    "insolvenzen": "insolvenzen", "stimmung": "stimmung", "temperatur": "umfeld",
    "umsatz_handel": "branchenvergleich", "umsatz_handel_real": "branchenvergleich",
    "umsatz_handel_ka": "branchenvergleich", "umsatz_handel_real_ka": "branchenvergleich",
    "umsatz_gastgewerbe": "umfeld", "uebernachtungen": "umfeld", "preise_grosshandel": "branchenvergleich", "preise_verbraucher": "branchenvergleich",
}


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _ident(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def sql_lage(reihen) -> str:
    werte = ",\n    ".join(f"({_q(g)}, {_q(r)}, {_q(t)}, {_q(th)}, {i}, {1 if pct else 0}, {_q(ZIEL_WIDGET.get(g, ''))})"
                           for i, (t, g, r, th, pct) in enumerate(reihen, 1))
    return f"""WITH k(g, r, Reihe, Thema, Sort, Pct, Ziel) AS (VALUES
    {werte}
), s AS (
    SELECT Groesse, Region, MAX(Periode) AS p FROM reihen WHERE Wert IS NOT NULL GROUP BY Groesse, Region
)
SELECT k.Thema, k.Reihe, a.Einheit,
    substr(a.Periode, 6, 2) || '/' || substr(a.Periode, 1, 4) AS Stand,
    ROUND(a.Wert, 2) AS Aktuell,
    ROUND(v.Wert, 2) AS Vorjahr,
    ROUND(a.Wert - v.Wert, 2) AS "Veränderung",
    CASE WHEN k.Pct = 1 AND v.Wert <> 0 THEN ROUND(100.0 * (a.Wert - v.Wert) / v.Wert, 1) END AS "Veränderung %",
    a.Quelle,
    k.Ziel
FROM k
JOIN s ON s.Groesse = k.g AND s.Region = k.r
JOIN reihen a ON a.Groesse = s.Groesse AND a.Region = s.Region AND a.Periode = s.p
LEFT JOIN reihen v ON v.Groesse = a.Groesse AND v.Region = a.Region
    AND v.Periode = (CAST(substr(a.Periode, 1, 4) AS INTEGER) - 1) || substr(a.Periode, 5)
ORDER BY k.Sort"""


def sql_verlauf(reihen) -> str:
    spalten = ",\n    ".join(f"MAX(CASE WHEN Groesse = {_q(g)} AND Region = {_q(r)} THEN Wert END) AS {_ident(t)}"
                             for t, g, r, _th, _p in reihen)
    return f"""SELECT Periode,
    {spalten}
FROM reihen
GROUP BY Periode
ORDER BY Periode"""


def _mapping(mid, name, sql, spalten):
    return {
        "id": mid, "name": name,
        "canvas_nodes": [{"id": "n_reihen", "dataset_id": "ds_reihen", "dataset_name": "reihen", "x": 40, "y": 40, "filters": {}}],
        "joins": [], "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
        "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
        "sql_nodes": [{"id": "sql1", "x": 380, "y": 40, "width": 350, "height": 244, "mode": "transform",
                       "output_field": "sql_1", "output_fields": spalten, "sql": sql}],
        "targets": [{"id": "t1", "name": name, "target_type": "xlsx", "target_connection_id": None,
                     "target_table": "", "target_write_mode": "replace", "target_options": {},
                     "fields": [{"source_dataset_id": "__sql__sql1", "source_field": c, "target_field": c,
                                 "transformer": {"type": "direct", "source_field": c}} for c in spalten]}],
    }


def paket(pid: str, p: dict) -> dict:
    reihen = p["reihen"]
    auswahl = {}
    for _t, g, r, _th, _p in reihen:
        auswahl.setdefault(g, [])
        if r not in auswahl[g]:
            auswahl[g].append(r)
    lage_spalten = ["Thema", "Reihe", "Einheit", "Stand", "Aktuell", "Vorjahr", "Veränderung", "Veränderung %", "Quelle", "Ziel"]
    verlauf_spalten = ["Periode"] + [t for t, *_ in reihen]
    themen = list(dict.fromkeys(th for *_, th, _p in reihen))

    widgets = [{"id": "w_lage", "type": "table", "label": "Lage auf einen Blick: letzter Wert gegen denselben Monat im Vorjahr",
                "action_id": "act_lage", "config": {"width": 12, "full_rows": True, "hidden_columns": ["Quelle", "Ziel"],
                                                   "sprung": {"spalte": "Ziel", "titel": "Mit eigenen Zahlen im Cockpit"}}}]
    for i, th in enumerate(themen, 1):
        widgets.append({"id": f"w_verlauf_{i}", "type": "line", "label": th, "action_id": "act_verlauf",
                        "config": {"width": 6, "x_column": "Periode",
                                   "y_columns": [t for t, *_x, th2, _p in reihen if th2 == th], "curved": True,
                                   "full_rows": True,      # sonst kappt die Vorschau nach 50 Monaten
                                   "luecken": True,       # Reihen enden in verschiedenen Monaten
                                   "markt": False}})      # sind selbst Marktreihen – kein Schalter „Markt“
    if p.get("profil"):
        widgets.append({"id": "w_profil", "type": "branchenprofil", "label": "Mit Ihren Cockpits verknüpfen",
                        "config": {"width": 12, "profil": p["profil"]}})
    quellen = "Destatis (Datenlizenz Deutschland – Namensnennung 2.0), Eurostat (Wiederverwendung mit Quellenangabe), " \
              "EZB, EU-Kommission (Weekly Oil Bulletin, CC BY 4.0), DWD (CC BY 4.0)"
    return {
        "format_version": "1.0",
        "template_id": f"markt_{pid}",
        "template_name": p["name"],
        "description": p["beschreibung"],
        "category": "marktdaten",
        "version": VERSION,
        "author": "Datenmonster",
        "hinweise": [
            "Voraussetzung: Datenmonster ab Stand 20.11.2026 (Quelle „Umfelddaten“) und eine aktive Lizenz – "
            "es wird keine Datenbankverbindung gebraucht.",
            "Beim allerersten Öffnen holt der Datendienst manche Reihen erst von der Quelle; dann nach einer Minute erneut laden.",
            "Die Reihen lassen sich im Dataset „" + p["name"] + " – Reihen“ erweitern (Werkstatt › Datasets) oder als "
            "Mapping-Quelle mit eigenen Zahlen verknüpfen.",
            f"Quellen: {quellen}. Die Quellenangabe gehört bei Weitergabe der Zahlen dazu.",
        ],
        "config_required": [],
        "datasets": [{
            "id": "ds_reihen", "name": f"{p['name']} – Reihen", "file_type": "umfeld",
            "columns": ["Groesse", "Bezeichnung", "Region", "Regionname", "Periode", "Datum", "Jahr", "Monat",
                        "Wert", "Einheit", "Quelle", "Stand"],
            "query_config": {"auswahl": [{"groesse": g, "regionen": r} for g, r in auswahl.items()],
                             "monate": 72, "format": "lang"},
        }],
        "mappings": [
            _mapping("m_lage", f"{p['name']} – Lage", sql_lage(reihen), lage_spalten),
            _mapping("m_verlauf", f"{p['name']} – Verlauf", sql_verlauf(reihen), verlauf_spalten),
        ],
        "pipelines": [],
        "forms": [{
            "name": p["name"],
            "portal_config": {"icon": "🌍"},
            "schema": {
                "fields": [], "layout": [], "result_tabs": [], "show_ai_assistant": False,
                "rubrik": {"id": "markt"},
                "actions": [
                    {"id": "act_lage", "type": "run_mapping", "mapping_id": "m_lage", "pipeline_id": None, "label": "Lage"},
                    {"id": "act_verlauf", "type": "run_mapping", "mapping_id": "m_verlauf", "pipeline_id": None, "label": "Verlauf"},
                ],
                "widgets": widgets,
                "doku": {
                    "intro": p["beschreibung"] + " Die Tabelle zeigt je Reihe den jüngsten verfügbaren Monat gegen denselben "
                             "Monat im Vorjahr, darunter der Verlauf der letzten sechs Jahre je Thema.",
                    "hinweise": [
                        "Amtliche Zahlen erscheinen mit Verzug: Preise und Umsätze meist nach 4–8 Wochen, Insolvenzen nach "
                        "etwa 3 Monaten. „Stand“ nennt den Monat des jeweils letzten Werts.",
                        "Preisindizes und Umsatzindizes: 2021 = 100. Stimmung: Wirtschaftsklima mit langjährigem Durchschnitt "
                        "= 100, Vertrauensindikatoren als Saldo (positiv = mehr Optimisten) – dort keine Prozentveränderung.",
                        "Insolvenzen: beantragte Verfahren je Monat; einzelne Monate schwanken stark, der Verlauf ist aussagekräftiger.",
                        f"Quellen: {quellen}.",
                    ],
                },
            },
        }],
        "alert_rules": [], "reports": [], "knowledge": [],
    }


if __name__ == "__main__":
    for pid, p in PAKETE.items():
        pfad = os.path.join(ZIEL, f"markt_{pid}.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(paket(pid, p), f, ensure_ascii=False, indent=2)
        print("geschrieben:", pfad)

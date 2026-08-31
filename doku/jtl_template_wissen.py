# -*- coding: utf-8 -*-
"""Bestückt die JTL-Templates mit dem KI-Wissen, das zu ihren Auswertungen gehört.

Warum: Ohne die passenden Regeln greift der KI-Assistent im Mapping-Editor zur
falschen Tabelle — "gekauft" landet bei Verkauf.tAuftrag statt Rechnung.vRechnung.
Das Wissen gehört deshalb ins Template-Bündel, nicht daneben.

Ablauf:
    python3 doku/jtl_template_wissen.py            # templates/*.json schreiben
    python3 doku/jtl_template_wissen.py --pruefen  # nur zeigen, nichts schreiben

Die Regeltexte kommen aus doku/jtl_wissen.json (Export der Wissensdatenbank).
Nach einer Änderung dort dieses Skript erneut laufen lassen und die Templates
mit doku/jtl_template_reseed.py in die laufende Datenbank spielen.
"""
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
WISSEN_DATEI = WURZEL / "doku" / "jtl_wissen.json"
TEMPLATE_ORDNER = WURZEL / "templates"

# ── Basis: gilt in jeder JTL-Auswertung ──────────────────────────────────────
# Diese Regeln beantworten die Fragen, die sich in JEDEM Cockpit stellen:
# Woher kommt der Umsatz, wie heißt der Kunde, welche Datensätze gehören raus.
BASIS = [
    'JTL – Umsatzbasis & Netto',
    'JTL – "gekauft" heißt Rechnung, nicht Auftrag',
    'JTL – vRechnung.cFirma = eigene Firma',
    'JTL – Kundennummer, Nachname, Vorname',
    'JTL – Kundenname: cFirma allein reicht nicht',
    'JTL – Gesperrte Kunden / inaktive Artikel',
    'JTL – zentrale Joins',
    'JTL – Artikelbezeichnung',
    'T-SQL – Kein Aggregat über Unterabfrage oder Fensterfunktion',
]

# Regeln für Auswertungen, die als Dashboard mit Drilldown gebaut sind.
DASHBOARD = [
    'Dashboard – Drilldown verdrahten (Schlüsselspalte, Fallen)',
    'Mapping – row_cap hebt hartkodierte TOP-Werte an',
    'Mapping – Ziel ohne Feldliste erzeugt leere Zeilen',
]

# ── Fachwissen je Template ───────────────────────────────────────────────────
ZUORDNUNG = {
    "jtl_gf_cockpit": BASIS + DASHBOARD + [
        'JTL – EK/VK & Deckungsbeitrag',
        'JTL – Lagerbestand & Kapitalbindung',
        'JTL – Bundesland aus PLZ',
        'JTL – Plattform & Warengruppe',
        'KI-Handlungsempfehlung: Kandidaten aus dem SQL vorgeben',
    ],

    "jtl_vertrieb_cockpit": BASIS + DASHBOARD + [
        'JTL – Aufträge und Angebote (Verkauf.tAuftrag)',
        'JTL – Auftragswerte aus Verkauf.tAuftragEckdaten',
        'JTL – Keine Verknüpfung Angebot → Auftrag',
        'JTL – Kundenname bei Aufträgen',
        'JTL – Offene Aufträge: welche Statusfelder wirklich zählen',
        'JTL – tAuftragEckdaten: fOffenerWert ist ZAHLUNG, nicht Lieferung',
        'JTL – nLieferstatus: die echten Werte',
        'JTL – Bundesland aus PLZ herleiten (Vertriebsregionen)',
        'Vertrieb – Marktdurchdringung je Bundesland',
    ],

    "jtl_einkauf_cockpit": BASIS + DASHBOARD + [
        'JTL – Einkauf: Bestellungen & Bestellwert',
        'JTL – Offene Bestellungen: nStatus ist unbrauchbar',
        'JTL – Wareneingang & Termintreue (tWarenLagerEingang)',
        'JTL – Eingangsrechnungen & Verbindlichkeiten',
        'JTL – EK/VK & Deckungsbeitrag',
    ],

    "jtl_versand_cockpit": BASIS + DASHBOARD + [
        'JTL – Versanddienstleister steht in der Versandart',
        'JTL – Versandkette Auftrag → Lieferschein → Sendung',
        'JTL – Aufträge und Angebote (Verkauf.tAuftrag)',
    ],

    "jtl_lager_cockpit": BASIS + DASHBOARD + [
        'JTL – Lagerbestand kommt aus tlagerbestand, nicht aus tArtikel',
        'JTL – Lagerbestand & Kapitalbindung',
        'JTL – Bestandshistorie liegt in dbo.vArtikelHistorie',
        'JTL – Bestand zu einem Stichtag rekonstruieren',
        'JTL – Lagerbewertung zum historischen Einkaufspreis',
        'JTL – Buchungsarten der Bestandshistorie',
        'JTL – Bestand je Warenlager',
        'JTL – Dispositionsdaten in dbo.tlagerbestand',
        'JTL – Stolperfelder im Artikelstamm (Lager)',
        'JTL – EK-Preisverlauf eines Artikels gegen den VK',
        'JTL – Vater/Kind-Artikel via Stückliste',
        'JTL – EK/VK & Deckungsbeitrag',
    ],

    "jtl_health_check": BASIS + DASHBOARD + [
        'JTL – Prüfbasis für Stammdaten-Checks',
        'JTL – cHAN ist oft die eigene Artikelnummer, keine Herstellernummer',
        'JTL – Artikelbeschreibungen und ihre Felder',
        'JTL – Lagerbestand kommt aus tlagerbestand, nicht aus tArtikel',
        'JTL – Pflichtfelder der Intrastat-Meldung im Artikelstamm',
        'JTL – Vater/Kind-Artikel via Stückliste',
        'JTL – Wo der Verkaufspreis steht (vier Ebenen)',
    ],

    "jtl_intrastat": BASIS + [
        'JTL – Pflichtfelder der Intrastat-Meldung im Artikelstamm',
        'Mapping – Ziel ohne Feldliste erzeugt leere Zeilen',
    ],

    "jtl_monitor": BASIS + DASHBOARD + [
        'KI-Handlungsempfehlung: Kandidaten aus dem SQL vorgeben',
        'JTL – Offene Aufträge: welche Statusfelder wirklich zählen',
        'JTL – Offene Bestellungen: nStatus ist unbrauchbar',
        'JTL – Lagerbestand kommt aus tlagerbestand, nicht aus tArtikel',
        'JTL – EK/VK & Deckungsbeitrag',
    ],
}


def version_hoch(v: str) -> str:
    """1.3 → 1.4, 2.13 → 2.14. Unlesbare Versionen bleiben, wie sie sind."""
    teile = str(v or "1.0").split(".")
    if len(teile) == 2 and teile[1].isdigit():
        return f"{teile[0]}.{int(teile[1]) + 1}"
    return v


def main() -> int:
    nur_pruefen = "--pruefen" in sys.argv

    wissen = {w["title"]: w for w in json.loads(WISSEN_DATEI.read_text(encoding="utf-8"))}
    fehlend = {t for titel in ZUORDNUNG.values() for t in titel if t not in wissen}
    if fehlend:
        print("FEHLER – diese Regeln stehen in der Zuordnung, aber nicht in "
              f"{WISSEN_DATEI.name}:", file=sys.stderr)
        for t in sorted(fehlend):
            print(f"  - {t}", file=sys.stderr)
        return 1

    for template_id, titel in ZUORDNUNG.items():
        datei = TEMPLATE_ORDNER / f"{template_id}.json"
        if not datei.exists():
            print(f"  ⚠ {template_id}: keine Datei {datei.name} – übersprungen")
            continue

        roh = datei.read_text(encoding="utf-8")
        tpl = json.loads(roh)
        # Vorhandene Einrückung übernehmen, sonst formatiert das Skript die
        # ganze Datei um und der Diff verdeckt die eigentliche Änderung.
        zweite = roh.split("\n")[1] if "\n" in roh else ""
        einzug = len(zweite) - len(zweite.lstrip(" ")) or 2
        # Reihenfolge stabil halten und Doppelnennungen (BASIS + Fachliste) entfernen
        eindeutig = list(dict.fromkeys(titel))
        neu = [{
            "category": wissen[t]["category"],
            "title": t,
            "content": wissen[t]["content"],
            "always_include": wissen[t]["always_include"],
            "scope": "global",
        } for t in eindeutig]

        alt = tpl.get("knowledge") or []
        if alt == neu:
            print(f"  = {template_id:24} v{tpl.get('version')}  unverändert ({len(neu)} Regeln)")
            continue

        tpl["knowledge"] = neu
        alte_version = tpl.get("version")
        tpl["version"] = version_hoch(alte_version)
        zeichen = sum(len(w["content"]) for w in neu)
        print(f"  ✓ {template_id:24} v{alte_version} → v{tpl['version']}  "
              f"{len(neu)} Regeln ({zeichen // 1000} kB Text)")

        if not nur_pruefen:
            datei.write_text(json.dumps(tpl, ensure_ascii=False, indent=einzug) + "\n",
                             encoding="utf-8")

    if nur_pruefen:
        print("\n(--pruefen: nichts geschrieben)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

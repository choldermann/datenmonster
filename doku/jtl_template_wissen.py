# -*- coding: utf-8 -*-
"""Bestückt die JTL-Templates mit dem KI-Wissen, das zu ihren Auswertungen gehört.

Warum: Ohne die passenden Regeln greift der KI-Assistent im Mapping-Editor zur
falschen Tabelle — "gekauft" landet bei Verkauf.tAuftrag statt Rechnung.vRechnung.
Das Wissen gehört deshalb ins Template-Bündel, nicht daneben.

Zuschnitt (Produktentscheidung): Die Cockpits bekommen nur die Grundregeln — das,
was ihre eigene KI-Analyse und die Drilldowns zum Funktionieren brauchen. Das
vollständige Wissen ist ein eigenes, im monstersuite-Shop kaufbares Modul
(templates/jtl_wissen_paket.json), das dieses Skript ebenfalls erzeugt.

Ablauf:
    python3 doku/jtl_template_wissen.py                # templates/*.json schreiben
    python3 doku/jtl_template_wissen.py --pruefen      # nur zeigen, nichts schreiben
    python3 doku/jtl_template_wissen.py --ohne-version # Inhalt korrigieren, Version lassen
                                                       # (für eine noch nicht ausgelieferte Fassung)

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

# ── Was die Cockpits mitbringen ──────────────────────────────────────────────
# Bewusst knapp: nur die Grundregeln, ohne die die KI-Analyse und die Drilldowns
# IM Cockpit falsche Aussagen produzieren. Alles Weitere ist das kaufbare Modul.
# Grundregeln erkennt das Skript an always_include in doku/jtl_wissen.json.
COCKPIT_ZUSATZ = {
    # Was ein Cockpit über die Grundregeln hinaus zwingend braucht, weil seine
    # eigenen Auswertungen sonst falsch erklärt werden.
    "jtl_lager_cockpit":   ['JTL – Lagerbestand kommt aus tlagerbestand, nicht aus tArtikel'],
    "jtl_vertrieb_cockpit": ['JTL – Aufträge und Angebote (Verkauf.tAuftrag)'],
    "jtl_einkauf_cockpit":  ['JTL – Offene Bestellungen: nStatus ist unbrauchbar'],
    "jtl_monitor":          ['KI-Handlungsempfehlung: Kandidaten aus dem SQL vorgeben'],
}

COCKPITS = [
    "jtl_gf_cockpit", "jtl_vertrieb_cockpit", "jtl_einkauf_cockpit",
    "jtl_versand_cockpit", "jtl_lager_cockpit", "jtl_health_check",
    "jtl_intrastat", "jtl_monitor",
]

# ── Das kaufbare Modul ───────────────────────────────────────────────────────
PAKET_ID = "jtl_wissen_paket"
PAKET = {
    "format_version": "1.0",
    "template_id": PAKET_ID,
    "template_name": "JTL-Wissen für die KI",
    "description": (
        "Macht den KI-Assistenten zum JTL-Kenner: die geprüften Regeln der "
        "JTL-Wawi-Datenbank — welche Tabelle den Umsatz führt, wo der Kundenname "
        "wirklich steht, welche Felder trügen. Damit schreibt die KI im "
        "Mapping-Editor auf Anhieb brauchbares SQL, statt sich Tabellen "
        "auszudenken. Ohne Datenbank-Verbindung nutzbar, wirkt sofort."
    ),
    "category": "jtl",
    "author": "Datenmonster",
    "datasets": [], "mappings": [], "pipelines": [], "forms": [], "reports": [],
    "config_required": [],
    "hinweise": [
        "Reines Wissensmodul: legt keine Datasets, Mappings oder Formulare an.",
        "Die Regeln landen in der KI-Wissensdatenbank und lassen sich dort "
        "unter Systemeinstellungen einzeln abschalten oder anpassen.",
        "Gilt für die JTL-Wawi ab Version 1.5; geprüft gegen echte Kundendatenbanken.",
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
    ohne_version = "--ohne-version" in sys.argv

    alle = json.loads(WISSEN_DATEI.read_text(encoding="utf-8"))
    wissen = {w["title"]: w for w in alle}
    grundregeln = [w["title"] for w in alle if w.get("always_include")]

    fehlend = {t for titel in COCKPIT_ZUSATZ.values() for t in titel if t not in wissen}
    if fehlend:
        print(f"FEHLER – nicht in {WISSEN_DATEI.name}:", file=sys.stderr)
        for t in sorted(fehlend):
            print(f"  - {t}", file=sys.stderr)
        return 1

    def als_eintrag(titel):
        return [{
            "category": wissen[t]["category"],
            "title": t,
            "content": wissen[t]["content"],
            "always_include": wissen[t]["always_include"],
            "scope": "global",
        } for t in dict.fromkeys(titel)]

    def schreiben(datei, tpl, einzug):
        if not nur_pruefen:
            datei.write_text(json.dumps(tpl, ensure_ascii=False, indent=einzug) + "\n",
                             encoding="utf-8")

    # ── Cockpits: Grundregeln + der eine fachliche Anker ──────────────────────
    for template_id in COCKPITS:
        datei = TEMPLATE_ORDNER / f"{template_id}.json"
        if not datei.exists():
            print(f"  ⚠ {template_id}: keine Datei – übersprungen")
            continue

        roh = datei.read_text(encoding="utf-8")
        tpl = json.loads(roh)
        # Vorhandene Einrückung übernehmen, sonst formatiert das Skript die
        # ganze Datei um und der Diff verdeckt die eigentliche Änderung.
        zweite = roh.split("\n")[1] if "\n" in roh else ""
        einzug = len(zweite) - len(zweite.lstrip(" ")) or 2

        neu = als_eintrag(grundregeln + COCKPIT_ZUSATZ.get(template_id, []))
        if (tpl.get("knowledge") or []) == neu:
            print(f"  = {template_id:24} v{tpl.get('version')}  unverändert ({len(neu)} Regeln)")
            continue

        tpl["knowledge"] = neu
        alte_version = tpl.get("version")
        if not ohne_version:
            tpl["version"] = version_hoch(alte_version)
        pfeil = f"v{alte_version}" if ohne_version else f"v{alte_version} → v{tpl['version']}"
        print(f"  ✓ {template_id:24} {pfeil}  {len(neu)} Regeln")
        schreiben(datei, tpl, einzug)

    # ── Das kaufbare Modul: alles, was die Wissensdatenbank hergibt ───────────
    datei = TEMPLATE_ORDNER / f"{PAKET_ID}.json"
    paket = dict(PAKET)
    paket["knowledge"] = als_eintrag([w["title"] for w in alle])
    # Version des Pakets folgt der Anzahl der Regeln: jede neue Regel ist eine
    # neue Fassung, und der Shop sieht am Sprung, dass es etwas zu laden gibt.
    paket["version"] = f"1.{len(alle)}"
    if datei.exists() and json.loads(datei.read_text(encoding="utf-8")) == paket:
        print(f"  = {PAKET_ID:24} v{paket['version']}  unverändert ({len(alle)} Regeln)")
    else:
        zeichen = sum(len(w["content"]) for w in paket["knowledge"])
        print(f"  ✓ {PAKET_ID:24} v{paket['version']}  "
              f"{len(alle)} Regeln ({zeichen // 1000} kB Text)")
        schreiben(datei, paket, 2)

    if nur_pruefen:
        print("\n(--pruefen: nichts geschrieben)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

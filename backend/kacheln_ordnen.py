"""Räumt die Kennzahlen-Kacheln der Unternehmensübersicht auf.

Zwei Mängel, beide beim Einbau der neuen Kacheln entstanden:

1. ANZAHLEN MIT EURO-ZEICHEN. Die Aufschlüsselung erbt Präfix und Nachkommastellen
   von der Kachel, wenn sie nichts eigenes mitbringt. „70 stornierte Rechnungen"
   stand deshalb als „€ 70,00" da, „27 Rechnungskorrekturen" als „€ 27,00" – und
   umgekehrt fehlte dem Erlös ohne Gegenkosten sein Euro-Zeichen. Das Widget kann
   das längst je Zeile (b.prefix / b.decimals), es wurde nur nicht genutzt.

2. ZERRISSENE GRUPPEN. Die Kachel „Versand ohne Kosten" schob sich mitten in die
   Ertragskennzahlen, wodurch „Umsatz nach Korrekturen" von „davon storniert" und
   „davon gutgeschrieben" in die nächste Zeile rutschte – ausgerechnet die vier
   Kacheln, die zusammen EINE Rechnung ergeben.

Zwölf Kacheln, drei Themen zu je vier. Deshalb Breite 3 statt 4: dann ist jede
Bildschirmzeile genau eine Gruppe, statt dass die Themen quer über Zeilenumbrüche
verlaufen.

Anwenden:
    docker cp backend/kacheln_ordnen.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/kacheln_ordnen.py --anwenden
    python3 backend/kacheln_ordnen.py --template templates/jtl_gf_cockpit.json --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"

# Reihenfolge = Lesereihenfolge. Je Zeile ein Thema.
GRUPPEN = [
    # Umsatz und was von ihm abgeht – die Brücke zur JTL-Statistik in einer Zeile
    ["w_kpi_umsatz", "w_kpi_storno", "w_kpi_korrektur", "w_kpi_umsatz_netto"],
    # Was daran verdient ist
    ["w_kpi_rohertrag", "w_kpi_db2", "w_kpi_marge", "w_kpi_db2marge"],
    # Belege, Kunden und die Datenlücke, die den Ertrag oben schönt
    ["w_kpi_rechnungen", "w_kpi_avg", "w_kpi_kunden", "w_kpi_versand_ohne_ek"],
]
BREITE = 3

# Aufschlüsselungszeilen, die KEINE Euro sind (oder es entgegen der Kachel sind).
ZEILEN_FORMAT = {
    ("w_kpi_storno", "Stornierte Rechnungen"): {"prefix": "", "decimals": 0},
    ("w_kpi_korrektur", "Rechnungskorrekturen"): {"prefix": "", "decimals": 0},
    ("w_kpi_versand_ohne_ek", "von Versandpositionen"): {"prefix": "", "decimals": 0},
    ("w_kpi_versand_ohne_ek", "Erlös ohne Gegenkosten"): {"prefix": "€ ", "decimals": 2},
}


def formate_setzen(widgets: list) -> int:
    n = 0
    for w in widgets:
        for zeile in ((w.get("config") or {}).get("breakdown") or []):
            fmt = ZEILEN_FORMAT.get((w.get("id"), zeile.get("label")))
            if not fmt or all(zeile.get(k) == v for k, v in fmt.items()):
                continue
            zeile.update(fmt)
            n += 1
    return n


def ordnen(widgets: list) -> int:
    """Sortiert die Kacheln in die Gruppen und setzt die Breite. Zahl der Änderungen."""
    reihenfolge = [wid for gruppe in GRUPPEN for wid in gruppe]
    nach_id = {w.get("id"): w for w in widgets}
    vorhanden = [wid for wid in reihenfolge if wid in nach_id]
    if not vorhanden:
        return 0
    # Die Kacheln stehen als Block beieinander; an die Stelle der ersten kommt der
    # sortierte Block zurück, alles andere bleibt, wo es ist.
    stellen = sorted(widgets.index(nach_id[wid]) for wid in vorhanden)
    alt = [widgets[i] for i in stellen]
    neu = [nach_id[wid] for wid in vorhanden]
    n = 0
    for w in neu:
        if (w.get("config") or {}).get("width") != BREITE:
            w.setdefault("config", {})["width"] = BREITE
            n += 1
    if alt != neu:
        n += 1
    for stelle, w in zip(stellen, neu):
        widgets[stelle] = w
    return n + formate_setzen(neu)


def _zeigen(widgets: list):
    reihe = [w for w in widgets if w.get("id") in
             {wid for g in GRUPPEN for wid in g}]
    for i in range(0, len(reihe), 4):
        print("   | " + " | ".join(f"{w.get('label')}" for w in reihe[i:i + 4]))


def main_db(anwenden: bool):
    c = sqlite3.connect(DB)
    sch = json.loads(c.execute("select schema from forms where id=1").fetchone()[0])
    n = ordnen(sch.get("widgets") or [])
    print(f"Formular 1: {n} Änderungen")
    _zeigen(sch["widgets"])
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    if n:
        c.execute("update forms set schema=? where id=1", (json.dumps(sch, ensure_ascii=False),))
        c.commit()
    print("geschrieben." if n else "nichts zu tun.")


def main_template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    n = ordnen(t["forms"][0]["schema"].get("widgets") or [])
    print(f"{pfad}: {n} Änderungen")
    _zeigen(t["forms"][0]["schema"]["widgets"])
    if not anwenden or not n:
        if n:
            print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    teile = str(t.get("version") or "1.0").split(".")
    t["version"] = f"{teile[0]}.{int(teile[1]) + 1}" if len(teile) > 1 and teile[1].isdigit() \
        else t.get("version")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print("geschrieben.")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        main_template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        main_db(anwenden)

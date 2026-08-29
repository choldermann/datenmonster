"""Führt Firmenname und Firmenzusatz zu einem Anzeigenamen zusammen.

Bei PPS trägt `cFirma` bei 21.474 von 22.493 Rechnungsadressen nur eine
Gattung – 5.342-mal steht dort schlicht „Zahnarztpraxis", 1.245-mal „Frau".
Der eigentliche Name steckt im Firmenzusatz. Jede Kundenliste zeigte damit
Dutzende Zeilen „Zahnarztpraxis" ohne Unterscheidungsmerkmal.

Die Spalte heißt je nach Quelle anders:
    dbo.tAdresse, Rechnung.vRechnungRechnungsadresse,
    Verkauf.vAuftragRechnungsadresse, RM.lvRetoure   -> cZusatz
    dbo.tLieferant                                   -> cFirmenZusatz

NICHT angefasst wird `RM.lvRetoure.cFirma`: das ist die EIGENE Firma
(„PPS Med. Versandhandel GmbH"), der Kunde steht dort in `cKundeFirma`.
Ebenso bleibt `R.cFirma` im GF-Cockpit unberührt – das ist eine CTE-Spalte,
die ihren Wert schon aus dem umgeschriebenen `RA.cFirma` bezieht.

Der Zusatz wird unterdrückt, wenn er bereits im Firmennamen steckt
(PPS: 175 Fälle, sonst stünde da „Zahnarztpraxis Uwe Göselt Uwe Göselt").
Ist cFirma leer und nur der Zusatz gefüllt, trägt der Zusatz allein (25 Fälle).
Sind beide leer, liefert der Ausdruck '' – das umschließende NULLIF greift
dann wie bisher auf Vor-/Nachname zurück.

Anwenden – BEIDE Orte, sonst kehrt der alte Stand bei der nächsten
Template-Installation zurück:

    python backend/firmenzusatz.py --templates --generatoren            # Trockenlauf
    python backend/firmenzusatz.py --templates --generatoren --anwenden

    docker cp backend/firmenzusatz.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/firmenzusatz.py --live
    docker exec datenmonster-backend python /tmp/firmenzusatz.py --live --anwenden
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys

DB = "/app/uploads/datenmonster.db"

# Alias -> (Firmenspalte, Zusatzspalte). Bewusst je Alias entschieden und an
# INFORMATION_SCHEMA beider Mandanten geprüft, nicht über \w+ geraten.
REGELN = {
    ("RA", "cFirma"): "cZusatz",        # Rechnungs-/Auftragsrechnungsadresse
    ("AD", "cFirma"): "cZusatz",        # dbo.tAdresse
    ("A", "cFirma"): "cZusatz",         # dbo.tAdresse (A ist sonst tArtikel – das hat kein cFirma)
    ("L", "cFirma"): "cFirmenZusatz",   # dbo.tLieferant
    ("R", "cKundeFirma"): "cZusatz",    # RM.lvRetoure
}

# RTRIM um die Firma, sonst erbt der zusammengesetzte Name ein doppeltes
# Leerzeichen aus Feldern wie 'UNIGLOVES® '. Ein äußeres RTRIM braucht es
# nicht mehr – der angehängte Zusatz ist bereits getrimmt.
VORLAGE = (
    "LTRIM(RTRIM(ISNULL({a}.{f},'')) + CASE WHEN ISNULL({a}.{z},'') = '' "
    "OR CHARINDEX(LTRIM(RTRIM({a}.{z})), ISNULL({a}.{f},'')) > 0 THEN '' "
    "ELSE ' ' + LTRIM(RTRIM({a}.{z})) END)"
)

# Steht die Spalte nackt in einer SELECT-Liste, verliert sie durch die
# Ersetzung ihren Namen ("No column name was specified") – dann muss ein
# Alias nachgezogen werden. In GROUP BY/ORDER BY wäre "AS" dagegen ein
# Syntaxfehler und innerhalb von ISNULL(NULLIF(...)) ist die Spalte gar kein
# Listenelement. Es zählt deshalb beides: das zuletzt vorangegangene
# Schlüsselwort muss SELECT sein UND die Klammerbilanz seither ausgeglichen.
KLAUSEL = re.compile(r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|"
                     r"PARTITION\s+BY|ON|SET|VALUES)\b", re.I)
FOLGT_NACKT = re.compile(r"^\s*(?:,|\bFROM\b)", re.I)


def _entkleiden(sql: str) -> str:
    """Ersetzt 'Literale' und --Kommentare durch Leerzeichen gleicher Länge.

    Sonst zählt ein Apostroph in einem Kommentar oder eine Klammer in
    '(unbekannt)' beim Bilanzieren mit.
    """
    aus, i, n = [], 0, len(sql)
    while i < n:
        if sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            aus.append(" " * (min(j, n - 1) - i + 1))
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            aus.append(" " * (j - i))
            i = j
        else:
            aus.append(sql[i])
            i += 1
    return "".join(aus)


def _nacktes_listenelement(vorher: str, nachher: str) -> bool:
    if not FOLGT_NACKT.match(nachher):
        return False
    rein = _entkleiden(vorher)
    treffer = list(KLAUSEL.finditer(rein))
    if not treffer or re.sub(r"\s+", " ", treffer[-1].group(1)).upper() != "SELECT":
        return False
    rest = rein[treffer[-1].end():]
    return rest.count("(") == rest.count(")")


def umschreiben(sql):
    """Liefert (neues_sql, anzahl_ersetzungen, anzahl_alias_nachgezogen)."""
    if not isinstance(sql, str) or "." not in sql:
        return sql, 0, 0
    # Bereits zusammengeführte Stellen aussparen – der erzeugte Ausdruck
    # enthält selbst wieder "RA.cFirma". Ohne diese Sperre verschachtelt ein
    # zweiter Lauf den Ausdruck in sich selbst (passiert leicht: Template neu
    # installieren, dann nochmal --live).
    fertig = [(m.start(), m.end())
              for (a, f), z in REGELN.items()
              for m in re.finditer(re.escape(VORLAGE.format(a=a, f=f, z=z)), sql)]

    ersetzt = aliasse = 0
    teile, pos = [], 0
    for m in MUSTER.finditer(sql):
        if any(anf <= m.start() < end for anf, end in fertig):
            continue
        alias, spalte = m.group(1), m.group(2)
        zusatz = REGELN.get((alias, spalte))
        if zusatz is None:          # z. B. R.cFirma = eigene Firma / CTE-Spalte
            continue
        neu = VORLAGE.format(a=alias, f=spalte, z=zusatz)
        if _nacktes_listenelement(sql[:m.start()], sql[m.end():]):
            neu += " AS " + spalte
            aliasse += 1
        teile.append(sql[pos:m.start()])
        teile.append(neu)
        pos = m.end()
        ersetzt += 1
    teile.append(sql[pos:])
    return "".join(teile), ersetzt, aliasse


MUSTER = re.compile(
    r"(?<![\w.])(" + "|".join(sorted({a for a, _ in REGELN}, key=len, reverse=True))
    + r")\.(cFirma|cKundeFirma)\b"
)


def durchlaufen(knoten):
    """Schreibt jeden SQL-String im Baum um. Zählt (Ausdrücke, Aliasse)."""
    if isinstance(knoten, str):
        neu, n, al = umschreiben(knoten)
        return neu, n, al
    if isinstance(knoten, list):
        n = al = 0
        for i, x in enumerate(knoten):
            knoten[i], a, b = durchlaufen(x)
            n += a; al += b
        return knoten, n, al
    if isinstance(knoten, dict):
        n = al = 0
        for k, x in knoten.items():
            knoten[k], a, b = durchlaufen(x)
            n += a; al += b
        return knoten, n, al
    return knoten, 0, 0


def templates(anwenden: bool) -> int:
    wurzel = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "templates")
    gesamt = 0
    for pfad in sorted(glob.glob(os.path.join(wurzel, "*.json"))):
        doc = json.load(open(pfad, encoding="utf-8"))
        doc, n, al = durchlaufen(doc)
        if not n:
            continue
        gesamt += n
        print(f"  {os.path.basename(pfad):28} {n:3} Ausdrücke"
              + (f", {al} Spaltenalias nachgezogen" if al else ""))
        if anwenden:
            # indent=2/ensure_ascii=False gibt die Dateien byte-genau wieder,
            # der Diff zeigt damit nur die echten Änderungen.
            with open(pfad, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
    return gesamt


def generatoren(anwenden: bool) -> int:
    """Die Drilldown-Bauskripte erzeugen die Detail-Mappings neu.

    Ohne sie kehrte der alte Ausdruck beim nächsten Lauf von
    *_drilldowns.py zurück – derselbe Doppelort wie Template/DB.
    """
    hier = os.path.dirname(os.path.abspath(__file__))
    gesamt = 0
    for pfad in sorted(glob.glob(os.path.join(hier, "*_drilldowns.py"))):
        roh = open(pfad, encoding="utf-8").read()
        neu_txt, n, al = umschreiben(roh)
        if not n:
            continue
        compile(neu_txt, pfad, "exec")   # bricht ab, wenn die Datei zerlegt wurde
        gesamt += n
        print(f"  {os.path.basename(pfad):28} {n:3} Ausdrücke"
              + (f", {al} Spaltenalias nachgezogen" if al else ""))
        if anwenden:
            open(pfad, "w", encoding="utf-8").write(neu_txt)
    return gesamt


def live(anwenden: bool) -> int:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    gesamt = 0
    for r in c.execute("SELECT id, project_id, name, sql_nodes FROM mappings").fetchall():
        if not r["sql_nodes"]:
            continue
        knoten, n, al = durchlaufen(json.loads(r["sql_nodes"]))
        if not n:
            continue
        gesamt += n
        print(f"  M{r['id']:<4} P{r['project_id']} {n:2}x  {(r['name'] or '')[:60]}"
              + (f"  (+{al} Alias)" if al else ""))
        if anwenden:
            c.execute("UPDATE mappings SET sql_nodes = ? WHERE id = ?",
                      (json.dumps(knoten, ensure_ascii=False), r["id"]))
    if anwenden:
        c.commit()
    c.close()
    return gesamt


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--templates", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--generatoren", action="store_true")
    p.add_argument("--anwenden", action="store_true")
    args = p.parse_args()
    if not (args.templates or args.live or args.generatoren):
        p.error("--templates, --generatoren und/oder --live angeben")
    n = 0
    if args.templates:
        print("== Templates ==")
        n += templates(args.anwenden)
    if args.generatoren:
        print("== Drilldown-Generatoren ==")
        n += generatoren(args.anwenden)
    if args.live:
        print("== Live-Mappings ==")
        n += live(args.anwenden)
    print(f"\n{n} Ausdrücke {'geändert' if args.anwenden else 'gefunden (Trockenlauf)'}")
    if not args.anwenden:
        print("Mit --anwenden schreiben.")

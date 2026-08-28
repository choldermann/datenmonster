"""Stornierte Rechnungen aus allen Auswertungen nehmen.

JTL markiert eine stornierte Rechnung mit Rechnung.vRechnung.nStorno = 1 und legt
zusätzlich eine Storno-Gutschrift an. Der Beleg bleibt aber vollständig in der
Datenbank stehen – wer ihn nicht ausfiltert, zählt ihn als Umsatz mit.

Zwei Formen kommen vor:
  A) FROM Rechnung.vRechnung WHERE …   (der Plattform-Vorfilter der Cockpits)
     → der Filter kommt als erste Bedingung in dieses WHERE
  B) FROM/JOIN Rechnung.vRechnung <alias>
     → die Tabelle wird durch eine gefilterte Unterabfrage ersetzt

ISNULL(nStorno,0) = 0 statt nStorno = 0: die Spalte ist in älteren JTL-Ständen
nullable, und NULL wäre sonst weder storniert noch nicht-storniert.
"""
import re, sys

FILTER = "ISNULL(nStorno,0) = 0"
KEYWORDS = {"WHERE","JOIN","LEFT","RIGHT","INNER","OUTER","CROSS","GROUP","ORDER",
            "UNION","ON","HAVING","AS","SELECT","FROM","WITH"}

def patch_sql(s: str):
    """Gibt (neues_sql, anzahl_aenderungen) zurück. Idempotent."""
    if not s or "Rechnung.vRechnung" not in s:
        return s, 0
    # Nur echte Tabellenbindungen anfassen. Der Name kommt auch in Fließtext vor
    # (Template-Beschreibungen, Schema-Hinweise für die KI) – dort ist er Prosa.
    if not re.search(r"(?i)\b(FROM|JOIN)\s+Rechnung\.vRechnung\b", s):
        return s, 0
    n = 0

    # ── A: FROM Rechnung.vRechnung WHERE …
    def a(m):
        nonlocal n
        rest = s[m.end():m.end() + 120]
        if FILTER in rest or re.match(r"(?i)\s*ISNULL\(nStorno", rest):
            return m.group(0)                      # schon gefiltert
        n += 1
        return f"{m.group(1)} Rechnung.vRechnung WHERE {FILTER} AND "
    s = re.sub(r"(?i)\b(FROM)\s+Rechnung\.vRechnung\s+WHERE\s+", a, s)

    # ── B: FROM/JOIN Rechnung.vRechnung <alias>
    def b(m):
        nonlocal n
        alias = m.group(2)
        if alias.upper() in KEYWORDS:
            raise SystemExit(f"UNERWARTET: kein Alias nach Rechnung.vRechnung → {m.group(0)!r}")
        n += 1
        return (f"{m.group(1)} (SELECT * FROM Rechnung.vRechnung "
                f"WHERE {FILTER}) {alias}")
    s = re.sub(r"(?i)\b(FROM|JOIN)\s+Rechnung\.vRechnung\s+(?!WHERE\b)([A-Za-z_][A-Za-z0-9_]*)",
               b, s)

    # Übrig gebliebene, nicht erfasste Vorkommen sichtbar machen: nach jedem
    # Vorkommen muss der Filter stehen – entweder als erste WHERE-Bedingung
    # (Form A) oder als WHERE der eingeschobenen Unterabfrage (Form B).
    for m in re.finditer(r"(?i)\b(?:FROM|JOIN)\s+Rechnung\.vRechnung\b", s):
        danach = s[m.end():m.end() + 40]
        if re.match(r"(?i)\s+WHERE\s+ISNULL\(nStorno,0\)\s*=\s*0", danach):
            continue
        raise SystemExit(f"UNBEHANDELT: …{s[max(0,m.start()-70):m.end()+40]}…")
    return s, n

def patch_obj(o):
    """Rekursiv durch beliebige JSON-Strukturen; patcht jeden String."""
    if isinstance(o, str):
        return patch_sql(o)
    if isinstance(o, dict):
        ges = 0; out = {}
        for k, v in o.items():
            out[k], c = patch_obj(v); ges += c
        return out, ges
    if isinstance(o, list):
        ges = 0; out = []
        for v in o:
            nv, c = patch_obj(v); out.append(nv); ges += c
        return out, ges
    return o, 0


# ── Anwendung ───────────────────────────────────────────────────────────────
# Einmalig je Installation, im Backend-Container:
#     docker cp doku/storno_filter_patch.py datenmonster-backend:/app/
#     docker exec -w /app datenmonster-backend python storno_filter_patch.py
#
# Ohne Argumente läuft er TROCKEN und zeigt nur, was er ändern würde.
# Mit  --anwenden  schreibt er – nach einer Sicherung nach /app/backups/.
if __name__ == "__main__":
    import sqlite3, json, datetime, os

    anwenden = "--anwenden" in sys.argv
    db_pfad = os.environ.get("DM_DB", "/app/uploads/datenmonster.db")
    c = sqlite3.connect(db_pfad)

    if anwenden:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        sicherung = {
            "mappings": {str(m): s for m, s in c.execute("select id,sql_nodes from mappings")},
            "templates": {t: (x if isinstance(x, str) else json.dumps(x))
                          for t, x in c.execute("select template_id,content from templates")},
        }
        ziel = f"/app/backups/vor_storno_patch_{stamp}.json"
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w") as f:
            json.dump(sicherung, f)
        print("Sicherung:", ziel)

    for tabelle, id_spalte, daten_spalte in (("mappings", "id", "sql_nodes"),
                                             ("templates", "template_id", "content")):
        anz = ges = 0
        for schluessel, roh in c.execute(
                f"select {id_spalte},{daten_spalte} from {tabelle}").fetchall():
            obj = json.loads(roh) if isinstance(roh, str) else roh
            if obj is None:
                continue
            neu, n = patch_obj(obj)
            if not n:
                continue
            anz += 1; ges += n
            if anwenden:
                c.execute(f"update {tabelle} set {daten_spalte}=? where {id_spalte}=?",
                          (json.dumps(neu, ensure_ascii=False), schluessel))
        if anwenden:
            c.commit()
        print(f"{tabelle}: {anz} Einträge, {ges} Stellen"
              + ("" if anwenden else "  (Trockenlauf – mit --anwenden schreiben)"))

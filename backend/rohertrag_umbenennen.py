"""Benennt die DB-Stufen nach dem, was sie wirklich sind – und macht sie dicht.

Drei Dinge auf einmal, weil sie dieselben Abfragen anfassen:

1. UMBENENNEN. „DB II" war irreführend: die Stufe zog keine weitere Kostenart ab,
   sie erweiterte nur die Basis um den Versand – deshalb konnte sie GRÖSSER sein
   als „DB I". Jetzt heißen sie „Rohertrag Ware" und „Rohertrag gesamt".

2. DICHT MACHEN. Die Gesamtstufe filterte auf `nType IN (1,2)`. Positionsarten
   außerhalb dieser Aufzählung fielen still heraus, obwohl ihr Erlös im Umsatz
   steckt – real sind das nType 0 (HaKo: 1.118 €) und nType 3 (PPS: Rabattposten
   „COMEBACK 10 %", −688 €). Eine Aufzählung ist hier die falsche Bauform: käme
   in einem JTL-Update ein nType 4 dazu, verschwände er wieder unbemerkt. Die
   Gesamtstufe zählt deshalb ab jetzt ALLE Positionen; sie ist damit per
   Konstruktion deckungsgleich mit dem Umsatz. Ware und Versand bleiben als
   benannte Teilstufen, alles Übrige wird als „Sonstiges" sichtbar ausgewiesen
   statt weggelassen.

3. VERSANDKOSTEN-LÜCKE ZEIGEN. Bei PPS haben alle 3.174 Versandpositionen keinen
   EK – der Versanderlös zählt dort als 100 % Marge und schönt den Rohertrag. Das
   ist eine Lücke in der Wawi, keine Rechenfrage; eine Kachel macht sie sichtbar.

Anwenden:
    docker cp backend/rohertrag_umbenennen.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/rohertrag_umbenennen.py --anwenden
    python3 backend/rohertrag_umbenennen.py --template templates/jtl_gf_cockpit.json --anwenden
    python3 backend/rohertrag_umbenennen.py --template templates/jtl_vertrieb_cockpit.json --anwenden
"""
import sqlite3, json, re, sys

DB = "/app/uploads/datenmonster.db"

# ── 1+2: Abfrageregeln ──────────────────────────────────────────────────────
# Zwei Schreibweisen der Gesamtstufe kommen vor. Beide werden entschärft, indem
# die Positionsart-Bedingung ersatzlos verschwindet – nicht durch eine längere
# Aufzählung ersetzt wird.
SQL_REGELN = [
    # a) „… AND nType IN (1,2) THEN …" – die Bedingung hängt an einer anderen
    (re.compile(r"\s+AND\s+(?:POS\.)?nType IN \(1,2\)"), ""),
    # b) „CASE WHEN nType IN (1,2) THEN <ausdruck> ELSE 0 END" – die ganze
    #    Fallunterscheidung fällt weg, der Ausdruck bleibt stehen
    (re.compile(r"CASE WHEN (?:POS\.)?nType IN \(1,2\)\s+THEN\s+(.+?)\s+ELSE 0 END", re.S), r"\1"),
    #    dieselbe Bauform ohne ELSE-Zweig; muss NACH der Regel mit ELSE stehen,
    #    sonst schnappt sie sich dort das „ELSE 0" mit in den Ausdruck
    (re.compile(r"CASE WHEN (?:POS\.)?nType IN \(1,2\)\s+THEN\s+(.+?)\s+END", re.S), r"\1"),
    # c) Spaltenüberschriften in den Tabellen
    (re.compile(r"AS \[DB I\]"), "AS [Rohertrag Ware]"),
    (re.compile(r"AS \[DB II\]"), "AS [Rohertrag gesamt]"),
    (re.compile(r"AS \[DB-Marge %\]"), "AS [Rohertragsmarge %]"),
]

# Die Zielfelder der Mappings tragen die Spaltennamen als GANZEN Wert. Sie
# müssen mit den Aliasen mitwandern, sonst laufen die Tabellen ins Leere –
# als Teilstring dürfen diese kurzen Namen nicht ersetzt werden, dafür sind
# sie zu allgemein („DB I" kommt auch in Fließtext vor).
EXAKT = {
    "DB I": "Rohertrag Ware",
    "DB II": "Rohertrag gesamt",
    "DB-Marge %": "Rohertragsmarge %",
}

# ── 1: Beschriftungen ───────────────────────────────────────────────────────
# Längere Texte zuerst, sonst zerlegt eine kurze Regel den Fließtext.
INFO_ALT = ("Deckungsbeitrag I (= Rohertrag) = Umsatz − Wareneinsatz (Einkaufspreis der "
            "verkauften Artikel). Deckungsbeitrag II = DB I zzgl. Versandergebnis "
            "(Versanderlöse − Versandkosten). DB-Marge % bezogen auf den Umsatz.")
INFO_NEU = ("Rohertrag Ware = Umsatz − Wareneinsatz (Einkaufspreis der verkauften Artikel), "
            "nur Artikelpositionen. Rohertrag gesamt = derselbe Rohertrag über ALLE "
            "Positionsarten, also zuzüglich Versandergebnis (Versanderlöse − Versandkosten) "
            "und sonstiger Positionen wie Rabatten. Marge % bezogen auf den Umsatz. "
            "Achtung: Versandarten ohne hinterlegte Kosten zählen als 100 % Marge.")

TEXT_REGELN = [
    (INFO_ALT, INFO_NEU),
    ("Deckungsbeitrag II (Rohertrag inkl. Versandergebnis) gegen die Fixkosten",
     "Rohertrag gesamt gegen die Fixkosten"),
    ("Betriebsergebnis (DB II abzüglich Fixkosten)", "Betriebsergebnis (Rohertrag gesamt abzüglich Fixkosten)"),
    ("Deckungsbeitrag II gegen Fixkosten je Monat", "Rohertrag gesamt gegen Fixkosten je Monat"),
    ("Deckungsbeitrag je Plattform", "Rohertrag je Plattform"),
    ("Rohertrag (DB I)", "Rohertrag Ware"),
    ("Deckungsbeitrag II", "Rohertrag gesamt"),
    ("DB II-Marge", "Rohertragsmarge"),
    ("DB-II-Quote", "Rohertragsquote"),
    ("dem DB II", "dem Rohertrag gesamt"),
]


def string_patchen(s: str) -> str:
    if s in EXAKT:
        return EXAKT[s]
    for alt, neu in TEXT_REGELN:
        s = s.replace(alt, neu)
    for muster, ersatz in SQL_REGELN:
        s = muster.sub(ersatz, s)
    return s


def obj_patchen(o):
    """Rekursiv durch beliebige JSON-Strukturen; patcht jeden String."""
    if isinstance(o, str):
        neu = string_patchen(o)
        return neu, (1 if neu != o else 0)
    if isinstance(o, dict):
        ges = 0; aus = {}
        for k, v in o.items():
            aus[k], n = obj_patchen(v); ges += n
        return aus, ges
    if isinstance(o, list):
        ges = 0; aus = []
        for v in o:
            nv, n = obj_patchen(v); aus.append(nv); ges += n
        return aus, ges
    return o, 0


# ── 3 + Sonstiges: Zusatzspalten der GF-Kennzahlen ──────────────────────────
# Die innere Zeilenebene bekommt eine Marke für Versandpositionen ohne EK; die
# Aggregatebene zählt sie und weist die Restpositionen getrennt aus.
ZEILE_ANKER = ("            POS.fAnzahl * (POS.fVkNetto - COALESCE(NULLIF(POS.fEkNetto, 0), "
               "A.fEKNetto, 0)) AS DBpos,")
ZEILE_ZUSATZ = ("\n            CASE WHEN POS.nType = 2 AND COALESCE(NULLIF(POS.fEkNetto, 0), A.fEKNetto) "
                "IS NULL THEN 1 ELSE 0 END AS VersandOhneEK,")

AGG_ANKER = "        COUNT(DISTINCT CASE WHEN cur = 1 THEN kRechnung END) AS Rechnungen,"

DURCHREICHEN_ANKER = "    Warenumsatz, Wareneinsatz, Versandergebnis,"
DURCHREICHEN = "\n    SonstigesErgebnis, VersandPos, VersandPosOhneEK, VersandErloesOhneEK,"
AGG_ZUSATZ = """
        CAST(ISNULL(SUM(CASE WHEN cur = 1 AND nType NOT IN (1,2) THEN DBpos END), 0) AS DECIMAL(18,2)) AS SonstigesErgebnis,
        SUM(CASE WHEN cur = 1 AND nType = 2 THEN 1 ELSE 0 END) AS VersandPos,
        SUM(CASE WHEN cur = 1 AND VersandOhneEK = 1 THEN 1 ELSE 0 END) AS VersandPosOhneEK,
        CAST(ISNULL(SUM(CASE WHEN cur = 1 AND VersandOhneEK = 1 THEN Netto END), 0) AS DECIMAL(18,2)) AS VersandErloesOhneEK,"""

NEUE_FELDER = [("SonstigesErgebnis", "float"), ("VersandPos", "int"),
               ("VersandPosOhneEK", "int"), ("VersandErloesOhneEK", "float")]

KACHEL_VERSAND = {
    "id": "w_kpi_versand_ohne_ek",
    "type": "kpi",
    "label": "Versand ohne Kosten",
    "action_id": "act_overview_kpi",
    "config": {
        "width": 4,
        "column": "VersandPosOhneEK",
        "aggregation": "first",
        "prefix": "",
        "suffix": "",
        "decimals": 0,
        # Mehr Lücken sind schlechter.
        "invert_delta": True,
        "breakdown": [
            {"label": "von Versandpositionen", "column": "VersandPos"},
            {"label": "Erlös ohne Gegenkosten", "column": "VersandErloesOhneEK"},
        ],
        "hint": ("Versandpositionen, bei denen in der Wawi kein Einkaufspreis hinterlegt "
                 "ist. Ihr Erlös zählt im Rohertrag als 100 % Marge und schönt ihn. Zu "
                 "beheben ist das nur in JTL bei den Versandarten, nicht hier."),
    },
}

# Die Aufschlüsselung der Gesamtstufe muss die neue Restposition mitzeigen,
# sonst geht die Rechnung für den Leser nicht auf.
BREAKDOWN_GESAMT = [
    {"label": "Rohertrag Ware", "column": "Rohertrag"},
    {"label": "+ Versandergebnis", "column": "Versandergebnis"},
    {"label": "+ Sonstige Positionen", "column": "SonstigesErgebnis"},
]
HINWEIS_GESAMT = ("Umsatz − Wareneinsatz über alle Positionsarten: Ware, Versand und "
                  "sonstige Positionen wie Rabatte. Bewusst ohne Aufzählung der "
                  "Positionsarten gerechnet, damit künftige Arten nicht stillschweigend "
                  "fehlen. Nicht zu verwechseln mit den Deckungsbeitragsstufen der "
                  "Kostenrechnung – hier wird keine weitere Kostenstufe abgezogen.")
HINWEIS_WARE = ("Nur Artikelpositionen: Umsatz − Wareneinsatz. Positionen ohne "
                "hinterlegten Einkaufspreis zählen als 100 % Marge.")


def kennzahlen_erweitern(nodes: list, targets: list) -> None:
    sql = nodes[0]["sql"]
    if "VersandPosOhneEK" in sql:
        return                                      # schon vorhanden
    for anker, zusatz in ((ZEILE_ANKER, ZEILE_ZUSATZ), (AGG_ANKER, AGG_ZUSATZ),
                          (DURCHREICHEN_ANKER, DURCHREICHEN)):
        if anker not in sql:
            raise SystemExit(f"Anker nicht gefunden: {anker[:60]!r}")
        sql = sql.replace(anker, anker + zusatz, 1)
    nodes[0]["sql"] = sql
    of = nodes[0].get("output_fields")
    if of:
        of.extend(n for n, _ in NEUE_FELDER if n not in of)
    felder = targets[0].get("fields") or []
    hat = {f.get("target_field") for f in felder}
    for name, typ in NEUE_FELDER:
        if name in hat:
            continue
        felder.append({"source_field": name, "target_field": name, "target_type": typ,
                       "source_dataset_id": "__sql__sql1",
                       "transformer": {"type": "direct", "source_field": name}})
    targets[0]["fields"] = felder


def widgets_erweitern(widgets: list) -> None:
    for w in widgets:
        c = w.get("config") or {}
        if w.get("id") == "w_kpi_db2":
            c["breakdown"] = json.loads(json.dumps(BREAKDOWN_GESAMT))
            c["hint"] = HINWEIS_GESAMT
        elif w.get("id") == "w_kpi_rohertrag":
            c["hint"] = HINWEIS_WARE
    if not any(w.get("id") == KACHEL_VERSAND["id"] for w in widgets):
        idx = next((i for i, w in enumerate(widgets) if w.get("id") == "w_kpi_db2marge"), None)
        widgets.insert(idx + 1 if idx is not None else len(widgets),
                       json.loads(json.dumps(KACHEL_VERSAND)))


def main_db(anwenden: bool):
    c = sqlite3.connect(DB)
    ges = 0
    for tabelle, id_spalte, spalten in (
            ("mappings", "id", ("sql_nodes", "canvas_nodes", "targets")),
            ("forms", "id", ("schema",)),
            ("templates", "template_id", ("content",))):
        anz = teil = 0
        for zeile in c.execute(f"select {id_spalte},{','.join(spalten)} from {tabelle}").fetchall():
            schluessel, rohwerte = zeile[0], zeile[1:]
            neu_werte, n = [], 0
            for roh in rohwerte:
                obj = json.loads(roh) if isinstance(roh, str) else roh
                if obj is None:
                    neu_werte.append(roh); continue
                neu, k = obj_patchen(obj); n += k
                neu_werte.append(json.dumps(neu, ensure_ascii=False) if k else roh)
            if not n:
                continue
            anz += 1; teil += n
            if anwenden:
                c.execute(f"update {tabelle} set " + ",".join(f"{s}=?" for s in spalten)
                          + f" where {id_spalte}=?", (*neu_werte, schluessel))
        print(f"{tabelle}: {anz} Einträge, {teil} geänderte Texte")
        ges += teil

    # Zusatzspalten und Kacheln nur im GF-Cockpit (Mapping 1 / Formular 1)
    sn, tg = c.execute("select sql_nodes, targets from mappings where id=1").fetchone()
    nodes, targets = json.loads(sn), json.loads(tg)
    kennzahlen_erweitern(nodes, targets)
    sch = json.loads(c.execute("select schema from forms where id=1").fetchone()[0])
    widgets_erweitern(sch.setdefault("widgets", []))
    print(f"Mapping 1: {len(targets[0]['fields'])} Zielfelder, "
          f"Versandlücke im SQL: {'VersandPosOhneEK' in nodes[0]['sql']}; "
          f"Formular 1: {len(sch['widgets'])} Widgets")

    if not anwenden:
        print(f"\n(Trockenlauf, {ges} Texte – mit --anwenden schreiben)")
        return
    c.execute("update mappings set sql_nodes=?, targets=? where id=1",
              (json.dumps(nodes, ensure_ascii=False), json.dumps(targets, ensure_ascii=False)))
    c.execute("update forms set schema=? where id=1", (json.dumps(sch, ensure_ascii=False),))
    c.commit()
    print("\ngeschrieben.")


def main_template(pfad: str, anwenden: bool):
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    t, n = obj_patchen(t)
    if "gf_cockpit" in pfad:
        m = next(x for x in t["mappings"] if x["name"] == "Cockpit – Kennzahlen")
        kennzahlen_erweitern(m["sql_nodes"], m["targets"])
        widgets_erweitern(t["forms"][0]["schema"].setdefault("widgets", []))
    t["version"] = "2.8" if "gf_cockpit" in pfad else t.get("version")
    print(f"{pfad}: {n} geänderte Texte")
    if not anwenden:
        print("\n(Trockenlauf – mit --anwenden schreiben)")
        return
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
    print("geschrieben.")


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        main_template(sys.argv[sys.argv.index("--template") + 1], anwenden)
    else:
        main_db(anwenden)

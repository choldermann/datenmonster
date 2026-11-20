"""Mapping-Baukasten: Steinkette → SQL.

Der Baukasten ist eine Ansicht; darunter steht diese Kette (JSON), und daraus entsteht eine einzige
SQL-Abfrage, die als ganz normales Mapping läuft (SQL-Knoten im Modus „transform“). Damit erben
Baukasten-Auswertungen Cockpit, Export, Zeitplan, PDF und Mandantentausch ohne Zusatzarbeit.

Sicherheit wie im Abfrage-Generator (query_builder/sql_bauer.py): **kein Name aus der Kette gelangt
ungeprüft ins SQL.** Tabellen und Spalten werden gegen den Schema-Cache der Verbindung geprüft und
gequotet, Operatoren und Funktionen kommen aus festen Listen, Werte werden gebunden (Vorschau) oder
als geprüftes Literal gesetzt (gespeichertes Mapping, das später ohne unsere Parameter läuft).

Kette (Beispiel):
    [
      {"type": "start", "trigger": "Wenn das Cockpit öffnet"},
      {"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
          {"type": "filter", "col": "dErstellt", "op": "im Zeitraum"},
          {"type": "join", "table": "dbo.tKunde", "links": "kKunde", "rechts": "kKunde", "inner": [
              {"type": "filter", "col": "cLand", "op": "=", "val": "DE"}]}]},
      {"type": "rechnen", "name": "Brutto", "a": "fWert", "op": "×", "b": "1.19"},
      {"type": "verdichten", "by": ["cFirma", {"col": "dErstellt", "teil": "monat"}],
       "aggs": [{"fn": "Summe", "col": "fWert"}, {"fn": "Anzahl"}]},
      {"type": "filter", "col": "Summe fWert", "op": ">", "val": "1000"},
      {"type": "sortieren", "col": "Summe fWert", "dir": "absteigend"},
      {"type": "begrenzen", "n": 10},
      {"type": "ausgabe", "target": "Tabelle im Cockpit"}
    ]

Block-IDs (für Zähler und Vorschau, gleich wie im Prototyp): oberste Ebene ":<i>", Kopf der Tabelle
":<i>:kopf", Steine im Winkel "<i>:<j>", Steine in „Dazuholen“ "<i>.<j>:<k>".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.query_builder.sql_bauer import _Binder

MAX_STEINE = 60
MAX_LIMIT = 100000


class BaukastenFehler(ValueError):
    """Die Kette ist unbrauchbar. Der Text geht an den Anwender."""


# ── Regeln: welcher Stein darf wohin (gleich wie im Prototyp) ──────────────
def pruefen(kette: list) -> None:
    if not isinstance(kette, list) or not kette:
        raise BaukastenFehler("Die Kette ist leer.")
    if _anzahl(kette) > MAX_STEINE:
        raise BaukastenFehler(f"Höchstens {MAX_STEINE} Steine.")
    tab = verd = -1
    for i, b in enumerate(kette):
        t = (b or {}).get("type")
        if t == "start" and i != 0:
            raise BaukastenFehler("„Start“ gehört an den Anfang.")
        if t == "join":
            raise BaukastenFehler("„Dazuholen“ gehört in den Winkel einer Tabelle.")
        if t == "tabelle":
            if tab >= 0:
                raise BaukastenFehler("Nur eine Tabelle auf oberster Ebene – weitere über „Dazuholen“.")
            tab = i
            _innen_pruefen(b.get("inner") or [], "tabelle")
        elif t in ("rechnen", "sortieren", "begrenzen", "verdichten", "ausgabe", "filter", "profi") and tab < 0:
            raise BaukastenFehler("Zuerst eine Tabelle, dann die Schritte.")
        if t == "filter" and verd < 0:
            raise BaukastenFehler("„Nur wenn“ auf oberster Ebene prüft eine Kennzahl und steht deshalb nach „Zusammenfassen“.")
        if t == "verdichten":
            if verd >= 0:
                raise BaukastenFehler("Nur ein „Zusammenfassen“ je Auswertung.")
            verd = i
        if t == "ausgabe" and i != len(kette) - 1:
            raise BaukastenFehler("Die Ausgabe ist immer der letzte Stein.")
        if t not in ("start", "tabelle", "filter", "rechnen", "verdichten", "sortieren", "begrenzen", "ausgabe", "profi"):
            raise BaukastenFehler(f"Unbekannter Stein: {t!r}")
    if tab < 0:
        raise BaukastenFehler("Es fehlt eine Tabelle.")


def _innen_pruefen(liste: list, art: str) -> None:
    for b in liste:
        t = (b or {}).get("type")
        if art == "tabelle" and t not in ("filter", "join"):
            raise BaukastenFehler("In den Winkel einer Tabelle passen nur „Nur wenn“ und „Dazuholen“.")
        if art == "join" and t != "filter":
            raise BaukastenFehler("In „Dazuholen“ passt nur „Nur wenn“.")
        if t == "join":
            _innen_pruefen(b.get("inner") or [], "join")


def _anzahl(liste) -> int:
    return sum(1 + _anzahl((b or {}).get("inner") or []) for b in liste)


# ── Schema und Dialekt ─────────────────────────────────────────────────────
ZAHL_TYPEN = ("int", "decimal", "numeric", "money", "float", "real", "double", "bit", "smallint", "tinyint", "bigint")
DATUM_TYPEN = ("date", "time", "timestamp")


@dataclass
class Spalte:
    name: str
    typ: str            # "zahl" | "datum" | "text"


class Schema:
    """Tabellen und Spalten aus dem Schema-Cache – die einzige Quelle für Namen im SQL."""

    def __init__(self, schema_json: dict):
        self.tabellen: dict[str, list[Spalte]] = {}
        mssql = (schema_json or {}).get("db_type", "mssql") == "mssql"
        for t in (schema_json or {}).get("tables", []):
            spalten = []
            for c in t.get("columns", []):
                roh = str(c.get("type") or "").lower()
                if mssql and roh in ("timestamp", "rowversion"):
                    spalten.append(Spalte(c["name"], "text"))     # SQL Server: Zeilenversion, keine Zeit
                    continue
                typ = "zahl" if any(z in roh for z in ZAHL_TYPEN) else "datum" if any(d in roh for d in DATUM_TYPEN) else "text"
                spalten.append(Spalte(c["name"], typ))
            self.tabellen[t["full_name"]] = spalten

    def spalten(self, tabelle: str) -> list[Spalte]:
        if tabelle not in self.tabellen:
            raise BaukastenFehler(f"Tabelle „{tabelle}“ gibt es in dieser Datenbank nicht (Schema neu laden?).")
        return self.tabellen[tabelle]


class Dialekt:
    def __init__(self, name: str):
        self.name = name if name in ("mssql", "mysql", "postgresql") else "mssql"

    def q(self, ident: str) -> str:
        if self.name == "mysql":
            return "`" + ident.replace("`", "``") + "`"
        if self.name == "postgresql":
            return '"' + ident.replace('"', '""') + '"'
        return "[" + ident.replace("]", "]]") + "]"

    def tabelle(self, voll: str) -> str:
        return ".".join(self.q(t) for t in voll.split("."))

    def monat(self, x: str) -> str:
        return {"mysql": f"DATE_FORMAT({x}, '%Y-%m')", "postgresql": f"to_char({x}, 'YYYY-MM')"}.get(self.name, f"CONVERT(char(7), {x}, 126)")

    def jahr(self, x: str) -> str:
        return {"postgresql": f"CAST(EXTRACT(YEAR FROM {x}) AS int)"}.get(self.name, f"YEAR({x})")

    def tage_zurueck(self, n: int) -> str:
        return {"mysql": f"DATE_SUB(CURDATE(), INTERVAL {n} DAY)",
                "postgresql": f"(CURRENT_DATE - INTERVAL '{n} days')"}.get(self.name, f"DATEADD(DAY, -{n}, CAST(GETDATE() AS date))")

    def bis_einschl(self, x: str) -> str:
        return {"mysql": f"DATE_ADD({x}, INTERVAL 1 DAY)", "postgresql": f"({x} + INTERVAL '1 day')"}.get(self.name, f"DATEADD(DAY, 1, {x})")

    def like(self, x: str, p: str) -> str:
        return f"LOWER({x}) LIKE LOWER({p})" if self.name != "postgresql" else f"{x} ILIKE {p}"

    def text(self, x: str) -> str:
        return f"CAST({x} AS {'char' if self.name == 'mysql' else 'varchar(400)' if self.name == 'postgresql' else 'nvarchar(400)'})"

    def datum(self, iso: str) -> str:
        """SQL Server liest 'JJJJ-MM-TT' bei deutscher Spracheinstellung als JJJJ-TT-MM – 'JJJJMMTT' ist eindeutig."""
        return iso.replace("-", "") if self.name == "mssql" else iso


def vorschau_begrenzen(sql: str, n: int, dialekt: str) -> str:
    """Vorschau-SQL auf n Zeilen deckeln (das letzte SELECT bekommt TOP bzw. die Abfrage LIMIT)."""
    n = int(n)
    if dialekt == "mssql":
        if re.search(r"SELECT TOP \(\d+\) \* FROM s\d+", sql):
            return sql
        pos = sql.rfind("\nSELECT * FROM ")
        if pos >= 0:
            return sql[:pos] + f"\nSELECT TOP ({n}) * FROM " + sql[pos + len("\nSELECT * FROM "):]
        return re.sub(r"^\s*SELECT\s+", f"SELECT TOP ({n}) ", sql, count=1, flags=re.I)
    return sql if re.search(r"\bLIMIT \d+\s*$", sql) else f"{sql}\nLIMIT {n}"


# ── Übersetzen ─────────────────────────────────────────────────────────────
OPS = ("=", "≠", ">", "<", "≥", "≤", "enthält", "beginnt mit", "ist leer", "ist nicht leer",
       "im Jahr", "in den letzten Tagen", "im Zeitraum")
RECHEN_OPS = {"+": "+", "−": "-", "-": "-", "×": "*", "*": "*", "÷": "/", "/": "/"}
AGG = {"Summe": "SUM", "Durchschnitt": "AVG", "Höchstwert": "MAX", "Tiefstwert": "MIN", "Anzahl": "COUNT"}
AGG_KURZ = {"Summe": "Summe", "Durchschnitt": "Ø", "Höchstwert": "Max", "Tiefstwert": "Min"}


@dataclass
class Stufe:
    """Eine CTE der Kette: Name, SQL-Rumpf, Spalten danach."""
    name: str
    sql: str
    spalten: list[Spalte]


@dataclass
class Ergebnis:
    sql: str                                   # die ganze Abfrage
    spalten: list[Spalte]                      # Ausgabespalten
    zaehl_sql: dict[str, str] = field(default_factory=dict)     # Block-ID → SELECT COUNT(*) …
    vorschau_sql: dict[str, str] = field(default_factory=dict)  # Block-ID → SELECT * … (für die Vorschau)
    spalten_je_block: dict[str, list[str]] = field(default_factory=dict)  # was an einem Stein ankommt (für die Auswahllisten)
    params: dict = field(default_factory=dict)
    nutzt_zeitraum: bool = False


def uebersetzen(kette: list, schema: Schema, dialekt: str = "mssql", literal: bool = False) -> Ergebnis:
    """Kette → SQL. literal=True setzt Werte als geprüfte Literale (für das gespeicherte Mapping)."""
    pruefen(kette)
    d = Dialekt(dialekt)
    bind = _Binder(literal=literal)
    ctx = {"zeitraum": False}
    stufen: list[Stufe] = []
    erg = Ergebnis(sql="", spalten=[])

    def cte_sql(bis: int) -> str:
        return "WITH " + ",\n".join(f"{s.name} AS (\n{s.sql}\n)" for s in stufen[:bis + 1])

    def merken(block_id: str, spalten_in: list[Spalte], bis_stufe: int | None, roh_sql: str | None = None):
        erg.spalten_je_block[block_id] = [s.name for s in spalten_in]
        if roh_sql is not None:
            erg.zaehl_sql[block_id] = f"SELECT COUNT(*) AS n FROM (\n{roh_sql}\n) z"
            erg.vorschau_sql[block_id] = roh_sql
        elif bis_stufe is not None:
            s = stufen[bis_stufe]
            erg.zaehl_sql[block_id] = f"{cte_sql(bis_stufe)}\nSELECT COUNT(*) AS n FROM {s.name}"
            erg.vorschau_sql[block_id] = f"{cte_sql(bis_stufe)}\nSELECT * FROM {s.name}"

    spalten: list[Spalte] = []
    sortierung = None
    limit = None
    for i, b in enumerate(kette):
        t = b.get("type")
        bid = f":{i}"
        if t == "tabelle":
            spalten = _tabelle(b, i, schema, d, bind, ctx, stufen, merken)
            merken(bid, [], len(stufen) - 1)
        elif t == "filter":
            bed = _bedingung(b, spalten, d, bind, ctx, alias=None)
            vorher = stufen[-1]
            stufen.append(Stufe(f"s{len(stufen)}", f"SELECT * FROM {vorher.name}" + (f"\nWHERE {bed}" if bed else ""), spalten))
            merken(bid, spalten, len(stufen) - 1)
        elif t == "rechnen":
            spalten_in = spalten
            name = _name(b.get("name") or "Neue Spalte")
            a = _operand(b.get("a"), spalten, d, bind)
            c = _operand(b.get("b"), spalten, d, bind)
            op = RECHEN_OPS.get(b.get("op") or "")
            if not op:
                raise BaukastenFehler("Rechnen: unbekannte Rechenart.")
            ausdruck = f"ROUND(CAST({a} AS float) / NULLIF(CAST({c} AS float), 0), 2)" if op == "/" else f"({a} {op} {c})"
            if any(s.name.lower() == name.lower() for s in spalten):
                raise BaukastenFehler(f"Rechnen: die Spalte „{name}“ gibt es schon – anderen Namen wählen.")
            vorher = stufen[-1]
            stufen.append(Stufe(f"s{len(stufen)}", f"SELECT *, {ausdruck} AS {d.q(name)} FROM {vorher.name}", spalten + [Spalte(name, "zahl")]))
            spalten = stufen[-1].spalten
            merken(bid, spalten_in, len(stufen) - 1)
        elif t == "verdichten":
            spalten_in = spalten
            gruppe, aus, neu = [], [], []
            for x in (b.get("by") or [])[:4]:
                if not x:
                    continue
                col = x.get("col") if isinstance(x, dict) else x
                teil = x.get("teil") if isinstance(x, dict) else None
                s = _spalte(col, spalten)
                expr = d.q(s.name)
                if teil in ("monat", "jahr"):
                    if s.typ != "datum":
                        raise BaukastenFehler(f"„{s.name}“ ist kein Datum – Monat/Jahr geht nur bei Datumsspalten.")
                    expr = d.monat(expr) if teil == "monat" else d.jahr(expr)
                    name = f"{s.name} ({'Monat' if teil == 'monat' else 'Jahr'})"
                    typ = "text" if teil == "monat" else "zahl"
                else:
                    name, typ = s.name, s.typ
                gruppe.append(expr)
                aus.append(f"{expr} AS {d.q(name)}")
                neu.append(Spalte(name, typ))
            if not gruppe:
                raise BaukastenFehler("Zusammenfassen: mindestens eine Spalte „je …“ wählen.")
            for a in (b.get("aggs") or [])[:8]:
                fn = a.get("fn")
                if fn not in AGG:
                    raise BaukastenFehler(f"Zusammenfassen: unbekannte Kennzahl {fn!r}.")
                if fn == "Anzahl":
                    name, expr = "Anzahl", "COUNT(*)"
                else:
                    s = _spalte(a.get("col"), spalten)
                    if s.typ != "zahl" and fn in ("Summe", "Durchschnitt"):
                        raise BaukastenFehler(f"„{fn}“ geht nur mit Zahlen – „{s.name}“ ist keine.")
                    name = f"{AGG_KURZ[fn]} {s.name}"
                    expr = f"ROUND({AGG[fn]}(CAST({d.q(s.name)} AS float)), 2)" if fn in ("Summe", "Durchschnitt") else f"{AGG[fn]}({d.q(s.name)})"
                if any(n.name.lower() == name.lower() for n in neu):
                    continue
                aus.append(f"{expr} AS {d.q(name)}")
                neu.append(Spalte(name, "zahl" if fn != "Höchstwert" and fn != "Tiefstwert" else _spalte(a.get("col"), spalten).typ))
            vorher = stufen[-1]
            stufen.append(Stufe(f"s{len(stufen)}", f"SELECT {', '.join(aus)}\nFROM {vorher.name}\nGROUP BY {', '.join(gruppe)}", neu))
            spalten = neu
            merken(bid, spalten_in, len(stufen) - 1)
        elif t == "sortieren":
            s = _spalte(b.get("col"), spalten)
            sortierung = f"{d.q(s.name)} {'DESC' if b.get('dir') != 'aufsteigend' else 'ASC'}"
            erg.spalten_je_block[bid] = [x.name for x in spalten]
        elif t == "begrenzen":
            try:
                limit = max(1, min(int(b.get("n") or 0), MAX_LIMIT))
            except (TypeError, ValueError):
                raise BaukastenFehler("„Nur die ersten“: bitte eine ganze Zahl.")
            erg.spalten_je_block[bid] = [x.name for x in spalten]
        elif t in ("start", "ausgabe", "profi"):
            erg.spalten_je_block[bid] = [x.name for x in spalten]

    letzte = stufen[-1].name
    cte = cte_sql(len(stufen) - 1)
    order = f"\nORDER BY {sortierung}" if sortierung else ""
    if d.name == "mssql":
        # TOP gehört ins äußere SELECT (nicht vor WITH); ORDER BY nur ganz außen
        kern = f"SELECT TOP ({limit}) * FROM {letzte}" if limit else f"SELECT * FROM {letzte}"
        final = f"{cte}\n{kern}{order}"
        # mit TOP darf ORDER BY in die Unterabfrage – dann zählt „Nur die ersten“ wirklich die ersten
        zaehl = f"{cte}\nSELECT COUNT(*) AS n FROM ({kern}{order if limit else ''}) z"
    else:
        lim = f"\nLIMIT {limit}" if limit else ""
        final = f"{cte}\nSELECT * FROM {letzte}{order}{lim}"
        zaehl = f"{cte}\nSELECT COUNT(*) AS n FROM (SELECT * FROM {letzte}{order}{lim}) z"
    # Sortieren/Begrenzen/Ausgabe zeigen das Endergebnis
    for i, b in enumerate(kette):
        if b.get("type") in ("sortieren", "begrenzen", "ausgabe", "profi"):
            erg.zaehl_sql[f":{i}"] = zaehl
            erg.vorschau_sql[f":{i}"] = final
    erg.sql = final
    erg.spalten = spalten
    erg.params = dict(bind.werte)
    erg.nutzt_zeitraum = ctx["zeitraum"]
    return erg


def _tabelle(b, i, schema: Schema, d: Dialekt, bind, ctx, stufen: list, merken) -> list[Spalte]:
    """Winkel „Aus Tabelle“ samt Filtern und „Dazuholen“ → eine CTE s0."""
    haupt = b.get("table") or ""
    basis = schema.spalten(haupt)
    alias = "t0"
    # Kopf: Tabelle roh
    kopf_sql = f"SELECT * FROM {d.tabelle(haupt)} {alias}"
    merken(f":{i}:kopf", [], None, roh_sql=kopf_sql)

    wo: list[str] = []
    joins: list[str] = []
    auswahl = [f"{alias}.{d.q(s.name)} AS {d.q(s.name)}" for s in basis]
    spalten = list(basis)
    n_join = 0

    def aktueller_sql() -> str:
        return (f"SELECT {', '.join(auswahl)}\nFROM {d.tabelle(haupt)} {alias}" + "".join(joins)
                + (f"\nWHERE {' AND '.join(wo)}" if wo else ""))

    for j, x in enumerate(b.get("inner") or []):
        bid = f"{i}:{j}"
        spalten_in = list(spalten)
        if x.get("type") == "filter":
            # Filter im Winkel prüfen die Haupttabelle oder bereits dazugeholte Spalten
            bed = _bedingung(x, spalten, d, bind, ctx, alias=None, quelle=_quellen(auswahl))
            if bed:
                wo.append(bed)
            merken(bid, spalten_in, None, roh_sql=aktueller_sql())
        elif x.get("type") == "join":
            n_join += 1
            ja = f"j{n_join}"
            fremd = x.get("table") or ""
            fspalten = schema.spalten(fremd)
            links = _spalte(x.get("links"), spalten)
            rechts = _spalte(x.get("rechts"), fspalten)
            # Filter in „Dazuholen“ wirken auf die dazugeholte Tabelle (Unterabfrage)
            fwo = []
            for k, f in enumerate(x.get("inner") or []):
                bed = _bedingung(f, fspalten, d, bind, ctx, alias=None)
                if bed:
                    fwo.append(bed)
                sub = f"SELECT * FROM {d.tabelle(fremd)}" + (f"\nWHERE {' AND '.join(fwo)}" if fwo else "")
                merken(f"{i}.{j}:{k}", fspalten, None, roh_sql=sub)
            sub = f"SELECT * FROM {d.tabelle(fremd)}" + (f" WHERE {' AND '.join(fwo)}" if fwo else "")
            links_expr = _quellen(auswahl).get(links.name, f"{alias}.{d.q(links.name)}")
            joins.append(f"\nINNER JOIN ({sub}) {ja} ON {links_expr} = {ja}.{d.q(rechts.name)}")
            # Namen ohne Rücksicht auf Groß-/Kleinschreibung vergleichen: für SQL Server sind cUstId und cUSTID dieselbe Spalte
            vorhanden = {s.name.lower() for s in spalten}
            for s in fspalten:
                if s.name.lower() == rechts.name.lower() and rechts.name.lower() == links.name.lower():
                    continue                      # Schlüssel nicht doppelt
                name = s.name if s.name.lower() not in vorhanden else f"{s.name} ({fremd.split('.')[-1]})"
                if name.lower() in vorhanden:
                    continue
                auswahl.append(f"{ja}.{d.q(s.name)} AS {d.q(name)}")
                spalten.append(Spalte(name, s.typ))
                vorhanden.add(name.lower())
            merken(bid, spalten_in, None, roh_sql=aktueller_sql())
            # Zähler „x von y passen“ der dazugeholten Tabelle
            merken(f"{i}:{j}:fremd", fspalten, None, roh_sql=sub)
    stufen.append(Stufe("s0", aktueller_sql(), spalten))
    return spalten


def _quellen(auswahl: list[str]) -> dict:
    """Ausgabename → Quellausdruck (für WHERE vor der CTE: dort gibt es die Aliase noch nicht)."""
    aus = {}
    for a in auswahl:
        expr, _, name = a.rpartition(" AS ")
        aus[name.strip("[]`\"").replace("]]", "]")] = expr
    return aus


def _spalte(name, spalten: list[Spalte]) -> Spalte:
    for s in spalten:
        if s.name == name:
            return s
    raise BaukastenFehler(f"Spalte „{name}“ gibt es an dieser Stelle nicht.")


def _name(n: str) -> str:
    n = re.sub(r"[\x00-\x1f\[\]`\"]", "", str(n)).strip()[:60]
    if not n:
        raise BaukastenFehler("Bitte einen Namen für die neue Spalte.")
    return n


def _operand(x, spalten: list[Spalte], d: Dialekt, bind) -> str:
    for s in spalten:
        if s.name == x:
            return d.q(s.name)
    try:
        return bind(float(str(x).replace(",", ".")), "zahl")
    except (TypeError, ValueError):
        raise BaukastenFehler(f"Rechnen: „{x}“ ist weder Spalte noch Zahl.")


def _bedingung(b: dict, spalten: list[Spalte], d: Dialekt, bind, ctx, alias=None, quelle: dict | None = None) -> str:
    """Eine Bedingung → SQL. Leerer Wert = Stein wirkt (noch) nicht (wie im Prototyp)."""
    op = b.get("op") or "="
    if op not in OPS:
        raise BaukastenFehler(f"Unbekannter Vergleich {op!r}.")
    s = _spalte(b.get("col"), spalten)
    x = (quelle or {}).get(s.name) or d.q(s.name)
    wert = b.get("val")
    leer = wert is None or str(wert).strip() == ""
    if op == "ist leer":
        return f"({x} IS NULL OR {d.text(x)} = '')" if s.typ == "text" else f"{x} IS NULL"
    if op == "ist nicht leer":
        return f"({x} IS NOT NULL AND {d.text(x)} <> '')" if s.typ == "text" else f"{x} IS NOT NULL"
    if op == "im Zeitraum":
        if s.typ != "datum":
            raise BaukastenFehler(f"„im Zeitraum“ geht nur bei Datumsspalten – „{s.name}“ ist keine.")
        ctx["zeitraum"] = True
        return f"{x} >= :von AND {x} < {d.bis_einschl(':bis')}"
    if leer:
        return ""
    w = str(wert).strip()
    if op == "im Jahr":
        try:
            jahr = int(w)
        except ValueError:
            raise BaukastenFehler("„im Jahr“: bitte eine Jahreszahl, z. B. 2026.")
        if s.typ != "datum":
            raise BaukastenFehler(f"„im Jahr“ geht nur bei Datumsspalten – „{s.name}“ ist keine.")
        return f"{x} >= {bind(d.datum(f'{jahr:04d}-01-01'), 'datum')} AND {x} < {bind(d.datum(f'{jahr + 1:04d}-01-01'), 'datum')}"
    if op == "in den letzten Tagen":
        try:
            n = max(0, min(int(w), 3650))
        except ValueError:
            raise BaukastenFehler("„in den letzten Tagen“: bitte eine Zahl.")
        return f"{x} >= {d.tage_zurueck(n)}"
    if op in ("enthält", "beginnt mit"):
        roh = w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        muster = f"%{roh}%" if op == "enthält" else f"{roh}%"
        return f"{d.like(d.text(x), bind(muster, 'text'))} ESCAPE '\\'"
    sql_op = {"=": "=", "≠": "<>", ">": ">", "<": "<", "≥": ">=", "≤": "<="}[op]
    if s.typ == "zahl":
        try:
            return f"{x} {sql_op} {bind(float(w.replace(',', '.')), 'zahl')}"
        except ValueError:
            raise BaukastenFehler(f"„{s.name}“ ist eine Zahl – „{w}“ passt nicht.")
    if s.typ == "datum":
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", w)
        iso = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else w
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
            raise BaukastenFehler(f"„{s.name}“ ist ein Datum – bitte TT.MM.JJJJ.")
        return f"{x} {sql_op} {bind(d.datum(iso), 'datum')}"
    return f"{x} {sql_op} {bind(w, 'text')}"

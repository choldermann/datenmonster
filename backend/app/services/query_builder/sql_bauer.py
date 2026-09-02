"""Baut aus einer Abfrage-Definition (JSON) SQL plus gebundene Parameter.

Reine Mechanik: jeder Ausdruck kommt aus `katalog.py`, jeder Wert wird gebunden.
Aus der Definition selbst gelangt **kein Zeichen** in den SQL-Text — damit ist
Injektion strukturell ausgeschlossen und nicht bloß gefiltert.

Definition:
    {
      "koernung": "kunde",
      "zeilenfilter":   {"op": "UND", "kinder": [ … ]},
      "kennzahlen":     ["auftraege", "rechnungen", "umsatz"],
      "kennzahlfilter": {"op": "UND", "kinder": [ … ]},
      "sortierung":     {"key": "umsatz", "richtung": "desc"},
      "limit":          500
    }

Ein Zweig ist entweder eine Gruppe  {"op": "UND"|"ODER", "kinder": [...]}
oder eine Bedingung                 {"key": "kunde.land", "vergleich": "=", "wert": "DE"}
"""
from . import katalog

MAX_LIMIT = 5000
MAX_TIEFE = 6          # gegen versehentlich (oder absichtlich) endlose Bäume
MAX_LISTE = 500        # Werte in einer „ist eines von“-Liste


class AbfrageFehler(ValueError):
    """Die Definition ist unbrauchbar. Der Text geht an den Anwender."""


class _Binder:
    """Vergibt Parameternamen und sammelt die Werte."""

    def __init__(self):
        self.werte: dict = {}
        self._n = 0

    def __call__(self, wert) -> str:
        name = f"p{self._n}"
        self._n += 1
        self.werte[name] = wert
        return f":{name}"


def _bedingung(ausdruck: str, typ: str, vergleich: str, wert, binde: _Binder) -> str:
    """Eine einzelne Bedingung als SQL-Schnipsel."""
    erlaubt = {o for o, _ in katalog.VERGLEICHE.get(typ, [])}
    if vergleich not in erlaubt:
        raise AbfrageFehler(f"Vergleich „{vergleich}“ passt nicht zu einem Feld vom Typ „{typ}“.")

    if vergleich == "leer":
        return f"({ausdruck} IS NULL OR LTRIM(RTRIM(CAST({ausdruck} AS NVARCHAR(400)))) = '')"
    if vergleich == "nicht_leer":
        return f"({ausdruck} IS NOT NULL AND LTRIM(RTRIM(CAST({ausdruck} AS NVARCHAR(400)))) <> '')"

    if vergleich == "zwischen":
        if not isinstance(wert, (list, tuple)) or len(wert) != 2:
            raise AbfrageFehler("„zwischen“ braucht genau zwei Werte.")
        return f"({ausdruck} >= {binde(wert[0])} AND {ausdruck} <= {binde(wert[1])})"

    if vergleich == "in":
        werte = wert if isinstance(wert, (list, tuple)) else [wert]
        werte = [w for w in werte if w is not None and w != ""]
        if not werte:
            # Leere Auswahl heißt „keine Einschränkung“ – nicht „nichts trifft zu“.
            return "(1 = 1)"
        if len(werte) > MAX_LISTE:
            raise AbfrageFehler(f"Höchstens {MAX_LISTE} Werte je Auswahl.")
        platz = ", ".join(binde(w) for w in werte)
        return f"({ausdruck} IN ({platz}))"

    if vergleich == "enthaelt":
        return f"({ausdruck} LIKE {binde('%' + str(wert) + '%')})"
    if vergleich == "beginnt":
        return f"({ausdruck} LIKE {binde(str(wert) + '%')})"

    if wert is None or wert == "":
        raise AbfrageFehler(f"Für den Vergleich „{vergleich}“ fehlt der Wert.")

    if typ == "ja_nein":
        wert = 1 if str(wert).lower() in ("1", "true", "ja", "y") else 0

    # NULL vergleicht sich in SQL mit nichts. Bei „ist nicht“ erwartet der
    # Anwender aber, dass leere Werte mitkommen – sonst verschwinden Zeilen,
    # ohne dass er es merkt.
    if vergleich == "<>":
        return f"({ausdruck} IS NULL OR {ausdruck} <> {binde(wert)})"
    return f"({ausdruck} {vergleich} {binde(wert)})"


def _baum(knoten: dict, aufloesen, binde: _Binder, tiefe: int = 0) -> str:
    """Übersetzt einen UND/ODER-Baum. `aufloesen(key)` liefert (sql, typ)."""
    if tiefe > MAX_TIEFE:
        raise AbfrageFehler("Der Bedingungsblock ist zu tief verschachtelt.")
    if not isinstance(knoten, dict):
        raise AbfrageFehler("Ungültiger Bedingungsblock.")

    if "op" in knoten:
        op = str(knoten.get("op", "UND")).upper()
        if op not in ("UND", "ODER"):
            raise AbfrageFehler(f"Unbekannte Verknüpfung „{op}“.")
        kinder = [k for k in (knoten.get("kinder") or []) if k]
        teile = [_baum(k, aufloesen, binde, tiefe + 1) for k in kinder]
        teile = [t for t in teile if t]
        if not teile:
            return ""
        if len(teile) == 1:
            return teile[0]
        return "(" + f" {'AND' if op == 'UND' else 'OR'} ".join(teile) + ")"

    key = knoten.get("key")
    if not key:
        return ""
    ausdruck, typ = aufloesen(key)
    return _bedingung(ausdruck, typ, knoten.get("vergleich") or "=",
                      knoten.get("wert"), binde)


def bauen(definition: dict) -> dict:
    """Gibt {sql, params, spalten} zurück. Wirft AbfrageFehler bei Unsinn."""
    kname = definition.get("koernung") or "kunde"
    k = katalog.KOERNUNGEN.get(kname)
    if not k:
        raise AbfrageFehler(f"Unbekannte Körnung „{kname}“.")

    binde = _Binder()

    # ── Spalten: Standardausgabe des Feldkatalogs plus gewählte Kennzahlen ──
    spalten, namen = [], []
    schluessel = k["schluessel"]
    spalten.append(f'{schluessel["sql"]} AS {schluessel["name"]}')
    namen.append({"name": schluessel["name"], "typ": "zahl", "schluessel": True})

    for f in k["felder"]:
        if not f.get("ausgabe"):
            continue
        alias = f["key"].split(".")[-1]
        spalten.append(f'{f["sql"]} AS {alias}')
        namen.append({"name": alias, "label": f["label"], "typ": f["typ"]})

    gewaehlt = definition.get("kennzahlen") or []
    if not isinstance(gewaehlt, list):
        raise AbfrageFehler("„kennzahlen“ muss eine Liste sein.")
    for key in gewaehlt:
        m = katalog.kennzahl(kname, key)
        if not m:
            raise AbfrageFehler(f"Unbekannte Kennzahl „{key}“.")
        spalten.append(f'{m["sql"]} AS {key}')
        namen.append({"name": key, "label": m["label"], "typ": m["typ"],
                      "decimals": m.get("decimals")})

    # Kennzahlen, die nur gefiltert werden, müssen trotzdem berechnet sein –
    # sonst steht im äußeren WHERE ein Name, den es nicht gibt.
    def _sammle_keys(knoten, raus):
        if not isinstance(knoten, dict):
            return
        if "op" in knoten:
            for kind in (knoten.get("kinder") or []):
                _sammle_keys(kind, raus)
        elif knoten.get("key"):
            raus.add(knoten["key"])

    gefiltert = set()
    _sammle_keys(definition.get("kennzahlfilter") or {}, gefiltert)
    for key in sorted(gefiltert - set(gewaehlt)):
        m = katalog.kennzahl(kname, key)
        if not m:
            raise AbfrageFehler(f"Unbekannte Kennzahl „{key}“ im Kennzahlfilter.")
        spalten.append(f'{m["sql"]} AS {key}')
        namen.append({"name": key, "label": m["label"], "typ": m["typ"],
                      "decimals": m.get("decimals")})

    # ── Zeilenfilter (inneres WHERE) ──
    def _feld_aufloesen(key):
        f = katalog.feld(kname, key)
        if not f:
            raise AbfrageFehler(f"Unbekanntes Feld „{key}“.")
        return f["sql"], f["typ"]

    wo = _baum(definition.get("zeilenfilter") or {}, _feld_aufloesen, binde)

    # ── Kennzahlfilter (äußeres WHERE über den Aliasnamen) ──
    def _kennzahl_aufloesen(key):
        m = katalog.kennzahl(kname, key)
        if not m:
            raise AbfrageFehler(f"Unbekannte Kennzahl „{key}“.")
        return f"x.{key}", m["typ"]

    aussen = _baum(definition.get("kennzahlfilter") or {}, _kennzahl_aufloesen, binde)

    # ── Sortierung ──
    sort = definition.get("sortierung") or {}
    sort_key = sort.get("key")
    if sort_key:
        gueltig = {n["name"] for n in namen}
        if sort_key not in gueltig:
            raise AbfrageFehler(f"Nach „{sort_key}“ kann nicht sortiert werden.")
        richtung = "DESC" if str(sort.get("richtung", "desc")).lower() == "desc" else "ASC"
        order = f"ORDER BY x.{sort_key} {richtung}"
    else:
        order = f'ORDER BY x.{namen[1]["name"]} ASC' if len(namen) > 1 else ""

    try:
        limit = int(definition.get("limit") or 500)
    except (TypeError, ValueError):
        limit = 500
    limit = max(1, min(limit, MAX_LIMIT))

    innen = ",\n         ".join(spalten)
    sql = (f"SELECT TOP ({limit}) * FROM (\n"
           f"  SELECT {innen}\n"
           f"  {k['basis']}\n"
           + (f"  WHERE {wo}\n" if wo else "")
           + f") x\n"
           + (f"WHERE {aussen}\n" if aussen else "")
           + (order if order else "")).strip()

    return {"sql": sql, "params": binde.werte, "spalten": namen}

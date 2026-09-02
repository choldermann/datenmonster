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


MAX_TEXT = 400


class _Binder:
    """Setzt Werte ins SQL – gebunden (Vorschau) oder als Literal (gespeichert).

    Warum zwei Wege: Die Vorschau führt das SQL selbst aus und kann Parameter
    mitgeben. Ein **gespeichertes** Mapping wird später vom Report ausgeführt,
    der nur :von/:bis kennt – ein dort verbliebenes :p0 bliebe ungebunden und
    die Abfrage lieferte **stumm null Zeilen**. Genau das ist beim ersten
    Speichern passiert.

    Die Literalfassung ist deshalb sicher, weil sie nichts durchreicht: Zahlen
    laufen durch float(), Text wird auf Länge geprüft, von Steuerzeichen befreit
    und mit verdoppelten Hochkommata in N'…' gesetzt. Feld- und Vergleichsnamen
    stammen ohnehin aus dem serverseitigen Katalog.
    """

    def __init__(self, literal: bool = False):
        self.werte: dict = {}
        self.literal = literal
        self._n = 0

    def __call__(self, wert, typ: str = "text") -> str:
        if not self.literal:
            name = f"p{self._n}"
            self._n += 1
            self.werte[name] = wert
            return f":{name}"

        if typ in ("zahl", "geld", "ja_nein"):
            try:
                f = float(wert)
            except (TypeError, ValueError):
                raise AbfrageFehler(f"„{wert}“ ist keine Zahl.")
            return str(int(f)) if f == int(f) else repr(f)

        s = str(wert)
        if len(s) > MAX_TEXT:
            raise AbfrageFehler(f"Werte dürfen höchstens {MAX_TEXT} Zeichen haben.")
        # Steuerzeichen raus – sie haben in einem Filterwert nichts zu suchen und
        # könnten ein Statement optisch zerlegen.
        s = "".join(c for c in s if c == " " or c.isprintable())
        return "N'" + s.replace("'", "''") + "'"


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
        return f"({ausdruck} >= {binde(wert[0], typ)} AND {ausdruck} <= {binde(wert[1], typ)})"

    if vergleich == "in":
        werte = wert if isinstance(wert, (list, tuple)) else [wert]
        werte = [w for w in werte if w is not None and w != ""]
        if not werte:
            # Leere Auswahl heißt „keine Einschränkung“ – nicht „nichts trifft zu“.
            return "(1 = 1)"
        if len(werte) > MAX_LISTE:
            raise AbfrageFehler(f"Höchstens {MAX_LISTE} Werte je Auswahl.")
        platz = ", ".join(binde(w, typ) for w in werte)
        return f"({ausdruck} IN ({platz}))"

    if vergleich == "enthaelt":
        return f"({ausdruck} LIKE {binde('%' + str(wert) + '%', 'text')})"
    if vergleich == "beginnt":
        return f"({ausdruck} LIKE {binde(str(wert) + '%', 'text')})"

    if wert is None or wert == "":
        raise AbfrageFehler(f"Für den Vergleich „{vergleich}“ fehlt der Wert.")

    if typ == "ja_nein":
        wert = 1 if str(wert).lower() in ("1", "true", "ja", "y") else 0

    # NULL vergleicht sich in SQL mit nichts. Bei „ist nicht“ erwartet der
    # Anwender aber, dass leere Werte mitkommen – sonst verschwinden Zeilen,
    # ohne dass er es merkt.
    if vergleich == "<>":
        return f"({ausdruck} IS NULL OR {ausdruck} <> {binde(wert, typ)})"
    return f"({ausdruck} {vergleich} {binde(wert, typ)})"


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


def _gruppe_einsetzen(sql: str, gruppe: list, binde: _Binder) -> str:
    """Ersetzt den Platzhalter der Vergleichsgruppe durch gebundene Werte.

    Die IDs laufen durch denselben Binder wie jeder andere Wert – im
    Literalmodus also durch float(), womit nur Zahlen durchkommen.
    """
    if katalog.GRUPPE not in sql:
        return sql
    if not gruppe:
        raise AbfrageFehler("Für diese Kennzahl fehlt die Vergleichsgruppe.")
    platz = ", ".join(binde(g, "zahl") for g in gruppe)
    return sql.replace(katalog.GRUPPE, platz)


def bauen(definition: dict, literal: bool = False) -> dict:
    """Gibt {sql, params, spalten} zurück. Wirft AbfrageFehler bei Unsinn.

    literal=True für das gespeicherte Mapping: Filterwerte werden eingesetzt
    statt gebunden, weil der Report später nur :von/:bis mitgibt.
    """
    kname = definition.get("koernung") or "kunde"
    k = katalog.KOERNUNGEN.get(kname)
    if not k:
        raise AbfrageFehler(f"Unbekannte Körnung „{kname}“.")

    binde = _Binder(literal=literal)

    gruppe = [g for g in ((definition.get("vergleichsgruppe") or {}).get("kunden") or [])
              if str(g).strip() != ""]

    # Alles ausser „Kunde" folgt der Zeilen-Bauart (Liste bzw. GROUP BY).
    if kname != "kunde":
        return _zeilenkoernung(definition, k, kname, binde)

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
        spalten.append(f'{_gruppe_einsetzen(m["sql"], gruppe, binde)} AS {key}')
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
        spalten.append(f'{_gruppe_einsetzen(m["sql"], gruppe, binde)} AS {key}')
        namen.append({"name": key, "label": m["label"], "typ": m["typ"],
                      "decimals": m.get("decimals")})

    # ── Zeilenfilter (inneres WHERE) ──
    def _feld_aufloesen(key):
        f = katalog.feld(kname, key)
        if not f:
            raise AbfrageFehler(f"Unbekanntes Feld „{key}“.")
        return f["sql"], f["typ"]

    wo = _baum(definition.get("zeilenfilter") or {}, _feld_aufloesen, binde)

    # Die Vergleichsgruppe gehört nicht in ihre eigene Ergebnisliste.
    if gruppe and k.get("gruppe_ausschluss"):
        ausschluss = _gruppe_einsetzen(k["gruppe_ausschluss"], gruppe, binde)
        wo = f"{wo} AND {ausschluss}" if wo else ausschluss

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


def _zeilenkoernung(definition: dict, k: dict, kname: str, binde: _Binder) -> dict:
    """Die vier Zeilen-Körnungen: Liste, oder mit Gruppierung verdichtet.

    Beide Formen bauen auf derselben Zwischenebene auf – innen die Rohwerte je
    Zeile, außen bei Bedarf Gruppierung und Aggregate. Das ist notwendig, nicht
    nur ordentlich: MSSQL verbietet SUM(<Unterabfrage>), und der Auftrags- wie
    der Rechnungswert IST eine Unterabfrage.

    Anders als bei „Kunde" kann es hier keine Nullfälle geben. Ein GROUP BY über
    Rechnungen liefert für einen Kunden ohne Rechnung nie eine Zeile — deshalb
    beantwortet nur die Kundenkörnung Fragen der Form „… = 0".
    """
    def _feld_aufloesen(key):
        f = katalog.feld(kname, key)
        if not f:
            raise AbfrageFehler(f"Unbekanntes Feld „{key}“.")
        return f["sql"], f["typ"]

    wo = _baum(definition.get("zeilenfilter") or {}, _feld_aufloesen, binde)
    bedingungen = " AND ".join(t for t in (k.get("grundfilter"), wo) if t)

    # Die Zwischenebene trägt Schlüssel und ALLE Felder – auch die, die nicht
    # ausgegeben werden: Gruppierungen und Kennzahlen rechnen mit ihren Aliasen.
    schluessel = k["schluessel"]
    innen_spalten = [f'{schluessel["sql"]} AS {schluessel["name"]}']
    for f in k["felder"]:
        innen_spalten.append(f'{f["sql"]} AS {f["key"].replace(".", "_")}')
    innen = ",\n         ".join(innen_spalten)
    basis = (f"  SELECT {innen}\n  {k['basis']}\n"
             + (f"  WHERE {bedingungen}\n" if bedingungen else ""))

    gkey = definition.get("gruppierung") or ""
    g = katalog.gruppierung(kname, gkey) if gkey else None
    if gkey and not g:
        raise AbfrageFehler(f"Unbekannte Gruppierung „{gkey}“.")

    try:
        limit = int(definition.get("limit") or 500)
    except (TypeError, ValueError):
        limit = 500
    limit = max(1, min(limit, MAX_LIMIT))

    if not g:
        if (definition.get("kennzahlfilter") or {}).get("kinder"):
            raise AbfrageFehler("Bedingungen an Kennzahlen brauchen eine Gruppierung – "
                                "ohne sie gibt es keine verdichteten Zahlen.")
        namen = [{"name": schluessel["name"], "typ": "zahl", "schluessel": True}]
        aussen = [f'x.{schluessel["name"]}']
        for f in k["felder"]:
            if not f.get("ausgabe"):
                continue
            alias = f["key"].replace(".", "_")
            aussen.append(f"x.{alias}")
            namen.append({"name": alias, "label": f["label"], "typ": f["typ"]})
        gruppen_sql = having = ""
    else:
        namen, aussen, gruppen_ausdruecke = [], [], []
        for ausdruck, alias in g["sql"]:
            aussen.append(f"{ausdruck} AS {alias}")
            namen.append({"name": alias, "label": alias, "typ": "text"})
            # Ein bereits aggregierter Ausdruck (MAX(…)) darf nicht ins GROUP BY.
            if not ausdruck.upper().lstrip().startswith(("MAX(", "MIN(", "SUM(", "COUNT(")):
                gruppen_ausdruecke.append(ausdruck)
        gruppen_sql = ", ".join(gruppen_ausdruecke)

        gewaehlt = list(definition.get("kennzahlen") or [])
        gefiltert = set()
        _sammle(definition.get("kennzahlfilter") or {}, gefiltert)
        if not gewaehlt and not gefiltert:
            raise AbfrageFehler("Bitte mindestens eine Kennzahl wählen.")
        for key in gewaehlt + sorted(gefiltert - set(gewaehlt)):
            m = katalog.kennzahl(kname, key)
            if not m:
                raise AbfrageFehler(f"Unbekannte Kennzahl „{key}“.")
            aussen.append(f'{m["sql"]} AS {key}')
            namen.append({"name": key, "label": m["label"], "typ": m["typ"],
                          "decimals": m.get("decimals")})

        def _kennzahl_aufloesen(key):
            m = katalog.kennzahl(kname, key)
            if not m:
                raise AbfrageFehler(f"Unbekannte Kennzahl „{key}“.")
            # HAVING rechnet mit dem Ausdruck, nicht mit dem Alias.
            return m["sql"], m["typ"]

        having = _baum(definition.get("kennzahlfilter") or {}, _kennzahl_aufloesen, binde)

    sort = definition.get("sortierung") or {}
    sort_key = sort.get("key")
    if sort_key and sort_key not in {n["name"] for n in namen}:
        sort_key = None
    if not sort_key:
        sort_key = namen[-1]["name"] if g else (namen[1]["name"] if len(namen) > 1 else None)
    richtung = "DESC" if str(sort.get("richtung", "desc")).lower() == "desc" else "ASC"
    order = f"ORDER BY {sort_key} {richtung}" if sort_key else ""

    sql = (f"SELECT TOP ({limit}) " + ",\n       ".join(aussen) + "\n"
           + f"FROM (\n{basis}) x\n"
           + (f"GROUP BY {gruppen_sql}\n" if gruppen_sql else "")
           + (f"HAVING {having}\n" if having else "")
           + order).strip()

    return {"sql": sql, "params": binde.werte, "spalten": namen}


def _sammle(knoten, raus):
    if not isinstance(knoten, dict):
        return
    if "op" in knoten:
        for kind in (knoten.get("kinder") or []):
            _sammle(kind, raus)
    elif knoten.get("key"):
        raus.add(knoten["key"])

# -*- coding: utf-8 -*-
"""Schema-Erkundung — Stufe A: messen statt raten.

Die Wissensdatenbank ist nur so gut wie ihre Belege. Jede Regel, die in dieser
Anwendung wirklich etwas gebracht hat, kam aus einer Zählabfrage: „572 von 572
kundenindividuellen Preisen haben kKundenGruppe = 0", „alle 28.039
tLieferschein.kBestellung treffen einen kAuftrag", „495 von 502 aktiven
Sonderpreisen haben gar keine Preiszeile". Ein Sprachmodell, das nur
Spaltennamen liest, erzeugt dagegen Sätze, die plausibel klingen und falsch
sind — genau die Sorte Wissen, die später falsches SQL erzeugt.

Dieses Modul stellt deshalb ausschließlich Messwerte her. Kein LLM, keine
Vermutung. Was daraus an Regeln formuliert wird, entscheidet Stufe B
(schema_erkundung_wissen) — und die darf keine Zahl erfinden, die hier nicht
gemessen wurde.

Schemaübergreifend: die untersuchten Objekte kommen aus der Auswahl, die
Zielkandidaten einer Beziehung IMMER aus der ganzen Datenbank. Genau dort
liegen die interessanten Fälle — Versand.lvLieferschein zeigt auf
dbo.tLieferschein, nicht auf etwas im eigenen Schema.

Views werden mitgemessen. Der Schema-Cache kennt nur sys.tables; die 1.109
Views einer JTL-Wawi (Preisliste.vPreislisteNetto, Rechnung.vRechnung, die 19
Versand.lv*) fehlen dort vollständig, obwohl JTLs eigene Auswertungen fast nur
darauf laufen.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from sqlalchemy import text

log = logging.getLogger(__name__)

# Wie viele Zeilen eine Stichprobe höchstens prüft. Eine Trefferquote auf 5.000
# Zeilen ist für die Aussage „gehört zusammen / gehört nicht zusammen" genau
# genug und hält den Lauf auf großen Belegtabellen im Sekundenbereich.
STICHPROBE = 5000

# Ab wie vielen verschiedenen Werten eine Spalte kein Status mehr ist, sondern
# Nutzdaten. Bei JTL liegen die Statusspalten (nType, nStorno, cAktiv) alle
# darunter.
STATUS_GRENZE = 12

# Schemata, die keine Fachdaten führen — sie zu vermessen kostet Zeit und
# liefert Regeln, die niemand braucht (siehe reference_jtl_schnittstellen_schemata).
UNINTERESSANT = {"dbes", "deprecated", "sync", "worker", "maintenance", "logging",
                 "blockly", "hwcfg", "pparams", "restapi", "odata", "subset"}


@dataclass
class Befund:
    art: str                    # leer | beziehung | statuswerte | zeitraum | ohne_treffer
    objekt: str                 # "Versand.lvLieferschein"
    titel: str
    beleg: str                  # der gemessene Satz, wörtlich zitierbar
    zahlen: dict = field(default_factory=dict)
    gewicht: int = 1            # wie berichtenswert (3 = hoch)


# Wo ein Schlüssel bei Gleichstand am ehesten hingehört. Ohne diese Reihung
# gewinnt der Zufall: kFirma traf DbeS.vFirma statt dbo.tfirma, kBestellung
# Auslieferung.vBestellung statt dbo.tBestellung.
_SCHEMA_RANG = {"dbo": 3, "verkauf": 3, "rechnung": 3, "einkauf": 3, "versand": 3,
                "lager": 3, "artikel": 3, "kunde": 3, "bestand": 3, "preisliste": 3,
                "statistik": 2, "beschaffung": 2, "auslieferung": 2, "rm": 2}


def _alle_objekte(con) -> dict[str, bool]:
    """Jedes Objekt der Datenbank → ist es ein View?"""
    return {f"{s}.{n}": (typ == "VIEW") for s, n, typ in con.execute(text(
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"))}


def _zielrang(spalte: str, ziel: str, ist_view: bool) -> tuple:
    """Reihung der Zielkandidaten: Namensnähe, dann Fachschema, dann Tabelle vor View."""
    schema = ziel.split(".")[0].lower()
    rang = 0 if schema in UNINTERESSANT else _SCHEMA_RANG.get(schema, 1)
    return (_namensnaehe(spalte, ziel), rang, 0 if ist_view else 1)


def _objekte(con, schemas: Optional[list[str]], nur: Optional[list[str]]) -> list[dict]:
    """Die zu untersuchenden Objekte — Tabellen UND Views."""
    rows = con.execute(text(
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES"
    )).fetchall()
    aus = []
    nur_set = {n.lower() for n in (nur or [])}
    schema_set = {s.lower() for s in (schemas or [])}
    for s, n, typ in rows:
        voll = f"{s}.{n}"
        if nur_set:
            if voll.lower() not in nur_set:
                continue
        elif schema_set:
            if s.lower() not in schema_set:
                continue
        elif s.lower() in UNINTERESSANT:
            continue
        aus.append({"schema": s, "name": n, "full_name": voll,
                    "ist_view": typ == "VIEW"})
    return sorted(aus, key=lambda o: o["full_name"])


def _spalten(con) -> dict[str, list[tuple[str, str]]]:
    spalten: dict[str, list[tuple[str, str]]] = {}
    for s, n, c, t in con.execute(text(
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
        "FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
    )):
        spalten.setdefault(f"{s}.{n}", []).append((c, (t or "").lower()))
    return spalten


def _pk_besitzer(con) -> dict[str, list[str]]:
    """Schlüsselname → Tabellen, in denen er Primärschlüssel ist."""
    ziele: dict[str, list[str]] = {}
    for s, t, c in con.execute(text("""
        SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
          ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
         AND tc.TABLE_SCHEMA   = ku.TABLE_SCHEMA
        WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
    """)):
        ziele.setdefault(c.lower(), []).append(f"{s}.{t}")
    return ziele


def _namensziele(alle_spalten: dict[str, list[tuple[str, str]]]) -> dict[str, list[str]]:
    """Schlüsselname → Objekte, die so heißen UND die Spalte führen.

    Der Primärschlüssel-Index allein reicht nicht: `kBestellung` gehört zu
    `dbo.tBestellung`, und das ist ein VIEW — Views haben keine
    PK-Constraints. Ohne diesen zweiten Index landet die Suche stattdessen bei
    `dbo.tBestellungPicklisteLock`, einer Sperrtabelle, und meldet dann
    fälschlich „zeigt ins Leere". Genau so heißt in dieser Wawi der Auftrag in
    den Versand- und Lieferschein-Objekten noch: mit seinem Altnamen.
    """
    treffer: dict[str, list[str]] = {}
    for voll, spalten in alle_spalten.items():
        name = voll.split(".")[-1].lower()
        for praefix in ("lv", "v", "t"):
            if name.startswith(praefix):
                kern = name[len(praefix):]
                break
        else:
            kern = name
        if not kern:
            continue
        schluessel = "k" + kern
        if any(sp.lower() == schluessel for sp, _ in spalten):
            treffer.setdefault(schluessel, []).append(voll)
    return treffer


def _namensnaehe(spalte: str, tabelle: str) -> int:
    """Wie gut passt der Schlüsselname zum Tabellennamen? kArtikel → tArtikel = 2.

    Ein Schlüsselname ist in der JTL-DB oft nicht eindeutig — kArtikel ist in
    sechs Tabellen Primärschlüssel. Ohne diese Reihung misst man zuerst
    Artikel.tArtikelMehrzweckGutschein und nie dbo.tArtikel.
    """
    kern = spalte.lower().lstrip("k")
    name = tabelle.split(".")[-1].lower()
    rumpf = name[1:] if name[:1] in "tv" else name
    if rumpf == kern:
        return 2
    if rumpf.startswith(kern) or kern.startswith(rumpf):
        return 1
    return 0


def _zaehle(con, voll: str) -> int:
    s, n = voll.split(".", 1)
    return con.execute(text(f"SELECT COUNT(*) FROM [{s}].[{n}]")).scalar() or 0


def _trefferquote(con, kind: str, kind_col: str, eltern: str, eltern_col: str) -> Optional[dict]:
    """Wie viele Kindzeilen finden einen Elternsatz?

    OUTER APPLY statt JOIN: ein JOIN zählt Treffer-PAARE und liefert bei einem
    Eltern-Datensatz mit mehreren Kindern über 100 % — im ersten Prototyp kamen
    so 325.433 % heraus. Gefragt ist aber, wie viele der geprüften Kindzeilen
    überhaupt einen Partner haben.
    """
    ks, kn = kind.split(".", 1)
    es, en = eltern.split(".", 1)
    sql = (
        f"SELECT COUNT(*) AS geprueft, COUNT(T.treffer) AS treffer FROM ("
        f"  SELECT TOP {STICHPROBE} [{kind_col}] AS wert FROM [{ks}].[{kn}] "
        f"  WHERE [{kind_col}] IS NOT NULL"
        f") S OUTER APPLY ("
        f"  SELECT TOP 1 1 AS treffer FROM [{es}].[{en}] P WHERE P.[{eltern_col}] = S.wert"
        f") T"
    )
    try:
        r = con.execute(text(sql)).fetchone()
    except Exception as e:
        log.debug("Trefferquote %s.%s → %s: %s", kind, kind_col, eltern, e)
        return None
    geprueft, treffer = int(r[0] or 0), int(r[1] or 0)
    if geprueft == 0:
        return None
    return {"geprueft": geprueft, "treffer": treffer,
            "quote": round(100.0 * treffer / geprueft, 1)}


def _statuswerte(con, voll: str, spalte: str) -> Optional[list[tuple[Any, int]]]:
    s, n = voll.split(".", 1)
    try:
        anzahl = con.execute(text(
            f"SELECT COUNT(DISTINCT [{spalte}]) FROM [{s}].[{n}]")).scalar()
    except Exception:
        return None
    if not anzahl or anzahl > STATUS_GRENZE:
        return None
    try:
        rows = con.execute(text(
            f"SELECT TOP {STATUS_GRENZE} [{spalte}], COUNT(*) FROM [{s}].[{n}] "
            f"GROUP BY [{spalte}] ORDER BY COUNT(*) DESC")).fetchall()
    except Exception:
        return None
    return [(r[0], int(r[1])) for r in rows]


def _zeitraum(con, voll: str, spalte: str) -> Optional[dict]:
    s, n = voll.split(".", 1)
    try:
        r = con.execute(text(
            f"SELECT MIN([{spalte}]), MAX([{spalte}]), COUNT([{spalte}]), "
            f"       SUM(CASE WHEN [{spalte}] < DATEADD(year, -3, GETDATE()) THEN 1 ELSE 0 END) "
            f"FROM [{s}].[{n}]")).fetchone()
    except Exception:
        return None
    if not r or not r[0]:
        return None
    return {"von": str(r[0])[:10], "bis": str(r[1])[:10],
            "gefuellt": int(r[2] or 0), "aelter_3j": int(r[3] or 0)}


# ── Der Lauf ──────────────────────────────────────────────────────────────────

def erkunde(
    conn_id: int,
    schemas: Optional[list[str]] = None,
    tabellen: Optional[list[str]] = None,
    max_objekte: int = 60,
    fortschritt=None,
) -> dict:
    """Misst die gewählten Objekte und gibt Befunde zurück.

    `schemas` grenzt ein, WO gesucht wird — die Ziele einer Beziehung kommen
    immer aus der ganzen Datenbank. `fortschritt` ist ein Callback(text, i, n)
    für die Anzeige; der Lauf dauert je nach Umfang Minuten.
    """
    from app.services.mapping_service import _get_sql_engine

    start = time.time()
    engine = _get_sql_engine(conn_id)
    befunde: list[Befund] = []
    beziehungen: list[dict] = []
    objekt_info: list[dict] = []

    with engine.connect() as con:
        try:
            con.connection.timeout = 120
        except Exception:
            pass

        objekte = _objekte(con, schemas, tabellen)
        if len(objekte) > max_objekte:
            objekte = objekte[:max_objekte]
        alle_spalten = _spalten(con)
        ziele = _pk_besitzer(con)
        namensziele = _namensziele(alle_spalten)
        objekt_typ = _alle_objekte(con)

        for i, obj in enumerate(objekte):
            voll = obj["full_name"]
            if fortschritt:
                fortschritt(voll, i, len(objekte))

            try:
                n = _zaehle(con, voll)
            except Exception as e:
                objekt_info.append({**obj, "zeilen": None, "fehler": str(e)[:200]})
                continue
            objekt_info.append({**obj, "zeilen": n})

            if n == 0:
                befunde.append(Befund(
                    art="leer", objekt=voll,
                    titel=f"{voll} ist leer",
                    beleg=f"{voll} enthält 0 Zeilen. Ein Join auf dieses Objekt läuft "
                          f"fehlerfrei durch und liefert nichts.",
                    zahlen={"zeilen": 0}, gewicht=3))
                continue

            spalten = alle_spalten.get(voll, [])

            # ── Beziehungen ────────────────────────────────────────────────
            for sp, typ in spalten:
                if not sp.lower().startswith("k") or typ not in ("int", "bigint", "smallint"):
                    continue
                # Zwei Quellen: Objekte, die so heißen wie der Schlüssel (auch
                # Views), und Tabellen, in denen er Primärschlüssel ist.
                kandidaten = list(dict.fromkeys(
                    [z for z in namensziele.get(sp.lower(), []) if z != voll]
                    + [z for z in ziele.get(sp.lower(), []) if z != voll]))
                if not kandidaten:
                    continue
                # Nach Namensnähe reihen und nur die besten prüfen: eine Messung
                # je Kandidat kostet eine Abfrage, und der richtige Treffer steht
                # fast immer vorn.
                kandidaten.sort(key=lambda z: _zielrang(sp, z, objekt_typ.get(z, False)),
                                reverse=True)
                bester = None
                for ziel in kandidaten[:3]:
                    q = _trefferquote(con, voll, sp, ziel, sp)
                    if not q:
                        continue
                    eintrag = {"von": voll, "von_spalte": sp, "nach": ziel,
                               "nach_spalte": sp, **q,
                               "namensnaehe": _namensnaehe(sp, ziel)}
                    beziehungen.append(eintrag)
                    if bester is None or q["quote"] > bester["quote"]:
                        bester = eintrag
                if not bester:
                    continue
                if bester["quote"] >= 99:
                    befunde.append(Befund(
                        art="beziehung", objekt=voll,
                        titel=f"{voll}.{sp} → {bester['nach']}",
                        beleg=f"{bester['treffer']} von {bester['geprueft']} geprüften Zeilen "
                              f"({bester['quote']} %) finden einen Satz in {bester['nach']}. "
                              f"Der Join {voll}.{sp} = {bester['nach']}.{sp} ist belegt.",
                        zahlen=bester, gewicht=2))
                elif bester["quote"] < 5 and bester["namensnaehe"] >= 1:
                    befunde.append(Befund(
                        art="ohne_treffer", objekt=voll,
                        titel=f"{voll}.{sp} zeigt ins Leere",
                        beleg=f"Nur {bester['treffer']} von {bester['geprueft']} geprüften Zeilen "
                              f"({bester['quote']} %) finden einen Satz in {bester['nach']}. "
                              f"Dieser Join sieht richtig aus, liefert aber praktisch nichts.",
                        zahlen=bester, gewicht=3))
                elif bester["quote"] < 5:
                    # Kein Ziel gefunden, das den Namen trägt — das ist ein
                    # Befund über die eigene Suche, nicht über die Daten.
                    continue
                else:
                    befunde.append(Befund(
                        art="beziehung", objekt=voll,
                        titel=f"{voll}.{sp} → {bester['nach']} (lückenhaft)",
                        beleg=f"{bester['quote']} % der geprüften Zeilen finden einen Satz in "
                              f"{bester['nach']}; {bester['geprueft'] - bester['treffer']} von "
                              f"{bester['geprueft']} nicht. Ein INNER JOIN verliert diese Zeilen.",
                        zahlen=bester, gewicht=2))

            # ── Statusspalten ──────────────────────────────────────────────
            for sp, typ in spalten:
                kurz = sp.lower()
                if not (kurz.startswith("n") or kurz.startswith("c")):
                    continue
                if typ not in ("int", "smallint", "tinyint", "bit", "char", "nchar"):
                    continue
                werte = _statuswerte(con, voll, sp)
                if not werte or len(werte) < 2:
                    continue
                liste = ", ".join(f"{v!r}: {c}" for v, c in werte)
                befunde.append(Befund(
                    art="statuswerte", objekt=voll,
                    titel=f"{voll}.{sp}: {len(werte)} verschiedene Werte",
                    beleg=f"In {voll}.{sp} kommen tatsächlich vor — {liste}. "
                          f"Andere Werte gibt es in diesen Daten nicht.",
                    zahlen={"werte": [[str(v), c] for v, c in werte]}, gewicht=2))

            # ── Zeiträume ──────────────────────────────────────────────────
            for sp, typ in spalten:
                if typ not in ("datetime", "datetime2", "date", "smalldatetime"):
                    continue
                z = _zeitraum(con, voll, sp)
                if not z or z["gefuellt"] == 0:
                    continue
                anteil_alt = round(100.0 * z["aelter_3j"] / z["gefuellt"], 1)
                gewicht = 3 if anteil_alt > 50 else 1
                befunde.append(Befund(
                    art="zeitraum", objekt=voll,
                    titel=f"{voll}.{sp}: {z['von']} bis {z['bis']}",
                    beleg=f"{voll}.{sp} reicht von {z['von']} bis {z['bis']}; "
                          f"{z['aelter_3j']} von {z['gefuellt']} Zeilen ({anteil_alt} %) sind "
                          f"älter als drei Jahre."
                          + (" Eine Abfrage ohne Zeitgrenze besteht hier überwiegend aus Altbestand."
                             if anteil_alt > 50 else ""),
                    zahlen={**z, "anteil_alt": anteil_alt}, gewicht=gewicht))

    dauer = round(time.time() - start, 1)
    befunde.sort(key=lambda b: (-b.gewicht, b.objekt))
    return {
        "objekte": objekt_info,
        "befunde": [asdict(b) for b in befunde],
        "beziehungen": beziehungen,
        "dauer_sek": dauer,
        "geprueft": len(objekt_info),
    }


# ── Stufe B: aus Messwerten werden Wissenseinträge ────────────────────────────

_WISSEN_SYSTEM = (
    "Du formulierst Regeln für eine Wissensdatenbank, die einem SQL-schreibenden "
    "Modell vorgelegt wird. Du bekommst ausschließlich MESSWERTE aus der echten "
    "Datenbank. Deine Aufgabe ist, sie zu VERDICHTEN — nicht nachzuerzählen.\n\n"
    "Eiserne Regeln:\n"
    "1. Erfinde nichts. Jeder Tabellen- und Spaltenname und jede Zahl muss in den "
    "Messwerten stehen.\n"
    "2. RECHNE NICHT. Übernimm Zahlen unverändert aus der Messung, zu der sie "
    "gehören. Zahlen aus verschiedenen Messungen gehören nie in einen Satz.\n"
    "3. Nenne unter \"objekt\" das Objekt, dessen Messwerte du verwendest "
    "(z. B. \"Versand.lvAuftrag\"). Nur dessen Zahlen darfst du nennen. Fasst ein "
    "Eintrag mehrere Objekte zusammen, lass \"objekt\" leer.\n"
    "4. Höchstens 700 Zeichen je Eintrag. Wiederhole nicht denselben Satzbau; "
    "gleichartige Messungen kommen in EINE Aufzählung.\n"
    "5. Der Titel ist ein kurzer Name, kein Satz: \"Bereich – Aussage\", ohne Punkt. "
    "Jeder Titel kommt nur EINMAL vor — nenne das Objekt darin, wenn sich sonst "
    "zwei Einträge gleich nennen würden.\n"
    "6. Schreib die Konsequenz fürs SQL dazu, nicht die Messung an sich.\n"
    "7. Deutsch, sachlich, keine Einleitung.\n\n"
    "So sieht ein guter Eintrag aus:\n"
    '{"kategorie":"table","objekt":"Versand.lvLieferschein",'
    '"titel":"Versand – lvLieferschein: belegte Joins",'
    '"inhalt":"Versand.lvLieferschein hängt an dbo.tLieferschein (kLieferschein), '
    'dbo.tkunde (kKunde), dbo.tfirma (kFirma) und dbo.tversandart (kVersandart) — '
    'je 100 % von 5.000 geprüften Zeilen. Diese Joins sind gemessen und können '
    'ohne Prüfung verwendet werden."}\n\n'
    "So NICHT (Nacherzählung statt Regel):\n"
    '{"inhalt":"5000 von 5000 geprüften Zeilen (100.0 %) finden einen Satz in '
    'dbo.tLieferschein. Der Join … ist belegt. 5000 von 5000 geprüften Zeilen …"}\n\n'
    'Antworte NUR mit JSON: {"eintraege":[{"kategorie":"table|field_mapping|rule",'
    '"objekt":"Schema.Objekt oder leer","titel":"…","inhalt":"…"}]}'
)


def _zahlen(text_: str) -> set[str]:
    """Alle Zahlen eines Textes, vergleichbar gemacht.

    „5.000" (Tausenderpunkt) und „100.0" (Dezimalpunkt) sehen gleich aus und
    müssen verschieden behandelt werden — ein pauschales Entfernen aller Punkte
    machte aus „100.0 %" die Zahl 1000 und meldete deshalb jedes ehrliche
    „100 %" als ungedeckt. Zu jeder Zahl kommt zusätzlich ihr Ganzzahlanteil in
    die Menge, damit „100" und „100.0" zusammenfinden.
    """
    import re
    aus: set[str] = set()
    for roh in re.findall(r"\d[\d.,]*\d|\d", text_ or ""):
        wert = re.sub(r"\.(?=\d{3}\b)", "", roh).replace(",", ".")
        aus.add(wert)
        aus.add(wert.split(".")[0])
    return aus


def pruefe_deckung(inhalt: str, befunde: list[dict], objekt: str = "") -> list[str]:
    """Zahlen im Entwurf, die zu diesem Objekt nicht gemessen wurden.

    Der Sinn der ganzen Übung: ein Sprachmodell, das Zahlen erfindet, richtet
    mehr Schaden an als gar kein Wissen. Ein globaler Abgleich reicht dafür
    nicht — im Test übernahm das Modell „1217 von 5000" aus der Messung eines
    ANDEREN Objekts in einen Satz über dbo.tArtikel. Die Zahl stand in den
    Belegen und wäre durchgegangen. Geprüft wird deshalb nur gegen die
    Messwerte des Objekts, auf das sich der Eintrag beruft.
    """
    passend = [b for b in befunde
               if (objekt and b.get("objekt") == objekt)
               or (b.get("objekt") and b["objekt"] in inhalt)]
    if not passend:
        passend = befunde
    bekannt = _zahlen("\n".join(b.get("beleg", "") for b in passend))
    # Jahreszahlen und Kleinstzahlen sind Beiwerk (Prozentangaben, Aufzählungen)
    return sorted(z for z in _zahlen(inhalt)
                  if z not in bekannt and len(z) > 2 and not z.startswith("20"))


def _eintraege_lesen(roh: str) -> Optional[list[dict]]:
    """Die Einträge aus der Antwort holen — auch wenn ein einzelner kaputt ist.

    Ein Modell, das zwölf Regeln am Stück schreibt, verhaut irgendwann ein
    Anführungszeichen. Das gesamte Ergebnis deswegen wegzuwerfen wäre die
    schlechteste Antwort; die übrigen elf Regeln sind in Ordnung.
    """
    import json as _json
    import re as _re

    text_ = _re.sub(r"^```[a-zA-Z]*\s*|```\s*$", "", (roh or "").strip(),
                    flags=_re.MULTILINE).strip()
    anfang, ende = text_.find("{"), text_.rfind("}")
    if anfang < 0 or ende < 0:
        return None
    try:
        return _json.loads(text_[anfang:ende + 1]).get("eintraege", [])
    except Exception:
        pass
    # Notlese: jedes einzelne Objekt für sich versuchen
    gefunden = []
    for stueck in _re.findall(r"\{[^{}]*\}", text_):
        try:
            obj = _json.loads(stueck)
        except Exception:
            continue
        if "titel" in obj and "inhalt" in obj:
            gefunden.append(obj)
    return gefunden or None


async def wissen_entwerfen(db, befunde: list[dict], svc, hoechstens: int = 12) -> list[dict]:
    """Macht aus Befunden Wissensentwürfe. Speichert nichts."""
    import json as _json
    from app.models.ai_memory import AiMemoryKnowledge

    if not befunde:
        return []

    vorhandene_titel = {
        (t or "").lower()
        for (t,) in db.query(AiMemoryKnowledge.title).all()
    }

    belege = "\n".join(f"- {b['beleg']}" for b in befunde)
    prompt = (
        "Messwerte aus der Datenbank:\n" + belege +
        f"\n\nFasse daraus höchstens {hoechstens} Regeln. Zusammenfassen:\n"
        "- ALLE leeren Objekte in EINEN Eintrag (objekt bleibt leer)\n"
        "- die belegten Joins EINES Objekts in EINEN Eintrag\n"
        "- die Statuswerte EINES Objekts in EINEN Eintrag, mit den tatsächlich "
        "vorkommenden Werten — daran scheitern Modelle sonst, weil sie sich eine "
        "Legende ausdenken\n"
        "- Zeitspannen nur, wenn der Altbestand überwiegt (dann ist die Zeitgrenze "
        "in der Abfrage Pflicht)\n"
        "Übergehe, was für das Schreiben von Abfragen bedeutungslos ist."
    )
    roh = await svc.complete_with_context(prompt, _WISSEN_SYSTEM)

    eintraege = _eintraege_lesen(roh)
    if eintraege is None:
        raise ValueError("Die KI hat kein lesbares JSON zurückgegeben")

    entwuerfe = []
    vergeben: set[str] = set()
    for e in eintraege:
        titel = (e.get("titel") or "").strip()
        inhalt = (e.get("inhalt") or "").strip()
        if not titel or not inhalt:
            continue
        # Der Titel ist beim Speichern der Schlüssel (Upsert nach Titel). Das
        # Modell vergibt trotz Anweisung gern sechsmal „Versand – belegte Joins";
        # ohne diese Ergänzung überschreiben sich die Einträge gegenseitig.
        objekt = (e.get("objekt") or "").strip()
        if titel.lower() in vergeben and objekt:
            titel = f"{titel}: {objekt.split('.')[-1]}"
        vergeben.add(titel.lower())
        entwuerfe.append({
            "kategorie": e.get("kategorie") if e.get("kategorie") in
                         ("table", "field_mapping", "rule", "format", "other") else "rule",
            "objekt": objekt,
            "titel": titel,
            "inhalt": inhalt,
            "zeichen": len(titel) + len(inhalt),
            # Warnungen, die der Benutzer sehen muss, bevor er übernimmt
            "ungedeckte_zahlen": pruefe_deckung(inhalt, befunde, objekt),
            "titel_existiert": titel.lower() in vorhandene_titel,
            "zu_lang": len(titel) + len(inhalt) > 800,
        })
    return entwuerfe

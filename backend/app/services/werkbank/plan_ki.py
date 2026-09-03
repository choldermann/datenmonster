"""Aus einem Satz einen Bauzettel machen – in Stufen, nicht in einem Zug.

**Warum mehrstufig:** Ein kleines Modell trifft Struktur und Inhalt nicht
gleichzeitig. Dieselbe Erfahrung steckt schon im Baumodus des Mapping-Editors:
Stufe 1 beschreibt nur den Bauplan, Stufe 2 füllt ihn mit vollem Fachkontext.

**Warum der Wortlaut immer mitreist:** Stufe 1 formuliert den Wunsch um und kann
ihn dabei verfälschen – aus „dieses Jahr" wurde dort schon „das Jahr 2023". Der
Originalsatz steht deshalb in jedem Folgeprompt und hat bei Widerspruch Vorrang.

**Warum die Ausgabe flach ist:** Der Filterbaum des Abfrage-Generators ist
verschachtelt (Gruppen aus Gruppen). Ein Modell trifft das unzuverlässig, und
ein halb gebauter Baum wäre nicht prüfbar. Das Modell liefert deshalb eine
flache Bedingungsliste plus eine Verknüpfung; den Baum baut dieses Modul.

**Jeder Schlüssel wird gegen den Katalog geprüft.** Was das Modell erfindet,
kommt nicht durch – es wird zur Rückfrage an den Anwender, nicht zu SQL.
"""
import json
import logging
from datetime import date

from app.services import sql_werkstatt
from app.services.query_builder import katalog

from . import werkzeuge

logger = logging.getLogger(__name__)


class PlanFehler(RuntimeError):
    """Der Planer konnte keinen brauchbaren Bauzettel erzeugen."""


def _heute_satz() -> str:
    h = date.today()
    return (f"Heutiges Datum: {h.strftime('%d.%m.%Y')} – „dieses Jahr“ ist {h.year}, "
            f"„letztes Jahr“ ist {h.year - 1}.")


def _streng(schema: dict) -> dict:
    """Macht ein Schema für OpenAIs strict-Modus zulässig.

    Der Datenmonster-Gateway reicht das Schema an `response_format` weiter, und
    dort gilt: jedes Objekt braucht `additionalProperties: false`, und `required`
    muss **alle** Eigenschaften aufzählen. Ein Schema ohne das wird mit HTTP 400
    abgewiesen – der Aufruf fällt dann auf Freitext zurück, und das Modell
    erfindet eine eigene Form. Genau daran sind die ersten Bauzettel gescheitert.

    Ollama stört das nicht; es liest dasselbe Schema unverändert.
    """
    if not isinstance(schema, dict):
        return schema
    s = dict(schema)
    if s.get("type") == "object":
        eigenschaften = {k: _streng(v) for k, v in (s.get("properties") or {}).items()}
        s["properties"] = eigenschaften
        s["required"] = list(eigenschaften)
        s["additionalProperties"] = False
    elif s.get("type") == "array" and isinstance(s.get("items"), dict):
        s["items"] = _streng(s["items"])
    return s


async def _json(svc, system: str, auftrag: str, schema: dict) -> dict:
    """Ein strukturierter Aufruf. Fällt auf Textparsen zurück, wenn nötig."""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": auftrag}]
    try:
        return await svc.complete_json(messages, _streng(schema))
    except Exception as e:
        logger.warning("Strukturierte Ausgabe fehlgeschlagen (%s), versuche Freitext", e)
        roh = await svc.complete_with_context(auftrag, system)
        start, ende = roh.find("{"), roh.rfind("}")
        if start == -1 or ende == -1:
            raise PlanFehler("Die KI hat keinen verwertbaren Bauplan geliefert.")
        try:
            return json.loads(roh[start:ende + 1])
        except Exception:
            raise PlanFehler("Die KI hat keinen verwertbaren Bauplan geliefert.")


# ─────────────────────────────────────────────────────────────────────────────
# Formtoleranz
#
# Auch mit gehärtetem Schema kann ein Aufruf auf Freitext zurückfallen (anderer
# Anbieter, Zeitüberschreitung, Gatewayfehler). Dann liefert das Modell dieselbe
# Aussage in einer anderen Form: „werkzeuge": ["abfrage"] statt „schritte", oder
# {"lieferscheine": "> 0"} statt {key, vergleich, wert}. Das ist kein Fehler des
# Modells, sondern eine andere Schreibweise – wir lesen sie, statt sie zu
# verwerfen und stumm einen halben Bauplan zu bauen.
# ─────────────────────────────────────────────────────────────────────────────

_VERGLEICH_TEXT = {"==": "=", "!=": "<>", "=": "=", "<>": "<>",
                   ">": ">", "<": "<", ">=": ">=", "<=": "<="}


def _ausdruck_teilen(text) -> tuple:
    """„> 0“ → („>“, „0“). Gibt (text, None) zurück, wenn kein Operator vorn steht."""
    t = str(text or "").strip()
    for op in (">=", "<=", "<>", "!=", "==", ">", "<", "="):
        if t.startswith(op):
            return op, t[len(op):].strip()
    return t, None


def _schritte_lesen(roh: dict) -> tuple:
    """Stufe-1-Antwort in (name, schritte, rueckfragen) bringen."""
    name = roh.get("name") or roh.get("vorhaben") or roh.get("titel") or ""
    rohe = roh.get("schritte") or roh.get("werkzeuge") or roh.get("tools") or []
    schritte = []
    for s in rohe:
        if isinstance(s, str):
            schritte.append({"werkzeug": s, "warum": ""})
        elif isinstance(s, dict):
            key = s.get("werkzeug") or s.get("key") or s.get("tool") or s.get("name")
            if key:
                schritte.append({"werkzeug": key,
                                 "warum": s.get("warum") or s.get("grund") or ""})
    fragen = [f for f in (roh.get("rueckfragen") or roh.get("fragen") or [])
              if isinstance(f, str)]
    return str(name), schritte, fragen


def _bedingungen_lesen(rohe) -> list:
    """Bedingungen auf {key, vergleich, wert} bringen, egal wie sie ankamen."""
    raus = []
    for b in rohe or []:
        if not isinstance(b, dict):
            continue
        key = b.get("key") or b.get("kennzahl") or b.get("feld") or b.get("name")
        vgl = b.get("vergleich") or b.get("operator") or b.get("op")
        wert = b.get("wert", b.get("value"))

        if not key and len(b) == 1:
            # {"lieferscheine": "> 0"} – die Form ohne Schema.
            key, ausdruck = next(iter(b.items()))
            vgl, wert = _ausdruck_teilen(ausdruck)
        elif vgl and wert in (None, ""):
            # {"vergleich": "> 0"} – Operator und Wert in einem Feld.
            vgl2, wert2 = _ausdruck_teilen(vgl)
            if wert2 is not None:
                vgl, wert = vgl2, wert2

        if not key or not vgl:
            continue
        v = str(vgl).strip()
        raus.append({"key": str(key), "vergleich": _VERGLEICH_TEXT.get(v, v),
                     "wert": wert})
    return raus


# ─────────────────────────────────────────────────────────────────────────────
# Stufe 1 · Welche Werkzeuge
# ─────────────────────────────────────────────────────────────────────────────

_STUFE1_SYSTEM = """Du planst in einer Datenauswertungs-Plattform, WELCHE Werkzeuge
für den Wunsch eines Anwenders nötig sind. Du füllst sie NICHT aus – das machen
spätere Schritte.

Regeln:
- Wähle so wenige Werkzeuge wie möglich.
- „abfrage" ist fast immer der erste bauende Schritt: sie liefert die Zahlen.
  Sie kann NUR Kunden, Aufträge, Auftragspositionen, Rechnungen und
  Rechnungspositionen. Geht es um etwas anderes – Artikel, Lager, Bestellungen,
  Lieferanten, Retouren, Zahlungen –, nimm stattdessen „mapping_frei".
- „abfrage" und „mapping_frei" schließen einander aus. Nie beide für dieselbe
  Frage.
- „pipeline" NUR, wenn Daten regelmäßig verarbeitet, geschrieben oder exportiert
  werden sollen. Soll ein Report per Mail kommen, ist „zustellplan" richtig.
- „report" nur, wenn das Ergebnis angesehen, als PDF gebraucht, veröffentlicht
  oder zugestellt werden soll.
- „zustellplan" NUR, wenn im Wunsch ein Takt vorkommt (täglich, montags,
  wöchentlich, monatlich).
- „warnung" NUR, wenn der Anwender benachrichtigt werden will, sobald etwas
  eintritt („sag mir Bescheid, wenn…", „warne mich").
- „veroeffentlichen" NUR, wenn von Kollegen, Portal oder Zugriff die Rede ist.
- „nachsehen" voranstellen, wenn der Wunsch nach einer Standard-Kennzahl klingt
  (Umsatz, Lager, Retouren, offene Posten) – vielleicht gibt es das schon.

Stelle eine Rückfrage nur, wenn ohne sie NICHT gebaut werden kann. Höchstens drei.
Antworte ausschließlich mit JSON."""


def _stufe1_schema() -> dict:
    keys = [w["key"] for w in werkzeuge.katalog_fuer_ki()]
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "schritte": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "werkzeug": {"type": "string", "enum": keys},
                        "warum": {"type": "string"},
                    },
                    "required": ["werkzeug", "warum"],
                },
            },
            "rueckfragen": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "schritte"],
    }


async def _stufe1(svc, wunsch: str) -> dict:
    liste = "\n".join(f'- {w["key"]}: {w["wofuer"]}' for w in werkzeuge.katalog_fuer_ki())
    auftrag = (f"Verfügbare Werkzeuge:\n{liste}\n\n{_heute_satz()}\n\n"
               f"Wunsch des Anwenders (wörtlich):\n„{wunsch}“\n\n"
               f"Welche Werkzeuge sind nötig? Gib auch einen kurzen Namen für das "
               f"Vorhaben an (höchstens 6 Wörter).")
    return await _json(svc, _STUFE1_SYSTEM, auftrag, _stufe1_schema())


# ─────────────────────────────────────────────────────────────────────────────
# Stufe 2a · Körnung
# ─────────────────────────────────────────────────────────────────────────────

_KOERNUNG_SYSTEM = """Du wählst die Körnung einer Datenabfrage: WAS ist eine Zeile
im Ergebnis? Antworte ausschließlich mit JSON.

Entscheidend: Nur die Körnung „kunde" kann NULLFÄLLE finden – Kunden ohne
Rechnung, ohne Auftrag, ohne Umsatz. Eine Gruppierung über Rechnungen liefert für
einen Kunden ohne Rechnung niemals eine Zeile. Wenn im Wunsch „ohne", „keine",
„fehlt" oder „null" vorkommt und es um Kunden geht, ist „kunde" die einzige
richtige Wahl."""


async def _stufe2a_koernung(svc, wunsch: str) -> str:
    optionen = [{"key": k, "label": v["label"], "beschreibung": v["beschreibung"]}
                for k, v in katalog.KOERNUNGEN.items()]
    schema = {
        "type": "object",
        "properties": {
            "koernung": {"type": "string", "enum": [o["key"] for o in optionen]},
            "warum": {"type": "string"},
        },
        "required": ["koernung"],
    }
    auftrag = ("Mögliche Körnungen:\n"
               + "\n".join(f'- {o["key"]} ({o["label"]}): {o["beschreibung"]}'
                           for o in optionen)
               + f"\n\nWunsch des Anwenders (wörtlich):\n„{wunsch}“")
    erg = await _json(svc, _KOERNUNG_SYSTEM, auftrag, schema)
    key = erg.get("koernung")
    return key if key in katalog.KOERNUNGEN else "kunde"


# ─────────────────────────────────────────────────────────────────────────────
# Stufe 2b · Definition
# ─────────────────────────────────────────────────────────────────────────────

_DEF_SYSTEM = """Du füllst eine Abfrage-Definition aus. Du schreibst KEIN SQL und
erfindest KEINE Feldnamen – du wählst ausschließlich aus den unten aufgelisteten
Schlüsseln. Ein Schlüssel, der nicht in der Liste steht, ist ein Fehler.

Zwei Sorten Bedingungen, die nicht verwechselt werden dürfen:
- „bedingungen" filtern eine ZEILE (Land = DE, Kunde gesperrt = 0).
- „kennzahl_bedingungen" prüfen eine ZAHL, die erst durch das Zählen entsteht
  (Anzahl Rechnungen = 0, Umsatz > 1000).
„Kunden, die Ware bekommen, aber keine Rechnung haben" ist also:
Kennzahl „Lieferungen > 0" UND Kennzahl „Anzahl Rechnungen = 0" – beides
Kennzahl-Bedingungen, keine Zeilenfilter.

Wähle die Kennzahlen, die die Frage beantworten, und höchstens fünf.
Antworte ausschließlich mit JSON."""


def _bedingung_schema(felder: list) -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "enum": [f["key"] for f in felder]},
                "vergleich": {"type": "string"},
                "wert": {"type": "string"},
            },
            "required": ["key", "vergleich"],
        },
    }


async def _stufe2b_definition(svc, wunsch: str, koernung: str) -> dict:
    k = katalog.KOERNUNGEN[koernung]
    felder = [{"key": f["key"], "label": f["label"], "typ": f["typ"]}
              for f in k["felder"]]
    # Kennzahlen, die eine Vergleichsgruppe brauchen, sind ohne sie gesperrt –
    # sie dürfen dem Modell gar nicht erst angeboten werden.
    kennzahlen = [{"key": m["key"], "label": m["label"], "typ": m["typ"]}
                  for m in k["kennzahlen"] if not m.get("braucht_gruppe")]

    schema = {
        "type": "object",
        "properties": {
            "verknuepfung": {"type": "string", "enum": ["UND", "ODER"]},
            "bedingungen": _bedingung_schema(felder),
            "kennzahlen": {"type": "array",
                           "items": {"type": "string",
                                     "enum": [m["key"] for m in kennzahlen]}},
            "kennzahl_bedingungen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string",
                                "enum": [m["key"] for m in kennzahlen]},
                        "vergleich": {"type": "string"},
                        "wert": {"type": "string"},
                    },
                    "required": ["key", "vergleich"],
                },
            },
        },
        "required": ["kennzahlen"],
    }

    vergleiche = "\n".join(
        f"  {typ}: " + ", ".join(o for o, _ in ops) for typ, ops in katalog.VERGLEICHE.items())
    auftrag = (
        f"Körnung: {k['label']} – {k['beschreibung']}\n\n"
        f"Felder (für „bedingungen“):\n"
        + "\n".join(f'- {f["key"]} ({f["label"]}, Typ {f["typ"]})' for f in felder)
        + "\n\nKennzahlen (für „kennzahlen“ und „kennzahl_bedingungen“):\n"
        + "\n".join(f'- {m["key"]} ({m["label"]}, Typ {m["typ"]})' for m in kennzahlen)
        + f"\n\nErlaubte Vergleiche je Typ:\n{vergleiche}\n\n{_heute_satz()}\n\n"
        f"Wunsch des Anwenders (wörtlich):\n„{wunsch}“")

    return await _json(svc, _DEF_SYSTEM, auftrag, schema)


def _wert_wandeln(typ: str, wert):
    """Text in den Typ des Feldes bringen. Der SQL-Bauer bindet ihn danach."""
    if wert is None or wert == "":
        return None
    if typ in ("zahl", "geld", "ja_nein"):
        try:
            zahl = float(str(wert).replace(",", "."))
            return int(zahl) if zahl == int(zahl) else zahl
        except (TypeError, ValueError):
            return None
    return str(wert)


def _baum(rohe: list, verknuepfung: str, aufloesen) -> tuple:
    """Flache Bedingungsliste → Filterbaum. Gibt (baum, verworfen) zurück."""
    kinder, verworfen = [], []
    for b in rohe or []:
        key = b.get("key")
        info = aufloesen(key)
        if not info:
            verworfen.append(f"„{key}“ gibt es im Katalog nicht")
            continue
        typ = info["typ"]
        erlaubt = {o for o, _ in katalog.VERGLEICHE.get(typ, [])}
        vgl = b.get("vergleich")
        if vgl not in erlaubt:
            verworfen.append(f"„{vgl}“ ist für {info['label']} kein gültiger Vergleich")
            continue
        knoten = {"key": key, "vergleich": vgl}
        if vgl not in katalog.OHNE_WERT:
            wert = _wert_wandeln(typ, b.get("wert"))
            if wert is None:
                verworfen.append(f"Für {info['label']} fehlt ein brauchbarer Wert")
                continue
            knoten["wert"] = wert
        kinder.append(knoten)

    if not kinder:
        return {}, verworfen
    op = "ODER" if str(verknuepfung).upper() == "ODER" else "UND"
    return {"op": op, "kinder": kinder}, verworfen


# ─────────────────────────────────────────────────────────────────────────────
# Stufe 2c · Zustellung, Warnung, Report
# ─────────────────────────────────────────────────────────────────────────────

_DETAIL_SYSTEM = """Du füllst die Feinheiten eines Auswertungs-Vorhabens aus:
Zeitraum, Takt der Zustellung und Warnschwelle. Wähle ausschließlich aus den
angebotenen Schlüsseln. Antworte ausschließlich mit JSON."""


async def _stufe2c_details(svc, wunsch: str) -> dict:
    from app.services.zeitraum import PRESETS

    schema = {
        "type": "object",
        "properties": {
            "zeitraum_preset": {"type": "string", "enum": list(PRESETS)},
            "cron_expr": {"type": "string", "enum": list(werkzeuge.TAKT_KEYS)},
            "schwelle": {"type": "integer"},
            "severity": {"type": "string",
                         "enum": ["kritisch", "warnung", "hinweis", "info"]},
        },
    }
    auftrag = (
        "Zeitraum-Vorgaben:\n"
        + "\n".join(f"- {k}: {v}" for k, v in PRESETS.items())
        + "\n\nTakte für die Zustellung:\n"
        + "\n".join(f"- {k}: {v}" for k, v in werkzeuge.TAKTE)
        + f"\n\n{_heute_satz()}\n\nWunsch des Anwenders (wörtlich):\n„{wunsch}“\n\n"
        "„schwelle“ ist die Anzahl Treffer, ab der gewarnt wird (mindestens 1).")
    return await _json(svc, _DETAIL_SYSTEM, auftrag, schema)


# ─────────────────────────────────────────────────────────────────────────────
# Der ganze Bauzettel
# ─────────────────────────────────────────────────────────────────────────────

async def bauzettel_stufen(db, svc, wunsch: str, ctx: dict):
    """Satz rein, Bauzettel raus – als Folge von Zwischenständen.

    Ein Bauzettel braucht mehrere Modellaufrufe hintereinander. Als eine einzige
    lange Antwort läuft er in Zeitüberschreitungen der Zwischenschichten; als
    Folge kleiner Meldungen fließen ständig Daten und der Anwender sieht, woran
    gerade gearbeitet wird.

    Liefert unterwegs `{"fortschritt": "…"}` und zum Schluss `{"ergebnis": {…}}`.
    `ctx` braucht project_id, mandant_id und die Mailadresse des Anwenders.
    """
    wunsch = (wunsch or "").strip()
    if not wunsch:
        raise PlanFehler("Es fehlt die Beschreibung dessen, was gebaut werden soll.")

    yield {"fortschritt": "Ich überlege, was gebaut werden muss …"}
    roh_plan = await _stufe1(svc, wunsch)
    roh_name, roh_schritte, roh_fragen = _schritte_lesen(roh_plan)
    name = (roh_name or wunsch)[:80].strip()
    rueckfragen = roh_fragen[:3]
    hinweise = []

    gewaehlt, gesehen = [], set()
    for s in roh_schritte:
        key = s.get("werkzeug")
        if key in werkzeuge.WERKZEUGE and key not in gesehen:
            gesehen.add(key)
            gewaehlt.append({"werkzeug": key, "warum": (s.get("warum") or "").strip()})

    # Ein Vorhaben ohne Abfrage hätte nichts zu zeigen; ein Zustellplan oder eine
    # Warnung ohne Report bzw. Abfrage wäre nicht lauffähig. Das ergänzen wir,
    # statt den Anwender in einen Fehler laufen zu lassen.
    def _sicherstellen(key: str, grund: str):
        if key not in gesehen:
            gesehen.add(key)
            gewaehlt.append({"werkzeug": key, "warum": grund})
            hinweise.append(grund)

    # Beide Abfragewege gleichzeitig wäre dieselbe Frage zweimal gebaut – der
    # geprüfte Katalogweg gewinnt, freies SQL ist nur der Rückfall.
    if "abfrage" in gesehen and "mapping_frei" in gesehen:
        gesehen.discard("mapping_frei")
        gewaehlt = [g for g in gewaehlt if g["werkzeug"] != "mapping_frei"]
        hinweise.append("Der Katalogweg deckt die Frage ab – freies SQL wurde "
                        "weggelassen.")

    hat_quelle = bool({"abfrage", "mapping_frei"} & gesehen)
    if not hat_quelle and ({"zustellplan", "warnung", "veroeffentlichen", "report",
                            "pipeline"} & gesehen):
        _sicherstellen("abfrage", "Ohne Abfrage gäbe es nichts zu zeigen – ergänzt.")
    if "zustellplan" in gesehen or "veroeffentlichen" in gesehen:
        _sicherstellen("report", "Zugestellt und veröffentlicht wird ein Report – ergänzt.")
    if not gesehen:
        _sicherstellen("abfrage", "Als Einstieg immer eine Abfrage.")

    details = {}
    if {"report", "zustellplan", "warnung", "pipeline", "mapping_frei"} & gesehen:
        yield {"fortschritt": "Zeitraum, Takt und Schwelle …"}
        try:
            details = await _stufe2c_details(svc, wunsch)
        except PlanFehler:
            details = {}

    # ── Eingaben füllen ──────────────────────────────────────────────────────
    schritte = []
    for eintrag in werkzeuge.sortiert(gewaehlt):
        key = eintrag["werkzeug"]
        eingabe: dict = {}

        if key == "nachsehen":
            eingabe = {"suchtext": wunsch, "uebernehmen": []}

        elif key == "abfrage":
            yield {"fortschritt": "Was ist eine Zeile im Ergebnis?"}
            koernung = await _stufe2a_koernung(svc, wunsch)
            yield {"fortschritt": f"Bedingungen und Kennzahlen für „{koernung}“ …"}
            roh = await _stufe2b_definition(svc, wunsch, koernung)

            zeilenfilter, verworfen1 = _baum(
                _bedingungen_lesen(roh.get("bedingungen")),
                roh.get("verknuepfung") or "UND",
                lambda k: katalog.feld(koernung, k))
            kennzahlfilter, verworfen2 = _baum(
                _bedingungen_lesen(roh.get("kennzahl_bedingungen")), "UND",
                lambda k: katalog.kennzahl(koernung, k))

            kennzahlen = [m for m in (roh.get("kennzahlen") or [])
                          if katalog.kennzahl(koernung, m)
                          and not (katalog.kennzahl(koernung, m) or {}).get("braucht_gruppe")]
            # Die gefilterten Kennzahlen gehören sichtbar ins Ergebnis – sonst
            # steht dort eine Zahl, nach der gefiltert wurde, die aber niemand
            # sieht und darum auch niemand nachrechnen kann.
            for b in (kennzahlfilter.get("kinder") or []):
                if b["key"] not in kennzahlen:
                    kennzahlen.append(b["key"])

            eingabe = {
                "name": name,
                "beschreibung": wunsch,
                "zeitraum_preset": details.get("zeitraum_preset") or "months_12",
                "definition": {
                    "koernung": koernung,
                    "zeilenfilter": zeilenfilter,
                    "kennzahlen": kennzahlen[:8],
                    "kennzahlfilter": kennzahlfilter,
                },
            }
            hinweise.extend(verworfen1 + verworfen2)
            if not kennzahlen:
                rueckfragen.append("Welche Kennzahl soll die Auswertung zeigen? "
                                   "Die KI hat keine passende gefunden.")

        elif key == "mapping_frei":
            # Das SQL entsteht HIER, nicht beim Bauen: nur so durchläuft es die
            # Prüfkette (gegen die Datenbank ausführen, reparieren, Leer- und
            # Join-Befund) und der Anwender sieht das Urteil im Bauzettel.
            yield {"fortschritt": "SQL schreiben und gegen die Datenbank prüfen …"}
            erg = None
            async for schritt in sql_werkstatt.erzeugen_stufen(
                    db, svc, wunsch, ctx.get("mandant_id")):
                if "ergebnis" in schritt:
                    erg = schritt["ergebnis"]
                else:
                    yield schritt
            erg = erg or {}
            eingabe = {
                "name": name, "beschreibung": wunsch,
                "zeitraum_preset": details.get("zeitraum_preset") or "months_12",
                "sql": erg.get("sql") or "",
                "spalten": erg.get("columns") or [],
                "fehler": erg.get("fehler"), "leer": erg.get("leer"),
                "warnung": erg.get("warnung"),
            }
            if erg.get("fehler"):
                rueckfragen.append("Das erzeugte SQL läuft nicht — die Frage bitte "
                                   "genauer stellen oder im Mapping-Editor nachbessern.")
            elif erg.get("leer"):
                hinweise.append("Das SQL läuft, liefert aber keine Zeile: "
                                + str(erg["leer"])[:160])
            elif erg.get("warnung"):
                hinweise.append(str(erg["warnung"])[:200])

        elif key == "pipeline":
            eingabe = {"name": name,
                       "cron_expr": details.get("cron_expr") or "0 6 * * 1",
                       "mapping_ids": [], "email_to": ctx.get("email") or "",
                       "aktiv": True}

        elif key == "report":
            eingabe = {"name": name,
                       "zeitraum_preset": details.get("zeitraum_preset") or "months_12",
                       "bausteine": []}

        elif key == "zustellplan":
            eingabe = {"name": name,
                       "cron_expr": details.get("cron_expr") or "0 6 * * 1",
                       "zeitraum_preset": details.get("zeitraum_preset") or "last_month",
                       "email_to": ctx.get("email") or "",
                       "aktiv": True}
            if not ctx.get("email"):
                rueckfragen.append("An welche Adresse soll der Report gehen?")

        elif key == "warnung":
            eingabe = {"name": name,
                       "schwelle": max(1, int(details.get("schwelle") or 1)),
                       "severity": details.get("severity") or "warnung"}

        elif key == "veroeffentlichen":
            eingabe = {"beschreibung": wunsch, "allowed_users": []}

        schritte.append({
            "werkzeug": key, "aktiv": True,
            "titel": werkzeuge.get(key)["label"],
            "warum": eintrag.get("warum") or "",
            "eingabe": eingabe,
            "zusammenfassung": werkzeuge.zusammenfassen(key, eingabe),
        })

    yield {"ergebnis": {"name": name, "beschreibung": wunsch, "bauplan": schritte,
                        "rueckfragen": rueckfragen[:3], "hinweise": hinweise}}


async def bauzettel(db, svc, wunsch: str, ctx: dict) -> dict:
    """Dieselbe Planung ohne Zwischenstände – für Aufrufer ohne Datenstrom."""
    ergebnis = None
    async for schritt in bauzettel_stufen(db, svc, wunsch, ctx):
        if "ergebnis" in schritt:
            ergebnis = schritt["ergebnis"]
    if ergebnis is None:
        raise PlanFehler("Die Planung hat kein Ergebnis geliefert.")
    return ergebnis

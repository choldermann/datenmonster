"""Mapping-Baukasten: Rezepte (fertige Steinketten) und KI-Steinketten (Schritt 4).

Rezepte sind ganz normale Ketten. Angeboten wird nur, was in der gewählten Datenbank wirklich passt: jede Kette
läuft vorher durch den Übersetzer (Tabellen und Spalten werden gegen das Schema geprüft). Tabellennamen werden
ohne Rücksicht auf Groß-/Kleinschreibung aufgelöst (JTL: „dbo.tkunde“).

Die KI schreibt kein SQL, sondern eine Kette im selben Format. Der Übersetzer ist der Prüfer: was er ablehnt,
geht mit seiner Meldung einmal zur Korrektur zurück. So kann die KI nur bauen, was auch ein Mensch mit den
Steinen bauen könnte – und der Anwender sieht danach Stein für Stein, was sie gebaut hat.
"""
from __future__ import annotations

import copy
import json
from datetime import date
import logging

from .uebersetzer import BaukastenFehler, Schema, uebersetzen

logger = logging.getLogger(__name__)

_RE = "Rechnung.tRechnung"
_ECK = "Rechnung.tRechnungEckdaten"
_POS = "Rechnung.tRechnungPosition"
_ADR = "dbo.tAdresse"
_ZEITRAUM = {"type": "filter", "col": "dErstellt", "op": "im Zeitraum"}
_OHNE_STORNO = {"type": "filter", "col": "nStorno", "op": "=", "val": "0"}
_RECHNUNGSADRESSE = [{"type": "filter", "col": "nStandard", "op": "=", "val": "1"},
                     {"type": "filter", "col": "nTyp", "op": "=", "val": "1"}]
_START = {"type": "start", "trigger": "Wenn das Cockpit öffnet"}
_AUS = {"type": "ausgabe", "target": "Tabelle im Cockpit"}

REZEPTE = [
    {"key": "umsatz_monat", "name": "Umsatz je Monat", "text": "Netto-Umsatz und Anzahl Rechnungen je Monat im Zeitraum, ohne Stornos",
     "kette": [_START,
               {"type": "tabelle", "table": _RE, "inner": [_OHNE_STORNO, _ZEITRAUM,
                {"type": "join", "table": _ECK, "links": "kRechnung", "rechts": "kRechnung", "inner": []}]},
               {"type": "verdichten", "by": [{"col": "dErstellt", "teil": "monat"}, ""],
                "aggs": [{"fn": "Summe", "col": "fVkNettoGesamt"}, {"fn": "Anzahl"}]},
               {"type": "sortieren", "col": "dErstellt (Monat)", "dir": "aufsteigend"}, _AUS]},
    {"key": "top_kunden", "name": "Top-Kunden", "text": "Die 20 Kunden mit dem meisten Netto-Umsatz im Zeitraum, mit Ø Rechnung",
     "kette": [_START,
               {"type": "tabelle", "table": _RE, "inner": [_OHNE_STORNO, _ZEITRAUM,
                {"type": "join", "table": _ECK, "links": "kRechnung", "rechts": "kRechnung", "inner": []},
                {"type": "join", "table": _ADR, "links": "kKunde", "rechts": "kKunde", "inner": copy.deepcopy(_RECHNUNGSADRESSE)}]},
               {"type": "verdichten", "by": ["cKundennr", "cFirma (tAdresse)"],
                "aggs": [{"fn": "Summe", "col": "fVkNettoGesamt"}, {"fn": "Anzahl"}]},
               {"type": "rechnen", "name": "Ø Rechnung", "a": "Summe fVkNettoGesamt", "op": "÷", "b": "Anzahl"},
               {"type": "sortieren", "col": "Summe fVkNettoGesamt", "dir": "absteigend"},
               {"type": "begrenzen", "n": 20}, _AUS]},
    {"key": "bestseller", "name": "Bestseller-Artikel", "text": "Die 20 meistverkauften Artikel im Zeitraum nach Menge, mit Umsatz",
     "kette": [_START,
               {"type": "tabelle", "table": _POS, "inner": [
                   {"type": "filter", "col": "nType", "op": "=", "val": "1"},
                   {"type": "join", "table": _RE, "links": "kRechnung", "rechts": "kRechnung", "inner": [_OHNE_STORNO, _ZEITRAUM]}]},
               {"type": "rechnen", "name": "Umsatz netto", "a": "fAnzahl", "op": "×", "b": "fVkNetto"},
               {"type": "verdichten", "by": ["cArtNr", "cName"],
                "aggs": [{"fn": "Summe", "col": "fAnzahl"}, {"fn": "Summe", "col": "Umsatz netto"}]},
               {"type": "sortieren", "col": "Summe fAnzahl", "dir": "absteigend"},
               {"type": "begrenzen", "n": 20}, _AUS]},
    {"key": "umsatz_land", "name": "Umsatz je Versandland", "text": "Netto-Umsatz und Rechnungen je Lieferland im Zeitraum",
     "kette": [_START,
               {"type": "tabelle", "table": _RE, "inner": [_OHNE_STORNO, _ZEITRAUM,
                {"type": "join", "table": _ECK, "links": "kRechnung", "rechts": "kRechnung", "inner": []}]},
               {"type": "verdichten", "by": ["cVersandlandISO", ""],
                "aggs": [{"fn": "Summe", "col": "fVkNettoGesamt"}, {"fn": "Anzahl"}]},
               {"type": "sortieren", "col": "Summe fVkNettoGesamt", "dir": "absteigend"}, _AUS]},
    {"key": "offene_rechnungen", "name": "Offene Rechnungen", "text": "Rechnungen mit offenem Betrag, größter zuerst, mit Kunde",
     "kette": [_START,
               {"type": "tabelle", "table": _RE, "inner": [_OHNE_STORNO,
                {"type": "join", "table": _ECK, "links": "kRechnung", "rechts": "kRechnung",
                 "inner": [{"type": "filter", "col": "fOffenerWert", "op": ">", "val": "0"}]},
                {"type": "join", "table": _ADR, "links": "kKunde", "rechts": "kKunde", "inner": copy.deepcopy(_RECHNUNGSADRESSE)}]},
               {"type": "sortieren", "col": "fOffenerWert", "dir": "absteigend"}, _AUS]},
    {"key": "lagerwert", "name": "Lagerwert je Artikel", "text": "Bestand × Einkaufspreis, die 50 größten Positionen",
     "kette": [_START,
               {"type": "tabelle", "table": "dbo.tArtikel", "inner": [
                   {"type": "join", "table": "dbo.tlagerbestand", "links": "kArtikel", "rechts": "kArtikel",
                    "inner": [{"type": "filter", "col": "fLagerbestand", "op": ">", "val": "0"}]}]},
               {"type": "rechnen", "name": "Lagerwert", "a": "fLagerbestand", "op": "×", "b": "fEKNetto"},
               {"type": "sortieren", "col": "Lagerwert", "dir": "absteigend"},
               {"type": "begrenzen", "n": 50}, _AUS]},
]



# ── büro+ (microtech) ──────────────────────────────────────────────────────
# Tabellen aus den büro+-Exporten (tools/bueroplus): Spalten heißen wie die büro+-Felder. Umsatz wie im
# büro+ GF-Cockpit: gebuchte, nicht stornierte „Rechnung I“ und „Sammel Rechnung“ (Rechnungskorrekturen getrennt).
_BV = "dbo.vVorgang"
_BP = "dbo.vVorgangPosition"
_BA = "dbo.Adressen"
_BART = "dbo.Artikel"
_BP_RECHNUNG = [{"type": "filter", "col": "VogArt", "op": "ist einer von", "val": "Rechnung I, Sammel Rechnung"},
                {"type": "filter", "col": "VogGebuchtKz", "op": "=", "val": "1"},
                {"type": "filter", "col": "VogStorniertKz", "op": "=", "val": "0"},
                {"type": "filter", "col": "VogDat", "op": "im Zeitraum"}]
_BP_KUNDE = {"type": "join", "table": _BA, "links": "VogAdrNr", "rechts": "AdrAdrNr", "alle": True, "inner": []}
_BP_ROH = {"type": "rechnen", "name": "Rohertrag", "a": "Summe VogGPreisNt", "op": "−", "b": "Summe VogGEkRoh"}
_BP_POS_INNEN = [{"type": "filter", "col": "ArtNr", "op": "ist nicht leer"},
                 {"type": "join", "table": _BV, "links": "VogID", "rechts": "VogID", "inner": copy.deepcopy(_BP_RECHNUNG)},
                 {"type": "join", "table": _BART, "links": "ArtNr", "rechts": "ArtArtNr", "alle": True, "inner": []}]

REZEPTE += [
    {"key": "bp_umsatz_monat", "system": "büro+", "name": "Umsatz je Monat",
     "text": "Netto-Umsatz, Rohertrag und Anzahl Rechnungen je Monat im Zeitraum (gebucht, ohne Stornos, ohne Rechnungskorrekturen)",
     "kette": [_START, {"type": "tabelle", "table": _BV, "inner": copy.deepcopy(_BP_RECHNUNG)},
               {"type": "verdichten", "by": [{"col": "VogDat", "teil": "monat"}],
                "aggs": [{"fn": "Summe", "col": "VogGPreisNt"}, {"fn": "Summe", "col": "VogGEkRoh"}, {"fn": "Anzahl"}]},
               _BP_ROH, {"type": "sortieren", "col": "VogDat (Monat)", "dir": "aufsteigend"}, _AUS]},
    {"key": "bp_top_kunden", "system": "büro+", "name": "Top-Kunden",
     "text": "Die 20 Kunden mit dem meisten Netto-Umsatz im Zeitraum, mit Rohertrag und Ø Rechnung",
     "kette": [_START, {"type": "tabelle", "table": _BV, "inner": copy.deepcopy(_BP_RECHNUNG) + [copy.deepcopy(_BP_KUNDE)]},
               {"type": "verdichten", "by": ["VogAdrNr", "AdrReNa2"],
                "aggs": [{"fn": "Summe", "col": "VogGPreisNt"}, {"fn": "Summe", "col": "VogGEkRoh"}, {"fn": "Anzahl"}]},
               _BP_ROH, {"type": "rechnen", "name": "Ø Rechnung", "a": "Summe VogGPreisNt", "op": "÷", "b": "Anzahl"},
               {"type": "sortieren", "col": "Summe VogGPreisNt", "dir": "absteigend"}, {"type": "begrenzen", "n": 20}, _AUS]},
    {"key": "bp_umsatz_verkaeufer", "system": "büro+", "name": "Umsatz je Verkäufer",
     "text": "Netto-Umsatz, Rohertrag und Rechnungen je Bearbeiter (VogVerk) im Zeitraum",
     "kette": [_START, {"type": "tabelle", "table": _BV, "inner": copy.deepcopy(_BP_RECHNUNG)},
               {"type": "verdichten", "by": ["VogVerk"],
                "aggs": [{"fn": "Summe", "col": "VogGPreisNt"}, {"fn": "Summe", "col": "VogGEkRoh"}, {"fn": "Anzahl"}]},
               _BP_ROH, {"type": "sortieren", "col": "Summe VogGPreisNt", "dir": "absteigend"}, _AUS]},
    {"key": "bp_bestseller", "system": "büro+", "name": "Bestseller-Artikel",
     "text": "Die 20 Artikel mit dem meisten Netto-Umsatz im Zeitraum, mit Menge und Rohertrag",
     "kette": [_START, {"type": "tabelle", "table": _BP, "inner": copy.deepcopy(_BP_POS_INNEN)},
               {"type": "verdichten", "by": ["ArtNr", "ArtBez1"],
                "aggs": [{"fn": "Summe", "col": "BuchMge"}, {"fn": "Summe", "col": "NettoPos"}, {"fn": "Summe", "col": "RohertragPos"}]},
               {"type": "sortieren", "col": "Summe NettoPos", "dir": "absteigend"}, {"type": "begrenzen", "n": 20}, _AUS]},
    {"key": "bp_warengruppen", "system": "büro+", "name": "Umsatz je Warengruppe",
     "text": "Netto-Umsatz und Rohertrag je Warengruppe im Zeitraum",
     "kette": [_START, {"type": "tabelle", "table": _BP, "inner": copy.deepcopy(_BP_POS_INNEN)},
               {"type": "verdichten", "by": ["ArtWgrNr", "ArtWgrNrInfo"],
                "aggs": [{"fn": "Summe", "col": "NettoPos"}, {"fn": "Summe", "col": "RohertragPos"}]},
               {"type": "sortieren", "col": "Summe NettoPos", "dir": "absteigend"}, _AUS]},
    {"key": "bp_offene_angebote", "system": "büro+", "name": "Angebote der letzten 90 Tage",
     "text": "Nicht stornierte Angebote aus der Vorgangsübersicht, größter Wert zuerst, mit Kunde",
     "kette": [_START, {"type": "tabelle", "table": "dbo.Vorgang", "inner": [
                   {"type": "filter", "col": "VogArt", "op": "=", "val": "Angebot"},
                   {"type": "filter", "col": "VogStorniertKz", "op": "=", "val": "0"},
                   {"type": "filter", "col": "VogDat", "op": "in den letzten Tagen", "val": "90"},
                   copy.deepcopy(_BP_KUNDE)]},
               {"type": "sortieren", "col": "VogGPreisNt", "dir": "absteigend"}, _AUS]},
    {"key": "bp_lieferscheine", "system": "büro+", "name": "Lieferscheine ohne Rechnung",
     "text": "Nicht stornierte Lieferscheine in der Vorgangsübersicht, älteste zuerst, mit Kunde",
     "kette": [_START, {"type": "tabelle", "table": "dbo.Vorgang", "inner": [
                   {"type": "filter", "col": "VogArt", "op": "=", "val": "Lieferschein"},
                   {"type": "filter", "col": "VogStorniertKz", "op": "=", "val": "0"},
                   copy.deepcopy(_BP_KUNDE)]},
               {"type": "sortieren", "col": "VogDat", "dir": "aufsteigend"}, _AUS]},
]
for _r in REZEPTE:
    _r.setdefault("system", "JTL")


def _tabellen_aufloesen(kette: list, schema: Schema) -> list:
    """Tabellennamen auf die Schreibweise der Datenbank bringen (dbo.tAdresse ↔ dbo.tadresse)."""
    namen = {t.lower(): t for t in schema.tabellen}

    def lauf(liste):
        for b in liste:
            if b.get("table"):
                b["table"] = namen.get(b["table"].lower(), b["table"])
            if b.get("inner"):
                lauf(b["inner"])
    k = copy.deepcopy(kette)
    lauf(k)
    return k


def passende(schema: Schema, dialekt: str) -> list[dict]:
    aus = []
    for r in REZEPTE:
        k = _tabellen_aufloesen(r["kette"], schema)
        try:
            uebersetzen(k, schema, dialekt)
        except BaukastenFehler as e:
            logger.info("Rezept %s passt hier nicht: %s", r["key"], e)
            continue
        aus.append({"key": r["key"], "name": r["name"], "text": r["text"], "system": r["system"], "kette": k})
    return aus


# ── KI-Steinketten ─────────────────────────────────────────────────────────
FORMAT = """Kettenformat (JSON-Liste von Steinen, Reihenfolge = Ablauf):
- {"type":"start","trigger":"Wenn das Cockpit öffnet"}  (immer zuerst)
- {"type":"tabelle","table":"<Schema.Tabelle>","inner":[ … ]}  genau EINE, enthält nur "filter" und "join"
- im Winkel: {"type":"filter","col":"<Spalte>","op":"<Vergleich>","val":"<Wert>"}
  Vergleiche: = ≠ > < ≥ ≤ "ist einer von" (Werte mit Komma getrennt) "enthält" "beginnt mit" "ist leer" "ist nicht leer" "im Jahr" "in den letzten Tagen" "im Zeitraum" (Datum, nutzt den Zeitraum des Cockpits, ohne val)
- WICHTIG: "join" steht NIE auf oberster Ebene, sondern immer in "inner" der Tabelle (wie im Beispiel).
- Ein "join" enthält in "inner" NUR "filter" – nie einen weiteren "join". Weitere Tabellen kommen als weiterer "join"
  direkt in "inner" der Tabelle; "links" darf dann eine Spalte einer schon dazugeholten Tabelle sein.
- Textwerte so, wie sie in der Datenbank stehen (Länder in Adressen oft ausgeschrieben, z. B. "Österreich"; ISO-Codes in cISO/cVersandlandISO, z. B. "AT").
- im Winkel: {"type":"join","table":"<Schema.Tabelle>","links":"<Spalte bisher>","rechts":"<Spalte der neuen Tabelle>","alle":false,"inner":[nur filter auf die neue Tabelle]}
  "alle":true behält auch Zeilen ohne Treffer – nur ohne "filter" im Winkel sinnvoll; soll die neue Tabelle eingrenzen, "alle":false.
  Spalten der dazugeholten Tabelle, die es schon gibt, heißen danach "<Spalte> (<Tabelle ohne Schema>)", z. B. "cFirma (tAdresse)".
- {"type":"rechnen","name":"<neu>","a":"<Spalte>","op":"+|−|×|÷","b":"<Spalte oder Zahl>"}
- {"type":"verdichten","by":["<Spalte>" oder {"col":"<Datumsspalte>","teil":"monat|jahr"}, …],"aggs":[{"fn":"Summe|Durchschnitt|Höchstwert|Tiefstwert","col":"<Zahlspalte>"},{"fn":"Anzahl"}]}
  höchstens einmal; danach heißen die Spalten: "<Spalte>", "<Datumsspalte> (Monat)", "Summe <Spalte>", "Ø <Spalte>", "Max <Spalte>", "Min <Spalte>", "Anzahl"
- nach "verdichten": {"type":"filter",…} prüft eine Kennzahl (z. B. "Summe fWert" > 1000)
- {"type":"sortieren","col":"<Spalte>","dir":"absteigend|aufsteigend"}, {"type":"begrenzen","n":20}
- {"type":"ausgabe","target":"Tabelle im Cockpit"}  (immer zuletzt)"""


def _json_reparieren(text: str):
    """JSON lesen; überzählige schließende Klammern (häufigster KI-Fehler bei Verschachtelung) entfernen."""
    t = text.strip()
    for _ in range(12):
        try:
            return json.loads(t), ""
        except json.JSONDecodeError as e:
            if e.pos < len(t) and t[e.pos] in "}]" and ("delimiter" in e.msg or "Extra data" in e.msg):
                t = t[:e.pos] + t[e.pos + 1:]
                continue
            return None, f"{e.msg} bei Zeichen {e.pos}"
    return None, "zu viele Klammerfehler"


def _normalisieren(kette: list) -> list:
    """Typische Strukturfehler der KI eindeutig richtigstellen (die Steine ergeben nur an einer Stelle Sinn):
    „join“ auf oberster Ebene → in den Winkel der Tabelle; „join“ im „join“ → daneben; Zeilenfilter vor dem
    Trichter (oder ganz ohne Trichter) auf oberster Ebene → in den Winkel; Start/Ausgabe an Anfang/Ende."""
    k = [b for b in kette if isinstance(b, dict) and b.get("type")]
    tab = next((b for b in k if b["type"] == "tabelle"), None)
    if tab is None:
        return k
    tab.setdefault("inner", [])
    verd = next((i for i, b in enumerate(k) if b["type"] == "verdichten"), None)
    aus = []
    for i, b in enumerate(k):
        if b["type"] == "join" or (b["type"] == "filter" and (verd is None or i < verd)):
            tab["inner"].append(b)
        else:
            aus.append(b)

    def flach(liste):
        neu = []
        for b in liste:
            if b.get("type") == "join":
                kinder = b.get("inner") or []
                b["inner"] = [x for x in kinder if x.get("type") == "filter"]
                if b["inner"] and b.get("alle"):
                    b["alle"] = False      # „Nur wenn“ im Winkel soll eingrenzen – mit „alle behalten“ würde es nichts filtern
                neu.append(b)
                neu.extend(flach([x for x in kinder if x.get("type") == "join"]))
            else:
                neu.append(b)
        return neu
    tab["inner"] = flach(tab["inner"])
    start = [b for b in aus if b["type"] == "start"][:1]
    ende = [b for b in aus if b["type"] == "ausgabe"][:1]
    mitte = [b for b in aus if b["type"] not in ("start", "ausgabe")]
    return start + mitte + ende


def _unvollstaendig(kette: list) -> str:
    """Steine, die der Übersetzer still als „noch nicht eingestellt“ übergehen würde – bei der KI ein Fehler."""
    def lauf(liste) -> str:
        for b in liste:
            t = b.get("type")
            if t == "join" and not (b.get("table") and b.get("links") and b.get("rechts")):
                return f"„Dazuholen {b.get('table') or ''}“ braucht table, links und rechts (genau diese Schlüssel)."
            if t == "filter" and not b.get("col"):
                return "Ein „filter“ braucht col."
            if t == "filter" and b.get("op") not in ("ist leer", "ist nicht leer", "im Zeitraum") and str(b.get("val") or "").strip() == "":
                return f"„filter {b.get('col')} {b.get('op')}“ braucht einen Wert in val (z. B. die Jahreszahl)."
            if t == "rechnen" and (not b.get("a") or b.get("b") in (None, "")):
                return "„rechnen“ braucht a und b."
            if t == "sortieren" and not b.get("col"):
                return "„sortieren“ braucht col."
            if t == "verdichten" and not [x for x in (b.get("by") or []) if x]:
                return "„verdichten“ braucht mindestens eine Spalte in by."
            if b.get("inner"):
                f = lauf(b["inner"])
                if f:
                    return f
        return ""
    return lauf(kette)


_REGELN_JTL = (
    "Lasse stornierte Rechnungen weg (nStorno = 0). "
    "Nimm Tabellen (z. B. Rechnung.tRechnung, Rechnung.tRechnungEckdaten, Rechnung.tRechnungPosition, dbo.tAdresse, dbo.tArtikel) "
    "statt Sichten (Namen mit v… oder lv…) und verknüpfe nur über die angegebenen Beziehungen. "
    "Holst du Adressen dazu, grenze auf eine je Kunde ein (nStandard = 1 und nTyp = 1), sonst verdoppeln sich die Zeilen.")
_REGELN_BUEROPLUS = (
    "Die Datenbank kommt aus microtech büro+; Spalten heißen wie die büro+-Felder. Belege: dbo.vVorgang (Archiv und "
    "Übersicht zusammen, VogArt = Belegart, VogDat = Belegdatum, VogGPreisNt = Netto, VogGEkRoh = Einkauf, VogVerk = Bearbeiter, "
    "VogAdrNr = Kunde). Umsatz = VogArt „ist einer von“ „Rechnung I, Sammel Rechnung“ mit VogGebuchtKz = 1 und "
    "VogStorniertKz = 0; Rechnungskorrekturen (VogArt = Rechnungskorrektur) haben positive Beträge und mindern den Umsatz. "
    "Positionen: dbo.vVorgangPosition über VogID (ArtNr, BuchMge = Menge, NettoPos, EkPos, RohertragPos – schon mit Preisfaktor). "
    "Offene Angebote, Aufträge (VogArt = Auftragsbestätigung) und Lieferscheine stehen in dbo.Vorgang (nur die Übersicht); "
    "dort nur VogStorniertKz = 0 filtern, nicht VogGebuchtKz, und nach VogGPreisNt oder VogDat sortieren. Kunden: dbo.Adressen über "
    "VogAdrNr = AdrAdrNr (Name in AdrReNa2, Ort in AdrReOrt, eine Zeile je Adresse; gesperrt = AdrGspKz = 1, AdrStatus ist "
    "nur ein Freitext). Artikel: dbo.Artikel über ArtNr = ArtArtNr "
    "(ArtBez1, ArtWgrNr/ArtWgrNrInfo = Warengruppe, ArtWgrNrInfo ist „Nummer Name“, z. B. „15 Pizzakarton“ → mit „enthält“ suchen). "
    "Umsatz, Menge oder Rohertrag je Artikel/Warengruppe: von dbo.vVorgangPosition ausgehen und dbo.vVorgang über VogID mit "
    "denselben Umsatz-Filtern (Belegart, gebucht, nicht storniert, Zeitraum) im Winkel dazuholen – sonst zählen Angebote und "
    "Lieferscheine mit. Werte je Beleg, Kunde, Verkäufer oder Monat (Umsatz, Einkauf, Rohertrag = Summe VogGPreisNt − "
    "Summe VogGEkRoh) kommen direkt aus dbo.vVorgang, ohne Positionen. Nimm nie dbo.VorgangArchiv, dbo.VorgangPosition oder "
    "dbo.VorgangPositionArchiv (Teilstücke), sondern die Sichten dbo.vVorgang und dbo.vVorgangPosition, und nie Tabellen aus dem Schema stg (Rohdaten des Imports).")


async def ki_kette(svc, schema_json: dict, schema: Schema, dialekt: str, text: str, probe=None) -> dict:
    """probe(kette) → Warnungen eines Probelaufs (z. B. „keine Zeile übrig“); sie gehen zur Nachbesserung zurück."""
    from app.services.schema_cache_service import (beziehungen_ableiten, extract_keywords,
                                                   filter_schema_by_keywords, schema_json_to_text)
    teil = filter_schema_by_keywords(schema_json, extract_keywords(text), max_tables=12)
    tabellen = [t["full_name"] for t in teil.get("tables", [])]
    bez = beziehungen_ableiten(schema_json, von_tabellen=tabellen, grenze=60)
    bez_text = "\n".join(f"{b['from_table']}.{b['from_col']} → {b['to_table']}.{b['to_col']}"
                         for b in bez if b["to_table"] in tabellen and b["quelle"] != "unsicher")[:4000]
    # Beispiele und Fachregeln passend zur Datenbank (JTL oder büro+) – erkannt an den Rezepten, die hier passen
    passt = passende(schema, dialekt)
    art = "büro+" if any(r["system"] == "büro+" for r in passt) else "JTL"
    beisp = [r for r in passt if r["system"] == art and r["key"] in ("top_kunden", "bestseller", "bp_top_kunden", "bp_bestseller")]
    if not beisp:
        beisp = [r for r in REZEPTE if r["key"] in ("top_kunden", "bestseller")]
    beispiele = "\n\n".join(f"Beispiel ({r['name']}):\n{json.dumps(_tabellen_aufloesen(r['kette'], schema), ensure_ascii=False)}"
                             for r in beisp)
    system = (
        "Du baust Auswertungen für einen Händler aus Bausteinen. Antworte NUR mit JSON "
        '{"kette_json":"<die Kette als JSON-Text>","hinweis":"<ein kurzer deutscher Satz, was die Auswertung zeigt oder was fehlt>"}. '
        "Nutze ausschließlich Tabellen und Spalten aus der Liste unten, exakt so geschrieben. Bevorzuge Netto-Werte "
        "und nutze für Zeiträume ohne genaue Angabe „im Zeitraum“. "
        f"Heute ist der {date.today():%d.%m.%Y} („dieses Jahr“ = {date.today().year}, „letztes Jahr“ = {date.today().year - 1}). "
        + (_REGELN_BUEROPLUS if art == "büro+" else _REGELN_JTL) +
        f"\n\n{FORMAT}\n\n{beispiele}\n\n"
        f"Beziehungen:\n{bez_text or '(keine erkannt)'}\n\nTabellen:\n{schema_json_to_text(teil, max_tables=12)[:14000]}")
    nachrichten = [{"role": "system", "content": system}, {"role": "user", "content": text}]
    # Strenges Antwortformat (OpenAI-kompatibel): die verschachtelte Kette kommt als JSON-Text
    ausgabe_schema = {"type": "object", "additionalProperties": False, "required": ["kette_json", "hinweis"],
                      "properties": {"kette_json": {"type": "string"}, "hinweis": {"type": "string"}}}
    for versuch in range(3):
        letzter = ""
        try:
            antwort = await svc.complete_json(nachrichten, ausgabe_schema, request_type="MAPPING_ASSISTANT",
                                              max_tokens=9000, temperature=0.1)
            logger.info("Baukasten-KI Antwort: %s", str(antwort)[:500])
        except Exception as e:
            raise BaukastenFehler(f"Die KI hat nicht geantwortet: {str(e)[:200]}")
        kette = None
        if isinstance(antwort, dict):
            kette = antwort.get("kette")
            if kette is None and isinstance(antwort.get("kette_json"), str):
                kette, json_fehler = _json_reparieren(antwort["kette_json"])
                if kette is None:
                    letzter = f"Der JSON-Text der Kette ist ungültig ({json_fehler}). Achte auf passende Klammern."
            if isinstance(kette, dict):
                kette = kette.get("kette")
        if not isinstance(kette, list) or not kette:
            letzter = letzter or "Die Antwort enthielt keine Kette."
        else:
            kette = _normalisieren(_tabellen_aufloesen(kette, schema))
            try:
                luecke = _unvollstaendig(kette)
                if luecke:
                    raise BaukastenFehler(luecke)
                uebersetzen(kette, schema, dialekt)
                warn = probe(kette) if probe else {}
                if warn and versuch < 2:
                    raise BaukastenFehler("Probelauf: " + " ".join(warn.values()))
                return {"kette": kette, "hinweis": antwort.get("hinweis") or "", "versuche": versuch + 1,
                        "warnungen": warn}
            except BaukastenFehler as e:
                letzter = str(e)
        # Mit der Meldung des Übersetzers nachbessern lassen (höchstens zweimal)
        nachrichten = nachrichten[:2] + [
            {"role": "assistant", "content": json.dumps(antwort, ensure_ascii=False)[:6000]},
            {"role": "user", "content": f"Das passt nicht: {letzter} Bitte korrigiere die Kette und antworte wieder nur mit JSON."}]
    raise BaukastenFehler(f"Die KI hat keine gültige Kette gebaut ({letzter}). Bitte die Frage genauer stellen oder mit einem Rezept beginnen.")

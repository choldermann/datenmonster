"""SQL von der KI erzeugen und so lange prüfen, bis es trägt.

Herausgezogen aus dem Baumodus des Mapping-Editors, weil die KI-Werkbank
dieselbe Kette braucht. Zwei Fassungen davon wären die sichere Art, dass eine
von beiden irgendwann ungeprüftes SQL durchlässt – und ungeprüftes KI-SQL ist
in dieser Plattform der teuerste Fehler: es sieht bis zur Vorschau wie eine
fertige Abfrage aus.

**Drei Sorten Befund**, alle drei müssen gefunden werden:

1. *Abgelehnt* – erfundene Tabelle oder Spalte. Die Datenbank sagt es selbst.
2. *Angenommen, aber leer* – läuft fehlerfrei und liefert nie eine Zeile, weil
   ein Join auf einen Schlüssel zeigt, der nie zusammenpasst.
3. *Angenommen mit Zeilen, aber unsinnigem Join* – zwei fremde Entitätsschlüssel
   gleichgesetzt (`kArtikel = kKunde`); die Treffer entstehen nur aus
   überlappenden Nummernkreisen.

Die letzten beiden sind die heimtückischen. Für alle drei gibt es bis zu zwei
Reparaturläufe mit dem echten Befund der Datenbank; der zweite bekommt
zusätzlich das Schema zur Fehlermeldung nachgereicht – einer reichte im
Kundenrückgang-Fall nicht.
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

REPARATURVERSUCHE = (1, 2, 3)


def beschreibung_zusammensetzen(original: str, praezisierung: str) -> str:
    """Wortlaut des Anwenders plus (nachrangig) die Umformulierung des Bauplans.

    Stufe 1 formuliert die Aufgabe um und kann sie dabei verfälschen – aus
    „dieses Jahr" wurde schon „das Jahr 2023". Der Wortlaut bleibt deshalb immer
    dabei und hat im Zweifel Vorrang.
    """
    original = (original or "").strip()
    praezisierung = (praezisierung or "").strip()
    if praezisierung and praezisierung.lower() != original.lower():
        return (f"{original}\n\nPräzisierung aus dem Bauplan (nachrangig – "
                f"bei Widerspruch gilt der Wortlaut oben): {praezisierung}")
    return praezisierung or original


def _urteil(fehler: Optional[str], leer: Optional[str], verdacht: Optional[str]) -> str:
    """Was dem Modell zum Befund gesagt wird."""
    if fehler:
        return (f"Die Datenbank lehnt es ab:\n{fehler}\n\n"
                "Korrigiere die Abfrage. Verwende ausschließlich Tabellen und "
                "Spalten, die oben im Schema stehen.")
    if verdacht and not leer:
        return (f"{verdacht}\n\n"
                "In dieser Datenbank ist eine Schlüsselspalte nach ihrer Entität "
                "benannt: kArtikel zeigt auf einen Artikel, kKunde auf einen Kunden. "
                "Zwei verschiedene davon gleichzusetzen verbindet zusammenhanglose "
                "Zeilen — die Abfrage liefert dann Treffer, die nur aus überlappenden "
                "Nummernkreisen entstehen. Suche im Schema oben die Tabelle, die "
                "beide Seiten wirklich verbindet, und schreibe die Abfrage neu. "
                "Gibt es keine, gehört die Tabelle nicht in die Abfrage.")
    # Keine Ursache behaupten, die der Befund nicht hergibt: `leer` nennt die
    # geprüften Tabellen, ihre Zeilenzahl und – wo möglich – die Werte, die in
    # den gefilterten Spalten wirklich vorkommen. Der frühere Text schrieb
    # darüber pauschal „fast immer ein Join-Fehler" und schickte das Modell
    # damit an den Joins herumbessern, während in Wahrheit ein geratener
    # Statuscode oder schlicht die falsche Tabelle das Problem war.
    return (f"{leer}\n\n"
            "Gehe der Reihe nach vor:\n"
            "1. Stehen oben die tatsächlichen Werte einer gefilterten Spalte? "
            "Dann war der Vergleichswert geraten – nimm einen der echten Werte "
            "oder lass den Filter weg.\n"
            "2. Passt die Tabelle überhaupt zur Frage? Sieh im Schema oben nach, "
            "ob es eine Tabelle gibt, die den gesuchten Sachverhalt WIRKLICH "
            "führt. Ein Statuscode in einer Belegtabelle ist selten die "
            "Rückmeldung eines externen Dienstes.\n"
            "3. Erst danach die JOINs prüfen: verbinden die Spalten wirklich "
            "denselben Schlüssel?\n"
            "Schreibe die Abfrage neu.")


def _lage(fehler, leer, verdacht) -> str:
    return ("SQL-Fehler" if fehler
            else "Abfrage bleibt leer" if leer
            else "Join verbindet fremde Schlüssel")


async def erzeugen_stufen(db, svc, beschreibung: str, connection_id: Optional[int],
                          mapping_id: Optional[int] = None,
                          canvas_nodes: Optional[list] = None):
    """Erzeugt SQL zur Beschreibung und prüft es gegen die echte Verbindung.

    Als Datenstrom, nicht als eine lange Antwort: Erzeugung und Reparaturen sind
    mehrere Modellaufrufe hintereinander, und der Anwender soll sehen, woran
    gerade gearbeitet wird – nicht eine halbe Minute auf ein leeres Feld starren
    und dann alle Meldungen auf einmal bekommen.

    Liefert unterwegs `{"fortschritt": "…"}` und zum Schluss
    `{"ergebnis": {sql, columns, fehler, leer, warnung, versuche}}`.
    `fehler` gesetzt heißt: unbrauchbar. `leer` oder `warnung` heißt: läuft,
    ist aber verdächtig – das gehört dem Anwender vorgelegt, nicht verschwiegen.
    """
    # Die Prüf- und Säuberungshelfer leben in der KI-API; sie hier zu
    # duplizieren hieße, zwei Fassungen derselben Regeln zu pflegen.
    from app.api.ai import (_joinbefund, _spalten_nachschlag, _sql_pruefen,
                            _sql_saeubern)
    from app.services.ai_context_builder import AIContextBuilder
    from app.services.ai_service import params_fuer_prompt, timeout_fuer_prompt

    ctx = AIContextBuilder(db)
    sql_system, sql_ctx = ctx.sql_generate_context(beschreibung, connection_id, mapping_id)
    auftrag = f"{sql_ctx}\n\nAufgabe: {beschreibung}" if sql_ctx else f"Aufgabe: {beschreibung}"

    sql_params = params_fuer_prompt(len(sql_system) + len(auftrag))
    svc.timeout = timeout_fuer_prompt(len(sql_system) + len(auftrag), svc.timeout)

    yield {"fortschritt": f"SQL wird erzeugt: {beschreibung[:80]}"}
    sql_text = _sql_saeubern(await svc.complete_with_context(
        auftrag, sql_system, params=sql_params))
    columns, fehler, leer = _sql_pruefen(db, sql_text, connection_id, canvas_nodes)
    verdacht = _joinbefund(sql_text) if not fehler else None

    versuche = 0
    for versuch in REPARATURVERSUCHE:
        if not fehler and not leer and not verdacht:
            break
        versuche = versuch
        befund = fehler or leer or verdacht
        yield {"fortschritt": f"{_lage(fehler, leer, verdacht)}, "
                              f"Reparaturversuch {versuch}: {befund[:110]}"}

        # Bei einem Spaltenfehler zählt Genauigkeit mehr als Sparsamkeit: die
        # echten Spalten der verwendeten Tabellen kommen sofort dazu, dazu das
        # passende Schema – die gesuchte Spalte liegt meist in einer Tabelle,
        # die im SQL noch gar nicht vorkommt.
        spaltenfehler = bool(fehler) and bool(re.search(
            r"Ungültiger Spaltenname|Invalid column name|Ungültiger Objektname|Invalid object name",
            fehler))
        nachschlag = ""
        if spaltenfehler:
            nachschlag = "\n\n" + _spalten_nachschlag(connection_id, sql_text)
        if (versuch == 2 or spaltenfehler) and connection_id:
            conn_obj = ctx._get_conn(connection_id)
            if conn_obj:
                from app.services.ai_context_builder import _schema_fuer_aufgabe
                nachschlag += "\n\n" + _schema_fuer_aufgabe(conn_obj, f"{beschreibung} {befund}")

        reparatur = (f"{auftrag}{nachschlag}\n\nDieses SQL wurde erzeugt:\n{sql_text}\n\n"
                     f"{_urteil(fehler, leer, verdacht)}\n\nAntworte NUR mit dem korrigierten SQL.")
        sql_neu = _sql_saeubern(await svc.complete_with_context(
            reparatur, sql_system, params=sql_params))
        columns_neu, fehler_neu, leer_neu = _sql_pruefen(db, sql_neu, connection_id, canvas_nodes)
        # Eine Reparatur, die zwar läuft, aber weiterhin leer bleibt, ist keine
        # Verschlechterung – der neue Stand wird übernommen.
        sql_text, columns, fehler, leer = sql_neu, columns_neu, fehler_neu, leer_neu
        verdacht = _joinbefund(sql_text) if not fehler else None

    yield {"ergebnis": {
        "sql": sql_text, "columns": columns or [], "fehler": fehler,
        "leer": leer, "warnung": verdacht if not fehler and not leer else None,
        "versuche": versuche}}


async def erzeugen(db, svc, beschreibung: str, connection_id: Optional[int],
                   mapping_id: Optional[int] = None,
                   canvas_nodes: Optional[list] = None,
                   melden=None) -> dict:
    """Dieselbe Kette ohne Datenstrom. `melden(text)` bekommt die Zwischenstände."""
    ergebnis = None
    async for schritt in erzeugen_stufen(db, svc, beschreibung, connection_id,
                                         mapping_id, canvas_nodes):
        if "ergebnis" in schritt:
            ergebnis = schritt["ergebnis"]
        elif melden:
            melden(schritt["fortschritt"])
    return ergebnis or {"sql": "", "columns": [], "fehler": "Kein SQL erzeugt",
                        "leer": None, "warnung": None, "versuche": 0}

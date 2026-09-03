"""Eine Abfrage-Definition rechnen, ohne etwas zu speichern.

Herausgezogen, weil zwei Stellen dasselbe brauchen: der Vorschau-Endpunkt des
Abfrage-Generators und die Vorschau der KI-Werkbank. Zwei Fassungen davon wären
die sichere Art, dass eine von beiden irgendwann gegen den falschen Mandanten
oder ohne Zeitfenster rechnet.
"""
import logging
from datetime import date, timedelta

from sqlalchemy import text

from . import sql_bauer

logger = logging.getLogger(__name__)

VORSCHAU_MAX = 200


class LaufFehler(RuntimeError):
    """Die Abfrage ließ sich nicht ausführen. Der Text geht an den Anwender."""


def rechnen(db, definition: dict, mandant_id: int,
            von: str | None = None, bis: str | None = None,
            limit: int | None = None) -> dict:
    """Baut das SQL und führt es gegen die WaWi des Mandanten aus.

    Gibt zusätzlich das erzeugte SQL zurück: wer es lesen kann, prüft es; wer
    nicht, sieht wenigstens, dass nichts gezaubert wird.
    """
    from app.services import mandant_service
    from app.services.sql_helpers import _resolve_sql_run_params, _get_sql_engine

    definition = dict(definition or {})
    # Immer gedeckelt – eine Abfrage über tKunde ohne Filter trifft 22.000
    # Zeilen und macht die Oberfläche unbenutzbar.
    obergrenze = min(int(limit or definition.get("limit") or VORSCHAU_MAX), VORSCHAU_MAX)
    definition["limit"] = obergrenze

    gebaut = sql_bauer.bauen(definition)     # wirft AbfrageFehler

    bis = bis or date.today().isoformat()
    von = von or (date.today() - timedelta(days=365)).isoformat()

    run = dict(gebaut["params"])
    run.update({"von": von, "bis": bis})
    sql, gebunden = _resolve_sql_run_params(gebaut["sql"], run)

    try:
        eng = _get_sql_engine(mandant_id)
        with eng.connect() as con:
            zeilen = [dict(r) for r in con.execute(text(sql), gebunden).mappings().all()]
    except Exception as e:
        logger.error(f"Abfrage fehlgeschlagen: {e}")
        raise LaufFehler(f"Abfrage fehlgeschlagen: {str(e)[:300]}")

    return {
        "zeilen": zeilen,
        "spalten": gebaut["spalten"],
        "anzahl": len(zeilen),
        "gedeckelt": len(zeilen) >= obergrenze,
        "sql": gebaut["sql"],
        "zeitraum": {"von": von, "bis": bis},
        "mandant": mandant_service.name_von(mandant_id, db),
    }

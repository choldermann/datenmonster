"""Abfrage-Generator: Katalog ausliefern, Vorschau rechnen.

Der Client schickt nie SQL, sondern nur eine Definition aus Schlüsseln des
serverseitigen Katalogs. Alles hier ist lesend.
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.query_builder import katalog, sql_bauer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/query", tags=["query-builder"])

VORSCHAU_MAX = 200


def _check_editor(user: User):
    if getattr(user, "is_portal_only", False):
        raise HTTPException(403, "Nur Admins und Editoren können Abfragen bauen")


class VorschauRequest(BaseModel):
    definition: dict
    project_id: Optional[int] = None
    mandant_id: Optional[int] = None
    von: Optional[str] = None
    bis: Optional[str] = None


@router.get("/schema")
def schema(user: User = Depends(get_current_user)):
    """Körnungen, Felder, Kennzahlen und die je Typ erlaubten Vergleiche."""
    _check_editor(user)
    return katalog.schema()


@router.post("/preview")
def preview(data: VorschauRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    """Rechnet die Abfrage mit Zeilenobergrenze und gibt auch das SQL zurück.

    Das erzeugte SQL wird bewusst mitgeliefert: wer es lesen kann, prüft es;
    wer nicht, sieht wenigstens, dass nichts gezaubert wird.
    """
    _check_editor(user)
    from app.services import mandant_service
    from app.services.sql_helpers import _resolve_sql_run_params, _get_sql_engine

    definition = dict(data.definition or {})
    # Vorschau immer gedeckelt – eine Abfrage über tKunde ohne Filter trifft
    # 22.000 Zeilen und macht die Oberfläche unbenutzbar.
    definition["limit"] = min(int(definition.get("limit") or VORSCHAU_MAX), VORSCHAU_MAX)

    try:
        gebaut = sql_bauer.bauen(definition)
    except sql_bauer.AbfrageFehler as e:
        raise HTTPException(400, str(e))

    # Der Mandant bestimmt, gegen welche Wawi gerechnet wird. Ohne ihn liefe die
    # Vorschau womöglich gegen den anderen Betrieb – Zahlen, die in sich stimmen
    # und trotzdem falsch sind.
    mandant_id = data.mandant_id or mandant_service.aktiver(data.project_id, user, db)
    if not mandant_id:
        raise HTTPException(400, "Kein Mandant gewählt – es ist unklar, gegen welche "
                                 "Warenwirtschaft gerechnet werden soll.")

    bis = data.bis or date.today().isoformat()
    von = data.von or (date.today() - timedelta(days=365)).isoformat()

    run = dict(gebaut["params"])
    run.update({"von": von, "bis": bis})
    sql, gebunden = _resolve_sql_run_params(gebaut["sql"], run)

    try:
        eng = _get_sql_engine(mandant_id)
        with eng.connect() as con:
            zeilen = [dict(r) for r in con.execute(text(sql), gebunden).mappings().all()]
    except Exception as e:
        logger.error(f"Abfrage-Vorschau fehlgeschlagen: {e}")
        raise HTTPException(500, f"Abfrage fehlgeschlagen: {str(e)[:300]}")

    return {
        "zeilen": zeilen,
        "spalten": gebaut["spalten"],
        "anzahl": len(zeilen),
        "gedeckelt": len(zeilen) >= definition["limit"],
        "sql": gebaut["sql"],
        "zeitraum": {"von": von, "bis": bis},
        "mandant": mandant_service.name_von(mandant_id, db),
    }

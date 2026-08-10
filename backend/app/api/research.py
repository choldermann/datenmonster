"""
Fehlende Stammdaten beim Hersteller nachschlagen.

Bisher: EANs für Artikel, die in der Wawi keine haben, deren Hersteller sie aber
auf der Produktseite veröffentlicht. Die Zuordnung läuft über die
Hersteller-Artikelnummer, ist also eindeutig (siehe services/product_research.py).

Bewusst stapelweise: je Artikel fällt ein Seitenabruf beim Hersteller an. Die
Oberfläche holt sich Stapel für Stapel, damit nichts in einen Zeitüberlauf läuft
und die Herstellerseiten nicht mit einem Schwall Anfragen belegt werden.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/research", tags=["research"])
logger = logging.getLogger(__name__)


class EanResearchRequest(BaseModel):
    mapping_id: int              # Mapping mit den Kandidaten (Artikel ohne EAN)
    limit: int = 20              # wie viele Artikel dieser Stapel prüft
    offset: int = 0


@router.get("/manufacturers")
def manufacturers(user: User = Depends(get_current_user)):
    """Für welche Hersteller gibt es einen Adapter?"""
    from app.services.product_research import HERSTELLER
    return [{"id": h["id"], "name": h["name"]} for h in HERSTELLER]


@router.post("/ean")
def ean_research(body: EanResearchRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Einen Stapel Artikel beim Hersteller nachschlagen und EANs vorschlagen."""
    from app.models.mapping import Mapping
    from app.services.mapping_service import MappingContext, execute_mapping
    from app.services.product_research import recherchiere, unterstuetzt
    from app.api.projects import can_read_project

    m = db.query(Mapping).filter(Mapping.id == body.mapping_id).first()
    if not m:
        raise HTTPException(404, "Kandidaten-Mapping nicht gefunden")
    if not can_read_project(m.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Mapping")

    ctx = MappingContext.from_orm(m)
    ctx.run_params = {}
    felder = (ctx.targets[0].get("fields") or []) if ctx.targets else []
    try:
        # row_cap hebt den 50er-Vorschaudeckel auf und deckelt zugleich das SQL –
        # ohne ihn sähen wir nur die ersten 50 Kandidaten.
        ergebnis = execute_mapping(**ctx.to_execute_kwargs(felder, 2000), row_cap=2000)
    except Exception as e:
        raise HTTPException(500, f"Kandidaten konnten nicht ermittelt werden: {str(e)[:200]}")

    alle = ergebnis.get("rows") or []
    # Nur Artikel, für deren Hersteller es einen Adapter gibt und die eine
    # eigenständige Herstellernummer haben – alles andere ist nicht auflösbar.
    machbar = [r for r in alle
               if str(r.get("HAN") or "").strip() and unterstuetzt(r.get("Hersteller") or "")]

    stapel = machbar[body.offset: body.offset + max(1, min(body.limit, 50))]
    vorschlaege, ohne_treffer = [], 0
    for r in stapel:
        try:
            res = recherchiere(r.get("Hersteller") or "", r.get("HAN") or "")
        except Exception as e:
            logger.warning("Recherche fehlgeschlagen (%s): %s", r.get("ArtNr"), e)
            res = None
        eans = {k: v for k, v in (res or {}).get("daten", {}).items()
                if "EAN" in k.upper() and str(v).strip().isdigit()}
        if not eans:
            ohne_treffer += 1
            continue
        vorschlaege.append({
            "kArtikel":   r.get("kArtikel"),
            "ArtNr":      r.get("ArtNr"),
            "Artikel":    r.get("Artikel"),
            "Hersteller": r.get("Hersteller"),
            "HAN":        r.get("HAN"),
            "Bestand":    r.get("Bestand"),
            "eans":       eans,
            "quelle":     res.get("url"),
        })

    return {
        "kandidaten_gesamt":  len(alle),
        "kandidaten_machbar": len(machbar),
        "geprueft":           len(stapel),
        "ohne_treffer":       ohne_treffer,
        "naechster_offset":   body.offset + len(stapel),
        "fertig":             body.offset + len(stapel) >= len(machbar),
        "vorschlaege":        vorschlaege,
    }

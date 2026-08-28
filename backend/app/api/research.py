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
    return [{"id": h["id"], "name": h["name"],
             "liefert_ean": bool(h.get("nummer_aus_url")),
             "liefert_text": bool(h.get("abschnitte"))} for h in HERSTELLER]


class SupportedRequest(BaseModel):
    namen: list[str] = []


@router.post("/supported")
def supported(body: SupportedRequest, user: User = Depends(get_current_user)):
    """Welche der übergebenen Herstellernamen lassen sich auswerten?

    Die Zuordnung Name → Adapter steckt in der Registry (Regex je Hersteller);
    die Oberfläche soll sie nicht nachbauen müssen.
    """
    from app.services.product_research import hersteller_profil
    out = {}
    for name in body.namen[:500]:
        p = hersteller_profil(name or "")
        out[name] = {
            "auswertbar":   bool(p),
            "adapter":      p["name"] if p else None,
            "liefert_ean":  bool(p and p.get("nummer_aus_url")),
            "liefert_text": bool(p and p.get("abschnitte")),
        }
    return out


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
    from app.services import mandant_service
    mandant_service.verbindung_ersetzen(
        ctx, mandant_service.aktiver(m.project_id, user, db), db, m.project_id)
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


# ── Mehrere Felder auf einmal (EAN, Warennummer, Herkunftsland) ─────────────────

class StammdatenRequest(BaseModel):
    hersteller: str                       # Herstellername aus der Wawi
    artikel: list[dict]                   # kArtikel, ArtNr, Artikel, HAN + aktuelle Werte
    felder: list[str] = ["EAN", "Warennummer", "Herkunftsland", "Gewicht"]
    limit: int = 20
    offset: int = 0
    nur_fehlende: bool = True             # nur Felder vorschlagen, die in der Wawi leer sind


def _fehlt(artikel: dict, feld: str) -> bool:
    return not str(artikel.get(feld) or "").strip()


@router.post("/stammdaten")
def stammdaten_research(body: StammdatenRequest, user: User = Depends(get_current_user)):
    """Eine Artikelliste beim Hersteller prüfen und fehlende Angaben vorschlagen.

    Anders als /ean holt das nicht nur die EAN, sondern auch Warennummer und
    Ursprungsland — und liefert je Wert einen Sicherheitsgrad mit Begründung
    (siehe services/stammdaten_research.py). Geschrieben wird hier nichts.
    """
    from app.services.product_research import unterstuetzt
    from app.services.stammdaten_research import FELDER, pruefe_artikel

    if not unterstuetzt(body.hersteller or ""):
        raise HTTPException(400, f"Für „{body.hersteller}“ gibt es keinen Adapter – "
                                 "die Produktseiten lassen sich nicht auswerten")
    felder = tuple(f for f in body.felder if f in FELDER)
    if not felder:
        raise HTTPException(400, "Keine gültigen Felder angefragt")

    # Nachschlagbar ist nur, was eine eigenständige Herstellernummer hat und
    # überhaupt eine Lücke aufweist – alles andere kostet nur einen Seitenabruf.
    machbar = [a for a in body.artikel
               if str(a.get("HAN") or "").strip()
               and (not body.nur_fehlende or any(_fehlt(a, f) for f in felder))]

    stapel = machbar[body.offset: body.offset + max(1, min(body.limit, 50))]
    vorschlaege, ohne_treffer = [], 0
    for a in stapel:
        try:
            res = pruefe_artikel(body.hersteller, str(a.get("HAN") or ""), felder)
        except Exception as e:
            logger.warning("Stammdaten-Recherche fehlgeschlagen (%s): %s", a.get("ArtNr"), e)
            res = None
        gefunden = [v for v in ((res or {}).get("vorschlaege") or [])
                    if not body.nur_fehlende or _fehlt(a, v["feld"])]
        if not gefunden:
            ohne_treffer += 1
            continue
        vorschlaege.append({
            "kArtikel":   a.get("kArtikel"),
            "ArtNr":      a.get("ArtNr"),
            "Artikel":    a.get("Artikel"),
            "HAN":        a.get("HAN"),
            "Bestand":    a.get("Bestand"),
            "quelle":     res.get("quelle"),
            "werte":      gefunden,
        })

    return {
        "kandidaten_gesamt":  len(body.artikel),
        "kandidaten_machbar": len(machbar),
        "geprueft":           len(stapel),
        "ohne_treffer":       ohne_treffer,
        "naechster_offset":   body.offset + len(stapel),
        "fertig":             body.offset + len(stapel) >= len(machbar),
        "vorschlaege":        vorschlaege,
    }

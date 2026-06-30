"""
API-Router für Business-Insights: Presets, Suggest-Mapping, Vorschau-Run.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.insight_engine import suggest_mapping, get_presets, compute_insights

router = APIRouter()


class SuggestRequest(BaseModel):
    columns: list[str]


class InsightsRunRequest(BaseModel):
    dataset_id: int
    semantic: dict[str, Any]
    comparison: dict[str, Any]
    modules: dict[str, bool] | None = None


@router.get("/api/insights/presets")
def list_presets(current_user=Depends(get_current_user)):
    return get_presets()


@router.post("/api/insights/suggest-mapping")
def suggest(body: SuggestRequest, current_user=Depends(get_current_user)):
    return suggest_mapping(body.columns)


@router.post("/api/insights/run")
def run_insights(body: InsightsRunRequest, db: Session = Depends(get_db),
                 current_user=Depends(get_current_user)):
    from app.models.dataset import Dataset
    from app.services.file_service import _load_parquet

    ds = db.query(Dataset).filter(Dataset.id == body.dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")

    try:
        df = _load_parquet(body.dataset_id)
    except Exception as e:
        raise HTTPException(400, f"Dataset konnte nicht geladen werden: {e}")

    findings_df = compute_insights(df, body.semantic, body.comparison, body.modules)
    records = findings_df.where(findings_df.notna(), None).to_dict(orient="records")
    return {"findings": records, "count": len(records)}

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/history")
def get_event_history(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models.event_log import EventLog
    events = (
        db.query(EventLog)
        .order_by(EventLog.received_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "received_at": e.received_at.isoformat() if e.received_at else None,
            "channel": e.channel,
            "plugin_id": e.plugin_id,
            "source_type_id": e.source_type_id,
            "payload": e.payload,
            "triggered_mappings": e.triggered_mappings,
            "status": e.status,
            "error": e.error,
        }
        for e in events
    ]


class TriggerBody(BaseModel):
    plugin_id: str
    source_type_id: str
    payload: dict = {}


@router.post("/trigger")
def manual_trigger(
    body: TriggerBody,
    user: User = Depends(get_current_user),
):
    """Manueller Test-Trigger – veröffentlicht ein Plugin-Event auf dem EventBus."""
    from app.services.eventbus import publish, CHANNEL_PLUGIN_TRIGGER
    payload = {"plugin_id": body.plugin_id, "source_type_id": body.source_type_id, **body.payload}
    publish(CHANNEL_PLUGIN_TRIGGER, payload)
    return {"ok": True, "channel": CHANNEL_PLUGIN_TRIGGER, "payload": payload}

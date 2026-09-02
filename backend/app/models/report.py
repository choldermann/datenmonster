from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean, Text
from datetime import datetime, timezone
from app.core.database import Base

class Report(Base):
    __tablename__ = "reports"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, nullable=False)
    project_id = Column(Integer, nullable=True)
    widgets    = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReportSchedule(Base):
    """Zustellplan eines Reports: wann er läuft, für welchen Zeitraum, an wen.

    Feldschnitt bewusst wie AlertSchedule – beide lösen dieselbe Aufgabe (ein
    Cron-Job, der etwas rechnet und per Mail zustellt), und zwei verschiedene
    Formen davon wären nur eine Fehlerquelle beim nächsten Anfassen.

    Der Report selbst ist ein ganz normales Formular; hier steht nur die
    Zustellung.
    """
    __tablename__ = "report_schedules"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String, nullable=False)
    form_id         = Column(Integer, nullable=False, index=True)
    project_id      = Column(Integer, nullable=True, index=True)
    # Ein Zeitplan gehört einem Mandanten: gerechnet wird gegen dessen WaWi, mit
    # dessen Fixkosten, und das Deckblatt trägt dessen Briefkopf.
    mandant_id      = Column(Integer, nullable=True, index=True)

    cron_expr       = Column(String, default="0 6 * * 1")   # Montags 6:00, Europe/Berlin
    active          = Column(Boolean, default=False)

    zeitraum_preset = Column(String, default="this_month")  # siehe services/zeitraum.py
    params          = Column(JSON, default=dict)            # zusätzliche Laufparameter
    sections        = Column(JSON, default=list)            # Reiter-Auswahl fürs PDF; leer = alles

    email_to        = Column(String, nullable=True)         # kommagetrennt
    email_subject   = Column(String, nullable=True)         # leer = automatischer Betreff

    last_run_at     = Column(DateTime, nullable=True)
    last_status     = Column(String, nullable=True)         # success | error
    last_message    = Column(Text, nullable=True)

    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    created_by      = Column(Integer, nullable=True)

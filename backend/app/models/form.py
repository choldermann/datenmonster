from sqlalchemy import Column, Integer, String, JSON, DateTime, Boolean, Text
from datetime import datetime, timezone
from app.core.database import Base


class FormSubmission(Base):
    """Ein einzelner Formular-Lauf: die eingegebenen Werte + Ergebnis-Zusammenfassung.
    Speichert bewusst NICHT die vollen Ergebnisdaten (können groß sein), nur die
    eingegebenen Parameter und pro Aktion die Zeilenzahl/Status."""
    __tablename__ = "form_submissions"
    id           = Column(Integer, primary_key=True, index=True)
    form_id      = Column(Integer, index=True, nullable=False)
    params       = Column(JSON, default=dict)         # eingegebene Feldwerte
    action_ids   = Column(JSON, nullable=True)         # ausgelöste Aktionen (oder null = alle)
    status       = Column(String, default="success")   # success | error
    error        = Column(Text, nullable=True)
    row_counts   = Column(JSON, default=dict)           # { action_id: anzahl_zeilen }
    submitted_by = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Form(Base):
    __tablename__ = "forms"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    project_id    = Column(Integer, nullable=True)
    schema        = Column(JSON, default=dict)    # { fields, layout, actions, widgets }
    version       = Column(Integer, default=1)
    # Portal / Veröffentlichung
    slug          = Column(String, unique=True, nullable=True)   # /app/<slug>
    published     = Column(Boolean, default=False)
    portal_config = Column(JSON, default=dict)   # { allowed_users, allow_download,
                                                 #   allow_manual_run, allow_save_params,
                                                 #   is_homepage, description, icon }
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    created_by    = Column(Integer, nullable=True)

"""Mandantenfähigkeit der Cockpits: wer darf welche WaWi sehen, und welche sieht er gerade.

Ein Mandant ist keine eigene Entität, sondern eine als Mandant gekennzeichnete
DB-Verbindung (`db_connections.is_mandant`). Dieselben Mappings, Formulare und
Kostendaten-Masken laufen gegen verschiedene JTL-Datenbanken – zur Laufzeit wird
lediglich die `connection_id` der SQL-Knoten ausgetauscht
(mandant_service.verbindung_ersetzen).

Hier liegen die beiden Dinge, die sich pro Benutzer unterscheiden:

MandantFreigabe – WELCHE Mandanten ein Benutzer überhaupt nutzen darf.
    Konvention wie bei der Formular-Veröffentlichung (portal_config.allowed_users):
    **keine Zeile = keine Einschränkung**. Wer nichts einträgt, sieht alle Mandanten
    seiner Projekte; erst ein Eintrag schaltet auf "nur diese". Sonst wäre jede
    bestehende Installation nach dem Update ausgesperrt.

MandantAuswahl – WELCHEN Mandanten er gerade ansieht, je Projekt.
    Bewusst serverseitig und nicht im Browser: eine unsichtbare Sitzungswahl, die
    die Anzeige stillschweigend umbiegt, hat beim KI-Anbieter schon einmal für
    stundenlange Verwirrung gesorgt. Der Server ist die einzige Quelle, jeder Lauf
    (Formular, Drilldown, PDF-Report) löst den Mandanten dort auf.
"""
from sqlalchemy import Column, Integer, DateTime, UniqueConstraint
from datetime import datetime, timezone
from app.core.database import Base


class MandantFreigabe(Base):
    __tablename__ = "mandant_freigaben"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, nullable=False, index=True)
    connection_id = Column(Integer, nullable=False, index=True)
    # Freigaben gelten je Projekt: derselbe Benutzer darf im einen Projekt eine
    # andere WaWi sehen als im anderen. NULL heißt "projektübergreifend" und ist
    # der Zustand aller Freigaben, die vor dieser Unterscheidung entstanden sind.
    project_id    = Column(Integer, nullable=True, index=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "connection_id", "project_id",
                         name="uq_mandant_freigabe"),
    )


class MandantAuswahl(Base):
    __tablename__ = "mandant_auswahl"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, nullable=False, index=True)
    project_id    = Column(Integer, nullable=True, index=True)
    connection_id = Column(Integer, nullable=False)
    updated_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_mandant_auswahl"),
    )

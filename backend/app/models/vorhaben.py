"""Bauvorhaben der KI-Werkbank: der Auftrag, sein Bauplan und was daraus wurde.

Warum ein eigenes Objekt und nicht nur ein Chatverlauf: Ein Vorhaben legt
mehrere Dinge gleichzeitig an (Abfrage, Report, Zustellplan …). Ohne
Herkunftsstempel ließe sich das später weder ändern noch zurückbauen – und
genau daran ist in dieser Plattform schon mehrfach etwas zerbrochen
(Waisen-Aktionen beim Umbenennen, doppelte Aktions-IDs).
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime
from datetime import datetime, timezone

from app.core.database import Base


class Vorhaben(Base):
    """Ein Bauauftrag des Anwenders samt Bauplan.

    `beschreibung` ist der **Originalsatz**, wörtlich. Er bleibt in jedem
    KI-Schritt dabei und schlägt im Zweifel jede Umformulierung – aus
    „dieses Jahr" wurde im Baumodus schon einmal „das Jahr 2023", weil nur die
    Umformulierung weitergereicht wurde.

    `bauplan` ist die Liste der Schritte:
        [{"werkzeug": "abfrage", "aktiv": true, "titel": "…",
          "warum": "…", "eingabe": {…}}, …]
    Ein Schritt mit `aktiv: false` ist vom Anwender abgewählt und wird
    übersprungen; er bleibt im Plan stehen, damit er wieder angehakt werden kann.
    """

    __tablename__ = "vorhaben"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, nullable=False)
    beschreibung = Column(Text, nullable=True)      # der Originalsatz, wörtlich
    project_id   = Column(Integer, nullable=True, index=True)
    # Gegen welche WaWi gebaut und gerechnet wird. Ohne diese Angabe fiele ein
    # späterer Lauf ohne angemeldeten Benutzer auf den Projekt-Standard zurück
    # und rechnete stumm den falschen Betrieb – der Zustellplan-Fehler.
    mandant_id   = Column(Integer, nullable=True, index=True)

    status       = Column(String, default="entwurf")  # entwurf | installiert | zurueckgebaut
    bauplan      = Column(JSON, default=list)
    verlauf      = Column(JSON, default=list)        # Rückfragen/Antworten, nachvollziehbar
    hinweise     = Column(JSON, default=list)        # was der Planer angemerkt hat

    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    created_by   = Column(Integer, nullable=True)
    gebaut_am    = Column(DateTime, nullable=True)
    zurueckgebaut_am = Column(DateTime, nullable=True)


class VorhabenArtefakt(Base):
    """Ein Objekt, das ein Vorhaben angelegt oder verändert hat.

    **`erzeugt` ist das wichtigste Feld dieses Modells.**

    * `erzeugt = True`  – das Objekt gehört uns. Der Rückbau löscht es.
    * `erzeugt = False` – wir haben ein **vorgefundenes** Objekt nur ergänzt.
      Der Rückbau entfernt ausschließlich unsere Zutat und stellt `vorher`
      wieder her.

    Ohne diese Unterscheidung löscht der erste Rückbau fremde Arbeit mit. Der
    Fall tritt sofort ein: das Sammelformular „Eigene Auswertungen" ist der Ort,
    an dem die nächste Auswertung landet, und darf nie verschwinden – auch dann
    nicht, wenn dieses Vorhaben es angelegt hat.
    """

    __tablename__ = "vorhaben_artefakte"

    id          = Column(Integer, primary_key=True, index=True)
    vorhaben_id = Column(Integer, nullable=False, index=True)
    schritt     = Column(Integer, default=0)      # Index im Bauplan
    werkzeug    = Column(String, nullable=True)   # welches Werkzeug es angelegt hat

    # mapping | form | widget | adhoc_query | report_schedule | alert_rule
    # | portal | pipeline
    art         = Column(String, nullable=False)
    ziel_id     = Column(Integer, nullable=True)  # Mapping.id, Form.id …
    ziel_key    = Column(String, nullable=True)   # widget_id / action_id / rule_key
    label       = Column(String, nullable=True)   # Klartext für die Anzeige

    erzeugt     = Column(Boolean, default=True)
    vorher      = Column(JSON, nullable=True)     # Zustand davor (nur bei erzeugt=False)

    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

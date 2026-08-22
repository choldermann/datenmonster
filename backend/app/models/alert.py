from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime, Float, UniqueConstraint
from datetime import datetime, timezone
from app.core.database import Base


class AlertRule(Base):
    """Eine Unternehmenswarnung als DATEN, nicht als Code.

    Grundregel des Systems: Die Zahl kommt aus SQL (einem ganz normalen Mapping),
    die Regel entscheidet nur, AB WANN daraus eine Warnung wird und wie dringend
    sie ist. Es wird nichts geschätzt, gerundet oder vom Modell erfunden.

    Quelle: mapping_id ODER mapping_name. Der Name ist der Regelfall, weil die
    Warnungen auf Mappings anderer Templates aufsetzen (GF-, Lager-, Einkaufs-
    Cockpit …) und deren IDs je Installation verschieden sind. Fehlt das Mapping,
    wird die Regel als "nicht verfügbar" gemeldet – kein Fehler.

    condition (JSON), je nach mode:
      {"mode": "count", "min_count": 1, "value_column": "Wert"}
          → eine Warnung, sobald die Ergebnisliste Zeilen hat (die SQL-Abfrage
            selbst definiert, was ein Problem ist). Anzahl + Summenwert im Text.
      {"mode": "kpi", "column": "Umsatz", "op": "<",
       "compare_column": "UmsatzVJ", "factor": 0.95}
          → vergleicht Werte EINER Kennzahlenzeile, optional gegen einen
            Schwellwert aus der business_config ("value_config": "oos_tage").
      {"mode": "rows", "limit": 5, "label_column": "Kunde", "value_column": "Betrag"}
          → jede Zeile wird zu einer eigenen Warnung (für Einzelfälle).

    severity_levels (JSON, optional): Eskalation, z.B.
      [{"metric": "wert", "op": ">=", "value": 10000, "severity": "kritisch"}]
      Der erste Treffer gewinnt, sonst greift severity.

    facts (JSON): [{"label": "Ø Absatz/Tag", "column": "AbsatzTag", "unit": ""}]
      – die nachvollziehbaren Fakten hinter der Warnung (Anforderung: der Anwender
        muss sehen, WARUM gewarnt wird).
    """

    __tablename__ = "alert_rules"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(Integer, nullable=True, index=True)
    rule_key        = Column(String, nullable=False, index=True)
    name            = Column(String, nullable=False)
    description     = Column(Text, nullable=True)
    category        = Column(String, default="allgemein")   # Geschäftsführung, Liquidität, Lager …
    cockpit         = Column(String, nullable=True)          # Herkunfts-Cockpit (nur Anzeige)
    severity        = Column(String, default="warnung")      # kritisch|warnung|hinweis|info|positiv
    severity_levels = Column(JSON, default=list)
    mapping_id      = Column(Integer, nullable=True)
    mapping_name    = Column(String, nullable=True)
    params          = Column(JSON, default=dict)             # zusätzliche run_params der Regel
    condition       = Column(JSON, default=dict)
    facts           = Column(JSON, default=list)
    title_template  = Column(String, nullable=True)          # "{anzahl} überfällige Forderungen"
    subtitle        = Column(String, nullable=True)          # Handlungshinweis im Klartext
    drilldown       = Column(JSON, default=dict)             # {mapping_name|mapping_id, title, hidden_columns}
    action_kind     = Column(String, nullable=True)          # KI-Empfehlungstyp (recommend-action)
    active          = Column(Boolean, default=True)
    sort            = Column(Integer, default=100)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("project_id", "rule_key", name="uq_alert_rule_key"),
    )


class AlertRun(Base):
    """Ergebnis eines Warnungs-Laufs. Wird persistiert, damit der Monitor den
    letzten Stand sofort zeigen kann, statt bei jedem Aufruf 30+ Abfragen gegen
    die produktive WaWi zu fahren."""

    __tablename__ = "alert_runs"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer, nullable=True, index=True)
    started_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    duration_ms = Column(Float, nullable=True)
    params      = Column(JSON, default=dict)      # Zeitraum/Filter des Laufs
    alerts      = Column(JSON, default=list)      # ausgelöste Warnungen (Anzeigeform)
    checked     = Column(Integer, default=0)      # geprüfte Regeln
    triggered   = Column(Integer, default=0)      # davon ausgelöst
    errors      = Column(JSON, default=list)

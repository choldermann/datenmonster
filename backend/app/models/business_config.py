from sqlalchemy import Column, Integer, String, JSON, DateTime, UniqueConstraint
from datetime import datetime, timezone
from app.core.database import Base


class BusinessConfig(Base):
    """Projektbezogene Geschäftsparameter: Schwellwerte, Kostensätze und Ziele.

    Bisher steckten solche Werte als {{platzhalter}} im Template und wurden beim
    Installieren fest in den SQL-Text substituiert – danach waren sie nicht mehr
    änderbar. Hier leben sie als Laufzeit-Konfiguration und werden über
    business_config_service.apply_config() als :cfg_<key> in jeden Mapping-Lauf
    injiziert (Muster: article_exclusion_service).

    scope trennt die Namensräume:
      threshold – Schwellwerte für Warnungen (Ladenhüter-Tage, Marge-Minimum …)
      cost      – monatliche Fixkosten je Kostenart (Miete, Personal, Strom …)
      goal      – Unternehmensziele (Jahresumsatz, DB-Marge …)

    value ist bewusst JSON: Schwellwerte sind Zahlen, Kostenarten und Ziele sind
    Objekte. Eine Kostenart trägt ihre zeitliche Entwicklung in sich –
    {"eintraege": [{"gueltig_ab": "2025-01-01", "betrag": 2400}, …]}, jeweils
    gültig bis zur nächsten Scheibe. Eigene Kostenarten (Schlüssel "x_…") legen
    zusätzlich label/gruppe/gruppe_key im Wert ab, Standardarten holen das aus
    business_config_service.COST_DEFAULTS.
    """

    __tablename__ = "business_config"

    id         = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)
    scope      = Column(String, nullable=False, default="threshold")
    key        = Column(String, nullable=False)
    value      = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("project_id", "scope", "key", name="uq_business_config_key"),
    )

from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class CustomerExclusion(Base):
    """Kunden, die aus Verkaufs- und Abfluss-Auswertungen herausfallen sollen –
    typischerweise verbundene Unternehmen und die eigene Firma, an die zwar Ware
    geliefert, aber außerhalb der WaWi abgerechnet wird.

    Ohne diese Liste verwässert eine Abfluss-Analyse: die Konzernlieferung ist
    mengenmäßig der größte „Kunde" und verdeckt, wer die Ware wirklich kauft.
    JTL bietet dafür kein Kennzeichen an – die Kundengruppen bilden etwas
    anderes ab (Preisstufen), und `cSperre` heißt nur „gesperrt".

    Matcht über die interne JTL-ID (kKunde), stabil auch bei Umbenennung.
    Achtung: derselbe Betrieb kann in der WaWi mehrfach angelegt sein – dann
    gehören alle Datensätze in die Liste, sonst fehlt die Hälfte der Menge.
    """

    __tablename__ = "customer_exclusions"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, nullable=True, index=True)
    connection_id = Column(Integer, nullable=True)   # JTL-DB, in der kKunde gilt
    k_kunde       = Column(Integer, nullable=False, index=True)
    kunden_nr     = Column(String, nullable=True)    # cKundenNr – nur Anzeige
    name          = Column(String, nullable=True)    # Firma/Name – nur Anzeige
    grund         = Column(Text, nullable=True)      # warum ausgeschlossen
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Mandantenfähig wie die Artikel-Ausschlussliste: dieselbe kKunde-Nummer
        # bezeichnet in einer anderen WaWi einen anderen Kunden.
        UniqueConstraint("project_id", "connection_id", "k_kunde",
                        name="uq_customer_excl_mandant_kunde"),
    )

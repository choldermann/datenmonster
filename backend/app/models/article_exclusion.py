from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class ArticleExclusion(Base):
    """Artikel, die aus statistischen Auswertungen (z.B. Intrastat) herausgefiltert
    werden sollen – z.B. Verpackungsmaterial wie Europaletten. Gilt pro Projekt und
    matcht über die interne JTL-Artikel-ID (kArtikel), stabil auch bei Umbenennung
    der Artikelnummer. art_nr/name werden nur zur Anzeige gecacht."""

    __tablename__ = "article_exclusions"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, nullable=True, index=True)
    connection_id = Column(Integer, nullable=True)   # JTL-DB-Verbindung, aus der der Artikel stammt
    k_artikel     = Column(Integer, nullable=False, index=True)  # interne JTL-ID (dbo.tArtikel.kArtikel)
    art_nr        = Column(String, nullable=True)    # cArtNr – nur Anzeige
    name          = Column(String, nullable=True)    # cName  – nur Anzeige
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # Mandantenfähig: dieselbe kArtikel-Nummer bezeichnet in einer anderen
        # WaWi einen anderen Artikel, deshalb gehört die Verbindung in den Schlüssel.
        UniqueConstraint("project_id", "connection_id", "k_artikel",
                        name="uq_article_excl_mandant_artikel"),
    )

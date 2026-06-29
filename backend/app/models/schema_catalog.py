from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class SchemaTableMeta(Base):
    __tablename__ = "schema_table_meta"

    id              = Column(Integer, primary_key=True, index=True)
    connection_id   = Column(Integer, nullable=False, index=True)
    table_full_name = Column(String, nullable=False)   # "dbo.tArtikel"
    business_name   = Column(String, nullable=True)    # "Artikel"
    description     = Column(Text, nullable=True)      # "JTL Artikelstammdaten"
    category        = Column(String, nullable=True)    # "Stammdaten" | "Bewegungsdaten" | ...
    is_important    = Column(Boolean, default=False)   # in Vorschlägen bevorzugen
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class SchemaColumnMeta(Base):
    __tablename__ = "schema_column_meta"

    id              = Column(Integer, primary_key=True, index=True)
    connection_id   = Column(Integer, nullable=False, index=True)
    table_full_name = Column(String, nullable=False)
    column_name     = Column(String, nullable=False)
    description     = Column(Text, nullable=True)      # "Netto-Einkaufspreis in EUR"
    example_values  = Column(String, nullable=True)    # "0.00, 12.50, 99.99"


class SchemaRelationMeta(Base):
    """Manuelle FK-Definitionen – wichtig für DBs ohne FK-Constraints (z.B. JTL Wawi)."""
    __tablename__ = "schema_relation_meta"

    id           = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, nullable=False, index=True)
    from_table   = Column(String, nullable=False)   # "Rechnung.tRechnungPosition"
    from_col     = Column(String, nullable=False)   # "kArtikel"
    to_table     = Column(String, nullable=False)   # "dbo.tArtikel"
    to_col       = Column(String, nullable=False)   # "kArtikel"
    description  = Column(String, nullable=True)    # "Artikel der Rechnungsposition"

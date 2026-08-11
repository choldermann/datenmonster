from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class ApiCollection(Base):
    """
    Sammlung von Requests (= RestSources) einer API.

    Bündelt gemeinsame Vorgaben: Basis-URL, Standard-Header und Standard-Auth.
    Ein Request erbt diese Vorgaben, kann sie aber einzeln überschreiben.
    """
    __tablename__ = "api_collections"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String,  nullable=False)
    project_id  = Column(Integer, nullable=True)
    description = Column(Text,    nullable=True)

    base_url        = Column(String, nullable=True)   # https://api.example.com/v1
    default_headers = Column(JSON,   default=dict)    # {"Accept": "application/json"}
    auth_type       = Column(String, default="none")  # wie RestSource.auth_type
    auth_config     = Column(JSON,   default=dict)    # Secrets verschlüsselt (Fernet)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ApiEnvironment(Base):
    """
    Umgebung mit Variablen ({{var}}) – z.B. "Test" vs. "Produktion".

    Variablen landen im bestehenden {{template}}-System von rest_service und
    überschreiben dort nichts: die eingebauten Datums-Variablen ({{heute}} …)
    gewinnen, damit bestehende Connectors sich nicht ändern.

    variables: [{ "key": "host", "value": "…", "secret": false }, …]
    Werte mit secret=true werden verschlüsselt gespeichert und maskiert ausgeliefert.
    """
    __tablename__ = "api_environments"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String,  nullable=False)
    project_id    = Column(Integer, nullable=True)
    collection_id = Column(Integer, nullable=True)   # None = projektweit gültig
    variables     = Column(JSON,    default=list)
    is_default    = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ApiRequestHistory(Base):
    """
    Verlauf ausgeführter Requests.

    Standardmäßig werden nur Metadaten gespeichert (Status, Dauer, Größe).
    Response-Körper nur, wenn der Nutzer das am Request ausdrücklich einschaltet
    (store_response) – Antworten können personenbezogene Daten enthalten.
    Secrets werden vor dem Speichern maskiert.
    """
    __tablename__ = "api_request_history"

    id             = Column(Integer, primary_key=True, index=True)
    project_id     = Column(Integer, nullable=True)
    rest_source_id = Column(Integer, nullable=True)   # None = Ad-hoc-Request
    user_id        = Column(Integer, nullable=True)

    name          = Column(String,  nullable=True)
    method        = Column(String,  nullable=True)
    url           = Column(Text,    nullable=True)    # aufgelöst, ohne Secrets
    status_code   = Column(Integer, nullable=True)
    ok            = Column(Integer, default=0)
    duration_ms   = Column(Integer, nullable=True)
    response_size = Column(Integer, nullable=True)
    error         = Column(Text,    nullable=True)

    request_snapshot = Column(JSON, default=dict)     # maskierte Request-Konfiguration
    response_body    = Column(Text, nullable=True)    # nur wenn ausdrücklich gewünscht

    created_at = Column(DateTime(timezone=True), server_default=func.now())

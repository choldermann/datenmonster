"""
Datenmonster Tier-2 Plugin: Faker Datengenerator
Generiert synthetische Testdaten. Implementiert das Tier-2 Plugin-Protokoll.

Konfigurations-Felder:
  locale    – Sprache/Region (de_DE, en_US, fr_FR, ...)
  fields    – Komma-getrennte Faker-Felder (z.B. "name,email,city")
  num_rows  – Anzahl zu generierender Zeilen
"""

import logging
import os
from typing import List, Optional

import requests
from faker import Faker
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PLUGIN_ID = os.getenv("PLUGIN_ID", "faker-source")
PLUGIN_MANAGER_URL = os.getenv("PLUGIN_MANAGER_URL", "http://plugin-manager:9001")


def fire_event(payload: dict = {}):
    """Signalisiert dem Backend via EventBus, dass neue Daten verfügbar sind."""
    try:
        requests.post(
            f"{PLUGIN_MANAGER_URL}/plugins/{PLUGIN_ID}/event",
            json={"payload": payload},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning(f"EventBus fire_event fehlgeschlagen: {e}")

app = FastAPI(title="Datenmonster Plugin: Faker Datengenerator", version="1.0.0")

# Alle unterstützten Faker-Felder (Methoden auf dem Faker-Objekt)
SUPPORTED_FIELDS = [
    "name", "first_name", "last_name",
    "email", "phone_number",
    "city", "country", "address", "postcode", "street_address",
    "company", "job", "bs",
    "date_of_birth", "date_this_century", "date_this_decade",
    "uuid4", "url", "ipv4", "user_agent",
    "credit_card_number", "iban", "currency_code",
    "color_name", "hex_color",
    "sentence", "word", "paragraph",
    "boolean", "pyint", "pyfloat",
]

MANIFEST = {
    "id": "faker-source",
    "name": "Faker Datengenerator",
    "version": "1.0.0",
    "description": "Generiert synthetische Testdaten mit der Faker-Bibliothek. Ideal für Tests und Demo-Pipelines.",
    "author": "Holdermann IT",
    "license": "free",
    "capabilities": ["source"],
    "source_type_id": "faker",
    "source_type_label": "Faker Datengenerator",
    "source_type_icon": "sparkles",
    "config_schema": [
        {
            "key": "locale",
            "label": "Sprache",
            "type": "select",
            "default": "de_DE",
            "options": ["de_DE", "en_US", "en_GB", "fr_FR", "es_ES", "it_IT", "nl_NL", "pl_PL"],
        },
        {
            "key": "fields",
            "label": "Felder (kommagetrennt)",
            "type": "string",
            "default": "name,email,phone_number,city,company",
            "placeholder": "name,email,city,company",
        },
        {
            "key": "num_rows",
            "label": "Anzahl Zeilen",
            "type": "number",
            "default": 100,
        },
    ],
}


def _parse_fields(config: dict) -> List[str]:
    raw = config.get("fields", "name,email,phone_number,city,company")
    return [f.strip() for f in raw.split(",") if f.strip()]


def _make_faker(config: dict) -> Faker:
    locale = config.get("locale", "de_DE")
    try:
        return Faker(locale)
    except Exception:
        return Faker("de_DE")


def _generate_row(fake: Faker, fields: List[str]) -> dict:
    row = {}
    for field in fields:
        try:
            generator = getattr(fake, field, None)
            if callable(generator):
                val = generator()
                # Datum/Zeit-Objekte zu String konvertieren
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                row[field] = str(val) if val is not None else ""
            else:
                row[field] = ""
        except Exception:
            row[field] = ""
    return row


# ── Tier-2 Plugin Protokoll ───────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "plugin": MANIFEST["id"]}


@app.get("/manifest")
def manifest():
    return MANIFEST


class RequestBody(BaseModel):
    config: dict = {}
    rows: Optional[List[dict]] = None


@app.post("/test")
def test_connection(body: RequestBody):
    config = body.config
    fields = _parse_fields(config)
    fake = _make_faker(config)

    unknown = [f for f in fields if not hasattr(fake, f)]
    if unknown:
        return {
            "ok": False,
            "message": f"Unbekannte Felder: {', '.join(unknown)}. "
                       f"Verfügbar: {', '.join(SUPPORTED_FIELDS[:10])} ...",
        }

    # Einen Test-Datensatz generieren
    sample = _generate_row(fake, fields[:3])
    num_rows = int(config.get("num_rows", 100))
    return {
        "ok": True,
        "message": f"Konfiguration OK. Generiere {num_rows} Zeilen mit {len(fields)} Feldern. "
                   f"Beispiel: {sample}",
    }


@app.post("/schema")
def get_schema(body: RequestBody):
    fields = _parse_fields(body.config)
    return {"columns": fields}


@app.post("/fetch")
def fetch_data(body: RequestBody):
    config = body.config
    fields = _parse_fields(config)
    num_rows = min(int(config.get("num_rows", 100)), 100_000)
    fake = _make_faker(config)

    Faker.seed(0)  # Reproduzierbare Ergebnisse wenn gewünscht
    rows = [_generate_row(fake, fields) for _ in range(num_rows)]
    logger.info(f"Faker: {num_rows} Zeilen generiert ({len(fields)} Felder, locale={config.get('locale','de_DE')})")
    return {"rows": rows}


@app.post("/write")
def write_data(body: RequestBody):
    rows = body.rows or []
    logger.info(f"Faker write: {len(rows)} Zeilen empfangen (werden verworfen – read-only Plugin)")
    return {
        "written": 0,
        "errors": ["Faker Datengenerator ist read-only und unterstützt kein Schreiben."],
    }

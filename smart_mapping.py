"""
Smart Mapping Service
Analysiert verfügbare Datasets + DB-Schema und schlägt automatisch
Tabellen + JOINs für ein Mapping vor.

Stufe 1: Keyword-Matching + FK-Traversal (kostenlos, offline)
Stufe 2: Claude API (optional, wenn API-Key konfiguriert)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.dataset import Dataset, DbConnection
from app.api.settings import get_setting

router = APIRouter(prefix="/api/smart-mapping", tags=["smart-mapping"])

# ── JTL Presets ───────────────────────────────────────────────────────────────
JTL_PRESETS = {
    "rechnungen": {
        "label": "Rechnungsübersicht",
        "tables": ["tRechnung", "tKunde"],
        "description": "Rechnungen mit Kundendaten",
    },
    "offene_rechnungen": {
        "label": "Offene Rechnungen",
        "tables": ["tRechnung", "tKunde", "tZahlung"],
        "description": "Offene Rechnungen mit Zahlungsstatus",
    },
    "bestellungen": {
        "label": "Bestellungen",
        "tables": ["tBestellung", "tBestellPos", "tArtikel", "tKunde"],
        "description": "Bestellungen mit Positionen und Artikeln",
    },
    "artikel": {
        "label": "Artikelstamm",
        "tables": ["tArtikel", "tArtikelBeschreibung"],
        "description": "Artikel mit Beschreibungen",
    },
    "lieferanten": {
        "label": "Lieferanten",
        "tables": ["tLieferant", "tLieferantAdresse"],
        "description": "Lieferantenstammdaten",
    },
}

# ── Synonyme für Keyword-Matching ─────────────────────────────────────────────
SYNONYMS = {
    "rechnung":    ["rechnung", "invoice", "beleg", "faktura", "billing"],
    "kunde":       ["kunde", "customer", "client", "kontakt", "kunden"],
    "bestellung":  ["bestellung", "order", "auftrag", "bestellungen"],
    "artikel":     ["artikel", "article", "produkt", "product", "item", "ware"],
    "zahlung":     ["zahlung", "payment", "bezahlung", "transaktion"],
    "lieferant":   ["lieferant", "supplier", "vendor", "lieferanten"],
    "lager":       ["lager", "stock", "inventory", "warenbestand"],
    "adresse":     ["adresse", "address", "anschrift"],
    "position":    ["position", "pos", "zeile", "line", "detail"],
}


def _keyword_match(text: str, tables: list) -> list:
    """Findet Tabellen deren Name zu den Keywords im Text passt."""
    text_lower = text.lower()
    matched = []

    # Sammle alle relevanten Synonymgruppen
    active_groups = []
    for group, synonyms in SYNONYMS.items():
        if any(s in text_lower for s in synonyms):
            active_groups.append(group)

    for table in tables:
        table_lower = table["name"].lower()
        # Direkte Übereinstimmung mit Synonymen
        for group in active_groups:
            if any(s in table_lower for s in SYNONYMS[group]):
                if table not in matched:
                    matched.append(table)
                break

    return matched


def _fk_traversal(matched_tables: list, all_tables: list, relationships: list) -> list:
    """Findet via FK-Traversal verbundene Tabellen."""
    matched_keys = {t["key"] for t in matched_tables}
    result = list(matched_tables)

    # Füge Tabellen hinzu die direkt per FK verbunden sind
    for rel in relationships:
        if rel["type"] != "foreign_key":
            continue
        from_in = rel["from_table"] in matched_keys
        to_in = rel["to_table"] in matched_keys
        if from_in and not to_in:
            t = next((t for t in all_tables if t["key"] == rel["to_table"]), None)
            if t and t not in result:
                result.append(t)
                matched_keys.add(t["key"])
        elif to_in and not from_in:
            t = next((t for t in all_tables if t["key"] == rel["from_table"]), None)
            if t and t not in result:
                result.append(t)
                matched_keys.add(t["key"])

    return result


def _get_relevant_joins(table_keys: set, relationships: list) -> list:
    """Gibt nur die Beziehungen zurück die zwischen den gewählten Tabellen bestehen."""
    return [
        r for r in relationships
        if r["from_table"] in table_keys and r["to_table"] in table_keys
    ]


# ── Request/Response Models ───────────────────────────────────────────────────

class SmartMappingRequest(BaseModel):
    query: str  # Freitext oder Preset-ID
    preset: Optional[str] = None  # JTL Preset Key
    connection_id: Optional[int] = None  # DB-Verbindung für Schema-Analyse
    project_id: Optional[int] = None
    use_ai: bool = False  # Claude API verwenden


class SuggestedTable(BaseModel):
    key: str
    name: str
    schema: str
    columns: list
    already_exists: bool
    dataset_id: Optional[int] = None


class SmartMappingResponse(BaseModel):
    tables: list
    joins: list
    used_ai: bool = False
    preset_used: Optional[str] = None
    message: str = ""


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/suggest")
def suggest_mapping(
    body: SmartMappingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Analysiert Query/Preset und schlägt Tabellen + JOINs vor.
    Prüft welche Tabellen bereits als Dataset vorhanden sind.
    """
    tables = []
    joins = []
    used_ai = False
    preset_used = None

    # ── Stufe 1: JTL Preset ──────────────────────────────────────────────────
    if body.preset and body.preset in JTL_PRESETS:
        preset = JTL_PRESETS[body.preset]
        preset_used = body.preset
        table_names = preset["tables"]

        # Aus DB-Schema laden wenn Verbindung angegeben
        if body.connection_id:
            try:
                conn = db.query(DbConnection).filter(DbConnection.id == body.connection_id).first()
                if conn:
                    from sqlalchemy import create_engine, inspect
                    from app.services.db_service import get_engine_str
                    engine = create_engine(get_engine_str(conn))
                    inspector = inspect(engine)
                    SKIP = {"sys","INFORMATION_SCHEMA","guest","db_owner","db_accessadmin",
                            "db_securityadmin","db_ddladmin","db_backupoperator",
                            "db_datareader","db_datawriter","db_denydatareader","db_denydatawriter"}

                    for tname in table_names:
                        # Suche in allen Schemas
                        found = False
                        for schema in [s for s in inspector.get_schema_names() if s not in SKIP]:
                            try:
                                db_tables = inspector.get_table_names(schema=schema)
                                if tname in db_tables:
                                    cols = inspector.get_columns(tname, schema=schema)
                                    pk_info = inspector.get_pk_constraint(tname, schema=schema)
                                    pk_cols = set(pk_info.get("constrained_columns", []))
                                    table_key = f"{schema}.{tname}"
                                    tables.append({
                                        "key": table_key,
                                        "name": tname,
                                        "schema": schema,
                                        "columns": [{"name": c["name"], "type": str(c["type"]), "is_primary": c["name"] in pk_cols} for c in cols],
                                    })
                                    found = True
                                    break
                            except Exception:
                                pass
                        if not found:
                            # Fallback ohne Schema-Info
                            tables.append({"key": tname, "name": tname, "schema": "dbo", "columns": []})
            except Exception as e:
                pass
        else:
            # Ohne DB-Verbindung: nur Namen
            for tname in table_names:
                tables.append({"key": tname, "name": tname, "schema": "dbo", "columns": []})

    # ── Stufe 2: Keyword-Matching + FK-Traversal ─────────────────────────────
    elif body.connection_id and body.query:
        try:
            conn = db.query(DbConnection).filter(DbConnection.id == body.connection_id).first()
            if conn:
                from sqlalchemy import create_engine, inspect
                from app.services.db_service import get_engine_str
                engine = create_engine(get_engine_str(conn))
                inspector = inspect(engine)
                SKIP = {"sys","INFORMATION_SCHEMA","guest","db_owner","db_accessadmin",
                        "db_securityadmin","db_ddladmin","db_backupoperator",
                        "db_datareader","db_datawriter","db_denydatareader","db_denydatawriter"}

                # Alle Tabellen + FKs laden
                all_tables = []
                all_rels = []
                for schema in [s for s in inspector.get_schema_names() if s not in SKIP]:
                    try:
                        for tname in inspector.get_table_names(schema=schema):
                            table_key = f"{schema}.{tname}"
                            all_tables.append({"key": table_key, "name": tname, "schema": schema, "columns": []})
                            try:
                                for fk in inspector.get_foreign_keys(tname, schema=schema):
                                    ref_schema = fk.get("referred_schema") or schema
                                    ref_table = fk.get("referred_table", "")
                                    ref_key = f"{ref_schema}.{ref_table}"
                                    for col, ref_col in zip(fk.get("constrained_columns",[]), fk.get("referred_columns",[])):
                                        all_rels.append({"type":"foreign_key","from_table":table_key,"from_col":col,"to_table":ref_key,"to_col":ref_col})
                            except Exception:
                                pass
                    except Exception:
                        pass

                # Keyword-Matching
                matched = _keyword_match(body.query, all_tables)

                # FK-Traversal
                if matched:
                    matched = _fk_traversal(matched, all_tables, all_rels)

                # Spalten für gematchte Tabellen laden
                for t in matched:
                    try:
                        cols = inspector.get_columns(t["name"], schema=t["schema"])
                        pk_info = inspector.get_pk_constraint(t["name"], schema=t["schema"])
                        pk_cols = set(pk_info.get("constrained_columns", []))
                        t["columns"] = [{"name": c["name"], "type": str(c["type"]), "is_primary": c["name"] in pk_cols} for c in cols]
                    except Exception:
                        pass

                tables = matched
                joins = _get_relevant_joins({t["key"] for t in matched}, all_rels)

        except Exception as e:
            raise HTTPException(400, f"Schema-Analyse fehlgeschlagen: {str(e)[:300]}")

    # ── Stufe 3: Claude API (optional) ───────────────────────────────────────
    if body.use_ai and tables:
        api_key = get_setting(db, "claude_api_key", "")
        if api_key:
            try:
                import httpx, json as _json
                schema_summary = "\n".join([f"- {t['key']} ({', '.join(c['name'] for c in t['columns'][:5])}...)" for t in tables[:20]])
                prompt = f"""Du bist ein Datenbankexperte. Der User möchte: "{body.query}"

Verfügbare Tabellen:
{schema_summary}

Welche dieser Tabellen sind für die Anfrage relevant? Antworte NUR mit einem JSON-Array der Table-Keys.
Beispiel: ["dbo.tRechnung", "dbo.tKunde"]"""

                resp = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-haiku-4-5-20251001", "max_tokens": 200, "messages": [{"role": "user", "content": prompt}]},
                    timeout=15,
                )
                if resp.status_code == 200:
                    text = resp.json()["content"][0]["text"].strip()
                    # JSON extrahieren
                    import re
                    match = re.search(r'\[.*?\]', text, re.DOTALL)
                    if match:
                        ai_keys = _json.loads(match.group())
                        tables = [t for t in tables if t["key"] in ai_keys]
                        joins = _get_relevant_joins({t["key"] for t in tables}, joins)
                        used_ai = True
            except Exception:
                pass  # Fallback auf Keyword-Matching

    # ── Existierende Datasets prüfen ─────────────────────────────────────────
    existing_datasets = {}
    if body.project_id:
        existing = db.query(Dataset).filter(Dataset.project_id == body.project_id).all()
        for ds in existing:
            # Matching: Dataset-Name enthält Tabellenname oder umgekehrt
            for t in tables:
                if t["name"].lower() in ds.name.lower() or ds.name.lower() in t["name"].lower():
                    existing_datasets[t["key"]] = ds.id

    # Response aufbauen
    result_tables = []
    for t in tables:
        ds_id = existing_datasets.get(t["key"])
        result_tables.append({
            "key": t["key"],
            "name": t["name"],
            "schema": t.get("schema", "dbo"),
            "columns": t.get("columns", []),
            "already_exists": ds_id is not None,
            "dataset_id": ds_id,
        })

    # JOIN-Vorschläge vereinfachen
    result_joins = []
    for rel in joins[:20]:  # max 20 JOINs
        result_joins.append({
            "from_table": rel["from_table"],
            "from_col": rel["from_col"],
            "to_table": rel["to_table"],
            "to_col": rel["to_col"],
            "type": "INNER JOIN",
        })

    msg = f"{len(result_tables)} Tabellen erkannt"
    if used_ai:
        msg += " (KI-unterstützt)"
    elif preset_used:
        msg += f" (Preset: {JTL_PRESETS[preset_used]['label']})"

    return {
        "tables": result_tables,
        "joins": result_joins,
        "used_ai": used_ai,
        "preset_used": preset_used,
        "message": msg,
    }


@router.get("/presets")
def get_presets(user: User = Depends(get_current_user)):
    """Gibt alle verfügbaren JTL-Presets zurück."""
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "tables"}} for k, v in JTL_PRESETS.items()]

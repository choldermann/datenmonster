"""Schema-Katalog API — Tabellen/Spalten-Beschreibungen + manuelle FK-Definitionen."""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.dataset import DbConnection
from app.models.schema_catalog import SchemaTableMeta, SchemaColumnMeta, SchemaRelationMeta

log = logging.getLogger("datenmonster")
router = APIRouter()

CATEGORIES = ["Stammdaten", "Bewegungsdaten", "Konfiguration", "Lookup", "System", "Sonstige"]


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class TableMetaIn(BaseModel):
    table_full_name: str
    business_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_important: bool = False

class ColumnMetaIn(BaseModel):
    table_full_name: str
    column_name: str
    description: Optional[str] = None
    example_values: Optional[str] = None

class RelationIn(BaseModel):
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    description: Optional[str] = None

class AiSuggestRequest(BaseModel):
    table_full_names: list[str] = []   # leer = alle Tabellen ohne Beschreibung


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_conn(conn_id: int, db: Session, user: User) -> DbConnection:
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    return conn

def _upsert_table_meta(db: Session, conn_id: int, table_full_name: str, **kwargs) -> SchemaTableMeta:
    meta = db.query(SchemaTableMeta).filter_by(
        connection_id=conn_id, table_full_name=table_full_name
    ).first()
    if not meta:
        meta = SchemaTableMeta(connection_id=conn_id, table_full_name=table_full_name)
        db.add(meta)
    for k, v in kwargs.items():
        if v is not None or k == "description":
            setattr(meta, k, v)
    db.commit()
    db.refresh(meta)
    return meta


# ── Sync: leere Meta-Einträge für alle Tabellen anlegen ──────────────────────

@router.post("/api/schema-catalog/{conn_id}/sync")
def sync_catalog(
    conn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Erstellt fehlende SchemaTableMeta-Einträge für alle Tabellen im Schema-Cache."""
    conn = _get_conn(conn_id, db, user)
    if not conn.schema_cache:
        return {"synced": 0, "existing": 0}

    try:
        schema = json.loads(conn.schema_cache)
    except Exception:
        return {"synced": 0, "existing": 0}

    existing = {
        m.table_full_name
        for m in db.query(SchemaTableMeta.table_full_name)
               .filter_by(connection_id=conn_id).all()
    }
    new_count = 0
    for tbl in schema.get("tables", []):
        name = tbl.get("full_name") or tbl.get("name")
        if name and name not in existing:
            db.add(SchemaTableMeta(connection_id=conn_id, table_full_name=name))
            new_count += 1
    db.commit()
    return {"synced": new_count, "existing": len(existing)}


# ── Katalog abrufen ───────────────────────────────────────────────────────────

@router.get("/api/schema-catalog/{conn_id}")
def get_catalog(
    conn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Gibt alle Tabellen-Metas mit zugehörigen Spalten-Metas zurück."""
    _get_conn(conn_id, db, user)

    table_metas = db.query(SchemaTableMeta).filter_by(connection_id=conn_id).all()
    col_metas   = db.query(SchemaColumnMeta).filter_by(connection_id=conn_id).all()
    relations   = db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()

    cols_by_table: dict[str, list] = {}
    for c in col_metas:
        cols_by_table.setdefault(c.table_full_name, []).append({
            "column_name":    c.column_name,
            "description":    c.description,
            "example_values": c.example_values,
        })

    tables = [
        {
            "id":              t.id,
            "table_full_name": t.table_full_name,
            "business_name":   t.business_name,
            "description":     t.description,
            "category":        t.category,
            "is_important":    t.is_important,
            "columns":         cols_by_table.get(t.table_full_name, []),
        }
        for t in table_metas
    ]

    return {
        "tables":    tables,
        "relations": [
            {
                "id":          r.id,
                "from_table":  r.from_table,
                "from_col":    r.from_col,
                "to_table":    r.to_table,
                "to_col":      r.to_col,
                "description": r.description,
            }
            for r in relations
        ],
        "categories": CATEGORIES,
    }


# ── Tabellen-Meta schreiben ───────────────────────────────────────────────────

@router.put("/api/schema-catalog/{conn_id}/table")
def upsert_table_meta(
    conn_id: int,
    body: TableMetaIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_conn(conn_id, db, user)
    meta = _upsert_table_meta(
        db, conn_id, body.table_full_name,
        business_name=body.business_name,
        description=body.description,
        category=body.category,
        is_important=body.is_important,
    )
    return {"id": meta.id, "table_full_name": meta.table_full_name}


# ── Spalten-Meta schreiben ────────────────────────────────────────────────────

@router.put("/api/schema-catalog/{conn_id}/column")
def upsert_column_meta(
    conn_id: int,
    body: ColumnMetaIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_conn(conn_id, db, user)
    col = db.query(SchemaColumnMeta).filter_by(
        connection_id=conn_id,
        table_full_name=body.table_full_name,
        column_name=body.column_name,
    ).first()
    if not col:
        col = SchemaColumnMeta(
            connection_id=conn_id,
            table_full_name=body.table_full_name,
            column_name=body.column_name,
        )
        db.add(col)
    col.description    = body.description
    col.example_values = body.example_values
    db.commit()
    return {"ok": True}


# ── Relationen ────────────────────────────────────────────────────────────────

@router.post("/api/schema-catalog/{conn_id}/relations")
def add_relation(
    conn_id: int,
    body: RelationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_conn(conn_id, db, user)
    rel = SchemaRelationMeta(
        connection_id=conn_id,
        from_table=body.from_table, from_col=body.from_col,
        to_table=body.to_table,   to_col=body.to_col,
        description=body.description,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return {"id": rel.id}


@router.delete("/api/schema-catalog/{conn_id}/relations/{rel_id}")
def delete_relation(
    conn_id: int,
    rel_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rel = db.query(SchemaRelationMeta).filter_by(id=rel_id, connection_id=conn_id).first()
    if rel:
        db.delete(rel)
        db.commit()
    return {"ok": True}


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/api/schema-catalog/{conn_id}/export")
def export_catalog(
    conn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Exportiert den vollständigen Katalog als JSON inkl. Spaltenstruktur aus Schema-Cache."""
    conn = _get_conn(conn_id, db, user)

    # Schema-Cache für Spaltenstruktur
    all_schema_tables: dict = {}
    if conn.schema_cache:
        try:
            schema = json.loads(conn.schema_cache)
            all_schema_tables = {t["full_name"]: t for t in schema.get("tables", [])}
        except Exception:
            pass

    table_metas = db.query(SchemaTableMeta).filter_by(connection_id=conn_id).all()
    col_metas   = db.query(SchemaColumnMeta).filter_by(connection_id=conn_id).all()
    relations   = db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()

    cols_by_table: dict[str, list] = {}
    for c in col_metas:
        cols_by_table.setdefault(c.table_full_name, []).append({
            "column_name":    c.column_name,
            "description":    c.description,
            "example_values": c.example_values,
        })

    tables_out = []
    for t in table_metas:
        schema_tbl = all_schema_tables.get(t.table_full_name, {})
        # Alle Spalten aus Schema-Cache mit eventuell vorhandenen Beschreibungen mergen
        schema_cols = schema_tbl.get("columns", [])
        meta_cols   = {c["column_name"]: c for c in cols_by_table.get(t.table_full_name, [])}
        columns = []
        for sc in schema_cols:
            mc = meta_cols.get(sc["name"], {})
            columns.append({
                "column_name":    sc["name"],
                "type":           sc.get("type", ""),
                "pk":             sc.get("pk", False),
                "description":    mc.get("description"),
                "example_values": mc.get("example_values"),
            })
        tables_out.append({
            "table_full_name": t.table_full_name,
            "business_name":   t.business_name,
            "description":     t.description,
            "category":        t.category,
            "is_important":    t.is_important,
            "columns":         columns,
        })

    payload = {
        "version":    1,
        "connection": conn.name,
        "database":   conn.database,
        "db_type":    conn.db_type,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": CATEGORIES,
        "tables":     tables_out,
        "relations": [
            {
                "from_table":  r.from_table, "from_col":  r.from_col,
                "to_table":    r.to_table,   "to_col":    r.to_col,
                "description": r.description,
            }
            for r in relations
        ],
    }

    filename = f"schema_catalog_{conn.name}_{datetime.now().strftime('%Y%m%d')}.json"
    content  = json.dumps(payload, ensure_ascii=False, indent=2)
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Import ────────────────────────────────────────────────────────────────────

class ImportTableEntry(BaseModel):
    table_full_name: str
    business_name:   Optional[str] = None
    description:     Optional[str] = None
    category:        Optional[str] = None
    is_important:    bool = False
    columns: List[dict] = []

class ImportRelEntry(BaseModel):
    from_table: str; from_col: str
    to_table:   str; to_col:   str
    description: Optional[str] = None

class ImportPayload(BaseModel):
    version:   int = 1
    tables:    List[ImportTableEntry] = []
    relations: List[ImportRelEntry]   = []

@router.post("/api/schema-catalog/{conn_id}/import")
def import_catalog(
    conn_id: int,
    body: ImportPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Importiert einen Katalog-Export (Upsert — vorhandene Daten werden überschrieben)."""
    _get_conn(conn_id, db, user)

    tables_done = 0
    cols_done   = 0

    for t in body.tables:
        _upsert_table_meta(
            db, conn_id, t.table_full_name,
            business_name=t.business_name,
            description=t.description,
            category=t.category,
            is_important=t.is_important,
        )
        tables_done += 1

        for col in t.columns:
            name = col.get("column_name")
            desc = col.get("description")
            examples = col.get("example_values")
            if not name or (not desc and not examples):
                continue
            existing = db.query(SchemaColumnMeta).filter_by(
                connection_id=conn_id,
                table_full_name=t.table_full_name,
                column_name=name,
            ).first()
            if not existing:
                existing = SchemaColumnMeta(
                    connection_id=conn_id,
                    table_full_name=t.table_full_name,
                    column_name=name,
                )
                db.add(existing)
            existing.description    = desc
            existing.example_values = examples
            cols_done += 1

    # Relationen: alles ersetzen
    if body.relations:
        db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).delete()
        for r in body.relations:
            db.add(SchemaRelationMeta(
                connection_id=conn_id,
                from_table=r.from_table, from_col=r.from_col,
                to_table=r.to_table,   to_col=r.to_col,
                description=r.description,
            ))

    db.commit()
    return {"tables": tables_done, "columns": cols_done, "relations": len(body.relations)}


# ── KI-Vorschläge (SSE) ───────────────────────────────────────────────────────

@router.post("/api/schema-catalog/{conn_id}/ai-suggest")
async def ai_suggest(
    conn_id: int,
    body: AiSuggestRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """KI generiert Beschreibungen für Tabellen und speichert sie direkt."""
    from app.services.ai_service import build_ai_service

    conn = _get_conn(conn_id, db, user)
    if not conn.schema_cache:
        raise HTTPException(400, "Kein Schema-Cache vorhanden")

    schema = json.loads(conn.schema_cache)
    all_tables = {t["full_name"]: t for t in schema.get("tables", [])}

    # Welche Tabellen bearbeiten?
    if body.table_full_names:
        targets = [all_tables[n] for n in body.table_full_names if n in all_tables]
    else:
        # Alle ohne Beschreibung
        described = {
            m.table_full_name
            for m in db.query(SchemaTableMeta.table_full_name)
                       .filter(SchemaTableMeta.connection_id == conn_id,
                               SchemaTableMeta.description.isnot(None),
                               SchemaTableMeta.description != "").all()
        }
        targets = [t for name, t in all_tables.items() if name not in described][:100]

    if not targets:
        async def empty():
            yield f"data: {json.dumps({'done': True, 'count': 0})}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    svc = build_ai_service(db)
    if not svc:
        async def _no_ai():
            yield f"data: {json.dumps({'error': 'KI nicht aktiviert. Bitte unter Einstellungen → KI aktivieren und ein Modell auswählen.'})}\n\n"
        return StreamingResponse(_no_ai(), media_type="text/event-stream")
    svc.timeout = 300

    async def generate():
        total = len(targets)
        done  = 0
        # Batch: je 10 Tabellen pro KI-Anfrage
        batch_size = 10
        for i in range(0, total, batch_size):
            batch = targets[i : i + batch_size]
            table_lines = []
            for tbl in batch:
                cols = ", ".join(c["name"] for c in tbl.get("columns", [])[:20])
                table_lines.append(f'- {tbl["full_name"]}: {cols}')

            prompt = (
                f"Du analysierst Datenbanktabellen aus {schema.get('database', 'einer Datenbank')} "
                f"({schema.get('db_type', 'SQL')}).\n\n"
                "Gib für jede Tabelle in EXAKT diesem JSON-Format zurück:\n"
                '[{"table":"name","business_name":"Anzeigename","description":"1 Satz was diese Tabelle enthält","category":"Stammdaten|Bewegungsdaten|Konfiguration|Lookup|System|Sonstige"}]\n\n'
                "Regeln:\n"
                "- business_name: kurzer, verständlicher Name ohne Präfix (z.B. 'Artikel' für 'tArtikel')\n"
                "- description: genau 1 Satz, fachlich, auf Deutsch\n"
                "- Schließe aus den Spaltennamen auf den Inhalt\n"
                "- Erfinde KEINE Bedeutungen – wenn unklar, schreibe 'Unbekannt'\n\n"
                "Tabellen:\n" + "\n".join(table_lines) + "\n\nJSON:"
            )

            result_text = ""
            async for token in svc._stream(
                [{"role": "user", "content": prompt}],
                system="Du bist ein Datenbankexperte. Antworte NUR mit dem JSON-Array, ohne Erklärungen.",
                json_mode=True,
            ):
                result_text += token

            # JSON parsen
            try:
                # JSON aus evtl. umgebenden Markdown-Fences extrahieren
                clean = result_text.strip()
                if "```" in clean:
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                suggestions = json.loads(clean)
                if not isinstance(suggestions, list):
                    suggestions = []
            except Exception:
                suggestions = []

            # Direkt in DB schreiben
            saved = []
            for s in suggestions:
                name = s.get("table", "")
                if not name:
                    continue
                _upsert_table_meta(
                    db, conn_id, name,
                    business_name=s.get("business_name") or None,
                    description=s.get("description") or None,
                    category=s.get("category") or None,
                )
                saved.append(name)
            done += len(saved)

            yield f"data: {json.dumps({'progress': done, 'total': total, 'saved': saved})}\n\n"

        yield f"data: {json.dumps({'done': True, 'count': done})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

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
    limit: int = 100                   # max. Tabellen pro Durchlauf
    # Anbieter nur für diesen Lauf: "ollama" | "datenmonster". Ohne Angabe gilt
    # die Einstellung. Der Katalog bietet die Wahl an, weil hier hunderte
    # Tabellen am Stück beschrieben werden — das ist der Fall, für den sich das
    # große Modell lohnt.
    provider: Optional[str] = None


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


class DeriveIn(BaseModel):
    tables: list[str] = []      # leer = wichtige Tabellen, sonst alle (gedeckelt)


@router.post("/api/schema-catalog/{conn_id}/relations/derive")
def derive_relations(
    conn_id: int,
    body: DeriveIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Beziehungsvorschläge aus den Schlüsseln — schreibt nichts, schlägt nur vor.

    Ohne Tabellenauswahl werden die als wichtig markierten genommen; gibt es
    keine, alle (gedeckelt). Bei 1.158 Tabellen kämen sonst ~1.250 Vorschläge
    heraus, die niemand durchsieht.
    """
    conn = _get_conn(conn_id, db, user)
    if not conn.schema_cache:
        raise HTTPException(400, "Kein Schema-Cache — bitte erst den Schema-Cache aufbauen.")

    from app.services.schema_cache_service import beziehungen_ableiten

    tabellen = body.tables
    quelle_auswahl = "auswahl"
    if not tabellen:
        wichtige = [t.table_full_name for t in
                    db.query(SchemaTableMeta).filter_by(connection_id=conn_id, is_important=True).all()]
        if wichtige:
            tabellen, quelle_auswahl = wichtige, "wichtige"
        else:
            quelle_auswahl = "alle"

    kandidaten = beziehungen_ableiten(json.loads(conn.schema_cache), tabellen or None)

    # Schon vorhandene nicht noch einmal vorschlagen
    vorhanden = {
        (r.from_table, r.from_col, r.to_table, r.to_col)
        for r in db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()
    }
    neu = [k for k in kandidaten
           if (k["from_table"], k["from_col"], k["to_table"], k["to_col"]) not in vorhanden]

    return {
        "kandidaten": neu,
        "geprueft_tabellen": len(tabellen) if tabellen else "alle",
        "auswahl": quelle_auswahl,
        "schon_vorhanden": len(kandidaten) - len(neu),
    }


class BulkRelationsIn(BaseModel):
    relations: list[RelationIn]


@router.post("/api/schema-catalog/{conn_id}/relations/bulk")
def add_relations_bulk(
    conn_id: int,
    body: BulkRelationsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mehrere Beziehungen auf einmal übernehmen (Dubletten werden übersprungen)."""
    _get_conn(conn_id, db, user)
    vorhanden = {
        (r.from_table, r.from_col, r.to_table, r.to_col)
        for r in db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()
    }
    angelegt = 0
    for r in body.relations:
        if (r.from_table, r.from_col, r.to_table, r.to_col) in vorhanden:
            continue
        db.add(SchemaRelationMeta(
            connection_id=conn_id, from_table=r.from_table, from_col=r.from_col,
            to_table=r.to_table, to_col=r.to_col, description=r.description,
        ))
        vorhanden.add((r.from_table, r.from_col, r.to_table, r.to_col))
        angelegt += 1
    db.commit()
    return {"angelegt": angelegt, "uebersprungen": len(body.relations) - angelegt}


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
        targets = [t for name, t in all_tables.items() if name not in described][:body.limit]

    if not targets:
        async def empty():
            yield f"data: {json.dumps({'done': True, 'count': 0})}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    svc = build_ai_service(db, provider=body.provider)
    if not svc:
        async def _no_ai():
            yield f"data: {json.dumps({'error': 'KI nicht aktiviert. Bitte unter Einstellungen → KI aktivieren und ein Modell auswählen.'})}\n\n"
        return StreamingResponse(_no_ai(), media_type="text/event-stream")
    svc.timeout = 300

    async def generate():
        total = len(targets)
        done  = 0
        # Kleine Batches für kleine Modelle
        batch_size = 5
        try:
            for i in range(0, total, batch_size):
                batch = targets[i : i + batch_size]
                table_lines = []
                for tbl in batch:
                    cols = ", ".join(c["name"] for c in tbl.get("columns", [])[:15])
                    table_lines.append(f'- {tbl["full_name"]}: {cols}')

                # Ein OBJEKT mit "tables" verlangen, kein nacktes Array: bei
                # erzwungenem JSON (format=json) antwortet das lokale Modell sonst
                # mit einem einzelnen Objekt — also nur der ersten Tabelle — und der
                # Parser verwarf das Ganze. Gemessen am 2026-08-13: 0 von 5
                # Tabellen über Ollama, 5 von 5 mit dieser Formulierung.
                prompt = (
                    "Analysiere diese Datenbanktabellen. Antworte mit EINEM JSON-Objekt, das "
                    "unter \"tables\" für JEDE genannte Tabelle einen Eintrag enthält.\n"
                    "Format: {\"tables\":[{\"table\":\"tabellenname\",\"business_name\":\"Kurzname\","
                    "\"description\":\"Ein Satz auf Deutsch\","
                    "\"category\":\"Stammdaten\"}]}\n\n"
                    "Kategorien: Stammdaten, Bewegungsdaten, Konfiguration, Lookup, System, Sonstige\n\n"
                    f"Tabellen ({len(batch)} Stück, alle beschreiben):\n" + "\n".join(table_lines)
                )

                result_text = ""
                async for token in svc._stream(
                    [{"role": "user", "content": prompt}],
                    system="Antworte nur mit einem JSON-Array. Kein Text davor oder danach.",
                    json_mode=True,
                ):
                    result_text += token

                # JSON parsen — mehrere Formate versuchen
                suggestions = []
                try:
                    clean = result_text.strip()
                    # Markdown-Fences entfernen
                    if "```" in clean:
                        parts = clean.split("```")
                        for part in parts:
                            part = part.strip()
                            if part.startswith("json"):
                                part = part[4:].strip()
                            if part.startswith("["):
                                clean = part
                                break
                    # Array direkt parsen
                    if clean.startswith("["):
                        parsed = json.loads(clean)
                        if isinstance(parsed, list):
                            suggestions = parsed
                    # Manchmal gibt das Modell {"tables": [...]} zurück
                    elif clean.startswith("{"):
                        parsed = json.loads(clean)
                        for key in ("tables", "data", "result", "items"):
                            if isinstance(parsed.get(key), list):
                                suggestions = parsed[key]
                                break
                        # Einzelnes Objekt statt Liste: lieber eine Tabelle
                        # übernehmen als den ganzen Stapel wegwerfen.
                        if not suggestions and parsed.get("table"):
                            suggestions = [parsed]
                except Exception as parse_err:
                    yield f"data: {json.dumps({'warning': f'JSON-Parsing fehlgeschlagen: {str(parse_err)[:100]}', 'raw': result_text[:200]})}\n\n"

                # In DB schreiben
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

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)[:300]})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Schema-Erkundung ─────────────────────────────────────────────────────────
# Die Wissensdatenbank von Hand zu füllen skaliert nicht. Automatisieren lässt
# sich aber nur das MESSEN — was ein Sprachmodell aus bloßen Spaltennamen
# ableitet, klingt plausibel und ist regelmäßig falsch. Deshalb drei getrennte
# Schritte: messen (ohne KI), formulieren (KI, nur aus Messwerten), übernehmen
# (der Benutzer wählt aus).

class ErkundenIn(BaseModel):
    schemas:     List[str] = []      # leer = alle Fachschemata
    tables:      List[str] = []      # noch enger: einzelne Objekte
    max_objekte: int = 60


@router.post("/api/schema-catalog/{conn_id}/erkunden")
async def schema_erkunden(
    conn_id: int,
    body: ErkundenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stufe A: misst die gewählten Objekte gegen die echte Datenbank.

    Läuft je nach Umfang Minuten, deshalb als Ereignisstrom mit Fortschritt —
    ein gewöhnlicher POST liefe in den Timeout des Browsers.
    """
    import asyncio, queue
    from app.services.schema_erkundung import erkunde

    _get_conn(conn_id, db, user)
    meldungen: "queue.Queue" = queue.Queue()

    def melde(objekt, i, n):
        meldungen.put({"progress": {"objekt": objekt, "i": i + 1, "n": n}})

    async def strom():
        aufgabe = asyncio.create_task(asyncio.to_thread(
            erkunde, conn_id,
            body.schemas or None, body.tables or None,
            max(1, min(body.max_objekte, 500)), melde,
        ))
        while True:
            try:
                yield f"data: {json.dumps(meldungen.get_nowait())}\n\n"
                continue
            except queue.Empty:
                pass
            if aufgabe.done():
                break
            await asyncio.sleep(0.2)
        try:
            ergebnis = await aufgabe
        except Exception as e:
            log.exception("Schema-Erkundung fehlgeschlagen")
            yield f"data: {json.dumps({'error': str(e)[:300]})}\n\n"
            yield "data: [DONE]\n\n"
            return
        while not meldungen.empty():
            yield f"data: {json.dumps(meldungen.get_nowait())}\n\n"
        yield f"data: {json.dumps({'result': ergebnis})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(strom(), media_type="text/event-stream")


class EntwerfenIn(BaseModel):
    befunde:    List[dict]
    hoechstens: int = 12
    provider:   Optional[str] = None


@router.post("/api/schema-catalog/{conn_id}/erkunden/wissen")
async def erkundung_wissen(
    conn_id: int,
    body: EntwerfenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stufe B: aus Messwerten werden Wissensentwürfe. Speichert nichts."""
    from app.services.ai_service import build_ai_service
    from app.services.schema_erkundung import wissen_entwerfen

    conn = _get_conn(conn_id, db, user)
    if not body.befunde:
        return {"entwuerfe": []}

    svc = build_ai_service(db, provider=body.provider)
    if not svc:
        raise HTTPException(400, "KI-Integration ist nicht aktiviert")
    svc.timeout = 300
    try:
        entwuerfe = await wissen_entwerfen(
            db, body.befunde, svc, body.hoechstens,
            scope="datasource", scope_id=conn.name)
    except ValueError as e:
        raise HTTPException(502, str(e))
    # Der Geltungsbereich gehört sichtbar an die Entwürfe: der Anwender soll vor
    # dem Übernehmen wissen, für welche Wawi diese Messwerte gelten.
    return {"entwuerfe": entwuerfe, "geltungsbereich": conn.name}


class UebernehmenIn(BaseModel):
    eintraege:   List[dict] = []     # {kategorie, titel, inhalt}
    beziehungen: List[dict] = []     # {von, von_spalte, nach, nach_spalte, quote}
    # Ohne Angabe gilt das Wissen für die vermessene Verbindung, nicht für alle.
    # Erkundungswissen sind Messwerte EINES Mandanten — „1003 von 2070 Objekten
    # leer" ist über einer anderen Wawi schlicht falsch.
    scope:       Optional[str] = None
    scope_id:    Optional[str] = None


@router.post("/api/schema-catalog/{conn_id}/erkunden/uebernehmen")
def erkundung_uebernehmen(
    conn_id: int,
    body: UebernehmenIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stufe C: übernimmt, was der Benutzer ausgewählt hat.

    Wissen wandert nach Titel per Upsert in die Wissensdatenbank, gemessene
    Beziehungen zusätzlich in den Schema-Katalog — davon profitieren auch die
    Join-Vorschläge im Mapping-Editor, nicht nur die KI.
    """
    from app.models.ai_memory import AiMemoryKnowledge

    conn = _get_conn(conn_id, db, user)
    # scope_id ist der VerbindungsNAME (so sucht ai_context_builder das Wissen
    # später wieder heraus), nicht die Id — mehrere Verbindungen auf dieselbe
    # Wawi teilen sich damit von selbst einen Wissensstand.
    scope    = body.scope or "datasource"
    scope_id = body.scope_id or (conn.name if scope == "datasource" else None)

    neu = akt = 0
    for e in body.eintraege:
        titel  = (e.get("titel") or "").strip()
        inhalt = (e.get("inhalt") or "").strip()
        if not titel or not inhalt:
            continue
        kategorie = e.get("kategorie") if e.get("kategorie") in (
            "table", "field_mapping", "rule", "format", "other") else "rule"
        # Der Titel allein taugt nicht als Schlüssel: die Erkundung vergibt für
        # jede Wawi dieselben Titel („Rechnung – Statuswerte"), und ein Upsert
        # nur nach Titel überschriebe damit die Messwerte des anderen Mandanten.
        row = (db.query(AiMemoryKnowledge)
                 .filter(AiMemoryKnowledge.title == titel,
                         AiMemoryKnowledge.scope == scope,
                         AiMemoryKnowledge.scope_id.is_(None) if scope_id is None
                         else AiMemoryKnowledge.scope_id == scope_id)
                 .first())
        if row:
            row.content, row.category, row.enabled = inhalt, kategorie, True
            akt += 1
        else:
            db.add(AiMemoryKnowledge(
                scope=scope, scope_id=scope_id, category=kategorie,
                title=titel, content=inhalt, enabled=True, always_include=False))
            neu += 1

    vorhanden = {
        (r.from_table, r.from_col, r.to_table, r.to_col)
        for r in db.query(SchemaRelationMeta).filter_by(connection_id=conn_id).all()
    }
    rel_neu = 0
    for b in body.beziehungen:
        schluessel = (b.get("von"), b.get("von_spalte"), b.get("nach"), b.get("nach_spalte"))
        if not all(schluessel) or schluessel in vorhanden:
            continue
        vorhanden.add(schluessel)
        # Unter 99 % ist der Join nicht falsch, sondern optional: die Spalte ist
        # bei einem Teil der Zeilen leer (Rechnung.tRechnung.kShop trifft zu
        # 34 %, weil zwei Drittel der Rechnungen keine Shop-Bestellungen sind).
        # Der Hinweis muss mit in den Katalog, sonst baut die KI einen INNER
        # JOIN und verliert stillschweigend Zeilen.
        quote = b.get("quote")
        beschreibung = f"gemessen: {quote} % Trefferquote"
        if isinstance(quote, (int, float)) and quote < 99:
            beschreibung += " — optionaler Schlüssel, LEFT JOIN nötig"
        db.add(SchemaRelationMeta(
            connection_id=conn_id,
            from_table=schluessel[0], from_col=schluessel[1],
            to_table=schluessel[2], to_col=schluessel[3],
            description=beschreibung))
        rel_neu += 1

    db.commit()
    return {"wissen_neu": neu, "wissen_aktualisiert": akt, "beziehungen_neu": rel_neu,
            "geltungsbereich": scope_id or "alle Verbindungen"}


@router.get("/api/schema-catalog/{conn_id}/schemata")
def schemata_auflisten(
    conn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Die Schemata der Datenbank mit Objektzahl — die Auswahl für die Erkundung."""
    from sqlalchemy import text as _text
    from app.services.mapping_service import _get_sql_engine
    from app.services.schema_erkundung import UNINTERESSANT

    _get_conn(conn_id, db, user)
    with _get_sql_engine(conn_id).connect() as con:
        rows = con.execute(_text(
            "SELECT TABLE_SCHEMA, "
            "  SUM(CASE WHEN TABLE_TYPE='BASE TABLE' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN TABLE_TYPE='VIEW' THEN 1 ELSE 0 END) "
            "FROM INFORMATION_SCHEMA.TABLES GROUP BY TABLE_SCHEMA ORDER BY TABLE_SCHEMA"
        )).fetchall()
    return {"schemata": [
        {"name": r[0], "tabellen": int(r[1] or 0), "views": int(r[2] or 0),
         "empfohlen": r[0].lower() not in UNINTERESSANT}
        for r in rows
    ]}

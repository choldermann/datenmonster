import traceback
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from pydantic import BaseModel
import json
from datetime import datetime, timezone
from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/templates", tags=["templates"])


def template_out(t):
    content = t.content if isinstance(t.content, dict) else json.loads(t.content or "{}")
    return {
        "id": t.id,
        "template_id": t.template_id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "version": t.version,
        "author": t.author,
        "hinweise": content.get("hinweise", []),
        "config_required": content.get("config_required", []),
        "created_at": str(t.created_at or ""),
    }


@router.get("/")
def list_templates(category: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.template import Template
    q = db.query(Template)
    if category:
        q = q.filter(Template.category == category)
    return [template_out(t) for t in q.order_by(Template.name).all()]


@router.get("/{template_id}/detail")
def get_template(template_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.template import Template
    t = db.query(Template).filter(Template.template_id == template_id).first()
    if not t:
        raise HTTPException(404, "Template nicht gefunden")
    content = t.content if isinstance(t.content, dict) else json.loads(t.content or "{}")
    return {**template_out(t), "content": content}


class InstallBody(BaseModel):
    template_id: str
    project_id: Optional[int] = None
    config: Optional[dict] = {}


def _apply_config(text: str, config: dict) -> str:
    """Ersetzt {{key}} Platzhalter im Text mit config-Werten."""
    if not isinstance(text, str):
        return text
    for k, v in config.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _apply_config_deep(obj, config: dict):
    """Ersetzt Platzhalter rekursiv in Strings, Dicts und Listen."""
    if isinstance(obj, str):
        return _apply_config(obj, config)
    if isinstance(obj, dict):
        return {k: _apply_config_deep(v, config) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_apply_config_deep(i, config) for i in obj]
    return obj


@router.post("/install")
def install_template(body: InstallBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Installiert ein Template: legt Datasets, Mappings und Pipeline an.
    Unterstützt file_type: db_query, rest_api, static
    """
    from app.models.template import Template
    from app.models.dataset import Dataset
    from app.models.mapping import Mapping
    from app.models.pipeline import Pipeline

    t = db.query(Template).filter(Template.template_id == body.template_id).first()
    if not t:
        raise HTTPException(404, "Template nicht gefunden")

    content = t.content if isinstance(t.content, dict) else json.loads(t.content or "{}")
    # config mit Defaults aus config_required auffüllen
    config = body.config or {}
    for req in content.get("config_required", []):
        key = req.get("key")
        if key and key not in config and req.get("default") not in (None, ""):
            config[key] = req["default"]
    created = {"datasets": [], "mappings": [], "pipelines": []}

    # ── Datasets anlegen ──────────────────────────────────────────────────────
    ds_id_map = {}
    for ds_def in content.get("datasets", []):
        file_type = ds_def.get("file_type", "db_query")
        columns = ds_def.get("columns", [])

        # Platzhalter in columns ersetzen (falls Strings)
        columns = [_apply_config(c, config) if isinstance(c, str) else c for c in columns]

        ds_kwargs = dict(
            name=ds_def.get("name", "Dataset"),
            file_type=file_type,
            row_count=0,
            columns=columns,
            xml_configured=1,
            project_id=body.project_id,
        )

        if file_type == "db_query":
            # Klassisches SQL-Dataset
            sql = _apply_config(ds_def.get("sql", ""), config)
            ds_kwargs["source_sql"] = sql
            ds_kwargs["query_config"] = ds_def.get("query_config")

        elif file_type == "rest_api":
            # REST API Dataset – echte RestSource anlegen + Dataset verknüpfen
            from app.models.rest_source import RestSource
            rest_config = _apply_config_deep(ds_def.get("rest_config", {}), config)
            # Tankerkoenig-Regel: type=all erfordert sort=dist
            if "type=all" in rest_config.get("url","") and "sort=price" in rest_config.get("url",""):
                rest_config["url"] = rest_config["url"].replace("sort=price","sort=dist")
            # Falls {{sortierung}} noch drin und {{kraftstoff}} = all: sort=dist
            if "{{kraftstoff}}" not in rest_config.get("url",""):
                if config.get("kraftstoff","") == "all" and "sort={{sortierung}}" in rest_config.get("url",""):
                    config["sortierung"] = "dist"
                    rest_config = _apply_config_deep(ds_def.get("rest_config", {}), config)

            # PLZ → lat/lng auflösen wenn nötig
            url_raw = rest_config.get("url", "")
            if "{{lat}}" in url_raw or "{{lng}}" in url_raw:
                if not config.get("lat") and config.get("plz"):
                    try:
                        import requests as _req
                        _r = _req.get(
                            f"https://nominatim.openstreetmap.org/search",
                            params={"postalcode": config["plz"], "country": "de",
                                    "format": "json", "limit": 1},
                            headers={"User-Agent": "Datenmonster/1.0"},
                            timeout=10,
                        )
                        _geo = _r.json()
                        if _geo:
                            config["lat"] = _geo[0]["lat"]
                            config["lng"] = _geo[0]["lon"]
                            rest_config = _apply_config_deep(ds_def.get("rest_config", {}), config)
                    except Exception as _e:
                        config.setdefault("lat", "0.0")
                        config.setdefault("lng", "0.0")
                        try:
                            from app.services.db_logger import log as _dblog
                            _dblog(db, "warning", "templates", "geocoding_failed",
                                f"PLZ-Geocoding fehlgeschlagen: {str(_e)[:200]}",
                                details={"plz": config.get("plz"),
                                         "exception_type": type(_e).__name__,
                                         "exception_message": str(_e)})
                        except Exception:
                            pass
            src = RestSource(
                name        = ds_def.get("name", "REST Dataset"),
                project_id  = body.project_id,
                url         = rest_config.get("url", ""),
                method      = rest_config.get("method", "GET"),
                headers     = rest_config.get("headers", {}),
                query_params= rest_config.get("query_params", {}),
                body_type   = rest_config.get("body_type", "none"),
                body_content= rest_config.get("body_content"),
                auth_type   = (rest_config.get("auth") or {}).get("type", "none"),
                auth_config = rest_config.get("auth", {}),
                data_path   = rest_config.get("data_path"),
                flatten     = 1,
                pagination  = rest_config.get("pagination", {}),
                dataset_mode = "replace",
            )
            db.add(src); db.commit(); db.refresh(src)

            # Dataset anlegen und sofort gegenseitig verknüpfen
            ds = Dataset(
                name           = ds_def.get("name", "REST Dataset"),
                file_type      = "rest_api",
                row_count      = 0,
                columns        = columns,
                xml_configured = 1,
                project_id     = body.project_id,
                query_config   = {"rest_source_id": src.id},
            )
            db.add(ds); db.commit(); db.refresh(ds)
            src.dataset_id = ds.id   # RestSource.dataset_id → Dataset (für manuelles Ausführen)
            db.commit()

            ds_id_map[ds_def["id"]] = ds.id
            created.setdefault("rest_sources", []).append({"id": src.id, "name": src.name})
            created["datasets"].append({"id": ds.id, "name": ds.name, "file_type": "rest_api"})
            continue  # weiter zum nächsten ds_def, Dataset ist bereits angelegt

        elif file_type == "static":
            # Statisches Dataset mit optionalen Initialdaten
            initial_data = ds_def.get("initial_data", [])
            if initial_data:
                # Initialdaten als JSON-Datei speichern
                import os, pathlib
                from app.services.file_service import UPLOAD_DIR
                ds_kwargs["query_config"] = {"initial_data": initial_data}

        ds = Dataset(**ds_kwargs)
        db.add(ds)
        db.commit()
        db.refresh(ds)

        # Bei static mit Initialdaten: JSON-Datei anlegen
        if file_type == "static" and ds_def.get("initial_data"):
            try:
                import os
                upload_dir = "/app/uploads"
                file_path = os.path.join(upload_dir, f"dataset_{ds.id}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(ds_def["initial_data"], f, ensure_ascii=False, indent=2)
                ds.file_path = file_path
                ds.row_count = len(ds_def["initial_data"])
                db.commit()
            except Exception as e:
                try:
                    from app.services.db_logger import log as _dblog
                    _dblog(db, "warning", "templates", "initial_data_failed",
                        f"Initialdaten konnten nicht gesetzt werden: {str(e)[:200]}",
                        details={"exception_type": type(e).__name__,
                                 "exception_message": str(e)})
                except Exception:
                    pass

        ds_id_map[ds_def["id"]] = ds.id
        created["datasets"].append({"id": ds.id, "name": ds.name, "file_type": file_type})

    # ── Mappings anlegen ──────────────────────────────────────────────────────
    mapping_id_map = {}
    for m_def in content.get("mappings", []):
        src_ds_id = ds_id_map.get(m_def.get("source_dataset"))

        # dataset_columns aus dem Source-Dataset holen
        src_columns = []
        if src_ds_id:
            src_ds = db.query(Dataset).filter(Dataset.id == src_ds_id).first()
            if src_ds:
                src_columns = src_ds.columns or []

        canvas_nodes = []
        if src_ds_id:
            canvas_nodes = [{
                "id": str(src_ds_id),
                "dataset_id": src_ds_id,
                "dataset_columns": src_columns,
                "x": 40,
                "y": 80,
            }]

        # Feldverbindungen aufbauen
        effective_ds_id = str(src_ds_id) if src_ds_id else "1"
        # Constant-Node output_fields sammeln für source-Erkennung
        const_output_fields = {cn.get("output_field") for cn in m_def.get("constant_nodes", [])}
        # REST-Node output_fields sammeln
        rest_output_fields = set()
        if m_def.get("rest_node"):
            for rm in m_def["rest_node"].get("response_mappings", []):
                if rm.get("output_field"):
                    rest_output_fields.add(rm["output_field"])

        connections = []
        for f in m_def.get("fields", []):
            src = f.get("source_field")
            explicit_source = f.get("source", "")
            # source_dataset_id je nach Herkunft setzen
            if explicit_source == "constant" or src in const_output_fields:
                # SvgOverlay erwartet "__const__<nodeId>" – passende constant_node finden
                matching_cn = next(
                    (cn for cn in m_def.get("constant_nodes", [])
                     if cn.get("output_field") == src),
                    None
                )
                cn_id = matching_cn.get("id", "c1") if matching_cn else "c1"
                src_id = f"__const__{cn_id}"
            elif explicit_source == "rest" or src in rest_output_fields:
                src_id = "__rest__rn1"
            else:
                src_id = effective_ds_id
            connections.append({
                "source_dataset_id": src_id,
                "source_field": src,
                "target_field": f.get("target_field"),
            })

        # SQL Node
        sql_nodes = []
        if m_def.get("sql_node"):
            sql = _apply_config(m_def["sql_node"].get("sql", ""), config)
            sql_nodes = [{"id": "sql1", "sql": sql, "x": 200, "y": 100}]

        # Constant Nodes (z.B. Zeitstempel)
        # const_type Mapping: Template-Werte → mapping_service Werte
        CONST_TYPE_MAP = {
            "now":      "current_datetime",
            "today":    "current_date",
            "date":     "current_date",
            "datetime": "current_datetime",
            "uuid":     "uuid",
            "year":     "current_year",
        }

        constant_nodes = []
        for cn in m_def.get("constant_nodes", []):
            raw_type = cn.get("const_type", "current_datetime")
            mapped_type = CONST_TYPE_MAP.get(raw_type, raw_type)
            constant_nodes.append({
                "id": cn.get("id", "c1"),
                "const_type": mapped_type,
                "output_field": cn.get("output_field", "timestamp"),
                "x": 40,
                "y": 200,
            })

        # REST Nodes (Batch-Lookup)
        rest_nodes = []
        if m_def.get("rest_node"):
            rn = _apply_config_deep(m_def["rest_node"], config)
            rest_nodes = [{
                "id": "rn1",
                "url": rn.get("url", ""),
                "method": rn.get("method", "GET"),
                "input_field": rn.get("input_field", ""),
                "mode": rn.get("mode", "batch"),
                "join_separator": rn.get("join_separator", ","),
                "join_key": rn.get("join_key", rn.get("input_field", "")),
                "data_path": rn.get("data_path", ""),
                "auth": rn.get("auth", {"type": "none"}),
                "response_mappings": rn.get("response_mappings", []),
                "x": 300, "y": 80,
            }]

        # Write-Mode
        write_mode = m_def.get("write_mode", "replace")

        targets = [{
            "id": "t1",
            "name": m_def.get("name", "Export"),
            "target_type": m_def.get("target_type", "dataset"),
            "target_name": _apply_config(m_def.get("target_filename", "export"), config),
            "write_mode": write_mode,
            # dataset target_type: save_as_dataset Flag + write_mode weitergeben
            "save_as_dataset": m_def.get("target_type", "dataset") == "dataset",
            "target_options": {"dataset_write_mode": write_mode},
            "fields": connections,
        }]

        m = Mapping(
            name=m_def.get("name", "Mapping"),
            project_id=body.project_id,
            canvas_nodes=canvas_nodes,
            joins=[],
            sql_nodes=sql_nodes,
            constant_nodes=constant_nodes,
            rest_nodes=rest_nodes,
            targets=targets,
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        mapping_id_map[m_def["id"]] = m.id
        created["mappings"].append({"id": m.id, "name": m.name})

    # ── Pipeline anlegen ─────────────────────────────────────────────────────
    pipeline_def = content.get("pipeline")
    if pipeline_def:
        import copy
        nodes = _apply_config_deep(copy.deepcopy(pipeline_def.get("nodes", [])), config)
        for node in nodes:
            ntype = node.get("type", "")
            ncfg  = node.get("config", {})
            # Mapping-IDs einsetzen
            if ntype == "mapping":
                mid = ncfg.get("mapping_id", "")
                if isinstance(mid, str) and mid.startswith("{{"):
                    key = mid.strip("{}")
                    if key in mapping_id_map:
                        node["config"]["mapping_id"] = mapping_id_map[key]
            # rest_fetch: dataset_name → rest_source_id einsetzen
            elif ntype == "rest_fetch":
                ds_name = ncfg.get("dataset_name", "")
                for tpl_id, real_ds_id in ds_id_map.items():
                    tpl_ds = next((d for d in content.get("datasets", []) if d["id"] == tpl_id), None)
                    if tpl_ds and tpl_ds.get("name") == ds_name and tpl_ds.get("file_type") == "rest_api":
                        # rest_source_id aus dem angelegten Dataset holen
                        from app.models.dataset import Dataset as _DS
                        _ds = db.query(_DS).filter(_DS.id == real_ds_id).first()
                        if _ds and _ds.query_config:
                            _qc = _ds.query_config
                            if isinstance(_qc, str):
                                import json as _j; _qc = _j.loads(_qc)
                            node["config"]["rest_source_id"] = _qc.get("rest_source_id")
                        break

        # connections normalisieren: from/to → from_node/to_node, ports ergänzen
        raw_conns = pipeline_def.get("connections", [])
        connections = [
            {"from_node": c.get("from_node") or c.get("from", ""),
             "from_port": c.get("from_port", "out"),
             "to_node":   c.get("to_node")   or c.get("to",   ""),
             "to_port":   c.get("to_port",   "in")}
            for c in raw_conns
        ]

        scheduler_def = pipeline_def.get("scheduler", {})

        # Trigger-Node automatisch vorschalten wenn scheduler definiert
        # und noch kein trigger-Node in nodes vorhanden
        has_trigger = any(n.get("type") == "trigger" for n in nodes)
        if scheduler_def.get("cron") and not has_trigger:
            trigger_id = "trigger_auto"
            trigger_node = {
                "id": trigger_id,
                "type": "trigger",
                "label": "Scheduler",
                "x": 40, "y": 150,
                "config": {
                    "mode": "cron",
                    "cron": scheduler_def["cron"],
                    "description": scheduler_def.get("description", ""),
                }
            }
            # Trigger als erstes Node einfügen
            nodes = [trigger_node] + nodes
            # Erste Connection vom Trigger zum ersten bisherigen Node
            if nodes[1:]:
                first_node_id = nodes[1]["id"]
                connections = [
                    {"from_node": trigger_id, "from_port": "out",
                     "to_node": first_node_id, "to_port": "in"},
                ] + connections

        p = Pipeline(
            name=_apply_config(pipeline_def.get("name", t.name), config),
            project_id=body.project_id,
            nodes=nodes,
            connections=connections,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        created["pipelines"].append({"id": p.id, "name": p.name})

    # ── Reports anlegen ──────────────────────────────────────────────────
    from app.models.report import Report
    for r_def in content.get("reports", []):
        import copy
        widgets_resolved = []
        for w in r_def.get("widgets", []):
            w_copy = copy.deepcopy(w)
            cfg = w_copy.get("config", {})
            if isinstance(cfg.get("dataset_id"), str) and cfg["dataset_id"].startswith("{{"):
                key = cfg["dataset_id"].strip("{}")
                if key in ds_id_map:
                    cfg["dataset_id"] = ds_id_map[key]
            widgets_resolved.append(w_copy)
        r = Report(
            name=_apply_config(r_def.get("name", "Report"), config),
            project_id=body.project_id,
            widgets=widgets_resolved,
        )
        db.add(r); db.commit(); db.refresh(r)
        created.setdefault("reports", []).append({"id": r.id, "name": r.name})

    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success", "templates", "template_installed",
            f"Template '{t.name}' erfolgreich installiert",
            details={"created": created, "config_keys": list(config.keys())})
    except Exception as _log_e:
        pass  # Logging-Fehler nicht eskalieren
    return {"ok": True, "template": t.name, "created": created}


@router.post("/upload")
async def upload_template(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Lädt ein Template-JSON hoch und registriert es."""
    from app.models.template import Template
    content = await file.read()
    try:
        data = json.loads(content)
    except Exception:
        raise HTTPException(400, "Ungültiges JSON")

    tid = data.get("template_id")
    if not tid:
        raise HTTPException(400, "template_id fehlt")

    existing = db.query(Template).filter(Template.template_id == tid).first()
    if existing:
        existing.content = data
        existing.name = data.get("template_name", tid)
        existing.description = data.get("description", "")
        db.commit()
        return {"ok": True, "action": "updated", "id": existing.id}

    t = Template(
        template_id=tid,
        name=data.get("template_name", tid),
        description=data.get("description", ""),
        category=data.get("category", "general"),
        version=data.get("version", "1.0"),
        author=data.get("author", ""),
        content=data,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ok": True, "action": "created", "id": t.id}


class CreateTemplateBody(BaseModel):
    name: str
    description: Optional[str] = ""
    category: str = "general"
    version: str = "1.0"
    project_id: Optional[int] = None
    dataset_ids: Optional[List[int]] = []
    mapping_ids: Optional[List[int]] = []
    pipeline_ids: Optional[List[int]] = []


@router.post("/create")
def create_template_from_project(body: CreateTemplateBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Erstellt ein Template aus bestehenden Projekt-Inhalten."""
    from app.models.template import Template
    from app.models.dataset import Dataset
    from app.models.mapping import Mapping
    from app.models.pipeline import Pipeline
    import re

    content = {
        "template_id": "custom_" + re.sub(r"[^a-z0-9]", "_", body.name.lower())[:40] + "_" + str(int(__import__("time").time())),
        "template_name": body.name,
        "description": body.description,
        "category": body.category,
        "version": body.version,
        "author": user.username if hasattr(user, "username") else "user",
        "datasets": [],
        "mappings": [],
        "pipelines": [],
        "config_required": [],
        "hinweise": [],
    }

    for ds_id in (body.dataset_ids or []):
        ds = db.query(Dataset).filter(Dataset.id == ds_id).first()
        if ds:
            ds_entry = {
                "id": f"ds_{ds_id}",
                "name": ds.name,
                "file_type": ds.file_type,
                "columns": ds.columns or [],
                "row_count": ds.row_count or 0,
            }
            if ds.file_type == "rest_api" and ds.query_config:
                ds_entry["rest_config"] = ds.query_config
            elif ds.file_type == "db_query" and ds.source_sql:
                ds_entry["sql"] = ds.source_sql
            content["datasets"].append(ds_entry)

    for m_id in (body.mapping_ids or []):
        m = db.query(Mapping).filter(Mapping.id == m_id).first()
        if m:
            targets = m.targets or []
            if isinstance(targets, str):
                targets = json.loads(targets)
            content["mappings"].append({
                "id": f"mapping_{m_id}",
                "name": m.name,
                "canvas_nodes": m.canvas_nodes or [],
                "joins": m.joins or [],
                "sql_nodes": getattr(m, "sql_nodes", None) or [],
                "agg_nodes": getattr(m, "agg_nodes", None) or [],
                "transform_nodes": getattr(m, "transform_nodes", None) or [],
                "constant_nodes": getattr(m, "constant_nodes", None) or [],
                "targets": targets,
            })

    for p_id in (body.pipeline_ids or []):
        p = db.query(Pipeline).filter(Pipeline.id == p_id).first()
        if p:
            content["pipelines"].append({
                "id": f"pipeline_{p_id}",
                "name": p.name,
                "nodes": p.nodes or [],
                "connections": p.connections or [],
            })
            if not content.get("pipeline"):
                content["pipeline"] = {
                    "name": p.name,
                    "nodes": p.nodes or [],
                    "connections": p.connections or [],
                }

    tid = content["template_id"]
    t = Template(
        template_id=tid,
        name=body.name,
        description=body.description,
        category=body.category,
        version=body.version,
        author=content["author"],
        content=content,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ok": True, "template_id": tid, "id": t.id}


@router.delete('/{template_id}')
def delete_template(template_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.template import Template
    from app.models.dataset import Dataset
    from app.models.mapping import Mapping
    from app.models.pipeline import Pipeline

    t = db.query(Template).filter(Template.template_id == template_id).first()
    if not t:
        raise HTTPException(404, 'Nicht gefunden')

    content = t.content if isinstance(t.content, dict) else json.loads(t.content or '{}')
    deleted = {'datasets': 0, 'mappings': 0, 'pipelines': 0}

    for ds_def in content.get('datasets', []):
        ds = db.query(Dataset).filter(Dataset.name == ds_def.get('name')).first()
        if ds:
            db.delete(ds)
            deleted['datasets'] += 1

    for m_def in content.get('mappings', []):
        m = db.query(Mapping).filter(Mapping.name == m_def.get('name')).first()
        if m:
            db.delete(m)
            deleted['mappings'] += 1

    pipeline_def = content.get('pipeline') or {}
    if pipeline_def.get('name'):
        p = db.query(Pipeline).filter(Pipeline.name == pipeline_def['name']).first()
        if p:
            db.delete(p)
            deleted['pipelines'] += 1

    for p_def in content.get('pipelines', []):
        p = db.query(Pipeline).filter(Pipeline.name == p_def.get('name')).first()
        if p:
            db.delete(p)
            deleted['pipelines'] += 1

    db.delete(t)
    db.commit()
    return {'ok': True, 'deleted': deleted}



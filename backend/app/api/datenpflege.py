"""Datenpflege – eine Tabelle einer fremden Datenbank im Formular pflegen.

Wozu: Stammtabellen, die kein Fachprogramm verwaltet (Partnerlisten,
Zuordnungen, Parameter), wurden bisher im SQL-Management-Studio von Hand
gepflegt. Das Widget „Datenpflege" zeigt so eine Tabelle an und lässt Zeilen
anlegen, bearbeiten und sperren.

⭐ Welche Tabelle gepflegt wird, steht im GESPEICHERTEN Formular, nicht in der
Anfrage. Der Browser nennt nur Formular und Widget – sonst könnte jeder, der
das Formular sieht, eine beliebige Tabelle der Verbindung beschreiben.

Bewusst ohne Löschen: auf solche Stammzeilen zeigen meist Bewegungsdaten
(Nachrichten, Belege). Wer eine Zeile loswerden will, sperrt sie über die
Aktiv-Spalte; die Historie bleibt lesbar.

Spalten, Pflichtfelder und Längen liest der Endpunkt aus INFORMATION_SCHEMA der
Zieltabelle. Eine Spalte, die in der Datenbank dazukommt, erscheint dadurch
ohne Formularänderung in der Maske.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.form import Form
from app.models.user import User
from app.api.projects import can_read_project, require_editor
from app.api.portal import _check_portal_access

router = APIRouter(prefix="/api/datenpflege", tags=["datenpflege"])

MAX_ZEILEN = 2000
# Vorgaben, die die Datenbank selbst setzt – solche Spalten sind Zeitstempel
# des Systems („angelegt am") und gehören nicht in die Eingabemaske.
_SYSTEM_DEFAULTS = ("getdate", "sysdatetime", "current_timestamp", "now(", "getutcdate")
_GANZZAHL = {"int", "bigint", "smallint", "tinyint", "integer"}
_KOMMA = {"decimal", "numeric", "money", "smallmoney", "float", "real", "double precision"}
_DATUM = {"date", "datetime", "datetime2", "smalldatetime", "timestamp",
          "timestamp without time zone", "timestamp with time zone"}
_BOOL = {"bit", "boolean", "bool"}


# ── Widget und Rechte ────────────────────────────────────────────────────────

def _widget(form_id: int, widget_id: str, user: User, db: Session,
            schreiben: bool = False) -> tuple:
    f = db.query(Form).filter(Form.id == form_id).first()
    if not f:
        raise HTTPException(404, "Formular nicht gefunden")
    if getattr(user, "is_portal_only", False) and not getattr(user, "is_admin", False):
        # Portal: nur über ein veröffentlichtes, freigegebenes Formular.
        _check_portal_access(f, user)
    elif schreiben:
        require_editor(f.project_id, user, db)
    elif not can_read_project(f.project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")

    w = next((w for w in (f.schema or {}).get("widgets", [])
              if w.get("id") == widget_id and w.get("type") == "datenpflege"), None)
    if not w:
        raise HTTPException(404, "Datenpflege-Widget nicht gefunden – Formular gespeichert?")
    cfg = w.get("config") or {}
    if not cfg.get("connection_id") or not cfg.get("table"):
        raise HTTPException(400, "Im Widget sind Verbindung und Tabelle noch nicht eingestellt")
    if schreiben and cfg.get("nur_lesen"):
        raise HTTPException(403, "Dieses Widget ist auf „nur lesen“ gestellt")

    conn_id = int(cfg["connection_id"])
    # Nur Verbindungen, die dem Projekt zugeordnet sind – ein Editor soll über
    # ein Formular nicht an Datenbanken fremder Projekte kommen.
    if f.project_id is not None:
        from app.services.db_service import verbundene_ids
        if conn_id not in verbundene_ids(f.project_id, db):
            raise HTTPException(403, "Die Verbindung ist diesem Projekt nicht zugeordnet")
    from app.services import mandant_service
    conn_id = mandant_service.schreibziel(conn_id, f.project_id, user, db)
    return f, cfg, conn_id


def _engine(conn_id: int):
    from app.services.sql_helpers import _get_sql_engine
    try:
        return _get_sql_engine(conn_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


def _tabelle(cfg: dict) -> tuple:
    name = str(cfg["table"]).strip().strip("[]")
    if "." in name:
        schema, tab = name.split(".", 1)
        return schema.strip("[]") or None, tab.strip("[]")
    return None, name


def _meta(engine, cfg: dict) -> dict:
    """Spalten der Zieltabelle aus INFORMATION_SCHEMA plus Einstellungen des Widgets."""
    schema, tab = _tabelle(cfg)
    ist_mssql = engine.dialect.name == "mssql"
    ident_sql = ("COLUMNPROPERTY(OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA)+'.'+QUOTENAME(c.TABLE_NAME)),"
                 " c.COLUMN_NAME, 'IsIdentity')" if ist_mssql else "0")
    sql = f"""
        SELECT c.TABLE_SCHEMA, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
               c.IS_NULLABLE, c.COLUMN_DEFAULT, {ident_sql} AS ist_identity
          FROM INFORMATION_SCHEMA.COLUMNS c
         WHERE c.TABLE_NAME = :tab {"AND c.TABLE_SCHEMA = :schema" if schema else ""}
         ORDER BY c.ORDINAL_POSITION"""
    pk_sql = f"""
        SELECT k.COLUMN_NAME
          FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
          JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE k
            ON k.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND k.TABLE_SCHEMA = tc.TABLE_SCHEMA
         WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_NAME = :tab
               {"AND tc.TABLE_SCHEMA = :schema" if schema else ""}"""
    p = {"tab": tab, **({"schema": schema} if schema else {})}
    with engine.connect() as c:
        zeilen = c.execute(text(sql), p).fetchall()
        pk = [r[0] for r in c.execute(text(pk_sql), p).fetchall()]
    if not zeilen:
        raise HTTPException(404, f"Tabelle {cfg['table']} gibt es in dieser Datenbank nicht")
    schemas = {r[0] for r in zeilen}
    if len(schemas) > 1:
        raise HTTPException(400, f"Tabelle {tab} gibt es in mehreren Schemas – bitte mit Schema angeben")

    key = cfg.get("key_column") or (pk[0] if len(pk) == 1 else None)
    if not key:
        raise HTTPException(400, "Die Tabelle hat keinen einspaltigen Primärschlüssel – "
                                 "bitte im Widget eine Schlüsselspalte angeben")
    labels = cfg.get("labels") or {}
    auswahl = cfg.get("auswahl") or {}
    readonly = set(cfg.get("readonly_columns") or [])
    ausgeblendet = set(cfg.get("hidden_columns") or [])
    pflicht_extra = set(cfg.get("pflicht_columns") or [])
    spalten = []
    for _s, name, typ, laenge, nullable, default, ident in zeilen:
        typ = (typ or "").lower()
        if typ in ("xml", "varbinary", "binary", "image", "rowversion") \
                or (ist_mssql and typ == "timestamp"):  # mssql: timestamp = rowversion
            continue  # nicht sinnvoll in einer Maske pflegbar
        system = bool(default) and any(s in str(default).lower() for s in _SYSTEM_DEFAULTS)
        auto = bool(ident) or system
        spalten.append({
            "name": name,
            "label": labels.get(name) or name,
            "typ": ("bool" if typ in _BOOL else "int" if typ in _GANZZAHL
                    else "zahl" if typ in _KOMMA else "datum" if typ in _DATUM else "text"),
            "db_typ": typ,
            "max_laenge": laenge if laenge and laenge > 0 else None,
            "pflicht": (nullable == "NO" and default is None and not auto) or name in pflicht_extra,
            "auto": auto,
            "schluessel": name == key,
            "bearbeitbar": not auto and name not in readonly and name != key,
            "ausgeblendet": name in ausgeblendet,
            "auswahl": auswahl.get(name) or None,
        })
    namen = {s["name"] for s in spalten}
    if key not in namen:
        raise HTTPException(400, f"Schlüsselspalte {key} gibt es in der Tabelle nicht")
    aktiv = cfg.get("aktiv_spalte") or None
    if aktiv and aktiv not in namen:
        raise HTTPException(400, f"Aktiv-Spalte {aktiv} gibt es in der Tabelle nicht")
    return {"schema": schema or next(iter(schemas)), "tabelle": tab, "key": key,
            "aktiv_spalte": aktiv, "spalten": spalten,
            "eindeutig": [u for u in (cfg.get("unique_columns") or []) if u in namen]}


def _q(engine):
    prep = engine.dialect.identifier_preparer
    return lambda n: prep.quote_identifier(n)


def _voll(engine, meta) -> str:
    q = _q(engine)
    return f"{q(meta['schema'])}.{q(meta['tabelle'])}"


def _json(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return None
    return v


def _wert(spalte: dict, roh: Any):
    """Eingabe aus der Maske in den Spaltentyp wandeln – mit lesbarer Fehlermeldung."""
    name = spalte["label"]
    if isinstance(roh, str):
        roh = roh.strip()
    if roh is None or roh == "":
        if spalte["typ"] == "bool":
            return False
        if spalte["pflicht"]:
            raise HTTPException(422, f"„{name}“ ist ein Pflichtfeld")
        return None
    typ = spalte["typ"]
    try:
        if typ == "bool":
            if isinstance(roh, bool):
                return roh
            return str(roh).lower() in ("1", "true", "ja", "wahr", "x")
        if typ == "int":
            return int(str(roh))
        if typ == "zahl":
            return Decimal(str(roh).replace(",", "."))
        if typ == "datum":
            return datetime.fromisoformat(str(roh))
    except (ValueError, InvalidOperation):
        raise HTTPException(422, f"„{name}“: „{roh}“ ist kein gültiger Wert")
    s = str(roh)
    if spalte["max_laenge"] and len(s) > spalte["max_laenge"]:
        raise HTTPException(422, f"„{name}“ ist zu lang ({len(s)} statt höchstens "
                                 f"{spalte['max_laenge']} Zeichen)")
    return s


def _eindeutig_pruefen(c, engine, meta, werte: dict, ausser_key=None) -> None:
    q = _q(engine)
    for u in meta["eindeutig"]:
        v = werte.get(u)
        if v in (None, ""):
            continue
        sql = f"SELECT COUNT(*) FROM {_voll(engine, meta)} WHERE {q(u)} = :v"
        p = {"v": v}
        if ausser_key is not None:
            sql += f" AND {q(meta['key'])} <> :k"
            p["k"] = ausser_key
        if c.execute(text(sql), p).scalar():
            label = next(s["label"] for s in meta["spalten"] if s["name"] == u)
            raise HTTPException(409, f"„{label}“ = „{v}“ gibt es schon")


def _protokoll(db, f: Form, user: User, aktion: str, text_: str, details: dict) -> None:
    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success", "datenpflege", aktion, text_, entity_id=f.id,
               entity_name=f.name, project_id=f.project_id,
               details={"benutzer": getattr(user, "username", None), **details})
    except Exception:
        pass


def _zeile_lesen(c, engine, meta, key_wert) -> Optional[dict]:
    q = _q(engine)
    cols = ", ".join(q(s["name"]) for s in meta["spalten"])
    r = c.execute(text(f"SELECT {cols} FROM {_voll(engine, meta)} WHERE {q(meta['key'])} = :k"),
                  {"k": key_wert}).mappings().first()
    return {k: _json(v) for k, v in r.items()} if r else None


# ── Endpunkte ────────────────────────────────────────────────────────────────

@router.get("/{form_id}/{widget_id}")
def zeilen(form_id: int, widget_id: str, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    f, cfg, conn_id = _widget(form_id, widget_id, user, db)
    engine = _engine(conn_id)
    meta = _meta(engine, cfg)
    q = _q(engine)
    cols = ", ".join(q(s["name"]) for s in meta["spalten"])
    sort = cfg.get("sort_column") or meta["key"]
    if sort not in {s["name"] for s in meta["spalten"]}:
        sort = meta["key"]
    if engine.dialect.name == "mssql":
        sql = f"SELECT TOP {MAX_ZEILEN + 1} {cols} FROM {_voll(engine, meta)} ORDER BY {q(sort)}"
    else:
        sql = f"SELECT {cols} FROM {_voll(engine, meta)} ORDER BY {q(sort)} LIMIT {MAX_ZEILEN + 1}"
    with engine.connect() as c:
        rows = [{k: _json(v) for k, v in r.items()} for r in c.execute(text(sql)).mappings()]
    return {**meta, "rows": rows[:MAX_ZEILEN], "abgeschnitten": len(rows) > MAX_ZEILEN,
            "nur_lesen": bool(cfg.get("nur_lesen"))}


class NeuIn(BaseModel):
    werte: Dict[str, Any]


@router.post("/{form_id}/{widget_id}")
def anlegen(form_id: int, widget_id: str, data: NeuIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    f, cfg, conn_id = _widget(form_id, widget_id, user, db, schreiben=True)
    engine = _engine(conn_id)
    meta = _meta(engine, cfg)
    q = _q(engine)
    werte = {}
    for s in meta["spalten"]:
        if not s["bearbeitbar"] and not (s["schluessel"] and not s["auto"]):
            continue
        if s["name"] == meta["aktiv_spalte"] and s["name"] not in data.werte:
            werte[s["name"]] = True  # neue Zeilen starten aktiv
            continue
        v = _wert(s, data.werte.get(s["name"]))
        if v is not None or s["typ"] == "bool":
            werte[s["name"]] = v
    if not werte:
        raise HTTPException(422, "Keine Werte angegeben")
    cols = ", ".join(q(n) for n in werte)
    binds = ", ".join(f":p{i}" for i in range(len(werte)))
    p = {f"p{i}": v for i, v in enumerate(werte.values())}
    with engine.begin() as c:
        _eindeutig_pruefen(c, engine, meta, werte)
        if engine.dialect.name == "mssql":
            neu = c.execute(text(f"INSERT INTO {_voll(engine, meta)} ({cols}) "
                                 f"OUTPUT INSERTED.{q(meta['key'])} VALUES ({binds})"), p).scalar()
        elif engine.dialect.name == "postgresql":
            neu = c.execute(text(f"INSERT INTO {_voll(engine, meta)} ({cols}) VALUES ({binds}) "
                                 f"RETURNING {q(meta['key'])}"), p).scalar()
        else:
            neu = c.execute(text(f"INSERT INTO {_voll(engine, meta)} ({cols}) VALUES ({binds})"),
                            p).lastrowid
        zeile = _zeile_lesen(c, engine, meta, neu) if neu is not None else None
    _protokoll(db, f, user, "datenpflege_anlegen",
               f"{meta['tabelle']}: Zeile {neu} angelegt",
               {"tabelle": meta["tabelle"], "key": neu, "werte": {k: _json(v) for k, v in werte.items()}})
    return {"ok": True, "key": neu, "zeile": zeile}


class AendernIn(BaseModel):
    key: Any
    werte: Dict[str, Any]
    # Stand der Zeile, als die Maske geöffnet wurde. Hat inzwischen jemand
    # anderes eines der geänderten Felder umgeschrieben, wird nicht überschrieben.
    vorher: Optional[Dict[str, Any]] = None


def _gleich(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return str(a) == str(b)


@router.put("/{form_id}/{widget_id}")
def aendern(form_id: int, widget_id: str, data: AendernIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    f, cfg, conn_id = _widget(form_id, widget_id, user, db, schreiben=True)
    engine = _engine(conn_id)
    meta = _meta(engine, cfg)
    q = _q(engine)
    spalten = {s["name"]: s for s in meta["spalten"] if s["bearbeitbar"]}
    werte = {n: _wert(spalten[n], v) for n, v in data.werte.items() if n in spalten}
    with engine.begin() as c:
        jetzt = _zeile_lesen(c, engine, meta, data.key)
        if jetzt is None:
            raise HTTPException(404, "Die Zeile gibt es nicht mehr")
        geaendert = {n: v for n, v in werte.items() if not _gleich(_json(v), jetzt.get(n))}
        if not geaendert:
            return {"ok": True, "geaendert": 0, "zeile": jetzt}
        if data.vorher:
            konflikt = [spalten[n]["label"] for n in geaendert
                        if n in data.vorher and not _gleich(data.vorher[n], jetzt.get(n))]
            if konflikt:
                raise HTTPException(409, "Inzwischen hat jemand anderes geändert: "
                                         + ", ".join(konflikt) + " – bitte neu laden")
        _eindeutig_pruefen(c, engine, meta, geaendert, ausser_key=data.key)
        setz = ", ".join(f"{q(n)} = :p{i}" for i, n in enumerate(geaendert))
        p = {f"p{i}": v for i, v in enumerate(geaendert.values())}
        p["k"] = data.key
        c.execute(text(f"UPDATE {_voll(engine, meta)} SET {setz} WHERE {q(meta['key'])} = :k"), p)
        zeile = _zeile_lesen(c, engine, meta, data.key)
    _protokoll(db, f, user, "datenpflege_aendern",
               f"{meta['tabelle']}: Zeile {data.key} geändert ({', '.join(geaendert)})",
               {"tabelle": meta["tabelle"], "key": data.key,
                "alt": {n: jetzt.get(n) for n in geaendert},
                "neu": {n: _json(v) for n, v in geaendert.items()}})
    return {"ok": True, "geaendert": len(geaendert), "zeile": zeile}


class SperrenIn(BaseModel):
    key: Any
    aktiv: bool


@router.post("/{form_id}/{widget_id}/aktiv")
def aktiv_setzen(form_id: int, widget_id: str, data: SperrenIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    f, cfg, conn_id = _widget(form_id, widget_id, user, db, schreiben=True)
    engine = _engine(conn_id)
    meta = _meta(engine, cfg)
    if not meta["aktiv_spalte"]:
        raise HTTPException(400, "Im Widget ist keine Aktiv-Spalte eingestellt")
    q = _q(engine)
    with engine.begin() as c:
        n = c.execute(text(f"UPDATE {_voll(engine, meta)} SET {q(meta['aktiv_spalte'])} = :a "
                           f"WHERE {q(meta['key'])} = :k"),
                      {"a": data.aktiv, "k": data.key}).rowcount
        if not n:
            raise HTTPException(404, "Die Zeile gibt es nicht mehr")
        zeile = _zeile_lesen(c, engine, meta, data.key)
    _protokoll(db, f, user, "datenpflege_aktiv",
               f"{meta['tabelle']}: Zeile {data.key} {'entsperrt' if data.aktiv else 'gesperrt'}",
               {"tabelle": meta["tabelle"], "key": data.key, "aktiv": data.aktiv})
    return {"ok": True, "zeile": zeile}

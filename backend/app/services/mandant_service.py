"""Mandantenfähigkeit: ein Satz Cockpits, mehrere JTL-Datenbanken.

Ausgangslage: sämtliche Cockpit-Mappings holen ihre Zahlen über genau einen
SQL-Knoten im Modus "transform" mit fest hinterlegter `connection_id`. Ein Mandant
ist deshalb nichts anderes als eine andere Verbindung – es braucht weder Kopien der
Mappings noch ein zweites Projekt, nur den Austausch dieser einen Zahl zur Laufzeit.

Was hier passiert:
  * `mandanten()`      – welche Verbindungen eines Projekts sind als Mandant markiert
  * `erlaubte()`       – davon: welche darf dieser Benutzer sehen (Freigaben)
  * `aktiver()`        – welchen sieht er gerade (gespeicherte Auswahl, sonst Standard)
  * `kontext()`        – beides zusammen, plus Anzeigename für Kopfzeilen und Reports
  * `verbindung_ersetzen()` – biegt einen MappingContext auf den Mandanten um

Bewusst NICHT umgebogen werden Schreibziele (`targets[*].target_connection_id`):
ein Lauf, der Daten wegschreibt, muss dorthin schreiben, wo er immer hingeschrieben
hat. Ein stillschweigend mitgewanderter Schreibpfad wäre die gefährlichste Art von
Überraschung, die dieses Feature haben könnte.
"""
from typing import Optional, List, Dict


# ── Stammdaten ───────────────────────────────────────────────────────────────

def _label(conn) -> str:
    return (getattr(conn, "mandant_label", None) or conn.name or f"Verbindung {conn.id}")


def _als_dict(conn) -> dict:
    return {
        "connection_id": conn.id,
        "name":          _label(conn),
        "verbindung":    conn.name,
        "datenbank":     conn.database,
        "host":          conn.host,
        "project_id":    conn.project_id,
        "ist_standard":  bool(getattr(conn, "is_mandant_default", False)),
    }


def mandanten(project_id: Optional[int], db) -> List[dict]:
    """Alle als Mandant gekennzeichneten Verbindungen des Projekts."""
    from app.models.dataset import DbConnection
    if db is None:
        return []
    q = db.query(DbConnection).filter(DbConnection.is_mandant.is_(True))
    if project_id is not None:
        q = q.filter(DbConnection.project_id == project_id)
    rows = q.all()
    rows.sort(key=lambda c: (getattr(c, "mandant_sort", 100) or 100, c.id))
    return [_als_dict(c) for c in rows]


def freigegebene_ids(user, db) -> Optional[set]:
    """IDs der für diesen Benutzer freigegebenen Verbindungen.

    None bedeutet "keine Einschränkung" – das ist der Normalfall und der Zustand
    jeder bestehenden Installation. Erst wer mindestens eine Freigabe einträgt,
    wird auf genau diese beschränkt.
    """
    if user is None:
        return None
    if getattr(user, "is_admin", False):
        return None
    from app.models.mandant import MandantFreigabe
    ids = {r.connection_id for r in db.query(MandantFreigabe)
           .filter(MandantFreigabe.user_id == user.id).all()}
    return ids or None


def erlaubte(project_id: Optional[int], user, db) -> List[dict]:
    """Die Mandanten des Projekts, die dieser Benutzer nutzen darf."""
    alle = mandanten(project_id, db)
    erlaubt = freigegebene_ids(user, db)
    if erlaubt is None:
        return alle
    return [m for m in alle if m["connection_id"] in erlaubt]


def standard(project_id: Optional[int], db) -> Optional[int]:
    """Standard-Mandant des Projekts: das ausdrücklich markierte, sonst das erste.

    Dient als Erstauswahl für Benutzer ohne gespeicherte Wahl und als Ziel der
    einmaligen Übernahme bestehender Kostendaten.
    """
    alle = mandanten(project_id, db)
    if not alle:
        return None
    for m in alle:
        if m["ist_standard"]:
            return m["connection_id"]
    return alle[0]["connection_id"]


# ── Auswahl je Benutzer ──────────────────────────────────────────────────────

def aktiver(project_id: Optional[int], user, db) -> Optional[int]:
    """Die aktive Mandanten-Verbindung dieses Benutzers in diesem Projekt.

    None heißt: das Projekt arbeitet (noch) ohne Mandanten – dann bleibt alles
    exakt wie bisher, die Mappings laufen gegen ihre eingetragene Verbindung.
    """
    erlaubt = erlaubte(project_id, user, db)
    if not erlaubt:
        return None
    ids = [m["connection_id"] for m in erlaubt]

    if user is not None:
        from app.models.mandant import MandantAuswahl
        q = db.query(MandantAuswahl).filter(MandantAuswahl.user_id == user.id)
        q = q.filter(MandantAuswahl.project_id == project_id) if project_id is not None \
            else q.filter(MandantAuswahl.project_id.is_(None))
        wahl = q.first()
        # Eine gespeicherte Wahl, die inzwischen entzogen wurde, wird ignoriert
        # statt zu einem Zugriff durch die Hintertür zu werden.
        if wahl and wahl.connection_id in ids:
            return wahl.connection_id

    std = standard(project_id, db)
    return std if std in ids else ids[0]


def waehlen(project_id: Optional[int], user, connection_id: int, db) -> int:
    """Speichert die Mandantenwahl. Wirft, wenn der Mandant nicht freigegeben ist."""
    from fastapi import HTTPException
    from app.models.mandant import MandantAuswahl

    ids = [m["connection_id"] for m in erlaubte(project_id, user, db)]
    if connection_id not in ids:
        raise HTTPException(403, "Dieser Mandant ist für Sie nicht freigegeben")

    q = db.query(MandantAuswahl).filter(MandantAuswahl.user_id == user.id)
    q = q.filter(MandantAuswahl.project_id == project_id) if project_id is not None \
        else q.filter(MandantAuswahl.project_id.is_(None))
    row = q.first()
    if row:
        row.connection_id = connection_id
    else:
        db.add(MandantAuswahl(user_id=user.id, project_id=project_id,
                              connection_id=connection_id))
    db.commit()
    return connection_id


def kontext(project_id: Optional[int], user, db) -> dict:
    """{mandant_id, mandant_name} – für Laufparameter, Kopfzeilen und Reports."""
    mid = aktiver(project_id, user, db)
    if mid is None:
        return {"mandant_id": None, "mandant_name": None}
    return {"mandant_id": mid, "mandant_name": name_von(mid, db)}


def name_von(connection_id: Optional[int], db) -> Optional[str]:
    if connection_id is None or db is None:
        return None
    from app.models.dataset import DbConnection
    c = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    return _label(c) if c else None


def darf_nutzen(connection_id: Optional[int], user, db) -> bool:
    """Darf dieser Benutzer gegen diese Mandanten-Verbindung auswerten?"""
    if connection_id is None:
        return True
    erlaubt = freigegebene_ids(user, db)
    if erlaubt is None:
        return True
    return connection_id in erlaubt


# ── Laufzeit: Mapping auf den Mandanten umbiegen ─────────────────────────────

def _umschreiben(nodes: Optional[List[Dict]], ziel_id: int,
                 austauschbar: set) -> List[Dict]:
    """Ersetzt die connection_id lesender Knoten – aber nur bei bekannten Quellen.

    `austauschbar` sind die Verbindungen, die als Mandant desselben Projekts in
    Frage kommen. Ein Knoten, der bewusst gegen eine ganz andere Datenbank läuft
    (Fremdsystem, Archiv), bleibt dadurch unangetastet.
    """
    if not nodes:
        return nodes or []
    neu = []
    for n in nodes:
        cid = n.get("connection_id")
        if cid is not None and cid != ziel_id and cid in austauschbar:
            n = {**n, "connection_id": ziel_id}
        neu.append(n)
    return neu


def austauschbare_ids(project_id: Optional[int], db) -> set:
    """Verbindungen, deren Rolle ein Mandant übernehmen darf.

    Das sind alle Mandanten des Projekts plus die übrigen Verbindungen desselben
    Projekts – letztere, weil die Cockpits vor der Umstellung auf eine ganz normale
    Projektverbindung zeigten, die niemand als Mandant markiert haben muss.
    """
    from app.models.dataset import DbConnection
    if db is None or project_id is None:
        return set()
    return {c.id for c in db.query(DbConnection)
            .filter(DbConnection.project_id == project_id).all()}


def verbindung_ersetzen(ctx, connection_id: Optional[int], db,
                        project_id: Optional[int] = None) -> None:
    """Biegt einen MappingContext auf den Mandanten um (verändert ctx in place).

    Wirkt auf SQL- und Lookup-Knoten, also auf alles Lesende. Ohne Mandanten oder
    ohne passende Verbindung ist der Aufruf ein No-Op – bestehende Projekte laufen
    unverändert weiter.
    """
    if connection_id is None or ctx is None:
        return
    pid = project_id if project_id is not None else getattr(ctx, "project_id", None)
    austauschbar = austauschbare_ids(pid, db)
    if not austauschbar:
        return
    ctx.sql_nodes    = _umschreiben(ctx.sql_nodes, connection_id, austauschbar)
    ctx.lookup_nodes = _umschreiben(ctx.lookup_nodes, connection_id, austauschbar)


def laufparameter(run_params: Optional[dict], connection_id: Optional[int],
                  db) -> dict:
    """Legt :mandant_id / :mandant_name in die Laufparameter.

    Damit kann eine Abfrage den Mandanten anzeigen oder – bei geteilten Datenbanken –
    sogar selbst filtern, ohne dass ein zweites Mapping nötig wäre.
    """
    p = dict(run_params or {})
    if connection_id is not None:
        p.setdefault("mandant_id", connection_id)
        p.setdefault("mandant_name", name_von(connection_id, db) or "")
    return p


def lauf_vorbereiten(run_params: Optional[dict], project_id: Optional[int], db,
                     user=None, mandant_id: Optional[int] = None):
    """Ein Aufruf für alles, was ein Lauf vom Mandanten braucht.

    Gibt (run_params, mandant_id) zurück: Schwellwerte und Fixkosten des richtigen
    Mandanten, dessen Ausschlussliste und die Parameter :mandant_id/:mandant_name.

    Absichtlich gebündelt: die drei Schritte einzeln an sieben Ausführungspfaden zu
    wiederholen ist genau die Sorte Aufgabe, bei der irgendwann einer vergessen wird
    – und ein vergessener Pfad zeigt Zahlen des falschen Betriebs, ohne dass es
    irgendwo knallt.
    """
    from app.services.business_config_service import apply_config
    from app.services.article_exclusion_service import apply_article_exclusions

    if mandant_id is None:
        mandant_id = aktiver(project_id, user, db)
    p = apply_config(run_params or {}, project_id, db, mandant_id)
    p = apply_article_exclusions(p, project_id, db, mandant_id)
    p = laufparameter(p, mandant_id, db)
    return p, mandant_id

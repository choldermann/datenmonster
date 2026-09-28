"""
Zentrale Zugriffsprüfung für Objekte (Sicherheitsreview 2, Stufe 2).

Vorher prüfte jeder Router selbst – und viele nur „angemeldet“. Ein Editor aus
Projekt A kam so an Datasets, Verbindungen und Zeitpläne von Projekt B, bis hin
zu beliebigem SQL gegen die WaWi eines anderen Mandanten. Hier stehen die Regeln
an einer Stelle:

- Admins dürfen alles.
- Ein Objekt gehört zu einem Projekt; lesen darf, wer dort Rolle hat (auch
  Betrachter), ändern nur Eigentümer/Editor (siehe projects.get_project_role).
- Eine Verbindung ist erreichbar, wenn sie einem Projekt zugeordnet ist, in dem
  der Benutzer eine Rolle hat (projekt_verbindungen, sonst alte project_id).
  Bei Mandanten-Verbindungen (is_mandant) gelten zusätzlich die Freigaben aus
  Systemeinstellungen → Mandanten.
"""
from typing import Iterable, Optional

from fastapi import HTTPException


def ist_admin(user) -> bool:
    return bool(getattr(user, "is_admin", False))


def nur_admin(user, meldung: str = "Nur Administratoren") -> None:
    if not ist_admin(user):
        raise HTTPException(403, meldung)


# ── Projekte ──────────────────────────────────────────────────────────────────

def lesen_pruefen(project_id: Optional[int], user, db) -> None:
    from app.api.projects import can_read_project
    if not can_read_project(project_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")


def schreiben_pruefen(project_id: Optional[int], user, db) -> None:
    from app.api.projects import require_editor
    require_editor(project_id, user, db)


def projekte_mit_rolle(user, db) -> set:
    """Projekte, in denen der Benutzer Eigentümer oder Mitglied ist."""
    from app.models.project import Project, ProjectMember
    eigene = {p.id for p in db.query(Project).filter(Project.owner_id == user.id).all()}
    mitglied = {m.project_id for m in db.query(ProjectMember)
                .filter(ProjectMember.user_id == user.id).all()}
    return eigene | mitglied


# ── Verbindungen ──────────────────────────────────────────────────────────────

def erreichbare_verbindungen(user, db) -> Optional[set]:
    """IDs der Verbindungen, die der Benutzer benutzen darf; None = alle (Admin)."""
    if ist_admin(user):
        return None
    from app.services.db_service import verbundene_ids
    ids: set = set()
    for pid in projekte_mit_rolle(user, db):
        ids |= verbundene_ids(pid, db)
    return ids


def darf_verbindung(connection_id, user, db) -> bool:
    if connection_id in (None, "", 0):
        return True
    if ist_admin(user):
        return True
    try:
        cid = int(connection_id)
    except (TypeError, ValueError):
        return False
    erreichbar = erreichbare_verbindungen(user, db)
    if erreichbar is not None and cid not in erreichbar:
        return False
    from app.models.dataset import DbConnection
    conn = db.query(DbConnection).filter(DbConnection.id == cid).first()
    if conn is not None and getattr(conn, "is_mandant", False):
        from app.services.mandant_service import darf_nutzen
        return darf_nutzen(cid, user, db)
    return True


def verbindung_pruefen(connection_id, user, db) -> None:
    if not darf_verbindung(connection_id, user, db):
        raise HTTPException(403, "Kein Zugriff auf diese Verbindung")


def lade_verbindung(connection_id, user, db):
    """Verbindung laden und Zugriff prüfen (404 / 403)."""
    from app.models.dataset import DbConnection
    conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    verbindung_pruefen(conn.id, user, db)
    return conn


def verbindung_bearbeiten_pruefen(connection_id, user, db):
    """Freies SQL gegen eine Verbindung (Vorschau, Import) darf, wer in einem
    Projekt, dem sie zugeordnet ist, Eigentümer oder Editor ist. Betrachter
    nicht – über „Vorschau“ ginge sonst auch ein UPDATE."""
    conn = lade_verbindung(connection_id, user, db)
    if ist_admin(user):
        return conn
    from app.api.projects import get_project_role
    from app.services.db_service import verbundene_ids
    for pid in projekte_mit_rolle(user, db):
        if conn.id in verbundene_ids(pid, db) and get_project_role(pid, user, db) in ("owner", "editor"):
            return conn
    raise HTTPException(403, "Mit dieser Verbindung arbeiten dürfen nur Editoren eines zugeordneten Projekts")


# ── Datasets ──────────────────────────────────────────────────────────────────

def lade_dataset(dataset_id, user, db, schreiben: bool = False):
    from app.models.dataset import Dataset
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    if schreiben:
        schreiben_pruefen(ds.project_id, user, db)
    else:
        lesen_pruefen(ds.project_id, user, db)
    return ds


def dataset_pruefen(dataset_id, user, db, schreiben: bool = False) -> None:
    if dataset_id in (None, "", 0):
        return
    try:
        lade_dataset(int(dataset_id), user, db, schreiben)
    except (TypeError, ValueError):
        raise HTTPException(400, "Ungültige Dataset-ID")


# ── Mapping-Knoten aus einer Anfrage ──────────────────────────────────────────

def _referenzen(obj, gefunden: dict) -> None:
    """Sammelt rekursiv alle *_connection_id / *connection_id und *dataset_id."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and isinstance(v, (int, str)) and not isinstance(v, bool):
                if k == "connection_id" or k.endswith("_connection_id"):
                    gefunden.setdefault("verbindungen", set()).add(v)
                elif k == "dataset_id" or k.endswith("_dataset_id"):
                    gefunden.setdefault("datasets", set()).add(v)
            _referenzen(v, gefunden)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _referenzen(v, gefunden)


def knoten_pruefen(teile: Iterable, user, db) -> None:
    """Jede Verbindung und jedes Dataset, auf das Knoten/Ziele verweisen, muss
    für den Benutzer erreichbar sein. Die Knoten kommen bei Vorschau/Ausführen
    aus der Anfrage – ohne diese Prüfung liefe darüber SQL gegen jede Verbindung
    und jedes Dataset der Instanz."""
    if ist_admin(user):
        return
    gefunden: dict = {}
    for t in teile:
        _referenzen(t, gefunden)
    for v in gefunden.get("verbindungen", ()):
        n = _als_id(v)
        if n:
            verbindung_pruefen(n, user, db)
    for d in gefunden.get("datasets", ()):
        n = _als_id(d)
        if n:
            dataset_pruefen(n, user, db)


def _als_id(v) -> Optional[int]:
    """Zahl oder None. Platzhalter wie "{{mandant}}" verweisen auf nichts."""
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None

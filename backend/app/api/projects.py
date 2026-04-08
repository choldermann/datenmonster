from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.project import Project, ProjectMember

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ShareRequest(BaseModel):
    user_id: int
    role: str = "editor"  # editor, viewer


def project_out(p: Project, role: str = "owner") -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "owner_id": p.owner_id,
        "role": role,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def get_accessible_project(project_id: int, user: User, db: Session) -> Project:
    """Returns project if user is owner or member, else raises 404."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Projekt nicht gefunden")
    if p.owner_id == user.id:
        return p
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()
    if not member:
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    return p


def get_project_role(project_id: Optional[int], user: User, db: Session) -> str:
    """Returns 'owner', 'editor', 'viewer', or 'none'. None project_id → 'owner' (legacy)."""
    if getattr(user, "is_admin", False):
        return "owner"  # Admins haben überall vollen Zugriff
    if project_id is None:
        return "owner"
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        return "none"
    if p.owner_id == user.id:
        return "owner"
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()
    return member.role if member else "none"


def require_editor(project_id: Optional[int], user: User, db: Session):
    """Raises 403 if user is only viewer or has no access."""
    role = get_project_role(project_id, user, db)
    if role == "none":
        raise HTTPException(403, "Kein Zugriff auf dieses Projekt")
    if role == "viewer":
        raise HTTPException(403, "Betrachter dürfen keine Änderungen vornehmen")


def can_read_project(project_id: Optional[int], user: User, db: Session) -> bool:
    """Gibt True zurück wenn der User das Projekt lesen darf."""
    if getattr(user, "is_admin", False):
        return True
    role = get_project_role(project_id, user, db)
    return role != "none"


def get_accessible_project_ids(user: User, db: Session) -> Optional[list]:
    """
    Gibt alle Projekt-IDs zurück auf die der User Zugriff hat.
    Gibt None zurück wenn kein Filter nötig ist (= alles sichtbar).

    Kein Filter wenn:
    - User ist einziger User auf der Instanz (Single-User/Single-Tenant)
    - Es keine Projekte gibt (Legacy-Modus)
    """
    # Prüfen ob Mehrbenutzer-Modus aktiv ist
    total_users = db.query(User).count()
    if total_users <= 1:
        return None  # Einzelinstanz: alles sichtbar

    total_projects = db.query(Project).count()
    if total_projects == 0:
        return None  # Keine Projekte: Legacy-Modus, alles sichtbar

    owned_ids = [p.id for p in db.query(Project).filter(Project.owner_id == user.id).all()]
    member_ids = [m.project_id for m in db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()]
    return list(set(owned_ids + member_ids))


@router.get("/")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Own projects
    owned = db.query(Project).filter(Project.owner_id == user.id).all()
    # Shared projects
    memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()
    shared_ids = {m.project_id: m.role for m in memberships}
    shared = db.query(Project).filter(Project.id.in_(shared_ids.keys())).all() if shared_ids else []

    result = [project_out(p, "owner") for p in owned]
    result += [project_out(p, shared_ids[p.id]) for p in shared]
    return result


@router.post("/")
def create_project(data: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = Project(name=data.name, description=data.description, owner_id=user.id)
    db.add(p); db.commit(); db.refresh(p)
    return project_out(p, "owner")


@router.patch("/{project_id}")
def update_project(project_id: int, data: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = get_accessible_project(project_id, user, db)
    if p.owner_id != user.id:
        raise HTTPException(403, "Nur der Eigentümer kann das Projekt bearbeiten")
    p.name = data.name
    p.description = data.description
    db.commit(); db.refresh(p)
    return project_out(p, "owner")


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id, Project.owner_id == user.id).first()
    if not p:
        raise HTTPException(404, "Projekt nicht gefunden oder kein Zugriff")

    from app.models.dataset import Dataset, DbConnection
    from app.models.mapping import Mapping
    from app.models.scheduled_job import ScheduledJob, JobRun
    from app.models.ftp_source import FtpSource
    from app.models.rest_source import RestSource
    from app.models.pipeline import Pipeline
    from app.models.report import Report
    import os

    # Cascade: alle zugehörigen Ressourcen löschen
    # 1. Scheduler-Jobs + Runs
    jobs = db.query(ScheduledJob).filter(ScheduledJob.project_id == project_id).all()
    for job in jobs:
        db.query(JobRun).filter(JobRun.scheduled_job_id == job.id).delete()
        db.delete(job)

    # 2. FTP-Quellen (Scheduler-Jobs deregistrieren)
    from app.api.ftp_sources import _unregister_ftp_job
    for src in db.query(FtpSource).filter(FtpSource.project_id == project_id).all():
        try: _unregister_ftp_job(src.id)
        except Exception as _e:
            import logging as _l; _l.getLogger("datenmonster").warning(f"FTP Job {src.id} deregistrierung: {_e}")
        db.delete(src)

    # 3. REST-Quellen
    db.query(RestSource).filter(RestSource.project_id == project_id).delete()

    # 4. Mappings
    db.query(Mapping).filter(Mapping.project_id == project_id).delete()

    # 5. Pipelines + Reports
    db.query(Pipeline).filter(Pipeline.project_id == project_id).delete()
    db.query(Report).filter(Report.project_id == project_id).delete()

    # 6. Datasets (inkl. Dateien)
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
    for ds in db.query(Dataset).filter(Dataset.project_id == project_id).all():
        for suffix in ["_raw.xml", ".parquet", ".json"]:
            path = os.path.join(UPLOAD_DIR, f"dataset_{ds.id}{suffix}")
            if os.path.exists(path):
                try: os.remove(path)
                except Exception as _e:
                    import logging as _l; _l.getLogger("datenmonster").warning(f"Datei löschen {path}: {_e}")
        db.delete(ds)

    # 7. DB-Verbindungen
    db.query(DbConnection).filter(DbConnection.project_id == project_id).delete()

    # 8. Projekt-Mitglieder + Projekt
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
    db.delete(p)
    db.commit()
    return {"ok": True, "deleted": {
        "jobs": len(jobs),
    }}


@router.get("/{project_id}/members")
def get_members(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_accessible_project(project_id, user, db)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    result = []
    for m in members:
        u = db.query(User).filter(User.id == m.user_id).first()
        if u:
            result.append({"user_id": u.id, "username": u.username, "role": m.role, "member_id": m.id})
    return result


@router.post("/{project_id}/members")
def add_member(project_id: int, req: ShareRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = get_accessible_project(project_id, user, db)
    if p.owner_id != user.id:
        raise HTTPException(403, "Nur der Eigentümer kann Mitglieder hinzufügen")
    if db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == req.user_id).first():
        raise HTTPException(400, "Benutzer ist bereits Mitglied")
    m = ProjectMember(project_id=project_id, user_id=req.user_id, role=req.role)
    db.add(m); db.commit()
    u = db.query(User).filter(User.id == req.user_id).first()
    return {"user_id": u.id, "username": u.username, "role": m.role}


@router.delete("/{project_id}/members/{member_user_id}")
def remove_member(project_id: int, member_user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = get_accessible_project(project_id, user, db)
    if p.owner_id != user.id:
        raise HTTPException(403, "Nur der Eigentümer kann Mitglieder entfernen")
    m = db.query(ProjectMember).filter(ProjectMember.project_id == project_id, ProjectMember.user_id == member_user_id).first()
    if not m:
        raise HTTPException(404, "Mitglied nicht gefunden")
    db.delete(m); db.commit()
    return {"ok": True}

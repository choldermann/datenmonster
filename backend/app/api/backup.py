"""
Datensicherung – Sichern und Zurückspielen aus der Oberfläche.

Die Anwendungsdaten liegen im Volume unter /app/uploads: die Datenbank mit allen
Mappings, Formularen, Warnregeln und Zeitplänen, dazu die Dateien der Datasets.

Die Datenbank wird über die Sicherungsschnittstelle von SQLite kopiert und nicht
mit einer Dateikopie: Bei laufendem Schreibzugriff wäre eine `cp`-Kopie
unbrauchbar. Die Anwendung muss dafür nicht angehalten werden.

Zum Zurückspielen siehe restore(): das ist der Notfallweg und deshalb bewusst
umständlich – mit Bestätigung, automatischer Sicherheitskopie und dem klaren
Hinweis, dass danach ein Neustart nötig ist.

Alles hier ist Administratoren vorbehalten. Ein Archiv enthält die Zugangsdaten
aller Verbindungen (verschlüsselt) und darf niemandem sonst in die Hände fallen.
"""
import io
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/backup", tags=["backup"])

DATEN_VERZ  = "/app/uploads"
SICHER_VERZ = os.path.join(DATEN_VERZ, "backups")
DB_DATEI    = os.path.join(DATEN_VERZ, "datenmonster.db")
BEHALTEN    = 14                      # so viele Archive bleiben auf dem Server liegen
_NAME_MUSTER = re.compile(r"^datenmonster_\d{8}_\d{6}\.tar\.gz$")


def _nur_admin(user: User):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Nur Administratoren dürfen Sicherungen verwalten")


def _archivpfad(name: str) -> str:
    """Pfad zu einem Archiv – und Schutz davor, über den Namen auszubrechen."""
    if not _NAME_MUSTER.match(name or ""):
        raise HTTPException(400, "Ungültiger Name")
    pfad = os.path.join(SICHER_VERZ, name)
    if os.path.dirname(os.path.abspath(pfad)) != os.path.abspath(SICHER_VERZ):
        raise HTTPException(400, "Ungültiger Name")
    if not os.path.exists(pfad):
        raise HTTPException(404, "Sicherung nicht gefunden")
    return pfad


def _datenbank_kopieren(ziel: str):
    """Konsistente Kopie der laufenden Datenbank."""
    quelle = sqlite3.connect(DB_DATEI)
    kopie = sqlite3.connect(ziel)
    try:
        with kopie:
            quelle.backup(kopie)
    finally:
        kopie.close()
        quelle.close()


def _aufraeumen():
    """Nur die jüngsten Archive behalten."""
    archive = sorted(
        (f for f in os.listdir(SICHER_VERZ) if _NAME_MUSTER.match(f)),
        reverse=True)
    for alt in archive[BEHALTEN:]:
        try:
            os.remove(os.path.join(SICHER_VERZ, alt))
        except OSError:
            pass


@router.get("/")
def liste(user: User = Depends(get_current_user)):
    """Vorhandene Sicherungen auf dem Server."""
    _nur_admin(user)
    os.makedirs(SICHER_VERZ, exist_ok=True)
    eintraege = []
    for name in os.listdir(SICHER_VERZ):
        if not _NAME_MUSTER.match(name):
            continue
        pfad = os.path.join(SICHER_VERZ, name)
        eintraege.append({
            "name": name,
            "groesse": os.path.getsize(pfad),
            "erstellt": datetime.fromtimestamp(
                os.path.getmtime(pfad), tz=timezone.utc).isoformat(),
        })
    eintraege.sort(key=lambda e: e["name"], reverse=True)
    frei = shutil.disk_usage(DATEN_VERZ).free
    return {"sicherungen": eintraege, "speicher_frei": frei, "behalten": BEHALTEN}


@router.post("/")
def erstellen(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Neue Sicherung anlegen: Datenbank + Dataset-Dateien."""
    _nur_admin(user)
    os.makedirs(SICHER_VERZ, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"datenmonster_{stempel}.tar.gz"
    ziel = os.path.join(SICHER_VERZ, name)

    arbeit = tempfile.mkdtemp()
    try:
        db_kopie = os.path.join(arbeit, "datenmonster.db")
        _datenbank_kopieren(db_kopie)

        dateien = os.path.join(arbeit, "uploads")
        os.makedirs(dateien, exist_ok=True)
        anzahl = 0
        for f in os.listdir(DATEN_VERZ):
            if f.startswith("dataset_"):
                shutil.copy2(os.path.join(DATEN_VERZ, f), os.path.join(dateien, f))
                anzahl += 1

        with open(os.path.join(arbeit, "SICHERUNG.txt"), "w", encoding="utf-8") as fh:
            fh.write(f"erstellt={datetime.now(timezone.utc).isoformat()}\n")
            fh.write(f"version={os.getenv('APP_VERSION', 'unbekannt')}\n")
            fh.write(f"quelle=oberflaeche\n")
            fh.write(f"benutzer={user.username}\n")

        with tarfile.open(ziel, "w:gz") as tar:
            tar.add(arbeit, arcname=".")
        os.chmod(ziel, 0o600)
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)

    _aufraeumen()

    try:
        from app.services.db_logger import log as _log
        _log(db, "success", "backup", "backup_created",
             f"Sicherung '{name}' angelegt ({os.path.getsize(ziel) // 1024} KB)",
             details={"datasets": anzahl, "benutzer": user.username})
    except Exception:
        pass

    return {"ok": True, "name": name, "groesse": os.path.getsize(ziel),
            "datasets": anzahl}


@router.get("/{name}/download")
def herunterladen(name: str, user: User = Depends(get_current_user)):
    """Archiv herunterladen – der eigentlich wichtige Schritt: eine Sicherung,
    die nur auf demselben Server liegt, hilft beim Serverausfall nicht."""
    _nur_admin(user)
    return FileResponse(_archivpfad(name), filename=name,
                        media_type="application/gzip")


@router.delete("/{name}")
def loeschen(name: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _nur_admin(user)
    pfad = _archivpfad(name)
    os.remove(pfad)
    try:
        from app.services.db_logger import log as _log
        _log(db, "info", "backup", "backup_deleted",
             f"Sicherung '{name}' gelöscht", details={"benutzer": user.username})
    except Exception:
        pass
    return {"ok": True}


def _pruefe_archiv(pfad: str) -> dict:
    """Archiv auspacken und prüfen, ob eine brauchbare Datenbank drinsteckt.

    Gibt das Arbeitsverzeichnis zurück – der Aufrufer räumt es weg.
    """
    arbeit = tempfile.mkdtemp()
    try:
        with tarfile.open(pfad, "r:gz") as tar:
            for mitglied in tar.getmembers():
                # Kein Ausbrechen über ../ oder absolute Pfade
                ziel = os.path.realpath(os.path.join(arbeit, mitglied.name))
                if not ziel.startswith(os.path.realpath(arbeit)):
                    raise HTTPException(400, "Archiv enthält unerlaubte Pfade")
                if mitglied.issym() or mitglied.islnk():
                    raise HTTPException(400, "Archiv enthält Verweise")
            tar.extractall(arbeit)

        db_datei = os.path.join(arbeit, "datenmonster.db")
        if not os.path.exists(db_datei):
            raise HTTPException(400, "Im Archiv ist keine Datenbank enthalten")

        pruef = sqlite3.connect(f"file:{db_datei}?mode=ro", uri=True)
        try:
            zustand = pruef.execute("PRAGMA integrity_check").fetchone()[0]
            if zustand != "ok":
                raise HTTPException(400, f"Die Datenbank im Archiv ist beschädigt: {zustand}")
            zahlen = {}
            for t in ("mappings", "forms", "datasets", "alert_rules", "users"):
                try:
                    zahlen[t] = pruef.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except sqlite3.Error:
                    zahlen[t] = None
        finally:
            pruef.close()
        return {"arbeit": arbeit, "zahlen": zahlen}
    except HTTPException:
        shutil.rmtree(arbeit, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(arbeit, ignore_errors=True)
        raise HTTPException(400, f"Archiv nicht lesbar: {str(e)[:200]}")


@router.post("/restore")
async def zurueckspielen(datei: UploadFile = File(None), name: str = None,
                         bestaetigt: bool = False,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """
    Sicherung zurückspielen – entweder eine hochgeladene Datei oder eine, die
    auf dem Server liegt (`name`).

    Ohne `bestaetigt=true` wird nur geprüft und berichtet, was drinsteckt. Das
    ist Absicht: Wer zurückspielt, soll vorher sehen, was er bekommt.

    **Danach ist der bisherige Stand weg und ein Neustart des Containers nötig.**
    Die laufende Anwendung hält die alte Datei weiterhin offen; erst nach dem
    Neustart arbeitet sie mit den zurückgespielten Daten.
    """
    _nur_admin(user)

    if datei is not None:
        quelle = tempfile.mktemp(suffix=".tar.gz")
        with open(quelle, "wb") as fh:
            fh.write(await datei.read())
        temporaer = True
    elif name:
        quelle = _archivpfad(name)
        temporaer = False
    else:
        raise HTTPException(400, "Weder eine Datei noch ein Name angegeben")

    geprueft = _pruefe_archiv(quelle)
    arbeit = geprueft["arbeit"]
    try:
        if not bestaetigt:
            return {"ok": True, "geprueft": True, "inhalt": geprueft["zahlen"],
                    "hinweis": ("Beim Zurückspielen wird der jetzige Stand ersetzt. "
                                "Danach ist ein Neustart des Backend-Containers nötig.")}

        # Sicherheitsnetz: der jetzige Stand kommt vor dem Überschreiben ins Archiv.
        os.makedirs(SICHER_VERZ, exist_ok=True)
        vorher = os.path.join(
            SICHER_VERZ, f"datenmonster_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz")
        vor_arbeit = tempfile.mkdtemp()
        try:
            _datenbank_kopieren(os.path.join(vor_arbeit, "datenmonster.db"))
            os.makedirs(os.path.join(vor_arbeit, "uploads"), exist_ok=True)
            for f in os.listdir(DATEN_VERZ):
                if f.startswith("dataset_"):
                    shutil.copy2(os.path.join(DATEN_VERZ, f),
                                 os.path.join(vor_arbeit, "uploads", f))
            with open(os.path.join(vor_arbeit, "SICHERUNG.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"erstellt={datetime.now(timezone.utc).isoformat()}\n")
                fh.write("quelle=automatisch vor dem Zurückspielen\n")
            with tarfile.open(vorher, "w:gz") as tar:
                tar.add(vor_arbeit, arcname=".")
            os.chmod(vorher, 0o600)
        finally:
            shutil.rmtree(vor_arbeit, ignore_errors=True)

        shutil.copy2(os.path.join(arbeit, "datenmonster.db"), DB_DATEI)
        zurueck = 0
        quell_uploads = os.path.join(arbeit, "uploads")
        if os.path.isdir(quell_uploads):
            for f in os.listdir(quell_uploads):
                shutil.copy2(os.path.join(quell_uploads, f), os.path.join(DATEN_VERZ, f))
                zurueck += 1

        try:
            from app.services.db_logger import log as _log
            _log(db, "warning", "backup", "backup_restored",
                 "Sicherung zurückgespielt – Neustart erforderlich",
                 details={"inhalt": geprueft["zahlen"], "benutzer": user.username,
                          "sicherheitskopie": os.path.basename(vorher)})
        except Exception:
            pass

        return {"ok": True, "zurueckgespielt": True, "inhalt": geprueft["zahlen"],
                "dateien": zurueck, "sicherheitskopie": os.path.basename(vorher),
                "hinweis": ("Zurückgespielt. Der Container muss jetzt neu gestartet "
                            "werden – bis dahin arbeitet die Anwendung weiter mit dem "
                            "alten Stand: docker compose restart backend")}
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
        if temporaer:
            try:
                os.remove(quelle)
            except OSError:
                pass

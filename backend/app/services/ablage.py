"""
Ablage = woher Dateien kommen und wohin sie gehen: FTP, SFTP oder ein Ordner.

Eine FtpSource mit protocol="ordner" ist ein Hotfolder: Dateien, die jemand in
den Austauschordner legt, werden beim nächsten Lauf eingelesen und danach
verschoben/gelöscht; nicht lesbare Dateien wandern in den Fehler-Ordner.

Ordner sind auf den Austauschordner beschränkt (Umgebungsvariable
AUSTAUSCH_BASIS, Vorgabe /app/austausch). Ein Netzlaufwerk bindet man auf dem
Server dort ein (docker-compose: AUSTAUSCH_DIR). So kann eine Quelle nie
/app/uploads/datenmonster.db oder ähnliches lesen.
"""
import fnmatch
import io
import os
import time
from datetime import datetime
from typing import List

from app.core.security import decrypt_credential

# Datei gilt als fertig geschrieben, wenn sie so lange nicht verändert wurde.
# Sonst liest der Lauf eine Datei, die ein anderes Programm gerade noch kopiert.
RUHEZEIT_SEK = 5


def austausch_basis() -> str:
    return os.path.realpath(os.environ.get("AUSTAUSCH_BASIS", "/app/austausch"))


def ordner_pfad(rel: str) -> str:
    """Relativen (oder mit / beginnenden) Pfad in den Austauschordner auflösen.
    Wirft ValueError, wenn er hinausführt (../, Symlink)."""
    basis = austausch_basis()
    pfad = os.path.realpath(os.path.join(basis, (rel or "").lstrip("/\\")))
    if os.path.commonpath([basis, pfad]) != basis:
        raise ValueError(f"Pfad „{rel}“ liegt außerhalb des Austauschordners")
    return pfad


class Ablage:
    def dateien(self, verz: str, muster: str) -> List[str]: ...
    def lesen(self, verz: str, name: str) -> bytes: ...
    def verschieben(self, verz: str, name: str, ziel_verz: str) -> None: ...
    def loeschen(self, verz: str, name: str) -> None: ...
    def schreiben(self, verz: str, name: str, daten: bytes) -> None: ...
    def schliessen(self) -> None: ...

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.schliessen()


def _p(verz: str, name: str) -> str:
    return f"{(verz or '/').rstrip('/')}/{name}"


class FtpAblage(Ablage):
    def __init__(self, host, port, user, pw):
        from app.services.ftp_service import _connect_ftp
        self.c = _connect_ftp(host, port, user, pw)

    def dateien(self, verz, muster):
        from app.services.ftp_service import list_files_ftp
        return list_files_ftp(self.c, verz, muster)

    def lesen(self, verz, name):
        from app.services.ftp_service import download_file_ftp
        return download_file_ftp(self.c, verz, name)

    def verschieben(self, verz, name, ziel_verz):
        self.c.rename(_p(verz, name), _p(ziel_verz, name))

    def loeschen(self, verz, name):
        self.c.delete(_p(verz, name))

    def schreiben(self, verz, name, daten):
        temp = _p(verz, name + ".part")
        self.c.storbinary(f"STOR {temp}", io.BytesIO(daten))
        try:
            self.c.delete(_p(verz, name))
        except Exception:  # noqa: BLE001 – gab es noch nicht
            pass
        self.c.rename(temp, _p(verz, name))

    def schliessen(self):
        try:
            self.c.quit()
        except Exception:  # noqa: BLE001
            pass


class SftpAblage(Ablage):
    def __init__(self, host, port, user, pw):
        from app.services.ftp_service import _connect_sftp
        self.c = _connect_sftp(host, port, user, pw)

    def dateien(self, verz, muster):
        from app.services.ftp_service import list_files_sftp
        return list_files_sftp(self.c, verz, muster)

    def lesen(self, verz, name):
        from app.services.ftp_service import download_file_sftp
        return download_file_sftp(self.c, verz, name)

    def verschieben(self, verz, name, ziel_verz):
        self.c.rename(_p(verz, name), _p(ziel_verz, name))

    def loeschen(self, verz, name):
        self.c.remove(_p(verz, name))

    def schreiben(self, verz, name, daten):
        temp = _p(verz, name + ".part")
        self.c.putfo(io.BytesIO(daten), temp)
        try:
            self.c.remove(_p(verz, name))
        except IOError:
            pass
        self.c.rename(temp, _p(verz, name))

    def schliessen(self):
        try:
            self.c.close()
            self.c._ssh.close()
        except Exception:  # noqa: BLE001
            pass


class OrdnerAblage(Ablage):
    def dateien(self, verz, muster):
        pfad = ordner_pfad(verz)
        if not os.path.isdir(pfad):
            raise ValueError(f"Ordner „{verz}“ gibt es nicht (im Austauschordner)")
        jetzt = time.time()
        namen = []
        for n in sorted(os.listdir(pfad)):
            voll = os.path.join(pfad, n)
            if not os.path.isfile(voll) or n.endswith(".part") or n.startswith("."):
                continue
            if not fnmatch.fnmatch(n, muster or "*"):
                continue
            if jetzt - os.path.getmtime(voll) < RUHEZEIT_SEK:
                continue  # wird gerade noch geschrieben – nächster Lauf
            namen.append(n)
        return namen

    def lesen(self, verz, name):
        with open(os.path.join(ordner_pfad(verz), name), "rb") as f:
            return f.read()

    def verschieben(self, verz, name, ziel_verz):
        ziel = ordner_pfad(ziel_verz)
        os.makedirs(ziel, exist_ok=True)
        dst = os.path.join(ziel, name)
        if os.path.exists(dst):
            # Gleichnamige Datei vom letzten Mal nicht überschreiben
            stamm, ext = os.path.splitext(name)
            dst = os.path.join(ziel, f"{stamm}_{datetime.now():%Y%m%d_%H%M%S}{ext}")
        os.replace(os.path.join(ordner_pfad(verz), name), dst)

    def loeschen(self, verz, name):
        os.remove(os.path.join(ordner_pfad(verz), name))

    def schreiben(self, verz, name, daten):
        ziel = ordner_pfad(verz)
        os.makedirs(ziel, exist_ok=True)
        if os.path.basename(name) != name:
            raise ValueError(f"Ungültiger Dateiname „{name}“")
        temp = os.path.join(ziel, name + ".part")
        with open(temp, "wb") as f:
            f.write(daten)
        os.replace(temp, os.path.join(ziel, name))

    def schliessen(self):
        pass


def ablage_oeffnen(source) -> Ablage:
    proto = (source.protocol or "ftp").lower()
    if proto == "ordner":
        return OrdnerAblage()
    pw = decrypt_credential(source.password) if source.password else ""
    if proto == "sftp":
        return SftpAblage(source.host, source.port, source.username, pw)
    return FtpAblage(source.host, source.port, source.username, pw)

"""
ftp_service – verbindet mit FTP/SFTP, listet Dateien, lädt herunter,
merged mehrere Dateien, schreibt in Dataset.
"""
import fnmatch
import io
import logging
import traceback
from app.core.security import decrypt_credential
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


# ─── Verbindungs-Helfer ───────────────────────────────────────────────────────

def _connect_ftp(host: str, port: int, username: str, password: str):
    import ftplib
    port = port or 21
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=15)
    ftp.login(username, password)
    ftp.set_pasv(True)
    return ftp


def _connect_sftp(host: str, port: int, username: str, password: str):
    import paramiko
    port = port or 22
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=username, password=password, timeout=15)
    sftp = ssh.open_sftp()
    sftp._ssh = ssh   # keep reference so SSH stays alive
    return sftp


# ─── Dateilisting ─────────────────────────────────────────────────────────────

def list_files_ftp(ftp, remote_dir: str, filename_filter: str) -> list[str]:
    """Returns list of matching filenames (not full paths) in remote_dir."""
    try:
        ftp.cwd(remote_dir)
    except Exception as e:
        raise ValueError(f"Verzeichnis '{remote_dir}' nicht gefunden: {e}")
    all_files = ftp.nlst()
    # nlst may return full paths – take basename
    all_files = [f.split("/")[-1] for f in all_files]
    matched = [f for f in all_files if fnmatch.fnmatch(f, filename_filter or "*")]
    return matched


def list_files_sftp(sftp, remote_dir: str, filename_filter: str) -> list[str]:
    try:
        entries = sftp.listdir(remote_dir)
    except Exception as e:
        raise ValueError(f"Verzeichnis '{remote_dir}' nicht gefunden: {e}")
    matched = [f for f in entries if fnmatch.fnmatch(f, filename_filter or "*")]
    return matched


# ─── Download ─────────────────────────────────────────────────────────────────

def download_file_ftp(ftp, remote_dir: str, filename: str) -> bytes:
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {remote_dir.rstrip('/')}/{filename}", buf.write)
    return buf.getvalue()


def download_file_sftp(sftp, remote_dir: str, filename: str) -> bytes:
    path = f"{remote_dir.rstrip('/')}/{filename}"
    buf = io.BytesIO()
    sftp.getfo(path, buf)
    return buf.getvalue()


# ─── After-import actions ─────────────────────────────────────────────────────

def move_file_ftp(ftp, remote_dir: str, filename: str, move_dir: str):
    src = f"{remote_dir.rstrip('/')}/{filename}"
    dst = f"{move_dir.rstrip('/')}/{filename}"
    try:
        ftp.rename(src, dst)
    except Exception as e:
        logger.warning(f"FTP move fehlgeschlagen {src} → {dst}: {e}")
        raise


def delete_file_ftp(ftp, remote_dir: str, filename: str):
    path = f"{remote_dir.rstrip('/')}/{filename}"
    try:
        ftp.delete(path)
    except Exception as e:
        logger.warning(f"FTP delete fehlgeschlagen {path}: {e}")
        raise


def move_file_sftp(sftp, remote_dir: str, filename: str, move_dir: str):
    src = f"{remote_dir.rstrip('/')}/{filename}"
    dst = f"{move_dir.rstrip('/')}/{filename}"
    try:
        sftp.rename(src, dst)
    except Exception as e:
        logger.warning(f"SFTP move fehlgeschlagen {src} → {dst}: {e}")
        raise


def delete_file_sftp(sftp, remote_dir: str, filename: str):
    path = f"{remote_dir.rstrip('/')}/{filename}"
    try:
        sftp.remove(path)
    except Exception as e:
        logger.warning(f"SFTP delete fehlgeschlagen {path}: {e}")
        raise


# ─── Upload ───────────────────────────────────────────────────────────────────

def upload_file_ftp(ftp, remote_dir: str, filename: str, data: bytes):
    """Lädt Bytes als Datei auf FTP-Server hoch."""
    path = f"{remote_dir.rstrip('/')}/{filename}"
    ftp.storbinary(f"STOR {path}", io.BytesIO(data))


def upload_file_sftp(sftp, remote_dir: str, filename: str, data: bytes):
    """Lädt Bytes als Datei auf SFTP-Server hoch."""
    path = f"{remote_dir.rstrip('/')}/{filename}"
    sftp.putfo(io.BytesIO(data), path)


def upload_file_ftp_source(source, df: "pd.DataFrame", remote_dir: str, filename: str) -> int:
    """Exportiert DataFrame als CSV und lädt auf FTP/SFTP-Ziel hoch. Gibt Zeilenanzahl zurück."""
    password = decrypt_credential(source.password) if source.password else ""
    data = df.to_csv(index=False).encode("utf-8")

    if (source.protocol or "ftp") == "sftp":
        sftp = _connect_sftp(source.host, source.port, source.username, password)
        try:
            upload_file_sftp(sftp, remote_dir, filename, data)
        finally:
            sftp._ssh.close()
    else:
        ftp = _connect_ftp(source.host, source.port, source.username, password)
        try:
            upload_file_ftp(ftp, remote_dir, filename, data)
        finally:
            try:
                ftp.quit()
            except Exception:
                pass

    logger.info(f"FTP-Upload abgeschlossen: {remote_dir.rstrip('/')}/{filename} ({len(df)} Zeilen)")
    return len(df)


# ─── Datei parsen ─────────────────────────────────────────────────────────────

def parse_bytes(data: bytes, filename: str, file_type: str, csv_delimiter: str = ";", skip_rows: int = 0) -> pd.DataFrame:
    """Parse downloaded bytes into a DataFrame."""
    buf = io.BytesIO(data)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    actual_type = file_type or ("xlsx" if ext in ("xlsx", "xls") else "csv")

    if actual_type == "xlsx" or ext in ("xlsx", "xls"):
        return pd.read_excel(buf, skiprows=skip_rows if skip_rows else None)
    elif actual_type == "ods" or ext == "ods":
        return pd.read_excel(buf, engine="odf", skiprows=skip_rows if skip_rows else None)
    elif actual_type == "xml" or ext == "xml":
        import xml.etree.ElementTree as ET
        tree = ET.parse(buf)
        root = tree.getroot()
        rows = []
        for child in root:
            rows.append({sub.tag: sub.text for sub in child})
        return pd.DataFrame(rows)
    else:
        # CSV – try configured delimiter, fallback to auto
        text_data = data.decode("utf-8-sig", errors="replace")
        try:
            return pd.read_csv(io.StringIO(text_data), sep=csv_delimiter)
        except Exception:
            return pd.read_csv(io.StringIO(text_data), sep=None, engine="python")


# ─── Haupt-Sync-Funktion ──────────────────────────────────────────────────────

def run_ftp_sync(source, db) -> dict:
    """
    Führt einen FTP/SFTP-Sync für eine FtpSource durch.
    Gibt { rows, files_processed, errors } zurück.
    Wirft bei schwerem Fehler eine Exception.
    """
    from app.models.dataset import Dataset
    from app.services.file_service import dataframe_to_storage
    from datetime import datetime, timezone

    protocol = (source.protocol or "ftp").lower()
    conn = None
    errors = []
    files_processed = []
    dfs = []

    try:
        # 1. Verbinden
        if protocol == "sftp":
            conn = _connect_sftp(source.host, source.port, source.username, decrypt_credential(source.password))
            files = list_files_sftp(conn, source.remote_dir, source.filename_filter or "*")
        else:
            conn = _connect_ftp(source.host, source.port, source.username, decrypt_credential(source.password))
            files = list_files_ftp(conn, source.remote_dir, source.filename_filter or "*")

        logger.info(f"FTP sync '{source.name}': {len(files)} Datei(en) gefunden: {files}")

        if not files:
            return {"rows": 0, "files_processed": [], "errors": [], "info": "Keine passenden Dateien gefunden"}

        # 2. Alle Dateien herunterladen & parsen
        for filename in files:
            try:
                if protocol == "sftp":
                    data = download_file_sftp(conn, source.remote_dir, filename)
                else:
                    data = download_file_ftp(conn, source.remote_dir, filename)

                df = parse_bytes(data, filename, source.file_type, source.csv_delimiter or ";", getattr(source, 'skip_rows', 0) or 0)
                dfs.append(df)
                files_processed.append(filename)
                logger.info(f"  ✓ {filename}: {len(df)} Zeilen, {len(df.columns)} Spalten")
            except Exception as e:
                errors.append(f"{filename}: {str(e)[:200]}")
                # db_logger: Datei-Fehler in system_logs schreiben
                try:
                    from app.services.db_logger import log as _dblog
                    _dblog(db, "error", "ftp_service", "file_import_error",
                        f"FTP-Datei-Fehler: {str(e)[:200]}",
                        entity_name=getattr(source, 'name', 'FTP'),
                        project_id=getattr(source, 'project_id', None),
                        details={"filename": filename,
                                 "exception_type": type(e).__name__,
                                 "exception_message": str(e),
                                 "traceback": traceback.format_exc()})
                except Exception:
                    pass
                logger.error(f"  ✗ {filename}: {e}")

        if not dfs:
            raise ValueError("Keine Datei konnte gelesen werden: " + "; ".join(errors))

        # 3. Zusammenführen
        merged = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
        cols = list(merged.columns)
        total_rows = len(merged)

        # 4. In Dataset schreiben
        if source.dataset_id:
            # Bestehendes Dataset
            ds = db.query(Dataset).filter(Dataset.id == source.dataset_id).first()
            if not ds:
                raise ValueError(f"Dataset #{source.dataset_id} nicht gefunden")

            if source.dataset_mode == "append":
                from app.services.file_service import read_dataset
                try:
                    existing = read_dataset(ds)
                    merged = pd.concat([existing, merged], ignore_index=True)
                    cols = list(merged.columns)
                    total_rows = len(merged)
                except Exception:
                    pass  # Falls Dataset noch leer

            path = dataframe_to_storage(merged, ds.id)
            ds.file_path = path
            ds.row_count = total_rows
            ds.columns = cols
            db.commit()
        else:
            # Neues Dataset anlegen
            ds_name = source.dataset_name_tpl or source.name or "FTP-Import"
            ds = Dataset(
                name=ds_name,
                file_type="csv",
                row_count=total_rows,
                columns=cols,
                xml_configured=1,
                project_id=source.project_id,
            )
            db.add(ds); db.commit(); db.refresh(ds)
            path = dataframe_to_storage(merged, ds.id)
            ds.file_path = path
            ds.row_count = total_rows
            # Wenn dataset_id leer war und mode=replace → für nächsten Run merken
            if source.dataset_mode == "replace" or not source.dataset_id:
                source.dataset_id = ds.id
            db.commit()

        # 5. After-import Aktion
        after = source.after_import or "nothing"
        if after != "nothing":
            for filename in files_processed:
                try:
                    if protocol == "sftp":
                        if after == "move" and source.move_dir:
                            move_file_sftp(conn, source.remote_dir, filename, source.move_dir)
                        elif after == "delete":
                            delete_file_sftp(conn, source.remote_dir, filename)
                    else:
                        if after == "move" and source.move_dir:
                            move_file_ftp(conn, source.remote_dir, filename, source.move_dir)
                        elif after == "delete":
                            delete_file_ftp(conn, source.remote_dir, filename)
                except Exception as e:
                    err_msg = f"After-import '{after}' für {filename}: {str(e)[:100]}"
                    errors.append(err_msg)
                    try:
                        from app.services.db_logger import log as _dblog
                        _dblog(db, "warning", "ftp_service", "after_import_error", err_msg,
                            entity_name=getattr(source, 'name', 'FTP'),
                            project_id=getattr(source, 'project_id', None),
                            details={"filename": filename, "action": after,
                                     "exception_type": type(e).__name__,
                                     "traceback": traceback.format_exc()})
                    except Exception:
                        pass

        # Dispatcher aufrufen für jede verarbeitete Datei
        if source.id:
            try:
                from app.services.dispatcher_service import run_dispatcher
                for i, filename in enumerate(files_processed):
                    df_single = dfs[i] if i < len(dfs) else merged
                    dispatch_results = run_dispatcher(source.id, filename, df_single, b"", db)
                    if dispatch_results:
                        logger.info(f"Dispatcher Ergebnisse: {dispatch_results}")
            except Exception as de:
                logger.warning(f"Dispatcher Fehler (nicht kritisch): {de}")

        # Zentrales Log via db_logger
        try:
            from app.services.db_logger import log as _dblog
            level = "success" if not errors else "warning"
            msg = f"FTP-Sync '{getattr(source,'name','')}': {total_rows} Zeilen, {len(files_processed)} Dateien"
            if errors:
                msg += f", {len(errors)} Fehler"
            _dblog(db, level, "ftp_service", "ftp_sync_complete", msg,
                entity_name=getattr(source, 'name', 'FTP'),
                project_id=getattr(source, 'project_id', None),
                rows_processed=total_rows,
                details={"files_processed": files_processed, "errors": errors})
        except Exception:
            pass
        return {"rows": total_rows, "files_processed": files_processed, "errors": errors}

    finally:
        # Verbindung schließen
        try:
            if conn:
                if protocol == "sftp":
                    conn.close()
                    if hasattr(conn, "_ssh"):
                        conn._ssh.close()
                else:
                    conn.quit()
        except Exception:
            pass
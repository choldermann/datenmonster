"""
Access Import Service
Nutzt mdbtools (mdb-tables, mdb-export) um .mdb/.accdb Dateien zu lesen.
Funktioniert auf Linux ohne Windows-ODBC-Treiber.
"""
import os
import subprocess
import tempfile
import io
import pandas as pd
from typing import List


def _run(cmd: list, timeout: int = 300) -> subprocess.CompletedProcess:
    """Führt einen Shell-Befehl aus und wirft bei Fehler eine Exception."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Befehl fehlgeschlagen: {' '.join(cmd)}\n{result.stderr[:500]}")
    return result


def check_mdbtools() -> bool:
    """Prüft ob mdbtools installiert ist."""
    try:
        subprocess.run(["mdb-tables", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def list_tables(mdb_path: str) -> List[str]:
    """
    Gibt alle Tabellen einer Access-Datei zurück.
    mdb-tables -1 gibt jede Tabelle auf einer eigenen Zeile aus.
    Timeout skaliert mit Dateigröße: 60s Basis + 1s pro MB, max 900s.
    """
    file_mb = os.path.getsize(mdb_path) / (1024 * 1024) if os.path.exists(mdb_path) else 0
    timeout = min(900, max(60, int(file_mb) + 60))
    result = _run(["mdb-tables", "-1", mdb_path], timeout=timeout)
    tables = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    if not tables:
        raise RuntimeError(
            "Keine Tabellen gefunden. Mögliche Ursachen: "
            "Datei beschädigt, falsches Format oder mdbtools unterstützt "
            "dieses Access-Format nicht (.accdb erfordert mdbtools >= 0.9)."
        )
    return tables


def get_table_preview(mdb_path: str, table: str, limit: int = 5) -> dict:
    """
    Liest die ersten `limit` Zeilen einer Tabelle für die Vorschau.
    Gibt { columns, rows } zurück.
    """
    df = read_table(mdb_path, table, limit=limit)
    return {
        "columns": list(df.columns),
        "rows": df.head(limit).to_dict(orient="records"),
        "total_columns": len(df.columns),
    }


def read_table(mdb_path: str, table: str, limit: int = None) -> pd.DataFrame:
    """
    Liest eine komplette Tabelle via mdb-export (CSV-Streaming) in einen DataFrame.
    mdb-export streamt zeilenweise → RAM-schonend auch bei großen Dateien.
    Limit: nur erste N Zeilen lesen (für Preview).
    """
    # mdb-export gibt die erste Zeile als Header aus.
    # -H unterdrückt den Header – weglassen damit Header erhalten bleibt.
    # -d: Delimiter (Komma), -Q: kein Quote-Character (vermeidet Parsing-Probleme)
    cmd = ["mdb-export", "-d", ",", mdb_path, table]

    if limit:
        # Für Preview: nur Header + limit Zeilen via head
        proc_export = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc_head = subprocess.Popen(
            ["head", "-n", str(limit + 1)],  # +1 für Header
            stdin=proc_export.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc_export.stdout.close()
        out, _ = proc_head.communicate(timeout=30)
        proc_export.wait()
        csv_data = out.decode("utf-8", errors="replace")
    else:
        # Vollständiger Export – Timeout skaliert mit Dateigröße
        file_mb = os.path.getsize(mdb_path) / (1024 * 1024) if os.path.exists(mdb_path) else 0
        export_timeout = min(3600, max(120, int(file_mb * 2)))  # ~2s pro MB, max 1h
        result = _run(cmd, timeout=export_timeout)
        csv_data = result.stdout

    if not csv_data.strip():
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            io.StringIO(csv_data),
            header=0,          # Erste Zeile immer als Header
            low_memory=False,
            on_bad_lines="warn",
        )
        # Spaltennamen bereinigen (führende/nachfolgende Leerzeichen)
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:
        raise RuntimeError(f"CSV-Parsing fehlgeschlagen für Tabelle '{table}': {e}")

    return df


def import_from_path(mdb_path: str, table: str) -> pd.DataFrame:
    """
    Importiert eine Tabelle aus einer Access-Datei die bereits auf dem Server liegt.
    """
    if not os.path.exists(mdb_path):
        raise FileNotFoundError(f"Datei nicht gefunden: {mdb_path}")
    ext = os.path.splitext(mdb_path)[1].lower()
    if ext not in (".mdb", ".accdb"):
        raise ValueError(f"Ungültiges Dateiformat: {ext} (erwartet .mdb oder .accdb)")
    return read_table(mdb_path, table)


def import_from_bytes(file_bytes: bytes, filename: str, table: str) -> pd.DataFrame:
    """
    Importiert eine Tabelle aus einem hochgeladenen Datei-Byte-Stream.
    Speichert temporär auf Disk, da mdbtools mit Dateipfaden arbeitet.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".mdb", ".accdb"):
        raise ValueError(f"Ungültiges Dateiformat: {ext} (erwartet .mdb oder .accdb)")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        df = read_table(tmp_path, table)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return df

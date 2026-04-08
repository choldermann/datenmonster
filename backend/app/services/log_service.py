"""
log_service – zentraler Logging-Service für alle Module.
Schreibt in DB und Python-Logger gleichzeitig.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

_py_logger = logging.getLogger("datenmonster")


def write_log(
    module: str,
    action: str,
    message: str,
    level: str = "info",
    entity_id: int = None,
    entity_name: str = None,
    project_id: int = None,
    user_id: int = None,
    duration_ms: int = None,
    rows_processed: int = None,
    rows_before: int = None,
    rows_after: int = None,
    details: Dict = None,
    db=None,
):
    """Schreibt einen Log-Eintrag in die DB und den Python-Logger."""
    # Python Logger
    log_fn = _py_logger.info if level == "info" else _py_logger.warning if level == "warning" else _py_logger.error
    log_fn(f"[{module.upper()}] {action}: {message}")

    # DB Log
    if db is None:
        return
    try:
        from app.models.system_log import SystemLog
        entry = SystemLog(
            level=level,
            module=module,
            action=action,
            message=message,
            details=details,
            entity_id=entity_id,
            entity_name=entity_name,
            project_id=project_id,
            user_id=user_id,
            duration_ms=duration_ms,
            rows_processed=rows_processed,
            rows_before=rows_before,
            rows_after=rows_after,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        _py_logger.error(f"Log-Service DB-Fehler: {e}")


class LogContext:
    """Context Manager für zeitmessende Log-Einträge."""
    def __init__(self, module: str, action: str, entity_name: str = None,
                 entity_id: int = None, project_id: int = None, db=None):
        self.module = module
        self.action = action
        self.entity_name = entity_name
        self.entity_id = entity_id
        self.project_id = project_id
        self.db = db
        self.start_time = None
        self.rows_before = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def success(self, message: str, rows_processed: int = None, rows_before: int = None,
                rows_after: int = None, details: Dict = None):
        ms = int((time.time() - self.start_time) * 1000) if self.start_time else None
        write_log(
            module=self.module, action=self.action, message=message, level="info",
            entity_id=self.entity_id, entity_name=self.entity_name,
            project_id=self.project_id, duration_ms=ms,
            rows_processed=rows_processed, rows_before=rows_before,
            rows_after=rows_after, details=details, db=self.db
        )

    def warning(self, message: str, details: Dict = None):
        ms = int((time.time() - self.start_time) * 1000) if self.start_time else None
        write_log(
            module=self.module, action=self.action, message=message, level="warning",
            entity_id=self.entity_id, entity_name=self.entity_name,
            project_id=self.project_id, duration_ms=ms, details=details, db=self.db
        )

    def error(self, message: str, details: Dict = None):
        ms = int((time.time() - self.start_time) * 1000) if self.start_time else None
        write_log(
            module=self.module, action=self.action, message=message, level="error",
            entity_id=self.entity_id, entity_name=self.entity_name,
            project_id=self.project_id, duration_ms=ms, details=details, db=self.db
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error(f"Unerwarteter Fehler: {str(exc_val)[:200]}")
        return False  # Exception nicht unterdrücken

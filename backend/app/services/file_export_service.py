"""
file_export_service – schreibt Exports in strukturierte Verzeichnisse
und registriert sie in der DB.

Pfad: /app/uploads/exports/{user_id}/{project_slug}/{context}/{name}_{ts}.{ext}
context = "job_{job_id}" | "manual"

Die Dateien liegen im Daten-Volume (/app/uploads). Frueher lagen sie unter
/app/exports im Container selbst – jedes Update legt den Container neu an, und
die Dateien waren weg, waehrend die Liste sie weiter anbot (Download: 410).
"""
import os
import re
from datetime import datetime
from typing import Optional
import pandas as pd

EXPORT_BASE = os.environ.get("EXPORT_BASE_DIR", "/app/uploads/exports")
ALTE_BASIS = "/app/exports"


def alte_exporte_umziehen(db) -> int:
    """Zieht noch vorhandene Dateien aus /app/exports ins Daten-Volume um.

    Laeuft beim Start. Was ein frueheres Update schon geloescht hat, ist nicht
    zu retten; der Eintrag bleibt stehen und meldet sich als „nicht mehr vorhanden“."""
    import shutil
    from app.models.export_file import ExportFile
    if os.path.abspath(EXPORT_BASE) == ALTE_BASIS:
        return 0
    umgezogen = 0
    for ef in db.query(ExportFile).filter(ExportFile.file_path.like(ALTE_BASIS + "/%")).all():
        ziel = os.path.join(EXPORT_BASE, os.path.relpath(ef.file_path, ALTE_BASIS))
        if os.path.exists(ef.file_path):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.move(ef.file_path, ziel)
        elif not os.path.exists(ziel):
            continue   # schon vor dem Umzug verloren
        # sonst: zweiter Eintrag auf dieselbe Datei, die schon umgezogen ist
        ef.file_path = ziel
        umgezogen += 1
    if umgezogen:
        db.commit()
    return umgezogen


def _slug(text: str) -> str:
    """Sanitize to filesystem-safe string."""
    return re.sub(r"[^\w\-]", "_", str(text or "unbekannt"))[:50]


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_export_path(
    user_id: int,
    project_name: Optional[str],
    context: str,        # "manual" or "job_123"
    target_name: str,
    ext: str,
) -> str:
    parts = [EXPORT_BASE, str(user_id), _slug(project_name or "kein_projekt"), context]
    os.makedirs(os.path.join(*parts), exist_ok=True)
    filename = f"{_slug(target_name)}_{_ts()}.{ext}"
    return os.path.join(*parts, filename)


def save_export_file(
    df: pd.DataFrame,
    *,
    user_id: int,
    project_id: Optional[int],
    project_name: Optional[str],
    job_id: Optional[int],
    mapping_id: Optional[int],
    mapping_name: Optional[str],
    target_name: str,
    target_type: str,        # csv | xlsx | json | xml | db
    target_options: dict,
    db,                      # SQLAlchemy Session
    triggered_by: str = "manual",
) -> dict:
    """
    Writes df to disk in the correct format, registers in export_files table.
    Returns { file_path, file_name, file_size, id }.
    Raises on error.
    """
    from app.models.export_file import ExportFile
    from app.services.export_service import (
        export_csv, export_xlsx, export_json, export_xml, export_destatis_csv,
        export_destatis_idev, export_destatis_intrahandel_csv, export_destatis_instat_xml,
        export_datev_extf, export_datev_kompakt,
    )

    context = f"job_{job_id}" if job_id else "manual"
    ext_map = {"csv": "csv", "xlsx": "xlsx", "json": "json", "xml": "xml",
               "destatis_csv": "csv", "destatis_idev": "idev", "destatis_intra_csv": "csv",
               "destatis_instat_xml": "xml",
               "datev_extf": "csv", "datev_kompakt": "csv"}
    ext = ext_map.get(target_type, "csv")
    opts = target_options or {}

    def inhalt(teil: pd.DataFrame) -> bytes:
        if target_type == "csv":
            from app.services.csv_format import csv_optionen
            return export_csv(teil, **csv_optionen(opts))
        if target_type == "destatis_csv":
            return export_destatis_csv(teil, opts.get("destatis_config"))
        if target_type == "destatis_idev":
            return export_destatis_idev(teil, opts.get("idev_config"))
        if target_type == "destatis_intra_csv":
            return export_destatis_intrahandel_csv(teil, opts.get("intra_csv_config"))
        if target_type == "destatis_instat_xml":
            return export_destatis_instat_xml(teil, opts.get("instat_config"))
        if target_type == "datev_extf":
            return export_datev_extf(teil, opts.get("datev_config"))
        if target_type == "datev_kompakt":
            return export_datev_kompakt(teil, opts.get("datev_config"))
        if target_type == "xlsx":
            return export_xlsx(teil)
        if target_type == "json":
            return export_json(teil, orient=opts.get("orient", "records"), indent=opts.get("indent", 2))
        if target_type == "xml":
            return export_xml(teil, opts.get("xml_template", {}))
        raise ValueError(f"Unbekannter target_type für Datei-Export: {target_type}")

    # Eine Datei je Wert einer Spalte (z.B. je Lieferant)
    gruppe_nach = (opts.get("gruppe_nach") or "").strip()
    if gruppe_nach:
        if gruppe_nach not in df.columns:
            raise ValueError(f"„Eine Datei je“: Spalte „{gruppe_nach}“ gibt es in der Ausgabe nicht "
                             f"(vorhanden: {', '.join(map(str, df.columns))})")
        teile = [(("leer" if pd.isna(k) else k), g)
                 for k, g in df.groupby(gruppe_nach, dropna=False, sort=True)]
    else:
        teile = [(None, df)]

    # Zusätzlich auf FTP/SFTP/Ordner ablegen – nur Quellen desselben Projekts,
    # sonst ließen sich fremde Zugangsdaten als Ausleitung benutzen.
    ablage = None
    ablage_verz = opts.get("ablage_verzeichnis") or "/"
    if opts.get("ablage_quelle_id"):
        from app.models.ftp_source import FtpSource
        from app.services.ablage import ablage_oeffnen
        quelle = db.query(FtpSource).filter(FtpSource.id == int(opts["ablage_quelle_id"])).first()
        if not quelle:
            raise ValueError(f"Ablage: Datei-Quelle #{opts['ablage_quelle_id']} nicht gefunden")
        if quelle.project_id != project_id:
            raise ValueError(f"Ablage: Datei-Quelle „{quelle.name}“ gehört zu einem anderen Projekt")
        ablage = ablage_oeffnen(quelle)

    muster = (opts.get("dateiname") or "").strip()
    ordner = os.path.join(EXPORT_BASE, str(user_id), _slug(project_name or "kein_projekt"), context)
    os.makedirs(ordner, exist_ok=True)
    ergebnisse = []
    try:
        for gruppe, teil in teile:
            erste = teil.iloc[0].to_dict() if len(teil) else {}
            if muster:
                from app.services.dateiname import dateiname_bauen
                file_name = dateiname_bauen(muster, {"ziel": target_name, "mapping": mapping_name,
                                                     "gruppe": gruppe}, erste, endung=ext)
            else:
                stamm = target_name if gruppe is None else f"{target_name}_{gruppe}"
                file_name = f"{_slug(stamm)}_{_ts()}.{ext}"
            # Lokal nie überschreiben – gleicher Name im selben Lauf bekommt _2, _3 …
            path = os.path.join(ordner, file_name)
            stamm_, endung_ = os.path.splitext(file_name)
            n = 2
            while os.path.exists(path):
                path = os.path.join(ordner, f"{stamm_}_{n}{endung_}")
                n += 1
            daten = inhalt(teil)
            with open(path, "wb") as f:
                f.write(daten)
            if ablage is not None:
                ablage.schreiben(ablage_verz, file_name, daten)

            record = ExportFile(
                user_id=user_id, project_id=project_id, project_name=project_name,
                job_id=job_id, mapping_id=mapping_id, mapping_name=mapping_name,
                target_name=target_name, file_path=path, file_name=os.path.basename(path),
                file_ext=ext, file_size=os.path.getsize(path), triggered_by=triggered_by,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            ergebnisse.append({"id": record.id, "file_path": path, "file_name": record.file_name,
                               "file_size": record.file_size, "gruppe": gruppe, "zeilen": len(teil)})
    finally:
        if ablage is not None:
            ablage.schliessen()

    erstes = dict(ergebnisse[0]) if ergebnisse else {"id": None, "file_path": None,
                                                     "file_name": None, "file_size": 0}
    erstes["dateien"] = ergebnisse
    return erstes

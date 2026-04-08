"""Patcht main.py: beim Start alle Pipeline-Scheduler registrieren"""
import sys
sys.path.insert(0, '/app')

with open('/app/app/main.py') as f:
    content = f.read()

# Nach dem FTP-Jobs laden Block einfügen
old = '''    # FTP-Jobs laden
    from app.api.ftp_sources import _sync_scheduler
    ftp_db = SessionLocal()
    try:
        for src in ftp_db.query(FtpSource).filter(FtpSource.active == True).all():
            _sync_scheduler(src)
    finally:
        ftp_db.close()
    yield'''

new = '''    # FTP-Jobs laden
    from app.api.ftp_sources import _sync_scheduler
    ftp_db = SessionLocal()
    try:
        for src in ftp_db.query(FtpSource).filter(FtpSource.active == True).all():
            _sync_scheduler(src)
    finally:
        ftp_db.close()

    # Pipeline-Scheduler registrieren (Trigger-Nodes mit Cron)
    from app.models.pipeline import Pipeline
    from app.api.pipelines import _sync_pipeline_scheduler
    pipe_db = SessionLocal()
    try:
        for pipeline in pipe_db.query(Pipeline).filter(Pipeline.active == True).all():
            _sync_pipeline_scheduler(pipeline)
    finally:
        pipe_db.close()

    yield'''

if old in content:
    content = content.replace(old, new)
    import ast
    ast.parse(content)
    with open('/app/app/main.py', 'w') as f:
        f.write(content)
    print("✓ main.py gepatcht")
else:
    print("NICHT GEFUNDEN – manuell suchen")
    # Zeige Kontext
    idx = content.find('FTP-Jobs laden')
    print(repr(content[idx:idx+400]))

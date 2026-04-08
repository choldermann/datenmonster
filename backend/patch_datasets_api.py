"""Patcht datasets.py um /rows Endpoints zu ergänzen"""
import sys
sys.path.insert(0, '/app')

api_file = '/app/app/api/datasets.py'
with open(api_file) as f:
    content = f.read()

# Prüfen ob bereits vorhanden
if '/rows' in content:
    print("Rows-Endpoints bereits vorhanden")
    import re
    routes = re.findall(r'@router\.(get|post|put|patch|delete)\(["\']([^"\']+)', content)
    for m, p in routes:
        print(f"  {m.upper():7} /api/datasets{p}")
else:
    # Imports prüfen
    needs_list = 'from typing import' in content and 'List' not in content
    
    snippet = '''

# ── Editierbare Dataset-Zeilen ────────────────────────────────────────────────

class RowsBody(BaseModel):
    rows: List[Any]


@router.get("/{dataset_id}/rows")
def get_rows(dataset_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """Liest alle Zeilen eines Datasets."""
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    try:
        from app.services.file_service import read_dataset
        result = read_dataset(dataset_id, page=0, page_size=99999)
        return {"rows": result.get("preview", []), "columns": result.get("columns", [])}
    except FileNotFoundError:
        return {"rows": [], "columns": ds.columns or []}
    except Exception as e:
        raise HTTPException(500, str(e)[:200])


@router.put("/{dataset_id}/rows")
def save_rows(dataset_id: int, body: RowsBody, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Ersetzt alle Zeilen eines Datasets."""
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(404, "Dataset nicht gefunden")
    import json, os
    from app.services.file_service import UPLOAD_DIR, infer_column_types
    import pandas as pd
    from datetime import datetime, timezone
    rows = body.rows or []
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        ds.columns = list(df.columns)
        ds.column_types = infer_column_types(df)
    ds.row_count = len(rows)
    ds.updated_at = datetime.now(timezone.utc)
    path = os.path.join(UPLOAD_DIR, f"dataset_{dataset_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
    ds.file_path = path
    db.commit()
    return {"ok": True, "rows": len(rows)}
'''
    content += snippet
    
    import ast
    try:
        ast.parse(content)
        with open(api_file, 'w') as f:
            f.write(content)
        print("✓ Rows-Endpoints hinzugefügt")
    except SyntaxError as e:
        print(f"Syntaxfehler: {e}")


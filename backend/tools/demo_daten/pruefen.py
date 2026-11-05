"""Alle Cockpits gegen die synthetische Demo laufen lassen.

Legt (einmalig) die Verbindung „Demo (synthetisch)“ und das Projekt „Demo
(synthetisch)“ an, installiert alle JTL-Vorlagen dorthin und führt jedes
Formular so aus wie die Oberfläche (nur lesende Aktionen). Meldet je Aktion
Zeilen, Fehler – und leere Ergebnisse, die in einer Vorführung auffallen.

    python -m tools.demo_daten.pruefen
"""
import sys
import time
from types import SimpleNamespace

from app.core.database import SessionLocal
from app.models.dataset import DbConnection, ProjektVerbindung
from app.models.form import Form
from app.models.project import Project
from app.models.template import Template
from tools.demo_daten.verbindung import QUELL_VERBINDUNG, ZIEL

NAME = "Demo (synthetisch)"
ADMIN = SimpleNamespace(id=1, is_admin=True, is_portal_only=False, username="admin")


def verbindung(db) -> DbConnection:
    c = db.query(DbConnection).filter(DbConnection.name == NAME).first()
    if c:
        return c
    q = db.query(DbConnection).get(QUELL_VERBINDUNG)
    c = DbConnection(name=NAME, db_type=q.db_type, host=q.host, port=q.port, database=ZIEL,
                     username=q.username, password=q.password, is_mandant=True, mandant_label=NAME)
    for feld in ("driver", "options", "trust_server_certificate", "encrypt"):
        if hasattr(q, feld):
            setattr(c, feld, getattr(q, feld))
    db.add(c); db.commit(); db.refresh(c)
    return c


def projekt(db, conn) -> Project:
    p = db.query(Project).filter(Project.name == NAME).first()
    if not p:
        p = Project(name=NAME, description="Synthetische Demo-Firma MediVersa (tools/demo_daten)", owner_id=1)
        db.add(p); db.commit(); db.refresh(p)
    if not db.query(ProjektVerbindung).filter_by(project_id=p.id, connection_id=conn.id).first():
        db.add(ProjektVerbindung(project_id=p.id, connection_id=conn.id)); db.commit()
    return p


def installieren(db, p, conn):
    from app.api.templates import install_template, InstallBody
    for t in db.query(Template).filter(Template.template_id.like("jtl_%")).order_by(Template.template_id):
        if t.template_id in ("jtl_wissen_paket", "jtl_eingangsrechnung"):
            continue
        try:
            install_template(InstallBody(template_id=t.template_id, project_id=p.id,
                                         config={"connection_jtl": conn.id}), db=db, user=ADMIN)
        except Exception as e:
            print(f"  ⚠ Installation {t.template_id}: {str(getattr(e, 'detail', e))[:200]}")


def ausfuehren(db, p):
    from app.api.forms import _execute_form, FormRunRequest
    leer, fehler, gesamt = [], [], 0
    for f in db.query(Form).filter(Form.project_id == p.id).order_by(Form.id):
        t0 = time.time()
        try:
            erg = _execute_form(f, FormRunRequest(params={}, preview_rows=50), db, user_id=1, user=ADMIN)
        except Exception as e:
            fehler.append((f.name, "Formular", str(getattr(e, "detail", e))[:200])); continue
        ergebnisse = erg.get("results") or {}
        namen = {a.get("id"): a.get("label") or a.get("name") or a.get("id")
                 for a in ((f.schema or {}).get("actions") or [])}
        n_leer = 0
        for aid, res in ergebnisse.items():
            gesamt += 1
            if not isinstance(res, dict):
                continue
            if res.get("error"):
                fehler.append((f.name, namen.get(aid, aid), str(res["error"])[:200]))
            elif res.get("kind") in (None, "mapping", "table") and not (res.get("rows") or res.get("total")):
                leer.append((f.name, namen.get(aid, aid))); n_leer += 1
        print(f"  {f.name[:45]:45s} {len(ergebnisse):3d} Aktionen, {n_leer:2d} leer  ({time.time() - t0:.0f}s)")
    print(f"\n{gesamt} Aktionen, {len(fehler)} Fehler, {len(leer)} leer")
    for x in fehler:
        print("  FEHLER", " | ".join(x))
    for x in leer:
        print("  leer  ", " | ".join(x))


def main():
    db = SessionLocal()
    conn = verbindung(db)
    p = projekt(db, conn)
    if "--ohne-installation" not in sys.argv:
        installieren(db, p, conn)
    print(f"Verbindung {conn.id}, Projekt {p.id}")
    ausfuehren(db, p)


if __name__ == "__main__":
    main()

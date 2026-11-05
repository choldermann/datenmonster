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
import app.models.user  # noqa: F401 – Fremdschlüssel projects.owner_id → users
from app.models.dataset import DbConnection, ProjektVerbindung
from app.models.form import Form
from app.models.project import Project
from app.models.template import Template
from tools.demo_daten.verbindung import ZIEL

NAME = "Demo (synthetisch)"
ADMIN = SimpleNamespace(id=1, is_admin=True, is_portal_only=False, username="admin")


def verbindung(db) -> DbConnection:
    c = db.query(DbConnection).filter(DbConnection.name == NAME).first()
    if c:
        return c
    raise RuntimeError(f"Verbindung „{NAME}“ fehlt – einmalig von Hand anlegen (Server wie JTLTEST, DB {ZIEL})")
    q = None
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
            # Jede Verbindungs-Angabe der Vorlage auf die Demo zeigen lassen (Intrastat
            # heißt z. B. connection_10)
            cfg = {c["key"]: conn.id for c in ((t.content or {}).get("config_required") or [])
                   if c.get("type") == "connection"}
            install_template(InstallBody(template_id=t.template_id, project_id=p.id,
                                         config=cfg or {"connection_jtl": conn.id}), db=db, user=ADMIN)
        except Exception as e:
            print(f"  ⚠ Installation {t.template_id}: {str(getattr(e, 'detail', e))[:200]}")


def ausfuehren(db, p):
    from app.api.forms import _execute_form, FormRunRequest
    leer, fehler, gesamt = [], [], 0
    for f in db.query(Form).filter(Form.project_id == p.id).order_by(Form.id):
        t0 = time.time()
        try:
            # Wie ein Zeitplan: Vorgaben der Filterfelder, Zeitraum "dieses Jahr"
            from app.services import report_catalog, zeitraum
            params = report_catalog.standardparameter(f.schema or {})
            params.update(zeitraum.berechne("this_year"))
            erg = _execute_form(f, FormRunRequest(params=params, preview_rows=50), db, user_id=1, user=ADMIN)
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


def herkunft_pruefen():
    """Gegenprobe: Daten dürfen nur in Tabellen stehen, die der Generator
    schreibt, oder in der von Hand geprüften Erlaubt-Liste."""
    from tools.demo_daten.erlaubt import ERLAUBT
    from tools.demo_daten.erzeugen import REIHENFOLGE
    from tools.demo_daten.verbindung import verbinden
    erzeugt = {t.lower() for t in REIHENFOLGE} | {t.lower() for t in STAMMDATEN_TABELLEN}
    erlaubt = {t.lower() for t in ERLAUBT}
    cur = verbinden(ZIEL).cursor()
    fremd = [(f"{s}.{t}", n) for s, t, n in cur.execute("""
        SELECT s.name, t.name, SUM(p.rows) FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
        WHERE t.is_ms_shipped = 0 GROUP BY s.name, t.name HAVING SUM(p.rows) > 0""")
             if f"{s}.{t}".lower() not in erzeugt | erlaubt]
    fremdbezug = cur.execute("SELECT COUNT(*) FROM sys.sql_expression_dependencies "
                             "WHERE referenced_database_name = 'eazybusiness'").fetchone()[0]
    print("Herkunft: " + ("nur erzeugte und erlaubte Tabellen haben Daten" if not fremd
                          else f"⚠ Daten in unerwarteten Tabellen: {fremd}"))
    print("Verweise auf andere Datenbank (eazybusiness): " + ("keine" if not fremdbezug else f"⚠ {fremdbezug}"))


STAMMDATEN_TABELLEN = [
    "dbo.tfirma", "dbo.tFirmaHistory", "dbo.tBenutzer", "dbo.tShop", "dbo.tKundenGruppe", "dbo.tZahlungsart",
    "dbo.tVersandArt", "dbo.tEinheit", "dbo.tEinheitSprache", "dbo.tWarenLager", "dbo.tWarenLagerPlatz",
    "dbo.tHersteller", "dbo.tWarengruppe", "dbo.tlieferant", "dbo.tArtikel", "dbo.tArtikelBeschreibung",
    "dbo.tLiefArtikel", "dbo.tPreis", "dbo.tPreisDetail", "dbo.tStueckliste", "dbo.tArtikelSonderpreis",
    "dbo.tSonderpreise", "dbo.tkunde", "dbo.tAdresse",
    # von JTL-Prozeduren aus den erzeugten Daten berechnet
    "dbo.tlagerbestand", "dbo.tArtikelHistory", "Verkauf.tAuftragEckdaten", "Verkauf.tAuftragPositionEckdaten",
    "Rechnung.tRechnungEckdaten", "Rechnung.tRechnungPositionEckdaten",
]


def main():
    herkunft_pruefen()
    db = SessionLocal()
    conn = verbindung(db)
    p = projekt(db, conn)
    if "--ohne-installation" not in sys.argv:
        installieren(db, p, conn)
    print(f"Verbindung {conn.id}, Projekt {p.id}")
    ausfuehren(db, p)


if __name__ == "__main__":
    main()

"""Einrichtungsassistent für JTL-Kunden (Büro, Phase 2).

Drei Schritte statt Templates → Verbindung → Install-Parameter:
  1. Mit der JTL-Wawi verbinden (Port der Instanz wird ermittelt, Fehler werden
     eingeordnet statt als ODBC-Text gezeigt)
  2. Cockpits wählen (Prüfung gegen die JTL-Version macht die Oberfläche über
     das vorhandene POST /api/templates/pruefe)
  3. Angaben zum Betrieb – dann installiert `abschliessen` alles in einem Rutsch.

Nur Administratoren: Verbindungen anlegen dürfen ohnehin nur sie.
Plan: ~/.claude/plans/haendler-ansicht.md, Phase 2.
"""
import logging
import re
import socket
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db, safe_commit
from app.core.zugriff import nur_admin
from app.models.dataset import DbConnection, ProjektVerbindung
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/einrichtung", tags=["einrichtung"])

PROJEKTNAME = "JTL-Auswertungen"
JTL_KATEGORIEN = {"jtl", "jtl-reporting"}


# ── Schritt 1: Verbindung ─────────────────────────────────────────────────────

def sql_browser(host: str, instanz: str, timeout: float = 2.0) -> Optional[dict]:
    """Fragt den SQL-Server-Browser (UDP 1434) nach einer benannten Instanz.

    Antwort z. B. {"tcp": "50000"} – fehlt "tcp", ist TCP/IP für die Instanz aus.
    None heißt: keine Antwort (Browser-Dienst aus oder UDP gesperrt).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\x04" + instanz.encode("latin-1") + b"\x00", (host, 1434))
            daten, _ = s.recvfrom(4096)
    except Exception:
        return None
    if not daten or daten[0] != 0x05:
        return None
    teile = daten[3:].decode("latin-1", errors="replace").split(";")
    return {teile[i].lower(): teile[i + 1] for i in range(0, len(teile) - 1, 2) if teile[i]}


def _server_zerlegen(server: str):
    """„SRV\\INSTANZ“, „SRV,1433“ oder „SRV“ → (host, instanz, port)."""
    server = (server or "").strip()
    port = None
    if "," in server:
        server, p = server.rsplit(",", 1)
        port = int(p) if p.strip().isdigit() else None
    host, _, instanz = server.partition("\\")
    return host.strip(), instanz.strip() or None, port


# Wie ODBC-Meldungen dem Händler erklärt werden. Reihenfolge = Vorrang.
FEHLERBILDER = [
    ("anmeldung", ("18456", "login failed"),
     "Benutzer oder Passwort stimmen nicht",
     "Der SQL Server hat die Anmeldung abgelehnt.",
     ["Benutzer und Passwort so eintragen, wie sie in JTL unter „Datenbank verbinden“ stehen.",
      "Bei Windows-Anmeldung in JTL: einen SQL-Benutzer anlegen und „Gemischter Modus“ "
      "in den Server-Eigenschaften (Sicherheit) einschalten, danach den Dienst neu starten."]),
    ("datenbank", ("4060", "cannot open database"),
     "Die Datenbank gibt es auf diesem Server nicht",
     "Der Server antwortet, kennt aber den Datenbanknamen nicht oder der Benutzer darf ihn nicht öffnen.",
     ["Den Namen prüfen – meist „eazybusiness“, weitere Mandanten heißen z. B. „eazybusiness_tm2“."]),
    ("erreichbar", ("08001", "hyt00", "login timeout", "tcp provider", "server was not found",
                    "network-related", "timeout expired", "no route", "connection refused"),
     "Der Server antwortet nicht",
     "Meistens ist beim SQL Server der Netzwerkzugang (TCP/IP) ausgeschaltet. JTL selbst "
     "braucht ihn nicht, Datenmonster schon.",
     ["Auf dem Wawi-Server den „SQL Server-Konfigurations-Manager“ öffnen.",
      "Unter „Netzwerkkonfiguration“ bei der Instanz „TCP/IP“ aktivieren.",
      "In den TCP/IP-Eigenschaften unter „IPAll“ das Feld „Dynamische Ports“ leeren und "
      "bei „TCP-Port“ einen festen Port eintragen (z. B. 50000).",
      "Den Dienst „SQL Server (Instanz)“ neu starten und hier erneut testen. "
      "Läuft eine Firewall, den Port dort freigeben."]),
]


def _fehler_einordnen(meldung: str, browser: Optional[dict], instanz: Optional[str]) -> dict:
    text = (meldung or "").lower()
    for art, muster, titel, erklaerung, schritte in FEHLERBILDER:
        if any(m in text for m in muster):
            aus = {"art": art, "titel": titel, "text": erklaerung, "schritte": list(schritte)}
            if art == "erreichbar" and instanz and browser is not None and "tcp" not in browser:
                aus["text"] = (f"Die Instanz „{instanz}“ meldet sich, hat aber keinen TCP-Port: "
                               "TCP/IP ist dort ausgeschaltet.")
            return aus
    return {"art": "unbekannt", "titel": "Die Verbindung hat nicht geklappt",
            "text": "Der Server hat eine Meldung zurückgegeben, die wir nicht zuordnen können.",
            "schritte": []}


def _jtl_kennzahlen(conn: DbConnection) -> dict:
    """Version, weitere Mandanten-Datenbanken und ein paar Größen zur Bestätigung."""
    from sqlalchemy import create_engine, text
    from app.services.db_service import get_engine_str
    aus = {"jtl_version": None, "mandanten": [], "artikel": None, "auftraege": None}
    engine = create_engine(get_engine_str(conn), connect_args={"timeout": 10, "login_timeout": 5})
    try:
        with engine.connect() as c:
            def eins(sql):
                try:
                    return c.execute(text(sql)).scalar()
                except Exception:
                    return None
            aus["jtl_version"] = eins("SELECT TOP 1 cVersion FROM dbo.tVersion ORDER BY cVersion DESC")
            aus["artikel"] = eins("SELECT COUNT(*) FROM dbo.tArtikel")
            aus["auftraege"] = eins("SELECT COUNT(*) FROM Verkauf.tAuftrag")
            try:
                aus["mandanten"] = [r[0] for r in c.execute(text(
                    "SELECT name FROM sys.databases WHERE name LIKE 'eazybusiness%' ORDER BY name"))]
            except Exception:
                pass
    finally:
        engine.dispose()
    return aus


class VerbindungIn(BaseModel):
    connection_id: Optional[int] = None    # bestehende Verbindung aktualisieren
    server: str                             # wie in JTL: „SRV\\JTLWAWI“, „SRV,50000“ oder „SRV“
    port: Optional[int] = None              # leer = über den SQL-Browser ermitteln
    datenbank: str = "eazybusiness"
    benutzer: str
    passwort: str = ""


@router.post("/verbindung")
def verbindung(data: VerbindungIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Testet die Zugangsdaten und speichert die Verbindung, wenn sie trägt."""
    nur_admin(user, "Die Einrichtung darf nur ein Administrator vornehmen")
    from app.core.security import encrypt_credential, decrypt_credential
    from app.services.db_service import test_connection

    host, instanz, port = _server_zerlegen(data.server)
    port_angegeben = port is not None
    if not host:
        raise HTTPException(400, "Bitte den Server angeben")
    port = data.port or port
    browser = sql_browser(host, instanz) if instanz else None
    if not port and browser and browser.get("tcp", "").isdigit():
        port = int(browser["tcp"])
    port = port or 1433

    vorhanden = None
    if data.connection_id:
        vorhanden = db.query(DbConnection).filter(DbConnection.id == data.connection_id).first()
        if not vorhanden:
            raise HTTPException(404, "Verbindung nicht gefunden")
    passwort = data.passwort
    if not passwort and vorhanden is not None:
        passwort = decrypt_credential(vorhanden.password) if vorhanden.password else ""

    hostfeld = f"{host}\\{instanz}" if instanz else host
    probe = DbConnection(name="Einrichtung", db_type="mssql", host=hostfeld, port=port,
                         database=data.datenbank.strip(), username=data.benutzer.strip(),
                         password=encrypt_credential(passwort))
    ergebnis = test_connection(probe)
    if not ergebnis.get("success"):
        fehler = _fehler_einordnen(ergebnis.get("message", ""), browser, instanz)
        if fehler["art"] == "erreichbar" and not (data.port or port_angegeben) and browser is None:
            # Ohne Antwort des SQL-Browsers haben wir 1433 nur geraten.
            fehler["schritte"].insert(0, "Ist für die Instanz ein fester Port eingerichtet (bei "
                                         "gehosteten Servern oft 50000), diesen unter „Port“ eintragen.")
        return {"ok": False, "port": port, "browser": browser is not None, **fehler,
                "technisch": ergebnis.get("message", "")}

    info = _jtl_kennzahlen(probe)
    if not info["jtl_version"]:
        return {"ok": False, "port": port, "art": "keine_jtl",
                "titel": "Das ist keine JTL-Wawi-Datenbank",
                "text": "Die Verbindung klappt, aber in dieser Datenbank fehlt die JTL-Versionstabelle.",
                "schritte": ["Den Datenbanknamen prüfen – meist „eazybusiness“."]
                + ([f"Auf diesem Server gibt es: {', '.join(info['mandanten'])}."] if info["mandanten"] else [])}

    # Speichern: eine bestehende Verbindung zu derselben Datenbank wiederverwenden,
    # statt bei jedem Durchlauf eine weitere anzulegen.
    conn = vorhanden or db.query(DbConnection).filter(
        DbConnection.db_type == "mssql", DbConnection.host == hostfeld,
        DbConnection.database == probe.database).first()
    if conn is None:
        from app.core import kontingent
        kontingent.pruefe(db, "verbindungen")
        conn = DbConnection(name=f"JTL-Wawi ({probe.database})", db_type="mssql")
        db.add(conn)
    conn.host, conn.port, conn.database = hostfeld, port, probe.database
    conn.username, conn.password = probe.username, probe.password
    safe_commit(db)
    db.refresh(conn)
    from app.services.sql_helpers import invalidate_sql_engine
    invalidate_sql_engine(conn.id)

    return {"ok": True, "connection_id": conn.id, "port": port, **info}


# ── Schritt 2: Cockpits ───────────────────────────────────────────────────────

def _anzeigename(name: str) -> str:
    return re.sub(r"^JTL\s*[–-]\s*", "", name or "").strip()


@router.get("/cockpits")
def cockpits(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """JTL-Vorlagen aus dem lokalen Katalog und dem Store (nur berechtigte zum Anhaken)."""
    nur_admin(user, "Die Einrichtung darf nur ein Administrator vornehmen")
    from app.models.template import Template
    from app.api.templates import _store_catalog

    eintraege = {}
    for t in db.query(Template).all():
        if (t.category or "").lower() not in JTL_KATEGORIEN:
            continue
        eintraege[t.template_id] = {
            "template_id": t.template_id, "name": _anzeigename(t.name),
            "beschreibung": t.description or "", "version": t.version,
            "im_katalog": True, "berechtigt": True,
            "installiert": bool(t.installations),
        }
    store = _store_catalog(db)
    for s in store.get("templates") or []:
        tid = s.get("template_id")
        if not tid or not tid.startswith("jtl_"):
            continue
        e = eintraege.setdefault(tid, {
            "template_id": tid, "name": _anzeigename(s.get("name")),
            "beschreibung": s.get("description") or "", "version": s.get("version"),
            "im_katalog": False, "installiert": False,
        })
        # Lokal vorhanden heißt nicht gekauft: gesperrte Vorlagen markiert das Laufzeit-Tor,
        # hier zählt die Store-Berechtigung, sobald es sie gibt.
        e["berechtigt"] = bool(s.get("entitled", e.get("berechtigt")))
        e["shop_url"] = s.get("url") or store.get("shop_url")
    liste = sorted(eintraege.values(), key=lambda e: (not e["berechtigt"], e["name"].lower()))
    return {"cockpits": liste, "store_fehler": store.get("error")}


# ── Schritt 3: Abschließen ────────────────────────────────────────────────────

class AbschlussIn(BaseModel):
    connection_id: int
    vorlagen: List[str]
    ladenhueter_tage: Optional[int] = None
    fixkosten_monat: Optional[float] = None
    warn_email: Optional[str] = None
    datev_berater: Optional[str] = None
    datev_mandant: Optional[str] = None


def _projekt_fuer(conn_id: int, user, db) -> int:
    """Das Projekt, in dem diese Verbindung schon hängt – sonst ein neues."""
    from app.models.project import Project
    zugeordnet = db.query(ProjektVerbindung).filter(
        ProjektVerbindung.connection_id == conn_id).order_by(ProjektVerbindung.project_id).first()
    if zugeordnet:
        return zugeordnet.project_id
    p = db.query(Project).filter(Project.name == PROJEKTNAME).first()
    if p is None:
        from app.core import kontingent
        kontingent.pruefe(db, "projekte")
        p = Project(name=PROJEKTNAME, description="Angelegt vom Einrichtungsassistenten",
                    owner_id=user.id)
        db.add(p)
        safe_commit(db)
        db.refresh(p)
    if not db.query(ProjektVerbindung).filter(ProjektVerbindung.project_id == p.id,
                                              ProjektVerbindung.connection_id == conn_id).first():
        db.add(ProjektVerbindung(project_id=p.id, connection_id=conn_id))
        safe_commit(db)
    return p.id


@router.post("/abschliessen")
def abschliessen(data: AbschlussIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Installiert die gewählten Vorlagen und trägt die Angaben zum Betrieb ein.

    Bricht nicht beim ersten Fehler ab: jede Vorlage meldet für sich, damit eine
    gesperrte oder fehlerhafte Vorlage nicht die übrigen verhindert.
    """
    nur_admin(user, "Die Einrichtung darf nur ein Administrator vornehmen")
    from app.models.template import Template
    from app.api import templates as tpl_api
    from app.services import business_config_service as cfg_service, mandant_service

    conn = db.query(DbConnection).filter(DbConnection.id == data.connection_id).first()
    if not conn:
        raise HTTPException(404, "Verbindung nicht gefunden")
    if not data.vorlagen:
        raise HTTPException(400, "Bitte mindestens ein Cockpit wählen")
    projekt = _projekt_fuer(conn.id, user, db)
    mandant_id = mandant_service.aktiver(projekt, user, db)

    ergebnisse = []
    for tid in dict.fromkeys(data.vorlagen):
        eintrag = {"template_id": tid, "ok": False}
        try:
            t = db.query(Template).filter(Template.template_id == tid).first()
            if t is None:                       # gekauft, aber noch nicht geholt
                tpl_api.install_from_store(tid, db, user)
                t = db.query(Template).filter(Template.template_id == tid).first()
            eintrag["name"] = _anzeigename(t.name)
            content = t.content if isinstance(t.content, dict) else {}
            config = {}
            for req in content.get("config_required", []) or []:
                key = req.get("key")
                if req.get("type") == "connection":
                    # Jede Verbindungs-Angabe der Vorlage zeigt auf die Wawi – auch
                    # ältere Schlüssel wie „connection_10“ (Intrastat).
                    config[key] = conn.id
                elif key == "ladenhueter_tage" and data.ladenhueter_tage:
                    config[key] = str(int(data.ladenhueter_tage))
            tpl_api.install_template(tpl_api.InstallBody(template_id=tid, project_id=projekt,
                                                         config=config), db, user)
            eintrag["ok"] = True
        except HTTPException as e:
            db.rollback()
            eintrag["fehler"] = str(e.detail)
        except Exception as e:
            db.rollback()
            logger.exception("Einrichtung: Vorlage %s", tid)
            eintrag["fehler"] = str(e)[:300]
        ergebnisse.append(eintrag)

    hinweise = []
    # Fixkosten als eine Sammel-Kostenart ab Jahresbeginn – im Kostenstruktur-
    # Cockpit lässt sie sich später aufteilen.
    if data.fixkosten_monat and data.fixkosten_monat > 0:
        key = "x_fixkosten_einrichtung"
        cfg_service.set_value(projekt, db, "cost", key, {
            "label": "Fixkosten gesamt (aus der Einrichtung)", "custom": True,
            "gruppe_key": "sonstiges", "gruppe": "Sonstiges",
            "eintraege": [{"gueltig_ab": date(date.today().year, 1, 1).isoformat(),
                           "betrag": round(float(data.fixkosten_monat), 2)}],
        }, mandant_id)
    for key, wert in (("datev_berater", data.datev_berater), ("datev_mandant", data.datev_mandant)):
        wert = (wert or "").strip()
        if not wert:
            continue
        if not wert.isdigit():
            hinweise.append(f"{'Beraternummer' if key == 'datev_berater' else 'Mandantennummer'} "
                            "nicht gespeichert: nur Ziffern erlaubt.")
            continue
        cfg_service.set_value(projekt, db, "datev", key, wert, mandant_id)

    if (data.warn_email or "").strip():
        from app.api.alerts import put_schedule, ScheduleIn
        try:
            put_schedule(ScheduleIn(project_id=projekt, mandant_id=mandant_id,
                                    cron_expr="30 5 * * *", active=True,
                                    email_to=data.warn_email.strip()), db, user)
        except HTTPException as e:
            hinweise.append(f"Warnungen per Mail nicht eingerichtet: {e.detail}")

    # Mit dem GF-Cockpit gleich die Kennzahl-Kacheln der Übersicht anlegen.
    if any(e["ok"] and e["template_id"] == "jtl_gf_cockpit" for e in ergebnisse):
        try:
            from app.api.start import kennzahlen_anlegen
            kennzahlen_anlegen(db, user, projekt)
        except Exception as e:
            hinweise.append(f"Kennzahlen der Übersicht nicht angelegt: {getattr(e, 'detail', e)}")

    return {"project_id": projekt, "ergebnisse": ergebnisse, "hinweise": hinweise}

"""ZUGFeRD-Ausgang: neue Rechnungen aus tInvoice abholen, erzeugen, ablegen.

Ablauf je Rechnung:
  1. Access legt Kopf + Positionen + PDF an (Status ENTWURF) und setzt zum
     Schluss Status = NEU. Erst dann fassen wir sie an - sonst läsen wir eine
     Rechnung, deren Positionen noch gar nicht geschrieben sind.
  2. Wir beanspruchen sie (NEU → IN_ARBEIT, nur wenn sie noch NEU ist). Laufen
     Zeitplan und Knopf gleichzeitig, bekommt so nur einer die Rechnung.
  3. Prüfen, XML bauen, in die PDF einbetten, auf den FTP legen.
  4. Status OK (mit Dateiname) bzw. FEHLER (mit Grund) zurückschreiben.

⭐ Ein Datenfehler (Summe passt nicht, USt-IdNr. fehlt) macht die Rechnung zu
FEHLER - daran muss jemand in Access ran. Ist dagegen der FTP nicht erreichbar,
geht sie zurück auf NEU und der Lauf bricht ab: das ist kein Fehler der
Rechnung, und beim nächsten Lauf geht sie von selbst durch.
"""
from __future__ import annotations

import datetime as _dt
import io
import logging
import re
import threading
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import decrypt_credential
from app.models.zugferd import ZugferdAusgang, ZugferdBeleg
from app.services import zugferd_pdf, zugferd_xml

logger = logging.getLogger(__name__)

ABLAGE = Path("/app/uploads/zugferd")
# Nach so langer Zeit gilt IN_ARBEIT als liegengeblieben (Absturz mitten im Lauf).
HAENGT_NACH = _dt.timedelta(minutes=30)
MAX_JE_LAUF = 200

KOPF_SPALTEN = [
    "InvoiceId", "InvoiceNumber", "InvoiceType", "InvoiceDate", "DeliveryDate",
    "PeriodStart", "PeriodEnd", "DueDate", "Currency", "PrecedingInvoiceNumber",
    "PrecedingInvoiceDate", "BuyerReference", "OrderReference", "CustomerNumber",
    "BuyerName", "BuyerContact", "BuyerStreet", "BuyerAddress2", "BuyerZip", "BuyerCity",
    "BuyerCountry", "BuyerVatId", "BuyerEmail", "BuyerIban", "DirectDebitMandate",
    "ShipToName", "ShipToStreet", "ShipToZip", "ShipToCity", "ShipToCountry",
    "PaymentMeans", "PaymentTerms", "SkontoDays", "SkontoPercent", "Note",
    "TotalNet", "TotalTax", "TotalGross", "Prepaid", "PdfFile", "Status",
    "StatusMessage", "OutputFileName", "ProcessedAt", "ZugferdFile", "SellerVatId",
]
POS_SPALTEN = [
    "PositionId", "InvoiceId", "LineNumber", "ArticleNumber", "BuyerArticleNumber", "Name",
    "Description", "Quantity", "Unit", "UnitPrice", "PriceBaseQuantity", "LineNet",
    "VatCategory", "VatRate", "ExemptionReason",
]

OPTIONAL = {"ZugferdFile", "SellerVatId"}

_TABELLE = re.compile(r"^(\[?[A-Za-z_][A-Za-z0-9_]*\]?\.)?\[?[A-Za-z_][A-Za-z0-9_]*\]?$")
_sperren: dict[int, threading.Lock] = {}


class LaufFehler(Exception):
    """Der Lauf als Ganzes kann nicht starten (Einstellungen, Ziel nicht erreichbar)."""


class _ZielFehler(Exception):
    """Ablegen auf dem FTP ging schief - die Rechnung kann nichts dafür."""


def tabelle_pruefen(name: str) -> str:
    n = (name or "").strip()
    # Der Name landet im SQL-Text (Tabellen lassen sich nicht binden) - deshalb
    # nur Bezeichner, Punkt und eckige Klammern.
    if not _TABELLE.match(n):
        raise LaufFehler(f"Tabellenname '{name}' ist ungültig (erlaubt: schema.Tabelle)")
    return n


def _kanonisch(zeile: dict, spalten: list[str]) -> dict:
    """Spaltennamen unabhängig von Groß-/Kleinschreibung auf unsere Schreibweise bringen."""
    karte = {s.lower(): s for s in spalten}
    return {karte.get(k.lower(), k): v for k, v in zeile.items()}


def _engine(connection_id: int, db: Session):
    from app.models.dataset import DbConnection
    from app.services.db_service import get_engine_str
    conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
    if not conn:
        raise LaufFehler(f"Verbindung {connection_id} gibt es nicht")
    return create_engine(get_engine_str(conn), pool_pre_ping=True)


def dateiname(muster: str, beleg: zugferd_xml.Beleg) -> str:
    werte = {
        "nummer": beleg.nummer, "typ": beleg.art.lower(),
        "datum": beleg.datum.strftime("%Y-%m-%d"),
        "kunde": str(beleg.kopf.get("CustomerNumber") or ""),
    }
    try:
        roh = (muster or "{nummer}.pdf").format(**werte)
    except (KeyError, IndexError, ValueError):
        roh = f"{beleg.nummer}.pdf"
    sicher = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in roh).strip(" .")
    if not sicher.lower().endswith(".pdf"):
        sicher += ".pdf"
    return sicher[:180]


# ── Ziel ──────────────────────────────────────────────────────────────────────

class _Ziel:
    """FTP/SFTP-Verbindung für einen Lauf - einmal öffnen, viele Dateien ablegen."""

    def __init__(self, ausgang: ZugferdAusgang):
        from app.services import ftp_service as ftp
        self.ausgang = ausgang
        self.sftp = (ausgang.protokoll or "ftp").lower() == "sftp"
        self.verz = (ausgang.verzeichnis or "/").rstrip("/") or ""
        pw = decrypt_credential(ausgang.password) if ausgang.password else ""
        if not ausgang.host:
            raise LaufFehler("Kein FTP-Server eingetragen")
        try:
            self.c = (ftp._connect_sftp if self.sftp else ftp._connect_ftp)(
                ausgang.host, ausgang.port, ausgang.username or "", pw)
        except Exception as e:                                # noqa: BLE001
            raise LaufFehler(f"Verbindung zum FTP-Server {ausgang.host} fehlgeschlagen: {e}")

    def ablegen(self, name: str, daten: bytes):
        # Erst unter einem Hilfsnamen hochladen, dann umbenennen: wer den Ordner
        # beobachtet (Access, ein Mailprogramm), sieht nie eine halbe Datei.
        ziel, temp = f"{self.verz}/{name}", f"{self.verz}/{name}.part"
        try:
            if self.sftp:
                self.c.putfo(io.BytesIO(daten), temp)
                try:
                    self.c.remove(ziel)
                except IOError:
                    pass
                self.c.rename(temp, ziel)
            else:
                self.c.storbinary(f"STOR {temp}", io.BytesIO(daten))
                try:
                    self.c.delete(ziel)
                except Exception:                             # noqa: BLE001
                    pass
                self.c.rename(temp, ziel)
        except Exception as e:                                # noqa: BLE001
            raise _ZielFehler(f"Ablegen von {name} auf dem FTP fehlgeschlagen: {e}")

    def schliessen(self):
        try:
            if self.sftp:
                self.c._ssh.close()
            else:
                self.c.quit()
        except Exception:                                     # noqa: BLE001
            pass


def ziel_testen(ausgang: ZugferdAusgang) -> dict:
    """Verbinden, Probedatei schreiben, wieder löschen."""
    z = _Ziel(ausgang)
    try:
        name = ".datenmonster_test.txt"
        try:
            z.ablegen(name, b"Datenmonster ZUGFeRD - Schreibtest\n")
        except _ZielFehler as e:
            raise LaufFehler(str(e))
        try:
            (z.c.remove if z.sftp else z.c.delete)(f"{z.verz}/{name}")
        except Exception:                                     # noqa: BLE001
            pass
        return {"ok": True, "meldung": f"Verbunden mit {ausgang.host}, Schreiben in "
                                       f"„{ausgang.verzeichnis or '/'}“ klappt"}
    finally:
        z.schliessen()


# ── Quelltabellen ─────────────────────────────────────────────────────────────

def tabellen_pruefen(engine, kopf: str, pos: str) -> list[str]:
    """Welche Pflichtspalten fehlen? Leere Liste = alles da."""
    fehlend = []
    with engine.connect() as c:
        for tab, spalten in ((kopf, KOPF_SPALTEN), (pos, POS_SPALTEN)):
            try:
                r = c.execute(text(f"SELECT * FROM {tab} WHERE 1=0"))
                da = {k.lower() for k in r.keys()}
            except Exception as e:                            # noqa: BLE001
                return [f"Tabelle {tab} nicht lesbar: {str(e).splitlines()[0][:200]}"]
            # Freiwillig: ZugferdFile (fertige PDF zurück) und SellerVatId (nur bei
            # mehreren eigenen USt-IdNrn.) - ältere Tabellen ohne sie laufen weiter.
            fehlend += [f"{tab}.{s}" for s in spalten
                        if s.lower() not in da and s not in OPTIONAL]
    return fehlend


def statistik(engine, kopf: str) -> dict:
    with engine.connect() as c:
        rows = c.execute(text(f"SELECT Status, COUNT(*) AS n FROM {kopf} GROUP BY Status")).all()
    return {str(r[0]): int(r[1]) for r in rows}


def erneut_einreihen(engine, kopf: str, invoice_id: int) -> bool:
    with engine.begin() as c:
        r = c.execute(text(f"UPDATE {kopf} SET Status = 'NEU', StatusMessage = NULL "
                           f"WHERE InvoiceId = :id AND Status IN ('FEHLER', 'OK')"),
                      {"id": invoice_id})
    return r.rowcount == 1


def _status(engine, kopf: str, invoice_id: int, status: str, meldung: Optional[str],
            datei: Optional[str] = None, zugferd: Optional[bytes] = None):
    setzen = "Status = :s, StatusMessage = :m, ProcessedAt = :t"
    werte = {"s": status, "m": (meldung or None), "t": _dt.datetime.now().replace(microsecond=0),
             "id": invoice_id}
    if datei is not None:
        setzen += ", OutputFileName = :f"
        werte["f"] = datei
    if zugferd is not None:
        setzen += ", ZugferdFile = :z"
        werte["z"] = zugferd
    with engine.begin() as c:
        c.execute(text(f"UPDATE {kopf} SET {setzen} WHERE InvoiceId = :id"), werte)


# ── der Lauf ──────────────────────────────────────────────────────────────────

def _protokoll(db: Session, ausgang: ZugferdAusgang, kopf: dict, status: str,
               meldung: str, ausloeser: str, beleg: Optional[zugferd_xml.Beleg] = None,
               datei: Optional[str] = None, pdf: Optional[bytes] = None) -> ZugferdBeleg:
    datum = kopf.get("InvoiceDate")
    e = ZugferdBeleg(
        ausgang_id=ausgang.id, connection_id=ausgang.connection_id,
        invoice_id=kopf.get("InvoiceId"), nummer=str(kopf.get("InvoiceNumber") or "")[:100],
        art=(str(kopf.get("InvoiceType") or "RECHNUNG")).upper()[:20],
        kunde=str(kopf.get("BuyerName") or "")[:200],
        datum=str(datum)[:10] if datum else None,
        brutto=beleg.brutto if beleg else kopf.get("TotalGross"),
        status=status, meldung=meldung or None, dateiname=datei,
        ausgeloest_von=ausloeser[:100])
    db.add(e)
    db.flush()
    if pdf is not None:
        ordner = ABLAGE / str(ausgang.id)
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = ordner / f"{e.id}_{datei}"
        pfad.write_bytes(pdf)
        e.pfad = str(pfad)
    db.commit()
    return e


def eine_rechnung(engine, ausgang: ZugferdAusgang, kopf: dict, positionen: list[dict],
                  verkaeufer: dict) -> tuple[bytes, str, zugferd_xml.Beleg, list[str]]:
    """Prüfen, XML bauen, einbetten. Wirft ZugferdFehler/PdfFehler bei Datenfehlern."""
    beleg = zugferd_xml.pruefen(kopf, positionen, verkaeufer)
    xml = zugferd_xml.baue_xml(beleg)
    pdf = kopf.get("PdfFile")
    if not pdf:
        raise zugferd_xml.ZugferdFehler(["PdfFile ist leer – Access hat keine PDF mitgeliefert"])
    titel = {"STORNO": "Stornorechnung", "KORREKTUR": "Rechnungskorrektur"}.get(
        beleg.art, "Rechnung") + f" {beleg.nummer}"
    fertig, warn = zugferd_pdf.einbetten(bytes(pdf), xml, titel=titel,
                                         autor=verkaeufer.get("name") or "")
    return fertig, dateiname(ausgang.dateiname_muster, beleg), beleg, beleg.warnungen + warn


def verarbeiten(db: Session, ausgang: ZugferdAusgang, ausloeser: str = "Zeitplan",
                engine=None, ziel=None) -> dict:
    """Ein Lauf über alle Rechnungen mit Status NEU. engine/ziel nur für Tests."""
    sperre = _sperren.setdefault(ausgang.id, threading.Lock())
    if not sperre.acquire(blocking=False):
        return {"ok": False, "meldung": "Es läuft bereits ein Durchgang", "erzeugt": 0,
                "fehler": 0}
    eigene_engine = engine is None
    ergebnis = {"ok": True, "erzeugt": 0, "fehler": 0, "meldung": ""}
    try:
        from app.services import business_config_service as cfg
        verkaeufer = cfg.get_zugferd(ausgang.project_id, db, ausgang.connection_id)
        fehlt = cfg.zugferd_unvollstaendig(verkaeufer)
        if fehlt:
            raise LaufFehler("Firmendaten unvollständig: " + ", ".join(fehlt))
        kopf_t = tabelle_pruefen(ausgang.tabelle_kopf or "dbo.tInvoice")
        pos_t = tabelle_pruefen(ausgang.tabelle_positionen or "dbo.tInvoicePositions")
        engine = engine or _engine(ausgang.connection_id, db)

        jetzt = _dt.datetime.now().replace(microsecond=0)
        with engine.begin() as c:
            # Liegengebliebenes wieder freigeben (Absturz, Neustart mitten im Lauf).
            c.execute(text(f"UPDATE {kopf_t} SET Status = 'NEU' WHERE Status = 'IN_ARBEIT' "
                           f"AND (ProcessedAt IS NULL OR ProcessedAt < :grenze)"),
                      {"grenze": jetzt - HAENGT_NACH})
            ids = [r[0] for r in c.execute(text(
                f"SELECT InvoiceId FROM {kopf_t} WHERE Status = 'NEU' ORDER BY InvoiceId")).all()]
        ids = ids[:MAX_JE_LAUF]
        if not ids:
            ergebnis["meldung"] = "Keine neuen Rechnungen"
            return ergebnis

        z = ziel or _Ziel(ausgang)
        try:
            for inv_id in ids:
                with engine.begin() as c:
                    r = c.execute(text(f"UPDATE {kopf_t} SET Status = 'IN_ARBEIT', "
                                       f"ProcessedAt = :t WHERE InvoiceId = :id "
                                       f"AND Status = 'NEU'"), {"id": inv_id, "t": jetzt})
                if r.rowcount != 1:
                    continue                                  # hat ein anderer Lauf
                with engine.connect() as c:
                    kopf = _kanonisch(dict(c.execute(text(
                        f"SELECT * FROM {kopf_t} WHERE InvoiceId = :id"),
                        {"id": inv_id}).mappings().first() or {}), KOPF_SPALTEN)
                    pos = [_kanonisch(dict(p), POS_SPALTEN) for p in c.execute(text(
                        f"SELECT * FROM {pos_t} WHERE InvoiceId = :id ORDER BY LineNumber"),
                        {"id": inv_id}).mappings().all()]
                try:
                    fertig, name, beleg, warn = eine_rechnung(engine, ausgang, kopf, pos,
                                                              verkaeufer)
                except (zugferd_xml.ZugferdFehler, zugferd_pdf.PdfFehler) as e:
                    gruende = e.fehler if isinstance(e, zugferd_xml.ZugferdFehler) else [str(e)]
                    _status(engine, kopf_t, inv_id, "FEHLER", "\n".join(gruende)[:4000])
                    _protokoll(db, ausgang, kopf, "fehler", "\n".join(gruende), ausloeser)
                    ergebnis["fehler"] += 1
                    continue
                except Exception as e:                        # noqa: BLE001
                    # Unerwartet - trotzdem FEHLER statt NEU, sonst kreist die
                    # Rechnung bei jedem Lauf und erzeugt jedes Mal denselben Fehler.
                    logger.exception("ZUGFeRD: Rechnung %s", inv_id)
                    _status(engine, kopf_t, inv_id, "FEHLER", f"Interner Fehler: {e}"[:4000])
                    _protokoll(db, ausgang, kopf, "fehler", f"Interner Fehler: {e}", ausloeser)
                    ergebnis["fehler"] += 1
                    continue

                try:
                    z.ablegen(name, fertig)
                except _ZielFehler as e:
                    _status(engine, kopf_t, inv_id, "NEU", None)
                    raise LaufFehler(str(e))

                _status(engine, kopf_t, inv_id, "OK", "\n".join(warn)[:4000] or None, name,
                        fertig if "ZugferdFile" in kopf else None)
                _protokoll(db, ausgang, kopf, "ok", "\n".join(warn), ausloeser, beleg,
                           name, fertig)
                ergebnis["erzeugt"] += 1
        finally:
            if ziel is None:
                z.schliessen()
        ergebnis["meldung"] = f"{ergebnis['erzeugt']} erzeugt, {ergebnis['fehler']} abgewiesen"
        return ergebnis
    except LaufFehler as e:
        ergebnis.update(ok=False, meldung=str(e))
        return ergebnis
    except Exception as e:                                    # noqa: BLE001
        logger.exception("ZUGFeRD-Lauf %s", ausgang.id)
        ergebnis.update(ok=False, meldung=f"Lauf abgebrochen: {str(e).splitlines()[0][:300]}")
        return ergebnis
    finally:
        ausgang.letzter_lauf = _dt.datetime.now(_dt.timezone.utc)
        ausgang.letzter_status = "ok" if ergebnis["ok"] else "fehler"
        ausgang.letzter_fehler = None if ergebnis["ok"] else ergebnis["meldung"][:1000]
        try:
            db.commit()
        except Exception:                                     # noqa: BLE001
            db.rollback()
        if eigene_engine and engine is not None:
            engine.dispose()
        sperre.release()

"""ZUGFeRD-Ausgang: Rechnungen einer Fremdanwendung zu E-Rechnungen machen.

Der Weg (bei EGP): Access druckt die Rechnung wie immer als PDF und legt sie
zusammen mit den Rechnungsdaten in tInvoice/tInvoicePositions auf dem SQL-Server
ab. Datenmonster holt neue Zeilen ab, baut das ZUGFeRD-XML, bettet es in die PDF
ein und schreibt die fertige Datei samt Status in tInvoice zurück (ZugferdFile),
damit Access sie per Outlook verschicken kann. Ein FTP-Server ist nur noch eine
zusätzliche, freiwillige Ablage.

Bewusst eine eigene FTP-Anbindung statt einer FTP-Quelle: die FTP-Quellen sind
Importe (Dateien holen, in ein Dataset schreiben) und würden mit ihrem Zeitplan
die abgelegten Rechnungen wieder einlesen. Die Verbindungsfunktionen selbst
kommen aus ftp_service.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric
from sqlalchemy.sql import func

from app.core.database import Base


class ZugferdAusgang(Base):
    """Einstellungen je Datenbankverbindung (eine Fremdanwendung = eine Verbindung)."""

    __tablename__ = "zugferd_ausgang"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, nullable=False, unique=True, index=True)
    project_id = Column(Integer, nullable=True, index=True)

    tabelle_kopf = Column(String, default="dbo.tInvoice")
    tabelle_positionen = Column(String, default="dbo.tInvoicePositions")

    # Ziel
    protokoll = Column(String, default="ftp")                 # ftp | sftp
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)                  # verschlüsselt
    verzeichnis = Column(String, default="/")
    dateiname_muster = Column(String, default="{nummer}.pdf")

    aktiv = Column(Boolean, default=False)
    cron_expr = Column(String, default="*/5 * * * *")

    # Anstoß aus Access: nur der SHA-256 des Schlüssels liegt hier. Der Schlüssel
    # selbst wird einmal angezeigt und steht danach nur noch im Access-Modul.
    ausloese_hash = Column(String, nullable=True, index=True)

    letzter_lauf = Column(DateTime(timezone=True), nullable=True)
    letzter_status = Column(String, nullable=True)            # ok | fehler
    letzter_fehler = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ZugferdBeleg(Base):
    """Protokoll: jede erzeugte (oder abgewiesene) Rechnung."""

    __tablename__ = "zugferd_beleg"

    id = Column(Integer, primary_key=True, index=True)
    ausgang_id = Column(Integer, nullable=False, index=True)
    connection_id = Column(Integer, nullable=False, index=True)

    invoice_id = Column(Integer, nullable=True, index=True)   # tInvoice.InvoiceId
    nummer = Column(String, nullable=True, index=True)
    art = Column(String, nullable=True)                       # RECHNUNG | STORNO | KORREKTUR
    kunde = Column(String, nullable=True)
    datum = Column(String, nullable=True)                     # Rechnungsdatum JJJJ-MM-TT
    brutto = Column(Numeric(18, 2), nullable=True)

    status = Column(String, nullable=False, index=True)       # ok | fehler
    meldung = Column(Text, nullable=True)                     # Fehler bzw. Warnungen
    dateiname = Column(String, nullable=True)                 # so liegt sie auf dem FTP
    pfad = Column(String, nullable=True)                      # Kopie im uploads-Volume
    ausgeloest_von = Column(String, nullable=True)            # Zeitplan | Benutzername

    erstellt_am = Column(DateTime(timezone=True), server_default=func.now(), index=True)

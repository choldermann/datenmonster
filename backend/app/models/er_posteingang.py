"""Posteingang für Eingangsrechnungen: Quellen und die Belege, die dort liegen.

Warum überhaupt: Rechnungen kamen bisher ausschließlich von Hand herein — jemand
zieht eine Datei in die Ablagefläche. Ab Januar 2027 verschickt Wepa nur noch
über Peppol, und weitere Lieferanten werden folgen; niemand soll dafür täglich
ein Postfach durchsehen.

Bewusst anbieterunabhängig: Eine Quelle ist ein IMAP-Postfach oder ein Ordner,
nicht die API eines bestimmten Peppol-Dienstleisters. Jeder Access Point kann
Belege per Mail weiterleiten oder in einen Ordner legen — welcher es am Ende
wird, ist damit keine Bauentscheidung mehr. Kommt später eine API dazu, ist sie
eine weitere Bezugsquelle in derselben Liste.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ErPosteingangQuelle(Base):
    """Woher Belege geholt werden."""

    __tablename__ = "er_posteingang_quelle"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    art = Column(String, nullable=False, default="imap")      # imap | ordner
    aktiv = Column(Boolean, default=True)

    # Für welchen Mandanten die Belege dieser Quelle gelten. Pflicht: ohne ihn
    # wäre beim Einlesen nicht klar, gegen welche Wawi geprüft werden soll —
    # und eine Rechnung im falschen Betrieb ist schlimmer als keine.
    mandant_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=True, index=True)

    # IMAP
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)                  # verschlüsselt abgelegt
    ssl = Column(Boolean, default=True)
    ordner = Column(String, default="INBOX")                  # IMAP-Ordner
    nach_abholung = Column(String, default="gelesen")         # gelesen | verschieben
    ziel_ordner = Column(String, nullable=True)               # bei verschieben

    # Ordner (im Container sichtbarer Pfad, z. B. ein eingebundenes Netzlaufwerk)
    pfad = Column(String, nullable=True)

    # Was als Beleg gilt. PDFs sind mitgemeint: viele Lieferanten schicken
    # weiterhin ZUGFeRD-PDFs, und der Leser kommt mit beidem zurecht.
    endungen = Column(String, default=".xml,.pdf")

    cron_expr = Column(String, nullable=True)                 # leer = nur von Hand
    letzter_lauf = Column(DateTime(timezone=True), nullable=True)
    letzter_status = Column(String, nullable=True)            # ok | fehler
    letzter_fehler = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ErPosteingangBeleg(Base):
    """Ein abgeholter Beleg, der auf seine Freigabe wartet."""

    __tablename__ = "er_posteingang_beleg"

    id = Column(Integer, primary_key=True, index=True)
    quelle_id = Column(Integer, nullable=True, index=True)    # NULL = von Hand abgelegt
    mandant_id = Column(Integer, nullable=False, index=True)

    dateiname = Column(String, nullable=False)
    pfad = Column(String, nullable=False)                     # im uploads-Volume
    # Derselbe Beleg kommt gern zweimal: als Mail-Anhang und noch einmal, weil
    # jemand die Mail erneut zustellt. Der Hash über den Inhalt hält ihn draußen,
    # ohne sich auf Dateinamen oder Betreffzeilen verlassen zu müssen.
    hash = Column(String, nullable=False, index=True)
    groesse = Column(Integer, nullable=True)

    absender = Column(String, nullable=True)
    betreff = Column(String, nullable=True)
    empfangen_am = Column(DateTime(timezone=True), server_default=func.now())

    # neu = wartet · erledigt = verbucht · verworfen = bewusst aussortiert
    status = Column(String, nullable=False, default="neu", index=True)
    kEingangsrechnung = Column(Integer, nullable=True)
    notiz = Column(Text, nullable=True)

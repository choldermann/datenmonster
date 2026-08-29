"""Preisautomatik: Regelwerke, Regeln, Läufe und das Änderungsjournal.

Warum eigene Tabellen und nicht business_config: Eine Preisregel ist kein
Schwellwert, sie hat einen Lebenslauf. Zu jeder Preisänderung müssen der
Vorher-Wert, die auslösende Regel, der Zustand (vorgeschlagen → freigegeben →
angewandt → zurückgenommen) und das Ergebnis der Soll/Ist-Kontrolle abfragbar
bleiben — sonst kann man weder zurückrollen noch beantworten, warum ein Artikel
das kostet, was er kostet.

Angewandt wird über SONDERPREISE (tArtikelSonderpreis + tSonderpreise), nie über
den Grundpreis: Ein Sonderpreis ist befristet, gruppenbezogen und läuft über
dEnde von selbst aus. Siehe doku/jtl-preis-schema.md und
docs/plans/preisautomatik-reiniger.md.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, JSON, DateTime, Float, Index
from datetime import datetime, timezone
from app.core.database import Base


def _jetzt():
    return datetime.now(timezone.utc)


# Zustände einer geplanten Preisänderung. Ein Lauf legt nur `vorgeschlagen` an;
# alles Weitere ist eine bewusste Handlung (oder das Sicherheitsnetz).
ZUSTAENDE = ("vorgeschlagen", "freigegeben", "angewandt", "zurueckgenommen",
             "verworfen", "fehlgeschlagen")

# Offene Zustände: ein erneuter Lauf soll dafür keinen zweiten Vorschlag bauen.
OFFENE_ZUSTAENDE = ("vorgeschlagen", "freigegeben", "angewandt")


class PriceRuleset(Base):
    """Ein Regelwerk gilt für genau EINEN Mandanten (eine JTL-Verbindung) —
    Preise des einen Betriebs dürfen nie die des anderen bewegen."""

    __tablename__ = "price_rulesets"

    id             = Column(Integer, primary_key=True, index=True)
    project_id     = Column(Integer, nullable=True, index=True)
    connection_id  = Column(Integer, nullable=False, index=True)   # Mandant
    name           = Column(String, nullable=False)
    description    = Column(Text, nullable=True)
    active         = Column(Boolean, default=False)                # aus, bis bewusst eingeschaltet

    # Welche Artikel überhaupt in Frage kommen:
    #   {"warengruppen": [...], "hersteller": [...], "min_bestand": 1,
    #    "artikel_ausschluss": ["1234", ...], "nur_aktive": true}
    scope          = Column(JSON, default=dict)
    # Für welche Kundengruppen/Shops der Rabatt gilt. Leere Liste = alle
    # Kundengruppen mit eigenem Preis, kShop 0 = alle Kanäle.
    kundengruppen  = Column(JSON, default=list)
    shops          = Column(JSON, default=list)

    # Sicherheitsnetz – siehe preisregel_service._sicherheitsnetz
    nie_unter_ek       = Column(Boolean, default=True)
    min_marge_prozent  = Column(Float, nullable=True)
    max_rabatt_prozent = Column(Float, nullable=True)

    laufzeit_tage  = Column(Integer, default=30)     # dEnde des Sonderpreises
    preisendung    = Column(String, nullable=True)   # z.B. "0.99" – optional
    # Automatische Freigabe ist eine bewusste Einstellung, kein Standard.
    auto_freigabe  = Column(Boolean, default=False)
    # Kandidatenliste kommt aus einem ganz normalen Mapping (SQL bleibt SQL).
    kandidaten_mapping = Column(String, default="Preisautomatik – Ladenhüter-Kandidaten")

    created_at     = Column(DateTime, default=_jetzt)
    updated_at     = Column(DateTime, default=_jetzt, onupdate=_jetzt)


class PriceRule(Base):
    """Eine Stufe innerhalb eines Regelwerks. Die Stufen werden absteigend nach
    `sort` geprüft, die erste zutreffende gewinnt – so schlägt „90 Tage → 20 %"
    die Stufe „30 Tage → 5 %"."""

    __tablename__ = "price_rules"

    id          = Column(Integer, primary_key=True, index=True)
    ruleset_id  = Column(Integer, nullable=False, index=True)
    sort        = Column(Integer, default=100)
    active      = Column(Boolean, default=True)
    label       = Column(String, nullable=True)
    kind        = Column(String, default="ladenhueter")
    # {"tage_ohne_verkauf_ab": 60}
    condition   = Column(JSON, default=dict)
    # {"typ": "rabatt_prozent", "wert": 10}  |  {"typ": "zielpreis", "wert": 9.99}
    action      = Column(JSON, default=dict)
    created_at  = Column(DateTime, default=_jetzt)
    updated_at  = Column(DateTime, default=_jetzt, onupdate=_jetzt)


class PriceRun(Base):
    """Ein Durchlauf eines Regelwerks. Auch ein Lauf ohne Vorschläge wird
    festgehalten – sonst weiß man später nicht, ob nichts zu tun war oder
    nichts gelaufen ist."""

    __tablename__ = "price_runs"

    id            = Column(Integer, primary_key=True, index=True)
    ruleset_id    = Column(Integer, nullable=False, index=True)
    project_id    = Column(Integer, nullable=True, index=True)
    connection_id = Column(Integer, nullable=False, index=True)
    started_at    = Column(DateTime, default=_jetzt)
    finished_at   = Column(DateTime, nullable=True)
    triggered_by  = Column(String, default="manuell")   # manuell | scheduler
    status        = Column(String, default="laeuft")    # laeuft | fertig | fehler
    kandidaten    = Column(Integer, default=0)
    vorschlaege   = Column(Integer, default=0)
    verworfen     = Column(Integer, default=0)
    params        = Column(JSON, default=dict)
    error         = Column(Text, nullable=True)


class PriceChange(Base):
    """Das Änderungsjournal – das Rückgrat der Automatik.

    Eine Zeile je Artikel × Kundengruppe × Shop. `preis_alt` samt Quelle wird VOR
    dem Anwenden gelesen; ohne Vorher-Wert entsteht kein Vorschlag. Eine Rücknahme
    löscht nichts, sondern erzeugt eine neue Zeile, die den Sonderpreis beendet.
    """

    __tablename__ = "price_changes"

    id             = Column(Integer, primary_key=True, index=True)
    run_id         = Column(Integer, nullable=True, index=True)
    ruleset_id     = Column(Integer, nullable=False, index=True)
    rule_id        = Column(Integer, nullable=True)
    project_id     = Column(Integer, nullable=True, index=True)
    connection_id  = Column(Integer, nullable=False, index=True)

    k_artikel      = Column(Integer, nullable=False, index=True)
    c_artnr        = Column(String, nullable=True)
    artikelname    = Column(String, nullable=True)   # mitgeschrieben, damit das
                                                     # Journal lesbar bleibt
    k_kundengruppe = Column(Integer, nullable=False, default=0)
    kundengruppe   = Column(String, nullable=True)   # Klartext, wie beim Artikelnamen
    k_shop         = Column(Integer, nullable=False, default=0)

    preis_alt        = Column(Float, nullable=True)
    preis_alt_quelle = Column(String, nullable=True)  # fVKNetto | tPreisDetail | sonderpreis
    preis_neu        = Column(Float, nullable=True)
    ek_netto         = Column(Float, nullable=True)   # Basis des Sicherheitsnetzes
    steuersatz       = Column(Float, nullable=True)   # für den Brutto-VK der Ameise
    gueltig_von      = Column(DateTime, nullable=True)
    gueltig_bis      = Column(DateTime, nullable=True)

    zustand        = Column(String, default="vorgeschlagen", index=True)
    weg            = Column(String, nullable=True)    # ameise | direkt
    export_file_id = Column(Integer, nullable=True)   # erzeugte CSV
    angewandt_am   = Column(DateTime, nullable=True)
    angewandt_von  = Column(String, nullable=True)
    # Rücknahme: zeigt auf die Zeile, die zurückgenommen wird.
    ruecknahme_von = Column(Integer, nullable=True, index=True)

    kontrolliert_am = Column(DateTime, nullable=True)
    ist_preis       = Column(Float, nullable=True)
    abweichung      = Column(String, nullable=True)   # ok | fehlt | abweichend

    begruendung    = Column(Text, nullable=True)      # Klartext, kein Code
    created_at     = Column(DateTime, default=_jetzt)
    updated_at     = Column(DateTime, default=_jetzt, onupdate=_jetzt)


# Der häufigste Zugriff: "gibt es für diesen Artikel/Gruppe/Shop schon etwas
# Offenes?" – beim Lauf für jeden Kandidaten einmal.
Index("ix_price_changes_ziel", PriceChange.connection_id, PriceChange.k_artikel,
      PriceChange.k_kundengruppe, PriceChange.k_shop, PriceChange.zustand)

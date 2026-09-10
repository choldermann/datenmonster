"""Inventur: Stichtagsbestände einfrieren, bewerten und dokumentieren.

Warum eigene Tabellen und kein Mapping-Ergebnis: Eine Inventur ist ein Beleg.
Sie muss Jahre später noch genau die Zahlen zeigen, die damals an den
Steuerberater gingen — auch wenn sich Bestände, Einkaufspreise und Artikelnamen
seither geändert haben. Ein Mapping rechnet dagegen immer den Jetzt-Zustand.
Deshalb wird die Liste beim Anlegen als Momentaufnahme in `inventur_positionen`
geschrieben und danach nicht mehr aus der WaWi nachgeladen.

Die Bestandsermittlung selbst bleibt SQL (Mapping „Inventur – Bestand zum
Stichtag"), damit sie nachvollziehbar und anpassbar ist — dieselbe Trennung wie
bei der Preisautomatik (Kandidaten-Mapping → Lauf → Journal).

Bewusst NICHT enthalten: das Zurückschreiben des abgewerteten Wertes in die
WaWi. JTL kennt keinen Abwertungswert, der Lagerwert ist dort immer Menge × EK;
ein Rückschreiben müsste also den Einkaufspreis verfälschen. Siehe
doku/inventur.md.
"""
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, JSON, Date, DateTime, Index
from datetime import datetime, timezone
from app.core.database import Base


def _jetzt():
    return datetime.now(timezone.utc)


# Eine abgeschlossene Inventur ist unveränderlich – sie ist der Beleg.
STATUS = ("offen", "abgeschlossen")

# Vorschlagsstufen für die Abwertung nach Restlaufzeit. Der Anwender kann jede
# Zeile überschreiben; der Vorschlag nimmt ihm nur das Vorsortieren ab.
STANDARD_STUFEN = [
    {"bis_tage": 0,   "prozent": 100, "label": "MHD überschritten"},
    {"bis_tage": 90,  "prozent": 50,  "label": "unter 3 Monate Restlaufzeit"},
    {"bis_tage": 180, "prozent": 25,  "label": "3 bis 6 Monate Restlaufzeit"},
]


class InventurLauf(Base):
    """Eine Inventur zu genau einem Stichtag und einem Mandanten."""

    __tablename__ = "inventur_laeufe"

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(Integer, nullable=True, index=True)
    # Mandant: Bestände des einen Betriebs dürfen nie in der Inventur des
    # anderen auftauchen (gleiche Regel wie bei Fixkosten und Preisregeln).
    connection_id = Column(Integer, nullable=False, index=True)
    name          = Column(String, nullable=False)
    stichtag      = Column(Date, nullable=False, index=True)
    status        = Column(String, default="offen", index=True)
    notiz         = Column(Text, nullable=True)

    # Woher die Liste kam – gehört zur Nachvollziehbarkeit dazu.
    quelle_mapping = Column(String, nullable=True)

    # Summen, beim Befüllen und nach jeder Bewertung neu gerechnet. Redundant
    # zu den Positionen, aber die Übersicht soll nicht 700 Zeilen summieren
    # müssen, und der abgeschlossene Lauf trägt seine Summe selbst.
    positionen_anzahl  = Column(Integer, default=0)
    bestand_wert       = Column(Float, default=0.0)   # Wert zum EK, vor Abwertung
    abwertung_summe    = Column(Float, default=0.0)
    wert_nach_abwertung = Column(Float, default=0.0)
    bewertete_positionen = Column(Integer, default=0)

    # Was beim Befüllen aufgefallen ist: Bestand ohne Chargenzuordnung, Artikel
    # ohne gebuchten EK. Eine Inventur, die solche Lücken verschweigt, ist
    # wertlos – deshalb reisen sie als Prüfhinweise mit.
    hinweise      = Column(JSON, default=list)

    # Ab wann wie viel abgewertet wird. Gehört zum Beleg: eine abgeschlossene
    # Inventur muss zeigen, nach welcher Staffel damals vorgeschlagen wurde, auch
    # wenn sie später geändert wird. Leer = STANDARD_STUFEN.
    abwertung_stufen = Column(JSON, nullable=True)

    # Verlauf: angelegt, eingelesen, abgeschlossen, wieder geöffnet – mit Zeit und
    # Person. `abgeschlossen_am/_von` nennen nur den LETZTEN Abschluss; ohne Verlauf
    # verschwände ein früherer Abschluss beim erneuten Abschließen spurlos.
    protokoll = Column(JSON, nullable=True)

    # Zähltag: an welchem Tag physisch gezählt wurde. Leer = am Stichtag. Liegt er
    # daneben, wird die gezählte Menge über die Buchungen dazwischen auf den
    # Stichtag zurückgerechnet (vor-/nachverlegte Stichtagsinventur, § 241 HGB).
    zaehltag = Column(Date, nullable=True)
    gezaehlte_positionen    = Column(Integer, default=0)
    differenz_wert          = Column(Float, default=0.0)   # Wert Ist minus Wert Soll
    abweichungen_ohne_grund = Column(Integer, default=0)

    erstellt_von     = Column(String, nullable=True)
    created_at       = Column(DateTime, default=_jetzt)
    updated_at       = Column(DateTime, default=_jetzt, onupdate=_jetzt)
    abgeschlossen_am = Column(DateTime, nullable=True)
    abgeschlossen_von = Column(String, nullable=True)


class InventurPosition(Base):
    """Eine Zeile der Inventur: ein Artikel zum Stichtag.

    Alle Stammdaten (Name, Warengruppe, EK) sind mitgeschrieben, nicht verlinkt —
    sonst zeigt der Beleg in zwei Jahren andere Zahlen als damals gedruckt.
    """

    __tablename__ = "inventur_positionen"

    id         = Column(Integer, primary_key=True, index=True)
    lauf_id    = Column(Integer, nullable=False, index=True)
    k_artikel  = Column(Integer, nullable=False, index=True)
    c_artnr    = Column(String, nullable=True)
    artikelname = Column(String, nullable=True)
    warengruppe = Column(String, nullable=True)
    hersteller  = Column(String, nullable=True)

    bestand    = Column(Float, default=0.0)
    ek         = Column(Float, default=0.0)      # gewichteter EK der Partien
    wert       = Column(Float, default=0.0)      # bestand × ek, zum Stichtag

    # MHD-Sicht: das früheste MHD der bestandsführenden Partien ist das
    # kritische – daran hängt der Abwertungsvorschlag.
    mhd_frueh        = Column(Date, nullable=True)
    resttage         = Column(Integer, nullable=True)
    menge_abgelaufen = Column(Float, default=0.0)
    wert_abgelaufen  = Column(Float, default=0.0)

    # Abverkauf: wie schnell die Ware wirklich weggeht.
    abgang_12m      = Column(Float, default=0.0)
    reichweite_tage = Column(Integer, nullable=True)
    letzter_abgang  = Column(Date, nullable=True)

    # Die Partien als Momentaufnahme: [{charge, mhd, menge, ek, wert}, …]
    chargen         = Column(JSON, default=list)
    # Menge, die sich keiner Eingangspartie zuordnen ließ (Altbestand aus der
    # Zeit vor der Buchungshistorie). Wird bewertet, aber ohne MHD.
    menge_ohne_partie = Column(Float, default=0.0)

    # ── Zählung ─────────────────────────────────────────────────────────────
    # `bestand`, `wert`, `menge_abgelaufen`, `wert_abgelaufen` und die Chargen tragen
    # die GÜLTIGE Menge (Ist zum Stichtag, wo gezählt). Die Buchmenge laut Wawi steht
    # in den *_soll-Feldern – so rechnen Abwertung, Staffel, Summen und Export ohne
    # Sonderweg mit der gezählten Menge. *_soll NULL = nie gezählt, dann gilt Soll.
    bestand_soll          = Column(Float, nullable=True)
    wert_soll             = Column(Float, nullable=True)
    menge_abgelaufen_soll = Column(Float, nullable=True)
    wert_abgelaufen_soll  = Column(Float, nullable=True)
    soll_zaehltag   = Column(Float, nullable=True)    # Buchmenge am Zähltag
    ist_gezaehlt    = Column(Float, nullable=True)    # gezählt am Zähltag; NULL = nicht gezählt
    zaehlung_ebene  = Column(String, nullable=True)   # artikel | charge | NULL
    differenz       = Column(Float, nullable=True)    # Ist − Soll am Zähltag (Stück)
    differenz_grund = Column(String, nullable=True)
    differenz_notiz = Column(Text, nullable=True)
    gezaehlt_am     = Column(DateTime, nullable=True)
    gezaehlt_von    = Column(String, nullable=True)
    # Altbestand ohne Chargenzuordnung: bei Chargenartikeln eine eigene Zählzeile.
    menge_ohne_partie_soll = Column(Float, nullable=True)
    ist_ohne_partie        = Column(Float, nullable=True)   # gezählt am Zähltag
    rest_soll_zaehltag     = Column(Float, nullable=True)   # Menge ohne Charge am Zähltag
    # Woher eine Zählung kam (Dateiname der Zählliste oder „Eingabe <Benutzer>").
    # Bei Chargen steht sie im Chargeneintrag (`ist_quelle`). Nötig, um beim
    # Zurückspielen verteilter Listen Überschreibungen mit ihrer Herkunft zu melden.
    ist_quelle             = Column(String, nullable=True)
    ist_ohne_partie_quelle = Column(String, nullable=True)

    # ── Bewertung durch den Anwender ────────────────────────────────────────
    # art: prozent | stueckwert | betrag – der Anwender denkt je nach Ware
    # anders („die Hälfte wert" vs. „noch 2 € das Stück").
    bewertung_art   = Column(String, nullable=True)
    bewertung_wert  = Column(Float, nullable=True)
    abwertung_betrag = Column(Float, default=0.0)
    wert_neu         = Column(Float, nullable=True)
    grund            = Column(Text, nullable=True)
    vorschlag        = Column(Boolean, default=False)  # aus der Stufenregel, noch nicht bestätigt
    # Woher die Bewertung stammt: "staffel" (auch nach dem Übernehmen) oder "hand".
    # Ohne das wäre eine übernommene Staffel-Bewertung von Handarbeit nicht zu
    # unterscheiden, und eine geänderte Staffel könnte sie nie mehr neu rechnen.
    bewertung_quelle = Column(String, nullable=True)
    bewertet_am      = Column(DateTime, nullable=True)
    bewertet_von     = Column(String, nullable=True)

    created_at = Column(DateTime, default=_jetzt)


# Der häufigste Zugriff: alle Positionen eines Laufs, sortiert nach Wert.
Index("ix_inventur_pos_lauf_wert", InventurPosition.lauf_id, InventurPosition.wert)

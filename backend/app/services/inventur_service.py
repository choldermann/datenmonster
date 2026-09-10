"""Inventur: Bestandsliste einfrieren, bewerten, Summen führen.

Ablauf einer Inventur:
  1. anlegen()   – Kopf mit Stichtag und Mandant
  2. befuellen() – führt das Bestands-Mapping aus und schreibt das Ergebnis als
                   Momentaufnahme in die Positionen. Ab hier ist die Liste
                   unabhängig von der WaWi.
  3. vorschlag_anwenden() – setzt Abwertungsvorschläge nach Restlaufzeit
  4. bewerten()  – der Anwender überschreibt einzelne Zeilen
  5. abschliessen() – friert den Lauf ein; er ist danach der Beleg.

Die Bestandsermittlung selbst steht bewusst NICHT hier, sondern in einem
Mapping (SQL bleibt SQL). Dieser Service kennt nur die Spaltennamen, die das
Mapping liefern muss – siehe SPALTEN.
"""
from datetime import date, datetime, timezone
from typing import Optional, List

from app.models.inventur import (InventurLauf, InventurPosition, STANDARD_STUFEN)

# Standardname des Mappings, das die Bestandsliste liefert. Kommt aus dem
# Template jtl_lager_cockpit; am Lauf überschreibbar.
STANDARD_MAPPING = "Inventur – Bestand zum Stichtag"

# Spalten, die das Bestands-Mapping liefern muss. Fehlt eine, bleibt das Feld
# leer – die Inventur läuft trotzdem, nur mit weniger Information.
SPALTEN = {
    "k_artikel": ("kArtikel", "k_artikel"),
    "c_artnr": ("ArtNr", "cArtNr", "Artikelnummer"),
    "artikelname": ("Artikel", "Artikelname", "cName"),
    "warengruppe": ("Warengruppe",),
    "hersteller": ("Hersteller",),
    "bestand": ("Bestand", "Menge"),
    "ek": ("EK", "EK netto"),
    "wert": ("Wert", "Bestandswert"),
    "mhd_frueh": ("MHD", "MHD früh", "MHD frühestes"),
    "resttage": ("Resttage", "Restzeit Tage"),
    "menge_abgelaufen": ("Menge abgelaufen",),
    "wert_abgelaufen": ("Wert abgelaufen",),
    "abgang_12m": ("Abgang 12M", "Abgang 12 Monate"),
    "reichweite_tage": ("Reichweite Tage", "Reichweite"),
    "letzter_abgang": ("Letzter Abgang",),
    "menge_ohne_partie": ("Menge ohne Charge", "Menge ohne Partie"),
    "chargen": ("Chargen",),
}


def _jetzt():
    return datetime.now(timezone.utc)


def _hole(row: dict, feld: str):
    """Liest einen Wert aus der Mapping-Zeile über die erlaubten Spaltennamen."""
    for name in SPALTEN.get(feld, ()):
        if name in row:
            return row[name]
    return None


def _zahl(v, default=0.0) -> float:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _ganzzahl(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _datum(v) -> Optional[date]:
    """Nimmt date, datetime oder String. Deutsche Schreibweise inbegriffen –
    die Mappings formatieren MHD teilweise als TT.MM.JJJJ für die Anzeige."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ─── Bestandsliste aus dem Mapping holen ──────────────────────────────────────

def _resolve_mapping(db, project_id, name: str):
    from app.models.mapping import Mapping
    q = db.query(Mapping).filter(Mapping.name == name)
    if project_id is not None:
        q = q.filter(Mapping.project_id == project_id)
    return q.first()


# Eine Inventur kann viele Positionen haben – der Deckel muss großzügig sein,
# sonst fehlt am Jahresende stillschweigend Ware in der Liste.
ZEILEN_MAX = 20000


def bestandsliste_laden(db, lauf: InventurLauf) -> list:
    """Führt das Bestands-Mapping in der WaWi des Laufs aus.

    SQL bleibt SQL: Wie ein Stichtagsbestand ermittelt wird, steht in einem
    normalen Mapping und ist im Editor nachlesbar und anpassbar – dieselbe
    Trennung wie bei der Preisautomatik.
    """
    from app.services.mapping_service import MappingContext, execute_mapping
    from app.services import mandant_service

    name = lauf.quelle_mapping or STANDARD_MAPPING
    m = _resolve_mapping(db, lauf.project_id, name)
    if not m:
        raise ValueError(f"Die Auswertung „{name}“ ist in diesem Projekt nicht "
                         f"installiert.")
    ctx = MappingContext.from_orm(m)
    # Über lauf_vorbereiten, nicht mit einem selbstgebauten Parameter-Dict: die
    # Abfrage erwartet auch die Ausschlusslisten und die Schwellwerte des
    # Mandanten. Ein fehlender Listen-Parameter bricht den Lauf ab, ein falscher
    # Mandant wäre schlimmer – dann stünden fremde Bestände in der Inventur.
    ctx.run_params, _ = mandant_service.lauf_vorbereiten(
        {"stichtag": lauf.stichtag}, lauf.project_id, db,
        mandant_id=lauf.connection_id)
    mandant_service.verbindung_ersetzen(ctx, lauf.connection_id, db, m.project_id)
    if not ctx.targets:
        raise ValueError(f"Die Auswertung „{name}“ hat kein Ziel.")
    felder = ctx.targets[0].get("fields") or []
    res = execute_mapping(row_cap=ZEILEN_MAX, **ctx.to_execute_kwargs(felder, ZEILEN_MAX))
    fehler = res.get("errors") or []
    rows = res.get("rows") or []
    if fehler and not rows:
        raise ValueError(f"Bestandsermittlung fehlgeschlagen: {str(fehler[0])[:200]}")
    if rows and _hole(rows[0], "k_artikel") is None:
        raise ValueError("Die Bestandsauswertung liefert keine Spalte „kArtikel“ – "
                         "ohne sie lässt sich keine Position zuordnen.")
    return rows


# ─── Anlegen und Befüllen ─────────────────────────────────────────────────────

def anlegen(db, project_id: Optional[int], connection_id: int, name: str,
            stichtag: date, notiz: str = None, quelle_mapping: str = None,
            benutzer: str = None) -> InventurLauf:
    lauf = InventurLauf(
        project_id=project_id,
        connection_id=connection_id,
        name=name,
        stichtag=stichtag,
        notiz=notiz,
        quelle_mapping=quelle_mapping or STANDARD_MAPPING,
        status="offen",
        erstellt_von=benutzer,
    )
    db.add(lauf)
    db.commit()
    db.refresh(lauf)
    return lauf


def befuellen(db, lauf: InventurLauf, zeilen: List[dict], benutzer: str = None) -> dict:
    """Schreibt das Ergebnis des Bestands-Mappings als Momentaufnahme.

    Ein erneutes Befüllen ersetzt die Positionen vollständig – inklusive bereits
    erfasster Bewertungen. Das ist Absicht: eine halb aktualisierte Liste, in der
    Abwertungen an Mengen hängen, die es nicht mehr gibt, wäre schlimmer als
    ein bewusster Neuanfang. Der Aufrufer warnt vorher.
    """
    if lauf.status == "abgeschlossen":
        raise ValueError("Die Inventur ist abgeschlossen und kann nicht neu befüllt werden.")

    db.query(InventurPosition).filter(InventurPosition.lauf_id == lauf.id).delete()

    ohne_ek = 0
    menge_ohne_partie_gesamt = 0.0
    angelegt = 0

    for row in zeilen or []:
        k_artikel = _ganzzahl(_hole(row, "k_artikel"))
        if k_artikel is None:
            continue
        bestand = _zahl(_hole(row, "bestand"))
        if abs(bestand) < 0.0001:
            continue
        ek = _zahl(_hole(row, "ek"))
        wert = _hole(row, "wert")
        wert = _zahl(wert) if wert is not None else bestand * ek
        if ek <= 0:
            ohne_ek += 1
        ohne_partie = _zahl(_hole(row, "menge_ohne_partie"))
        menge_ohne_partie_gesamt += ohne_partie

        chargen = _hole(row, "chargen")
        if isinstance(chargen, str):
            # Das Mapping kann die Partien als JSON-Text liefern (MSSQL FOR JSON).
            import json
            try:
                chargen = json.loads(chargen)
            except ValueError:
                chargen = []

        pos = InventurPosition(
            lauf_id=lauf.id,
            k_artikel=k_artikel,
            c_artnr=_hole(row, "c_artnr"),
            artikelname=_hole(row, "artikelname"),
            warengruppe=_hole(row, "warengruppe"),
            hersteller=_hole(row, "hersteller"),
            bestand=bestand,
            ek=ek,
            wert=wert,
            mhd_frueh=_datum(_hole(row, "mhd_frueh")),
            resttage=_ganzzahl(_hole(row, "resttage")),
            menge_abgelaufen=_zahl(_hole(row, "menge_abgelaufen")),
            wert_abgelaufen=_zahl(_hole(row, "wert_abgelaufen")),
            abgang_12m=_zahl(_hole(row, "abgang_12m")),
            reichweite_tage=_ganzzahl(_hole(row, "reichweite_tage")),
            letzter_abgang=_datum(_hole(row, "letzter_abgang")),
            menge_ohne_partie=ohne_partie,
            chargen=chargen if isinstance(chargen, list) else [],
        )
        db.add(pos)
        angelegt += 1

    hinweise = []
    if ohne_ek:
        hinweise.append({
            "art": "ohne_ek",
            # Diese Positionen stehen mit 0 € in der Liste – weder eine
            # Eingangsbuchung noch der Artikelstamm kennen einen Preis. Eine
            # Inventur muss das ausweisen, sonst fehlt der Wert unbemerkt.
            "text": f"{ohne_ek} Artikel haben überhaupt keinen Einkaufspreis "
                    f"(weder gebucht noch im Artikelstamm) und stehen deshalb "
                    f"mit 0 € in der Liste.",
            "anzahl": ohne_ek,
        })
    if menge_ohne_partie_gesamt > 0.0001:
        hinweise.append({
            "art": "ohne_partie",
            "text": f"{menge_ohne_partie_gesamt:,.0f} Stück lassen sich keiner "
                    f"Eingangspartie zuordnen (Altbestand aus der Zeit vor der "
                    f"Buchungshistorie) – für diese Menge gibt es kein MHD.".replace(",", "."),
            "anzahl": menge_ohne_partie_gesamt,
        })

    lauf.hinweise = hinweise
    lauf.updated_at = _jetzt()
    db.commit()
    summen_neu_rechnen(db, lauf)
    return {"positionen": angelegt, "hinweise": hinweise}


# ─── Bewerten ─────────────────────────────────────────────────────────────────

def _abwertung_rechnen(pos: InventurPosition, art: str, wert: float) -> tuple:
    """Rechnet aus der Eingabe des Anwenders (Prozent, neuer Stückwert oder
    Betrag) den Abwertungsbetrag und den neuen Positionswert.

    Ein Prozentsatz braucht einen BEZUG. „prozent" wirkt auf die ganze Position,
    „prozent_abgelaufen" nur auf den Wert der Partien, deren MHD am Stichtag
    vorbei war. Der Unterschied ist keine Kleinigkeit: Artikel 80123 bei PPS hat
    45.630 € Bestand, davon 31.936 € abgelaufen – die restlichen 13.694 € liegen
    in drei Chargen, die noch bis 2028 haltbar sind. „100 % Abschlag" auf die
    ganze Position hätte die mit abgeschrieben. Dieselbe Regel führt schon der
    Vorschlag (_vorschlag_fuer), nur staffelt der zusätzlich nach Restlaufzeit.

    Gedeckelt auf den Bestandswert: eine Abwertung kann eine Position auf null
    bringen, aber nicht ins Negative – ein negativer Lagerwert wäre keine
    Bewertung mehr, sondern ein Tippfehler mit Folgen für die Bilanz.
    """
    basis = pos.wert or 0.0
    if art == "prozent":
        betrag = basis * (wert / 100.0)
    elif art == "prozent_abgelaufen":
        betrag = (pos.wert_abgelaufen or 0.0) * (wert / 100.0)
    elif art == "stueckwert":
        betrag = basis - (pos.bestand or 0.0) * wert
    elif art == "betrag":
        betrag = wert
    else:
        raise ValueError(f"Unbekannte Bewertungsart: {art}")

    betrag = max(0.0, min(betrag, basis))
    return round(betrag, 2), round(basis - betrag, 2)


def bewerten(db, pos: InventurPosition, art: str, wert: float,
             grund: str = None, benutzer: str = None,
             vorschlag: bool = False) -> InventurPosition:
    betrag, neu = _abwertung_rechnen(pos, art, _zahl(wert))
    if not grund and art == "prozent_abgelaufen":
        # Der Bezug muss im Beleg stehen. Ohne ihn steht im Export des
        # Steuerberaters „50 %" neben einer Abwertung, die nur ein Drittel der
        # Position trifft – das sieht nach einem Rechenfehler aus.
        grund = (f"{_zahl(wert):g} % auf {_menge(pos.menge_abgelaufen)} Stück "
                 f"abgelaufene Ware ({_euro(pos.wert_abgelaufen)})")
    pos.bewertung_art = art
    pos.bewertung_wert = _zahl(wert)
    pos.abwertung_betrag = betrag
    pos.wert_neu = neu
    pos.grund = grund
    pos.vorschlag = vorschlag
    pos.bewertet_am = _jetzt()
    pos.bewertet_von = benutzer
    db.commit()
    return pos


def bewertung_loeschen(db, pos: InventurPosition) -> InventurPosition:
    pos.bewertung_art = None
    pos.bewertung_wert = None
    pos.abwertung_betrag = 0.0
    pos.wert_neu = None
    pos.grund = None
    pos.vorschlag = False
    pos.bewertet_am = None
    pos.bewertet_von = None
    db.commit()
    return pos


def _euro(v) -> str:
    """Betrag in deutscher Schreibweise – landet in Begründungen und im Export."""
    return f"{_zahl(v):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _menge(v) -> str:
    """Mengen im Begründungstext ohne Nachkommastellen, wenn sie ganzzahlig sind."""
    n = _zahl(v)
    return f"{n:,.0f}".replace(",", ".") if abs(n - round(n)) < 0.001 else f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _vorschlag_fuer(pos: InventurPosition, stufen: List[dict],
                    stichtag: date) -> tuple:
    """Rechnet den Abwertungsvorschlag einer Position aus ihren Partien.

    Entscheidend: gestaffelt wird je CHARGE, nicht je Artikel. Ein Artikel mit
    zehn Chargen hat oft eine abgelaufene und neun frische — würde die Stufe
    „MHD überschritten → 100 %" den ganzen Positionswert treffen, wäre bei PPS
    eine Position mit 45.630 € Bestand komplett abgewertet worden, obwohl nur
    31.936 € davon tatsächlich abgelaufen sind.

    Gibt (betrag, grundtext) zurück; betrag 0 heißt „kein Vorschlag".
    """
    betrag = 0.0
    teile = {}   # label → Menge

    for c in (pos.chargen or []):
        mhd = _datum(c.get("mhd"))
        if mhd is None:
            continue
        menge = _zahl(c.get("menge"))
        # `wert` kommt exakt summiert aus der Abfrage; menge × ek wäre um die
        # Rundung des angezeigten EK daneben.
        wert = _zahl(c.get("wert")) or menge * _zahl(c.get("ek"))
        if wert <= 0:
            continue
        resttage = (mhd - stichtag).days
        treffer = next((s for s in stufen if resttage <= _zahl(s.get("bis_tage"), 0)), None)
        if not treffer:
            continue
        prozent = _zahl(treffer.get("prozent"))
        if prozent <= 0:
            continue
        betrag += wert * prozent / 100.0
        label = treffer.get("label") or f"bis {_zahl(treffer.get('bis_tage')):g} Tage"
        teile[f"{label} ({prozent:g} %)"] = teile.get(f"{label} ({prozent:g} %)", 0) + menge

    if not teile:
        # Position ohne Chargenangabe, aber mit MHD am Artikel: dann trifft die
        # Stufe die ganze Position – mehr Information gibt es nicht her.
        if pos.resttage is None:
            return 0.0, None
        treffer = next((s for s in stufen if pos.resttage <= _zahl(s.get("bis_tage"), 0)), None)
        if not treffer:
            return 0.0, None
        prozent = _zahl(treffer.get("prozent"))
        if prozent <= 0:
            return 0.0, None
        return ((pos.wert or 0.0) * prozent / 100.0,
                f"{treffer.get('label') or 'Restlaufzeit'} ({prozent:g} %)")

    grund = "; ".join(f"{_menge(m)} Stück {label}" for label, m in teile.items())
    return betrag, grund


def vorschlag_anwenden(db, lauf: InventurLauf, stufen: List[dict] = None,
                       nur_unbewertete: bool = True, benutzer: str = None) -> dict:
    """Setzt Abwertungsvorschläge nach Restlaufzeit bis zum MHD.

    `nur_unbewertete` schützt die Handarbeit: wer eine Zeile schon selbst
    bewertet hat, will sie nicht von der Automatik überschrieben bekommen.
    Vorschläge sind als solche markiert (`vorschlag = True`) und lassen sich
    dadurch später von bestätigten Bewertungen unterscheiden.
    """
    if lauf.status == "abgeschlossen":
        raise ValueError("Die Inventur ist abgeschlossen.")

    stufen = stufen or STANDARD_STUFEN
    # Aufsteigend: die engste Stufe (kleinste bis_tage) gewinnt.
    stufen = sorted(stufen, key=lambda s: _zahl(s.get("bis_tage"), 0))

    q = db.query(InventurPosition).filter(InventurPosition.lauf_id == lauf.id)
    gesetzt = 0
    for pos in q.all():
        if nur_unbewertete and pos.bewertung_art and not pos.vorschlag:
            continue
        betrag, grund = _vorschlag_fuer(pos, stufen, lauf.stichtag)
        if betrag <= 0:
            continue
        bewerten(db, pos, "betrag", round(betrag, 2), grund=grund,
                 benutzer=benutzer, vorschlag=True)
        gesetzt += 1

    summen_neu_rechnen(db, lauf)
    return {"vorschlaege": gesetzt}


def vorschlaege_bestaetigen(db, lauf: InventurLauf, benutzer: str = None) -> dict:
    """Macht aus Vorschlägen verbindliche Bewertungen (Häkchen unter die Liste)."""
    if lauf.status == "abgeschlossen":
        raise ValueError("Die Inventur ist abgeschlossen.")
    rows = (db.query(InventurPosition)
            .filter(InventurPosition.lauf_id == lauf.id,
                    InventurPosition.vorschlag.is_(True)).all())
    for pos in rows:
        pos.vorschlag = False
        pos.bewertet_von = benutzer or pos.bewertet_von
        pos.bewertet_am = _jetzt()
    db.commit()
    return {"bestaetigt": len(rows)}


# ─── Summen und Abschluss ─────────────────────────────────────────────────────

def summen_neu_rechnen(db, lauf: InventurLauf) -> InventurLauf:
    from sqlalchemy import func as sqlfunc
    q = db.query(
        sqlfunc.count(InventurPosition.id),
        sqlfunc.coalesce(sqlfunc.sum(InventurPosition.wert), 0.0),
        sqlfunc.coalesce(sqlfunc.sum(InventurPosition.abwertung_betrag), 0.0),
        sqlfunc.count(InventurPosition.bewertung_art),
    ).filter(InventurPosition.lauf_id == lauf.id).one()

    lauf.positionen_anzahl = int(q[0] or 0)
    lauf.bestand_wert = round(float(q[1] or 0.0), 2)
    lauf.abwertung_summe = round(float(q[2] or 0.0), 2)
    lauf.wert_nach_abwertung = round(lauf.bestand_wert - lauf.abwertung_summe, 2)
    lauf.bewertete_positionen = int(q[3] or 0)
    lauf.updated_at = _jetzt()
    db.commit()
    db.refresh(lauf)
    return lauf


def abschliessen(db, lauf: InventurLauf, benutzer: str = None) -> InventurLauf:
    """Friert den Lauf ein. Offene Vorschläge gelten damit als bestätigt –
    wer abschließt, steht für die Zahlen ein."""
    if lauf.status == "abgeschlossen":
        return lauf
    vorschlaege_bestaetigen(db, lauf, benutzer)
    summen_neu_rechnen(db, lauf)
    lauf.status = "abgeschlossen"
    lauf.abgeschlossen_am = _jetzt()
    lauf.abgeschlossen_von = benutzer
    db.commit()
    db.refresh(lauf)
    return lauf


def wieder_oeffnen(db, lauf: InventurLauf) -> InventurLauf:
    """Nur für den Irrtumsfall. Der Abschluss bleibt in `abgeschlossen_am`
    stehen, damit sichtbar bleibt, dass der Beleg einmal fertig war."""
    lauf.status = "offen"
    lauf.updated_at = _jetzt()
    db.commit()
    db.refresh(lauf)
    return lauf


# ─── Ausgabe für den Steuerberater ────────────────────────────────────────────

# Für den Steuerberater lesbar statt der internen Kennung – „prozent_abgelaufen"
# sagt ihm nichts, „% auf abgelaufene Chargen" schon.
ART_LABEL = {
    "prozent": "% auf Position",
    "prozent_abgelaufen": "% auf abgelaufene Chargen",
    "stueckwert": "neuer Stückwert",
    "betrag": "Abwertungsbetrag",
}

EXPORT_SPALTEN = [
    ("c_artnr", "Artikelnummer"),
    ("artikelname", "Artikel"),
    ("warengruppe", "Warengruppe"),
    ("hersteller", "Hersteller"),
    ("bestand", "Bestand"),
    ("ek", "EK netto"),
    ("wert", "Wert zum EK"),
    ("mhd_frueh", "MHD"),
    ("resttage", "Resttage"),
    ("menge_abgelaufen", "Menge abgelaufen"),
    ("abgang_12m", "Abgang 12 Monate"),
    ("reichweite_tage", "Reichweite Tage"),
    ("bewertung_art", "Bewertungsart"),
    ("bewertung_wert", "Bewertungswert"),
    ("abwertung_betrag", "Abwertung"),
    ("wert_neu", "Wert nach Abwertung"),
    ("grund", "Grund"),
]

# Excel-Formate je Spalte. Mengen bleiben „Standard": ein Format wie '#,##0' würde
# eine Bruchmenge (Meter, Liter) in der Anzeige stumm runden.
_EURO = '#,##0.00 "€"'
EXPORT_FORMATE = {
    "EK netto": '#,##0.00## "€"',
    "Wert zum EK": _EURO,
    "MHD": "DD.MM.YYYY",
    "Resttage": "#,##0",
    "Reichweite Tage": "#,##0",
    "Bewertungswert": "#,##0.00##",
    "Abwertung": _EURO,
    "Wert nach Abwertung": _EURO,
}
EXPORT_SUMMEN = ["Wert zum EK", "Abwertung", "Wert nach Abwertung"]


def export_zeilen(db, lauf: InventurLauf, datum_als_text: bool = True) -> List[dict]:
    """Flache Zeilen für CSV/XLSX – bewusst ohne Chargen-Detail, das würde die
    Liste für den Steuerberater vervielfachen. Die Partien stehen im Drilldown.

    `datum_als_text=False` lässt Datumswerte als Datum stehen – für Excel, damit
    die MHD-Spalte richtig sortiert und nach Zeitraum filterbar ist."""
    rows = (db.query(InventurPosition)
            .filter(InventurPosition.lauf_id == lauf.id)
            .order_by(InventurPosition.wert.desc()).all())
    out = []
    for p in rows:
        zeile = {}
        for feld, label in EXPORT_SPALTEN:
            v = getattr(p, feld, None)
            if isinstance(v, date) and datum_als_text:
                v = v.strftime("%d.%m.%Y")
            if feld == "bewertung_art" and v:
                v = ART_LABEL.get(v, v)
            # Unbewertete Positionen behalten ihren vollen Wert – sonst summiert
            # der Steuerberater eine Spalte mit Löchern.
            if feld == "wert_neu" and v is None:
                v = p.wert
            zeile[label] = v
        out.append(zeile)
    return out

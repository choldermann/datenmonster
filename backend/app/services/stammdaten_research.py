"""
Aus einer Herstellerseite Stammdaten ableiten – mit Sicherheitsgrad.

product_research.py holt die richtige Produktseite und liefert die Beschriftung/
Wert-Paare der technischen Daten. Hier wird daraus entschieden, was davon als
EAN, Warennummer (cTaric) oder Ursprungsland taugt — und vor allem, wie sicher
das ist. Der Sicherheitsgrad ist kein Bauchgefühl, sondern ergibt sich aus
nachprüfbaren Merkmalen; jede Abwertung nennt ihren Grund, damit am Bildschirm
nachvollziehbar bleibt, warum eine Zahl nur „vermutlich\" richtig ist.

  100      gesichert    – eindeutige Zuordnung, eindeutige Beschriftung, Wert formal gültig
  51–99    prüfen       – Wert gefunden, aber ein Merkmal ist unsicher
  bis 50   ungesichert  – Wert ist da, taugt aber nicht als Grundlage zum Schreiben

Die härtesten Abwertungen sind bewusst gesetzt:
  * Zuordnung über den Produktnamen statt über eine Nummer (Rhenus) — kein Beweis.
  * Mehrere EANs auf einer Seite: Hersteller geben Stück, Karton und Palette an;
    welche die Verkaufseinheit ist, weiß nur der Anwender.
  * „Herstellungsland\"/„Made in\" ist nicht dasselbe wie der zollrechtliche
    Ursprung — als Intrastat-Angabe deshalb nie gesichert.
"""
from __future__ import annotations

import logging
import re

from app.services.jtl_artikel_writer import (pruefe_ean, pruefe_gewicht, pruefe_iso2,
                                             pruefe_taric)
from app.services.product_research import hersteller_profil, recherchiere

logger = logging.getLogger(__name__)

# Gewicht ist mit dabei, weil es das dritte Intrastat-Pflichtfeld ist und auf den
# Herstellerseiten häufiger steht als EAN oder Warennummer (Denios z.B. nennt nur
# Maße und Gewicht).
FELDER = ("EAN", "Warennummer", "Herkunftsland", "Gewicht")

BASIS_NUMMER = 100      # Produktseite über die Hersteller-Artikelnummer gefunden
BASIS_NAME = 60         # … nur über den Produktnamen (Slug) – schwächer

# Beschriftungen auf den Herstellerseiten
_EAN_LABEL = re.compile(r"\b(ean|gtin|barcode|strichcode)\b", re.I)
_EAN_GEBINDE = re.compile(r"(karton|umkarton|vpe|verpackungseinheit|palette|gebinde|"
                          r"außen|aussen|outer|case)", re.I)
_TARIC_LABEL = re.compile(r"(zolltarif|warentarif|warennummer|tarifnummer|hs[\s-]?code|"
                          r"taric|customs\s*tariff|commodity\s*code)", re.I)
_HERKUNFT_STRENG = re.compile(r"(ursprungsland|herkunftsland|country\s+of\s+origin)", re.I)
_HERKUNFT_WEICH = re.compile(r"(herstellungsland|produktionsland|herstellerland|"
                             r"hergestellt\s+in|made\s+in)", re.I)
# Mehrere Länder in einem Feld („DE/CN“, „Deutschland oder Polen“)
_MEHRERE_LAENDER = re.compile(r"[/,;]|\bund\b|\boder\b", re.I)
_GEWICHT_LABEL = re.compile(r"\b(gewicht|eigenmasse|weight)\b", re.I)
_GEWICHT_GEBINDE = re.compile(r"(brutto|versand|karton|vpe|palette|gebinde|verpack)", re.I)
_EINHEIT_IM_LABEL = re.compile(r"\[\s*(kg|g)\s*\]", re.I)


def stufe(sicherheit: int) -> str:
    if sicherheit >= 100:
        return "gesichert"
    if sicherheit > 50:
        return "pruefen"
    return "ungesichert"


def _eintrag(feld: str, wert, roh, label: str, sicherheit: int,
             gruende: list[str]) -> dict:
    sicherheit = max(0, min(100, int(sicherheit)))
    return {
        "feld": feld,
        "wert": wert,
        "roh": str(roh),
        "label": label,
        "sicherheit": sicherheit,
        "stufe": stufe(sicherheit),
        "begruendung": gruende,
    }


# ── Felder aus den Beschriftung/Wert-Paaren lesen ───────────────────────────────

def _ean(daten: dict, basis: int, basis_grund: list[str]) -> list[dict]:
    roh_treffer: list[tuple[str, str]] = []      # (Beschriftung, Ziffernfolge)
    for label, wert in daten.items():
        if not _EAN_LABEL.search(label):
            continue
        for ziffern in re.findall(r"\d[\d\s.\-]{6,}\d", str(wert)):
            nur = re.sub(r"[^0-9]", "", ziffern)
            if len(nur) in (8, 12, 13, 14):
                roh_treffer.append((label, nur))

    eindeutig = {n for _, n in roh_treffer}
    ergebnis = []
    for label, nummer in roh_treffer:
        gruende = list(basis_grund)
        deckel = [basis]

        geprueft, fehler, _ = pruefe_ean(nummer)
        if fehler:
            deckel.append(20)
            gruende.append(fehler)
        # Beide Abstufungen bleiben im Bereich „prüfen": die Nummer ist echt und
        # eindeutig zugeordnet, offen ist nur, ob sie zur Verkaufseinheit dieses
        # Artikels gehört. Das kann nur der Anwender entscheiden.
        if len(eindeutig) > 1:
            deckel.append(60)
            gruende.append(f"{len(eindeutig)} verschiedene EANs auf der Seite – "
                           "Hersteller geben Stück, Karton und Palette getrennt an; "
                           "die Verkaufseinheit muss geprüft werden")
        if _EAN_GEBINDE.search(label):
            deckel.append(55)
            gruende.append(f"die Beschriftung „{label}“ nennt ein Gebinde – nur richtig, "
                           "wenn du in dieser Einheit verkaufst")
        elif len(nummer) == 14:
            deckel.append(50)
            gruende.append("14-stellig (GTIN-14) – das ist üblicherweise der Umkarton")
        ergebnis.append(_eintrag("EAN", geprueft or nummer, nummer, label,
                                 min(deckel), gruende))
    return ergebnis


def _warennummer(daten: dict, basis: int, basis_grund: list[str]) -> list[dict]:
    treffer: list[tuple[str, str]] = []
    for label, wert in daten.items():
        if not _TARIC_LABEL.search(label):
            continue
        nur = re.sub(r"[^0-9]", "", str(wert))
        if len(nur) >= 4:
            treffer.append((label, nur))

    eindeutig = {n for _, n in treffer}
    ergebnis = []
    for label, nummer in treffer:
        gruende = list(basis_grund)
        deckel = [basis]
        wert = nummer

        if len(nummer) == 8:
            pass                                  # genau das, was Intrastat braucht
        elif 9 <= len(nummer) <= 11:
            wert = nummer[:8]
            deckel.append(70)
            gruende.append(f"{len(nummer)}-stellige Taric-Nummer – für die Warennummer "
                           f"zählen die ersten 8 Stellen ({wert}); die Kürzung ist zu prüfen")
        elif len(nummer) == 6:
            deckel.append(35)
            gruende.append("nur die 6-stellige HS-Position – die beiden Stellen der "
                           "Kombinierten Nomenklatur fehlen")
        else:
            deckel.append(25)
            gruende.append(f"{len(nummer)} Stellen – keine gültige Warennummer")

        if len(eindeutig) > 1:
            deckel.append(40)
            gruende.append("die Seite nennt mehrere Warennummern")

        _, fehler, _ = pruefe_taric(wert)
        if fehler and not any(fehler in g for g in gruende):
            gruende.append(fehler)
        ergebnis.append(_eintrag("Warennummer", wert, nummer, label,
                                 min(deckel), gruende))
    return ergebnis


def _herkunftsland(daten: dict, basis: int, basis_grund: list[str]) -> list[dict]:
    ergebnis = []
    for label, wert in daten.items():
        streng = bool(_HERKUNFT_STRENG.search(label))
        if not streng and not _HERKUNFT_WEICH.search(label):
            continue
        roh = str(wert).strip()
        gruende = list(basis_grund)
        deckel = [basis]

        if not streng:
            deckel.append(60)
            gruende.append(f"„{label}“ ist nicht zwingend der zollrechtliche Ursprung – "
                           "für die Intrastat-Meldung zählt das Ursprungsland")
        if _MEHRERE_LAENDER.search(roh):
            deckel.append(30)
            gruende.append(f"„{roh}“ nennt mehr als ein Land")

        code, fehler, hinweis = pruefe_iso2(roh)
        if fehler:
            deckel.append(25)
            gruende.append(fehler)
        elif hinweis:
            gruende.append(hinweis)
        ergebnis.append(_eintrag("Herkunftsland", code or roh, roh, label,
                                 min(deckel), gruende))
    return ergebnis


def _gewicht(daten: dict, basis: int, basis_grund: list[str]) -> list[dict]:
    ergebnis = []
    for label, wert in daten.items():
        if not _GEWICHT_LABEL.search(label):
            continue
        roh = str(wert).strip()
        # Denios schreibt die Einheit in die Beschriftung („Gewicht [kg]“), der
        # Wert selbst ist dann eine nackte Zahl.
        einheit = _EINHEIT_IM_LABEL.search(label)
        pruefwert = f"{roh} {einheit.group(1)}" if einheit and roh[-1:].isdigit() else roh

        gruende = list(basis_grund)
        # Nie gesichert: der Hersteller wiegt sein Produkt, nicht deine
        # Verkaufseinheit – bei Gebinden weichen die Angaben regelmäßig ab.
        deckel = [basis, 70]
        gruende.append("Herstellerangabe – prüfen, ob sie sich auf deine "
                       "Verkaufseinheit bezieht (Intrastat meldet die Eigenmasse)")
        if _GEWICHT_GEBINDE.search(label):
            deckel.append(50)
            gruende.append(f"„{label}“ nennt ein Gebinde- oder Bruttogewicht")

        kg, fehler, hinweis = pruefe_gewicht(pruefwert)
        if fehler:
            deckel.append(25)
            gruende.append(fehler)
        elif hinweis:
            gruende.append(hinweis)
        ergebnis.append(_eintrag("Gewicht", kg if kg is not None else roh, roh, label,
                                 min(deckel), gruende))
    return ergebnis


# ── Einstieg ────────────────────────────────────────────────────────────────────

def pruefe_artikel(hersteller: str, han: str,
                   felder: tuple[str, ...] = FELDER) -> dict | None:
    """Eine Produktseite abrufen und die gesuchten Felder daraus ableiten.

    Gibt None zurück, wenn es zu diesem Artikel keine auswertbare Seite gibt —
    der Aufrufer zählt das als „nichts gefunden“ und macht weiter.
    """
    profil = hersteller_profil(hersteller or "")
    if not profil:
        return None
    res = recherchiere(hersteller, han)
    if not res:
        return None

    per_name = profil.get("zuordnung") == "name"
    basis = BASIS_NAME if per_name else BASIS_NUMMER
    basis_grund = ([f"Zuordnung über den Produktnamen, nicht über eine eindeutige "
                    f"Nummer – die Seite kann ein ähnliches Produkt sein"]
                   if per_name else [])

    daten = res.get("daten") or {}
    vorschlaege: list[dict] = []
    if "EAN" in felder:
        vorschlaege += _ean(daten, basis, basis_grund)
    if "Warennummer" in felder:
        vorschlaege += _warennummer(daten, basis, basis_grund)
    if "Herkunftsland" in felder:
        vorschlaege += _herkunftsland(daten, basis, basis_grund)
    if "Gewicht" in felder:
        vorschlaege += _gewicht(daten, basis, basis_grund)

    # Bester Wert je Feld zuerst – die Oberfläche zeigt ihn oben an.
    vorschlaege.sort(key=lambda v: (v["feld"], -v["sicherheit"]))
    return {
        "hersteller": res.get("hersteller"),
        "quelle": res.get("url"),
        "vorschlaege": vorschlaege,
        "gelesene_felder": len(daten),
    }

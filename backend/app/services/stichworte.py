"""
Stichwörter aus Freitext ziehen — gemeinsame Grundlage der deterministischen
Suchen (API-Doku-Assistent, AI-Memory-Auswahl).

Bewusst ohne Modell: die Auswahl bleibt nachvollziehbar, ist reproduzierbar und
funktioniert auch, wenn gar keine KI erreichbar ist.
"""

import re

# Wörter, die in fast jeder Frage und fast jedem Beschreibungstext vorkommen.
# Ohne diese Liste gewinnt das Rauschen: „Wie funktioniert die Bierbestellung?"
# fand über „funktioniert" zwölf beliebige Endpunkte und meldete Erfolg.
# Englische Fachwörter (get, list, all, …) stehen bewusst NICHT hier – die
# tragen in einer API-Beschreibung Bedeutung.
FUELLWOERTER = {
    "wie", "was", "wer", "wem", "wen", "wo", "warum", "wieso", "welche", "welcher",
    "welches", "kann", "kannst", "könnte", "muss", "soll", "will", "möchte",
    "ich", "man", "mir", "mich", "sich", "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "einer", "eines", "und", "oder", "aber",
    "für", "mit", "von", "vom", "zum", "zur", "aus", "bei", "auf", "über", "unter",
    "ist", "sind", "war", "wird", "werden", "wurde", "haben", "habe", "hat",
    "gibt", "geht", "macht", "machen", "mache", "funktioniert", "bekomme",
    "bekommen", "lege", "legt", "legen", "alle", "alles", "mehr", "auch", "noch",
    "nur", "dann", "damit", "dass", "nicht", "kein", "keine", "etwas", "bitte",
    "brauche", "benötige", "möglich", "richtig", "sowie", "beim", "einfach",
}


def stichworte(text: str, zusatz_fuellwoerter: set[str] | None = None) -> list[str]:
    """
    Freitext in gewichtbare Stichwörter zerlegen: kleinschreiben, an allem
    zerteilen, was kein Wortzeichen ist, Füllwörter und Kurzwörter raus.

    Die Reihenfolge bleibt erhalten (erste Nennung gewinnt), Dubletten fallen
    weg — sonst zählt ein doppelt genanntes Wort doppelt in die Bewertung.
    """
    fuell = FUELLWOERTER | (zusatz_fuellwoerter or set())
    gesehen: set[str] = set()
    ergebnis: list[str] = []
    for w in re.split(r"[^\wäöüß]+", (text or "").lower()):
        if len(w) > 2 and w not in fuell and w not in gesehen:
            gesehen.add(w)
            ergebnis.append(w)
    return ergebnis

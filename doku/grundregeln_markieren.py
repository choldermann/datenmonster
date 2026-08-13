# -*- coding: utf-8 -*-
"""
Markiert die Grundregeln der Wissensdatenbank (`always_include`).

Hintergrund: Seit die KI nur noch das zur Frage passende Wissen bekommt, braucht
es eine kleine Menge Regeln, die IMMER mitgehen — die, ohne die eine Antwort
schlicht falsch wird (Umsatz netto, cFirma ist die eigene Firma, gesperrte
Kunden raus …). Alles andere kommt über die Stichwortsuche.

Die ältesten zehn Regeln stammen nicht aus jtl_wissen_seed.py, sondern wurden
direkt in der DB angelegt; deshalb wird hier über Titel-Muster gesucht statt
über exakte Titel.

Lauf (Trockenlauf ist Standard):
    docker exec -i datenmonster-backend python3 - < doku/grundregeln_markieren.py
    docker exec -i datenmonster-backend python3 - --apply < doku/grundregeln_markieren.py

Über den Container per stdin ausführen, NICHT per `docker cp` hineinkopieren:
/app ist ein Bind-Mount auf ./backend, kopierte Skripte landen sonst im Repo.
"""
import sys
sys.path.insert(0, "/app")
from app.core.database import SessionLocal
from app.models.ai_memory import AiMemoryKnowledge as K

# Titel-Muster (Kleinschreibung, „oder"-Verknüpft je Zeile) der Regeln, die in
# jeden Kontext gehören. Sparsam halten: jede kostet Rechenzeit bei JEDER
# Anfrage — das ist genau der Aufwand, den die Relevanzauswahl einspart.
MUSTER = [
    ("umsatz",        "Umsatzbasis (netto, Rechnungen)"),
    ("cfirma",        "vRechnung.cFirma ist die EIGENE Firma"),
    ("gesperr",       "gesperrte Kunden / inaktive Artikel"),
    ("csperre",       "gesperrte Kunden / inaktive Artikel"),
    ("artikelname",   "Artikelname steht in tArtikelBeschreibung"),
    ("zentrale join", "die zentralen Joins"),
]

apply = "--apply" in sys.argv
db = SessionLocal()

rows = db.query(K).filter(K.scope == "global").order_by(K.id).all()
treffer, gesetzt = [], 0
for r in rows:
    titel = (r.title or "").lower()
    for muster, warum in MUSTER:
        if muster in titel:
            treffer.append((r, warum))
            break

print(f"{len(rows)} globale Einträge, {len(treffer)} als Grundregel erkannt:\n")
for r, warum in treffer:
    status = "bereits gesetzt" if r.always_include else ("wird gesetzt" if apply else "WÜRDE gesetzt")
    print(f"  [{status}] {r.title}   ({warum})")
    if apply and not r.always_include:
        r.always_include = True
        gesetzt += 1

bereits = sum(1 for r in rows if r.always_include and r not in [t[0] for t in treffer])
if bereits:
    print(f"\nHinweis: {bereits} weitere Einträge sind bereits als Grundregel markiert "
          f"(z. B. in der Oberfläche) — die bleiben unangetastet.")

if apply:
    db.commit()
    print(f"\n{gesetzt} Einträge neu markiert.")
else:
    print("\nTrockenlauf — mit --apply schreiben.")

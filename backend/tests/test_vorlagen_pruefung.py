"""
Prueft die Teile der naechtlichen Vorlagen-Pruefung, die ohne Datenbank auskommen:
Platzhalter im Vorlagen-SQL, Fingerabdruck ("dasselbe wie gestern?") und den Bericht.

Der Fingerabdruck entscheidet, ob eine Mail rausgeht. Haengt er an der Reihenfolge
oder an der Laufzeit, kommt jede Nacht dieselbe Mail - und wird nach drei Tagen
nicht mehr gelesen.

Lauf:  docker compose exec -T backend python tests/test_vorlagen_pruefung.py
"""
import sys
sys.path.insert(0, "/app")

from app.services import vorlagen_pruefung as VP  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


print("\n── SQL aus der Vorlage ──")

vorlage = {"mappings": [
    {"name": "Mit Platzhalter", "sql_nodes": [
        {"sql": "SELECT 1 WHERE x < {{beschreibung_min_zeichen}} AND d > DATEADD(DAY, -{{tage}}, GETDATE())"}]},
    {"name": "Leerer Knoten", "sql_nodes": [{"sql": "   "}]},
    {"name": "Ohne Knoten"},
    "kaputt",
]}
knoten = list(VP._sql_knoten(vorlage))
pruefe("leere und fehlende Knoten fallen raus", len(knoten) == 1, str(knoten))
pruefe("Platzhalter werden zu 0", "{{" not in knoten[0][1] and "< 0 " in knoten[0][1], knoten[0][1])
pruefe("Mapping-Name kommt mit", knoten[0][0] == "Mit Platzhalter")

print("\n── Fingerabdruck ──")

a = [{"template_id": "t1", "jtl": "2.0.5.0", "mapping": "M1", "art": "spalte", "name": "fX"},
     {"template_id": "t2", "jtl": "1.8.10.0", "mapping": "M2", "art": "objekt", "name": "dbo.v"}]
b = list(reversed(a))
pruefe("Reihenfolge aendert nichts", VP._fingerabdruck(a) == VP._fingerabdruck(b))
pruefe("anderer Befund faellt auf",
       VP._fingerabdruck(a) != VP._fingerabdruck(a[:1]))
pruefe("keine Befunde ist ein eigener Stand",
       VP._fingerabdruck([]) != VP._fingerabdruck(a) and VP._fingerabdruck([]) == VP._fingerabdruck(None))

print("\n── Bericht ──")

refs = [{"version": "1.8.10.0", "kurz": "1.8", "connection_id": 5, "name": "HyDa"},
        {"version": "2.0.5.0", "kurz": "2.0", "connection_id": 7, "name": "HaKo"}]
gruen = VP.bericht({"befunde": [], "referenzen": refs, "vorlagen": 12, "dauer_s": 30.0})
pruefe("gruene Mail nennt die Zahl der Vorlagen", "12" in gruen["subject"], gruen["subject"])
pruefe("gruene Mail nennt die geprueften Staende", "1.8.10.0" in gruen["text"] and "HaKo" in gruen["text"])
pruefe("gruene Mail zaehlt null Befunde", gruen["anzahl"] == 0)

rot = VP.bericht({"befunde": [
    {"vorlage": "Preis-Cockpit", "template_id": "jtl_preis_cockpit", "version": "1.2",
     "jtl": "2.0.5.0", "datenbank": "HaKo", "mapping": "Rabatt-KPI", "art": "spalte",
     "name": "fWertNettoGesamtFixiert"},
    {"vorlage": "Lager-Cockpit", "template_id": "jtl_lager_cockpit", "version": "1.7",
     "jtl": "1.8.10.0", "datenbank": "HyDa", "mapping": "Kennzahlen", "art": "objekt",
     "name": "dbo.vArtikelHistorie"},
], "referenzen": refs, "vorlagen": 12, "dauer_s": 55.0})
pruefe("Betreff nennt beide JTL-Staende",
       "1.8.10.0" in rot["subject"] and "2.0.5.0" in rot["subject"], rot["subject"])
pruefe("Betreff zaehlt betroffene Vorlagen, nicht Befunde", "2 Vorlagen" in rot["subject"], rot["subject"])
pruefe("Text nennt Mapping und Feld",
       "Rabatt-KPI" in rot["text"] and "fWertNettoGesamtFixiert" in rot["text"])
pruefe("Spalte heisst Feld, Objekt heisst Objekt",
       'Feld "fWertNettoGesamtFixiert"' in rot["text"] and 'Objekt "dbo.vArtikelHistorie"' in rot["text"])
pruefe("HTML enthaelt beide Vorlagen",
       "Preis-Cockpit" in rot["html"] and "Lager-Cockpit" in rot["html"])

print()
if FEHLER:
    print(f"{len(FEHLER)} Pruefung(en) fehlgeschlagen: {', '.join(FEHLER)}")
    sys.exit(1)
print("Alle Pruefungen bestanden.")

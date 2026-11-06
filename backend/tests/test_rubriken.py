"""
Ein Cockpit mit Rubriken, Phase 0 (06.11.2026): Rubrik-Ermittlung und Menü.

Reine Logik-Tests auf Platzhalter-Formularen (keine DB-Objekte, nichts aufzuräumen),
dazu die Portal-Freigabe des neuen Endpunkts.

Lauf:  docker compose exec -T backend python tests/test_rubriken.py
"""
import sys
from types import SimpleNamespace
sys.path.insert(0, "/app")

from app.services import rubriken as rb  # noqa: E402
from app.core.portal_zugriff import portal_darf  # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if extra and not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


def form(fid, name, widgets=("kpi",), tabs=2, **schema):
    s = {"widgets": [{"id": f"w{i}", "type": t} for i, t in enumerate(widgets)],
         "result_tabs": [{"id": f"t{i}", "label": f"T{i}"} for i in range(tabs)], **schema}
    return SimpleNamespace(id=fid, name=name, schema=s)


def eintrag(f, gesperrt=None, bericht=False):
    return {"id": f.id, "name": f.name, "projekt": "P", "zusatz": None,
            "art": "bericht" if bericht else "cockpit", "gesperrt": gesperrt}


def menue(formulare, vorlagen=None, gesperrt=(), berichte=()):
    vorlagen = vorlagen or {}
    ein = {f.id: eintrag(f, bericht=f.id in berichte) for f in formulare}
    return rb.menue(formulare, ein, lambda fid: vorlagen.get(fid), lambda fid: fid in gesperrt)


def rubrik(m, rid):
    for g in m:
        for r in g["rubriken"]:
            if r["id"] == rid:
                return g["id"], r
    return None, None


print("1. Woher die Rubrik kommt")
gf = form(1, "Geschäftsführer-Cockpit")
eigen = form(2, "Mein Cockpit", rubrik={"id": "vertrieb"})
neu = form(3, "Finanzen Lexware", rubrik={"id": "finanzen", "name": "Finanzen", "gruppe": "cockpit", "reihenfolge": 15})
lager_alt = form(4, "Lager-Cockpit")              # Altbestand: nicht im Vorlagen-Index
kosten = form(5, "Kostenstruktur", widgets=("kostenstruktur",), tabs=0)
frei = form(6, "DHL-Rücksendungen")
m = menue([gf, eigen, neu, lager_alt, kosten, frei], vorlagen={1: "jtl_gf_cockpit", 5: "jtl_gf_cockpit"})
g, r = rubrik(m, "gf")
pruefe("Vorlage → gf, Gruppe cockpit", g == "cockpit" and r["haupt"]["id"] == 1)
g, r = rubrik(m, "vertrieb")
pruefe("schema.rubrik als Text-ID mit Vorgaben", r and r["name"] == "Vertrieb" and r["haupt"]["id"] == 2)
g, r = rubrik(m, "finanzen")
pruefe("eigene Rubrik einer Vorlage", r and r["name"] == "Finanzen" and g == "cockpit")
g, r = rubrik(m, "lager")
pruefe("Altbestand über Formularnamen", r and r["haupt"]["id"] == 4)
g, r = rubrik(m, "gf")
pruefe("Kostenstruktur = Pflege-Eintrag unter GF", [(e["id"], e["art"]) for e in r["eintraege"]] == [(5, "pflege")])
g, r = rubrik(m, "f6")
pruefe("Eigenbau ohne Rubrik → Weitere", g == "weitere" and r["name"] == "DHL-Rücksendungen")
reihen = [x["id"] for x in m[0]["rubriken"]]
pruefe("Reihenfolge: gf vor finanzen vor vertrieb", reihen.index("gf") < reihen.index("finanzen") < reihen.index("vertrieb"), reihen)
pruefe("Gruppen in fester Folge", [x["id"] for x in m] == ["cockpit", "weitere"])

print("2. Pflegemaske verschwindet, wenn das Cockpit sie als Reiter hat")
gf2 = form(1, "Geschäftsführer-Cockpit", widgets=("kpi", "kostenstruktur"))
_, r = rubrik(menue([gf2, kosten], vorlagen={1: "jtl_gf_cockpit"}), "gf")
pruefe("keine Pflege-Einträge mehr", r["eintraege"] == [])

print("3. Kopien und Berichte")
kopie = form(7, "Vertrieb Außendienst", kopie_von={"form_id": 8, "name": "Vertriebs-Cockpit"})
vertrieb = form(8, "Vertriebs-Cockpit")
bericht = form(9, "Monatsbericht", report_builder={"entries": [
    {"form_id": 1}, {"form_id": 1}, {"form_id": 8}]})
m = menue([gf, kopie, vertrieb, bericht], vorlagen={1: "jtl_gf_cockpit", 8: "jtl_vertrieb_cockpit"}, berichte={9})
_, r = rubrik(m, "vertrieb")
pruefe("Kopie erbt Rubrik, Original bleibt Haupteintrag",
       r["haupt"]["id"] == 8 and [(e["id"], e["art"]) for e in r["eintraege"]] == [(7, "kopie")])
_, r = rubrik(m, "gf")
pruefe("Bericht → Rubrik mit den meisten Bausteinen", [(e["id"], e["art"]) for e in r["eintraege"]] == [(9, "bericht")])
kopie_eigen = form(10, "Kopie woanders", kopie_von={"form_id": 8}, rubrik={"id": "lager"})
_, r = rubrik(menue([vertrieb, kopie_eigen], vorlagen={8: "jtl_vertrieb_cockpit"}), "lager")
pruefe("eigene Angabe schlägt Vererbung", r and r["haupt"]["id"] == 10)
kreis_a = form(11, "A", kopie_von={"form_id": 12})
kreis_b = form(12, "B", kopie_von={"form_id": 11})
m = menue([kreis_a, kreis_b])
pruefe("Kopie-Kreis läuft nicht endlos", sum(len(g["rubriken"]) for g in m) == 2)

print("4. Freischaltung")
m = menue([gf, vertrieb, kopie], vorlagen={1: "jtl_gf_cockpit", 8: "jtl_vertrieb_cockpit"}, gesperrt={8})
pruefe("gesperrte Vorlage fehlt ganz, auch ihre Kopie", rubrik(m, "vertrieb") == (None, None), m)
pruefe("anderes bleibt sichtbar", rubrik(m, "gf")[1] is not None)
_, r = rubrik(menue([kopie], vorlagen={}), "f7")
pruefe("Kopie ohne sichtbares Original wird Haupteintrag", r and r["haupt"]["id"] == 7)

print("5. Zwei Projekte mit demselben Cockpit")
gf_b = form(13, "Geschäftsführer-Cockpit")
_, r = rubrik(menue([gf, gf_b], vorlagen={1: "jtl_gf_cockpit", 13: "jtl_gf_cockpit"}), "gf")
pruefe("erstes = Haupt, zweites = Eintrag 'cockpit'",
       r["haupt"]["id"] == 1 and [(e["id"], e["art"]) for e in r["eintraege"]] == [(13, "cockpit")])

print("6. Portal-Freigabe")
pruefe("GET /api/start/rubriken erlaubt", portal_darf("GET", "/api/start/rubriken"))
pruefe("POST /api/start/rubriken gesperrt", not portal_darf("POST", "/api/start/rubriken"))

print()
print("FEHLER: " + ", ".join(FEHLER) if FEHLER else "Alle Prüfungen bestanden.")
sys.exit(1 if FEHLER else 0)

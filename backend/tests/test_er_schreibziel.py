"""
Prueft, in WELCHE Wawi der Eingangsrechnungs-Import schreibt.

Bis 2026-09-22 folgte er stur der Verbindung aus der Widget-Konfiguration,
waehrend das Formular davor laengst dem Mandanten-Umschalter folgte. Oben stand
"HaKo", die Rechnung landete in der Testumgebung - lautlos, denn beides sieht
gleich aus. DATEV und die Stammdaten lenkten schon um, dieser Pfad nicht.

Geprueft wird die Aufloesung selbst, ohne Wawi: welche connection_id kommt aus
`verbindung_aufloesen` heraus.

Lauf:  docker compose exec -T backend python tests/test_er_schreibziel.py
"""
import sys
sys.path.insert(0, "/app")

import sqlalchemy as sa                                   # noqa: E402
from sqlalchemy.orm import sessionmaker                   # noqa: E402

from app.models.dataset import DbConnection, ProjektVerbindung  # noqa: E402
from app.models.mandant import MandantAuswahl             # noqa: E402
from app.models.user import User                          # noqa: E402
from app.services import mandant_service                  # noqa: E402
import app.api.eingangsrechnung as ER                     # noqa: E402

FEHLER = []


def pruefe(name, bedingung, extra=""):
    print(("  OK   " if bedingung else "  FAIL ") + name + (f"  [{extra}]" if not bedingung else ""))
    if not bedingung:
        FEHLER.append(name)


ENGINE = sa.create_engine("sqlite://")
for modell in (DbConnection, ProjektVerbindung, MandantAuswahl, User):
    modell.__table__.create(ENGINE, checkfirst=True)
db = sessionmaker(bind=ENGINE)()


def verbindung(id, project_id, name, is_mandant=False):
    db.add(DbConnection(id=id, name=name, db_type="mssql", host="h", port=1433,
                        database="eazybusiness", username="u", password="p",
                        project_id=project_id, is_mandant=is_mandant))


verbindung(6, 6, "Testumgebung", is_mandant=True)      # steht im Widget
verbindung(3, 6, "PPS", is_mandant=True)               # zweiter Mandant
verbindung(99, 9, "Fremdes Projekt", is_mandant=True)  # gehoert woanders hin
admin = User(id=1, username="admin", hashed_password="x", is_admin=True)
db.add(admin)
db.commit()

# Die Freigabepruefung haengt an Formularen und Portalrechten - hier nicht das Thema.
ER._check_connection_access = lambda *a, **k: None


def ziel(widget_verbindung, umschalter):
    if umschalter is not None:
        mandant_service.waehlen(6, admin, umschalter, db)
    return ER.verbindung_aufloesen(widget_verbindung, admin, db)


print("\n── Schreibziel ──")
pruefe("Umschalter auf der Widget-Verbindung: bleibt dort", ziel(6, 6) == 6, ziel(6, 6))
pruefe("Umschalter auf dem zweiten Mandanten: Import folgt", ziel(6, 3) == 3, ziel(6, 3))
pruefe("zurueck geschaltet: wieder die Vorgabe", ziel(6, 6) == 6, ziel(6, 6))

# Eine Verbindung aus einem fremden Projekt ist nicht austauschbar - der
# Umschalter eines anderen Projekts darf sie nicht umbiegen.
pruefe("fremde Verbindung bleibt unangetastet", ziel(99, 3) == 99, ziel(99, 3))

print("\n── Antwort an die Oberflaeche ──")
mandant_service.waehlen(6, admin, 3, db)
info = ER._verbindungsinfo(6, ER.verbindung_aufloesen(6, admin, db), db)
pruefe("meldet die Umlenkung", info["umgelenkt"] is True, info)
pruefe("nennt den Namen der Ziel-Wawi", info["name"] == "PPS", info)
mandant_service.waehlen(6, admin, 6, db)
info = ER._verbindungsinfo(6, ER.verbindung_aufloesen(6, admin, db), db)
pruefe("ohne Umlenkung keine Meldung", info["umgelenkt"] is False, info)

print()
if FEHLER:
    print(f"{len(FEHLER)} Pruefung(en) fehlgeschlagen: {', '.join(FEHLER)}")
    sys.exit(1)
print("Alle Pruefungen bestanden.")

"""
Mengenbegrenzungen der kostenlosen Stufe.

Der Grundgedanke: **Objekte aus gekauften Vorlagen zaehlen nicht mit.** Das
GF-Cockpit bringt rund 50 Mappings mit — ein naiver Zaehler waere nach der ersten
Installation voll und die gekaufte Vorlage damit unbrauchbar. Gezaehlt wird nur,
was jemand selbst angelegt hat.

Woher wir wissen, was aus einer Vorlage stammt: der Installer schreibt die dabei
erzeugten IDs nach `Template.installations` (siehe app/models/template.py). Die
Vereinigung ueber alle Installationen ist die Menge der Vorlagen-Objekte.

Grenzen gelten nur ohne das jeweilige Recht; mit Pro faellt alles weg.
"""
from typing import Set
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.lizenz_gate import hat_recht, meldung

# Kostenlose Stufe: genug zum Ausprobieren, zu wenig zum Arbeiten.
GRENZEN = {
    "mappings":    3,
    "datasets":    3,
    "projekte":    1,
    "verbindungen": 1,   # ein Mandant
    "benutzer":    1,    # ein Administrator; Portal-Zugaenge sind unbegrenzt
}

# Welches Recht hebt welche Grenze auf
RECHT_FUER = {
    "mappings":     "unlimited",
    "datasets":     "unlimited",
    "projekte":     "unlimited",
    "verbindungen": "multi_tenant",
    "benutzer":     "multi_user",
}

_BEZEICHNUNG = {
    "mappings":     ("Mapping", "Mappings"),
    "datasets":     ("Dataset", "Datasets"),
    "projekte":     ("Projekt", "Projekte"),
    "verbindungen": ("Verbindung", "Verbindungen"),
    "benutzer":     ("Administrator", "Administratoren"),
}


def vorlagen_objekte(db: Session, art: str) -> Set[int]:
    """IDs, die beim Installieren von Vorlagen entstanden sind (art z.B. 'mappings')."""
    from app.models.template import Template
    ids: Set[int] = set()
    for (installationen,) in db.query(Template.installations).all():
        for inst in (installationen or []):
            for oid in ((inst.get("objects") or {}).get(art) or []):
                if isinstance(oid, int):
                    ids.add(oid)
    return ids


def eigenbau_anzahl(db: Session, art: str) -> int:
    """Wie viele Objekte dieser Art hat der Anwender selbst angelegt?"""
    from app.models.dataset import Dataset, DbConnection
    from app.models.mapping import Mapping
    from app.models.project import Project
    from app.models.user import User

    if art == "mappings":
        alle = {m.id for m in db.query(Mapping.id).all()}
        return len(alle - vorlagen_objekte(db, "mappings"))
    if art == "datasets":
        alle = {d.id for d in db.query(Dataset.id).all()}
        return len(alle - vorlagen_objekte(db, "datasets"))
    if art == "projekte":
        return db.query(Project).count()
    if art == "verbindungen":
        return db.query(DbConnection).count()
    if art == "benutzer":
        # Portal-Zugaenge sind kostenlos und zaehlen nicht mit — sonst koennte ein
        # gekauftes Cockpit nicht an die Geschaeftsfuehrung weitergereicht werden.
        # Deaktivierte zaehlen nicht: wer einen Benutzer abschaltet, gibt den Platz frei.
        return (db.query(User)
                .filter(User.is_portal_only == False)  # noqa: E712
                .filter((User.is_active == True) | (User.is_active == None))  # noqa: E711,E712
                .count())
    return 0


def pruefe(db: Session, art: str) -> None:
    """Vor dem Anlegen aufrufen. Wirft 402, wenn die Grenze erreicht ist."""
    recht = RECHT_FUER.get(art)
    if not recht or hat_recht(db, recht):
        return
    grenze = GRENZEN.get(art)
    if grenze is None:
        return
    anzahl = eigenbau_anzahl(db, art)
    if anzahl < grenze:
        return

    einzahl, mehrzahl = _BEZEICHNUNG.get(art, (art, art))
    zusatz = ""
    if art in ("mappings", "datasets"):
        zusatz = (" Objekte aus installierten Vorlagen zählen nicht mit — "
                  "betroffen sind nur selbst angelegte.")
    raise HTTPException(402, detail=(
        f"In der kostenlosen Version {'ist' if grenze == 1 else 'sind'} "
        f"{grenze} {einzahl if grenze == 1 else mehrzahl} möglich, "
        f"und so viele gibt es bereits.{zusatz} "
        f"Mehr davon gehört zur Pro-Version — freischalten unter monstersuite.de."
    ))


def pruefe_db_ziel(db: Session, mapping_id, ziele: list, ziel_typ: str | None) -> None:
    """Ein Mapping, das in eine Datenbank schreibt, braucht ohne Pro einen
    Vorlagen-Ursprung. Sonst waere `db_write_template` ein Schlupfloch: man baut
    sich das Schreib-Mapping einfach selbst."""
    if hat_recht(db, "db_write"):
        return
    schreibt = (ziel_typ == "db") or any((z or {}).get("target_type") == "db" for z in (ziele or []))
    if not schreibt:
        return
    if mapping_id and int(mapping_id) in vorlagen_objekte(db, "mappings"):
        return          # gehoert zu einer gekauften Vorlage — die darf das
    raise HTTPException(402, detail=meldung("db_write"))

"""Gegen welche Datenbank die Werkbank baut – und warum.

**Warum das nicht einfach `mandant_service.aktiver()` sein kann:** Mandant ist
ein *Etikett* an einer Verbindung (`is_mandant`), gedacht für Projekte, die
mehrere Betriebe nebeneinander auswerten. Ein Projekt kann aber eine ganz
normale Datenbankverbindung haben, ohne dass jemand dieses Etikett gesetzt hat –
dann liefert `aktiver()` `None`, und die Werkbank verweigerte den Dienst mit
„Kein Mandant gewählt", obwohl die Verbindung direkt daneben liegt. Genau das ist
in Projekt „Test" passiert.

Die Werkbank braucht keinen Mandanten, sie braucht **eine Datenbank**. Diese
Auflösung geht deshalb in Stufen und sagt in `quelle` immer, woher die Wahl
stammt – der Anwender soll ohne Klick wissen, worauf er gerade blickt.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def auswahl(db, project_id: Optional[int]) -> list:
    """Alle Datenbankverbindungen des Projekts – für die Anzeige und die Wahl."""
    from app.models.dataset import DbConnection

    q = db.query(DbConnection)
    if project_id is not None:
        q = q.filter(DbConnection.project_id == project_id)
    return [{"connection_id": c.id,
             "name": getattr(c, "mandant_label", None) or c.name or f"Verbindung {c.id}",
             "ist_mandant": bool(getattr(c, "is_mandant", False))}
            for c in q.order_by(DbConnection.id).all()]


def aufloesen(db, project_id: Optional[int], user,
              gewuenscht: Optional[int] = None) -> dict:
    """Ermittelt die Verbindung, gegen die gebaut und gerechnet wird.

    Gibt `connection_id` (kann None sein), `name`, `quelle` und `auswahl` zurück.
    `quelle`:
      gewaehlt            – ausdrücklich mitgegeben
      mandant             – über die Mandantenwahl des Benutzers
      einzige_verbindung  – das Projekt hat genau eine, also kann es nur die sein
      mehrdeutig          – mehrere Verbindungen, keine als Mandant markiert
      keine               – das Projekt hat gar keine Datenbankverbindung
    """
    from app.services import mandant_service

    alle = auswahl(db, project_id)

    if gewuenscht is not None:
        if not mandant_service.darf_nutzen(gewuenscht, user, db, project_id):
            return {"connection_id": None, "name": None, "quelle": "gesperrt",
                    "auswahl": alle,
                    "hinweis": "Diese Verbindung ist für dich nicht freigegeben."}
        return {"connection_id": gewuenscht,
                "name": mandant_service.name_von(gewuenscht, db),
                "quelle": "gewaehlt", "auswahl": alle, "hinweis": None}

    aktiv = mandant_service.aktiver(project_id, user, db)
    if aktiv:
        return {"connection_id": aktiv, "name": mandant_service.name_von(aktiv, db),
                "quelle": "mandant", "auswahl": alle, "hinweis": None}

    if len(alle) == 1:
        # Kein Mandanten-Etikett, aber nur eine Verbindung: dann ist die Frage
        # „gegen welche Datenbank" beantwortet, und ein Fehler wäre reine Schikane.
        return {"connection_id": alle[0]["connection_id"], "name": alle[0]["name"],
                "quelle": "einzige_verbindung", "auswahl": alle,
                "hinweis": f"Das Projekt hat genau eine Datenbankverbindung "
                           f"(„{alle[0]['name']}“) – gegen die wird gebaut."}

    if len(alle) > 1:
        return {"connection_id": None, "name": None, "quelle": "mehrdeutig",
                "auswahl": alle,
                "hinweis": "Das Projekt hat mehrere Datenbankverbindungen, aber "
                           "keine ist als Betrieb markiert. Wähle oben aus, gegen "
                           "welche gebaut werden soll — oder markiere sie unter "
                           "DB-Connectors als Mandant, dann merkt sich Datenmonster "
                           "die Wahl."}

    return {"connection_id": None, "name": None, "quelle": "keine", "auswahl": [],
            "hinweis": "Dieses Projekt hat keine Datenbankverbindung. Lege sie "
                       "unter „DB-Connectors“ an, dann kann die Werkbank bauen."}

# -*- coding: utf-8 -*-
"""Legt das Formular „Preisautomatik" an bzw. bringt es auf Stand.

Eigenes Formular statt Reiter in einem Cockpit – wie bei der Kostenstruktur:
Ein Widget ohne action_id würde in JEDEM Reiter eines Cockpits auftauchen
(FormRunner filtert Reiter über action_id), und die Preisautomatik ist ohnehin
eine eigene Arbeitsfläche und keine Auswertung.

    docker cp backend/preisautomatik_formular.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/preisautomatik_formular.py --projekt 1 --anwenden
"""
import argparse
import json
import sqlite3

DB = "/app/uploads/datenmonster.db"
NAME = "Preisautomatik"

SCHEMA = {
    "fields": [],
    "layout": [],
    "actions": [],
    "widgets": [{
        "id": "w_preisautomatik",
        "type": "preisautomatik",
        "label": "Ladenhüter-Rabatte",
        "action_id": None,
        "config": {
            "width": 12,
            "info": ("Rabatte werden als befristeter Sonderpreis gesetzt, der Grundpreis "
                     "bleibt unangetastet. „Angewandt“ vergibt allein die Kontrolle – sie "
                     "liest die echten Preise aus der Wawi zurück."),
        },
    }],
    "result_tabs": [],
    "show_ai_assistant": False,
}


def anlegen(projekt: int, anwenden: bool):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT id FROM forms WHERE name = ? AND project_id = ?",
                    (NAME, projekt)).fetchone()
    roh = json.dumps(SCHEMA, ensure_ascii=False)
    if row:
        print(f"aktualisiere Formular {row['id']}")
        if anwenden:
            c.execute("UPDATE forms SET schema = ?, updated_at = CURRENT_TIMESTAMP "
                      "WHERE id = ?", (roh, row["id"]))
    else:
        print("lege Formular neu an")
        if anwenden:
            c.execute("INSERT INTO forms (name, project_id, schema, version, slug, "
                      "published, portal_config, created_at, updated_at) "
                      "VALUES (?, ?, ?, 1, 'preisautomatik', 0, '{}', "
                      "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (NAME, projekt, roh))
    if anwenden:
        c.commit()
    c.close()
    print("angewandt" if anwenden else "Trockenlauf – mit --anwenden schreiben")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--projekt", type=int, required=True)
    p.add_argument("--anwenden", action="store_true")
    a = p.parse_args()
    anlegen(a.projekt, a.anwenden)

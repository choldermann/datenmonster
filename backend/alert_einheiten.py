"""Trägt die Einheit der Kopfzahl in die Prüfregeln ein.

Die große Zahl rechts in einer Warnungszeile stand fest auf „€". Bei jeder
Kennzahl-Regel, deren Wert eine Stückzahl ist, las sich das falsch:
„14 offene Aufträge mit überschrittenem Liefertermin" mit „14 €" daneben.

Ohne Angabe rät alert_service._wert_einheit weiter „€" für Regeln, die eine
Wertspalte summieren (fast immer Geld), und gar nichts für Kennzahl-Regeln.
Hier wird jede vorhandene Regel ausdrücklich gesetzt, damit nichts geraten wird.

Anwenden:
    docker cp backend/alert_einheiten.py datenmonster-backend:/tmp/
    docker exec datenmonster-backend python /tmp/alert_einheiten.py --anwenden
"""
import sqlite3, json, sys

DB = "/app/uploads/datenmonster.db"

# "" = blanke Zahl (Stückzahlen). Bewusst je Regel entschieden, nicht geraten.
EINHEIT = {
    # Kennzahl-Regeln: der Wert ist die geprüfte Spalte selbst
    "gf_umsatz_rueckgang":      "€",       # Umsatz
    "gf_umsatz_plus":           "€",       # Umsatz
    "gf_db_marge":              "%",       # Rohertragsmarge
    "op_ueberfaellig":          "€",       # überfälliger Betrag
    "vertrieb_auftragseingang": "€",       # Auftragseingang
    "vertrieb_backlog":         "",        # Anzahl Aufträge
    "lager_ladenhueter":        "",        # Anzahl Artikel
    "lager_negativbestand":     "",        # Anzahl Artikel
    "lager_inventurdifferenz":  "",        # Anzahl Buchungen
    "health_stammdaten":        "",        # Anzahl Artikel
    # Summen-Regeln: der Wert ist die Summe der Wertspalte
    "op_mahnkandidaten":        "€",
    "kunden_rueckgang":         "€",
    "kunden_churn":             "€",
    "vertrieb_angebote":        "€",
    "ek_bestellverzug":         "€",
    "ek_eingangsrechnungen":    "€",
    "lager_fehlmengen":         "€",
    "artikel_gesperrt_bestand": "€",
    "health_vk_unter_ek":       "€",
    "gf_rohertrag_trend":       "€",
    "gf_beschreibungen":        "Stück",   # summiert Lagerbestand, kein Geld
    # Ohne Wertspalte gibt es keine Kopfzahl – Einheit trotzdem festhalten,
    # damit eine spätere Wertspalte nicht stillschweigend Euro erbt.
    "kunden_zahlungsmoral":     "",
    "ek_termintreue":           "",
    "artikel_negative_marge":   "",
    "artikel_ohne_bestand":     "",
    "versand_rueckstand":       "",
}

# Überbleibsel der Umbenennung von „DB II" auf „Rohertrag" in den Regeltexten.
TEXTE = {
    "gf_db_marge": {"name": "Rohertragsmarge gesunken",
                    "title_template": "Rohertragsmarge mehr als 2 Punkte unter Vorjahr"},
}

# Dieselbe Umbenennung in den Faktenchips unter der Warnung – nach SPALTE, nicht
# nach Beschriftung. Nur so fällt auch der Chip auf, der schon vorher falsch hieß:
# bei „Rohertragsmarge gesunken" trug die Spalte `Marge` die Beschriftung
# „Rohertragsmarge", also stand sie zweimal in derselben Zeile.
FAKTEN_SPALTE = {
    "DB2":       "Rohertrag gesamt",
    "DB2Marge":  "Rohertragsmarge",
    "DB2Quote":  "Rohertragsquote",
    "Rohertrag": "Rohertrag Ware",
    "Marge":     "Marge",
}


def fakten_patchen(fakten) -> tuple:
    """Gibt (neue Fakten, geändert?) zurück.

    Chips auf einer Vorjahresspalte heißen bewusst „Vorjahr" – die Beschriftung
    kommt dort aus dem Zusammenhang der Zeile und bleibt unangetastet.
    """
    d = json.loads(fakten) if isinstance(fakten, str) else (fakten or [])
    n = False
    for x in d:
        spalte = str(x.get("column") or "")
        if spalte.endswith("VJ") or spalte.endswith("Vorjahr"):
            continue
        neu = FAKTEN_SPALTE.get(spalte)
        if neu and x.get("label") != neu:
            x["label"] = neu; n = True
    return d, n


def regeln_patchen(c, anwenden: bool) -> int:
    n = 0
    for rid, key, cond, name, titel, fakten in c.execute(
            "select id, rule_key, condition, name, title_template, facts "
            "from alert_rules").fetchall():
        if key not in EINHEIT:
            print(f"  ! unbekannte Regel ohne Einheit: {key}")
            continue
        d = json.loads(cond) if isinstance(cond, str) else (cond or {})
        neu_name, neu_titel = name, titel
        t = TEXTE.get(key)
        if t:
            neu_name = t.get("name", name)
            neu_titel = t.get("title_template", titel)
        neu_fakten, fakten_geaendert = fakten_patchen(fakten)
        if (d.get("value_unit") == EINHEIT[key] and neu_name == name
                and neu_titel == titel and not fakten_geaendert):
            continue
        d["value_unit"] = EINHEIT[key]
        n += 1
        print(f"  {key:26} value_unit={EINHEIT[key]!r}"
              + ("  + Text erneuert" if t else "")
              + ("  + Faktenchips erneuert" if fakten_geaendert else ""))
        if anwenden:
            c.execute("update alert_rules set condition=?, name=?, title_template=?, facts=? "
                      "where id=?",
                      (json.dumps(d, ensure_ascii=False), neu_name, neu_titel,
                       json.dumps(neu_fakten, ensure_ascii=False), rid))
    return n


def template_patchen(c, anwenden: bool) -> int:
    """Dieselben Einheiten im Template, sonst kommen sie bei einer Neuinstallation zurück."""
    n = 0
    for tid, roh in c.execute("select template_id, content from templates").fetchall():
        if not roh:
            continue
        inhalt = json.loads(roh) if isinstance(roh, str) else roh
        regeln = inhalt.get("alert_rules") or []
        geaendert = False
        for r in regeln:
            key = r.get("rule_key")
            if key not in EINHEIT:
                continue
            d = r.get("condition")
            if isinstance(d, str):
                d = json.loads(d)
            d = d or {}
            t = TEXTE.get(key) or {}
            neu_fakten, fakten_geaendert = fakten_patchen(r.get("facts"))
            # `and not t` genügt nicht: bei einer Regel mit Textkorrektur wäre die
            # Bedingung dann immer falsch und das Skript nie fertig.
            if (d.get("value_unit") == EINHEIT[key] and not fakten_geaendert
                    and all(r.get(k) == v for k, v in t.items())):
                continue
            d["value_unit"] = EINHEIT[key]
            r["condition"] = d
            if fakten_geaendert:
                r["facts"] = neu_fakten
            r.update(t)
            geaendert = True; n += 1
        if geaendert:
            print(f"  Template {tid}: {n} Regeln")
            if anwenden:
                c.execute("update templates set content=? where template_id=?",
                          (json.dumps(inhalt, ensure_ascii=False), tid))
    return n


def datei_patchen(pfad: str, anwenden: bool) -> int:
    """Dieselben Einheiten in einer Template-DATEI im Repo.

    Nötig, weil die Datei eines Cockpits an anderer Stelle weiter sein kann als
    die Installation (siehe backend/template_abgleich.py): dort wäre ein
    Überschreiben aus der Datenbank ein Rückschritt.
    """
    with open(pfad, encoding="utf-8") as f:
        t = json.load(f)
    n = 0
    for r in (t.get("alert_rules") or []):
        key = r.get("rule_key")
        if key not in EINHEIT:
            continue
        d = r.get("condition")
        d = json.loads(d) if isinstance(d, str) else (d or {})
        txt = TEXTE.get(key) or {}
        neu_fakten, fakten_geaendert = fakten_patchen(r.get("facts"))
        if (d.get("value_unit") == EINHEIT[key] and not fakten_geaendert
                and all(r.get(k) == v for k, v in txt.items())):
            continue
        d["value_unit"] = EINHEIT[key]
        r["condition"] = d
        if fakten_geaendert:
            r["facts"] = neu_fakten
        r.update(txt)
        n += 1
    print(f"{pfad}: {n} Regeln")
    if n and anwenden:
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=2); f.write("\n")
        print("geschrieben.")
    elif n:
        print("(Trockenlauf – mit --anwenden schreiben)")
    return n


if __name__ == "__main__":
    anwenden = "--anwenden" in sys.argv
    if "--template" in sys.argv:
        datei_patchen(sys.argv[sys.argv.index("--template") + 1], anwenden)
        raise SystemExit(0)
    c = sqlite3.connect(DB)
    print("Prüfregeln:")
    n = regeln_patchen(c, anwenden)
    print("Templates:")
    n += template_patchen(c, anwenden)
    if anwenden:
        c.commit(); print(f"\n{n} Änderungen geschrieben.")
    else:
        print(f"\n{n} Änderungen – (Trockenlauf, mit --anwenden schreiben)")

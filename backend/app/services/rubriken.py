"""Rubriken für das Büro: ein Cockpit, links die Bereiche.

Jedes Dashboard-Formular gehört zu genau einer Rubrik (GF-Cockpit, Vertrieb, …).
Das Menü des Büros ergibt sich daraus. Plan: ~/.claude/plans/ein-cockpit-rubriken.md.

Woher die Rubrik kommt, in dieser Reihenfolge:
1. ``schema.rubrik`` am Formular (künftig aus der Vorlage oder vom Formular-Editor),
2. die Vorlage, aus der das Formular installiert wurde (``vorlagen_gate``-Index),
3. ein Widget-Typ, der nur in einem Bereich vorkommt (Kostenstruktur, Preisautomatik),
4. der Formularname einer bekannten Vorlage. Ältere Installationen sind im Index
   nicht verzeichnet (z. B. ein Lager-Cockpit von vor dem Herkunftsstempel).
Sonst: Gruppe „Weitere“, jedes Formular als eigener Eintrag.

Kopien erben die Rubrik ihres Originals, Berichte aus dem Report-Baukasten die
Rubrik, aus der die meisten ihrer Bausteine stammen.

Bewusst nicht JTL-fest: Rubriken sind Themen, die Vorlage sagt, wohin sie gehört.
Die feste Tabelle unten ist nur der Ersatzweg für Bestand ohne ``schema.rubrik``.
"""
from collections import Counter
from typing import Dict, List, Optional

GRUPPEN = [
    {"id": "cockpit", "name": "Cockpit"},
    {"id": "aufgabe", "name": "Aufgaben"},
    {"id": "weitere", "name": "Weitere"},
]
_GRUPPEN_IDS = {g["id"] for g in GRUPPEN}

# Bekannte Rubriken mit Vorgaben. Eine Vorlage kann eigene mitbringen (schema.rubrik).
RUBRIKEN: Dict[str, dict] = {
    "gf":                 {"name": "GF-Cockpit",         "gruppe": "cockpit", "reihenfolge": 10, "icon": "gf"},
    "monitor":            {"name": "Unternehmensmonitor", "gruppe": "cockpit", "reihenfolge": 20, "icon": "monitor"},
    "vertrieb":           {"name": "Vertrieb",           "gruppe": "cockpit", "reihenfolge": 30, "icon": "vertrieb"},
    "einkauf":            {"name": "Einkauf",            "gruppe": "cockpit", "reihenfolge": 40, "icon": "einkauf"},
    "lager":              {"name": "Lager",              "gruppe": "cockpit", "reihenfolge": 50, "icon": "lager"},
    "versand":            {"name": "Versand",            "gruppe": "cockpit", "reihenfolge": 60, "icon": "versand"},
    "preis":              {"name": "Preis & Marge",      "gruppe": "cockpit", "reihenfolge": 70, "icon": "preis"},
    "health":             {"name": "Health-Check",       "gruppe": "cockpit", "reihenfolge": 80, "icon": "health"},
    "datev":              {"name": "DATEV-Export",       "gruppe": "aufgabe", "reihenfolge": 10, "icon": "datev"},
    "intrastat":          {"name": "Intrastat",          "gruppe": "aufgabe", "reihenfolge": 20, "icon": "intrastat"},
    "eingangsrechnungen": {"name": "Eingangsrechnungen", "gruppe": "aufgabe", "reihenfolge": 30, "icon": "eingangsrechnungen"},
}

# Ersatzweg 2: Vorlage → Rubrik
VORLAGE_RUBRIK = {
    "jtl_gf_cockpit": "gf",
    "jtl_monitor": "monitor",
    "jtl_vertrieb_cockpit": "vertrieb",
    "jtl_einkauf_cockpit": "einkauf",
    "jtl_lager_cockpit": "lager",
    "jtl_versand_cockpit": "versand",
    "jtl_preis_cockpit": "preis",
    "jtl_health_check": "health",
    "jtl_datev": "datev",
    "jtl_intrastat": "intrastat",
    "jtl_eingangsrechnung": "eingangsrechnungen",
}

# Ersatzweg 3: Widget-Typ → (Rubrik, Art). „pflege“ = Pflegemaske eines Cockpits;
# sie verschwindet aus dem Menü, sobald das Hauptformular dasselbe Widget als Reiter hat.
WIDGET_RUBRIK = {
    "kostenstruktur": ("gf", "pflege"),
    "preisautomatik": ("preis", "pflege"),
}

# Ersatzweg 4: Formularname einer bekannten Vorlage → Rubrik
NAME_RUBRIK = {
    "geschäftsführer-cockpit": "gf",
    "unternehmensmonitor": "monitor",
    "vertriebs-cockpit": "vertrieb",
    "einkaufs-cockpit": "einkauf",
    "lager-cockpit": "lager",
    "versand-cockpit": "versand",
    "preis- & marge-cockpit": "preis",
    "stammdaten-health-check": "health",
    "datev-export": "datev",
    "intrastat zeitraum": "intrastat",
    "eingangsrechnungs-import": "eingangsrechnungen",
}


def _widget_typen(schema: dict) -> set:
    return {w.get("type") for w in (schema.get("widgets") or []) if isinstance(w, dict)}


def _eigene_angabe(schema: dict) -> Optional[dict]:
    """schema.rubrik prüfen und mit den Vorgaben einer bekannten Rubrik auffüllen."""
    r = schema.get("rubrik")
    if isinstance(r, str):
        r = {"id": r}
    if not isinstance(r, dict) or not str(r.get("id") or "").strip():
        return None
    rid = str(r["id"]).strip()
    basis = dict(RUBRIKEN.get(rid) or {})
    for k in ("name", "gruppe", "reihenfolge", "icon"):
        if r.get(k) not in (None, ""):
            basis[k] = r[k]
    if basis.get("gruppe") not in _GRUPPEN_IDS:
        basis["gruppe"] = "cockpit"
    basis.setdefault("name", rid)
    basis.setdefault("reihenfolge", 500)
    basis.setdefault("icon", "")
    return {"id": rid, **basis, "rolle": r.get("rolle") or None}


def eigene_zuordnung(form, vorlage_id: Optional[str]) -> Optional[dict]:
    """Rubrik eines Formulars ohne Kopie-/Bericht-Vererbung. None = keine bekannt."""
    schema = form.schema or {}
    eigen = _eigene_angabe(schema)
    if eigen:
        return eigen
    rid = VORLAGE_RUBRIK.get(vorlage_id or "")
    typen = _widget_typen(schema)
    rolle = None
    # Pflegemasken liefert dieselbe Vorlage mit (GF → Kostenstruktur): Widget-Typ vor Vorlage.
    for typ, (w_rid, w_rolle) in WIDGET_RUBRIK.items():
        if typ in typen and len(schema.get("result_tabs") or []) <= 1 and len(typen) == 1:
            rid, rolle = w_rid, w_rolle
            break
    if not rid:
        rid = NAME_RUBRIK.get((form.name or "").strip().lower())
    if not rid or rid not in RUBRIKEN:
        return None
    return {"id": rid, **RUBRIKEN[rid], "rolle": rolle}


def zuordnen(formulare: list, vorlage_von) -> Dict[int, dict]:
    """form_id → Rubrik für alle Formulare, inkl. Vererbung an Kopien und Berichte.

    ``vorlage_von(form_id)`` liefert die template_id (oder None).
    """
    nach_id = {f.id: f for f in formulare}
    direkt = {f.id: eigene_zuordnung(f, vorlage_von(f.id)) for f in formulare}
    ergebnis: Dict[int, dict] = {}

    def fuer(fid: int, tiefe: int = 0) -> Optional[dict]:
        if fid in ergebnis:
            return ergebnis[fid]
        f = nach_id.get(fid)
        if f is None or tiefe > 5:
            return None
        schema = f.schema or {}
        r = direkt.get(fid)
        # Eigene Angabe am Formular geht vor; sonst erben.
        if not _eigene_angabe(schema):
            quelle = (schema.get("kopie_von") or {}).get("form_id")
            if isinstance(quelle, int) and quelle in nach_id:
                geerbt = fuer(quelle, tiefe + 1)
                if geerbt:
                    r = {**geerbt, "rolle": None}
            elif schema.get("report_builder"):
                stimmen, meta = Counter(), {}
                for e in (schema["report_builder"].get("entries") or []):
                    try:
                        q = fuer(int(e.get("form_id")), tiefe + 1)
                    except (TypeError, ValueError):
                        q = None
                    if q:
                        stimmen[q["id"]] += 1
                        meta[q["id"]] = q
                if stimmen:
                    r = {**meta[stimmen.most_common(1)[0][0]], "rolle": None}
        if r:
            ergebnis[fid] = r
        return r

    for f in formulare:
        fuer(f.id)
    return ergebnis


def _art(c: dict, schema: dict, rubrik: Optional[dict]) -> str:
    if c.get("art") == "bericht":
        return "bericht"
    if schema.get("kopie_von"):
        return "kopie"
    if rubrik and rubrik.get("rolle") == "pflege":
        return "pflege"
    return "cockpit"


def menue(formulare: list, eintraege: Dict[int, dict], vorlage_von, gesperrt_von) -> List[dict]:
    """Das Büro-Menü: Gruppen → Rubriken → Haupteintrag + weitere Einträge.

    ``eintraege``: form_id → Ausgabe von ``_cockpit_out`` (id, name, projekt, …).
    ``gesperrt_von(form_id)``: True, wenn die Vorlage nicht freigeschaltet ist –
    solche Formulare und ihre Kopien erscheinen nicht.
    """
    nach_id = {f.id: f for f in formulare}
    zuordnung = zuordnen(formulare, vorlage_von)

    def gesperrt(fid: int, tiefe: int = 0) -> bool:
        if gesperrt_von(fid):
            return True
        f = nach_id.get(fid)
        quelle = ((f.schema or {}).get("kopie_von") or {}).get("form_id") if f else None
        return isinstance(quelle, int) and tiefe < 5 and quelle in nach_id and gesperrt(quelle, tiefe + 1)

    rubriken: Dict[str, dict] = {}
    for f in formulare:
        if f.id not in eintraege or gesperrt(f.id):
            continue
        schema = f.schema or {}
        r = zuordnung.get(f.id)
        if r:
            key, meta = r["id"], r
        else:
            key = f"f{f.id}"
            meta = {"id": key, "name": f.name, "gruppe": "weitere", "reihenfolge": 1000, "icon": ""}
        ziel = rubriken.setdefault(key, {
            "id": key, "name": meta["name"], "gruppe": meta["gruppe"],
            "reihenfolge": meta.get("reihenfolge", 500), "icon": meta.get("icon") or "",
            "haupt": None, "eintraege": []})
        c = {**eintraege[f.id], "art": _art(eintraege[f.id], schema, r)}
        if c["art"] == "cockpit" and ziel["haupt"] is None:
            ziel["haupt"] = c
        else:
            ziel["eintraege"].append(c)

    for r in rubriken.values():
        # Pflegemaske weg, sobald das Hauptformular ihr Widget selbst als Reiter hat.
        if r["haupt"]:
            haupt_typen = _widget_typen(nach_id[r["haupt"]["id"]].schema or {})
            r["eintraege"] = [e for e in r["eintraege"] if not (
                e["art"] == "pflege" and _widget_typen(nach_id[e["id"]].schema or {}) <= haupt_typen)]
        # Nur Kopien oder Berichte übrig: der erste wird Haupteintrag.
        if r["haupt"] is None and r["eintraege"]:
            r["haupt"] = r["eintraege"].pop(0)
        rang = {"cockpit": 0, "kopie": 1, "bericht": 2, "pflege": 3}
        r["eintraege"].sort(key=lambda e: (rang.get(e["art"], 9), (e.get("name") or "").lower()))

    aus = []
    for g in GRUPPEN:
        rs = sorted((r for r in rubriken.values() if r["gruppe"] == g["id"] and r["haupt"]),
                    key=lambda r: (r["reihenfolge"], r["name"].lower()))
        if rs:
            aus.append({**g, "rubriken": rs})
    return aus

"""Projektbezogene Geschäftsparameter laden und in Mapping-Läufe injizieren.

Warum es das gibt: Schwellwerte steckten bisher entweder hart im SQL ("180 Tage
ohne Verkauf") oder als {{platzhalter}} im Template, der beim Installieren
substituiert und danach vergessen wurde. Beides ist nach der Installation nicht
mehr änderbar.

Wie es wirkt: apply_config() legt zu jedem Schwellwert einen gebundenen Parameter
:cfg_<key> in die run_params. SQL-Statements, die den Parameter nicht
referenzieren, bleiben davon völlig unberührt (sql_helpers._resolve_sql_run_params
bindet ausschließlich, was im SQL-Text vorkommt) – deshalb ist die Injektion für
alle bestehenden Mappings ein No-Op.
"""
from datetime import date, timedelta
from typing import Optional

# ── Schwellwerte: Standardwerte + Beschreibung für die Oberfläche ────────────
# Reihenfolge = Anzeigereihenfolge. "unit" ist reine Darstellung.
THRESHOLD_DEFAULTS: list[dict] = [
    # Vertrieb & Kunden
    {"key": "umsatz_rueckgang_prozent", "label": "Umsatzrückgang meldet ab",
     "default": 5, "unit": "%", "gruppe": "Vertrieb & Kunden",
     "hinweis": "Abweichung zum Vorjahreszeitraum, ab der gewarnt wird."},
    {"key": "auftragseingang_rueckgang_prozent", "label": "Auftragseingang-Rückgang meldet ab",
     "default": 10, "unit": "%", "gruppe": "Vertrieb & Kunden"},
    {"key": "kunde_rueckgang_prozent", "label": "Kundenrückgang meldet ab",
     "default": 25, "unit": "%", "gruppe": "Vertrieb & Kunden"},
    {"key": "kunde_rueckgang_betrag", "label": "… und mindestens",
     "default": 2000, "unit": "€", "gruppe": "Vertrieb & Kunden",
     "hinweis": "Kleine Rückgänge sind Rauschen – erst ab diesem Betrag ist es eine Aufgabe."},
    {"key": "angebot_nachfass_tage", "label": "Angebot nachfassen nach",
     "default": 14, "unit": "Tagen", "gruppe": "Vertrieb & Kunden"},
    {"key": "auftrag_alt_tage", "label": "Offener Auftrag gilt als alt ab",
     "default": 30, "unit": "Tagen", "gruppe": "Vertrieb & Kunden"},

    # Liquidität
    {"key": "forderung_kritisch_tage", "label": "Forderung kritisch ab",
     "default": 30, "unit": "Tagen überfällig", "gruppe": "Liquidität"},
    {"key": "forderung_kritisch_betrag", "label": "Einzelforderung kritisch ab",
     "default": 5000, "unit": "€", "gruppe": "Liquidität"},
    {"key": "zahldauer_verschlechterung_tage", "label": "Zahlungsmoral verschlechtert ab",
     "default": 10, "unit": "Tagen", "gruppe": "Liquidität"},

    # Einkauf & Lieferanten
    {"key": "lieferverzug_tage", "label": "Lieferverzug kritisch ab",
     "default": 7, "unit": "Tagen", "gruppe": "Einkauf & Lieferanten"},
    {"key": "termintreue_min_prozent", "label": "Termintreue-Warnung unter",
     "default": 80, "unit": "%", "gruppe": "Einkauf & Lieferanten"},
    {"key": "ek_anstieg_prozent", "label": "EK-Steigerung meldet ab",
     "default": 5, "unit": "%", "gruppe": "Einkauf & Lieferanten"},

    # Lager & Artikel
    {"key": "ladenhueter_tage", "label": "Ladenhüter ab",
     "default": 180, "unit": "Tagen ohne Verkauf", "gruppe": "Lager & Artikel"},
    {"key": "oos_tage", "label": "Ausverkauft-Warnung unter",
     "default": 14, "unit": "Tagen Reichweite", "gruppe": "Lager & Artikel"},
    {"key": "ueberbestand_tage", "label": "Überbestand ab",
     "default": 180, "unit": "Tagen Reichweite", "gruppe": "Lager & Artikel"},
    {"key": "marge_min_prozent", "label": "Margenwarnung unter",
     "default": 15, "unit": "%", "gruppe": "Lager & Artikel"},

    # Retouren & Versand
    {"key": "retoure_quote_prozent", "label": "Retourenquote meldet ab",
     "default": 5, "unit": "%", "gruppe": "Retouren & Versand"},
    {"key": "retoure_anomalie_faktor", "label": "Retouren-Anomalie ab Faktor",
     "default": 2.0, "unit": "× Normalwert", "gruppe": "Retouren & Versand",
     "hinweis": "Greift erst ab ausreichender Fallzahl – sonst wäre es Zufallsrauschen."},
    {"key": "versandrueckstand_tage", "label": "Versandrückstand ab",
     "default": 3, "unit": "Tagen", "gruppe": "Retouren & Versand"},
]

_DEFAULTS_BY_KEY = {d["key"]: d for d in THRESHOLD_DEFAULTS}


# ── Kostenarten: Standardkatalog für die Kostenmaske ─────────────────────────
# Warum ein fester Katalog: die Gemeinkosten eines Handelsbetriebs sind immer
# dieselben Blöcke. Vorgeblendet muss der Anwender nur noch "gültig ab" und den
# Monatsbetrag eintragen, statt sich eine Struktur auszudenken. Eigene Arten
# kommen als Schlüssel "x_<slug>" dazu und leben komplett in der Datenbank.
#
# gruppe_key ist der stabile Anteil des Laufzeit-Parameters
# (:cfg_kosten_<gruppe_key>_monat) – Labels dürfen sich ändern, Schlüssel nicht.
COST_DEFAULTS: list[dict] = [
    {"key": "personal", "label": "Löhne & Gehälter", "gruppe": "Personal",
     "gruppe_key": "personal",
     "hinweis": "Bruttolöhne inkl. Arbeitgeberanteil, ohne Geschäftsführung."},
    {"key": "geschaeftsfuehrung", "label": "Geschäftsführung / Unternehmerlohn",
     "gruppe": "Personal", "gruppe_key": "personal"},
    {"key": "personal_sonstiges", "label": "Sonstige Personalkosten",
     "gruppe": "Personal", "gruppe_key": "personal",
     "hinweis": "Fortbildung, Berufsgenossenschaft, Arbeitskleidung."},

    {"key": "miete", "label": "Miete / Pacht", "gruppe": "Raum & Gebäude",
     "gruppe_key": "raum"},
    {"key": "nebenkosten", "label": "Nebenkosten & Reinigung",
     "gruppe": "Raum & Gebäude", "gruppe_key": "raum"},
    {"key": "instandhaltung", "label": "Instandhaltung Gebäude",
     "gruppe": "Raum & Gebäude", "gruppe_key": "raum"},

    {"key": "strom", "label": "Strom", "gruppe": "Energie", "gruppe_key": "energie"},
    {"key": "heizung", "label": "Heizung / Gas", "gruppe": "Energie",
     "gruppe_key": "energie"},
    {"key": "wasser", "label": "Wasser & Abwasser", "gruppe": "Energie",
     "gruppe_key": "energie"},

    {"key": "fahrzeuge_leasing", "label": "Leasing / Abschreibung Fahrzeuge",
     "gruppe": "Fahrzeuge", "gruppe_key": "fahrzeuge"},
    {"key": "fahrzeuge_kraftstoff", "label": "Kraftstoff", "gruppe": "Fahrzeuge",
     "gruppe_key": "fahrzeuge"},
    {"key": "fahrzeuge_versicherung", "label": "Kfz-Versicherung & -Steuer",
     "gruppe": "Fahrzeuge", "gruppe_key": "fahrzeuge"},
    {"key": "fahrzeuge_wartung", "label": "Wartung & Reparatur",
     "gruppe": "Fahrzeuge", "gruppe_key": "fahrzeuge"},

    {"key": "it_software", "label": "Software & Lizenzen",
     "gruppe": "IT & Kommunikation", "gruppe_key": "it",
     "hinweis": "Warenwirtschaft, Office, Cloud-Dienste."},
    {"key": "it_hardware", "label": "Hardware & IT-Betreuung",
     "gruppe": "IT & Kommunikation", "gruppe_key": "it"},
    {"key": "telefon_internet", "label": "Telefon & Internet",
     "gruppe": "IT & Kommunikation", "gruppe_key": "it"},

    {"key": "marketing", "label": "Werbung & Marketing",
     "gruppe": "Marketing & Vertrieb", "gruppe_key": "marketing"},
    {"key": "messen", "label": "Messen & Reisekosten",
     "gruppe": "Marketing & Vertrieb", "gruppe_key": "marketing"},

    {"key": "versicherungen", "label": "Betriebliche Versicherungen",
     "gruppe": "Versicherungen & Beiträge", "gruppe_key": "versicherungen"},
    {"key": "beitraege", "label": "Beiträge & Gebühren",
     "gruppe": "Versicherungen & Beiträge", "gruppe_key": "versicherungen",
     "hinweis": "IHK, Verbände, LUCID/EPR, behördliche Gebühren."},

    {"key": "beratung", "label": "Steuer- & Rechtsberatung",
     "gruppe": "Beratung & Finanzen", "gruppe_key": "finanzen"},
    {"key": "zinsen", "label": "Zinsen & Bankgebühren",
     "gruppe": "Beratung & Finanzen", "gruppe_key": "finanzen"},
    {"key": "abschreibungen", "label": "Abschreibungen (ohne Fahrzeuge)",
     "gruppe": "Beratung & Finanzen", "gruppe_key": "finanzen"},

    {"key": "buero", "label": "Bürobedarf & Porto", "gruppe": "Sonstiges",
     "gruppe_key": "sonstiges"},
    {"key": "sonstiges", "label": "Sonstige betriebliche Kosten",
     "gruppe": "Sonstiges", "gruppe_key": "sonstiges"},
]

_COST_BY_KEY = {d["key"]: d for d in COST_DEFAULTS}

# Reihenfolge der Gruppen für die Oberfläche und für die Parameternamen.
COST_GROUPS: list[dict] = []
for _d in COST_DEFAULTS:
    if not any(g["key"] == _d["gruppe_key"] for g in COST_GROUPS):
        COST_GROUPS.append({"key": _d["gruppe_key"], "label": _d["gruppe"]})


def cost_meta() -> list[dict]:
    """Standardkatalog der Kostenarten für die Oberfläche."""
    return [dict(d) for d in COST_DEFAULTS]



def default_thresholds() -> dict:
    return {d["key"]: d["default"] for d in THRESHOLD_DEFAULTS}


def threshold_meta() -> list[dict]:
    """Beschreibung aller Schwellwerte für die Einstellungs-Oberfläche."""
    return [dict(d) for d in THRESHOLD_DEFAULTS]


def _rows(project_id, db, scope: str) -> list:
    if db is None:
        return []
    try:
        from app.models.business_config import BusinessConfig
        q = db.query(BusinessConfig).filter(BusinessConfig.scope == scope)
        q = q.filter(BusinessConfig.project_id == project_id) if project_id is not None \
            else q.filter(BusinessConfig.project_id.is_(None))
        return q.all()
    except Exception:
        return []


def get_thresholds(project_id, db) -> dict:
    """Standardwerte, überschrieben von den projektbezogenen Einstellungen."""
    values = default_thresholds()
    for r in _rows(project_id, db, "threshold"):
        if r.key in values or r.key.startswith("x_"):
            values[r.key] = r.value
    return values


def _parse_datum(wert) -> Optional[date]:
    try:
        return date.fromisoformat(str(wert)[:10])
    except Exception:
        return None


def _eintraege(value) -> list[dict]:
    """Zeitscheiben einer Kostenart, aufsteigend nach "gültig ab".

    Ein Betrag ohne Zeitscheiben (altes Format {"betrag": 100}) wird als eine
    Scheibe ohne Startdatum gelesen – damit bleibt Vorhandenes lesbar.
    """
    if not isinstance(value, dict):
        return []
    roh = value.get("eintraege")
    if roh is None and value.get("betrag") is not None:
        roh = [{"gueltig_ab": value.get("gueltig_ab"), "betrag": value.get("betrag")}]
    out = []
    for e in roh or []:
        if not isinstance(e, dict):
            continue
        try:
            betrag = float(e.get("betrag") or 0)
        except (TypeError, ValueError):
            continue
        d = _parse_datum(e.get("gueltig_ab")) or date(1970, 1, 1)
        out.append({"gueltig_ab": d.isoformat(), "betrag": betrag})
    out.sort(key=lambda e: e["gueltig_ab"])
    return out


def betrag_am(eintraege: list[dict], stichtag: date) -> float:
    """Monatsbetrag, der am Stichtag gilt.

    Vor der frühesten Zeitscheibe ist der Betrag 0 – "gültig ab" wird wörtlich
    genommen. Wer einen Vorjahresvergleich rechnen will, muss die erste Scheibe
    entsprechend weit zurückdatieren; stillschweigend rückwärts zu verlängern
    würde Kosten erfinden, die es damals nicht gab.
    """
    treffer = 0.0
    for e in eintraege:
        if e["gueltig_ab"] <= stichtag.isoformat():
            treffer = e["betrag"]
        else:
            break
    return treffer


def get_costs(project_id, db) -> list[dict]:
    """Kostenarten-Katalog: Standardarten, angereichert um die gepflegten Werte.

    Standardarten erscheinen immer – auch ungepflegt, damit die Maske sie
    vorblenden kann. Eigene Arten (Schlüssel "x_…") kommen aus der Datenbank und
    tragen Bezeichnung und Gruppe im Wert selbst.
    """
    gespeichert = {r.key: (r.value if isinstance(r.value, dict) else {})
                   for r in _rows(project_id, db, "cost")}
    heute = date.today()

    def bauen(key: str, meta: dict, value: dict) -> dict:
        eintraege = _eintraege(value)
        return {
            "key": key,
            "label": meta.get("label") or value.get("label") or key,
            "gruppe": meta.get("gruppe") or value.get("gruppe") or "Sonstiges",
            "gruppe_key": meta.get("gruppe_key") or value.get("gruppe_key") or "sonstiges",
            "hinweis": meta.get("hinweis") or value.get("hinweis") or "",
            "custom": not meta,
            "eintraege": eintraege,
            "betrag_aktuell": betrag_am(eintraege, heute),
        }

    out = [bauen(m["key"], m, gespeichert.get(m["key"], {})) for m in COST_DEFAULTS]
    for key, value in gespeichert.items():
        if key not in _COST_BY_KEY:
            out.append(bauen(key, {}, value))
    return out


def _monatstage(d: date) -> int:
    naechster = date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
    return (naechster - date(d.year, d.month, 1)).days


def kosten_monat(project_id, db, stichtag: Optional[date] = None) -> dict:
    """Monatliche Fixkosten zum Stichtag: Summe und je Gruppe."""
    stichtag = stichtag or date.today()
    je_gruppe: dict = {g["key"]: 0.0 for g in COST_GROUPS}
    gesamt = 0.0
    for k in get_costs(project_id, db):
        betrag = betrag_am(k["eintraege"], stichtag)
        if not betrag:
            continue
        je_gruppe[k["gruppe_key"]] = je_gruppe.get(k["gruppe_key"], 0.0) + betrag
        gesamt += betrag
    return {"gesamt": round(gesamt, 2),
            "gruppen": {g: round(v, 2) for g, v in je_gruppe.items()}}


def kosten_zeitraum(project_id, db, von: date, bis: date) -> float:
    """Fixkosten für einen Zeitraum – taggenau anteilig.

    Tagweise statt monatsweise, weil ein Cockpit-Zeitraum selten auf
    Monatsgrenzen liegt und eine Kostenänderung mitten im Monat greifen kann.
    """
    if bis < von:
        return 0.0
    if (bis - von).days > 366 * 20:      # Schutz gegen unsinnige Zeiträume
        bis = von + timedelta(days=366 * 20)
    arten = [k["eintraege"] for k in get_costs(project_id, db)]
    summe = 0.0
    tag = von
    while tag <= bis:
        tage = _monatstage(tag)
        for eintraege in arten:
            b = betrag_am(eintraege, tag)
            if b:
                summe += b / tage
        tag += timedelta(days=1)
    return round(summe, 2)


def get_goals(project_id, db) -> list[dict]:
    """Ziele/Budgets (Phase 4)."""
    out = []
    for r in _rows(project_id, db, "goal"):
        v = r.value if isinstance(r.value, dict) else {"wert": r.value}
        out.append({**v, "key": r.key})
    return out


def apply_config(run_params: Optional[dict], project_id, db) -> dict:
    """Injiziert die Schwellwerte als :cfg_<key> in die run_params.

    Idempotent und nicht-überschreibend: ein explizit übergebener Wert (z.B. aus
    einem Formularfeld) gewinnt gegen die Projektkonfiguration.
    """
    run_params = dict(run_params or {})
    try:
        for key, value in get_thresholds(project_id, db).items():
            pname = f"cfg_{key}"
            if pname not in run_params:
                run_params[pname] = value
    except Exception:
        # Konfiguration darf einen Mapping-Lauf niemals verhindern.
        pass

    # Fixkosten als Laufzeit-Parameter: :cfg_kosten_monat (Summe zum Stichtag),
    # :cfg_kosten_<gruppe>_monat und :cfg_kosten_zeitraum (taggenau anteilig auf
    # den Auswertungszeitraum). Stichtag ist das "bis" des Laufs, sonst heute.
    try:
        bis = _parse_datum(run_params.get("bis")) or date.today()
        von = _parse_datum(run_params.get("von"))
        monat = kosten_monat(project_id, db, bis)
        run_params.setdefault("cfg_kosten_monat", monat["gesamt"])
        for gruppe, betrag in monat["gruppen"].items():
            run_params.setdefault(f"cfg_kosten_{gruppe}_monat", betrag)
        run_params.setdefault(
            "cfg_kosten_zeitraum",
            kosten_zeitraum(project_id, db, von, bis) if von else monat["gesamt"])
    except Exception:
        pass
    return run_params


def set_value(project_id, db, scope: str, key: str, value):
    from app.models.business_config import BusinessConfig
    row = (db.query(BusinessConfig)
             .filter(BusinessConfig.scope == scope, BusinessConfig.key == key,
                     BusinessConfig.project_id == project_id
                     if project_id is not None else BusinessConfig.project_id.is_(None))
             .first())
    if row is None:
        row = BusinessConfig(project_id=project_id, scope=scope, key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    return row


def reset_value(project_id, db, scope: str, key: str) -> bool:
    """Löscht die Überschreibung – der Standardwert gilt wieder."""
    from app.models.business_config import BusinessConfig
    q = db.query(BusinessConfig).filter(BusinessConfig.scope == scope,
                                        BusinessConfig.key == key)
    q = q.filter(BusinessConfig.project_id == project_id) if project_id is not None \
        else q.filter(BusinessConfig.project_id.is_(None))
    row = q.first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def is_default(project_id, db, key: str) -> bool:
    meta = _DEFAULTS_BY_KEY.get(key)
    if not meta:
        return False
    return get_thresholds(project_id, db).get(key) == meta["default"]

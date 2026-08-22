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


def get_costs(project_id, db) -> list[dict]:
    """Kostenregeln (Phase 2: kalkulatorischer Deckungsbeitrag)."""
    out = []
    for r in _rows(project_id, db, "cost"):
        v = r.value if isinstance(r.value, dict) else {}
        out.append({**v, "key": r.key})
    return out


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

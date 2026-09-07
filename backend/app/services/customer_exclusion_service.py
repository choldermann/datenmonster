"""Injiziert die Liste der ausgeschlossenen Kunden (verbundene Unternehmen, eigene
Firma) als gebundene Parameter in die run_params eines Mapping-Laufs.

Gesetzt werden:
  excluded_customers        – Liste der kKunde (interne JTL-IDs), evtl. leer
  excluded_customers_empty  – 1 wenn die Liste leer ist, sonst 0

Muster und Empty-Behandlung wie article_exclusion_service. Die betroffenen
SQL-Statements kombinieren beides empty-safe:
  AND (:excluded_customers_empty = 1 OR B.tKunde_kKunde NOT IN (:excluded_customers))

Wichtig: Die Liste FILTERT nicht automatisch alles. Sie steht als Parameter
bereit; jedes Mapping entscheidet selbst, ob es sie anwendet. Eine Umsatzsumme
soll die Konzernlieferung meist weiterhin enthalten – nur die Frage „wer kauft
das wirklich?" will sie draußen haben.
"""
from typing import Optional


def apply_customer_exclusions(run_params: Optional[dict], project_id, db,
                              mandant_id=None) -> dict:
    """Idempotent: ein vom Formular gesetzter Wert wird nicht überschrieben,
    nur das _empty-Flag konsistent gehalten.

    Mandantenfähig: kKunde ist eine interne ID der jeweiligen WaWi-Datenbank.
    Dieselbe Zahl bezeichnet in einer anderen JTL-Datenbank einen anderen Kunden,
    eine mandantenübergreifende Liste würde also die Falschen ausblenden.
    Alteinträge ohne Verbindung gehören dem Standard-Mandanten.
    """
    run_params = dict(run_params or {})

    if "excluded_customers" in run_params:
        existing = run_params.get("excluded_customers") or []
        run_params["excluded_customers_empty"] = 0 if existing else 1
        return run_params

    ids = []
    if project_id is not None and db is not None:
        try:
            from app.models.customer_exclusion import CustomerExclusion
            rows = (db.query(CustomerExclusion)
                    .filter(CustomerExclusion.project_id == project_id).all())
            if mandant_id is not None:
                from app.services import mandant_service
                ist_standard = mandant_service.standard(project_id, db) == mandant_id
                rows = [r for r in rows
                        if r.connection_id == mandant_id
                        or (r.connection_id is None and ist_standard)]
            ids = [r.k_kunde for r in rows]
        except Exception:
            ids = []

    run_params["excluded_customers"] = ids
    run_params["excluded_customers_empty"] = 0 if ids else 1
    return run_params

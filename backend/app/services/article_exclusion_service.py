"""Injiziert die projektbezogene Ausschlussliste (z.B. Europaletten) als gebundene
Parameter in die run_params eines Mapping-Laufs.

Gesetzt werden:
  excluded_articles        – Liste der kArtikel (interne JTL-IDs), evtl. leer
  excluded_articles_empty  – 1 wenn die Liste leer ist, sonst 0

Die betroffenen SQL-Statements kombinieren beides empty-safe, z.B.:
  AND (:excluded_articles_empty = 1 OR A.kArtikel NOT IN (:excluded_articles))
"""
from typing import Optional


def apply_article_exclusions(run_params: Optional[dict], project_id, db,
                             mandant_id=None) -> dict:
    """Idempotent: wenn excluded_articles bereits gesetzt ist (z.B. explizit vom
    Formular), wird nicht überschrieben – nur das _empty-Flag konsistent gehalten.

    Mandantenfähig: kArtikel ist eine interne ID der jeweiligen WaWi-Datenbank.
    Dieselbe Zahl bezeichnet in einer anderen JTL-Datenbank einen völlig anderen
    Artikel – eine mandantenübergreifende Ausschlussliste würde also stillschweigend
    die falschen Artikel aus der Statistik werfen. Deshalb zählt nur, was zu dieser
    Verbindung erfasst wurde; Alteinträge ohne Verbindung gehören dem Standard-
    Mandanten, weil es damals nur einen gab.
    """
    run_params = dict(run_params or {})

    if "excluded_articles" in run_params:
        existing = run_params.get("excluded_articles") or []
        run_params["excluded_articles_empty"] = 0 if existing else 1
        return run_params

    ids = []
    if project_id is not None and db is not None:
        try:
            from app.models.article_exclusion import ArticleExclusion
            rows = (db.query(ArticleExclusion)
                    .filter(ArticleExclusion.project_id == project_id).all())
            if mandant_id is not None:
                from app.services import mandant_service
                ist_standard = mandant_service.standard(project_id, db) == mandant_id
                rows = [r for r in rows
                        if r.connection_id == mandant_id
                        or (r.connection_id is None and ist_standard)]
            ids = [r.k_artikel for r in rows]
        except Exception:
            ids = []

    run_params["excluded_articles"] = ids
    run_params["excluded_articles_empty"] = 0 if ids else 1
    return run_params

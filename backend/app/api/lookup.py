"""
Lookup-API — lädt Auswahloptionen (Dropdown-Werte) aus einer JTL-DB.

Bewusst KEIN Client-SQL: der Client schickt nur eine vordefinierte `kind` +
die Verbindungs-ID. Die read-only Abfragen sind hier serverseitig hinterlegt.
Zugriff ist gegatet wie bei den Eingangsrechnungs-Endpunkten: Admins/interne
Editoren dürfen jede Verbindung, ein reiner Portal-Benutzer nur Verbindungen,
die in einem veröffentlichten Formular gebunden sind, auf das er Zugriff hat.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.form import Form as FormModel

router = APIRouter(prefix="/api/lookup", tags=["lookup"])

# Vordefinierte, read-only Abfragen. value/label sind die erwarteten Aliase.
# Schema kann je JTL-Version abweichen – bei Bedarf hier anpassen.
LOOKUP_QUERIES = {
    "warengruppe": "SELECT kWarengruppe AS value, cName AS label "
                   "FROM dbo.tWarengruppe ORDER BY cName",
    "kategorie":   "SELECT k.kKategorie AS value, ks.cName AS label "
                   "FROM dbo.tkategorie k "
                   "JOIN dbo.tkategoriesprache ks ON ks.kKategorie = k.kKategorie "
                   "WHERE ISNULL(ks.cName, '') <> '' "
                   "ORDER BY ks.cName",
    # Plattform-Familien (nTyp) – Unterkanäle (ebay.de, Amazon.de …, nInet=1)
    # werden über nTyp zusammengefasst; value = nTyp, gefiltert wird auf tPlattform.nTyp.
    "plattform":   "SELECT nTyp AS value, MIN(cName) AS label "
                   "FROM dbo.tPlattform WHERE nInet = 0 AND nTyp IS NOT NULL "
                   "GROUP BY nTyp ORDER BY MIN(cName)",
    # Kunden für die Vergleichsgruppe des Abfrage-Generators. Auf Kunden mit
    # Bewegung in 24 Monaten begrenzt (3.301 statt 22.495) – eine Auswahlliste
    # über den ganzen Stamm wäre unbedienbar. Name wie überall aus Firma plus
    # Firmenzusatz, weil cFirma bei PPS meist nur die Gattung trägt.
    "kunde":       "SELECT k.kKunde AS value, "
                   "  ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(a.cFirma,'')) "
                   "    + CASE WHEN ISNULL(a.cZusatz,'') = '' "
                   "      OR CHARINDEX(LTRIM(RTRIM(a.cZusatz)), ISNULL(a.cFirma,'')) > 0 THEN '' "
                   "      ELSE ' ' + LTRIM(RTRIM(a.cZusatz)) END), ''), "
                   "    LTRIM(RTRIM(ISNULL(a.cVorname,'') + ' ' + ISNULL(a.cName,'')))) "
                   "  + ISNULL(' – ' + NULLIF(a.cOrt,''), '') AS label "
                   "FROM dbo.tKunde k "
                   "JOIN dbo.tAdresse a ON a.kKunde = k.kKunde AND a.nTyp = 1 AND a.nStandard = 1 "
                   "WHERE EXISTS (SELECT 1 FROM dbo.tBestellung b "
                   "              WHERE b.tKunde_kKunde = k.kKunde "
                   "                AND b.dErstellt >= DATEADD(MONTH, -24, GETDATE())) "
                   "ORDER BY 2",
    # Lieferanten (Einkauf). Gelöschte/inaktive (cAktiv = 'N') bleiben außen vor.
    # cFirma trägt oft nur ein Kürzel, der Rest steckt im Firmenzusatz –
    # deshalb dasselbe Zusammensetzen wie in den Cockpit-Abfragen
    # (backend/firmenzusatz.py). Der Filterwert bleibt kLieferant.
    "lieferant":   "SELECT kLieferant AS value, "
                   "  LTRIM(RTRIM(ISNULL(cFirma,'')) + CASE WHEN ISNULL(cFirmenZusatz,'') = '' "
                   "  OR CHARINDEX(LTRIM(RTRIM(cFirmenZusatz)), ISNULL(cFirma,'')) > 0 THEN '' "
                   "  ELSE ' ' + LTRIM(RTRIM(cFirmenZusatz)) END) AS label "
                   "FROM dbo.tlieferant "
                   "WHERE ISNULL(cAktiv, 'Y') <> 'N' AND ISNULL(cFirma, '') <> '' "
                   "ORDER BY label",
    # Kundengruppen (Preisautomatik). Der Name geht UNVERÄNDERT zurück, auch mit
    # nachgestelltem Leerzeichen („ProLiberis Kitas ") – die Ameise bildet ihre
    # Spaltennamen aus genau diesem Feld, ein aufgeräumter Name träfe nicht.
    "kundengruppe": "SELECT kKundenGruppe AS value, cName AS label "
                    "FROM dbo.tkundenGruppe ORDER BY cName",
    # Versandarten (Versand). Der Dienstleister steckt im Namen der Versandart –
    # dbo.tVersand.cLogistiker ist in der Praxis leer.
    "versandart":  "SELECT kVersandArt AS value, cName AS label "
                   "FROM dbo.tVersandArt "
                   "WHERE ISNULL(cAktiv, 'Y') <> 'N' AND ISNULL(cName, '') <> '' "
                   "ORDER BY cName",
    # Artikel mit EK-Historie (Preisverlauf). Bewusst nur Artikel, für die es
    # überhaupt gebuchte Einkaufspreise gibt – sonst stünden Tausende Einträge
    # zur Auswahl, die nichts anzuzeigen hätten. Die Artikelnummer steht vorn,
    # damit die Tippsuche der Auswahlliste darauf greift.
    "artikel":     "SELECT A.kArtikel AS value, "
                   "  A.cArtNr + ISNULL(' – ' + NULLIF(AB.cName, ''), '') AS label "
                   "FROM dbo.tArtikel A "
                   "LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel "
                   "     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0 "
                   "WHERE A.cAktiv = 'Y' AND A.kVaterArtikel = 0 "
                   "  AND EXISTS (SELECT 1 FROM dbo.vArtikelHistorie H "
                   "              WHERE H.kArtikel = A.kArtikel AND H.cTyp = 'Eingang' "
                   "                AND ISNULL(H.fEKNetto, 0) > 0) "
                   "ORDER BY A.cArtNr",
    # Artikel mit Lagerbuchungen (Artikelhistorie im Lager-Cockpit). Anders als
    # „artikel“ auch ohne gebuchten EK und auch inaktive – deren Bewegungen will
    # man gerade nachschlagen.
    "artikel_historie": "SELECT A.kArtikel AS value, "
                        "  A.cArtNr + ISNULL(' – ' + NULLIF(AB.cName, ''), '') "
                        "  + CASE WHEN A.cAktiv = 'Y' THEN '' ELSE ' (inaktiv)' END AS label "
                        "FROM dbo.tArtikel A "
                        "LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel "
                        "     AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0 "
                        "WHERE EXISTS (SELECT 1 FROM dbo.vArtikelHistorie H "
                        "              WHERE H.kArtikel = A.kArtikel) "
                        "ORDER BY A.cArtNr",
    # Warenlager (Lagerliste im Lager-Cockpit). Mehrfachauswahl, leer = alle.
    "warenlager":  "SELECT kWarenLager AS value, cName AS label "
                   "FROM dbo.tWarenLager WHERE ISNULL(cName, '') <> '' ORDER BY cName",
    # Papinet-Partner (PapinetV2, eigene EGP-Datenbank, nicht JTL). Gesperrte
    # stehen mit drin – ihre alten Nachrichten sollen auffindbar bleiben.
    "papinet_partner": "SELECT PartnerID AS value, PartnerName + ' (' + PartnerCode + ')' "
                       "  + CASE WHEN IsActive = 0 THEN ' – gesperrt' ELSE '' END AS label "
                       "FROM dbo.tPapinetPartner ORDER BY PartnerName",
}


def _walk_connection_ids(obj, acc: set) -> None:
    """Sammelt alle connection_id-Werte irgendwo in einem Formular-Schema."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "connection_id" and v is not None:
                acc.add(str(v))
            else:
                _walk_connection_ids(v, acc)
    elif isinstance(obj, list):
        for it in obj:
            _walk_connection_ids(it, acc)


def _check_lookup_access(connection_id: int, user: User, db: Session) -> None:
    if getattr(user, "is_admin", False) or not getattr(user, "is_portal_only", False):
        return
    from app.api.portal import _check_portal_access
    forms = db.query(FormModel).filter(FormModel.published == True).all()
    for f in forms:
        try:
            _check_portal_access(f, user)
        except HTTPException:
            continue
        acc: set = set()
        _walk_connection_ids(f.schema or {}, acc)
        if str(connection_id) in acc:
            return
    raise HTTPException(403, "Kein Zugriff auf diese Verbindung")


MAX_SPALTENWERTE = 1000


def _feld_freigegeben(connection_id: int, table: str, column: str, user: User, db: Session) -> None:
    """Portal-Benutzer: Werte einer Spalte nur, wenn ein für ihn sichtbares, veröffentlichtes Cockpit genau
    diese Auswahlliste enthält – sonst könnte er über die Liste beliebige Spalten der Datenbank auslesen."""
    if getattr(user, "is_admin", False) or not getattr(user, "is_portal_only", False):
        return
    from app.api.portal import _check_portal_access
    for f in db.query(FormModel).filter(FormModel.published == True).all():
        try:
            _check_portal_access(f, user)
        except HTTPException:
            continue
        for fld in (f.schema or {}).get("fields") or []:
            c = fld.get("config") or {}
            if (fld.get("type") == "db_dropdown" and c.get("kind") == "spalte" and c.get("table") == table
                    and c.get("column") == column and str(c.get("connection_id")) == str(connection_id)):
                return
    raise HTTPException(403, "Kein Zugriff auf diese Auswahlliste")


def _spalten_sql(db: Session, connection_id: int, table: str, column: str) -> str:
    """Werte einer Spalte (Baukasten „im Cockpit wählbar“). Namen nur aus dem Schema-Cache, gequotet."""
    from app.models.dataset import DbConnection as _DBC
    from app.services.baukasten.uebersetzer import Dialekt, Schema
    from app.services.schema_cache_service import get_cached_schema
    conn = db.query(_DBC).filter(_DBC.id == connection_id).first()
    if conn is None:
        raise HTTPException(404, "Verbindung nicht gefunden")
    schema = Schema(get_cached_schema(conn) or {})
    if table not in schema.tabellen or column not in [s.name for s in schema.tabellen[table]]:
        raise HTTPException(400, "Tabelle oder Spalte gibt es in dieser Datenbank nicht")
    d = Dialekt(conn.db_type)
    c, t = d.q(column), d.tabelle(table)
    if d.name == "mssql":
        return (f"SELECT DISTINCT TOP ({MAX_SPALTENWERTE}) {c} AS value, {c} AS label FROM {t} "
                f"WHERE {c} IS NOT NULL ORDER BY 1")
    return f"SELECT DISTINCT {c} AS value, {c} AS label FROM {t} WHERE {c} IS NOT NULL ORDER BY 1 LIMIT {MAX_SPALTENWERTE}"


@router.get("/options")
def options(connection_id: int, kind: str, table: str | None = None, column: str | None = None,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Liefert [{value, label}, ...] für eine vordefinierte Lookup-Art – oder („spalte“) die Werte einer Spalte."""
    _check_lookup_access(connection_id, user, db)
    if kind == "spalte":
        if not table or not column:
            raise HTTPException(400, "Tabelle und Spalte fehlen")
        _feld_freigegeben(connection_id, table, column, user, db)
        sql = _spalten_sql(db, connection_id, table, column)
    else:
        sql = LOOKUP_QUERIES.get(kind)
    if not sql:
        raise HTTPException(400, f"Unbekannte Lookup-Art: {kind}")

    # Die Auswahlliste eines Filters muss aus derselben WaWi kommen wie die Zahlen
    # daneben – sonst wählt man einen Kunden, den es im aktiven Mandanten nicht gibt.
    from app.models.dataset import DbConnection as _DBC
    from app.services import mandant_service
    _conn = db.query(_DBC).filter(_DBC.id == connection_id).first()
    if _conn is not None:
        _aktiv = mandant_service.aktiver(_conn.project_id, user, db)
        if _aktiv and connection_id in mandant_service.austauschbare_ids(_conn.project_id, db):
            connection_id = _aktiv

    import pandas as pd
    import sqlalchemy as sa
    from app.services.sql_helpers import _get_sql_engine
    try:
        engine = _get_sql_engine(connection_id)
        df = pd.read_sql(sa.text(sql), engine)
    except Exception as e:
        raise HTTPException(502, f"Abfrage fehlgeschlagen: {str(e)[:200]}")
    return {"options": [
        {"value": str(r["value"]), "label": str(r["label"])}
        for _, r in df.iterrows()
        if kind != "spalte" or str(r["value"]).strip() != ""
    ]}

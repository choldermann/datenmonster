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


@router.get("/options")
def options(connection_id: int, kind: str,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Liefert [{value, label}, ...] für eine vordefinierte Lookup-Art."""
    sql = LOOKUP_QUERIES.get(kind)
    if not sql:
        raise HTTPException(400, f"Unbekannte Lookup-Art: {kind}")
    _check_lookup_access(connection_id, user, db)

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
    ]}

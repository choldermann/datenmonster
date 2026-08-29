"""Preisautomatik: Läufe, Vorschläge, Ameise-Export und Soll/Ist-Kontrolle.

Der Ablauf ist bewusst in Schritte zerlegt, die einzeln nachvollziehbar sind:

    lauf()      Kandidaten holen → Regel zuordnen → Preis rechnen →
                Sicherheitsnetz → Vorschläge ins Journal
    freigeben() eine bewusste Handlung (oder auto_freigabe des Regelwerks)
    ameise_csv() erzeugt die Importdatei; der Zustand bleibt „freigegeben“
    kontrolle() liest die echten Preise aus der Wawi und setzt erst DANN
                „angewandt“ – wir glauben keinem Import, wir prüfen ihn

Gerechnet wird deterministisch, nichts wird geschätzt. Angewandt wird über
SONDERPREISE, nie über den Grundpreis (siehe doku/jtl-preis-schema.md).
"""
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Optional

import sqlalchemy as sa

from app.models.preisregel import (PriceRuleset, PriceRule, PriceRun, PriceChange,
                                   OFFENE_ZUSTAENDE)

logger = logging.getLogger(__name__)

# Spalten, die das Kandidaten-Mapping liefern muss.
PFLICHTSPALTEN = ("kArtikel", "ArtNr", "TageOhneAbgang", "kKundenGruppe",
                  "kShop", "PreisAktuell")


# ── Hilfen ───────────────────────────────────────────────────────────────────

def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _int(v, standard=0) -> int:
    n = _num(v)
    return standard if n is None else int(n)


def _jetzt():
    return datetime.now(timezone.utc)


def _resolve_mapping(db, project_id, name: str):
    from app.models.mapping import Mapping
    q = db.query(Mapping).filter(Mapping.name == name)
    if project_id is not None:
        q = q.filter(Mapping.project_id == project_id)
    return q.first()


def kandidaten(db, ruleset: PriceRuleset, stichtag: date, tage_min: int,
               shops: Optional[list] = None) -> list:
    """Führt das Kandidaten-Mapping in der Wawi des Regelwerks aus.

    SQL bleibt SQL: Was ein Ladenhüter ist, steht in einem ganz normalen Mapping
    und ist im Editor änderbar – nicht hier im Code."""
    from app.services.mapping_service import MappingContext, execute_mapping
    from app.services import mandant_service

    m = _resolve_mapping(db, ruleset.project_id, ruleset.kandidaten_mapping)
    if not m:
        raise ValueError(f"Kandidaten-Auswertung „{ruleset.kandidaten_mapping}“ "
                         f"ist in diesem Projekt nicht installiert.")
    ctx = MappingContext.from_orm(m)
    # shops als Liste: leer heißt „alle Kanäle" (Muster :name / :name_empty).
    ctx.run_params = {"bis": stichtag, "tage_min": tage_min, "shops": shops or []}
    mandant_service.verbindung_ersetzen(ctx, ruleset.connection_id, db, m.project_id)
    if not ctx.targets:
        raise ValueError("Kandidaten-Auswertung hat kein Ziel.")
    felder = ctx.targets[0].get("fields") or []
    res = execute_mapping(row_cap=5000, **ctx.to_execute_kwargs(felder, 5000))
    fehler = res.get("errors") or []
    rows = res.get("rows") or []
    if fehler and not rows:
        raise ValueError(f"Kandidaten-Auswertung fehlgeschlagen: {str(fehler[0])[:200]}")
    if rows:
        fehlt = [s for s in PFLICHTSPALTEN if s not in rows[0]]
        if fehlt:
            raise ValueError("Kandidaten-Auswertung liefert nicht alle Pflichtspalten "
                             f"(fehlt: {', '.join(fehlt)}).")
    return rows


# ── Regelauswertung ──────────────────────────────────────────────────────────

def _im_geltungsbereich(scope: dict, k: dict) -> Optional[str]:
    """Gibt den Ablehnungsgrund zurück – oder None, wenn der Artikel passt."""
    scope = scope or {}
    wg = scope.get("warengruppen") or []
    if wg and str(k.get("Warengruppe") or "") not in [str(x) for x in wg]:
        return "Warengruppe nicht im Geltungsbereich"
    aus = [str(x).strip() for x in (scope.get("artikel_ausschluss") or [])]
    if aus and str(k.get("ArtNr") or "").strip() in aus:
        return "Artikel steht auf der Ausschlussliste"
    min_bestand = _num(scope.get("min_bestand"))
    if min_bestand is not None and (_num(k.get("Bestand")) or 0) < min_bestand:
        return f"Bestand unter {min_bestand:g}"
    min_kapital = _num(scope.get("min_kapital"))
    if min_kapital is not None and (_num(k.get("GebundenesKapital")) or 0) < min_kapital:
        return f"gebundenes Kapital unter {min_kapital:g} €"
    return None


def _passende_regel(regeln: list, k: dict) -> Optional[PriceRule]:
    """Erste zutreffende Stufe gewinnt – die Liste ist absteigend sortiert, damit
    „90 Tage → 20 %“ die Stufe „30 Tage → 5 %“ schlägt."""
    tage = _num(k.get("TageOhneAbgang")) or 0
    for r in regeln:
        ab = _num((r.condition or {}).get("tage_ohne_verkauf_ab"))
        if ab is not None and tage >= ab:
            return r
    return None


def _neuer_preis(action: dict, preis_alt: float) -> Optional[float]:
    typ = (action or {}).get("typ", "rabatt_prozent")
    wert = _num((action or {}).get("wert"))
    if wert is None:
        return None
    if typ == "rabatt_prozent":
        return preis_alt * (1 - wert / 100.0)
    if typ == "rabatt_betrag":
        return preis_alt - wert
    if typ == "zielpreis":
        return wert
    return None


def _runden(preis: float, preisendung: Optional[str]) -> float:
    """Optionale Preisendung, z.B. „0.99“ → 8,7412 wird zu 8,99 (nächstkleinere
    Endung, damit der Rabatt nicht durch die Rundung verschwindet)."""
    endung = _num(preisendung)
    if endung is None:
        return round(preis, 2)
    ganz = int(preis)
    kandidat = ganz + endung
    if kandidat > preis:
        kandidat = ganz - 1 + endung
    return round(max(kandidat, 0.01), 2)


def _sicherheitsnetz(rs: PriceRuleset, k: dict, preis_neu: float):
    """Gibt (ok, grund) zurück. Ein abgelehnter Vorschlag wird als „verworfen“
    gespeichert, nicht stillschweigend übersprungen – sonst sieht niemand, dass
    die Regel an der Marge scheitert."""
    ek = _num(k.get("EKNetto"))
    if preis_neu is None or preis_neu <= 0:
        return False, "errechneter Preis ist 0 oder negativ"
    if rs.max_rabatt_prozent:
        alt = _num(k.get("PreisAktuell")) or 0
        if alt > 0 and (1 - preis_neu / alt) * 100 > rs.max_rabatt_prozent + 1e-9:
            return False, f"Rabatt über der Obergrenze von {rs.max_rabatt_prozent:g} %"
    if ek is None or ek <= 0:
        # Ohne Einstandspreis lässt sich die Marge nicht prüfen. Lieber kein
        # Vorschlag als ein ungeprüfter.
        if rs.nie_unter_ek or rs.min_marge_prozent:
            return False, "kein Einstandspreis hinterlegt – Marge nicht prüfbar"
        return True, None
    if rs.nie_unter_ek and preis_neu < ek:
        return False, f"läge unter dem Einstandspreis ({ek:.2f} €)"
    if rs.min_marge_prozent:
        marge = (preis_neu - ek) / preis_neu * 100 if preis_neu else 0
        if marge < rs.min_marge_prozent - 1e-9:
            return False, (f"Marge {marge:.1f} % unter dem Minimum von "
                           f"{rs.min_marge_prozent:g} %")
    return True, None


# ── Lauf ─────────────────────────────────────────────────────────────────────

def lauf(db, ruleset_id: int, user=None, triggered_by: str = "manuell",
         stichtag: Optional[date] = None) -> dict:
    rs = db.query(PriceRuleset).filter(PriceRuleset.id == ruleset_id).first()
    if not rs:
        raise ValueError("Regelwerk nicht gefunden")
    regeln = (db.query(PriceRule)
              .filter(PriceRule.ruleset_id == rs.id, PriceRule.active.is_(True))
              .order_by(PriceRule.sort.desc()).all())
    if not regeln:
        raise ValueError("Das Regelwerk hat keine aktive Stufe.")

    stichtag = stichtag or date.today()
    tage_min = min([_num((r.condition or {}).get("tage_ohne_verkauf_ab")) or 0
                    for r in regeln] or [0])
    run = PriceRun(ruleset_id=rs.id, project_id=rs.project_id,
                   connection_id=rs.connection_id, triggered_by=triggered_by,
                   params={"stichtag": str(stichtag), "tage_min": tage_min})
    db.add(run)
    db.commit()

    try:
        rows = kandidaten(db, rs, stichtag, int(tage_min),
                          [int(x) for x in (rs.shops or [])])
    except Exception as e:
        run.status, run.error, run.finished_at = "fehler", str(e)[:500], _jetzt()
        db.commit()
        raise

    gruppen = [int(g) for g in (rs.kundengruppen or [])]
    shops = [int(s) for s in (rs.shops or [0])]
    # Was für dieses Ziel schon offen ist, wird nicht erneut vorgeschlagen.
    offen, abgelehnt = set(), {}
    for c in db.query(PriceChange).filter(
            PriceChange.connection_id == rs.connection_id,
            PriceChange.ruleset_id == rs.id,
            PriceChange.zustand.in_(tuple(OFFENE_ZUSTAENDE) + ("verworfen",))).all():
        ziel = (c.k_artikel, c.k_kundengruppe, c.k_shop)
        if c.zustand == "verworfen":
            # Eine unveränderte Ablehnung gehört nicht jede Nacht neu ins Journal.
            # Ändert sich der Preis, ist der neue Eintrag dagegen eine Information.
            abgelehnt[ziel] = (c.rule_id, c.preis_alt, c.preis_neu)
        else:
            offen.add(ziel)

    vor, verw, gesehen = 0, 0, set()
    bis = datetime.combine(stichtag, datetime.min.time()) + timedelta(days=rs.laufzeit_tage or 30)
    for k in rows:
        kg, shop = _int(k.get("kKundenGruppe")), _int(k.get("kShop"))
        if gruppen and kg not in gruppen:
            continue
        if shops and shop not in shops:
            continue
        art = _int(k.get("kArtikel"))
        ziel = (art, kg, shop)
        if ziel in offen or ziel in gesehen:
            continue
        gesehen.add(ziel)

        grund = _im_geltungsbereich(rs.scope, k)
        if grund:
            continue                      # gehört gar nicht dazu – kein Journaleintrag
        if _int(k.get("SonderpreisAktiv")) == 1:
            continue                      # von Hand gepflegte Aktion nicht anfassen

        regel = _passende_regel(regeln, k)
        if not regel:
            continue
        alt = _num(k.get("PreisAktuell"))
        if alt is None or alt <= 0:
            continue                      # ohne Vorher-Wert kein Vorschlag

        roh = _neuer_preis(regel.action, alt)
        neu = _runden(roh, rs.preisendung) if roh is not None else None
        ok, ablehnung = _sicherheitsnetz(rs, k, neu)
        if not ok and abgelehnt.get(ziel) == (regel.id, alt, neu):
            continue                      # dieselbe Ablehnung steht schon im Journal
        tage = _int(k.get("TageOhneAbgang"))
        stufe = _num((regel.condition or {}).get("tage_ohne_verkauf_ab"))
        text = (f"{tage} Tage ohne Verkauf, Stufe ab {stufe:g} Tagen"
                if stufe is not None else f"{tage} Tage ohne Verkauf")
        if _int(k.get("NieVerkauft")) == 1:
            text += " (nie verkauft, gerechnet ab Lagerzugang)"

        db.add(PriceChange(
            run_id=run.id, ruleset_id=rs.id, rule_id=regel.id,
            project_id=rs.project_id, connection_id=rs.connection_id,
            k_artikel=art, c_artnr=str(k.get("ArtNr") or ""),
            artikelname=str(k.get("Artikel") or "")[:250],
            k_kundengruppe=kg, kundengruppe=str(k.get("Kundengruppe") or ""),
            k_shop=shop, shop_name=str(k.get("Shop") or ""),
            preis_alt=alt, preis_alt_quelle=str(k.get("PreisQuelle") or ""),
            preis_neu=neu, ek_netto=_num(k.get("EKNetto")),
            steuersatz=_num(k.get("Steuersatz")),
            gueltig_von=datetime.combine(stichtag, datetime.min.time()),
            gueltig_bis=bis,
            zustand=("verworfen" if not ok else
                     "freigegeben" if rs.auto_freigabe else "vorgeschlagen"),
            begruendung=(text if ok else f"{text} – abgelehnt: {ablehnung}"),
        ))
        if ok:
            vor += 1
        else:
            verw += 1

    run.kandidaten, run.vorschlaege, run.verworfen = len(rows), vor, verw
    run.status, run.finished_at = "fertig", _jetzt()
    db.commit()
    return {"run_id": run.id, "kandidaten": len(rows), "vorschlaege": vor,
            "verworfen": verw}


# ── Zustandswechsel ──────────────────────────────────────────────────────────

def zustand_setzen(db, ids: list, neuer: str, user=None) -> int:
    q = db.query(PriceChange).filter(PriceChange.id.in_(ids or []))
    n = 0
    for c in q.all():
        if neuer == "freigegeben" and c.zustand != "vorgeschlagen":
            continue
        c.zustand = neuer
        c.updated_at = _jetzt()
        n += 1
    db.commit()
    return n


# ── Ameise-Export ────────────────────────────────────────────────────────────

# Die Ameise importiert Preise ARTIKELWEISE: eine Zeile je Artikel, je
# Kundengruppe eine eigene Spalte. Das Journal führt dagegen eine Zeile je
# Artikel × Gruppe × Shop – der Export dreht das quer. Spaltennamen 1:1 aus
# einem echten Artikelstammdaten-Export derselben Wawi:
#
#   Sonderpreise aktivieren vom (Startdatum)      -> tArtikelSonderpreis.dStart
#   Bis einschließlich (Enddatum)                 -> tArtikelSonderpreis.dEnde
#   Sonderpreise: <Gruppe> netto                  -> kShop = 0 (alle Kanäle)
#   Verkaufskanal [<Shop>]: Sonderpreis: <Gruppe> netto  -> kShop > 0
#
# Zwei Fallen: Start- und Enddatum stehen je ARTIKEL (wie in der Wawi, wo
# tArtikelSonderpreis der Kopf ist), nicht je Gruppe. Und die Kanalvariante
# heißt „Sonderpreis" im Singular, die Wawi-Variante „Sonderpreise" im Plural.
SPALTE_START = "Sonderpreise aktivieren vom (Startdatum)"
SPALTE_ENDE  = "Bis einschließlich (Enddatum)"


def _spalte_sonderpreis(gruppe: str, shop_name: str) -> str:
    """Der Gruppenname geht UNVERÄNDERT in die Überschrift, auch mit
    nachgestelltem Leerzeichen („ProLiberis Kitas ") – die Ameise bildet ihre
    Spaltennamen aus genau diesem Feld."""
    if shop_name:
        return f"Verkaufskanal [{shop_name}]: Sonderpreis: {gruppe} netto"
    return f"Sonderpreise: {gruppe} netto"


def _zahl(v) -> str:
    return "" if v is None else f"{v:.2f}".replace(".", ",")


def _datum(v) -> str:
    return v.strftime("%d.%m.%Y") if v else ""


def _ameise_text(posten: list) -> str:
    """Baut den Dateiinhalt in der Schreibweise der Ameise: UTF-8 ohne BOM, LF,
    Semikolon, jede Zeile endet auf ein Semikolon, Werte in Anführungszeichen,
    leere Felder bleiben wirklich leer, Dezimalkomma, Datum TT.MM.JJJJ."""
    def zelle(v):
        text = "" if v is None else str(v)
        return f'"{text}"' if text != "" else ""

    # Spaltensatz aus den vorkommenden Gruppen/Kanälen – in stabiler Reihenfolge.
    preisspalten, gesehen = [], set()
    for c in posten:
        name = _spalte_sonderpreis(c.kundengruppe or str(c.k_kundengruppe),
                                   c.shop_name or "")
        if name not in gesehen:
            gesehen.add(name)
            preisspalten.append(name)

    kopf = ["Artikelnummer", "Artikelname", SPALTE_START, SPALTE_ENDE] + preisspalten

    zeilen_je_artikel = {}
    for c in posten:
        z = zeilen_je_artikel.setdefault(c.c_artnr, {
            "Artikelnummer": c.c_artnr, "Artikelname": c.artikelname,
            SPALTE_START: _datum(c.gueltig_von), SPALTE_ENDE: _datum(c.gueltig_bis)})
        spalte = _spalte_sonderpreis(c.kundengruppe or str(c.k_kundengruppe),
                                     c.shop_name or "")
        if c.ruecknahme_von:
            # Rücknahme: kein neuer Preis, sondern ein Enddatum in der
            # Vergangenheit – damit endet die Aktion, ohne dass eine leere Zelle
            # interpretiert werden müsste.
            z[SPALTE_ENDE] = _datum(c.gueltig_bis)
            z[spalte] = _zahl(c.preis_alt)
        else:
            z[spalte] = _zahl(c.preis_neu)

    text = [";".join(zelle(k) for k in kopf) + ";"]
    for z in zeilen_je_artikel.values():
        text.append(";".join(zelle(z.get(k, "")) for k in kopf) + ";")
    return "\n".join(text) + "\n"


def ameise_csv(db, ruleset_id: int, ids: Optional[list], user) -> dict:
    """Erzeugt die Importdatei für die JTL-Ameise.

    Der Zustand bleibt bewusst „freigegeben“: Erzeugt heißt nicht importiert.
    Erst die Kontrolle (§kontrolle) setzt „angewandt“, und zwar anhand der
    echten Preise in der Wawi."""
    import os
    from app.services.file_export_service import build_export_path
    from app.models.export_file import ExportFile
    from app.models.project import Project

    rs = db.query(PriceRuleset).filter(PriceRuleset.id == ruleset_id).first()
    if not rs:
        raise ValueError("Regelwerk nicht gefunden")
    q = db.query(PriceChange).filter(PriceChange.ruleset_id == rs.id,
                                     PriceChange.zustand == "freigegeben")
    if ids:
        q = q.filter(PriceChange.id.in_(ids))
    posten = q.order_by(PriceChange.c_artnr, PriceChange.k_kundengruppe).all()
    if not posten:
        raise ValueError("Keine freigegebenen Preisänderungen zum Exportieren.")

    projekt = (db.query(Project).filter(Project.id == rs.project_id).first()
               if rs.project_id else None)
    pfad = build_export_path(getattr(user, "id", 0), getattr(projekt, "name", None),
                             "manual", f"ameise_sonderpreise_{rs.name}", "csv")
    # UTF-8 OHNE BOM – so exportiert die Ameise selbst.
    with open(pfad, "wb") as fh:
        fh.write(_ameise_text(posten).encode("utf-8"))

    datei = ExportFile(
        user_id=getattr(user, "id", 0), project_id=rs.project_id,
        project_name=getattr(projekt, "name", None), job_id=None,
        mapping_id=None, mapping_name=None,
        target_name=f"Preisautomatik – {rs.name}", file_path=pfad,
        file_name=os.path.basename(pfad), file_ext="csv",
        file_size=os.path.getsize(pfad), triggered_by="manual")
    db.add(datei)
    db.commit()
    db.refresh(datei)

    for c in posten:
        c.weg, c.export_file_id, c.updated_at = "ameise", datei.id, _jetzt()
    db.commit()
    return {"export_file_id": datei.id, "file_name": datei.file_name,
            "zeilen": len(posten)}


# ── Soll/Ist-Kontrolle ───────────────────────────────────────────────────────

IST_SQL = """
SELECT S.kArtikel, SP.kKundenGruppe, SP.kShop, SP.fNettoPreis, S.nAktiv, S.dEnde
FROM dbo.tArtikelSonderpreis S
JOIN dbo.tSonderpreise SP ON SP.kArtikelSonderpreis = S.kArtikelSonderpreis
WHERE S.kArtikel IN :artikel AND S.nAktiv = 1
  AND (S.nIstDatum = 0 OR (S.dStart <= GETDATE() AND S.dEnde >= GETDATE()))
"""


def kontrolle(db, ruleset_id: int, ids: Optional[list] = None,
              toleranz: float = 0.005) -> dict:
    """Liest die echten Sonderpreise aus der Wawi und gleicht sie mit dem ab, was
    wir angewiesen haben. Erst hier wird aus „freigegeben“ ein „angewandt“ –
    egal ob über die Ameise oder direkt geschrieben."""
    from app.services.mapping_service import _get_sql_engine

    rs = db.query(PriceRuleset).filter(PriceRuleset.id == ruleset_id).first()
    if not rs:
        raise ValueError("Regelwerk nicht gefunden")
    q = db.query(PriceChange).filter(
        PriceChange.ruleset_id == rs.id,
        PriceChange.zustand.in_(("freigegeben", "angewandt")))
    if ids:
        q = q.filter(PriceChange.id.in_(ids))
    posten = q.all()
    if not posten:
        return {"geprueft": 0, "angewandt": 0, "fehlt": 0, "abweichend": 0}

    artikel = sorted({c.k_artikel for c in posten})
    engine = _get_sql_engine(rs.connection_id)
    with engine.connect() as con:
        ist = con.execute(sa.text(IST_SQL).bindparams(
            sa.bindparam("artikel", expanding=True)), {"artikel": artikel}).fetchall()
    gefunden = {(int(r[0]), int(r[1]), int(r[2])): float(r[3]) for r in ist}

    zaehler = {"angewandt": 0, "fehlt": 0, "abweichend": 0}
    for c in posten:
        wert = gefunden.get((c.k_artikel, c.k_kundengruppe, c.k_shop))
        c.kontrolliert_am, c.ist_preis = _jetzt(), wert
        if c.ruecknahme_von:
            # Eine Rücknahme ist erfolgreich, wenn KEIN Sonderpreis mehr läuft.
            if wert is None:
                c.abweichung, c.zustand = "ok", "angewandt"
                c.angewandt_am = c.angewandt_am or _jetzt()
                # Jetzt – und erst jetzt – ist der ursprüngliche Rabatt auch im
                # Betrieb beendet.
                original = db.query(PriceChange).filter(
                    PriceChange.id == c.ruecknahme_von).first()
                if original is not None and original.zustand == "angewandt":
                    original.zustand, original.updated_at = "zurueckgenommen", _jetzt()
                zaehler["angewandt"] += 1
            else:
                c.abweichung = "abweichend"
                zaehler["abweichend"] += 1
        elif wert is None:
            c.abweichung = "fehlt"
            if c.zustand == "angewandt":
                # War schon angewandt und ist nun weg – z.B. Aktion abgelaufen
                # oder von Hand entfernt. Nicht stillschweigend übergehen.
                c.zustand = "zurueckgenommen"
            zaehler["fehlt"] += 1
        elif abs(wert - (c.preis_neu or 0)) <= toleranz:
            c.abweichung, c.zustand = "ok", "angewandt"
            c.angewandt_am = c.angewandt_am or _jetzt()
            zaehler["angewandt"] += 1
        else:
            c.abweichung = "abweichend"
            zaehler["abweichend"] += 1
        c.updated_at = _jetzt()
    db.commit()
    return {"geprueft": len(posten), **zaehler}


# ── Rücknahme ────────────────────────────────────────────────────────────────

def ruecknahme(db, ids: list, user=None, zustand: str = "freigegeben",
               grund: Optional[str] = None) -> dict:
    """Nimmt angewandte Änderungen zurück – nicht durch Löschen, sondern durch
    einen neuen Journaleintrag, der den Sonderpreis beendet. Der Export dieser
    Einträge trägt ein Enddatum von gestern.

    Der Originaleintrag bleibt bewusst auf „angewandt": In der Wawi läuft der
    Rabatt weiter, bis die Gegenbuchung dort angekommen ist. Erst die Kontrolle
    setzt ihn auf „zurückgenommen" – sonst behauptet das Journal etwas, das im
    Betrieb noch nicht stimmt."""
    posten = db.query(PriceChange).filter(
        PriceChange.id.in_(ids or []),
        PriceChange.zustand == "angewandt").all()
    # Wofür schon eine Gegenbuchung offen ist, wird nicht zweimal zurückgenommen.
    laufend = {r.ruecknahme_von for r in db.query(PriceChange).filter(
        PriceChange.ruecknahme_von.in_([c.id for c in posten] or [0]),
        PriceChange.zustand.in_(OFFENE_ZUSTAENDE)).all()}
    gestern = datetime.now() - timedelta(days=1)
    n = 0
    for c in posten:
        if c.id in laufend:
            continue
        db.add(PriceChange(
            run_id=None, ruleset_id=c.ruleset_id, rule_id=c.rule_id,
            project_id=c.project_id, connection_id=c.connection_id,
            k_artikel=c.k_artikel, c_artnr=c.c_artnr, artikelname=c.artikelname,
            k_kundengruppe=c.k_kundengruppe, kundengruppe=c.kundengruppe,
            k_shop=c.k_shop, shop_name=c.shop_name,
            preis_alt=c.preis_neu, preis_alt_quelle="sonderpreis",
            preis_neu=c.preis_alt, ek_netto=c.ek_netto, steuersatz=c.steuersatz,
            gueltig_von=c.gueltig_von, gueltig_bis=gestern,
            zustand=zustand, ruecknahme_von=c.id,
            begruendung=grund or f"Rücknahme der Änderung #{c.id}"))
        n += 1
    db.commit()
    return {"zurueckgenommen": n}


# ── Rabatt endet, wenn der Artikel wieder läuft ──────────────────────────────

VERKAUF_SQL = """
SELECT H.kArtikel, SUM(-H.fAnzahl) AS Menge
FROM dbo.vArtikelHistorie H
WHERE H.cTyp = 'Ausgang' AND H.cBuchungsart = 'Warenausgang'
  AND H.kArtikel IN :artikel AND H.dGebucht >= :seit
GROUP BY H.kArtikel
"""


def wiederverkauf(db, ruleset_id: int) -> dict:
    """Beendet Rabatte für Artikel, die sich seit Beginn der Aktion wieder
    verkauft haben.

    Ein Ladenhüter, der wieder anzieht, braucht den Nachlass nicht mehr – und
    jeder weitere Tag kostet Marge. Ob und ab welcher Menge das greift, steht am
    Regelwerk; ohne den Schalter passiert nichts.

    Die Gegenbuchung folgt derselben Regel wie ein neuer Vorschlag: Ist
    `auto_freigabe` gesetzt, ist sie sofort exportierbar, sonst wartet sie auf
    eine Freigabe."""
    from app.services.mapping_service import _get_sql_engine

    rs = db.query(PriceRuleset).filter(PriceRuleset.id == ruleset_id).first()
    if not rs:
        raise ValueError("Regelwerk nicht gefunden")
    if not rs.ende_bei_verkauf:
        return {"geprueft": 0, "beendet": 0, "aus": True}

    aktiv = db.query(PriceChange).filter(
        PriceChange.ruleset_id == rs.id,
        PriceChange.zustand == "angewandt",
        PriceChange.ruecknahme_von.is_(None)).all()
    if not aktiv:
        return {"geprueft": 0, "beendet": 0}

    schwelle = float(rs.ende_ab_menge or 1)
    engine = _get_sql_engine(rs.connection_id)
    # Ein Lauf legt alle Änderungen mit demselben Startdatum an – nach Datum
    # gruppieren spart die Abfrage je Artikel.
    nach_datum: dict = {}
    for c in aktiv:
        nach_datum.setdefault(c.gueltig_von, []).append(c)

    verkauft: dict = {}
    with engine.connect() as con:
        for seit, posten in nach_datum.items():
            artikel = sorted({c.k_artikel for c in posten})
            zeilen = con.execute(
                sa.text(VERKAUF_SQL).bindparams(sa.bindparam("artikel", expanding=True)),
                {"artikel": artikel, "seit": seit or datetime(1990, 1, 1)}).fetchall()
            for r in zeilen:
                verkauft[(seit, int(r[0]))] = float(r[1] or 0)

    zustand = "freigegeben" if rs.auto_freigabe else "vorgeschlagen"
    beendet = 0
    for c in aktiv:
        menge = verkauft.get((c.gueltig_von, c.k_artikel), 0.0)
        if menge < schwelle:
            continue
        erg = ruecknahme(db, [c.id], zustand=zustand,
                         grund=(f"seit Rabattbeginn {menge:g} Stück verkauft "
                                f"(Schwelle {schwelle:g}) – Rabatt wird beendet"))
        beendet += erg["zurueckgenommen"]
    return {"geprueft": len(aktiv), "beendet": beendet}

# ── Nachtlauf ────────────────────────────────────────────────────────────────

def nachtlauf(db, ruleset_id: int, triggered_by: str = "scheduler") -> dict:
    """Ein Nachtlauf macht zwei Dinge, in dieser Reihenfolge:

    1. **Kontrolle** der offenen und angewandten Änderungen. Erst danach steht
       fest, was gestern wirklich in der Wawi angekommen ist und was inzwischen
       ausgelaufen ist – ein Bericht vor der Kontrolle wäre von gestern.
    2. **Lauf**: neue Vorschläge. Angewandt wird nichts; ohne Freigabe passiert
       im Betrieb nichts, auch wenn die Automatik jede Nacht denkt.

    Ausgehende Post nur, wenn Empfänger eingetragen sind UND es etwas zu sagen
    gibt.
    """
    rs = db.query(PriceRuleset).filter(PriceRuleset.id == ruleset_id).first()
    if not rs:
        raise ValueError("Regelwerk nicht gefunden")

    bericht = {"ruleset_id": rs.id, "name": rs.name, "kontrolle": None,
               "wiederverkauf": None, "lauf": None, "mail": None, "fehler": None}
    try:
        bericht["kontrolle"] = kontrolle(db, rs.id)
        # Zwischen Kontrolle und neuem Lauf: Erst wissen wir, was wirklich aktiv
        # ist; dann beenden wir, was sich wieder verkauft; und erst danach wird
        # neu vorgeschlagen – sonst schlüge der Lauf einen Artikel vor, dessen
        # Rabatt in derselben Nacht endet.
        bericht["wiederverkauf"] = wiederverkauf(db, rs.id)
        bericht["lauf"] = lauf(db, rs.id, triggered_by=triggered_by)
        rs.last_status = "success"
        rs.last_message = _bericht_zeile(bericht)
    except Exception as e:
        bericht["fehler"] = str(e)[:400]
        rs.last_status = "error"
        rs.last_message = bericht["fehler"]
    rs.last_run_at = _jetzt()
    db.commit()

    try:
        bericht["mail"] = _bericht_senden(db, rs, bericht)
    except Exception as e:            # ein Mailproblem darf den Lauf nicht kippen
        logger.warning(f"Preisautomatik: Bericht nicht versendet: {e}")
        bericht["mail"] = {"sent": False, "grund": str(e)[:200]}
    return bericht


def _bericht_zeile(b: dict) -> str:
    k = b.get("kontrolle") or {}
    l = b.get("lauf") or {}
    w = b.get("wiederverkauf") or {}
    text = (f"{l.get('vorschlaege', 0)} neue Vorschläge, "
            f"{l.get('verworfen', 0)} abgelehnt; Kontrolle: "
            f"{k.get('angewandt', 0)} angekommen, {k.get('fehlt', 0)} offen, "
            f"{k.get('abweichend', 0)} abweichend")
    if w.get("beendet"):
        text += f"; {w['beendet']} Rabatte beendet (wieder verkauft)"
    return text


def offene_zahlen(db, ruleset_id: int) -> dict:
    """Was gerade auf jemanden wartet – Grundlage für Bericht und Oberfläche."""
    from sqlalchemy import func
    zahlen = dict(db.query(PriceChange.zustand, func.count())
                  .filter(PriceChange.ruleset_id == ruleset_id)
                  .group_by(PriceChange.zustand).all())
    nicht_angekommen = (db.query(func.count(PriceChange.id))
                        .filter(PriceChange.ruleset_id == ruleset_id,
                                PriceChange.zustand == "freigegeben",
                                PriceChange.abweichung.in_(("fehlt", "abweichend")))
                        .scalar() or 0)
    aeltester = (db.query(func.min(PriceChange.created_at))
                 .filter(PriceChange.ruleset_id == ruleset_id,
                         PriceChange.zustand == "vorgeschlagen").scalar())
    return {"vorgeschlagen": zahlen.get("vorgeschlagen", 0),
            "freigegeben": zahlen.get("freigegeben", 0),
            "angewandt": zahlen.get("angewandt", 0),
            "nicht_angekommen": nicht_angekommen,
            "aeltester_vorschlag": aeltester.isoformat() if aeltester else None}


def _bericht_senden(db, rs: PriceRuleset, bericht: dict) -> dict:
    """Verschickt den Tagesbericht – aber nur, wenn es etwas zu berichten gibt.

    Eine Mail „0 Vorschläge, alles in Ordnung" jede Nacht bringt niemanden dazu,
    die nächste zu lesen."""
    from app.services.email_service import send_email

    ziele = [e.strip() for e in (rs.email_to or "").replace(";", ",").split(",")
             if e.strip()]
    if not ziele:
        return {"sent": False, "grund": "keine Empfänger"}

    offen = offene_zahlen(db, rs.id)
    l = bericht.get("lauf") or {}
    if bericht.get("fehler") is None and not l.get("vorschlaege") \
            and not offen["vorgeschlagen"] and not offen["nicht_angekommen"]:
        return {"sent": False, "grund": "nichts zu berichten"}

    if bericht.get("fehler"):
        betreff = f"Preisautomatik „{rs.name}“: Lauf fehlgeschlagen"
        zeilen = [f"Der nächtliche Lauf ist gescheitert:", "", bericht["fehler"]]
    else:
        betreff = (f"Preisautomatik „{rs.name}“: {offen['vorgeschlagen']} "
                   f"Vorschläge warten auf Freigabe")
        k = bericht.get("kontrolle") or {}
        zeilen = [
            f"Neu vorgeschlagen: {l.get('vorschlaege', 0)}",
            f"Durch das Sicherheitsnetz abgelehnt: {l.get('verworfen', 0)}",
            "",
            f"Warten auf Freigabe: {offen['vorgeschlagen']}",
            f"Freigegeben, noch nicht in der Wawi: {offen['freigegeben']}",
            f"Aktive Rabatte: {offen['angewandt']}",
        ]
        w = bericht.get("wiederverkauf") or {}
        if w.get("beendet"):
            zeilen += ["", f"Beendet, weil wieder verkauft: {w['beendet']} "
                           f"(von {w.get('geprueft', 0)} laufenden Rabatten)"]
        if offen["nicht_angekommen"]:
            zeilen += ["",
                       f"ACHTUNG: {offen['nicht_angekommen']} freigegebene Änderungen "
                       "sind nicht in der Wawi angekommen oder weichen ab. "
                       "Wurde die Datei importiert?"]
        if k:
            zeilen += ["", f"Kontrolle: {k.get('angewandt', 0)} angekommen, "
                           f"{k.get('fehlt', 0)} nicht gefunden, "
                           f"{k.get('abweichend', 0)} abweichend."]
        zeilen += ["", "Angewandt wird nichts ohne Freigabe."]

    send_email(to=", ".join(ziele), subject=betreff, body="\n".join(zeilen), db=db)
    return {"sent": True, "empfaenger": ziele}

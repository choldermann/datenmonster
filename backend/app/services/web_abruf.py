"""
Web-Abruf als gespeicherter Stand – Grundlage der Preisbeobachtung.

Eine Web-Quelle (doc_html) wird nicht bei jeder Vorschau neu aus dem Netz geholt,
sondern beim „Aktualisieren“ bzw. nach Zeitplan: alle Seiten abrufen, mit dem
letzten Stand vergleichen und speichern. Mappings und Warnregeln lesen dann den
gespeicherten Stand.

Vergleichsspalten je Zeile (Schlüssel: Einstellung „schluessel“, sonst
quelle_url + EAN/SKU/MPN/Name):
  abgerufen_am       Zeitpunkt des Abrufs
  status             neu | geändert | gleich | weg
  preis_vorher       Preis beim letzten Abruf
  aenderung          preis - preis_vorher
  aenderung_prozent  in %, gerundet auf 2 Stellen
„weg“ = beim letzten Mal da, diesmal nicht gefunden (Zeile mit altem Inhalt).

Verlauf „ja“: alle Abrufe bleiben im Dataset (je abgerufen_am).
Verlauf „nein“: nur der letzte Abruf (mit dem Vergleich zum vorigen).
"""
import logging
import os
import threading
from datetime import datetime, timezone
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)

WEB_TYPEN = {"doc_html"}
VERGLEICH = ["abgerufen_am", "status", "preis_vorher", "aenderung", "aenderung_prozent"]
_laufend = set()
_sperre = threading.Lock()


def ist_web_dataset(ds) -> bool:
    return (ds.file_type or "") in WEB_TYPEN


def web_plugin(file_type: str):
    """Leser zur Web-Quelle – auch ohne geladene Plugin-Registry (Thread, Test)."""
    from app.plugins.registry import registry
    plugin = registry.get_source(file_type)
    if plugin is None and file_type == "doc_html":
        from app.plugins.builtin.web.html_reader import HtmlDocumentSource
        plugin = HtmlDocumentSource()
    if plugin is None:
        raise ValueError(f"Keine Web-Quelle „{file_type}“")
    return plugin


def _schluessel(df: pd.DataFrame, config: dict) -> List[str]:
    eigen = [s.strip() for s in str(config.get("schluessel") or "").split(",") if s.strip()]
    if eigen:
        fehlt = [s for s in eigen if s not in df.columns]
        if fehlt:
            raise ValueError(f"Schlüssel-Spalte(n) fehlen im Ergebnis: {', '.join(fehlt)}")
        return eigen
    teile = ["quelle_url"] if "quelle_url" in df.columns else []
    for k in ("gtin", "sku", "mpn", "name"):
        if k in df.columns and df[k].notna().any() and (df[k].astype(str).str.strip() != "").any():
            teile.append(k)
            break
    return teile or list(df.columns[:2])


def _key(df: pd.DataFrame, spalten: List[str]) -> pd.Series:
    return df[spalten].astype(str).agg("\x1f".join, axis=1)


def vergleichen(neu: pd.DataFrame, alt: pd.DataFrame, config: dict, zeitpunkt) -> pd.DataFrame:
    """Neuen Abruf mit dem letzten vergleichen → neue Zeilen + „weg“-Zeilen."""
    neu = neu.copy()
    neu["abgerufen_am"] = zeitpunkt
    if neu.empty:
        schl = []
    else:
        schl = _schluessel(neu, config)
        neu = neu.drop_duplicates(subset=schl, keep="first")
    preis = "preis" if "preis" in neu.columns else None
    if preis:
        # „£51.77“, „12,90 €“ aus Klick-Selektoren → Zahl (produkte liefert schon Zahlen)
        from app.plugins.builtin.web.produktdaten import preis_zahl
        neu[preis] = neu[preis].map(lambda v: preis_zahl(v) if not isinstance(v, (int, float)) else v)
        neu[preis] = pd.to_numeric(neu[preis], errors="coerce")

    if alt is None or alt.empty or not schl or any(s not in alt.columns for s in schl):
        neu["status"] = "neu"
        neu["preis_vorher"] = None
        neu["aenderung"] = None
        neu["aenderung_prozent"] = None
        return neu

    alt = alt.copy()
    alt["_k"] = _key(alt, schl)
    neu["_k"] = _key(neu, schl)
    alt_idx = alt.drop_duplicates("_k").set_index("_k")
    inhalt = [c for c in neu.columns if c not in VERGLEICH + ["_k", "quelle_url"]]

    status, vorher = [], []
    for _, z in neu.iterrows():
        if z["_k"] not in alt_idx.index:
            status.append("neu"); vorher.append(None); continue
        a = alt_idx.loc[z["_k"]]
        pv = pd.to_numeric(a.get(preis), errors="coerce") if preis else None
        vorher.append(None if pv is None or pd.isna(pv) else float(pv))
        geaendert = any(str(z.get(c)) != str(a.get(c)) for c in inhalt if c in alt_idx.columns
                        and not (pd.isna(z.get(c)) and pd.isna(a.get(c))))
        if preis:
            p_neu, p_alt = z.get(preis), pv
            gleich_preis = (pd.isna(p_neu) and (p_alt is None or pd.isna(p_alt))) or \
                (not pd.isna(p_neu) and p_alt is not None and not pd.isna(p_alt) and abs(p_neu - p_alt) < 0.005)
            geaendert = geaendert or not gleich_preis
        status.append("geändert" if geaendert else "gleich")
    neu["status"] = status
    neu["preis_vorher"] = vorher
    if preis:
        diff = neu[preis] - pd.to_numeric(neu["preis_vorher"], errors="coerce")
        neu["aenderung"] = diff.round(2)
        neu["aenderung_prozent"] = (diff / pd.to_numeric(neu["preis_vorher"], errors="coerce") * 100).round(2)
    else:
        neu["aenderung"] = None
        neu["aenderung_prozent"] = None

    weg = alt[~alt["_k"].isin(set(neu["_k"]))]   # alt enthält keine „weg“-Zeilen (_letzter_stand)
    if not weg.empty:
        weg = weg.copy()
        if preis and preis in weg.columns:
            weg["preis_vorher"] = pd.to_numeric(weg[preis], errors="coerce")
        weg["status"] = "weg"
        weg["abgerufen_am"] = zeitpunkt
        weg["aenderung"] = None
        weg["aenderung_prozent"] = None
        neu = pd.concat([neu, weg[[c for c in neu.columns if c in weg.columns]]], ignore_index=True)
    return neu.drop(columns=["_k"], errors="ignore")


def _letzter_stand(ds) -> pd.DataFrame:
    if not ds.file_path or not os.path.exists(ds.file_path) or not ds.file_path.endswith(".parquet"):
        return pd.DataFrame()
    df = pd.read_parquet(ds.file_path)
    if "ist_aktuell" in df.columns and not df.empty:
        df = df[df["ist_aktuell"] == "ja"]
        df = df[df["status"] != "weg"] if "status" in df.columns else df
    elif "abgerufen_am" in df.columns and not df.empty:
        letzter = df["abgerufen_am"].max()
        df = df[df["abgerufen_am"] == letzter]
        df = df[df["status"] != "weg"] if "status" in df.columns else df
    return df


def abruf_ausfuehren(dataset_id: int) -> dict:
    """Abruf + Vergleich + Speichern. Läuft im eigenen DB-Kontext (auch im Thread)."""
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.plugins.registry import registry
    from app.services.file_service import dataframe_to_storage, infer_column_types
    from app.services.db_logger import log as _dblog

    db = SessionLocal()
    try:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not ds:
            raise ValueError(f"Dataset {dataset_id} nicht gefunden")
        config = dict(ds.query_config or {})
        _url_dataset_pruefen(config, ds, db)
        plugin = web_plugin(ds.file_type)
        config.pop("limit", None)
        roh, info = plugin.abrufen(config)
        jetzt = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
        alt_gesamt = pd.read_parquet(ds.file_path) if (ds.file_path and ds.file_path.endswith(".parquet")
                                                        and os.path.exists(ds.file_path)) else pd.DataFrame()
        if roh.empty and info["fehler"]:
            raise ValueError("Nichts abgerufen: " + "; ".join(info["fehler"][:3]))
        stand = vergleichen(roh, _letzter_stand(ds), config, jetzt)
        # ist_aktuell + neuester Abruf oben: Warnregeln und Vorschauen lesen nur
        # die ersten Zeilen – das sollen die aktuellen sein, nicht die ältesten.
        stand["ist_aktuell"] = "ja"
        if str(config.get("verlauf", "nein")).lower() in ("ja", "true", "1") and not alt_gesamt.empty:
            alt_gesamt = alt_gesamt.copy()
            alt_gesamt["ist_aktuell"] = "nein"
            gesamt = pd.concat([stand, alt_gesamt], ignore_index=True)
        else:
            gesamt = stand
        ds.file_path = dataframe_to_storage(gesamt, ds.id)
        ds.row_count = len(gesamt)
        ds.columns = list(gesamt.columns)
        ds.column_types = infer_column_types(gesamt)
        zaehl = stand["status"].value_counts().to_dict() if "status" in stand.columns else {}
        aenderungen = ", ".join(f"{v} {k}" for k, v in zaehl.items() if k != "gleich" and v)
        msg = f"{len(roh)} Zeilen aus {info['abrufe']} Abrufen · " + (aenderungen or "keine Änderungen")
        probleme = info["fehler"] + info["uebersprungen"]
        if probleme:
            msg += f" · {len(probleme)} Problem(e): " + "; ".join(probleme[:3])
        ds.last_refresh_at = datetime.now(timezone.utc)
        ds.last_refresh_status = "warning" if probleme else "success"
        ds.last_refresh_msg = msg[:500]
        ds.updated_at = datetime.now(timezone.utc)
        db.commit()
        _dblog(db, "warning" if probleme else "success", "datasets", "web_abruf",
               f"Web-Abruf '{ds.name}': {msg}"[:300], project_id=ds.project_id,
               rows_processed=len(roh), details={"dataset_id": ds.id, **info, "status": zaehl})
        return {"zeilen": len(roh), "status": zaehl, **info}
    except Exception as e:
        logger.exception(f"Web-Abruf {dataset_id} fehlgeschlagen")
        try:
            ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if ds:
                ds.last_refresh_at = datetime.now(timezone.utc)
                ds.last_refresh_status = "error"
                ds.last_refresh_msg = str(e)[:500]
                db.commit()
                _dblog(db, "error", "datasets", "web_abruf_error",
                       f"Web-Abruf '{ds.name}' fehlgeschlagen: {str(e)[:200]}", project_id=ds.project_id,
                       details={"dataset_id": dataset_id})
        except Exception:
            pass
        raise
    finally:
        db.close()


def abruf_im_hintergrund(dataset_id: int) -> bool:
    """Startet den Abruf in einem Thread. False, wenn für das Dataset schon einer läuft."""
    with _sperre:
        if dataset_id in _laufend:
            return False
        _laufend.add(dataset_id)

    def _lauf():
        try:
            abruf_ausfuehren(dataset_id)
        except Exception:
            pass
        finally:
            with _sperre:
                _laufend.discard(dataset_id)

    threading.Thread(target=_lauf, daemon=True).start()
    return True


def laeuft(dataset_id: int) -> bool:
    return dataset_id in _laufend


def _url_dataset_pruefen(config: dict, ds, db):
    """URLs aus einem anderen Dataset nur im selben Projekt."""
    from app.models.dataset import Dataset
    ref = config.get("url_dataset_id")
    if ref in (None, "", 0, "0"):
        return
    quelle = db.query(Dataset).filter(Dataset.id == int(ref)).first()
    if not quelle:
        raise ValueError(f"URL-Dataset #{ref} nicht gefunden")
    if quelle.project_id != ds.project_id:
        raise ValueError(f"URL-Dataset „{quelle.name}“ gehört zu einem anderen Projekt")


# ── Preiswarnung ─────────────────────────────────────────────────────────────

_NICHT_IN_WARNUNG = {"bild", "quelle_daten", "ist_aktuell", "abgerufen_am", "status", "aenderung"}


def preiswarnung_einrichten(ds, schwelle_prozent: float, db) -> dict:
    """Legt zu einer Web-Quelle ein Mapping „Preisänderungen – …“ (nur aktueller
    Abruf, nur geänderte Preise) und zwei Warnregeln an: gesenkt / erhöht um
    mindestens X %. Erneuter Aufruf aktualisiert beides (Schwelle, Spalten)."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.alert import AlertRule
    from app.models.mapping import Mapping

    if not ist_web_dataset(ds):
        raise ValueError("Preiswarnung gibt es nur für Web-Quellen")
    spalten = list(ds.columns or [])
    for pflicht in ("preis", "preis_vorher", "aenderung_prozent", "ist_aktuell"):
        if pflicht not in spalten:
            raise ValueError(f"Spalte „{pflicht}“ fehlt – erst einmal abrufen "
                             "(Extraktion „produkte“ oder ein Feld „preis“)")
    schwelle = abs(float(schwelle_prozent))
    felder = [{"source_dataset_id": ds.id, "source_field": c, "target_field": c,
               "transformer": {"type": "direct", "source_field": c}}
              for c in spalten if c not in _NICHT_IN_WARNUNG]
    canvas = [{"id": f"ds_{ds.id}", "dataset_id": ds.id, "dataset_name": ds.name, "x": 40, "y": 40,
               "filters": {"ist_aktuell": "= ja", "status": "= geändert"}}]
    ziele = [{"id": "t1", "name": "Preisänderungen", "target_type": "xlsx", "fields": felder,
              "target_options": {}}]

    config = dict(ds.query_config or {})
    m = None
    if config.get("preiswarnung_mapping_id"):
        m = db.query(Mapping).filter(Mapping.id == int(config["preiswarnung_mapping_id"])).first()
    if m is None:
        m = Mapping(name=f"Preisänderungen – {ds.name}", project_id=ds.project_id,
                    canvas_nodes=canvas, fields=[], joins=[], targets=ziele)
        db.add(m)
        db.commit()
        db.refresh(m)
    else:
        m.canvas_nodes, m.targets = canvas, ziele
        flag_modified(m, "canvas_nodes"); flag_modified(m, "targets")
    config["preiswarnung_mapping_id"] = m.id
    config["preiswarnung_schwelle"] = schwelle
    ds.query_config = config
    flag_modified(ds, "query_config")

    s_txt = f"{schwelle:g}".replace(".", ",")
    fakten = [{"label": "Produkt", "column": "name", "unit": "", "decimals": 0},
              {"label": "Preis vorher", "column": "preis_vorher", "unit": "", "decimals": 2},
              {"label": "Preis jetzt", "column": "preis", "unit": "", "decimals": 2},
              {"label": "Änderung", "column": "aenderung_prozent", "unit": "%", "decimals": 1}]
    regeln = []
    for key, name, op, wert, sev, titel, hinweis in (
        (f"web_preis_gesenkt_{ds.id}", f"Wettbewerber senkt Preis ({ds.name})", "<=", -schwelle, "warnung",
         f"Wettbewerb: {{anzahl}}× Preis um mindestens {s_txt} % gesenkt",
         "Eigenen Preis prüfen – liegt der Wettbewerber jetzt deutlich darunter?"),
        (f"web_preis_erhoeht_{ds.id}", f"Wettbewerber erhöht Preis ({ds.name})", ">=", schwelle, "hinweis",
         f"Wettbewerb: {{anzahl}}× Preis um mindestens {s_txt} % erhöht",
         "Spielraum für den eigenen Preis?"),
    ):
        r = db.query(AlertRule).filter(AlertRule.rule_key == key,
                                       AlertRule.project_id == ds.project_id).first()
        daten = dict(rule_key=key, project_id=ds.project_id, name=name, category="Wettbewerb",
                     severity=sev, mapping_id=m.id, mapping_name=m.name,
                     condition={"mode": "rows", "limit": 200, "value_unit": "",
                                "row_filter": {"column": "aenderung_prozent", "op": op, "value": wert}},
                     facts=fakten, title_template=titel, subtitle=hinweis,
                     drilldown={"mapping_id": m.id, "title": f"Preisänderungen – {ds.name}"},
                     active=True)
        if r is None:
            r = AlertRule(**daten)
            db.add(r)
        else:
            for k, v in daten.items():
                setattr(r, k, v)
        regeln.append(key)
    db.commit()
    return {"mapping_id": m.id, "regeln": regeln, "schwelle_prozent": schwelle}

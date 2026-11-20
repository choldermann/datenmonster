"""Mapping-Quelle „Umfelddaten“: Markt- und Umfeldreihen des monstersuite-Datendienstes
(Destatis, Eurostat, DWD, RKI, EZB, EU-Kommission) als ganz normales Dataset.

Damit lassen sich die Reihen im Mapping-Editor mit eigenen Zahlen verknüpfen (z. B. über die
Spalte `Periode` = „JJJJ-MM“ mit dem Monatsumsatz), filtern, exportieren oder in eine eigene
Tabelle schreiben – ohne ein spezielles Cockpit-Widget.

Es fließen keine Kundendaten zum Dienst: die Anfrage nennt nur Lizenz, Größe, Regionen und Zeitraum
(siehe app/api/umfeld.py, dort auch der 6-Stunden-Zwischenspeicher).

query_config:
  auswahl: [{"groesse": "temperatur", "regionen": ["Deutschland", "Bayern"]}, …]   („*“ = alle Regionen)
  monate:  60      (0 = alles, was die Quelle hat)
  format:  "lang"  (eine Zeile je Größe × Region × Periode) | "breit" (eine Zeile je Periode, eine Spalte je Reihe)
"""
import re
from datetime import date
from typing import List

from app.plugins.base import SourcePlugin

SPALTEN_LANG = ["Groesse", "Bezeichnung", "Region", "Regionname", "Periode", "Datum", "Jahr", "Monat",
                "Wert", "Einheit", "Quelle", "Stand"]
TYPEN_LANG = {"Datum": "date", "Jahr": "integer", "Monat": "integer", "Wert": "decimal"}
MAX_AUSWAHL = 12


def _auswahl(config: dict) -> list:
    aus = []
    for a in (config.get("auswahl") or [])[:MAX_AUSWAHL]:
        g = str((a or {}).get("groesse") or "").strip()
        if not g:
            continue
        regs = [str(r) for r in ((a or {}).get("regionen") or []) if str(r).strip()]
        aus.append((g, regs or ["Deutschland"]))
    return aus


def _von(config: dict) -> str:
    try:
        monate = int(config.get("monate", 60) or 0)
    except (TypeError, ValueError):
        monate = 60
    if monate <= 0:
        return ""
    heute = date.today()
    m = heute.year * 12 + heute.month - 1 - monate
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def _spaltenname(groesse: str, region: str) -> str:
    return re.sub(r"\W+", "_", f"{groesse}_{region}").strip("_")


def _periode(p: str):
    """„2026-08“ → (Datum 01.08.2026, 2026, 8); Jahreswert „2024“ → (31.12.2024, 2024, None)."""
    try:
        if len(p) == 7:
            j, m = int(p[:4]), int(p[5:7])
            return date(j, m, 1), j, m
        if len(p) == 4:
            return date(int(p), 12, 31), int(p), None
    except ValueError:
        pass
    return None, None, None


def spaltentypen(spalten: list, format: str = "lang") -> dict:
    """Spaltentypen ohne Abruf (auch für die Vorlagen-Installation): im Aufbau „breit“ ist jede
    Reihenspalte ein Dezimalwert."""
    typen = {}
    for c in spalten:
        if c in TYPEN_LANG:
            typen[c] = TYPEN_LANG[c]
        elif format == "breit" and c != "Periode":
            typen[c] = "decimal"
        else:
            typen[c] = "string"
    return typen


def _db():
    from app.core.database import SessionLocal
    return SessionLocal()


def katalog(db) -> dict:
    from app.api.umfeld import _fragen
    return _fragen(db, "datenkatalog", {})


class UmfeldSource(SourcePlugin):
    id = "umfeld"
    name = "Umfelddaten"
    version = "1.0.0"
    description = ("Markt- und Umfelddaten aus amtlichen Quellen (Destatis, Eurostat, DWD, RKI, EZB, "
                   "EU-Kommission) als Dataset – zum Verknüpfen mit eigenen Zahlen.")
    author = "Holdermann IT"
    capabilities = ["source"]
    source_type_id = "umfeld"
    source_type_label = "Umfelddaten (Destatis, Eurostat, DWD …)"
    source_type_icon = "globe"
    source_category = "umfeld"     # eigener Schritt im Dataset-Assistenten, nicht in der Plugin-Liste
    config_schema = [
        {"key": "auswahl", "label": "Reihen", "type": "json", "hidden": True, "default": []},
        {"key": "monate", "label": "Zeitraum (Monate)", "type": "number", "default": 60},
        {"key": "format", "label": "Format", "type": "select", "options": ["lang", "breit"], "default": "lang"},
    ]

    def test_connection(self, config: dict) -> dict:
        db = _db()
        try:
            k = katalog(db)
            return {"ok": True, "message": f"{len(k.get('groessen') or [])} Größen verfügbar"}
        except Exception as e:
            return {"ok": False, "message": getattr(e, "detail", None) or str(e)}
        finally:
            db.close()

    def get_columns(self, config: dict) -> List[str]:
        if (config or {}).get("format") != "breit":
            return list(SPALTEN_LANG)
        auswahl = _auswahl(config)
        kat = {}
        if any("*" in regs for _, regs in auswahl):
            db = _db()
            try:
                kat = {g["key"]: g for g in (katalog(db).get("groessen") or [])}
            finally:
                db.close()
        spalten = []
        for g, regs in auswahl:
            codes = [r["code"] for r in (kat.get(g, {}).get("regionen") or [])] if "*" in regs else regs
            spalten += [_spaltenname(g, r) for r in codes]
        return ["Periode", "Datum", "Jahr", "Monat"] + list(dict.fromkeys(spalten))

    def get_column_types(self, config: dict) -> dict:
        return spaltentypen(self.get_columns(config), (config or {}).get("format"))

    def _lang(self, config: dict) -> List[dict]:
        from fastapi import HTTPException
        from app.api.umfeld import _fragen
        auswahl = _auswahl(config)
        if not auswahl:
            raise ValueError("Keine Reihen gewählt – im Dataset mindestens eine Größe auswählen.")
        von = _von(config)
        db = _db()
        try:
            try:
                kat = {g["key"]: g for g in (katalog(db).get("groessen") or [])}
            except HTTPException:
                kat = {}
            zeilen = []
            for groesse, regs in auswahl:
                # Jahreswerte (Einwohner, Einkommen) tragen „JJJJ“ – mit „JJJJ-MM“ verglichen fiele das
                # laufende Jahr heraus
                v = von[:4] if kat.get(groesse, {}).get("takt") == "jahr" else von
                antwort = _fragen(db, "reihen", {"groessen": [groesse], "regionen": sorted(set(regs)),
                                                 "von": v, "bis": ""})
                namen = {r["code"]: r["label"] for r in (kat.get(groesse, {}).get("regionen") or [])}
                for reihe in antwort.get("reihen") or []:
                    werte = reihe.get("werte") or {}
                    if reihe.get("hinweis") and not any(werte.values()):
                        raise ValueError(f"{reihe.get('label') or groesse}: {reihe['hinweis']}")
                    for region, monate in werte.items():
                        for periode, wert in sorted(monate.items()):
                            d, j, m = _periode(periode)
                            zeilen.append({
                                "Groesse": groesse, "Bezeichnung": reihe.get("label"),
                                "Region": region, "Regionname": namen.get(region, region),
                                "Periode": periode, "Datum": d, "Jahr": j, "Monat": m,
                                "Wert": wert, "Einheit": reihe.get("einheit"),
                                "Quelle": reihe.get("quelle"), "Stand": reihe.get("stand"),
                            })
            return zeilen
        finally:
            db.close()

    def fetch(self, config: dict) -> List[dict]:
        zeilen = self._lang(config)
        if (config or {}).get("format") != "breit":
            return zeilen
        perioden: dict = {}
        jahreswerte = [z for z in zeilen if z["Monat"] is None]
        for z in zeilen:
            if z["Monat"] is None:
                continue
            p = perioden.setdefault(z["Periode"], {"Periode": z["Periode"], "Datum": z["Datum"],
                                                   "Jahr": z["Jahr"], "Monat": z["Monat"]})
            p[_spaltenname(z["Groesse"], z["Region"])] = z["Wert"]
        # Jahreswerte in jeden Monat ihres Jahres schreiben (z. B. Umsatz je Einwohner rechnen);
        # gibt es zu dem Jahr keine Monatszeile, bleibt eine eigene Jahreszeile
        for z in jahreswerte:
            spalte = _spaltenname(z["Groesse"], z["Region"])
            monate = [p for k, p in perioden.items() if k.startswith(f"{z['Periode']}-")]
            if not monate:
                monate = [perioden.setdefault(z["Periode"], {"Periode": z["Periode"], "Datum": z["Datum"],
                                                             "Jahr": z["Jahr"], "Monat": None})]
            for p in monate:
                p[spalte] = z["Wert"]
        return [perioden[k] for k in sorted(perioden)]

    def fetch_preview(self, config: dict, limit: int = 50) -> List[dict]:
        return self.fetch(config)[:limit]


ALL_PLUGINS = [UmfeldSource]

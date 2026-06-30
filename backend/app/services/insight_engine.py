"""
insight_engine – Business-Insights-Berechnungslogik (kein LLM, reines pandas/DuckDB).
"""
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Keyword-Heuristik für Auto-Suggest ────────────────────────────────────────

FIELD_HINTS: dict[str, list[str]] = {
    "revenue":  ["umsatz", "netto", "brutto", "betrag", "wert", "preis", "revenue", "amount",
                 "positionswert", "gesamtbetrag", "rechnungsbetrag"],
    "date":     ["datum", "date", "erstellt", "timestamp", "rechnungsdatum", "bestelldatum",
                 "lieferdatum", "created", "modified", "derstellt", "dbestelldatum"],
    "country":  ["land", "country", "iso", "versandland", "lieferland", "herkunftsland", "nation"],
    "customer": ["kunde", "customer", "kundennr", "kkunde", "kundenname", "client",
                 "kundennummer", "kkundennr"],
    "article":  ["artikel", "article", "artnr", "kartikel", "artikelnr", "artikelnummer",
                 "sku", "produktnr", "cbarcode"],
    "quantity": ["anzahl", "menge", "quantity", "stueck", "stück", "fanzahl", "nmenge",
                 "nanzahl", "fmenge"],
    "stock":    ["lager", "bestand", "stock", "inventory", "flagerbestand", "bestandsmenge",
                 "verfuegbar", "verfügbar"],
}

PRESETS: dict[str, dict] = {
    "jtl_rechnung": {
        "label": "JTL Rechnungsanalyse",
        "mapping": {
            "revenue":  "NettoPositionswert",
            "date":     "Rechnungsdatum",
            "country":  "Versandland",
            "customer": "Kundennummer",
            "article":  "Artikelnummer",
            "quantity": "Menge",
            "stock":    None,
        },
    },
    "jtl_bestellpos": {
        "label": "JTL Bestellpositionen",
        "mapping": {
            "revenue":  "fVKNetto",
            "date":     "dErstellt",
            "country":  "cVersandlandISO",
            "customer": "kKunde",
            "article":  "cArtNr",
            "quantity": "fAnzahl",
            "stock":    "fLagerbestand",
        },
    },
}


def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    """Schlägt Semantic-Mapping per Keyword-Heuristik vor. Kein LLM."""
    col_lower = {c.lower(): c for c in columns}
    result: dict[str, str | None] = {}
    for role, keywords in FIELD_HINTS.items():
        found = None
        for kw in keywords:
            # Exakt-Match (case-insensitive)
            if kw in col_lower:
                found = col_lower[kw]
                break
            # Enthält-Match
            for col_l, col_orig in col_lower.items():
                if kw in col_l:
                    found = col_orig
                    break
            if found:
                break
        result[role] = found
    return result


def get_presets() -> list[dict]:
    return [{"id": k, "label": v["label"], "mapping": v["mapping"]} for k, v in PRESETS.items()]


# ── Haupt-Einstiegspunkt ──────────────────────────────────────────────────────

def compute_insights(
    df: pd.DataFrame,
    semantic: dict[str, str | None],
    comparison: dict,
    modules: dict[str, bool] | None = None,
) -> pd.DataFrame:
    """
    Berechnet alle aktivierten Analyse-Module und gibt ein Findings-DataFrame zurück.

    semantic: {"revenue": "fVKNetto", "date": "dErstellt", ...}
    comparison: {"mode": "mom" | "yoy_month" | "yoy_year" | "custom",
                 "custom_start": "YYYY-MM-DD", "custom_end": "YYYY-MM-DD",
                 "custom_prev_start": "YYYY-MM-DD", "custom_prev_end": "YYYY-MM-DD"}
    modules: {"umsatzentwicklung": True, "laenderanalyse": True, ...}
    """
    if modules is None:
        modules = {"umsatzentwicklung": True, "laenderanalyse": True,
                   "top_kunden": True, "lagerbestand": True}

    findings: list[dict] = []

    date_col     = semantic.get("date")
    revenue_col  = semantic.get("revenue")
    country_col  = semantic.get("country")
    customer_col = semantic.get("customer")
    article_col  = semantic.get("article")
    quantity_col = semantic.get("quantity")
    stock_col    = semantic.get("stock")

    # Datumsfeld parsen
    if date_col and date_col in df.columns:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])

    # Vergleichszeiträume ermitteln
    cur_start, cur_end, prev_start, prev_end = _resolve_periods(df, date_col, comparison)

    if date_col and date_col in df.columns:
        df_cur  = df[(df[date_col] >= pd.Timestamp(cur_start))  & (df[date_col] <= pd.Timestamp(cur_end))]
        df_prev = df[(df[date_col] >= pd.Timestamp(prev_start)) & (df[date_col] <= pd.Timestamp(prev_end))]
    else:
        df_cur = df_prev = df

    if modules.get("umsatzentwicklung") and revenue_col and revenue_col in df.columns:
        findings += _umsatzentwicklung(df_cur, df_prev, revenue_col, cur_start, cur_end)

    if modules.get("laenderanalyse") and revenue_col and country_col and revenue_col in df.columns and country_col in df.columns:
        findings += _laenderanalyse(df_cur, df_prev, revenue_col, country_col)

    if modules.get("top_kunden") and revenue_col and customer_col and revenue_col in df.columns and customer_col in df.columns:
        findings += _top_kunden(df_cur, revenue_col, customer_col)

    if modules.get("lagerbestand") and stock_col and stock_col in df.columns:
        qty = quantity_col if quantity_col and quantity_col in df.columns else None
        findings += _lagerbestand(df, stock_col, article_col, qty)

    if not findings:
        findings.append({
            "type": "info", "icon": "ℹ️", "entity": "–", "metric": "–",
            "value": None, "delta_pct": None, "period": str(cur_start),
            "text": "Keine Findings für die gewählten Felder und den gewählten Zeitraum.",
            "severity": "info",
        })

    return pd.DataFrame(findings)


# ── Perioden-Resolver ─────────────────────────────────────────────────────────

def _resolve_periods(df: pd.DataFrame, date_col: str | None, comparison: dict):
    today = date.today()
    mode  = comparison.get("mode", "mom")

    if mode == "custom":
        cs  = comparison.get("custom_start") or str(today.replace(day=1))
        ce  = comparison.get("custom_end")   or str(today)
        ps  = comparison.get("custom_prev_start") or str(today.replace(day=1) - timedelta(days=1))
        pe  = comparison.get("custom_prev_end")   or str(today.replace(day=1) - timedelta(days=1))
        return cs, ce, ps, pe

    if mode == "yoy_year":
        cur_start  = date(today.year, 1, 1)
        cur_end    = today
        prev_start = date(today.year - 1, 1, 1)
        prev_end   = date(today.year - 1, today.month, today.day)
        return str(cur_start), str(cur_end), str(prev_start), str(prev_end)

    if mode == "yoy_month":
        cur_start  = today.replace(day=1)
        cur_end    = today
        prev_year  = today.year - 1
        prev_start = cur_start.replace(year=prev_year)
        prev_end   = today.replace(year=prev_year)
        return str(cur_start), str(cur_end), str(prev_start), str(prev_end)

    # Default: mom – aktueller Monat vs. Vormonat
    cur_start = today.replace(day=1)
    first_prev = (cur_start - timedelta(days=1)).replace(day=1)
    last_prev  = cur_start - timedelta(days=1)
    return str(cur_start), str(today), str(first_prev), str(last_prev)


# ── Analyse-Module ────────────────────────────────────────────────────────────

def _safe_float(val) -> float:
    try:
        return float(val)
    except Exception:
        return 0.0


def _delta_pct(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def _umsatzentwicklung(
    df_cur: pd.DataFrame, df_prev: pd.DataFrame,
    revenue_col: str, cur_start: str, cur_end: str,
) -> list[dict]:
    cur_sum  = _safe_float(pd.to_numeric(df_cur[revenue_col],  errors="coerce").sum())
    prev_sum = _safe_float(pd.to_numeric(df_prev[revenue_col], errors="coerce").sum())
    delta    = _delta_pct(cur_sum, prev_sum)

    if delta is None:
        icon, severity = "ℹ️", "info"
        text = f"Umsatz aktuell: {cur_sum:,.2f} (kein Vorjahreszeitraum vorhanden)"
    elif delta >= 5:
        icon, severity = "📈", "info"
        text = f"Umsatz stieg um {delta:+.1f}% auf {cur_sum:,.2f}"
    elif delta <= -5:
        icon, severity = "⚠️", "warning"
        text = f"Umsatz fiel um {abs(delta):.1f}% auf {cur_sum:,.2f}"
    else:
        icon, severity = "↔️", "info"
        text = f"Umsatz stabil ({delta:+.1f}%): {cur_sum:,.2f}"

    return [{
        "type": "trend_revenue", "icon": icon, "entity": "Gesamt", "metric": revenue_col,
        "value": round(cur_sum, 2), "delta_pct": delta, "period": cur_start,
        "text": text, "severity": severity,
    }]


def _laenderanalyse(
    df_cur: pd.DataFrame, df_prev: pd.DataFrame,
    revenue_col: str, country_col: str,
) -> list[dict]:
    findings: list[dict] = []

    cur_by_land  = (pd.to_numeric(df_cur[revenue_col],  errors="coerce")
                    .groupby(df_cur[country_col]).sum())
    prev_by_land = (pd.to_numeric(df_prev[revenue_col], errors="coerce")
                    .groupby(df_prev[country_col]).sum())

    all_lands = set(cur_by_land.index) | set(prev_by_land.index)

    rows: list[dict] = []
    for land in all_lands:
        cur_v  = _safe_float(cur_by_land.get(land,  0))
        prev_v = _safe_float(prev_by_land.get(land, 0))
        delta  = _delta_pct(cur_v, prev_v)
        rows.append({"land": land, "cur": cur_v, "prev": prev_v, "delta": delta})

    rows.sort(key=lambda r: r["cur"], reverse=True)

    for r in rows[:10]:
        land, cur_v, delta = r["land"], r["cur"], r["delta"]
        if delta is None:
            icon, severity = "🌍", "info"
            text = f"{land}: {cur_v:,.2f} (neu im Zeitraum)"
        elif delta <= -10:
            icon, severity = "⚠️", "warning"
            text = f"{land} sank um {abs(delta):.1f}% auf {cur_v:,.2f}"
        elif delta >= 10:
            icon, severity = "📈", "info"
            text = f"{land} wuchs um {delta:.1f}% auf {cur_v:,.2f}"
        else:
            continue  # Stabile Länder nicht einzeln aufführen
        findings.append({
            "type": "country_trend", "icon": icon, "entity": land, "metric": revenue_col,
            "value": round(cur_v, 2), "delta_pct": delta, "period": "",
            "text": text, "severity": severity,
        })

    return findings


def _top_kunden(
    df_cur: pd.DataFrame, revenue_col: str, customer_col: str,
) -> list[dict]:
    findings: list[dict] = []
    rev = pd.to_numeric(df_cur[revenue_col], errors="coerce")
    by_kunde = rev.groupby(df_cur[customer_col]).sum().sort_values(ascending=False)

    total = _safe_float(rev.sum())
    if total == 0:
        return findings

    top10_sum = _safe_float(by_kunde.head(10).sum())
    top10_pct = round(top10_sum / total * 100, 1)

    icon = "💰" if top10_pct >= 60 else "👥"
    severity = "warning" if top10_pct >= 70 else "info"
    findings.append({
        "type": "customer_concentration", "icon": icon,
        "entity": "Top-10-Kunden", "metric": revenue_col,
        "value": round(top10_pct, 1), "delta_pct": None, "period": "",
        "text": f"Top-10-Kunden erzeugen {top10_pct:.1f}% des Umsatzes ({top10_sum:,.2f} von {total:,.2f})",
        "severity": severity,
    })

    # Top-3 namentlich
    for i, (kunde, val) in enumerate(by_kunde.head(3).items(), 1):
        pct = round(_safe_float(val) / total * 100, 1)
        findings.append({
            "type": "top_customer", "icon": f"#{i}", "entity": str(kunde), "metric": revenue_col,
            "value": round(_safe_float(val), 2), "delta_pct": pct, "period": "",
            "text": f"#{i} {kunde}: {_safe_float(val):,.2f} ({pct:.1f}% Umsatzanteil)",
            "severity": "info",
        })

    return findings


def _lagerbestand(
    df: pd.DataFrame, stock_col: str,
    article_col: str | None, quantity_col: str | None,
) -> list[dict]:
    findings: list[dict] = []

    stock_series = pd.to_numeric(df[stock_col], errors="coerce")

    if article_col and article_col in df.columns:
        # Aktuellen Bestand pro Artikel (letzter Wert)
        by_artikel = stock_series.groupby(df[article_col]).last()

        # Tagesverbrauch schätzen wenn Mengenspalte vorhanden
        if quantity_col and quantity_col in df.columns:
            qty_series = pd.to_numeric(df[quantity_col], errors="coerce")
            days_span = max((df.index.max() - df.index.min()).days
                           if isinstance(df.index, pd.DatetimeIndex) else 30, 1)
            daily_qty = qty_series.groupby(df[article_col]).sum() / days_span
        else:
            daily_qty = None

        low_stock = by_artikel[by_artikel <= 0]
        for artikel, bestand in low_stock.items():
            findings.append({
                "type": "stock_out", "icon": "🚨", "entity": str(artikel),
                "metric": stock_col, "value": round(_safe_float(bestand), 0),
                "delta_pct": None, "period": "",
                "text": f"Artikel {artikel}: Lagerbestand bei {_safe_float(bestand):.0f} (ausverkauft oder negativ)",
                "severity": "critical",
            })

        if daily_qty is not None:
            for artikel, bestand in by_artikel[by_artikel > 0].items():
                daily = _safe_float(daily_qty.get(artikel, 0))
                if daily > 0:
                    days_left = _safe_float(bestand) / daily
                    if days_left <= 14:
                        sev = "critical" if days_left <= 7 else "warning"
                        icon = "🚨" if days_left <= 7 else "⚠️"
                        findings.append({
                            "type": "stock_low", "icon": icon, "entity": str(artikel),
                            "metric": stock_col, "value": round(_safe_float(bestand), 0),
                            "delta_pct": round(days_left, 1), "period": "",
                            "text": f"Artikel {artikel}: Lagerbestand reicht noch ca. {days_left:.0f} Tage",
                            "severity": sev,
                        })
    else:
        # Ohne Artikel-Aufschlüsselung: nur Gesamt-Minimum
        min_stock = _safe_float(stock_series.min())
        if min_stock <= 0:
            findings.append({
                "type": "stock_out", "icon": "🚨", "entity": "Lager",
                "metric": stock_col, "value": round(min_stock, 0),
                "delta_pct": None, "period": "",
                "text": f"Lagerbestand bei {min_stock:.0f} — Nachbestellung prüfen",
                "severity": "critical",
            })

    return findings

"""Baut templates/bueroplus_gf_cockpit.json (Reiter Übersicht)."""
import json, sys, re
OUT = sys.argv[1]
CONN = "{{connection_bp}}"

# Umsatzbelege: gebuchte, nicht stornierte Rechnungen und Rechnungskorrekturen.
# Rechnungskorrekturen stehen in büro+ mit positivem Betrag und werden abgezogen.
BELEGE = """SELECT Quelle, VogID, VogBelegNr, VogArt, VogDat, VogAdrNr, VogVerk, VogVtrNr,
           VogGPreisNt AS Netto, VogGEkRoh AS Ek,
           CASE WHEN VogArt = 'Rechnungskorrektur' THEN -1 ELSE 1 END AS Vz
    FROM dbo.vVorgang
    WHERE VogArt IN ('Rechnung I', 'Sammel Rechnung', 'Rechnungskorrektur')
      AND VogGebuchtKz = 1 AND ISNULL(VogStorniertKz, 0) = 0"""

SQL = {}
SQL["m_bp_kpi"] = f"""
WITH b AS (
    {BELEGE}
), p AS (
    SELECT b.*,
        CASE WHEN VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis) THEN 1
             WHEN VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 2 END AS Per
    FROM b
), s AS (
    SELECT
        SUM(CASE WHEN Per = 1 AND Vz = 1 THEN Netto ELSE 0 END) AS Umsatz,
        SUM(CASE WHEN Per = 2 AND Vz = 1 THEN Netto ELSE 0 END) AS UmsatzVJ,
        SUM(CASE WHEN Per = 1 AND Vz = -1 THEN Netto ELSE 0 END) AS KorrekturWert,
        SUM(CASE WHEN Per = 2 AND Vz = -1 THEN Netto ELSE 0 END) AS KorrekturWertVJ,
        SUM(CASE WHEN Per = 1 AND Vz = -1 THEN 1 ELSE 0 END) AS KorrekturAnzahl,
        SUM(CASE WHEN Per = 1 THEN Vz * Ek ELSE 0 END) AS Wareneinsatz,
        SUM(CASE WHEN Per = 2 THEN Vz * Ek ELSE 0 END) AS WareneinsatzVJ,
        SUM(CASE WHEN Per = 1 THEN Vz * (Netto - Ek) ELSE 0 END) AS Rohertrag,
        SUM(CASE WHEN Per = 2 THEN Vz * (Netto - Ek) ELSE 0 END) AS RohertragVJ,
        SUM(CASE WHEN Per = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen,
        SUM(CASE WHEN Per = 2 AND Vz = 1 THEN 1 ELSE 0 END) AS RechnungenVJ,
        COUNT(DISTINCT CASE WHEN Per = 1 AND Vz = 1 THEN VogAdrNr END) AS AktiveKunden,
        COUNT(DISTINCT CASE WHEN Per = 2 AND Vz = 1 THEN VogAdrNr END) AS AktiveKundenVJ
    FROM p WHERE Per IS NOT NULL
), ohne_ek AS (
    SELECT COUNT(*) AS PosOhneEk, ISNULL(SUM(pos.NettoPos), 0) AS UmsatzOhneEk
    FROM dbo.vVorgangPosition pos
    JOIN b ON b.VogID = pos.VogID AND b.Quelle = pos.Quelle AND b.Vz = 1
    WHERE b.VogDat >= :von AND b.VogDat < DATEADD(DAY, 1, :bis)
      AND pos.ArtKz = 1 AND ISNULL(pos.EEkRoh, 0) = 0 AND pos.NettoPos > 0
)
SELECT
    CAST(Umsatz AS DECIMAL(18,2)) AS Umsatz, CAST(UmsatzVJ AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(KorrekturWert AS DECIMAL(18,2)) AS KorrekturWert, CAST(KorrekturWertVJ AS DECIMAL(18,2)) AS KorrekturWertVJ,
    KorrekturAnzahl,
    CAST(Umsatz - KorrekturWert AS DECIMAL(18,2)) AS UmsatzNachKorrektur,
    CAST(UmsatzVJ - KorrekturWertVJ AS DECIMAL(18,2)) AS UmsatzNachKorrekturVJ,
    CAST(Umsatz - KorrekturWert AS DECIMAL(18,2)) AS Warenumsatz,
    CAST(Wareneinsatz AS DECIMAL(18,2)) AS Wareneinsatz, CAST(WareneinsatzVJ AS DECIMAL(18,2)) AS WareneinsatzVJ,
    CAST(Rohertrag AS DECIMAL(18,2)) AS Rohertrag, CAST(RohertragVJ AS DECIMAL(18,2)) AS RohertragVJ,
    CAST(CASE WHEN Umsatz - KorrekturWert > 0 THEN 100.0 * Rohertrag / (Umsatz - KorrekturWert) END AS DECIMAL(18,2)) AS Marge,
    CAST(CASE WHEN UmsatzVJ - KorrekturWertVJ > 0 THEN 100.0 * RohertragVJ / (UmsatzVJ - KorrekturWertVJ) END AS DECIMAL(18,2)) AS MargeVJ,
    Rechnungen, RechnungenVJ,
    CAST(CASE WHEN Rechnungen > 0 THEN Umsatz / Rechnungen END AS DECIMAL(18,2)) AS AvgRechnung,
    CAST(CASE WHEN RechnungenVJ > 0 THEN UmsatzVJ / RechnungenVJ END AS DECIMAL(18,2)) AS AvgRechnungVJ,
    AktiveKunden, AktiveKundenVJ,
    PosOhneEk, CAST(UmsatzOhneEk AS DECIMAL(18,2)) AS UmsatzOhneEk
FROM s CROSS JOIN ohne_ek
"""

SQL["m_bp_pipeline"] = """
WITH v AS (
    SELECT VogArt, VogDat, VogGPreisNt,
        CASE WHEN VogDat >= DATEADD(MONTH, -{{pipeline_monate}}, CAST(GETDATE() AS date)) THEN 1 ELSE 0 END AS InFrist
    FROM dbo.Vorgang
    WHERE ISNULL(VogStorniertKz, 0) = 0
)
SELECT
    SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 1 THEN 1 ELSE 0 END) AS AngeboteOffen,
    CAST(SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 1 THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AngeboteWert,
    SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 1 AND VogDat < DATEADD(DAY, -90, CAST(GETDATE() AS date)) THEN 1 ELSE 0 END) AS AngeboteAlt,
    CAST(SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 1 AND VogDat < DATEADD(DAY, -90, CAST(GETDATE() AS date)) THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AngeboteAltWert,
    CAST(SUM(CASE WHEN VogArt = 'Angebot' AND VogDat >= DATEADD(DAY, -90, CAST(GETDATE() AS date)) THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AngeboteFrischWert,
    SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 0 THEN 1 ELSE 0 END) AS AngeboteAusserFrist,
    CAST(SUM(CASE WHEN VogArt = 'Angebot' AND InFrist = 0 THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AngeboteAusserFristWert,
    SUM(CASE WHEN VogArt = 'Auftragsbestätigung' AND InFrist = 1 THEN 1 ELSE 0 END) AS AuftraegeOffen,
    CAST(SUM(CASE WHEN VogArt = 'Auftragsbestätigung' AND InFrist = 1 THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AuftragsbestandWert,
    SUM(CASE WHEN VogArt = 'Auftragsbestätigung' AND InFrist = 0 THEN 1 ELSE 0 END) AS AuftraegeAusserFrist,
    CAST(SUM(CASE WHEN VogArt = 'Auftragsbestätigung' AND InFrist = 0 THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS AuftraegeAusserFristWert,
    SUM(CASE WHEN VogArt = 'Lieferschein' THEN 1 ELSE 0 END) AS LieferscheineOffen,
    CAST(SUM(CASE WHEN VogArt = 'Lieferschein' THEN VogGPreisNt ELSE 0 END) AS DECIMAL(18,2)) AS LieferscheineWert,
    MAX(CASE WHEN VogArt = 'Lieferschein' THEN DATEDIFF(DAY, VogDat, CAST(GETDATE() AS date)) END) AS LieferscheinAeltesterTage
FROM v
"""

SQL["m_bp_verlauf"] = f"""
WITH b AS (
    {BELEGE}
), cur AS (
    SELECT CONVERT(char(7), VogDat, 120) AS Monat, SUM(Vz * Netto) AS Umsatz, SUM(Vz * (Netto - Ek)) AS Rohertrag
    FROM b WHERE VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis)
    GROUP BY CONVERT(char(7), VogDat, 120)
), vj AS (
    SELECT CONVERT(char(7), DATEADD(YEAR, 1, VogDat), 120) AS Monat, SUM(Vz * Netto) AS UmsatzVorjahr
    FROM b WHERE VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis))
    GROUP BY CONVERT(char(7), DATEADD(YEAR, 1, VogDat), 120)
)
SELECT ISNULL(cur.Monat, vj.Monat) AS Monat,
    CAST(ISNULL(cur.Umsatz, 0) AS DECIMAL(18,2)) AS Umsatz,
    CAST(ISNULL(vj.UmsatzVorjahr, 0) AS DECIMAL(18,2)) AS UmsatzVorjahr,
    CAST(ISNULL(cur.Rohertrag, 0) AS DECIMAL(18,2)) AS Rohertrag
FROM cur FULL OUTER JOIN vj ON cur.Monat = vj.Monat
ORDER BY Monat
"""

KUNDE = "COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(a.AdrReNa2, ''))), ''), CONCAT('Adresse ', b.VogAdrNr))"

SQL["m_bp_rg_monat"] = f"""
WITH b AS (
    {BELEGE}
), m AS (
    SELECT b.*, ROW_NUMBER() OVER (ORDER BY b.Netto DESC) AS rn
    FROM b WHERE CONVERT(char(7), b.VogDat, 120) = :monat
)
SELECT 0 AS Sortierung, m.VogBelegNr AS Beleg, m.VogArt AS Art, CONVERT(char(10), m.VogDat, 104) AS Datum,
    m.VogAdrNr AS AdrNr, COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(a.AdrReNa2, ''))), ''), CONCAT('Adresse ', m.VogAdrNr)) AS Kunde,
    CAST(m.Vz * m.Netto AS DECIMAL(18,2)) AS Umsatz,
    CAST(m.Vz * (m.Netto - m.Ek) AS DECIMAL(18,2)) AS Rohertrag,
    m.VogVerk AS Bearbeiter, CONCAT(CASE m.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, m.VogID) AS VogID
FROM m LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = m.VogAdrNr
WHERE m.rn <= 499
UNION ALL
SELECT 1, '', '', '', NULL, CONCAT('… ', COUNT(*), ' weitere Belege'),
    CAST(SUM(Vz * Netto) AS DECIMAL(18,2)), CAST(SUM(Vz * (Netto - Ek)) AS DECIMAL(18,2)), '', ''
FROM m WHERE rn > 499
HAVING COUNT(*) > 0
ORDER BY Sortierung, Umsatz DESC
"""

SQL["m_bp_positionen"] = """
SELECT TOP 500 p.Pos, p.ArtNr, COALESCE(NULLIF(art.ArtKuBez1, ''), LEFT(art.ArtBez1, 80)) AS Bezeichnung,
    CAST(p.BuchMge AS DECIMAL(18,2)) AS Menge, p.Einh AS Einheit,
    CAST(p.EPrNt AS DECIMAL(18,4)) AS Preis, CAST(p.EPreisFak AS DECIMAL(9,4)) AS Preisfaktor,
    p.NettoPos AS Umsatz, p.EkPos AS Einsatz, p.RohertragPos AS Rohertrag
FROM dbo.vVorgangPosition p
LEFT JOIN dbo.Artikel art ON art.ArtArtNr = p.ArtNr
WHERE p.VogID = CAST(SUBSTRING(:vogid, 2, 20) AS int)
  AND p.Quelle = CASE LEFT(:vogid, 1) WHEN 'A' THEN 'Archiv' ELSE 'Übersicht' END
ORDER BY p.ZeilenNr
"""

# ── Warnungen „Heute zu tun“ ────────────────────────────────────────────────
SQL["m_bp_w_lieferscheine"] = f"""
SELECT TOP 500 b.VogBelegNr AS Beleg, CONVERT(char(10), b.VogDat, 104) AS Datum,
    DATEDIFF(DAY, b.VogDat, CAST(GETDATE() AS date)) AS TageOffen,
    b.VogAdrNr AS AdrNr, {KUNDE} AS Kunde,
    CAST(b.VogGPreisNt AS DECIMAL(18,2)) AS Wert, b.VogVerk AS Bearbeiter, CONCAT('U', b.VogID) AS VogID
FROM dbo.Vorgang b LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE b.VogArt = 'Lieferschein' AND ISNULL(b.VogStorniertKz, 0) = 0
  AND b.VogDat <= DATEADD(DAY, -{{{{lieferschein_tage}}}}, CAST(GETDATE() AS date))
ORDER BY b.VogDat
"""

SQL["m_bp_w_angebote"] = f"""
SELECT b.VogBelegNr AS Beleg, CONVERT(char(10), b.VogDat, 104) AS Datum,
    DATEDIFF(DAY, b.VogDat, CAST(GETDATE() AS date)) AS Alter_Tage,
    b.VogAdrNr AS AdrNr, {KUNDE} AS Kunde,
    CAST(b.VogGPreisNt AS DECIMAL(18,2)) AS Wert, b.VogVerk AS Bearbeiter, CONCAT('U', b.VogID) AS VogID
FROM dbo.Vorgang b LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE b.VogArt = 'Angebot' AND ISNULL(b.VogStorniertKz, 0) = 0
  AND b.VogDat < DATEADD(DAY, -{{{{angebot_tage}}}}, CAST(GETDATE() AS date))
ORDER BY b.VogGPreisNt DESC
"""

SQL["m_bp_w_ohne_ek"] = f"""
WITH b AS (
    {BELEGE}
)
SELECT TOP 500 p.ArtNr, MAX(COALESCE(NULLIF(art.ArtKuBez1, ''), LEFT(art.ArtBez1, 80))) AS Bezeichnung,
    COUNT(*) AS Positionen, CAST(SUM(p.NettoPos) AS DECIMAL(18,2)) AS Umsatz,
    CONVERT(char(10), MAX(b.VogDat), 104) AS LetzterVerkauf
FROM dbo.vVorgangPosition p
JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle AND b.Vz = 1
LEFT JOIN dbo.Artikel art ON art.ArtArtNr = p.ArtNr
WHERE b.VogDat >= DATEADD(DAY, -90, CAST(GETDATE() AS date))
  AND p.ArtKz = 1 AND ISNULL(p.EEkRoh, 0) = 0 AND p.NettoPos > 0
GROUP BY p.ArtNr
ORDER BY SUM(p.NettoPos) DESC
"""

SQL["m_bp_w_gesperrt"] = f"""
WITH b AS (
    {BELEGE}
)
SELECT TOP 500 b.VogAdrNr AS AdrNr, MAX({KUNDE}) AS Kunde,
    CONVERT(char(10), MAX(a.AdrGspDat), 104) AS GesperrtSeit,
    COUNT(*) AS Rechnungen, CAST(SUM(b.Vz * b.Netto) AS DECIMAL(18,2)) AS Umsatz,
    CONVERT(char(10), MAX(b.VogDat), 104) AS LetzteRechnung,
    MAX(LEFT(REPLACE(REPLACE(a.AdrGspInfo, CHAR(13), ' '), CHAR(10), ' '), 200)) AS Sperrgrund
FROM b JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE a.AdrGspKz = 1 AND b.VogDat >= DATEADD(DAY, -90, CAST(GETDATE() AS date))
GROUP BY b.VogAdrNr
ORDER BY SUM(b.Vz * b.Netto) DESC
"""

SQL["m_bp_w_ek_unplausibel"] = f"""
WITH b AS (
    {BELEGE}
)
SELECT TOP 500 b.VogBelegNr AS Beleg, b.VogArt AS Art, CONVERT(char(10), b.VogDat, 104) AS Datum,
    b.VogAdrNr AS AdrNr, {KUNDE} AS Kunde,
    CAST(b.Netto AS DECIMAL(18,2)) AS Umsatz, CAST(b.Ek AS DECIMAL(18,2)) AS Einsatz,
    CAST(b.Ek - b.Netto AS DECIMAL(18,2)) AS Verzerrung,
    CAST(CASE WHEN b.Netto > 0 THEN b.Ek / b.Netto END AS DECIMAL(18,1)) AS EkFaktor,
    b.VogVerk AS Bearbeiter, CONCAT(CASE b.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, b.VogID) AS VogID
FROM b LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE b.Ek > 100 AND b.Ek > b.Netto * {{{{ek_faktor}}}}
ORDER BY b.Ek - b.Netto DESC
"""

NAMEN = {
    "m_bp_kpi": "büro+ GF – Kennzahlen",
    "m_bp_pipeline": "büro+ GF – Vertriebspipeline",
    "m_bp_verlauf": "büro+ GF – Umsatzverlauf",
    "m_bp_rg_monat": "büro+ GF – Rechnungen des Monats (Detail)",
    "m_bp_positionen": "büro+ GF – Positionen des Belegs (Detail)",
    "m_bp_w_lieferscheine": "büro+ GF – Lieferscheine ohne Rechnung",
    "m_bp_w_angebote": "büro+ GF – Alte offene Angebote",
    "m_bp_w_ohne_ek": "büro+ GF – Umsatz ohne Einkaufspreis",
    "m_bp_w_gesperrt": "büro+ GF – Gesperrte Kunden mit Umsatz",
    "m_bp_w_ek_unplausibel": "büro+ GF – Belege mit unplausiblem Einkaufspreis",
}

exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) if "__file__" in globals() else "/tmp", "artikel_sql.py")).read())
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) if "__file__" in globals() else "/tmp", "kunden_sql.py")).read())
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) if "__file__" in globals() else "/tmp", "verkauf12_sql.py")).read())
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)) if "__file__" in globals() else "/tmp", "inventur_sql.py")).read())

def aliase(sql):
    """SELECT-Aliase der äußersten Abfrage (… AS Name)."""
    letzte = sql[sql.rfind("\nSELECT"):] if "\nSELECT" in sql else sql
    letzte = letzte.split("\nFROM")[0]
    return re.findall(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|$)", letzte, flags=re.M) or []

def mapping(mid, felder):
    sql = SQL[mid].strip()
    return {
        "id": mid, "name": NAMEN[mid], "canvas_nodes": [], "joins": [],
        "sql_nodes": [{"id": "sql1", "x": 120, "y": 40, "width": 380, "height": 260,
                       "connection_id": CONN, "mode": "transform", "output_field": "sql_1",
                       "output_fields": felder, "sql": sql}],
        "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
        "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
        "targets": [{"id": "t1", "name": NAMEN[mid], "target_type": "dataset",
                     "target_connection_id": None, "target_table": "", "target_write_mode": "replace",
                     "target_options": {},
                     "fields": [{"source_field": f, "target_field": f, "target_type": "string",
                                 "source_dataset_id": "__sql__sql1",
                                 "transformer": {"type": "direct", "source_field": f}} for f in felder]}],
    }

FELDER = json.load(open(sys.argv[2]))   # vom Test ermittelte Ergebnisspalten je Mapping

def kpi(wid, label, col, act="act_kpi", width=3, prefix="€ ", suffix="", dec=2, vj=True, invert=False, hint=None, breakdown=None):
    c = {"width": width, "column": col, "aggregation": "first", "prefix": prefix, "suffix": suffix, "decimals": dec}
    if vj:
        c.update({"compare_column": col + "VJ", "compare_label": "Vorjahr", "invert_delta": invert})
    if hint: c["hint"] = hint
    if breakdown: c["breakdown"] = breakdown
    return {"id": wid, "type": "kpi", "label": label, "action_id": act, "config": c}

DD_POS = {"mapping_id": "m_bp_positionen", "param": "vogid", "key_column": "VogID", "title": "Positionen des Belegs"}
widgets_roh = [
    kpi("w_umsatz", "Umsatz netto", "Umsatz", hint="Gebuchte Rechnungen und Sammelrechnungen im Zeitraum, netto. Stornierte und nicht gebuchte Belege zählen nicht."),
    kpi("w_umsatz_nk", "Umsatz nach Korrekturen", "UmsatzNachKorrektur",
        breakdown=[{"label": "Umsatz netto", "column": "Umsatz"},
                   {"label": "− Rechnungskorrekturen", "column": "KorrekturWert"},
                   {"label": "Anzahl Korrekturen", "column": "KorrekturAnzahl", "prefix": "", "decimals": 0},
                   {"label": "Korrekturen Vorjahr", "column": "KorrekturWertVJ"}],
        hint="Umsatz abzüglich der Rechnungskorrekturen – die kaufmännisch belastbare Zahl. büro+ führt Korrekturen mit positivem Betrag; sie werden hier abgezogen."),
    kpi("w_wareneinsatz", "Wareneinsatz", "Wareneinsatz", invert=True,
        hint="Summe der Einkaufspreise für den Rohertrag (büro+-Feld GEkRoh) der berechneten Ware, Korrekturen gegengerechnet. Positionen ohne Einkaufspreis fehlen hier – siehe „Heute zu tun“."),
    kpi("w_rohertrag", "Rohertrag", "Rohertrag",
        breakdown=[{"label": "Umsatz nach Korrekturen", "column": "Warenumsatz"}, {"label": "− Wareneinsatz (EK)", "column": "Wareneinsatz"}],
        hint="Umsatz − Einkaufspreis für den Rohertrag (büro+-Feld GEkRoh), Korrekturen gegengerechnet. Positionen ohne Einkaufspreis zählen mit 100 % Marge – siehe Kachel „Umsatz ohne EK“."),
    kpi("w_marge", "Marge", "Marge", prefix="", suffix=" %", dec=1),
    kpi("w_rechnungen", "Rechnungen", "Rechnungen", prefix="", dec=0),
    kpi("w_avg", "Ø Rechnungswert", "AvgRechnung"),
    kpi("w_kunden", "Aktive Kunden", "AktiveKunden", prefix="", dec=0,
        hint="Adressen mit mindestens einer Rechnung im Zeitraum. Ein Barverkaufskonto zählt als ein Kunde."),
    {"id": "w_ai", "type": "ai_summary", "label": "KI-Kurzanalyse der Kennzahlen", "action_id": "act_kpi",
     "config": {"width": 12, "report_layout": True,
                "instruction": "Daten aus microtech büro+. Rechnungskorrekturen sind bereits als eigene Kennzahl ausgewiesen. Bewerte auch die Vertriebspipeline (offene Angebote, Auftragsbestand, Lieferscheine ohne Rechnung).",
                "extra_sections": [{"action_id": "act_pipeline", "label": "Vertriebspipeline (Stand heute)", "kind": "kpi"}]}},
    kpi("w_angebote", "Offene Angebote", "AngeboteWert", act="act_pipeline", vj=False,
        breakdown=[{"label": "Angebote", "column": "AngeboteOffen", "prefix": "", "decimals": 0},
                   {"label": "davon älter als 90 Tage", "column": "AngeboteAlt", "prefix": "", "decimals": 0},
                   {"label": "Wert der alten Angebote", "column": "AngeboteAltWert"},
                   {"label": "nicht gezählt: älter als {{pipeline_monate}} Monate", "column": "AngeboteAusserFrist", "prefix": "", "decimals": 0},
                   {"label": "deren Wert", "column": "AngeboteAusserFristWert"}],
        hint="Offene Angebote der letzten {{pipeline_monate}} Monate aus der Vorgangsübersicht – Stand heute, unabhängig vom gewählten Zeitraum. Ältere offene Angebote zählen nicht mit (siehe Warnung „Alte offene Angebote“)."),
    kpi("w_frisch", "Angebote der letzten 90 Tage", "AngeboteFrischWert", act="act_pipeline", vj=False,
        hint="Der realistische Teil der Pipeline: offene Angebote, die höchstens 90 Tage alt sind."),
    kpi("w_auftraege", "Auftragsbestand", "AuftragsbestandWert", act="act_pipeline", vj=False,
        breakdown=[{"label": "offene Auftragsbestätigungen", "column": "AuftraegeOffen", "prefix": "", "decimals": 0},
                   {"label": "nicht gezählt: älter als {{pipeline_monate}} Monate", "column": "AuftraegeAusserFrist", "prefix": "", "decimals": 0},
                   {"label": "deren Wert", "column": "AuftraegeAusserFristWert"}],
        hint="Auftragsbestätigungen der letzten {{pipeline_monate}} Monate in der Vorgangsübersicht: zugesagt, aber noch nicht geliefert bzw. berechnet. Ältere offene AB zählen nicht mit – meist sind sie in büro+ nur nicht erledigt."),
    kpi("w_lieferscheine", "Geliefert, nicht berechnet", "LieferscheineWert", act="act_pipeline", vj=False, invert=True,
        breakdown=[{"label": "Lieferscheine", "column": "LieferscheineOffen", "prefix": "", "decimals": 0},
                   {"label": "ältester (Tage)", "column": "LieferscheinAeltesterTage", "prefix": "", "decimals": 0}],
        hint="Lieferscheine in der Vorgangsübersicht, aus denen noch keine Rechnung geworden ist."),
    {"id": "w_alerts", "type": "alerts", "label": "📋 Heute zu tun", "action_id": "act_alerts",
     "config": {"width": 12, "info": "Jede Zeile ist eine Prüfregel auf den büro+-Daten. Klick öffnet die Detailliste."}},
    {"id": "w_verlauf", "type": "line", "label": "Umsatzentwicklung nach Korrekturen (aktuell vs. Vorjahr)", "action_id": "act_verlauf",
     "config": {"width": 12, "x_column": "Monat", "y_columns": ["Umsatz", "UmsatzVorjahr"], "curved": True,
                "drilldown": {"mapping_id": "m_bp_rg_monat", "key_column": "Monat", "param": "monat",
                              "title": "Rechnungen und Korrekturen dieses Monats", "hidden_columns": ["VogID", "Sortierung"],
                              "levels": [DD_POS]}}},
]

REIHENFOLGE = ["w_umsatz", "w_umsatz_nk", "w_wareneinsatz", "w_rohertrag", "w_marge", "w_rechnungen", "w_avg", "w_kunden",
               "w_angebote", "w_frisch", "w_auftraege", "w_lieferscheine", "w_alerts", "w_verlauf", "w_ai"]
_w = {w["id"]: w for w in widgets_roh}
widgets = [_w[i] for i in REIHENFOLGE]

# ── Reiter „Artikel & Warengruppen“ ─────────────────────────────────────────
DD_ART = {"mapping_id": "m_bp_art_belege", "key_column": "ArtNr", "param": "artnr",
          "title": "Belege mit diesem Artikel im Zeitraum", "hidden_columns": ["VogID"], "levels": [DD_POS]}
DD_WG = {"mapping_id": "m_bp_wg_artikel", "key_column": "Warengruppe", "param": "warengruppe",
         "title": "Artikel dieser Warengruppe", "hidden_columns": [],
         "levels": [{"mapping_id": "m_bp_art_belege", "param": "artnr", "key_column": "ArtNr",
                     "title": "Belege mit diesem Artikel", "hidden_columns": ["VogID"]}, DD_POS]}
PREIS_INFO = ("Preise je Preiseinheit des Artikels (bei %o je 1.000 Stück). Listenpreis = büro+-Preis {{listenpreis}}; "
              "Nachlass = wie weit der tatsächlich berechnete Preis im Schnitt darunter liegt.")
A = "act_art_kpi"
widgets += [
    kpi("w_art_verkauft", "Verkaufte Artikel", "ArtikelVerkauft", act=A, prefix="", dec=0,
        breakdown=[{"label": "Warengruppen", "column": "Warengruppen", "prefix": "", "decimals": 0}],
        hint="Verschiedene Artikel mit mindestens einer berechneten Position im Zeitraum."),
    kpi("w_art_top20", "Anteil Top-20-Artikel", "AnteilTop20", act=A, prefix="", suffix=" %", dec=1, vj=False,
        breakdown=[{"label": "Umsatz der Top 20", "column": "UmsatzTop20"}],
        hint="Wie viel des Artikelumsatzes auf die 20 umsatzstärksten Artikel entfällt – Maß für die Abhängigkeit von wenigen Artikeln."),
    kpi("w_art_nachlass", "Ø Nachlass auf Listenpreis", "Nachlass", act=A, prefix="", suffix=" %", dec=1, invert=True,
        breakdown=[{"label": "Nachlass in €", "column": "NachlassWert"}],
        hint="Berechneter Umsatz gegenüber Menge × Listenpreis ({{listenpreis}}), nur Artikel mit Listenpreis. Enthält vereinbarte Kundenpreise – kein Fehler, sondern Preisniveau."),
    kpi("w_art_unter_ek", "Verkauf unter Einkaufspreis", "VerlustUnterEk", act=A, invert=True,
        breakdown=[{"label": "Positionen", "column": "PosUnterEk", "prefix": "", "decimals": 0},
                   {"label": "Artikel", "column": "ArtikelUnterEk", "prefix": "", "decimals": 0}],
        hint="Summe der Verluste aus Positionen, deren Einkaufspreis über dem Verkaufspreis lag. Enthält auch Erfassungsfehler beim EK – siehe Tabelle unten."),
    kpi("w_art_aktiv", "Aktive Artikel im Sortiment", "AktiveArtikel", act=A, prefix="", dec=0, vj=False, width=4,
        hint="Nicht gesperrte Artikel in büro+."),
    kpi("w_art_ohne", "davon ohne Verkauf seit 12 Monaten", "OhneVerkauf12M", act=A, prefix="", dec=0, vj=False, width=4, invert=True,
        breakdown=[{"label": "Anteil", "column": "AnteilOhneVerkauf", "prefix": "", "suffix": " %", "decimals": 1}],
        hint="Aktive Artikel ohne Rechnung in den zwölf Monaten bis zum Ende des Zeitraums – Kandidaten zum Sperren oder Bereinigen. Liste ganz unten."),
    kpi("w_art_gesperrt", "Gesperrt, aber verkauft", "GesperrtVerkauft", act=A, prefix="", dec=0, vj=False, width=4, invert=True,
        hint="Gesperrte Artikel, die in den letzten zwölf Monaten trotzdem berechnet wurden – Sperre veraltet oder umgangen."),
    {"id": "w_wg_bar", "type": "bar", "label": "Umsatz nach Warengruppe – Top 15 (aktuell vs. Vorjahr)", "action_id": "act_wg_top",
     "config": {"width": 12, "x_column": "Warengruppe", "y_columns": ["Umsatz", "UmsatzVJ"], "stacked": False, "drilldown": DD_WG}},
    {"id": "w_wg_tbl", "type": "table", "label": "Warengruppen-Entwicklung", "action_id": "act_wg",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_WG,
                "info": "Warengruppe in der heutigen Zuordnung des Artikels (büro+ speichert sie nicht im Beleg). Rohertrag = Umsatz − Einkaufspreis der Positionen, Korrekturen gegengerechnet. Klick: Artikel der Warengruppe."}},
    {"id": "w_art_top", "type": "table", "label": "Top 50 Artikel nach Umsatz", "action_id": "act_top_artikel",
     "config": {"width": 12, "drilldown": DD_ART, "info": PREIS_INFO + " Klick: Belege mit diesem Artikel."}},
    {"id": "w_art_unter_ek_tbl", "type": "table", "label": "Verkauf unter Einkaufspreis", "action_id": "act_art_unter_ek",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_ART,
                "info": "Artikel mit Positionen im Zeitraum, deren Einkaufspreis über dem Verkaufspreis lag. Liegt der EK um Zehnerpotenzen über dem heutigen Kalkulations-EK, ist es meist ein Erfassungsfehler (Stück statt 1.000)."}},
    {"id": "w_art_preispflege", "type": "table", "label": "Preiserhöhung prüfen", "action_id": "act_art_preispflege",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_ART,
                "info": "Letzte 90 Tage bis Zeitraumende gegen dieselben 90 Tage im Vorjahr: Einkaufspreis um mehr als 3 % gestiegen, Verkaufspreis nicht im selben Maß, Listenpreis seit über einem Jahr unverändert. MargeVerlust90Tage = Rohertrag, der durch den nicht weitergegebenen Anstieg fehlt."}},
]

# ── Reiter „Kunden“ ─────────────────────────────────────────────────────────
DD_KD = {"mapping_id": "m_bp_kd_belege", "key_column": "AdrNr", "param": "adrnr",
         "title": "Belege des Kunden (Zeitraum und Vorjahr)", "hidden_columns": ["VogID"], "levels": [DD_POS]}
K = "act_kd_kpi"
widgets_kd = [
    kpi("w_kd_aktiv", "Aktive Kunden", "AktiveKunden", act=K, prefix="", dec=0,
        hint="Adressen mit mindestens einer Rechnung im Zeitraum."),
    kpi("w_kd_neu", "Neukunden", "Neukunden", act=K, prefix="", dec=0,
        breakdown=[{"label": "Umsatz der Neukunden", "column": "UmsatzNeukunden"}],
        hint="Kunden, deren allererste Rechnung in den Zeitraum fällt. Maßgeblich ist der geladene Datenbestand (Archiv ab 2020) – für Zeiträume in 2020 ist die Zahl deshalb zu hoch."),
    kpi("w_kd_avg", "Ø Umsatz je Kunde", "UmsatzJeKunde", act=K),
    kpi("w_kd_top10", "Umsatzanteil Top-10-Kunden", "AnteilTop10", act=K, prefix="", suffix=" %", dec=1, vj=False,
        breakdown=[{"label": "Top 5", "column": "AnteilTop5", "prefix": "", "suffix": " %", "decimals": 1}],
        hint="Klumpenrisiko: wie viel des Umsatzes an den zehn größten Kunden hängt."),
    kpi("w_kd_rueckgang", "Kunden mit Rückgang > 20 %", "KundenRueckgang", act=K, prefix="", dec=0, vj=False, width=6, invert=True,
        breakdown=[{"label": "Umsatz weniger als im Vorjahr", "column": "Rueckgang"}],
        hint="Kunden, die im Zeitraum mehr als 20 % weniger Umsatz brachten als im gleichen Zeitraum des Vorjahres (einschließlich Kunden ganz ohne Umsatz)."),
    kpi("w_kd_schlaf", "Schlafende Stammkunden", "Schlafend", act=K, prefix="", dec=0, vj=False, width=6, invert=True,
        breakdown=[{"label": "Jahresumsatz in Gefahr", "column": "UmsatzInGefahr"}],
        hint="Stand heute: mindestens {{schlaf_min_rechnungen}} Rechnungen in 24 Monaten, aber seit über {{schlaf_tage}} Tagen keine mehr. Jahresumsatz = Umsatz der zwölf Monate vor ihrer letzten Rechnung."),
    {"id": "w_kd_abc", "type": "table", "label": "ABC-Verteilung der Kunden", "action_id": "act_kd_abc",
     "config": {"width": 6, "info": "A = die Kunden, die zusammen 80 % des Umsatzes bringen, B = die nächsten 15 %, C = der Rest."}},
    {"id": "w_kd_status", "type": "pie", "label": "Umsatz nach Adress-Status", "action_id": "act_kd_status",
     "config": {"width": 6, "label_column": "Status", "value_column": "Umsatz", "donut": True}},
    {"id": "w_kd_top", "type": "table", "label": "Top 25 Kunden", "action_id": "act_kd_top",
     "config": {"width": 12, "drilldown": DD_KD, "info": "Klick: Belege des Kunden im Zeitraum und im Vorjahreszeitraum, weiter bis zu den Positionen."}},
    {"id": "w_kd_rueckgang_tbl", "type": "table", "label": "Kunden mit dem größten Rückgang", "action_id": "act_kd_rueckgang",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_KD}},
    {"id": "w_kd_schlaf_tbl", "type": "table", "label": "Schlafende Stammkunden – zurückgewinnen", "action_id": "act_kd_schlafend",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_KD,
                "info": "Ausgewählt sind Stammkunden mit mindestens {{schlaf_min_rechnungen}} Rechnungen in den letzten 24 Monaten, deren letzte Rechnung länger als {{schlaf_tage}} Tage zurückliegt (ohne Barverkauf). Jahresumsatz = Netto-Umsatz der 12 Monate vor ihrer letzten Rechnung. Gezählt werden gebuchte, nicht stornierte Rechnungen. Stand heute, unabhängig vom gewählten Zeitraum; größter Jahresumsatz zuerst, Telefon aus der Rechnungsanschrift. Gesperrte Adressen sind enthalten (Spalte Sperre) und lassen sich über den Filter ausblenden."}},
    {"id": "w_kd_neu_tbl", "type": "table", "label": "Neukunden im Zeitraum", "action_id": "act_kd_neu",
     "config": {"width": 12, "full_rows": True, "drilldown": DD_KD, "info": "Umsatz und Rohertrag seit der ersten Rechnung bis zum Ende des Zeitraums."}},
]
widgets += [
    {"id": "w_art_ohne_tbl", "type": "table", "label": "Aktive Artikel ohne Verkauf seit 12 Monaten", "action_id": "act_art_ohne",
     "config": {"width": 12, "full_rows": True, "info": "Zuletzt verkaufte zuerst; Artikel ganz ohne Verkauf seit 2020 am Ende."}},
] + widgets_kd

# ── Reiter „Artikel-Verkauf“: Gruppentabelle Warengruppe → Artikel, rollierende 12-Monats-Scheiben ──
DD_V12 = {"mapping_id": "m_bp_v12_kunden", "key_column": "ArtNr", "param": "artnr",
          "title": "Kunden dieses Artikels – wer kauft ihn nicht mehr?", "hidden_columns": ["KdArt"],
          "levels": [{"mapping_id": "m_bp_v12_kd_belege", "param": "kdart", "key_column": "KdArt",
                      "title": "Belege des Kunden mit diesem Artikel", "hidden_columns": ["VogID"]}, DD_POS]}
widgets += [
    {"id": "w_v12", "type": "gruppentabelle", "label": "Artikel-Verkauf – rollierende 12-Monats-Scheiben", "action_id": "act_v12",
     "config": {"width": 12, "full_rows": 8000, "gruppe": "Warengruppe",
                "text_spalten": ["ArtNr", "Bezeichnung", "Einheit", "Sperre"],
                "kennzahlen": [{"id": "menge", "label": "Menge", "praefix": "M", "summe": "einheit", "dezimal": 0},
                               {"id": "umsatz", "label": "Umsatz €", "praefix": "U", "summe": True, "dezimal": 0},
                               {"id": "rohertrag", "label": "Rohertrag €", "praefix": "R", "summe": True, "dezimal": 0}],
                "scheiben": 6, "einheit_spalte": "Einheit",
                "einheit_gleich": {"%o": "Stück", "%": "Stück", "Stk": "Stück", "Stück": "Stück", "Stk.": "Stück", "St": "Stück"},
                "zusatz_spalten": [{"spalte": "Kunden0", "titel": "Kunden 12 M"}, {"spalte": "Kunden1", "titel": "Kunden VJ"},
                                   {"spalte": "LetzterVerkauf", "titel": "zuletzt verkauft"}],
                "aktiv_spalte": "Aktuell", "such_spalte": "Suchtext", "drilldown": DD_V12,
                "info": "Zwölf-Monats-Scheiben bis zum Ende des gewählten Zeitraums, Korrekturen gegengerechnet. Menge in der Einheit des Artikels (bei %o in Stück); bei gemischten Einheiten ist die Warengruppen-Summe blass mit „≈“ markiert. Suche über Artikelnummer, Bezeichnungen, Suchbegriff und Barcode; mehrere Wörter = alle müssen vorkommen. Klick auf einen Artikel: seine Kunden, wer ihn nicht mehr kauft zuerst."}},
]

# ── Reiter „Inventurliste“: verkaufte Artikel als Zählvorlage, Export CSV/Excel ──
widgets += [
    {"id": "w_inventur", "type": "table", "label": "Inventurliste – Artikel mit Verkauf in den letzten {{inventur_monate}} Monaten", "action_id": "act_inventur",
     "config": {"width": 12, "full_rows": 6000,
                "drilldown": {"mapping_id": "m_bp_inventur_belege", "key_column": "ArtNr", "param": "artnr",
                              "title": "Belege mit diesem Artikel in den letzten {{inventur_monate}} Monaten",
                              "hidden_columns": ["VogID"], "levels": [DD_POS]},
                "info": "Stand heute, unabhängig vom gewählten Zeitraum. Alle Artikel mit Rechnung in den letzten {{inventur_monate}} Monaten, ohne DSZ-Gebühren und ohne Text-/Leistungsartikel (keine Warengruppe und kein EK). "
                        "Paletten, Kartons und Stück sind leer – zum Eintragen nach dem Export (CSV/Excel). EK = Kalkulations-EK aus büro+ je Mengeneinheit "
                        "(Tsd = je 1.000 Stück); zum Vergleich der EK der letzten Bestellung. Verkauft = Menge und Umsatz im selben Zeitraum, Korrekturen gegengerechnet. "
                        "Klick auf einen Artikel: seine Belege im selben Zeitraum."}},
]

def warnung(key, name, mid, cond, facts, title, sub, sev="warnung", sort=10, dd_title=None):
    return {"rule_key": key, "name": name, "category": "Geschäftsführung", "cockpit": "büro+ GF-Cockpit",
            "description": None, "severity": sev, "severity_levels": [], "mapping_id": None,
            "mapping_name": NAMEN[mid], "params": {}, "condition": cond, "facts": facts,
            "title_template": title, "subtitle": sub,
            "drilldown": {"mapping_name": NAMEN[mid], "title": dd_title or name, "hidden_columns": ["VogID"],
                          "levels": [{"mapping_name": NAMEN["m_bp_positionen"], "param": "vogid", "key_column": "VogID", "title": "Positionen des Belegs"}] if "VogID" in FELDER[mid] else []},
            "action_kind": None, "active": True, "sort": sort}

alert_rules = [
    warnung("bp_lieferscheine_offen", "Lieferscheine ohne Rechnung", "m_bp_w_lieferscheine",
            {"mode": "count", "value_column": "Wert", "min_count": 1, "value_unit": "€"},
            [{"label": "Ältester", "column": "Datum", "unit": "", "decimals": 0}, {"label": "Kunde", "column": "Kunde", "unit": "", "decimals": 0}],
            "{anzahl} Lieferscheine ohne Rechnung – {summe} € geliefert, aber nicht berechnet",
            "Älter als die eingestellte Frist. Zeile anklicken: die Lieferscheine, älteste zuerst.", sev="kritisch", sort=1),
    warnung("bp_umsatz_ohne_ek", "Umsatz ohne Einkaufspreis", "m_bp_w_ohne_ek",
            {"mode": "count", "value_column": "Umsatz", "min_count": 1, "value_unit": "€"},
            [{"label": "Größter Artikel", "column": "ArtNr", "unit": "", "decimals": 0}],
            "{anzahl} Artikel ohne Einkaufspreis verkauft (90 Tage) – {summe} € Umsatz mit 100 % Marge",
            "Der Rohertrag ist um diesen Betrag geschönt. EK am Artikel in büro+ nachtragen.", sort=2),
    warnung("bp_ek_unplausibel", "Unplausibler Einkaufspreis", "m_bp_w_ek_unplausibel",
            {"mode": "count", "value_column": "Verzerrung", "min_count": 1, "value_unit": "€"},
            [{"label": "Größter", "column": "Beleg", "unit": "", "decimals": 0}, {"label": "Datum", "column": "Datum", "unit": "", "decimals": 0},
             {"label": "Umsatz", "column": "Umsatz", "unit": "€", "decimals": 0}, {"label": "Einsatz", "column": "Einsatz", "unit": "€", "decimals": 0}],
            "{anzahl} Belege mit unplausiblem Einkaufspreis – Rohertrag um {summe} € verfälscht",
            "Einkaufspreis mehr als das eingestellte Vielfache des Umsatzes – meist ein Erfassungsfehler (z. B. Preis je Stück statt je 1.000). In büro+ korrigieren; Zeile anklicken: Belege, dann Positionen.", sort=2),
    warnung("bp_kd_schlafend", "Schlafende Stammkunden", "m_bp_kd_schlafend",
            {"mode": "count", "value_column": "Jahresumsatz", "min_count": 1, "value_unit": "€"},
            [{"label": "Größter", "column": "Kunde", "unit": "", "decimals": 0}, {"label": "Letzte Rechnung", "column": "LetzteRechnung", "unit": "", "decimals": 0}],
            "{anzahl} Stammkunden bestellen seit über {{schlaf_tage}} Tagen nicht mehr – {summe} € Jahresumsatz in Gefahr",
            "Größter Jahresumsatz zuerst. Anrufen, bevor der Kunde ganz weg ist.", sort=4, dd_title="Schlafende Stammkunden"),
    warnung("bp_gesperrt_mit_umsatz", "Gesperrte Kunden mit Umsatz", "m_bp_w_gesperrt",
            {"mode": "count", "value_column": "Umsatz", "min_count": 1, "value_unit": "€"},
            [{"label": "Größter", "column": "Kunde", "unit": "", "decimals": 0}],
            "{anzahl} gesperrte Kunden haben in 90 Tagen trotzdem Rechnungen bekommen – {summe} €",
            "Entweder ist die Sperre veraltet oder sie wird umgangen. Sperrgrund steht in der Liste.", sort=3),
    warnung("bp_angebote_alt", "Alte offene Angebote", "m_bp_w_angebote",
            {"mode": "rows", "value_column": "Wert", "limit": 5000, "value_unit": "€"},
            [{"label": "Größtes", "column": "Kunde", "unit": "", "decimals": 0}],
            "{anzahl} Angebote älter als die Frist – {summe} € in der Pipeline, die wohl nicht mehr kommt",
            "Nachfassen oder in büro+ erledigen bzw. archivieren, damit die Pipeline stimmt.", sev="info", sort=4),
]

tpl = {
    "format_version": "1.0",
    "template_id": "bueroplus_gf_cockpit",
    "template_name": "büro+ – GF-Cockpit",
    "description": "Geschäftsführer-Cockpit für microtech büro+ auf Basis der Export-Layouts (Artikel, Adressen, Vorgänge mit Positionen, Übersicht und Archiv).",
    "category": "bueroplus-reporting",
    "version": "0.11",
    "author": "Datenmonster",
    "hinweise": [
        "Erwartet im SQL-Server die Tabellen dbo.Artikel, dbo.Adressen, dbo.Vorgang, dbo.VorgangArchiv, dbo.VorgangPosition, dbo.VorgangPositionArchiv und die Views dbo.vVorgang, dbo.vVorgangPosition (Spaltennamen = büro+-Feldnamen ohne Punkte).",
        "Umsatz = gebuchte Rechnungen und Sammelrechnungen; Rechnungskorrekturen werden gesondert ausgewiesen und abgezogen.",
    ],
    "config_required": [
        {"key": "connection_bp", "label": "SQL-Server mit den büro+-Exporttabellen", "type": "connection", "default": ""},
        {"key": "lieferschein_tage", "label": "Lieferschein ohne Rechnung melden ab … Tagen", "type": "text", "default": "7"},
        {"key": "angebot_tage", "label": "Angebot gilt als alt ab … Tagen", "type": "text", "default": "90"},
        {"key": "pipeline_monate", "label": "Offene Angebote/AB zählen in der Pipeline nur bis … Monate alt", "type": "text", "default": "12"},
        {"key": "inventur_monate", "label": "Inventurliste: Artikel mit Verkauf in den letzten … Monaten", "type": "text", "default": "12"},
        {"key": "listenpreis", "label": "Listenpreis-Feld des Artikels (ArtVk0Preis … ArtVk9Preis)", "type": "text", "default": "ArtVk0Preis"},
        {"key": "schlaf_tage", "label": "Stammkunde gilt als schlafend nach … Tagen ohne Rechnung", "type": "text", "default": "90"},
        {"key": "schlaf_min_rechnungen", "label": "Stammkunde = mindestens … Rechnungen in 24 Monaten", "type": "text", "default": "4"},
        {"key": "barverkauf_adrnr", "label": "Adressnummer des Barverkaufs-Kontos (0 = keins)", "type": "text", "default": "0"},
        {"key": "ek_faktor", "label": "Einkaufspreis unplausibel ab dem …-fachen des Umsatzes", "type": "text", "default": "2"},
    ],
    "datasets": [], "pipelines": [],
    "mappings": [mapping(m, FELDER[m]) for m in SQL],
    "forms": [{
        "name": "büro+ GF-Cockpit", "portal_config": {},
        "schema": {
            "fields": [{"id": "f_zeitraum", "type": "daterange", "row": 0, "colSpan": 12, "label": "Zeitraum",
                        "name": "zeitraum", "action_ids": [],
                        "config": {"param_from": "von", "param_to": "bis", "default": "this_year", "auto_run": True}}],
            "layout": [],
            "actions": [
                {"id": "act_alerts", "type": "run_alerts", "mapping_id": None, "pipeline_id": None,
                 "label": "Warnungen prüfen", "options": {"cockpits": ["büro+ GF-Cockpit"]}},
                {"id": "act_kpi", "type": "run_mapping", "mapping_id": "m_bp_kpi", "pipeline_id": None, "label": "Kennzahlen"},
                {"id": "act_pipeline", "type": "run_mapping", "mapping_id": "m_bp_pipeline", "pipeline_id": None, "label": "Vertriebspipeline"},
                {"id": "act_verlauf", "type": "run_mapping", "mapping_id": "m_bp_verlauf", "pipeline_id": None, "label": "Umsatzverlauf"},
                {"id": "act_art_kpi", "type": "run_mapping", "mapping_id": "m_bp_art_kpi", "pipeline_id": None, "label": "Artikel-Kennzahlen"},
                {"id": "act_wg_top", "type": "run_mapping", "mapping_id": "m_bp_wg_top", "pipeline_id": None, "label": "Top-Warengruppen"},
                {"id": "act_wg", "type": "run_mapping", "mapping_id": "m_bp_wg", "pipeline_id": None, "label": "Warengruppen-Entwicklung"},
                {"id": "act_top_artikel", "type": "run_mapping", "mapping_id": "m_bp_top_artikel", "pipeline_id": None, "label": "Top-Artikel"},
                {"id": "act_art_unter_ek", "type": "run_mapping", "mapping_id": "m_bp_art_unter_ek", "pipeline_id": None, "label": "Verkauf unter Einkaufspreis"},
                {"id": "act_art_preispflege", "type": "run_mapping", "mapping_id": "m_bp_art_preispflege", "pipeline_id": None, "label": "Preiserhöhung prüfen"},
                {"id": "act_art_ohne", "type": "run_mapping", "mapping_id": "m_bp_art_ohne_verkauf", "pipeline_id": None, "label": "Artikel ohne Verkauf"},
                {"id": "act_v12", "type": "run_mapping", "mapping_id": "m_bp_v12_artikel", "pipeline_id": None, "label": "Artikel-Verkauf 12-Monats-Vergleich"},
                {"id": "act_inventur", "type": "run_mapping", "mapping_id": "m_bp_inventurliste", "pipeline_id": None, "label": "Inventurliste"},
                {"id": "act_kd_kpi", "type": "run_mapping", "mapping_id": "m_bp_kd_kpi", "pipeline_id": None, "label": "Kunden-Kennzahlen"},
                {"id": "act_kd_abc", "type": "run_mapping", "mapping_id": "m_bp_kd_abc", "pipeline_id": None, "label": "ABC-Kunden"},
                {"id": "act_kd_status", "type": "run_mapping", "mapping_id": "m_bp_kd_status", "pipeline_id": None, "label": "Umsatz nach Adress-Status"},
                {"id": "act_kd_top", "type": "run_mapping", "mapping_id": "m_bp_kd_top", "pipeline_id": None, "label": "Top-Kunden"},
                {"id": "act_kd_rueckgang", "type": "run_mapping", "mapping_id": "m_bp_kd_rueckgang", "pipeline_id": None, "label": "Kunden mit Rückgang"},
                {"id": "act_kd_schlafend", "type": "run_mapping", "mapping_id": "m_bp_kd_schlafend", "pipeline_id": None, "label": "Schlafende Stammkunden"},
                {"id": "act_kd_neu", "type": "run_mapping", "mapping_id": "m_bp_kd_neu", "pipeline_id": None, "label": "Neukunden"},
            ],
            "widgets": widgets,
            "result_tabs": [{"id": "tab_uebersicht", "label": "Übersicht",
                             "action_ids": ["act_alerts", "act_kpi", "act_pipeline", "act_verlauf"]},
                            {"id": "tab_artikel", "label": "Artikel & Warengruppen",
                             "action_ids": ["act_art_kpi", "act_wg_top", "act_wg", "act_top_artikel", "act_art_unter_ek",
                                            "act_art_preispflege", "act_art_ohne"]},
                            {"id": "tab_v12", "label": "Artikel-Verkauf", "action_ids": ["act_v12"]},
                            {"id": "tab_inventur", "label": "Inventurliste", "action_ids": ["act_inventur"]},
                            {"id": "tab_kunden", "label": "Kunden",
                             "action_ids": ["act_kd_kpi", "act_kd_abc", "act_kd_status", "act_kd_top", "act_kd_rueckgang",
                                            "act_kd_schlafend", "act_kd_neu"]}],
            "reiter_gruppen": [{"id": "g_uebersicht", "label": "Unternehmensübersicht", "reiter": ["tab_uebersicht"]},
                               {"id": "g_vertrieb", "label": "Vertrieb & Sortiment", "reiter": ["tab_kunden", "tab_artikel", "tab_v12"]},
                               {"id": "g_lager", "label": "Lager", "reiter": ["tab_inventur"]}],
            "show_ai_assistant": True,
            "rubrik": {"id": "gf"},
            "doku": {"intro": "Die Gesamtsicht für die Geschäftsführung auf Basis von microtech büro+: Umsatz und Rohertrag mit Vorjahresvergleich, die Vertriebspipeline von Angebot bis Lieferschein und was heute zu tun ist. Jede Kurve lässt sich bis auf den einzelnen Beleg und seine Positionen aufklappen.",
                     "hinweise": ["Umsatz zählt gebuchte Rechnungen, nicht Auftragseingänge.",
                                  "Rechnungskorrekturen führt büro+ mit positivem Betrag; das Cockpit weist sie gesondert aus und zieht sie ab.",
                                  "Die Pipeline-Kacheln zeigen den Stand heute aus der Vorgangsübersicht, unabhängig vom Zeitraum. Offene Angebote und Auftragsbestätigungen zählen nur, wenn sie höchstens {{pipeline_monate}} Monate alt sind.",
                                  "Warengruppen gelten in der heutigen Zuordnung des Artikels – büro+ speichert sie nicht im Beleg.",
                                  "Die Inventurliste zeigt alle in den letzten {{inventur_monate}} Monaten verkauften Artikel (Stand heute) mit Mengeneinheit und EK als Zählvorlage; Export über CSV/Excel."]},
        },
    }],
    "alert_rules": alert_rules,
    "knowledge": [],
}
json.dump(tpl, open(OUT, "w"), ensure_ascii=False, indent=1)
print("geschrieben", OUT, len(tpl["mappings"]), "Mappings,", len(widgets), "Widgets,", len(alert_rules), "Warnungen")

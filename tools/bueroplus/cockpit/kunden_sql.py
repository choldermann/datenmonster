# Reiter „Kunden“ – wird von bauen.py per exec() eingebunden (nutzt BELEGE, SQL, NAMEN)
KD = "COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(adr.AdrReNa2, ''))), ''), CONCAT('Adresse ', {nr}))"

# Umsatzbelege je Kunde mit Zeitraum (Per 1) und Vorjahreszeitraum (Per 2)
KB = f"""b AS (
    {BELEGE}
), k AS (
    SELECT VogAdrNr AS AdrNr, VogID, VogDat, Vz, Vz * Netto AS Umsatz, Vz * (Netto - Ek) AS Rohertrag,
        CASE WHEN VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis) THEN 1
             WHEN VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 2 END AS Per
    FROM b
), kd AS (
    SELECT AdrNr,
        SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS U1, SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS U2,
        SUM(CASE WHEN Per = 1 THEN Rohertrag ELSE 0 END) AS R1,
        SUM(CASE WHEN Per = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS N1, SUM(CASE WHEN Per = 2 AND Vz = 1 THEN 1 ELSE 0 END) AS N2,
        MAX(CASE WHEN Per = 1 AND Vz = 1 THEN VogDat END) AS Letzte
    FROM k WHERE Per IS NOT NULL GROUP BY AdrNr
), erste AS (
    SELECT VogAdrNr AS AdrNr, MIN(VogDat) AS Erste FROM b WHERE Vz = 1 GROUP BY VogAdrNr
)"""

# Schlafende Stammkunden – Stand heute, unabhängig vom Zeitraum
SCHLAF = """sb AS (
    SELECT VogAdrNr AS AdrNr, VogDat, VogGPreisNt AS Netto
    FROM dbo.vVorgang
    WHERE VogArt IN ('Rechnung I', 'Sammel Rechnung') AND VogGebuchtKz = 1 AND ISNULL(VogStorniertKz, 0) = 0
      AND VogDat > DATEADD(MONTH, -24, CAST(GETDATE() AS date))
), sl AS (
    SELECT AdrNr, MAX(VogDat) AS Letzte, COUNT(*) AS Rechnungen24M FROM sb GROUP BY AdrNr
), schlaf AS (
    SELECT sl.AdrNr, sl.Letzte, sl.Rechnungen24M, DATEDIFF(DAY, sl.Letzte, CAST(GETDATE() AS date)) AS TageSeither,
        (SELECT SUM(x.Netto) FROM sb x WHERE x.AdrNr = sl.AdrNr AND x.VogDat > DATEADD(YEAR, -1, sl.Letzte)) AS Jahresumsatz
    FROM sl
    WHERE sl.Rechnungen24M >= {{schlaf_min_rechnungen}}
      AND sl.Letzte < DATEADD(DAY, -{{schlaf_tage}}, CAST(GETDATE() AS date))
      AND sl.AdrNr <> {{barverkauf_adrnr}}
)"""

SQL["m_bp_kd_kpi"] = f"""
WITH {KB}, {SCHLAF},
rang AS (
    SELECT AdrNr, U1, ROW_NUMBER() OVER (ORDER BY U1 DESC) AS rn FROM kd WHERE U1 > 0
), s AS (
    SELECT
        SUM(CASE WHEN N1 > 0 THEN 1 ELSE 0 END) AS AktiveKunden,
        SUM(CASE WHEN N2 > 0 THEN 1 ELSE 0 END) AS AktiveKundenVJ,
        SUM(U1) AS Umsatz, SUM(U2) AS UmsatzVJ,
        SUM(CASE WHEN U2 > 0 AND U1 < U2 * 0.8 THEN 1 ELSE 0 END) AS KundenRueckgang,
        SUM(CASE WHEN U2 > 0 AND U1 < U2 * 0.8 THEN U2 - U1 ELSE 0 END) AS Rueckgang
    FROM kd
), neu AS (
    SELECT
        SUM(CASE WHEN e.Erste >= :von AND e.Erste < DATEADD(DAY, 1, :bis) THEN 1 ELSE 0 END) AS Neukunden,
        SUM(CASE WHEN e.Erste >= DATEADD(YEAR, -1, :von) AND e.Erste < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 1 ELSE 0 END) AS NeukundenVJ,
        SUM(CASE WHEN e.Erste >= :von AND e.Erste < DATEADD(DAY, 1, :bis) THEN ISNULL(kd.U1, 0) ELSE 0 END) AS UmsatzNeukunden
    FROM erste e LEFT JOIN kd ON kd.AdrNr = e.AdrNr
), t AS (
    SELECT SUM(CASE WHEN rn <= 5 THEN U1 ELSE 0 END) AS Top5, SUM(CASE WHEN rn <= 10 THEN U1 ELSE 0 END) AS Top10,
        SUM(U1) AS Positiv FROM rang
), sch AS (
    SELECT COUNT(*) AS Schlafend, ISNULL(SUM(Jahresumsatz), 0) AS UmsatzInGefahr FROM schlaf
)
SELECT s.AktiveKunden, s.AktiveKundenVJ, neu.Neukunden, neu.NeukundenVJ,
    CAST(neu.UmsatzNeukunden AS DECIMAL(18,2)) AS UmsatzNeukunden,
    CAST(CASE WHEN s.AktiveKunden > 0 THEN s.Umsatz / s.AktiveKunden END AS DECIMAL(18,2)) AS UmsatzJeKunde,
    CAST(CASE WHEN s.AktiveKundenVJ > 0 THEN s.UmsatzVJ / s.AktiveKundenVJ END AS DECIMAL(18,2)) AS UmsatzJeKundeVJ,
    CAST(CASE WHEN t.Positiv > 0 THEN 100.0 * t.Top10 / t.Positiv END AS DECIMAL(9,1)) AS AnteilTop10,
    CAST(CASE WHEN t.Positiv > 0 THEN 100.0 * t.Top5 / t.Positiv END AS DECIMAL(9,1)) AS AnteilTop5,
    s.KundenRueckgang, CAST(s.Rueckgang AS DECIMAL(18,2)) AS Rueckgang,
    sch.Schlafend, CAST(sch.UmsatzInGefahr AS DECIMAL(18,2)) AS UmsatzInGefahr
FROM s CROSS JOIN neu CROSS JOIN t CROSS JOIN sch
"""

KD_SPALTEN = f"""kd.AdrNr, {KD.format(nr='kd.AdrNr')} AS Kunde, adr.AdrReOrt AS Ort, adr.AdrVtrNr AS Vertreter"""

SQL["m_bp_kd_top"] = f"""
WITH {KB}
SELECT TOP 25 {KD_SPALTEN},
    CAST(kd.U1 AS DECIMAL(18,2)) AS Umsatz, CAST(kd.U2 AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(CASE WHEN kd.U2 > 0 THEN 100.0 * (kd.U1 - kd.U2) / kd.U2 END AS DECIMAL(9,1)) AS Veraenderung,
    CAST(kd.R1 AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN kd.U1 > 0 THEN 100.0 * kd.R1 / kd.U1 END AS DECIMAL(9,1)) AS Marge,
    kd.N1 AS Rechnungen, CONVERT(char(10), kd.Letzte, 104) AS LetzteRechnung,
    CASE WHEN adr.AdrGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM kd LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = kd.AdrNr
WHERE kd.U1 > 0
ORDER BY kd.U1 DESC
"""

SQL["m_bp_kd_rueckgang"] = f"""
WITH {KB}
SELECT TOP 50 {KD_SPALTEN},
    CAST(kd.U1 AS DECIMAL(18,2)) AS Umsatz, CAST(kd.U2 AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(kd.U1 - kd.U2 AS DECIMAL(18,2)) AS Veraenderung,
    CAST(100.0 * (kd.U1 - kd.U2) / kd.U2 AS DECIMAL(9,1)) AS VeraenderungProzent,
    kd.N1 AS Rechnungen, kd.N2 AS RechnungenVJ, CONVERT(char(10), kd.Letzte, 104) AS LetzteRechnung
FROM kd LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = kd.AdrNr
WHERE kd.U2 > 0 AND kd.U1 < kd.U2 * 0.8
ORDER BY kd.U1 - kd.U2
"""

SQL["m_bp_kd_schlafend"] = f"""
WITH {SCHLAF}
SELECT TOP 500 schlaf.AdrNr, {KD.format(nr='schlaf.AdrNr')} AS Kunde, adr.AdrReOrt AS Ort, adr.AdrReTel AS Telefon,
    adr.AdrVtrNr AS Vertreter, CONVERT(char(10), schlaf.Letzte, 104) AS LetzteRechnung, schlaf.TageSeither,
    schlaf.Rechnungen24M, CAST(schlaf.Jahresumsatz AS DECIMAL(18,2)) AS Jahresumsatz,
    CASE WHEN adr.AdrGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM schlaf LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = schlaf.AdrNr
ORDER BY schlaf.Jahresumsatz DESC
"""

SQL["m_bp_kd_neu"] = f"""
WITH {KB},
seit AS (
    SELECT k.AdrNr, SUM(k.Umsatz) AS Umsatz, SUM(k.Rohertrag) AS Rohertrag, SUM(CASE WHEN k.Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen
    FROM k JOIN erste e ON e.AdrNr = k.AdrNr
    WHERE e.Erste >= :von AND e.Erste < DATEADD(DAY, 1, :bis) AND k.VogDat < DATEADD(DAY, 1, :bis)
    GROUP BY k.AdrNr
)
SELECT TOP 500 seit.AdrNr, {KD.format(nr='seit.AdrNr')} AS Kunde, adr.AdrReOrt AS Ort, adr.AdrVtrNr AS Vertreter,
    adr.AdrBranche AS Branche, CONVERT(char(10), e.Erste, 104) AS ErsteRechnung,
    seit.Rechnungen, CAST(seit.Umsatz AS DECIMAL(18,2)) AS Umsatz, CAST(seit.Rohertrag AS DECIMAL(18,2)) AS Rohertrag
FROM seit JOIN erste e ON e.AdrNr = seit.AdrNr
LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = seit.AdrNr
ORDER BY seit.Umsatz DESC
"""

SQL["m_bp_kd_abc"] = f"""
WITH {KB},
r AS (
    SELECT AdrNr, U1, SUM(U1) OVER (ORDER BY U1 DESC, AdrNr ROWS UNBOUNDED PRECEDING) AS Kum, SUM(U1) OVER () AS Ges
    FROM kd WHERE U1 > 0
), c AS (
    SELECT CASE WHEN Kum - U1 < 0.8 * Ges THEN 'A' WHEN Kum - U1 < 0.95 * Ges THEN 'B' ELSE 'C' END AS Klasse, U1, Ges FROM r
)
SELECT Klasse, COUNT(*) AS Kunden, CAST(SUM(U1) AS DECIMAL(18,2)) AS Umsatz,
    CAST(100.0 * SUM(U1) / MAX(Ges) AS DECIMAL(9,1)) AS AnteilUmsatz,
    CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS DECIMAL(9,1)) AS AnteilKunden
FROM c GROUP BY Klasse ORDER BY Klasse
"""

SQL["m_bp_kd_status"] = f"""
WITH {KB}
SELECT COALESCE(NULLIF(LTRIM(RTRIM(adr.AdrStatus)), ''), 'ohne Status') AS Status,
    COUNT(*) AS Kunden, CAST(SUM(kd.U1) AS DECIMAL(18,2)) AS Umsatz
FROM kd LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = kd.AdrNr
WHERE kd.U1 > 0
GROUP BY COALESCE(NULLIF(LTRIM(RTRIM(adr.AdrStatus)), ''), 'ohne Status')
ORDER BY SUM(kd.U1) DESC
"""

SQL["m_bp_kd_belege"] = f"""
WITH b AS (
    {BELEGE}
)
SELECT TOP 500 b.VogBelegNr AS Beleg, b.VogArt AS Art, CONVERT(char(10), b.VogDat, 104) AS Datum,
    CAST(b.Vz * b.Netto AS DECIMAL(18,2)) AS Umsatz, CAST(b.Vz * (b.Netto - b.Ek) AS DECIMAL(18,2)) AS Rohertrag,
    b.VogVerk AS Bearbeiter, CONCAT(CASE b.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, b.VogID) AS VogID
FROM b
WHERE b.VogAdrNr = CAST(:adrnr AS int)
  AND b.VogDat >= DATEADD(YEAR, -1, :von) AND b.VogDat < DATEADD(DAY, 1, :bis)
ORDER BY b.VogDat DESC
"""

NAMEN.update({
    "m_bp_kd_kpi": "büro+ GF – Kunden-Kennzahlen",
    "m_bp_kd_top": "büro+ GF – Top-Kunden",
    "m_bp_kd_rueckgang": "büro+ GF – Kunden mit Rückgang",
    "m_bp_kd_schlafend": "büro+ GF – Schlafende Stammkunden",
    "m_bp_kd_neu": "büro+ GF – Neukunden",
    "m_bp_kd_abc": "büro+ GF – ABC-Kunden",
    "m_bp_kd_status": "büro+ GF – Umsatz nach Adress-Status",
    "m_bp_kd_belege": "büro+ GF – Belege des Kunden (Detail)",
})

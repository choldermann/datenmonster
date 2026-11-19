# Reiter „Marge“ und „Vertreter“ – wird von bauen.py per exec() eingebunden
# (nutzt BELEGE, POS, LISTE, WGR, BEZ, SQL, NAMEN).

# DB-Grenze aus dem Formularfeld db_grenze (Komma oder Punkt, leer = 15 %)
DB_GRENZE = "ISNULL(TRY_CAST(REPLACE(NULLIF(LTRIM(RTRIM(CAST(:db_grenze AS nvarchar(20)))), ''), ',', '.') AS decimal(9,2)), 15)"

# ── Artikel mit Deckungsbeitrag unter der Grenze (Zeitraum) ──
SQL["m_bp_art_db"] = f"""
WITH {POS}, a AS (
    SELECT ArtNr,
        SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS U1, SUM(CASE WHEN Per = 1 THEN Einsatz ELSE 0 END) AS E1,
        SUM(CASE WHEN Per = 1 THEN Menge ELSE 0 END) AS M1, SUM(CASE WHEN Per = 1 THEN PE ELSE 0 END) AS PE1,
        SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS U2, SUM(CASE WHEN Per = 2 THEN Einsatz ELSE 0 END) AS E2,
        COUNT(CASE WHEN Per = 1 THEN 1 END) AS Positionen,
        COUNT(DISTINCT CASE WHEN Per = 1 THEN VogAdrNr END) AS Kunden,
        MAX(CASE WHEN Per = 1 THEN VogDat END) AS Letzter
    FROM pos GROUP BY ArtNr
)
SELECT a.ArtNr, {BEZ} AS Bezeichnung, {WGR} AS Warengruppe,
    CASE art.ArtEinh WHEN '%o' THEN 'Tsd' ELSE ISNULL(art.ArtEinh, '') END AS Einheit,
    CAST(a.U1 AS DECIMAL(18,2)) AS Umsatz, CAST(a.E1 AS DECIMAL(18,2)) AS Einsatz,
    CAST(a.U1 - a.E1 AS DECIMAL(18,2)) AS DB,
    CAST(100.0 * (a.U1 - a.E1) / NULLIF(a.U1, 0) AS DECIMAL(18,1)) AS [DB %],
    CAST(CASE WHEN a.U2 > 0 THEN 100.0 * (a.U2 - a.E2) / a.U2 END AS DECIMAL(18,1)) AS [DB % VJ],
    -- Durchschnittspreise je Preiseinheit (bei Tsd je 1.000 Stück), wie in büro+
    CAST(CASE WHEN a.PE1 <> 0 THEN a.U1 / a.PE1 END AS DECIMAL(18,2)) AS VkSchnitt,
    CAST(CASE WHEN a.PE1 <> 0 THEN a.E1 / a.PE1 END AS DECIMAL(18,2)) AS EkSchnitt,
    CAST({LISTE} AS DECIMAL(18,2)) AS VkAktuell, CAST(art.ArtEkKalk AS DECIMAL(18,2)) AS EkAktuell,
    CAST(a.M1 AS DECIMAL(18,2)) AS Menge, a.Positionen, a.Kunden,
    CONVERT(char(10), a.Letzter, 104) AS LetzterVerkauf,
    CASE WHEN art.ArtGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM a LEFT JOIN dbo.Artikel art ON art.ArtArtNr = a.ArtNr
WHERE a.U1 > 0 AND 100.0 * (a.U1 - a.E1) / NULLIF(a.U1, 0) < {DB_GRENZE}
ORDER BY a.U1 DESC
"""

# Klick: die Rechnungspositionen des Artikels im Zeitraum mit DB je Position
SQL["m_bp_art_db_belege"] = f"""
WITH b AS (
    {BELEGE}
      AND VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis)
)
SELECT TOP 1000 b.VogBelegNr AS Beleg, b.VogArt AS Art, CONVERT(char(10), b.VogDat, 104) AS Datum,
    b.VogAdrNr AS AdrNr, COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(a.AdrReNa2, ''))), ''), CONCAT('Adresse ', b.VogAdrNr)) AS Kunde,
    CAST(b.Vz * p.BuchMge AS DECIMAL(18,2)) AS Menge,
    CAST(p.EPrNt AS DECIMAL(18,4)) AS Preis, CAST(p.EEkRoh AS DECIMAL(18,4)) AS EkPreis,
    CAST(b.Vz * p.NettoPos AS DECIMAL(18,2)) AS Umsatz, CAST(b.Vz * p.EkPos AS DECIMAL(18,2)) AS Einsatz,
    CAST(b.Vz * (p.NettoPos - p.EkPos) AS DECIMAL(18,2)) AS DB,
    CAST(CASE WHEN p.NettoPos <> 0 THEN 100.0 * (p.NettoPos - p.EkPos) / p.NettoPos END AS DECIMAL(18,1)) AS [DB %],
    b.VogVerk AS Bearbeiter, b.VogVtrNr AS Vertreter,
    CONCAT(CASE b.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, b.VogID) AS VogID
FROM dbo.vVorgangPosition p
JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle
LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE p.ArtNr = :artnr AND p.ArtKz = 1
ORDER BY CASE WHEN p.NettoPos <> 0 THEN (p.NettoPos - p.EkPos) / p.NettoPos END, b.VogDat DESC
"""

# ── Vertreter (Vertreternummer am Beleg) ──
VTR = f"""v AS (
    SELECT VogAdrNr, VogDat, Vz, Vz * Netto AS Umsatz, Vz * (Netto - Ek) AS Rohertrag,
        Vz * Netto * ISNULL(pv.VogVtrProvSz, 0) / 100.0 AS Provision,
        ISNULL(VogVtrNr, -1) AS VtrNr,
        CASE WHEN VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis) THEN 1
             WHEN VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 2 END AS Per
    FROM ({BELEGE}) b0
    LEFT JOIN (SELECT Quelle AS Q, VogID AS VID, VogVtrProvSz FROM dbo.vVorgang) pv ON pv.Q = b0.Quelle AND pv.VID = b0.VogID
)"""

SQL["m_bp_vertreter"] = f"""
WITH {VTR}
SELECT CASE WHEN VtrNr = -1 THEN 'ohne Vertreter' ELSE CONCAT('Vertreter ', VtrNr) END AS Vertreter,
    VtrNr AS VtrNr,
    CAST(SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS DECIMAL(18,2)) AS Umsatz,
    CAST(SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(CASE WHEN SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) > 0
              THEN 100.0 * SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) / SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) - 100 END AS DECIMAL(18,1)) AS [Veränderung %],
    CAST(SUM(CASE WHEN Per = 1 THEN Rohertrag ELSE 0 END) AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) > 0
              THEN 100.0 * SUM(CASE WHEN Per = 1 THEN Rohertrag ELSE 0 END) / SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) END AS DECIMAL(18,1)) AS [Marge %],
    COUNT(DISTINCT CASE WHEN Per = 1 AND Vz = 1 THEN VogAdrNr END) AS Kunden,
    COUNT(DISTINCT CASE WHEN Per = 2 AND Vz = 1 THEN VogAdrNr END) AS KundenVJ,
    SUM(CASE WHEN Per = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen,
    CAST(SUM(CASE WHEN Per = 1 AND Vz = 1 THEN Umsatz ELSE 0 END) / NULLIF(SUM(CASE WHEN Per = 1 AND Vz = 1 THEN 1 ELSE 0 END), 0) AS DECIMAL(18,2)) AS [Ø Rechnung],
    CAST(SUM(CASE WHEN Per = 1 THEN Provision ELSE 0 END) AS DECIMAL(18,2)) AS Provision
FROM v WHERE Per IS NOT NULL
GROUP BY VtrNr
HAVING SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) <> 0 OR SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) <> 0
ORDER BY SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) DESC
"""

# Klick auf einen Vertreter: seine Kunden (Zeitraum und Vorjahr)
SQL["m_bp_vertreter_kunden"] = f"""
WITH {VTR}
SELECT v.VogAdrNr AS AdrNr,
    COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(a.AdrReNa2, ''))), ''), CONCAT('Adresse ', v.VogAdrNr)) AS Kunde, MAX(a.AdrReOrt) AS Ort,
    CAST(SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS DECIMAL(18,2)) AS Umsatz,
    CAST(SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) - SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS DECIMAL(18,2)) AS Veraenderung,
    CAST(SUM(CASE WHEN Per = 1 THEN Rohertrag ELSE 0 END) AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) > 0
              THEN 100.0 * SUM(CASE WHEN Per = 1 THEN Rohertrag ELSE 0 END) / SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) END AS DECIMAL(18,1)) AS [Marge %],
    SUM(CASE WHEN Per = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen,
    CONVERT(char(10), MAX(CASE WHEN Vz = 1 THEN v.VogDat END), 104) AS LetzteRechnung
FROM v LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = v.VogAdrNr
WHERE v.Per IS NOT NULL AND v.VtrNr = CAST(:vtrnr AS int)
GROUP BY v.VogAdrNr, a.AdrReNa2
ORDER BY SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) DESC
"""

NAMEN.update({
    "m_bp_art_db": "büro+ GF – Artikel unter DB-Grenze",
    "m_bp_art_db_belege": "büro+ GF – Rechnungspositionen des Artikels mit DB (Detail)",
    "m_bp_vertreter": "büro+ GF – Vertreter",
    "m_bp_vertreter_kunden": "büro+ GF – Kunden des Vertreters (Detail)",
})

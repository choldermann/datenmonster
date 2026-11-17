# Reiter „Inventurliste“ – wird von bauen.py per exec() eingebunden.
# Alle Artikel mit Verkauf in den letzten {{inventur_monate}} Monaten (Stand heute, unabhängig vom
# gewählten Zeitraum) mit Mengeneinheit, EK und leeren Zählspalten – als Vorlage für die Inventur,
# über CSV/Excel exportierbar.

SQL["m_bp_inventurliste"] = f"""
WITH b AS (
    {BELEGE}
      AND VogDat >= DATEADD(MONTH, -CAST('{{{{inventur_monate}}}}' AS int), CAST(GETDATE() AS date))
), v AS (
    SELECT p.ArtNr, SUM(b.Vz * p.BuchMge) AS Menge, SUM(b.Vz * p.NettoPos) AS Umsatz, MAX(b.VogDat) AS Letzter
    FROM dbo.vVorgangPosition p JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle
    WHERE p.ArtKz = 1 AND p.ArtNr IS NOT NULL AND p.ArtNr <> ''
    GROUP BY p.ArtNr
    HAVING SUM(CASE WHEN b.Vz = 1 THEN p.BuchMge ELSE 0 END) <> 0
), best AS (
    SELECT p.ArtNr, k.VogDat, k.VogBelegNr, k.VogAdrNr, p.EPrNt,
        ROW_NUMBER() OVER (PARTITION BY p.ArtNr ORDER BY k.VogDat DESC, k.VogBelegNr DESC) AS rn
    FROM dbo.vVorgangPosition p JOIN dbo.vVorgang k ON k.VogID = p.VogID AND k.Quelle = p.Quelle
    WHERE k.VogArt = 'Bestellung an Lieferant' AND ISNULL(k.VogStorniertKz, 0) = 0
      AND p.ArtNr IN (SELECT ArtNr FROM v) AND ISNULL(p.EPrNt, 0) <> 0
)
SELECT
    CASE WHEN TRY_CAST(REPLACE(LEFT(v.ArtNr, 6), '.', '') AS int) IS NOT NULL
         THEN REPLACE(LEFT(v.ArtNr, 6), '.', '') ELSE LEFT(v.ArtNr, 6) END AS Sortierung,
    v.ArtNr,
    COALESCE(NULLIF(LTRIM(RTRIM(art.ArtBez1)), ''), art.ArtKuBez1, '(Artikel fehlt)') AS Beschreibung,
    CAST(NULL AS int) AS Paletten, CAST(NULL AS int) AS Kartons, CAST(NULL AS int) AS Stueck,
    CASE art.ArtEinh WHEN '%o' THEN 'Tsd' WHEN 'Stk' THEN 'Stück' WHEN 'Stk.' THEN 'Stück' WHEN 'Kg' THEN 'KG'
         WHEN 'Karton' THEN 'Paket' WHEN 'Pack' THEN 'Paket' ELSE COALESCE(art.ArtEinh, 'Stück') END AS Mengeneinheit,
    CAST(COALESCE(NULLIF(art.ArtEkKalk, 0), NULLIF(art.ArtEkMitt, 0)) AS DECIMAL(18,4)) AS EK,
    COALESCE(NULLIF(LTRIM(RTRIM(adr.AdrReNa2)), ''), adr.AdrSuchBeg) AS Lieferant,
    best.VogBelegNr AS LetzteBestellung, CONVERT(char(10), best.VogDat, 104) AS Bestelldatum,
    CAST(best.EPrNt AS DECIMAL(18,4)) AS EkLetzteBestellung,
    CAST(v.Menge AS DECIMAL(18,2)) AS VerkauftMenge, CAST(v.Umsatz AS DECIMAL(18,2)) AS VerkauftUmsatz,
    CONVERT(char(10), v.Letzter, 104) AS LetzterVerkauf,
    COALESCE(NULLIF(LTRIM(RTRIM(art.ArtWgrNrInfo)), ''), '') AS Warengruppe,
    CASE WHEN art.ArtGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM v
LEFT JOIN dbo.Artikel art ON art.ArtArtNr = v.ArtNr
LEFT JOIN best ON best.ArtNr = v.ArtNr AND best.rn = 1
LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = best.VogAdrNr
-- DSZ-Gebühren (Verpackungslizenz) sind Rechnungspositionen ohne Ware – nicht zählbar
WHERE ISNULL(art.ArtWgrNrInfo, '') NOT LIKE 'DSZ%' AND v.ArtNr NOT LIKE '%DSZ%'
ORDER BY TRY_CAST(LEFT(v.ArtNr, CHARINDEX('.', v.ArtNr + '.') - 1) AS int),
    LEFT(v.ArtNr, CHARINDEX('.', v.ArtNr + '.') - 1), v.ArtNr
"""

NAMEN.update({
    "m_bp_inventurliste": "büro+ GF – Inventurliste (verkaufte Artikel)",
})

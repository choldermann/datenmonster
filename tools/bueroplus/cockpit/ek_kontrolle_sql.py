# Reiter „EK-Kontrolle“ – wird von bauen.py per exec() eingebunden (nutzt BELEGE, SQL, NAMEN).
# Rechnungspositionen im gewählten Zeitraum, deren Einkaufspreis (büro+ EEkRoh, daraus der
# Wareneinsatz) fehlt oder unplausibel hoch ist – je Artikel, mit Wirkung auf den Rohertrag.
# Fracht/Nebenkosten (27.000 …) und DSZ/DSD-Gebühren stehen getrennt: dort fehlt der EK
# systematisch (Kosten des Spediteurs bzw. Lizenz stehen nicht im Artikel).

SQL["m_bp_ek_kontrolle"] = f"""
WITH b AS (
    {BELEGE}
      AND VogArt <> 'Rechnungskorrektur' AND VogDat >= :von AND VogDat < DATEADD(DAY, 1, :bis)
), pos AS (
    SELECT p.ArtNr, b.VogDat, p.BuchMge, p.NettoPos, p.EkPos, art.ArtWgrNrInfo,
        CASE
            -- Gratisware (Spender o. Ä.): EK ist echt, kein Fehler – nur zur Information
            WHEN p.EkPos > 100 AND p.NettoPos = 0 THEN 'Kostenlos abgegeben'
            WHEN p.EkPos > 100 AND p.EkPos > p.NettoPos * {{{{ek_faktor}}}} THEN 'EK zu hoch'
            WHEN ISNULL(p.EEkRoh, 0) = 0 AND p.NettoPos > 0 THEN
                CASE WHEN p.ArtNr LIKE '27.000%' OR p.ArtNr LIKE '%DSZ%'
                          OR ISNULL(art.ArtWgrNrInfo, '') LIKE 'DSZ%' OR ISNULL(art.ArtWgrNrInfo, '') LIKE '0 DSD%'
                     THEN 'Fracht/Nebenkosten ohne EK' ELSE 'EK fehlt' END
        END AS Problem
    FROM dbo.vVorgangPosition p
    JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle
    LEFT JOIN dbo.Artikel art ON art.ArtArtNr = p.ArtNr
    WHERE p.ArtKz = 1 AND p.ArtNr IS NOT NULL AND p.ArtNr <> ''
)
SELECT pos.Problem, pos.ArtNr,
    MAX(COALESCE(NULLIF(LTRIM(RTRIM(art.ArtKuBez1)), ''), LEFT(REPLACE(REPLACE(art.ArtBez1, CHAR(13), ' '), CHAR(10), ' '), 80))) AS Bezeichnung,
    MAX(ISNULL(pos.ArtWgrNrInfo, '')) AS Warengruppe,
    COUNT(*) AS Positionen,
    CAST(SUM(pos.NettoPos) AS DECIMAL(18,2)) AS Umsatz,
    CAST(SUM(pos.EkPos) AS DECIMAL(18,2)) AS Einsatz,
    -- + = Rohertrag im Cockpit zu hoch (EK fehlt), − = zu niedrig (EK zu hoch)
    CAST(CASE WHEN pos.Problem = 'EK zu hoch' THEN -(SUM(pos.EkPos) - SUM(pos.NettoPos))
              WHEN pos.Problem = 'Kostenlos abgegeben' THEN 0 ELSE SUM(pos.NettoPos) END AS DECIMAL(18,2)) AS WirkungRohertrag,
    CAST(CASE WHEN SUM(pos.NettoPos) > 0 THEN SUM(pos.EkPos) / SUM(pos.NettoPos) END AS DECIMAL(18,1)) AS EkFaktor,
    CAST(MAX(art.ArtEkKalk) AS DECIMAL(18,2)) AS EkKalkHeute,
    CONVERT(char(10), MAX(pos.VogDat), 104) AS LetzterVerkauf,
    CASE WHEN MAX(CAST(art.ArtGspKz AS int)) = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM pos LEFT JOIN dbo.Artikel art ON art.ArtArtNr = pos.ArtNr
WHERE pos.Problem IS NOT NULL
GROUP BY pos.Problem, pos.ArtNr
ORDER BY CASE pos.Problem WHEN 'EK fehlt' THEN 1 WHEN 'EK zu hoch' THEN 2 WHEN 'Fracht/Nebenkosten ohne EK' THEN 3 ELSE 4 END,
    ABS(CASE WHEN pos.Problem = 'EK fehlt' OR pos.Problem LIKE 'Fracht%' THEN SUM(pos.NettoPos) ELSE SUM(pos.EkPos) - SUM(pos.NettoPos) END) DESC
"""

NAMEN.update({
    "m_bp_ek_kontrolle": "büro+ GF – EK-Kontrolle (fehlender/zu hoher Einkaufspreis)",
})

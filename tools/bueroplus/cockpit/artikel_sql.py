# Reiter „Artikel & Warengruppen“ – wird von bauen.py per exec() eingebunden (nutzt BELEGE, KUNDE, SQL, NAMEN)
LISTE = "art.{{listenpreis}}"
WGR = "COALESCE(NULLIF(LTRIM(RTRIM(art.ArtWgrNrInfo)), ''), 'ohne Warengruppe')"
BEZ = "COALESCE(NULLIF(art.ArtKuBez1, ''), LEFT(art.ArtBez1, 80))"

# Artikelpositionen der Umsatzbelege, Zeitraum (Per 1) und Vorjahreszeitraum (Per 2)
POS = f"""b AS (
    {BELEGE}
      AND VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, :bis)
), pos AS (
    SELECT p.ArtNr, b.VogID, b.VogAdrNr, b.VogDat,
        b.Vz * p.NettoPos AS Umsatz, b.Vz * p.EkPos AS Einsatz,
        b.Vz * p.BuchMge AS Menge, b.Vz * p.BuchMge * p.EPreisFak AS PE,
        b.Vz * p.BuchMge * p.EPreisFak * {LISTE} AS Listenwert,
        {WGR} AS Warengruppe,
        CASE WHEN b.VogDat >= :von THEN 1
             WHEN b.VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 2 END AS Per
    FROM dbo.vVorgangPosition p
    JOIN b ON b.VogID = p.VogID
    LEFT JOIN dbo.Artikel art ON art.ArtArtNr = p.ArtNr
    WHERE p.ArtKz = 1 AND p.ArtNr IS NOT NULL
)"""

SQL["m_bp_art_kpi"] = f"""
WITH {POS},
s AS (
    SELECT
        COUNT(DISTINCT CASE WHEN Per = 1 THEN ArtNr END) AS ArtikelVerkauft,
        COUNT(DISTINCT CASE WHEN Per = 2 THEN ArtNr END) AS ArtikelVerkauftVJ,
        COUNT(DISTINCT CASE WHEN Per = 1 THEN Warengruppe END) AS Warengruppen,
        SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS Umsatz,
        SUM(CASE WHEN Per = 1 AND Listenwert > 0 THEN Umsatz ELSE 0 END) AS UmsatzMitListe,
        SUM(CASE WHEN Per = 1 AND Listenwert > 0 THEN Listenwert ELSE 0 END) AS Listenwert,
        SUM(CASE WHEN Per = 2 AND Listenwert > 0 THEN Umsatz ELSE 0 END) AS UmsatzMitListeVJ,
        SUM(CASE WHEN Per = 2 AND Listenwert > 0 THEN Listenwert ELSE 0 END) AS ListenwertVJ
    FROM pos WHERE Per IS NOT NULL
), unter_ek AS (
    SELECT
        SUM(CASE WHEN Per = 1 THEN Einsatz - Umsatz ELSE 0 END) AS VerlustUnterEk,
        SUM(CASE WHEN Per = 2 THEN Einsatz - Umsatz ELSE 0 END) AS VerlustUnterEkVJ,
        SUM(CASE WHEN Per = 1 THEN 1 ELSE 0 END) AS PosUnterEk,
        COUNT(DISTINCT CASE WHEN Per = 1 THEN ArtNr END) AS ArtikelUnterEk
    FROM pos WHERE Per IS NOT NULL AND Umsatz > 0 AND Einsatz > Umsatz
), top20 AS (
    SELECT SUM(u) AS UmsatzTop20 FROM (
        SELECT TOP 20 SUM(Umsatz) AS u FROM pos WHERE Per = 1 GROUP BY ArtNr ORDER BY SUM(Umsatz) DESC) t
), letzter AS (
    SELECT p.ArtNr, MAX(k.VogDat) AS Letzter
    FROM dbo.vVorgangPosition p JOIN dbo.vVorgang k ON k.VogID = p.VogID
    WHERE k.VogArt IN ('Rechnung I', 'Sammel Rechnung') AND p.ArtKz = 1
    GROUP BY p.ArtNr
), sortiment AS (
    SELECT
        SUM(CASE WHEN art.ArtGspKz = 0 THEN 1 ELSE 0 END) AS AktiveArtikel,
        SUM(CASE WHEN art.ArtGspKz = 0 AND (l.Letzter IS NULL OR l.Letzter <= DATEADD(YEAR, -1, :bis)) THEN 1 ELSE 0 END) AS OhneVerkauf12M,
        SUM(CASE WHEN art.ArtGspKz = 1 AND l.Letzter > DATEADD(YEAR, -1, :bis) THEN 1 ELSE 0 END) AS GesperrtVerkauft
    FROM dbo.Artikel art LEFT JOIN letzter l ON l.ArtNr = art.ArtArtNr
)
SELECT s.ArtikelVerkauft, s.ArtikelVerkauftVJ, s.Warengruppen,
    CAST(CASE WHEN s.Umsatz > 0 THEN 100.0 * t.UmsatzTop20 / s.Umsatz END AS DECIMAL(9,1)) AS AnteilTop20,
    CAST(t.UmsatzTop20 AS DECIMAL(18,2)) AS UmsatzTop20,
    CAST(CASE WHEN s.Listenwert > 0 THEN 100.0 * (1 - s.UmsatzMitListe / s.Listenwert) END AS DECIMAL(9,1)) AS Nachlass,
    CAST(CASE WHEN s.ListenwertVJ > 0 THEN 100.0 * (1 - s.UmsatzMitListeVJ / s.ListenwertVJ) END AS DECIMAL(9,1)) AS NachlassVJ,
    CAST(s.Listenwert - s.UmsatzMitListe AS DECIMAL(18,2)) AS NachlassWert,
    CAST(ISNULL(u.VerlustUnterEk, 0) AS DECIMAL(18,2)) AS VerlustUnterEk,
    CAST(ISNULL(u.VerlustUnterEkVJ, 0) AS DECIMAL(18,2)) AS VerlustUnterEkVJ,
    ISNULL(u.PosUnterEk, 0) AS PosUnterEk, ISNULL(u.ArtikelUnterEk, 0) AS ArtikelUnterEk,
    so.AktiveArtikel, so.OhneVerkauf12M, so.GesperrtVerkauft,
    CAST(CASE WHEN so.AktiveArtikel > 0 THEN 100.0 * so.OhneVerkauf12M / so.AktiveArtikel END AS DECIMAL(9,1)) AS AnteilOhneVerkauf
FROM s CROSS JOIN top20 t CROSS JOIN unter_ek u CROSS JOIN sortiment so
"""

WG_AGG = """SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS U1, SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS U2,
        SUM(CASE WHEN Per = 1 THEN Umsatz - Einsatz ELSE 0 END) AS R1, SUM(CASE WHEN Per = 2 THEN Umsatz - Einsatz ELSE 0 END) AS R2,
        COUNT(DISTINCT CASE WHEN Per = 1 THEN ArtNr END) AS A1, COUNT(DISTINCT CASE WHEN Per = 1 THEN VogAdrNr END) AS K1"""

SQL["m_bp_wg"] = f"""
WITH {POS},
g AS (SELECT Warengruppe, {WG_AGG} FROM pos WHERE Per IS NOT NULL GROUP BY Warengruppe)
SELECT Warengruppe,
    CAST(U1 AS DECIMAL(18,2)) AS Umsatz, CAST(U2 AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(CASE WHEN U2 > 0 THEN 100.0 * (U1 - U2) / U2 END AS DECIMAL(9,1)) AS Veraenderung,
    CAST(R1 AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN U1 > 0 THEN 100.0 * R1 / U1 END AS DECIMAL(9,1)) AS Marge,
    CAST(CASE WHEN U2 > 0 THEN 100.0 * R2 / U2 END AS DECIMAL(9,1)) AS MargeVJ,
    A1 AS Artikel, K1 AS Kunden
FROM g WHERE U1 <> 0 OR U2 <> 0
ORDER BY U1 DESC
"""

SQL["m_bp_wg_top"] = f"""
WITH {POS},
g AS (SELECT Warengruppe, {WG_AGG} FROM pos WHERE Per IS NOT NULL GROUP BY Warengruppe)
SELECT TOP 15 Warengruppe, CAST(U1 AS DECIMAL(18,2)) AS Umsatz, CAST(U2 AS DECIMAL(18,2)) AS UmsatzVJ
FROM g ORDER BY U1 DESC
"""

ART_AGG = f"""SUM(CASE WHEN Per = 1 THEN Umsatz ELSE 0 END) AS U1, SUM(CASE WHEN Per = 2 THEN Umsatz ELSE 0 END) AS U2,
        SUM(CASE WHEN Per = 1 THEN Umsatz - Einsatz ELSE 0 END) AS R1,
        SUM(CASE WHEN Per = 1 THEN Menge ELSE 0 END) AS M1, SUM(CASE WHEN Per = 1 THEN PE ELSE 0 END) AS PE1,
        SUM(CASE WHEN Per = 1 AND Listenwert > 0 THEN Umsatz ELSE 0 END) AS UL1,
        SUM(CASE WHEN Per = 1 AND Listenwert > 0 THEN Listenwert ELSE 0 END) AS L1,
        COUNT(DISTINCT CASE WHEN Per = 1 THEN VogAdrNr END) AS K1"""

ART_SELECT = f"""a.ArtNr, {BEZ} AS Bezeichnung, {WGR} AS Warengruppe,
    CAST(a.M1 AS DECIMAL(18,2)) AS Menge, art.ArtEinh AS Einheit,
    CAST(a.U1 AS DECIMAL(18,2)) AS Umsatz, CAST(a.U2 AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(CASE WHEN a.U2 > 0 THEN 100.0 * (a.U1 - a.U2) / a.U2 END AS DECIMAL(9,1)) AS Veraenderung,
    CAST(a.R1 AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN a.U1 > 0 THEN 100.0 * a.R1 / a.U1 END AS DECIMAL(9,1)) AS Marge,
    CAST(CASE WHEN a.PE1 <> 0 THEN a.U1 / a.PE1 END AS DECIMAL(18,2)) AS PreisSchnitt,
    CAST({LISTE} AS DECIMAL(18,2)) AS Listenpreis,
    CAST(CASE WHEN a.L1 > 0 THEN 100.0 * (1 - a.UL1 / a.L1) END AS DECIMAL(9,1)) AS Nachlass,
    a.K1 AS Kunden"""

SQL["m_bp_top_artikel"] = f"""
WITH {POS},
a AS (SELECT ArtNr, {ART_AGG} FROM pos WHERE Per IS NOT NULL GROUP BY ArtNr)
SELECT TOP 50 {ART_SELECT}
FROM a LEFT JOIN dbo.Artikel art ON art.ArtArtNr = a.ArtNr
WHERE a.U1 <> 0
ORDER BY a.U1 DESC
"""

SQL["m_bp_wg_artikel"] = f"""
WITH {POS},
a AS (SELECT ArtNr, {ART_AGG} FROM pos WHERE Per IS NOT NULL AND Warengruppe = :warengruppe GROUP BY ArtNr)
SELECT TOP 500 {ART_SELECT}
FROM a LEFT JOIN dbo.Artikel art ON art.ArtArtNr = a.ArtNr
WHERE a.U1 <> 0 OR a.U2 <> 0
ORDER BY a.U1 DESC
"""

SQL["m_bp_art_belege"] = f"""
WITH b AS (
    {BELEGE}
)
SELECT TOP 500 b.VogBelegNr AS Beleg, b.VogArt AS Art, CONVERT(char(10), b.VogDat, 104) AS Datum,
    b.VogAdrNr AS AdrNr, {KUNDE} AS Kunde,
    CAST(SUM(b.Vz * p.BuchMge) AS DECIMAL(18,2)) AS Menge,
    CAST(MAX(p.EPrNt) AS DECIMAL(18,4)) AS Preis, CAST(MAX(p.EEkRoh) AS DECIMAL(18,4)) AS EkPreis,
    CAST(SUM(b.Vz * p.NettoPos) AS DECIMAL(18,2)) AS Umsatz,
    CAST(SUM(b.Vz * p.RohertragPos) AS DECIMAL(18,2)) AS Rohertrag,
    b.VogVerk AS Bearbeiter, CAST(b.VogID AS varchar(20)) AS VogID
FROM dbo.vVorgangPosition p
JOIN b ON b.VogID = p.VogID
LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
WHERE p.ArtNr = :artnr AND b.VogDat >= :von AND b.VogDat < DATEADD(DAY, 1, :bis)
GROUP BY b.VogID, b.VogBelegNr, b.VogArt, b.VogDat, b.VogAdrNr, a.AdrReNa2, b.VogVerk
ORDER BY b.VogDat DESC
"""

SQL["m_bp_art_unter_ek"] = f"""
WITH {POS},
a AS (
    SELECT ArtNr, COUNT(*) AS Positionen, SUM(Menge) AS M1, SUM(PE) AS PE1,
        SUM(Umsatz) AS U1, SUM(Einsatz) AS E1, MAX(VogDat) AS Letzter
    FROM pos WHERE Per = 1 AND Umsatz > 0 AND Einsatz > Umsatz
    GROUP BY ArtNr
)
SELECT TOP 200 a.ArtNr, {BEZ} AS Bezeichnung, {WGR} AS Warengruppe, a.Positionen,
    CAST(a.U1 AS DECIMAL(18,2)) AS Umsatz, CAST(a.E1 AS DECIMAL(18,2)) AS Einsatz,
    CAST(a.U1 - a.E1 AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN a.PE1 <> 0 THEN a.U1 / a.PE1 END AS DECIMAL(18,2)) AS VkSchnitt,
    CAST(CASE WHEN a.PE1 <> 0 THEN a.E1 / a.PE1 END AS DECIMAL(18,2)) AS EkSchnitt,
    CAST(art.ArtEkKalk AS DECIMAL(18,2)) AS EkKalkHeute,
    CONVERT(char(10), a.Letzter, 104) AS LetzterVerkauf
FROM a LEFT JOIN dbo.Artikel art ON art.ArtArtNr = a.ArtNr
ORDER BY a.U1 - a.E1
"""

# Preiserhöhung prüfen: EK in den letzten 90 Tagen vor :bis gegenüber denselben 90 Tagen ein Jahr
# früher gestiegen, der Verkaufspreis aber nicht mitgezogen und der Listenpreis seit über einem Jahr alt.
SQL["m_bp_art_preispflege"] = f"""
WITH b AS (
    {BELEGE}
      AND VogArt <> 'Rechnungskorrektur'
      AND ((VogDat > DATEADD(DAY, -90, :bis) AND VogDat < DATEADD(DAY, 1, :bis))
        OR (VogDat > DATEADD(DAY, -90, DATEADD(YEAR, -1, :bis)) AND VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis))))
), pos AS (
    SELECT p.ArtNr, p.NettoPos AS Umsatz, p.EkPos AS Einsatz, p.BuchMge * p.EPreisFak AS PE,
        CASE WHEN b.VogDat > DATEADD(DAY, -90, :bis) THEN 1 ELSE 2 END AS Per
    FROM dbo.vVorgangPosition p JOIN b ON b.VogID = p.VogID
    WHERE p.ArtKz = 1 AND p.ArtNr IS NOT NULL AND p.NettoPos > 0 AND p.EkPos > 0
), a AS (
    SELECT ArtNr,
        SUM(CASE WHEN Per = 1 THEN Umsatz END) AS U1, SUM(CASE WHEN Per = 1 THEN Einsatz END) AS E1, SUM(CASE WHEN Per = 1 THEN PE END) AS P1,
        SUM(CASE WHEN Per = 2 THEN Umsatz END) AS U2, SUM(CASE WHEN Per = 2 THEN Einsatz END) AS E2, SUM(CASE WHEN Per = 2 THEN PE END) AS P2
    FROM pos GROUP BY ArtNr
), k AS (
    SELECT ArtNr, U1, E1 / P1 AS EkNeu, E2 / P2 AS EkAlt, U1 / P1 AS VkNeu, U2 / P2 AS VkAlt,
        100.0 * (U1 - E1) / U1 AS MargeNeu, 100.0 * (U2 - E2) / U2 AS MargeAlt
    FROM a WHERE P1 > 0 AND P2 > 0 AND U1 > 0 AND U2 > 0
)
SELECT TOP 200 k.ArtNr, {BEZ} AS Bezeichnung, {WGR} AS Warengruppe,
    CAST(k.EkAlt AS DECIMAL(18,2)) AS EkVorjahr, CAST(k.EkNeu AS DECIMAL(18,2)) AS EkJetzt,
    CAST(100.0 * (k.EkNeu - k.EkAlt) / k.EkAlt AS DECIMAL(9,1)) AS EkAnstieg,
    CAST(k.VkAlt AS DECIMAL(18,2)) AS VkVorjahr, CAST(k.VkNeu AS DECIMAL(18,2)) AS VkJetzt,
    CAST(100.0 * (k.VkNeu - k.VkAlt) / k.VkAlt AS DECIMAL(9,1)) AS VkAnstieg,
    CAST(k.MargeAlt AS DECIMAL(9,1)) AS MargeVorjahr, CAST(k.MargeNeu AS DECIMAL(9,1)) AS MargeJetzt,
    CAST({LISTE} AS DECIMAL(18,2)) AS Listenpreis, CONVERT(char(10), art.ArtVkDat, 104) AS PreisGeaendert,
    CAST(k.U1 AS DECIMAL(18,2)) AS Umsatz90Tage,
    CAST(k.U1 * (k.EkNeu - k.EkAlt) / NULLIF(k.EkNeu, 0) - k.U1 * (k.VkNeu - k.VkAlt) / NULLIF(k.VkNeu, 0) AS DECIMAL(18,2)) AS MargeVerlust90Tage
FROM k LEFT JOIN dbo.Artikel art ON art.ArtArtNr = k.ArtNr
WHERE k.EkNeu > k.EkAlt * 1.03
  AND k.VkNeu < k.VkAlt * (k.EkNeu / k.EkAlt) - 0.005
  AND (art.ArtVkDat IS NULL OR art.ArtVkDat <= DATEADD(YEAR, -1, :bis))
ORDER BY k.U1 * (k.EkNeu - k.EkAlt) / NULLIF(k.EkNeu, 0) - k.U1 * (k.VkNeu - k.VkAlt) / NULLIF(k.VkNeu, 0) DESC
"""

SQL["m_bp_art_ohne_verkauf"] = f"""
WITH letzter AS (
    SELECT p.ArtNr, MAX(k.VogDat) AS Letzter,
        SUM(CASE WHEN k.VogDat > DATEADD(YEAR, -2, :bis) THEN p.NettoPos ELSE 0 END) AS UmsatzVor12M
    FROM dbo.vVorgangPosition p JOIN dbo.vVorgang k ON k.VogID = p.VogID
    WHERE k.VogArt IN ('Rechnung I', 'Sammel Rechnung') AND p.ArtKz = 1
    GROUP BY p.ArtNr
)
SELECT TOP 500 art.ArtArtNr AS ArtNr, {BEZ} AS Bezeichnung, {WGR} AS Warengruppe,
    CONVERT(char(10), l.Letzter, 104) AS LetzterVerkauf,
    CAST(ISNULL(l.UmsatzVor12M, 0) AS DECIMAL(18,2)) AS UmsatzVorjahr,
    CAST({LISTE} AS DECIMAL(18,2)) AS Listenpreis, CONVERT(char(10), art.ArtVkDat, 104) AS PreisGeaendert
FROM dbo.Artikel art LEFT JOIN letzter l ON l.ArtNr = art.ArtArtNr
WHERE art.ArtGspKz = 0 AND (l.Letzter IS NULL OR l.Letzter <= DATEADD(YEAR, -1, :bis))
ORDER BY CASE WHEN l.Letzter IS NULL THEN 1 ELSE 0 END, l.Letzter DESC
"""

NAMEN.update({
    "m_bp_art_kpi": "büro+ GF – Artikel-Kennzahlen",
    "m_bp_wg": "büro+ GF – Warengruppen-Entwicklung",
    "m_bp_wg_top": "büro+ GF – Top-Warengruppen",
    "m_bp_top_artikel": "büro+ GF – Top-Artikel",
    "m_bp_wg_artikel": "büro+ GF – Artikel der Warengruppe (Detail)",
    "m_bp_art_belege": "büro+ GF – Belege mit diesem Artikel (Detail)",
    "m_bp_art_unter_ek": "büro+ GF – Verkauf unter Einkaufspreis",
    "m_bp_art_preispflege": "büro+ GF – Preiserhöhung prüfen",
    "m_bp_art_ohne_verkauf": "büro+ GF – Artikel ohne Verkauf",
})

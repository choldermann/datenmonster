# Reiter „Artikel-Verkauf (12-Monats-Vergleich)“ – wird von bauen.py per exec() eingebunden
# Rollierende 12-Monats-Scheiben bis zum Ende des gewählten Zeitraums (:bis):
#   0 = letzte 12 Monate, 1 = die 12 davor, … 5 = vor fünf Jahren.
SCHEIBEN = 6
# Volle Monate zwischen Belegdatum und :bis (angebrochener Monat zählt nicht) / 12 –
# gleichbedeutend mit „VogDat > :bis − (n+1) Jahre“, aber nur ein Ausdruck je Position.
SCHEIBE = "(DATEDIFF(MONTH, b.VogDat, :bis) - CASE WHEN DAY(b.VogDat) > DAY(:bis) THEN 1 ELSE 0 END) / 12"

V12 = f"""b AS (
    {BELEGE}
      AND VogDat > DATEADD(YEAR, -{SCHEIBEN}, :bis) AND VogDat < DATEADD(DAY, 1, :bis)
), pos AS (
    SELECT p.ArtNr, b.VogAdrNr AS AdrNr, b.VogDat, {SCHEIBE} AS S,
        b.Vz * p.BuchMge AS Menge, b.Vz * p.NettoPos AS Umsatz, b.Vz * p.RohertragPos AS Rohertrag
    FROM dbo.vVorgangPosition p JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle
    WHERE p.ArtKz = 1 AND p.ArtNr IS NOT NULL
)"""

def _je(feld, praefix, dec="18,2"):
    return ",\n    ".join(
        f"CAST(SUM(CASE WHEN S = {i} THEN {feld} ELSE 0 END) AS DECIMAL({dec})) AS {praefix}{i}" for i in range(SCHEIBEN))

# erst je Artikel × Scheibe verdichten (wenige tausend Zeilen), dann in Spalten drehen
G = """g AS (
    SELECT ArtNr, S, SUM(Menge) AS Menge, SUM(Umsatz) AS Umsatz, SUM(Rohertrag) AS Rohertrag,
        COUNT(DISTINCT AdrNr) AS Kunden, MAX(VogDat) AS Letzter
    FROM pos GROUP BY ArtNr, S
)"""

SQL["m_bp_v12_artikel"] = f"""
WITH {V12}, {G},
a AS (
    SELECT ArtNr,
    {_je('Menge', 'M')},
    {_je('Umsatz', 'U')},
    {_je('Rohertrag', 'R')},
    MAX(CASE WHEN S = 0 THEN Kunden ELSE 0 END) AS Kunden0,
    MAX(CASE WHEN S = 1 THEN Kunden ELSE 0 END) AS Kunden1,
    MAX(Letzter) AS Letzter
    FROM g GROUP BY ArtNr
)
SELECT COALESCE(NULLIF(LTRIM(RTRIM(art.ArtWgrNrInfo)), ''), 'ohne Warengruppe') AS Warengruppe,
    a.ArtNr, COALESCE(NULLIF(art.ArtKuBez1, ''), LEFT(art.ArtBez1, 80), '(Artikel fehlt)') AS Bezeichnung,
    art.ArtEinh AS Einheit,
    CASE WHEN a.U0 <> 0 OR a.M0 <> 0 THEN 1 ELSE 0 END AS Aktuell,
    CASE WHEN art.ArtGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre,
    {', '.join(f'a.M{i}' for i in range(SCHEIBEN))},
    {', '.join(f'a.U{i}' for i in range(SCHEIBEN))},
    {', '.join(f'a.R{i}' for i in range(SCHEIBEN))},
    a.Kunden0, a.Kunden1, CONVERT(char(10), a.Letzter, 104) AS LetzterVerkauf,
    LEFT(CONCAT(a.ArtNr, ' ', art.ArtKuBez1, ' ', art.ArtBez1, ' ', art.ArtKuBez2, ' ', art.ArtSuchBeg, ' ', art.ArtBarCd), 600) AS Suchtext
FROM a LEFT JOIN dbo.Artikel art ON art.ArtArtNr = a.ArtNr
ORDER BY Warengruppe, a.U0 DESC
"""

# Kunden eines Artikels – wer kauft ihn nicht mehr, wer weniger, wer neu.
SQL["m_bp_v12_kunden"] = f"""
WITH {V12},
k AS (
    SELECT AdrNr,
        SUM(CASE WHEN S = 0 THEN Menge ELSE 0 END) AS M0, SUM(CASE WHEN S = 1 THEN Menge ELSE 0 END) AS M1,
        SUM(CASE WHEN S = 2 THEN Menge ELSE 0 END) AS M2,
        SUM(CASE WHEN S = 0 THEN Umsatz ELSE 0 END) AS U0, SUM(CASE WHEN S = 1 THEN Umsatz ELSE 0 END) AS U1,
        SUM(CASE WHEN S = 2 THEN Umsatz ELSE 0 END) AS U2,
        SUM(CASE WHEN S >= 3 THEN Umsatz ELSE 0 END) AS UAelter,
        MAX(VogDat) AS Letzter
    FROM pos WHERE ArtNr = :artnr GROUP BY AdrNr
), s AS (
    SELECT k.*,
        CASE WHEN U0 <= 0 AND (U1 > 0 OR U2 > 0) THEN 'kauft nicht mehr'
             WHEN U0 <= 0 THEN 'früher (vor über 3 Jahren)'
             WHEN U1 > 0 AND U0 < U1 * 0.5 THEN 'kauft deutlich weniger'
             WHEN U1 <= 0 AND U2 <= 0 THEN 'neu'
             ELSE 'kauft' END AS Status,
        CASE WHEN U0 <= 0 AND (U1 > 0 OR U2 > 0) THEN 1
             WHEN U1 > 0 AND U0 > 0 AND U0 < U1 * 0.5 THEN 2
             WHEN U0 > 0 THEN 3 ELSE 4 END AS Rang
    FROM k
)
SELECT TOP 1000 s.Status, s.AdrNr, COALESCE(NULLIF(LTRIM(RTRIM(adr.AdrReNa2)), ''), CONCAT('Adresse ', s.AdrNr)) AS Kunde,
    adr.AdrReOrt AS Ort, adr.AdrReTel AS Telefon, adr.AdrVtrNr AS Vertreter,
    CONVERT(char(10), s.Letzter, 104) AS LetzterKauf,
    CAST(s.M0 AS DECIMAL(18,2)) AS MengeAktuell, CAST(s.M1 AS DECIMAL(18,2)) AS MengeVorjahr, CAST(s.M2 AS DECIMAL(18,2)) AS MengeVor2J,
    CAST(s.U0 AS DECIMAL(18,2)) AS UmsatzAktuell, CAST(s.U1 AS DECIMAL(18,2)) AS UmsatzVorjahr, CAST(s.U2 AS DECIMAL(18,2)) AS UmsatzVor2J,
    CASE WHEN adr.AdrGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre,
    CONCAT(s.AdrNr, '|', :artnr) AS KdArt
FROM s LEFT JOIN dbo.Adressen adr ON adr.AdrAdrNr = s.AdrNr
ORDER BY s.Rang, s.U1 + s.U2 + s.UAelter DESC, s.U0 DESC
"""

# Belege eines Kunden mit diesem Artikel (Schlüssel „AdrNr|ArtNr“ aus der Kundenliste)
SQL["m_bp_v12_kd_belege"] = f"""
WITH b AS (
    {BELEGE}
), sel AS (
    SELECT TRY_CONVERT(int, LEFT(:kdart, CHARINDEX('|', :kdart) - 1)) AS AdrNr,
        SUBSTRING(:kdart, CHARINDEX('|', :kdart) + 1, 100) AS ArtNr
)
SELECT TOP 500 b.VogBelegNr AS Beleg, b.VogArt AS Art, CONVERT(char(10), b.VogDat, 104) AS Datum,
    CAST(SUM(b.Vz * p.BuchMge) AS DECIMAL(18,2)) AS Menge, MAX(p.Einh) AS Einheit,
    CAST(MAX(p.EPrNt) AS DECIMAL(18,4)) AS Preis, CAST(MAX(p.EPreisFak) AS DECIMAL(9,4)) AS Preisfaktor,
    CAST(SUM(b.Vz * p.NettoPos) AS DECIMAL(18,2)) AS Umsatz, CAST(SUM(b.Vz * p.RohertragPos) AS DECIMAL(18,2)) AS Rohertrag,
    b.VogVerk AS Bearbeiter, CONCAT(CASE b.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, b.VogID) AS VogID
FROM dbo.vVorgangPosition p
JOIN b ON b.VogID = p.VogID AND b.Quelle = p.Quelle
JOIN sel ON sel.AdrNr = b.VogAdrNr AND sel.ArtNr = p.ArtNr
GROUP BY b.Quelle, b.VogID, b.VogBelegNr, b.VogArt, b.VogDat, b.VogVerk
ORDER BY b.VogDat DESC
"""

NAMEN.update({
    "m_bp_v12_artikel": "büro+ GF – Artikel-Verkauf 12-Monats-Vergleich",
    "m_bp_v12_kunden": "büro+ GF – Kunden des Artikels (Detail)",
    "m_bp_v12_kd_belege": "büro+ GF – Belege des Kunden mit dem Artikel (Detail)",
})

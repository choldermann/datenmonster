# Reiter „Regionen“ – wird von bauen.py per exec() eingebunden (nutzt BELEGE, SQL, NAMEN).
# Umsatz je Land und je Bundesland für die Karten-Widgets (wie im JTL-Cockpit).
# büro+-Vorgänge haben in unseren Exporten keine Lieferadresse → Land/PLZ aus der
# Rechnungsanschrift der Adresse (Adressen.AdrReLand = ISO-3166-Nummer, z. B. 276 = DE).

GEO_BASIS = f"""b AS (
    {BELEGE}
      AND VogDat >= DATEADD(YEAR, -1, :von) AND VogDat < DATEADD(DAY, 1, :bis)
), src AS (
    SELECT b.VogAdrNr, b.Vz, b.Netto, b.Ek,
        CASE WHEN b.VogDat >= :von AND b.VogDat < DATEADD(DAY, 1, :bis) THEN 1 ELSE 0 END AS cur,
        CASE WHEN b.VogDat >= DATEADD(YEAR, -1, :von) AND b.VogDat < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)) THEN 1 ELSE 0 END AS vj,
        ISNULL(a.AdrReLand, 276) AS IsoNum,
        TRY_CONVERT(INT, LEFT(LTRIM(a.AdrRePLZ), 2)) AS p, LTRIM(a.AdrRePLZ) AS plz
    FROM b LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = b.VogAdrNr
)"""

LAENDER = {
    276: "Deutschland", 40: "Österreich", 756: "Schweiz", 250: "Frankreich", 56: "Belgien", 528: "Niederlande",
    442: "Luxemburg", 208: "Dänemark", 752: "Schweden", 578: "Norwegen", 246: "Finnland", 380: "Italien",
    724: "Spanien", 620: "Portugal", 616: "Polen", 203: "Tschechien", 703: "Slowakei", 348: "Ungarn",
    705: "Slowenien", 191: "Kroatien", 642: "Rumänien", 100: "Bulgarien", 300: "Griechenland", 826: "Vereinigtes Königreich",
    372: "Irland", 438: "Liechtenstein", 233: "Estland", 428: "Lettland", 440: "Litauen", 470: "Malta", 196: "Zypern",
    792: "Türkei", 688: "Serbien", 70: "Bosnien und Herzegowina", 8: "Albanien", 807: "Nordmazedonien", 499: "Montenegro",
    804: "Ukraine", 840: "Vereinigte Staaten", 124: "Kanada", 156: "China", 784: "Vereinigte Arabische Emirate",
    # Bei Gehlen nur durch Fehlgriffe in der Länderauswahl belegt (Adressen in Karlsruhe, Bruchsal, Elsass)
    262: "Dschibuti (prüfen)", 212: "Dominica (prüfen)", 258: "Französisch-Polynesien (prüfen)",
}
LAND_CASE = "CASE g.IsoNum " + " ".join(f"WHEN {k} THEN N'{v}'" for k, v in LAENDER.items()) + \
            " ELSE CONCAT(N'Land ', g.IsoNum) END"

SQL["m_bp_geo_land"] = f"""
WITH {GEO_BASIS}, g AS (
    SELECT IsoNum,
        CAST(SUM(cur * Vz * Netto) AS DECIMAL(18,2)) AS Umsatz,
        CAST(SUM(vj * Vz * Netto) AS DECIMAL(18,2)) AS UmsatzVJ,
        CAST(SUM(cur * Vz * (Netto - Ek)) AS DECIMAL(18,2)) AS Rohertrag,
        COUNT(DISTINCT CASE WHEN cur = 1 AND Vz = 1 THEN VogAdrNr END) AS Kunden,
        SUM(CASE WHEN cur = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen
    FROM src GROUP BY IsoNum
)
SELECT CAST(g.IsoNum AS VARCHAR(10)) AS IsoNum, {LAND_CASE} AS Land,
    g.Umsatz, g.UmsatzVJ, g.Rohertrag,
    CAST(CASE WHEN g.Umsatz > 0 THEN 100.0 * g.Rohertrag / g.Umsatz END AS DECIMAL(18,1)) AS [Marge %],
    g.Kunden, g.Rechnungen
FROM g
WHERE g.Umsatz <> 0 OR g.UmsatzVJ <> 0
ORDER BY g.Umsatz DESC
"""

SQL["m_bp_geo_bundesland"] = f"""
WITH {GEO_BASIS}, k AS (
    SELECT *,
        CASE
            WHEN p IS NULL OR LEN(plz) <> 5 THEN '(ohne gültige PLZ)'
            WHEN p IN (1,2,4,8,9) THEN 'Sachsen'
            WHEN p IN (3,15,16) THEN 'Brandenburg'
            WHEN p IN (6,39) THEN 'Sachsen-Anhalt'
            WHEN p IN (7,98,99) THEN 'Thüringen'
            WHEN p IN (10,11,12,13,14) THEN 'Berlin'
            WHEN p IN (17,18,19) THEN 'Mecklenburg-Vorpommern'
            WHEN p IN (20,21,22) THEN 'Hamburg'
            WHEN p IN (23,24,25) THEN 'Schleswig-Holstein'
            WHEN p IN (26,27,29,30,31,37,38,49) THEN 'Niedersachsen'
            WHEN p = 28 THEN 'Bremen'
            WHEN p IN (32,33,40,41,42,44,45,46,47,48,50,51,52,53,57,58,59) THEN 'Nordrhein-Westfalen'
            WHEN p IN (34,35,36,60,61,63,64,65) THEN 'Hessen'
            WHEN p IN (54,55,56,67) THEN 'Rheinland-Pfalz'
            WHEN p = 66 THEN 'Saarland'
            WHEN p IN (68,69,88) OR p BETWEEN 70 AND 79 THEN 'Baden-Württemberg'
            WHEN p BETWEEN 80 AND 87 OR p BETWEEN 89 AND 97 THEN 'Bayern'
            ELSE '(unbekannt)'
        END AS Bundesland
    FROM src WHERE IsoNum = 276
)
SELECT Bundesland,
    CAST(SUM(cur * Vz * Netto) AS DECIMAL(18,2)) AS Umsatz,
    CAST(SUM(vj * Vz * Netto) AS DECIMAL(18,2)) AS UmsatzVJ,
    CAST(SUM(cur * Vz * (Netto - Ek)) AS DECIMAL(18,2)) AS Rohertrag,
    CAST(CASE WHEN SUM(cur * Vz * Netto) > 0 THEN 100.0 * SUM(cur * Vz * (Netto - Ek)) / SUM(cur * Vz * Netto) END AS DECIMAL(18,1)) AS [Marge %],
    COUNT(DISTINCT CASE WHEN cur = 1 AND Vz = 1 THEN VogAdrNr END) AS Kunden,
    SUM(CASE WHEN cur = 1 AND Vz = 1 THEN 1 ELSE 0 END) AS Rechnungen
FROM k GROUP BY Bundesland
HAVING SUM(cur * Vz * Netto) <> 0 OR SUM(vj * Vz * Netto) <> 0
ORDER BY SUM(cur * Vz * Netto) DESC
"""

NAMEN.update({
    "m_bp_geo_land": "büro+ GF – Umsatz je Land",
    "m_bp_geo_bundesland": "büro+ GF – Umsatz je Bundesland",
})

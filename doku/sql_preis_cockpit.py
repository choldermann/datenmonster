# -*- coding: utf-8 -*-
"""Die SQL-Bausteine des Preis- und Marge-Cockpits.

Getrennt vom Generator gehalten, damit jede Abfrage einzeln gegen eine WaWi
geprueft werden kann. Geprueft am 2026-09-08 gegen PPS (Verbindung 3) und
HaKo ecomData (Verbindung 7).

Laufzeitparameter: :von, :bis sowie die Schwellwerte :cfg_marge_min_prozent,
:cfg_marge_verfall_punkte und :cfg_ek_anstieg_prozent aus den
Projekteinstellungen. Die Drilldowns bekommen zusaetzlich :kArtikel, :kKunde,
:band oder :monat.
"""

SQL = {
    'm_pr_kpi': """WITH pos AS (
    SELECT
        CASE WHEN R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
             THEN 1 ELSE 0 END AS cur,
        CASE WHEN R.dErstellt >= DATEADD(YEAR, -1, :von)
              AND R.dErstellt < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis))
             THEN 1 ELSE 0 END AS vj,
        P.cArtNr, P.fVkNetto,
        P.fAnzahl * P.fVkNetto AS umsatz,
        P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS einsatz,
        CASE WHEN ISNULL(P.fEkNetto, 0) = 0 AND ISNULL(A.fEKNetto, 0) = 0
             THEN 1 ELSE 0 END AS ohne_ek
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= DATEADD(YEAR, -1, :von)
      AND R.dErstellt < DATEADD(DAY, 1, :bis)
),
art AS (
    SELECT cArtNr, SUM(umsatz) AS u, SUM(einsatz) AS e
    FROM pos WHERE cur = 1 GROUP BY cArtNr
)
SELECT
    CAST(SUM(CASE WHEN cur = 1 THEN umsatz END) AS DECIMAL(18,2))   AS Umsatz,
    CAST(SUM(CASE WHEN vj  = 1 THEN umsatz END) AS DECIMAL(18,2))   AS UmsatzVJ,
    CAST(SUM(CASE WHEN cur = 1 THEN einsatz END) AS DECIMAL(18,2))  AS Wareneinsatz,
    CAST(SUM(CASE WHEN cur = 1 THEN umsatz - einsatz END) AS DECIMAL(18,2))  AS Rohertrag,
    CAST(SUM(CASE WHEN vj  = 1 THEN umsatz - einsatz END) AS DECIMAL(18,2))  AS RohertragVJ,
    CAST(100.0 * SUM(CASE WHEN cur = 1 THEN umsatz - einsatz END)
         / NULLIF(SUM(CASE WHEN cur = 1 THEN umsatz END), 0) AS DECIMAL(18,2)) AS Marge,
    CAST(100.0 * SUM(CASE WHEN vj = 1 THEN umsatz - einsatz END)
         / NULLIF(SUM(CASE WHEN vj = 1 THEN umsatz END), 0) AS DECIMAL(18,2))  AS MargeVJ,
    SUM(CASE WHEN cur = 1 THEN ohne_ek ELSE 0 END)                  AS PosOhneEK,
    CAST(SUM(CASE WHEN cur = 1 AND ohne_ek = 1 THEN umsatz ELSE 0 END) AS DECIMAL(18,2)) AS UmsatzOhneEK,
    /* Gratisware: Position mit Erloes 0, aber echtem Wareneinsatz. Bei PPS sind
       das Muster und MHD-Abverkauf - sie druecken die Marge und sind sonst
       unsichtbar, weil sie in keiner Umsatzkennzahl auftauchen. */
    SUM(CASE WHEN cur = 1 AND fVkNetto = 0 AND einsatz > 0 THEN 1 ELSE 0 END) AS PosGratis,
    CAST(SUM(CASE WHEN cur = 1 AND fVkNetto = 0 THEN einsatz ELSE 0 END) AS DECIMAL(18,2)) AS EinsatzGratis,
    (SELECT COUNT(*) FROM art
      WHERE u > 0 AND 100.0 * (u - e) / NULLIF(u, 0) < :cfg_marge_min_prozent)
                                                                    AS ArtikelUnterMinMarge,
    (SELECT CAST(ISNULL(SUM(u), 0) AS DECIMAL(18,2)) FROM art
      WHERE u > 0 AND 100.0 * (u - e) / NULLIF(u, 0) < :cfg_marge_min_prozent)
                                                                    AS UmsatzUnterMinMarge
FROM pos""",
    'm_pr_monat': """WITH pos AS (
    SELECT FORMAT(R.dErstellt, 'yyyy-MM') AS Monat,
           CASE WHEN R.dErstellt >= :von THEN 1 ELSE 0 END AS cur,
           P.fAnzahl * P.fVkNetto AS umsatz,
           P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS einsatz
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= DATEADD(YEAR, -1, :von)
      AND R.dErstellt < DATEADD(DAY, 1, :bis)
),
m AS (
    /* Monat und Periode stehen schon als Spalten fest - wird erst hier
       gruppiert, muessten die Ausdruecke in der GROUP BY wiederholt werden,
       und der Ausfuehrungsweg des Mapping-Motors bricht daran ab. */
    SELECT Monat, cur, SUM(umsatz) AS u, SUM(umsatz - einsatz) AS r
    FROM pos GROUP BY Monat, cur
)
SELECT a.Monat,
       CAST(100.0 * a.r / NULLIF(a.u, 0) AS DECIMAL(18,2)) AS Marge,
       CAST(100.0 * v.r / NULLIF(v.u, 0) AS DECIMAL(18,2)) AS Vorjahr,
       CAST(a.u AS DECIMAL(18,2)) AS Umsatz,
       CAST(a.r AS DECIMAL(18,2)) AS Rohertrag
FROM m a
LEFT JOIN m v ON v.cur = 0
              AND v.Monat = FORMAT(DATEADD(YEAR, -1, CAST(a.Monat + '-01' AS DATE)), 'yyyy-MM')
WHERE a.cur = 1
ORDER BY a.Monat""",
    'm_pr_band': """WITH art AS (
    SELECT P.cArtNr,
           SUM(P.fAnzahl * P.fVkNetto) AS u,
           SUM(P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)) AS e,
           SUM(CASE WHEN ISNULL(P.fEkNetto, 0) = 0 AND ISNULL(A.fEKNetto, 0) = 0
                    THEN 1 ELSE 0 END) AS ohne_ek
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
    GROUP BY P.cArtNr
),
band AS (
    SELECT CASE
             WHEN ohne_ek > 0 AND e = 0        THEN '(kein EK hinterlegt)'
             WHEN u <= 0                       THEN 'ohne Umsatz'
             WHEN 100.0*(u-e)/u <  0           THEN 'unter 0 %'
             WHEN 100.0*(u-e)/u < 10           THEN '0 bis 10 %'
             WHEN 100.0*(u-e)/u < 20           THEN '10 bis 20 %'
             WHEN 100.0*(u-e)/u < 30           THEN '20 bis 30 %'
             WHEN 100.0*(u-e)/u < 50           THEN '30 bis 50 %'
             ELSE                                   'ueber 50 %'
           END AS Margenband,
           CASE
             WHEN ohne_ek > 0 AND e = 0 THEN 9 WHEN u <= 0 THEN 8
             WHEN 100.0*(u-e)/u <  0 THEN 1 WHEN 100.0*(u-e)/u < 10 THEN 2
             WHEN 100.0*(u-e)/u < 20 THEN 3 WHEN 100.0*(u-e)/u < 30 THEN 4
             WHEN 100.0*(u-e)/u < 50 THEN 5 ELSE 6 END AS Sortierung,
           u, e
    FROM art
)
SELECT Margenband, Sortierung,
       COUNT(*)                                   AS Artikelzahl,
       CAST(SUM(u) AS DECIMAL(18,2))              AS Umsatz,
       CAST(SUM(u - e) AS DECIMAL(18,2))          AS Rohertrag
FROM band GROUP BY Margenband, Sortierung ORDER BY Sortierung""",
    'm_pr_verfall': """WITH pos AS (
    SELECT P.cArtNr, P.cName,
        CASE WHEN R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
             THEN 1 ELSE 0 END AS cur,
        P.fAnzahl AS menge,
        P.fAnzahl * P.fVkNetto AS umsatz,
        P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS einsatz,
        CASE WHEN P.fVkNetto = 0 THEN P.fAnzahl ELSE 0 END AS menge_gratis,
        CASE WHEN P.fVkNetto = 0
             THEN P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)
             ELSE 0 END AS einsatz_gratis
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND (R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
        OR R.dErstellt >= DATEADD(YEAR, -1, :von)
       AND R.dErstellt < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)))
),
art AS (
    SELECT cArtNr, MAX(cName) AS cName,
        SUM(CASE WHEN cur = 1 THEN umsatz END)  AS uA, SUM(CASE WHEN cur = 1 THEN einsatz END) AS eA,
        SUM(CASE WHEN cur = 0 THEN umsatz END)  AS uV, SUM(CASE WHEN cur = 0 THEN einsatz END) AS eV,
        SUM(CASE WHEN cur = 1 THEN menge END)   AS mA, SUM(CASE WHEN cur = 0 THEN menge END)   AS mV
    FROM pos GROUP BY cArtNr
),
b AS (
    SELECT cArtNr, cName, uA, uV,
        100.0 * (uA - eA) / NULLIF(uA, 0) AS margeA,
        100.0 * (uV - eV) / NULLIF(uV, 0) AS margeV,
        uA / NULLIF(mA, 0) AS vkA, uV / NULLIF(mV, 0) AS vkV,
        eA / NULLIF(mA, 0) AS ekA, eV / NULLIF(mV, 0) AS ekV
    FROM art WHERE uA > 0 AND uV > 0 AND eA > 0 AND eV > 0
)
SELECT
    cArtNr                                        AS ArtNr,
    cName                                         AS Artikel,
    CAST(uA AS DECIMAL(18,2))                     AS Umsatz,
    CAST(margeA AS DECIMAL(18,2))                 AS Marge,
    CAST(margeV AS DECIMAL(18,2))                 AS MargeVorjahr,
    CAST(margeA - margeV AS DECIMAL(18,2))        AS Veraenderung,
    /* Was der Rueckgang in Euro kostet: der Rohertrag, der bei alter Marge
       auf dem heutigen Umsatz angefallen waere, abzueglich des heutigen. */
    CAST(uA * (margeV - margeA) / 100.0 AS DECIMAL(18,2)) AS RohertragEntgangen,
    CAST(vkA AS DECIMAL(18,4))                    AS VKaktuell,
    CAST(vkV AS DECIMAL(18,4))                    AS VKvorjahr,
    CAST(ekA AS DECIMAL(18,4))                    AS EKaktuell,
    CAST(ekV AS DECIMAL(18,4))                    AS EKvorjahr,
    CASE
      WHEN ekA > ekV * (1 + :cfg_ek_anstieg_prozent / 100.0) AND vkA < vkV * 0.99
           THEN 'EK gestiegen und VK gefallen'
      WHEN ekA > ekV * (1 + :cfg_ek_anstieg_prozent / 100.0)
           THEN 'EK gestiegen'
      WHEN vkA < vkV * 0.99
           THEN 'VK gefallen'
      ELSE 'Mengen-/Kundenmix'
    END                                           AS Ursache
FROM b
WHERE margeA > 0 AND margeV - margeA >= :cfg_marge_verfall_punkte
ORDER BY uA * (margeV - margeA) DESC""",
    'm_pr_unter_ek': """WITH pos AS (
    SELECT P.cArtNr, P.cName,
        CASE WHEN R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
             THEN 1 ELSE 0 END AS cur,
        P.fAnzahl AS menge,
        P.fAnzahl * P.fVkNetto AS umsatz,
        P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS einsatz,
        CASE WHEN P.fVkNetto = 0 THEN P.fAnzahl ELSE 0 END AS menge_gratis,
        CASE WHEN P.fVkNetto = 0
             THEN P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)
             ELSE 0 END AS einsatz_gratis
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND (R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
        OR R.dErstellt >= DATEADD(YEAR, -1, :von)
       AND R.dErstellt < DATEADD(DAY, 1, DATEADD(YEAR, -1, :bis)))
),
art AS (
    SELECT cArtNr, MAX(cName) AS cName,
        SUM(menge) AS m, SUM(umsatz) AS u, SUM(einsatz) AS e,
        SUM(menge_gratis) AS mg, SUM(einsatz_gratis) AS eg,
        COUNT(*) AS pos
    FROM pos WHERE cur = 1 GROUP BY cArtNr
)
SELECT
    cArtNr                                   AS ArtNr,
    cName                                    AS Artikel,
    CAST(m AS DECIMAL(18,2))                 AS Menge,
    CAST(u AS DECIMAL(18,2))                 AS Umsatz,
    CAST(e AS DECIMAL(18,2))                 AS Wareneinsatz,
    CAST(u - e AS DECIMAL(18,2))             AS Verlust,
    CAST(mg AS DECIMAL(18,2))                AS MengeGratis,
    CAST(eg AS DECIMAL(18,2))                AS EinsatzGratis,
    /* Trennt die beiden Ursachen: verschenkte Ware ist eine Entscheidung,
       ein zu tiefer Preis ist ein Fehler. */
    CASE WHEN eg >= (e - u) * 0.8 THEN 'Gratisware (Muster/Abverkauf)'
         WHEN eg > 0              THEN 'gemischt'
         ELSE                          'unter EK verkauft' END AS Ursache
FROM art
WHERE u - e < 0
ORDER BY u - e ASC""",
    'm_pr_kalk': """SELECT
    A.kArtikel,
    A.cArtNr                                    AS ArtNr,
    ISNULL(AB.cName, A.cArtNr)                  AS Artikel,
    ISNULL(G.cName, '(Standard)')               AS Kundengruppe,
    CAST(PL.fNettoPreis AS DECIMAL(18,4))       AS Verkaufspreis,
    CAST(A.fEKNetto AS DECIMAL(18,4))           AS Einkaufspreis,
    CAST(PL.fNettoPreis - A.fEKNetto AS DECIMAL(18,4)) AS Spanne,
    CAST(100.0 * (PL.fNettoPreis - A.fEKNetto) / NULLIF(PL.fNettoPreis, 0)
         AS DECIMAL(18,2))                      AS Marge,
    /* Was der Preis kosten muesste, um die Mindestmarge zu erreichen. */
    CAST(A.fEKNetto / NULLIF(1 - :cfg_marge_min_prozent / 100.0, 0)
         AS DECIMAL(18,4))                      AS Mindestpreis,
    CASE WHEN PL.fNettoPreis <= 0     THEN 'Preis nicht gepflegt'
         WHEN PL.fNettoPreis < A.fEKNetto THEN 'unter Einkaufspreis'
         ELSE                              'unter Mindestmarge' END AS Befund,
    CAST(ISNULL(L.fVerfuegbar, 0) AS DECIMAL(18,2)) AS Bestand
FROM dbo.tArtikel A
JOIN Preisliste.vPreislisteNetto PL ON PL.kArtikel = A.kArtikel
                                   AND PL.nAnzahlAb = 0 AND PL.kShop = 0
LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
                                     AND AB.kSprache = 1 AND AB.kPlattform = 1
LEFT JOIN dbo.tKundenGruppe G ON G.kKundenGruppe = PL.kKundenGruppe
LEFT JOIN dbo.tlagerbestand L ON L.kArtikel = A.kArtikel
WHERE ISNULL(A.nIstVater, 0) = 0
  AND ISNULL(A.cAktiv, 'Y') = 'Y'
  AND A.fEKNetto > 0
  AND (PL.fNettoPreis <= 0
    OR 100.0 * (PL.fNettoPreis - A.fEKNetto) / NULLIF(PL.fNettoPreis, 0)
       < :cfg_marge_min_prozent)
ORDER BY (PL.fNettoPreis - A.fEKNetto) ASC""",
    'm_pr_kalk_kpi': """WITH p AS (
    SELECT A.kArtikel, PL.kKundenGruppe, PL.fNettoPreis AS vk, A.fEKNetto AS ek
    FROM dbo.tArtikel A
    JOIN Preisliste.vPreislisteNetto PL ON PL.kArtikel = A.kArtikel
                                       AND PL.nAnzahlAb = 0 AND PL.kShop = 0
    WHERE ISNULL(A.nIstVater, 0) = 0 AND ISNULL(A.cAktiv, 'Y') = 'Y'
)
SELECT
    COUNT(*)                                                       AS Preise,
    COUNT(DISTINCT kArtikel)                                       AS ArtikelMitPreis,
    SUM(CASE WHEN ek > 0 AND (vk <= 0
                          OR 100.0 * (vk - ek) / NULLIF(vk, 0) < :cfg_marge_min_prozent)
             THEN 1 ELSE 0 END)                                    AS UnterMindestmarge,
    SUM(CASE WHEN ek > 0 AND vk > 0 AND vk < ek THEN 1 ELSE 0 END) AS UnterEinkaufspreis,
    SUM(CASE WHEN ISNULL(vk, 0) <= 0 THEN 1 ELSE 0 END)            AS PreisNull,
    SUM(CASE WHEN ISNULL(ek, 0) = 0 THEN 1 ELSE 0 END)             AS OhneEK,
    CAST(AVG(CASE WHEN ek > 0 AND vk > 0 THEN 100.0 * (vk - ek) / vk END)
         AS DECIMAL(18,2))                                         AS MargeDurchschnitt
FROM p""",
    'm_pr_ek_anstieg': """WITH e AS (
    SELECT W.kArtikel, W.dErstellt, W.fEKEinzel,
           ROW_NUMBER() OVER (PARTITION BY W.kArtikel ORDER BY W.dErstellt DESC) AS rn
    FROM dbo.tWarenLagerEingang W
    WHERE W.fEKEinzel > 0.05 AND W.fAnzahl > 0
      AND W.dErstellt >= DATEADD(YEAR, -2, :bis)
),
v AS (
    SELECT n.kArtikel,
           n.fEKEinzel AS ek_neu,  n.dErstellt AS d_neu,
           a.fEKEinzel AS ek_alt,  a.dErstellt AS d_alt
    FROM e n JOIN e a ON a.kArtikel = n.kArtikel AND a.rn = 2
    WHERE n.rn = 1
)
SELECT v.kArtikel,
    A.cArtNr                                        AS ArtNr,
    ISNULL(AB.cName, A.cArtNr)                      AS Artikel,
    CAST(v.ek_alt AS DECIMAL(18,4))                 AS EKvorher,
    CAST(v.ek_neu AS DECIMAL(18,4))                 AS EKneu,
    CAST(100.0 * (v.ek_neu - v.ek_alt) / NULLIF(v.ek_alt, 0) AS DECIMAL(18,2)) AS Anstieg,
    CAST(v.d_alt AS DATE)                           AS Vorherige,
    CAST(v.d_neu AS DATE)                           AS Letzte,
    CAST(A.fVKNetto AS DECIMAL(18,4))               AS Verkaufspreis,
    /* Marge zum neuen EK am unveraenderten Verkaufspreis - das ist der Punkt:
       ein gestiegener EK wirkt erst, wenn der VK nicht nachgezogen wurde. */
    CAST(100.0 * (A.fVKNetto - v.ek_neu) / NULLIF(A.fVKNetto, 0) AS DECIMAL(18,2)) AS MargeNeu,
    CAST(100.0 * (A.fVKNetto - v.ek_alt) / NULLIF(A.fVKNetto, 0) AS DECIMAL(18,2)) AS MargeVorher,
    CAST(ISNULL(L.fVerfuegbar, 0) AS DECIMAL(18,2)) AS Bestand
FROM v
JOIN dbo.tArtikel A ON A.kArtikel = v.kArtikel
LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
                                     AND AB.kSprache = 1 AND AB.kPlattform = 1
LEFT JOIN dbo.tlagerbestand L ON L.kArtikel = A.kArtikel
WHERE 100.0 * (v.ek_neu - v.ek_alt) / NULLIF(v.ek_alt, 0) >= :cfg_ek_anstieg_prozent
  AND v.ek_neu <= v.ek_alt * 5
ORDER BY 100.0 * (v.ek_neu - v.ek_alt) / NULLIF(v.ek_alt, 0) DESC""",
    'm_pr_rabatt_kpi': """SELECT
    COUNT(*)                                                   AS Positionen,
    SUM(CASE WHEN P.fRabatt > 0 THEN 1 ELSE 0 END)             AS MitRabatt,
    CAST(SUM(P.fAnzahl * P.fVkNetto) AS DECIMAL(18,2))         AS Listenwert,
    CAST(SUM(ISNULL(P.fWertNettoGesamtFixiert, P.fAnzahl * P.fVkNetto))
         AS DECIMAL(18,2))                                     AS Rechnungswert,
    CAST(SUM(P.fAnzahl * P.fVkNetto)
         - SUM(ISNULL(P.fWertNettoGesamtFixiert, P.fAnzahl * P.fVkNetto))
         AS DECIMAL(18,2))                                     AS Rabattbetrag,
    CAST(100.0 * (SUM(P.fAnzahl * P.fVkNetto)
         - SUM(ISNULL(P.fWertNettoGesamtFixiert, P.fAnzahl * P.fVkNetto)))
         / NULLIF(SUM(P.fAnzahl * P.fVkNetto), 0) AS DECIMAL(18,2)) AS Rabattquote,
    CAST(MAX(P.fRabatt) AS DECIMAL(18,2))                      AS HoechsterRabatt
FROM Rechnung.vRechnung R
JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
  AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)""",
    'm_pr_kunde_marge': """SELECT
    CAST(R.kKunde AS VARCHAR(20))                  AS kKunde,
    MAX(LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''), ISNULL(RA.cVorname,'') + ' ' + ISNULL(RA.cName,'')))))                                   AS Kunde,
    CAST(SUM(P.fAnzahl * P.fVkNetto) AS DECIMAL(18,2))  AS Umsatz,
    CAST(SUM(P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0))
         AS DECIMAL(18,2))                         AS Wareneinsatz,
    CAST(SUM(P.fAnzahl * (P.fVkNetto - COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)))
         AS DECIMAL(18,2))                         AS Rohertrag,
    CAST(100.0 * SUM(P.fAnzahl * (P.fVkNetto - COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)))
         / NULLIF(SUM(P.fAnzahl * P.fVkNetto), 0) AS DECIMAL(18,2)) AS Marge,
    CAST(SUM(P.fAnzahl * P.fVkNetto)
         - SUM(ISNULL(P.fWertNettoGesamtFixiert, P.fAnzahl * P.fVkNetto))
         AS DECIMAL(18,2))                         AS Rabattbetrag,
    COUNT(DISTINCT R.kRechnung)                    AS Rechnungen
FROM Rechnung.vRechnung R
JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
LEFT JOIN Rechnung.vRechnungRechnungsadresse RA ON RA.kRechnung = R.kRechnung
LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
  AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
GROUP BY R.kKunde
HAVING SUM(P.fAnzahl * P.fVkNetto) > 0
ORDER BY SUM(P.fAnzahl * P.fVkNetto) DESC""",
    'm_pr_pos_artikel': """WITH p AS (
    SELECT R.cRechnungsNr AS Rechnungsnr, R.dErstellt,
        LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''), ISNULL(RA.cVorname,'') + ' ' + ISNULL(RA.cName,'')))) AS Kunde,
        P.cArtNr AS ArtNr, P.cName AS Artikel,
        P.fAnzahl AS Menge, P.fVkNetto AS VK,
        COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS EK,
        P.fAnzahl * P.fVkNetto AS Erloes,
        P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS Einsatz,
        ROW_NUMBER() OVER (ORDER BY P.fAnzahl * P.fVkNetto DESC) AS rn
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN Rechnung.vRechnungRechnungsadresse RA ON RA.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
      AND P.cArtNr = :artnr
)
SELECT 0 AS Sortierung, Rechnungsnr,
    CONVERT(char(10), dErstellt, 104)          AS Datum,
    Kunde, ArtNr, Artikel,
    CAST(Menge AS DECIMAL(18,2))               AS Menge,
    CAST(VK AS DECIMAL(18,4))                  AS VK,
    CAST(EK AS DECIMAL(18,4))                  AS EK,
    CAST(Erloes AS DECIMAL(18,2))              AS Erloes,
    CAST(Erloes - Einsatz AS DECIMAL(18,2))    AS Rohertrag,
    CAST(100.0 * (Erloes - Einsatz) / NULLIF(Erloes, 0) AS DECIMAL(18,2)) AS Marge
FROM p WHERE rn <= 499
UNION ALL
SELECT 1, '', '', CONCAT('… ', COUNT(*), ' weitere Positionen'), '', '',
    CAST(SUM(Menge) AS DECIMAL(18,2)), NULL, NULL,
    CAST(SUM(Erloes) AS DECIMAL(18,2)),
    CAST(SUM(Erloes - Einsatz) AS DECIMAL(18,2)), NULL
FROM p WHERE rn > 499
HAVING COUNT(*) > 0
ORDER BY Sortierung, Erloes DESC""",
    'm_pr_pos_kunde': """WITH p AS (
    SELECT R.cRechnungsNr AS Rechnungsnr, R.dErstellt,
        LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,'')) + CASE WHEN ISNULL(RA.cZusatz,'') = '' OR CHARINDEX(LTRIM(RTRIM(RA.cZusatz)), ISNULL(RA.cFirma,'')) > 0 THEN '' ELSE ' ' + LTRIM(RTRIM(RA.cZusatz)) END), ''), ISNULL(RA.cVorname,'') + ' ' + ISNULL(RA.cName,'')))) AS Kunde,
        P.cArtNr AS ArtNr, P.cName AS Artikel,
        P.fAnzahl AS Menge, P.fVkNetto AS VK,
        COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS EK,
        P.fAnzahl * P.fVkNetto AS Erloes,
        P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0) AS Einsatz,
        ROW_NUMBER() OVER (ORDER BY P.fAnzahl * P.fVkNetto DESC) AS rn
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN Rechnung.vRechnungRechnungsadresse RA ON RA.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
      AND R.kKunde = :kKunde
)
SELECT 0 AS Sortierung, Rechnungsnr,
    CONVERT(char(10), dErstellt, 104)          AS Datum,
    Kunde, ArtNr, Artikel,
    CAST(Menge AS DECIMAL(18,2))               AS Menge,
    CAST(VK AS DECIMAL(18,4))                  AS VK,
    CAST(EK AS DECIMAL(18,4))                  AS EK,
    CAST(Erloes AS DECIMAL(18,2))              AS Erloes,
    CAST(Erloes - Einsatz AS DECIMAL(18,2))    AS Rohertrag,
    CAST(100.0 * (Erloes - Einsatz) / NULLIF(Erloes, 0) AS DECIMAL(18,2)) AS Marge
FROM p WHERE rn <= 499
UNION ALL
SELECT 1, '', '', CONCAT('… ', COUNT(*), ' weitere Positionen'), '', '',
    CAST(SUM(Menge) AS DECIMAL(18,2)), NULL, NULL,
    CAST(SUM(Erloes) AS DECIMAL(18,2)),
    CAST(SUM(Erloes - Einsatz) AS DECIMAL(18,2)), NULL
FROM p WHERE rn > 499
HAVING COUNT(*) > 0
ORDER BY Sortierung, Erloes DESC""",
    'm_pr_band_detail': """WITH art AS (
    SELECT P.cArtNr, MAX(P.cName) AS cName,
           SUM(P.fAnzahl) AS m,
           SUM(P.fAnzahl * P.fVkNetto) AS u,
           SUM(P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)) AS e,
           SUM(CASE WHEN ISNULL(P.fEkNetto, 0) = 0 AND ISNULL(A.fEKNetto, 0) = 0
                    THEN 1 ELSE 0 END) AS ohne_ek
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
    GROUP BY P.cArtNr
),
band AS (
    SELECT cArtNr, cName, m, u, e,
           CASE
             WHEN ohne_ek > 0 AND e = 0 THEN '(kein EK hinterlegt)'
             WHEN u <= 0                THEN 'ohne Umsatz'
             WHEN 100.0*(u-e)/u <  0    THEN 'unter 0 %'
             WHEN 100.0*(u-e)/u < 10    THEN '0 bis 10 %'
             WHEN 100.0*(u-e)/u < 20    THEN '10 bis 20 %'
             WHEN 100.0*(u-e)/u < 30    THEN '20 bis 30 %'
             WHEN 100.0*(u-e)/u < 50    THEN '30 bis 50 %'
             ELSE                            'ueber 50 %'
           END AS Margenband
    FROM art
)
SELECT cArtNr AS ArtNr, cName AS Artikel,
    CAST(m AS DECIMAL(18,2))          AS Menge,
    CAST(u AS DECIMAL(18,2))          AS Umsatz,
    CAST(e AS DECIMAL(18,2))          AS Wareneinsatz,
    CAST(u - e AS DECIMAL(18,2))      AS Rohertrag,
    CAST(100.0 * (u - e) / NULLIF(u, 0) AS DECIMAL(18,2)) AS Marge
FROM band
WHERE Margenband = :band
ORDER BY u DESC""",
    'm_pr_monat_detail': """WITH art AS (
    SELECT P.cArtNr, MAX(P.cName) AS cName,
           SUM(P.fAnzahl) AS m,
           SUM(P.fAnzahl * P.fVkNetto) AS u,
           SUM(P.fAnzahl * COALESCE(NULLIF(P.fEkNetto, 0), NULLIF(A.fEKNetto, 0), 0)) AS e
    FROM Rechnung.vRechnung R
    JOIN Rechnung.tRechnungPosition P ON P.kRechnung = R.kRechnung
    LEFT JOIN dbo.tArtikel A ON A.cArtNr = P.cArtNr
    WHERE ISNULL(R.nStorno, 0) = 0 AND P.nType = 1
      AND R.dErstellt >= :von AND R.dErstellt < DATEADD(DAY, 1, :bis)
      AND CONVERT(char(7), R.dErstellt, 120) = :monat
    GROUP BY P.cArtNr
)
SELECT cArtNr AS ArtNr, cName AS Artikel,
    CAST(m AS DECIMAL(18,2))          AS Menge,
    CAST(u AS DECIMAL(18,2))          AS Umsatz,
    CAST(e AS DECIMAL(18,2))          AS Wareneinsatz,
    CAST(u - e AS DECIMAL(18,2))      AS Rohertrag,
    CAST(100.0 * (u - e) / NULLIF(u, 0) AS DECIMAL(18,2)) AS Marge
FROM art
ORDER BY u DESC""",
}

# Reiter „Negative Bestände“ – wird von bauen.py per exec() eingebunden (nutzt SQL, NAMEN).
# büro+ exportiert weder Lagerbestand noch Lagerbuch. Deshalb Fortschreibung:
#   Soll = gezählte Menge der Inventur (dbo.InventurZaehlung, Skript tools/bueroplus/inventur.sql)
#        + Zugänge − Abgänge aus GEBUCHTEN, nicht stornierten Belegen nach dem Stichtag.
# Bei Gehlen bucht die Rechnung den Bestand (Lieferscheine fast nie gebucht), Zugänge über
# gebuchte Bestellungen. Negativer Soll-Bestand = Abgang ohne passenden Zugang: fehlende oder
# beleglose Zubuchung, falsche Einheit, Zählfehler oder Ware unter falscher Artikelnummer.
# Beleglose Lagerbuchungen in büro+ sind hier NICHT sichtbar.

STICHTAG = "CAST('{{inventur_stichtag}}' AS date)"

BEWEGUNG = f"""bew AS (
    SELECT p.ArtNr, v.Quelle, v.VogID, v.VogBelegNr, v.VogArt, v.VogDat, v.VogAdrNr, v.VogVerk,
        CASE WHEN v.VogArt IN ('Bestellung an Lieferant', 'Eingangsrechnung', 'Rechnungskorrektur') THEN 1 ELSE -1 END
            * p.BuchMge AS Menge
    FROM dbo.vVorgang v
    JOIN dbo.vVorgangPosition p ON p.VogID = v.VogID AND p.Quelle = v.Quelle
    WHERE v.VogGebuchtKz = 1 AND ISNULL(v.VogStorniertKz, 0) = 0
      AND v.VogDat > {STICHTAG}
      AND v.VogArt IN ('Bestellung an Lieferant', 'Eingangsrechnung', 'Rechnungskorrektur',
                       'Rechnung I', 'Sammel Rechnung', 'Lieferschein', 'Rechnungskorrektur vom Lieferant')
      AND p.ArtKz = 1 AND p.ArtNr IS NOT NULL AND p.ArtNr <> '' AND ISNULL(p.BuchMge, 0) <> 0
)"""

SQL["m_bp_negativ_bestand"] = f"""
WITH {BEWEGUNG}, inv AS (
    SELECT ArtNr, Menge, Einheit FROM dbo.InventurZaehlung WHERE Stichtag = {STICHTAG}
), s AS (
    SELECT ArtNr,
        SUM(CASE WHEN Menge > 0 THEN Menge ELSE 0 END) AS Zugaenge,
        -SUM(CASE WHEN Menge < 0 THEN Menge ELSE 0 END) AS Abgaenge,
        MAX(VogDat) AS Letzte
    FROM bew GROUP BY ArtNr
), k AS (
    SELECT COALESCE(inv.ArtNr, s.ArtNr) AS ArtNr, inv.Menge AS Gezaehlt, inv.Einheit AS EinheitInventur,
        ISNULL(s.Zugaenge, 0) AS Zugaenge, ISNULL(s.Abgaenge, 0) AS Abgaenge, s.Letzte,
        ISNULL(inv.Menge, 0) + ISNULL(s.Zugaenge, 0) - ISNULL(s.Abgaenge, 0) AS Soll
    FROM inv FULL JOIN s ON s.ArtNr = inv.ArtNr
)
SELECT k.ArtNr,
    COALESCE(NULLIF(LTRIM(RTRIM(art.ArtKuBez1)), ''), LEFT(REPLACE(REPLACE(art.ArtBez1, CHAR(13), ' '), CHAR(10), ' '), 80), '(Artikel fehlt)') AS Bezeichnung,
    CASE art.ArtEinh WHEN '%o' THEN 'Tsd' ELSE ISNULL(art.ArtEinh, '') END AS Einheit,
    CAST(k.Gezaehlt AS DECIMAL(18,2)) AS Gezaehlt,
    CAST(k.Zugaenge AS DECIMAL(18,2)) AS Zugaenge,
    CAST(k.Abgaenge AS DECIMAL(18,2)) AS Abgaenge,
    CAST(k.Soll AS DECIMAL(18,2)) AS SollBestand,
    -- Fehlmenge bewertet mit dem Kalkulations-EK (bei ‰ je 1.000 Stück)
    CAST(k.Soll * ISNULL(art.ArtEkKalk, 0) / CASE WHEN art.ArtEinh = '%o' THEN 1000 ELSE 1 END AS DECIMAL(18,2)) AS WertFehlmenge,
    CONCAT_WS('; ',
        CASE WHEN k.Gezaehlt IS NULL THEN 'nicht in der Inventur gezählt' END,
        CASE WHEN k.EinheitInventur = 'Paket' AND art.ArtEinh = '%o' THEN 'Inventur in Paketen, büro+ in Stück – Einheit prüfen' END,
        CASE WHEN k.Zugaenge = 0 THEN 'kein Zugang seit Inventur' END) AS Hinweis,
    CONVERT(char(10), k.Letzte, 104) AS LetzteBewegung,
    COALESCE(NULLIF(LTRIM(RTRIM(art.ArtWgrNrInfo)), ''), '') AS Warengruppe,
    CASE WHEN art.ArtGspKz = 1 THEN 'gesperrt' ELSE '' END AS Sperre
FROM k LEFT JOIN dbo.Artikel art ON art.ArtArtNr = k.ArtNr
WHERE k.Soll < 0
  -- keine DSZ-Gebühren, Fracht/Nebenkosten und Textartikel (weder Warengruppe noch EK)
  AND k.ArtNr NOT LIKE '%DSZ%' AND ISNULL(art.ArtWgrNrInfo, '') NOT LIKE 'DSZ%' AND ISNULL(art.ArtWgrNrInfo, '') NOT LIKE '0 DSD%'
  AND k.ArtNr NOT LIKE '27.000%' AND k.ArtNr <> '17.000'
  AND NOT (ISNULL(LTRIM(RTRIM(art.ArtWgrNrInfo)), '') = '' AND COALESCE(NULLIF(art.ArtEkKalk, 0), NULLIF(art.ArtEkMitt, 0)) IS NULL)
ORDER BY k.Soll * ISNULL(art.ArtEkKalk, 0) / CASE WHEN art.ArtEinh = '%o' THEN 1000 ELSE 1 END, k.ArtNr
"""

# Klick auf einen Artikel: Inventur als Startzeile, dann jede Bewegung mit laufendem Bestand
SQL["m_bp_negativ_bewegungen"] = f"""
WITH {BEWEGUNG}, z AS (
    SELECT 0 AS Reihe, {STICHTAG} AS VogDat, CAST(NULL AS nvarchar(40)) AS VogBelegNr,
        CONCAT('Inventur gezählt (', ISNULL(Einheit, ''), ')') AS Vorgang, CAST(NULL AS int) AS VogAdrNr,
        Menge, CAST(NULL AS nvarchar(20)) AS VogVerk, CAST(NULL AS nvarchar(20)) AS Quelle, CAST(NULL AS int) AS VogID
    FROM dbo.InventurZaehlung WHERE Stichtag = {STICHTAG} AND ArtNr = :artnr
    UNION ALL
    SELECT 1, VogDat, VogBelegNr, CONCAT(CASE WHEN Menge > 0 THEN 'Zugang – ' ELSE 'Abgang – ' END, VogArt),
        VogAdrNr, Menge, VogVerk, Quelle, VogID
    FROM bew WHERE ArtNr = :artnr
)
SELECT CONVERT(char(10), z.VogDat, 104) AS Datum, z.Vorgang, z.VogBelegNr AS Beleg,
    CASE WHEN z.VogAdrNr IS NOT NULL THEN COALESCE(NULLIF(LTRIM(RTRIM(ISNULL(a.AdrReNa2, ''))), ''), CONCAT('Adresse ', z.VogAdrNr)) END AS Partner,
    CAST(CASE WHEN z.Menge > 0 THEN z.Menge END AS DECIMAL(18,2)) AS Zugang,
    CAST(CASE WHEN z.Menge < 0 THEN -z.Menge END AS DECIMAL(18,2)) AS Abgang,
    CAST(SUM(z.Menge) OVER (ORDER BY z.Reihe, z.VogDat, z.VogBelegNr ROWS UNBOUNDED PRECEDING) AS DECIMAL(18,2)) AS Bestand,
    z.VogVerk AS Bearbeiter,
    CASE WHEN z.VogID IS NOT NULL THEN CONCAT(CASE z.Quelle WHEN 'Archiv' THEN 'A' ELSE 'U' END, z.VogID) END AS VogID
FROM z LEFT JOIN dbo.Adressen a ON a.AdrAdrNr = z.VogAdrNr
-- neueste Bewegung oben (lange Listen werden in der Anzeige gekürzt), Inventur als letzte Zeile
ORDER BY z.Reihe DESC, z.VogDat DESC, z.VogBelegNr DESC
"""

NAMEN.update({
    "m_bp_negativ_bestand": "büro+ GF – Negative Bestände seit Inventur",
    "m_bp_negativ_bewegungen": "büro+ GF – Bestandsbewegungen des Artikels seit Inventur (Detail)",
})

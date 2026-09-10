# -*- coding: utf-8 -*-
"""Die SQL-Bausteine für die neuen Reiter „Inventur" und „Abflüsse je Artikel".

Getrennt vom Generator gehalten, damit das SQL lesbar bleibt und einzeln gegen
die WaWi geprüft werden kann.
"""

# ── Gemeinsame Bausteine ─────────────────────────────────────────────────────

# Bestand je Eingangspartie zum Stichtag. Jede Historienzeile trägt
# kWarenLagerEingang, deshalb lässt sich der Bestand chargengenau auf jeden
# Stichtag zurückrechnen (gegen tWarenLagerEingang.fAnzahlAktuell verprobt:
# 4.773 von 4.773 Partien exakt).
PARTIE = """WITH partie AS (
    SELECT e.kArtikel, e.cChargenNr, e.dMHD,
           NULLIF(e.fEKEinzel, 0) AS ek_gebucht,
           COALESCE(NULLIF(e.fEKEinzel, 0), NULLIF(a0.fEKNetto, 0), 0) AS ek,
           SUM(h.fAnzahl) AS menge
    FROM dbo.vArtikelHistorie h
    JOIN dbo.tWarenLagerEingang e ON e.kWarenLagerEingang = h.kWarenLagerEingang
    JOIN dbo.tArtikel a0          ON a0.kArtikel = e.kArtikel
    WHERE h.dGebucht < DATEADD(DAY, 1, {ST})
    GROUP BY e.kArtikel, e.kWarenLagerEingang, e.cChargenNr, e.dMHD, e.fEKEinzel, a0.fEKNetto
    HAVING SUM(h.fAnzahl) > 0.0001
),
part_art AS (
    SELECT p.kArtikel,
           SUM(p.menge)             AS menge_partien,
           SUM(p.menge * p.ek)      AS wert_partien,
           SUM(CASE WHEN p.ek_gebucht IS NULL THEN p.menge ELSE 0 END) AS menge_ohne_ek,
           MIN(p.dMHD)              AS mhd_frueh,
           SUM(CASE WHEN p.dMHD IS NOT NULL AND p.dMHD < {ST} THEN p.menge ELSE 0 END)          AS menge_abgelaufen,
           SUM(CASE WHEN p.dMHD IS NOT NULL AND p.dMHD < {ST} THEN p.menge * p.ek ELSE 0 END)   AS wert_abgelaufen,
           -- Der Wert der Partien, die bald ablaufen. Bewusst NICHT der ganze
           -- Artikelwert: bei zehn Chargen ist meist nur eine betroffen, und
           -- eine Kennzahl, die den Rest mitzählt, führt zur Überabwertung.
           SUM(CASE WHEN p.dMHD IS NOT NULL AND p.dMHD >= {ST}
                     AND p.dMHD < DATEADD(MONTH, 3, {ST}) THEN p.menge * p.ek ELSE 0 END)       AS wert_unter3
    FROM partie p GROUP BY p.kArtikel
),
-- Der Gesamtbestand kommt aus tlagerbestand, auf den Stichtag zurückgerechnet.
-- Nur so ist auch Altbestand erfasst, der vor Beginn der Buchungshistorie
-- eingelagert wurde und zu keiner Partie gehört. Vaterartikel führen die Summe
-- ihrer Varianten und hätten den Bestand sonst doppelt gezählt.
bestand AS (
    SELECT l.kArtikel,
           l.fLagerbestand - ISNULL((SELECT SUM(h2.fAnzahl) FROM dbo.vArtikelHistorie h2
                                     WHERE h2.kArtikel = l.kArtikel
                                       AND h2.dGebucht >= DATEADD(DAY, 1, {ST})), 0) AS menge
    FROM dbo.tlagerbestand l
    JOIN dbo.tArtikel a ON a.kArtikel = l.kArtikel
    WHERE a.nIstVater = 0
),
abgang AS (
    SELECT h.kArtikel, SUM(-h.fAnzahl) AS menge12
    FROM dbo.vArtikelHistorie h
    WHERE h.fAnzahl < 0 AND h.cBuchungsart = 'Warenausgang'
      AND h.dGebucht >= DATEADD(MONTH, -12, {ST})
      AND h.dGebucht <  DATEADD(DAY, 1, {ST})
    GROUP BY h.kArtikel
),
letzter AS (
    SELECT h.kArtikel, MAX(h.dGebucht) AS dLetzter
    FROM dbo.vArtikelHistorie h
    WHERE h.fAnzahl < 0 AND h.cBuchungsart = 'Warenausgang'
      AND h.dGebucht < DATEADD(DAY, 1, {ST})
    GROUP BY h.kArtikel
)"""

# Wert einer Position: bewertete Partien plus der Rest zum Stammdaten-EK.
WERT = ("ISNULL(pa.wert_partien, 0) "
        "+ (b.menge - ISNULL(pa.menge_partien, 0)) * ISNULL(a.fEKNetto, 0)")


def _mit(st):
    return PARTIE.replace("{ST}", st)


# ── 1. Bestandsliste zum Stichtag (Grundlage der Inventur) ───────────────────

INV_BESTAND = _mit(":stichtag") + f"""
SELECT
    a.kArtikel                                       AS [kArtikel],
    a.cArtNr                                         AS [ArtNr],
    ab.cName                                         AS [Artikel],
    wg.cName                                         AS [Warengruppe],
    he.cName                                         AS [Hersteller],
    CAST(b.menge AS decimal(18,3))                   AS [Bestand],
    CAST(CASE WHEN b.menge > 0 THEN ({WERT}) / b.menge ELSE 0 END AS decimal(18,4)) AS [EK],
    CAST({WERT} AS decimal(18,2))                    AS [Wert],
    CONVERT(varchar(10), pa.mhd_frueh, 104)          AS [MHD],
    CASE WHEN pa.mhd_frueh IS NOT NULL
         THEN DATEDIFF(DAY, :stichtag, pa.mhd_frueh) END AS [Resttage],
    CAST(ISNULL(pa.menge_abgelaufen, 0) AS decimal(18,3)) AS [Menge abgelaufen],
    CAST(ISNULL(pa.wert_abgelaufen, 0) AS decimal(18,2))  AS [Wert abgelaufen],
    CAST(ISNULL(ag.menge12, 0) AS decimal(18,3))     AS [Abgang 12M],
    CASE WHEN ISNULL(ag.menge12, 0) > 0
         THEN CAST(b.menge / (ag.menge12 / 365.0) AS int) END AS [Reichweite Tage],
    CONVERT(varchar(10), le.dLetzter, 104)           AS [Letzter Abgang],
    CAST(CASE WHEN b.menge - ISNULL(pa.menge_partien, 0) > 0.0001
              THEN b.menge - ISNULL(pa.menge_partien, 0) ELSE 0 END AS decimal(18,3)) AS [Menge ohne Charge],
    -- Die Partien reisen als JSON mit: daraus rechnet der Abwertungsvorschlag
    -- den betroffenen Wertanteil je Restlaufzeit-Stufe.
    --
    -- Zusammengefasst nach Charge + MHD + EK, nicht je Einlagerung: JTL legt für
    -- JEDEN Wareneingang einen eigenen tWarenLagerEingang-Satz an, auch wenn es
    -- dieselbe Charge ist. Artikel 80217 bei PPS steht so mit fünf Zeilen
    -- „P26584" da (586 + 1 + 1 + 1 + 30 Stück), was wie eine Doppelbuchung
    -- aussieht und keine ist – 31 % aller Partien sind solche Nachbuchungen.
    -- Der EK bleibt im Schlüssel, weil dieselbe Charge zu unterschiedlichen
    -- Preisen eingelagert sein kann (131 Fälle); die zusammenzuwerfen würde
    -- Bewertungsinformation vernichten. `einlagerungen` weist die Bündelung aus.
    -- Gruppiert wird nach dem auf vier Stellen gerundeten EK, weil sonst
    -- Rechenrauschen zwei Zeilen erzeugt, die in der Anzeige identisch
    -- aussehen (bei Artikel 10181: 3,76880000 gegen 3,76884400). `wert` reist
    -- exakt summiert mit, damit die Rundung des EK die Bewertung nicht
    -- verschiebt – der Abwertungsvorschlag rechnet damit.
    (SELECT p2.cChargenNr AS charge,
            CONVERT(varchar(10), p2.dMHD, 104) AS mhd,
            CAST(SUM(p2.menge) AS decimal(18,3)) AS menge,
            CAST(SUM(p2.menge * p2.ek) / NULLIF(SUM(p2.menge), 0) AS decimal(18,4)) AS ek,
            CAST(SUM(p2.menge * p2.ek) AS decimal(18,2)) AS wert,
            COUNT(*) AS einlagerungen
     FROM partie p2 WHERE p2.kArtikel = a.kArtikel
     GROUP BY p2.cChargenNr, p2.dMHD, CAST(ROUND(p2.ek, 4) AS decimal(18,4))
     ORDER BY p2.dMHD FOR JSON PATH)                 AS [Chargen]
FROM bestand b
JOIN dbo.tArtikel a   ON a.kArtikel = b.kArtikel
LEFT JOIN part_art pa ON pa.kArtikel = a.kArtikel
LEFT JOIN abgang ag   ON ag.kArtikel = a.kArtikel
LEFT JOIN letzter le  ON le.kArtikel = a.kArtikel
LEFT JOIN dbo.tArtikelBeschreibung ab ON ab.kArtikel = a.kArtikel AND ab.kSprache = 1 AND ab.kPlattform = 1
LEFT JOIN dbo.tWarengruppe wg ON wg.kWarengruppe = a.kWarengruppe
LEFT JOIN dbo.tHersteller he  ON he.kHersteller  = a.kHersteller
WHERE b.menge > 0.0001
  AND (:excluded_articles_empty = 1 OR a.kArtikel NOT IN (:excluded_articles))
ORDER BY [Wert] DESC"""


# ── 2. Kennzahlen des Stichtagsbestands ──────────────────────────────────────

INV_KPI = _mit(":bis") + f"""
SELECT
    COUNT(*)                                          AS [Artikel],
    CAST(SUM(b.menge) AS decimal(18,0))               AS [Stueck],
    CAST(SUM({WERT}) AS decimal(18,2))                AS [Bestandswert],
    CAST(SUM(ISNULL(pa.wert_abgelaufen, 0)) AS decimal(18,2)) AS [WertAbgelaufen],
    CAST(SUM(ISNULL(pa.wert_unter3, 0)) AS decimal(18,2)) AS [WertUnter3Monate],
    SUM(CASE WHEN ISNULL(ag.menge12, 0) = 0 THEN 1 ELSE 0 END) AS [OhneAbgang12M],
    CAST(SUM(CASE WHEN ISNULL(ag.menge12, 0) = 0 THEN {WERT} ELSE 0 END) AS decimal(18,2)) AS [WertOhneAbgang],
    SUM(CASE WHEN ISNULL(pa.menge_ohne_ek, 0) > 0 THEN 1 ELSE 0 END) AS [OhneGebuchtenEK],
    CAST(SUM(CASE WHEN b.menge - ISNULL(pa.menge_partien, 0) > 0.0001
                  THEN b.menge - ISNULL(pa.menge_partien, 0) ELSE 0 END) AS decimal(18,0)) AS [MengeOhneCharge]
FROM bestand b
JOIN dbo.tArtikel a   ON a.kArtikel = b.kArtikel
LEFT JOIN part_art pa ON pa.kArtikel = a.kArtikel
LEFT JOIN abgang ag   ON ag.kArtikel = a.kArtikel
WHERE b.menge > 0.0001
  AND (:excluded_articles_empty = 1 OR a.kArtikel NOT IN (:excluded_articles))"""


# ── 3. Bestandswert nach Restlaufzeit ────────────────────────────────────────
#
# Klassifiziert wird die einzelne PARTIE, nicht der Artikel: Ein Artikel mit
# zehn Chargen hat oft eine abgelaufene und neun frische. Würde man ihn nach
# dem frühesten MHD einordnen, stünden bei PPS 90 T€ unter „überschritten"
# statt der tatsächlichen 46 T€ – und genau danach würde abgewertet.

INV_MHD = _mit(":bis") + """
, klasse AS (
    SELECT CASE
             WHEN p.dMHD IS NULL THEN '6 ohne MHD'
             WHEN p.dMHD <  :bis THEN '1 abgelaufen'
             WHEN p.dMHD <  DATEADD(MONTH, 3,  :bis) THEN '2 unter 3 Monate'
             WHEN p.dMHD <  DATEADD(MONTH, 6,  :bis) THEN '3 drei bis sechs Monate'
             WHEN p.dMHD <  DATEADD(MONTH, 12, :bis) THEN '4 sechs bis zwoelf Monate'
             ELSE '5 ueber ein Jahr' END AS klasse,
           p.menge * p.ek AS wert, p.menge, p.kArtikel
    FROM partie p
    JOIN dbo.tArtikel a ON a.kArtikel = p.kArtikel
    WHERE (:excluded_articles_empty = 1 OR p.kArtikel NOT IN (:excluded_articles))
    UNION ALL
    -- Altbestand ohne Eingangspartie hat kein MHD, gehört aber in die Summe,
    -- sonst passt die Klassenverteilung nicht zum Bestandswert.
    SELECT '6 ohne MHD',
           (b.menge - ISNULL(pa.menge_partien, 0)) * ISNULL(a.fEKNetto, 0),
           b.menge - ISNULL(pa.menge_partien, 0), a.kArtikel
    FROM bestand b
    JOIN dbo.tArtikel a   ON a.kArtikel = b.kArtikel
    LEFT JOIN part_art pa ON pa.kArtikel = a.kArtikel
    WHERE b.menge - ISNULL(pa.menge_partien, 0) > 0.0001
      AND (:excluded_articles_empty = 1 OR a.kArtikel NOT IN (:excluded_articles))
)
SELECT
    CASE k.klasse
      WHEN '1 abgelaufen'              THEN 'MHD überschritten'
      WHEN '2 unter 3 Monate'          THEN 'unter 3 Monate'
      WHEN '3 drei bis sechs Monate'   THEN '3 bis 6 Monate'
      WHEN '4 sechs bis zwoelf Monate' THEN '6 bis 12 Monate'
      WHEN '5 ueber ein Jahr'          THEN 'über 1 Jahr'
      ELSE 'ohne MHD' END                        AS [Restlaufzeit],
    COUNT(DISTINCT k.kArtikel)                   AS [Artikel],
    CAST(SUM(k.menge) AS decimal(18,0))          AS [Stueck],
    CAST(SUM(k.wert) AS decimal(18,2))           AS [Wert]
FROM klasse k
GROUP BY k.klasse
ORDER BY k.klasse"""


# ── Abflüsse: gemeinsamer Kopf ───────────────────────────────────────────────
#
# Der Artikelfilter greift auch über den Vaterartikel: „VAR80215" findet alle
# Größen darunter, „80218" nur die eine. Ohne Eingabe gilt kein Filter – dann
# kommt das ganze Sortiment, nach Menge sortiert. Früher blieb der Reiter leer,
# und ein leeres Feld sah aus wie „keine Abgänge" (PPS, 10.09.). Über alle
# Artikel eines Jahres läuft das bei PPS in rund einer Sekunde.
ABFLUSS_KOPF = """WITH treffer AS (
    SELECT a.kArtikel
    FROM dbo.tArtikel a
    LEFT JOIN dbo.tArtikel va ON va.kArtikel = a.kVaterArtikel
    LEFT JOIN dbo.tArtikelBeschreibung ab ON ab.kArtikel = a.kArtikel AND ab.kSprache = 1 AND ab.kPlattform = 1
    WHERE a.nIstVater = 0
      AND (LTRIM(RTRIM(ISNULL(:artikel_suche, ''))) = ''
           OR a.cArtNr LIKE :artikel_suche + '%'
           OR va.cArtNr LIKE :artikel_suche + '%'
           OR ab.cName LIKE '%' + :artikel_suche + '%')
),
-- Abgänge kommen aus der Buchungshistorie, nicht aus Rechnungen: nur so sind
-- auch unberechnete Lieferungen und Korrekturen sichtbar.
ausgang AS (
    SELECT h.kArtikel, h.kLieferscheinPos, h.cBuchungsart, h.dGebucht, -h.fAnzahl AS menge
    FROM dbo.vArtikelHistorie h
    JOIN treffer t ON t.kArtikel = h.kArtikel
    WHERE h.fAnzahl < 0
      AND h.dGebucht >= :von AND h.dGebucht < DATEADD(DAY, 1, :bis)
),
zeile AS (
    SELECT g.menge, g.cBuchungsart, g.dGebucht, g.kArtikel,
           a.cArtNr, ab.cName AS artikelname,
           b.tKunde_kKunde AS kKunde,
           ISNULL(bp.fVkNetto, 0) AS vk_netto
    FROM ausgang g
    JOIN dbo.tArtikel a ON a.kArtikel = g.kArtikel
    LEFT JOIN dbo.tArtikelBeschreibung ab ON ab.kArtikel = a.kArtikel AND ab.kSprache = 1 AND ab.kPlattform = 1
    LEFT JOIN dbo.tLieferscheinPos lp ON lp.kLieferscheinPos = g.kLieferscheinPos
    LEFT JOIN dbo.tLieferschein ls    ON ls.kLieferschein = lp.kLieferschein
    LEFT JOIN dbo.tBestellung b       ON b.kBestellung = ls.kBestellung
    LEFT JOIN dbo.tBestellPos bp      ON bp.kBestellPos = lp.kBestellPos
)"""

# Der Schalter „verbundene Unternehmen ausblenden" wirkt nur auf zugeordnete
# Kunden. Buchungen ohne Kundenbezug (Korrekturen, Umlagerungen) bleiben
# sichtbar – sie zu verstecken würde die Mengendifferenz unerklärlich machen.
OHNE_VERBUNDENE = ("(:ohne_verbundene = 0 OR :excluded_customers_empty = 1 "
                   "OR z.kKunde IS NULL OR z.kKunde NOT IN (:excluded_customers))")

KUNDENNAME = """LTRIM(RTRIM(ISNULL(NULLIF(adr.cFirma, ''), '') + ' ' + ISNULL(NULLIF(adr.cZusatz, ''), '')))"""
KUNDENNAME_VOLL = f"""CASE WHEN z.kKunde IS NULL
         THEN '(ohne Kundenbezug: ' + ISNULL(z.cBuchungsart, 'unbekannt') + ')'
         WHEN LTRIM(RTRIM(ISNULL(adr.cFirma, '') + ISNULL(adr.cZusatz, ''))) = ''
         THEN LTRIM(RTRIM(ISNULL(adr.cVorname, '') + ' ' + ISNULL(adr.cName, '')))
         ELSE {KUNDENNAME} END"""

ADR = ("""OUTER APPLY (SELECT TOP 1 a2.cFirma, a2.cZusatz, a2.cVorname, a2.cName
             FROM dbo.tAdresse a2 WHERE a2.kKunde = z.kKunde AND a2.nTyp = 1
             ORDER BY a2.nStandard DESC, a2.kAdresse) adr""")


# ── 4. Abflüsse: Kennzahlen ──────────────────────────────────────────────────

AB_KPI = ABFLUSS_KOPF + f"""
SELECT
    CAST(SUM(z.menge) AS decimal(18,2))              AS [AbgangGesamt],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [AnKunden],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND (:excluded_customers_empty = 0
                   AND z.kKunde IN (:excluded_customers)) THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [AnVerbundene],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND (:excluded_customers_empty = 1
                   OR z.kKunde NOT IN (:excluded_customers)) THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [AnFremdkunden],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND z.vk_netto = 0 THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [OhneBerechnung],
    CAST(SUM(CASE WHEN z.kKunde IS NULL THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [OhneKundenbezug],
    CAST(SUM(z.menge * z.vk_netto) AS decimal(18,2)) AS [UmsatzNetto],
    COUNT(DISTINCT CASE WHEN z.kKunde IS NOT NULL AND (:excluded_customers_empty = 1
                   OR z.kKunde NOT IN (:excluded_customers)) THEN z.kKunde END) AS [Fremdkunden],
    COUNT(DISTINCT z.kArtikel)                       AS [Artikel]
FROM zeile z"""


# ── 5. Abflüsse je Kunde ─────────────────────────────────────────────────────

AB_KUNDEN = ABFLUSS_KOPF + f"""
SELECT
    {KUNDENNAME_VOLL}                                AS [Kunde],
    z.kKunde                                         AS [kKunde],
    CAST(SUM(z.menge) AS decimal(18,2))              AS [Menge],
    CAST(SUM(CASE WHEN z.vk_netto > 0 THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [davon berechnet],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND z.vk_netto = 0 THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [davon zum Preis 0],
    CAST(SUM(z.menge * z.vk_netto) AS decimal(18,2)) AS [Umsatz netto],
    CAST(CASE WHEN SUM(CASE WHEN z.vk_netto > 0 THEN z.menge ELSE 0 END) > 0
              THEN SUM(z.menge * z.vk_netto) / SUM(CASE WHEN z.vk_netto > 0 THEN z.menge ELSE 0 END)
         END AS decimal(18,2))                       AS [Preis je Stueck],
    CASE WHEN :excluded_customers_empty = 0 AND z.kKunde IN (:excluded_customers)
         THEN 'verbunden' ELSE '' END                AS [Hinweis]
FROM zeile z
{ADR}
WHERE {OHNE_VERBUNDENE}
GROUP BY z.kKunde, z.cBuchungsart, adr.cFirma, adr.cZusatz, adr.cVorname, adr.cName
ORDER BY [Menge] DESC"""


# ── 6. Abflüsse je Artikel / Größe ───────────────────────────────────────────

AB_ARTIKEL = ABFLUSS_KOPF + f"""
SELECT
    z.cArtNr                                         AS [ArtNr],
    z.artikelname                                    AS [Artikel],
    CAST(SUM(z.menge) AS decimal(18,2))              AS [Menge],
    CAST(SUM(CASE WHEN z.vk_netto > 0 THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [davon berechnet],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND z.vk_netto = 0 THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [davon zum Preis 0],
    CAST(SUM(CASE WHEN z.kKunde IS NULL THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [ohne Kundenbezug],
    COUNT(DISTINCT z.kKunde)                         AS [Kunden],
    CAST(SUM(z.menge * z.vk_netto) AS decimal(18,2)) AS [Umsatz netto]
FROM zeile z
WHERE {OHNE_VERBUNDENE}
GROUP BY z.kArtikel, z.cArtNr, z.artikelname
ORDER BY [Menge] DESC"""


# ── 7. Abflüsse je Monat ─────────────────────────────────────────────────────

AB_MONAT = ABFLUSS_KOPF + f"""
SELECT
    FORMAT(z.dGebucht, 'yyyy-MM')                    AS [Monat],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND (:excluded_customers_empty = 1
              OR z.kKunde NOT IN (:excluded_customers)) THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [Fremdkunden],
    CAST(SUM(CASE WHEN z.kKunde IS NOT NULL AND :excluded_customers_empty = 0
              AND z.kKunde IN (:excluded_customers) THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [Verbundene],
    CAST(SUM(CASE WHEN z.kKunde IS NULL THEN z.menge ELSE 0 END) AS decimal(18,2)) AS [ohne Kundenbezug]
FROM zeile z
GROUP BY FORMAT(z.dGebucht, 'yyyy-MM')
ORDER BY [Monat]"""


# ── 8. Abflüsse nach Buchungsart ─────────────────────────────────────────────
#
# Der Reiter muss zeigen, was KEIN Kundenabfluss ist: bei einer der Größen des
# Beispielartikels waren 9.800 von 13.122 Stück Korrekturbuchungen. Wer die als
# Verkauf liest, plant am Bedarf vorbei.
AB_ARTEN = ABFLUSS_KOPF + """
SELECT
    ISNULL(z.cBuchungsart, 'unbekannt')              AS [Buchungsart],
    CASE WHEN z.kKunde IS NULL THEN 'ohne Kundenbezug' ELSE 'mit Kundenbezug' END AS [Zuordnung],
    CAST(SUM(z.menge) AS decimal(18,2))              AS [Menge],
    COUNT(*)                                         AS [Buchungen]
FROM zeile z
GROUP BY z.cBuchungsart, CASE WHEN z.kKunde IS NULL THEN 'ohne Kundenbezug' ELSE 'mit Kundenbezug' END
ORDER BY [Menge] DESC"""


# ── 9. Drilldown: Belege eines Kunden ────────────────────────────────────────

AB_BELEGE = ABFLUSS_KOPF.replace(
    "SELECT g.menge, g.cBuchungsart, g.dGebucht, g.kArtikel,",
    "SELECT g.menge, g.cBuchungsart, g.dGebucht, g.kArtikel, ls.cLieferscheinNr,") + f"""
SELECT
    CONVERT(varchar(10), z.dGebucht, 104)            AS [Datum],
    z.cLieferscheinNr                                AS [Lieferschein],
    z.cArtNr                                         AS [ArtNr],
    z.artikelname                                    AS [Artikel],
    CAST(z.menge AS decimal(18,2))                   AS [Menge],
    CAST(z.vk_netto AS decimal(18,2))                AS [Preis netto],
    CAST(z.menge * z.vk_netto AS decimal(18,2))      AS [Wert],
    z.cBuchungsart                                   AS [Buchungsart]
FROM zeile z
WHERE (:kunde IS NULL OR z.kKunde = :kunde)
ORDER BY z.dGebucht DESC"""

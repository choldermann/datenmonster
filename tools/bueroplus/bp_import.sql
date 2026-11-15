/* büro+-Import: Staging, Ladeprozeduren, Protokoll.
   ERZEUGT von tools/bueroplus/sql_bauen.py – nicht von Hand ändern.
   Einmal je Datenbank ausführen (idempotent; legt nichts doppelt an, ändert keine Zieldaten). */
SET NOCOUNT ON;
GO
IF SCHEMA_ID(N'stg') IS NULL EXEC(N'CREATE SCHEMA stg');
GO
IF OBJECT_ID(N'dbo.ImportLog') IS NULL
CREATE TABLE dbo.ImportLog (
  ID int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ImportLog PRIMARY KEY,
  Zeitpunkt datetime2(0) NOT NULL CONSTRAINT DF_ImportLog_Zeitpunkt DEFAULT SYSDATETIME(),
  Tabelle nvarchar(100) NULL,
  ZeilenAlt int NULL,
  ZeilenNeu int NULL,
  Status nvarchar(20) NOT NULL,
  Meldung nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'stg.Artikel') IS NOT NULL DROP TABLE stg.Artikel;
CREATE TABLE stg.Artikel (
  [ArtID] nvarchar(max) NULL,
  [ArtArtNr] nvarchar(max) NULL,
  [ArtSuchBeg] nvarchar(max) NULL,
  [ArtArtikelArt] nvarchar(max) NULL,
  [ArtGspKz] nvarchar(max) NULL,
  [ArtBarCd] nvarchar(max) NULL,
  [ArtWgrNr] nvarchar(max) NULL,
  [ArtWgrNrInfo] nvarchar(max) NULL,
  [ArtKuBez1] nvarchar(max) NULL,
  [ArtBez1] nvarchar(max) NULL,
  [ArtKuBez2] nvarchar(max) NULL,
  [ArtBez2] nvarchar(max) NULL,
  [ArtKuBez3] nvarchar(max) NULL,
  [ArtBez3] nvarchar(max) NULL,
  [ArtEinh] nvarchar(max) NULL,
  [ArtMgeFak] nvarchar(max) NULL,
  [ArtEPreisFak] nvarchar(max) NULL,
  [ArtGew] nvarchar(max) NULL,
  [ArtLaenge] nvarchar(max) NULL,
  [ArtBreite] nvarchar(max) NULL,
  [ArtHoehe] nvarchar(max) NULL,
  [ArtLaengeEinh] nvarchar(max) NULL,
  [ArtInhaltMge] nvarchar(max) NULL,
  [ArtInhaltEinh] nvarchar(max) NULL,
  [ArtGrPrEinh] nvarchar(max) NULL,
  [ArtBeschr] nvarchar(max) NULL,
  [ArtStSchl] nvarchar(max) NULL,
  [ArtStSchlArt] nvarchar(max) NULL,
  [ArtSktoKz] nvarchar(max) NULL,
  [ArtNichtSktoNetBet] nvarchar(max) NULL,
  [ArtStGArtKz] nvarchar(max) NULL,
  [ArtHstAdrNr] nvarchar(max) NULL,
  [ArtHstArtNr] nvarchar(max) NULL,
  [ArtEkMitt] nvarchar(max) NULL,
  [ArtEkKalkVgb] nvarchar(max) NULL,
  [ArtEkKalkSchl] nvarchar(max) NULL,
  [ArtEkKalk] nvarchar(max) NULL,
  [ArtEkRohVgb] nvarchar(max) NULL,
  [ArtVk0Preis] nvarchar(max) NULL,
  [ArtVk1Preis] nvarchar(max) NULL,
  [ArtVk2Preis] nvarchar(max) NULL,
  [ArtVk3Preis] nvarchar(max) NULL,
  [ArtVk4Preis] nvarchar(max) NULL,
  [ArtVk5Preis] nvarchar(max) NULL,
  [ArtVk6Preis] nvarchar(max) NULL,
  [ArtVk7Preis] nvarchar(max) NULL,
  [ArtVk8Preis] nvarchar(max) NULL,
  [ArtVk9Preis] nvarchar(max) NULL,
  [ArtVkDat] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.Artikel') IS NULL
BEGIN
  CREATE TABLE dbo.Artikel (
    [ArtID] int,
    [ArtArtNr] nvarchar(30) NOT NULL,
    [ArtSuchBeg] nvarchar(50),
    [ArtArtikelArt] nvarchar(30),
    [ArtGspKz] bit NOT NULL CONSTRAINT DF_Artikel_ArtGspKz DEFAULT 0,
    [ArtBarCd] nvarchar(30),
    [ArtWgrNr] nvarchar(30),
    [ArtWgrNrInfo] nvarchar(100),
    [ArtKuBez1] nvarchar(100),
    [ArtBez1] nvarchar(max),
    [ArtKuBez2] nvarchar(100),
    [ArtBez2] nvarchar(200),
    [ArtKuBez3] nvarchar(100),
    [ArtBez3] nvarchar(200),
    [ArtEinh] nvarchar(10),
    [ArtMgeFak] decimal(18,4),
    [ArtEPreisFak] decimal(9,4),
    [ArtGew] decimal(18,4),
    [ArtLaenge] decimal(18,4),
    [ArtBreite] decimal(18,4),
    [ArtHoehe] decimal(18,4),
    [ArtLaengeEinh] nvarchar(10),
    [ArtInhaltMge] decimal(18,4),
    [ArtInhaltEinh] nvarchar(20),
    [ArtGrPrEinh] nvarchar(20),
    [ArtBeschr] nvarchar(max),
    [ArtStSchl] nvarchar(60),
    [ArtStSchlArt] int,
    [ArtSktoKz] bit,
    [ArtNichtSktoNetBet] decimal(14,2),
    [ArtStGArtKz] bit,
    [ArtHstAdrNr] int,
    [ArtHstArtNr] nvarchar(30),
    [ArtEkMitt] decimal(14,4),
    [ArtEkKalkVgb] decimal(14,4),
    [ArtEkKalkSchl] nvarchar(60),
    [ArtEkKalk] decimal(14,4),
    [ArtEkRohVgb] decimal(14,4),
    [ArtVk0Preis] decimal(14,4),
    [ArtVk1Preis] decimal(14,4),
    [ArtVk2Preis] decimal(14,4),
    [ArtVk3Preis] decimal(14,4),
    [ArtVk4Preis] decimal(14,4),
    [ArtVk5Preis] decimal(14,4),
    [ArtVk6Preis] decimal(14,4),
    [ArtVk7Preis] decimal(14,4),
    [ArtVk8Preis] decimal(14,4),
    [ArtVk9Preis] decimal(14,4),
    [ArtVkDat] date,
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_Artikel PRIMARY KEY (ArtArtNr)
  );
  CREATE INDEX IX_Artikel_ArtWgrNr ON dbo.Artikel(ArtWgrNr);
  CREATE INDEX IX_Artikel_ArtID ON dbo.Artikel(ArtID);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_Artikel @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.Artikel prüfen und dbo.Artikel vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.Artikel);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.Artikel);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'Artikel: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'Artikel: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'ArtID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtID], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtID]), N'')) IS NULL
    UNION ALL
    SELECT N'ArtArtNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtArtNr], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtArtNr]) > 30
    UNION ALL
    SELECT N'ArtSuchBeg' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtSuchBeg], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtSuchBeg]) > 50
    UNION ALL
    SELECT N'ArtArtikelArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtArtikelArt], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtArtikelArt]) > 30
    UNION ALL
    SELECT N'ArtGspKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtGspKz], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGspKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGspKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'ArtBarCd' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtBarCd], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtBarCd]) > 30
    UNION ALL
    SELECT N'ArtWgrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtWgrNr], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtWgrNr]) > 30
    UNION ALL
    SELECT N'ArtWgrNrInfo' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtWgrNrInfo], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtWgrNrInfo]) > 100
    UNION ALL
    SELECT N'ArtKuBez1' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtKuBez1], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtKuBez1]) > 100
    UNION ALL
    SELECT N'ArtKuBez2' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtKuBez2], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtKuBez2]) > 100
    UNION ALL
    SELECT N'ArtBez2' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtBez2], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtBez2]) > 200
    UNION ALL
    SELECT N'ArtKuBez3' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtKuBez3], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtKuBez3]) > 100
    UNION ALL
    SELECT N'ArtBez3' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtBez3], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtBez3]) > 200
    UNION ALL
    SELECT N'ArtEinh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEinh], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtEinh]) > 10
    UNION ALL
    SELECT N'ArtMgeFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtMgeFak], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtMgeFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtMgeFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtMgeFak]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtEPreisFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEPreisFak], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEPreisFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEPreisFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEPreisFak]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtGew' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtGew], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGew]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGew]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGew]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtLaenge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtLaenge], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtLaenge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtLaenge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtLaenge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtBreite' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtBreite], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBreite]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBreite]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBreite]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtHoehe' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtHoehe], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHoehe]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHoehe]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHoehe]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtLaengeEinh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtLaengeEinh], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtLaengeEinh]) > 10
    UNION ALL
    SELECT N'ArtInhaltMge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtInhaltMge], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtInhaltMge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtInhaltMge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtInhaltMge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtInhaltEinh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtInhaltEinh], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtInhaltEinh]) > 20
    UNION ALL
    SELECT N'ArtGrPrEinh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtGrPrEinh], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtGrPrEinh]) > 20
    UNION ALL
    SELECT N'ArtStSchl' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtStSchl], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtStSchl]) > 60
    UNION ALL
    SELECT N'ArtStSchlArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtStSchlArt], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStSchlArt]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStSchlArt]), N'')) IS NULL
    UNION ALL
    SELECT N'ArtSktoKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtSktoKz], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtSktoKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtSktoKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'ArtNichtSktoNetBet' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtNichtSktoNetBet], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNichtSktoNetBet]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNichtSktoNetBet]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNichtSktoNetBet]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtStGArtKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtStGArtKz], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStGArtKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStGArtKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'ArtHstAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtHstAdrNr], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHstAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHstAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'ArtHstArtNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtHstArtNr], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtHstArtNr]) > 30
    UNION ALL
    SELECT N'ArtEkMitt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEkMitt], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkMitt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkMitt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkMitt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtEkKalkVgb' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEkKalkVgb], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalkVgb]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalkVgb]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalkVgb]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtEkKalkSchl' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEkKalkSchl], 40)) AS Beispiel FROM stg.Artikel s WHERE LEN(s.[ArtEkKalkSchl]) > 60
    UNION ALL
    SELECT N'ArtEkKalk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEkKalk], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalk]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalk]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalk]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtEkRohVgb' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtEkRohVgb], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkRohVgb]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkRohVgb]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkRohVgb]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk0Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk0Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk0Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk0Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk0Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk1Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk1Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk1Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk1Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk1Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk2Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk2Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk2Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk2Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk2Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk3Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk3Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk3Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk3Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk3Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk4Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk4Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk4Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk4Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk4Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk5Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk5Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk5Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk5Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk5Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk6Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk6Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk6Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk6Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk6Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk7Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk7Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk7Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk7Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk7Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk8Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk8Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk8Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk8Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk8Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVk9Preis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVk9Preis], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk9Preis]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk9Preis]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk9Preis]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'ArtVkDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtVkDat], 40)) AS Beispiel FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVkDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVkDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVkDat]), N''), 104) IS NULL
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'Artikel: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.Artikel s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtArtNr]), N'') IS NULL) THROW 50004, N'Artikel: Datensatz ohne Schlüssel (ArtArtNr).', 1;
  SELECT TOP 1 @msg = CONCAT(N'Artikel: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[ArtArtNr], N'') AS k, COUNT(*) AS n FROM stg.Artikel s GROUP BY ISNULL(s.[ArtArtNr], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.Artikel;
  INSERT INTO dbo.Artikel ([ArtID], [ArtArtNr], [ArtSuchBeg], [ArtArtikelArt], [ArtGspKz], [ArtBarCd], [ArtWgrNr], [ArtWgrNrInfo], [ArtKuBez1], [ArtBez1], [ArtKuBez2], [ArtBez2], [ArtKuBez3], [ArtBez3], [ArtEinh], [ArtMgeFak], [ArtEPreisFak], [ArtGew], [ArtLaenge], [ArtBreite], [ArtHoehe], [ArtLaengeEinh], [ArtInhaltMge], [ArtInhaltEinh], [ArtGrPrEinh], [ArtBeschr], [ArtStSchl], [ArtStSchlArt], [ArtSktoKz], [ArtNichtSktoNetBet], [ArtStGArtKz], [ArtHstAdrNr], [ArtHstArtNr], [ArtEkMitt], [ArtEkKalkVgb], [ArtEkKalkSchl], [ArtEkKalk], [ArtEkRohVgb], [ArtVk0Preis], [ArtVk1Preis], [ArtVk2Preis], [ArtVk3Preis], [ArtVk4Preis], [ArtVk5Preis], [ArtVk6Preis], [ArtVk7Preis], [ArtVk8Preis], [ArtVk9Preis], [ArtVkDat])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtArtNr]), N'') IS NULL THEN NULL ELSE s.[ArtArtNr] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtSuchBeg]), N'') IS NULL THEN NULL ELSE s.[ArtSuchBeg] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtArtikelArt]), N'') IS NULL THEN NULL ELSE s.[ArtArtikelArt] END,
      ISNULL(CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGspKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END, 0),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBarCd]), N'') IS NULL THEN NULL ELSE s.[ArtBarCd] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtWgrNr]), N'') IS NULL THEN NULL ELSE s.[ArtWgrNr] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtWgrNrInfo]), N'') IS NULL THEN NULL ELSE s.[ArtWgrNrInfo] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKuBez1]), N'') IS NULL THEN NULL ELSE s.[ArtKuBez1] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBez1]), N'') IS NULL THEN NULL ELSE s.[ArtBez1] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKuBez2]), N'') IS NULL THEN NULL ELSE s.[ArtKuBez2] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBez2]), N'') IS NULL THEN NULL ELSE s.[ArtBez2] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKuBez3]), N'') IS NULL THEN NULL ELSE s.[ArtKuBez3] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBez3]), N'') IS NULL THEN NULL ELSE s.[ArtBez3] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEinh]), N'') IS NULL THEN NULL ELSE s.[ArtEinh] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtMgeFak]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEPreisFak]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGew]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtLaenge]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBreite]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHoehe]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtLaengeEinh]), N'') IS NULL THEN NULL ELSE s.[ArtLaengeEinh] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtInhaltMge]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtInhaltEinh]), N'') IS NULL THEN NULL ELSE s.[ArtInhaltEinh] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtGrPrEinh]), N'') IS NULL THEN NULL ELSE s.[ArtGrPrEinh] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtBeschr]), N'') IS NULL THEN NULL ELSE s.[ArtBeschr] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStSchl]), N'') IS NULL THEN NULL ELSE s.[ArtStSchl] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStSchlArt]), N'')),
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtSktoKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNichtSktoNetBet]), N''), N'.', N''), N',', N'.')),
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtStGArtKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHstAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtHstArtNr]), N'') IS NULL THEN NULL ELSE s.[ArtHstArtNr] END,
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkMitt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalkVgb]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalkSchl]), N'') IS NULL THEN NULL ELSE s.[ArtEkKalkSchl] END,
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkKalk]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtEkRohVgb]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk0Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk1Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk2Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk3Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk4Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk5Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk6Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk7Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk8Preis]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVk9Preis]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVkDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtVkDat]), N''), 104) END
  FROM stg.Artikel s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'Artikel', @alt, @neu, N'OK', NULL);
END;
GO
IF OBJECT_ID(N'stg.Adressen') IS NOT NULL DROP TABLE stg.Adressen;
CREATE TABLE stg.Adressen (
  [AdrAdrNr] nvarchar(max) NULL,
  [AdrStatus] nvarchar(max) NULL,
  [AdrReNa1] nvarchar(max) NULL,
  [AdrReNa2] nvarchar(max) NULL,
  [AdrReNa3] nvarchar(max) NULL,
  [AdrReStr] nvarchar(max) NULL,
  [AdrReLand] nvarchar(max) NULL,
  [AdrRePLZ] nvarchar(max) NULL,
  [AdrReOrt] nvarchar(max) NULL,
  [AdrReTel] nvarchar(max) NULL,
  [AdrReEMail1] nvarchar(max) NULL,
  [AdrReStdReKz] nvarchar(max) NULL,
  [AdrReStdLiKz] nvarchar(max) NULL,
  [AdrReUStId] nvarchar(max) NULL,
  [AdrReInfo] nvarchar(max) NULL,
  [AdrReGspKz] nvarchar(max) NULL,
  [AdrSel1] nvarchar(max) NULL,
  [AdrVtrNr] nvarchar(max) NULL,
  [AdrBranche] nvarchar(max) NULL,
  [AdrLiAnsNr] nvarchar(max) NULL,
  [AdrReAnsNr] nvarchar(max) NULL,
  [AdrSuchBeg] nvarchar(max) NULL,
  [AdrErstDat] nvarchar(max) NULL,
  [AdrSel2] nvarchar(max) NULL,
  [AdrGspKz] nvarchar(max) NULL,
  [AdrGspDat] nvarchar(max) NULL,
  [AdrGspInfo] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.Adressen') IS NULL
BEGIN
  CREATE TABLE dbo.Adressen (
    [AdrAdrNr] int NOT NULL,
    [AdrStatus] nvarchar(50),
    [AdrReNa1] nvarchar(100),
    [AdrReNa2] nvarchar(100),
    [AdrReNa3] nvarchar(100),
    [AdrReStr] nvarchar(100),
    [AdrReLand] smallint,
    [AdrRePLZ] nvarchar(20),
    [AdrReOrt] nvarchar(60),
    [AdrReTel] nvarchar(50),
    [AdrReEMail1] nvarchar(255),
    [AdrReStdReKz] bit,
    [AdrReStdLiKz] bit,
    [AdrReUStId] nvarchar(30),
    [AdrReInfo] nvarchar(max),
    [AdrReGspKz] bit,
    [AdrSel1] nvarchar(100),
    [AdrVtrNr] int,
    [AdrBranche] nvarchar(60),
    [AdrLiAnsNr] smallint,
    [AdrReAnsNr] smallint,
    [AdrSuchBeg] nvarchar(50),
    [AdrErstDat] datetime2(0),
    [AdrSel2] nvarchar(100),
    [AdrGspKz] bit NOT NULL CONSTRAINT DF_Adressen_AdrGspKz DEFAULT 0,
    [AdrGspDat] date,
    [AdrGspInfo] nvarchar(max),
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_Adressen PRIMARY KEY (AdrAdrNr)
  );
  CREATE INDEX IX_Adressen_AdrVtrNr ON dbo.Adressen(AdrVtrNr);
  CREATE INDEX IX_Adressen_AdrRePLZ ON dbo.Adressen(AdrRePLZ);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_Adressen @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.Adressen prüfen und dbo.Adressen vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.Adressen);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.Adressen);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'Adressen: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'Adressen: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'AdrAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrAdrNr], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AdrStatus' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrStatus], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrStatus]) > 50
    UNION ALL
    SELECT N'AdrReNa1' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReNa1], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReNa1]) > 100
    UNION ALL
    SELECT N'AdrReNa2' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReNa2], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReNa2]) > 100
    UNION ALL
    SELECT N'AdrReNa3' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReNa3], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReNa3]) > 100
    UNION ALL
    SELECT N'AdrReStr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReStr], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReStr]) > 100
    UNION ALL
    SELECT N'AdrReLand' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReLand], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReLand]), N'') IS NOT NULL AND TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReLand]), N'')) IS NULL
    UNION ALL
    SELECT N'AdrRePLZ' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrRePLZ], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrRePLZ]) > 20
    UNION ALL
    SELECT N'AdrReOrt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReOrt], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReOrt]) > 60
    UNION ALL
    SELECT N'AdrReTel' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReTel], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReTel]) > 50
    UNION ALL
    SELECT N'AdrReEMail1' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReEMail1], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReEMail1]) > 255
    UNION ALL
    SELECT N'AdrReStdReKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReStdReKz], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdReKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdReKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AdrReStdLiKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReStdLiKz], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdLiKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdLiKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AdrReUStId' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReUStId], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrReUStId]) > 30
    UNION ALL
    SELECT N'AdrReGspKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReGspKz], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReGspKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReGspKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AdrSel1' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrSel1], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrSel1]) > 100
    UNION ALL
    SELECT N'AdrVtrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrVtrNr], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrVtrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrVtrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AdrBranche' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrBranche], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrBranche]) > 60
    UNION ALL
    SELECT N'AdrLiAnsNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrLiAnsNr], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrLiAnsNr]), N'') IS NOT NULL AND TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrLiAnsNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AdrReAnsNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrReAnsNr], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReAnsNr]), N'') IS NOT NULL AND TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReAnsNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AdrSuchBeg' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrSuchBeg], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrSuchBeg]) > 50
    UNION ALL
    SELECT N'AdrErstDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrErstDat], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrErstDat]), N'') IS NOT NULL AND TRY_CONVERT(datetime2(0), NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrErstDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'AdrSel2' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrSel2], 40)) AS Beispiel FROM stg.Adressen s WHERE LEN(s.[AdrSel2]) > 100
    UNION ALL
    SELECT N'AdrGspKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrGspKz], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AdrGspDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AdrGspDat], 40)) AS Beispiel FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspDat]), N''), 104) IS NULL
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'Adressen: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.Adressen s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrAdrNr]), N'') IS NULL) THROW 50004, N'Adressen: Datensatz ohne Schlüssel (AdrAdrNr).', 1;
  SELECT TOP 1 @msg = CONCAT(N'Adressen: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[AdrAdrNr], N'') AS k, COUNT(*) AS n FROM stg.Adressen s GROUP BY ISNULL(s.[AdrAdrNr], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.Adressen;
  INSERT INTO dbo.Adressen ([AdrAdrNr], [AdrStatus], [AdrReNa1], [AdrReNa2], [AdrReNa3], [AdrReStr], [AdrReLand], [AdrRePLZ], [AdrReOrt], [AdrReTel], [AdrReEMail1], [AdrReStdReKz], [AdrReStdLiKz], [AdrReUStId], [AdrReInfo], [AdrReGspKz], [AdrSel1], [AdrVtrNr], [AdrBranche], [AdrLiAnsNr], [AdrReAnsNr], [AdrSuchBeg], [AdrErstDat], [AdrSel2], [AdrGspKz], [AdrGspDat], [AdrGspInfo])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrStatus]), N'') IS NULL THEN NULL ELSE s.[AdrStatus] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReNa1]), N'') IS NULL THEN NULL ELSE s.[AdrReNa1] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReNa2]), N'') IS NULL THEN NULL ELSE s.[AdrReNa2] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReNa3]), N'') IS NULL THEN NULL ELSE s.[AdrReNa3] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStr]), N'') IS NULL THEN NULL ELSE s.[AdrReStr] END,
      TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReLand]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrRePLZ]), N'') IS NULL THEN NULL ELSE s.[AdrRePLZ] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReOrt]), N'') IS NULL THEN NULL ELSE s.[AdrReOrt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReTel]), N'') IS NULL THEN NULL ELSE s.[AdrReTel] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReEMail1]), N'') IS NULL THEN NULL ELSE s.[AdrReEMail1] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdReKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReStdLiKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReUStId]), N'') IS NULL THEN NULL ELSE s.[AdrReUStId] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReInfo]), N'') IS NULL THEN NULL ELSE s.[AdrReInfo] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReGspKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrSel1]), N'') IS NULL THEN NULL ELSE s.[AdrSel1] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrVtrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrBranche]), N'') IS NULL THEN NULL ELSE s.[AdrBranche] END,
      TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrLiAnsNr]), N'')),
      TRY_CONVERT(smallint, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrReAnsNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrSuchBeg]), N'') IS NULL THEN NULL ELSE s.[AdrSuchBeg] END,
      TRY_CONVERT(datetime2(0), NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrErstDat]), N''), 104),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrSel2]), N'') IS NULL THEN NULL ELSE s.[AdrSel2] END,
      ISNULL(CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END, 0),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspDat]), N''), 104) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AdrGspInfo]), N'') IS NULL THEN NULL ELSE s.[AdrGspInfo] END
  FROM stg.Adressen s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'Adressen', @alt, @neu, N'OK', NULL);
END;
GO
IF OBJECT_ID(N'stg.Vorgang') IS NOT NULL DROP TABLE stg.Vorgang;
CREATE TABLE stg.Vorgang (
  [VogID] nvarchar(max) NULL,
  [VogBelegNr] nvarchar(max) NULL,
  [VogAdrNr] nvarchar(max) NULL,
  [VogArt] nvarchar(max) NULL,
  [VogVerk] nvarchar(max) NULL,
  [VogVtrNr] nvarchar(max) NULL,
  [VogVtrProvSz] nvarchar(max) NULL,
  [VogBez] nvarchar(max) NULL,
  [VogGspKz] nvarchar(max) NULL,
  [VogGebuchtKz] nvarchar(max) NULL,
  [VogStorniertKz] nvarchar(max) NULL,
  [VogDat] nvarchar(max) NULL,
  [VogZahlBed] nvarchar(max) NULL,
  [VogZahlArt] nvarchar(max) NULL,
  [VogGGew] nvarchar(max) NULL,
  [VogGPreisNt] nvarchar(max) NULL,
  [VogGPreisSt] nvarchar(max) NULL,
  [VogGPreisBt] nvarchar(max) NULL,
  [VogGEkKalk] nvarchar(max) NULL,
  [VogGEkRoh] nvarchar(max) NULL,
  [VogReILN] nvarchar(max) NULL,
  [VogLiAnsVwKz] nvarchar(max) NULL,
  [VogLiAdrNr] nvarchar(max) NULL,
  [VogLiefDat] nvarchar(max) NULL,
  [VogKdBezBet] nvarchar(max) NULL,
  [VogToArt] nvarchar(max) NULL,
  [VogLtzArt] nvarchar(max) NULL,
  [VogDreiGsKz] nvarchar(max) NULL,
  [VogVsdArt] nvarchar(max) NULL,
  [VogVsdZWeise] nvarchar(max) NULL,
  [VogLiefBed] nvarchar(max) NULL,
  [VogKdLiefNr] nvarchar(max) NULL,
  [VogBKtoNr] nvarchar(max) NULL,
  [VogStGeschKz] nvarchar(max) NULL,
  [VogRBetPrNaKz] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.Vorgang') IS NULL
BEGIN
  CREATE TABLE dbo.Vorgang (
    [VogID] int NOT NULL,
    [VogBelegNr] nvarchar(20),
    [VogAdrNr] int,
    [VogArt] nvarchar(40),
    [VogVerk] nvarchar(10),
    [VogVtrNr] int,
    [VogVtrProvSz] decimal(6,2),
    [VogBez] nvarchar(200),
    [VogGspKz] bit,
    [VogGebuchtKz] bit,
    [VogStorniertKz] bit,
    [VogDat] date,
    [VogZahlBed] nvarchar(200),
    [VogZahlArt] nvarchar(100),
    [VogGGew] decimal(18,3),
    [VogGPreisNt] decimal(14,2),
    [VogGPreisSt] decimal(14,2),
    [VogGPreisBt] decimal(14,2),
    [VogGEkKalk] decimal(14,2),
    [VogGEkRoh] decimal(14,2),
    [VogReILN] nvarchar(20),
    [VogLiAnsVwKz] bit,
    [VogLiAdrNr] int,
    [VogLiefDat] date,
    [VogKdBezBet] decimal(14,2),
    [VogToArt] nvarchar(40),
    [VogLtzArt] nvarchar(40),
    [VogDreiGsKz] bit,
    [VogVsdArt] nvarchar(60),
    [VogVsdZWeise] nvarchar(60),
    [VogLiefBed] nvarchar(200),
    [VogKdLiefNr] nvarchar(30),
    [VogBKtoNr] nvarchar(20),
    [VogStGeschKz] bit,
    [VogRBetPrNaKz] bit,
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_Vorgang PRIMARY KEY (VogID)
  );
  CREATE INDEX IX_Vorgang_VogAdrNr ON dbo.Vorgang(VogAdrNr);
  CREATE INDEX IX_Vorgang_VogDat ON dbo.Vorgang(VogDat);
  CREATE INDEX IX_Vorgang_VogArt ON dbo.Vorgang(VogArt);
  CREATE INDEX IX_Vorgang_VogBelegNr ON dbo.Vorgang(VogBelegNr);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_Vorgang @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.Vorgang prüfen und dbo.Vorgang vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.Vorgang);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.Vorgang);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'Vorgang: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'Vorgang: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'VogID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogID], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')) IS NULL
    UNION ALL
    SELECT N'VogBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBelegNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogBelegNr]) > 20
    UNION ALL
    SELECT N'VogAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogAdrNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogArt], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogArt]) > 40
    UNION ALL
    SELECT N'VogVerk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVerk], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogVerk]) > 10
    UNION ALL
    SELECT N'VogVtrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVtrNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogVtrProvSz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVtrProvSz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(6,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogBez' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBez], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogBez]) > 200
    UNION ALL
    SELECT N'VogGspKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGspKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogGebuchtKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGebuchtKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogStorniertKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogStorniertKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogDat], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'VogZahlBed' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogZahlBed], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogZahlBed]) > 200
    UNION ALL
    SELECT N'VogZahlArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogZahlArt], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogZahlArt]) > 100
    UNION ALL
    SELECT N'VogGGew' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGGew], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,3), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisNt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisNt], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisSt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisSt], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisBt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisBt], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGEkKalk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGEkKalk], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGEkRoh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGEkRoh], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogReILN' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogReILN], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogReILN]) > 20
    UNION ALL
    SELECT N'VogLiAnsVwKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiAnsVwKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogLiAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiAdrNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogLiefDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiefDat], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'VogKdBezBet' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogKdBezBet], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogToArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogToArt], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogToArt]) > 40
    UNION ALL
    SELECT N'VogLtzArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLtzArt], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogLtzArt]) > 40
    UNION ALL
    SELECT N'VogDreiGsKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogDreiGsKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogVsdArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVsdArt], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogVsdArt]) > 60
    UNION ALL
    SELECT N'VogVsdZWeise' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVsdZWeise], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogVsdZWeise]) > 60
    UNION ALL
    SELECT N'VogLiefBed' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiefBed], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogLiefBed]) > 200
    UNION ALL
    SELECT N'VogKdLiefNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogKdLiefNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogKdLiefNr]) > 30
    UNION ALL
    SELECT N'VogBKtoNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBKtoNr], 40)) AS Beispiel FROM stg.Vorgang s WHERE LEN(s.[VogBKtoNr]) > 20
    UNION ALL
    SELECT N'VogStGeschKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogStGeschKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogRBetPrNaKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogRBetPrNaKz], 40)) AS Beispiel FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') NOT IN (N'Ja', N'Nein')
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'Vorgang: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.Vorgang s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NULL) THROW 50004, N'Vorgang: Datensatz ohne Schlüssel (VogID).', 1;
  SELECT TOP 1 @msg = CONCAT(N'Vorgang: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[VogID], N'') AS k, COUNT(*) AS n FROM stg.Vorgang s GROUP BY ISNULL(s.[VogID], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.Vorgang;
  INSERT INTO dbo.Vorgang ([VogID], [VogBelegNr], [VogAdrNr], [VogArt], [VogVerk], [VogVtrNr], [VogVtrProvSz], [VogBez], [VogGspKz], [VogGebuchtKz], [VogStorniertKz], [VogDat], [VogZahlBed], [VogZahlArt], [VogGGew], [VogGPreisNt], [VogGPreisSt], [VogGPreisBt], [VogGEkKalk], [VogGEkRoh], [VogReILN], [VogLiAnsVwKz], [VogLiAdrNr], [VogLiefDat], [VogKdBezBet], [VogToArt], [VogLtzArt], [VogDreiGsKz], [VogVsdArt], [VogVsdZWeise], [VogLiefBed], [VogKdLiefNr], [VogBKtoNr], [VogStGeschKz], [VogRBetPrNaKz])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBelegNr]), N'') IS NULL THEN NULL ELSE s.[VogBelegNr] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogArt]), N'') IS NULL THEN NULL ELSE s.[VogArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVerk]), N'') IS NULL THEN NULL ELSE s.[VogVerk] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'')),
      TRY_CONVERT(decimal(6,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBez]), N'') IS NULL THEN NULL ELSE s.[VogBez] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N''), 104) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogZahlBed]), N'') IS NULL THEN NULL ELSE s.[VogZahlBed] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogZahlArt]), N'') IS NULL THEN NULL ELSE s.[VogZahlArt] END,
      TRY_CONVERT(decimal(18,3), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogReILN]), N'') IS NULL THEN NULL ELSE s.[VogReILN] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N''), 104) END,
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogToArt]), N'') IS NULL THEN NULL ELSE s.[VogToArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLtzArt]), N'') IS NULL THEN NULL ELSE s.[VogLtzArt] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVsdArt]), N'') IS NULL THEN NULL ELSE s.[VogVsdArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVsdZWeise]), N'') IS NULL THEN NULL ELSE s.[VogVsdZWeise] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefBed]), N'') IS NULL THEN NULL ELSE s.[VogLiefBed] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdLiefNr]), N'') IS NULL THEN NULL ELSE s.[VogKdLiefNr] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBKtoNr]), N'') IS NULL THEN NULL ELSE s.[VogBKtoNr] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END
  FROM stg.Vorgang s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'Vorgang', @alt, @neu, N'OK', NULL);
END;
GO
IF OBJECT_ID(N'stg.VorgangArchiv') IS NOT NULL DROP TABLE stg.VorgangArchiv;
CREATE TABLE stg.VorgangArchiv (
  [VogID] nvarchar(max) NULL,
  [VogBelegNr] nvarchar(max) NULL,
  [VogAdrNr] nvarchar(max) NULL,
  [VogArt] nvarchar(max) NULL,
  [VogVerk] nvarchar(max) NULL,
  [VogVtrNr] nvarchar(max) NULL,
  [VogVtrProvSz] nvarchar(max) NULL,
  [VogBez] nvarchar(max) NULL,
  [VogGspKz] nvarchar(max) NULL,
  [VogGebuchtKz] nvarchar(max) NULL,
  [VogStorniertKz] nvarchar(max) NULL,
  [VogDat] nvarchar(max) NULL,
  [VogZahlBed] nvarchar(max) NULL,
  [VogZahlArt] nvarchar(max) NULL,
  [VogGGew] nvarchar(max) NULL,
  [VogGPreisNt] nvarchar(max) NULL,
  [VogGPreisSt] nvarchar(max) NULL,
  [VogGPreisBt] nvarchar(max) NULL,
  [VogGEkKalk] nvarchar(max) NULL,
  [VogGEkRoh] nvarchar(max) NULL,
  [VogReILN] nvarchar(max) NULL,
  [VogLiAnsVwKz] nvarchar(max) NULL,
  [VogLiAdrNr] nvarchar(max) NULL,
  [VogLiefDat] nvarchar(max) NULL,
  [VogKdBezBet] nvarchar(max) NULL,
  [VogToArt] nvarchar(max) NULL,
  [VogLtzArt] nvarchar(max) NULL,
  [VogDreiGsKz] nvarchar(max) NULL,
  [VogVsdArt] nvarchar(max) NULL,
  [VogVsdZWeise] nvarchar(max) NULL,
  [VogLiefBed] nvarchar(max) NULL,
  [VogKdLiefNr] nvarchar(max) NULL,
  [VogBKtoNr] nvarchar(max) NULL,
  [VogStGeschKz] nvarchar(max) NULL,
  [VogRBetPrNaKz] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.VorgangArchiv') IS NULL
BEGIN
  CREATE TABLE dbo.VorgangArchiv (
    [VogID] int NOT NULL,
    [VogBelegNr] nvarchar(20),
    [VogAdrNr] int,
    [VogArt] nvarchar(40),
    [VogVerk] nvarchar(10),
    [VogVtrNr] int,
    [VogVtrProvSz] decimal(6,2),
    [VogBez] nvarchar(200),
    [VogGspKz] bit,
    [VogGebuchtKz] bit,
    [VogStorniertKz] bit,
    [VogDat] date,
    [VogZahlBed] nvarchar(200),
    [VogZahlArt] nvarchar(100),
    [VogGGew] decimal(18,3),
    [VogGPreisNt] decimal(14,2),
    [VogGPreisSt] decimal(14,2),
    [VogGPreisBt] decimal(14,2),
    [VogGEkKalk] decimal(14,2),
    [VogGEkRoh] decimal(14,2),
    [VogReILN] nvarchar(20),
    [VogLiAnsVwKz] bit,
    [VogLiAdrNr] int,
    [VogLiefDat] date,
    [VogKdBezBet] decimal(14,2),
    [VogToArt] nvarchar(40),
    [VogLtzArt] nvarchar(40),
    [VogDreiGsKz] bit,
    [VogVsdArt] nvarchar(60),
    [VogVsdZWeise] nvarchar(60),
    [VogLiefBed] nvarchar(200),
    [VogKdLiefNr] nvarchar(30),
    [VogBKtoNr] nvarchar(20),
    [VogStGeschKz] bit,
    [VogRBetPrNaKz] bit,
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_VorgangArchiv PRIMARY KEY (VogID)
  );
  CREATE INDEX IX_VorgangArchiv_VogAdrNr ON dbo.VorgangArchiv(VogAdrNr);
  CREATE INDEX IX_VorgangArchiv_VogDat ON dbo.VorgangArchiv(VogDat);
  CREATE INDEX IX_VorgangArchiv_VogArt ON dbo.VorgangArchiv(VogArt);
  CREATE INDEX IX_VorgangArchiv_VogBelegNr ON dbo.VorgangArchiv(VogBelegNr);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_VorgangArchiv @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.VorgangArchiv prüfen und dbo.VorgangArchiv vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.VorgangArchiv);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.VorgangArchiv);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'VorgangArchiv: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'VorgangArchiv: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'VogID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogID], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')) IS NULL
    UNION ALL
    SELECT N'VogBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBelegNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogBelegNr]) > 20
    UNION ALL
    SELECT N'VogAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogAdrNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogArt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogArt]) > 40
    UNION ALL
    SELECT N'VogVerk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVerk], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogVerk]) > 10
    UNION ALL
    SELECT N'VogVtrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVtrNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogVtrProvSz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVtrProvSz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(6,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogBez' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBez], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogBez]) > 200
    UNION ALL
    SELECT N'VogGspKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGspKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogGebuchtKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGebuchtKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogStorniertKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogStorniertKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogDat], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'VogZahlBed' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogZahlBed], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogZahlBed]) > 200
    UNION ALL
    SELECT N'VogZahlArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogZahlArt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogZahlArt]) > 100
    UNION ALL
    SELECT N'VogGGew' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGGew], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,3), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisNt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisNt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisSt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisSt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGPreisBt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGPreisBt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGEkKalk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGEkKalk], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogGEkRoh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogGEkRoh], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogReILN' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogReILN], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogReILN]) > 20
    UNION ALL
    SELECT N'VogLiAnsVwKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiAnsVwKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogLiAdrNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiAdrNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'')) IS NULL
    UNION ALL
    SELECT N'VogLiefDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiefDat], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'VogKdBezBet' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogKdBezBet], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'VogToArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogToArt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogToArt]) > 40
    UNION ALL
    SELECT N'VogLtzArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLtzArt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogLtzArt]) > 40
    UNION ALL
    SELECT N'VogDreiGsKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogDreiGsKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogVsdArt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVsdArt], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogVsdArt]) > 60
    UNION ALL
    SELECT N'VogVsdZWeise' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogVsdZWeise], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogVsdZWeise]) > 60
    UNION ALL
    SELECT N'VogLiefBed' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogLiefBed], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogLiefBed]) > 200
    UNION ALL
    SELECT N'VogKdLiefNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogKdLiefNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogKdLiefNr]) > 30
    UNION ALL
    SELECT N'VogBKtoNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBKtoNr], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE LEN(s.[VogBKtoNr]) > 20
    UNION ALL
    SELECT N'VogStGeschKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogStGeschKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'VogRBetPrNaKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogRBetPrNaKz], 40)) AS Beispiel FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') NOT IN (N'Ja', N'Nein')
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'VorgangArchiv: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.VorgangArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NULL) THROW 50004, N'VorgangArchiv: Datensatz ohne Schlüssel (VogID).', 1;
  SELECT TOP 1 @msg = CONCAT(N'VorgangArchiv: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[VogID], N'') AS k, COUNT(*) AS n FROM stg.VorgangArchiv s GROUP BY ISNULL(s.[VogID], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.VorgangArchiv;
  INSERT INTO dbo.VorgangArchiv ([VogID], [VogBelegNr], [VogAdrNr], [VogArt], [VogVerk], [VogVtrNr], [VogVtrProvSz], [VogBez], [VogGspKz], [VogGebuchtKz], [VogStorniertKz], [VogDat], [VogZahlBed], [VogZahlArt], [VogGGew], [VogGPreisNt], [VogGPreisSt], [VogGPreisBt], [VogGEkKalk], [VogGEkRoh], [VogReILN], [VogLiAnsVwKz], [VogLiAdrNr], [VogLiefDat], [VogKdBezBet], [VogToArt], [VogLtzArt], [VogDreiGsKz], [VogVsdArt], [VogVsdZWeise], [VogLiefBed], [VogKdLiefNr], [VogBKtoNr], [VogStGeschKz], [VogRBetPrNaKz])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBelegNr]), N'') IS NULL THEN NULL ELSE s.[VogBelegNr] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogArt]), N'') IS NULL THEN NULL ELSE s.[VogArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVerk]), N'') IS NULL THEN NULL ELSE s.[VogVerk] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrNr]), N'')),
      TRY_CONVERT(decimal(6,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVtrProvSz]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBez]), N'') IS NULL THEN NULL ELSE s.[VogBez] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGspKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGebuchtKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStorniertKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDat]), N''), 104) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogZahlBed]), N'') IS NULL THEN NULL ELSE s.[VogZahlBed] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogZahlArt]), N'') IS NULL THEN NULL ELSE s.[VogZahlArt] END,
      TRY_CONVERT(decimal(18,3), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGGew]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisNt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisSt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGPreisBt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkKalk]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogGEkRoh]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogReILN]), N'') IS NULL THEN NULL ELSE s.[VogReILN] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAnsVwKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiAdrNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefDat]), N''), 104) END,
      TRY_CONVERT(decimal(14,2), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdBezBet]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogToArt]), N'') IS NULL THEN NULL ELSE s.[VogToArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLtzArt]), N'') IS NULL THEN NULL ELSE s.[VogLtzArt] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogDreiGsKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVsdArt]), N'') IS NULL THEN NULL ELSE s.[VogVsdArt] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogVsdZWeise]), N'') IS NULL THEN NULL ELSE s.[VogVsdZWeise] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogLiefBed]), N'') IS NULL THEN NULL ELSE s.[VogLiefBed] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogKdLiefNr]), N'') IS NULL THEN NULL ELSE s.[VogKdLiefNr] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBKtoNr]), N'') IS NULL THEN NULL ELSE s.[VogBKtoNr] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogStGeschKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogRBetPrNaKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END
  FROM stg.VorgangArchiv s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'VorgangArchiv', @alt, @neu, N'OK', NULL);
END;
GO
IF OBJECT_ID(N'stg.VorgangPosition') IS NOT NULL DROP TABLE stg.VorgangPosition;
CREATE TABLE stg.VorgangPosition (
  [VogID] nvarchar(max) NULL,
  [VogBelegNr] nvarchar(max) NULL,
  [IntBelegNr] nvarchar(max) NULL,
  [ZeilenNr] nvarchar(max) NULL,
  [BelegPosNr] nvarchar(max) NULL,
  [AusblendenKz] nvarchar(max) NULL,
  [AbrPosKz] nvarchar(max) NULL,
  [PosNr] nvarchar(max) NULL,
  [TitelNr] nvarchar(max) NULL,
  [Pos] nvarchar(max) NULL,
  [ArtNr] nvarchar(max) NULL,
  [ArtKz] nvarchar(max) NULL,
  [HatZusKz] nvarchar(max) NULL,
  [IstZusKz] nvarchar(max) NULL,
  [AZusID] nvarchar(max) NULL,
  [Einh] nvarchar(max) NULL,
  [Mge] nvarchar(max) NULL,
  [MgeFak] nvarchar(max) NULL,
  [BuchMge] nvarchar(max) NULL,
  [LiefMge] nvarchar(max) NULL,
  [LiefDat] nvarchar(max) NULL,
  [LeistDat] nvarchar(max) NULL,
  [EEkKalk] nvarchar(max) NULL,
  [EEkRoh] nvarchar(max) NULL,
  [EPreisOMf] nvarchar(max) NULL,
  [EPrNt] nvarchar(max) NULL,
  [EPrSt] nvarchar(max) NULL,
  [EPrBt] nvarchar(max) NULL,
  [EPreis] nvarchar(max) NULL,
  [EPreisFak] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.VorgangPosition') IS NULL
BEGIN
  CREATE TABLE dbo.VorgangPosition (
    [VogID] int NOT NULL,
    [VogBelegNr] nvarchar(20),
    [IntBelegNr] int,
    [ZeilenNr] int NOT NULL,
    [BelegPosNr] int,
    [AusblendenKz] bit,
    [AbrPosKz] bit,
    [PosNr] int,
    [TitelNr] int,
    [Pos] nvarchar(20),
    [ArtNr] nvarchar(30),
    [ArtKz] bit,
    [HatZusKz] bit,
    [IstZusKz] bit,
    [AZusID] int,
    [Einh] nvarchar(10),
    [Mge] decimal(18,4),
    [MgeFak] decimal(18,4),
    [BuchMge] decimal(18,4),
    [LiefMge] decimal(18,4),
    [LiefDat] date,
    [LeistDat] date,
    [EEkKalk] decimal(18,4),
    [EEkRoh] decimal(18,4),
    [EPreisOMf] nvarchar(40),
    [EPrNt] decimal(18,4),
    [EPrSt] decimal(18,4),
    [EPrBt] decimal(18,4),
    [EPreis] nvarchar(40),
    [EPreisFak] decimal(9,4),
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_VorgangPosition PRIMARY KEY (VogID, ZeilenNr)
  );
  CREATE INDEX IX_VorgangPosition_ArtNr ON dbo.VorgangPosition(ArtNr);
  CREATE INDEX IX_VorgangPosition_VogBelegNr ON dbo.VorgangPosition(VogBelegNr);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_VorgangPosition @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.VorgangPosition prüfen und dbo.VorgangPosition vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.VorgangPosition);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.VorgangPosition);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'VorgangPosition: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'VorgangPosition: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'VogID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogID], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')) IS NULL
    UNION ALL
    SELECT N'VogBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBelegNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[VogBelegNr]) > 20
    UNION ALL
    SELECT N'IntBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[IntBelegNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'')) IS NULL
    UNION ALL
    SELECT N'ZeilenNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ZeilenNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'')) IS NULL
    UNION ALL
    SELECT N'BelegPosNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[BelegPosNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AusblendenKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AusblendenKz], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AbrPosKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AbrPosKz], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'PosNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[PosNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'')) IS NULL
    UNION ALL
    SELECT N'TitelNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[TitelNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'')) IS NULL
    UNION ALL
    SELECT N'Pos' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Pos], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[Pos]) > 20
    UNION ALL
    SELECT N'ArtNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtNr], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[ArtNr]) > 30
    UNION ALL
    SELECT N'ArtKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtKz], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'HatZusKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[HatZusKz], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'IstZusKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[IstZusKz], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AZusID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AZusID], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'')) IS NULL
    UNION ALL
    SELECT N'Einh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Einh], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[Einh]) > 10
    UNION ALL
    SELECT N'Mge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Mge], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'MgeFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[MgeFak], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'BuchMge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[BuchMge], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'LiefMge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LiefMge], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'LiefDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LiefDat], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'LeistDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LeistDat], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'EEkKalk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EEkKalk], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EEkRoh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EEkRoh], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPreisOMf' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreisOMf], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[EPreisOMf]) > 40
    UNION ALL
    SELECT N'EPrNt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrNt], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPrSt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrSt], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPrBt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrBt], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPreis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreis], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE LEN(s.[EPreis]) > 40
    UNION ALL
    SELECT N'EPreisFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreisFak], 40)) AS Beispiel FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N'') LIKE N'%[^0-9.,-]%')
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'VorgangPosition: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.VorgangPosition s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'') IS NULL) THROW 50004, N'VorgangPosition: Datensatz ohne Schlüssel (VogID, ZeilenNr).', 1;
  SELECT TOP 1 @msg = CONCAT(N'VorgangPosition: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[VogID], N'') + N'|' + ISNULL(s.[ZeilenNr], N'') AS k, COUNT(*) AS n FROM stg.VorgangPosition s GROUP BY ISNULL(s.[VogID], N'') + N'|' + ISNULL(s.[ZeilenNr], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.VorgangPosition;
  INSERT INTO dbo.VorgangPosition ([VogID], [VogBelegNr], [IntBelegNr], [ZeilenNr], [BelegPosNr], [AusblendenKz], [AbrPosKz], [PosNr], [TitelNr], [Pos], [ArtNr], [ArtKz], [HatZusKz], [IstZusKz], [AZusID], [Einh], [Mge], [MgeFak], [BuchMge], [LiefMge], [LiefDat], [LeistDat], [EEkKalk], [EEkRoh], [EPreisOMf], [EPrNt], [EPrSt], [EPrBt], [EPreis], [EPreisFak])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBelegNr]), N'') IS NULL THEN NULL ELSE s.[VogBelegNr] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'')),
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Pos]), N'') IS NULL THEN NULL ELSE s.[Pos] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNr]), N'') IS NULL THEN NULL ELSE s.[ArtNr] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Einh]), N'') IS NULL THEN NULL ELSE s.[Einh] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N''), 104) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N''), 104) END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisOMf]), N'') IS NULL THEN NULL ELSE s.[EPreisOMf] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreis]), N'') IS NULL THEN NULL ELSE s.[EPreis] END,
      TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N''), N'.', N''), N',', N'.'))
  FROM stg.VorgangPosition s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'VorgangPosition', @alt, @neu, N'OK', NULL);
END;
GO
IF OBJECT_ID(N'stg.VorgangPositionArchiv') IS NOT NULL DROP TABLE stg.VorgangPositionArchiv;
CREATE TABLE stg.VorgangPositionArchiv (
  [VogID] nvarchar(max) NULL,
  [VogBelegNr] nvarchar(max) NULL,
  [IntBelegNr] nvarchar(max) NULL,
  [ZeilenNr] nvarchar(max) NULL,
  [BelegPosNr] nvarchar(max) NULL,
  [AusblendenKz] nvarchar(max) NULL,
  [AbrPosKz] nvarchar(max) NULL,
  [PosNr] nvarchar(max) NULL,
  [TitelNr] nvarchar(max) NULL,
  [Pos] nvarchar(max) NULL,
  [ArtNr] nvarchar(max) NULL,
  [ArtKz] nvarchar(max) NULL,
  [HatZusKz] nvarchar(max) NULL,
  [IstZusKz] nvarchar(max) NULL,
  [AZusID] nvarchar(max) NULL,
  [Einh] nvarchar(max) NULL,
  [Mge] nvarchar(max) NULL,
  [MgeFak] nvarchar(max) NULL,
  [BuchMge] nvarchar(max) NULL,
  [LiefMge] nvarchar(max) NULL,
  [LiefDat] nvarchar(max) NULL,
  [LeistDat] nvarchar(max) NULL,
  [EEkKalk] nvarchar(max) NULL,
  [EEkRoh] nvarchar(max) NULL,
  [EPreisOMf] nvarchar(max) NULL,
  [EPrNt] nvarchar(max) NULL,
  [EPrSt] nvarchar(max) NULL,
  [EPrBt] nvarchar(max) NULL,
  [EPreis] nvarchar(max) NULL,
  [EPreisFak] nvarchar(max) NULL
);
GO
IF OBJECT_ID(N'dbo.VorgangPositionArchiv') IS NULL
BEGIN
  CREATE TABLE dbo.VorgangPositionArchiv (
    [VogID] int NOT NULL,
    [VogBelegNr] nvarchar(20),
    [IntBelegNr] int,
    [ZeilenNr] int NOT NULL,
    [BelegPosNr] int,
    [AusblendenKz] bit,
    [AbrPosKz] bit,
    [PosNr] int,
    [TitelNr] int,
    [Pos] nvarchar(20),
    [ArtNr] nvarchar(30),
    [ArtKz] bit,
    [HatZusKz] bit,
    [IstZusKz] bit,
    [AZusID] int,
    [Einh] nvarchar(10),
    [Mge] decimal(18,4),
    [MgeFak] decimal(18,4),
    [BuchMge] decimal(18,4),
    [LiefMge] decimal(18,4),
    [LiefDat] date,
    [LeistDat] date,
    [EEkKalk] decimal(18,4),
    [EEkRoh] decimal(18,4),
    [EPreisOMf] nvarchar(40),
    [EPrNt] decimal(18,4),
    [EPrSt] decimal(18,4),
    [EPrBt] decimal(18,4),
    [EPreis] nvarchar(40),
    [EPreisFak] decimal(9,4),
    ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT PK_VorgangPositionArchiv PRIMARY KEY (VogID, ZeilenNr)
  );
  CREATE INDEX IX_VorgangPositionArchiv_ArtNr ON dbo.VorgangPositionArchiv(ArtNr);
  CREATE INDEX IX_VorgangPositionArchiv_VogBelegNr ON dbo.VorgangPositionArchiv(VogBelegNr);
END
GO
CREATE OR ALTER PROCEDURE dbo.bp_Lade_VorgangPositionArchiv @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.VorgangPositionArchiv prüfen und dbo.VorgangPositionArchiv vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.VorgangPositionArchiv);
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.VorgangPositionArchiv);
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'VorgangPositionArchiv: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'VorgangPositionArchiv: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
    SELECT N'VogID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogID], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')) IS NULL
    UNION ALL
    SELECT N'VogBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[VogBelegNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[VogBelegNr]) > 20
    UNION ALL
    SELECT N'IntBelegNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[IntBelegNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'')) IS NULL
    UNION ALL
    SELECT N'ZeilenNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ZeilenNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'')) IS NULL
    UNION ALL
    SELECT N'BelegPosNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[BelegPosNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'')) IS NULL
    UNION ALL
    SELECT N'AusblendenKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AusblendenKz], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AbrPosKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AbrPosKz], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'PosNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[PosNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'')) IS NULL
    UNION ALL
    SELECT N'TitelNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[TitelNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'')) IS NULL
    UNION ALL
    SELECT N'Pos' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Pos], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[Pos]) > 20
    UNION ALL
    SELECT N'ArtNr' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtNr], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[ArtNr]) > 30
    UNION ALL
    SELECT N'ArtKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[ArtKz], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'HatZusKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[HatZusKz], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'IstZusKz' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[IstZusKz], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') NOT IN (N'Ja', N'Nein')
    UNION ALL
    SELECT N'AZusID' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[AZusID], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'') IS NOT NULL AND TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'')) IS NULL
    UNION ALL
    SELECT N'Einh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Einh], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[Einh]) > 10
    UNION ALL
    SELECT N'Mge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[Mge], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'MgeFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[MgeFak], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'BuchMge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[BuchMge], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'LiefMge' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LiefMge], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'LiefDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LiefDat], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'LeistDat' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[LeistDat], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') IS NOT NULL AND NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') <> N'30.12.1899' AND TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N''), 104) IS NULL
    UNION ALL
    SELECT N'EEkKalk' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EEkKalk], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EEkRoh' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EEkRoh], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPreisOMf' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreisOMf], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[EPreisOMf]) > 40
    UNION ALL
    SELECT N'EPrNt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrNt], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPrSt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrSt], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPrBt' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPrBt], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N'') LIKE N'%[^0-9.,-]%')
    UNION ALL
    SELECT N'EPreis' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreis], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE LEN(s.[EPreis]) > 40
    UNION ALL
    SELECT N'EPreisFak' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[EPreisFak], 40)) AS Beispiel FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N'') IS NOT NULL AND (TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N''), N'.', N''), N',', N'.')) IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N'') LIKE N'%[^0-9.,-]%')
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'VorgangPositionArchiv: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.VorgangPositionArchiv s WHERE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'') IS NULL OR NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'') IS NULL) THROW 50004, N'VorgangPositionArchiv: Datensatz ohne Schlüssel (VogID, ZeilenNr).', 1;
  SELECT TOP 1 @msg = CONCAT(N'VorgangPositionArchiv: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT ISNULL(s.[VogID], N'') + N'|' + ISNULL(s.[ZeilenNr], N'') AS k, COUNT(*) AS n FROM stg.VorgangPositionArchiv s GROUP BY ISNULL(s.[VogID], N'') + N'|' + ISNULL(s.[ZeilenNr], N'') HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.VorgangPositionArchiv;
  INSERT INTO dbo.VorgangPositionArchiv ([VogID], [VogBelegNr], [IntBelegNr], [ZeilenNr], [BelegPosNr], [AusblendenKz], [AbrPosKz], [PosNr], [TitelNr], [Pos], [ArtNr], [ArtKz], [HatZusKz], [IstZusKz], [AZusID], [Einh], [Mge], [MgeFak], [BuchMge], [LiefMge], [LiefDat], [LeistDat], [EEkKalk], [EEkRoh], [EPreisOMf], [EPrNt], [EPrSt], [EPrBt], [EPreis], [EPreisFak])
  SELECT
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[VogBelegNr]), N'') IS NULL THEN NULL ELSE s.[VogBelegNr] END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IntBelegNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ZeilenNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BelegPosNr]), N'')),
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AusblendenKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AbrPosKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[PosNr]), N'')),
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[TitelNr]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Pos]), N'') IS NULL THEN NULL ELSE s.[Pos] END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtNr]), N'') IS NULL THEN NULL ELSE s.[ArtNr] END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[ArtKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[HatZusKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      CASE NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[IstZusKz]), N'') WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END,
      TRY_CONVERT(int, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[AZusID]), N'')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Einh]), N'') IS NULL THEN NULL ELSE s.[Einh] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[Mge]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[MgeFak]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[BuchMge]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefMge]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LiefDat]), N''), 104) END,
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N'') = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[LeistDat]), N''), 104) END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkKalk]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EEkRoh]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisOMf]), N'') IS NULL THEN NULL ELSE s.[EPreisOMf] END,
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrNt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrSt]), N''), N'.', N''), N',', N'.')),
      TRY_CONVERT(decimal(18,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPrBt]), N''), N'.', N''), N',', N'.')),
      CASE WHEN NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreis]), N'') IS NULL THEN NULL ELSE s.[EPreis] END,
      TRY_CONVERT(decimal(9,4), REPLACE(REPLACE(NULLIF(TRIM(NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10) FROM s.[EPreisFak]), N''), N'.', N''), N',', N'.'))
  FROM stg.VorgangPositionArchiv s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'VorgangPositionArchiv', @alt, @neu, N'OK', NULL);
END;
GO
CREATE OR ALTER PROCEDURE dbo.bp_Uebernehmen @Tabellen nvarchar(400), @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* Ersetzt die genannten Tabellen (Komma-Liste) aus stg.* in EINER Transaktion:
     scheitert eine, bleibt bei allen der bisherige Stand. */
  SET NOCOUNT ON; SET XACT_ABORT ON;
  DECLARE @t sysname, @sql nvarchar(400);
  BEGIN TRY
    BEGIN TRAN;
    DECLARE c CURSOR LOCAL FAST_FORWARD FOR
      SELECT TRIM(value) FROM STRING_SPLIT(@Tabellen, N',', 1) WHERE TRIM(value) <> N'' ORDER BY ordinal;
    OPEN c; FETCH NEXT FROM c INTO @t;
    WHILE @@FETCH_STATUS = 0
    BEGIN
      IF @t NOT IN (N'Artikel', N'Adressen', N'Vorgang', N'VorgangArchiv', N'VorgangPosition', N'VorgangPositionArchiv') THROW 50010, N'Unbekannte Tabelle in @Tabellen.', 1;
      SET @sql = N'EXEC dbo.bp_Lade_' + @t + N' @MinAnteil = @m';
      EXEC sp_executesql @sql, N'@m decimal(5,2)', @m = @MinAnteil;
      FETCH NEXT FROM c INTO @t;
    END;
    CLOSE c; DEALLOCATE c;
    COMMIT;
  END TRY
  BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK;
    DECLARE @fehler nvarchar(max) = ERROR_MESSAGE();
    INSERT INTO dbo.ImportLog (Tabelle, Status, Meldung) VALUES (@Tabellen, N'Fehler', @fehler);
    THROW;
  END CATCH
END;
GO

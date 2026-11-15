"""Erzeugt bp_import.sql: Staging-Tabellen (stg.*), Ladeprozeduren und Importprotokoll
für den täglichen büro+-Import (siehe bp_import.ps1 und LIESMICH.md).

Die Spaltenlisten sind die Header der büro+-Export-Layouts (Feldname ohne «», ohne
Punkte). Der Typ bestimmt die Umwandlung vom Rohtext in die Zieltabelle:
  text      leer/Leerraum → NULL, sonst unverändert
  int       ganze Zahl
  dec(p,s)  deutsche Zahl „1.234,56“
  date      „TT.MM.JJJJ“, 30.12.1899 (büro+-Nullwert) → NULL
  datetime  „TT.MM.JJJJ hh:mm:ss“
  bit       Ja/Nein, leer → NULL;  bit0: leer → 0 (Kennzeichen, die büro+ nur bei „Ja“ füllt)

Aufruf:  python tools/bueroplus/sql_bauen.py > tools/bueroplus/bp_import.sql
"""

T = lambda n: ("text", f"nvarchar({n})")
TABELLEN = {
 "Artikel": {"pk": ["ArtArtNr"], "index": ["ArtWgrNr", "ArtID"], "spalten": [
  ("ArtID","int"),("ArtArtNr",T(30)),("ArtSuchBeg",T(50)),("ArtArtikelArt",T(30)),("ArtGspKz","bit0"),
  ("ArtBarCd",T(30)),("ArtWgrNr",T(30)),("ArtWgrNrInfo",T(100)),("ArtKuBez1",T(100)),("ArtBez1",T("max")),
  ("ArtKuBez2",T(100)),("ArtBez2",T(200)),("ArtKuBez3",T(100)),("ArtBez3",T(200)),("ArtEinh",T(10)),
  ("ArtMgeFak","dec(18,4)"),("ArtEPreisFak","dec(9,4)"),("ArtGew","dec(18,4)"),("ArtLaenge","dec(18,4)"),
  ("ArtBreite","dec(18,4)"),("ArtHoehe","dec(18,4)"),("ArtLaengeEinh",T(10)),("ArtInhaltMge","dec(18,4)"),
  ("ArtInhaltEinh",T(20)),("ArtGrPrEinh",T(20)),("ArtBeschr",T("max")),("ArtStSchl",T(60)),("ArtStSchlArt","int"),
  ("ArtSktoKz","bit"),("ArtNichtSktoNetBet","dec(14,2)"),("ArtStGArtKz","bit"),("ArtHstAdrNr","int"),
  ("ArtHstArtNr",T(30)),("ArtEkMitt","dec(14,4)"),("ArtEkKalkVgb","dec(14,4)"),("ArtEkKalkSchl",T(60)),
  ("ArtEkKalk","dec(14,4)"),("ArtEkRohVgb","dec(14,4)")]
  + [(f"ArtVk{i}Preis","dec(14,4)") for i in range(10)] + [("ArtVkDat","date")]},
 "Adressen": {"pk": ["AdrAdrNr"], "index": ["AdrVtrNr", "AdrRePLZ"], "spalten": [
  ("AdrAdrNr","int"),("AdrStatus",T(50)),("AdrReNa1",T(100)),("AdrReNa2",T(100)),("AdrReNa3",T(100)),
  ("AdrReStr",T(100)),("AdrReLand","smallint"),("AdrRePLZ",T(20)),("AdrReOrt",T(60)),("AdrReTel",T(50)),
  ("AdrReEMail1",T(255)),("AdrReStdReKz","bit"),("AdrReStdLiKz","bit"),("AdrReUStId",T(30)),("AdrReInfo",T("max")),
  ("AdrReGspKz","bit"),("AdrSel1",T(100)),("AdrVtrNr","int"),("AdrBranche",T(60)),("AdrLiAnsNr","smallint"),
  ("AdrReAnsNr","smallint"),("AdrSuchBeg",T(50)),("AdrErstDat","datetime"),("AdrSel2",T(100)),
  ("AdrGspKz","bit0"),("AdrGspDat","date"),("AdrGspInfo",T("max"))]},
}
KOPF = [("VogID","int"),("VogBelegNr",T(20)),("VogAdrNr","int"),("VogArt",T(40)),("VogVerk",T(10)),("VogVtrNr","int"),
  ("VogVtrProvSz","dec(6,2)"),("VogBez",T(200)),("VogGspKz","bit"),("VogGebuchtKz","bit"),("VogStorniertKz","bit"),
  ("VogDat","date"),("VogZahlBed",T(200)),("VogZahlArt",T(100)),("VogGGew","dec(18,3)"),("VogGPreisNt","dec(14,2)"),
  ("VogGPreisSt","dec(14,2)"),("VogGPreisBt","dec(14,2)"),("VogGEkKalk","dec(14,2)"),("VogGEkRoh","dec(14,2)"),
  ("VogReILN",T(20)),("VogLiAnsVwKz","bit"),("VogLiAdrNr","int"),("VogLiefDat","date"),("VogKdBezBet","dec(14,2)"),
  ("VogToArt",T(40)),("VogLtzArt",T(40)),("VogDreiGsKz","bit"),("VogVsdArt",T(60)),("VogVsdZWeise",T(60)),
  ("VogLiefBed",T(200)),("VogKdLiefNr",T(30)),("VogBKtoNr",T(20)),("VogStGeschKz","bit"),("VogRBetPrNaKz","bit")]
POS = [("VogID","int"),("VogBelegNr",T(20)),("IntBelegNr","int"),("ZeilenNr","int"),("BelegPosNr","int"),
  ("AusblendenKz","bit"),("AbrPosKz","bit"),("PosNr","int"),("TitelNr","int"),("Pos",T(20)),("ArtNr",T(30)),
  ("ArtKz","bit"),("HatZusKz","bit"),("IstZusKz","bit"),("AZusID","int"),("Einh",T(10)),("Mge","dec(18,4)"),
  ("MgeFak","dec(18,4)"),("BuchMge","dec(18,4)"),("LiefMge","dec(18,4)"),("LiefDat","date"),("LeistDat","date"),
  ("EEkKalk","dec(18,4)"),("EEkRoh","dec(18,4)"),("EPreisOMf",T(40)),("EPrNt","dec(18,4)"),("EPrSt","dec(18,4)"),
  ("EPrBt","dec(18,4)"),("EPreis",T(40)),("EPreisFak","dec(9,4)")]
for t in ("Vorgang", "VorgangArchiv"):
    TABELLEN[t] = {"pk": ["VogID"], "index": ["VogAdrNr", "VogDat", "VogArt", "VogBelegNr"], "spalten": KOPF}
for t in ("VorgangPosition", "VorgangPositionArchiv"):
    TABELLEN[t] = {"pk": ["VogID", "ZeilenNr"], "index": ["ArtNr", "VogBelegNr"], "spalten": POS}

WS = "NCHAR(32)+NCHAR(9)+NCHAR(13)+NCHAR(10)"

def roh(c):   # getrimmter Rohwert, leer → NULL
    return f"NULLIF(TRIM({WS} FROM s.[{c}]), N'')"

def zieltyp(t):
    if isinstance(t, tuple): return t[1]
    if t.startswith("dec"): return "decimal" + t[3:]
    return {"int": "int", "smallint": "smallint", "date": "date", "datetime": "datetime2(0)",
            "bit": "bit", "bit0": "bit"}[t]

def ausdruck(c, t):
    r = roh(c)
    if isinstance(t, tuple):
        return f"CASE WHEN {r} IS NULL THEN NULL ELSE s.[{c}] END"
    if t in ("int", "smallint"): return f"TRY_CONVERT({t}, {r})"
    if t.startswith("dec"):
        return f"TRY_CONVERT({zieltyp(t)}, REPLACE(REPLACE({r}, N'.', N''), N',', N'.'))"
    if t == "date": return f"CASE WHEN {r} = N'30.12.1899' THEN NULL ELSE TRY_CONVERT(date, {r}, 104) END"
    if t == "datetime": return f"TRY_CONVERT(datetime2(0), {r}, 104)"
    b = f"CASE {r} WHEN N'Ja' THEN CAST(1 AS bit) WHEN N'Nein' THEN CAST(0 AS bit) END"
    return f"ISNULL({b}, 0)" if t == "bit0" else b

def ungueltig(c, t):
    """Bedingung: Rohwert vorhanden, aber nicht umwandelbar (oder zu lang)."""
    r = roh(c)
    if isinstance(t, tuple):
        n = t[1][9:-1]
        return None if n == "max" else f"LEN(s.[{c}]) > {n}"
    if t.startswith("dec"):
        return f"{r} IS NOT NULL AND ({ausdruck(c, t)} IS NULL OR {r} LIKE N'%[^0-9.,-]%')"
    if t == "date":
        return f"{r} IS NOT NULL AND {r} <> N'30.12.1899' AND TRY_CONVERT(date, {r}, 104) IS NULL"
    if t in ("bit", "bit0"):
        return f"{r} IS NOT NULL AND {r} NOT IN (N'Ja', N'Nein')"
    return f"{r} IS NOT NULL AND {ausdruck(c, t)} IS NULL"

out = []
w = out.append
w("""/* büro+-Import: Staging, Ladeprozeduren, Protokoll.
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
GO""")

for name, d in TABELLEN.items():
    sp = d["spalten"]
    # Staging: alles Text, Spaltenreihenfolge = Header des Exports
    w(f"IF OBJECT_ID(N'stg.{name}') IS NOT NULL DROP TABLE stg.{name};")
    w(f"CREATE TABLE stg.{name} (\n  " + ",\n  ".join(f"[{c}] nvarchar(max) NULL" for c, _ in sp) + "\n);\nGO")
    # Zieltabelle nur anlegen, wenn sie fehlt (bestehende Daten bleiben unangetastet)
    defs = []
    for c, t in sp:
        nn = " NOT NULL" if c in d["pk"] else ""
        dflt = f" NOT NULL CONSTRAINT DF_{name}_{c} DEFAULT 0" if t == "bit0" else ""
        defs.append(f"[{c}] {zieltyp(t)}{nn}{dflt}")
    defs.append("ImportiertAm datetime2(0) NOT NULL DEFAULT SYSDATETIME()")
    defs.append(f"CONSTRAINT PK_{name} PRIMARY KEY ({', '.join(d['pk'])})")
    w(f"IF OBJECT_ID(N'dbo.{name}') IS NULL\nBEGIN\n  CREATE TABLE dbo.{name} (\n    " + ",\n    ".join(defs) + "\n  );")
    for ix in d["index"]:
        w(f"  CREATE INDEX IX_{name}_{ix} ON dbo.{name}({ix});")
    w("END\nGO")

    pruef = []
    for c, t in sp:
        u = ungueltig(c, t)
        if u:
            pruef.append(f"    SELECT N'{c}' AS Spalte, COUNT(*) AS Anzahl, MIN(LEFT(s.[{c}], 40)) AS Beispiel FROM stg.{name} s WHERE {u}")
    pkleer = " OR ".join(f"{roh(c)} IS NULL" for c in d["pk"])
    pkkey = " + N'|' + ".join(f"ISNULL(s.[{c}], N'')" for c in d["pk"])
    spalten = ", ".join(f"[{c}]" for c, _ in sp)
    werte = ",\n      ".join(ausdruck(c, t) for c, t in sp)
    w(f"""CREATE OR ALTER PROCEDURE dbo.bp_Lade_{name} @MinAnteil decimal(5,2) = 0.80
AS
BEGIN
  /* stg.{name} prüfen und dbo.{name} vollständig ersetzen. Läuft in der Transaktion des Aufrufers. */
  SET NOCOUNT ON;
  DECLARE @neu int = (SELECT COUNT(*) FROM stg.{name});
  DECLARE @alt int = (SELECT COUNT(*) FROM dbo.{name});
  DECLARE @msg nvarchar(max);
  IF @neu = 0 THROW 50001, N'{name}: Die Staging-Tabelle ist leer – nichts ersetzt.', 1;
  IF @alt > 0 AND @neu < @alt * @MinAnteil
  BEGIN
    SET @msg = CONCAT(N'{name}: nur ', @neu, N' Zeilen statt bisher ', @alt, N' – unter ', CAST(@MinAnteil * 100 AS int), N' %, vermutlich unvollständiger Export. Nichts ersetzt.');
    SET @msg = REPLACE(@msg, N'%', N'%%');  /* THROW wertet % als Formatzeichen */
    THROW 50002, @msg, 1;
  END;
  SELECT @msg = STRING_AGG(CONCAT(Spalte, N': ', Anzahl, N'× ungültig (z. B. „', Beispiel, N'“)'), N'; ')
  FROM (
{chr(10).join(p + chr(10) + '    UNION ALL' for p in pruef[:-1])}
{pruef[-1]}
  ) f WHERE Anzahl > 0;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(N'{name}: ' + @msg, N'%', N'%%'); THROW 50003, @msg, 1; END;
  IF EXISTS (SELECT 1 FROM stg.{name} s WHERE {pkleer}) THROW 50004, N'{name}: Datensatz ohne Schlüssel ({", ".join(d["pk"])}).', 1;
  SELECT TOP 1 @msg = CONCAT(N'{name}: Schlüssel doppelt: ', k, N' (', n, N'×)')
  FROM (SELECT {pkkey} AS k, COUNT(*) AS n FROM stg.{name} s GROUP BY {pkkey} HAVING COUNT(*) > 1) d;
  IF @msg IS NOT NULL BEGIN SET @msg = REPLACE(@msg, N'%', N'%%'); THROW 50005, @msg, 1; END;

  TRUNCATE TABLE dbo.{name};
  INSERT INTO dbo.{name} ({spalten})
  SELECT
      {werte}
  FROM stg.{name} s;
  INSERT INTO dbo.ImportLog (Tabelle, ZeilenAlt, ZeilenNeu, Status, Meldung)
  VALUES (N'{name}', @alt, @neu, N'OK', NULL);
END;
GO""")

namen = ", ".join(f"N'{n}'" for n in TABELLEN)
w(f"""CREATE OR ALTER PROCEDURE dbo.bp_Uebernehmen @Tabellen nvarchar(400), @MinAnteil decimal(5,2) = 0.80
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
      IF @t NOT IN ({namen}) THROW 50010, N'Unbekannte Tabelle in @Tabellen.', 1;
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
GO""")
print("\n".join(out))

-- Gezählte Inventurbestände je Stichtag (Quelle: Inventurliste aus Excel).
-- Grundlage der Cockpit-Liste „Negative Bestände seit Inventur“:
-- Soll = gezählte Menge + Zugänge − Abgänge aus gebuchten Belegen nach dem Stichtag.
IF OBJECT_ID('dbo.InventurZaehlung') IS NULL
CREATE TABLE dbo.InventurZaehlung (
    Stichtag    date          NOT NULL,
    ArtNr       nvarchar(40)  NOT NULL,
    Menge       decimal(18,3) NOT NULL,   -- in Stück (bei Tsd/‰ ebenfalls Stück), bei Paket in Paketen
    Einheit     nvarchar(20)  NULL,       -- Mengeneinheit laut Inventurliste (Tsd, Stück, Paket, KG)
    Quelle      nvarchar(200) NULL,       -- Datei/Blatt
    GeladenAm   datetime2     NOT NULL CONSTRAINT DF_InventurZaehlung_GeladenAm DEFAULT (SYSDATETIME()),
    CONSTRAINT PK_InventurZaehlung PRIMARY KEY (Stichtag, ArtNr)
);

"""SQL-Skript für die Übergabetabellen (SQL Server). Das Widget bietet es zum Download an."""

SKRIPT = r"""-- ============================================================================
-- Datenmonster ZUGFeRD-Ausgang: Übergabetabellen für Access
--
-- Ablauf in Access:
--   1. PDF erzeugen wie bisher
--   2. Kopf in tInvoice schreiben (Status bleibt 'ENTWURF'), PDF nach OrgFile
--   3. Positionen in tInvoicePositions schreiben
--   4. UPDATE tInvoice SET Status = 'NEU'      <- erst jetzt greift Datenmonster zu
--   5. warten, bis Status = 'OK' (fertige ZUGFeRD-PDF steht in ZugferdFile)
--      oder 'FEHLER' (Grund in StatusMessage; korrigieren, wieder 'NEU' setzen)
--
-- Beträge immer so, wie sie auf der PDF stehen. Datenmonster rechnet nach und
-- weist die Rechnung ab, wenn XML und PDF nicht centgenau übereinstimmen.
-- Steuer bitte JE STEUERSATZ runden (Summe Netto je Satz x Satz), nicht je Position.
-- ============================================================================

CREATE TABLE dbo.tInvoice (
    InvoiceId              INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_tInvoice PRIMARY KEY,
    InvoiceNumber          NVARCHAR(50)  NOT NULL,
    InvoiceType            NVARCHAR(20)  NOT NULL CONSTRAINT DF_tInvoice_Type DEFAULT (N'RECHNUNG'),
        -- RECHNUNG | STORNO (Gutschrift, Bezug auf Rechnung) | KORREKTUR (Rechnungskorrektur)
    InvoiceDate            DATE          NOT NULL,
    DeliveryDate           DATE          NULL,      -- Leistungs-/Lieferdatum
    PeriodStart            DATE          NULL,      -- oder Leistungszeitraum von ...
    PeriodEnd              DATE          NULL,      -- ... bis
    DueDate                DATE          NULL,      -- Fälligkeit
    Currency               CHAR(3)       NOT NULL CONSTRAINT DF_tInvoice_Currency DEFAULT ('EUR'),
    PrecedingInvoiceNumber NVARCHAR(50)  NULL,      -- Pflicht bei STORNO/KORREKTUR
    PrecedingInvoiceDate   DATE          NULL,
    SellerVatId            NVARCHAR(30)  NULL,      -- eigene USt-IdNr. dieser Rechnung (leer = Standard
                                                    -- aus Datenmonster; muss dort hinterlegt sein)
    BuyerReference         NVARCHAR(100) NULL,      -- Leitweg-ID (Behörden) bzw. "Ihr Zeichen"
    OrderReference         NVARCHAR(100) NULL,      -- Bestellnummer des Kunden
    CustomerNumber         NVARCHAR(50)  NULL,
    BuyerName              NVARCHAR(200) NOT NULL,
    BuyerContact           NVARCHAR(100) NULL,
    BuyerStreet            NVARCHAR(200) NULL,
    BuyerAddress2          NVARCHAR(200) NULL,
    BuyerZip               NVARCHAR(20)  NULL,
    BuyerCity              NVARCHAR(100) NULL,
    BuyerCountry           CHAR(2)       NOT NULL CONSTRAINT DF_tInvoice_Country DEFAULT ('DE'),
    BuyerVatId             NVARCHAR(30)  NULL,      -- Pflicht bei Reverse Charge / EU-Lieferung
    BuyerEmail             NVARCHAR(200) NULL,
    BuyerIban              NVARCHAR(34)  NULL,      -- nur bei Lastschrift
    DirectDebitMandate     NVARCHAR(50)  NULL,      -- nur bei Lastschrift
    ShipToName             NVARCHAR(200) NULL,      -- abweichende Lieferanschrift
    ShipToStreet           NVARCHAR(200) NULL,
    ShipToZip              NVARCHAR(20)  NULL,
    ShipToCity             NVARCHAR(100) NULL,
    ShipToCountry          CHAR(2)       NULL,
    PaymentMeans           NVARCHAR(3)   NULL,      -- leer = Vorgabe aus Datenmonster (58 = SEPA-Überweisung)
    PaymentTerms           NVARCHAR(500) NULL,      -- leer = Vorgabe aus Datenmonster
    SkontoDays             INT           NULL,
    SkontoPercent          DECIMAL(5,2)  NULL,
    Note                   NVARCHAR(MAX) NULL,      -- freier Hinweistext
    TotalNet               DECIMAL(18,2) NOT NULL,
    TotalTax               DECIMAL(18,2) NOT NULL,
    TotalGross             DECIMAL(18,2) NOT NULL,
    Prepaid                DECIMAL(18,2) NULL,      -- bereits gezahlt / Anzahlung
    OrgFile                VARBINARY(MAX) NULL,     -- die PDF aus Access (Original)
    -- ab hier schreibt Datenmonster
    Status                 NVARCHAR(20)  NOT NULL CONSTRAINT DF_tInvoice_Status DEFAULT (N'ENTWURF'),
    StatusMessage          NVARCHAR(MAX) NULL,
    OutputFileName         NVARCHAR(260) NULL,      -- Dateiname für den Mail-Anhang
    ProcessedAt            DATETIME2(0)  NULL,
    ZugferdFile            VARBINARY(MAX) NULL,     -- die fertige ZUGFeRD-PDF für den Versand
    CreatedAt              DATETIME2(0)  NOT NULL CONSTRAINT DF_tInvoice_Created DEFAULT (SYSDATETIME()),
    CONSTRAINT CK_tInvoice_Type   CHECK (InvoiceType IN (N'RECHNUNG', N'STORNO', N'KORREKTUR')),
    CONSTRAINT CK_tInvoice_Status CHECK (Status IN (N'ENTWURF', N'NEU', N'IN_ARBEIT', N'OK', N'FEHLER'))
);
CREATE UNIQUE INDEX UX_tInvoice_Number ON dbo.tInvoice (InvoiceNumber);
CREATE INDEX IX_tInvoice_Status ON dbo.tInvoice (Status);

CREATE TABLE dbo.tInvoicePositions (
    PositionId         INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_tInvoicePositions PRIMARY KEY,
    InvoiceId          INT           NOT NULL
        CONSTRAINT FK_tInvoicePositions_Invoice REFERENCES dbo.tInvoice (InvoiceId) ON DELETE CASCADE,
    LineNumber         INT           NOT NULL,
    ArticleNumber      NVARCHAR(100) NULL,
    BuyerArticleNumber NVARCHAR(100) NULL,
    Name               NVARCHAR(500) NOT NULL,
    Description        NVARCHAR(MAX) NULL,
    Quantity           DECIMAL(18,4) NOT NULL,
    Unit               NVARCHAR(20)  NOT NULL CONSTRAINT DF_tInvoicePositions_Unit DEFAULT (N'H87'),
        -- UN/ECE-Code (H87 Stück, HUR Stunde, KGM kg, LS pauschal …) oder Stk/Std/kg/psch/Pal
    UnitPrice          DECIMAL(18,4) NOT NULL,  -- Nettoeinzelpreis
    PriceBaseQuantity  DECIMAL(18,4) NULL,      -- Preis je ... (leer = 1)
    LineNet            DECIMAL(18,2) NOT NULL,  -- Zeilenbetrag netto wie gedruckt (nach Rabatt)
    VatCategory        NVARCHAR(2)   NOT NULL CONSTRAINT DF_tInvoicePositions_Cat DEFAULT (N'S'),
        -- S normal | Z 0 % | E steuerfrei (Grund nötig) | AE Reverse Charge
        -- K innergem. Lieferung | G Ausfuhr Drittland
    VatRate            DECIMAL(5,2)  NOT NULL,  -- 19, 7, bei Z/E/AE/K/G: 0
    ExemptionReason    NVARCHAR(500) NULL,      -- abweichender Befreiungstext
    CONSTRAINT UX_tInvoicePositions_Line UNIQUE (InvoiceId, LineNumber)
);
"""

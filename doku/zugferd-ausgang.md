# ZUGFeRD-Ausgang: E-Rechnungen aus Access

Access erstellt die Rechnung wie bisher als PDF. Zusätzlich schreibt es die
Rechnungsdaten in zwei Tabellen auf dem SQL-Server. Datenmonster baut daraus das
ZUGFeRD-XML (Profil **EN 16931**), bettet es in die PDF ein (PDF/A-3,
`factur-x.xml`) und legt die fertige Datei auf einen FTP-Server im Firmennetz.
Den Stand schreibt es in die Tabelle zurück. Access versendet danach wie gewohnt
über Outlook.

```
Access ──PDF + Daten──▶ tInvoice / tInvoicePositions ──▶ Datenmonster ──▶ FTP
   ▲                         Status OK / FEHLER  ◀──────────────┘
   └── wartet auf OK, hängt die Datei an die Outlook-Mail
```

## Einrichtung

1. **Tabellen anlegen**: Formular „ZUGFeRD-Rechnungen“ → Reiter *Einrichtung* →
   „SQL-Skript zum Anlegen“ herunterladen und auf dem SQL-Server ausführen
   (Quelle: `backend/app/services/zugferd_sql.py`).
   Wer die fertige PDF auch in der Datenbank haben will, kommentiert vorher die
   Zeile `ZugferdFile` ein.
2. **Firmendaten** im gleichen Formular pflegen (Name, Anschrift, USt-IdNr. bzw.
   Steuernummer, IBAN, Standard-Zahlungsbedingung).
3. **Einrichtung** (nur Admin): FTP-Server, Verzeichnis, Dateiname, Zeitplan →
   „Verbindung und Tabellen prüfen“. Der Test schreibt eine Probedatei und
   löscht sie wieder.
4. In Access das Modul unten einfügen und die zwei Abfragen anlegen.

## Belegarten und Steuerfälle

| InvoiceType | XML-Typ | Pflicht zusätzlich |
|---|---|---|
| `RECHNUNG` | 380 | – |
| `STORNO` | 381 (Gutschrift) | `PrecedingInvoiceNumber`. Negative Beträge sind erlaubt, Datenmonster dreht sie um |
| `KORREKTUR` | 384 | `PrecedingInvoiceNumber`, Beträge mit Vorzeichen |

| VatCategory | Bedeutung | Satz | Pflicht zusätzlich |
|---|---|---|---|
| `S` | normal besteuert | 19 / 7 | – |
| `Z` | 0 % | 0 | – |
| `E` | steuerfrei | 0 | `ExemptionReason` (z. B. „§ 4 Nr. 14 UStG“) |
| `AE` | Reverse Charge | 0 | `BuyerVatId`, eigene USt-IdNr. |
| `K` | innergemeinschaftliche Lieferung | 0 | `BuyerVatId`, `DeliveryDate` oder Zeitraum, Lieferland ≠ DE |
| `G` | Ausfuhr ins Drittland | 0 | eigene USt-IdNr. |

**Abgewiesen wird**, was sich nicht sauber ausstellen lässt, zum Beispiel:

- Netto, Steuer oder Brutto weichen um einen Cent von der Rechnung nach EN 16931
  ab. ⚠️ Die Steuer muss **je Steuersatz** gerundet werden
  (Summe netto × Satz), nicht je Position.
- Unbekannte Einheit, fehlende Pflichtangaben oder eine verschlüsselte PDF.

Der Grund steht in `tInvoice.StatusMessage` und im Protokoll. In Access
korrigieren, `Status = 'NEU'` setzen (oder im Protokoll auf „erneut“ klicken),
dann geht die Rechnung beim nächsten Lauf durch.

**Mehrere eigene USt-IdNrn.** (z. B. je Land): In den Firmendaten steht die
Standardnummer, alle weiteren kommen ins Feld „Weitere USt-IdNrn.“. Access trägt
je Rechnung die Nummer, die es auch druckt, in `tInvoice.SellerVatId` ein. Ist
das Feld leer, gilt die Standardnummer. Eine Nummer, die nicht in den Firmendaten
steht, führt zur Abweisung. Die Nummer wird bewusst nicht nach Kundenland
gewählt: Bei einer EU-Lieferung aus Deutschland gilt die deutsche Nummer, auch
wenn der Kunde in Frankreich sitzt.

**Einheiten**: UN/ECE-Code (`H87` Stück, `HUR` Stunde, `KGM`, `LS` pauschal, `XPX`
Palette …) oder die üblichen Kürzel `Stk`, `Std`, `kg`, `psch`, `Pal`, `Karton`.
Unbekannte Einheiten werden nicht geraten.

**Rabatte**: `LineNet` ist der gedruckte Zeilenbetrag. Liegt er unter
Menge × Preis, wird die Differenz als Positionsrabatt ausgewiesen. Eine
Rabattzeile mit negativem Preis ist erlaubt.

**Status**: `ENTWURF` (Access schreibt noch) → `NEU` → `IN_ARBEIT` → `OK` / `FEHLER`.
Ist der FTP nicht erreichbar, geht die Rechnung zurück auf `NEU`. Das ist kein
Fehler der Rechnung.

**PDF/A**: Damit die Datei ein sauberes PDF/A ist, müssen die Schriften in der
Access-PDF eingebettet sein. Fehlen sie, meldet das Protokoll einen Hinweis. Das
XML bleibt trotzdem gültig.

## Access: zwei Abfragen + ein Modul

Die Abfragen **`qZugferdKopf`** und **`qZugferdPositionen`** liefern die Spalten
unter den Namen der Zieltabellen (Alias im Abfrageentwurf, z. B.
`InvoiceNumber: [RechnungsNr]`). Die Positionsabfrage braucht zusätzlich
`InvoiceNumber`, damit sie sich filtern lässt. Das Modul kopiert alle Spalten,
deren Namen in der Zieltabelle vorkommen. Andere Spalten werden übersprungen.

```vba
Option Compare Database
Option Explicit

' Verbindung zum SQL-Server mit tInvoice / tInvoicePositions
Private Const CONN_STR As String = _
    "Provider=MSOLEDBSQL;Server=SERVER\INSTANZ;Database=auftragsbuch;Integrated Security=SSPI;"
' Freigabe, auf die der FTP-Server schreibt (für den Mail-Anhang)
Private Const ABLAGE As String = "\\fileserver\zugferd\"

Private Const adOpenKeyset = 1, adLockOptimistic = 3, adTypeBinary = 1
Private Const adCmdText = 1, adVarWChar = 202, adParamInput = 1

' Übergibt eine Rechnung an Datenmonster. Gibt die InvoiceId zurück.
Public Function ZugferdUebergeben(ByVal rechnungsNr As String, ByVal pdfPfad As String) As Long
    Dim cn As Object, rs As Object, f As DAO.Field
    Dim qk As DAO.Recordset, qp As DAO.Recordset, id As Long
    Dim krit As String: krit = "InvoiceNumber = '" & Replace(rechnungsNr, "'", "''") & "'"

    Set qk = CurrentDb.OpenRecordset("SELECT * FROM qZugferdKopf WHERE " & krit, dbOpenSnapshot)
    If qk.EOF Then Err.Raise vbObjectError + 1, , "Rechnung " & rechnungsNr & " fehlt in qZugferdKopf"

    Set cn = CreateObject("ADODB.Connection")
    cn.Open CONN_STR
    cn.BeginTrans
    On Error GoTo Fehler

    ' Ein abgewiesener oder halber Vorversuch derselben Nummer wird ersetzt.
    ' Eine bereits erzeugte Rechnung (OK) bleibt stehen. Für die Korrektur gibt es eine neue Nummer.
    Befehl(cn, "DELETE FROM dbo.tInvoice WHERE InvoiceNumber = ? AND Status IN ('ENTWURF','FEHLER')", rechnungsNr).Execute

    Set rs = CreateObject("ADODB.Recordset")
    rs.Open "SELECT * FROM dbo.tInvoice WHERE 1 = 0", cn, adOpenKeyset, adLockOptimistic
    rs.AddNew
    For Each f In qk.Fields
        If FeldDa(rs, f.Name) Then rs.Fields(f.Name).Value = f.Value
    Next
    rs.Fields("PdfFile").Value = DateiLesen(pdfPfad)
    rs.Fields("Status").Value = "ENTWURF"
    rs.Update
    rs.Close

    id = Befehl(cn, "SELECT InvoiceId FROM dbo.tInvoice WHERE InvoiceNumber = ?", rechnungsNr).Execute()(0)

    Set qp = CurrentDb.OpenRecordset("SELECT * FROM qZugferdPositionen WHERE " & krit, dbOpenSnapshot)
    rs.Open "SELECT * FROM dbo.tInvoicePositions WHERE 1 = 0", cn, adOpenKeyset, adLockOptimistic
    Do Until qp.EOF
        rs.AddNew
        For Each f In qp.Fields
            If FeldDa(rs, f.Name) And f.Name <> "InvoiceId" Then rs.Fields(f.Name).Value = f.Value
        Next
        rs.Fields("InvoiceId").Value = id
        rs.Update
        qp.MoveNext
    Loop
    rs.Close

    ' Erst jetzt darf Datenmonster zugreifen.
    cn.Execute "UPDATE dbo.tInvoice SET Status = 'NEU' WHERE InvoiceId = " & id
    cn.CommitTrans
    cn.Close
    ZugferdUebergeben = id
    Exit Function
Fehler:
    cn.RollbackTrans
    Err.Raise Err.Number, , "ZUGFeRD-Übergabe " & rechnungsNr & ": " & Err.Description
End Function

' Wartet, bis Datenmonster fertig ist. Gibt den Pfad der ZUGFeRD-PDF zurück.
' Bei FEHLER wird der Grund als Fehler gemeldet.
Public Function ZugferdWarten(ByVal id As Long, Optional ByVal maxSekunden As Long = 600) As String
    Dim cn As Object, rs As Object, ende As Single
    Set cn = CreateObject("ADODB.Connection")
    cn.Open CONN_STR
    ende = Timer + maxSekunden
    Do
        Set rs = cn.Execute("SELECT Status, StatusMessage, OutputFileName FROM dbo.tInvoice WHERE InvoiceId = " & id)
        Select Case rs!Status
            Case "OK"
                ZugferdWarten = ABLAGE & rs!OutputFileName
                Exit Do
            Case "FEHLER"
                Err.Raise vbObjectError + 2, , "E-Rechnung abgewiesen:" & vbCrLf & rs!StatusMessage
        End Select
        If Timer > ende Then Err.Raise vbObjectError + 3, , "Datenmonster hat nach " & maxSekunden & " s noch nicht geantwortet"
        Pause 5
    Loop
    cn.Close
End Function

Private Function Befehl(cn As Object, sql As String, wert As String) As Object
    Set Befehl = CreateObject("ADODB.Command")
    Set Befehl.ActiveConnection = cn
    Befehl.CommandType = adCmdText
    Befehl.CommandText = sql
    Befehl.Parameters.Append Befehl.CreateParameter("p", adVarWChar, adParamInput, 50, wert)
End Function

Private Function FeldDa(rs As Object, ByVal name As String) As Boolean
    Dim f As Object
    For Each f In rs.Fields
        If StrComp(f.Name, name, vbTextCompare) = 0 Then FeldDa = True: Exit Function
    Next
End Function

Private Function DateiLesen(ByVal pfad As String) As Variant
    Dim s As Object
    Set s = CreateObject("ADODB.Stream")
    s.Type = adTypeBinary
    s.Open
    s.LoadFromFile pfad
    DateiLesen = s.Read
    s.Close
End Function

Private Sub Pause(ByVal sekunden As Single)
    Dim bis As Single: bis = Timer + sekunden
    Do While Timer < bis: DoEvents: Loop
End Sub
```

Einbau in den bestehenden Versand (Beispiel):

```vba
DoCmd.OutputTo acOutputReport, "rptRechnung", acFormatPDF, pdfPfad
id = ZugferdUebergeben(rechnungsNr, pdfPfad)
anhang = ZugferdWarten(id)          ' statt pdfPfad an die Outlook-Mail hängen
```

Ist die Spalte `ZugferdFile` angelegt, kann Access die fertige PDF auch direkt aus
der Datenbank holen. Dann braucht es keinen Zugriff auf die FTP-Ablage
(`ADODB.Stream` → `Write rs!ZugferdFile` → `SaveToFile`).

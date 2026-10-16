# ZUGFeRD-Ausgang: E-Rechnungen aus Access

Access erstellt die Rechnung wie bisher als PDF. Die PDF und die Rechnungsdaten
schreibt es in zwei Tabellen auf dem SQL-Server (Datenbank `auftragsbuch`).
Datenmonster baut daraus das ZUGFeRD-XML (Profil **EN 16931**), bettet es in die
PDF ein (PDF/A-3, `factur-x.xml`) und schreibt die fertige Datei in dieselbe
Zeile zurück. Access holt sie dort ab und versendet sie wie gewohnt über Outlook.

```
Access ──OrgFile + Daten──▶ tInvoice / tInvoicePositions ◀──liest── Datenmonster
   │                                  ▲                                   │
   └─ Anstoß (HTTP, über VPN) ────────┼──────────────────────────────────▶│
   ◀── ZugferdFile, Status OK/FEHLER ─┘◀──────────── schreibt zurück ──────┘
```

Access (Terminalserver) und SQL-Server stehen im selben Rechenzentrum. Die Datei
geht deshalb nie durch den VPN. Durch den Tunnel läuft nur der kurze Anstoß, und
auch der darf ausfallen: Das Intervall in Datenmonster holt die Rechnung dann
beim nächsten Takt.

## Einrichtung

1. **Tabellen**: Formular „ZUGFeRD-Rechnungen“ → Reiter *Einrichtung* →
   „SQL-Skript zum Anlegen“ (Quelle: `backend/app/services/zugferd_sql.py`).
   In `auftragsbuch` sind sie seit 16.10.2026 angelegt.
2. **Firmendaten** im gleichen Formular pflegen (Name, Anschrift, USt-IdNr. bzw.
   Steuernummer, weitere USt-IdNrn., IBAN, Standard-Zahlungsbedingung).
3. **Einrichtung** (nur Admin): Zeitplan einschalten (Sicherheitsnetz, z. B.
   alle 5 Minuten) und „Schlüssel erzeugen“. Den Schlüssel und die angezeigte
   Adresse ins Access-Modul übernehmen. Der Schlüssel wird nur einmal angezeigt,
   ein neuer macht den alten ungültig. Ein FTP-Server ist nicht nötig, er ist
   nur eine zusätzliche Ablage.
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
Ist eine (freiwillige) FTP-Ablage eingetragen und nicht erreichbar, geht die
Rechnung zurück auf `NEU`. Das ist kein Fehler der Rechnung.

**PDF/A**: Damit die Datei ein sauberes PDF/A ist, müssen die Schriften in der
Access-PDF eingebettet sein. Fehlen sie, meldet das Protokoll einen Hinweis. Das
XML bleibt trotzdem gültig.

## Access: zwei Abfragen + ein Modul

Die Abfragen **`qZugferdKopf`** und **`qZugferdPositionen`** liefern die Spalten
unter den Namen der Zieltabellen (Alias im Abfrageentwurf, z. B.
`InvoiceNumber: [RechnungsNr]`, `SellerVatId: [EigeneUStId]`). Die
Positionsabfrage braucht zusätzlich `InvoiceNumber`, damit sie sich filtern lässt.
Das Modul kopiert alle Spalten, deren Namen in der Zieltabelle vorkommen. Andere
Spalten werden übersprungen. `OrgFile` (die PDF) setzt das Modul selbst.

> Das Modul ist noch nicht in Access ausgeführt worden. Beim ersten Durchlauf
> mit Kleinigkeiten rechnen.

```vba
Option Compare Database
Option Explicit

' SQL-Server mit tInvoice / tInvoicePositions (Datenbank auftragsbuch)
Private Const CONN_STR As String = _
    "Provider=MSOLEDBSQL;Server=SERVER\INSTANZ;Database=auftragsbuch;UID=...;PWD=...;"
' Aus Datenmonster, Formular „ZUGFeRD-Rechnungen“ → Einrichtung → Anstoß aus Access
Private Const DM_URL As String = "http://DATENMONSTER:5174/api/zugferd/anstoss"
Private Const SCHLUESSEL As String = "zf_..."

Private Const adOpenKeyset = 1, adLockOptimistic = 3, adTypeBinary = 1
Private Const adSaveCreateOverWrite = 2
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
    ' Eine bereits erzeugte Rechnung (OK) bleibt stehen - die Korrektur bekommt eine neue Nummer.
    Befehl(cn, "DELETE FROM dbo.tInvoice WHERE InvoiceNumber = ? AND Status IN ('ENTWURF','FEHLER')", rechnungsNr).Execute

    Set rs = CreateObject("ADODB.Recordset")
    rs.Open "SELECT * FROM dbo.tInvoice WHERE 1 = 0", cn, adOpenKeyset, adLockOptimistic
    rs.AddNew
    For Each f In qk.Fields
        If FeldDa(rs, f.Name) Then rs.Fields(f.Name).Value = f.Value
    Next
    rs.Fields("OrgFile").Value = DateiLesen(pdfPfad)
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
    On Error GoTo 0

    Anstossen
    ZugferdUebergeben = id
    Exit Function
Fehler:
    cn.RollbackTrans
    Err.Raise Err.Number, , "ZUGFeRD-Übergabe " & rechnungsNr & ": " & Err.Description
End Function

' „Bitte jetzt verarbeiten“ an Datenmonster. Darf scheitern (VPN weg o. Ä.):
' dann holt das Intervall die Rechnung - Access wartet hier höchstens 5 Sekunden.
Public Sub Anstossen()
    Dim http As Object
    On Error Resume Next
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 3000, 3000, 5000, 5000      ' Auflösen, Verbinden, Senden, Antwort (ms)
    http.Open "POST", DM_URL, False
    http.SetRequestHeader "X-Ausloese-Schluessel", SCHLUESSEL
    http.Send
    If Err.Number <> 0 Then
        Debug.Print "ZUGFeRD-Anstoß nicht angekommen: " & Err.Description
    ElseIf http.Status <> 202 Then
        Debug.Print "ZUGFeRD-Anstoß abgelehnt: " & http.Status & " " & http.ResponseText
    End If
End Sub

' Wartet, bis Datenmonster fertig ist, speichert die ZUGFeRD-PDF als temporäre
' Datei und gibt deren Pfad zurück (für den Outlook-Anhang).
' Bei FEHLER wird der Grund als Fehler gemeldet.
Public Function ZugferdWarten(ByVal id As Long, Optional ByVal maxSekunden As Long = 600) As String
    Dim cn As Object, rs As Object, ende As Single, pfad As String
    Set cn = CreateObject("ADODB.Connection")
    cn.Open CONN_STR
    ende = Timer + maxSekunden
    Do
        Set rs = cn.Execute("SELECT Status, StatusMessage, OutputFileName, ZugferdFile " & _
                            "FROM dbo.tInvoice WHERE InvoiceId = " & id)
        Select Case rs!Status
            Case "OK"
                pfad = Environ("TEMP") & "\" & rs!OutputFileName
                DateiSchreiben pfad, rs!ZugferdFile
                ZugferdWarten = pfad
                Exit Do
            Case "FEHLER"
                Err.Raise vbObjectError + 2, , "E-Rechnung abgewiesen:" & vbCrLf & rs!StatusMessage
        End Select
        If Timer > ende Then Err.Raise vbObjectError + 3, , _
            "Datenmonster hat nach " & maxSekunden & " s noch nicht geantwortet"
        Pause 2
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

Private Sub DateiSchreiben(ByVal pfad As String, ByVal daten As Variant)
    Dim s As Object
    Set s = CreateObject("ADODB.Stream")
    s.Type = adTypeBinary
    s.Open
    s.Write daten
    s.SaveToFile pfad, adSaveCreateOverWrite
    s.Close
End Sub

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

**Kommt der Anstoß nicht an**, obwohl Datenmonster im Browser der Terminalsitzung
erreichbar ist: `WinHttpRequest` nutzt die Windows-Proxy-Einstellung (WinHTTP),
nicht die des Browsers. Nachsehen mit `netsh winhttp show proxy` in der
Terminalsitzung. Steht dort ein Proxy, braucht die Datenmonster-Adresse eine
Ausnahme. Die Meldung erscheint im Direktfenster (Strg + G).

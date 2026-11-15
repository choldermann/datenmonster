"""Projektwissen für microtech büro+ (Quelle: doku/bueroplus-wissen.md, Online-Hilfe Stand 11/2026).
Aufruf:
   docker compose cp doku/bueroplus_wissen_seed.py backend:/tmp/bp.py
   docker compose exec -e PYTHONPATH=/app backend python /tmp/bp.py
Wiederholbar: vorhandene Einträge (gleicher Titel) werden aktualisiert.
"""
from app.core.database import SessionLocal
from app.models.ai_memory import AiMemoryKnowledge as K

EINTRAEGE = [
 ("other", "microtech büro+ – Pakete und Zugriffswege auf die Daten",
  "microtech büro+ (auch 'microtech ERP', 'büro plus'). Erst Generation und Paket klären: bis 2023 Stufen "
  "M/L/XL/XXL, ab Gen. 24 Pakete Basic (199 EUR/Monat), Core (299 EUR), Enterprise (399 EUR), Version "
  "erkennbar am Zusatz '(G24)'. Zugriffswege: "
  "(1) SQL-Replikation nach PostgreSQL – nur Enterprise ab Build 6980, nur lesend, ideal für Cockpits. "
  "(2) GraphQL-API über HTTPS mit OAuth 2.0 – nur Enterprise ab Build 7076, lesen und schreiben, "
  "Endpunkt https://<server>/microtech/erp/mand/<MandNr>/graphql/v1. "
  "(3) ADO-Export direkt in SQL Server/Access/ODBC – zeitgesteuert per Automatisierungsaufgabe ab Core "
  "bzw. Gen. 20 XL; laut Hilfe 'werden keine Daten aktualisiert' (nur Anfügen) – Staging vor Lauf leeren. "
  "(4) Export-Layouts in Dateien (CSV, SDF = kommagetrennt, Excel, XML-Tags) – von Hand in allen Paketen, "
  "zeitgesteuert ab Core; passt zum Datenmonster-Hotfolder. "
  "(5) Ad-hoc-Export nach Excel: exportiert genau die Spalten der aktuellen Tabellenansicht. "
  "(6) COM-Aktiv (BpNT.Application) und mDL (nur lesende Abfragesprache, XML-Ergebnis) – nur Windows, "
  "laut microtech von GraphQL abgelöst. Datenbank-Engine intern ist NexusDB (BpServer) – kein direkter SQL-Zugriff."),

 ("table", "microtech büro+ – SQL-Replikation (PostgreSQL) Aufbau und Fallen",
  "büro+ repliziert die per Berechtigungsstruktur freigegebenen Tabellen (Vorgabe '(Standard-Replikation)') "
  "in ein frei benanntes Schema einer PostgreSQL-Datenbank; nach dem ersten Lauf nur geänderte Zeilen. "
  "Tabellennamen DEUTSCH wie im DB-Manager (z. B. artikel, Adressen, Anschriften). Verschachtelte Tabellen "
  "werden flach mit Endung abgelegt, z. B. artikel_ums = Artikelumsatz. Ab Schema-Version 1.1 stehen "
  "Selektionsfelder in <Tabelle>_Sel (Join über RefNr), ab 1.2 alle Texte als TEXT, ab 1.3 Überlauftabellen "
  "_1/_2/_3 bei mehr als 1600 Spalten. VK-Preise sind enthalten, BERECHNETE Felder NICHT. "
  "FALLEN: Bei jeder Strukturänderung wird die Tabelle komplett neu aufgebaut und eigene Views/Trigger darauf "
  "werden GELÖSCHT – eigene Views in eigenem Schema halten oder in der Prozedur <schema>.onAfterAll_ApplyNew() "
  "anlegen. RefNr, insertLSN und modifyLSN ändern sich bei Reorganisation – nie als Schlüssel speichern, "
  "fachliche Schlüssel nehmen (ArtNr, AdrNr, BelegNr). Replikation zeigt nur den AKTUELLEN Stand, keine Historie. "
  "PostgreSQL braucht max_locks_per_transaction=1024 (sonst 'EUniError Shared Memory aufgebraucht')."),

 ("table", "microtech büro+ – Datenmodell: wo stehen Artikel, Preise, Adressen, Vorgänge",
  "GraphQL-Namen englisch (Felder deutsch mit fld-Präfix), Replikation/DB-Manager deutsch. "
  "Artikel: tblProducts / artikel, Schlüssel ArtNr; LagNr, LiefNr (Standard-Lieferant), SuchBeg. "
  "VK-Preise: 3 bis 10 Preisstufen je Artikel im Artikelsatz (Felder Vk0_Preis ...), eine Stufe ist Standard, "
  "Adresse kann Preisstufe vorgeben; je Stufe Roherlös RohSz (%) und RohBet. Beträge sind netto ODER brutto "
  "gespeichert (GraphQL acoXxx.isCalculatedAndStoredAsGross). Ein 'Kundenpreis mit aller Preislogik' ist per "
  "API nicht abrufbar. "
  "Adressen: tblAddresses / Adressen (AdrNr, Status Kunde/Lieferant/Interessent) -> Anschriften "
  "tblPostalAddresses / Anschriften (AdrNr+AnsNr; Na2, Str, PLZ, Ort, Tel, EMail1; StdReKz/StdLiKz = "
  "Standard-Rechnungs-/Lieferanschrift) -> Ansprechpartner tblContactPeople (AdrNr+AnsNr+AspNr). "
  "Vorgänge: tblTransactions (BelegNr, Art = Vorgangsart-Nummer, DokGUID), Positionen tblTransactionItems "
  "(EPr Einzelpreis), Archiv tblTransactionsArchive (eigene Tabelle!). Lager: tblWarehouses (ArtNr+LagNr, "
  "Mge, MinMge). Offene Posten: tblOpenItems (Adresse -> lnkOpenItems -> rowBelegNr -> Vorgang). "
  "Dokumente/PDF: tblDocuments über DokGUID. Umsätze vorverdichtet in den Umsatz-Detailtabellen (*_ums) "
  "sowie ab Build 7285 'Verkaufsstatistik (Umsatz)' / 'Einkaufsstatistik (Umsatz)'. "
  "Exakte Spaltennamen immer am echten System prüfen."),

 ("rule", "microtech büro+ – Vorgangsarchiv: Umsatz immer aus Übersicht UND Archiv",
  "Vorgänge liegen in drei Registern: 'Vorgänge' (Übersicht), 'Zwischenbelege' und 'Archiv Vorgänge' "
  "(getrennte Tabelle). Was nach dem Buchen passiert, stellt der Kunde JE VORGANGSART in den "
  "Buchungsparametern ein: in Archiv VERSCHIEBEN, nach Zwischenbelege verschieben, in Archiv KOPIEREN "
  "(dann steht er in Übersicht UND Archiv) oder LÖSCHEN. Beim Wandeln: 'vor dem Wandeln in Vorgangsarchiv "
  "kopieren', Positionen verschieben (Quelle verschwindet, wenn nicht vorher archiviert) oder kopieren, "
  "'nach Komplettlieferung/letzter Teillieferung in Archiv kopieren'. Sammelrechnung: eingeladene Vorgänge "
  "ins Archiv verschieben oder LÖSCHEN. Zusätzlich AutoArchivierung nach Tagen (erledigt-Kennzeichen, läuft "
  "beim Wechsel des Arbeitsdatums). Aus dem Archiv geholte Vorgänge sind Kopien, teils mit NEUER Belegnummer. "
  "REGELN für Auswertungen: (1) Übersicht UNION ALL Archiv (und Zwischenbelege) lesen, nie nur eine Tabelle. "
  "(2) Nach BelegNr + Vorgangsart entdoppeln. (3) Angebote/Aufträge können fehlen (gelöscht/verschoben) – "
  "Umsatz auf Rechnungen und Gutschriften stützen. (4) Nur gebuchte Vorgänge zählen. (5) Vorgangsarten "
  "sind kundenindividuell – Zuordnung Art -> Angebot/Auftrag/Lieferschein/Rechnung/Gutschrift je Kunde klären. "
  "(6) Rechnung -> Gutschrift am selben Tag mit gleichem Betrag entfernt die Rechnung aus FiBu-Protokoll."),

 ("rule", "microtech büro+ – Warengruppe und EK in alten Belegen sind nicht historisch",
  "Die Warengruppe wird im Vorgang NICHT gespeichert. Auswertungen nach Warengruppe (auch microtechs eigene "
  "Verkaufsstatistik) nutzen die HEUTIGE Warengruppe des Artikels – nach Umgruppierungen historisch falsch; im "
  "Cockpit so kennzeichnen. Ist der Buchungsparameter 'Roherlös EK-Preise immer aktualisieren' bzw. "
  "'Kalkulations EK-Preise immer aktualisieren' gesetzt, kann der EK in alten Vorgängen beim Öffnen "
  "überschrieben werden – Margen alter Belege sind dann nicht mehr die damaligen. Der Roherlös einer Position "
  "rechnet mit dem Feld 'EK für Roherlöse' aus dem Artikel (z. B. mittlerer EK), nicht mit dem EK der "
  "Lagercharge."),

 ("rule", "microtech büro+ – Quellen für historische EK- und VK-Preise (Preisverlauf)",
  "(1) Tabelle 'Artikel-Preisverlauf': VK je Preisgruppe und Tag, Sonderpreise als eigener Satz; ab Build "
  "6810, XL bzw. Core+. Füllt sich NUR, wenn die Automatisierungsaufgabe 'Überwachung für Artikel-Preisverlauf' "
  "dauerhaft läuft – keine Rückwirkung, kein EK. Funktion CalcNiedrigsterPreis(ArtNr|Tage) für PAngV. "
  "(2) Erzielter VK rückwirkend aus Rechnungs-/Gutschriftspositionen (EPr, Belegdatum), Übersicht + Archiv. "
  "(3) EK rückwirkend aus Einkaufsvorgängen (Bestellung, Wareneingang, Eingangsrechnung). "
  "(4) Lagerbuch (ab XL): je Bewegung 'Einzel-Einkaufspreis' (EK zum Zeitpunkt) und 'Einkaufswert' "
  "(mittlerer EK nach Bewegung x Menge) -> MEK-Verlauf. (5) Lagerbestand mit EK: je Zugang eigener "
  "Bestandssatz (FIFO). (6) History: Zu-/Abgänge, nur wenn Vorgangsart und Artikel dafür eingestellt sind. "
  "(7) Artikelstamm/Replikation zeigt nur aktuelle Preise – für einen Verlauf ab jetzt täglich Schnappschuss "
  "in Datenmonster speichern."),

 ("other", "microtech büro+ – GraphQL-API Grundlagen",
  "Präfixe: tbl Tabelle, rowRead (ein Satz, exactMatch/nearestMatch), rowsRead (Liste), conRead(first, after) "
  "(seitenweise mit pageInfo.endCursor), fld Feld, by Sortierfolge (byNr, byNrNum), kf1.. Schlüsselfeld, "
  "lnk Link auf verwandte Liste, row Verweis, aco Betragsgruppe (totalNetAmount, totalGrossAmount, "
  "totalTaxAmount), img Bild. Filter: fastFilter (auf dem Datenserver, schnell; eq, lt, gt, isNull ...) vs. "
  "slowFilter (flexibel, langsam, z. B. in, Teilstring). Änderungen erkennen: fldModifyLSN/fldInsertLSN je "
  "Top-Level-Tabelle (steigend); keine Webhooks/Subscriptions; structureTag ändert sich bei Strukturänderung "
  "-> gespeicherte LSNs verwerfen. Mutations transaktional (rowNew/rowSave), Vorgangsfunktionen fnPost "
  "(buchen), fnReverse (stornieren), fnConvert (wandeln), fnMoveToArchive, fnRestoreToTransactions. Kein Druck "
  "per API. Benutzer braucht Kennzeichen 'Zugriff über GraphQL erlaubt'; Rechte = Berechtigungsstruktur. "
  "Statusseite ohne Login: https://<server>/microtech/erp/mand/ (Accept: application/json)."),
]

db = SessionLocal()
neu = akt = 0
for kategorie, titel, inhalt in EINTRAEGE:
    row = db.query(K).filter(K.title == titel).first()
    if row:
        row.content, row.category, row.enabled = inhalt, kategorie, True
        akt += 1
    else:
        db.add(K(scope="global", scope_id=None, category=kategorie, title=titel,
                 content=inhalt, enabled=True, always_include=False))
        neu += 1
db.commit()
print(f"büro+-Wissen: {neu} neu, {akt} aktualisiert")

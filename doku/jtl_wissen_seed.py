# -*- coding: utf-8 -*-
"""Trägt die beim Bau der Template-Serie (Vertrieb, Einkauf, Versand, Health-Check)
gegen die echte JTL-DB verifizierten Erkenntnisse in die KI-Wissensdatenbank ein.
Upsert nach Titel – wiederholter Lauf aktualisiert, statt zu doppeln."""
import sys
sys.path.insert(0, "/app")
from app.core.database import SessionLocal
from app.models.ai_memory import AiMemoryKnowledge as K

EINTRAEGE = [
    # ── Vertrieb / Aufträge & Angebote ──────────────────────────────────────
    ("table", "JTL – Aufträge und Angebote (Verkauf.tAuftrag)",
     "Aufträge UND Angebote liegen in derselben Tabelle Verkauf.tAuftrag, unterschieden über "
     "nType: 0 = Angebot (Nummernkreis ANG-), 1 = Auftrag (AUF-). Immer auf nType filtern, "
     "sonst mischen sich beide. Storno: nStorno (bit) – für Auftragseingang nStorno = 0 "
     "verlangen. Weitere Merker: nKomplettAusgeliefert (offene Aufträge), "
     "dVoraussichtlichesLieferdatum (Liefertermin), kPlattform (Verkaufskanal). "
     "Auftragseingang ist der Frühindikator VOR der Rechnung – für Vertriebsauswertungen "
     "besser geeignet als Rechnungsumsatz."),

    ("field_mapping", "JTL – Auftragswerte aus Verkauf.tAuftragEckdaten",
     "Werte eines Auftrags NICHT aus den Positionen summieren, sondern aus "
     "Verkauf.tAuftragEckdaten (Join kAuftrag): fWertNetto / fWertBrutto (Auftragswert), "
     "fOffenerWert (noch offen), nLieferstatus (5 = komplett geliefert, 3 = teilgeliefert, "
     "0 = offen), nAnzahlPakete, dBezahlt. Positionen (Verkauf.tAuftragPosition, nType = 1 für "
     "Artikelpositionen) nur für Artikel-/Mengenauswertungen verwenden."),

    ("rule", "JTL – Keine Verknüpfung Angebot → Auftrag",
     "Es gibt in der JTL-DB KEINE Verknüpfung zwischen Angebot und daraus entstandenem Auftrag: "
     "kAuftragQuelle ist praktisch immer NULL, die Nummernkreise ANG-/AUF- sind getrennt, und "
     "ein gewandeltes Angebot behält seine ANG-Nummer nicht. Eine Angebots-Conversion kann "
     "deshalb nur als HEURISTIK berechnet werden (z. B. Auftrag desselben Kunden binnen "
     "60 Tagen nach Angebotsdatum) – und muss im Widget als Näherung gekennzeichnet werden."),

    ("field_mapping", "JTL – Kundenname bei Aufträgen",
     "Kundenname zu einem Auftrag über die View Verkauf.vAuftragRechnungsadresse (Join kAuftrag): "
     "cFirma, sonst cVorname + cName. Analog zu Rechnung.vRechnungRechnungsadresse bei "
     "Rechnungen. dbo.tkunde enthält KEINE Namensfelder – die stehen in dbo.tAdresse "
     "(nStandard = 1 für die Standardadresse, dort auch cMail, cTel, cUSTID)."),

    # ── Einkauf ─────────────────────────────────────────────────────────────
    ("table", "JTL – Einkauf: Bestellungen & Bestellwert",
     "Lieferantenbestellungen: dbo.tLieferantenBestellung (Kopf: kLieferant, dErstellt, "
     "dLieferdatum = Soll-Termin, nDeleted, nManuellAbgeschlossen, cEigeneBestellnummer) + "
     "dbo.tLieferantenBestellungPos (fMenge, fEKNetto, fMengeGeliefert, fAnzahlOffen). "
     "Bestellwert = SUM(fMenge * fEKNetto) über die Positionen. Lieferantenname aus "
     "dbo.tlieferant.cFirma (Achtung: Tabellenname klein geschrieben)."),

    ("rule", "JTL – Offene Bestellungen: nStatus ist unbrauchbar",
     "Ob eine Lieferantenbestellung offen ist, NICHT über nStatus bestimmen – auch Bestellungen "
     "mit dem dominanten Status 500 haben noch offene Restmengen. Verlässlich ist: "
     "EXISTS(Position mit fAnzahlOffen > 0) AND ISNULL(nDeleted,0)=0 AND "
     "ISNULL(nManuellAbgeschlossen,0)=0. Offener Wert = SUM(fAnzahlOffen * fEKNetto). "
     "Praxis-Hinweis: sehr alte offene Bestellungen sind meist Karteileichen (nie manuell "
     "abgeschlossen) und verzerren Durchschnitts-Verzugswerte massiv."),

    ("table", "JTL – Wareneingang & Termintreue (tWarenLagerEingang)",
     "dbo.tWarenLagerEingang ist der echte Wareneingang und verweist über "
     "kLieferantenBestellungPos direkt auf die Bestellposition; Datumsfelder dGeliefertAM "
     "(bevorzugt) bzw. dErstellt, Menge fAnzahl, Preis fEKEinzel. Damit ist Termintreue echt "
     "messbar: Ist-Termin = MIN(ISNULL(dGeliefertAM, dErstellt)) je Bestellung, Soll-Termin = "
     "tLieferantenBestellung.dLieferdatum, Verzug = DATEDIFF(DAY, Soll, Ist), Lieferzeit = "
     "DATEDIFF(DAY, Bestelldatum, Ist). Nur Bestellungen mit gesetztem dLieferdatum auswerten."),

    ("table", "JTL – Eingangsrechnungen & Verbindlichkeiten",
     "dbo.tEingangsrechnung (kLieferant, dBelegdatum, dZahlungsziel, dBezahlt, nDeleted, "
     "cFremdbelegnummer = Rechnungsnummer des Lieferanten) + dbo.tEingangsrechnungPos "
     "(fMenge, fEKNetto, kLieferantenbestellung für die Zuordnung zur Bestellung). "
     "Rechnungsbetrag = SUM(fMenge * fEKNetto). Offen = dBezahlt IS NULL, überfällig = "
     "dZahlungsziel < GETDATE()."),

    # ── Versand ─────────────────────────────────────────────────────────────
    ("rule", "JTL – Versanddienstleister steht in der Versandart",
     "dbo.tVersand.cLogistiker ist in der Praxis durchgängig LEER – nicht dafür verwenden. Der "
     "Dienstleister ergibt sich aus dbo.tVersandArt.cName (Join über kVersandArt), z. B. "
     "'GLS auto', 'DHL', 'Selbstabholer', 'Speditionsdirektfahrt'. Tracking-Nummer = "
     "tVersand.cIdentCode; sie fehlt systematisch bei Selbstabholern und Spedition. Eine "
     "Auswertung 'Sendungen ohne Tracking' sollte deshalb nur Versandarten betrachten, die "
     "sonst überwiegend eine Tracking-Nummer tragen."),

    ("table", "JTL – Versandkette Auftrag → Lieferschein → Sendung",
     "Verknüpfung: dbo.tVersand.kLieferschein → dbo.tLieferschein.kLieferschein, und "
     "dbo.tLieferschein.kBestellung = Verkauf.tAuftrag.kAuftrag (Feldname 'kBestellung' meint "
     "den Auftrag!). Versanddatum: tVersand.dVersendet bzw. tLieferscheinEckdaten.dVersendet "
     "(dort auch nAnzahlPakete, fVersandGewicht). Durchlaufzeit = DATEDIFF(HOUR, "
     "tAuftrag.dErstellt, tVersand.dVersendet). Lieferscheine ohne dVersendet = Versandrückstand."),

    # ── Stammdatenqualität ──────────────────────────────────────────────────
    ("rule", "JTL – Prüfbasis für Stammdaten-Checks",
     "Für Datenqualitäts-Prüfungen auf Artikel gilt als Prüfbasis: ISNULL(nDelete,0)=0 AND "
     "ISNULL(cAktiv,'Y')='Y' AND ISNULL(nIstVater,0)=0 – Vater-Artikel tragen selbst keine "
     "EAN/Gewichte und würden die Quoten verfälschen. Relevante Felder in dbo.tArtikel: "
     "cBarcode (EAN), fGewicht/fArtGewicht, fEKNetto/fVKNetto/fLetzterEK, kWarengruppe, "
     "cTaric (Warentarifnummer), cHerkunftsland, cHAN, kHersteller. Artikelname weiterhin aus "
     "dbo.tArtikelBeschreibung. Kunden: dbo.tkunde + dbo.tAdresse (nStandard = 1), gesperrt via "
     "tkunde.cSperre."),

    ("rule", "JTL – Bundesland aus PLZ herleiten (Vertriebsregionen)",
     "JTL füllt cBundesland in den Adressen nicht – das Bundesland muss aus LEFT(cPLZ,2) über "
     "eine CASE-Klassifikation hergeleitet werden (Referenz: Mappings 'Cockpit – Umsatz nach "
     "Region' und 'Vertrieb – Auftragseingang je Bundesland', identische Zuordnung verwenden, "
     "damit Auswertungen vergleichbar bleiben). Vorher auf Inland prüfen "
     "(UPPER(cLand) IN ('','DE','D','DEU','DEUTSCHLAND','GERMANY')), sonst '(Ausland)'. "
     "Adressquelle: Verkauf.vAuftragRechnungsadresse bzw. Rechnung.vRechnungRechnungsadresse."),

    ("rule", "Vertrieb – Marktdurchdringung je Bundesland",
     "Schwachstellen in Regionen erkennt man über den Vergleich Umsatzanteil zu "
     "Bevölkerungsanteil des Bundeslands (Einwohneranteile fest hinterlegt, Destatis 2024). "
     "Marktdurchdringung = Umsatzanteil / Bevölkerungsanteil: 1,0 = so stark vertreten wie die "
     "Region groß ist, unter 0,8 unterrepräsentiert, unter 0,5 deutlich unterrepräsentiert. "
     "Zusatzpotenzial = (Bevölkerungsanteil − Umsatzanteil)/100 × Inlandsumsatz. WICHTIG: Das "
     "ist ein FAKTOR, kein Prozentwert – in KI-Prompts ausdrücklich erklären, sonst formulieren "
     "Modelle '0,2 Prozent Marktdurchdringung'. Die Kennzahl ist eine Orientierung, kein echter "
     "Marktanteil (Branchenschwerpunkte weichen regional ab)."),

    ("rule", "KI-Handlungsempfehlung: Kandidaten aus dem SQL vorgeben",
     "Bei KI-Empfehlungen zu Regionen/Kunden immer die konkreten Namen (Betrieb, Ort, "
     "Rückgangsbetrag) als fertige Liste aus dem SQL mitgeben – z. B. per FOR XML PATH "
     "aggregiert – und dem Modell verbieten, Namen zu erfinden. Alle Kennzahlen werden "
     "serverseitig deterministisch berechnet (/api/ai/recommend-action, Arten "
     "customer_winback / article_liquidation / region_potential) und als meta-Event "
     "vorab gesendet; das Modell formuliert nur die Prosa."),

    # ── T-SQL-Fallen ────────────────────────────────────────────────────────
    ("rule", "T-SQL – Kein Aggregat über Unterabfrage oder Fensterfunktion",
     "SQL Server lehnt SUM/AVG über einen Ausdruck ab, der eine Unterabfrage oder eine "
     "Fensterfunktion enthält (Fehler 130: 'Eine Aggregatfunktion kann auf einem Ausdruck, der "
     "ein Aggregat oder eine Unterabfrage enthält, nicht ausgeführt werden'). Typische Fälle: "
     "SUM(CASE WHEN EXISTS(...) THEN 1 END) oder MAX(CASE WHEN d = MAX(d) OVER (...) THEN x END). "
     "Lösung: den Ausdruck in einer abgeleiteten Tabelle/CTE als Spalte vorberechnen (z. B. "
     "CASE WHEN EXISTS(...) THEN 1 ELSE 0 END AS Flag bzw. ROW_NUMBER() OVER (...) AS rn) und "
     "erst in der äußeren Abfrage aggregieren."),
    ("fact", "JTL – cHAN ist oft die eigene Artikelnummer, keine Herstellernummer",
     "In tArtikel.cHAN steht bei vielen Beständen nicht die Nummer des Herstellers, sondern eine "
     "Kopie der eigenen cArtNr (gemessen: 1.510 von 2.818 aktiven Artikeln). Für Abgleiche mit "
     "Herstellerdaten ist cHAN deshalb nur brauchbar, wenn cHAN <> cArtNr gilt. Bei manchen "
     "Herstellern steht dort auch ein Produktname statt einer Nummer (z. B. 'rhenus FY 122 L'), "
     "und derselbe cHAN kann mehrere Artikel abdecken (Gebindegrößen, Farben, Konfektionsgrößen)."),

    ("fact", "JTL – Artikelbeschreibungen und ihre Felder",
     "Beschreibungstexte liegen in dbo.tArtikelBeschreibung: cName (Artikelname), cBeschreibung "
     "(Langtext) und cKurzBeschreibung. Join über kArtikel mit kSprache=1, kPlattform=1, kShop=0. "
     "In der Praxis enthält cKurzBeschreibung häufig die eigentlichen technischen Daten (Maße, "
     "Material, Verpackungsstaffel), während cBeschreibung leer ist — beim Erzeugen von Texten "
     "ist die Kurzbeschreibung deshalb die wichtigste Quelle im Artikelstamm."),

    ("rule", "JTL – Lagerbestand kommt aus tlagerbestand, nicht aus tArtikel",
     "tArtikel.nLagerbestand ist in lagergeführten Beständen durchgehend 0. Der reale Bestand "
     "steht in dbo.tlagerbestand und muss je Artikel summiert werden: "
     "(SELECT kArtikel, SUM(fLagerbestand) AS Bestand FROM dbo.tlagerbestand GROUP BY kArtikel). "
     "Gilt für alle Auswertungen, die nach Bestand priorisieren oder Kapitalbindung rechnen."),

    ("rule", "JTL – Pflichtfelder der Intrastat-Meldung im Artikelstamm",
     "Eine Intrastat-Meldezeile braucht drei Angaben aus dbo.tArtikel: cTaric (achtstellige "
     "Warennummer der Kombinierten Nomenklatur), cHerkunftsland (Ursprungsland, seit 2022 auch "
     "bei der Versendung Pflicht) und das Gewicht als Eigenmasse — dabei fGewicht prüfen und auf "
     "fArtGewicht ausweichen, denn gepflegt ist mal das eine, mal das andere. Fehlt eines davon, "
     "ist die Zeile nicht meldefähig. Artikel mit cHerkunftsland NOT IN ('', 'DE') sind die "
     "vorrangigen Kandidaten für die Pflege."),

    ("rule", "Mapping – Ziel ohne Feldliste erzeugt leere Zeilen",
     "Wird ein Mapping per Skript angelegt und bekommt targets[0].fields nicht gefüllt, liefert "
     "execute_mapping zu jeder echten Zeile eine zusätzliche leere ({}). Die Feldliste muss je "
     "Ausgabespalte einen Eintrag haben: source_field/target_field = Spaltenname, target_type "
     "'string' bzw. 'float', source_dataset_id '__sql__<knoten-id>' und transformer "
     "{'type':'direct','source_field': <name>}. Zusätzlich deckelt execute_mapping Vorschauläufe "
     "hart auf 50 Zeilen — für vollständige Listen row_cap übergeben."),
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
                 content=inhalt, enabled=True))
        neu += 1
db.commit()
print(f"Wissensdatenbank: {neu} neu, {akt} aktualisiert, gesamt {db.query(K).count()} Einträge")

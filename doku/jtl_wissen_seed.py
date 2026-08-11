# -*- coding: utf-8 -*-
"""Trägt die beim Bau der Template-Serie (Vertrieb, Einkauf, Versand, Health-Check,
Lager) gegen die echte JTL-DB verifizierten Erkenntnisse in die KI-Wissensdatenbank
ein. Upsert nach Titel – wiederholter Lauf aktualisiert, statt zu doppeln."""
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

    # ── Lager: Bestandshistorie ─────────────────────────────────────────────
    ("table", "JTL – Bestandshistorie liegt in dbo.vArtikelHistorie",
     "Die Lagerbewegungen stehen in der View dbo.vArtikelHistorie. Eine Tabelle "
     "dbo.tLagerbewegung gibt es NICHT – wer danach sucht, hält die Bestandshistorie "
     "fälschlich für nicht vorhanden. Spalten: dGebucht, cTyp (Eingang/Ausgang), kArtikel, "
     "fAnzahl (VORZEICHENBEHAFTET, Ausgang negativ), cBuchungsart/kBuchungsart, "
     "fLagerBestandGesamt (laufender Bestand nach der Buchung), fLagerBestandPlatz, "
     "kWarenLagerPlatz, fEKNetto (EK zum Buchungszeitpunkt), kBenutzer, cChargenNr, dMHD "
     "sowie die Verknüpfungen kAuftragPos, kLieferscheinPos, kLieferantenBestellungPos, "
     "kWarenLagerEingang, cLieferscheinNr."),

    ("rule", "JTL – Bestand zu einem Stichtag rekonstruieren",
     "Bestand(Stichtag) = SUM(fAnzahl) aus dbo.vArtikelHistorie WHERE dGebucht < "
     "DATEADD(DAY,1,:stichtag), gruppiert je kArtikel. Gegen die echte DB geprüft: das "
     "Ergebnis deckt sich bei 2817 von 2817 aktiven Artikeln exakt mit "
     "dbo.tlagerbestand.fLagerbestand (Toleranz 0,01). Damit sind Stichtagsbewertung, "
     "Lagerwertverlauf und Umschlag aus echten Warenausgängen möglich. Für eine Monatskurve "
     "die Stichtage als kleine Monats-CTE erzeugen und per CROSS APPLY je Stichtag "
     "aggregieren – 12 Stichtage laufen in rund zwei Sekunden."),

    ("rule", "JTL – Lagerbewertung zum historischen Einkaufspreis",
     "Für stichtagsfeste Zahlen NICHT mit tArtikel.fEKNetto rechnen (der ändert rückwirkend "
     "die Vergangenheit), sondern mit dem historischen EK: für BESTÄNDE der fEKNetto der "
     "letzten Eingangsbuchung bis zum Stichtag (ROW_NUMBER() OVER (PARTITION BY kArtikel "
     "ORDER BY dGebucht DESC) über cTyp='Eingang' AND fEKNetto>0), für BEWEGUNGEN der "
     "fEKNetto der Buchungszeile selbst. Fallback nur, wenn nie ein EK gebucht wurde: "
     "COALESCE(hist.fEKNetto, A.fEKNetto, 0) – und die Zahl der Fallback-Fälle als eigene "
     "Kennzahl ausweisen. fEKNetto ist auf 98–99 % der Zeilen gefüllt. Größenordnung des "
     "Unterschieds an der Prüf-DB: 862 T€ historisch gegen 840 T€ mit heutigem EK."),

    ("fact", "JTL – Buchungsarten der Bestandshistorie",
     "cBuchungsart in dbo.vArtikelHistorie: Warenausgang und Wareneingang (die Masse), "
     "Korrekturbuchung, Lagerumbuchung, 'JTL-Ameise Import', Inventurdifferenzbuchung, "
     "Retouren, Sonstige. Korrekturbuchung und Inventurdifferenzbuchung sind GETRENNTE "
     "Arten – für Schwund/Inventur beide zusammen auswerten. Lagerumbuchungen erzeugen je "
     "eine Ein- und eine Ausgangszeile, die sich in der Summe exakt aufheben; sie "
     "verfälschen den Bestand also nicht, sind aber aus Bewegungsanalysen auszuschließen. "
     "Ein dauerhaft negativer Korrektursaldo ist ein Hinweis auf Schwund oder Pflegefehler, "
     "keine Buchungsgröße für die Buchhaltung."),

    ("field_mapping", "JTL – Bestand je Warenlager",
     "Ein Lagerbezug fehlt in dbo.tlagerbestand (dort steht der Bestand nur je Artikel). Je "
     "Lager geht es über die Historie: dbo.vArtikelHistorie.kWarenLagerPlatz → "
     "dbo.tWarenLagerPlatz.kWarenLager → dbo.tWarenLager.cName. In der Praxis liegt fast "
     "alles im 'Standardlager', daneben existieren kleine Außen-/Kommissionslager."),

    ("table", "JTL – Dispositionsdaten in dbo.tlagerbestand",
     "dbo.tlagerbestand führt je Artikel nicht nur fLagerbestand, sondern die ganze "
     "Dispositionssicht: fVerfuegbar (frei verfügbar), fInAuftraegen (reserviert), fZulauf "
     "(aus offenen Bestellungen erwartet), fAufEinkaufsliste, dLieferdatum (erwarteter "
     "Zulauftermin), fLagerbestandEigen. Fehlmenge = fInAuftraegen > fLagerbestand, "
     "überreserviert = fVerfuegbar < 0. WICHTIG: Diese Felder gibt es NUR als aktuellen "
     "Stand, nicht in der Historie – Dispo-Auswertungen sind damit immer Momentaufnahmen "
     "und dürfen keinen Zeitraumfilter vortäuschen."),

    ("fact", "JTL – Stolperfelder im Artikelstamm (Lager)",
     "dbo.tArtikel.nMidestbestand ist im JTL-Schema FALSCH GESCHRIEBEN (kein 'n' nach 'Mi') "
     "– 'nMindestbestand' gibt es nicht. Zudem ist das Feld meist kaum gepflegt (an der "
     "Prüf-DB 149 von 2817 Artikeln), taugt also als Zusatzspalte, nicht als tragende "
     "Auswertung. cLagerArtikel = 'Y' trifft dort 0 Artikel und ist als Filter für "
     "'Lagerartikel' unbrauchbar."),

    ("rule", "JTL – EK-Preisverlauf eines Artikels gegen den VK",
     "Preisverlauf je Artikel aus den Eingangsbuchungen: je Monatsstichtag den zuletzt "
     "gebuchten fEKNetto per TOP 1 ... ORDER BY dGebucht DESC fortschreiben (sonst entstehen "
     "Lücken in Monaten ohne Wareneingang). Den Verkaufspreis daneben als AVG(POS.fVkNetto) "
     "der im selben Monat berechneten Rechnungspositionen; Monate ohne Verkauf bleiben leer. "
     "Beide Reihen in einem Liniendiagramm zeigen die Margenentwicklung. Den Lieferanten zu "
     "einer Eingangsbuchung über kLieferantenBestellungPos → tLieferantenBestellung → "
     "tlieferant auflösen."),

    # ── Datenmonster: Drilldown-Bau ─────────────────────────────────────────
    ("rule", "Dashboard – Drilldown verdrahten (Schlüsselspalte, Fallen)",
     "Ein Tabellen-Drilldown braucht config.drilldown = {mapping_id, key_column, param, title, "
     "hidden_columns?, levels?[]} und eine SCHLÜSSELSPALTE in der Liste (kKunde, kAuftrag, "
     "kLieferant …), die per config.hidden_columns ausgeblendet wird – sie bleibt in den "
     "Zeilendaten erhalten und taucht in CSV/E-Mail/PDF nicht auf. Drei Fallen: (1) Die "
     "Schlüsselspalte IMMER hinten anhängen, weil manche Listen über Spaltennummern sortieren "
     "(ORDER BY 7 DESC). (2) Bei Unterabfragen/CTEs muss der Schlüssel von innen nach außen "
     "durchgereicht werden – zwei Stellen. (3) Ist am selben Widget config.ai_action gesetzt, "
     "schluckt die KI-Aktion den Zeilenklick; ein zusätzlicher Drilldown wäre tote "
     "Konfiguration."),

    ("rule", "Mapping – row_cap hebt hartkodierte TOP-Werte an",
     "_apply_row_cap deckelt nicht nur, es HEBT ein TOP N im SQL auf row_cap AN. Ein 'SELECT "
     "TOP 50' in einem Detail-Mapping ist deshalb nur beratend – der Drilldown-Endpunkt ruft "
     "mit row_cap 200 auf und bekommt bis zu 200 Zeilen. Wer wirklich begrenzen will, muss im "
     "SQL filtern (WHERE/HAVING), nicht über TOP."),

    ("rule", "Datenmonster – Formulare beim Template-Install nicht überschrieben",
     "Der Template-Installer gleicht MAPPINGS über den Namen ab und bringt sie auf den Stand "
     "des Templates. Gleichnamige FORMULARE lässt er dagegen unangetastet, damit im Betrieb "
     "ergänzte Reiter und Widgets nicht verloren gehen. Folge: Änderungen an der Verdrahtung "
     "eines bereits installierten Dashboards (neue Drilldowns, neue Widgets) müssen direkt am "
     "Formular gepatcht werden – ein erneuter Template-Install genügt nicht. Deshalb "
     "Mappings, die sich mehrere Cockpits teilen, neutral benennen (z. B. 'Cockpit – "
     "Auftragspositionen (Detail)' statt 'Vertrieb – …'), sonst legt der Installer Doppel an."),
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

"""Die erfundene Welt: Medizin- und Praxisbedarf.

Orte/PLZ sind echte Paare (die Cockpits leiten das Bundesland aus der PLZ ab),
alles andere ist erfunden. Mailadressen nur unter den reservierten Domains
example.com/.org/.net (RFC 2606), Telefonnummern im fiktiven Bereich 0xxxx-99….
"""

FIRMA = dict(cName="MediVersa Praxisbedarf GmbH", cStrasse="Am Demopark 7", cPLZ="70173",
             cOrt="Stuttgart", cLand="Deutschland", cLandISO="DE", cTel="0711 99000-0",
             cFax="0711 99000-99", cEMail="info@mediversa.example.com", cInet="www.mediversa.example.com",
             cSteuerNr="99/999/99999", cUSTID="DE999999999")

BENUTZER = ["Sabine Demo", "Thomas Beispiel", "Julia Muster", "Lager Terminal", "Webshop"]

ORTE = [  # (PLZ, Ort) – über alle Bundesländer verteilt
    ("10115", "Berlin"), ("10969", "Berlin"), ("12049", "Berlin"), ("13353", "Berlin"), ("14467", "Potsdam"),
    ("03046", "Cottbus"), ("15230", "Frankfurt (Oder)"), ("20095", "Hamburg"), ("22767", "Hamburg"),
    ("21073", "Hamburg"), ("24103", "Kiel"), ("23552", "Lübeck"), ("24937", "Flensburg"), ("18055", "Rostock"),
    ("19053", "Schwerin"), ("17489", "Greifswald"), ("28195", "Bremen"), ("27568", "Bremerhaven"),
    ("30159", "Hannover"), ("38100", "Braunschweig"), ("26122", "Oldenburg"), ("49074", "Osnabrück"),
    ("37073", "Göttingen"), ("21335", "Lüneburg"), ("39104", "Magdeburg"), ("06108", "Halle (Saale)"),
    ("06844", "Dessau-Roßlau"), ("01067", "Dresden"), ("04109", "Leipzig"), ("09111", "Chemnitz"),
    ("08056", "Zwickau"), ("99084", "Erfurt"), ("07743", "Jena"), ("99423", "Weimar"), ("40210", "Düsseldorf"),
    ("50667", "Köln"), ("50937", "Köln"), ("44135", "Dortmund"), ("45127", "Essen"), ("47051", "Duisburg"),
    ("44787", "Bochum"), ("42103", "Wuppertal"), ("33602", "Bielefeld"), ("48143", "Münster"),
    ("53111", "Bonn"), ("52062", "Aachen"), ("41061", "Mönchengladbach"), ("57072", "Siegen"),
    ("32423", "Minden"), ("59065", "Hamm"), ("60311", "Frankfurt am Main"), ("60487", "Frankfurt am Main"),
    ("65183", "Wiesbaden"), ("64283", "Darmstadt"), ("34117", "Kassel"), ("35037", "Marburg"),
    ("36037", "Fulda"), ("63065", "Offenbach am Main"), ("55116", "Mainz"), ("67059", "Ludwigshafen am Rhein"),
    ("56068", "Koblenz"), ("54290", "Trier"), ("67655", "Kaiserslautern"), ("66111", "Saarbrücken"),
    ("66763", "Dillingen/Saar"), ("70173", "Stuttgart"), ("70469", "Stuttgart"), ("68159", "Mannheim"),
    ("76133", "Karlsruhe"), ("79098", "Freiburg im Breisgau"), ("69117", "Heidelberg"), ("89073", "Ulm"),
    ("72070", "Tübingen"), ("75175", "Pforzheim"), ("78462", "Konstanz"), ("74072", "Heilbronn"),
    ("73728", "Esslingen am Neckar"), ("71638", "Ludwigsburg"), ("88212", "Ravensburg"), ("80331", "München"),
    ("80799", "München"), ("81369", "München"), ("90402", "Nürnberg"), ("86150", "Augsburg"),
    ("93047", "Regensburg"), ("97070", "Würzburg"), ("85049", "Ingolstadt"), ("91052", "Erlangen"),
    ("95444", "Bayreuth"), ("94032", "Passau"), ("84028", "Landshut"), ("87435", "Kempten (Allgäu)"),
    ("96047", "Bamberg"), ("83022", "Rosenheim"),
]
ORTE_AUSLAND = [("AT", "Österreich", "1010", "Wien"), ("AT", "Österreich", "5020", "Salzburg"),
                ("AT", "Österreich", "6020", "Innsbruck"), ("LU", "Luxemburg", "1009", "Luxembourg"),
                ("NL", "Niederlande", "6211", "Maastricht"), ("BE", "Belgien", "4700", "Eupen")]

STRASSEN = ["Lindenweg", "Am Mühlbach", "Gartenstraße", "Birkenallee", "Schulstraße", "Am Markt",
            "Kirchgasse", "Ahornring", "Sonnenhang", "Talstraße", "Rosenstraße", "Wiesenweg", "Bergstraße",
            "Am Stadtpark", "Uferweg", "Hauptstraße", "Feldstraße", "Brunnenstraße", "Waldweg", "Am Anger",
            "Eichendorffstraße", "Bahnhofsplatz", "Mozartweg", "Kastanienallee", "Im Winkel"]

VORNAMEN = ["Anna", "Lena", "Marie", "Sophie", "Laura", "Julia", "Sarah", "Katharina", "Hannah", "Lea",
            "Christina", "Sandra", "Nicole", "Petra", "Monika", "Claudia", "Andrea", "Stefanie", "Miriam", "Eva",
            "Lukas", "Jonas", "Felix", "Paul", "Maximilian", "Tobias", "Florian", "David", "Simon", "Jan",
            "Michael", "Thomas", "Andreas", "Stefan", "Markus", "Christian", "Martin", "Frank", "Peter", "Jens"]
NACHNAMEN = ["Brandt", "Lehmann", "Krüger", "Hoffmann", "Schuster", "Vogel", "Kaiser", "Busch", "Pohl",
             "Winkler", "Lorenz", "Seidel", "Engel", "Kraus", "Böhm", "Arnold", "Haas", "Lange", "Sommer",
             "Pfeiffer", "Franke", "Albrecht", "Schulte", "Graf", "Hahn", "Roth", "Beck", "Jung", "Kühn",
             "Ludwig", "Busse", "Thiel", "Ernst", "Heinrich", "Hartwig", "Reuter", "Marx", "Stein", "Fuchs",
             "Wolff", "Schreiber", "Günther", "Brenner", "Ziegler", "Kunz", "Voigt", "Möller", "Wagner"]

# Kundengruppen: (kKundenGruppe, Name, Rabatt %, Anteil an Kunden)
KUNDENGRUPPEN = [(1, "Endkunden", 0, 0.22), (2, "Arztpraxen", 3, 0.34), (3, "Zahnarztpraxen", 4, 0.16),
                 (4, "Pflege & Therapie", 2, 0.16), (5, "Kliniken & MVZ", 8, 0.07), (6, "Tierarztpraxen", 3, 0.05)]

PRAXISFORMEN = {
    2: ["Hausarztpraxis Dr. {n}", "Praxis Dr. med. {v} {n}", "Gemeinschaftspraxis {n} & {n2}",
        "Internistische Praxis Dr. {n}", "Kinderarztpraxis {n}", "Hautarztpraxis Dr. {n}", "Praxis am {s}"],
    3: ["Zahnarztpraxis Dr. {n}", "Zahnärzte {n} & {n2}", "Kieferorthopädie {n}", "Zahnzentrum {o}"],
    4: ["Pflegedienst {n}", "Physiotherapie {v} {n}", "Ergotherapie am {s}", "Ambulante Pflege {o}",
        "Seniorenresidenz am {s}", "Podologie {n}", "Hebammenpraxis {v} {n}"],
    5: ["MVZ {o} Mitte", "Tagesklinik {o}", "Medizinisches Versorgungszentrum {n}", "Ärztehaus {o}"],
    6: ["Tierarztpraxis Dr. {n}", "Kleintierpraxis {n}", "Tierklinik {o}"],
}

HERSTELLER = ["Nordamed", "Curaflex", "Hygisan", "Medilux", "Sterivo", "Praxomed", "Vitaplast", "Dentaro",
              "Klarsept", "Optimed Labs", "Bandavita", "Purigen"]

# Lieferanten: (Firma, Land-ISO, Ort, PLZ, Lieferzeit Tage, Anteil der Artikel)
LIEFERANTEN = [
    ("Medisupply Großhandel GmbH", "DE", "Hannover", "30159", 3),
    ("Hygiene-Partner Süd GmbH", "DE", "Augsburg", "86150", 4),
    ("Praxiswelt Logistik KG", "DE", "Köln", "50667", 2),
    ("Verbandstoff-Werk Rheinland GmbH", "DE", "Bonn", "53111", 6),
    ("Alpenmed Handels GmbH", "AT", "Salzburg", "5020", 7),
    ("Dutch Care Supplies B.V.", "NL", "Maastricht", "6211", 6),
    ("Polmed Distribution Sp. z o.o.", "PL", "Poznań", "61-001", 9),
    ("Dentalbedarf Ost GmbH", "DE", "Leipzig", "04109", 3),
    ("Diagnostik Direkt GmbH", "DE", "Frankfurt am Main", "60311", 2),
    ("Labortechnik Weser GmbH", "DE", "Bremen", "28195", 5),
    ("Einmalartikel Import GmbH", "DE", "Hamburg", "20095", 14),
    ("Desinfekt Chemie GmbH", "DE", "Mannheim", "68159", 5),
]

# Sortiment: (Warengruppe, [(Produktfamilie, Varianten, VK-Bereich netto, Marge-Ziel, Einheit,
#             Taric, Herkunft, Gewicht kg, Steuerklasse, MHD/Charge?)])
SORTIMENT = [
    ("Untersuchungshandschuhe", [
        ("Nitril-Untersuchungshandschuhe puderfrei, blau, 100 Stück", ["XS", "S", "M", "L", "XL"], (6.9, 9.9), 0.28, "Box", "40151900", "MY", 0.6, 1, False),
        ("Nitril-Handschuhe extra lang, schwarz, 100 Stück", ["S", "M", "L", "XL"], (11.5, 14.5), 0.30, "Box", "40151900", "TH", 0.7, 1, False),
        ("Latex-Untersuchungshandschuhe gepudert, 100 Stück", ["S", "M", "L"], (5.5, 7.5), 0.25, "Box", "40151100", "MY", 0.6, 1, False),
        ("Vinyl-Handschuhe transparent, 100 Stück", ["S", "M", "L", "XL"], (3.9, 5.4), 0.22, "Box", "39262000", "CN", 0.5, 1, False),
        ("OP-Handschuhe steril, Paar", ["6,5", "7", "7,5", "8", "8,5"], (0.85, 1.4), 0.34, "Paar", "40151100", "MY", 0.03, 1, True),
    ]),
    ("Desinfektion", [
        ("Händedesinfektion alkoholisch", ["500 ml", "1 l", "5 l Kanister"], (5.9, 39.0), 0.36, "Flasche", "38089490", "DE", 1.0, 1, True),
        ("Flächendesinfektion alkoholfrei", ["1 l", "5 l Kanister"], (8.9, 42.0), 0.38, "Flasche", "38089490", "DE", 1.2, 1, True),
        ("Desinfektionstücher Spenderdose, 100 Tücher", ["Standard", "Sensitiv"], (7.4, 9.8), 0.40, "Dose", "38089490", "DE", 0.5, 1, True),
        ("Instrumentendesinfektion Konzentrat", ["2 l", "5 l"], (24.0, 59.0), 0.35, "Flasche", "38089490", "AT", 2.5, 1, True),
        ("Hautantiseptikum farblos", ["250 ml", "1 l"], (4.9, 13.5), 0.37, "Flasche", "30049000", "DE", 0.6, 1, True),
    ]),
    ("Verbandmaterial", [
        ("Kompressen steril 10 x 10 cm, 25 x 2 Stück", ["8-fach", "12-fach"], (4.2, 5.9), 0.42, "Pack", "30059099", "DE", 0.25, 1, True),
        ("Fixierpflaster Rolle", ["2,5 cm x 5 m", "5 cm x 5 m", "10 cm x 10 m"], (1.9, 8.9), 0.45, "Rolle", "30051000", "DE", 0.1, 1, False),
        ("Wundschnellverband Strips, 100 Stück", ["Textil", "wasserfest"], (3.5, 4.9), 0.48, "Box", "30051000", "PL", 0.15, 1, False),
        ("Mullbinden elastisch, 20 Stück", ["6 cm", "8 cm", "10 cm"], (6.9, 11.0), 0.40, "Pack", "30059031", "PL", 0.6, 1, False),
        ("Wundauflage Schaumstoff steril, 10 Stück", ["7,5 x 7,5 cm", "10 x 10 cm", "15 x 15 cm"], (18.0, 39.0), 0.33, "Pack", "30059099", "NL", 0.2, 1, True),
    ]),
    ("Spritzen & Kanülen", [
        ("Einmalspritzen 2-teilig, 100 Stück", ["2 ml", "5 ml", "10 ml", "20 ml"], (4.9, 11.9), 0.30, "Box", "90183110", "DE", 0.7, 1, True),
        ("Einmalkanülen, 100 Stück", ["0,45 x 25 mm", "0,6 x 30 mm", "0,8 x 40 mm", "0,9 x 40 mm"], (2.9, 4.2), 0.32, "Box", "90183210", "DE", 0.2, 1, True),
        ("Insulinspritzen 1 ml mit Kanüle, 100 Stück", ["U-40", "U-100"], (14.0, 17.5), 0.27, "Box", "90183110", "IE", 0.4, 1, True),
        ("Kanülenabwurfbehälter", ["0,7 l", "1,5 l", "3 l"], (1.6, 3.9), 0.44, "Stück", "39231090", "DE", 0.25, 1, False),
    ]),
    ("Diagnostik", [
        ("Blutzuckerteststreifen, 50 Stück", ["Standard"], (14.5, 16.9), 0.26, "Pack", "38220000", "DE", 0.1, 1, True),
        ("Urinteststreifen 10 Parameter, 100 Stück", ["Standard"], (19.0, 24.0), 0.30, "Dose", "38220000", "CN", 0.15, 1, True),
        ("Fieberthermometer digital", ["Standard", "flexible Spitze"], (3.9, 6.9), 0.42, "Stück", "90251180", "CN", 0.05, 1, False),
        ("Blutdruckmessgerät Oberarm", ["Standard", "mit Großmanschette"], (29.0, 49.0), 0.31, "Stück", "90189084", "CN", 0.6, 1, False),
        ("Pulsoximeter Finger", ["Standard"], (19.0, 24.0), 0.38, "Stück", "90189084", "CN", 0.1, 1, False),
        ("Stethoskop Doppelkopf", ["schwarz", "blau", "bordeaux"], (24.0, 39.0), 0.35, "Stück", "90189084", "PK", 0.2, 1, False),
    ]),
    ("Praxishygiene & Einmalartikel", [
        ("Untersuchungsliegen-Papier, 2-lagig, 6 Rollen", ["39 cm", "50 cm", "59 cm"], (16.9, 26.0), 0.34, "Karton", "48183000", "DE", 4.5, 1, False),
        ("Mund-Nasen-Schutz Typ IIR, 50 Stück", ["blau", "weiß"], (3.9, 6.9), 0.40, "Box", "63079098", "CN", 0.3, 1, False),
        ("FFP2-Atemschutzmasken, 20 Stück", ["Standard"], (6.9, 9.9), 0.38, "Box", "63079098", "CN", 0.2, 1, False),
        ("Einmal-Schutzkittel, 10 Stück", ["M", "L", "XL"], (8.9, 12.9), 0.36, "Pack", "62101098", "CN", 0.6, 1, False),
        ("Zellstofftupfer unsteril, 4 x 500 Stück", ["4 x 5 cm"], (6.4, 7.9), 0.41, "Pack", "48189090", "DE", 0.9, 1, False),
        ("Papierhandtücher Zickzack, 3.200 Blatt", ["grün", "hochweiß"], (19.0, 29.0), 0.30, "Karton", "48182010", "DE", 6.0, 1, False),
    ]),
    ("Dentalbedarf", [
        ("Speichelsauger flexibel, 100 Stück", ["blau", "weiß", "transparent"], (2.9, 3.8), 0.46, "Pack", "90184990", "IT", 0.25, 1, False),
        ("Dental-Servietten 3-lagig, 500 Stück", ["blau", "grün", "rosa"], (11.0, 14.0), 0.38, "Karton", "48183000", "DE", 2.6, 1, False),
        ("Abformlöffel Einweg, 12 Stück", ["OK", "UK"], (9.5, 12.0), 0.37, "Pack", "90184990", "IT", 0.3, 1, False),
        ("Prophylaxepaste Becher", ["Minze", "Erdbeere", "Kirsche"], (15.0, 18.0), 0.35, "Stück", "33069000", "CH", 0.3, 1, True),
    ]),
    ("Instrumente & Praxisausstattung", [
        ("Pinzette anatomisch Edelstahl", ["11,5 cm", "14,5 cm"], (3.9, 6.5), 0.48, "Stück", "90189084", "PK", 0.05, 1, False),
        ("Verbandschere Lister", ["14,5 cm", "18 cm"], (6.9, 9.9), 0.47, "Stück", "82130000", "PK", 0.1, 1, False),
        ("Instrumentenschale Edelstahl", ["klein", "mittel", "groß"], (9.5, 24.0), 0.40, "Stück", "73239300", "DE", 0.4, 1, False),
        ("Untersuchungsleuchte LED", ["Standfuß", "Wandmontage"], (189.0, 279.0), 0.29, "Stück", "94054199", "DE", 4.0, 1, False),
        ("Hocker mit Rollen", ["schwarz", "grau"], (89.0, 129.0), 0.30, "Stück", "94013000", "PL", 8.0, 1, False),
    ]),
    ("Labor", [
        ("Blutentnahmeröhrchen, 50 Stück", ["Serum", "EDTA", "Citrat"], (8.9, 12.5), 0.31, "Pack", "90189084", "AT", 0.35, 1, True),
        ("Probenbecher 100 ml, 100 Stück", ["unsteril", "steril"], (9.9, 16.0), 0.36, "Pack", "39233010", "DE", 0.9, 1, False),
        ("Objektträger Mattrand, 50 Stück", ["Standard"], (3.5, 4.5), 0.44, "Pack", "70179000", "CN", 0.3, 1, False),
    ]),
    ("Fachliteratur", [
        ("Praxishandbuch Hygieneplan", ["aktuelle Auflage"], (39.0, 39.0), 0.30, "Stück", "49019900", "DE", 0.8, 2, False),
        ("Pocketguide Notfallmedizin", ["aktuelle Auflage"], (24.9, 24.9), 0.30, "Stück", "49019900", "DE", 0.3, 2, False),
    ]),
]

ZAHLUNGSARTEN = [(1, "Rechnung"), (2, "Lastschrift"), (3, "Vorkasse"), (4, "PayPal"), (5, "Kreditkarte")]
VERSANDARTEN = [(1, "DHL Paket", "DHL", 5.90), (2, "DPD Classic", "DPD", 6.40), (3, "GLS Business", "GLS", 6.20),
                (4, "Spedition", "Spedition", 39.00), (5, "Selbstabholung", "", 0.00)]
EINHEITEN = ["Stück", "Box", "Pack", "Karton", "Flasche", "Rolle", "Paar", "Dose"]

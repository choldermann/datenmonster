"""Die einzigen Tabellen, deren Inhalt aus der Kopie stehen bleibt.

Nur Kataloge, die JTL selbst mitliefert (Länder, Steuern, Einheiten, Status-
und Grundtexte). Alles, was ein Kunde anlegt oder was Geschäftsdaten trägt,
wird geleert – auch Kundengruppen, Zahlungs-/Versandarten, Lager, Firma,
Benutzer; die erzeugt der Generator neu. Inhalt dieser Liste am 05.11.2026
Zeile für Zeile angesehen (siehe pruefe_erlaubt).
"""
ERLAUBT = {
    "dbo.tversion",
    "dbo.tLand", "dbo.tBundesland",
    "dbo.tWaehrung",
    "dbo.tSteuersatz", "dbo.tSteuerklasse", "dbo.tSteuerzone", "dbo.tSteuerzoneLand", "dbo.tSteuerschluessel",
    # tEinheit/tEinheitSprache NICHT: dort stand ein echter Firmenname als Einheit
    "dbo.tMassEinheit", "dbo.tMassEinheitSprache",
    "dbo.tSpracheUsed",
    "dbo.tZustand", "dbo.tZustandSprache",
    "dbo.tLieferStatus", "dbo.tRMStatus", "dbo.tRMStatusSprache", "dbo.tRMGrund", "dbo.tRMGrundSprache",
    "dbo.tRueckhalteGrund",
    "Rechnung.tRechnungStornogrund", "Verkauf.tAuftragStornogrund", "dbo.tGutschriftStornogrund",
    "dbo.tBuchungsArt", "dbo.tFeldTyp", "dbo.tDateityp",
    "dbo.tPlattform", "Verkauf.tVorgangsstatus",
}

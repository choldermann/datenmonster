"""Drei Jahre Geschäft, Tag für Tag simuliert.

Lager wird echt geführt (FIFO über Wareneingänge mit Chargen/MHD): ausgeliefert
wird nur, was da ist; Rückstände warten. Unterschreitet der Bestand inklusive
offener Bestellungen den Meldebestand, geht eine Lieferantenbestellung raus.
Rechnung beim Versand, Zahlung nach Zahlungsmoral des Kunden. Abgeleitete
Werte (Eckdaten, Lagerbestand) rechnet danach JTL selbst (siehe erzeugen.py).
"""
import datetime as dt
import math
import random
from collections import defaultdict, deque

from tools.demo_daten import welt

START = dt.date(2023, 11, 1)
ENDE = dt.date(2026, 11, 4)          # gestern aus Sicht der Demo
UMSATZ_JAHR = 2_100_000              # Zielgröße netto im ersten Jahr
WACHSTUM = 0.09                      # pro Jahr


def _tage(d0, d1):
    d = d0
    while d <= d1:
        yield d
        d += dt.timedelta(days=1)


def _zeit(r, tag, h0=8, h1=17):
    return dt.datetime.combine(tag, dt.time(r.randint(h0, h1 - 1), r.randint(0, 59), r.randint(0, 59)))


class Sim:
    def __init__(self, w, r: random.Random, s: dict):
        self.w, self.r, self.s = w, r, s
        self.art = s["artikel"]
        self.kunden = s["kunden"]
        self.ids = defaultdict(int)
        self.nr = defaultdict(int)
        self.rows = defaultdict(list)
        self.lose = defaultdict(deque)       # kArtikel → deque[[kWLE, rest, ek, charge, mhd]]
        self.bestand = defaultdict(float)
        self.offen_po = defaultdict(float)   # kArtikel → offene Bestellmenge
        self.lieferungen = defaultdict(list) # Datum → [(kLBP, kArtikel, menge, kLB, kLieferant, ek)]
        self.rueckstand = deque()            # Aufträge, die auf Ware warten
        self.platz = {k: r.choice(s["lagerplaetze"]) for k in self.art}
        self.nachfrage = defaultdict(lambda: 0.2)  # gleitender Tagesbedarf je Artikel
        # Einkaufspreis-Entwicklung: allgemein +2,5 %/Jahr, einige Artikel springen
        self.ek_sprung = {k: (dt.date(2025, r.randint(2, 11), 1), r.uniform(0.10, 0.22))
                          for k in r.sample([k for k, a in self.art.items() if not a.get("set")], 16)}
        # Verkaufspreis: jeweils im Januar +3 % – außer bei den Sprung-Artikeln
        self.lagerhueter = set(r.sample([k for k, a in self.art.items() if a["beliebt"] < 0.25 and not a.get("set")], 9))
        self.kunden_liste = list(self.kunden.values())

    # ── Hilfen ───────────────────────────────────────────────────────────────
    def neu(self, was):
        self.ids[was] += 1
        return self.ids[was]

    def nummer(self, praefix, tag):
        self.nr[(praefix, tag.year)] += 1
        return f"{praefix}{tag.year}-{self.nr[(praefix, tag.year)]:05d}"

    def jahre_seit(self, tag):
        return (tag - START).days / 365.25

    def ek(self, k, tag):
        a = self.art[k]
        if a.get("set"):
            return 0.0
        rueck = (ENDE - tag).days / 365.25
        wert = a["ek"] / (1.025 ** rueck)
        sprung = self.ek_sprung.get(k)
        if sprung:
            wert = wert / (1 + sprung[1]) if tag < sprung[0] else wert
        return round(wert, 2)

    def vk(self, k, tag, gruppe):
        a = self.art[k]
        basis = self.s["gruppenpreis"].get((k, gruppe), a["vk"])
        jahre_zurueck = ENDE.year - tag.year
        if k not in self.ek_sprung:
            basis = basis / (1.03 ** jahre_zurueck)
        return round(basis, 2)

    def saison(self, tag, wg):
        m = tag.month
        grund = {1: 1.05, 2: 1.0, 3: 1.02, 4: 0.97, 5: 0.95, 6: 0.9, 7: 0.82, 8: 0.85, 9: 1.0, 10: 1.08, 11: 1.12, 12: 0.95}[m]
        if wg in (1, 2, 6) and m in (10, 11, 12, 1, 2):     # Handschuhe, Desinfektion, Hygiene im Winter
            grund *= 1.15
        return grund

    # ── Lager ────────────────────────────────────────────────────────────────
    def einbuchen(self, k, menge, ek, zeit, buchungsart, kLBP=None, ls_nr="", kommentar=""):
        a = self.art[k]
        charge, mhd = "", None
        if a["mhd"]:
            charge = f"CH{zeit:%y%m}{self.r.randint(100, 999)}"
            mhd = zeit.date() + dt.timedelta(days=self.r.randint(420, 1000))
        kwle = self.neu("wle")
        self.rows["dbo.tWarenLagerEingang"].append(dict(
            kWarenLagerEingang=kwle, kArtikel=k, kWarenLagerPlatz=self.platz[k], kLieferantenBestellungPos=kLBP or 0,
            kBenutzer=4, fAnzahl=menge, fEKEinzel=ek, cLieferscheinNr=ls_nr, cChargenNr=charge, dMHD=mhd,
            dErstellt=zeit, dGeliefertAM=zeit, cKommentar=kommentar, kBuchungsart=buchungsart,
            fAnzahlAktuell=menge, fAnzahlReserviertPickpos=0))
        los = [kwle, menge, ek, charge, mhd]
        self.lose[k].append(los)
        self.bestand[k] += menge
        return los

    def ausbuchen(self, k, menge, zeit, buchungsart, kLSP=None, kommentar=""):
        """FIFO; gibt den Einkaufswert der entnommenen Menge zurück."""
        wert, rest = 0.0, menge
        while rest > 1e-9 and self.lose[k]:
            los = self.lose[k][0]
            nimm = min(rest, los[1])
            self.rows["dbo.tWarenLagerAusgang"].append(dict(
                kWarenLagerAusgang=self.neu("wla"), kWarenLagerEingang=los[0], kLieferscheinPos=kLSP or 0,
                fAnzahl=nimm, kWarenLagerPlatz=self.platz[k], kArtikel=k, cKommentar=kommentar, dErstellt=zeit,
                kBenutzer=4, kBuchungsart=buchungsart))
            wert += nimm * los[2]
            los[1] -= nimm
            rest -= nimm
            if los[1] <= 1e-9:
                self.lose[k].popleft()
        self.bestand[k] -= menge - rest
        return wert

    # ── Einkauf ──────────────────────────────────────────────────────────────
    def nachbestellen(self, tag):
        je_lieferant = defaultdict(list)
        for k, a in self.art.items():
            if a.get("set") or k in self.lagerhueter:
                continue
            lief = self.s["lieferanten"][a["lief"]]
            bedarf = self.nachfrage[k]
            melde = bedarf * (lief["nLieferzeit"] + 7) + (a["nMidestbestand"] if "nMidestbestand" in a else 0)
            if self.bestand[k] + self.offen_po[k] < melde:
                menge = max(10, math.ceil(bedarf * self.r.uniform(30, 55) / 10) * 10)
                je_lieferant[a["lief"]].append((k, menge))
        for kl, posten in je_lieferant.items():
            lief = self.s["lieferanten"][kl]
            zeit = _zeit(self.r, tag, 9, 12)
            klb = self.neu("lb")
            soll = tag + dt.timedelta(days=lief["nLieferzeit"])
            self.rows["dbo.tLieferantenBestellung"].append(dict(
                kLieferantenBestellung=klb, kLieferant=kl, kSprache=1, cWaehrungISO="EUR", nStatus=20, dErstellt=zeit,
                kFirma=1, kKunde=0, dLieferdatum=dt.datetime.combine(soll, dt.time(10)), cEigeneBestellnummer=self.nummer("BE", tag),
                kBenutzer=2, nDeleted=0, nManuellAbgeschlossen=0, cFremdbelegnummer=""))
            # Verzug: manche Lieferanten liefern öfter zu spät
            verzug = self.r.choices([0, 0, 0, 1, 2, 5, 12], [40, 20, 15, 10, 7, 5, 3])[0] + (4 if kl in (5, 7, 11) else 0)
            teil = self.r.random() < 0.08
            for i, (k, menge) in enumerate(posten):
                ek = self.ek(k, tag)
                klbp = self.neu("lbp")
                self.rows["dbo.tLieferantenBestellungPos"].append(dict(
                    kLieferantenBestellungPos=klbp, kLieferantenBestellung=klb, kArtikel=k, cArtNr=self.art[k]["cArtNr"],
                    cLieferantenArtNr=f"{kl:02d}-{k:05d}", cName=self.art[k]["name"], cLieferantenBezeichnung=self.art[k]["name"],
                    fMenge=menge, fEKNetto=ek, nPosTyp=1, dLieferdatum=dt.datetime.combine(soll, dt.time(10)), nSort=i,
                    fMengeGeliefert=0, fAnzahlOffen=menge, cHinweis=""))
                self.offen_po[k] += menge
                ankunft = soll + dt.timedelta(days=verzug)
                if teil and i == 0:
                    erste = math.floor(menge * 0.6)
                    self.lieferungen[ankunft].append((klbp, k, erste, klb, kl, ek))
                    self.lieferungen[ankunft + dt.timedelta(days=self.r.randint(6, 20))].append((klbp, k, menge - erste, klb, kl, ek))
                else:
                    self.lieferungen[ankunft].append((klbp, k, menge, klb, kl, ek))

    def wareneingang(self, tag):
        if tag not in self.lieferungen:
            return
        je_bestellung = defaultdict(list)
        for eintrag in self.lieferungen.pop(tag):
            je_bestellung[eintrag[3]].append(eintrag)
        for klb, posten in je_bestellung.items():
            if tag > ENDE:
                continue
            zeit = _zeit(self.r, tag, 8, 15)
            kl = posten[0][4]
            ls_nr = f"LS-{kl:02d}-{self.r.randint(100000, 999999)}"
            ker = self.neu("er")
            ziel = tag + dt.timedelta(days=30)
            bezahlt = dt.datetime.combine(ziel - dt.timedelta(days=self.r.randint(0, 12)), dt.time(9)) \
                if ziel - dt.timedelta(days=12) <= ENDE else None
            lief = self.s["lieferanten"][kl]
            self.rows["dbo.tEingangsrechnung"].append(dict(
                kEingangsrechnung=ker, kBenutzer=2, kLieferant=kl, kAnsprechpartner=0,
                cFremdbelegnummer=f"R{kl:02d}{self.r.randint(100000, 999999)}", cEigeneRechnungsnummer=self.nummer("ER", tag),
                cHinweise="", cLieferant=lief["cFirma"], cStrasse=lief["cStrasse"], cPLZ=lief["cPLZ"], cOrt=lief["cOrt"],
                cLandISO=lief["cISO"], cTel=lief["cTelZentralle"], cMail=lief["cEMail"], nStatus=20 if bezahlt else 5,
                nDeleted=0, nZahlungFreigegeben=1, dErstellt=zeit, nKumuliert=0,
                dBezahlt=bezahlt if bezahlt and bezahlt.date() <= ENDE else None,
                dZahlungsziel=dt.datetime.combine(ziel, dt.time(0)), fFremdFaktor=1, nVerteilungsArt=0,
                dBelegdatum=zeit))
            for klbp, k, menge, _, _, ek in posten:
                self.einbuchen(k, menge, ek, zeit, 10, kLBP=klbp, ls_nr=ls_nr)
                self.offen_po[k] -= menge
                self.gelieferte[klbp] += menge
                self.rows["dbo.tEingangsrechnungPos"].append(dict(
                    kEingangsrechnungPos=self.neu("erp"), kEingangsrechnung=ker, kLieferantenbestellung=klb,
                    kLieferantenBestellungPos=klbp, kArtikel=k, cArtNr=self.art[k]["cArtNr"],
                    cLieferantenArtNr=f"{kl:02d}-{k:05d}", cName=self.art[k]["name"],
                    cLieferantenBezeichnung=self.art[k]["name"], cEinheit=self.art[k]["einheit"], cHinweis="",
                    fMenge=menge, fEKNetto=ek, fMwSt=19 if self.art[k]["stkl"] == 1 else 7, nPosTyp=1))
            if self.r.random() < 0.35:   # Fracht als eigene Position
                self.rows["dbo.tEingangsrechnungPos"].append(dict(
                    kEingangsrechnungPos=self.neu("erp"), kEingangsrechnung=ker, kLieferantenbestellung=klb,
                    kArtikel=0, cArtNr="", cName="Frachtkosten", cLieferantenBezeichnung="Fracht", cEinheit="",
                    cHinweis="", fMenge=1, fEKNetto=round(self.r.uniform(12, 65), 2), fMwSt=19, nPosTyp=2))

    # ── Verkauf ──────────────────────────────────────────────────────────────
    def warenkorb(self, kunde, tag):
        g = kunde["gruppe"]
        bevorzugt = {3: (7,), 6: (1, 2, 5), 4: (1, 2, 3, 6), 5: (1, 2, 4, 9), 2: (1, 2, 3, 4, 5), 1: (1, 2, 3, 5, 10)}[g]
        kandidaten = [a for a in self.art.values() if a["cAktiv"] == "Y"]
        gewichte = []
        for a in kandidaten:
            gw = (a["beliebt"] + 0.05) ** 1.6 * self.saison(tag, a["kWarengruppe"])
            if a["kWarengruppe"] in bevorzugt:
                gw *= 3
            if a["kWarengruppe"] == 7 and g != 3:
                gw *= 0.05
            if a["kArtikel"] in self.lagerhueter:
                gw *= 0.02
            if a["vk"] > 150 and g == 1:
                gw *= 0.2
            gewichte.append(gw)
        n_pos = min(len(kandidaten), self.r.choices([1, 2, 3, 4, 5, 6, 8], [26, 24, 18, 12, 9, 6, 5])[0])
        if g == 5:
            n_pos = min(len(kandidaten), n_pos + 2)
        gewaehlt = {}
        while len(gewaehlt) < n_pos:
            a = self.r.choices(kandidaten, gewichte)[0]
            if a["kArtikel"] in gewaehlt:
                continue
            basis = {1: (1, 2), 2: (1, 4), 3: (1, 3), 4: (1, 5), 5: (2, 12), 6: (1, 3)}[g]
            menge = self.r.randint(*basis)
            if a["vk"] > 60:          # Kartons, Geräte: selten mehr als eins
                menge = 1 if self.r.random() < 0.8 else 2
            gewaehlt[a["kArtikel"]] = menge
        return gewaehlt

    def tagesauftraege(self, tag):
        wt = tag.weekday()
        faktor = [1.08, 1.05, 1.02, 1.0, 0.92, 0.18, 0.08][wt]
        mittel_auftrag = 235.0
        n = UMSATZ_JAHR * (1 + WACHSTUM) ** self.jahre_seit(tag) / 252 / mittel_auftrag
        n *= faktor * self.saison(tag, 0) * self.r.uniform(0.8, 1.2)
        if tag.month == 12 and tag.day > 22 or (tag.month == 1 and tag.day < 3):
            n *= 0.25
        return max(0, int(round(n)))

    def kunde_waehlen(self, tag):
        while True:
            k = self.r.choices(self.kunden_liste, [x["aktiv"] for x in self.kunden_liste])[0]
            if k["erstellt"].date() > tag:
                continue
            if k["abwandern"] and tag > dt.date(2026, 3, 1):
                continue
            if k["cSperre"] == "Y" and tag > dt.date(2025, 6, 1):
                continue
            return k

    def auftrag(self, tag):
        r = self.r
        kunde = self.kunde_waehlen(tag)
        zeit = _zeit(r, tag, 7, 21) if kunde["gruppe"] == 1 else _zeit(r, tag, 8, 17)
        shop = kunde["gruppe"] == 1 or r.random() < 0.25
        kab = self.neu("auftrag")
        va = r.choices([1, 2, 3, 4, 5], [55, 18, 17, 3, 7])[0]
        korb = self.warenkorb(kunde, tag)
        if va == 4 and sum(korb.values()) < 20:
            va = 1
        za = kunde["za"]
        angebot = kunde["gruppe"] in (5, 2) and r.random() < 0.06
        storno = not angebot and r.random() < 0.012
        nr = self.nummer("AN" if angebot else "AU", tag)
        self.rows["Verkauf.tAuftrag"].append(dict(
            kAuftrag=kab, kBenutzer=1 if not shop else 5, kBenutzerErstellt=1 if not shop else 5, kKunde=kunde["kKunde"],
            cAuftragsNr=nr, nType=0 if angebot else 1, dErstellt=zeit, cInet="Y" if shop else "N", cWaehrung="EUR",
            fFaktor=1, kFirmaHistory=1, kShop=1 if shop else 0, kPlattform=2 if shop else 1, kSprache=1,
            cVersandlandISO=kunde["iso"], cVersandlandWaehrung="EUR", fVersandlandWaehrungFaktor=1, kVersandArt=va,
            nZahlungszielTage=kunde["zz"], fSkonto=kunde["fSkonto"], nStorno=1 if storno else 0, nKomplettAusgeliefert=0,
            kZahlungsart=za, nDebitorennr=kunde["nDebitorennr"], cKundenNr=kunde["cKundenNr"],
            cKundeUstId="", fFinanzierungskosten=0,
            dVoraussichtlichesLieferdatum=zeit + dt.timedelta(days=2)))
        for typ in (0, 1):
            self.rows["Verkauf.tAuftragAdresse"].append(self._adresse(kunde, kab, typ, "kAuftrag"))
        positionen = []
        for i, (k, menge) in enumerate(korb.items()):
            a = self.art[k]
            preis = self.vk(k, tag, kunde["gruppe"])
            rabatt = 0
            if kunde["gruppe"] == 5 and r.random() < 0.5:
                rabatt = r.choice([5, 8, 10, 12, 15])
            elif kunde["gruppe"] in (2, 3) and menge >= 6 and r.random() < 0.25:
                rabatt = r.choice([3, 5])
            if r.random() < 0.004:       # Muster/Gratisware
                preis, rabatt = 0.0, 0
            kap = self.neu("apos")
            positionen.append(dict(kAuftragPosition=kap, kArtikel=k, kAuftrag=kab, cArtNr=a["cArtNr"], cName=a["name"],
                                   cHinweis="", fAnzahl=menge, fEkNetto=self.ek(k, tag), fVkNetto=preis, fRabatt=rabatt,
                                   fMwSt=19 if a["stkl"] == 1 else 7, nSort=i, kSteuerklasse=a["stkl"], nType=1,
                                   cEinheit=a["einheit"]))
        netto = sum(p["fAnzahl"] * p["fVkNetto"] * (1 - p["fRabatt"] / 100) for p in positionen)
        versand_netto = 0 if va == 5 or netto >= 150 else [None, 5.90, 6.40, 6.20, 39.0][va]
        if versand_netto:
            positionen.append(dict(kAuftragPosition=self.neu("apos"), kArtikel=0, kAuftrag=kab, cArtNr="",
                                   cName=f"Versand: {welt.VERSANDARTEN[va - 1][1]}", cHinweis="", fAnzahl=1, fEkNetto=0,
                                   fVkNetto=versand_netto, fRabatt=0, fMwSt=19, nSort=len(positionen), kSteuerklasse=1,
                                   nType=2, cEinheit=""))
        self.rows["Verkauf.tAuftragPosition"].extend(positionen)
        for p in positionen:
            if p["nType"] == 1:
                self.heute[p["kArtikel"]] += p["fAnzahl"]
        if storno:
            self.rows["Verkauf.tAuftragStorno"].append(dict(kAuftrag=kab, kBenutzer=1, cKommentar="Kunde hat storniert",
                                                            kAuftragStornogrund=1, dStorniert=zeit + dt.timedelta(hours=3)))
            return
        if angebot:
            return
        self.rueckstand.append(dict(kAuftrag=kab, kunde=kunde, zeit=zeit, positionen=positionen, va=va, za=za,
                                    shop=shop, nr=nr))

    def _adresse(self, kunde, schluessel, typ, feld):
        return {feld: schluessel, "kKunde": kunde["kKunde"], "cFirma": kunde["firma"], "cVorname": kunde["v"],
                "cName": kunde["n"], "cStrasse": kunde["strasse"], "cPLZ": kunde["plz"], "cOrt": kunde["ort"],
                "cLand": kunde["land"], "cISO": kunde["iso"], "cMail": kunde["mail"], "cTel": "", "nTyp": typ}

    def versenden(self, tag):
        """Rückstand abarbeiten: komplett lieferbare Aufträge gehen raus."""
        bleibt = deque()
        while self.rueckstand:
            au = self.rueckstand.popleft()
            if au["zeit"].date() >= tag and au["zeit"].hour >= 15:
                bleibt.append(au); continue
            artikel_pos = [p for p in au["positionen"] if p["nType"] == 1]
            def verfuegbar(k, m):
                a = self.art[k]
                if a.get("set"):
                    return all(self.bestand[t["kArtikel"]] >= m * t["fAnzahl"] for t in self.s_stueck)
                return self.bestand[k] >= m
            if not all(verfuegbar(p["kArtikel"], p["fAnzahl"]) for p in artikel_pos):
                bleibt.append(au); continue
            self._liefern_und_berechnen(au, tag)
        self.rueckstand = bleibt

    def _liefern_und_berechnen(self, au, tag):
        r = self.r
        zeit = _zeit(r, tag, 10, 16)
        kls = self.neu("ls")
        self.rows["dbo.tLieferschein"].append(dict(kLieferschein=kls, kBestellung=au["kAuftrag"], kBenutzer=4,
                                                   cLieferscheinNr=self.nummer("LS", tag), cHinweis="", dErstellt=zeit,
                                                   kLieferantenBestellung=0))
        gewicht = 0.0
        ek_pos = {}
        for p in au["positionen"]:
            if p["nType"] != 1:
                continue
            klsp = self.neu("lsp")
            self.rows["dbo.tLieferscheinPos"].append(dict(kLieferscheinPos=klsp, kLieferschein=kls,
                                                          kBestellPos=p["kAuftragPosition"], fAnzahl=p["fAnzahl"], cHinweis=""))
            a = self.art[p["kArtikel"]]
            if a.get("set"):
                wert = sum(self.ausbuchen(t["kArtikel"], p["fAnzahl"] * t["fAnzahl"], zeit, 20, klsp) for t in self.s_stueck)
            else:
                wert = self.ausbuchen(p["kArtikel"], p["fAnzahl"], zeit, 20, klsp)
            ek_pos[p["kAuftragPosition"]] = round(wert / p["fAnzahl"], 4) if p["fAnzahl"] else 0
            gewicht += a["gew"] * p["fAnzahl"]
        pakete = 1 if gewicht <= 31.5 else min(8, math.ceil(gewicht / 31.5))
        versendet = zeit + dt.timedelta(hours=r.randint(1, 5)) if au["va"] != 5 else zeit
        self.rows["dbo.tLieferscheinEckdaten"].append(dict(kLieferschein=kls, dErstellt=zeit, dVersendet=versendet,
                                                           nAnzahlPakete=pakete, nAnzahlVersendetePakete=pakete,
                                                           kVersandArt=au["va"], fVersandGewicht=round(gewicht + 0.4 * pakete, 2),
                                                           fArtikelGewicht=round(gewicht, 2), nRechnungStatus=2))
        if au["va"] != 5:
            for _ in range(pakete):
                self.rows["dbo.tVersand"].append(dict(kVersand=self.neu("versand"), kLieferschein=kls, kBenutzer=4,
                                                      cIdentCode=f"00340{r.randint(10**12, 10**13 - 1)}", dErstellt=zeit,
                                                      cHinweis="", fGewicht=round(gewicht / pakete + 0.4, 2),
                                                      kVersandArt=au["va"], cLogistiker=welt.VERSANDARTEN[au["va"] - 1][2],
                                                      dVersendet=versendet, nStatus=1))
        self.rows["_ausgeliefert"].append(au["kAuftrag"])
        self.rechnung(au, versendet, ek_pos)

    def rechnung(self, au, zeit, ek_pos, korrektur_von=None):
        r = self.r
        kunde = au["kunde"]
        krg = self.neu("rechnung")
        self.rows["Rechnung.tRechnung"].append(dict(
            kRechnung=krg, kBenutzer=1, kKunde=kunde["kKunde"], cRechnungsnr=self.nummer("RE", zeit.date()),
            dErstellt=zeit, dLeistungsdatum=zeit, cKundennr=kunde["cKundenNr"], cFirma="MediVersa Praxisbedarf GmbH",
            kFirmaHistory=1, nZahlungszielTage=kunde["zz"], fSkonto=kunde["fSkonto"], nStatus=0,
            cVersandlandISO=kunde["iso"], cVersandlandWaehrung="EUR", fVersandlandWaehrungsfaktor=1, cWaehrung="EUR",
            fWaehrungsfaktor=1, kZahlungsart=au["za"], cZahlungsart=welt.ZAHLUNGSARTEN[au["za"] - 1][1], kSprache=1,
            nSteuereinstellung=0, kPlattform=2 if au["shop"] else 1, kShop=1 if au["shop"] else 0,
            kVersandArt=au["va"], cVersandart=welt.VERSANDARTEN[au["va"] - 1][1], nIstEntwurf=0, nIstProforma=0,
            nStorno=0, nRechnungStatus=100, nIstExterneRechnung=0, nArchiv=0, nDebitorennr=kunde["nDebitorennr"],
            cKundeUstId="", kKundengruppe=kunde["gruppe"]))
        self.rows["Verkauf.tAuftragRechnung"].append(dict(kAuftrag=au["kAuftrag"], kRechnung=krg))
        for typ in (0, 1):
            self.rows["Rechnung.tRechnungAdresse"].append(self._adresse(kunde, krg, typ, "kRechnung"))
        brutto = 0.0
        for p in au["positionen"]:
            ek = ek_pos.get(p["kAuftragPosition"], 0)
            if p["nType"] == 1 and r.random() < 0.004:   # Position ohne EK (Ehrlichkeitskachel)
                ek = 0
            self.rows["Rechnung.tRechnungPosition"].append(dict(
                kRechnungPosition=self.neu("rpos"), kRechnung=krg, kAuftrag=au["kAuftrag"],
                kAuftragPosition=p["kAuftragPosition"], kArtikel=p["kArtikel"], cArtNr=p["cArtNr"], cName=p["cName"],
                cEinheit=p["cEinheit"], fAnzahl=p["fAnzahl"], fMwSt=p["fMwSt"], fVkNetto=p["fVkNetto"],
                fRabatt=p["fRabatt"], nType=p["nType"], fGewicht=self.art[p["kArtikel"]]["gew"] if p["kArtikel"] else 0,
                fEkNetto=ek, nSort=p["nSort"], kSteuerklasse=p["kSteuerklasse"]))
            brutto += p["fAnzahl"] * p["fVkNetto"] * (1 - p["fRabatt"] / 100) * (1 + p["fMwSt"] / 100)
        brutto = round(brutto, 2)
        self.rechnungen.append(dict(kRechnung=krg, au=au, zeit=zeit, brutto=brutto, ek_pos=ek_pos))
        # Zahlung nach Zahlungsmoral
        if au["za"] in (3, 4, 5):
            bezahlt = au["zeit"] + dt.timedelta(hours=r.randint(0, 30))
        else:
            zz = max(kunde["zz"], 7)
            art = kunde["zahlt"]
            tage = {"puenktlich": r.randint(2, zz), "spaet": zz + r.randint(4, 35),
                    "schlecht": zz + r.randint(25, 140)}[art]
            if art == "schlecht" and r.random() < 0.25:
                tage = None
            bezahlt = zeit + dt.timedelta(days=tage) if tage is not None else None
        if bezahlt and bezahlt.date() <= ENDE:
            self.rows["dbo.tZahlung"].append(dict(
                kZahlung=self.neu("zahlung"), cName=kunde["firma"] or f"{kunde['v']} {kunde['n']}", dDatum=bezahlt,
                fBetrag=brutto, kBestellung=au["kAuftrag"], kRechnung=krg, kBenutzer=1, cHinweis="",
                kZahlungsart=au["za"], nZahlungstyp=0, kGutschrift=0, kEingangsrechnung=0))
        return krg

    # ── Nachgelagert: Retouren, Rechnungskorrekturen ─────────────────────────
    def retouren_und_korrekturen(self):
        r = self.r
        for rg in self.rechnungen:
            zufall = r.random()
            if zufall < 0.022:
                self._retoure(rg)
            elif zufall < 0.030:
                self._rechnungsstorno(rg)

    def _gutschrift(self, rg, zeit, posten, storno_typ):
        kg = self.neu("gutschrift")
        kunde = rg["au"]["kunde"]
        self.rows["dbo.tgutschrift"].append(dict(
            kGutschrift=kg, kRechnung=rg["kRechnung"], kKunde=kunde["kKunde"], cGutschriftNr=self.nummer("GU", zeit.date()),
            fMwSt=19, dErstellt=zeit, cWaehrung="EUR", kFirma=1, kSprache=1, kBenutzer=1,
            kPlattform=2 if rg["au"]["shop"] else 1, nStorno=0, nStornoTyp=storno_typ, cKundeUstId="",
            cStatus=""))
        betrag = 0.0
        for i, (p, menge) in enumerate(posten):
            self.rows["dbo.tGutschriftPos"].append(dict(
                kGutschriftPos=self.neu("gpos"), tGutschrift_kGutschrift=kg, tArtikel_kArtikel=p["kArtikel"],
                cArtNr=p["cArtNr"], cString=p["cName"], nAnzahl=menge, fVKNetto=p["fVkNetto"], fRabatt=p["fRabatt"],
                fMwSt=p["fMwSt"], kBestellPos=p["kAuftragPosition"], nSort=i))
            betrag += menge * p["fVkNetto"] * (1 - p["fRabatt"] / 100) * (1 + p["fMwSt"] / 100)
        return kg, round(betrag, 2)

    def _retoure(self, rg):
        r = self.r
        au = rg["au"]
        art_pos = [p for p in au["positionen"] if p["nType"] == 1 and not self.art[p["kArtikel"]].get("set")]
        if not art_pos:
            return
        p = r.choice(art_pos)
        menge = max(1, int(p["fAnzahl"] * r.choice([1, 1, 0.5])))
        zeit = rg["zeit"] + dt.timedelta(days=r.randint(5, 21), hours=r.randint(0, 6))
        if zeit.date() > ENDE:
            return
        kg, betrag = self._gutschrift(rg, zeit, [(p, menge)], 0)
        krm = self.neu("retoure")
        self.rows["dbo.tRMRetoure"].append(dict(kRMRetoure=krm, kKunde=au["kunde"]["kKunde"], kBenutzer=4,
                                                cRetoureNr=self.nummer("RT", zeit.date()), dErstellt=zeit, kFirma=1,
                                                kGutschrift=kg, kBestellung=au["kAuftrag"], kRMStatus=3,
                                                kRMRetoureAbholAdresse=0, nHerkunft=0, fKorrekturBetrag=0,
                                                nVersandkostenErstatten=0))
        self.rows["dbo.tRMRetourePos"].append(dict(kRMRetourePos=self.neu("rmpos"), kRMRetoure=krm, kZustand=1,
                                                   kLieferscheinPos=0, kBenutzer=4, fAnzahl=menge, kArtikel=p["kArtikel"],
                                                   cArtNr=p["cArtNr"], cName=p["cName"],
                                                   kRMGrund=r.choice([1, 2, 3, 4, 5, 6]), kRMStatusVerlauf=0,
                                                   nGutschreiben=1))
        self.retour_zugaenge.append((p["kArtikel"], menge, p["fEkNetto"], zeit))
        self.gutschrift_zahlungen.append((kg, rg, -betrag, zeit + dt.timedelta(days=2)))

    def _rechnungsstorno(self, rg):
        r = self.r
        zeit = rg["zeit"] + dt.timedelta(days=r.randint(0, 6), hours=2)
        if zeit.date() > ENDE:
            return
        posten = [(p, p["fAnzahl"]) for p in rg["au"]["positionen"]]
        kg, _ = self._gutschrift(rg, zeit, posten, 1)
        self.storno_rechnungen.append(rg["kRechnung"])
        # korrigierte Rechnung (gleiche Ware, neuer Beleg)
        self.rechnung(rg["au"], zeit + dt.timedelta(minutes=20), rg["ek_pos"])

    # ── Lauf ─────────────────────────────────────────────────────────────────
    def lauf(self):
        r = self.r
        self.rechnungen, self.storno_rechnungen, self.retour_zugaenge, self.gutschrift_zahlungen = [], [], [], []
        self.gelieferte = defaultdict(float)
        self.heute = defaultdict(float)
        self.s_stueck = [dict(kArtikel=t["kArtikel"], fAnzahl=t["fAnzahl"]) for t in self.s.get("stueckliste", [])]
        # Anfangsbestand (Übernahme ins neue System)
        t0 = dt.datetime.combine(START - dt.timedelta(days=1), dt.time(18))
        for k, a in self.art.items():
            if a.get("set"):
                continue
            tage = 600 if k in self.lagerhueter else r.randint(25, 60)
            menge = max(5, math.ceil(0.25 * (a["beliebt"] + 0.05) ** 1.6 * 40 * tage / 10) * 10)
            self.einbuchen(k, menge, self.ek(k, START), t0, 80, kommentar="Anfangsbestand Übernahme")
            self.nachfrage[k] = (a["beliebt"] + 0.05) ** 1.6 * 2
        for tag in _tage(START, ENDE):
            self.wareneingang(tag)
            if tag.weekday() < 6:
                for _ in range(self.tagesauftraege(tag)):
                    self.auftrag(tag)
            if tag.weekday() < 5:
                self.versenden(tag)
                self.nachbestellen(tag)
            if tag.month == 12 and tag.day == 31:
                self.inventur(tag)
            # Tagesbedarf je Artikel (gleitend, ~4 Wochen) für die Nachbestellung
            for k in self.art:
                self.nachfrage[k] = self.nachfrage[k] * 0.965 + self.heute[k] * 0.035
            self.heute.clear()
        self.retouren_und_korrekturen()
        for k, menge, ek, zeit in self.retour_zugaenge:
            self.einbuchen(k, menge, ek or self.ek(k, zeit.date()), zeit, 170, kommentar="Retoure")
        for kg, rg, betrag, zeit in self.gutschrift_zahlungen:
            if zeit.date() <= ENDE:
                self.rows["dbo.tZahlung"].append(dict(
                    kZahlung=self.neu("zahlung"), cName="Erstattung Retoure", dDatum=zeit, fBetrag=betrag,
                    kBestellung=rg["au"]["kAuftrag"], kRechnung=rg["kRechnung"], kBenutzer=1, cHinweis="",
                    kZahlungsart=rg["au"]["za"], nZahlungstyp=0, kGutschrift=kg, kEingangsrechnung=0))
        # Bestellstatus nach Lieferung, Bestände der Lose
        offen_je_lb = defaultdict(float)
        for p in self.rows["dbo.tLieferantenBestellungPos"]:
            p["fMengeGeliefert"] = self.gelieferte[p["kLieferantenBestellungPos"]]
            p["fAnzahlOffen"] = max(0.0, p["fMenge"] - p["fMengeGeliefert"])
            offen_je_lb[p["kLieferantenBestellung"]] += p["fAnzahlOffen"]
        gel_je_lb = defaultdict(float)
        for p in self.rows["dbo.tLieferantenBestellungPos"]:
            gel_je_lb[p["kLieferantenBestellung"]] += p["fMengeGeliefert"]
        for b in self.rows["dbo.tLieferantenBestellung"]:
            offen = offen_je_lb[b["kLieferantenBestellung"]]
            b["nStatus"] = 500 if offen == 0 else (30 if gel_je_lb[b["kLieferantenBestellung"]] > 0 else 20)
        aktuell = {}
        for k, lose in self.lose.items():
            for los in lose:
                aktuell[los[0]] = los[1]
        for e in self.rows["dbo.tWarenLagerEingang"]:
            e["fAnzahlAktuell"] = round(aktuell.get(e["kWarenLagerEingang"], 0.0), 4)
        ausgeliefert = set(self.rows.pop("_ausgeliefert"))
        for a in self.rows["Verkauf.tAuftrag"]:
            if a["kAuftrag"] in ausgeliefert:
                a["nKomplettAusgeliefert"] = 1
        stornos = set(self.storno_rechnungen)
        # Auf eine stornierte Rechnung wird nicht gezahlt – die Zahlung gehört zur Korrektur
        self.rows["dbo.tZahlung"] = [z for z in self.rows["dbo.tZahlung"] if z["kRechnung"] not in stornos]
        for rg in self.rows["Rechnung.tRechnung"]:
            if rg["kRechnung"] in stornos:
                rg["nStorno"] = 1
        return self.rows

    def inventur(self, tag):
        r = self.r
        zeit = dt.datetime.combine(tag, dt.time(14))
        for k in r.sample([k for k in self.art if not self.art[k].get("set") and self.bestand[k] > 5], 12):
            diff = r.choice([-3, -2, -1, -1, 1, 2])
            if diff < 0:
                self.ausbuchen(k, -diff, zeit, 100, kommentar=f"Inventur {tag.year}")
            else:
                self.einbuchen(k, diff, self.ek(k, tag), zeit, 100, kommentar=f"Inventur {tag.year}")

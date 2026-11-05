"""Stammdaten der erfundenen Firma. Gibt ein Dict mit allem zurück, was die
Bewegungsdaten brauchen (Kunden, Artikel mit EK/VK, Lieferanten …)."""
import datetime as dt
import random

from tools.demo_daten import welt

START = dt.datetime(2023, 11, 1, 8, 0)


def _tel(r):
    return f"0{r.randint(200, 999)} 99{r.randint(1000, 9999)}"


def _plz_ort_bundesland(r):
    plz, ort = r.choice(welt.ORTE)
    return plz, ort


def anlegen(w, r: random.Random) -> dict:
    d = {}
    f = welt.FIRMA
    # ── Firma, Benutzer, Shop ────────────────────────────────────────────────
    w.schreiben("dbo.tfirma", [dict(kFirma=1, cName=f["cName"], cStrasse=f["cStrasse"], cPLZ=f["cPLZ"],
                                   cOrt=f["cOrt"], cLand=f["cLand"], cTel=f["cTel"], cFax=f["cFax"],
                                   cEMail=f["cEMail"], cSteuerNr=f["cSteuerNr"], cInet=f["cInet"],
                                   cAktiv="Y", cLandISO="DE")])
    w.schreiben("dbo.tFirmaHistory", [dict(kFirmaHistory=1, kFirma=1, cName=f["cName"], cStrasse=f["cStrasse"],
                                          cPLZ=f["cPLZ"], cOrt=f["cOrt"], cLand=f["cLand"], cTel=f["cTel"],
                                          cFax=f["cFax"], cEMail=f["cEMail"], cSteuerNr=f["cSteuerNr"],
                                          cLandISO="DE")])
    w.schreiben("dbo.tBenutzer", [dict(kBenutzer=i, cName=n, cLogin=n.split()[0].lower(), kFirma=1, nAktiv=1, nType=0,
                                      cEMail=f"{n.split()[0].lower()}@mediversa.example.com")
                                 for i, n in enumerate(welt.BENUTZER, 1)])
    d["benutzer"] = [1, 2, 3]
    w.schreiben("dbo.tShop", [dict(kShop=1, cName="MediVersa Onlineshop", kFirma=1, nTyp=0, nAktiv=1, kSprache=1)])

    # ── Kataloge ─────────────────────────────────────────────────────────────
    w.schreiben("dbo.tKundenGruppe", [dict(kKundenGruppe=k, cName=n, fRabatt=rab, nStandard=1 if k == 1 else 0)
                                      for k, n, rab, _ in welt.KUNDENGRUPPEN])
    w.schreiben("dbo.tZahlungsart", [dict(kZahlungsart=k, cName=n, nAktiv=1) for k, n in welt.ZAHLUNGSARTEN])
    w.schreiben("dbo.tVersandArt", [dict(kVersandArt=k, cName=n, cAktiv="Y", cInet="N", fMwSt=19, kSteuerklasse=1)
                                    for k, n, _, _p in welt.VERSANDARTEN])
    d["versandarten"] = welt.VERSANDARTEN
    w.schreiben("dbo.tEinheit", [dict(kEinheit=i) for i, _ in enumerate(welt.EINHEITEN, 1)])
    w.schreiben("dbo.tEinheitSprache", [dict(kEinheit=i, kSprache=1, cName=n) for i, n in enumerate(welt.EINHEITEN, 1)])
    d["einheit_id"] = {n: i for i, n in enumerate(welt.EINHEITEN, 1)}
    w.schreiben("dbo.tWarenLager", [dict(kWarenLager=1, cName="Hauptlager Stuttgart", cBeschreibung="Zentrallager",
                                         cStrasse="Am Demopark 7", cPLZ="70173", cOrt="Stuttgart", cLand="Deutschland",
                                         kFirma=1, nAktiv=1, nFulfillment=0, nLagerplatzVerwaltung=1)])
    plaetze = []
    for i, (gang, fach) in enumerate(((g, f_) for g in "ABCDE" for f_ in range(1, 9)), 1):
        plaetze.append(dict(kWarenLagerPlatz=i, kWarenLager=1, cName=f"{gang}-{fach:02d}", nSort=i, nStatus=0))
    w.schreiben("dbo.tWarenLagerPlatz", plaetze)
    d["lagerplaetze"] = [p["kWarenLagerPlatz"] for p in plaetze]
    w.schreiben("dbo.tHersteller", [dict(kHersteller=i, cName=n, nSort=i) for i, n in enumerate(welt.HERSTELLER, 1)])
    w.schreiben("dbo.tWarengruppe", [dict(kWarengruppe=i, cName=g) for i, (g, _) in enumerate(welt.SORTIMENT, 1)])

    # ── Lieferanten ──────────────────────────────────────────────────────────
    lief = []
    for i, (firma, iso, ort, plz, lz) in enumerate(welt.LIEFERANTEN, 1):
        lief.append(dict(kLieferant=i, cFirma=firma, cStrasse=f"{r.choice(welt.STRASSEN)} {r.randint(1, 120)}",
                         cPLZ=plz, cOrt=ort, cLand={"DE": "Deutschland", "AT": "Österreich", "NL": "Niederlande",
                                                    "PL": "Polen"}[iso], cISO=iso, cTelZentralle=_tel(r),
                         cEMail=f"bestellung@lieferant{i}.example.net", dErstellt=START, cAktiv="Y", kSprache=1,
                         cLieferantID=f"L{1000 + i}", cWaehrungISO="EUR", nLieferzeit=lz, nZahlungsziel=30,
                         fSkonto=2 if i % 3 == 0 else 0, fMindestbestellwert=150 if i % 2 else 0, nType=0,
                         cUstid="" if iso == "DE" else f"{iso}99999999{i}", nStandardFirma=1, nStandardLager=1))
    w.schreiben("dbo.tlieferant", lief)
    d["lieferanten"] = {l["kLieferant"]: l for l in lief}

    # ── Artikel ──────────────────────────────────────────────────────────────
    artikel, beschr, liefart, preise, preisdet, stueck = [], [], [], [], [], []
    k = 0
    for wg_id, (wg, familien) in enumerate(welt.SORTIMENT, 1):
        for fam_i, (name, varianten, (vk_lo, vk_hi), marge, einheit, taric, herkunft, gew, stkl, mhd) in enumerate(familien):
            herst = r.randint(1, len(welt.HERSTELLER))
            lief_id = r.choice([l for l in d["lieferanten"] if l != 7] if herkunft == "DE" else list(d["lieferanten"]))
            # Kleinpackungen gibt es zusätzlich im Karton (10 ×) – günstiger je Stück
            liste = [(v, 1) for v in varianten]
            if einheit in ("Box", "Pack", "Dose", "Rolle") and vk_hi < 25:
                liste += [(v, 10) for v in varianten]
            for v_i, (var, menge) in enumerate(liste):
                k += 1
                pos = v_i % len(varianten)
                vk = round(vk_lo + (vk_hi - vk_lo) * (pos / max(1, len(varianten) - 1)), 2) if len(varianten) > 1 else vk_lo
                if menge > 1:
                    vk = round(vk * menge * 0.92, 2)
                vk = round(vk * r.uniform(0.97, 1.03), 2)
                ek = round(vk * (1 - marge) * r.uniform(0.94, 1.06), 2)
                beliebt = r.random()
                a = dict(kArtikel=k, cArtNr=f"MV-{wg_id:02d}{fam_i + 1:02d}{v_i + 1:02d}" + ("-K" if menge > 1 else ""), fVKNetto=vk, fEKNetto=ek,
                         fLetzterEK=ek, cAktiv="Y", cLagerAktiv="Y", cLagerArtikel="N", cTeilbar="N",
                         cLagerKleinerNull="N", cInet="Y", cTopArtikel="Y" if beliebt > 0.93 else "N",
                         nIstVater=0, kVaterArtikel=0, nDelete=0, kSteuerklasse=stkl, kWarengruppe=wg_id,
                         kHersteller=herst, kZustand=1, kVersandklasse=1, fGewicht=gew * menge, fArtGewicht=gew * menge,
                         cTaric=taric, cHerkunftsland=herkunft, cHAN=f"{welt.HERSTELLER[herst - 1][:3].upper()}-{r.randint(10000, 99999)}",
                         cBarcode=f"4099{r.randint(100000000, 999999999)}",
                         nMidestbestand=r.choice([0, 0, 5, 10, 20, 30]), fPackeinheit=1,
                         dErstelldatum=START - dt.timedelta(days=r.randint(30, 900)),
                         nSort=0, cNeu="N", cDelInet="N", cPreisliste="Y", cLagerVariation="N",
                         nProzentualePreisStaffelAktiv=0, kStueckliste=0, nPuffer=0)
                artikel.append(a)
                vollname = f"{name} – {var}" if var not in ("Standard", "aktuelle Auflage") else name
                if menge > 1:
                    vollname += f" (Karton à {menge})"
                beschr.append(dict(kArtikel=k, kSprache=1, kPlattform=1, kShop=0, cName=vollname,
                                   cBeschreibung=f"{vollname}. Für den professionellen Einsatz in Praxis und Pflege.",
                                   cKurzBeschreibung=wg))
                beschr.append(dict(kArtikel=k, kSprache=1, kPlattform=2, kShop=1, cName=vollname,
                                   cBeschreibung=f"{vollname} – jetzt im MediVersa Onlineshop.", cKurzBeschreibung=wg))
                liefart.append(dict(kLiefArtikel=k, tArtikel_kArtikel=k, tLieferant_kLieferant=lief_id, fEKNetto=ek,
                                    fEKBrutto=round(ek * 1.19, 2), cLiefArtNr=f"{lief_id:02d}-{r.randint(10000, 99999)}",
                                    cWaehrung="EUR", nLieferbar=1, nStandard=1, nLieferzeit=d["lieferanten"][lief_id]["nLieferzeit"],
                                    cName=vollname, fMwSt=19 if stkl == 1 else 7))
                artikel[-1]["_meta"] = dict(name=vollname, einheit="Karton" if menge > 1 else einheit, wg=wg_id, mhd=mhd, lief=lief_id,
                                            beliebt=beliebt * (0.5 if menge > 1 else 1), marge=marge, gew=gew * menge, stkl=stkl, vk=vk, ek=ek)
    # Kunden-/Gruppenpreise für Praxen, Kliniken mit Staffel
    kp = 0
    for a in artikel:
        for gruppe, faktor in ((2, 0.97), (3, 0.96), (5, 0.90)):
            if r.random() < 0.35:
                kp += 1
                preise.append(dict(kPreis=kp, kArtikel=a["kArtikel"], kKundenGruppe=gruppe, kShop=0, kKunde=0))
                basis = round(a["fVKNetto"] * faktor, 2)
                preisdet.append(dict(kPreis=kp, nAnzahlAb=0, fNettoPreis=basis, fProzent=0))
                if a["fVKNetto"] < 30 and r.random() < 0.6:
                    preisdet.append(dict(kPreis=kp, nAnzahlAb=10, fNettoPreis=round(basis * 0.95, 2), fProzent=0))
                    preisdet.append(dict(kPreis=kp, nAnzahlAb=50, fNettoPreis=round(basis * 0.90, 2), fProzent=0))
    # Ein paar Klinikpreise bewusst UNTER Mindestmarge (Kalkulation zeigt sie)
    vorhanden = {(p["kArtikel"], p["kKundenGruppe"]): p["kPreis"] for p in preise}
    for a in r.sample(artikel, 8):
        zu_billig = round(a["fEKNetto"] * 1.04, 2)
        kp_alt = vorhanden.get((a["kArtikel"], 5))
        if kp_alt:
            for x in preisdet:
                if x["kPreis"] == kp_alt and x["nAnzahlAb"] == 0:
                    x["fNettoPreis"] = zu_billig
            continue
        kp += 1
        preise.append(dict(kPreis=kp, kArtikel=a["kArtikel"], kKundenGruppe=5, kShop=0, kKunde=0))
        preisdet.append(dict(kPreis=kp, nAnzahlAb=0, fNettoPreis=zu_billig, fProzent=0))

    # Stückliste: Praxis-Starterset
    k += 1
    set_teile = [a for a in artikel if a["kWarengruppe"] in (1, 2, 3)][:4]
    artikel.append(dict(kArtikel=k, cArtNr="MV-SET-001", fVKNetto=79.0, fEKNetto=0, fLetzterEK=0, cAktiv="Y",
                        cLagerAktiv="N", cLagerArtikel="N", cTeilbar="N", cLagerKleinerNull="N", cInet="Y",
                        nIstVater=0, kVaterArtikel=0, nDelete=0, kSteuerklasse=1, kWarengruppe=6, kHersteller=1,
                        kZustand=1, kVersandklasse=1, fGewicht=3.0, fArtGewicht=3.0, cTaric="63079098",
                        cHerkunftsland="DE", kStueckliste=k, dErstelldatum=START, nSort=0, cNeu="Y", cDelInet="N",
                        cPreisliste="Y", cLagerVariation="N", nProzentualePreisStaffelAktiv=0, nPuffer=0,
                        _meta=dict(name="Praxis-Starterset Hygiene", einheit="Karton", wg=6, mhd=False, lief=1,
                                   beliebt=0.5, marge=0.3, gew=3.0, stkl=1, vk=79.0, ek=0, set=True)))
    beschr.append(dict(kArtikel=k, kSprache=1, kPlattform=1, kShop=0, cName="Praxis-Starterset Hygiene",
                       cBeschreibung="Set aus Handschuhen, Desinfektion und Verbandmaterial.", cKurzBeschreibung="Set"))
    for i, t in enumerate(set_teile):
        stueck.append(dict(kStueckliste=k, kArtikel=t["kArtikel"], fAnzahl=2 if i < 2 else 1, nSort=i, kVaterArtikel=k))

    # Sonderpreise (aktuell laufende Aktion + eine abgelaufene)
    sp, spp = [], []
    for i, a in enumerate(r.sample(artikel[:-1], 10), 1):
        laeuft = i <= 6
        sp.append(dict(kArtikelSonderpreis=i, kArtikel=a["kArtikel"], nAktiv=1, nIstDatum=1,
                       dStart=dt.datetime(2026, 10, 15) if laeuft else dt.datetime(2026, 3, 1),
                       dEnde=dt.datetime(2026, 11, 30) if laeuft else dt.datetime(2026, 3, 31), nIstAnzahl=0, nAnzahl=0))
        for g in (1, 2, 3, 4, 5, 6):
            spp.append(dict(kArtikelSonderpreis=i, kKundenGruppe=g, kShop=0, fNettoPreis=round(a["fVKNetto"] * 0.88, 2)))

    # Typische Pflegefehler, damit der Stammdaten-Check etwas findet
    normal = [a for a in artikel if not a["_meta"].get("set")]
    pf = r.sample(normal, 16)
    for a in pf[0:3]:
        a["fGewicht"] = 0; a["fArtGewicht"] = 0
    for a in pf[3:6]:
        a["cTaric"] = ""
    for a in pf[6:8]:
        a["cHerkunftsland"] = ""
    pf[8]["cBarcode"] = pf[9]["cBarcode"]                       # doppelte EAN
    pf[10]["cBarcode"] = "+H123" + pf[10]["cArtNr"].replace("-", "") + "1"   # HIBC
    pf[11]["fVKNetto"] = round(pf[11]["fEKNetto"] * 0.93, 2)    # VK unter EK
    pf[11]["_meta"]["vk"] = pf[11]["fVKNetto"]
    pf[12]["kWarengruppe"] = 0                                    # ohne Warengruppe
    meta = {a["kArtikel"]: a.pop("_meta") for a in artikel}
    w.schreiben("dbo.tArtikel", artikel)
    w.schreiben("dbo.tArtikelBeschreibung", beschr)
    w.schreiben("dbo.tLiefArtikel", liefart)
    w.schreiben("dbo.tPreis", preise)
    w.schreiben("dbo.tPreisDetail", preisdet)
    w.schreiben("dbo.tStueckliste", stueck)
    d["stueckliste"] = stueck
    w.schreiben("dbo.tArtikelSonderpreis", sp)
    w.schreiben("dbo.tSonderpreise", spp)
    d["artikel"] = {a["kArtikel"]: {**a, **meta[a["kArtikel"]]} for a in artikel}
    d["gruppenpreis"] = {}
    for p in preise:
        det = [x for x in preisdet if x["kPreis"] == p["kPreis"] and x["nAnzahlAb"] == 0]
        d["gruppenpreis"][(p["kArtikel"], p["kKundenGruppe"])] = det[0]["fNettoPreis"]

    # ── Kunden ───────────────────────────────────────────────────────────────
    kunden, adressen = [], []
    gewichte = [g[3] for g in welt.KUNDENGRUPPEN]
    ka = 0
    for kk in range(1, 1301):
        gruppe = r.choices([g[0] for g in welt.KUNDENGRUPPEN], gewichte)[0]
        v, n, n2 = r.choice(welt.VORNAMEN), r.choice(welt.NACHNAMEN), r.choice(welt.NACHNAMEN)
        ausland = r.random() < 0.04
        if ausland:
            iso, land, plz, ort = r.choice(welt.ORTE_AUSLAND)
        else:
            iso, land = "DE", "Deutschland"
            plz, ort = r.choice(welt.ORTE)
        strasse = r.choice(welt.STRASSEN)
        firma = "" if gruppe == 1 else r.choice(welt.PRAXISFORMEN[gruppe]).format(n=n, n2=n2, v=v, o=ort, s=strasse)
        erstellt = START - dt.timedelta(days=r.randint(0, 1200)) if kk <= 900 else \
            START + dt.timedelta(days=int((kk - 900) / 400 * 1090))
        zz = 30 if gruppe in (2, 3, 5) else (14 if gruppe in (4, 6) else 0)
        za = 1 if gruppe != 1 else r.choice([3, 4, 4, 5])
        kunden.append(dict(kKunde=kk, cKundenNr=f"K{10000 + kk}", dErstellt=erstellt, fRabatt=0,
                           cSperre="Y" if r.random() < 0.015 else "N", kKundenGruppe=gruppe, nZahlungsziel=zz,
                           kSprache=1, kZahlungsart=za, nDebitorennr=10000 + kk, kFirma=1,
                           cSteuerNr="", fSkonto=2 if gruppe == 5 else 0))
        mail = f"{(firma or f'{v}.{n}').lower().replace(' ', '.').replace('&', 'und')[:28]}@example.org"
        if r.random() < 0.03:
            mail = ""                                                  # Kunde ohne E-Mail
        for typ in (1, 0):
            ka += 1
            adressen.append(dict(kAdresse=ka, kKunde=kk, cFirma=firma, cVorname=v, cName=n,
                                 cStrasse=f"{strasse} {r.randint(1, 140)}", cPLZ=plz, cOrt=ort, cLand=land,
                                 cISO=iso, cTel=_tel(r), cMail=mail, nStandard=1, nTyp=typ,
                                 cUSTID=f"{iso}99999{kk:04d}" if ausland and firma else ""))
        kunden[-1]["_meta"] = dict(gruppe=gruppe, firma=firma, v=v, n=n, plz=plz, ort=ort, iso=iso, land=land,
                                   strasse=adressen[-1]["cStrasse"], mail=mail, erstellt=erstellt, zz=zz, za=za,
                                   # Bestellfreude und Zahlungsmoral je Kunde
                                   aktiv=r.lognormvariate(0, 0.9) * (3.0 if gruppe == 5 else 1.0),
                                   zahlt=r.choices(["puenktlich", "spaet", "schlecht"], [0.78, 0.18, 0.04])[0],
                                   abwandern=r.random() < 0.12)
    meta = {k_["kKunde"]: k_.pop("_meta") for k_ in kunden}
    w.schreiben("dbo.tkunde", kunden)
    w.schreiben("dbo.tAdresse", adressen)
    d["kunden"] = {k_["kKunde"]: {**k_, **meta[k_["kKunde"]]} for k_ in kunden}
    return d

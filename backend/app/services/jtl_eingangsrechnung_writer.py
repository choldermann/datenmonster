"""
Write-Logik für JTL-Eingangsrechnungen (Kopf + Positionen).

Grundlage: Golden-Master-Diff auf der Test-WaWi (2026-07-24, erweitert 2026-09-04).
Beim Anlegen einer Eingangsrechnung berührt JTL DB-weit nur diese Tabellen:
  - dbo.tEingangsrechnung                 (INSERT, kEingangsrechnung = IDENTITY)
  - dbo.tEingangsrechnungPos              (INSERT je Position, IDENTITY)
  - dbo.tEingangsrechnungPosZusatzkosten  (INSERT je Position, wenn Fracht/Zuschläge)
  - dbo.tLaufendeNummern                  (UPDATE des Nummernkreises – NICHT selbst
                                           anfassen, sondern über dbo.spGetNextNummer)
Keine Buchungs-/Export-Queue, keine FiBu. Die Rechnung entsteht UNVERBUCHT
(nStatus = 0) und ist damit bestand-entkoppelt.

Die Bewertung fassen wir bewusst nicht an: erst beim Verbuchen in JTL wandert die
Fracht über tWarenLagerEingang.fEKEinzel (= Positions-EK + Zusatzkosten/Menge) in
den durchschnittlichen Netto-EK, den JTL als gewichtetes Mittel der Lagerschichten
in tArtikel.fEKNetto fortschreibt. Verbuchen setzt zudem einen Wareneingang voraus.

Write-Rezept (eine Transaktion):
  1. EXEC dbo.spGetNextNummer @cName='Eingangsrechnung' → cEigeneRechnungsnummer
  2. INSERT tEingangsrechnung → SCOPE_IDENTITY() = kEingangsrechnung
  3. INSERT tEingangsrechnungPos (je Position) mit Bestell-Matching → SCOPE_IDENTITY()
  4. INSERT tEingangsrechnungPosZusatzkosten (verteilte Fracht je Position)

Dieser Writer löst zuerst alle Referenzen read-only auf (Lieferant, Artikel,
Bestellung, Dublette), baut daraus einen Plan und führt im Dry-Run NICHTS aus.
"""
from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, text

from app.core.database import SessionLocal
from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str

NUMMERNKREIS_NAME = "Eingangsrechnung"

# Echte DB-Spalten von tEingangsrechnungPos (die Positions-Dicts tragen zusätzlich
# Metadaten wie status/_match/_kandidaten fürs Formular, die NICHT ins INSERT dürfen)
POS_DB_COLS = ["kEingangsrechnung", "kLieferantenbestellung", "kArtikel", "cArtNr",
               "cLieferantenArtNr", "cName", "cLieferantenBezeichnung", "cEinheit",
               "cHinweis", "fMenge", "fEKNetto", "fMwSt", "nPosTyp", "kLieferantenBestellungPos"]


# ── Eingabe-Strukturen (normalisiert, z.B. aus einer geparsten E-Rechnung) ──────
@dataclass
class ERPositionInput:
    cName: str
    fMenge: float
    fEKNetto: float
    fMwSt: float                                  # Prozentwert, z.B. 19.0
    cArtNr: Optional[str] = None                  # eigene Artikelnr. → löst kArtikel auf
    cLieferantenArtNr: Optional[str] = None
    cLieferantenBezeichnung: Optional[str] = None
    cEinheit: Optional[str] = None
    nPosTyp: int = 1
    # Bestellreferenz aus der Rechnung (z.B. ZUGFeRD BuyerOrderReferencedDocument)
    # = JTLs cEigeneBestellnummer; stärkstes Matching-Signal wenn vorhanden
    bestellnummer: Optional[str] = None
    # Matching-Anker – wenn nicht gesetzt, wird über Scoring gesucht
    kLieferantenbestellung: Optional[int] = None
    kLieferantenBestellungPos: Optional[int] = None
    # Anmerkungen des Auslesers zu GENAU DIESER Zeile. Sie hängen an der Position
    # und nicht am Kopf, damit sie im Formular unter ihrer Zeile stehen können und
    # die Zuordnung auch dann hält, wenn das Formular Zeilen umwidmet oder der
    # Beleg zwischen Vorschau und Freigabe hin- und hergereicht wird.
    leser_hinweise: list[str] = field(default_factory=list)


@dataclass
class ERZusatzkostenInput:
    """Fracht/Zuschlag/Rabatt auf Dokumentebene (aus ZUGFeRD SpecifiedTradeAllowanceCharge)."""
    cName: str
    betrag: float
    fMwSt: float = 0.0
    ist_zuschlag: bool = True         # True=Zuschlag/Fracht, False=Rabatt/Allowance


@dataclass
class ERKopfInput:
    cFremdbelegnummer: str                         # Lieferanten-Rechnungsnr. (Pflicht)
    dBelegdatum: datetime.datetime
    positionen: list[ERPositionInput]
    dZahlungsziel: Optional[datetime.datetime] = None
    # Rechnungssummen aus der E-Rechnung (für den Summen-Abgleich)
    nettoSumme: Optional[float] = None             # TaxBasisTotal (BT-109)
    steuerSumme: Optional[float] = None            # TaxTotal (BT-110)
    bruttoSumme: Optional[float] = None            # GrandTotal (BT-112)
    zusatzkosten: list[ERZusatzkostenInput] = field(default_factory=list)
    kBenutzer: int = 1
    cHinweise: Optional[str] = None
    # Lieferant identifizieren – mind. eins von diesen dreien
    kLieferant: Optional[int] = None
    ustIdNr: Optional[str] = None
    lieferantName: Optional[str] = None
    # Optionale Adress-Overrides aus der Rechnung (E-Rechnung ist Quelle der Wahrheit;
    # fehlt ein Feld, wird aus dem Lieferantenstamm ergänzt)
    cLieferant: Optional[str] = None
    cStrasse: Optional[str] = None
    cPLZ: Optional[str] = None
    cOrt: Optional[str] = None
    cLandISO: Optional[str] = None
    cMail: Optional[str] = None
    cTel: Optional[str] = None
    cFax: Optional[str] = None
    # Bestellreferenz auf Kopfebene (gilt für alle Positionen ohne eigene Referenz)
    bestellnummer: Optional[str] = None
    # Woher die Daten stammen: "e-rechnung" = strukturiert aus ZUGFeRD/XRechnung
    # (exakt), "pdf_ki" = aus einem gewöhnlichen PDF ausgelesen. Der Unterschied
    # ist keine Kleinigkeit: bei einer E-Rechnung ist ein Wert richtig oder er
    # fehlt, bei der KI-Auslesung kann er plausibel aussehen und falsch sein.
    # Deshalb reist die Herkunft bis in die Freigabe mit.
    quelle: str = "e-rechnung"
    # Anmerkungen des Auslesers zu Stellen, an denen er nachbessern musste –
    # gehören dem Menschen vor die Augen, nicht in die Datenbank.
    leser_hinweise: list[str] = field(default_factory=list)


# ── Ergebnis-Strukturen ─────────────────────────────────────────────────────────
@dataclass
class ERWritePlan:
    ok: bool
    dry_run: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    lieferant: dict = field(default_factory=dict)          # aufgelöster Stamm
    naechste_nummer: Optional[str] = None                  # gepeekt (nicht verbraucht)
    kopf_werte: dict = field(default_factory=dict)         # Spalte → Wert
    positionen: list[dict] = field(default_factory=list)   # je Pos: Spalte → Wert (+ _match-Info)
    statements: list[str] = field(default_factory=list)    # parametrisiertes SQL (Anzeige)
    zusatzkosten: list[dict] = field(default_factory=list)  # Fracht/Zuschläge (Dokumentebene)
    kostenarten: list[dict] = field(default_factory=list)   # Katalog dieser Wawi (fürs Zuordnen)
    zusatzkosten_zeilen: list[dict] = field(default_factory=list)  # verteilt, je Position
    summen: dict = field(default_factory=dict)             # {rechnung_*, berechnet_*, differenz}
    reconciliation_ok: Optional[bool] = None               # Summen-Abgleich bestanden?
    # nach echtem Write gefüllt:
    kEingangsrechnung: Optional[int] = None

    def to_dict(self) -> dict:
        """JSON-serialisierbar fürs Freigabe-Formular / API."""
        def _j(v):
            if isinstance(v, Decimal):
                return float(v)
            if isinstance(v, (datetime.datetime, datetime.date)):
                return v.isoformat()
            if isinstance(v, dict):
                return {k: _j(x) for k, x in v.items()}
            if isinstance(v, list):
                return [_j(x) for x in v]
            return v
        return {
            "ok": self.ok, "dry_run": self.dry_run,
            "warnings": self.warnings, "errors": self.errors,
            "lieferant": _j(self.lieferant),
            "naechste_nummer": self.naechste_nummer,
            "kopf_werte": _j(self.kopf_werte),
            "positionen": _j(self.positionen),
            "zusatzkosten": _j(self.zusatzkosten),
            "kostenarten": _j(self.kostenarten),
            "zusatzkosten_zeilen": _j(self.zusatzkosten_zeilen),
            "summen": _j(self.summen),
            "reconciliation_ok": self.reconciliation_ok,
            "statements": self.statements,
            "kEingangsrechnung": self.kEingangsrechnung,
        }

    def report(self) -> str:
        L = []
        L.append(f"{'DRY-RUN' if self.dry_run else 'WRITE'}  →  {'OK' if self.ok else 'FEHLER'}")
        if self.errors:
            L.append("\nFEHLER:")
            L += [f"  ✗ {e}" for e in self.errors]
        if self.warnings:
            L.append("\nWarnungen:")
            L += [f"  ⚠ {w}" for w in self.warnings]
        if self.lieferant:
            L.append(f"\nLieferant: kLieferant={self.lieferant.get('kLieferant')} "
                     f"{self.lieferant.get('cFirma')!r} (Match: {self.lieferant.get('_match')})")
        if self.dry_run and self.naechste_nummer is not None:
            L.append(f"cEigeneRechnungsnummer (gepeekt, nicht verbraucht): {self.naechste_nummer}")
        if self.kopf_werte:
            L.append("\ntEingangsrechnung (Kopf):")
            for k, v in self.kopf_werte.items():
                L.append(f"    {k:24} = {v!r}")
        for i, p in enumerate(self.positionen, 1):
            aq = f"  [Artikel via {p.get('_artikel_quelle')}]" if p.get("_artikel_quelle") else ""
            st = p.get("status", "?")
            L.append(f"\ntEingangsrechnungPos #{i}  [{st}]  (Match: {p.get('_match')}){aq}:")
            for k, v in p.items():
                if k.startswith("_"):
                    continue
                L.append(f"    {k:26} = {v!r}")
            for meldung in (p.get("_meldungen") or []):
                L.append(f"    ⚠ {meldung}")
            kand = p.get("_kandidaten") or []
            if len(kand) > 1:
                L.append(f"    Kandidaten ({len(kand)}, für 4-Augen-Freigabe):")
                for c in kand:
                    mark = "→" if c["kPos"] == p.get("kLieferantenBestellungPos") else " "
                    L.append(f"     {mark} #{c['kPos']} {c['bestellnr']} "
                             f"EK={c['ek']:.2f} Menge={c['menge']:g} offen={c['offen']:g} "
                             f"score={c['score']:.0f} [{c['why']}]")
        if self.zusatzkosten:
            L.append("\nZusatzkosten (Fracht/Zuschläge):")
            for z in self.zusatzkosten:
                vz = "＋" if z.get("ist_zuschlag", True) else "－"
                art = (f"→ Kostenart „{z['kostenart']}“ ({z.get('kostenart_quelle')})"
                       if z.get("kostenart") else "→ KEINE Kostenart zugeordnet")
                L.append(f"    {vz} {z['cName']}: {z['betrag']:.2f} (MwSt {z.get('fMwSt',0)}%) "
                         f"[{z.get('quelle')}] {art}")
        if self.zusatzkosten_zeilen:
            L.append("\nVerteilung auf die Positionen (mengenproportional):")
            for zk in self.zusatzkosten_zeilen:
                pos = (self.positionen[zk["_zeile"]].get("cName")
                       if zk["_zeile"] < len(self.positionen) else "?")
                L.append(f"    Kostenart {zk['kZusatzkosten']} → {pos}: "
                         f"{zk['dWert']} (MwSt {zk['fMwst']}%)")
        if self.summen:
            s = self.summen
            # None heisst: der Beleg nennt keine eigene Summe, es wurde also gar
            # nicht verglichen. Das darf nicht wie ein gescheiterter Abgleich
            # aussehen – gerechnet haben wir trotzdem.
            amp = {True: "✅", False: "❌"}.get(self.reconciliation_ok, "– kein Vergleich")
            L.append(f"\nSummen-Abgleich {amp}:")
            L.append(f"    Rechnung: netto={s.get('rechnung_netto')} steuer={s.get('rechnung_steuer')} "
                     f"brutto={s.get('rechnung_brutto')}")
            L.append(f"    Berechnet: netto={s.get('berechnet_netto')} steuer={s.get('berechnet_steuer')} "
                     f"brutto={s.get('berechnet_brutto')}  (Δ {s.get('differenz')})")
        if self.kEingangsrechnung:
            L.append(f"\n✓ Geschrieben: kEingangsrechnung = {self.kEingangsrechnung}")
        return "\n".join(L)


class EingangsrechnungWriter:
    def __init__(self, connection_id: int):
        db = SessionLocal()
        try:
            conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
            if not conn:
                raise ValueError(f"DB-Verbindung #{connection_id} nicht gefunden")
            if conn.db_type != "mssql":
                raise ValueError("Eingangsrechnungs-Write nur für JTL/MSSQL")
            self._engine = create_engine(get_engine_str(conn),
                                         connect_args={"timeout": 30, "login_timeout": 10})
        finally:
            db.close()

    # ── Read-only-Auflösungen ────────────────────────────────────────────────────
    def _resolve_lieferant(self, conn, kopf: ERKopfInput, plan: ERWritePlan) -> Optional[dict]:
        row = None
        match = None
        if kopf.kLieferant:
            row = conn.execute(text("SELECT * FROM dbo.tlieferant WHERE kLieferant = :k"),
                               {"k": kopf.kLieferant}).mappings().first()
            match = "kLieferant"
        if row is None and kopf.ustIdNr:
            row = conn.execute(text(
                "SELECT * FROM dbo.tlieferant WHERE REPLACE(cUstid,' ','') = :u"),
                {"u": kopf.ustIdNr.replace(" ", "")}).mappings().first()
            match = "USt-IdNr"
        if row is None and kopf.lieferantName:
            hits = conn.execute(text(
                "SELECT * FROM dbo.tlieferant WHERE cFirma = :n"),
                {"n": kopf.lieferantName}).mappings().all()
            if len(hits) == 1:
                row, match = hits[0], "Firmenname (exakt)"
            elif len(hits) > 1:
                plan.errors.append(f"Lieferant '{kopf.lieferantName}': {len(hits)} Treffer – nicht eindeutig")
                return None
        if row is None:
            plan.errors.append("Lieferant nicht auflösbar (weder kLieferant, USt-IdNr noch Firmenname trafen)")
            return None
        d = dict(row)
        d["_match"] = match
        return d

    def _resolve_artikel(self, conn, pos: ERPositionInput, kLieferant: int) -> dict:
        """
        Löst kArtikel auf: zuerst über die eigene cArtNr (tArtikel), sonst als
        Fallback über die Lieferanten-Artikelnummer (tliefartikel) – echte
        Rechnungen tragen oft nur die Lieferanten-Nr. Gibt kArtikel, die
        kanonische eigene cArtNr, die Quelle und ggf. eine Warnung zurück.
        """
        kArtikel = None
        quelle = None
        warnung = None

        # 1) eigene Artikelnummer
        if pos.cArtNr:
            r = conn.execute(text("SELECT kArtikel FROM dbo.tArtikel WHERE cArtNr = :a"),
                             {"a": pos.cArtNr}).first()
            if r:
                kArtikel, quelle = int(r[0]), "cArtNr"

        # 2) Fallback: Lieferanten-Artikelnummer über tliefartikel
        if kArtikel is None and pos.cLieferantenArtNr and kLieferant:
            rows = conn.execute(text(
                "SELECT tArtikel_kArtikel AS ka, nStandard FROM dbo.tliefartikel "
                "WHERE tLieferant_kLieferant = :kl AND cLiefArtNr = :nr"),
                {"kl": kLieferant, "nr": pos.cLieferantenArtNr}).mappings().all()
            arts = {int(r["ka"]) for r in rows}
            std = list({int(r["ka"]) for r in rows if r["nStandard"] == 1})
            if len(arts) == 1:
                kArtikel, quelle = arts.pop(), "Lieferanten-ArtNr"
            elif len(std) == 1:
                kArtikel, quelle = std[0], "Lieferanten-ArtNr (Standard)"
            elif len(arts) > 1:
                warnung = (f"Lieferanten-ArtNr '{pos.cLieferantenArtNr}' mehrdeutig "
                           f"({len(arts)} Artikel) – manuell zuordnen")

        # kanonische eigene cArtNr für die Zielzeile (falls Rechnung nur Liefer-Nr trug)
        cArtNr = pos.cArtNr
        if kArtikel is not None and not cArtNr:
            r = conn.execute(text("SELECT cArtNr FROM dbo.tArtikel WHERE kArtikel = :k"),
                             {"k": kArtikel}).first()
            cArtNr = r[0] if r else None

        return {"kArtikel": kArtikel, "cArtNr": cArtNr, "quelle": quelle, "warnung": warnung}

    def _match_bestellung(self, conn, kLieferant: int, kArtikel: Optional[int],
                          pos: ERPositionInput, kopf: ERKopfInput,
                          used_pos_ids: set) -> dict:
        """
        Findet die passende Bestellposition via Scoring statt „jüngste".
        Signale: Bestellnummer-Referenz (stärkstes), Preis-Match, noch offene
        (nicht schon berechnete) Menge, Mengen-Match, Recency (Tiebreaker).
        Gibt best match + transparente Kandidatenliste + ggf. Warnung zurück.
        """
        if pos.kLieferantenbestellung and pos.kLieferantenBestellungPos:
            return {"kLieferantenbestellung": pos.kLieferantenbestellung,
                    "kLieferantenBestellungPos": pos.kLieferantenBestellungPos,
                    "_match": "explizit vorgegeben", "kandidaten": [], "warnung": None}
        if not kArtikel:
            return {"kLieferantenbestellung": None, "kLieferantenBestellungPos": None,
                    "_match": "kein Artikel → kein Bestell-Match", "kandidaten": [],
                    "warnung": "kein Artikel auflösbar → keine Bestellzuordnung"}

        # `bereits` zaehlt nur Rechnungen mit nDeleted = 0. Eine geloeschte
        # Eingangsrechnung verschwindet in JTL naemlich NICHT: der Kopf wird nur
        # markiert, Positionen und Zusatzkosten bleiben stehen. Ohne den Filter
        # gaelte eine stornierte Rechnung weiter als „bereits berechnet", die
        # Bestellposition bekaeme -50 Punkte und eine Doppelrechnungs-Warnung –
        # ausgerechnet beim Neuerfassen nach einer Stornierung, also genau dann,
        # wenn man die Position wieder braucht. (Positionen loescht JTL dagegen
        # hart, samt ihrer Zusatzkostenzeile.)
        bestellnr_ref = (pos.bestellnummer or kopf.bestellnummer or "").strip()
        rows = conn.execute(text("""
            SELECT bp.kLieferantenBestellung, bp.kLieferantenBestellungPos,
                   b.cEigeneBestellnummer, b.nStatus, b.dErstellt,
                   bp.fMenge, bp.fEKNetto, ISNULL(bp.fMengeGeliefert,0) AS geliefert,
                   (SELECT ISNULL(SUM(er.fMenge),0)
                      FROM dbo.tEingangsrechnungPos er
                      JOIN dbo.tEingangsrechnung r2
                        ON r2.kEingangsrechnung = er.kEingangsrechnung
                     WHERE er.kLieferantenBestellungPos = bp.kLieferantenBestellungPos
                       AND ISNULL(r2.nDeleted,0) = 0) AS bereits,
                   (SELECT COUNT(*) FROM dbo.tWarenLagerEingang w
                     WHERE w.kLieferantenBestellungPos = bp.kLieferantenBestellungPos) AS wareneingaenge
            FROM dbo.tLieferantenBestellungPos bp
            JOIN dbo.tLieferantenBestellung  b ON b.kLieferantenBestellung = bp.kLieferantenBestellung
            WHERE b.kLieferant = :kl AND bp.kArtikel = :ka AND ISNULL(b.nDeleted,0) = 0
        """), {"kl": kLieferant, "ka": kArtikel}).mappings().all()

        menge_inv = float(pos.fMenge)
        ek_inv = float(pos.fEKNetto)
        scored = []
        for r in rows:
            kpos = int(r["kLieferantenBestellungPos"])
            if kpos in used_pos_ids:           # nicht zwei Rechnungszeilen auf dieselbe Bestellpos
                continue
            ek_po = float(r["fEKNetto"]); menge_po = float(r["fMenge"])
            bereits = float(r["bereits"]); offen = menge_po - bereits
            score = 0.0; why = []
            # Preis
            if abs(ek_po - ek_inv) < 0.005:
                score += 50; why.append("Preis exakt")
            elif ek_inv and abs(ek_po - ek_inv) / ek_inv < 0.02:
                score += 25; why.append("Preis ~")
            else:
                why.append(f"Preis {ek_po:.2f}≠{ek_inv:.2f}")
            # noch offen (gegen bereits berechnete ER) – schützt vor Doppel-Berechnung
            if offen >= menge_inv - 1e-9:
                score += 40; why.append("offen genügt")
            elif offen > 0:
                score += 15; why.append(f"nur {offen:g} offen")
            else:
                score -= 50; why.append("bereits voll berechnet")
            # Mengen-Match
            if abs(menge_po - menge_inv) < 1e-9:
                score += 20; why.append("Menge exakt")
            # Wareneingang: nur gelieferte Positionen lassen sich in JTL verbuchen –
            # und erst beim Verbuchen rechnet JTL die Zusatzkosten in den
            # Durchschnitts-EK ein. Eine Bestellposition ohne Lieferung ist damit
            # zwar zuordenbar, aber die Rechnung bliebe in der Wawi liegen.
            geliefert = float(r["geliefert"])
            if geliefert >= menge_inv - 1e-9:
                score += 30; why.append("geliefert")
            elif geliefert > 0:
                score += 10; why.append(f"erst {geliefert:g} geliefert")
            else:
                score -= 20; why.append("nicht geliefert")
            # Bestellnummer-Referenz aus der Rechnung → entscheidend
            if bestellnr_ref and r["cEigeneBestellnummer"] \
                    and bestellnr_ref == r["cEigeneBestellnummer"].strip():
                score += 100; why.append("Bestellnr-Referenz")
            scored.append({
                "kBest": int(r["kLieferantenBestellung"]), "kPos": kpos,
                "bestellnr": r["cEigeneBestellnummer"], "nStatus": int(r["nStatus"]),
                "ek": ek_po, "menge": menge_po, "bereits": bereits, "offen": offen,
                "geliefert": geliefert, "wareneingaenge": int(r["wareneingaenge"]),
                "score": score, "why": ", ".join(why), "dErstellt": r["dErstellt"],
            })

        if not scored:
            return {"kLieferantenbestellung": None, "kLieferantenBestellungPos": None,
                    "_match": "keine freie Bestellposition gefunden", "kandidaten": [],
                    "warnung": "keine (freie) Bestellposition – manuell zuordnen"}

        scored.sort(key=lambda x: (x["score"], x["dErstellt"]), reverse=True)
        best = scored[0]
        warnung = None
        if best["offen"] <= 1e-9:
            warnung = ("gewählte Bestellposition bereits voll berechnet → "
                       "mögliche Doppel-Rechnung, Prüfung nötig")
        elif best["score"] <= 0:
            warnung = ("schwacher Match (Preis abweichend / kaum offen) – Prüfung nötig")
        elif best["geliefert"] <= 1e-9:
            warnung = ("Bestellposition ist noch nicht als geliefert gebucht – die "
                       "Rechnung lässt sich anlegen, in JTL aber erst verbuchen, wenn "
                       "der Wareneingang erfasst ist")
        elif len(scored) > 1 and (best["score"] - scored[1]["score"]) < 15 \
                and "Bestellnr-Referenz" not in best["why"]:
            warnung = (f"mehrdeutig: Top-2 nah beieinander "
                       f"(#{best['kPos']} score {best['score']:.0f} vs "
                       f"#{scored[1]['kPos']} score {scored[1]['score']:.0f})")
        return {"kLieferantenbestellung": best["kBest"],
                "kLieferantenBestellungPos": best["kPos"],
                "_match": f"score {best['score']:.0f}: {best['why']} ({best['bestellnr']})",
                "kandidaten": scored[:5], "warnung": warnung}

    def _find_dublette(self, conn, kLieferant: int, cFremdbelegnummer: str) -> Optional[int]:
        r = conn.execute(text("""
            SELECT kEingangsrechnung FROM dbo.tEingangsrechnung
            WHERE kLieferant = :kl AND cFremdbelegnummer = :nr AND nDeleted = 0
        """), {"kl": kLieferant, "nr": cFremdbelegnummer}).first()
        return int(r[0]) if r else None

    def _peek_nummer(self, conn) -> Optional[str]:
        """Nächste Nummer ansehen OHNE sie zu verbrauchen (@nNoUpdate=1)."""
        try:
            r = conn.execute(text(
                "EXEC dbo.spGetNextNummer @cName=:n, @kFirma=0, @nNoUpdate=1, @nNoSelect=0"),
                {"n": NUMMERNKREIS_NAME}).first()
            return str(r[0]) if r else None
        except Exception as e:  # SP-Aufruf im Read-Kontext soll den Dry-Run nicht killen
            return f"(nicht peekbar: {str(e)[:80]})"

    def kostenarten(self, conn=None) -> list[dict]:
        """Der Zusatzkosten-Katalog dieser Wawi.

        Die Kostenarten sind Stammdaten, die der Anwender in JTL selbst pflegt
        (Einkauf → Eingangsrechnungen → Zusatzkosten definieren). **Die IDs sind
        installationsspezifisch:** kZusatzkosten 2 heißt bei einem Kunden
        „Frachtkosten", beim nächsten „Gefahrgutzuschlag". Deshalb wird niemals
        eine ID geraten – wir lösen über den Namen auf und lassen den Anwender
        zuordnen, wenn das nicht eindeutig gelingt.

        `nPreis = 1` heißt „Beeinflusst Gesamtsumme", `nGLD = 1` „Beeinflusst
        durchschnittlichen Netto-EK".
        """
        sql = text("SELECT kZusatzkosten, cName, nGLD, nPreis "
                   "FROM dbo.tEingangsrechnungZusatzkosten ORDER BY cName")
        if conn is not None:
            rows = conn.execute(sql).fetchall()
        else:
            with self._engine.connect() as c:
                rows = c.execute(sql).fetchall()
        return [{"kZusatzkosten": int(r[0]), "cName": r[1] or "",
                 "nGLD": int(r[2] or 0), "nPreis": int(r[3] or 0)} for r in rows]

    @staticmethod
    def _match_kostenart(katalog: list[dict], name: str) -> Optional[dict]:
        """Kostenart über den Namen finden – exakt, sonst normalisiert."""
        if not name:
            return None
        def norm(s):
            return "".join(ch for ch in (s or "").lower() if ch.isalnum())
        gesucht = norm(name)
        for k in katalog:
            if (k["cName"] or "").strip().lower() == name.strip().lower():
                return k
        treffer = [k for k in katalog if norm(k["cName"]) == gesucht]
        return treffer[0] if len(treffer) == 1 else None

    @staticmethod
    def _verteile(betrag: float, positionen: list[dict]) -> dict[int, float]:
        """Einen Zusatzkostenbetrag mengenproportional auf die Positionen verteilen.

        So macht es JTL (am Golden Master nachgemessen): Grundlage sind **nur die
        Artikelzeilen** (`nPosTyp = 1`) und deren Menge. Nicht-Artikelzeilen (Skonto,
        `nPosTyp = 2`) bekommen zwar eine Zeile, aber den Wert 0.

        Der Rundungsrest landet auf der letzten Artikelzeile, damit die Summe der
        Einzelbeträge **exakt** dem Dokumentbetrag entspricht – daran hängen
        Rechnungswert und offener Posten (JTL summiert die Einzelwerte, den
        Dokumentbetrag speichert es nirgends).
        """
        artikel = [i for i, p in enumerate(positionen) if p.get("nPosTyp") == 1]
        anteile = {i: 0.0 for i in range(len(positionen))}
        gesamt_menge = sum(float(positionen[i]["fMenge"]) for i in artikel)
        if not artikel or gesamt_menge == 0:
            return anteile
        rest = round(betrag, 4)
        for i in artikel[:-1]:
            teil = round(betrag * float(positionen[i]["fMenge"]) / gesamt_menge, 4)
            anteile[i] = teil
            rest = round(rest - teil, 4)
        anteile[artikel[-1]] = rest
        return anteile

    def _plane_zusatzkosten(self, conn, plan: ERWritePlan, arten_override: dict) -> None:
        """Aus den Zusatzkosten der Rechnung die DB-Zeilen planen.

        Mehrere Rechnungszeilen können auf dieselbe Kostenart fallen (zweimal
        Fracht). Der Primärschlüssel von tEingangsrechnungPosZusatzkosten ist
        (kZusatzkosten, kEingangsrechnungPos) – pro Position also **eine** Zeile je
        Kostenart. Deshalb wird vor dem Verteilen je Kostenart summiert, sonst
        liefe der zweite INSERT in einen Schlüsselkonflikt.
        """
        if not plan.zusatzkosten:
            return
        katalog = self.kostenarten(conn)
        plan.kostenarten = katalog
        if not katalog:
            plan.errors.append(
                "Diese Wawi hat keine Zusatzkostenarten angelegt (Einkauf → "
                "Eingangsrechnungen → Zusatzkosten definieren). Ohne Kostenart "
                "können Fracht/Zuschläge nicht gebucht werden.")
            return

        # Kostenart je Rechnungszeile bestimmen: Zuordnung des Anwenders geht vor.
        gruppen: dict[int, float] = {}
        for idx, z in enumerate(plan.zusatzkosten):
            manuell = arten_override.get(idx, arten_override.get(str(idx)))
            art = next((k for k in katalog if k["kZusatzkosten"] == int(manuell)), None) \
                if manuell else self._match_kostenart(katalog, z.get("cName", ""))
            z["kZusatzkosten"] = art["kZusatzkosten"] if art else None
            z["kostenart"] = art["cName"] if art else None
            z["kostenart_quelle"] = ("manuell zugeordnet" if manuell
                                     else ("über Namen erkannt" if art else None))
            if art is None:
                z["status"] = "unmapped"
                plan.errors.append(
                    f"Zusatzkosten „{z.get('cName') or '(ohne Name)'}“ "
                    f"({float(z['betrag']):.2f}) lassen sich keiner Kostenart dieser "
                    f"Wawi zuordnen – bitte zuordnen. Vorhanden: "
                    + ", ".join(k["cName"] for k in katalog))
                continue
            if not art["nPreis"]:
                plan.warnings.append(
                    f"Kostenart „{art['cName']}“ ist in JTL auf „Beeinflusst "
                    f"Gesamtsumme: Nein“ gestellt – der Betrag zählt dort nicht in "
                    f"Rechnungswert und offenen Posten.")
            vorzeichen = 1.0 if z.get("ist_zuschlag", True) else -1.0
            gruppen[art["kZusatzkosten"]] = round(
                gruppen.get(art["kZusatzkosten"], 0.0) + vorzeichen * float(z["betrag"]), 4)

        # Verteilen und Zeilen bauen. JTL legt für JEDE Position eine Zeile an,
        # auch mit Wert 0 (am Golden Master gesehen) – das machen wir nach.
        for kZusatz, betrag in sorted(gruppen.items()):
            anteile = self._verteile(betrag, plan.positionen)
            mwst = next((float(z.get("fMwSt") or 0) for z in plan.zusatzkosten
                         if z.get("kZusatzkosten") == kZusatz), 0.0)
            for i, pos in enumerate(plan.positionen):
                plan.zusatzkosten_zeilen.append({
                    "kZusatzkosten": kZusatz,
                    "_zeile": i,                      # Index der Position im Plan
                    "dWert": round(anteile[i], 4),
                    "fFremdFaktor": 1.0,
                    "cWaehrungISO": "EUR",
                    "fMwst": mwst,
                })

    def _reconcile(self, kopf: ERKopfInput, plan: ERWritePlan) -> None:
        """Summen-Abgleich: berechnete Summe (Pos + Zusatzkosten) vs. Rechnungssumme.

        Gerechnet wird IMMER, verglichen nur, wenn die Rechnung eine eigene Summe
        nennt. Früher stieg die Methode ohne Rechnungssumme sofort aus und ließ
        `plan.summen` leer – dann hatte das Formular nichts anzuzeigen, obwohl die
        Zahlen längst feststanden. Das Gate hängt weiterhin allein am Vergleich.
        """
        netto_pos = sum(float(p["fMenge"]) * float(p["fEKNetto"]) for p in plan.positionen)
        steuer = sum(float(p["fMenge"]) * float(p["fEKNetto"]) * float(p["fMwSt"]) / 100.0
                     for p in plan.positionen)
        # Zusatzkosten zählen genau so mit, wie JTL selbst rechnet: nur Kostenarten
        # mit nPreis = 1 („Beeinflusst Gesamtsumme"). Nachzulesen in JTLs eigener
        # Sicht Zahlungsabgleich.vOffenerPostenEingangsrechnung und in
        # dbo.spEingangsrechnungStatusSetzen – dieselbe Summe treibt dort den
        # offenen Posten. Solange eine Kostenart noch nicht zugeordnet ist, zählt
        # sie hier mit (sonst schlüge der Abgleich mit einer irreführenden
        # Differenz fehl statt mit der eigentlichen Ursache: der fehlenden
        # Zuordnung, die den Write ohnehin blockiert).
        zaehlt = {k["kZusatzkosten"] for k in plan.kostenarten if k["nPreis"]}
        netto_zk = 0.0
        for z in plan.zusatzkosten:
            art = z.get("kZusatzkosten")
            if art is not None and art not in zaehlt:
                continue
            betrag = z["betrag"] if z.get("ist_zuschlag", True) else -z["betrag"]
            netto_zk += betrag
            steuer += betrag * float(z.get("fMwSt", 0)) / 100.0
        netto_ber = round(netto_pos + netto_zk, 2)
        steuer_ber = round(steuer, 2)
        brutto_ber = round(netto_ber + steuer_ber, 2)
        plan.summen = {
            "rechnung_netto": kopf.nettoSumme, "rechnung_steuer": kopf.steuerSumme,
            "rechnung_brutto": kopf.bruttoSumme, "berechnet_netto": netto_ber,
            "berechnet_steuer": steuer_ber, "berechnet_brutto": brutto_ber,
            # Aufgeschlüsselt, damit das Formular die Rechnung zeigen kann, statt
            # nur ihr Ergebnis: Warenwert + Zusatzkosten = Netto, + MwSt = Brutto.
            "berechnet_waren_netto": round(netto_pos, 2),
            "berechnet_zusatzkosten_netto": round(netto_zk, 2),
        }
        if kopf.bruttoSumme is None and kopf.nettoSumme is None:
            return          # nichts zu vergleichen – die Zahlen stehen trotzdem
        if kopf.bruttoSumme is not None:
            ref, cmp, label = kopf.bruttoSumme, brutto_ber, "brutto"
        else:
            ref, cmp, label = kopf.nettoSumme, netto_ber, "netto"
        diff = round(ref - cmp, 2)
        plan.summen["differenz"] = diff
        plan.reconciliation_ok = abs(diff) < 0.02
        if not plan.reconciliation_ok:
            plan.errors.append(
                f"Summen-Abgleich ({label}) fehlgeschlagen: Rechnung {ref:.2f} ≠ "
                f"berechnet {cmp:.2f} (Δ {diff:+.2f}) – Freigabe blockiert")

    def search_artikel(self, q: str, limit: int = 20) -> list[dict]:
        """Artikelsuche fürs manuelle Zuordnen: über eigene ArtNr, Lieferanten-ArtNr, Name."""
        like = f"%{q}%"
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT TOP (:lim) a.kArtikel, a.cArtNr, MAX(la.cName) AS cName
                FROM dbo.tArtikel a
                LEFT JOIN dbo.tliefartikel la ON la.tArtikel_kArtikel = a.kArtikel
                WHERE a.cArtNr LIKE :q OR la.cLiefArtNr LIKE :q OR la.cName LIKE :q
                GROUP BY a.kArtikel, a.cArtNr
                ORDER BY a.cArtNr
            """), {"lim": limit, "q": like}).mappings().all()
        return [{"kArtikel": int(r["kArtikel"]), "cArtNr": r["cArtNr"], "cName": r["cName"]}
                for r in rows]

    def learn_liefartikel(self, kLieferant: int, cLiefArtNr: str, kArtikel: int) -> dict:
        """
        Schreibt eine Lieferanten-Artikel-Zuordnung nach tliefartikel zurück, damit
        sie künftig automatisch greift. Wird vom Freigabe-Formular explizit ausgelöst,
        wenn ein Nutzer eine bisher unbekannte Liefer-ArtNr manuell zugeordnet hat.
        Idempotent: legt nur an, wenn die Kombination noch nicht existiert.
        """
        with self._engine.begin() as conn:
            exists = conn.execute(text(
                "SELECT 1 FROM dbo.tliefartikel WHERE tLieferant_kLieferant=:kl "
                "AND tArtikel_kArtikel=:ka AND cLiefArtNr=:nr"),
                {"kl": kLieferant, "ka": kArtikel, "nr": cLiefArtNr}).first()
            if exists:
                return {"created": False, "reason": "Zuordnung existiert bereits"}
            conn.execute(text(
                "INSERT INTO dbo.tliefartikel "
                "(tArtikel_kArtikel, tLieferant_kLieferant, cLiefArtNr, nStandard, nLieferbar) "
                "VALUES (:ka, :kl, :nr, 0, 1)"),
                {"ka": kArtikel, "kl": kLieferant, "nr": cLiefArtNr})
        return {"created": True}

    # ── Plan bauen ───────────────────────────────────────────────────────────────
    def build_plan(self, kopf: ERKopfInput, dry_run: bool = True,
                   overrides: Optional[dict] = None) -> ERWritePlan:
        """
        overrides: {positions_index: {...}} für manuelle Zuordnung im Freigabe-Formular:
          kArtikel, kLieferantenbestellung, kLieferantenBestellungPos (erzwingen),
          als_zusatzkosten (bool → Zeile als Zusatzkosten statt Artikelposition),
          platzhalter (bool → auf Sammelartikel, bewusst ohne 1:1-Zuordnung).
        """
        plan = ERWritePlan(ok=False, dry_run=dry_run)
        overrides = overrides or {}

        # Grund-Validierung
        if not kopf.cFremdbelegnummer:
            plan.errors.append("cFremdbelegnummer (Lieferanten-Rechnungsnr.) fehlt")
        if not kopf.positionen:
            plan.errors.append("Keine Positionen")

        with self._engine.connect() as conn:
            lief = self._resolve_lieferant(conn, kopf, plan) if not plan.errors else None
            if lief:
                plan.lieferant = {k: v for k, v in lief.items() if not k.startswith("b")}
                kLieferant = int(lief["kLieferant"])

                dub = self._find_dublette(conn, kLieferant, kopf.cFremdbelegnummer)
                if dub:
                    plan.errors.append(
                        f"Dublette: ER mit cFremdbelegnummer={kopf.cFremdbelegnummer!r} "
                        f"für diesen Lieferant existiert bereits (kEingangsrechnung={dub})")

                plan.naechste_nummer = self._peek_nummer(conn)

                # Kopf-Werte (Reihenfolge/Defaults aus Golden-Master belegt)
                plan.kopf_werte = {
                    "kBenutzer": kopf.kBenutzer,
                    "kLieferant": kLieferant,
                    "kAnsprechpartner": 0,
                    "cFremdbelegnummer": kopf.cFremdbelegnummer,
                    "cEigeneRechnungsnummer": "«spGetNextNummer»",
                    "cHinweise": kopf.cHinweise or "",
                    "cLieferant": kopf.cLieferant or lief.get("cFirma") or "",
                    "cAdresszusatz": "",
                    "cStrasse": kopf.cStrasse or lief.get("cStrasse") or "",
                    "cPLZ": kopf.cPLZ or lief.get("cPLZ") or "",
                    "cOrt": kopf.cOrt or lief.get("cOrt") or "",
                    # Land und Mail stehen im Lieferantenstamm unter cISO bzw.
                    # cEMail. Eine frühere Notiz behauptete, sie kämen dort nicht
                    # vor – das lag an den Spaltennamen. cISO ist bei allen 257
                    # Lieferanten gefüllt, cEMail bei 169. Die Rechnung hat
                    # weiterhin Vorrang, sie ist die Quelle der Wahrheit.
                    "cLandISO": kopf.cLandISO or lief.get("cISO") or "",
                    "cBundesland": "",
                    "cTel": kopf.cTel or lief.get("cTelZentralle") or lief.get("cTelDurchwahl") or "",
                    "cFax": kopf.cFax or lief.get("cFax") or "",
                    "cMobil": "",
                    "cMail": kopf.cMail or lief.get("cEMail") or "",
                    "nStatus": 0,               # 0 = offen/unbezahlt (Golden-Master)
                    "nDeleted": 0,
                    "nZahlungFreigegeben": 0,
                    "dErstellt": datetime.datetime.now(),
                    "nKumuliert": 0,
                    "dBezahlt": None,
                    "dZahlungsziel": kopf.dZahlungsziel,
                    "fFremdFaktor": Decimal("1"),   # EUR
                    "nVerteilungsArt": 0,
                    "dBelegdatum": kopf.dBelegdatum,
                }
                if not (plan.kopf_werte.get("cLandISO") or "").strip():
                    plan.warnings.append(
                        "cLandISO leer – weder die Rechnung noch der Lieferantenstamm "
                        "führen ein Land (relevant für DATEV/Steuer)")
                if not (plan.kopf_werte.get("cMail") or "").strip():
                    plan.warnings.append(
                        "cMail leer – weder die Rechnung noch der Lieferantenstamm "
                        "führen eine Mailadresse")

                # Zusatzkosten aus der Rechnung (Dokumentebene: Fracht/Zuschläge)
                for z in kopf.zusatzkosten:
                    plan.zusatzkosten.append({
                        "cName": z.cName, "betrag": round(z.betrag, 2), "fMwSt": z.fMwSt,
                        "ist_zuschlag": z.ist_zuschlag, "quelle": "E-Rechnung (Dokumentebene)",
                        "status": "non_article"})

                # Positionen auflösen (inkl. manueller Overrides + Status)
                used_pos_ids: set = set()
                for idx, pos in enumerate(kopf.positionen):
                    ov = overrides.get(idx) or overrides.get(str(idx)) or {}

                    # a) Zeile bewusst als Zusatzkosten umklassifiziert
                    if ov.get("als_zusatzkosten"):
                        plan.zusatzkosten.append({
                            "cName": pos.cName, "betrag": round(pos.fMenge * pos.fEKNetto, 2),
                            "fMwSt": pos.fMwSt, "ist_zuschlag": True,
                            "quelle": "Position → Zusatzkosten (manuell)", "status": "non_article"})
                        continue

                    ares = self._resolve_artikel(conn, pos, kLieferant)
                    kArtikel = ov.get("kArtikel") or ares["kArtikel"]
                    artikel_quelle = "override (manuell)" if ov.get("kArtikel") else ares["quelle"]

                    if ov.get("kLieferantenBestellungPos"):
                        m = {"kLieferantenbestellung": ov.get("kLieferantenbestellung"),
                             "kLieferantenBestellungPos": ov.get("kLieferantenBestellungPos"),
                             "_match": "override (manuell)", "kandidaten": [], "warnung": None}
                    else:
                        m = self._match_bestellung(conn, kLieferant, kArtikel, pos, kopf, used_pos_ids)
                    if m["kLieferantenBestellungPos"]:
                        used_pos_ids.add(m["kLieferantenBestellungPos"])

                    # Eigene Artikelnummer immer aus dem Artikelstamm holen, sobald
                    # kArtikel feststeht. Lieferanten drucken ihre eigene Nummer
                    # ("SI-ART.9000472"), unsere heißt "9000472" – und wer den
                    # Artikel im Formular von Hand zuordnet, korrigiert die Nummer
                    # dabei nicht mit. Ohne diesen Schritt stand in der Wawi eine
                    # eigene Artikelnummer, die es gar nicht gibt. Die gelesene
                    # Nummer bleibt in cLieferantenArtNr, wo sie hingehört.
                    kanonisch = None
                    if kArtikel:
                        r = conn.execute(text(
                            "SELECT cArtNr FROM dbo.tArtikel WHERE kArtikel = :k"),
                            {"k": kArtikel}).first()
                        kanonisch = r[0] if r else None

                    # Status bestimmen
                    if ov.get("platzhalter"):
                        status = "platzhalter"
                    elif kArtikel is None and (pos.cArtNr or pos.cLieferantenArtNr):
                        status = "unknown_article"
                    elif ares["warnung"] or (m.get("warnung") and "mehrdeutig" in (m.get("warnung") or "")):
                        status = "ambiguous"
                    elif kArtikel is not None and not m["kLieferantenBestellungPos"]:
                        status = "no_order"
                    elif kArtikel is not None and m["kLieferantenBestellungPos"]:
                        status = "matched"
                    else:
                        status = "unklar"

                    # Warnungen (nur wenn nicht per Override bereits gelöst).
                    #
                    # Sie hängen an der Position, nicht in der Sammelliste am Fuß
                    # des Formulars: bei einer Rechnung mit einem Dutzend Zeilen
                    # musste der Anwender sonst raten, welche Meldung zu welcher
                    # Zeile gehört, und die Zeile darüber im Kopf wiederfinden.
                    # Was den ganzen Beleg betrifft (Lieferant, Summen, Hinweise
                    # der Auslesung), steht weiterhin in plan.warnings.
                    #
                    # Zuerst, was der Ausleser zu genau dieser Zeile angemerkt hat –
                    # das steht schon fest, bevor hier ein Artikel gesucht wird.
                    meldungen: list[str] = list(pos.leser_hinweise or [])
                    if not ov.get("kArtikel") and ares["warnung"]:
                        meldungen.append(ares["warnung"])
                    elif status == "unknown_article":
                        meldungen.append(
                            f"Artikel nicht auflösbar (cArtNr={pos.cArtNr}, "
                            f"Liefer-ArtNr={pos.cLieferantenArtNr})")
                    if not ov.get("kLieferantenBestellungPos") and m.get("warnung"):
                        meldungen.append(m["warnung"])

                    plan.positionen.append({
                        "kEingangsrechnung": "«SCOPE_IDENTITY()»",
                        "kLieferantenbestellung": m["kLieferantenbestellung"],
                        "kArtikel": kArtikel,
                        "cArtNr": kanonisch or ares["cArtNr"] or pos.cArtNr or "",
                        "cLieferantenArtNr": pos.cLieferantenArtNr or "",
                        "cName": pos.cName,
                        "cLieferantenBezeichnung": pos.cLieferantenBezeichnung or pos.cName,
                        "cEinheit": pos.cEinheit or "",
                        "cHinweis": "",
                        "fMenge": Decimal(str(pos.fMenge)),
                        "fEKNetto": Decimal(str(pos.fEKNetto)),
                        "fMwSt": Decimal(str(pos.fMwSt)),
                        "nPosTyp": pos.nPosTyp,
                        "kLieferantenBestellungPos": m["kLieferantenBestellungPos"],
                        "status": status,
                        "_zeile": idx,
                        "_match": m["_match"],
                        "_artikel_quelle": artikel_quelle,
                        "_kandidaten": m.get("kandidaten", []),
                        "_meldungen": meldungen,
                    })

                for h in (kopf.leser_hinweise or []):
                    plan.warnings.append(h)
                if kopf.quelle == "pdf_ki":
                    plan.warnings.append(
                        "Diese Rechnung wurde aus einem PDF ausgelesen, nicht aus "
                        "strukturierten E-Rechnungsdaten. Beträge und Mengen bitte "
                        "gegen das PDF prüfen – die Summenkontrolle findet Fehler "
                        "nur, wenn sie sich in der Summe auswirken.")

                # Zusatzkosten auf die Positionen verteilen (braucht die fertigen
                # Positionen, muss also nach der Positionsschleife laufen)
                self._plane_zusatzkosten(
                    conn, plan, overrides.get("zusatzkosten_arten") or {})

                # Summen-Abgleich (Gate) – Position + Zusatzkosten gegen Rechnungssumme
                self._reconcile(kopf, plan)

                # Freigabe-Policy „manuell zuordnen": unaufgelöste Zeilen blockieren Write
                offen = [p["cName"] for p in plan.positionen
                         if p["status"] in ("unknown_article", "ambiguous", "unklar")]
                if offen:
                    plan.errors.append(
                        "Nicht zugeordnete Positionen (manuelle Zuordnung nötig): "
                        + ", ".join(offen))

            plan.statements = self._render_statements(plan)
            plan.ok = not plan.errors

        # Echter Write nur wenn ausdrücklich gewünscht und fehlerfrei – auf einer
        # eigenen transaktionalen Connection (getrennt von den Read-Auflösungen oben).
        if not dry_run and plan.ok:
            self._execute(plan)

        return plan

    def _render_statements(self, plan: ERWritePlan) -> list[str]:
        """Parametrisiertes SQL für die Anzeige (keine Werte inline – nur zur Ansicht)."""
        s = []
        s.append("BEGIN TRAN;")
        s.append("DECLARE @nr NVARCHAR(50);")
        s.append("EXEC dbo.spGetNextNummer @cName=N'Eingangsrechnung', @kFirma=0, "
                 "@nNoUpdate=0, @cNeueNummer=@nr OUTPUT, @nNoSelect=1;")
        if plan.kopf_werte:
            cols = [c for c in plan.kopf_werte if c not in ("cEigeneRechnungsnummer",)]
            collist = ", ".join(["cEigeneRechnungsnummer"] + cols)
            vallist = ", ".join(["@nr"] + [f":{c}" for c in cols])
            s.append(f"INSERT INTO dbo.tEingangsrechnung ({collist})\n  VALUES ({vallist});")
            s.append("DECLARE @kER INT = SCOPE_IDENTITY();")
        for i, p in enumerate(plan.positionen, 1):
            cols = [c for c in POS_DB_COLS if c != "kEingangsrechnung"]
            collist = ", ".join(["kEingangsrechnung"] + cols)
            vallist = ", ".join(["@kER"] + [f":p{i}_{c}" for c in cols])
            s.append(f"INSERT INTO dbo.tEingangsrechnungPos ({collist})\n  VALUES ({vallist});")
            s.append(f"DECLARE @kPos{i} INT = SCOPE_IDENTITY();")
        for zk in plan.zusatzkosten_zeilen:
            s.append("INSERT INTO dbo.tEingangsrechnungPosZusatzkosten "
                     "(kZusatzkosten, kEingangsrechnungPos, dWert, fFremdFaktor, "
                     "cWaehrungISO, fMwst)\n"
                     f"  VALUES ({zk['kZusatzkosten']}, @kPos{zk['_zeile'] + 1}, "
                     f"{zk['dWert']}, 1, N'{zk['cWaehrungISO']}', {zk['fMwst']});")
        s.append("COMMIT TRAN;")
        return s

    def _execute(self, plan: ERWritePlan) -> None:
        """Echter Write in EINER Transaktion. Wird nur mit dry_run=False erreicht."""
        with self._engine.begin() as conn:
            nr = conn.execute(text(
                "EXEC dbo.spGetNextNummer @cName=:n, @kFirma=0, @nNoUpdate=0, @nNoSelect=0"),
                {"n": NUMMERNKREIS_NAME}).first()
            cEigene = str(nr[0]) if nr else None

            kopf_vals = dict(plan.kopf_werte)
            kopf_vals["cEigeneRechnungsnummer"] = cEigene
            cols = list(kopf_vals.keys())
            collist = ", ".join(cols)
            vallist = ", ".join(f":{c}" for c in cols)
            # SCOPE_IDENTITY() statt OUTPUT INSERTED → trigger-sicher (falls JTL einen
            # INSERT-Trigger auf tEingangsrechnung hat, würde OUTPUT sonst Fehler 334 werfen).
            # SCOPE_IDENTITY() muss im SELBEN Batch wie das INSERT stehen, sonst ist der
            # Scope leer (NULL). SET NOCOUNT ON, damit das SELECT das einzige Resultset ist.
            new_id = conn.execute(
                text(f"SET NOCOUNT ON; "
                     f"INSERT INTO dbo.tEingangsrechnung ({collist}) VALUES ({vallist}); "
                     f"SELECT CAST(SCOPE_IDENTITY() AS INT);"),
                kopf_vals).scalar()

            # Positions-IDs mitnehmen: die Zusatzkosten hängen an
            # kEingangsrechnungPos, nicht an der Rechnung. Gleiche Technik wie oben –
            # SCOPE_IDENTITY() im selben Batch wie das INSERT.
            pos_ids: list[int] = []
            for p in plan.positionen:
                pv = {k: p.get(k) for k in POS_DB_COLS}
                pv["kEingangsrechnung"] = new_id
                cols = list(pv.keys())
                collist = ", ".join(cols)
                vallist = ", ".join(f":{c}" for c in cols)
                kpos = conn.execute(text(
                    f"SET NOCOUNT ON; "
                    f"INSERT INTO dbo.tEingangsrechnungPos ({collist}) VALUES ({vallist}); "
                    f"SELECT CAST(SCOPE_IDENTITY() AS INT);"), pv).scalar()
                pos_ids.append(int(kpos))

            for zk in plan.zusatzkosten_zeilen:
                conn.execute(text(
                    "INSERT INTO dbo.tEingangsrechnungPosZusatzkosten "
                    "(kZusatzkosten, kEingangsrechnungPos, dWert, fFremdFaktor, "
                    " cWaehrungISO, fMwst) "
                    "VALUES (:kZusatzkosten, :kEingangsrechnungPos, :dWert, "
                    "        :fFremdFaktor, :cWaehrungISO, :fMwst)"),
                    {"kZusatzkosten": zk["kZusatzkosten"],
                     "kEingangsrechnungPos": pos_ids[zk["_zeile"]],
                     "dWert": Decimal(str(zk["dWert"])),
                     "fFremdFaktor": Decimal(str(zk["fFremdFaktor"])),
                     "cWaehrungISO": zk["cWaehrungISO"],
                     "fMwst": Decimal(str(zk["fMwst"]))})

            plan.kEingangsrechnung = int(new_id)
            plan.kopf_werte["cEigeneRechnungsnummer"] = cEigene


def build_dry_run(connection_id: int, kopf: ERKopfInput) -> ERWritePlan:
    """Bequemer Einstieg: Plan im Dry-Run bauen, nichts schreiben."""
    return EingangsrechnungWriter(connection_id).build_plan(kopf, dry_run=True)


# ── (De)Serialisierung des geparsten Kopfs für die zustandslose API ──────────────
def serialize_kopf(kopf: ERKopfInput) -> dict:
    """ERKopfInput → JSON-fähiges dict (datetime als ISO)."""
    def _d(dt):
        return dt.isoformat() if dt else None
    d = dataclasses.asdict(kopf)
    d["dBelegdatum"] = _d(kopf.dBelegdatum)
    d["dZahlungsziel"] = _d(kopf.dZahlungsziel)
    return d


def deserialize_kopf(d: dict) -> ERKopfInput:
    """dict (aus der API) → ERKopfInput, für den Write nach der Freigabe."""
    def _dt(s):
        return datetime.datetime.fromisoformat(s) if s else None
    pos = [ERPositionInput(**p) for p in (d.get("positionen") or [])]
    zk = [ERZusatzkostenInput(**z) for z in (d.get("zusatzkosten") or [])]
    fields = {f.name for f in dataclasses.fields(ERKopfInput)}
    rest = {k: v for k, v in d.items()
            if k in fields and k not in ("positionen", "zusatzkosten", "dBelegdatum", "dZahlungsziel")}
    return ERKopfInput(
        positionen=pos, zusatzkosten=zk,
        dBelegdatum=_dt(d.get("dBelegdatum")) or datetime.datetime.now(),
        dZahlungsziel=_dt(d.get("dZahlungsziel")),
        **rest)

# -*- coding: utf-8 -*-
"""Die Debitorennummer eines Kunden in der JTL-Wawi setzen.

Bewusst ein einziges Feld: `dbo.tkunde.nDebitorennr`. Kein generischer Weg, der
beliebige Spalten schreiben könnte – der Anwender klickt hier einen Knopf, und
was dahinter passiert, soll man in einem Satz sagen können.

Anlass ist der DATEV-Export: ohne Debitorennummer hat eine Buchung kein Konto,
und DATEV weist den ganzen Stapel ab. Die Nummer nachzupflegen ist Fleißarbeit
in der Wawi, die niemand gern macht – deshalb dieser Weg.

An der Wawi geprüft (2026-09-04):
  - ⭐ **Ein direktes UPDATE auf `dbo.tkunde` ist unmöglich.** JTL blockt es per
    Trigger ab: „Die Tabelle dbo.tKunde kann nur über die SPs Kunde.spKundeInsert,
    Kunde.spKundeUpdate und Kunde.spKundeDelete geändert werden." (Anders als bei
    `tArtikel`, wo Direktschreiben geht — siehe jtl_artikel_writer.) Geschrieben
    wird deshalb über **`Kunde.spKundeUpdate`**.
  - Die Prozedur nimmt einen Tabellentyp `dbo.TYPE_spkundeUpdate`, in dem jede
    Spalte ein `xFlag_`-Gegenstück hat. Ihre Zuweisung lautet
    `CASE WHEN Daten.<spalte> IS NOT NULL OR Daten.xFlag_<spalte> = 1
          THEN Daten.<spalte> ELSE tkunde.<spalte> END`
    — wer nur `kKunde`, `nDebitorennr` und `xFlag_nDebitorennr` füllt, ändert
    garantiert nichts anderes. Das ist sicherer als jedes selbstgebaute UPDATE.
  - Die Tabelle hat `bRowversion`; weil die Prozedur sie nicht entgegennimmt,
    wird die Zeile stattdessen in derselben Transaktion mit UPDLOCK gelesen und
    nach dem Aufruf gegengeprüft.
  - ⚠️ Der Index `IX_tKunde_nDebitorenNummer` ist **nicht eindeutig**. Die
    Datenbank verhindert eine doppelte Debitorennummer also NICHT (im Bestand
    ist 11613 tatsächlich zweimal vergeben). Zwei Kunden auf einem Konto lassen
    ihre Umsätze beim Steuerberater zu einem Saldo verschmelzen – deshalb prüft
    dieser Code die Eindeutigkeit selbst, unmittelbar vor dem Schreiben.
  - JTL zieht die Nummer an bereits gebuchten Rechnungen NICHT nach. Das ist
    kein Problem: der Export fällt auf den Kundenstamm zurück, sobald der Beleg
    keine führt.

Ablauf wie bei den anderen Writern dieses Projekts: `build_plan()` löst read-only
auf und prüft; im Dry-Run wird nichts ausgeführt. Der echte Write nimmt denselben
Codepfad und läuft nur mit `dry_run=False` und fehlerfreiem Plan.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text

from app.core.database import SessionLocal
from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str

# Obergrenze je Lauf – begrenzt den Schaden eines Fehlgriffs.
MAX_AENDERUNGEN = 200

# nDebitorennr ist int; die Kundennummer ist Text und darf nicht jeden Wert tragen.
MAX_NUMMER = 2_147_483_647


@dataclass
class KundeWritePlan:
    dry_run: bool
    zeilen: list[dict] = field(default_factory=list)   # je Kunde: was passieren soll
    errors: list[str] = field(default_factory=list)
    geschrieben: int = 0

    @property
    def bereit(self) -> list[dict]:
        return [z for z in self.zeilen if z["status"] == "bereit"]

    def to_dict(self) -> dict:
        return {"dry_run": self.dry_run, "zeilen": self.zeilen,
                "errors": self.errors, "geschrieben": self.geschrieben,
                "anzahl_bereit": len(self.bereit)}


class KundeWriter:
    def __init__(self, connection_id: int, k_benutzer: int = 1):
        # kBenutzer ist ein Pflichtparameter der JTL-Prozedur (wer hat geändert).
        # 1 ist derselbe Notnagel wie im Eingangsrechnungs-Writer; eine Abbildung
        # Datenmonster-Benutzer → JTL-kBenutzer fehlt projektweit noch.
        self.k_benutzer = k_benutzer
        db = SessionLocal()
        try:
            conn_row = db.query(DbConnection).filter(
                DbConnection.id == connection_id).first()
            if not conn_row:
                raise ValueError(f"Verbindung {connection_id} gibt es nicht")
            self._engine = create_engine(get_engine_str(conn_row), pool_pre_ping=True)
            self.connection_id = connection_id
        finally:
            db.close()

    # ── Vorschlagsliste ────────────────────────────────────────────────────────
    def offene_faelle(self, jahr: int, monat: int) -> list[dict]:
        """Kunden, die im Zeitraum Umsatz hatten und keine Debitorennummer führen.

        Geliefert wird je Kunde EINE Zeile (nicht je Rechnung): gepflegt wird der
        Kunde, nicht der Beleg. Dazu der Vorschlag und ob er im Bestand frei ist.
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT  k.kKunde,
                        LTRIM(RTRIM(ISNULL(k.cKundenNr, '')))         AS kundennummer,
                        LTRIM(RTRIM(COALESCE(NULLIF(a.cFirma, ''),
                              LTRIM(RTRIM(ISNULL(a.cVorname,'') + ' ' + ISNULL(a.cName,''))),
                              '(ohne Namen)')))                       AS name,
                        COUNT(DISTINCT r.kRechnung)                   AS belege,
                        CAST(ROUND(SUM(ROUND(rp.fAnzahl * rp.fVkNetto
                             * (1 - ISNULL(rp.fRabatt,0)/100.0)
                             * (1 + rp.fMwSt/100.0), 2)), 2) AS DECIMAL(18,2)) AS brutto,
                        belegt.kKunde                                 AS kollision_kunde,
                        belegt.cFirma                                 AS kollision_name
                FROM Rechnung.tRechnung r
                JOIN Rechnung.tRechnungPosition rp ON rp.kRechnung = r.kRechnung
                LEFT JOIN dbo.tkunde k   ON k.kKunde = r.kKunde
                LEFT JOIN dbo.tAdresse a ON a.kKunde = r.kKunde
                                        AND a.nTyp = 1 AND a.nStandard = 1
                -- TOP 1: die Debitorennummer ist im Bestand nicht garantiert
                -- eindeutig, ein JOIN würde den Kunden sonst mehrfach liefern.
                OUTER APPLY (SELECT TOP 1 b.kKunde, b.cKundenNr AS cFirma
                             FROM dbo.tkunde b
                             WHERE CAST(b.nDebitorennr AS VARCHAR(20))
                                   = LTRIM(RTRIM(k.cKundenNr))
                               AND b.kKunde <> k.kKunde) belegt
                WHERE ISNULL(r.nIstProforma,0) = 0 AND ISNULL(r.nIstEntwurf,0) = 0
                  AND YEAR(r.dErstellt) = :jahr AND MONTH(r.dErstellt) = :monat
                  AND ISNULL(r.nDebitorennr, 0) = 0
                  AND ISNULL(k.nDebitorennr, 0) = 0
                GROUP BY k.kKunde, k.cKundenNr, a.cFirma, a.cVorname, a.cName,
                         belegt.kKunde, belegt.cFirma
                ORDER BY 5 DESC
            """), {"jahr": jahr, "monat": monat}).mappings().all()

        faelle = []
        for r in rows:
            vorschlag, hinweis, uebernehmbar = self._vorschlag(
                r["kundennummer"], r["kollision_kunde"])
            faelle.append({
                "kKunde": r["kKunde"], "kundennummer": r["kundennummer"],
                "name": r["name"], "belege": r["belege"],
                "brutto": float(r["brutto"] or 0),
                "vorschlag": vorschlag, "hinweis": hinweis,
                "uebernehmbar": uebernehmbar,
            })
        return faelle

    @staticmethod
    def _vorschlag(kundennummer: str, kollision_kunde) -> tuple:
        """Taugt die Kundennummer als Debitorennummer – und ist sie noch frei?

        Im Bestand dieses Kunden stimmen 90 % der gepflegten Debitorennummern mit
        der Kundennummer überein. Das ist ein guter Vorschlag, aber keine Regel:
        die übrigen 10 % tragen Nummern aus einem anderen Kreis. Deshalb wird
        vorgeschlagen und geprüft, nie automatisch übernommen.
        """
        nr = (kundennummer or "").strip()
        if not nr or not nr.isdigit():
            return None, "Kundennummer taugt nicht als Nummer – von Hand vergeben", False
        if int(nr) <= 0 or int(nr) > MAX_NUMMER:
            return None, "Kundennummer liegt außerhalb des gültigen Bereichs", False
        if kollision_kunde:
            return int(nr), (f"{nr} ist bereits Debitor von Kunde {kollision_kunde} – "
                             f"NICHT übernehmen, sonst laufen zwei Kunden auf ein Konto"), False
        return int(nr), f"{nr} ist im Bestand noch frei", True

    # ── Plan + Write ───────────────────────────────────────────────────────────
    def build_plan(self, kunden: list[dict], dry_run: bool = True) -> KundeWritePlan:
        """kunden: [{kKunde, nummer}] – die Auswahl des Anwenders.

        Jede Zeile wird noch einmal frisch gegen die Wawi geprüft, egal was das
        Formular mitschickt: der Kunde darf keine Nummer haben, die Nummer muss
        frei sein. Zwischen Anzeigen und Klicken kann jemand anderes gearbeitet haben.
        """
        plan = KundeWritePlan(dry_run=dry_run)
        if not kunden:
            plan.errors.append("Keine Kunden ausgewählt")
            return plan
        if len(kunden) > MAX_AENDERUNGEN:
            plan.errors.append(
                f"{len(kunden)} Kunden auf einmal – erlaubt sind {MAX_AENDERUNGEN}")
            return plan

        gewuenscht: dict[int, int] = {}
        for k in kunden:
            try:
                kk, nr = int(k["kKunde"]), int(k["nummer"])
            except (KeyError, TypeError, ValueError):
                plan.errors.append(f"Unbrauchbarer Eintrag: {k!r}")
                return plan
            if nr <= 0 or nr > MAX_NUMMER:
                plan.errors.append(f"Nummer {nr} liegt außerhalb des gültigen Bereichs")
                return plan
            if kk in gewuenscht:
                plan.errors.append(f"Kunde {kk} steht mehrfach in der Auswahl")
                return plan
            gewuenscht[kk] = nr

        # Zwei Kunden derselben Auswahl dürfen nicht dieselbe Nummer bekommen.
        doppelt = {n for n in gewuenscht.values()
                   if list(gewuenscht.values()).count(n) > 1}
        if doppelt:
            plan.errors.append(
                f"Dieselbe Nummer für mehrere Kunden vorgesehen: {sorted(doppelt)}")
            return plan

        with self._engine.connect() as conn:
            platz = ", ".join(f":k{i}" for i in range(len(gewuenscht)))
            ist = {r["kKunde"]: r for r in conn.execute(text(f"""
                SELECT kKunde, cKundenNr, ISNULL(nDebitorennr,0) AS nDebitorennr,
                       bRowversion
                FROM dbo.tkunde WHERE kKunde IN ({platz})
            """), {f"k{i}": k for i, k in enumerate(gewuenscht)}).mappings().all()}

            # Ist eine der Nummern inzwischen vergeben?
            platz2 = ", ".join(f":n{i}" for i in range(len(gewuenscht)))
            vergeben: dict[int, int] = {}
            for r in conn.execute(text(f"""
                SELECT kKunde, nDebitorennr FROM dbo.tkunde
                WHERE nDebitorennr IN ({platz2})
            """), {f"n{i}": n for i, n in enumerate(gewuenscht.values())}).mappings():
                vergeben.setdefault(int(r["nDebitorennr"]), int(r["kKunde"]))

        for kk, nr in gewuenscht.items():
            zeile = {"kKunde": kk, "nummer": nr,
                     "kundennummer": (ist.get(kk) or {}).get("cKundenNr"),
                     "status": "bereit", "grund": None}
            if kk not in ist:
                zeile.update(status="fehler", grund="Kunde nicht gefunden")
            elif int(ist[kk]["nDebitorennr"]) > 0:
                zeile.update(status="uebersprungen",
                             grund=f"hat inzwischen die Nummer {ist[kk]['nDebitorennr']}")
            elif nr in vergeben and vergeben[nr] != kk:
                zeile.update(status="fehler",
                             grund=f"Nummer {nr} gehört inzwischen Kunde {vergeben[nr]}")
            plan.zeilen.append(zeile)

        if any(z["status"] == "fehler" for z in plan.zeilen):
            plan.errors.append(
                "Mindestens eine Zeile ist nicht schreibbar – es wird nichts geschrieben")
        elif not plan.bereit:
            plan.errors.append("Nichts zu schreiben")

        if not dry_run and not plan.errors:
            self._execute(plan)
        return plan

    def _execute(self, plan: KundeWritePlan) -> None:
        """Schreibt über JTLs eigene Prozedur, in EINER Transaktion.

        Ein direktes UPDATE lässt die Wawi nicht zu (siehe Modulkopf). Der
        Tabellentyp wird nur mit `kKunde`, `nDebitorennr` und dessen `xFlag`
        gefüllt — alle übrigen Kundenfelder bleiben damit nachweislich unberührt.

        Gegen Nebenläufigkeit hilft hier nicht die Rowversion (die Prozedur nimmt
        keine entgegen), sondern das Lesen mit UPDLOCK unmittelbar vor dem Aufruf
        und eine Gegenprobe danach. Stimmt etwas nicht, fliegt eine Ausnahme und
        die ganze Transaktion wird zurückgerollt.
        """
        with self._engine.begin() as conn:
            for zeile in plan.bereit:
                jetzt = conn.execute(text("""
                    SELECT ISNULL(nDebitorennr, 0) FROM dbo.tkunde WITH (UPDLOCK)
                    WHERE kKunde = :kk
                """), {"kk": zeile["kKunde"]}).scalar()
                if jetzt is None:
                    raise RuntimeError(f"Kunde {zeile['kKunde']} nicht gefunden – "
                                       f"nichts geschrieben")
                if int(jetzt) != 0:
                    raise RuntimeError(
                        f"Kunde {zeile['kKunde']} hat inzwischen die Nummer {jetzt} – "
                        f"nichts geschrieben (alle Änderungen zurückgerollt)")

                conn.execute(text("""
                    DECLARE @daten dbo.TYPE_spkundeUpdate;
                    INSERT INTO @daten (kKunde, nDebitorennr, xFlag_nDebitorennr)
                    VALUES (:kk, :nr, 1);
                    EXEC Kunde.spKundeUpdate @Daten = @daten, @kBenutzer = :ben;
                """), {"kk": zeile["kKunde"], "nr": zeile["nummer"],
                       "ben": self.k_benutzer})

                nachher = conn.execute(text(
                    "SELECT ISNULL(nDebitorennr,0) FROM dbo.tkunde WHERE kKunde = :kk"
                ), {"kk": zeile["kKunde"]}).scalar()
                if int(nachher or 0) != int(zeile["nummer"]):
                    raise RuntimeError(
                        f"Kunde {zeile['kKunde']}: erwartet {zeile['nummer']}, "
                        f"in der Wawi steht {nachher} – alles zurückgerollt")
                zeile["status"] = "geschrieben"
                plan.geschrieben += 1


def protokolliere(db, benutzer, connection_id: int, plan: KundeWritePlan) -> None:
    """Wer hat wann welche Nummer gesetzt – im normalen Systemprotokoll."""
    geschrieben = [z for z in plan.zeilen if z["status"] == "geschrieben"]
    try:
        from app.services.db_logger import log as _dblog
        _dblog(db, "success" if geschrieben else "warning", "jtl_kunde_writer",
               "debitorennummer_write",
               f"{len(geschrieben)} Debitorennummern in die Wawi geschrieben",
               entity_id=connection_id, rows_processed=len(geschrieben),
               details={
                   "benutzer": (getattr(benutzer, "username", None)
                                or getattr(benutzer, "email", None)),
                   "zeitpunkt": datetime.datetime.now().isoformat(timespec="seconds"),
                   "gesetzt": [{"kKunde": z["kKunde"], "nummer": z["nummer"]}
                               for z in geschrieben],
                   "uebersprungen": [{"kKunde": z["kKunde"], "grund": z["grund"]}
                                     for z in plan.zeilen
                                     if z["status"] == "uebersprungen"],
               })
    except Exception:            # Protokollieren darf den Vorgang nie kippen
        pass

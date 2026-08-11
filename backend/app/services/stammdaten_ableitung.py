"""
Warennummer und Ursprungsland aus den eigenen gepflegten Artikeln ableiten.

Die Herstellerseiten geben beides praktisch nie her (Deiss nur EANs, Denios nur
Maße und Gewicht). Die verlässlichste Quelle ist deshalb der eigene Stamm: wo
ein Artikel gepflegt ist, tragen seine Geschwister meist dieselbe Nummer.

Nachgewiesen an den echten Daten dieses Kunden (2.817 aktive Artikel):
  * 106 Artikel haben eine Warennummer, 77 ein Ursprungsland – wenig, aber genug
    als Ankerpunkt für ganze Warengruppen.
  * „Papierhandtücher": 8 von 8 gepflegten tragen 48182099 – starke Evidenz.
  * „Spender/Spendersysteme": 25 gepflegte, aber 6 verschiedene Codes – schwach.
  * Ursprungsland ist je Hersteller meist einheitlich (Dreumex 5/5 NL, paperdi
    9/9 IT), Wepa verteilt sich dagegen auf fünf Länder – darf also nicht
    einfach je Hersteller durchgereicht werden.

Daraus die Regel: **Sicherheit = Deckel(Stichprobe) × Anteil des führenden Werts.**
Ein einzelner Beleg deckelt hart bei 40, und 100 % gibt es hier grundsätzlich
nicht — die zolltarifliche Einreihung ist eine rechtliche Entscheidung, keine
Mehrheitsabstimmung. Der Nutzen liegt in der Vorauswahl, nicht in der Gewissheit.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import create_engine, text

from app.core.database import SessionLocal
from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str
from app.services.jtl_artikel_writer import pruefe_iso2, pruefe_taric
from app.services.stammdaten_research import stufe

logger = logging.getLogger(__name__)

FELDER = ("Warennummer", "Herkunftsland")
MAX_ARTIKEL = 500

# Deckel nach Größe der Stichprobe: ein Beleg ist ein Zufall, acht sind ein Muster.
def _deckel(n: int, basis: int) -> int:
    if n >= 8:
        return basis
    if n >= 4:
        return basis - 10
    if n >= 2:
        return basis - 20
    return 40


_WORT = re.compile(r"[a-zäöüß]{3,}")


def _tokens(name: str) -> set:
    """Wörter eines Artikelnamens ohne Maße und Füllwörter – für die Ähnlichkeit."""
    roh = set(_WORT.findall((name or "").lower()))
    return roh - {"und", "mit", "für", "der", "die", "das", "von", "pro", "stk",
                  "stück", "karton", "rolle", "rollen", "pack", "packung"}


def _aehnlichkeit(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _normiere(feld: str, roh):
    """Auf die Schreibweise bringen, in der gezählt wird ('Italien' und 'IT' sind
    derselbe Beleg). Gibt None zurück, wenn der gepflegte Wert selbst unbrauchbar ist."""
    if feld == "Herkunftsland":
        wert, fehler, _ = pruefe_iso2(roh)
        return None if fehler else wert
    wert, fehler, _ = pruefe_taric(roh)
    return None if fehler else wert


SPALTE = {"Warennummer": "cTaric", "Herkunftsland": "cHerkunftsland"}


class Ableitung:
    def __init__(self, connection_id: int):
        db = SessionLocal()
        try:
            conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
            if not conn:
                raise ValueError(f"DB-Verbindung #{connection_id} nicht gefunden")
            if conn.db_type != "mssql":
                raise ValueError("Ableitung nur für JTL/MSSQL")
            self._engine = create_engine(get_engine_str(conn),
                                         connect_args={"timeout": 30, "login_timeout": 10})
        finally:
            db.close()

    # ── Daten holen ─────────────────────────────────────────────────────────────
    _SPALTEN = """
        A.kArtikel, A.cArtNr, A.kWarengruppe, A.kHersteller,
        LTRIM(RTRIM(ISNULL(A.cTaric,''))) AS Warennummer,
        LTRIM(RTRIM(ISNULL(A.cHerkunftsland,''))) AS Herkunftsland,
        ISNULL(AB.cName, '') AS Artikel, ISNULL(W.cName,'') AS Warengruppe,
        ISNULL(H.cName,'') AS Hersteller
        FROM dbo.tArtikel A
        LEFT JOIN dbo.tArtikelBeschreibung AB ON AB.kArtikel = A.kArtikel
             AND AB.kSprache = 1 AND AB.kPlattform = 1 AND AB.kShop = 0
        LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe
        LEFT JOIN dbo.tHersteller  H ON H.kHersteller  = A.kHersteller
    """

    def _gepflegte(self, conn) -> list[dict]:
        """Alle Artikel, die mindestens eines der beiden Felder gepflegt haben.

        Das sind wenige hundert Zeilen – die Auswertung läuft danach im Speicher,
        weil sich die Begründung („8 von 8 …") so viel leichter belegen lässt.
        """
        rows = conn.execute(text(f"""
            SELECT {self._SPALTEN}
            WHERE A.cAktiv = 'Y' AND A.kVaterArtikel = 0
              AND (LTRIM(RTRIM(ISNULL(A.cTaric,''))) <> ''
                OR LTRIM(RTRIM(ISNULL(A.cHerkunftsland,''))) <> '')
        """)).mappings().all()
        return [dict(r) for r in rows]

    def _ziele(self, conn, k_artikel: list[int]) -> list[dict]:
        platzhalter = ", ".join(f":k{i}" for i in range(len(k_artikel)))
        params = {f"k{i}": k for i, k in enumerate(k_artikel)}
        rows = conn.execute(text(f"""
            SELECT {self._SPALTEN} WHERE A.kArtikel IN ({platzhalter})
        """), params).mappings().all()
        return [dict(r) for r in rows]

    # ── Auswertung ──────────────────────────────────────────────────────────────
    @staticmethod
    def _mehrheit(feld: str, menge: list[dict]) -> tuple | None:
        """Führender normierter Wert einer Belegmenge → (wert, treffer, gesamt, beispiel)."""
        zaehler: dict = {}
        beispiel: dict = {}
        for r in menge:
            wert = _normiere(feld, r.get(feld))
            if not wert:
                continue
            zaehler[wert] = zaehler.get(wert, 0) + 1
            beispiel.setdefault(wert, r.get("cArtNr"))
        if not zaehler:
            return None
        gesamt = sum(zaehler.values())
        wert, treffer = max(zaehler.items(), key=lambda kv: kv[1])
        return wert, treffer, gesamt, beispiel[wert]

    def _ebenen(self, feld: str, ziel: dict, gepflegte: list[dict]) -> list[tuple]:
        """Belegmengen von der aussagekräftigsten zur schwächsten.

        Für die Warennummer zählt die Warengruppe (gleiche Ware = gleiche
        Einreihung), für das Ursprungsland der Hersteller (er produziert an einem
        Ort). Die Warengruppe allein sagt über die Herkunft nichts.
        """
        wg, he = ziel.get("kWarengruppe"), ziel.get("kHersteller")
        eigene = ziel.get("kArtikel")
        andere = [g for g in gepflegte if g["kArtikel"] != eigene]

        ebenen = []
        if wg and he:
            ebenen.append((85, f"Warengruppe „{ziel.get('Warengruppe')}“ dieses Herstellers",
                           [g for g in andere if g["kWarengruppe"] == wg and g["kHersteller"] == he]))
        if feld == "Warennummer" and wg:
            ebenen.append((80, f"Warengruppe „{ziel.get('Warengruppe')}“",
                           [g for g in andere if g["kWarengruppe"] == wg]))
        if feld == "Herkunftsland" and he:
            ebenen.append((80, f"Hersteller „{ziel.get('Hersteller')}“",
                           [g for g in andere if g["kHersteller"] == he]))

        # Letzte Ebene nur für die Warennummer: gleichartige Ware wird gleich
        # eingereiht, egal wie sie einsortiert ist. Fürs Ursprungsland taugt das
        # nicht — an den echten Daten geprüft: ein Sofidel-Artikel bekam so die
        # Herkunft eines gleichnamigen Wepa-Artikels. Wo der Hersteller nichts
        # hergibt, gibt es lieber keinen Vorschlag als einen erfundenen.
        if feld == "Warennummer":
            ziel_worte = _tokens(ziel.get("Artikel"))
            aehnlich = [g for g in andere
                        if _aehnlichkeit(ziel_worte, _tokens(g["Artikel"])) >= 0.5]
            if aehnlich:
                ebenen.append((55, "ähnlich benannte Artikel", aehnlich))
        return ebenen

    def vorschlaege(self, k_artikel: list[int],
                    felder: tuple[str, ...] = FELDER,
                    nur_fehlende: bool = True) -> list[dict]:
        if not k_artikel:
            return []
        k_artikel = k_artikel[:MAX_ARTIKEL]
        with self._engine.connect() as conn:
            gepflegte = self._gepflegte(conn)
            ziele = self._ziele(conn, k_artikel)

        ergebnis = []
        for ziel in ziele:
            werte = []
            for feld in felder:
                if feld not in FELDER:
                    continue
                if nur_fehlende and str(ziel.get(feld) or "").strip():
                    continue
                bester = None
                for basis, herkunft, menge in self._ebenen(feld, ziel, gepflegte):
                    treffer = self._mehrheit(feld, menge)
                    if not treffer:
                        continue
                    wert, n, gesamt, beispiel = treffer
                    anteil = n / gesamt
                    sicherheit = max(5, min(basis, round(_deckel(gesamt, basis) * anteil)))
                    gruende = [
                        f"{n} von {gesamt} gepflegten Artikeln – {herkunft} – "
                        f"tragen {wert} (z. B. {beispiel})",
                    ]
                    if anteil < 1:
                        rest = gesamt - n
                        gruende.append("der übrige Artikel trägt einen anderen Wert" if rest == 1
                                       else f"die übrigen {rest} tragen einen anderen Wert")
                    if gesamt == 1:
                        gruende.append("nur ein einziger Beleg – das kann ein Einzelfall sein")
                    if feld == "Warennummer":
                        gruende.append("die zolltarifliche Einreihung bleibt deine Entscheidung")
                    if bester is None or sicherheit > bester["sicherheit"]:
                        bester = {"feld": feld, "wert": wert, "roh": wert,
                                  "label": herkunft, "sicherheit": sicherheit,
                                  "stufe": stufe(sicherheit), "begruendung": gruende}
                if bester:
                    werte.append(bester)
            if werte:
                ergebnis.append({
                    "kArtikel": ziel["kArtikel"], "ArtNr": ziel["cArtNr"],
                    "Artikel": ziel["Artikel"], "quelle": None,
                    "quelle_text": "aus dem eigenen Artikelstamm abgeleitet",
                    "werte": werte,
                })
        return ergebnis

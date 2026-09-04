"""
Write-Logik für JTL-Artikelstammdaten (Lücken füllen aus dem Health-Check).

Geschrieben werden ausschließlich sechs Felder, jedes über eine Weißliste fest
verdrahtet auf Tabelle + Spalte. Alles andere ist nicht erreichbar — bewusst kein
generischer Weg wie export_to_db(), der jede gelieferte Spalte ins SET nimmt.

An der Wawi geprüft (2026-08-11, read-only):
  - dbo.tArtikel trägt JTLs eigene Trigger tgr_tartikel_INSUP und
    tgr_tArtikel_Sync_INSUP (AFTER INSERT, UPDATE). ALLE sechs Zielspalten stehen in
    der UPDATE(...)-Wächterliste des Sync-Triggers, JTLs Buchführung für den
    Plattform-/Shop-Abgleich läuft bei einem direkten UPDATE also mit.
    jtlActionValidator_tartikel ist ein reiner AFTER-DELETE-Trigger.
  - Beide Zieltabellen haben bRowversion (timestamp) → optimistisches Sperren.
  - Jeder aktive Artikel hat eine Beschreibungszeile für kSprache=1/kPlattform=1/
    kShop=0 (0 Ausnahmen) → reines UPDATE, kein INSERT-Pfad. Die Shop-Zeilen
    (kPlattform=2, kShop=1) bleiben unangetastet.
  - cBarcode hat KEINEN eindeutigen Index → Dubletten muss dieser Code selbst abfangen.
  - Gewicht geht nach fGewicht, weil der Intrastat-Export dieses Projekts damit rechnet.

Ablauf wie beim Eingangsrechnungs-Writer: build_plan() löst read-only auf, prüft und
baut einen Plan. Im Dry-Run wird NICHTS ausgeführt; der echte Write nimmt denselben
Codepfad und läuft nur mit dry_run=False und fehlerfreiem Plan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from sqlalchemy import create_engine, text

from app.core.database import SessionLocal
from app.models.dataset import DbConnection
from app.services.db_service import get_engine_str

# Sprache/Plattform/Shop der Beschreibungszeile, die die Wawi-Oberfläche zeigt.
BESCHREIBUNG_SCHLUESSEL = {"kSprache": 1, "kPlattform": 1, "kShop": 0}

# Obergrenze je Lauf – begrenzt den Schaden eines Fehlgriffs.
MAX_AENDERUNGEN = 500


# ── Feld-Weißliste ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Feld:
    tabelle: str
    spalte: str
    pruefe: Callable            # (rohwert) -> (wert, fehler|None, hinweis|None)
    beschriftung: str


def _iso2_tabelle() -> dict:
    """Klartext-Ländernamen → ISO-3166-alpha-2. Der Stamm ist gemischt gepflegt
    ('IT' neben 'Italien'), deshalb wird normalisiert statt abgelehnt."""
    namen = {
        "deutschland": "DE", "brd": "DE", "germany": "DE",
        "oesterreich": "AT", "österreich": "AT", "austria": "AT",
        "schweiz": "CH", "switzerland": "CH",
        "italien": "IT", "italy": "IT",
        "niederlande": "NL", "holland": "NL", "netherlands": "NL",
        "frankreich": "FR", "france": "FR",
        "belgien": "BE", "polen": "PL", "poland": "PL",
        "tschechien": "CZ", "tschechische republik": "CZ", "czech republic": "CZ",
        "daenemark": "DK", "dänemark": "DK", "denmark": "DK",
        "schweden": "SE", "sweden": "SE", "spanien": "ES", "spain": "ES",
        "portugal": "PT", "ungarn": "HU", "hungary": "HU",
        "slowakei": "SK", "slowenien": "SI", "griechenland": "GR",
        "finnland": "FI", "irland": "IE", "luxemburg": "LU", "norwegen": "NO",
        "kroatien": "HR", "litauen": "LT", "lettland": "LV", "estland": "EE",
        "malta": "MT", "zypern": "CY", "rumaenien": "RO", "rumänien": "RO",
        "bulgarien": "BG",
        "grossbritannien": "GB", "großbritannien": "GB",
        "vereinigtes koenigreich": "GB", "vereinigtes königreich": "GB",
        "usa": "US", "vereinigte staaten": "US",
        "china": "CN", "volksrepublik china": "CN", "tuerkei": "TR", "türkei": "TR",
        "japan": "JP", "indien": "IN", "taiwan": "TW", "vietnam": "VN", "thailand": "TH",
    }
    return namen


ISO2_NAMEN = _iso2_tabelle()
ISO2_GUELTIG = set(ISO2_NAMEN.values()) | {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    "DE", "CH", "GB", "NO", "US", "CN", "TR", "JP", "IN", "TW", "VN", "TH", "KR",
    "RS", "BA", "UA", "MX", "BR", "CA", "AU", "ZA", "IL", "AE", "MY", "ID", "PK", "BD",
}


def _pruefziffer_ok(ziffern: str) -> bool:
    """GTIN-Prüfziffer (mod 10) – gilt für EAN-8, UPC-12, EAN-13 und GTIN-14."""
    stellen = [int(z) for z in ziffern]
    pruef = stellen.pop()
    # Von rechts nach links abwechselnd 3 und 1 gewichten.
    summe = sum(z * (3 if i % 2 == 0 else 1) for i, z in enumerate(reversed(stellen)))
    return (10 - summe % 10) % 10 == pruef


def pruefe_ean(roh):
    wert = re.sub(r"[\s\-.]", "", str(roh or ""))
    if not wert:
        return None, "leer", None
    if not wert.isdigit():
        return None, f"'{roh}' enthält Zeichen, die keine Ziffern sind", None
    if len(wert) not in (8, 12, 13, 14):
        return None, f"{len(wert)} Stellen – gültig sind 8, 12, 13 oder 14", None
    if not _pruefziffer_ok(wert):
        return None, f"Prüfziffer von '{wert}' stimmt nicht", None
    return wert, None, None


def pruefe_taric(roh):
    wert = re.sub(r"[\s.]", "", str(roh or ""))
    if not wert:
        return None, "leer", None
    if not wert.isdigit():
        return None, f"'{roh}' enthält Zeichen, die keine Ziffern sind", None
    if len(wert) != 8:
        return None, (f"{len(wert)} Stellen – die Warennummer der Kombinierten "
                      "Nomenklatur hat 8"), None
    return wert, None, None


def pruefe_iso2(roh):
    wert = str(roh or "").strip()
    if not wert:
        return None, "leer", None
    hinweis = None
    if len(wert) != 2:
        code = ISO2_NAMEN.get(wert.lower())
        if not code:
            return None, f"'{wert}' ist kein bekanntes Land – bitte ISO-Kürzel (z.B. DE)", None
        hinweis = f"'{wert}' als '{code}' geschrieben"
        wert = code
    wert = wert.upper()
    if wert not in ISO2_GUELTIG:
        return None, f"'{wert}' ist kein gültiges ISO-3166-Länderkürzel", None
    return wert, None, hinweis


def pruefe_gewicht(roh):
    wert = str(roh or "").strip().lower().replace(",", ".")
    if not wert:
        return None, "leer", None
    treffer = re.match(r"^([0-9]*\.?[0-9]+)\s*(kg|g|gramm|kilo|kilogramm)?$", wert)
    if not treffer:
        return None, f"'{roh}' ist keine Gewichtsangabe", None
    zahl = float(treffer.group(1))
    hinweis = None
    if treffer.group(2) in ("g", "gramm"):
        zahl = zahl / 1000.0
        hinweis = f"{treffer.group(1)} g als {zahl:.3f} kg geschrieben"
    if zahl <= 0:
        return None, "Gewicht muss größer als 0 sein", None
    if zahl > 2000:
        return None, f"{zahl} kg ist unplausibel (Grenze 2.000 kg)", None
    return round(zahl, 3), None, hinweis


def _pruefe_text(max_laenge: int):
    def pruefer(roh):
        wert = str(roh or "").strip()
        if not wert:
            return None, "leer", None
        if len(wert) > max_laenge:
            return None, f"{len(wert)} Zeichen – die Spalte fasst {max_laenge}", None
        return wert, None, None
    return pruefer


FELDER: dict[str, Feld] = {
    "EAN":           Feld("dbo.tArtikel", "cBarcode", pruefe_ean, "EAN"),
    "HAN":           Feld("dbo.tArtikel", "cHAN", _pruefe_text(255), "Herstellernummer"),
    "Warennummer":   Feld("dbo.tArtikel", "cTaric", pruefe_taric, "Warennummer (cTaric)"),
    "Herkunftsland": Feld("dbo.tArtikel", "cHerkunftsland", pruefe_iso2, "Ursprungsland"),
    "Gewicht":       Feld("dbo.tArtikel", "fGewicht", pruefe_gewicht, "Gewicht (kg)"),
    "Beschreibung":  Feld("dbo.tArtikelBeschreibung", "cBeschreibung",
                          _pruefe_text(100000), "Beschreibung"),
}


# ── Ergebnis-Struktur ───────────────────────────────────────────────────────────

@dataclass
class ArtikelWritePlan:
    ok: bool = False
    dry_run: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # je Änderung: kArtikel, ArtNr, Artikel, feld, tabelle, spalte, alt, neu, quelle,
    #              status (bereit|fehler|belegt|unveraendert|geschrieben|kollision), hinweis
    aenderungen: list[dict] = field(default_factory=list)
    statements: list[str] = field(default_factory=list)

    @property
    def bereit(self) -> list[dict]:
        return [a for a in self.aenderungen if a["status"] == "bereit"]

    def to_dict(self) -> dict:
        def _j(v):
            if isinstance(v, Decimal):
                return float(v)
            if isinstance(v, (bytes, bytearray)):
                return v.hex()
            return v
        return {
            "ok": self.ok,
            "dry_run": self.dry_run,
            "warnings": self.warnings,
            "errors": self.errors,
            "aenderungen": [{k: _j(v) for k, v in a.items() if not k.startswith("_")}
                            for a in self.aenderungen],
            "statements": self.statements,
            "anzahl_bereit": len(self.bereit),
            "anzahl_artikel": len({a["kArtikel"] for a in self.bereit}),
        }

    def report(self) -> str:
        L = [f"{'DRY-RUN' if self.dry_run else 'WRITE'}  →  {'OK' if self.ok else 'FEHLER'}"]
        if self.errors:
            L.append("\nFEHLER:")
            L += [f"  ✗ {e}" for e in self.errors]
        if self.warnings:
            L.append("\nWarnungen:")
            L += [f"  ⚠ {w}" for w in self.warnings]
        L.append("")
        for a in self.aenderungen:
            zeichen = {"bereit": "→", "geschrieben": "✓"}.get(a["status"], "·")
            L.append(f"  {zeichen} [{a['status']:12}] {a['ArtNr']:22} {a['feld']:14} "
                     f"{str(a['alt'])[:28]!r} → {str(a['neu'])[:40]!r}"
                     + (f"   ({a['hinweis']})" if a.get("hinweis") else ""))
        L.append(f"\n{len(self.bereit)} Werte in "
                 f"{len({a['kArtikel'] for a in self.bereit})} Artikeln bereit.")
        return "\n".join(L)


# ── Writer ──────────────────────────────────────────────────────────────────────

class ArtikelWriter:
    def __init__(self, connection_id: int):
        db = SessionLocal()
        try:
            conn = db.query(DbConnection).filter(DbConnection.id == connection_id).first()
            if not conn:
                raise ValueError(f"DB-Verbindung #{connection_id} nicht gefunden")
            if conn.db_type != "mssql":
                raise ValueError("Artikel-Write nur für JTL/MSSQL")
            self.connection_id = connection_id
            self._engine = create_engine(get_engine_str(conn),
                                         connect_args={"timeout": 30, "login_timeout": 10})
        finally:
            db.close()

    # ── Read-only-Auflösung ─────────────────────────────────────────────────────
    def _lade_artikel(self, conn, k_artikel: list[int]) -> dict:
        """Aktuelle Werte + bRowversion beider Tabellen, je kArtikel."""
        if not k_artikel:
            return {}
        platzhalter = ", ".join(f":k{i}" for i in range(len(k_artikel)))
        params = {f"k{i}": k for i, k in enumerate(k_artikel)}
        rows = conn.execute(text(f"""
            SELECT A.kArtikel, A.cArtNr, A.cBarcode, A.cHAN, A.cTaric, A.cHerkunftsland,
                   A.fGewicht, A.bRowversion AS rv_artikel,
                   AB.cName, AB.cBeschreibung, AB.bRowversion AS rv_beschreibung
            FROM dbo.tArtikel A
            LEFT JOIN dbo.tArtikelBeschreibung AB
                   ON AB.kArtikel = A.kArtikel AND AB.kSprache = :s
                  AND AB.kPlattform = :p AND AB.kShop = :sh
            WHERE A.kArtikel IN ({platzhalter})
        """), {**params, "s": BESCHREIBUNG_SCHLUESSEL["kSprache"],
               "p": BESCHREIBUNG_SCHLUESSEL["kPlattform"],
               "sh": BESCHREIBUNG_SCHLUESSEL["kShop"]}).mappings().all()
        return {r["kArtikel"]: dict(r) for r in rows}

    def _ean_dubletten(self, conn, eans: list[str], eigene: dict) -> dict:
        """EAN → (kArtikel, cArtNr) eines ANDEREN Artikels, der sie schon trägt."""
        if not eans:
            return {}
        platzhalter = ", ".join(f":e{i}" for i in range(len(eans)))
        params = {f"e{i}": e for i, e in enumerate(eans)}
        treffer = {}
        for r in conn.execute(text(
                f"SELECT kArtikel, cArtNr, cBarcode FROM dbo.tArtikel "
                f"WHERE cBarcode IN ({platzhalter})"), params).mappings():
            if eigene.get(r["cBarcode"]) != r["kArtikel"]:
                treffer[r["cBarcode"]] = (r["kArtikel"], r["cArtNr"])
        return treffer

    # ── Plan ────────────────────────────────────────────────────────────────────
    def build_plan(self, aenderungen: list[dict], dry_run: bool = True,
                   ersetzen: bool = False) -> ArtikelWritePlan:
        """
        aenderungen: [{kArtikel, feld, wert, quelle, ersetzen?}]
        ersetzen=False (Grundfall): bereits gefüllte Felder werden NICHT überschrieben.

        Je Änderung darf `ersetzen` den Grundfall aufheben. Das ist nötig, weil die
        Felder verschieden gemeint sind: eine vorhandene EAN überschreibt man nie
        versehentlich, ein dürftiger Beschreibungstext soll dagegen genau ersetzt
        werden. Ein Stapel darf deshalb beides enthalten.
        """
        plan = ArtikelWritePlan(dry_run=dry_run)

        if not aenderungen:
            plan.errors.append("Keine Änderungen übergeben")
            return plan
        if len(aenderungen) > MAX_AENDERUNGEN:
            plan.errors.append(
                f"{len(aenderungen)} Änderungen – erlaubt sind {MAX_AENDERUNGEN} je Lauf")
            return plan

        unbekannt = {a.get("feld") for a in aenderungen} - set(FELDER)
        if unbekannt:
            plan.errors.append("Nicht schreibbare Felder: " + ", ".join(sorted(map(str, unbekannt))))
            return plan

        k_liste = sorted({int(a["kArtikel"]) for a in aenderungen})

        with self._engine.connect() as conn:
            stamm = self._lade_artikel(conn, k_liste)

            fehlend = [k for k in k_liste if k not in stamm]
            if fehlend:
                plan.errors.append(
                    f"{len(fehlend)} Artikel gibt es nicht (mehr): "
                    + ", ".join(map(str, fehlend[:10])))

            # EAN-Dubletten in einem Rutsch prüfen (cBarcode hat keinen eindeutigen Index)
            ean_werte, ean_eigner = [], {}
            for a in aenderungen:
                if a.get("feld") == "EAN":
                    wert, fehler, _ = pruefe_ean(a.get("wert"))
                    if wert and not fehler:
                        ean_werte.append(wert)
                        ean_eigner[wert] = int(a["kArtikel"])
            dubletten = self._ean_dubletten(conn, ean_werte, ean_eigner)
            # Dubletten innerhalb des Stapels selbst
            doppelt_im_stapel = {e for e in ean_werte if ean_werte.count(e) > 1}

            for a in aenderungen:
                k = int(a["kArtikel"])
                feld = a["feld"]
                f = FELDER[feld]
                zeile = stamm.get(k, {})
                alt = zeile.get(f.spalte)
                eintrag = {
                    "kArtikel": k,
                    "ArtNr": zeile.get("cArtNr") or f"#{k}",
                    "Artikel": zeile.get("cName") or "",
                    "feld": feld,
                    "tabelle": f.tabelle,
                    "spalte": f.spalte,
                    "alt": float(alt) if isinstance(alt, Decimal) else alt,
                    "neu": None,
                    "quelle": a.get("quelle") or "manuell",
                    "status": "fehler",
                    "hinweis": "",
                    "_rv": zeile.get("rv_beschreibung" if f.tabelle.endswith("Beschreibung")
                                     else "rv_artikel"),
                }
                plan.aenderungen.append(eintrag)

                if k not in stamm:
                    eintrag["hinweis"] = "Artikel nicht gefunden"
                    continue
                if f.tabelle.endswith("Beschreibung") and zeile.get("rv_beschreibung") is None:
                    eintrag["hinweis"] = ("Keine Beschreibungszeile für Sprache 1 / "
                                          "Plattform 1 / Shop 0")
                    continue

                wert, fehler, hinweis = f.pruefe(a.get("wert"))
                if fehler:
                    eintrag["hinweis"] = fehler
                    continue
                eintrag["neu"] = wert
                if hinweis:
                    eintrag["hinweis"] = hinweis

                # Ist das Feld schon gefüllt?
                belegt = alt is not None and str(alt).strip() not in ("", "0", "0.0")
                if f.spalte == "fGewicht":
                    belegt = alt is not None and float(alt) > 0
                if belegt and str(alt).strip() == str(wert).strip():
                    eintrag["status"] = "unveraendert"
                    eintrag["hinweis"] = "steht schon so in der Wawi"
                    continue
                darf_ersetzen = ersetzen if a.get("ersetzen") is None else bool(a["ersetzen"])
                if belegt and not darf_ersetzen:
                    eintrag["status"] = "belegt"
                    eintrag["hinweis"] = f"steht bereits auf '{alt}' – nicht überschrieben"
                    continue
                if belegt:
                    eintrag["hinweis"] = (eintrag["hinweis"] + " · " if eintrag["hinweis"] else "") \
                        + f"überschreibt '{str(alt)[:60]}'"

                if feld == "EAN":
                    if wert in doppelt_im_stapel:
                        eintrag["hinweis"] = "dieselbe EAN kommt in diesem Stapel mehrfach vor"
                        continue
                    if wert in dubletten:
                        fremd_k, fremd_nr = dubletten[wert]
                        eintrag["hinweis"] = f"EAN gehört schon zu Artikel {fremd_nr} (#{fremd_k})"
                        continue

                eintrag["status"] = "bereit"

        plan.statements = self._render_statements(plan)

        belegt_anzahl = len([a for a in plan.aenderungen if a["status"] == "belegt"])
        if belegt_anzahl:
            plan.warnings.append(
                f"{belegt_anzahl} Werte übergangen, weil das Feld in der Wawi schon "
                "gefüllt ist")
        fehler_anzahl = len([a for a in plan.aenderungen if a["status"] == "fehler"])
        if fehler_anzahl:
            plan.errors.append(f"{fehler_anzahl} Werte sind nicht schreibbar (siehe Liste)")
        if not plan.bereit and not plan.errors:
            plan.warnings.append("Nichts zu schreiben")

        plan.ok = not plan.errors and bool(plan.bereit)

        # Echter Write nur ausdrücklich gewünscht und fehlerfrei.
        if not dry_run and plan.ok:
            self._execute(plan)

        return plan

    def _render_statements(self, plan: ArtikelWritePlan) -> list[str]:
        """Parametrisiertes SQL zur Anzeige – exakt das, was _execute ausführt."""
        s = ["BEGIN TRAN;"]
        for tabelle, k, felder in self._gruppen(plan):
            sets = ", ".join(f"[{sp}] = :{sp}" for sp in felder)
            if tabelle.endswith("Beschreibung"):
                s.append(f"UPDATE {tabelle} SET {sets}\n  WHERE kArtikel = {k} AND kSprache = 1 "
                         f"AND kPlattform = 1 AND kShop = 0 AND bRowversion = :rv;")
            else:
                s.append(f"UPDATE {tabelle} SET {sets}\n  WHERE kArtikel = {k} AND bRowversion = :rv;")
        s.append("COMMIT TRAN;")
        return s

    @staticmethod
    def _gruppen(plan: ArtikelWritePlan):
        """Je (Tabelle, kArtikel) ein UPDATE mit allen Feldern dieser Zeile."""
        gruppen: dict = {}
        for a in plan.bereit:
            gruppen.setdefault((a["tabelle"], a["kArtikel"]), []).append(a)
        for (tabelle, k), eintraege in gruppen.items():
            yield tabelle, k, {e["spalte"]: e for e in eintraege}

    def _execute(self, plan: ArtikelWritePlan) -> None:
        """Echter Write in EINER Transaktion. Nur über dry_run=False erreichbar.

        Optimistisches Sperren über bRowversion: hat jemand zwischen Plan und Write
        gepflegt, trifft das UPDATE nicht mehr (rowcount 0) und die Zeile wird als
        Kollision gemeldet statt überschrieben. Die übrigen Artikel sind voneinander
        unabhängig und werden trotzdem geschrieben.
        """
        with self._engine.begin() as conn:
            for tabelle, k, felder in self._gruppen(plan):
                eintraege = list(felder.values())
                rv = eintraege[0]["_rv"]
                sets = ", ".join(f"[{sp}] = :{sp}" for sp in felder)
                params = {sp: e["neu"] for sp, e in felder.items()}
                params.update({"k": k, "rv": rv})
                if tabelle.endswith("Beschreibung"):
                    sql = (f"UPDATE {tabelle} SET {sets} WHERE kArtikel = :k "
                           f"AND kSprache = :s AND kPlattform = :p AND kShop = :sh "
                           f"AND bRowversion = :rv")
                    params.update({"s": BESCHREIBUNG_SCHLUESSEL["kSprache"],
                                   "p": BESCHREIBUNG_SCHLUESSEL["kPlattform"],
                                   "sh": BESCHREIBUNG_SCHLUESSEL["kShop"]})
                else:
                    sql = f"UPDATE {tabelle} SET {sets} WHERE kArtikel = :k AND bRowversion = :rv"
                betroffen = conn.execute(text(sql), params).rowcount
                for e in eintraege:
                    if betroffen:
                        e["status"] = "geschrieben"
                    else:
                        e["status"] = "kollision"
                        e["hinweis"] = ("in der Wawi zwischenzeitlich geändert – "
                                        "nicht überschrieben")

        kollisionen = [a for a in plan.aenderungen if a["status"] == "kollision"]
        if kollisionen:
            plan.warnings.append(
                f"{len(kollisionen)} Werte übersprungen: die Artikel wurden zwischen "
                "Vorschau und Schreiben in der Wawi geändert")


def build_dry_run(connection_id: int, aenderungen: list[dict],
                  ersetzen: bool = False) -> ArtikelWritePlan:
    """Bequemer Einstieg: Plan bauen, nichts schreiben."""
    return ArtikelWriter(connection_id).build_plan(aenderungen, dry_run=True, ersetzen=ersetzen)


# ── Artikel neu anlegen ─────────────────────────────────────────────────────────
#
# Anlass: beim Buchen einer Lieferantenrechnung taucht eine Zeile auf, zu der es
# in der Wawi noch keinen Artikel gibt. Statt den Beleg zu verlassen, soll der
# Artikel aus dem Formular heraus entstehen — mit den Stammdaten, die auf der
# Rechnung ohnehin stehen (Warennummer, Herkunftsland, Gewicht, Lieferanten-
# Artikelnummer, EK).
#
# ACHTUNG, das ist der erste INSERT-Pfad dieses Moduls. Alles darüber ändert nur
# vorhandene Zeilen. Was JTL beim Anlegen eines Artikels tatsächlich schreibt,
# ist NICHT geraten, sondern am 2026-09-04 in der Test-Wawi (Verbindung 6) mit
# doku/gm_diff.py gemessen: von Hand Artikel „TEST_DM" angelegt, Datenbank
# vorher/nachher verglichen. Ergebnis — sechs Tabellen:
#
#   tArtikel              +1  die Zeile selbst (kArtikel ist IDENTITY)
#   tArtikelBeschreibung  +1  kSprache 1 / kPlattform 1 / kShop 0, Name + Kurztext
#   tliefartikel          +1  Lieferant, dessen ArtNr, EK, cWaehrung, nStandard=1
#   tlagerbestand         +1  reine Nullzeile
#   tArtikelSpeicher      +3  JTLs Suchindex: nID 0 = ArtNr, 5 = Name, 8 = Liefer-Nr
#   tkategorieartikel     +1  nur, weil beim Anlegen eine Kategorie gewählt wurde
#
# tlagerbestand und tArtikelSpeicher pflegen JTLs eigene Trigger
# (tgr_tartikel_INSUP bzw. tgr_tArtikelBeschreibung_INSUP / tgr_tliefartikel_INSUP).
# Wir schreiben sie deshalb NICHT selbst, sondern prüfen nach dem Anlegen nach und
# ergänzen nur, was fehlt — sonst entstünden Dubletten im Suchindex, und der
# Artikel wäre in der Wawi doppelt oder gar nicht auffindbar.
#
# Die Kategorie lassen wir weg: sie ist eine Sortierentscheidung des Anwenders,
# keine Angabe der Rechnung. Der Artikel ist ohne sie vollständig.

# Werte, die JTL beim Anlegen setzt und die NICHT aus dem Spaltenstandard kommen.
# Ohne sie entstünde ein Artikel, der anders aussieht als ein von Hand angelegter:
# cAktiv stünde auf 'N' (unsichtbar), fPackeinheit auf 0 (Division!),
# kSteuerklasse auf 0 (keine gültige Klasse). Alle Werte aus der Messung.
ANLEGE_VORGABEN = {
    "cAktiv": "Y", "cNeu": "Y", "cPreisliste": "N", "cTopArtikel": "N",
    "cInet": "N", "cDelInet": " ", "cLagerArtikel": "N", "cTeilbar": "N",
    "cLagerKleinerNull": "N", "cLagerVariation": "N",
    "fPackeinheit": 1.0, "kSteuerklasse": 1, "kVersandklasse": 1,
    "kZustand": 1, "nEbayAbgleich": 1, "nPuffer": 0, "nIstVater": 0,
}

# Lagerführung: in dieser Wawi stehen 2.515 von 2.794 aktiven Artikeln auf
# cLagerAktiv='Y'. Ein Artikel, der über eine Eingangsrechnung hereinkommt, wird
# eingelagert — deshalb ist 'Y' die Vorgabe. Der von Hand angelegte Testartikel
# bekam 'N', weil beim Anlegen im Client niemand das Häkchen gesetzt hat; das ist
# eine Entscheidung des Anwenders und steht im Formular als Schalter.
LAGER_VORGABE = "Y"

# Was das Formular anbieten darf. Alles andere wird nicht geschrieben — eine
# Weißliste, wie beim Ändern auch, damit ein manipulierter Aufruf keine fremden
# Spalten erreicht.
ANLEGE_FELDER = {
    # Feld              Spalte            Tabelle    Prüfer
    "cArtNr":           ("cArtNr",           "A",  _pruefe_text(100)),
    "cName":            ("cName",            "B",  _pruefe_text(255)),
    "cKurzBeschreibung": ("cKurzBeschreibung", "B", _pruefe_text(2000)),
    "cBarcode":         ("cBarcode",         "A",  pruefe_ean),
    "cHAN":             ("cHAN",             "A",  _pruefe_text(255)),
    "cTaric":           ("cTaric",           "A",  pruefe_taric),
    "cHerkunftsland":   ("cHerkunftsland",   "A",  pruefe_iso2),
    "fGewicht":         ("fGewicht",         "A",  pruefe_gewicht),
}


def _zahl_oder_none(roh):
    """Freundlich gemeinte Zahl aus dem Formular (auch '17,04')."""
    if roh is None or str(roh).strip() == "":
        return None
    try:
        return float(str(roh).strip().replace(",", "."))
    except ValueError:
        return None


@dataclass
class AnlegePlan:
    """Was passieren soll, samt allem, was dagegen spricht."""
    werte: dict = field(default_factory=dict)       # geprüfte Spaltenwerte
    beschreibung: dict = field(default_factory=dict)
    lieferant: dict = field(default_factory=dict)
    fehler: list = field(default_factory=list)      # blockieren
    hinweise: list = field(default_factory=list)    # nur zur Kenntnis
    kArtikel: int = 0                               # nach dem Schreiben gesetzt

    @property
    def ok(self) -> bool:
        return not self.fehler

    def to_dict(self) -> dict:
        return {"ok": self.ok, "werte": self.werte, "beschreibung": self.beschreibung,
                "lieferant": self.lieferant, "fehler": self.fehler,
                "hinweise": self.hinweise, "kArtikel": self.kArtikel}


class ArtikelAnleger(ArtikelWriter):
    """Legt einen Artikel in der Wawi an. Zweistufig wie das Ändern auch:
    erst `pruefe` (schreibt nichts), dann `lege_an` (schreibt nur einen
    geprüften Plan)."""

    def pruefe(self, eingabe: dict) -> AnlegePlan:
        """Alles prüfen, was sich ohne Schreiben prüfen lässt.

        Blockierend sind nur Dinge, die einen kaputten oder doppelten Artikel
        ergäben. Ein unlesbares Gewicht ist kein Grund, das Anlegen zu
        verweigern — dann bleibt das Feld eben leer und wird als Hinweis
        ausgewiesen. Bei Artikelnummer und Name ist es umgekehrt: ohne sie ist
        der Artikel in der Wawi nicht benutzbar.
        """
        plan = AnlegePlan()

        for feld, (spalte, tabelle, pruefer) in ANLEGE_FELDER.items():
            roh = eingabe.get(feld)
            if roh is None or str(roh).strip() == "":
                continue
            wert, fehler, hinweis = pruefer(roh)
            if fehler:
                # Pflichtfelder blockieren, der Rest wird nur weggelassen.
                if feld in ("cArtNr", "cName"):
                    plan.fehler.append(f"{feld}: {fehler}")
                else:
                    plan.hinweise.append(f"{feld} nicht übernommen – {fehler}")
                continue
            if hinweis:
                plan.hinweise.append(hinweis)
            (plan.beschreibung if tabelle == "B" else plan.werte)[spalte] = wert

        if not plan.werte.get("cArtNr"):
            plan.fehler.append("Ohne Artikelnummer geht es nicht")
        if not plan.beschreibung.get("cName"):
            plan.fehler.append("Ohne Artikelname geht es nicht")

        vk = _zahl_oder_none(eingabe.get("fVKNetto"))
        plan.werte["fVKNetto"] = vk if vk and vk > 0 else 0.0
        plan.werte["cLagerAktiv"] = (
            LAGER_VORGABE if eingabe.get("lagerAktiv", True) else "N")

        # Lieferantenzuordnung – nur vollständig oder gar nicht.
        kLieferant = eingabe.get("kLieferant")
        if kLieferant:
            ek = _zahl_oder_none(eingabe.get("fEKNetto"))
            plan.lieferant = {
                "kLieferant": int(kLieferant),
                "cLiefArtNr": str(eingabe.get("cLiefArtNr") or "").strip()[:100],
                "fEKNetto": ek if ek and ek > 0 else 0.0,
                "cName": str(eingabe.get("cLiefName")
                             or plan.beschreibung.get("cName") or "")[:255],
            }
            if not plan.lieferant["cLiefArtNr"]:
                plan.hinweise.append(
                    "Ohne Lieferanten-Artikelnummer wird die Zuordnung angelegt, "
                    "aber die Rechnung findet den Artikel beim nächsten Mal nicht "
                    "automatisch wieder.")

        if plan.fehler:
            return plan

        # Ab hier wird die Wawi befragt – nur lesend.
        with self._engine.connect() as conn:
            vorhanden = conn.execute(text(
                "SELECT kArtikel FROM dbo.tArtikel WHERE cArtNr = :a"),
                {"a": plan.werte["cArtNr"]}).first()
            if vorhanden:
                plan.fehler.append(
                    f"Die Artikelnummer '{plan.werte['cArtNr']}' gibt es schon "
                    f"(kArtikel {vorhanden[0]}). Artikelnummern sind in JTL "
                    f"eindeutig – bitte den vorhandenen Artikel zuordnen.")

            ean = plan.werte.get("cBarcode")
            if ean:
                doppelt = conn.execute(text(
                    "SELECT TOP 1 kArtikel, cArtNr FROM dbo.tArtikel "
                    "WHERE cBarcode = :e"), {"e": ean}).first()
                if doppelt:
                    # Kein Abbruch: cBarcode hat keinen eindeutigen Index, und
                    # Gebinde teilen sich in der Praxis eine EAN. Aber sichtbar.
                    plan.hinweise.append(
                        f"Die EAN {ean} trägt bereits Artikel {doppelt[1]} "
                        f"(kArtikel {doppelt[0]}).")

            if plan.lieferant:
                lief = conn.execute(text(
                    "SELECT cFirma FROM dbo.tlieferant WHERE kLieferant = :k"),
                    {"k": plan.lieferant["kLieferant"]}).first()
                if not lief:
                    plan.fehler.append(
                        f"Lieferant {plan.lieferant['kLieferant']} gibt es nicht")
                else:
                    plan.lieferant["cFirma"] = lief[0]

        return plan

    def lege_an(self, eingabe: dict) -> AnlegePlan:
        """Anlegen. Prüft IMMER frisch, schreibt nur einen fehlerfreien Plan.

        Alles in EINER Transaktion: entsteht auf halbem Weg ein Fehler, gibt es
        auch keinen halben Artikel. JTLs Trigger laufen in derselben Transaktion
        mit, deshalb steht der Suchindex am Ende schon, wenn sie ihn pflegen.
        """
        plan = self.pruefe(eingabe)
        if not plan.ok:
            return plan

        spalten = {**ANLEGE_VORGABEN, **plan.werte}
        jetzt = "SYSDATETIME()"
        namen = list(spalten)
        # SET NOCOUNT ON ist Pflicht, nicht Kosmetik: auf tArtikel liegen
        # Trigger, deren Anweisungen jeweils eine eigene Ergebnismenge
        # ("n rows affected") erzeugen. Ohne NOCOUNT liefert der Treiber die
        # erste davon zurueck und SCOPE_IDENTITY() kaeme nie an.
        sql = (f"SET NOCOUNT ON; INSERT INTO dbo.tArtikel "
               f"({', '.join(namen)}, dErstelldatum, dMod, dNeuImSortiment) "
               f"VALUES ({', '.join(':' + n for n in namen)}, {jetzt}, {jetzt}, {jetzt}); "
               f"SELECT CAST(SCOPE_IDENTITY() AS INT);")

        with self._engine.begin() as conn:
            # SCOPE_IDENTITY statt @@IDENTITY: auf tArtikel liegen Trigger, und
            # @@IDENTITY gäbe den Schlüssel zurück, den ein Trigger zuletzt
            # erzeugt hat – also womöglich eine ganz andere Tabelle.
            k = conn.execute(text(sql), spalten).scalar()
            if not k:
                raise RuntimeError("Die Wawi hat keine kArtikel zurückgegeben")
            plan.kArtikel = int(k)

            b = {**BESCHREIBUNG_SCHLUESSEL, **plan.beschreibung, "kArtikel": plan.kArtikel}
            conn.execute(text(
                f"INSERT INTO dbo.tArtikelBeschreibung ({', '.join(b)}) "
                f"VALUES ({', '.join(':' + n for n in b)})"), b)

            if plan.lieferant:
                L = plan.lieferant
                conn.execute(text("""
                    INSERT INTO dbo.tliefartikel
                      (tArtikel_kArtikel, tLieferant_kLieferant, cLiefArtNr,
                       fEKNetto, fEKBrutto, cWaehrung, nStandard, cName, dLBGeaendert)
                    VALUES (:ka, :kl, :nr, :ek, :ek, 'EUR', 1, :name, SYSDATETIME())
                """), {"ka": plan.kArtikel, "kl": L["kLieferant"],
                       "nr": L["cLiefArtNr"], "ek": L["fEKNetto"], "name": L["cName"]})

            # Nachsehen statt annehmen: die Bestandszeile legen JTLs Trigger an,
            # aber verlassen wollen wir uns darauf nicht – ein Artikel ohne
            # tlagerbestand macht in der Wawi Ärger. Nur ergänzen, was fehlt.
            if not conn.execute(text(
                    "SELECT 1 FROM dbo.tlagerbestand WHERE kArtikel = :k"),
                    {"k": plan.kArtikel}).first():
                conn.execute(text(
                    "INSERT INTO dbo.tlagerbestand (kArtikel) VALUES (:k)"),
                    {"k": plan.kArtikel})
                plan.hinweise.append("Bestandszeile selbst angelegt "
                                     "(kein Trigger hat sie erzeugt).")

            # Dasselbe für den Suchindex: ohne nID 0 findet die Wawi den Artikel
            # nicht über seine Nummer.
            hat = {r[0] for r in conn.execute(text(
                "SELECT nID FROM dbo.tArtikelSpeicher WHERE kArtikel = :k"),
                {"k": plan.kArtikel})}
            if 0 not in hat:
                conn.execute(text(
                    "INSERT INTO dbo.tArtikelSpeicher (kArtikel, cNummer, nID, nAktiv) "
                    "VALUES (:k, :n, 0, 1)"),
                    {"k": plan.kArtikel, "n": plan.werte["cArtNr"]})
                plan.hinweise.append("Suchindex-Eintrag der Artikelnummer selbst "
                                     "angelegt (kein Trigger hat ihn erzeugt).")

        return plan

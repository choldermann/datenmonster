"""
Export Service – schreibt das Mapping-Ergebnis in verschiedene Formate.
Unterstützt: CSV, XLSX, JSON, XML (template-basiert), DB (MSSQL/MySQL)
"""
import io
import csv
import json
import re
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Dict, Any, Optional
import pandas as pd


# ─── CSV ──────────────────────────────────────────────────────────────────────

def export_csv(df: pd.DataFrame, delimiter: str = ";", encoding: str = "utf-8-sig") -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=delimiter)
    return buf.getvalue().encode(encoding)


# ─── Destatis Intrastat CSV (IDEV-Upload) ───────────────────────────────────────

def export_destatis_csv(df: pd.DataFrame, config: Optional[dict] = None) -> bytes:
    """
    Erzeugt die Destatis-Intrastat-CSV (IDEV-Upload-Format, "Meldung.csv"):
    16 Felder, ';'-getrennt, CRLF-Zeilenende, CP1252, KEINE Kopfzeile.

    Kennnummer und Zeitraum stehen bewusst nicht in der Datei – die werden im
    IDEV-Webformular eingetragen (analog zum ASC-Format, wo sie enthalten sind).

    Erwartete Spalten im df: commodity_code, country_of_origin, partner_country,
    transaction_nature, mode_of_transport, net_mass, statistical_value und optional
    'bundesland' (Ursprungs-/Bestimmungsbundesland pro Zeile → Feld 7).

    config: {
        "direction": "E" | "V",   # Feld 1 (Eingang / Versendung)
        "bundesland": "05",        # Feld 2, Bundesland des Meldepflichtigen (konstant)
    }
    """
    cfg = config or {}
    direction = str(cfg.get("direction") or "")
    bl_firma = str(cfg.get("bundesland") or "")
    # Feld 7 (Ursprungs-/Bestimmungsbundesland): fester Code aus der Config; leer →
    # fällt auf das Bundesland des Meldepflichtigen (Feld 2) zurück. Eine ggf. pro
    # Zeile im df vorhandene Spalte 'bundesland' hat weiterhin Vorrang.
    bl_line = str(cfg.get("bundesland_line") or "")

    def _s(v) -> str:
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).strip()

    def _num(v) -> str:
        s = _s(v)
        if s == "":
            return ""
        try:
            return str(int(round(float(s))))
        except (TypeError, ValueError):
            return s

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n",
                        quoting=csv.QUOTE_MINIMAL)
    for _, row in df.iterrows():
        writer.writerow([
            direction,                          # 1  Richtung (E/V)
            bl_firma,                           # 2  Bundesland Meldepflichtiger
            _s(row.get("transaction_nature")),  # 3  Art des Geschäfts
            _s(row.get("mode_of_transport")),   # 4  Verkehrszweig
            _s(row.get("country_of_origin")),   # 5  Ursprungsland
            "",                                 # 6  (reserviert)
            _s(row.get("bundesland")) or bl_line or bl_firma,  # 7  Ursprungs-/Bestimmungsbundesland
            "",                                 # 8  (reserviert)
            _s(row.get("partner_country")),     # 9  Herkunfts-/Bestimmungsland
            _s(row.get("commodity_code")),      # 10 Warennummer (KN8)
            "",                                 # 11 Besondere Maßeinheit
            _num(row.get("net_mass")),          # 12 Eigenmasse (kg)
            "",                                 # 13 (reserviert)
            _num(row.get("statistical_value")), # 14 Statistischer Wert
            "",                                 # 15 Rechnungsbetrag
            "",                                 # 16 (reserviert)
        ])
    return buf.getvalue().encode("cp1252", errors="replace")


# ─── Destatis Intrahandel CSV (IDEV "Außenhandel-A-Intrahandel Formularmeldung") ─

def export_destatis_intrahandel_csv(df: pd.DataFrame, config: Optional[dict] = None) -> bytes:
    """
    Erzeugt die Destatis-Intrahandel-CSV für den IDEV-CSV-Import in das Formular
    "Außenhandel-A-Intrahandel Formularmeldung" (hinterlegter Standardfilter "CSV").

    Format laut Destatis-Anleitung (Stand August 2024): 16 Felder, ';'-getrennt,
    KEINE Kopfzeile, KEINE Anführungszeichen (gelten als Feldbegrenzer und sind
    verboten), CRLF-Zeilenende, ganze Zahlen (volle kg / volle EURO). Eine Datei
    enthält BEIDE Richtungen; die Richtung kommt pro Zeile aus der Spalte
    'richtung' (Fallback: config['direction']).

    Spalten (Pos 1–16):
      1 Verkehrsrichtung (E/V)          9 Ursprungsland
      2 Bezugsmonat                    10 Warennummer (8-stellig)
      3 Art des Geschäfts              11 Warenbezeichnung (freiwillig → leer)
      4 Verkehrszweig                  12 Eigenmasse (volle kg)
      5 Versendungsmitgliedstaat (E)   13 Besondere Maßeinheit (→ leer)
      6 Bestimmungsmitgliedstaat (V)   14 Rechnungsbetrag (volle EURO)
      7 Bestimmungsbundesland (E)      15 Statistischer Wert (volle EURO)
      8 Ursprungsbundesland (V)        16 USt-IdNr. Warenempfänger (nur V)

    Erwartete df-Spalten: richtung, monat, transaction_nature, mode_of_transport,
    partner_country, country_of_origin, commodity_code, net_mass, invoiced_amount,
    statistical_value und optional bundesland, vat_id_recipient.

    config: { "direction": "V"|"E" (Fallback), "bundesland": "05" (Fallback) }
    """
    cfg = config or {}
    default_dir = str(cfg.get("direction") or "").strip()
    bl_cfg = str(cfg.get("bundesland") or "").strip()

    def _s(v) -> str:
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        # Anführungszeichen und Trennzeichen sind in der CSV nicht erlaubt
        return str(v).strip().replace('"', "").replace(";", " ").replace("\r", " ").replace("\n", " ")

    def _num(v) -> str:
        s = _s(v)
        if s == "":
            return ""
        try:
            return str(int(round(float(s))))
        except (TypeError, ValueError):
            return s

    lines: List[str] = []
    for _, row in df.iterrows():
        richtung = _s(row.get("richtung")) or default_dir
        is_v = richtung == "V"
        region = _s(row.get("bundesland")) or bl_cfg
        partner = _s(row.get("partner_country"))
        vat = _s(row.get("vat_id_recipient"))
        fields = [
            richtung,                              # 1  Verkehrsrichtung
            _s(row.get("monat")),                  # 2  Bezugsmonat
            _s(row.get("transaction_nature")),     # 3  Art des Geschäfts
            _s(row.get("mode_of_transport")),      # 4  Verkehrszweig
            "" if is_v else partner,               # 5  Versendungsmitgliedstaat (nur E)
            partner if is_v else "",               # 6  Bestimmungsmitgliedstaat (nur V)
            "" if is_v else region,                # 7  Bestimmungsbundesland (nur E)
            region if is_v else "",                # 8  Ursprungsbundesland (nur V)
            _s(row.get("country_of_origin")),      # 9  Ursprungsland
            _s(row.get("commodity_code")),         # 10 Warennummer
            "",                                    # 11 Warenbezeichnung (freiwillig)
            _num(row.get("net_mass")),             # 12 Eigenmasse (volle kg)
            "",                                    # 13 Besondere Maßeinheit
            _num(row.get("invoiced_amount")),      # 14 Rechnungsbetrag (volle EURO)
            _num(row.get("statistical_value")),    # 15 Statistischer Wert (volle EURO)
            vat if is_v else "",                   # 16 USt-IdNr. Warenempfänger (nur V)
        ]
        lines.append(";".join(fields))

    return ("\r\n".join(lines) + ("\r\n" if lines else "")).encode("cp1252", errors="replace")


# ─── Destatis Intrastat .idev (IDEV-Onlineformular-Import) ──────────────────────

def export_destatis_idev(df: pd.DataFrame, config: Optional[dict] = None) -> bytes:
    """
    Erzeugt EINE Destatis-Intrastat-".idev"-Datei (Import-/Exportformat des
    IDEV-Onlineformulars). Aufbau: 4-Byte-Header 1d e5 00 01, danach ein
    gzip-Stream mit kompaktem UTF-8-JSON.

    Eine Datei enthält BEIDE Richtungen gemischt (V = Versendung, E = Eingang):
    die Zeilenrichtung kommt pro df-Zeile aus der Spalte 'richtung' (Fallback:
    config['direction']).

    Erwartete df-Spalten (je Zeile): richtung ('V'/'E'), commodity_code,
    transaction_nature, mode_of_transport, net_mass, invoiced_amount,
    country_of_origin, partner_country und optional bundesland,
    vat_id_recipient, monat, bzr.

    config: {
        "login_name": "w3s81881",     # IDEV-Kennnummer (Pflicht)
        "bundesland": "05",            # Ursprungs-/Bestimmungsbundesland (Fallback)
        "direction": "V",             # Fallback wenn Zeile keine 'richtung' hat
        "bzr": "2026",                # Berichtszeitraum-Jahr (Fallback, sonst aus df.bzr)
        # Kontext-Konstanten (Defaults i.d.R. passend):
        "statistic_office_id": 1, "form_id": 639, "form_version": 6,
        "form_context_id": 1, "form_context_name": "intra", "language": "de",
        "fehlanzeige": "2",
    }
    """
    import gzip as _gzip
    import time as _time

    cfg = config or {}

    def _s(v) -> str:
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return str(v).strip()

    def _num(v) -> str:
        s = _s(v)
        if s == "":
            return ""
        try:
            return str(int(round(float(s))))
        except (TypeError, ValueError):
            return s

    default_dir = _s(cfg.get("direction"))
    bl_cfg = _s(cfg.get("bundesland"))
    bzr_cfg = _s(cfg.get("bzr"))

    meldungen: List[Dict[str, str]] = []
    bzr_seen = ""
    for _, row in df.iterrows():
        richtung = _s(row.get("richtung")) or default_dir
        adg = _s(row.get("transaction_nature"))
        region = _s(row.get("bundesland")) or bl_cfg
        row_bzr = _s(row.get("bzr"))
        if row_bzr and not bzr_seen:
            bzr_seen = row_bzr

        m: Dict[str, str] = {
            "artDesGeschäfts": adg,
            "artDesGeschäfts1": adg[0:1],
            "artDesGeschäfts2": adg[1:2],
            "eigenMass": _num(row.get("net_mass")),
            "monat": _s(row.get("monat")),
            "rechBetrag": _num(row.get("invoiced_amount")),
            "richtung": richtung,
            "ursprLand": _s(row.get("country_of_origin")),
            "verkehrszweig": _s(row.get("mode_of_transport")),
            "warennummer": _s(row.get("commodity_code")),
        }
        partner = _s(row.get("partner_country"))
        if richtung == "V":
            # Versendung: Bestimmungsland, Ursprungsbundesland, USt-IdNr Empfänger
            m["bestLand"] = partner
            if region:
                m["ursprRegion"] = region
            uid = _s(row.get("vat_id_recipient"))
            if uid:
                m["ustIdNrEmpf"] = uid
        else:
            # Eingang: Versendungsland, Bestimmungsbundesland
            m["versLand"] = partner
            if region:
                m["bestRegion"] = region
        # Feldreihenfolge alphabetisch wie im Referenz-Export
        meldungen.append({k: m[k] for k in sorted(m.keys())})

    bzr = bzr_cfg or bzr_seen
    now_ms = int(_time.time() * 1000)
    obj = {
        "context": {
            "creationDate": now_ms,
            "loginName": _s(cfg.get("login_name")),
            "statisticOfficeId": int(cfg.get("statistic_office_id", 1)),
            "reportingPeriod": bzr,
            "formId": int(cfg.get("form_id", 639)),
            "formVersion": int(cfg.get("form_version", 6)),
            "formContextId": int(cfg.get("form_context_id", 1)),
            "formContextName": _s(cfg.get("form_context_name")) or "intra",
            "language": _s(cfg.get("language")) or "de",
        },
        "dataset": {
            "BZR": bzr,
            "Fehlanzeige": _s(cfg.get("fehlanzeige")) or "2",
            "meldung": meldungen,
        },
        "formState": {},
    }

    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz_buf = io.BytesIO()
    with _gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=now_ms // 1000) as gz:
        gz.write(payload)
    return bytes([0x1D, 0xE5, 0x00, 0x01]) + gz_buf.getvalue()


# ─── DATEV Buchungsstapel (EXTF) ────────────────────────────────────────────────

# Die 125 Spalten des Buchungsstapels, Formatversion 700 / Kategorie 21 / Version 13.
# Reihenfolge und Schreibweise sind gegen eine echte DATEV-Beispieldatei geprüft –
# geraten werden darf hier nichts: DATEV ordnet die Werte über DIESE Kopfzeile zu,
# eine verschobene Spalte bucht stillschweigend auf das falsche Feld.
DATEV_SPALTEN: List[str] = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs",
    "Basisumsatz", "WKZ Basisumsatz", "Konto", "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel", "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Skonto",
    "Buchungstext", "Postensperre", "Diverse Adressnummer", "Geschäftspartnerbank",
    "Sachverhalt", "Zinssperre", "Beleglink",
] + [f"Beleginfo – {a} {i}" for i in range(1, 9) for a in ("Art", "Inhalt")] + [
    "KOST1 – Kostenstelle", "KOST2 – Kostenstelle", "Kost Menge",
    "EU-Land u. USt-IdNr.", "EU-Steuersatz", "Abw. Versteuerungsart",
    "Sachverhalt L+L", "Funktionsergänzung L+L", "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer", "BU 49 Funktionsergänzung",
] + [f"Zusatzinformation – {a} {i}" for i in range(1, 21) for a in ("Art", "Inhalt")] + [
    "Stück", "Gewicht", "Zahlweise", "Forderungsart", "Veranlagungsjahr",
    "Zugeordnete Fälligkeit", "Skontotyp", "Auftragsnummer", "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)", "EU-Mitgliedstaat (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)", "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)", "Herkunft-Kz", "Leerfeld", "KOST-Datum",
    "SEPA-Mandatsreferenz", "Skontosperre", "Gesellschaftername",
    "Beteiligtennummer", "Identifikationsnummer", "Zeichnernummer",
    "Postensperre bis", "Bezeichnung", "Kennzeichen", "Festschreibung",
    "Leistungsdatum", "Datum Zuord.", "Fälligkeit", "Generalumkehr", "Steuersatz",
    "Land", "Abrechnungsreferent", "BVV-Position",
    "EU-Mitgliedstaat u. UStID (Ursprung)", "EU-Steuersatz (Ursprung)",
    "Abw. Skontokonto",
]

# Welche Spalte des Mapping-Ergebnisses in welche DATEV-Spalte geht. Alles, was
# hier nicht steht, bleibt leer – das ist bei 125 Spalten der Normalfall.
_DATEV_FELDER = {
    "umsatz": 1, "soll_haben": 2, "wkz": 3, "konto": 7, "gegenkonto": 8,
    "bu_schluessel": 9, "belegdatum": 10, "belegfeld1": 11, "belegfeld2": 12,
    "skonto": 13, "buchungstext": 14, "eu_ustid": 40, "eu_steuersatz": 41,
    "faelligkeit": 117, "festschreibung": 114,
}

# Spalten, die DATEV in Anführungszeichen erwartet (Textfelder). Zahlen und
# Beträge stehen ohne – so hält es auch die Beispieldatei von DATEV.
_DATEV_TEXTFELDER = {2, 3, 9, 11, 12, 14, 40, 112, 113}


def _datev_text(v) -> str:
    """Feldwert als DATEV-Text: ohne Anführungszeichen, ohne Trenn-/Steuerzeichen."""
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return (str(v).strip().replace('"', "'").replace(";", " ")
            .replace("\r", " ").replace("\n", " "))


def _datev_betrag(v) -> str:
    """Betrag deutsch mit Komma, zwei Nachkommastellen, IMMER positiv.

    Das Vorzeichen trägt in DATEV nicht der Betrag, sondern das
    Soll/Haben-Kennzeichen – ein Minus im Umsatzfeld weist die Zeile ab.
    """
    s = _datev_text(v).replace(",", ".")
    if s == "":
        return ""
    try:
        return f"{abs(float(s)):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def export_datev_extf(df: pd.DataFrame, config: Optional[dict] = None) -> bytes:
    """DATEV-Buchungsstapel im offiziellen EXTF-Format (Version 700).

    Aufbau: Kopfzeile (31 Felder) + Spaltenzeile (125 Namen) + je Buchung eine
    Zeile mit 125 Feldern, ';'-getrennt, **CP1252** und **CRLF** – beides
    Vorgabe von DATEV, nicht Geschmack. Umlaute in UTF-8 lassen den Import
    scheitern, deshalb wird bewusst mit Ersatzzeichen kodiert statt zu brechen.

    Erwartete Spalten im df (alles andere wird ignoriert):
      umsatz            Bruttobetrag. **Brutto ist richtig:** bei Automatikkonten
                        (SKR03 3400/8400 …) rechnet DATEV die Steuer selbst heraus.
      soll_haben        "S" oder "H"
      konto             Personenkonto (Kreditor/Debitor)
      gegenkonto        Sachkonto (Wareneingang/Erlöse)
      belegdatum        TTMM, 4-stellig – das Jahr steht in der Kopfzeile
      belegfeld1        Rechnungsnummer
      belegfeld2        frei (im Altsystem: Fälligkeit)
      buchungstext, bu_schluessel, eu_ustid, eu_steuersatz, skonto, faelligkeit

    config: {
      "berater": "1001", "mandant": "456", "wj_beginn": "20260101",
      "sachkontenlaenge": 4, "datum_von": "20260801", "datum_bis": "20260831",
      "bezeichnung": "Eingangsrechnungen 08/2026", "herkunft": "DM",
      "exportiert_von": "Datenmonster", "festschreibung": False,
      "waehrung": "EUR", "buchungstyp": 1,
    }
    """
    cfg = config or {}

    def _c(key, default=""):
        v = cfg.get(key)
        return default if v is None or str(v).strip() == "" else str(v).strip()

    def _aus_spalte(name: str) -> str:
        """Erster Wert einer Spalte - die Zeitraumgrenzen kommen aus der Abfrage."""
        if name not in df.columns or df.empty:
            return ""
        return _datev_text(df[name].iloc[0])

    def _stamm(name: str, default: str = "") -> str:
        """Mandanten-Stammdatum: die Spalte schlaegt die Konfiguration.

        ⭐ Die Reihenfolge ist der Kern der Mandantenfaehigkeit. In der
        target_options-Konfiguration steht, was beim INSTALLIEREN galt - unter dem
        Mandanten-Umschalter ist das die Kennung des falschen Betriebs. Die Spalte
        dagegen kommt aus business_config des gerade aktiven Mandanten und reist
        mit den Zahlen mit, zu denen sie gehoert. Deshalb gewinnt sie.
        """
        return _aus_spalte(name) or _c(name, default)

    jetzt = datetime.now().strftime("%Y%m%d%H%M%S") + "000"
    # Der ausgewertete Zeitraum steht nicht in der Konfiguration, sondern im
    # Formular - die Abfrage reicht ihn deshalb als Spalte mit. DATEV braucht ihn
    # in der Kopfzeile; leer bleiben darf er nicht.
    von = _c("datum_von") or _aus_spalte("zeitraum_von")
    bis = _c("datum_bis") or _aus_spalte("zeitraum_bis")
    wj = _stamm("wj_beginn") or (von[:4] + "0101" if len(von) >= 4 else "")

    # Kopfzeile: 31 Felder. Die Positionen sind fix – siehe DATEV-Beispieldatei.
    kopf = [""] * 31
    kopf[0] = '"EXTF"'
    kopf[1] = "700"                                   # Formatversion
    kopf[2] = "21"                                    # Kategorie Buchungsstapel
    kopf[3] = '"Buchungsstapel"'
    kopf[4] = "13"                                    # Version der Kategorie
    kopf[5] = jetzt                                   # erzeugt am
    kopf[7] = '"%s"' % _datev_text(_c("herkunft", "DM"))[:2]
    kopf[8] = '"%s"' % _datev_text(_c("exportiert_von", "Datenmonster"))
    # Ohne Kennung ist der Stapel wertlos: DATEV weist ihn beim Einlesen ab, und
    # zwar erst beim Steuerberater. Lieber hier abbrechen mit einem Satz, der
    # sagt, wo man es einträgt.
    berater, mandant = _stamm("berater"), _stamm("mandant")
    if not berater or not mandant:
        offen = [n for n, v in (("Beraternummer", berater),
                                ("Mandantennummer", mandant)) if not v]
        raise ValueError(
            f"{' und '.join(offen)} {'fehlen' if len(offen) > 1 else 'fehlt'} – "
            "DATEV weist den Buchungsstapel ohne sie ab. "
            "Einzutragen im Reiter „DATEV-Stammdaten“ (gilt je Mandant).")

    kopf[10] = berater
    kopf[11] = mandant
    kopf[12] = wj
    kopf[13] = _stamm("sachkontenlaenge", "4")
    kopf[14] = von
    kopf[15] = bis
    # Bezeichnung um den Zeitraum ergaenzen, damit der Stapel im DATEV-Bestand
    # unterscheidbar ist ("Eingangsrechnungen 01/2026" statt zwoelfmal gleich).
    bezeichnung = _c("bezeichnung")
    if bis and len(bis) >= 6 and bezeichnung and bis[4:6] not in bezeichnung:
        bezeichnung = f"{bezeichnung} {bis[4:6]}/{bis[:4]}"
    kopf[16] = '"%s"' % _datev_text(bezeichnung)
    kopf[18] = _c("buchungstyp", "1")                 # 1 = Finanzbuchführung
    kopf[20] = "1" if str(cfg.get("festschreibung") or "").lower() in ("1", "true", "ja") else "0"
    kopf[21] = '"%s"' % _c("waehrung", "EUR")

    zeilen: List[str] = [";".join(kopf), ";".join(DATEV_SPALTEN)]

    for _, row in df.iterrows():
        felder = [""] * len(DATEV_SPALTEN)
        for quelle, pos in _DATEV_FELDER.items():
            if quelle not in df.columns:
                continue
            wert = row.get(quelle)
            if quelle in ("umsatz", "skonto"):
                text = _datev_betrag(wert)
            else:
                text = _datev_text(wert)
            if text == "":
                continue
            felder[pos - 1] = '"%s"' % text if pos in _DATEV_TEXTFELDER else text
        # Ohne Betrag ist die Zeile keine Buchung – DATEV wiese sie zurück.
        if not felder[0]:
            continue
        zeilen.append(";".join(felder))

    # errors="replace": ein einzelnes exotisches Zeichen in einem Buchungstext
    # darf nicht den ganzen Monatsexport verhindern.
    return ("\r\n".join(zeilen) + "\r\n").encode("cp1252", errors="replace")


def export_datev_kompakt(df: pd.DataFrame, config: Optional[dict] = None) -> bytes:
    """Das schlanke Format des bisherigen Access-Werkzeugs (Reporting Tool v1.2).

    Acht Spalten mit Kopfzeile, ';'-getrennt – so, wie der Steuerberater es seit
    Jahren bekommt. Bewusst erhalten, damit der Umstieg auf das offizielle
    Format nicht erzwungen ist und beide Wege vergleichbar bleiben.

    Kopfzeile: Betrag;Gegenkonto;Belegfeld;Belegfeld2;Datum;Konto;Lieferant UST;Eigene UST
    Das Datum steht hier als TTMMJJ (im offiziellen Format dagegen TTMM).
    """
    cfg = config or {}
    eigene_ustid = _datev_text(cfg.get("eigene_ustid"))
    kopf = ("Betrag;Gegenkonto;Belegfeld;Belegfeld2;Datum;Konto;"
            "Lieferant UST;Eigene UST")
    zeilen: List[str] = [kopf]
    for _, row in df.iterrows():
        betrag = _datev_betrag(row.get("umsatz"))
        if betrag == "":
            continue
        # Im Altformat trägt der Betrag das Vorzeichen, es gibt kein S/H-Feld.
        if _datev_text(row.get("vorzeichen_negativ")) in ("1", "True", "true"):
            betrag = "-" + betrag
        zeilen.append(";".join([
            betrag,
            _datev_text(row.get("gegenkonto")),
            _datev_text(row.get("belegfeld1")),
            _datev_text(row.get("belegfeld2_kompakt")) or _datev_text(row.get("belegfeld2")),
            _datev_text(row.get("datum_kompakt")) or _datev_text(row.get("belegdatum")),
            _datev_text(row.get("konto")),
            # Im Altformat steht die USt-IdNr. des Lieferanten IMMER, nicht nur
            # beim EU-Erwerb – deshalb eine eigene Spalte mit Rückfall auf die,
            # die das offizielle Format nur bei EU-Fällen führt.
            _datev_text(row.get("partner_ustid")) or _datev_text(row.get("eu_ustid")),
            _datev_text(row.get("eigene_ustid")) or eigene_ustid,
        ]))
    return ("\r\n".join(zeilen) + "\r\n").encode("cp1252", errors="replace")


# ─── XLSX ─────────────────────────────────────────────────────────────────────

def export_xlsx(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Export")
        ws = writer.sheets["Export"]
        # Auto-fit column widths
        for col_cells in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 50)
    return buf.getvalue()


# ─── JSON ─────────────────────────────────────────────────────────────────────

def export_json(df: pd.DataFrame, orient: str = "records", indent: int = 2) -> bytes:
    data = json.loads(df.to_json(orient=orient, force_ascii=False))
    return json.dumps(data, ensure_ascii=False, indent=indent).encode("utf-8")


# ─── XML (template-basiert) ───────────────────────────────────────────────────

def export_xml(df: pd.DataFrame, template: dict) -> bytes:
    """
    Renders XML from a tree template (new node-based format).
    template = { tree: { id, tag, attributes, children, fieldBinding, staticValue, isRepeating } }
    Falls back to simple flat format if no tree is present.
    """
    tree = template.get("tree")
    if not tree:
        return _export_xml_flat(df, template)

    records = df.to_dict(orient="records")

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def render_node(node, row):
        tag = node.get("tag", "element")
        children = node.get("children", [])
        field_binding = node.get("fieldBinding")
        static_value = node.get("staticValue")

        attr_str = ""
        for a in node.get("attributes", []):
            val = str(row.get(a["fieldBinding"], "") or "") if a.get("fieldBinding") else str(a.get("staticValue", "") or "")
            attr_str += f' {a["name"]}="{esc(val)}"'

        if children:
            inner = "".join(render_node(c, row) for c in children)
            return f"<{tag}{attr_str}>{inner}</{tag}>"
        elif field_binding:
            return f"<{tag}{attr_str}>{esc(str(row.get(field_binding, '') or ''))}</{tag}>"
        elif static_value is not None:
            return f"<{tag}{attr_str}>{esc(str(static_value))}</{tag}>"
        else:
            return f"<{tag}{attr_str}/>"

    def find_repeating(node):
        if node.get("isRepeating"):
            return node
        for c in node.get("children", []):
            found = find_repeating(c)
            if found:
                return found
        return None

    repeating = find_repeating(tree)
    row_tag_id = repeating["id"] if repeating else None

    if repeating and row_tag_id != tree["id"]:
        row_xmls = [render_node(repeating, row) for row in records]
        rows_joined = "\n  ".join(row_xmls)

        def build_outer(node):
            tag = node.get("tag", "element")
            attr_str = ""
            for a in node.get("attributes", []):
                val = str(a.get("staticValue", "") or "")
                attr_str += f' {a["name"]}="{esc(val)}"'
            if node["id"] == row_tag_id:
                return rows_joined
            children = node.get("children", [])
            if children:
                inner = "\n  ".join(build_outer(c) for c in children)
                return f"<{tag}{attr_str}>\n  {inner}\n</{tag}>"
            return f"<{tag}{attr_str}/>"

        body = build_outer(tree)
    else:
        row_xmls = [render_node(tree, row) for row in records]
        body = "\n".join(row_xmls)

    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n{body}'
    try:
        from xml.dom import minidom
        pretty = minidom.parseString(xml_str.encode("utf-8")).toprettyxml(indent="  ")
        # Fix double XML declaration
        pretty_lines = pretty.split("\n")
        if pretty_lines[0].startswith("<?xml") and pretty_lines[1].startswith("<?xml"):
            pretty_lines = pretty_lines[1:]
        return "\n".join(pretty_lines).encode("utf-8")
    except Exception:
        return xml_str.encode("utf-8")


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _indent_xml(xml_str: str) -> str:
    try:
        from xml.dom import minidom
        return minidom.parseString(xml_str.encode("utf-8")).toprettyxml(indent="  ")
    except Exception:
        return xml_str


def _export_xml_flat(df: pd.DataFrame, template: dict) -> bytes:
    """Legacy flat XML export."""
    root_tag = template.get("root", "root")
    row_tag = template.get("row", "row")
    fields_cfg = template.get("fields", [])

    root_el = ET.Element(root_tag)
    for _, record in df.iterrows():
        row_el = ET.SubElement(root_el, row_tag)
        sub_elements: Dict[str, ET.Element] = {}
        for fc in fields_cfg:
            src_field = fc.get("field")
            xml_path = fc.get("xmlPath", src_field)
            is_attr = fc.get("isAttribute", False)
            val = str(record.get(src_field, "") or "")
            if not xml_path:
                continue
            if is_attr:
                if "/@" in xml_path:
                    elem_name, attr_name = xml_path.split("/@", 1)
                    if elem_name not in sub_elements:
                        sub_elements[elem_name] = ET.SubElement(row_el, elem_name)
                    sub_elements[elem_name].set(attr_name, val)
                elif xml_path.startswith("@"):
                    row_el.set(xml_path[1:], val)
                else:
                    row_el.set(xml_path, val)
            else:
                parts = xml_path.split("/")
                parent = row_el
                for part in parts[:-1]:
                    if part not in sub_elements:
                        sub_elements[part] = ET.SubElement(parent, part)
                    parent = sub_elements[part]
                child = ET.SubElement(parent, parts[-1])
                child.text = val

    raw = ET.tostring(root_el, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    pretty_lines = pretty.split("\n")
    if pretty_lines[0].startswith("<?xml"):
        pretty_lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    return "\n".join(pretty_lines).encode("utf-8")


# ─── DB Write ─────────────────────────────────────────────────────────────────

def export_to_db(
    df: pd.DataFrame,
    conn_obj,
    table: str,
    write_mode: str,
    key_columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from sqlalchemy import create_engine, text, inspect
    from app.services.db_service import get_engine_str
    import logging
    log = logging.getLogger(__name__)

    rows_affected = 0

    # Sicherheitsgurt (vor Verbindungsaufbau): Modi, die zeilenweise über Schlüssel
    # arbeiten, dürfen ohne key_columns nicht laufen – sonst würde DELETE/UPDATE die
    # ganze Tabelle treffen bzw. ins Leere greifen. Fail-fast als klarer ValueError,
    # nicht als getarnter DB-Export-Fehler.
    if write_mode in ("update", "upsert", "delete") and not key_columns:
        raise ValueError(
            f"Schreibmodus '{write_mode}' benötigt Schlüsselspalten (key_columns), "
            f"sonst würde ohne Filter geschrieben/gelöscht.")

    try:
        connect_args = {}
        if conn_obj.db_type == "mssql":
            connect_args = {"timeout": 30, "login_timeout": 10}
        elif conn_obj.db_type in ("mysql", "postgresql"):
            connect_args = {"connect_timeout": 10}

        engine = create_engine(get_engine_str(conn_obj), connect_args=connect_args)
        log.info(f"export_to_db: engine={engine.url}, table={table}, mode={write_mode}, rows={len(df)}, cols={list(df.columns)}")

        # Spalten gegen Zieltabelle abgleichen
        try:
            # Schema-Namen trennen: "dbo.Tabelle" → schema="dbo", table_name="Tabelle"
            schema, tname = (table.split(".", 1) + [None])[:2]
            if tname is None:
                schema, tname = None, schema
            insp = inspect(engine)
            db_cols = {c["name"] for c in insp.get_columns(tname, schema=schema)}
            log.info(f"export_to_db: DB-Spalten={db_cols}")
            common_cols = [c for c in df.columns if c in db_cols]
            log.info(f"export_to_db: gemeinsame Spalten={common_cols}")
            if not common_cols:
                raise ValueError(f"Keine übereinstimmenden Spalten. DataFrame: {list(df.columns)}, Tabelle: {db_cols}")
            df = df[common_cols]
        except ValueError:
            raise
        except Exception as col_err:
            log.warning(f"export_to_db: Spalten-Abgleich fehlgeschlagen ({col_err}), verwende alle DataFrame-Spalten")

        with engine.begin() as con:
            if write_mode == "truncate_insert":
                con.execute(text(f"DELETE FROM {table}"))

            if write_mode in ("insert", "truncate_insert"):
                if conn_obj.db_type == "mssql":
                    # Direktes INSERT via parameterisiertes SQL – kein to_sql
                    cols = list(df.columns)
                    col_list = ", ".join(f"[{c}]" for c in cols)
                    param_list = ", ".join(f":{c}" for c in cols)
                    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({param_list})")
                    records = df.where(df.notna(), other=None).to_dict(orient="records")
                    for chunk_start in range(0, len(records), 500):
                        chunk = records[chunk_start:chunk_start + 500]
                        con.execute(sql, chunk)
                    rows_affected = len(df)
                else:
                    df.to_sql(table, con=con, if_exists="append", index=False,
                              method="multi", chunksize=200)
                    rows_affected = len(df)

            elif write_mode in ("update", "upsert") and key_columns:
                insp2 = inspect(engine)
                schema2, tname2 = (table.split(".", 1) + [None])[:2]
                if tname2 is None: schema2, tname2 = None, schema2
                db_cols2 = [c["name"] for c in insp2.get_columns(tname2, schema=schema2)]
                non_key_cols = [c for c in df.columns if c in db_cols2 and c not in key_columns]

                for _, row in df.iterrows():
                    row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
                    where_clause = " AND ".join([f"[{k}] = :{k}" for k in key_columns])

                    if write_mode == "update":
                        set_clause = ", ".join([f"[{c}] = :set_{c}" for c in non_key_cols])
                        params = {f"set_{c}": row_dict.get(c) for c in non_key_cols}
                        params.update({k: row_dict.get(k) for k in key_columns})
                        result = con.execute(text(f"UPDATE {table} SET {set_clause} WHERE {where_clause}"), params)
                        rows_affected += result.rowcount
                    elif write_mode == "upsert":
                        check_params = {k: row_dict.get(k) for k in key_columns}
                        exists = con.execute(text(f"SELECT 1 FROM {table} WHERE {where_clause}"), check_params).fetchone()
                        if exists:
                            if non_key_cols:
                                set_clause = ", ".join([f"[{c}] = :set_{c}" for c in non_key_cols])
                                params = {f"set_{c}": row_dict.get(c) for c in non_key_cols}
                                params.update(check_params)
                                con.execute(text(f"UPDATE {table} SET {set_clause} WHERE {where_clause}"), params)
                        else:
                            col_list = ", ".join(f"[{k}]" for k in row_dict)
                            val_list = ", ".join(f":{k}" for k in row_dict)
                            con.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({val_list})"), row_dict)
                        rows_affected += 1

            elif write_mode == "delete":
                # Löscht je DataFrame-Zeile die Treffer über die Schlüsselspalten.
                # key_columns ist durch den Sicherheitsgurt oben garantiert.
                for _, row in df.iterrows():
                    row_dict = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
                    where_clause = " AND ".join([f"[{k}] = :{k}" for k in key_columns])
                    params = {k: row_dict.get(k) for k in key_columns}
                    result = con.execute(text(f"DELETE FROM {table} WHERE {where_clause}"), params)
                    rows_affected += result.rowcount
            else:
                raise ValueError(f"Unbekannter write_mode oder fehlende key_columns: {write_mode}")

        log.info(f"export_to_db: ✓ {rows_affected} Zeilen geschrieben")

    except Exception as e:
        log.error(f"export_to_db: FEHLER: {e}")
        raise RuntimeError(f"DB-Export fehlgeschlagen ({table}): {str(e)[:800]}")

    return {"rows_affected": rows_affected, "mode": write_mode, "table": table, "errors": []}

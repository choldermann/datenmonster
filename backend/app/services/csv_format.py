"""
CSV lesen und schreiben – an EINER Stelle.

Vorher hatte jeder Weg (Datei-Upload, FTP, Mail-Anhang, FTP-Upload, Mapping-Ziel)
seine eigene Variante: FTP las nur UTF-8 (Umlaute aus Windows-Dateien wurden zu „�“),
der Upload übersprang Zeilen nur im Notfallzweig, der Export brach bei Zeichen ab,
die es in ANSI nicht gibt, und deutsche Zahlen („1.234,56“) blieben Text.
"""
import csv
import io
import re
from typing import Optional

import pandas as pd

# Reihenfolge zählt: UTF-8 ist streng (schlägt bei ANSI-Umlauten sicher fehl),
# cp1252 deckt Windows ab, latin-1 nimmt jedes Byte und ist nur noch Netz.
KODIERUNGEN = ("utf-8-sig", "cp1252", "latin-1")

_GANZZAHL = re.compile(r"^[+-]?\d+$")
_FUEHRENDE_NULL = re.compile(r"^[+-]?0\d")
# 1234 | 1234,5 | 1.234 | 1.234,56 – aber kein Datum wie 01.02.2026
_DEUTSCHE_ZAHL = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")


def text_dekodieren(data: bytes, encoding: Optional[str] = None) -> str:
    """Bytes → Text. Ohne Vorgabe wird UTF-8, dann Windows-1252 probiert."""
    if encoding:
        return data.decode(encoding, errors="replace")
    for enc in KODIERUNGEN:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def trennzeichen_erkennen(text: str) -> str:
    probe = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(probe, delimiters=";,\t|").delimiter
    except csv.Error:
        kopf = probe.splitlines()[0] if probe else ""
        return max(";,\t|", key=kopf.count) if kopf else ","


def _deutsche_zahlen(df: pd.DataFrame) -> pd.DataFrame:
    """Spalten, deren Werte ALLE wie deutsche Zahlen aussehen, werden Zahlen.
    Alles andere (Text, Datum, gemischte Spalten) bleibt unverändert Text."""
    for col in df.columns:
        s = df[col]
        werte = s.dropna().astype(str).str.strip()
        werte = werte[werte != ""]
        if werte.empty:
            continue
        # „0815“, „01234“: Artikelnummern/PLZ – die führende Null muss bleiben
        if werte.str.match(_FUEHRENDE_NULL).any():
            continue
        if werte.str.match(_GANZZAHL).all():
            df[col] = pd.to_numeric(s.str.strip(), errors="coerce")
        elif werte.str.match(_DEUTSCHE_ZAHL).all():
            norm = s.str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(norm, errors="coerce")
    return df


def csv_lesen(data: bytes, sep: Optional[str] = None, skip_rows: int = 0,
              decimal: str = ".", encoding: Optional[str] = None,
              header: bool = True) -> pd.DataFrame:
    """
    sep:      Trennzeichen; None oder "auto" = erkennen
    skip_rows: so viele Zeilen VOR der Kopfzeile überspringen
    decimal:  "." (wie bisher) oder "," (deutsche Zahlen: 1.234,56 → 1234.56)
    encoding: None = automatisch (UTF-8, sonst Windows-1252)
    """
    text = text_dekodieren(data, encoding)
    if text.startswith("﻿"):
        text = text[1:]
    if skip_rows:
        text = "\n".join(text.splitlines()[skip_rows:])
    if not sep or sep == "auto":
        sep = trennzeichen_erkennen(text)
    kopf = {} if header else {"header": None}
    if decimal == ",":
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, low_memory=False, **kopf)
        df = _deutsche_zahlen(df)
    else:
        df = pd.read_csv(io.StringIO(text), sep=sep, low_memory=False, **kopf)
    if not header:
        # Ohne Kopfzeile heißen die Spalten Spalte_1, Spalte_2, …
        df.columns = [f"Spalte_{i + 1}" for i in range(len(df.columns))]
    return df


ANFUEHRUNG = {
    "minimal": csv.QUOTE_MINIMAL,      # nur wo nötig (Trenner/Zeilenumbruch im Text)
    "alle": csv.QUOTE_ALL,             # jedes Feld in "…"
    "text": csv.QUOTE_NONNUMERIC,      # Text in "…", Zahlen ohne
}
ZEILENENDE = {"crlf": "\r\n", "lf": "\n"}


def csv_schreiben(df: pd.DataFrame, delimiter: str = ";", encoding: str = "utf-8-sig",
                  decimal: str = ".", quote: str = "minimal", header: bool = True,
                  line_ending: str = "lf", date_format: Optional[str] = None) -> bytes:
    """Zeichen, die es in der Zielkodierung nicht gibt (z.B. „→“ in ANSI), werden
    zu „?“ statt den ganzen Export abzubrechen.

    quote:       minimal | alle | text
    header:      Kopfzeile schreiben
    line_ending: lf | crlf (Windows-Programme, ältere Importe)
    date_format: strftime-Muster für Datumsspalten, z.B. "%d.%m.%Y"
    """
    if date_format:
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime(date_format)
    if quote == "text" and (decimal or ".") != ".":
        # pandas macht aus Zahlen mit Dezimalkomma vorher Text und setzt sie dann
        # mit in "…" – hier also selbst schreiben: Text in "…", Zahlen ohne.
        return _text_in_anfuehrung(df, delimiter or ";", decimal, header,
                                   ZEILENENDE.get(line_ending or "lf", "\n")
                                   ).encode(encoding or "utf-8-sig", errors="replace")
    buf = io.StringIO()
    df.to_csv(buf, index=False, sep=delimiter or ";", decimal=decimal or ".",
              quoting=ANFUEHRUNG.get(quote or "minimal", csv.QUOTE_MINIMAL),
              header=bool(header) if header is not None else True,
              lineterminator=ZEILENENDE.get(line_ending or "lf", "\n"))
    return buf.getvalue().encode(encoding or "utf-8-sig", errors="replace")


def _text_in_anfuehrung(df: pd.DataFrame, sep: str, decimal: str, header, nl: str) -> str:
    def feld(v) -> str:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
            return ""
        if isinstance(v, bool):
            return '"' + str(v) + '"'
        if isinstance(v, (int, float)) or pd.api.types.is_number(v):
            return str(v).replace(".", decimal)
        return '"' + str(v).replace('"', '""') + '"'

    zeilen = []
    if header is not False:
        zeilen.append(sep.join(feld(str(c)) for c in df.columns))
    for row in df.itertuples(index=False, name=None):
        zeilen.append(sep.join(feld(v) for v in row))
    return nl.join(zeilen) + nl


def csv_optionen(opts: dict, vorgabe_trenner: str = ";", vorgabe_kodierung: str = "utf-8-sig") -> dict:
    """Optionen aus einer Ziel-/Knoten-Konfiguration für csv_schreiben."""
    opts = opts or {}
    return {
        "delimiter": opts.get("delimiter") or vorgabe_trenner,
        "encoding": opts.get("encoding") or vorgabe_kodierung,
        "decimal": opts.get("decimal") or ".",
        "quote": opts.get("quote") or "minimal",
        "header": opts.get("header", True) is not False,
        "line_ending": opts.get("line_ending") or "lf",
        "date_format": opts.get("date_format") or None,
    }

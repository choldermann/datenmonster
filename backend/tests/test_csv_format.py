"""CSV/XML lesen und schreiben – Umlaute, Zeilen überspringen, deutsche Zahlen,
Export ohne Abbruch, XML vom FTP mit Zielknoten."""
import os
import tempfile

import pandas as pd

from app.services.csv_format import csv_lesen
from app.services.export_service import export_csv
from app.services.file_service import parse_file
from app.services.ftp_service import parse_bytes

ANSI = "Name;Ort;Preis\nMüller;Köln;1.234,56\nSträßle;Göttingen;12,50\n".encode("cp1252")
VORSPANN = "Export vom 12.11.2026\nLeerzeile\nArtNr;Menge;Datum\n0815;3;01.02.2026\n4711;1.000;05.03.2026\n".encode()


def test_ftp_liest_windows_umlaute():
    df = parse_bytes(ANSI, "x.csv", "csv", ";", 0)
    assert df.iloc[0].tolist()[:2] == ["Müller", "Köln"]
    assert df.iloc[1]["Name"] == "Sträßle"


def test_dezimalkomma_wird_zahl():
    df = parse_bytes(ANSI, "x.csv", "csv", ";", 0, csv_decimal=",")
    assert df["Preis"].tolist() == [1234.56, 12.5]
    assert df["Preis"].dtype == "float64"


def test_ohne_dezimalkomma_bleibt_alles_wie_bisher():
    df = parse_bytes(ANSI, "x.csv", "csv", ";", 0)
    assert df["Preis"].tolist() == ["1.234,56", "12,50"]


def test_zeilen_ueberspringen_beim_upload():
    p = tempfile.mktemp(suffix=".csv")
    with open(p, "wb") as f:
        f.write(VORSPANN)
    try:
        df = parse_file(p, "csv", csv_delimiter=";", skip_rows=2)
    finally:
        os.remove(p)
    assert list(df.columns) == ["ArtNr", "Menge", "Datum"]


def test_fuehrende_null_und_datum_bleiben_text():
    df = csv_lesen(VORSPANN, sep=";", skip_rows=2, decimal=",")
    assert df["ArtNr"].tolist() == ["0815", "4711"]
    assert df["Menge"].tolist() == [3, 1000]
    assert df["Datum"].tolist() == ["01.02.2026", "05.03.2026"]


def test_gemischte_spalte_bleibt_text():
    df = csv_lesen("a;b\n1,5;x\nabc;y\n".encode(), sep=";", decimal=",")
    assert df["a"].tolist() == ["1,5", "abc"]


def test_trennzeichen_wird_erkannt():
    assert list(csv_lesen(ANSI, sep="auto").columns) == ["Name", "Ort", "Preis"]


def test_export_ansi_bricht_nicht_ab_und_schreibt_dezimalkomma():
    d = pd.DataFrame({"Text": ["A → B", "Größe"], "Preis": [1234.5, 0.99], "Menge": [3, 4]})
    zeilen = export_csv(d, ";", "cp1252", decimal=",").decode("cp1252").splitlines()
    assert zeilen == ["Text;Preis;Menge", "A ? B;1234,5;3", "Größe;0,99;4"]


XML = ("<Auftraege><Auftrag nr='1'><Kunde><Name>Müller</Name></Kunde><Summe>10</Summe></Auftrag>"
       "<Auftrag nr='2'><Kunde><Name>Ko</Name></Kunde><Summe>5</Summe></Auftrag></Auftraege>").encode()


def test_xml_vom_ftp_liest_verschachtelte_felder():
    df = parse_bytes(XML, "a.xml", "xml")
    assert df["Kunde.Name"].tolist() == ["Müller", "Ko"]
    assert df["@nr"].tolist() == ["1", "2"]


def test_xml_vom_ftp_mit_zielknoten():
    df = parse_bytes(XML, "a.xml", "xml", xml_target_node="Auftrag")
    assert df["Summe"].tolist() == ["10", "5"]

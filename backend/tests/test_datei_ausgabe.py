"""Datei-Ziele: Dateiname mit Platzhaltern, eine Datei je Gruppe, zusätzliche
Ablage (nur Quellen desselben Projekts) und Excel-Blatt wählen."""
import io
import os
import re

import pandas as pd
import pytest

from app.core.database import SessionLocal
from app.models.export_file import ExportFile
from app.models.ftp_source import FtpSource
from app.services.csv_format import excel_blaetter, excel_lesen
from app.services.dateiname import dateiname_bauen
from app.services.file_export_service import save_export_file

DF = pd.DataFrame({"Lieferant": ["Müller GmbH", "Abc", "Müller GmbH", None],
                   "ArtNr": ["0815", "1", "2", "3"], "Menge": [1, 2, 3, 4]})


def test_dateiname_platzhalter():
    n = dateiname_bauen("{ziel}_{Lieferant}_{datum}", {"ziel": "Bestellung"}, {"Lieferant": "Müller/GmbH"}, "csv")
    assert re.fullmatch(r"Bestellung_Müller_GmbH_\d{8}\.csv", n)
    boese = dateiname_bauen("../../etc/{unbekannt}", {}, {}, "csv")
    assert "/" not in boese and not boese.startswith(".") and "{unbekannt}" in boese


@pytest.fixture
def lauf(tmp_path, monkeypatch):
    monkeypatch.setenv("AUSTAUSCH_BASIS", str(tmp_path))
    db = SessionLocal()
    vorher = {e.id for e in db.query(ExportFile).all()}
    angelegt = []

    def quelle(projekt):
        q = FtpSource(name="__test_ablage", protocol="ordner", host="", username="", password="",
                      remote_dir="/", project_id=projekt)
        db.add(q); db.commit(); db.refresh(q); angelegt.append(q.id)
        return q

    def speichern(**opts):
        return save_export_file(DF, user_id=1, project_id=4, project_name="__test_projekt", job_id=None,
                                mapping_id=None, mapping_name="__test_mapping", target_name="Bestellung",
                                target_type="csv", target_options={"encoding": "utf-8", **opts}, db=db)

    yield {"db": db, "quelle": quelle, "speichern": speichern, "basis": tmp_path}

    for e in db.query(ExportFile).all():
        if e.id not in vorher and e.project_name == "__test_projekt":
            try:
                os.remove(e.file_path)
            except OSError:
                pass
            db.delete(e)
    for qid in angelegt:
        q = db.get(FtpSource, qid)
        if q:
            db.delete(q)
    db.commit()
    db.close()


def test_eine_datei_je_gruppe_mit_ablage(lauf):
    q = lauf["quelle"](4)
    r = lauf["speichern"](gruppe_nach="Lieferant", dateiname="best_{Lieferant}",
                          ablage_quelle_id=q.id, ablage_verzeichnis="/ausgang")
    namen = sorted(d["file_name"] for d in r["dateien"])
    assert namen == ["best_Abc.csv", "best_Müller_GmbH.csv", "best_leer.csv"]
    zeilen = {d["file_name"]: d["zeilen"] for d in r["dateien"]}
    assert zeilen["best_Müller_GmbH.csv"] == 2
    abgelegt = sorted(os.listdir(lauf["basis"] / "ausgang"))
    assert abgelegt == namen
    inhalt = (lauf["basis"] / "ausgang" / "best_Müller_GmbH.csv").read_text("utf-8")
    assert inhalt.splitlines() == ["Lieferant;ArtNr;Menge", "Müller GmbH;0815;1", "Müller GmbH;2;3"]


def test_gleicher_name_ueberschreibt_lokal_nicht(lauf):
    r = lauf["speichern"](dateiname="fest")
    r2 = lauf["speichern"](dateiname="fest")
    assert r["file_path"] != r2["file_path"] and r2["file_name"] == "fest_2.csv"


def test_ablage_aus_fremdem_projekt_wird_abgelehnt(lauf):
    q = lauf["quelle"](3)
    with pytest.raises(ValueError, match="anderen Projekt"):
        lauf["speichern"](ablage_quelle_id=q.id)


def test_unbekannte_gruppenspalte(lauf):
    with pytest.raises(ValueError, match="gibt es in der Ausgabe nicht"):
        lauf["speichern"](gruppe_nach="Gibtsnicht")


def _mappe():
    b = io.BytesIO()
    with pd.ExcelWriter(b) as w:
        pd.DataFrame({"a": [1]}).to_excel(w, sheet_name="Info", index=False)
        pd.DataFrame({"ArtNr": ["0815"], "Preis": [1.5]}).to_excel(w, sheet_name="Preise", index=False)
    b.seek(0)
    return b


def test_excel_blatt_nach_name_und_nummer():
    assert excel_blaetter(_mappe()) == ["Info", "Preise"]
    assert list(excel_lesen(_mappe(), blatt="Preise").columns) == ["ArtNr", "Preis"]
    assert list(excel_lesen(_mappe(), blatt="2").columns) == ["ArtNr", "Preis"]
    assert list(excel_lesen(_mappe()).columns) == ["a"]
    with pytest.raises(ValueError, match="vorhanden: Info, Preise"):
        excel_lesen(_mappe(), blatt="Gibtsnicht")

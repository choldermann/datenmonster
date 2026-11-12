"""Datei-Regeln (Dispatcher): Mapping liest die eingegangene Datei, Nach-Aktionen
wirken, Regeln ohne Quelle greifen im eigenen Projekt – und nur dort.

Legt Testobjekte in der echten DB an und räumt sie per ID wieder ab
(nie per Name, siehe Projektregel).
"""
import os
import shutil

import pandas as pd
import pytest

from app.core.database import SessionLocal
from app.models.dataset import Dataset
from app.models.dispatcher import DispatcherRule
from app.models.export_file import ExportFile
from app.models.ftp_source import FtpSource
from app.models.mapping import Mapping
from app.services import dispatcher_service as D
from app.services.file_service import dataframe_to_storage

PROJEKT = 4
FREMDES_PROJEKT = 3
NEU = pd.DataFrame({"ArtNr": ["NEU1", "NEU2"], "Menge": [5, 7]})
ROH = b"ArtNr;Menge\nNEU1;5\nNEU2;7\n"


@pytest.fixture
def welt(tmp_path, monkeypatch):
    monkeypatch.setenv("AUSTAUSCH_BASIS", str(tmp_path))
    gesendet = []
    import app.services.email_service as E
    monkeypatch.setattr(E, "send_email", lambda **kw: gesendet.append(kw))

    db = SessionLocal()
    angelegt = []   # (Klasse, id)
    vorher = {e.id for e in db.query(ExportFile).all()}

    def neu(obj):
        db.add(obj); db.commit(); db.refresh(obj)
        angelegt.append((type(obj), obj.id))
        return obj

    alt = pd.DataFrame({"ArtNr": ["ALT"], "Menge": [1]})
    ds = neu(Dataset(name="__test_dispatcher_quelle", file_type="csv", row_count=1,
                     columns=list(alt.columns), xml_configured=1, project_id=PROJEKT))
    ds.file_path = dataframe_to_storage(alt, ds.id); db.commit()
    felder = [{"source_dataset_id": ds.id, "source_field": f, "target_field": f,
               "transformer": {"type": "direct", "source_field": f}} for f in ("ArtNr", "Menge")]
    m = neu(Mapping(name="__test_dispatcher_mapping", project_id=PROJEKT,
                    canvas_nodes=[{"id": f"ds_{ds.id}", "dataset_id": ds.id, "dataset_name": ds.name, "x": 0, "y": 0}],
                    fields=[], joins=[],
                    targets=[{"id": "t1", "name": "Test", "target_type": "csv", "fields": felder,
                              "target_options": {"delimiter": ";"}}]))
    src = neu(FtpSource(name="__test_dispatcher_ordner", protocol="ordner", host="", username="",
                        password="", remote_dir="/", project_id=PROJEKT))

    yield {"db": db, "ds": ds, "m": m, "src": src, "neu": neu, "mails": gesendet,
           "basis": tmp_path, "vorher": vorher}

    for e in db.query(ExportFile).all():
        if e.id not in vorher and e.mapping_id == m.id:
            try:
                os.remove(e.file_path)
            except OSError:
                pass
            db.delete(e)
    for cls, oid in reversed(angelegt):
        o = db.get(cls, oid)
        if o is not None:
            db.delete(o)
    db.commit()
    for ext in ("parquet", "json"):
        p = f"/app/uploads/dataset_{ds.id}.{ext}"
        if os.path.exists(p):
            os.remove(p)
    db.close()


def _exporte(w):
    return [e for e in w["db"].query(ExportFile).all()
            if e.id not in w["vorher"] and e.mapping_id == w["m"].id]


def _regel(w, **kw):
    werte = dict(name="__test_dispatcher_regel", ftp_source_id=w["src"].id, mapping_id=w["m"].id,
                 active=True, priority=0, condition_mode="AND", conditions=[],
                 post_actions=[], project_id=PROJEKT)
    werte.update(kw)
    return w["neu"](DispatcherRule(**werte))


def test_mapping_liest_die_eingegangene_datei(welt):
    r = D._run_mapping(welt["m"].id, NEU, welt["db"])
    assert r["rows"] == 2
    inhalt = open(_exporte(welt)[0].file_path, encoding="utf-8-sig").read().split()
    assert inhalt == ["ArtNr;Menge", "NEU1;5", "NEU2;7"]
    # Quelle bleibt, wie sie war; kein Wegwerf-Dataset
    assert pd.read_parquet(welt["ds"].file_path)["ArtNr"].tolist() == ["ALT"]
    assert welt["db"].query(Dataset).filter(Dataset.name.like("dispatcher_input_%")).count() == 0


def test_nach_aktionen(welt):
    _regel(welt, conditions=[{"type": "filename", "pattern": "bestand_*.csv"}], post_actions=[
        {"type": "ftp_upload", "ftp_source_id": welt["src"].id, "remote_dir": "/archiv", "filename": "kopie_{datei}"},
        {"type": "email", "to": "test@example.com", "subject": "{regel}: {zeilen} Zeilen"},
        {"type": "chain_mapping", "mapping_id": welt["m"].id},
        {"type": "ftp_upload", "ftp_source_id": None},
    ])
    res = D.run_dispatcher(welt["src"].id, "bestand_1.csv", NEU, ROH, welt["db"])
    status = [(x.get("action"), x["status"]) for x in res]
    assert status == [(None, "ok"), ("ftp_upload", "ok"), ("email", "ok"),
                      ("chain_mapping", "ok"), ("ftp_upload", "error")]
    assert (welt["basis"] / "archiv" / "kopie_bestand_1.csv").read_bytes() == ROH
    assert welt["mails"][0]["subject"] == "__test_dispatcher_regel: 2 Zeilen"
    assert len(_exporte(welt)) == 2          # Regel-Mapping + Folge-Mapping


def test_bedingung_passt_nicht(welt):
    _regel(welt, conditions=[{"type": "filename", "pattern": "bestand_*.csv"}])
    assert D.run_dispatcher(welt["src"].id, "andere.csv", NEU, ROH, welt["db"]) == []


def test_regel_ohne_quelle_gilt_im_eigenen_projekt(welt):
    _regel(welt, ftp_source_id=None)
    res = D.run_dispatcher(welt["src"].id, "x.csv", NEU, ROH, welt["db"])
    assert res and res[0]["status"] == "ok"


def test_regel_ohne_quelle_greift_nicht_im_fremden_projekt(welt):
    _regel(welt, ftp_source_id=None, project_id=FREMDES_PROJEKT)
    assert D.run_dispatcher(welt["src"].id, "x.csv", NEU, ROH, welt["db"]) == []

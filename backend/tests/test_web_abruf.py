"""Preisbeobachtung: Produktdaten aus Shopseiten, viele Seiten, Vergleich mit dem
letzten Abruf, Verlauf. Seiten kommen aus einem nachgebauten Netz (kein Internet)."""
import json
import os

import pandas as pd
import pytest

from app.plugins.builtin.web import abruf as abruf_modul
from app.plugins.builtin.web.html_reader import HtmlDocumentSource, tabelle_saeubern
from app.plugins.builtin.web.produktdaten import preis_zahl, produkte_aus_html
from app.services.web_abruf import vergleichen


def jsonld(obj):
    return f'<html><head><script type="application/ld+json">{json.dumps(obj)}</script></head><body></body></html>'


def produkt(name, preis, gtin, verf="https://schema.org/InStock"):
    return {"@context": "https://schema.org", "@type": "Product", "name": name, "gtin13": gtin,
            "sku": "S-" + gtin[-3:], "brand": {"@type": "Brand", "name": "Hygi"},
            "offers": {"@type": "Offer", "price": preis, "priceCurrency": "EUR", "availability": verf}}


# ─── Produktdaten ─────────────────────────────────────────────────────────────

def test_jsonld_produkt():
    z = produkte_aus_html(jsonld(produkt("Bettschutz", "12.90", "4012345678901")), "https://a.de/p/1")
    assert z[0]["name"] == "Bettschutz" and z[0]["preis"] == 12.9 and z[0]["gtin"] == "4012345678901"
    assert z[0]["verfuegbar"] == "lieferbar" and z[0]["marke"] == "Hygi" and z[0]["quelle_daten"] == "json-ld"


def test_jsonld_graph_und_aggregateoffer():
    html = jsonld({"@graph": [{"@type": "WebPage"}, {"@type": ["Product"], "name": "Set",
                   "offers": {"@type": "AggregateOffer", "lowPrice": 9.5, "highPrice": 20, "priceCurrency": "EUR"}}]})
    z = produkte_aus_html(html, "u")
    assert z[0]["preis"] == 9.5


def test_microdata_und_opengraph():
    micro = ('<div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Seife</span>'
             '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
             '<meta itemprop="price" content="2,49"><meta itemprop="priceCurrency" content="EUR"></div></div>')
    assert produkte_aus_html(micro, "u")[0]["preis"] == 2.49
    og = '<meta property="og:title" content="Tücher"><meta property="product:price:amount" content="1.234,50">'
    assert produkte_aus_html(og, "u")[0]["preis"] == 1234.5


def test_preis_zahl():
    assert preis_zahl("1.234,56 €") == 1234.56
    assert preis_zahl("1,234.56") == 1234.56
    assert preis_zahl("19.99") == 19.99
    assert preis_zahl("") is None


def test_tabelle_saeubern():
    df = pd.DataFrame([["Berlin\xa0[1]", 5]], columns=pd.MultiIndex.from_tuples([("Name", "Name"), ("Einw.", "1939[3]")]))
    t = tabelle_saeubern(df)
    assert list(t.columns) == ["Name", "Einw. 1939"] and t.iloc[0, 0] == "Berlin"


# ─── Viele Seiten ─────────────────────────────────────────────────────────────

NETZ = {}


@pytest.fixture
def netz(monkeypatch):
    NETZ.clear()
    aufrufe = []

    def holen(self, url):
        aufrufe.append(url)
        self.abrufe += 1
        if url not in NETZ:
            raise RuntimeError("404 Not Found")
        return NETZ[url]

    monkeypatch.setattr(abruf_modul.Abrufer, "holen", holen)
    return aufrufe


def test_blaettern_bis_leere_seite(netz):
    for i in (1, 2):
        NETZ[f"https://s.de/k?page={i}"] = jsonld({"@graph": [produkt(f"P{i}a", i, f"40000000000{i}1"),
                                                              produkt(f"P{i}b", i + 0.5, f"40000000000{i}2")]})
    NETZ["https://s.de/k?page=3"] = "<html></html>"
    df, info = HtmlDocumentSource().abrufen({"url": "https://s.de/k?page={seite}", "extract_type": "produkte"})
    assert df["name"].tolist() == ["P1a", "P1b", "P2a", "P2b"]
    assert netz == [f"https://s.de/k?page={i}" for i in (1, 2, 3)]


def test_detail_links_folgen_und_url_liste(netz):
    NETZ["https://s.de/liste"] = '<a class="p" href="/p/1">1</a><a class="p" href="/p/2">2</a>'
    NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", 1, "4000000000011"))
    NETZ["https://s.de/p/2"] = jsonld(produkt("Zwei", 2, "4000000000022"))
    NETZ["https://t.de/x"] = jsonld(produkt("Drei", 3, "4000000000033"))
    df, info = HtmlDocumentSource().abrufen({"url": "https://s.de/liste", "folge_links": "a.p",
                                             "urls": "https://t.de/x\nhttps://t.de/gibtsnicht",
                                             "extract_type": "produkte"})
    assert df["name"].tolist() == ["Eins", "Zwei", "Drei"]
    assert df["quelle_url"].tolist() == ["https://s.de/p/1", "https://s.de/p/2", "https://t.de/x"]
    assert len(info["fehler"]) == 1 and "gibtsnicht" in info["fehler"][0]


def test_robots_txt_wird_beachtet(monkeypatch):
    from urllib.robotparser import RobotFileParser
    rp = RobotFileParser(); rp.parse(["User-agent: *", "Disallow: /geheim"])
    monkeypatch.setattr(abruf_modul.Abrufer, "_robots_fuer", lambda self, url: rp)
    a = abruf_modul.Abrufer({}, robots_beachten=True)
    assert a.holen("https://s.de/geheim/1") is None
    assert a.uebersprungen and a.abrufe == 0


# ─── Vergleich ────────────────────────────────────────────────────────────────

def _stand(*zeilen):
    return pd.DataFrame([{"quelle_url": u, "name": n, "gtin": g, "preis": p} for u, n, g, p in zeilen])


def test_vergleich_neu_geaendert_gleich_weg():
    t1 = vergleichen(_stand(("u1", "A", "1", 10.0), ("u2", "B", "2", 20.0), ("u3", "C", "3", 5.0)), None, {}, "T1")
    assert set(t1["status"]) == {"neu"}
    t2 = vergleichen(_stand(("u1", "A", "1", 9.0), ("u2", "B", "2", 20.0), ("u4", "D", "4", 1.0)), t1, {}, "T2")
    s = dict(zip(t2["name"], t2["status"]))
    assert s == {"A": "geändert", "B": "gleich", "D": "neu", "C": "weg"}
    a = t2[t2["name"] == "A"].iloc[0]
    assert a["preis_vorher"] == 10.0 and a["aenderung"] == -1.0 and a["aenderung_prozent"] == -10.0


# ─── Ende zu Ende mit gespeichertem Dataset ───────────────────────────────────

def test_abruf_ausfuehren_mit_verlauf(netz):
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.services.web_abruf import abruf_ausfuehren
    from app.connectors.factory import get_connector

    db = SessionLocal()
    ds = Dataset(name="__test_web_abruf", file_type="doc_html", project_id=4, xml_configured=1,
                 row_count=0, columns=[], query_config={"urls": "https://s.de/p/1\nhttps://s.de/p/2",
                                                        "extract_type": "produkte", "verlauf": "ja",
                                                        "pause_ms": 0})
    db.add(ds); db.commit(); db.refresh(ds)
    try:
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", "10.00", "4000000000011"))
        NETZ["https://s.de/p/2"] = jsonld(produkt("Zwei", "20.00", "4000000000022"))
        abruf_ausfuehren(ds.id)
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", "8.50", "4000000000011"))
        r = abruf_ausfuehren(ds.id)
        assert r["status"] == {"geändert": 1, "gleich": 1}
        df = get_connector(ds.id).fetch_full()      # liest den gespeicherten Stand
        assert len(df) == 4 and df["abgerufen_am"].nunique() <= 2
        letzte = df[df["status"] == "geändert"].iloc[0]
        assert letzte["preis"] == 8.5 and letzte["aenderung_prozent"] == -15.0
        db.refresh(ds)
        assert ds.last_refresh_status == "success"
    finally:
        pfad = ds.file_path
        db.delete(db.get(Dataset, ds.id)); db.commit(); db.close()
        if pfad and os.path.exists(pfad):
            os.remove(pfad)


def test_preis_als_text_wird_verglichen():
    t1 = vergleichen(pd.DataFrame([{"quelle_url": "u", "name": "A", "preis": "£51.77"}]), None, {}, "T1")
    t2 = vergleichen(pd.DataFrame([{"quelle_url": "u", "name": "A", "preis": "£50.00"}]), t1, {}, "T2")
    assert t2.iloc[0]["status"] == "geändert" and t2.iloc[0]["preis_vorher"] == 51.77


def test_preiswarnung_meldet_gesenkten_preis(netz):
    from app.core.database import SessionLocal
    from app.models.alert import AlertRule
    from app.models.dataset import Dataset
    from app.models.mapping import Mapping
    from app.services import alert_service
    from app.services.web_abruf import abruf_ausfuehren, preiswarnung_einrichten

    db = SessionLocal()
    ds = Dataset(name="__test_preiswarnung", file_type="doc_html", project_id=4, xml_configured=1,
                 row_count=0, columns=[], query_config={"urls": "https://s.de/p/1\nhttps://s.de/p/2",
                                                        "extract_type": "produkte", "verlauf": "ja",
                                                        "pause_ms": 0})
    db.add(ds); db.commit(); db.refresh(ds)
    mid = None
    try:
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", "10.00", "4000000000011"))
        NETZ["https://s.de/p/2"] = jsonld(produkt("Zwei", "20.00", "4000000000022"))
        abruf_ausfuehren(ds.id)
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", "9.00", "4000000000011"))    # −10 %
        NETZ["https://s.de/p/2"] = jsonld(produkt("Zwei", "20.40", "4000000000022"))   # +2 %
        abruf_ausfuehren(ds.id)
        db.refresh(ds)
        r = preiswarnung_einrichten(ds, 5, db)
        mid = r["mapping_id"]
        res = alert_service._run_mapping(mid, {}, preview_rows=200)
        assert sorted(z["name"] for z in res["rows"]) == ["Eins", "Zwei"]   # beide geändert, nur aktuell
        regel = db.query(AlertRule).filter(AlertRule.rule_key == f"web_preis_gesenkt_{ds.id}").first()
        treffer = alert_service._filter_rows(res["rows"], regel.condition, {})
        assert [z["name"] for z in treffer] == ["Eins"]
        erh = db.query(AlertRule).filter(AlertRule.rule_key == f"web_preis_erhoeht_{ds.id}").first()
        assert alert_service._filter_rows(res["rows"], erh.condition, {}) == []
        # zweiter Aufruf aktualisiert statt doppelt anzulegen
        assert preiswarnung_einrichten(ds, 1.5, db)["mapping_id"] == mid
        assert len(alert_service._filter_rows(res["rows"], db.query(AlertRule).filter(
            AlertRule.rule_key == f"web_preis_erhoeht_{ds.id}").first().condition, {})) == 1
    finally:
        for key in (f"web_preis_gesenkt_{ds.id}", f"web_preis_erhoeht_{ds.id}"):
            for regel in db.query(AlertRule).filter(AlertRule.rule_key == key).all():
                db.delete(regel)
        if mid:
            m = db.get(Mapping, mid)
            if m:
                db.delete(m)
        pfad = ds.file_path
        db.delete(db.get(Dataset, ds.id)); db.commit(); db.close()
        if pfad and os.path.exists(pfad):
            os.remove(pfad)


# ─── KI-Extraktion ────────────────────────────────────────────────────────────

class _FakeKI:
    def __init__(self, antwort):
        self.antwort, self.aufrufe = antwort, 0

    async def complete_json(self, messages, schema, **kw):
        self.aufrufe += 1
        assert set(schema["properties"]["zeilen"]["items"]["properties"]) == {"name", "preis", "lieferzeit"}
        return self.antwort


@pytest.fixture
def ki(monkeypatch, tmp_path):
    import app.services.ai_service as ais
    from app.plugins.builtin.web import ki_extraktion as kx
    monkeypatch.setattr(kx, "_cache_pfad", lambda k: str(tmp_path / f"{k}.json"))
    fake = _FakeKI({"zeilen": [{"name": "Bettschutz Classic", "preis": "12,90", "lieferzeit": "2-3 Tage"},
                               {"name": "Erfunden", "preis": "9,99", "lieferzeit": None}]})
    monkeypatch.setattr(ais, "build_ai_service", lambda db: fake)
    return fake


SEITE = ("<html><body><nav>Menü</nav><h1>Bettschutz Classic</h1><p>Preis: 12,90 €</p>"
         "<p>Lieferzeit: 2-3 Tage</p><script>var x=1</script></body></html>")


def test_ki_nur_belegte_werte_und_cache(ki):
    from app.plugins.builtin.web.ki_extraktion import ki_extrahieren
    z = ki_extrahieren(SEITE, ["name", "preis", "lieferzeit"])
    # „Erfunden“ / 9,99 stehen nicht auf der Seite → Zeile fällt weg
    assert z == [{"name": "Bettschutz Classic", "preis": "12,90", "lieferzeit": "2-3 Tage"}]
    assert ki_extrahieren(SEITE, ["name", "preis", "lieferzeit"]) == z
    assert ki.aufrufe == 1          # zweiter Abruf aus dem Zwischenspeicher


def test_ki_im_html_leser_mit_preisvergleich(ki, netz):
    NETZ["https://k.de/a"] = SEITE
    df, info = HtmlDocumentSource().abrufen({"url": "https://k.de/a", "extract_type": "ki",
                                             "ki_felder": "name, preis, lieferzeit"})
    assert df["preis"].tolist() == ["12,90"]
    t = vergleichen(df, None, {}, "T1")
    assert t.iloc[0]["preis"] == 12.9


def test_verlauf_wird_gekuerzt(netz):
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.services.web_abruf import abruf_ausfuehren
    db = SessionLocal()
    ds = Dataset(name="__test_verlauf_tage", file_type="doc_html", project_id=4, xml_configured=1,
                 row_count=0, columns=[], query_config={"url": "https://s.de/p/1", "extract_type": "produkte",
                                                        "verlauf": "ja", "verlauf_tage": 30, "pause_ms": 0})
    db.add(ds); db.commit(); db.refresh(ds)
    try:
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins", "10.00", "4000000000011"))
        abruf_ausfuehren(ds.id)
        db.refresh(ds)
        alt = pd.read_parquet(ds.file_path)
        alt["abgerufen_am"] = pd.Timestamp("2020-01-01")      # uralter Abruf
        alt.to_parquet(ds.file_path, index=False)
        abruf_ausfuehren(ds.id)
        df = pd.read_parquet(ds.file_path)
        assert len(df) == 1 and df.iloc[0]["ist_aktuell"] == "ja"
    finally:
        pfad = ds.file_path
        db.delete(db.get(Dataset, ds.id)); db.commit(); db.close()
        if pfad and os.path.exists(pfad):
            os.remove(pfad)


def test_abgleich_mit_eigenen_preisen(netz):
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.services.file_service import dataframe_to_storage
    from app.services.web_abruf import abruf_ausfuehren
    db = SessionLocal()
    eigen = Dataset(name="__test_eigene_preise", file_type="csv", project_id=4, xml_configured=1,
                    row_count=2, columns=["ArtNr", "Artikel", "VK_brutto", "EK_netto", "MwSt"])
    urls = Dataset(name="__test_url_liste", file_type="csv", project_id=4, xml_configured=1,
                   row_count=2, columns=["ArtNr", "url"])
    db.add_all([eigen, urls]); db.commit(); db.refresh(eigen); db.refresh(urls)
    eigen.file_path = dataframe_to_storage(pd.DataFrame({
        "ArtNr": ["A1", "A2"], "Artikel": ["Eins", "Zwei"], "VK_brutto": [11.90, 20.00],
        "EK_netto": [5.0, 15.0], "MwSt": [19, 19]}), eigen.id)
    urls.file_path = dataframe_to_storage(pd.DataFrame({
        "ArtNr": ["A1", "A2"], "url": ["https://s.de/p/1", "https://s.de/p/2"]}), urls.id)
    web = Dataset(name="__test_abgleich", file_type="doc_html", project_id=4, xml_configured=1, row_count=0,
                  columns=[], query_config={"url_dataset_id": urls.id, "eigene_preise_dataset_id": eigen.id,
                                            "extract_type": "produkte", "pause_ms": 0})
    db.add(web); db.commit(); db.refresh(web)
    try:
        NETZ["https://s.de/p/1"] = jsonld(produkt("Eins beim Wettbewerb", "10.71", "4000000000011"))
        NETZ["https://s.de/p/2"] = jsonld(produkt("Zwei beim Wettbewerb", "22.00", "4000000000022"))
        abruf_ausfuehren(web.id)
        db.refresh(web)
        df = pd.read_parquet(web.file_path).set_index("ArtNr")
        assert df.loc["A1", "eigener_preis"] == 11.9 and df.loc["A1", "guenstiger"] == 1
        assert df.loc["A1", "differenz_prozent"] == -10.0 and df.loc["A1", "unterbietung_prozent"] == 10.0
        assert df.loc["A1", "marge_bei_wettbewerbspreis"] == 44.4      # 10,71/1,19 = 9,00 netto, EK 5
        assert df.loc["A2", "guenstiger"] == 0 and df.loc["A2", "differenz"] == 2.0
        assert df.loc["A1", "artikel_eigen"] == "Eins"
    finally:
        for d in (web, eigen, urls):
            pfad = db.get(Dataset, d.id).file_path
            db.delete(db.get(Dataset, d.id))
            if pfad and os.path.exists(pfad):
                os.remove(pfad)
        db.commit(); db.close()


def test_waehrung_wird_umgerechnet(monkeypatch):
    from types import SimpleNamespace
    import app.services.web_abruf as wa
    monkeypatch.setattr(wa, "wechselkurse", lambda ws: {"USD": (1.12, "2026-10")})

    class _Conn:
        def fetch_full(self):
            return pd.DataFrame({"ArtNr": ["A1", "A2"], "Preis_aktuell_brutto": [300.0, 100.0],
                                 "EK_netto": [100.0, 50.0], "MwSt": [19, 19]})
    import app.connectors.factory as fac
    monkeypatch.setattr(fac, "get_connector", lambda i: _Conn())

    class _Q:
        def filter(self, *a):
            return self
        def first(self):
            return SimpleNamespace(id=1, project_id=4, name="eigen")
    db = SimpleNamespace(query=lambda m: _Q())
    ds = SimpleNamespace(project_id=4)
    roh = pd.DataFrame({"quelle_url": ["u1", "u2"], "ArtNr": ["A1", "A2"], "preis": ["$336.00", "95,00 €"]})
    stand = vergleichen(roh, None, {}, "T1")
    assert stand["waehrung"].tolist() == ["USD", "EUR"]
    erg = wa.mit_eigenen_preisen(stand, {"eigene_preise_dataset_id": 1, "eigener_preis_spalte": "Preis_aktuell_brutto"}, ds, db)
    a1 = erg[erg["ArtNr"] == "A1"].iloc[0]
    assert a1["preis_eur"] == 300.0 and a1["kurs"] == 1.12 and a1["kurs_stand"] == "2026-10"
    assert a1["guenstiger"] == 0 and a1["differenz"] == 0.0
    a2 = erg[erg["ArtNr"] == "A2"].iloc[0]
    assert a2["guenstiger"] == 1 and a2["differenz_prozent"] == -5.0

    monkeypatch.setattr(wa, "wechselkurse", lambda ws: (_ for _ in ()).throw(RuntimeError("offline")))
    erg = wa.mit_eigenen_preisen(stand, {"eigene_preise_dataset_id": 1, "eigener_preis_spalte": "Preis_aktuell_brutto"}, ds, db)
    assert pd.isna(erg[erg["ArtNr"] == "A1"].iloc[0]["differenz"])
    assert "Wechselkurse nicht abrufbar" in erg.attrs["hinweise"][0]

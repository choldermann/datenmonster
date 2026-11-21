"""Mapping-Baukasten: Übersetzer Steinkette → SQL (ohne Datenbank).

Lauf:  docker compose exec -T backend python tests/test_baukasten_uebersetzer.py
"""
import re
import sys
from contextlib import contextmanager
sys.path.insert(0, "/app")

from app.services.baukasten.uebersetzer import BaukastenFehler, Schema, uebersetzen, vorschau_begrenzen

@contextmanager
def raises(art, muster=None):
    try:
        yield
    except art as e:
        if muster and not re.search(muster, str(e)):
            raise AssertionError(f"Meldung passt nicht: {e}")
        return
    raise AssertionError(f"{art.__name__} erwartet")


SCHEMA = Schema({"tables": [
    {"full_name": "Rechnung.tRechnung", "columns": [
        {"name": "kRechnung", "type": "int"}, {"name": "kKunde", "type": "int"},
        {"name": "dErstellt", "type": "datetime"}, {"name": "fWert", "type": "decimal(18,2)"},
        {"name": "cRechnungsNr", "type": "nvarchar(50)"}]},
    {"full_name": "dbo.tKunde", "columns": [
        {"name": "kKunde", "type": "int"}, {"name": "cFirma", "type": "nvarchar(100)"},
        {"name": "cLand", "type": "nvarchar(5)"}]},
]})

KETTE = [
    {"type": "start", "trigger": "Wenn das Cockpit öffnet"},
    {"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "filter", "col": "dErstellt", "op": "im Jahr", "val": "2026"},
        {"type": "join", "table": "dbo.tKunde", "links": "kKunde", "rechts": "kKunde", "inner": [
            {"type": "filter", "col": "cLand", "op": "=", "val": "DE"}]},
    ]},
    {"type": "verdichten", "by": ["cFirma", {"col": "dErstellt", "teil": "monat"}],
     "aggs": [{"fn": "Summe", "col": "fWert"}, {"fn": "Anzahl"}]},
    {"type": "rechnen", "name": "Ø Rechnung", "a": "Summe fWert", "op": "÷", "b": "Anzahl"},
    {"type": "filter", "col": "Summe fWert", "op": ">", "val": "1000"},
    {"type": "sortieren", "col": "Summe fWert", "dir": "absteigend"},
    {"type": "begrenzen", "n": 10},
    {"type": "ausgabe", "target": "Tabelle im Cockpit"},
]


def test_ganze_kette_mssql():
    e = uebersetzen(KETTE, SCHEMA, "mssql", literal=True)
    sql = e.sql
    assert sql.startswith("WITH s0 AS (")
    assert "FROM [Rechnung].[tRechnung] t0" in sql
    assert "INNER JOIN (SELECT * FROM [dbo].[tKunde] WHERE [cLand] = N'DE') j1 ON t0.[kKunde] = j1.[kKunde]" in sql
    assert "t0.[dErstellt] >= N'20260101' AND t0.[dErstellt] < N'20270101'" in sql   # JJJJMMTT: eindeutig in SQL Server
    assert "CONVERT(char(7), [dErstellt], 126) AS [dErstellt (Monat)]" in sql
    assert "GROUP BY [cFirma], CONVERT(char(7), [dErstellt], 126)" in sql
    assert "ROUND(CAST([Summe fWert] AS float) / NULLIF(CAST([Anzahl] AS float), 0), 2) AS [Ø Rechnung]" in sql
    assert "ROUND(SUM(CAST([fWert] AS float)), 2) AS [Summe fWert]" in sql
    assert "WHERE [Summe fWert] > 1000" in sql
    assert sql.rstrip().endswith("SELECT TOP (10) * FROM s3\nORDER BY [Summe fWert] DESC")
    assert [s.name for s in e.spalten] == ["cFirma", "dErstellt (Monat)", "Summe fWert", "Anzahl", "Ø Rechnung"]
    assert ":p" not in sql                      # gespeichertes Mapping: keine ungebundenen Parameter


def test_zaehler_und_spalten_je_block():
    e = uebersetzen(KETTE, SCHEMA, "mssql")
    for bid in (":1:kopf", "1:0", "1:1", "1.1:0", "1:1:fremd", ":1", ":2", ":3", ":4", ":5", ":6", ":7"):
        assert bid in e.zaehl_sql, bid
    # was am Trichter ankommt: Rechnungs- und Kundenspalten (Schlüssel nicht doppelt)
    assert e.spalten_je_block[":2"] == ["kRechnung", "kKunde", "dErstellt", "fWert", "cRechnungsNr", "cFirma", "cLand"]
    assert e.params == {"p0": "20260101", "p1": "20270101", "p2": "DE", "p3": 1000.0}
    # Zähler „Nur die ersten“ zählt das Begrenzte (TOP mit ORDER BY ist in der Unterabfrage erlaubt)
    assert "SELECT COUNT(*) AS n FROM (SELECT TOP (10) * FROM s3\nORDER BY [Summe fWert] DESC) z" in e.zaehl_sql[":6"]


def test_injektion_ueber_namen_und_werte_unmoeglich():
    boese = [{"type": "tabelle", "table": "Rechnung.tRechnung; DROP TABLE x", "inner": []}]
    with raises(BaukastenFehler):
        uebersetzen(boese, SCHEMA)
    boese = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "filter", "col": "cRechnungsNr", "op": "=", "val": "x'; DROP TABLE y; --"}]}]
    sql = uebersetzen(boese, SCHEMA, literal=True).sql
    assert "N'x''; DROP TABLE y; --'" in sql
    with raises(BaukastenFehler):
        uebersetzen([{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
            {"type": "filter", "col": "fWert]; DROP TABLE z; --", "op": "=", "val": "1"}]}], SCHEMA)
    with raises(BaukastenFehler):
        uebersetzen([{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
            {"type": "filter", "col": "fWert", "op": "OR 1=1", "val": "1"}]}], SCHEMA)


REGELN = [
    ([{"type": "verdichten", "by": ["x"]}], "Zuerst eine Tabelle"),
    ([{"type": "tabelle", "table": "dbo.tKunde", "inner": []}, {"type": "filter", "col": "cLand", "op": "=", "val": "DE"}], "Kennzahl"),
    ([{"type": "tabelle", "table": "dbo.tKunde", "inner": []}, {"type": "ausgabe"}, {"type": "begrenzen", "n": 1}], "letzte Stein"),
    ([{"type": "tabelle", "table": "dbo.tKunde", "inner": [{"type": "rechnen"}]}], "Winkel"),
    ([{"type": "tabelle", "table": "dbo.tKunde", "inner": []}, {"type": "verdichten", "by": ["cLand"], "aggs": [{"fn": "Summe", "col": "cFirma"}]}], "nur mit Zahlen"),
]


def test_regeln():
    for kette, meldung in REGELN:
        with raises(BaukastenFehler, meldung):
            uebersetzen(kette, SCHEMA)


def test_zeitraum_des_cockpits_bleibt_parameter():
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [{"type": "filter", "col": "dErstellt", "op": "im Zeitraum"}]}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert "t0.[dErstellt] >= :von AND t0.[dErstellt] < DATEADD(DAY, 1, :bis)" in e.sql
    assert e.nutzt_zeitraum


def test_leerer_wert_wirkt_nicht_und_enthaelt_maskiert():
    k = [{"type": "tabelle", "table": "dbo.tKunde", "inner": [
        {"type": "filter", "col": "cFirma", "op": "enthält", "val": ""},
        {"type": "filter", "col": "cLand", "op": "enthält", "val": "50%_"}]}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert "WHERE LOWER(CAST(t0.[cLand] AS nvarchar(400))) LIKE LOWER(N'%50\\%\\_%') ESCAPE '\\'" in e.sql
    assert "cFirma" not in e.sql.split("WHERE")[1]


def test_andere_dialekte_und_vorschau():
    k = [{"type": "tabelle", "table": "dbo.tKunde", "inner": []}, {"type": "sortieren", "col": "cFirma", "dir": "aufsteigend"},
         {"type": "begrenzen", "n": 5}]
    pg = uebersetzen(k, SCHEMA, "postgresql", literal=True).sql
    assert 'FROM "dbo"."tKunde" t0' in pg and pg.rstrip().endswith('ORDER BY "cFirma" ASC\nLIMIT 5')
    my = uebersetzen(k, SCHEMA, "mysql", literal=True).sql
    assert "FROM `dbo`.`tKunde` t0" in my
    ms = uebersetzen([k[0]], SCHEMA, "mssql").sql
    assert vorschau_begrenzen(ms, 50, "mssql").endswith("SELECT TOP (50) * FROM s0")
    assert vorschau_begrenzen("SELECT * FROM [dbo].[tKunde] t0", 50, "mssql") == "SELECT TOP (50) * FROM [dbo].[tKunde] t0"


def test_spaltennamen_ohne_gross_klein():
    """SQL Server: cUstId und cUSTID sind dieselbe Spalte – die dazugeholte bekommt einen Zusatz (Fund aus dem Live-Test)."""
    sch = Schema({"db_type": "mssql", "tables": [
        {"full_name": "a.R", "columns": [{"name": "kK", "type": "int"}, {"name": "cUstId", "type": "nvarchar(20)"},
                                          {"name": "bRowversion", "type": "timestamp"}]},
        {"full_name": "a.K", "columns": [{"name": "kK", "type": "int"}, {"name": "cUSTID", "type": "nvarchar(20)"}]}]})
    e = uebersetzen([{"type": "tabelle", "table": "a.R", "inner": [
        {"type": "join", "table": "a.K", "links": "kK", "rechts": "kK", "inner": []}]}], sch)
    assert [s.name for s in e.spalten] == ["kK", "cUstId", "bRowversion", "cUSTID (K)"]
    assert sch.tabellen["a.R"][2].typ == "text"          # timestamp = Zeilenversion, kein Datum


def test_warnung_bei_vervielfachung():
    from app.services.baukasten.ausfuehren import warnungen
    k = [{"type": "tabelle", "table": "x", "inner": [
        {"type": "filter"}, {"type": "join", "table": "dbo.tAdresse", "links": "kKunde"}]}]
    w = warnungen(k, {":0:kopf": 30879, "0:0": 10219, "0:1": 10219})
    assert w == {}
    w = warnungen(k, {":0:kopf": 30879, "0:0": 10219, "0:1": 20438})
    assert "Aus 10.219 werden 20.438 Zeilen" in w["0:1"]
    k[0]["inner"][1].update(alle=True, inner=[{"type": "filter", "col": "cOrt", "op": "=", "val": "Stuttgart"}])
    assert "filtert dann keine Zeilen weg" in warnungen(k, {":0:kopf": 10, "0:0": 10, "0:1": 10})["0:1"]


def test_ki_normalisierung_alle_mit_filter_aus():
    from app.services.baukasten.rezepte import _normalisieren
    k = _normalisieren([{"type": "tabelle", "table": "x", "inner": [
        {"type": "join", "table": "y", "links": "a", "rechts": "a", "alle": True, "inner": [{"type": "filter", "col": "o"}]},
        {"type": "join", "table": "z", "links": "a", "rechts": "a", "alle": True, "inner": []}]}])
    assert [j["alle"] for j in k[0]["inner"]] == [False, True]


def test_ist_einer_von_und_differenz_gerundet():
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "filter", "col": "cRechnungsNr", "op": "ist einer von", "val": "Rechnung I, Sammel Rechnung"},
        {"type": "filter", "col": "kKunde", "op": "ist einer von", "val": "1; 2,5"}]},
         {"type": "rechnen", "name": "Diff", "a": "fWert", "op": "−", "b": "kKunde"}]
    sql = uebersetzen(k, SCHEMA, literal=True).sql
    assert "t0.[cRechnungsNr] IN (N'Rechnung I', N'Sammel Rechnung')" in sql, sql
    assert "t0.[kKunde] IN (1, 2.5)" in sql, sql
    assert "ROUND(CAST([fWert] AS float) - CAST([kKunde] AS float), 2) AS [Diff]" in sql, sql


def test_bueroplus_rezepte_passen_nur_zu_bueroplus():
    from app.services.baukasten.rezepte import passende
    bp = Schema({"tables": [
        {"full_name": "dbo.vVorgang", "columns": [{"name": n, "type": t} for n, t in [
            ("VogID", "int"), ("VogAdrNr", "int"), ("VogArt", "nvarchar"), ("VogVerk", "nvarchar"), ("VogGebuchtKz", "bit"),
            ("VogStorniertKz", "bit"), ("VogDat", "date"), ("VogGPreisNt", "decimal"), ("VogGEkRoh", "decimal")]]},
        {"full_name": "dbo.Adressen", "columns": [{"name": "AdrAdrNr", "type": "int"}, {"name": "AdrReNa2", "type": "nvarchar"}]}]})
    keys = [r["key"] for r in passende(bp, "mssql")]
    assert keys == ["bp_umsatz_monat", "bp_top_kunden", "bp_abgewandert", "bp_kunden_vorjahr", "bp_umsatz_verkaeufer"], keys
    assert not [r for r in passende(SCHEMA, "mssql") if r["system"] == "büro+"]


def test_widget_vorbelegung():
    from app.services.baukasten.ausfuehren import _widget_config
    from app.services.baukasten.uebersetzer import Spalte
    sp = [Spalte("Monat", "text"), Spalte("Umsatz", "zahl"), Spalte("Anzahl", "zahl")]
    assert _widget_config("bar", {}, sp) == {"width": 12, "x_column": "Monat", "y_columns": ["Umsatz", "Anzahl"]}
    assert _widget_config("line", {"x": "Monat", "y": ["Umsatz", "gibtsnicht"]}, sp)["y_columns"] == ["Umsatz"]
    assert _widget_config("kpi", {"wert": "Anzahl"}, sp)["column"] == "Anzahl"
    with raises(BaukastenFehler, "Zahlenspalte"):
        _widget_config("bar", {}, [Spalte("Monat", "text")])


def test_neue_steine():
    # nur ohne Treffer
    k = [{"type": "tabelle", "table": "dbo.tKunde", "inner": [
        {"type": "join", "table": "Rechnung.tRechnung", "links": "kKunde", "rechts": "kKunde", "ohne": True,
         "inner": [{"type": "filter", "col": "dErstellt", "op": "im Jahr", "val": "2026"}]}]}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert "NOT EXISTS (SELECT 1 FROM (SELECT * FROM [Rechnung].[tRechnung] WHERE [dErstellt] >= N'20260101'" in e.sql, e.sql
    assert [x.name for x in e.spalten] == ["kKunde", "cFirma", "cLand"]
    # Einteilen
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": []},
         {"type": "einteilen", "name": "Größe", "col": "fWert", "regeln": [
             {"op": "≥", "val": "1000", "wert": "groß"}, {"op": "≥", "val": "100", "wert": "mittel"}], "sonst": "klein"}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert "CASE WHEN [fWert] >= 1000 THEN N'groß' WHEN [fWert] >= 100 THEN N'mittel' ELSE N'klein' END AS [Größe]" in e.sql, e.sql
    # Datum rechnen
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": []},
         {"type": "rechnen", "name": "Alter", "a": "dErstellt", "op": "Tage bis heute", "b": ""}]
    assert "DATEDIFF(DAY, [dErstellt], CAST(GETDATE() AS date)) AS [Alter]" in uebersetzen(k, SCHEMA).sql
    with raises(BaukastenFehler, "Datumsspalten"):
        uebersetzen([k[0], {"type": "rechnen", "name": "x", "a": "fWert", "op": "Tage bis heute"}], SCHEMA)
    # Zeitraum + Vorjahr
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "filter", "col": "dErstellt", "op": "im Zeitraum + Vorjahr"}]},
         {"type": "verdichten", "by": ["kKunde"], "aggs": [{"fn": "Summe", "col": "fWert"}, {"fn": "Anzahl"}]}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert [x.name for x in e.spalten] == ["kKunde", "Summe fWert", "Summe fWert Vorjahr", "Anzahl", "Anzahl Vorjahr"]
    assert "t0.[dErstellt] >= DATEADD(YEAR, -1, :von)" in e.sql
    assert "ROUND(COALESCE(SUM(CASE WHEN [dErstellt] >= DATEADD(YEAR, -1, :von) AND [dErstellt] < DATEADD(YEAR, -1, DATEADD(DAY, 1, :bis)) THEN CAST([fWert] AS float) END), 0), 2) AS [Summe fWert Vorjahr]" in e.sql, e.sql
    assert e.nutzt_zeitraum



def test_stein_spalten():
    basis = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "join", "table": "dbo.tKunde", "links": "kKunde", "rechts": "kKunde", "inner": []}]},
        {"type": "verdichten", "by": ["cFirma"], "aggs": [{"fn": "Summe", "col": "fWert"}, {"fn": "Anzahl"}]}]
    sp = {"type": "spalten", "liste": [{"col": "Summe fWert", "als": "Umsatz"}, {"col": "cFirma", "als": "Kunde"}]}
    # Sortieren davor: Name folgt der Umbenennung
    e = uebersetzen(basis + [{"type": "sortieren", "col": "Summe fWert"}, sp], SCHEMA, literal=True)
    assert [x.name for x in e.spalten] == ["Umsatz", "Kunde"]
    assert "SELECT [Summe fWert] AS [Umsatz], [cFirma] AS [Kunde] FROM s1" in e.sql
    assert e.sql.rstrip().endswith("ORDER BY [Umsatz] DESC"), e.sql
    # danach: neue Namen
    e = uebersetzen(basis + [sp, {"type": "sortieren", "col": "Umsatz", "dir": "aufsteigend"}], SCHEMA, literal=True)
    assert e.sql.rstrip().endswith("ORDER BY [Umsatz] ASC")
    # weggelassene Sortierspalte, doppelte Namen, leere Liste
    with raises(BaukastenFehler, "Sortieren.*Anzahl"):
        uebersetzen(basis + [{"type": "sortieren", "col": "Anzahl"}, sp], SCHEMA)
    with raises(BaukastenFehler, "zweimal"):
        uebersetzen(basis + [{"type": "spalten", "liste": [{"col": "cFirma", "als": "X"}, {"col": "Anzahl", "als": "x"}]}], SCHEMA)
    e = uebersetzen(basis + [{"type": "spalten", "liste": []}], SCHEMA)
    assert [x.name for x in e.spalten] == ["cFirma", "Summe fWert", "Anzahl"]
    with raises(BaukastenFehler, "gibt es an dieser Stelle nicht"):
        uebersetzen(basis + [{"type": "spalten", "liste": [{"col": "x]; DROP TABLE y--"}]}], SCHEMA)


def test_im_cockpit_waehlbar():
    k = [{"type": "tabelle", "table": "Rechnung.tRechnung", "inner": [
        {"type": "join", "table": "dbo.tKunde", "links": "kKunde", "rechts": "kKunde", "inner": [
            {"type": "filter", "col": "cLand", "op": "im Cockpit wählbar", "label": "Land"}]},
        {"type": "filter", "col": "cFirma", "op": "im Cockpit wählbar"}]}]
    e = uebersetzen(k, SCHEMA, literal=True)
    assert "(:bk_tKunde_cLand_empty = 1 OR [cLand] IN (:bk_tKunde_cLand))" in e.sql, e.sql
    assert "(:bk_tKunde_cFirma_empty = 1 OR j1.[cFirma] IN (:bk_tKunde_cFirma))" in e.sql, e.sql
    assert e.auswahl == [
        {"param": "bk_tKunde_cLand", "label": "Land", "table": "dbo.tKunde", "column": "cLand"},
        {"param": "bk_tKunde_cFirma", "label": "cFirma", "table": "dbo.tKunde", "column": "cFirma"}]
    with raises(BaukastenFehler, "nur im Winkel"):
        uebersetzen(k + [{"type": "verdichten", "by": ["cLand"], "aggs": [{"fn": "Anzahl"}]},
                         {"type": "filter", "col": "Anzahl", "op": "im Cockpit wählbar"}], SCHEMA)
    # Lauf: nichts gewählt/fehlt → alle; Auswahl → IN-Liste
    from app.services.sql_helpers import _resolve_sql_run_params
    sql, p = _resolve_sql_run_params(e.sql, {"von": "x"})
    assert p["bk_tKunde_cLand_empty"] == 1 and "IN (NULL)" in sql
    sql, p = _resolve_sql_run_params(e.sql, {"bk_tKunde_cLand": ["DE", "AT"], "bk_tKunde_cFirma": ""})
    assert p["bk_tKunde_cLand_empty"] == 0 and "[cLand] IN (:bk_tKunde_cLand__0, :bk_tKunde_cLand__1)" in sql
    assert p["bk_tKunde_cFirma_empty"] == 1


if __name__ == "__main__":
    fehler = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f(); print("  OK  ", name)
            except Exception as e:
                fehler += 1; print("  FAIL", name, "→", repr(e)[:400])
    print("Alle Prüfungen bestanden." if not fehler else f"{fehler} Fehler")
    sys.exit(1 if fehler else 0)

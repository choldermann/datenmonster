"""Schreibt Zeilen in eazybusiness_synth – ohne jede Spalte von Hand zu nennen.

Pflichtspalten, die der Generator nicht setzt, bekommen einen neutralen Wert
(0, '', Datum der Zeile …). rowversion- und berechnete Spalten werden
übersprungen, Identitätsspalten bei Bedarf mit IDENTITY_INSERT gesetzt.
"""
import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal

from tools.demo_daten.verbindung import ZIEL, verbinden

_ZAHL = {"int", "bigint", "smallint", "tinyint", "bit", "decimal", "numeric", "money", "smallmoney", "float", "real"}
_TEXT = {"varchar", "nvarchar", "char", "nchar", "text", "ntext"}
_DATUM = {"datetime", "datetime2", "smalldatetime", "date", "datetimeoffset"}
_NEUTRAL_DATUM = dt.datetime(2023, 11, 1)


class Schreiber:
    def __init__(self, nur_pruefen: bool = False):
        # nur_pruefen: nichts schreiben, alle falschen Spaltennamen sammeln
        self.nur_pruefen = nur_pruefen
        self.fehler = []
        self.con = verbinden(ZIEL, autocommit=False)
        self.cur = self.con.cursor()
        assert self.cur.execute("SELECT DB_NAME()").fetchone()[0] == ZIEL, "falsche Datenbank!"
        self.cur.fast_executemany = True
        self._meta = {}
        self.zaehler = {}

    def meta(self, tabelle: str):
        if tabelle not in self._meta:
            s, n = tabelle.split(".")
            rows = self.cur.execute("""
                SELECT c.name, TYPE_NAME(c.system_type_id), c.is_nullable, c.is_identity, c.is_computed,
                       CASE WHEN c.default_object_id <> 0 THEN 1 ELSE 0 END, c.max_length
                FROM sys.columns c WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id""",
                                    f"[{s}].[{n}]").fetchall()
            if not rows:
                raise KeyError(f"Tabelle {tabelle} gibt es nicht")
            self._meta[tabelle] = [
                dict(name=r[0], typ=r[1], null=bool(r[2]), ident=bool(r[3]), calc=bool(r[4]),
                     default=bool(r[5]), laenge=r[6])
                for r in rows if r[1] not in ("timestamp",) and not r[4]]
        return self._meta[tabelle]

    def _eindeutig_pruefen(self, tabelle, zeilen):
        """Eindeutige Indizes/PKs gegen die erzeugten Zeilen prüfen (NULL zählt
        bei UNIQUE-Constraints in SQL Server als Wert – wie hier)."""
        s, n = tabelle.split(".")
        idx = defaultdict(list)
        for name, spalte, gefiltert in self.cur.execute("""
                SELECT i.name, c.name, i.has_filter FROM sys.indexes i
                JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
                JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                WHERE i.object_id = OBJECT_ID(?) AND i.is_unique = 1 ORDER BY i.name, ic.key_ordinal""", f"[{s}].[{n}]"):
            if not gefiltert:
                idx[name].append(spalte.lower())
        sp = {x["name"].lower(): x for x in self.meta(tabelle)}
        for name, spalten in idx.items():
            if any(c in sp and sp[c]["ident"] for c in spalten) and not any(c in {k.lower() for k in zeilen[0]} for c in spalten):
                continue
            gesehen = set()
            for z in zeilen:
                zl = {k.lower(): v for k, v in z.items()}
                schl = tuple(zl.get(c, None if sp.get(c, {}).get("null", True) else self._neutral(sp[c]))
                             if c in sp else None for c in spalten)
                if schl in gesehen:
                    self.fehler.append(f"{tabelle}: {name} doppelt {dict(zip(spalten, schl))}")
                    break
                gesehen.add(schl)

    def _neutral(self, sp):
        if sp["typ"] in _ZAHL:
            return 0
        if sp["typ"] in _TEXT:
            return ""
        if sp["typ"] in _DATUM:
            return _NEUTRAL_DATUM
        if sp["typ"] == "uniqueidentifier":
            return str(uuid.uuid4())
        if sp["typ"] in ("varbinary", "binary", "image"):
            return b""
        return None

    def schreiben(self, tabelle: str, zeilen: list, stapel: int = 2000):
        if not zeilen:
            return
        sp = self.meta(tabelle)
        bekannt = {s["name"].lower(): s for s in sp}
        gesetzt = {k.lower() for z in zeilen for k in z}
        unbekannt = gesetzt - set(bekannt)
        if unbekannt:
            meldung = f"{tabelle}: unbekannte Spalten {sorted(unbekannt)}"
            if not self.nur_pruefen:
                raise KeyError(meldung)
            self.fehler.append(meldung)
        if self.nur_pruefen:
            self._eindeutig_pruefen(tabelle, zeilen)
            self.zaehler[tabelle] = self.zaehler.get(tabelle, 0) + len(zeilen)
            return
        # Spalten: alles Gesetzte + Pflichtspalten ohne Standardwert
        spalten = [s for s in sp if s["name"].lower() in gesetzt
                   or (not s["null"] and not s["default"] and not s["ident"])]
        ident = any(s["ident"] and s["name"].lower() in gesetzt for s in sp)
        namen = [s["name"] for s in spalten]
        werte = []
        for z in zeilen:
            zl = {k.lower(): v for k, v in z.items()}
            reihe = []
            for s in spalten:
                v = zl.get(s["name"].lower(), None)
                if v is None and not s["null"]:
                    v = self._neutral(s)
                if isinstance(v, float):
                    v = Decimal(str(round(v, 6))) if s["typ"] in ("decimal", "numeric", "money") else v
                if isinstance(v, str) and s["typ"] in _TEXT and s["laenge"] > 0:
                    grenze = s["laenge"] // (2 if s["typ"].startswith("n") else 1)
                    v = v[:grenze]
                reihe.append(v)
            werte.append(reihe)
        s_, n_ = tabelle.split(".")
        sql = (f"INSERT INTO [{s_}].[{n_}] (" + ", ".join(f"[{n}]" for n in namen) + ") VALUES ("
               + ", ".join("?" * len(namen)) + ")")
        if ident:
            self.cur.execute(f"SET IDENTITY_INSERT [{s_}].[{n_}] ON")
        try:
            for i in range(0, len(werte), stapel):
                self.cur.executemany(sql, werte[i:i + stapel])
        finally:
            if ident:
                self.cur.execute(f"SET IDENTITY_INSERT [{s_}].[{n_}] OFF")
        self.con.commit()
        self.zaehler[tabelle] = self.zaehler.get(tabelle, 0) + len(zeilen)

    def sql(self, text: str, *param):
        self.cur.execute(text, *param)
        self.con.commit()

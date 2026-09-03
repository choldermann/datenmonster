"""
Persistent schema cache for DB connections.
Builds a structured JSON snapshot of a DB schema and stores it in DbConnection.schema_cache.
The AI context builder reads from this cache to avoid live DB queries and to filter
relevant tables by keyword before sending to the model.
"""
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger("datenmonster")

SKIP_SCHEMAS = {
    "sys", "INFORMATION_SCHEMA", "guest", "db_owner",
    "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
}


def build_schema_json(conn, timeout_sec: int = 90) -> dict:
    """
    Queries the live DB and returns a structured schema dict:
    {db_type, database, tables: [{schema, name, full_name, columns: [{name, type, pk, fk}]}]}
    Raises TimeoutError if the operation takes longer than timeout_sec.
    """
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_build_schema_json_inner, conn)
        try:
            return future.result(timeout=timeout_sec)
        except _cf.TimeoutError:
            raise TimeoutError(f"Schema-Build hat nach {timeout_sec}s abgebrochen (DB zu groß oder nicht erreichbar)")


def _build_schema_json_inner(conn) -> dict:
    """Inner (blocking) schema build — call via build_schema_json for timeout protection."""
    from sqlalchemy import create_engine, text
    from app.services.db_service import get_engine_str

    db_type = conn.db_type
    # Use raw SQL for schema discovery — much faster than SQLAlchemy inspector on large MSSQL DBs
    engine = create_engine(
        get_engine_str(conn),
        connect_args={"timeout": 15, "login_timeout": 10} if db_type == "mssql" else {"connect_timeout": 10},
    )

    tables = []
    try:
        with engine.connect() as con:
            if db_type == "mssql":
                # Single query: all schemas, tables, columns, PKs in one shot
                rows = con.execute(text("""
                    SELECT
                        s.name  AS schema_name,
                        t.name  AS table_name,
                        c.name  AS col_name,
                        tp.name AS col_type,
                        CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS is_pk,
                        CASE WHEN fk.parent_column_id IS NOT NULL THEN 1 ELSE 0 END AS is_fk,
                        fk_ref.name AS fk_ref_table,
                        fk_ref_s.name AS fk_ref_schema,
                        fkc_ref.name AS fk_ref_col
                    FROM sys.tables t
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    JOIN sys.columns c ON c.object_id = t.object_id
                    JOIN sys.types tp  ON c.user_type_id = tp.user_type_id
                    LEFT JOIN (
                        SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
                        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                          ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                         AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
                        WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    ) pk ON pk.TABLE_SCHEMA = s.name
                         AND pk.TABLE_NAME  = t.name
                         AND pk.COLUMN_NAME = c.name
                    LEFT JOIN sys.foreign_key_columns fk
                           ON fk.parent_object_id = c.object_id
                          AND fk.parent_column_id  = c.column_id
                    LEFT JOIN sys.tables   fk_ref   ON fk_ref.object_id   = fk.referenced_object_id
                    LEFT JOIN sys.schemas  fk_ref_s ON fk_ref_s.schema_id = fk_ref.schema_id
                    LEFT JOIN sys.columns  fkc_ref  ON fkc_ref.object_id  = fk.referenced_object_id
                                                    AND fkc_ref.column_id = fk.referenced_column_id
                    WHERE s.name NOT IN (
                        'sys','INFORMATION_SCHEMA','guest','db_owner',
                        'db_accessadmin','db_securityadmin','db_ddladmin',
                        'db_backupoperator','db_datareader','db_datawriter',
                        'db_denydatareader','db_denydatawriter'
                    )
                    ORDER BY s.name, t.name, c.column_id
                """)).fetchall()

                cur_table = None
                for row in rows:
                    key = f"{row.schema_name}.{row.table_name}"
                    if key != cur_table:
                        cur_table = key
                        tables.append({
                            "schema":    row.schema_name,
                            "name":      row.table_name,
                            "full_name": key,
                            "columns":   [],
                        })
                    col: dict = {"name": row.col_name, "type": row.col_type}
                    if row.is_pk:
                        col["pk"] = True
                    if row.is_fk and row.fk_ref_table:
                        ref = f"{row.fk_ref_schema}.{row.fk_ref_table}.{row.fk_ref_col}" if row.fk_ref_schema else f"{row.fk_ref_table}.{row.fk_ref_col}"
                        col["fk"] = ref
                    tables[-1]["columns"].append(col)

                # ── Zeilenzahlen ──────────────────────────────────────────
                # Aus sys.partitions, nicht per COUNT(*): das liest die
                # Verwaltungsdaten und rührt keine Tabelle an – bei 2.000
                # Tabellen der Unterschied zwischen Millisekunden und Minuten.
                # Wozu: In einer JTL-Wawi ist rund die Hälfte aller Objekte leer.
                # Ohne Füllstand landen sechs leere Ticketsystem-Tabellen im
                # Prompt und verdrängen die gefüllten Fachtabellen – genau so
                # ist eine Frage nach dem Sendungsstatus ins Leere gelaufen.
                try:
                    zeilen_map = {
                        f"{r.schema_name}.{r.table_name}": int(r.zeilen or 0)
                        for r in con.execute(text("""
                            SELECT s.name AS schema_name, t.name AS table_name,
                                   SUM(p.rows) AS zeilen
                            FROM sys.tables t
                            JOIN sys.schemas s ON s.schema_id = t.schema_id
                            JOIN sys.partitions p ON p.object_id = t.object_id
                                                 AND p.index_id IN (0, 1)
                            GROUP BY s.name, t.name
                        """)).fetchall()
                    }
                    for t in tables:
                        if t["full_name"] in zeilen_map:
                            t["rows"] = zeilen_map[t["full_name"]]
                except Exception as e:
                    # Ohne Zeilenzahlen funktioniert alles wie bisher – nur die
                    # Bevorzugung gefüllter Tabellen entfällt.
                    log.warning(f"Zeilenzahlen nicht ermittelbar: {e}")

                # ── Views ──────────────────────────────────────────────────
                # sys.tables kennt sie nicht, und damit fehlten der KI die
                # 1.109 Views einer JTL-Wawi vollständig — auch
                # Preisliste.vPreislisteNetto und Rechnung.vRechnung, auf denen
                # JTLs eigene Auswertungen laufen und auf die unser Projektwissen
                # ausdrücklich verweist. Ein zweiter, einfacher Durchgang: Views
                # haben weder Primär- noch Fremdschlüssel.
                view_rows = con.execute(text("""
                    SELECT
                        s.name  AS schema_name,
                        v.name  AS table_name,
                        c.name  AS col_name,
                        tp.name AS col_type
                    FROM sys.views v
                    JOIN sys.schemas s ON v.schema_id = s.schema_id
                    JOIN sys.columns c ON c.object_id = v.object_id
                    JOIN sys.types tp  ON c.user_type_id = tp.user_type_id
                    WHERE s.name NOT IN (
                        'sys','INFORMATION_SCHEMA','guest','db_owner',
                        'db_accessadmin','db_securityadmin','db_ddladmin',
                        'db_backupoperator','db_datareader','db_datawriter',
                        'db_denydatareader','db_denydatawriter'
                    )
                    ORDER BY s.name, v.name, c.column_id
                """)).fetchall()

                cur_view = None
                for row in view_rows:
                    key = f"{row.schema_name}.{row.table_name}"
                    if key != cur_view:
                        cur_view = key
                        tables.append({
                            "schema":    row.schema_name,
                            "name":      row.table_name,
                            "full_name": key,
                            "is_view":   True,
                            "columns":   [],
                        })
                    tables[-1]["columns"].append({"name": row.col_name, "type": row.col_type})

            else:
                # MySQL / PostgreSQL: use inspector (faster than MSSQL)
                from sqlalchemy import inspect as _inspect
                inspector = _inspect(engine)
                for tname in inspector.get_table_names():
                    try:
                        cols_raw = inspector.get_columns(tname)
                        pk_cols = set(inspector.get_pk_constraint(tname).get("constrained_columns", []))
                    except Exception:
                        continue
                    columns = []
                    for c in cols_raw:
                        col_type = str(c["type"]).split("(")[0]
                        entry = {"name": c["name"], "type": col_type}
                        if c["name"] in pk_cols:
                            entry["pk"] = True
                        columns.append(entry)
                    tables.append({
                        "schema": "", "name": tname, "full_name": tname, "columns": columns,
                    })
    finally:
        engine.dispose()

    return {
        "db_type":  db_type,
        "database": conn.database,
        "tables":   tables,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def schema_json_to_text(schema_json: dict, max_tables: int = 120) -> str:
    """Renders a schema JSON dict to the compact text format used by the AI prompt."""
    db_type  = schema_json.get("db_type", "")
    database = schema_json.get("database", "")
    tables   = schema_json.get("tables", [])

    lines = [f"Datenbank: {database} ({db_type})"]
    for tbl in tables[:max_tables]:
        # „Sicht" statt „Tabelle": das Modell soll wissen, dass die Joins darin
        # schon erledigt sind — genau dafür hat JTL sie angelegt.
        art = "Sicht" if tbl.get("is_view") else "Tabelle"
        # Der Füllstand gehört in den Prompt: „0 Zeilen" ist die knappste Art,
        # dem Modell zu sagen, dass es diese Tabelle nicht brauchen kann. Ohne
        # das rät es Spalten in Tabellen zusammen, in denen nie etwas stand.
        n = tbl.get("rows")
        fuellstand = f" ({n:,} Zeilen)".replace(",", ".") if isinstance(n, int) else ""
        if n == 0:
            fuellstand = " (LEER – enthält keine Daten)"
        lines.append(f"\n{art} {tbl['full_name']}:{fuellstand}")
        for c in tbl["columns"]:
            flags = []
            if c.get("pk"):
                flags.append("PK")
            flag_str = f"  [{','.join(flags)}]" if flags else ""
            lines.append(f"  {c['name']} {c['type']}{flag_str}")
            if c.get("fk"):
                lines.append(f"    → FK: {c['fk']}")
    return "\n".join(lines)


# Column names that are internal/system fields — excluded from AI context to reduce noise.
# dErstellt steht bewusst NICHT hier: in JTL ist das das fachliche Belegdatum
# (Rechnungs-/Bestelldatum), ohne das sich kein Zeitraum filtern lässt.
_SYSTEM_COL_LOWER = {
    "browversion", "dgeaendert", "dmutdat", "nversion",
    "cjtlwawi", "kbenutzerstellt", "kbenutzergeaendert",
    "created_at", "updated_at", "timestamp", "rowversion",
    "npositionslauf", "nlaufnummer",
}


def _filter_system_columns(table: dict) -> dict:
    """Remove internal/system columns to reduce AI prompt noise."""
    cols = [c for c in table.get("columns", []) if c["name"].lower() not in _SYSTEM_COL_LOWER]
    return {**table, "columns": cols or table.get("columns", [])}


def _build_fk_graph(tables: list[dict]) -> tuple[dict, dict]:
    """
    Returns (outgoing, incoming) adjacency dicts keyed by full_name.
    outgoing[A] = set of full_names that A references via FK.
    incoming[A] = set of full_names that reference A via FK.
    FK column format in schema: "dbo.tLieferant.kLieferant"
    """
    outgoing: dict[str, set] = {}
    incoming: dict[str, set] = {}
    for tbl in tables:
        key = tbl["full_name"]
        outgoing.setdefault(key, set())
        incoming.setdefault(key, set())
        for col in tbl.get("columns", []):
            fk = col.get("fk", "")
            if not fk:
                continue
            # "dbo.tLieferant.kLieferant" → ref_table = "dbo.tLieferant"
            parts = fk.rsplit(".", 1)
            if len(parts) == 2:
                ref = parts[0]
                outgoing[key].add(ref)
                incoming.setdefault(ref, set()).add(key)
    return outgoing, incoming


# Nur Zahlenschlüssel taugen als Join-Ziel. Ohne diese Prüfung entstehen
# Beziehungen über cName oder dErstellt — die sind in irgendeiner Protokoll-
# tabelle tatsächlich Primärschlüssel, als Join aber Unsinn.
_SCHLUESSEL_TYPEN = {"int", "bigint", "smallint", "tinyint", "integer"}


def _pk_index(tables: list[dict]) -> dict[str, list[str]]:
    """Spaltenname des (einzigen, numerischen) Primärschlüssels → Tabellen."""
    index: dict[str, list[str]] = {}
    for t in tables:
        pks = [c for c in t.get("columns", []) if c.get("pk")]
        if len(pks) != 1:                      # zusammengesetzte PKs taugen nicht als Join-Ziel
            continue
        if (pks[0].get("type") or "").lower() not in _SCHLUESSEL_TYPEN:
            continue
        index.setdefault(pks[0]["name"], []).append(t["full_name"])
    return index


def _namensgleich(schluessel: str, voll_name: str) -> bool:
    """kArtikel ↔ dbo.tArtikel — die JTL-Namenskonvention, k weg, t weg, Rest vergleichen."""
    return voll_name.split(".")[-1].lower().lstrip("t") == schluessel.lower().lstrip("k")


def beziehungen_ableiten(schema_json: dict, von_tabellen: list[str] | None = None,
                         grenze: int = 400) -> list[dict]:
    """
    Beziehungen aus den Schlüsseln ableiten — dieselbe Regel, nach der der
    Mapping-Editor seine Joins vorschlägt, nur für den Schema-Katalog.

    Zwei Quellen:
    - `fk`: echte Fremdschlüssel aus der Datenbank. Zuverlässig, aber die
      JTL-Wawi setzt kaum welche (557 von 1.158 Tabellen).
    - `schluessel`: eine Spalte heißt genauso wie der Primärschlüssel einer
      anderen Tabelle (kArtikel in tRechnungPosition → dbo.tArtikel).

    Die Falle dabei: ein Schlüsselname ist oft NICHT eindeutig — `kArtikel` ist
    Primärschlüssel in sechs Tabellen (auch in tlagerbestand und
    tLagerbestandBackup). Wer da auf Eindeutigkeit besteht, verliert
    ausgerechnet den wichtigsten Join. Deshalb entscheidet bei mehreren
    Kandidaten der Name (_namensgleich); bleibt es uneindeutig, wird die
    Beziehung als „unsicher" samt Alternativen zurückgegeben statt geraten.

    Gibt Kandidaten zurück, schreibt nichts.
    """
    tables = schema_json.get("tables", [])
    pk_index = _pk_index(tables)
    auswahl = [t for t in tables if not von_tabellen or t["full_name"] in set(von_tabellen)]

    kandidaten: list[dict] = []
    gesehen: set[tuple] = set()

    def merken(von_t, von_c, zu_t, zu_c, quelle, alternativen=None):
        schluessel = (von_t, von_c, zu_t, zu_c)
        if schluessel in gesehen or von_t == zu_t:
            return
        gesehen.add(schluessel)
        kandidaten.append({
            "from_table": von_t, "from_col": von_c,
            "to_table": zu_t, "to_col": zu_c,
            "quelle": quelle,
            "alternativen": alternativen or [],
        })

    for tbl in auswahl:
        voll = tbl["full_name"]
        eigene_pks = {c["name"] for c in tbl.get("columns", []) if c.get("pk")}
        for col in tbl.get("columns", []):
            name = col["name"]

            fk = col.get("fk")
            if fk:
                teile = fk.rsplit(".", 1)
                if len(teile) == 2:
                    merken(voll, name, teile[0], teile[1], "fk")
                continue

            if name in eigene_pks or name not in pk_index:
                continue
            ziele = [z for z in pk_index[name] if z != voll]
            if not ziele:
                continue
            if len(ziele) == 1:
                merken(voll, name, ziele[0], name, "schluessel")
            else:
                treffer = [z for z in ziele if _namensgleich(name, z)]
                if len(treffer) == 1:
                    merken(voll, name, treffer[0], name, "schluessel")
                else:
                    merken(voll, name, ziele[0], name, "unsicher", alternativen=ziele[1:])

            if len(kandidaten) >= grenze:
                return kandidaten

    return kandidaten


def _kw_score_against(kw: str, full_name: str, col_str: str) -> int:
    """
    Score keyword against table full_name + column names.
    Handles German plural/compound forms:
    - "rechnungen" → stem "rechnung" found in "tRechnung"  (suffix stripping)
    - "lieferantendaten" → table core "lieferant" found inside keyword  (reverse match)
    """
    kl = kw.lower()
    tname_lower = full_name.lower()
    score = 0

    table_core = tname_lower.split(".")[-1]              # "trechnung" from "dbo.trechnung"
    if len(table_core) > 2 and table_core[0] in "tvk":
        table_core = table_core[1:]                      # "rechnung"

    # 1. Forward: keyword (or stem up to -4 chars) in table name
    matched_name = False
    for stem_len in range(len(kl), max(3, len(kl) - 4), -1):
        stem = kl[:stem_len]
        if stem in tname_lower:
            score += 6 if stem_len == len(kl) else 3
            matched_name = True
            break

    # 1b. Volltreffer: die Tabelle HEISST so. „Artikel" meint dbo.tArtikel und
    #     nicht tArtikelMindestLagerbestandProLager, in dem das Wort auch nur
    #     vorkommt. Ohne diesen Vorzug verdrängen die langen Zusammensetzungen
    #     die Stammtabelle aus dem Prompt (gemessen an „Lagerbestand je Artikel").
    if table_core == kl:
        score += 6

    # 2. Reverse: table core found inside keyword
    #    catches compound keywords: "lieferantendaten" contains "lieferant" from "tLieferant"
    if not matched_name:
        if len(table_core) >= 4 and table_core in kl:
            score += 4

    # 3. Keyword (or stem) in column names
    for stem_len in range(len(kl), max(3, len(kl) - 4), -1):
        stem = kl[:stem_len]
        if stem in col_str:
            score += 2 if stem_len == len(kl) else 1
            break

    return score


# Schemata und Tabellen, die zwar namensähnlich sind, aber nicht zur Fachauswertung
# gehören: Austauschtabellen mit fremden Nummernkreisen (DbeS), Altlasten, Protokolle.
# Ohne Abwertung landet DbeS.tRechnungadresse vor Rechnung.tRechnungAdresse und
# verdrängt bei knappem Platz die richtige Tabelle aus dem Prompt.
# „dal" kam mit den Views dazu: 187 Sichten der internen Zugriffsschicht, die
# jede Fachtabelle noch einmal unter eigenem Namen führen.
_NEBEN_SCHEMATA = {"dbes", "deprecated", "sync", "fulfillmentnetwork", "pf", "bi",
                   "dal", "scx", "worker", "maintenance"}
# „Old" ohne Unterstrich ist JTLs Schreibweise für abgelöste Tabellen:
# Shipping.tPackageOld und tStateOld tragen MEHR Zeilen als die aktuellen und
# gewinnen deshalb jede Bevorzugung nach Füllstand. Wer nach dem Sendungsstatus
# fragt, meint aber die laufenden Daten.
_NEBEN_ENDUNGEN = ("_log", "_history", "_alt", "_backup", "_tmp", "_temp",
                   "old", "archiv", "archive")

# Höchstanteil der Prompt-Plätze, den Sichten belegen dürfen. Sie sind fachlich
# oft die richtige Quelle (Preisliste.vPreislisteNetto, vOffenerPostenRechnung),
# treten aber in Rudeln auf: zu einer Adresse gibt es vStandardRechnungsadresse,
# …Cache, vRechnungAdresse, vRechnungLieferadresse und vRechnungRechnungsadresse.
# Gemessen an „Top 20 Kunden nach Umsatz": ohne Deckel verdrängten sie tkunde
# UND tAdresse aus dem Prompt.
_VIEW_ANTEIL = 0.5

# Beiwerk-Tabellen: Übersetzungen, freie Attribute, Drucktexte, Shop-Zuordnungen.
# Sie tragen den Namen der Fachtabelle im eigenen (tKundenGruppeSprache,
# tKundenGruppeAttribute, tShopMappingKundengruppe) und verdrängen deshalb bei
# einer Kundenfrage reihenweise die Tabellen, in denen die Fachdaten stehen.
# Gemessen an „alle Kunden mit kundenindividuellen Sonderpreisen": sechs der
# fünfzehn Prompt-Plätze gingen an solche Tabellen, tPreis war nicht dabei —
# das Modell griff daraufhin zu tKundenGruppeAttribute und zählte Attribute
# statt Preise.
_BEIWERK_NAMENSTEILE = ("sprache", "attribut", "drucktext", "shopmapping",
                        "ranking", "merkmal",
                        # Einstell- und Austauschtabellen: tPreisImportVorlage,
                        # tPreiskalkulationSetting, tPreiskonfiguration. Sie
                        # tragen die Fachnamen im eigenen, enthalten aber keine
                        # auswertbaren Daten.
                        "vorlage", "setting", "konfig", "import", "export",
                        # Mit den Views dazugekommen: „…Cache"-Sichten sind
                        # Kopien der Sicht daneben und besetzen nur Plätze.
                        "cache")


def _nebenschauplatz_malus(full_name: str, score: int) -> int:
    """Halbiert den Treffer-Score von Austausch-, Protokoll- und Altlast-Tabellen,
    damit die Fachtabellen zuerst im Prompt landen. Ausschließen wäre falsch –
    manchmal will jemand genau dort hineinsehen –, aber der Vortritt gehört den
    Belegtabellen."""
    if score <= 0:
        return score
    teile = full_name.lower().split(".")
    schema = teile[0] if len(teile) > 1 else ""
    name = teile[-1]
    if schema in _NEBEN_SCHEMATA or name.endswith(_NEBEN_ENDUNGEN):
        return max(1, score // 2)
    if any(teil in name for teil in _BEIWERK_NAMENSTEILE):
        return max(1, score // 2)
    return score


def filter_schema_with_fk_expansion(
    schema_json: dict, keywords: list[str], max_tables: int = 15
) -> tuple[dict, list[dict]]:
    """
    Returns (filtered_schema_json, table_info_list).
    Finds keyword-matching tables, expands to FK neighbors (depth 1),
    removes system columns, caps at max_tables.
    table_info_list entries have extra keys: match_type, score, col_count.
    """
    kw_lower = [k.lower() for k in keywords if len(k) > 2]
    all_tables = schema_json.get("tables", [])
    table_by_key = {t["full_name"]: t for t in all_tables}

    # Score tables by keyword match
    kw_scored: dict[str, int] = {}
    for tbl in all_tables:
        col_str = " ".join(c["name"].lower() for c in tbl.get("columns", []))
        score = sum(
            _kw_score_against(kw, tbl["full_name"], col_str) * (2 if kw in _LEITBEGRIFFE else 1)
            for kw in kw_lower
        )
        score = _nebenschauplatz_malus(tbl["full_name"], score)
        if score > 0:
            kw_scored[tbl["full_name"]] = score

    outgoing, incoming = _build_fk_graph(all_tables)

    # FK neighbors of keyword-matched tables
    fk_neighbors: dict[str, tuple[str, int]] = {}
    for key in kw_scored:
        for ref in outgoing.get(key, set()):
            if ref not in kw_scored and ref in table_by_key:
                fk_neighbors.setdefault(ref, ("fk_parent", 2))
        for child in incoming.get(key, set()):
            if child not in kw_scored and child in table_by_key:
                fk_neighbors.setdefault(child, ("fk_child", 1))

    result: list[dict] = []

    view_deckel = max(1, int(max_tables * _VIEW_ANTEIL))
    view_platz = 0

    def _rang(eintrag):
        """Gefüllte Tabellen zuerst, innerhalb davon nach Treffer-Güte.

        Zwei Ebenen statt Punkteabzug: Ein leeres Objekt soll nicht *etwas*
        schlechter dastehen, sondern erst dann einen Platz bekommen, wenn keine
        gefüllte Tabelle mehr wartet. Ausschließen wäre falsch – manchmal fragt
        jemand genau danach –, aber der Vortritt gehört dem, wo Daten liegen.
        """
        key, score = eintrag
        n = (table_by_key.get(key) or {}).get("rows")
        leer = (n == 0)
        return (0 if leer else 1, score)

    for key, score in sorted(kw_scored.items(), key=_rang, reverse=True):
        if key in table_by_key:
            if table_by_key[key].get("is_view"):
                if view_platz >= view_deckel:
                    continue
                view_platz += 1
            t = _filter_system_columns(table_by_key[key])
            result.append({**t, "_match_type": "keyword", "_score": score})

    for key, (mtype, score) in sorted(fk_neighbors.items(), key=lambda x: -x[1][1]):
        if key in table_by_key:
            t = _filter_system_columns(table_by_key[key])
            result.append({**t, "_match_type": mtype, "_score": score})

    if not result:
        result = [_filter_system_columns(t) for t in all_tables[:max_tables]]
        for r in result:
            r["_match_type"] = "fallback"
            r["_score"] = 0

    result = result[:max_tables]

    clean_tables = [{k: v for k, v in t.items() if not k.startswith("_")} for t in result]
    filtered_schema = {**schema_json, "tables": clean_tables}

    table_info = [
        {
            "full_name":  t["full_name"],
            "schema":     t.get("schema", ""),
            "name":       t["name"],
            "col_count":  len(t["columns"]),
            "match_type": t["_match_type"],
            "score":      t["_score"],
            "columns":    t["columns"],
        }
        for t in result
    ]

    return filtered_schema, table_info


def filter_schema_by_keywords(schema_json: dict, keywords: list[str], max_tables: int = 30) -> dict:
    """
    Returns a copy of schema_json with only tables relevant to the given keywords.
    Matches against table names and column names (case-insensitive).
    Falls back to first max_tables tables if no match found.
    """
    if not keywords:
        filtered = schema_json.get("tables", [])[:max_tables]
        return {**schema_json, "tables": filtered}

    kw_lower = [k.lower() for k in keywords if len(k) > 2]
    scored = []
    for tbl in schema_json.get("tables", []):
        col_str = " ".join(c["name"].lower() for c in tbl.get("columns", []))
        score = sum(
            _kw_score_against(kw, tbl["full_name"], col_str) * (2 if kw in _LEITBEGRIFFE else 1)
            for kw in kw_lower
        )
        if score > 0:
            scored.append((score, tbl))

    if scored:
        scored.sort(key=lambda x: -x[0])
        filtered = [t for _, t in scored[:max_tables]]
    else:
        filtered = schema_json.get("tables", [])[:max_tables]

    return {**schema_json, "tables": filtered}


# Geschäftsdeutsch → Tabellen-Vokabular. Nutzer fragen nach "Verkäufen nach
# Postleitzahl"; die Tabellen heißen tRechnung und cPLZ. Ohne diese Brücke
# gewinnt bei der Stichwortsuche irgendeine Tabelle mit zufälliger Namensähnlichkeit
# (gemessen: "Verkäufe … Postleitzahl" traf in einer JTL-DB dbo.ebay_itemcomp_bike),
# das Modell sieht die richtige Tabelle nie und erfindet daraufhin Spaltennamen.
_FACHBEGRIFFE: dict[str, tuple[str, ...]] = {
    "verkauf":       ("rechnung", "auftrag"),
    "verkäufe":      ("rechnung", "auftrag"),
    "verkaeufe":     ("rechnung", "auftrag"),
    "umsatz":        ("rechnung", "eckdaten"),
    "erlös":         ("rechnung",),
    "erloes":        ("rechnung",),
    "beleg":         ("rechnung", "auftrag"),
    "gutschrift":    ("gutschrift", "rechnung"),
    "storno":        ("rechnung",),
    "postleitzahl":  ("adresse", "plz"),
    "plz":           ("adresse", "plz"),
    "ort":           ("adresse",),
    "stadt":         ("adresse",),
    "land":          ("adresse",),
    "region":        ("adresse",),
    "bundesland":    ("adresse",),
    "anschrift":     ("adresse",),
    "straße":        ("adresse",),
    "strasse":       ("adresse",),
    "kunde":         ("kunde", "adresse"),
    "kunden":        ("kunde", "adresse"),
    "käufer":        ("kunde", "adresse"),
    "lieferant":     ("lieferant",),
    "lieferanten":   ("lieferant",),
    "artikel":       ("artikel",),
    "produkt":       ("artikel",),
    "ware":          ("artikel",),
    "bestand":       ("lager", "bestand", "artikel"),
    "lagerbestand":  ("lager", "bestand"),
    "bestellung":    ("bestellung", "auftrag"),
    "einkauf":       ("bestellung", "lieferant"),
    "angebot":       ("auftrag",),
    "retoure":       ("retoure", "rma"),
    "rücksendung":   ("retoure", "rma"),
    "versand":       ("versand", "lieferschein"),
    "lieferung":     ("lieferschein", "versand"),
    # Sendungsverfolgung: „Sendung", „zugestellt" und „Paket" trafen vorher
    # keine einzige Tabelle. Eine Frage nach dem Sendungsstatus bekam deshalb
    # Lieferschein-Tabellen und das leere Ticketsystem in den Prompt – und die
    # KI riet einen Statuscode, statt Shipping.tPackage/tState zu benutzen.
    # „Lieferschein" traf die Tabelle zwar über die Wortstamm-Suche, aber nur mit
    # halbem Gewicht – bei zwölf Plätzen reichte das nicht gegen ein Dutzend
    # namensähnlicher Versand-Nebentabellen. Als Fachbegriff zählt er doppelt.
    "lieferschein":  ("lieferschein", "versand"),
    "sendung":       ("versand", "package", "lieferschein"),
    "sendungsstatus": ("versand", "package", "state"),
    "sendungsverfolgung": ("package", "state", "versand"),
    "zugestellt":    ("package", "state", "versand"),
    "zustellung":    ("package", "state", "versand"),
    "zustelldatum":  ("package", "state"),
    "paket":         ("package", "versand"),
    "pakete":        ("package", "versand"),
    "tracking":      ("package", "state", "tracking"),
    "trackingnummer": ("package", "versand"),
    "laufzeit":      ("versand", "package", "state"),
    "transportzeit": ("versand", "package", "state"),
    "lieferzeit":    ("versand", "lieferschein", "package"),
    "logistiker":    ("logistik", "versand"),
    "versanddienstleister": ("logistik", "versand"),
    "paketdienst":   ("logistik", "versand"),
    "zahlung":       ("zahlung",),
    "zahlungen":     ("zahlung",),
    "mahnung":       ("mahnung", "eckdaten"),
    "betrag":        ("netto", "brutto", "wert"),
    "rechnungsbetrag": ("rechnung", "netto", "wert"),
    "preis":         ("preis", "preisdetail"),
    "preisliste":    ("preis", "preisdetail"),
    "verkaufspreis": ("preis", "preisdetail"),
    "sonderpreis":   ("sonderpreis", "preis", "preisdetail"),
    "aktionspreis":  ("sonderpreis", "preis"),
    "kundenpreis":   ("preis", "preisdetail"),
    "staffel":       ("preisdetail", "preis"),
    "staffelpreis":  ("preisdetail", "preis"),
    "kundenindividuell": ("preis", "preisdetail"),
    "individualpreis":   ("preis", "preisdetail"),
    "rabatt":        ("preis", "kundengruppe"),
    "menge":         ("anzahl", "menge"),
    "anzahl":        ("anzahl",),
    "mitarbeiter":   ("benutzer", "mitarbeiter"),
    "verkäufer":     ("benutzer", "vertreter"),
}

# Die Zielbegriffe der Brücke oben. Wer „Sonderpreise" schreibt, meint die
# Preistabellen und nicht irgendeine Tabelle, in deren Namen zufällig „Kunden"
# vorkommt — deshalb wiegt ein solcher Treffer beim Ranking doppelt.
_LEITBEGRIFFE: frozenset[str] = frozenset(
    b for ziele in _FACHBEGRIFFE.values() for b in ziele
)

# Deutsche Beugung: „Sonderpreise", „Sonderpreisen", „Kundenpreises" sollen
# denselben Eintrag treffen wie „Sonderpreis". rstrip() allein reichte nicht —
# es entfernt nur wiederholte Einzelzeichen, „preise" blieb dadurch ungebrückt
# und die Preistabellen fehlten im Prompt.
_NACHSILBEN = ("", "n", "en", "e", "s", "es", "er", "em", "ne", "nen")


def _fachbegriff(wort: str) -> tuple[str, ...] | None:
    """Sucht den Fachbegriff zu einem Wort, auch in gebeugter Form."""
    treffer = _FACHBEGRIFFE.get(wort)
    if treffer:
        return treffer
    for silbe in _NACHSILBEN:
        if silbe and wort.endswith(silbe):
            treffer = _FACHBEGRIFFE.get(wort[: -len(silbe)])
            if treffer:
                return treffer
    return None


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful words from a description for schema filtering.

    Ergänzt deutsche Fachbegriffe um die Wortstämme, unter denen die Tabellen
    tatsächlich geführt werden – siehe _FACHBEGRIFFE.
    """
    import re
    # Split on whitespace and punctuation, keep words >= 3 chars
    words = re.split(r"[\s,;.()\[\]{}\"'/\\|+\-=<>!?@#$%^&*]+", text)
    # Deduplicate, lowercase, filter short/stop words
    STOP = {"und", "oder", "die", "der", "das", "mit", "für", "von", "aus", "alle",
            "the", "and", "for", "with", "from", "all", "bitte", "nach", "eine", "einen",
            "dieses", "diesem", "diesen", "jahr", "jahres", "monat", "heute", "gruppiert",
            "sortiert", "möchte", "moechte", "brauche", "zeige", "liste", "summe"}
    seen = set()
    result = []
    for w in words:
        wl = w.lower()
        if len(wl) < 3 or wl in seen:
            continue
        seen.add(wl)
        # Fachbegriffe zählen auch dann, wenn sie sonst als Stoppwort gälten
        treffer = _fachbegriff(wl)
        if wl not in STOP:
            result.append(wl)
        for ersatz in (treffer or ()):
            if ersatz not in seen:
                seen.add(ersatz)
                result.append(ersatz)
    return result


def rebuild_cache(conn_id: int, db) -> dict:
    """
    Builds a fresh schema JSON for the given connection and saves it to DB.
    Returns the schema dict on success, raises on error.
    """
    from app.models.dataset import DbConnection
    conn = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not conn:
        raise ValueError(f"Connection {conn_id} not found")

    schema = build_schema_json(conn)
    conn.schema_cache     = json.dumps(schema, ensure_ascii=False)
    conn.schema_cached_at = datetime.now(timezone.utc)
    db.commit()
    log.info(f"Schema cache rebuilt for connection {conn_id} ({len(schema['tables'])} tables)")

    # Katalog-Einträge für neue Tabellen anlegen
    try:
        from app.models.schema_catalog import SchemaTableMeta
        existing = {
            m.table_full_name
            for m in db.query(SchemaTableMeta.table_full_name)
                       .filter_by(connection_id=conn_id).all()
        }
        new_entries = [
            SchemaTableMeta(connection_id=conn_id, table_full_name=t["full_name"])
            for t in schema.get("tables", [])
            if t.get("full_name") and t["full_name"] not in existing
        ]
        if new_entries:
            db.add_all(new_entries)
            db.commit()
            log.info(f"Schema catalog: {len(new_entries)} neue Tabellen-Einträge angelegt")
    except Exception as e:
        log.warning(f"Katalog-Sync fehlgeschlagen: {e}")

    return schema


def get_cached_schema(conn) -> dict | None:
    """Returns the parsed schema JSON from conn.schema_cache, or None if not cached."""
    if not getattr(conn, "schema_cache", None):
        return None
    try:
        return json.loads(conn.schema_cache)
    except Exception:
        return None

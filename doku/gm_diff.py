# -*- coding: utf-8 -*-
"""Golden-Master-Diff gegen eine JTL-Wawi.

Wozu: bevor wir selbst in JTL-Tabellen schreiben, wollen wir wissen, was JTL beim
selben Vorgang schreibt — nicht raten. Also: Zustand merken, den Vorgang in der
Wawi von Hand anlegen, danach die Datenbank fragen, was sich geändert hat.

Das geht, weil praktisch jede JTL-Tabelle eine `rowversion`-Spalte hat und
`@@DBTS` der datenbankweite Zähler dazu ist. Alles mit rowversion > Grundstand
wurde seit dem Merken angefasst (eingefügt ODER geändert). Zusammen mit den
Zeilenzahlen je Tabelle trennt sich daraus INSERT von UPDATE.

    # 1. Grundstand merken (VOR dem manuellen Anlegen in JTL)
    docker compose exec backend python /tmp/gm_diff.py baseline 6

    # 2. Jetzt in der JTL-Wawi den Vorgang von Hand anlegen

    # 3. Nachsehen, was JTL geschrieben hat
    docker compose exec backend python /tmp/gm_diff.py diff 6

Hinweise:
- `tUserSession`, `tUserLayout`, `tUserSetting` u. ä. tauchen als Rauschen auf —
  das ist der JTL-Client, der beim Klicken seine Oberfläche speichert, nicht der
  Vorgang. Solche Tabellen stehen in RAUSCHEN und werden getrennt ausgewiesen.
- Nur lesend. Das Skript schreibt ausschließlich seine eigenen JSON-Dateien.
- Die Ablage liegt unter /app/uploads (Docker-Volume), überlebt also den Container.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text                    # noqa: E402
from app.core.database import SessionLocal                    # noqa: E402
from app.models.dataset import DbConnection                   # noqa: E402
from app.services.db_service import get_engine_str            # noqa: E402

ABLAGE = Path("/app/uploads")

# Tabellen, die der JTL-Client beim bloßen Klicken beschreibt. Kein Teil des
# fachlichen Vorgangs — sonst sucht man sich an der Oberfläche tot.
# tBenutzer/tOptions/tWidgetLayout stehen hier, weil ein blosses Anmelden am
# JTL-Client sie anfasst – beim ersten Lauf gegen die Test-Wawi waren genau das
# die einzigen Treffer, ohne dass irgendein Vorgang angelegt worden war.
RAUSCHEN = {"tUserSession", "tUserLayout", "tUserSetting", "tBenutzerEinstellung",
            "tBenutzer", "tOptions", "tWidgetLayout", "tUserControlSetting",
            "tSuchIndex", "tLogEintrag", "tSystemLog", "tJobqueue", "tWorkflowLog"}

# Tabellen, deren neue Zeilen vollständig ausgegeben werden (Feld für Feld).
VOLLDUMP = ("tEingangsrechnung", "tEingangsrechnungPos",
            "tEingangsrechnungZusatzkosten", "tEingangsrechnungPosZusatzkosten",
            "tLaufendeNummern",
            # Wareneingang/Bestellung: hier haengt die Bewertung. Der gleitende
            # Durchschnitts-EK wird laut spWarenlagerEingangSchreiben ueber
            # nGLDBerechnungMitEingangsrechnung an tWarenLagerEingang gesteuert.
            "tWarenLagerEingang", "tLieferantenBestellung", "tLieferantenBestellungPos",
            "tArtikelHistory")


def engine(conn_id: int):
    db = SessionLocal()
    c = db.query(DbConnection).filter(DbConnection.id == conn_id).first()
    if not c:
        raise SystemExit(f"Verbindung {conn_id} gibt es nicht.")
    print(f"Verbindung {conn_id}: {c.name} ({c.host}/{c.database})")
    return create_engine(get_engine_str(c), pool_pre_ping=True)


def rowversion_tabellen(con):
    """Alle Benutzertabellen mit ihrer rowversion-Spalte (Typ timestamp)."""
    return {r[0]: r[1] for r in con.execute(text("""
        SELECT t.name, c.name
        FROM sys.tables t
        JOIN sys.columns c ON c.object_id = t.object_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE ty.name = 'timestamp' AND SCHEMA_NAME(t.schema_id) = 'dbo'
    """)).fetchall()}


def zeilenzahlen(con):
    """Zeilen je Tabelle aus den Systemsichten — schnell, ohne COUNT(*) je Tabelle."""
    return {r[0]: int(r[1]) for r in con.execute(text("""
        SELECT t.name, SUM(p.rows)
        FROM sys.tables t
        JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0, 1)
        WHERE SCHEMA_NAME(t.schema_id) = 'dbo'
        GROUP BY t.name
    """)).fetchall()}


def _jsonfest(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return "0x" + v.hex()
    return v


def durchschnitts_ek(con):
    """Durchschnittlicher Netto-EK je Artikel.

    Zusatzkostenarten tragen in JTL das Kennzeichen „Beeinflusst durchschnittlichen
    Netto-EK" (Spalte nGLD). Ob und wann JTL diesen Wert tatsächlich fortschreibt,
    sieht man nur, wenn man ihn vorher kennt: die rowversion verrät, DASS tArtikel
    angefasst wurde, nicht um wie viel sich der Wert bewegt hat.
    """
    return {int(k): (float(v) if v is not None else None) for k, v in con.execute(text(
        "SELECT kArtikel, fEKNetto FROM dbo.tArtikel")).fetchall()}


def baseline(conn_id: int):
    e = engine(conn_id)
    with e.connect() as con:
        dbts = con.execute(text("SELECT CAST(@@DBTS AS BIGINT)")).scalar()
        zahlen = zeilenzahlen(con)
        ek = durchschnitts_ek(con)
    ziel = ABLAGE / f"gm_baseline_{conn_id}.json"
    ziel.write_text(json.dumps({"conn_id": conn_id, "dbts": int(dbts),
                                "zeitpunkt": datetime.now().isoformat(),
                                "zeilen": zahlen,
                                "ek": {str(k): v for k, v in ek.items()}}, indent=1))
    print(f"\nGrundstand gemerkt: @@DBTS = {dbts}, {len(zahlen)} Tabellen, "
          f"{len(ek)} Artikel-EKs")
    print(f"→ {ziel}")
    print("\nJetzt den Vorgang in der JTL-Wawi von Hand anlegen, danach 'diff' laufen lassen.")


def diff(conn_id: int):
    quelle = ABLAGE / f"gm_baseline_{conn_id}.json"
    if not quelle.exists():
        raise SystemExit(f"Kein Grundstand für Verbindung {conn_id} – erst 'baseline' laufen lassen.")
    grund = json.loads(quelle.read_text())
    dbts, alt = grund["dbts"], grund["zeilen"]
    print(f"Grundstand von {grund['zeitpunkt']}, @@DBTS = {dbts}\n")

    e = engine(conn_id)
    treffer, rauschen, volldump = [], [], {}
    with e.connect() as con:
        neu = zeilenzahlen(con)
        tabellen = rowversion_tabellen(con)
        ek_alt = {int(k): v for k, v in (grund.get("ek") or {}).items()}
        ek_neu = durchschnitts_ek(con)
        for tab, rvspalte in sorted(tabellen.items()):
            try:
                n = con.execute(text(
                    f"SELECT COUNT(*) FROM dbo.[{tab}] "
                    f"WHERE CAST([{rvspalte}] AS BIGINT) > :d"), {"d": dbts}).scalar()
            except Exception:
                continue          # Sicht/Berechtigung/Sonderfall – überspringen
            if not n:
                continue
            delta = neu.get(tab, 0) - alt.get(tab, 0)
            eintrag = {"tabelle": tab, "angefasst": int(n), "zeilen_delta": int(delta),
                       "deutung": "INSERT" if delta >= n else
                                  ("INSERT+UPDATE" if delta > 0 else "UPDATE")}
            (rauschen if tab in RAUSCHEN else treffer).append(eintrag)

            if tab in VOLLDUMP:
                rs = con.execute(text(
                    f"SELECT * FROM dbo.[{tab}] "
                    f"WHERE CAST([{rvspalte}] AS BIGINT) > :d"), {"d": dbts})
                cols = list(rs.keys())
                volldump[tab] = [{k: _jsonfest(v) for k, v in zip(cols, row)}
                                 for row in rs.fetchall()]

    print("=" * 74)
    print("GEÄNDERTE TABELLEN (fachlich)")
    print("=" * 74)
    if not treffer:
        print("  keine – wurde der Vorgang wirklich angelegt?")
    for t in treffer:
        print(f"  {t['tabelle']:38} {t['angefasst']:4} Zeilen  "
              f"Δ{t['zeilen_delta']:+4}  {t['deutung']}")
    if rauschen:
        print("\nOberflächen-Rauschen (JTL-Client, nicht der Vorgang):")
        for t in rauschen:
            print(f"  {t['tabelle']:38} {t['angefasst']:4} Zeilen")

    for tab, zeilen in volldump.items():
        if not zeilen:
            continue
        print("\n" + "=" * 74)
        print(f"NEUE/GEÄNDERTE ZEILEN: {tab}")
        print("=" * 74)
        for z in zeilen:
            # Bewusst ALLE Felder, auch leere und Nullen: beim Golden Master ist
            # `nStatus = 0` genauso Beweis wie ein gefuellter Wert – und ob JTL ein
            # Feld als '' oder als NULL hinterlaesst, muessen wir nachmachen.
            for k, v in z.items():
                print(f"   {k:34} {v!r}")
            print("   " + "-" * 60)

    ek_bewegt = [{"kArtikel": k, "vorher": ek_alt.get(k), "nachher": v,
                  "differenz": round((v or 0) - (ek_alt.get(k) or 0), 4)}
                 for k, v in ek_neu.items()
                 if k in ek_alt and (v or 0) != (ek_alt.get(k) or 0)]
    print("\n" + "=" * 74)
    print("DURCHSCHNITTLICHER NETTO-EK (tArtikel.fEKNetto)")
    print("=" * 74)
    if not ek_bewegt:
        print("  unverändert – JTL hat den Durchschnitts-EK bei diesem Vorgang NICHT")
        print("  fortgeschrieben (trotz „Beeinflusst durchschnittlichen Netto-EK: Ja\")")
    for b in ek_bewegt[:25]:
        print(f"   kArtikel {b['kArtikel']:8}  {b['vorher']} → {b['nachher']}  "
              f"({b['differenz']:+.4f})")
    if len(ek_bewegt) > 25:
        print(f"   … und {len(ek_bewegt) - 25} weitere")

    ziel = ABLAGE / f"gm_result_{conn_id}.json"
    ziel.write_text(json.dumps({"tabellen": treffer, "rauschen": rauschen,
                                "zeilen": volldump, "ek_bewegt": ek_bewegt},
                               indent=1, ensure_ascii=False))
    print(f"\n→ vollständig in {ziel}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("baseline", "diff"):
        raise SystemExit(__doc__)
    globals()[sys.argv[1]](int(sys.argv[2]))

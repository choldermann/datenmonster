"""
Verdichtet die synthetische Demo-Firma (eazybusiness_synth, „MediVersa“) zu der
Datei, die die Live-Demo auf monstersuite.de/jtl-wawi/demo/ im Browser rechnet.

Rechenweg wie im Geschäftsführer-Cockpit (jtl_gf_cockpit.json, m_top_kunden):
Rechnung.vRechnung ohne Stornos, gesperrte Kunden ausgenommen, Netto =
fAnzahl × fVkNetto, Rohertrag = fAnzahl × (fVkNetto − EK der Position, sonst
Artikel-EK). Alle Daten sind erfunden; ausgegeben werden nur Summen sowie die
(erfundenen) Namen der umsatzstärksten Kunden.

Lauf:  docker compose exec -T backend python -m tools.demo_daten.web_demo_export > daten.json
"""
import json
import sys
from collections import defaultdict
from datetime import date, timedelta

import sqlalchemy as sa

sys.path.insert(0, "/app")
from app.core.database import SessionLocal  # noqa: E402
from app.models.dataset import DbConnection  # noqa: E402
from app.services.mapping_service import _get_sql_engine  # noqa: E402

BASIS = """
  FROM Rechnung.vRechnung RE
  JOIN Rechnung.tRechnungPosition POS ON POS.kRechnung = RE.kRechnung
  LEFT JOIN dbo.tArtikel A ON A.cArtNr = POS.cArtNr
  WHERE ISNULL(RE.nStorno, 0) = 0
    AND RE.kKunde NOT IN (SELECT kKunde FROM dbo.tKunde WHERE cSperre = 'Y')
"""
NETTO = "POS.fAnzahl * POS.fVkNetto"
DB = "POS.fAnzahl * (POS.fVkNetto - COALESCE(NULLIF(POS.fEkNetto, 0), A.fEKNetto, 0))"


def main():
    db = SessionLocal()
    conn = db.query(DbConnection).filter(DbConnection.database == "eazybusiness_synth").first()
    eng = _get_sql_engine(conn.id)
    q = lambda sql: [dict(r._mapping) for r in eng.connect().execute(sa.text(sql))]  # noqa: E731

    rechnungen = q(f"""SELECT RE.kRechnung, CAST(RE.dErstellt AS DATE) AS d, RE.kKunde,
        SUM({NETTO}) AS netto, SUM({DB}) AS db {BASIS}
        GROUP BY RE.kRechnung, CAST(RE.dErstellt AS DATE), RE.kKunde""")
    wg = q(f"""SELECT CAST(RE.dErstellt AS DATE) AS d, ISNULL(W.cName, 'Ohne Warengruppe') AS wg,
        SUM({NETTO}) AS netto, SUM({DB}) AS db {BASIS.replace('LEFT JOIN dbo.tArtikel A ON A.cArtNr = POS.cArtNr',
        'LEFT JOIN dbo.tArtikel A ON A.cArtNr = POS.cArtNr LEFT JOIN dbo.tWarengruppe W ON W.kWarengruppe = A.kWarengruppe')}
        AND POS.nType = 1
        GROUP BY CAST(RE.dErstellt AS DATE), W.cName""")
    # Bestehende Demo-DB enthält noch „Praxis am Am Markt“ (Generatorfehler, in
    # stammdaten.py behoben) – für die Website glätten, ohne die DB neu zu erzeugen.
    namen = {r["kKunde"]: (r["name"] or "").replace(" am Am ", " am ") for r in q("""
        SELECT RE.kKunde, MAX(LTRIM(RTRIM(ISNULL(NULLIF(LTRIM(RTRIM(ISNULL(RA.cFirma,''))), ''),
               ISNULL(RA.cVorname,'') + ' ' + ISNULL(RA.cName,''))))) AS name
        FROM Rechnung.vRechnung RE JOIN Rechnung.vRechnungRechnungsadresse RA ON RA.kRechnung = RE.kRechnung
        GROUP BY RE.kKunde""")}
    aging = q("""SELECT SortOrder AS s, COUNT(*) AS n, CAST(SUM(fOffenerWert) AS DECIMAL(18,2)) AS summe FROM (
        SELECT E.fOffenerWert,
          CASE WHEN E.dZahlungsziel IS NULL OR E.dZahlungsziel >= CAST(GETDATE() AS DATE) THEN 0
               WHEN DATEDIFF(DAY, E.dZahlungsziel, GETDATE()) <= 30 THEN 1
               WHEN DATEDIFF(DAY, E.dZahlungsziel, GETDATE()) <= 60 THEN 2
               WHEN DATEDIFF(DAY, E.dZahlungsziel, GETDATE()) <= 90 THEN 3 ELSE 4 END AS SortOrder
        FROM Rechnung.vRechnungEckdaten E JOIN Rechnung.vRechnung RE ON RE.kRechnung = E.kRechnung
        WHERE E.fOffenerWert > 0 AND ISNULL(RE.nStorno, 0) = 0) x GROUP BY SortOrder ORDER BY SortOrder""")
    schuldner = q("""SELECT TOP 6 RE.kKunde, CAST(SUM(E.fOffenerWert) AS DECIMAL(18,2)) AS summe,
          MAX(DATEDIFF(DAY, E.dZahlungsziel, GETDATE())) AS tage, COUNT(*) AS n
        FROM Rechnung.vRechnungEckdaten E JOIN Rechnung.vRechnung RE ON RE.kRechnung = E.kRechnung
        WHERE E.fOffenerWert > 0 AND ISNULL(RE.nStorno, 0) = 0 AND E.dZahlungsziel < CAST(GETDATE() AS DATE)
        GROUP BY RE.kKunde ORDER BY SUM(E.fOffenerWert) DESC""")

    heute = max(r["d"] for r in rechnungen)

    def zeitraeume():
        j = heute.year
        yield "ytd", f"{j} bis heute", date(j, 1, 1), heute
        yield "vorjahr", str(j - 1), date(j - 1, 1, 1), date(j - 1, 12, 31)
        # zwölf Monate inklusive des laufenden: Dez. Vorjahr bis heute, wenn heute im November
        m = heute.month - 11
        yield "l12m", "Letzte 12 Monate", date(heute.year - (m <= 0), (m - 1) % 12 + 1, 1), heute
        for quartal in range(1, 5):
            von = date(j, 3 * quartal - 2, 1)
            if von > heute:
                break
            bis = min(date(j + (quartal == 4), (3 * quartal) % 12 + 1, 1) - timedelta(days=1), heute)
            yield f"q{quartal}", f"Q{quartal} {j}", von, bis

    def vj(d):
        try:
            return d.replace(year=d.year - 1)
        except ValueError:          # 29.02.
            return d.replace(year=d.year - 1, day=28)

    def summe(von, bis):
        rs = [r for r in rechnungen if von <= r["d"] <= bis]
        u = sum(float(r["netto"]) for r in rs)
        rohertrag = sum(float(r["db"]) for r in rs)
        kunden = {r["kKunde"] for r in rs}
        return {"umsatz": round(u, 2), "rohertrag": round(rohertrag, 2), "rechnungen": len(rs),
                "kunden": len(kunden), "marge": round(100 * rohertrag / u, 1) if u else None,
                "auftragswert": round(u / len(rs), 2) if rs else None}

    def monate(von, bis):
        aus, m = [], date(von.year, von.month, 1)
        while m <= bis:
            naechster = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
            ende = min(naechster - timedelta(days=1), bis)
            a, b = summe(m, ende), summe(vj(m), vj(ende))
            aus.append({"m": m.strftime("%Y-%m"), "umsatz": a["umsatz"], "rohertrag": a["rohertrag"],
                        "umsatzVJ": b["umsatz"], "rohertragVJ": b["rohertrag"], "teil": ende < naechster - timedelta(days=1)})
            m = naechster
        return aus

    def top_kunden(von, bis):
        jetzt, vorher = defaultdict(float), defaultdict(float)
        rohertrag = defaultdict(float)
        for r in rechnungen:
            if von <= r["d"] <= bis:
                jetzt[r["kKunde"]] += float(r["netto"]); rohertrag[r["kKunde"]] += float(r["db"])
            elif vj(von) <= r["d"] <= vj(bis):
                vorher[r["kKunde"]] += float(r["netto"])
        top = sorted(jetzt, key=jetzt.get, reverse=True)[:10]
        return [{"k": k, "name": namen.get(k, f"Kunde {k}"), "umsatz": round(jetzt[k], 2),
                 "umsatzVJ": round(vorher.get(k, 0), 2), "marge": round(100 * rohertrag[k] / jetzt[k], 1)} for k in top]

    def warengruppen(von, bis):
        u, rohertrag, uvj = defaultdict(float), defaultdict(float), defaultdict(float)
        for r in wg:
            if von <= r["d"] <= bis:
                u[r["wg"]] += float(r["netto"]); rohertrag[r["wg"]] += float(r["db"])
            elif vj(von) <= r["d"] <= vj(bis):
                uvj[r["wg"]] += float(r["netto"])
        return sorted([{"wg": w, "umsatz": round(u[w], 2), "umsatzVJ": round(uvj.get(w, 0), 2),
                        "marge": round(100 * rohertrag[w] / u[w], 1) if u[w] else None} for w in u],
                      key=lambda x: -x["umsatz"])

    perioden, kunden_ids = [], set()
    for key, label, von, bis in zeitraeume():
        tk = top_kunden(von, bis)
        kunden_ids |= {t["k"] for t in tk}
        perioden.append({"key": key, "label": label, "von": von.isoformat(), "bis": bis.isoformat(),
                         "kpi": summe(von, bis), "kpiVJ": summe(vj(von), vj(bis)),
                         "monate": monate(von, bis), "kunden": tk, "warengruppen": warengruppen(von, bis)})

    # Verlauf je Top-Kunde (24 Monate) für den Drilldown
    start = date(heute.year - 2, heute.month, 1)
    verlauf = {}
    for k in kunden_ids:
        je_monat = defaultdict(float)
        for r in rechnungen:
            if r["kKunde"] == k and r["d"] >= start:
                je_monat[r["d"].strftime("%Y-%m")] += float(r["netto"])
        m, reihe = start, []
        while m <= heute:
            reihe.append(round(je_monat.get(m.strftime("%Y-%m"), 0), 2))
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        verlauf[str(k)] = reihe

    stufen = ["Nicht fällig", "1–30 Tage", "31–60 Tage", "61–90 Tage", "über 90 Tage"]
    json.dump({
        "firma": "MediVersa Praxisbedarf GmbH (erfunden)",
        "stand": heute.isoformat(),
        "perioden": perioden,
        "verlaufStart": start.strftime("%Y-%m"),
        "verlauf": verlauf,
        "offenePosten": [{"stufe": stufen[int(a["s"])], "n": a["n"], "summe": float(a["summe"])} for a in aging],
        "schuldner": [{"name": namen.get(s["kKunde"], f"Kunde {s['kKunde']}"), "summe": float(s["summe"]),
                       "tage": s["tage"], "n": s["n"]} for s in schuldner],
    }, sys.stdout, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()

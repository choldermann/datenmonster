"""Erzeugt frontend/src/assets/geo/de_bundeslaender.json.

Quelle: Natural Earth 1:10m „Admin 1 – States, Provinces“ (gemeinfrei),
https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_1_states_provinces.zip
Aufruf: python3 -I tools/geo/de_bundeslaender.py <entpackt>/ne_10m_admin_1_states_provinces <ziel.json>

Bundesländer aus Natural Earth admin-1 (Shapefile) → vereinfachtes GeoJSON. Eigenes Lesen, keine Bibliotheken."""
import struct, json, sys, math
basis, ziel = sys.argv[1], sys.argv[2]

def dbf_lesen(pfad):
    with open(pfad, "rb") as f:
        kopf = f.read(32)
        n, hlen, rlen = struct.unpack("<IHH", kopf[4:12])
        felder = []
        while True:
            d = f.read(32)
            if d[0] == 0x0D: break
            name = d[:11].split(b"\0")[0].decode("ascii")
            felder.append((name, d[16]))
        f.seek(hlen)
        for _ in range(n):
            r = f.read(rlen); pos = 1; rec = {}
            for name, ln in felder:
                rec[name] = r[pos:pos+ln].decode("utf-8", "replace").replace("\x00", " ").strip(); pos += ln
            yield rec

def shp_lesen(pfad):
    with open(pfad, "rb") as f:
        f.seek(100)
        while True:
            k = f.read(8)
            if len(k) < 8: return
            _, laenge = struct.unpack(">ii", k)
            inhalt = f.read(laenge * 2)
            typ = struct.unpack("<i", inhalt[:4])[0]
            if typ == 0: yield []; continue
            nparts, npoints = struct.unpack("<ii", inhalt[36:44])
            parts = struct.unpack(f"<{nparts}i", inhalt[44:44+4*nparts])
            o = 44 + 4*nparts
            pts = [struct.unpack("<dd", inhalt[o+16*i:o+16*i+16]) for i in range(npoints)]
            ringe = [pts[parts[i]:(parts[i+1] if i+1 < nparts else npoints)] for i in range(nparts)]
            yield ringe

def dp(pts, eps):
    if len(pts) < 3: return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2-x1, y2-y1; nrm = math.hypot(dx, dy) or 1e-12
    imax, dmax = 0, -1
    for i in range(1, len(pts)-1):
        x, y = pts[i]
        d = abs(dy*x - dx*y + x2*y1 - y2*x1)/nrm if (dx or dy) else math.hypot(x-x1, y-y1)
        if d > dmax: imax, dmax = i, d
    if dmax <= eps: return [pts[0], pts[-1]]
    return dp(pts[:imax+1], eps)[:-1] + dp(pts[imax:], eps)

def flaeche(r):
    return 0.5*sum(r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1] for i in range(len(r)-1))

NAMEN = {"Bayern","Baden-Württemberg","Berlin","Brandenburg","Bremen","Hamburg","Hessen","Mecklenburg-Vorpommern",
         "Niedersachsen","Nordrhein-Westfalen","Rheinland-Pfalz","Saarland","Sachsen","Sachsen-Anhalt","Schleswig-Holstein","Thüringen"}
feat = []
for rec, ringe in zip(dbf_lesen(basis+".dbf"), shp_lesen(basis+".shp")):
    if rec.get("adm0_a3") != "DEU": continue
    name = (rec.get("name") or "").strip()
    name = {"Freie Hansestadt Bremen": "Bremen"}.get(name, name)
    if name not in NAMEN:
        print("UNBEKANNT:", rec.get("name"), rec.get("name_de")); continue
    # Shapefile: Außenring im Uhrzeigersinn (Fläche < 0), Loch gegen den Uhrzeigersinn (> 0).
    # Ein Loch gehört zum vorangehenden Außenring (Bremen in Niedersachsen, Berlin in Brandenburg).
    polys = []
    for r in ringe:
        aussen = flaeche(r) < 0
        s = dp(r, 0.008)
        s = [[round(x, 3), round(y, 3)] for x, y in s]
        if len(s) < 4: continue
        if aussen:
            if abs(flaeche(s)) < 0.0004: polys.append(None); continue   # Mini-Insel weg (samt Löchern)
            polys.append([s])
        elif polys and polys[-1] is not None:
            polys[-1].append(s)
    polys = [p for p in polys if p]
    # Shapefile: Außenringe im Uhrzeigersinn, Löcher gegen – Löcher kommen bei den Ländern nicht vor
    # (Berlin/Bremen liegen als eigene Länder daneben). d3-geo will Außenringe im Uhrzeigersinn: passt.
    feat.append({"type": "Feature", "properties": {"id": name, "name": name},
                 "geometry": {"type": "MultiPolygon", "coordinates": polys}})
print(len(feat), "Länder:", sorted(f["properties"]["id"] for f in feat))
fehlt = NAMEN - {f["properties"]["id"] for f in feat}
print("fehlt:", fehlt)
json.dump({"type": "FeatureCollection",
           "_quelle": "Natural Earth 1:10m admin-1 (gemeinfrei), vereinfacht ~1 km",
           "features": feat}, open(ziel, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

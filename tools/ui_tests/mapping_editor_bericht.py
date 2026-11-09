"""
Browser-Test: Bericht „Umsatz je Kunde“ im visuellen Mapping-Editor nur mit Maus
und Tastatur bauen – Datasets ziehen, Join per Feld-auf-Feld, LEFT wählen,
Aggregation, Ausdruck, Datenqualität, Excel-Ziel, Vorschau, Speichern, Ausführen.

Entstanden am 09.11.2026 beim Nachhärten des Editors (fand u. a. die still als
INNER laufenden Anti-Joins und die doppelten Feldnamen in den Knoten-Listen).

Voraussetzungen: lokaler Stack läuft (Frontend :5174, Backend :8000), Projekt mit
den Datasets „Kunden“ und „Rechnungen“ – anlegen mit
  docker exec -w /app datenmonster-backend python tests/test_mapping_szenario.py --behalten
und PROJEKT unten auf dessen ID setzen. Token:
  docker exec -i -w /app datenmonster-backend python3 -c "import sys; sys.path.insert(0,'/app'); \
    from app.core.database import SessionLocal; from app.core.security import token_fuer; \
    from app.models.user import User; db=SessionLocal(); \
    print(token_fuer(db.query(User).filter(User.is_admin==True).first()))" > /tmp/ui/token.txt
Lauf (Ordner /tmp/ui enthält dieses Skript und token.txt, Screenshots landen dort):
  docker run --rm --network host -v /tmp/ui:/out -w /out \
    mcr.microsoft.com/playwright/python:v1.49.0-noble \
    sh -c "pip install -q playwright==1.49.0 && python mapping_editor_bericht.py"
Das angelegte Mapping wird am Ende wieder gelöscht.
"""
import sys, json, time
from playwright.sync_api import sync_playwright
T=open("/out/token.txt").read().strip()
PROJEKT = 13   # Projekt mit den Datasets Kunden und Rechnungen
SCHRITTE=int(sys.argv[1]) if len(sys.argv)>1 else 99
n=0
def ziehe(pg, quelle, x, y):
    """HTML5-Drag per Maus: Quelle greifen, in Schritten zum Ziel, loslassen."""
    bb = quelle.bounding_box()
    gx, gy = bb["x"] + max(2, bb["width"]*0.3), bb["y"] + bb["height"]/2
    oben = pg.evaluate("([x,y])=>{const e=document.elementFromPoint(x,y); return e? (e.getAttribute('draggable')||'-')+' '+e.tagName : 'nichts'}", [gx, gy])
    print("GREIFE", round(gx), round(gy), oben)
    pg.mouse.move(gx, gy)
    pg.mouse.down()
    pg.mouse.move(gx + 10, gy + 10, steps=3)
    pg.mouse.move(x, y, steps=15)
    pg.mouse.up()
    pg.wait_for_timeout(800)
def mitte(loc):
    bb = loc.bounding_box(); return bb["x"] + bb["width"]/2, bb["y"] + bb["height"]/2
def shot(pg, name):
    global n; n+=1; pg.screenshot(path=f"/out/{n:02d}_{name}.png")
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1600,"height":1000}, locale="de-DE")
    pg.goto("http://localhost:5174/")
    pg.evaluate("""([t, pid])=>{localStorage.setItem('dm_token',t);
      localStorage.setItem('dm_active_project', JSON.stringify({id:pid,name:'Testprojekt',role:'owner'}));}""", [T, PROJEKT])
    pg.goto("http://localhost:5174/mappings/new"); pg.wait_for_timeout(5000)
    pg.add_style_tag(content="canvas{display:none!important}")
    shot(pg,"start")
    ziehe(pg, pg.get_by_text("Kunden", exact=True).first, 420, 180)
    pg.wait_for_timeout(2500); shot(pg, "kunden")
    ziehe(pg, pg.get_by_text("Rechnungen", exact=True).first, 420, 520)
    pg.wait_for_timeout(3000); shot(pg, "rechnungen")
    kk = pg.locator("div[data-field='1']", has_text="kKunde")
    ziehe(pg, kk.nth(0), *mitte(kk.nth(1)))
    pg.wait_for_timeout(1500); shot(pg, "join")
    pg.get_by_text("INNER", exact=True).first.click(); pg.wait_for_timeout(1000); shot(pg, "join_dialog")
    pg.get_by_text("LEFT", exact=True).first.click(); pg.wait_for_timeout(800)
    print("Join-Dialog schließt nach Auswahl:", pg.get_by_text("Join löschen").count() == 0)
    shot(pg, "left")
    # Palette: Symbol mit Titel ansteuern
    titel = pg.evaluate("""()=>[...document.querySelectorAll('button[title],div[title]')].map(e=>e.title).filter(t=>t)""")
    print("TITEL", titel[:40])
    def palette(name): return pg.locator(f"[title^='{name} –']").first
    pg.evaluate("()=>{const e=document.elementFromPoint(900,450); e.id='dm-flaeche'; return e.outerHTML.slice(0,120)}")
    def platziere(name, x, y):
        fl = pg.locator("#dm-flaeche").bounding_box()
        palette(name).drag_to(pg.locator("#dm-flaeche"), target_position={"x": x - fl["x"], "y": y - fl["y"]})
        pg.wait_for_timeout(800)
    platziere("Aggregation", 700, 130)
    shot(pg, "agg")
    agg = pg.locator("div[style*=\"position: absolute\"]", has=pg.get_by_text("Feld hinzufügen")).last
    for _ in range(4):
        agg.get_by_text("Feld hinzufügen").click(); pg.wait_for_timeout(300)
    sel = agg.locator("select")
    print("SELECTS", sel.count(), [sel.nth(i).locator("option").all_inner_texts() for i in range(min(2, sel.count()))])
    print("INPUTS", agg.locator("input").count())
    shot(pg, "agg_felder")
    def agg_zeile(i, eingabe, funktion, ausgabe):
        sel = agg.locator("select")
        sel.nth(2*i).select_option(label=eingabe)
        sel.nth(2*i+1).select_option(label=funktion)
        inp = agg.locator("input").nth(i)
        inp.fill(ausgabe)
    agg_zeile(0, "Kunden.kKunde", "GROUP BY", "kKunde")
    agg_zeile(1, "cName", "GROUP BY", "cName")
    agg_zeile(2, "fBetrag", "SUM", "Umsatz")
    agg_zeile(3, "kRechnung", "COUNT", "Anzahl")
    pg.wait_for_timeout(800); shot(pg, "agg_gefuellt")
    pg.get_by_role("button", name="Neues Ziel").last.click(); pg.wait_for_timeout(1000); shot(pg, "ziel_dialog")
    pg.get_by_placeholder("z.B. Kunden-Export").fill("Umsatz je Kunde")
    pg.get_by_role("button", name="Excel", exact=True).click()
    pg.get_by_role("button", name="Ziel erstellen").click(); pg.wait_for_timeout(1000)
    shot(pg, "ziel_angelegt")
    # Ausgänge der Aggregation (Punkte rechts) auf die Zielliste ziehen
    punkte = agg.locator("div[draggable='true']")
    print("AGG-PUNKTE", punkte.count())
    for i in range(punkte.count()):
        ablage = pg.get_by_text("Feld hier ablegen").first
        ziehe(pg, punkte.nth(i), *mitte(ablage))
    pg.wait_for_timeout(1000); shot(pg, "felder_zugeordnet")
    platziere("Expression", 640, 400)
    ex = pg.locator("div[style*='position: absolute']", has=pg.get_by_text("Formelfeld hinzufügen")).last
    ex.get_by_text("Formelfeld hinzufügen").click(); pg.wait_for_timeout(300)
    fe = ex.locator("input")
    print("EXPR-INPUTS", fe.count(), [fe.nth(i).get_attribute("placeholder") for i in range(fe.count())])
    fe.nth(fe.count()-2).fill("Kategorie")
    fe.nth(fe.count()-1).fill("IF_({Umsatz} >= 100, 'A-Kunde', 'B-Kunde')")
    pg.wait_for_timeout(300)
    ziehe(pg, ex.locator("div[draggable='true']").last, *mitte(pg.get_by_text("Feld hier ablegen").first))
    platziere("Datenqualität", 640, 640)
    dq = pg.locator("div[style*='position: absolute']", has=pg.get_by_text("Regel hinzufügen")).last
    dq.get_by_text("Regel hinzufügen").click(); pg.wait_for_timeout(300)
    di = dq.locator("input"); ds = dq.locator("select")
    print("DQ-INPUTS", di.count(), [di.nth(i).get_attribute("placeholder") for i in range(di.count())], "SELECTS", ds.count(), ds.first.locator("option").all_inner_texts()[:8])
    shot(pg, "knoten_da")
    dq.get_by_placeholder("Feldname").fill("cMail")
    ds.first.select_option(label="E-Mail")
    dq.get_by_placeholder("Fehlermeldung (optional)").fill("E-Mail ungültig")
    ziehe(pg, dq.locator("div[draggable='true']").first, *mitte(pg.get_by_text("Feld hier ablegen").first))
    pg.wait_for_timeout(800)
    pg.locator("span", has_text="Vorschau").filter(has_text="▶").first.click(); pg.wait_for_timeout(5000)
    shot(pg, "vorschau")
    print("ZIELFELDER", pg.locator("text=DIRECT").count())
    pg.get_by_role("button", name="Speichern").click(); pg.wait_for_timeout(2500)
    print("URL", pg.url)
    shot(pg, "gespeichert")
    vorher = pg.evaluate("()=>Date.now()")
    pg.get_by_role("button", name="Ausführen").click(); pg.wait_for_timeout(6000)
    shot(pg, "ausgefuehrt")
    # Aufräumen: das eben gespeicherte Mapping löschen
    mid = pg.url.rstrip("/").split("/")[-1]
    if mid.isdigit():
        pg.evaluate("""async ([t, id]) => { await fetch('/api/mappings/' + id, {method: 'DELETE', headers: {Authorization: 'Bearer ' + t}}); }""", [T, mid])
        print("gelöscht: Mapping", mid)
    b.close()

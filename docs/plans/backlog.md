# Backlog

Alles, was offen ist — nach Bereichen, in der Reihenfolge, in der ich es angehen
würde. Erledigtes steht nicht drin: Die Liste soll zeigen, was zu tun ist, nicht
was war. Beim Abhaken die Zeile also löschen, nicht durchstreichen.

Stand: 30.08.2026 · 44 Aufgaben in 9 Bereichen

Markierungen: **⏳ wartet auf dich** = braucht eine Entscheidung, einen Zugang
oder einen Test von außen. **⏸ geparkt** = bewusst zurückgestellt, mit Grund.

> Es gibt eine gestaltete Fassung derselben Liste als Artifact-Seite (mit
> Drucklayout für ein PDF). Wenn hier etwas geändert wird, sollte sie
> mitgezogen werden — sonst laufen zwei Wahrheiten nebeneinander.

---

## 1. Preisautomatik: Ladenhüter-Rabatte

Gebaut und gegen PPS getestet: Regelwerk, Lauf, Freigabe, Ameise-Datei,
Kontrolle, Rücknahme, Nachtlauf. Was fehlt, ist der Beweis, dass eine Zeile den
Weg bis in die Wawi schafft.

1. [ ] **Erster echter Ameise-Import** ⏳
   Einen Artikel freigeben, Datei erzeugen, importieren, „Kontrolle" drücken.
   Meldet sie „1 angekommen", steht die Kette. Alles Weitere baut darauf auf.
2. [ ] **Staffelpreise gegen Sonderpreis prüfen** ⏳
   Bei PPS gibt es heute keinen einzigen Fall, in dem ein Sonderpreis über einer
   Staffelstufe liegt — deshalb ist aus den Daten nicht ablesbar, welcher Preis
   dann gilt. Ein Beleg mit Menge 30 klärt es.
3. [ ] **Rabatt endet, wenn der Artikel wieder läuft** — ½ Tag
   Die einzige echte Funktionslücke gegenüber SellerMath. Heute endet ein Rabatt
   nur über das Datum; ein Artikel, der am dritten Tag anzieht, bleibt 27 Tage zu
   billig. Der Nachtlauf hat die Verkaufsdaten bereits.
4. [ ] **Sicherheitsnetz gegen Staffelpreis-Kollision** — ¼ Tag
   Vorschlag ablehnen, wenn er über einer bestehenden Staffelstufe derselben
   Gruppe läge — sonst zahlt ein Mengenkäufer plötzlich mehr.
5. [ ] **Erfolgskontrolle: hat der Rabatt gewirkt?** — 1 Tag
   Absatz 30 Tage davor gegen 30 Tage danach, abgeflossener Bestand, entgangene
   Marge gegen freigewordenes Kapital. Das Journal kennt Vorher-Wert und
   Zeitpunkt schon — SellerMath hat dazu nichts.
6. [ ] **Direktschreiben als zweiter Anwendungsweg** — nach dem Import
   Journal, Kontrolle und Rücknahme stehen bereits; es kommt nur eine zweite
   Rückseite an dieselbe Schnittstelle.
7. [ ] **Gruppenrabatt in die Margenrechnung aufnehmen** — sobald ein Wert ≠ 0
   `tkundenGruppe.fRabatt` steht bei allen neun PPS-Gruppen auf 0. Sobald dort
   etwas steht, läge der effektive Preis unter unserer Rechnung und das
   Margen-Minimum wäre stiller Selbstbetrug.

Grundlagen: `docs/plans/preisautomatik-reiniger.md`, `doku/jtl-preis-schema.md`.

## 2. Preisautomatik: die nächsten Stufen

Der Aufholplan gegen SellerMath. Weder PPS noch HaKo verkauft über Marktplätze —
alles Marktplatz-Getriebene wartet deshalb auf den ersten Kunden, der einen hat.

1. [ ] **Kalkulierer für Kundengruppen** — mehrtägig
   EK + Versand + Retourenanteil + Zielmarge → VK je Gruppe, ohne
   Marktplatz-Gebührenkatalog. Nimmt PPS die Handarbeit über rund 4.000
   Preissätze ab. Braucht den Preis-Schreibkern aus Bereich 1.
2. [ ] **Preisspion: Wettbewerbsshops beobachten** — mittel
   Sitzt auf dem fertigen HTML-Reader mit visuellem Selektor. Offen sind
   Beobachtungsliste, Preisverlauf und der Umgang mit Shops, die ihre Preise per
   JavaScript nachladen.
3. [ ] **Aktualisierer: Mindest-/Höchstpreise an einen Repricer** ⏸
   Fällt fast aus dem Kalkulierer heraus — aber Repricer gibt es für die Amazon
   Buy Box. Ohne Marktplatz gegenstandslos.
4. [ ] **Preischecker: Portalpreise per EAN** ⏸
   Keine Entwicklungs-, sondern eine Einkaufsentscheidung: Portal-API
   lizenzieren oder den Kunden seinen eigenen Vertrag mitbringen lassen.
5. [ ] **Marktplatz-Gebührenkatalog** ⏸
   Amazon-Provisionen je Kategorie, FBA-Größenklassen, eBay-Staffeln, PayPal.
   Der teuerste Baustein des Kalkulierers — und für unsere beiden Betriebe wertlos.

## 3. Die echten Kosten

Der größte inhaltliche Rückstand gegenüber SellerMaths KostenWalter — und reiner
Einleseaufwand, kein neues Konzept. Solange er offen ist, ist jede „Marge" bei
uns eine Warenmarge.

1. [ ] **Skonto erfassen** — klein
   An der Kunden-DB als größter nicht erfasster Kostenblock gemessen:
   `tZahlungsart.fSkontoWert`, 2 % bei der häufigsten Zahlungsart. Steht bereits
   in der Wawi — es liest nur niemand.
2. [ ] **Echte Versandkosten** — je Anbieter
   `tVersandArt.fEKPreis` ist teils unbrauchbar gepflegt; belastbar wird es erst
   mit den Carrier-Rechnungen von DHL, GLS und DPD. Der Health-Check meldet die
   Versandkosten-Lücke heute schon als Befund.
3. [ ] **Zahlungsdienstleister-Gebühren** — je Anbieter
   PayPal, Mollie und Co. — je Beleg, nicht als Pauschale. Erst damit stimmt der
   Deckungsbeitrag einer einzelnen Bestellung.
4. [ ] **Kalkulatorischer Deckungsbeitrag / Profitabilitäts-Cockpit** — nach 1–3
   Phase 2 der BI-Roadmap. Ergibt sich fast von selbst, sobald die drei
   Kostenblöcke darüber eingelesen sind — vorher wäre es eine hübsche Fassade.

## 4. Unternehmensmonitor & Warnungen

26 Regeln laufen, der Drilldown stimmt seit dieser Woche mit den Kopfzahlen
überein. Offen ist vor allem die Zustellung.

1. [ ] **SMTP einrichten** ⏳
   Ohne Postausgang bleibt jede Warnung im Dashboard stehen — und der
   Tagesbericht der Preisautomatik verschickt sich ebenfalls nicht.
2. [ ] **Geänderte Schwellwerte testen** — klein
   Die Tabelle `business_config` ist leer, es greifen also nur die Vorgabewerte.
   Ein von Hand gesetzter Schwellwert ist nie durchgelaufen.
3. [ ] **Widersprüchliche Wegbeschreibung im Text** — Minuten
   Template-Hinweis und Aktionseditor schicken zu „Projekteinstellungen →
   Kennzahlen & Warnungen", das Panel sitzt aber als Dashboard-Reiter „Warnungen".
4. [ ] **Zwei offene Entscheidungen aus der Planung** ⏳
   Soll die Rabattbereinigung (`fWertNettoGesamtFixiert`) auch in die
   Altcockpits? Und wie weit gehen die Kostenregeln — Versand, Verpackung,
   Skonto, oder zusätzlich Plattform und Payment?
5. [ ] **Drilldown „Artikel mit unvollständigen Stammdaten"** — klein
   Die Warnung meldet 1.388 Artikel, der Klick führt auf die Ampel-Übersicht mit
   13 Zeilen. Vertretbar, aber die einzige Regel, deren Detailliste nicht die
   gemeldete Menge zeigt.

## 5. Cockpits

Sechs Cockpits plus Monitor sind live. Was hier steht, sind Feinheiten — nichts
davon blockiert den Betrieb.

1. [ ] **Ø Alter nur über die laufenden Vorgänge** — klein
   392 Tage sind rechnerisch richtig, als Kennzahl aber wertlos, solange 172 von
   207 Aufträgen Altbestand sind.
2. [ ] **Drilldown-Fenster hängen am alten 50er-Deckel** — klein
   Die Cockpit-Tabellen laden seit dem `full_rows`-Umbau vollständig, die
   Detailfenster nicht — bei langen Listen fehlt unbemerkt der Rest.
3. [ ] **Ladenhüter-Warnung: 526 gemeldet, 500 gezeigt** — mit Aufgabe 2
   Die Detailliste stößt an den harten 500er-Deckel des Drilldown-Endpunkts.
4. [ ] **GF-Cockpit: Auftragseingang & Backlog** — ½ Tag
   Letzter Punkt aus dem GF-Backlog: der vorlaufende Indikator neben den
   Rechnungszahlen. Die Daten stehen im Vertriebs-Cockpit bereits.

## 6. Stammdaten nach JTL schreiben

Der Schreibkern ist fertig und im Trockenlauf geprüft (EAN, HAN, Warennummer,
Herkunftsland, Gewicht, Beschreibung) — bedient wird er noch nicht.

1. [ ] **Schreiben-Knopf in der Oberfläche** — ½ Tag
   Endpunkte und Plan stehen, es fehlt der Weg vom Vorschlag zum Schreibvorgang.
2. [ ] **Erster Echtlauf an einem Testartikel** ⏳
   Vorher Sicherung der Wawi-Datenbank, dann genau ein Artikel.
3. [ ] **Ungültige Zeilen überspringen statt alles blockieren** — klein
   Heute setzt ein einziger fehlerhafter Wert den ganzen Stapel still — so
   beschlossen, aber in der Oberfläche vermutlich lästig.
4. [ ] **Schwesterartikel-Vorschläge** — ½ Tag
   Was für den Handschuh in Größe S gilt, gilt meist auch für M, L und XL.

## 7. Plattform

Datenmonster selbst — unabhängig von JTL und den Cockpits.

1. [ ] **Pipelines und Zeitpläne kennen keinen Mandanten** — 1 Tag
   Cockpits, Kosten, Warnungen und Reports laufen je Mandant; mapping-basierte
   Pipelines und Zeitpläne laufen weiter gegen ihre fest eingetragene Verbindung.
   Die Lücke wächst mit jedem neuen Nachtlauf.
2. [ ] **Form Builder: weitere Aktionstypen** — je Typ klein
   Heute nur Mapping und Pipeline. Offen: E-Mail-Versand, Webhook, PDF,
   Plugin-Aufruf.
3. [ ] **Form Builder: bedingte Sichtbarkeit** — ½ Tag
   Feld B nur zeigen, wenn Feld A einen bestimmten Wert hat.
4. [ ] **Formular-Einträge: Detailansicht und CSV-Export** — ½ Tag
   Eingegangene Einträge lassen sich listen, aber nicht einzeln ansehen oder
   herausziehen.
5. [ ] **API Studio Phase 4: OpenAPI** — mehrtägig
   Phasen 0 bis 3 sind fertig. Falle für jede Erweiterung: Sammlung und Umgebung
   müssen an *jeder* neuen Ausführungsstelle aufgelöst werden.
6. [ ] **Onboarding: Demo-Projekt** — 1 Tag
   Checkliste und Leerzustände stehen; es fehlt das vorinstallierte Beispiel, an
   dem ein neuer Nutzer sofort sieht, was möglich ist.
7. [ ] **Handbuch: Plugin-Kapitel ist veraltet** — Minuten
   `Anleitung.md` beschreibt noch die alte Trennung in Tier 1 und Tier 2 — in der
   Oberfläche gibt es längst einen einzigen Katalog.

## 8. Plugins, Templates, Vertrieb

Alles rund um monstersuite als Lizenz- und Verkaufsseite.

1. [ ] **Sechs Template-Artikel stehen unveröffentlicht im Shop** — Minuten
   Angelegt und lizenzgeprüft, aber `is_published=false` — sie sind schlicht
   noch nicht sichtbar.
2. [ ] **Plugin-Store: Verwaltung nachziehen** — 1 Tag
   Offen: Admin-Oberfläche zum Hochladen, Berechtigung je Plugin statt pauschal
   `plugin_tier2`, und die Tarballs aus der CI automatisch veröffentlichen.
3. [ ] **Öffentliches Plugin-Schaufenster** — 1 Tag
   Ein Katalog auf der Homepage, der zeigt, was es gibt — heute sieht man
   Plugins erst nach dem Kauf.
4. [ ] **monstersuite: lokale Umgebung ist kaputt** — ½ Tag
   Der Code erwartet Postgres, die lokale `.env` zeigt auf sqlite. Getestet wird
   deshalb an einer Wegwerf-Instanz — auf Dauer die falsche Antwort.

## 9. Kundenprojekte & Datenpflege

Nichts davon ist Entwicklung — aber es blockiert oder verzerrt Entwicklung.

1. [ ] **Intrastat: Zugangsdaten und Pipeline** ⏳
   Mapping „Intrastat HaKo" und die JTL-Feldzuordnungen sind fertig, die
   Anmeldedaten für die Meldestelle fehlen.
2. [ ] **Shipman-Fulfillment** ⏸
   Pausiert, bis die Zugangsdaten da sind. Härtung und Positions-Test sind
   erledigt, Wiedereinstieg ist Testplan T3.
3. [ ] **PPS: 90 abgelaufene Sonderpreise aufräumen** — klein
   Von 439 aktiven Aktionen sind 90 längst abgelaufen und stehen trotzdem auf
   aktiv. Sie wirken nicht, stehen aber in jeder Liste — und die Preisautomatik
   sollte auf sauberem Grund starten. `Dashboard.vAbgelaufeneSonderpreise`
   liefert sie fertig.
4. [ ] **HaKo: Kundengruppen sind unbenutzt** — Beratung, kein Code
   6.240 von rund 7.200 Kunden hängen in „Neukunde", 16 der 30 Gruppen haben
   keinen einzigen Kunden, und ganze 10 Artikel haben einen Gruppenpreis.
   Solange das so ist, ist jede Preisautomatik dort ein Werkzeug ohne Werkstück.

---

**Wenn nur eine Sache passiert:** Bereich 1, Aufgabe 1. Bis eine Preiszeile
nachweislich in der Wawi ankommt, bauen alle weiteren Ausbaustufen auf einer
ungeprüften Kette auf.

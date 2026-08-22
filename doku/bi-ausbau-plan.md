# Datenmonster → JTL Business Intelligence & Decision Support
### Bestandsaufnahme, Architekturplan, Alert-Katalog

Stand: 23.08.2026 · Grundlage: Repo-Analyse + lesende Stichproben gegen die produktive
JTL-DB (Verbindung 1, „HaKo Server Lokal", `eazybusiness`). Intrastat ist ausgeklammert.

---

## Teil A — Was heute existiert (und was das für den Umbau bedeutet)

### A.1 Die Bausteine, auf denen alles aufsetzt

| Baustein | Wo | Zustand | Für den Umbau |
|---|---|---|---|
| Mapping-Engine | `mapping_service.execute_mapping` | SQL-Node im Modus `transform` bindet `:param` aus `run_params`; **nicht referenzierte Parameter werden ignoriert** (`sql_helpers._resolve_sql_run_params`) | ✅ Zusätzliche Parameter (Schwellwerte, Kostensätze) sind **rückwärtskompatibel** injizierbar |
| Parameter-Injektion | `article_exclusion_service.apply_article_exclusions` | Injiziert projektbezogene Ausschlussliste in jeden Form-/Drilldown-Lauf | ✅ **Blaupause** für einen `business_config_service` |
| Formular-Lauf | `forms._execute_form` | Actions parallel (5 Worker), `full_rows`-Cap, `requires_params`-Skip | ✅ Ein Alert-Lauf kann denselben Weg gehen |
| Drilldown | `POST /api/forms/drilldown` | Mapping + `run_params`, mehrstufig (`row_detail.levels`) | ✅ Alerts brauchen nur `mapping_id` + Parameter |
| Ampel-Aufgabenliste | Widget `tasklist`, Mapping „Cockpit – Aufgabenliste (Ampel)" | **Ein einziges Monster-SQL** mit 7 Subselects, Schwellwerte (180 Tage, 90 Tage, 20 Zeichen) hart im SQL | ⚠️ Genau die Sonderlösung, die durch das Regelwerk ersetzt gehört – Widget bleibt, Datenquelle wird generisch |
| KI-Analyse | `ai.summarize-data`, `AiSummaryWidget` | Fakten serverseitig vorformatiert, deutsche Zahlen, Marker, **deterministische Bewertungstabelle** | ✅ Trennung Zahl/Prosa ist bereits die geforderte Architektur |
| Bewertungstabelle | `AiSummaryWidget.buildAssessment` **und** `cockpit_report._assessment_rows` | Logik **doppelt gepflegt**, Action-IDs hart kodiert (`_ASSESSMENT_ACTION_IDS`) | ⚠️ Konsolidierungskandidat: eine Regel-Definition, zwei Renderer |
| KI-Handlungsempfehlung | `ai.recommend-action` (4 `kind`s) + `AiActionModal` | Kennzahlen (Rückgewinnungs-W., Rabatt) **deterministisch im Backend**, Fakten-Kacheln im Modal | ✅ Muster für §15 steht bereits – aber `kind` und Kacheln sind hart kodiert |
| PDF-Report | `cockpit_report.py` + `POST /forms/{id}/report` | generisch über `result_tabs`/Widgets, KI-Summary + Bewertung | ✅ Neue Widgets erscheinen automatisch, sobald ein Renderer existiert |
| Zeitraum/Vorjahr | Feld `daterange` → `:von`/`:bis`, Vorjahr **im SQL** via `DATEADD(YEAR,-1,…)` | 60+ Mappings | ⚠️ Freier Periodenvergleich geht nur additiv über neue Parameter, nicht durch Umbau |
| Scheduler | `ScheduledJob` (Cron je Mapping) + `JobRun` | vorhanden | ✅ Trägt nächtliche Alert-Läufe/Snapshots |
| Template-Install | `templates.install_template` | Wiederverwendung nach Namen, Mappings werden aktualisiert, **Formulare bewusst nicht** | ✅ Additive Templates sind sicher |
| Template-Config | `config_required` | wird **beim Installieren in den SQL-Text substituiert und danach verworfen** (nur die *Keys* landen im Log) | ❌ **Kein Ort für laufende Schwellwerte** – der zentrale Grund für §16 |
| Caching / Snapshots | – | **existiert nicht**; Redis ist nur Event-Bus, gecacht wird nur die SQLAlchemy-Engine | ❌ Muss neu, sobald Alerts/Historien teurer werden |
| Formular-Assistent | `dashboardContext.js` → `/ai/chat` | sieht nur den **aktiven Reiter**, max. 6 Zeilen je Widget | ⚠️ Für Ursachenanalyse zu wenig – der Orchestrator muss serverseitig Fakten holen |

### A.2 Abgleich mit den 22 Anforderungen

| Anforderung | Status heute | Lücke |
|---|---|---|
| §3/4 Profitabilität | DB I, DB II (= Rohertrag + Versandergebnis), DB je Plattform | Kosten außerhalb JTL, Kostenregeln, Auftrags-/Kundensicht |
| §5 „Heute zu tun" | `tasklist` im GF-Cockpit, 7 Prüfungen | Monolith-SQL, nicht erweiterbar, kein eigener Monitor, keine Priorisierung nach Wirkung |
| §6 Alert-Regelwerk | – | komplett neu (aber Widget + Drilldown wiederverwendbar) |
| §7 EK/Marge | „EK-Preisentwicklung (12 M)" im Einkaufs-Cockpit | keine Verknüpfung EK↔VK↔Umsatz, keine Ergebniswirkung, kein Alert |
| §8 Out-of-Stock | Fehlmengen, Zulauf, Reichweite (Lager-Cockpit) | keine Prognose (Datum), kein Abgleich Zulauftermin ↔ Bedarfstermin |
| §9 Retouren-Anomalien | Retouren-Reiter mit Quote/Gründen | kein Normalwert-Vergleich, keine Fallzahl-Sicherung |
| §10 Lieferanten-Score | Termintreue, Lieferzeit, Volumen, Preisentwicklung – **alle Bestandteile da** | nur Zusammenführung + Gewichtung |
| §11 Ziele/Budgets | – | komplett neu (Speicher + KPI-Widget-Erweiterung) |
| §12 Freie Periodenvergleiche | Vorjahr fest im SQL | neue Parameter `:von2/:bis2` + Feld, nur wo gewünscht |
| §13 Ursachenanalyse | Chat mit Reiter-Kontext | Orchestrator + kuratierte Faktenbündel |
| §14 Cross-Cockpit | einzelne Doppelnutzungen (Einkaufs-KPIs im GF-Cockpit) | echte Ketten fehlen |
| §15 Nachvollziehbarkeit | Fakten-Kacheln im KI-Modal | für Alerts generisch nötig |
| §16 Konfigurierbarkeit | Install-Zeit-Platzhalter | Laufzeit-Konfiguration fehlt |
| §17 Performance | parallele Läufe, `row_cap`, Pushdown | kein Cache, keine Snapshots |
| §18 Keine Breaking Changes | – | Leitplanke, siehe D |

---

## Teil B — Datenverfügbarkeit in JTL (an der Kunden-DB verifiziert)

Alle Angaben stammen aus lesenden Abfragen gegen die produktive WaWi (Ø 0,2–0,9 s je
Cockpit-Mapping; 35.413 Aufträge, 27.865 Rechnungen, 3.232 Artikel, 7.215 Kunden,
106.485 Historienzeilen — also eine **kleine** Installation; die Aussagen zur Performance
sind entsprechend zu skalieren).

| Kostenart / Faktor | Quelle in JTL | Verfügbar? | Befund |
|---|---|---|---|
| Wareneinsatz | `tRechnungPosition.fEkNetto` (historisch), Fallback `tArtikel.fEKNetto` | ✅ | bereits in Nutzung |
| Versanderlös | Position `nType = 2` | ✅ | 27.532 Positionen; 22.446 € netto in 12 M |
| **Versandkosten (Soll)** | `tVersandArt.fEKPreis` | ⚠️ teilweise | DPD 5,95 €, GLS 5,70 € gepflegt – **DHL steht auf 50 €**, Spedition 45/50 €, mehrere auf 0. Als Default brauchbar, **muss überschreibbar sein** |
| Versandart je Auftrag | `Verkauf.tAuftrag.kVersandArt` | ✅ | 12 M: GLS auto 2.621, Kleine Spedition 1.894, Eigenlieferung 1.412, Selbstabholer 790 |
| Zahlungsart je Auftrag | `tAuftrag.kZahlungsart` → `tZahlungsart` | ✅ | vollständig |
| **Skonto** | `tZahlungsart.fSkontoWert` / `nSkontoZeitraum` | ✅ **gepflegt** | „Überweisung 10 Tage 2 %" ist mit 2.979 Aufträgen die häufigste Zahlungsart; 2–3 % sind hier der **größte nicht erfasste Kostenblock** – bei ~4,5 Mio. € Umsatz sprechen wir über einen sechsstelligen Betrag |
| Tatsächlich gezogenes Skonto | `dbo.tZahlung` gegen Rechnungsbetrag | ✅ ableitbar | Zahlungsmoral-Mappings nutzen `tZahlung` bereits |
| Plattform | `tAuftrag.kPlattform` → `tPlattform` | ✅ | **hier**: JTL-Wawi 6.852, Onlineshop 808 – kein Amazon/eBay. Plattformgebühren-Regeln sind für *dieses* Haus irrelevant, für das Produkt aber Pflicht |
| Rabatte | `Position.fRabatt` (%) | ✅ | **Befund:** `fWertNettoGesamtFixiert = fAnzahl × fVkNetto × (1 − fRabatt/100)`. Die Cockpits rechnen mit `fAnzahl × fVkNetto`, also **vor Rabatt**. Effekt hier: 998 € auf 4,57 Mio. € (0,02 %) – vernachlässigbar, aber bei rabattstarken Händlern relevant |
| Verpackung, Handling, Plattformgebühr, Payment-Gebühr | – | ❌ | **nur über Kostenregeln** |
| Bestand / verfügbar / Zulauf | `tlagerbestand`: `fLagerbestand`, `fVerfuegbar`, `fInAuftraegen`, `fZulauf`, `dLieferdatum` | ✅ | alles für die OOS-Prognose vorhanden |
| Mindestbestand | `tArtikel.nMidestbestand` | ✅ | (JTL-Schreibfehler im Feldnamen ist echt) |
| Lieferzeit Lieferant | `tliefartikel.nLieferzeit` | ⚠️ | nur **536 von 3.270** Lieferanten-Artikeln gepflegt, `fDurchschnittlicheLieferzeit` **durchgehend 0** → Lieferzeit **aus der Bestellhistorie** rechnen (Logik existiert im Einkaufs-Cockpit) |
| Lieferanten-Ranking (JTL) | `tLieferantenRankingGlobal/-Zeitraum` | ❌ leer (0 Zeilen) | eigener Score nötig – wie gefordert |
| Retouren | `tRMRetoure` / `tRMRetourePos` | ⚠️ dünn | **179 Retouren, 251 Positionen insgesamt**. Anomalieerkennung je Artikel ist statistisch nur mit Mindestfallzahl seriös (siehe D.4) |
| Wareneingänge | `tWarenLagerEingang` | ✅ | Termintreue läuft darüber |
| Offene Posten / Mahnstufe | `Rechnung.vRechnungEckdaten` | ✅ | fertig aufbereitet |

**Fazit:** Der kalkulatorische DB ist zu ~70 % aus JTL rekonstruierbar. Die entscheidende
Ergänzung ist **nicht** Amazon/PayPal (wie im Auftrag vermutet), sondern **Skonto** und
**echte Versandkosten** — beides ist hier deterministisch bzw. halb-deterministisch da.

---

## Teil C — Architekturvorschlag (additiv, in dieser Reihenfolge)

### C.1 Fundament: `business_config` (Voraussetzung für fast alles Weitere)

Ein Schlüssel-Wert-Speicher **je Projekt**, drei Namensräume:

```
BusinessConfig(id, project_id, scope, key, value_json, updated_at)
  scope = "threshold" | "cost" | "goal"
```

* `threshold`: `ladenhueter_tage=180`, `oos_tage=14`, `ueberbestand_tage=180`,
  `forderung_kritisch_tage=30`, `marge_min_prozent=15`, `ek_anstieg_prozent=5`,
  `retoure_anomalie_faktor=2.0`, `lieferverzug_tage=7`, …
* `cost`: Regeln mit Geltungsbereich und Formel-Typ, z. B.
  `{"typ":"versand","match":{"kVersandArt":8},"betrag_je_sendung":6.90}`,
  `{"typ":"plattform","match":{"kPlattform":3},"prozent":15.0}`,
  `{"typ":"payment","match":{"kZahlungsart":27},"prozent":2.49,"fix":0.35}`,
  `{"typ":"verpackung","betrag_je_sendung":0.85}`.
  **Priorität:** JTL-Wert (`fEKPreis`, `fSkontoWert`) → Regel → 0, mit Herkunftsausweis.
* `goal`: `{"kennzahl":"umsatz","periode":"2026","wert":2500000}`.

**Auslieferung an die Mappings:** ein `business_config_service.apply_config(run_params,
project_id, db)` — exakt nach dem Muster von `apply_article_exclusions`, aufgerufen an
denselben drei Stellen (Form-Run, Drilldown, Report). Setzt `:cfg_ladenhueter_tage`,
`:cfg_oos_tage` … Bestehende SQLs referenzieren die Parameter nicht und laufen deshalb
**unverändert weiter**; neue/angepasste SQLs schreiben `:cfg_x` statt einer Zahl.
Kostenregeln kommen als Liste von Tripeln (`match_typ`, `match_id`, `betrag`/`prozent`)
und werden im SQL über eine `VALUES`-Ableitung gejoint — keine Stringinterpolation.

UI: neuer Reiter in den Projekteinstellungen („Kennzahlen & Schwellwerte"), plus
Anzeige der aktiven Werte im Alert-Detail (§15).

### C.2 Alert-Engine (das eigentliche Herzstück)

**Regel = Daten, nicht Code.** Zwei neue Tabellen:

```
AlertRule(id, project_id, rule_key, name, category, severity_default,
          mapping_id, params_json, condition_json, threshold_keys,
          drilldown_json, action_kind, facts_json, cockpit, active, sort)
AlertRun(id, project_id, started_at, duration_ms, rule_key, severity,
         count, value, title, subtitle, facts_json, entity_key, payload_json)
```

* `mapping_id` zeigt auf ein ganz normales Mapping — **jede Regel ist ein SQL, das eine
  standardisierte Zeilenform liefert**:
  `severity, entity_key, entity_label, wert, anzahl, fakt_1..n`.
* `condition_json` bewertet nur noch das Ergebnis (`count > 0`, `wert >= :cfg_x`,
  `abweichung_prozent <= -5`) — die Zahl kommt aus SQL, nie aus der Regel.
* `facts_json` benennt die Faktenzeilen für die Detailansicht (§15).
* `drilldown_json` = `{mapping_id, params, hidden_columns}` → bestehender Drilldown.
* `action_kind` = optionaler `recommend-action`-Typ (§C.5).

**Evaluator** (`alert_service.evaluate(project_id, params)`): lädt aktive Regeln, führt
die Mappings gedrosselt parallel aus (wie `_execute_form`), wertet die Bedingungen aus,
schreibt einen `AlertRun`. Aufruf aus (a) dem Monitor-Formular, (b) dem Scheduler
(nächtlich), (c) einem Endpunkt `POST /api/alerts/evaluate`.

**Auslieferung ins Frontend:** neues Widget `alerts` (Severity-Gruppen, Anzahl, Wert,
Klick → Fakten + Drilldown + optional KI-Empfehlung). Der `tasklist`-Renderer ist die
Vorlage; das alte Widget bleibt unangetastet bestehen.

**Regeln reisen im Template mit** (neuer Content-Key `alert_rules`, Installer legt sie
mit aufgelösten `{{mapping_x}}`-IDs an) — so bleibt der Auslieferungsweg der bekannte.

### C.3 Monitor „Heute" (§5) — als Formular, nicht als neue Seite

Ein eigenes Template `jtl_monitor` mit **einem** Formular:
Reiter 1 „Heute" = `alerts`-Widget (nach Severity und **Wirkung in Euro** sortiert) +
6–8 KPI-Kacheln (Umsatz/DB Monat gegen Vorjahr) + KI-Kurzanalyse; Reiter 2 „Alle Prüfungen"
= vollständige Regelliste mit Status. Als Portal-Homepage veröffentlichbar.
*(Bewusst kein eigener Programmbereich — Reports und Dashboards gehören in Formulare.)*

### C.4 Kalkulatorischer DB + Profitabilitäts-Cockpit (§3/§4)

Ein **SQL-Baustein** (eine CTE, in jedes Profitabilitäts-Mapping kopiert — die Engine
kennt keine geteilten Views):

```
Auftrags-/Rechnungsebene:
  Erlös        = Σ fWertNettoGesamtFixiert (nType 1)      ← rabattbereinigt
+ Versanderlös = Σ fWertNettoGesamtFixiert (nType 2)
− Wareneinsatz = Σ fAnzahl × COALESCE(NULLIF(fEkNetto,0), tArtikel.fEKNetto)
− Versandkosten= COALESCE(Regel(kVersandArt), tVersandArt.fEKPreis, 0)
− Verpackung   = Regel je Sendung
− Plattform    = Regel(kPlattform) × Erlös
− Payment      = Regel(kZahlungsart) prozentual + fix
− Skonto       = tZahlungsart.fSkontoWert × Erlös   (optional: nur tatsächlich gezogenes)
= kalkulatorischer DB
```

Jede Komponente wird **als eigene Spalte** ausgewiesen, plus `KostenHerkunft`
(JTL / Regel / fehlt) — ohne diesen Ausweis ist die Zahl im B2B nicht diskutierbar.

Das neue Template `jtl_profitabilitaet_cockpit` (Reiter Übersicht / Artikel / Kunden /
Plattformen & Zahlarten / Aufträge) ist sinnvoll **als eigenes Template**, weil es
zwingend Kostenregeln braucht: ohne gepflegte Regeln zeigt es Halbwahrheiten, und das
GF-Cockpit darf davon nicht abhängen. Ich würde den geforderten Reiter „Plattformen"
zu **„Kanäle & Zahlarten"** erweitern — bei B2B-Händlern wie hier ist die Zahlart der
Kostenhebel, nicht der Marktplatz.

### C.5 Generische KI-Empfehlung

`recommend-action` bekommt einen fünften, **datengetriebenen** `kind`: Fakten kommen als
`[{label, wert, einheit}]` aus der Regel, das Modell formuliert. Die vier bestehenden
`kind`s bleiben unverändert (kein Bruch), das Modal rendert Kacheln künftig aus den
gelieferten Fakten statt aus hart kodierten Listen.

### C.6 Prognosen (§8) — rein deterministisch

`Reichweite_Tage = fVerfuegbar / Ø-Tagesabsatz`, Ø-Absatz aus zwei Fenstern (90 Tage und
28 Tage, gewichtet), `OOS_Datum = heute + Reichweite`, Abgleich gegen
`tlagerbestand.dLieferdatum` bzw. den frühesten offenen Bestellzulauf. Alle Zwischenwerte
werden ausgegeben (Bestand, reserviert, verfügbar, Ø/Tag, Zulauf, Datum) — das ist
gleichzeitig die Faktenliste des Alerts.

### C.7 Ziele & freie Periodenvergleiche (§11/§12)

* Ziele aus `business_config` (scope `goal`) → KPI-Widget lernt `config.goal_key`:
  zeigt Ist | Ziel | Abweichung | Forecast. Kacheln ohne `goal_key` bleiben wie sie sind.
* Periodenvergleich: **neue** Parameter `:von2/:bis2`, im Formular ein zweites
  `daterange`-Feld „Vergleichszeitraum" mit Default „Vorjahr". Umgestellt wird
  ausschließlich, wo der Vergleich gebraucht wird; die 60+ bestehenden Vorjahres-SQLs
  bleiben unberührt (§18).

### C.8 Analyse-Orchestrator (§13) — zuletzt, klein anfangen

Kein generisches KI-SQL. Stattdessen **kuratierte Faktenbündel**: eine Handvoll Intents
(`umsatzrueckgang`, `margenverfall`, `liquiditaet`, `lagerprobleme`), jeder mit einer
festen Liste von Mapping-IDs + Parametern. `POST /api/ai/analyze-cause` erkennt den Intent
(Stichwörter, kein Modell nötig), führt das Bündel aus, übergibt der KI **fertige Zahlen**
mit der bekannten „nur gelieferte Zahlen"-Regel. Antwort trägt die Faktenliste sichtbar mit.

### C.9 Performance & Snapshots (§17)

* Alert-Läufe werden **persistiert** (`AlertRun`) und im Monitor aus dem letzten Lauf
  gerendert; „Jetzt neu prüfen" ist ein bewusster Klick.
* Nächtlicher Cron-Job über den vorhandenen Scheduler.
* Optionale Tages-Snapshots (Lagerwert, Umsatz/DB je Tag) in einer Datenmonster-eigenen
  Tabelle — **niemals** in die WaWi schreiben.
* Regel: eine Regel = eine Query mit Aggregat; kein `SELECT *`, kein Scan über
  `vArtikelHistorie` ohne Datumsfilter. Messwerte oben zeigen den Rahmen, an dem sich
  neue SQLs messen lassen müssen.

---

## Teil D — Risiken und ehrliche Einschätzung

1. **Kostenregeln sind Vertrauenssache.** Ein DB, der auf geschätzten Versandkosten
   beruht, ist im Zweifel schlechter als keiner. Deshalb: Komponenten einzeln ausweisen,
   Herkunft markieren, und im Cockpit sichtbar machen, wenn Regeln fehlen.
2. **`tVersandArt.fEKPreis` ist hier teils Unsinn** (DHL = 50 €). Automatisch übernehmen
   würde falsche DBs erzeugen → Regel schlägt JTL-Wert, nicht umgekehrt, sobald eine
   Regel existiert.
3. **Rabatt-Befund** (Teil B): Umsatz wird heute vor Rabatt gerechnet. Für neue
   Profitabilitäts-SQLs nehme ich `fWertNettoGesamtFixiert`. Die **bestehenden** Cockpits
   würde ich nur nach ausdrücklicher Ansage umstellen — es verschiebt historische
   Vergleichszahlen (hier um 0,02 %).
4. **Retouren-Anomalien sind bei dieser Datenlage kaum tragfähig** (179 Retouren gesamt).
   Regel deshalb mit Mindestfallzahl (z. B. ≥ 20 Verkäufe *und* ≥ 3 Retouren im Fenster)
   — sonst produziert die Engine Fehlalarme aus Zufallsrauschen. Bei Retouren-starken
   Händlern greift dieselbe Regel dann automatisch.
5. **30–50 Regeln × 1 Query** sind bei dieser DB ~10–20 s, bei einer Million Rechnungen
   deutlich mehr. Ohne den persistierten Lauf (C.9) wird der Monitor sonst zur Bremse.
6. **Doppelte Bewertungslogik** (Frontend + Report) wächst mit jedem neuen Bereich weiter.
   Ich würde sie im Zuge von C.2 auf eine Definition zusammenführen — additiv, mit
   unverändertem Ergebnis für die heutigen Reiter.
7. **Was ich weglassen würde:** ein „Verlustauftrag"-Alert ohne gepflegte Kostenregeln
   (produziert nur Rauschen), sowie plattformspezifische Gebührenlogik als Sonderfall —
   sie ist ein normaler Regeltyp, mehr nicht.

---

## Teil E — Alert-Katalog (58 Regeln)

Legende: **Sev** = Severity-Default (K kritisch, W Warnung, H Hinweis, I Info, P positiv) ·
**P** = Priorität (1 = erste Welle) · **KI** = für Handlungsempfehlung geeignet ·
*kursiv* = Logik existiert bereits als Mapping und wird nur eingehängt.

### Geschäftsführung
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 1 | Umsatz unter Vorjahr | vRechnung | Monat vs. Vorjahresmonat < −5 % | W | 1 | ✓ |
| 2 | DB-II-Marge gesunken | *KPI-Mapping* | Marge − MargeVJ ≤ −2 pp | W | 1 | ✓ |
| 3 | Rohertrag 3 Monate in Folge fallend | *Trend-Mapping* | 3× LAG fallend | W | 1 | – |
| 4 | Umsatz über Vorjahr | vRechnung | ≥ +5 % | P | 1 | – |
| 5 | Jahresziel in Gefahr | Forecast + `goal` | Forecast/Ziel < 95 % | W | 2 | ✓ |
| 6 | Klumpenrisiko Kunden | *ABC-Mapping* | Top-5-Anteil > 40 % | H | 2 | ✓ |

### Vertrieb
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 7 | Auftragseingang unter Vorjahr | tAuftrag | < −10 % | W | 1 | ✓ |
| 8 | Überfällige Liefertermine im Backlog | tAuftrag | dLieferdatum < heute, offen | K | 1 | – |
| 9 | Alte offene Aufträge | tAuftrag | Alter > 30 Tage & Wert > 1.000 € | W | 2 | – |
| 10 | Angebote unnachgefasst | tAuftrag (ANG) | > 14 Tage offen, Wert > 500 € | H | 1 | ✓ |
| 11 | Storno-Quote erhöht | tAuftrag | > 5 % und > Vorjahr | W | 3 | – |
| 12 | Angebots-Conversion gefallen | *Angebots-Mapping* | < Ø 12 M − 10 pp | H | 3 | – |

### Kunden
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 13 | A-Kunde schläft ein | *Churn-Mapping* | > 2× Bestellrhythmus, Top-20-%-Kunde | K | 1 | ✓ |
| 14 | Kunde mit Umsatzrückgang | *Rückgang-Mapping* | < −25 % und > 2.000 € | W | 1 | ✓ |
| 15 | Neukunden unter Vorjahr | vRechnung | < −20 % | H | 2 | – |
| 16 | Erstbesteller ohne Folgeauftrag | tAuftrag | 1 Auftrag, > 60 Tage her | H | 3 | ✓ |
| 17 | Neuer A-Kunde gewonnen | tAuftrag | Neukunde mit Umsatz > Median A | P | 3 | – |

### Liquidität
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 18 | Überfällige Forderungen | *vRechnungEckdaten* | Summe überfällig > 0, Aging | K | 1 | – |
| 19 | Großer überfälliger Beleg | vRechnungEckdaten | > 5.000 € und > 30 Tage | K | 1 | ✓ |
| 20 | DSO verschlechtert | *OP-KPI* | +5 Tage ggü. Vorjahr | W | 2 | – |
| 21 | Zahlungsmoral eines Kunden kippt | *Zahlungsmoral-Mapping* | Ø-Zahldauer +10 Tage | W | 2 | ✓ |
| 22 | Überfällig ohne Mahnstufe | vRechnungEckdaten | > 14 Tage, Mahnstufe 0 | W | 1 | – |
| 23 | Kundenrisiko (Cross) | OP + Zahlungsmoral | Top-10-Umsatz **und** überfällig > 10.000 € | K | 2 | ✓ |

### Einkauf
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 24 | Bestellung überfällig | *tLieferantenBestellung* | Verzug > `cfg_lieferverzug_tage` (7) | W | 1 | ✓ |
| 25 | Karteileichen im Bestellbestand | tLieferantenBestellung | offen > 180 Tage | H | 2 | – |
| 26 | **Skontofrist läuft ab** | tEingangsrechnung + tZahlungsart | Fälligkeit Skonto ≤ 3 Tage | K | 1 | – |
| 27 | Eingangsrechnung überfällig | *tEingangsrechnung* | Zahlungsziel überschritten | W | 1 | – |
| 28 | EK-Sprung bei einem Artikel | Bestellhistorie | letzter EK vs. Vor-EK ≥ `cfg_ek_anstieg` (5 %) | W | 1 | ✓ |
| 29 | Lieferant mit Ø-EK-Steigerung | Bestellhistorie | 12 M vs. Vorjahr ≥ 5 % | H | 2 | ✓ |

### Lieferanten
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 30 | Termintreue unter Schwelle | *tWarenLagerEingang* | < 80 % bei ≥ 5 Lieferungen | W | 1 | ✓ |
| 31 | Termintreue fällt | Wareneingänge | −15 pp ggü. Vorperiode | W | 2 | ✓ |
| 32 | Lieferzeit gestiegen | Wareneingänge | +50 % ggü. 12-M-Ø | H | 2 | – |
| 33 | Verhandlungskandidat | Volumen + Score | Top-10-Volumen **und** Score < 60 | H | 2 | ✓ |
| 34 | Verzug blockiert Kundenaufträge (Cross) | Bestellung → Bestand → Auftrag | verspätete Bestellung deckt Fehlmenge zu offenen Aufträgen | K | 2 | ✓ |

### Lager
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 35 | Drohender Out-of-Stock | tlagerbestand + Absatz | Reichweite < `cfg_oos_tage` (14), kein Zulauf | K | 1 | ✓ |
| 36 | Zulauf kommt zu spät | + dLieferdatum | Zulauftermin > OOS-Datum | K | 1 | ✓ |
| 37 | Unter Mindestbestand | tArtikel.nMidestbestand | verfügbar < Mindestbestand | W | 1 | – |
| 38 | Überbestand | Reichweite | > `cfg_ueberbestand_tage` (180) und Kapital > 1.000 € | H | 2 | ✓ |
| 39 | *Ladenhüter* | *bestehendes Mapping* | ohne Abgang > `cfg_ladenhueter_tage` | H | 1 | ✓ |
| 40 | Inventurdifferenzen auffällig | vArtikelHistorie | Monatswert > 2× 12-M-Ø | W | 2 | – |
| 41 | Bestand ohne gebuchten EK | vArtikelHistorie | Anteil > 10 % des Lagerwerts | I | 3 | – |

### Artikel & Profitabilität
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 42 | **VK nicht nachgezogen** | EK-Historie + tArtikel | EK ≥ +5 %, VK unverändert, Umsatz 12 M > 1.000 € → Ergebniswirkung €/Jahr | K | 1 | ✓ |
| 43 | *Negative Marge* | *bestehendes Mapping* | DB < 0 im Zeitraum | K | 1 | ✓ |
| 44 | Marge unter Zielmarge | Positionen | < `cfg_marge_min` (15 %) bei Umsatz > 5.000 € | W | 2 | ✓ |
| 45 | Kunde mit negativem DB | kalk. DB | DB < 0 bei ≥ 3 Aufträgen | W | 2 | ✓ |
| 46 | Versandergebnis negativ | Erlös nType 2 vs. Kosten | Deckung < 80 % je Versandart | W | 2 | – |
| 47 | Skonto-Belastung hoch | tZahlungsart + Zahlungen | > 1,5 % vom Umsatz | H | 2 | ✓ |
| 48 | Absatzeinbruch bei A-Artikel | Positionen | 28 Tage vs. 90-Tage-Ø < −40 % | W | 2 | ✓ |
| 49 | *Umsatzstarker Artikel ohne Bestand* | *bestehendes Mapping* | verkauft 90 Tage, Bestand 0 | K | 1 | ✓ |

### Retouren / Versand / Stammdaten
| # | Warnung | Quelle | Logik / Default | Sev | P | KI |
|---|---|---|---|---|---|---|
| 50 | Retourenquote über Schwelle | tRMRetoure | Wertquote > 5 % | W | 2 | – |
| 51 | Artikel-Retourenanomalie | tRMRetoure | 30-Tage-Quote ≥ 2× historisch, **min. 20 Verkäufe / 3 Retouren** | W | 3 | ✓ |
| 52 | Grund „defekt" häufen sich | tRMRetourePos | Anteil ≥ 2× Vorperiode je Hersteller | W | 3 | ✓ |
| 53 | Versandrückstand | *tLieferschein* | ohne Versand > 3 Tage | W | 1 | – |
| 54 | Durchlaufzeit verschlechtert | *Versand-KPI* | Anteil > 72 h steigt > 10 pp | H | 3 | – |
| 55 | Tracking-Quote gefallen | *Versand-KPI* | −10 pp ggü. Vorperiode | H | 3 | – |
| 56 | *Stammdatenlücken über Schwelle* | *Health-Check-Ampel* | je Prüfung (EAN, Gewicht, Zolltarif, Herkunft) | H | 1 | – |
| 57 | *VK unter EK* | *Health-Check* | Verkaufspreis < Einkaufspreis | K | 1 | ✓ |
| 58 | *Gesperrte Artikel mit Bestand* | *bestehendes Mapping* | Kapital in gesperrter Ware | H | 2 | – |

**58 Regeln entworfen, davon 27 in der ersten Welle (P1)** — 14 davon nutzen bereits
existierende Mappings und kosten nur die Regel-Definition.

---

## Teil F — Vorgeschlagene erste Phase

**Ziel: das Fundament steht und trägt sichtbar — ohne ein einziges bestehendes Cockpit anzufassen.**

| Schritt | Inhalt | Berührte Dateien |
|---|---|---|
| 1 | `BusinessConfig`-Modell + Service + API + Einstellungs-Reiter | neu: `models/business_config.py`, `services/business_config_service.py`, `api/business_config.py`, Frontend-Reiter |
| 2 | Injektion in Form-Run / Drilldown / Report (3 Zeilen, analog Ausschlussartikel) | `api/forms.py`, `services/cockpit_report.py` |
| 3 | `AlertRule` / `AlertRun` + `alert_service` + `POST /api/alerts/evaluate` | neu: `models/alert.py`, `services/alert_service.py`, `api/alerts.py` |
| 4 | Widget `alerts` (Renderer + Editor-Eintrag + Report-Renderer) | `WidgetRenderer.tsx`, `widgets/AlertsWidget.tsx`, `WidgetsEditor.tsx`, `cockpit_report.py` |
| 5 | Template `jtl_monitor` mit den **27 P1-Regeln**, davon 14 auf bestehenden Mappings | neu: `templates/jtl_monitor.json` |
| 6 | Nächtlicher Alert-Lauf über den vorhandenen Scheduler | `services/scheduler_service.py` |

Danach Phase 2 (Kostenmodell → kalkulatorischer DB → Profitabilitäts-Cockpit),
Phase 3 (OOS/EK-Frühwarnung als weitere Regeln — dann nur noch Regel-Definitionen),
Phase 4 (Ziele, Periodenvergleich), Phase 5 (Orchestrator).

**Entscheidungen, die ich von dir brauche, bevor Phase 1 startet:**

1. **Monitor als eigenes Template** (`jtl_monitor`) oder als neuer erster Reiter im
   GF-Cockpit? Ich empfehle das eigene Template: das GF-Cockpit bleibt unangetastet und
   der Monitor ist portalfähig als Startseite.
2. **Alte Aufgabenliste**: parallel weiterlaufen lassen (Empfehlung) oder direkt durch
   das `alerts`-Widget ersetzen?
3. **Rabattbereinigung** (`fWertNettoGesamtFixiert`) nur in neuen Auswertungen — oder
   auch die bestehenden Cockpits umstellen (verschiebt historische Zahlen um 0,02 %)?
4. **Kostenregeln**: fangen wir mit Versand + Verpackung + Skonto an (das, was hier real
   greift), oder gleich inklusive Plattform-/Payment-Gebühren für Marktplatz-Kunden?

# Umsetzungsplan: Datenmonster-Template „Shipman Fulfillment"

Stand: 27.08.2026 · Autor: Analyse auf Basis des Repositorys, Commit `8160434`
Status: **Planung, nicht freigegeben.** Kein Code geschrieben.

---

## 0. Kernbefund vorab

Die Analyse hat vier Blockierer gefunden, die vor dem Feinentwurf entschieden
werden müssen. Sie betreffen nicht die Shipman-API, sondern die Datenmonster-
Plattform:

| # | Befund | Auswirkung |
|---|---|---|
| **B1** | Der REST-Node im Mapping kann **keinen Request-Body senden**. `mapping_service.py:1541` und `:1476` rufen `requests.post(url, headers=…)` ohne `json=`/`data=`. | `POST /orders` ist als Mapping-Node **nicht baubar**. |
| **B2** | Ein Template kann **keinen Python-, Datenqualitäts-, Ausdrucks-, Parameter- oder KI-Node ausliefern**. Der Installer überträgt nur 11 der 16 Node-Arrays (`templates.py:664-677`). | Adress-Trennlogik und Datenqualitätsregel – beides in der Aufgabe ausdrücklich als Python-/DQ-Node vorgesehen – sind im Template nicht auslieferbar. |
| **B3** | `dataset_write_mode: "upsert"` und `"append"` sind **wirkungslos**: der Code liest den Dataset-Speicher mit `json.load()` (`mapping_writer.py:57,84`), gespeichert wird aber Parquet (`file_service.py:447`). Der Lesefehler wird verschluckt (`except: existing = []`), Ergebnis ist ein stilles **Replace**. | Das Journal-Muster – der Kern des Entwurfs – funktioniert auf einem Dataset-Ziel nicht. |
| **B4** | Es gibt **keine eingehende REST-Schnittstelle**. Kein Router in `main.py:406-456` nimmt unauthentifizierte Fremddaten an; `/api/rest-sources/{id}/trigger` ist ein interner, Editor-authentifizierter Auslöser für einen *ausgehenden* Import. | Ein Push-Rückkanal von Shipman ist nicht möglich. Der Rückkanal muss pollen. |

Keiner der vier ist unlösbar, aber jeder verschiebt Aufwand. Der Plan macht in
§2 pro Blockierer einen Vorschlag (Plattformfunktion nachrüsten vs. im Template
umgehen) und in §7 eine Reihenfolge daraus.

**Widersprüche in der Aufgabenstellung**, wie erbeten benannt statt geglättet:

1. Phase 1 Frage 5 fragt, „wie eigene Endpunkte definiert und authentifiziert
   werden". Solche Endpunkte gibt es nicht (B4). Die Frage setzt eine Fähigkeit
   voraus, die die Plattform nicht hat.
2. Phase 1 Frage 2 fragt nach einer „Node-Registry". Es gibt keine. Node-Typen
   sind an drei Stellen fest verdrahtet (§1.2).
3. Der Abschnitt „Bekannte Mapping-Fallstricke" schreibt die Adresstrennung
   einem **Python-Node** zu und verlangt zusätzlich eine **Datenqualitätsregel**.
   Beides ist per Template nicht installierbar (B2).
4. Das Journal-Muster setzt auf ein Dataset mit Upsert. Das ist derzeit defekt
   (B3).
5. Kleinere Ungenauigkeit: Die Aufgabe verweist auf Plattformfähigkeiten, die
   ich selbst gestern in `whatwecan.md` und `Anleitung.md` beschrieben habe.
   Zwei davon sind dort **falsch** und werden hier korrigiert: die eingehende
   REST-Schnittstelle (B4) und „FTP/SFTP-Ablage" als Mapping-Ziel – FTP ist
   ausschließlich ein Pipeline-Schritt, `_BUILTIN_TARGET_TYPES` in
   `mapping_writer.py:9` kennt kein `ftp`. Beide Dateien sind zu berichtigen.

---

## 1. Ist-Analyse

### 1.1 Template-Format, Installation und Abgleich

**Format** — eine einzelne JSON-Datei. Referenz: `doku/template-format.md`
(770 Zeilen, aus dem Code hergeleitet). Reale Beispiele: `templates/*.json`.

Top-Level-Schlüssel, wie sie in `templates/jtl_gf_cockpit.json` tatsächlich
vorkommen: `format_version`, `template_id`, `template_name`, `description`,
`category`, `version`, `author`, `hinweise`, `config_required`, `datasets`,
`mappings`, `pipelines`, `forms`, `alert_rules`. `templates/jtl_intrastat.json`
hat zusätzlich `reports` und das abwärtskompatible Singular `pipeline`.

> **Lücke in der Doku:** `alert_rules` wird vom Installer voll unterstützt
> (`templates.py:785-823`), ist in `doku/template-format.md` aber **nicht
> dokumentiert**. Gleiches gilt für `reports`. Wer nach der Doku baut, kann die
> in der Aufgabe geforderten Warnregeln nicht mitliefern.

**Installation** — `POST /api/templates/install`, `templates.py:282`.
Ablauf: `config_required` abfragen → `{{key}}`-Platzhalter rekursiv ersetzen
(`_apply_config_deep`) → Datasets → Mappings → Pipelines → Formulare →
Warnregeln → Installationsprotokoll.

**Abgleich gegen Bestehendes** — pro Objekttyp unterschiedlich, das ist für die
Entwicklungsschleife wichtig:

| Objekt | Verhalten bei Namensgleichheit im Projekt | Fundstelle |
|---|---|---|
| Mapping | **wird überschrieben** (alle Node-Arrays + targets neu gesetzt) | `templates.py:683-694` |
| Formular | **bleibt unangetastet**, nur als `reused` gemeldet | `templates.py:744-750` |
| Warnregel | Abgleich über `rule_key`; aktualisiert, aber `active`/`severity`/`sort` bleiben, wie der Anwender sie gesetzt hat | `templates.py:808-812` |
| Dataset | über `_bestehendes()` / `refs` aus dem Installationsprotokoll | `templates.py:838-850` |

> **Konsequenz für die Bauphase:** Formularänderungen kommen per Re-Install
> **nicht** an. Das ist Absicht (installierte Dashboards werden im Betrieb
> gepatcht), heißt aber: jede Schema-Änderung am Cockpit während der Entwicklung
> erfordert Löschen des Formulars oder ein gezieltes Patchen per API.

Deinstallation läuft ID-basiert über das Installationsprotokoll
(`t.installations`, `templates.py:834-852`), nicht über Namen.

### 1.2 Node-„Registry" — es gibt keine

Ein Node-Typ ist an **drei** Stellen fest verdrahtet:

1. **Modell** — eine eigene JSON-Spalte in `models/mapping.py:11-29`.
   Vorhanden: `canvas_nodes`, `joins`, `transform_nodes`, `constant_nodes`,
   `sql_nodes`, `agg_nodes`, `rest_nodes`, `lookup_nodes`, `calc_nodes`,
   `switch_nodes`, `sort_nodes`, `python_nodes`, `ai_nodes`, `expr_nodes`,
   `quality_nodes`, `param_nodes` — 16 Arrays.
2. **Ausführung** — ein hartkodierter Block in `services/mapping_service.py`
   (z. B. REST ab `:1390`, Lookup ab `:1565`).
3. **Oberfläche** — eine React-Komponente je Typ in
   `frontend/src/components/mapping/`.

Ein neuer Node-Typ bedeutet also: Migration + Service-Block + Komponente +
Template-Format + Installer. Es gibt keinen Erweiterungspunkt, über den ein
Plugin einen Node beisteuern könnte.

**Kritisch (B2):** Der Installer setzt nur diese Arrays
(`templates.py:664-677`): `canvas_nodes`, `joins`, `sql_nodes`, `agg_nodes`,
`transform_nodes`, `constant_nodes`, `rest_nodes`, `lookup_nodes`,
`calc_nodes`, `switch_nodes`, `sort_nodes`, `targets`.
Der Export (`templates.py:1078-1094`) exportiert dieselben elf.
**`python_nodes`, `ai_nodes`, `expr_nodes`, `quality_nodes` und `param_nodes`
gehen bei Export und Import verloren** — ohne Fehlermeldung.

### 1.3 REST: zwei Implementierungen mit sehr unterschiedlicher Reife

Das ist der wichtigste Befund der Analyse.

**(a) `services/rest_service.py` (914 Zeilen) — der ausgereifte Weg.**
Genutzt von REST-Quellen, API Studio und dem Pipeline-Node `rest_fetch`.

- Auth: `none`, `basic`, `bearer`, `apikey` (Header oder Query), `oauth2_cc`
  (Client Credentials mit Token-Cache), `oauth2_refresh` (`:266-305`)
- Methoden: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
- Body: `none`, `json`, `form`, `multipart`, `xml`, `raw` (`:318-360`)
- **Retry**: 3 Versuche bei 429/502/503/504 und Netzaussetzern, exponentieller
  Backoff, `Retry-After` wird respektiert, Deckel 60 s (`:37-45`, `:361-425`).
  500 wird bewusst **nicht** wiederholt.
- **Timeout**: Vorgabe 30 s, Parameter
- **SSRF-Schutz**: jeder Aufruf über `guarded_request` inkl. Redirect-Hops
- Variablen: `{{heute}}`, `{{timestamp}}` u. a. plus freie Umgebungsvariablen
- Paginierung: `page`, `offset`, `cursor`, `link_header`
- Zugangsdaten verschlüsselt (`_decrypt_auth_config`, `:91`)

**(b) Der REST-Node im Mapping (`mapping_service.py:1390-1562`) — eine eigene,
deutlich einfachere Implementierung.**

- Auth: nur `bearer`, `apikey`, `basic`, jeweils mit **statischem** Wert aus der
  Node-Konfiguration (`:1407-1420`). Kein Token aus einem vorherigen Schritt.
- **Kein Request-Body.** `_req.post(url, headers=headers, timeout=10)`
  (`:1541`) bzw. `timeout=30` im Batch-Zweig (`:1476`). **Das ist B1.**
- Kein Retry. Timeout fest (10 s einzeln, 30 s Batch).
- **Kein SSRF-Guard** – nutzt `requests` direkt statt `guarded_request`.
- Platzhalter nur `{feldname}` und `{value}` aus der Zeile (`:1538`), **keine**
  Laufzeitparameter aus `run_params`.
- Fehler werden als Text ins Zielfeld geschrieben:
  `"[API-Fehler: …]"` (`:1556`) – keine getrennte Statusspalte.
- Antwortwerte werden im Einzelmodus per `str(val)` zu Strings (`:1561`).

Der Mapping-REST-Node ist damit ein **GET-Anreicherungsnode**, kein
Integrationsbaustein.

### 1.4 Pipelines

Node-Typen laut `services/pipeline_service.py:78-460`: `trigger`, `ftp`,
`dispatcher`, `mapping`, `email`, `condition`, `rest_fetch`,
`business_insights`, `ftp_upload`.

**Werteübergabe zwischen Schritten** — `_get_prev_data` (`:524-530`):

```
für jede Verbindung c: wenn c["to_node"] == node_id → return results[c["from_node"]]
```

Es wird die **erste** eingehende Verbindung genommen und deren Ergebnis-Dict
(`{"status", "rows", "df"}`) zurückgegeben. **Ein Node kann nicht zwei
Vorgänger zusammenführen.** Das ist für die Auth-Frage entscheidend (§2.4).

**`rest_fetch` kann, was der Mapping-Node nicht kann** (`:243-336`):

- ruft `fetch_rest_source` auf → volle Auth-, Body- und Retry-Palette aus (a)
- `config.for_each: true` → **ein Aufruf pro Zeile des Vorgängers**, gedeckelt
  auf `config.for_each_max`, Vorgabe **100** (`:272`)
- `_mit_zeilenwerten` (`:494-520`) ersetzt `{{spalte}}` in **allen** Quellfeldern
  einschließlich `body_content`, `headers`, `url`, `query_params`
- eingesetzte Spalten werden dem Ergebnis als Spalten beigefügt (`:288-291`),
  sodass sich Antwort und Auslöserzeile zuordnen lassen
- einzelne fehlgeschlagene Aufrufe brechen den Lauf **nicht** ab, sie werden
  gesammelt protokolliert (`:283-287`, `:297-303`)
- das Ergebnis kann in ein Dataset geschrieben werden (`:325-331`)

Einschränkung: `_mit_zeilenwerten._inject` ersetzt per `str(v)` **im Textkörper**.
Der Body ist ein String mit Platzhaltern – kein strukturierter Aufbau. Folgen:
Anführungszeichen oder Backslashes in Kundennamen zerstören das JSON, und ein
**variabel langes `items[]`-Array lässt sich so nicht erzeugen**.

### 1.5 Eingehende REST-Schnittstelle — nicht vorhanden (B4)

Alle 39 Router in `main.py:406-456` sind ausgehend oder verwaltend. Der einzige
Kandidat, `POST /api/rest-sources/{id}/trigger` (`rest_sources.py:398`),
verlangt `get_current_user` **und** `require_editor` und stößt lediglich den
Abruf einer *ausgehenden* Quelle an. Der Portal-Router (`portal.py`) bedient
Formulare, nimmt aber keine Fremdsysteme entgegen.

Es gibt keinen Weg, dass Shipman von sich aus etwas liefert.

### 1.6 Ziele und „Upsert nach Schlüssel"

`_BUILTIN_TARGET_TYPES` (`mapping_writer.py:9`):
`csv`, `xlsx`, `json`, `xml`, `db`, `dataset`, `destatis_csv`, `destatis_idev`,
`destatis_intra_csv`. Alles andere wird an ein Plugin-Ziel geleitet
(`_is_plugin_target`). **Kein FTP-Ziel.**

**DB-Ziel** (`export_to_db`): `insert`, `truncate_insert`, `update`, `upsert`,
`delete`, Schlüsselspalten über `target_options.key_columns`.

**Dataset-Ziel** (`mapping_writer.py:26-134`) — hier liegt **B3**:

```
Zeile 45:  if write_mode == "append" and getattr(ds, "file_path", None):
Zeile 57:      with open(ds.file_path, "r", encoding="utf-8") as ef:
Zeile 58:          existing = json.load(ef)
Zeile 59-60:  except Exception: existing = []
```

`ds.file_path` ist laut `models/dataset.py:13` der **Parquet**-Pfad, gesetzt in
`mapping_writer.py:132` aus `dataframe_to_storage`, das
`dataset_{id}.parquet` schreibt (`file_service.py:445-455`). `json.load` auf
eine Parquet-Datei wirft immer; der Block fängt das ab und macht mit
`existing = []` weiter. Der Upsert-Zweig (`:78-113`) hat dieselbe Konstruktion.

**Ergebnis: Append und Upsert auf Dataset-Zielen verhalten sich wie Replace,
ohne Fehlermeldung.** Zusätzlich wäre der Ansatz selbst bei korrektem Lesen ein
Read-Modify-Write der kompletten Datei – bei jedem Lauf, für jede Zeile.

Ein weiterer Stolperstein derselben Funktion (`:34-38`): Ein Dataset-Ziel mit
einem Namen, den bereits ein Dataset **eines anderen Mappings** trägt, wirft
einen Fehler. Journal-Datasets brauchen also projektweit eindeutige Namen.

### 1.7 Stammdaten-Rückschreiben: Kollisionsschutz und Trockenlauf

`services/jtl_artikel_writer.py` (495 Zeilen) plus API `api/stammdaten.py`.

Muster: `build_plan(aenderungen, dry_run=True)` löst read-only auf, prüft und
liefert einen `ArtikelWritePlan`; `write` läuft nur mit `bestaetigt=true` und
führt **vor** dem Schreiben erneut eine frische Vorschau aus
(`stammdaten.py:173-190`) – geschrieben wird gegen deren Ergebnis, nicht gegen
das, was die Oberfläche zu wissen glaubt.

Kollisionsschutz: `bRowversion` beider Zieltabellen wird beim Laden mitgelesen
(`jtl_artikel_writer.py:266-267`) und beim UPDATE als Bedingung verwendet
(optimistisches Sperren). Weitere Sicherungen: Feld-Whitelist `FELDER`,
Obergrenze `MAX_AENDERUNGEN` je Lauf, EAN-Dublettenprüfung.

> **Wichtig für diesen Plan:** Das ist **kein wiederverwendbarer Baustein.** Der
> Writer ist fest auf `tArtikel`/`tArtikelBeschreibung` verdrahtet. Für
> Versanddaten gibt es nichts Vergleichbares; das Muster wäre nachzubauen.

### 1.8 Warn-Engine

Modell `models/alert.py`. Eine Regel ist **Daten, kein Code**. Felder u. a.:
`rule_key`, `name`, `category`, `cockpit`, `severity`, `severity_levels`,
`mapping_id` **oder** `mapping_name`, `params`, `condition`, `facts`,
`title_template`, `subtitle`, `drilldown`, `action_kind`, `active`, `sort`.

`condition.mode`:
- `count` – Warnung, sobald die Ergebnisliste Zeilen hat
- `kpi` – Vergleich innerhalb einer Kennzahlenzeile, optional gegen einen
  zentralen Schwellwert über `condition.value_config`
  (`alert_service.py:124-131`)
- `rows` – jede Zeile wird zu einer eigenen Warnung

Der Bezug auf ein Mapping läuft bevorzugt über `mapping_name`, weil IDs je
Installation verschieden sind; fehlt das Mapping, meldet sich die Regel als
„nicht verfügbar" statt zu scheitern. Auslieferung im Template über
`alert_rules[]` (§1.1). Zentrale Schwellwerte liegen in `business_config`
(`api/business_config.py`, `GET/PUT /thresholds`).

### 1.9 Formulare im Template

Struktur: `{ name, schema: { fields, layout, actions, widgets, result_tabs,
show_ai_assistant }, portal_config }`.

**Action-Typen** (`api/forms.py:585-690`) — die Doku nennt nur die ersten zwei:

| Typ | Verhalten |
|---|---|
| `run_mapping` | **read-only.** Ruft `execute_mapping` (`forms.py:493-528`) – Vorschau, **Ziele werden nicht geschrieben.** Mehrere laufen gedrosselt parallel. |
| `export_mapping` | **Schreiblauf.** Ruft `run_mapping_object` (`forms.py:647-689`) – schreibt alle Ziele und legt Export-Dateien an. |
| `run_pipeline` | startet eine Pipeline |
| `run_alerts` | wertet die Warnregeln aus, optional auf `cockpits`/`rule_keys` eingegrenzt |

> **Zentral für dieses Template:** Ein Button, der Aufträge übermittelt und das
> Journal fortschreibt, **muss `export_mapping` oder `run_pipeline` sein.**
> `run_mapping` würde nichts schreiben – und zwar lautlos.

Beim Install wird `mapping_id` in Actions typunabhängig aufgelöst
(`templates.py:752-755`), `export_mapping` ist also auslieferbar.

Widget-Typen im Code (`WidgetRenderer.tsx:24-30`): `table`, `kpi`, `bar`,
`line`, `pie`, `ai_summary`, `tasklist`, `alerts`, `kostenstruktur`,
`eingangsrechnung`, `ean_research`, `hersteller_navigator`. Die Doku kennt nur
sieben davon.

---

## 2. Machbarkeit

### 2.1 Was ohne Änderung an der Plattform geht

- **Auftragsselektion aus JTL** – SQL-Node gegen `Verkauf.tAuftrag`, mit
  Laufzeitparametern. Bewährtes Muster aus sechs Cockpits.
- **`POST /orders` je Auftrag** – als **REST-Quelle + Pipeline-Node
  `rest_fetch` mit `for_each: true`** (§1.4). Body als JSON-Vorlage mit
  `{{spalte}}`-Platzhaltern, Auth-Header ebenso.
- **`GET /orders/{ID}/tracking` je offenem Auftrag** – dasselbe Muster.
- **Journal als Tabelle** – siehe §2.3, aber **nicht** als Dataset-Upsert.
- **Cockpit** – Formular mit `run_mapping`-Actions und Tabellen/KPI-Widgets,
  Drilldown, manueller Wiederanstoß über einen `export_mapping`- oder
  `run_pipeline`-Button.
- **Warnregeln** – vier Stück als `alert_rules[]`, Schwellwerte über
  `condition.value_config` gegen `business_config`.
- **Trackingcode-Katalog** – `datasets[]` mit `file_type: "static"` und
  `initial_data` (`template-format.md` §4.3).
- **Zeitsteuerung** – `pipelines[].scheduler.cron`; fehlt ein Trigger-Node,
  ergänzt ihn der Installer.

### 2.2 Was fehlt — Vorschlag je Blockierer

**B1 – REST-Node ohne Body.**
*Empfehlung: im Template umgehen, nicht nachrüsten.* Der Pipeline-Weg
(`rest_fetch` + `for_each`) kann alles Nötige und ist der gepflegte Codepfad
mit Retry und SSRF-Schutz. Den Mapping-REST-Node nachzurüsten hieße, eine
zweite, schwächere HTTP-Implementierung auszubauen, statt sie loszuwerden.
*Mittelfristig* sollte der Mapping-Node auf `rest_service` umgestellt werden –
das ist eine eigene Aufgabe, kein Teil dieses Templates.

**B2 – Python-/DQ-Node nicht auslieferbar.**
Zwei Wege:
- *(a) Im Template umgehen:* Adresstrennung und Feldlängenprüfung **in T-SQL**
  im selben SQL-Node, der die Aufträge selektiert. Machbar (`CHARINDEX`,
  `PATINDEX`, `REVERSE`, `LEFT`/`RIGHT`), aber schwerer lesbar und schwerer zu
  testen als ein Python-Node.
- *(b) Plattform nachrüsten:* die fünf fehlenden Arrays in
  `templates.py:664-677` und `:1078-1094` ergänzen. Überschaubarer Eingriff,
  aber er verändert Export- und Importverhalten für **alle** Templates und
  braucht eigene Tests.

*Empfehlung: (a) für dieses Template, (b) als getrennter Plattform-Vorgang.*
Begründung: die Trennlogik gehört ohnehin dorthin, wo auch die Datenqualität
entschieden wird – und in SQL sieht man sie im selben Statement wie die
Selektion. Das nimmt der Aussage „nicht trennbare Fälle in den Fehlerstatus"
die Sonderbehandlung: sie wird zu einer `CASE`-Spalte.

**B3 – Dataset-Upsert defekt.**
Drei Wege:
- *(a) Journal in einer eigenen Datenbank* (Ziel `target_type: "db"`,
  `write_mode: "upsert"`, `key_columns: ["id_external"]`). Dieser Pfad ist
  intakt und wird produktiv genutzt. Braucht eine schreibbare Verbindung –
  **nicht** die JTL-Datenbank, sondern eine separate (SQLite-Datei, MySQL,
  Postgres) als zweiter `config_required`-Eintrag.
- *(b) B3 vorher reparieren* (Parquet statt `json.load` lesen). Kleiner Fix,
  aber er verändert stillschweigend das Verhalten aller bestehenden Mappings mit
  `append`/`upsert` auf Dataset-Zielen – die laufen heute faktisch als Replace,
  und irgendwo verlässt sich womöglich etwas darauf.
- *(c) Journal ganz vermeiden*, Zustand aus Shipman zurücklesen. Scheidet aus:
  es gibt keinen Listen-Endpunkt.

*Empfehlung: (a).* Begründung: Der Fix (b) ist richtig und sollte kommen, aber
er darf nicht auf dem kritischen Pfad dieses Templates liegen. (a) ist zudem
sachlich besser: ein Journal ist eine transaktionale Tabelle mit Schlüssel und
Nebenläufigkeit, keine Auswertungsdatei.

> **Zur Frage aus der Aufgabe, ab welchem Volumen das relevant wird:** Der
> Dataset-Weg ist ein vollständiger Read-Modify-Write je Lauf. Schon bei
> einigen tausend Journalzeilen und stündlichem Lauf ist das spürbar, und es
> gibt keine Nebenläufigkeitssicherung – zwei gleichzeitige Läufe verlieren
> Schreibvorgänge. Der DB-Weg hat beides nicht. Die Grenze ist damit weniger
> eine Zeilenzahl als die Frage, ob je zwei Läufe gleichzeitig laufen können.
> Sobald der Zeitplan enger ist als die Laufzeit, ist (a) zwingend.

**B4 – kein Push-Rückkanal.**
*Empfehlung: im Template umgehen.* Der Rückkanal pollt ohnehin, weil Shipman
keine Zustellung anbietet. Eine eingehende Schnittstelle nachzurüsten wäre ein
großes Sicherheitsthema (Authentifizierung, Ratenbegrenzung, Wiedergabeschutz)
und für Shipman nutzlos.

### 2.3 Was mit dieser API grundsätzlich nicht baubar ist

Wie in der Aufgabe vorgegeben, hier als ausdrückliche Einschränkung:

- **Kein Bestandsabgleich.** Es gibt keinen Bestands-Endpunkt. JTL kennt den
  Bestand im Fulfillment-Lager nicht.
- **Kein Artikelstamm-Sync.** `items[].item` verweist auf eine Kennung, die im
  Shipman-System bereits existieren muss. Wie sie dorthin kommt, ist nicht Teil
  der API.
- **Kein Wareneingang, keine Retourenmeldung, kein Listen-Endpunkt.**

**Folge und Vorschlag zum Umgang:** Überverkäufe werden nicht erkannt. Drei
Möglichkeiten, in aufsteigendem Aufwand:

1. **Dokumentieren** – in `hinweise[]` des Templates unmissverständlich
   festhalten, dass der Bestand nicht zurückfließt. Minimum, immer nötig.
2. **Zweiter Kanal per Datei** – falls Shipman Bestandslisten per CSV/SFTP
   liefert (nicht dokumentiert, siehe F8 in §3), ein zweites Mapping, das sie in
   JTL einliest. Das ist Standardarbeit für die Plattform.
3. **Portal-Maske zur manuellen Pflege** – ein Formular, in dem das Lager
   Bestände einträgt. Ehrlich, aber Handarbeit.

*Empfehlung: 1 immer, 2 sobald F8 beantwortet ist.*

### 2.4 Die Auth-Kette — der zweite strukturelle Knoten

Anforderung: JWT als ersten Schritt jedes Laufs holen und weiterreichen.

Die Pipeline kann `rest_fetch` (`/auth`) → `rest_fetch` (`/orders`) verketten.
`_mit_zeilenwerten` setzt `{{access_token}}` in Header und Body ein. **Aber:**
`_get_prev_data` liefert nur **einen** Vorgänger (§1.4). Der `/orders`-Node
braucht gleichzeitig
- die Auftragsliste (für `for_each`) und
- den Token (aus dem `/auth`-Schritt).

Das geht mit dem heutigen Pipeline-Modell **nicht direkt**. Vier Optionen:

| Option | Bewertung |
|---|---|
| **A: Token als Spalte an jede Auftragszeile** | Bräuchte einen Schritt, der Token und Liste zusammenführt – genau das fehlt. Ein Mapping kann den Token nicht kennen. **Scheidet aus.** |
| **B: Auth über `auth_type` der REST-Quelle statt über die Kette** | `rest_service` kann `oauth2_cc` mit Token-Cache – aber Shipman ist kein OAuth2-Client-Credentials-Fluss, sondern ein eigener `/auth`-Endpunkt mit `username`/`password` im JSON-Body. Passt **nicht** auf die vorhandenen Auth-Typen. |
| **C: Langlebiger Token in der Verbindungskonfiguration** | Setzt eine bekannte, lange Token-Laufzeit voraus – ist **undokumentiert** (F5). Nicht planbar, bevor F5 beantwortet ist. |
| **D: `_get_prev_data` um Mehrfach-Eingänge erweitern** | Plattformänderung, ~30 Zeilen, aber sie berührt jeden Pipeline-Node. |

*Empfehlung: Entscheidung vertagen, bis F5 (Token-Lebensdauer) beantwortet ist.*
Ist der Token lang genug gültig (Stunden), ist **C** der einfachste Weg mit einem
Erneuerungsschritt im Zeitplan. Ist er kurzlebig, führt kein Weg an **D** vorbei.
Das ist der zweite Grund, warum der Testplan (§4) vor dem Feinentwurf steht.

**Zugangsdaten** kommen in jedem Fall in die verschlüsselte
Verbindungsverwaltung (REST-Quelle mit `auth_config`, `_decrypt_auth_config`),
nicht in ein Mapping und nicht ins Template.

### 2.5 Rückschreiben in die Wawi — Bewertung der drei Wege

Die Vorgabe „kein direkter INSERT von Versanddaten in die JTL-Datenbank" ist
fachlich richtig und wird hier nicht in Frage gestellt: an einem Versandvorgang
hängen Bestandsbuchung, Statusfortschreibung und Marktplatzrückmeldung. Ein
INSERT in `tVersand`/`tLieferschein` erzeugt einen Beleg, der nach außen nie
gemeldet wird.

| Weg | Bewertung |
|---|---|
| **Versanddaten-Import des Fulfillment-Lagers** (JTL-Wawi-Funktion „Versanddaten importieren") | Fachlich der vorgesehene Weg: JTL bucht selbst und meldet an Marktplätze. Datenmonster erzeugt lediglich eine Datei im erwarteten Format. **Offen:** ob dieser Import beim Kunden lizenziert und eingerichtet ist. |
| **JTL-Wawi-API (REST, lokal, lizenzpflichtig)** | Sauberste Kopplung, echte Rückmeldung. Zusätzliche Lizenz und lokale Installation nötig; unbekannt, ob beim Kunden vorhanden. |
| **Ameise-Import** | Funktioniert, ist aber ein Kommandozeilenwerkzeug auf dem Wawi-Rechner. Datenmonster läuft im Container und müsste die Datei nur bereitstellen; die Ausführung liegt außerhalb. Betrieblich der fragilste Weg. |

*Empfehlung: Versanddaten-Import als Vorgabe, JTL-API als Ausbaustufe.*
Begründung: Der Versanddaten-Import ist genau für diesen Fall gebaut
(Fulfillment meldet Tracking zurück), braucht keine zusätzliche Lizenz und
lässt Datenmonster bei dem, was es gut kann – eine Datei erzeugen. Das Template
sollte den Tracking-Export deshalb als **Datei-Ziel** ausführen und **nicht**
selbst in die Wawi schreiben.

*Voraussetzung:* Das genaue Spaltenformat des Versanddaten-Imports ist zu
klären (F11) – es steht nicht in diesem Repository.

**Abliefernachweis (Base64-PDF).** Hier gibt es eine **Lücke**: Der REST-Weg
liefert den Nachweis als Base64-**String** in einer Spalte. Es gibt in
Datenmonster keinen Schritt, der einen Base64-Wert in eine Binärdatei
dekodiert und ablegt – `_BUILTIN_TARGET_TYPES` kennt nur tabellarische Formate,
und der Mapping-Node-Vorrat hat keine Dekodierfunktion (`expr_nodes` wären ein
Kandidat, sind aber nicht auslieferbar, B2). Optionen:
- den Base64-String im Journal ablegen und die Datei **außerhalb** erzeugen
  (Skript, das die Datenbank liest) – pragmatisch, aber außerhalb des Templates
- ein neues Datei-Ziel „Binärspalte als Datei" in der Plattform – sauber,
  aber eine Plattformerweiterung
- den Nachweis gar nicht holen und nur die `tracking_url` speichern, unter der
  er beim Carrier liegt – **die billigste brauchbare Lösung**

*Empfehlung: zunächst nur `tracking_url` und die Flags speichern; das Holen der
Signaturen erst in Phase 4, wenn geklärt ist, wohin die PDF soll.*

---

## 3. Offene Fragen an Shipman

Priorisiert. „Blockierend" heißt: ohne Antwort lässt sich der betroffene
Teil nicht entwerfen, nur raten.

| # | Frage | Warum | Status |
|---|---|---|---|
| **F1** | **Was liefert `POST /orders` tatsächlich zurück, und woher kommt die `ID` für `/orders/{ID}/…`?** Ist es `id_external`? Eine eigene numerische ID? Steht sie im `Location`-Header? | Ohne die ID sind Tracking, Signaturen und Storno **nicht aufrufbar**. Die Spec gibt `CreateOrderDto` als Antwort an, worin kein ID-Feld existiert. | **blockierend** – der gesamte Rückkanal und das Storno hängen daran |
| **F2** | **Wie lautet die Basis-URL?** `https://shipman-api.de/api/` (Swagger) oder `https://shipman-api.de/` (cURL-Beispiele)? Die OpenAPI-Spec hat keine `servers`. | Jeder Aufruf. Trivial zu klären, aber blockierend. | **blockierend** |
| **F3** | **Was passiert bei doppelt übermittelter `id_external`?** Ablehnung, zweiter Auftrag oder stille Übernahme? | Bestimmt, wie streng das Journal sein muss und ob ein Wiederholungslauf nach einem Abbruch gefährlich ist. | **blockierend** für die Idempotenz-Zusage |
| **F4** | **Welche HTTP-Fehlercodes und Fehlerobjekte gibt es?** Speziell: Validierungsfehler, abgelaufener Token, unbekannte Order-ID. | Ohne das lässt sich `fehlgeschlagen` nicht von „später erneut versuchen" unterscheiden. Nur Erfolgsfälle sind spezifiziert. | **blockierend** für die Fehlerbehandlung |
| **F5** | **JWT-Lebensdauer, Refresh, Ratenbegrenzung.** | Entscheidet zwischen Option C und D in §2.4 – also über die Pipeline-Architektur. | **blockierend** für die Auth-Kette |
| F6 | **Welche Artikel-Kennungen sind in `items[].item` zulässig, und wie wird der `alias:`-Namensraum gepflegt?** | Ohne das ist unklar, welches JTL-Feld gemappt wird. Wird als Template-Parameter geplant, aber ein Fehlmapping bricht jeden Auftrag. | hoch |
| F7 | **Vollständige Liste der Trackingcodes je Carrier**, oder Bestätigung, dass sie durchgereicht werden. | Bestimmt, ob der Katalog aus §5 dauerhaft nötig ist. Die Statusableitung ist bewusst so gebaut, dass sie ohne diese Antwort auskommt. | mittel |
| F8 | **Gibt es einen Bestandsrückfluss außerhalb der API** (CSV, SFTP, Portal)? | Entscheidet über §2.3 Option 2. | mittel |
| F9 | **Grenzwerte:** maximale Positionsanzahl, Dokumentgröße, zulässige Dokumenttypen, Zeichencodierung, zulässige `country_code`-Werte. | Feldlängen werden ohnehin vorab gekürzt; die übrigen Grenzen sind unbekannt. | mittel |
| F10 | **Verhalten von `PUT /cancel`** bei bereits versandtem oder unbekanntem Auftrag. | Bestimmt den Storno-Zweig. | mittel |
| F11 | *(an den Kunden, nicht an Shipman)* **Welcher Rückschreibeweg in die Wawi ist verfügbar** – Versanddaten-Import, JTL-API-Lizenz, Ameise? | Bestimmt §2.5. | **blockierend** für Phase 4 |

---

## 4. Testplan für das API Studio

Ziel: F1–F5 klären, bevor irgendein Template-Objekt entworfen wird. Alles im
**API Studio** (`api/api_studio.py`), das Sammlungen, Umgebungen, Verlauf und
einen Fehler-Debugger mitbringt und Geheimnisse maskiert.

**Vorbereitung**
1. Umgebung `shipman-test` anlegen mit `basis_url`, `benutzer`, `passwort`
   (letzteres als Geheimnis).
2. Sammlung `Shipman` anlegen, Basis-URL aus der Umgebung.

**T1 – Basis-URL klären (F2)**
Zwei Aufrufe `POST {{basis_url}}/auth` mit `https://shipman-api.de` und
`https://shipman-api.de/api` als `basis_url`. Erwartung: einer liefert 200 mit
`access_token`, der andere 404.
*Ergebnis festhalten:* die funktionierende Basis-URL.

**T2 – Auth und Token-Form (F5, Teil 1)**
`POST /auth` mit gültigen Zugangsdaten. Festhalten: Statuscode, vollständiger
Antwortkörper (gibt es außer `access_token` noch `expires_in`, `refresh_token`?),
Antwortheader (`Retry-After`, Ratenbegrenzungsheader).
Danach das JWT dekodieren (Base64, Mittelteil) und `exp` ablesen – **das
beantwortet F5 ohne Rückfrage bei Shipman.**

**T3 – Der kritische Test: was liefert `POST /orders`? (F1)**
Einen minimalen Auftrag anlegen: nur `name` und `data.id_external`, `items` mit
einer bekannten Kennung. Festhalten:
- **vollständiger** Antwortkörper, Feld für Feld
- **alle** Antwortheader, besonders `Location`
- Statuscode (201 erwartet)

*Das ist der wichtigste Aufruf des ganzen Plans.* Kommt hier keine ID, sind
Tracking, Signaturen und Storno nicht erreichbar und die Integration ist auf
eine Einbahnstraße reduziert – dann muss Shipman gefragt werden, bevor
weitergeplant wird.

**T4 – ID-Kandidaten durchprobieren (F1, Fortsetzung)**
Falls T3 keine explizite ID liefert, mit `GET /orders/{X}/tracking` prüfen,
welcher Wert als `{ID}` funktioniert: die `id_external`, der `name`, ein Wert
aus dem `Location`-Header. Erfolgreich = 200 statt 404.
*Reihenfolge wichtig:* zuerst `id_external`, das ist der plausibelste Kandidat.

**T5 – Doppelte `id_external` (F3)**
T3 mit **identischem** `id_external` wiederholen. Festhalten: Statuscode und ob
danach zwei Aufträge existieren (über T4 prüfbar).
*Achtung:* Das erzeugt einen echten zweiten Versandauftrag, falls die API keine
Dedup macht. **Nur im Testmandanten ausführen** und, falls möglich, direkt per
`PUT /cancel` aufräumen.

**T6 – Fehlerobjekte (F4)**
Vier gezielte Fehlaufrufe, jeweils Statuscode und Antwortkörper festhalten:
- `POST /orders` ohne `name` (Pflichtfeld fehlt)
- `POST /orders` mit `delivery_address`, in der `house_number` fehlt
- `POST /orders` mit `name` über 250 Zeichen
- `GET /orders/{unbekannt}/tracking`
- ein beliebiger Aufruf mit abgelaufenem oder verfälschtem Token

**T7 – Tracking-Struktur (F7)**
`GET /orders/{ID}/tracking` für einen realen, bereits versendeten Auftrag.
Festhalten: welche `code`-Werte tatsächlich vorkommen und ob die Booleans
`retoure`/`delivered` gefüllt sind, auch wenn der Code unbekannt ist.

**T8 – Ratenbegrenzung (F5, Teil 2)**
20 Aufrufe von `GET /orders/{ID}/tracking` in schneller Folge. Festhalten: ob
429 auftritt und ob `Retry-After` gesetzt ist. *Relevant, weil der Rückkanal
pro offenem Auftrag einen Aufruf macht und `for_each` bei 100 deckelt.*

**Abschluss:** Ergebnisse aus T1–T8 in diesen Plan zurückschreiben, dann §5–§7
verfeinern. Über „Integration erstellen" im API Studio lassen sich die
funktionierenden Aufrufe direkt in REST-Quellen überführen.

---

## 5. Objektinventar des Templates

Vorläufig – T1–T8 können einzelne Objekte verändern. `[A]` markiert eine
Annahme, die noch zu bestätigen ist.

### Verbindungen und Konfiguration (`config_required`)

| Schlüssel | Typ | Zweck |
|---|---|---|
| `connection_jtl` | `connection` | JTL-Wawi, **lesend** |
| `connection_journal` | `connection` | Journal-Datenbank, **schreibend** – nicht die JTL-DB (§2.2 B3) |
| `shipman_basis_url` | `text` | aus T1 |
| `artikel_kennung_feld` | `text` | welches JTL-Feld auf `items[].item` abbildet, Vorgabe `cArtNr` (F6) |
| `versand_praefix` | `text` | Präfix für `data.id_external`, damit Testläufe unterscheidbar bleiben |

Die Shipman-Zugangsdaten stehen **nicht** hier, sondern in der REST-Quelle
(verschlüsselt).

### Datasets

| Name | Typ | Zweck |
|---|---|---|
| `shipman_journal` | DB-Tabelle in `connection_journal` | Zustand je Auftrag. Felder: `id_external` (Schlüssel), `auftragsnummer`, `shipman_id`, `status`, `payload_hash`, `versuche`, `letzter_fehler`, `erstellt_am`, `geaendert_am`. |
| `shipman_trackingcode_mapping` | `static` mit `initial_data` | Code, Carrier, Klartext, eigene Kategorie. Startbestand: eine Zeile `DLVRD`. |
| `shipman_tracking_roh` | Dataset (Replace) | Antworten des Tracking-Abrufs, Zwischenstufe |

### REST-Quellen

| Name | Aufruf | Anmerkung |
|---|---|---|
| `shipman_auth` | `POST /auth` | Zugangsdaten verschlüsselt; Body `json` |
| `shipman_order_anlegen` | `POST /orders` | Body-Vorlage mit `{{spalte}}`-Platzhaltern; Auth-Header je nach §2.4 |
| `shipman_tracking` | `GET /orders/{{shipman_id}}/tracking` | |
| `shipman_storno` | `PUT /orders/{{shipman_id}}/cancel` | |
| `shipman_signaturen` | `GET /orders/{{shipman_id}}/signatures` | **erst Phase 4**, siehe §2.5 |

### Mappings

| # | Name | Eingang | Ausgang | Zweck |
|---|---|---|---|---|
| M1 | Versandkandidaten ermitteln | SQL auf JTL | Dataset | Aufträge, die zu übermitteln sind: versandbereit, nicht storniert, **nicht** im Journal mit Status ≥ `uebermittelt`. Enthält Adresstrennung und Feldkürzung in T-SQL (§2.2 B2). |
| M2 | Journal fortschreiben nach Übermittlung | Antworten aus der Pipeline | DB-Ziel, `upsert` auf `id_external` | Setzt `shipman_id` und `status = uebermittelt`, erhöht `versuche`. |
| M3 | Offene Sendungen ermitteln | SQL auf Journal | Dataset | Aufträge mit `status IN (uebermittelt, getrackt)` – Eingang für den Tracking-Abruf. |
| M4 | Tracking auswerten | `shipman_tracking_roh` | DB-Ziel `upsert` | Leitet Status **nur aus den Booleans** ab (§ Statusableitung), speichert `code` roh. |
| M5 | Unbekannte Trackingcodes sammeln | `shipman_tracking_roh` + Katalog | DB-/Dataset-Ziel | Codes, die nicht im Katalog stehen, mit Zähler. |
| M6 | Änderungen nach Übermittlung erkennen | SQL auf JTL + Journal | Dataset | Vergleicht aktuellen `payload_hash` mit dem gespeicherten. |
| M7 | Stornokandidaten | SQL auf JTL + Journal | Dataset | In JTL storniert, in Shipman noch aktiv. |
| M8 | Versanddaten-Export für die Wawi | SQL auf Journal | **Datei-Ziel** (CSV) | Rückschreiben über den JTL-Versanddatenimport (§2.5), Format offen (F11). |
| M9–M12 | Cockpit-Listen | SQL auf Journal | Dataset | Fehlerstatus, überfällig ohne Tracking, `not_delivered`/`returned`, unbekannte Codes. |
| M13 | Detail zu einem Auftrag | SQL auf Journal + JTL | Dataset | Drilldown-Ziel der Cockpit-Tabellen. |

### Pipelines

| # | Name | Ablauf |
|---|---|---|
| P1 | Aufträge übermitteln | Trigger → `rest_fetch` (`/auth`) → Mapping M1 → `rest_fetch` (`/orders`, `for_each`) → Mapping M2 |
| P2 | Tracking abholen | Trigger → `rest_fetch` (`/auth`) → Mapping M3 → `rest_fetch` (`/tracking`, `for_each`) → Mapping M4 → Mapping M5 |
| P3 | Stornos übermitteln | Trigger → `rest_fetch` (`/auth`) → Mapping M7 → `rest_fetch` (`/cancel`, `for_each`) → Mapping M2 |
| P4 | Versanddaten für die Wawi bereitstellen | Trigger → Mapping M8 |

> **Achtung, zwei ungelöste Punkte in P1–P3:** (1) die Auth-Kette aus §2.4 –
> die dargestellte Reihenfolge funktioniert nur mit Option C oder D; (2) der
> `for_each`-Deckel von 100 (`pipeline_service.py:272`). Bei mehr als 100
> offenen Aufträgen je Lauf muss `for_each_max` erhöht **und** die Laufzeit
> geprüft werden – 100 sequenzielle HTTP-Aufrufe mit je bis zu 30 s Timeout
> sind im schlechtesten Fall sehr lang.

### Formular „Fulfillment-Cockpit"

Reiter über `result_tabs`:
1. **Übersicht** – KPI: offen, übermittelt, getrackt, zugestellt, fehlgeschlagen
2. **Fehler** – Tabelle aus M9, Drilldown auf M13, Button `run_pipeline` (P1)
   für den manuellen Wiederanstoß
3. **Überfällig** – Tabelle aus M10 (übermittelt ohne Tracking seit > X Stunden)
4. **Zustellprobleme** – Tabelle aus M11 (`not_delivered` / `returned`)
5. **Unbekannte Trackingcodes** – Tabelle aus M12
6. **Warnungen** – Widget `alerts`, Action `run_alerts` auf
   `cockpits: ["shipman"]`

### Warnregeln (`alert_rules[]`)

| `rule_key` | Bedingung | Schwellwert |
|---|---|---|
| `shipman_ohne_tracking` | `count` auf M10 | `value_config: "shipman_tracking_stunden"` |
| `shipman_versuche` | `count` auf einer M9-Variante | `value_config: "shipman_max_versuche"` |
| `shipman_unbekannter_code` | `count` auf M12 | – (jede Zeile ist meldenswert) |
| `shipman_nicht_zugestellt` | `rows` auf M11 | – |

Alle drei Schwellwerte werden über `business_config` gepflegt, nicht im Template
hart gesetzt.

### Generalisierbarkeit

Die Trennlinie zwischen fachlichem Kern und dienstleisterspezifischer Schicht
verläuft **an der Journaltabelle**:

- **Kern, dienstleisterunabhängig:** `shipman_journal` (umzubenennen in
  `fulfillment_journal`) mit seiner Statusfolge, M3, M5, M9–M13, die vier
  Warnregeln, das Cockpit. Sie kennen nur die Journalspalten.
- **Spezifische Schicht:** die fünf REST-Quellen, M1 (Feldmapping JTL →
  `CreateOrderDto`), M2 und M4 (Auslesen der jeweiligen Antwortstruktur),
  P1–P3.

**Die Schnittstelle zwischen beiden ist der Vertrag über die Journalspalten:**
ein zweiter Dienstleister muss `id_external`, `dienstleister_id`, `status`,
`payload_hash`, `versuche`, `letzter_fehler` füllen und dieselbe Statusfolge
verwenden. Dazu ist eine Spalte `dienstleister` aufzunehmen, damit ein Journal
mehrere bedienen kann. Alles Übrige bleibt unverändert.

*Diese Trennung kostet jetzt fast nichts und ist später kaum nachzuholen –
sie sollte von Anfang an so gebaut werden.*

---

## 6. Feldmapping JTL → `CreateOrderDto`

Quelle der JTL-Namen: die SQL-Knoten der ausgelieferten Cockpits, also real
verwendete Spalten (`templates/jtl_vertrieb_cockpit.json`,
`templates/jtl_versand_cockpit.json`). `[A]` = Annahme, in T1–T8 oder am
Kundensystem zu bestätigen.

| Shipman-Feld | Quelle | Transformation | Anmerkung |
|---|---|---|---|
| `name` | `Verkauf.tAuftrag.cAuftragsNr` | auf 250 kürzen | Einziges Pflichtfeld oben. Auftragsnummer ist der sprechendste Wert. |
| `note` | `Verkauf.tAuftrag.cAnmerkung` `[A]` | auf 750 kürzen | Spaltenname in den Cockpits nicht belegt – **zu prüfen**. |
| `data.id_external` | `{{versand_praefix}}` + `Verkauf.tAuftrag.kAuftrag` | Verkettung | Der Journalschlüssel. `kAuftrag` ist stabil, `cAuftragsNr` theoretisch änderbar. |
| `data.tags` | konstant, z. B. `["datenmonster"]` | – | Erleichtert die Zuordnung auf Shipman-Seite. |
| `data.documents` | – | – | **Nicht befüllen** (Phase 1). Base64-Anhänge sind ungeklärt (F9). |
| `delivery.ship_to_date` | `Verkauf.tAuftrag.dLieferdatum` `[A]` | lokal → **UTC**, ISO-8601 | Zeitzone: JTL liefert lokale Zeit. Umrechnung in T-SQL über `AT TIME ZONE`. |
| `delivery.neutral_packaging` | konstant `false` `[A]` | – | Als Template-Parameter vorsehen, wenn der Kunde neutral versendet. |
| `delivery.notification` | konstant `false` `[A]` | – | dito |
| `delivery.cost_centre` | – | – | Nicht befüllen. |
| `delivery_address.name` | Lieferadresse `cFirma`, sonst `cVorname + ' ' + cName` | `NULLIF`/`ISNULL`-Kaskade wie in den Cockpits, auf 100 kürzen | **Offen:** Die Cockpits verwenden durchgängig `Verkauf.vAuftragRechnungsadresse`. Eine Lieferadress-Sicht ist im Repository **nicht belegt** – der korrekte View bzw. der `tAdresse`-Filter (`nTyp`) ist am Kundensystem zu ermitteln. **Die Rechnungsadresse ist hier falsch.** |
| `delivery_address.name2` | Lieferadresse `cZusatz` `[A]` | auf 100 kürzen | |
| `delivery_address.street` | aus `cStrasse` **getrennt** | siehe unten | |
| `delivery_address.house_number` | aus `cStrasse` **getrennt** | siehe unten, auf 30 kürzen | Pflicht, sobald die Adresse übertragen wird |
| `delivery_address.postal_code` | Lieferadresse `cPLZ` | auf 20 kürzen | |
| `delivery_address.city` | Lieferadresse `cOrt` | auf 100 kürzen | |
| `delivery_address.state` | – | – | JTL führt `cBundesland` leer (bekannt aus dem GF-Cockpit); nicht befüllen. |
| `delivery_address.country_code` | Lieferadresse `cISO` `[A]` | zwei Zeichen, Vorgabe `DE` | Zulässige Werte nicht spezifiziert (F9). |
| `delivery_address.email` | `dbo.tKunde.cMail` `[A]` | auf 100 kürzen | Nur nötig, wenn `notification` genutzt wird. |
| `delivery_address.phone` | `dbo.tKunde.cTel` `[A]` | auf 100 kürzen | |
| `items[].item` | `Verkauf.tAuftragPosition.cArtNr`, Feld konfigurierbar über `{{artikel_kennung_feld}}` | ggf. Präfix `alias:` | F6. `cArtNr` ist in den Cockpits die durchgängig verwendete Artikelkennung. |
| `items[].amount` | `Verkauf.tAuftragPosition.fAnzahl` | – | Nur `POS.nType = 1` (Artikelpositionen); `nType = 2` ist Versand und gehört **nicht** in `items`. Belegt in `jtl_vertrieb_cockpit.json`. |

### Die Adresstrennung — der schwierigste Punkt

JTL hält Straße und Hausnummer in `cStrasse`, Shipman verlangt beide getrennt
und als Pflicht.

**Vorgehen** (in T-SQL, weil Python-Nodes nicht auslieferbar sind, B2):
eine `CASE`-Kaskade, die den Auftrag in genau drei Töpfe sortiert:

1. **Sicher trennbar** – die Zeichenkette endet auf Ziffern, optional gefolgt von
   einem Buchstaben oder Zusatz (`Musterweg 12`, `Musterweg 12a`,
   `Musterweg 12-14`). Trennung an der letzten Position, ab der nur noch
   Ziffern/Trennzeichen folgen.
2. **Sicher nicht trennbar** – keine Ziffer enthalten, oder die Ziffern stehen
   vorn (`12 Rue de la Paix`, in AT/NL/CH übliche Formen). → **Fehlerstatus,
   nicht raten.** Diese Aufträge erscheinen im Cockpit-Reiter „Fehler" mit dem
   Grund `adresse_nicht_trennbar` und werden von Hand geklärt.
3. **Zweifelhaft** – alles Übrige. Ebenfalls Fehlerstatus.

Das entspricht der Vorgabe „nicht trennbare Fälle in den Fehlerstatus, nicht
raten". Der Preis: Bei Kunden mit vielen Auslandsadressen landet anfangs ein
spürbarer Anteil in Topf 2/3. Das ist beabsichtigt und im Cockpit sichtbar –
eine falsch geratene Hausnummer ist teurer als eine Zeile Handarbeit.

*Zu prüfen (T-SQL-Grenzen):* `PATINDEX` mit `%[0-9]%` und `REVERSE` reichen für
Topf 1 und 2. Für Topf 3 ist die Regel bewusst konservativ.

### `payload_hash`

Über die Felder gebildet, die Shipman tatsächlich bekommt (Adresse, Positionen,
Lieferdatum) – **nicht** über den ganzen Auftrag, sonst schlägt jede
JTL-interne Änderung an. In T-SQL über `HASHBYTES('SHA2_256', …)` auf der
verketteten Zeichenkette.

**Was passiert bei Änderung nach der Übermittlung?** Die API kennt kein Update,
nur Storno plus Neuanlage. Drei Möglichkeiten:

| Verhalten | Bewertung |
|---|---|
| **Automatisch stornieren und neu anlegen** | Gefährlich: Ist die Sendung bereits beim Carrier, entsteht ein zweiter Versand. Ohne Antwort auf F10 nicht verantwortbar. |
| **Melden, nicht handeln** | Warnung im Cockpit „Auftrag hat sich nach Übermittlung geändert", Entscheidung beim Menschen. |
| **Nur bis Status `uebermittelt` automatisch, danach melden** | Kompromiss, setzt aber voraus, dass `uebermittelt` zuverlässig „noch nicht angefasst" bedeutet – das ist nicht zugesichert. |

*Empfehlung: melden, nicht handeln.* Begründung: Der Schaden eines
Doppelversands ist deutlich größer als der einer manuellen Nachbearbeitung, und
die API gibt uns kein Mittel, den Bearbeitungsstand vor dem Storno zu prüfen.
Nach Beantwortung von F10 kann das neu bewertet werden.

---

## 7. Umsetzungsschritte

Jede Phase ist für sich testbar und endet mit einem überprüfbaren Ergebnis.

### Phase 0 – Klärung (keine Implementierung)
1. Testplan §4 durchführen (T1–T8).
2. F1–F5 und F11 beantworten lassen, soweit die Tests sie nicht klären.
3. Entscheidung §2.4 (Auth-Kette: Option C oder D) treffen.
4. Entscheidung §2.2 B3 bestätigen (Journal in eigener DB).
5. Diesen Plan mit den Ergebnissen fortschreiben.

**Abbruchkriterium:** Bleibt F1 (Herkunft der Order-ID) offen, wird **nur**
Phase 1 gebaut – eine Einbahnstraße ohne Rückkanal. Der Rückkanal darf nicht
auf einer geratenen ID aufsetzen.

### Phase 1 – Auftragsübergabe, ohne Rückkanal
- Journal-Tabelle anlegen, Verbindung einrichten
- M1 (Versandkandidaten inkl. Adresstrennung), M2 (Journal fortschreiben)
- REST-Quellen `shipman_auth`, `shipman_order_anlegen`
- Pipeline P1
- **Test:** Ein Auftrag aus einem Testmandanten geht durch, das Journal steht
  auf `uebermittelt`, ein zweiter Lauf übermittelt ihn **nicht** erneut.
  Ein Auftrag mit nicht trennbarer Adresse landet auf `fehlgeschlagen` mit
  lesbarem Grund.

### Phase 2 – Cockpit und Warnungen
- M9–M13, Formular mit sechs Reitern, vier Warnregeln, Schwellwerte in
  `business_config`
- **Test:** Ein künstlich fehlgeschlagener Auftrag erscheint im Reiter „Fehler",
  der Wiederanstoß-Button übermittelt ihn erneut, die Warnung schlägt an und
  verschwindet nach der Korrektur.

### Phase 3 – Rückkanal Tracking
- M3, M4, M5, Katalog-Dataset, REST-Quelle `shipman_tracking`, Pipeline P2
- **Test:** Ein realer versendeter Auftrag erreicht `getrackt` und später
  `zugestellt`, allein über die Booleans. Ein erfundener Code taucht im Reiter
  „Unbekannte Trackingcodes" auf und löst die Warnung aus.

### Phase 4 – Rückschreiben in die Wawi
- M8 (Versanddaten-Export im Format aus F11), Pipeline P4
- **Test:** Die erzeugte Datei wird von der JTL-Wawi angenommen, Tracking steht
  am Beleg, der Marktplatz erhält die Rückmeldung.
- *Vorbedingung:* F11 beantwortet.

### Phase 5 – Storno
- M7, REST-Quelle `shipman_storno`, Pipeline P3
- **Test:** Ein in JTL stornierter, bereits übermittelter Auftrag wird bei
  Shipman storniert, das Journal steht auf `storniert`.
- *Vorbedingung:* F10 beantwortet.

### Phase 6 – Ausbau (optional, je nach Klärung)
- Abliefernachweis (§2.5), sobald das Ablageziel geklärt ist
- Bestandsrückfluss (§2.3 Option 2), sobald F8 beantwortet ist
- Umbenennung auf `fulfillment_*` und Spalte `dienstleister`, sobald ein
  zweiter Dienstleister absehbar ist

### Parallel, aber getrennt vom Template (Plattformarbeit)
Diese drei Punkte sind **eigene Vorgänge**, keine Template-Aufgaben. Sie stehen
hier, weil die Analyse sie zutage gefördert hat:

| Vorgang | Grund |
|---|---|
| **B3 beheben** – Dataset-Append/Upsert liest Parquet statt `json.load` | Stiller Datenverlust; betrifft jedes Mapping, das heute `append`/`upsert` auf ein Dataset schreibt |
| **B2 beheben** – die fünf fehlenden Node-Arrays in Export und Import | Templates verlieren Python-, DQ-, Ausdrucks-, Parameter- und KI-Nodes ohne Fehlermeldung |
| **Mapping-REST-Node auf `rest_service` umstellen** | Zweite HTTP-Implementierung ohne Body, ohne Retry, **ohne SSRF-Schutz** |
| **`doku/template-format.md` ergänzen** | `alert_rules`, `reports`, die Action-Typen `run_alerts`/`export_mapping` und fünf Widget-Typen fehlen |
| **`whatwecan.md` und `Anleitung.md` korrigieren** | Eingehende REST-Schnittstelle und FTP als Mapping-Ziel sind dort falsch beschrieben (§0) |

---

## 8. Risiken und Annahmen

### Annahmen — jede ist eine Annahme, keine Feststellung

| # | Annahme | Wenn falsch |
|---|---|---|
| A1 | Die Order-ID ist `data.id_external` oder aus der Antwort ableitbar. | Rückkanal und Storno entfallen; nur Phase 1 bleibt. |
| A2 | Der JWT ist lange genug gültig, um pro Lauf einmal geholt zu werden. | Auth-Kette braucht Option D (§2.4), also eine Plattformänderung. |
| A3 | Shipman lehnt eine doppelte `id_external` ab oder behandelt sie idempotent. | Das Journal muss vor jedem Aufruf gegen den Ist-Zustand prüfen – ohne Listen-Endpunkt kaum möglich. Dann ist ein Abbruch mitten im Lauf gefährlich. |
| A4 | Der Kunde hat den JTL-Versanddaten-Import verfügbar. | Phase 4 wird neu bewertet (JTL-API-Lizenz oder Ameise). |
| A5 | Es existiert eine Lieferadress-Sicht in der JTL-DB, analog zu `vAuftragRechnungsadresse`. | Die Adresse muss über `dbo.tAdresse` mit dem richtigen `nTyp` gejoint werden – die Dublettenfallen dort sind bekannt und aufwendiger. |
| A6 | `cArtNr` bildet auf `items[].item` ab. | `{{artikel_kennung_feld}}` wird umgestellt; die Template-Struktur ändert sich nicht. |
| A7 | Weniger als 100 Aufträge je Lauf. | `for_each_max` erhöhen und Laufzeit messen; ggf. Aufteilung in mehrere Läufe. |
| A8 | Eine schreibbare Datenbank für das Journal steht zur Verfügung. | Zurück auf den Dataset-Weg, dann muss B3 vorher behoben werden. |

### Risiken

| Risiko | Auswirkung | Umgang |
|---|---|---|
| **Doppelter Versandauftrag** durch Wiederholungslauf nach Teilabbruch | echte Kosten, doppelte Sendung | Journal **vor** dem Aufruf auf `uebermittelt` setzen und bei Fehler zurücksetzen, statt danach zu schreiben. Setzt A3 voraus – bis F3 beantwortet ist, das größte Einzelrisiko. |
| **JSON-Zerstörung durch Sonderzeichen** in Namen/Adressen (`_mit_zeilenwerten` ist Textersetzung, §1.4) | Aufruf schlägt fehl oder überträgt Unsinn | Alle eingesetzten Felder in M1 bereits JSON-sicher aufbereiten (Anführungszeichen und Backslashes ersetzen). **Muss in Phase 1 explizit getestet werden** – ein Kunde namens `Meyer "Bau" GmbH` reicht. |
| **Variable Positionsanzahl** lässt sich per Textersetzung nicht als `items[]`-Array bauen (§1.4) | Aufträge mit mehr als einer Position nicht übertragbar | **Ungelöst.** Denkbar: `items` in M1 als fertigen JSON-Teilstring erzeugen (T-SQL `STRING_AGG`/`FOR JSON`) und als **eine** Spalte einsetzen. Muss in Phase 1 als Erstes geprüft werden – davon hängt ab, ob der Pipeline-Weg überhaupt trägt. |
| **`for_each`-Deckel 100** und sequenzielle Aufrufe | lange Laufzeiten, unvollständige Läufe | Zeitplan enger takten statt Deckel erhöhen; Laufzeit in Phase 1 messen. |
| **Kein Bestandsabgleich** | Überverkäufe | §2.3 – dokumentieren, später zweiter Kanal |
| **Unbekannte Fehlerobjekte** (F4) | `fehlgeschlagen` vs. „später erneut" nicht unterscheidbar | Bis F4 beantwortet ist: alles außer 2xx als `fehlgeschlagen` mit Rohtext in `letzter_fehler`, kein automatischer Wiederholungsversuch. Lieber eine Zeile Handarbeit als eine Schleife gegen die API. |
| **Formular wird beim Re-Install nicht aktualisiert** (§1.1) | Änderungen am Cockpit kommen nicht an, wirken „verloren" | In der Entwicklungsschleife das Formular vor dem Re-Install löschen; im Betrieb gezielt patchen. |
| **Testläufe erzeugen echte Versandaufträge** | Kosten, Aufwand beim Dienstleister | Ausschließlich im Testmandanten, `versand_praefix` setzen, T5 nur mit anschließendem Storno. Vorab mit Shipman klären, ob es einen Testmandanten gibt. |

---

## 9. Was als Nächstes zu entscheiden ist

Bevor implementiert wird, brauche ich von Dir drei Entscheidungen:

1. **Journal in eigener Datenbank** (§2.2 B3, Empfehlung) – oder soll B3 vorher
   in der Plattform behoben werden?
2. **Adresstrennung in T-SQL** (§2.2 B2, Empfehlung) – oder sollen die fünf
   fehlenden Node-Arrays im Installer nachgerüstet werden, damit der Python-Node
   auslieferbar wird?
3. **Testplan §4 zuerst** – ich halte ihn für zwingend: F1 und das
   `items[]`-Risiko entscheiden, ob der geplante Weg überhaupt trägt.

Sind diese drei geklärt, kann Phase 1 entworfen und gebaut werden.

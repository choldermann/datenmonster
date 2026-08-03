# Datenmonster – Template-Format (Referenz für Template-Generierung)

> **Zweck dieses Dokuments:** Vollständige, in sich geschlossene Beschreibung des Datenmonster-Template-Formats (JSON). Es enthält alles, was nötig ist, um mit einer externen KI (z. B. ChatGPT) ein komplettes, installierbares Template inklusive Datasets, Mappings und **Formularen/Dashboards** zu erzeugen – ohne Zugriff auf den Quellcode.
>
> **So verwendest du es:** Gib dieses Dokument der KI als Kontext/Systemprompt mit und beschreibe dann, welches Template du brauchst (welche Auswertung, welche Datenquelle, welche Widgets). Die KI gibt **eine einzelne JSON-Datei** aus. Diese lädst du in Datenmonster unter *Templates → Hochladen* hoch und installierst sie in ein Projekt.

---

## 1. Was ist ein Template?

Ein Template ist **eine JSON-Datei**, die ein „Bündel" fertiger Datenmonster-Objekte beschreibt:

- **Datasets** – Datenquellen (SQL-Abfrage, REST-API oder statische Daten)
- **Mappings** – Transformations-/Auswertungslogik (SQL-Knoten, Feldzuordnungen → Ziel)
- **Pipelines** (optional) – automatisierte Abläufe mit Scheduler
- **Forms** – Formulare und **Dashboards** (Eingabefelder, Buttons/Aktionen, Widgets/Charts)

Beim **Installieren** legt Datenmonster aus diesen Definitionen echte Objekte im gewählten Projekt an. Platzhalter (`{{...}}`) werden dabei durch die vom Nutzer eingegebenen Werte ersetzt – insbesondere die **Datenbank-Verbindung** (Zugangsdaten sind aus Sicherheitsgründen **nie** im Template enthalten).

### Wichtigstes Muster: „SQL rechnet, Widget zeigt an"

Die JTL-Reporting-Templates funktionieren nach einem sehr einfachen, robusten Muster:

1. Pro Kennzahl/Diagramm gibt es **ein Mapping** mit **einem SQL-Knoten**, der die fertig aggregierten Zahlen liefert (GROUP BY im SQL).
2. Das Mapping-Ziel ist ein **Dataset** (`target_type: "dataset"`, `target_write_mode: "replace"`).
3. Im **Formular** gibt es pro Mapping eine **Action** vom Typ `run_mapping` und darauf verweisende **Widgets** (KPI, Balken, Linie, Kreis, Tabelle).
4. Der Nutzer öffnet das Formular und klickt die Auswerten-Buttons → Widgets laden Daten.

Wenn du nichts anderes brauchst, **halte dich exakt an dieses Muster** – es ist am zuverlässigsten. Die restlichen Node-Typen (agg, transform, lookup …) sind optional und nur für komplexere Fälle nötig.

---

## 2. Top-Level-Struktur

```json
{
  "template_id": "jtl_umsatz_nach_kunde",
  "template_name": "JTL – Umsatz nach Kunde",
  "description": "Kurzbeschreibung, erscheint im Template-Katalog.",
  "category": "jtl-reporting",
  "version": "1.0",
  "author": "Datenmonster",
  "hinweise": [ "Freitext-Hinweise für den Installierenden ..." ],
  "config_required": [ ... ],
  "datasets": [ ... ],
  "mappings": [ ... ],
  "pipelines": [],
  "forms": [ ... ]
}
```

| Feld | Pflicht | Bedeutung |
|------|---------|-----------|
| `template_id` | **ja** | Eindeutige technische ID, `snake_case`, nur `[a-z0-9_]`. Beim erneuten Upload mit gleicher ID wird das bestehende Template **überschrieben**. |
| `template_name` | ja | Anzeigename im Katalog. |
| `description` | empfohlen | Kurzbeschreibung. |
| `category` | empfohlen | Freitext-Kategorie, z. B. `"jtl-reporting"`. Default `"general"`. |
| `version` | empfohlen | z. B. `"1.0"`. |
| `author` | optional | z. B. `"Datenmonster"`. |
| `hinweise` | empfohlen | Array aus Strings. Wird dem Nutzer beim Installieren angezeigt. |
| `config_required` | siehe §3 | Vom Nutzer beim Install abgefragte Werte (v. a. DB-Verbindung, Zeiträume). |
| `datasets` | Array | Kann leer sein (`[]`), wenn Mappings ihre Daten über SQL-Knoten holen. |
| `mappings` | Array | Die Auswertungslogik. |
| `pipelines` | Array | Meist `[]`. |
| `forms` | Array | Formulare/Dashboards. |

> **Hinweis zu `pipelines`:** Kanonisch ist das **Array `pipelines`** – ein Template kann mehrere Pipelines enthalten. Für reine Reporting-Templates bleibt es einfach leer (`"pipelines": []`). Pipelines werden in §7 beschrieben. (Ein älteres Singular-Feld `pipeline` als Objekt wird vom Installer weiterhin akzeptiert, ist aber nur Fallback – neue Templates nutzen das Array.)

---

## 3. `config_required` – Nutzer-Eingaben & Platzhalter

Jeder Eintrag definiert einen Wert, den der Nutzer beim Installieren angibt. Überall im Template kann dieser Wert per **`{{key}}`** eingesetzt werden (in SQL, URLs, Namen, Optionen – rekursiv in Strings).

```json
"config_required": [
  {
    "key": "connection_jtl",
    "label": "JTL-Datenbankverbindung (MS SQL Server)",
    "type": "connection",
    "default": ""
  },
  {
    "key": "monate",
    "label": "Zeitraum rückwirkend in Monaten",
    "type": "text",
    "default": "24"
  }
]
```

| Feld | Bedeutung |
|------|-----------|
| `key` | Platzhalter-Name. Wird als `{{key}}` referenziert. |
| `label` | Anzeigetext im Install-Dialog. |
| `type` | `"connection"` (DB-Verbindungsauswahl) oder `"text"` (freie Texteingabe). |
| `default` | Vorbelegung. Bei `type: "text"` sinnvoll (z. B. `"24"`). Bei `connection` leer `""`. |

### 3.1 Datenbank-Verbindung (der wichtigste Platzhalter)

- Verwende **immer** einen `config_required`-Eintrag mit `"type": "connection"`, z. B. `key: "connection_jtl"`.
- Referenziere ihn in SQL-Knoten als `"connection_id": "{{connection_jtl}}"`.
- Beim Install löst Datenmonster `{{connection_jtl}}` in die echte (Integer-)Verbindungs-ID auf.
- **Zugangsdaten sind nie im Template.** Der Nutzer wählt eine vorhandene Verbindung aus.

### 3.2 Parameter-Platzhalter (Zeiträume, Grenzwerte …)

`type: "text"`-Einträge eignen sich für Zahlen/Zeiträume, die direkt in SQL eingesetzt werden, z. B. `DATEADD(MONTH, -{{monate}}, ...)`. Der eingesetzte Wert ist immer ein **String** – für SQL-Zahlen unproblematisch, solange du sie an numerischer Stelle einsetzt (`-{{monate}}` → `-24`).

> **Regel:** Jeder `{{platzhalter}}`, den du irgendwo im Template verwendest, **muss** einen passenden `config_required`-Eintrag haben (Ausnahme: die intern aufgelösten `{{connection_X}}` beim Export – die generierst du hier selbst als `connection`-Eintrag).

---

## 4. `datasets` – Datenquellen

Für das Standard-Reporting-Muster ist `datasets` meist **leer** (`[]`), weil die SQL-Knoten in den Mappings direkt gegen die JTL-DB laufen. Datasets brauchst du für REST-APIs, statische Daten oder wiederverwendete SQL-Quellen.

Jedes Dataset hat eine **Template-interne String-`id`** (z. B. `"ds_1"`), über die Mappings/Pipelines es referenzieren.

### 4.1 `file_type: "db_query"` – SQL-Abfrage

```json
{
  "id": "ds_kunden",
  "name": "Kundenliste",
  "file_type": "db_query",
  "columns": ["kKunde", "cFirma"],
  "sql": "SELECT kKunde, cFirma FROM dbo.tKunde",
  "source_connection_id": "{{connection_jtl}}"
}
```

### 4.2 `file_type: "rest_api"` – REST-Quelle

```json
{
  "id": "ds_preise",
  "name": "Spritpreise",
  "file_type": "rest_api",
  "columns": ["station", "preis"],
  "rest_config": {
    "url": "https://api.example.com/prices?plz={{plz}}",
    "method": "GET",
    "headers": {},
    "query_params": {},
    "body_type": "none",
    "auth": { "type": "none" },
    "data_path": "stations",
    "pagination": {}
  }
}
```

`rest_config`-Felder: `url`, `method` (GET/POST/…), `headers` (Objekt), `query_params` (Objekt), `body_type` (`"none"`/`"json"`/…), `body_content`, `auth` (`{ "type": "none" | "bearer" | ... }`), `data_path` (Pfad zum Array in der Antwort), `pagination` (Objekt).

### 4.3 `file_type: "static"` – Statische Daten

```json
{
  "id": "ds_mapping_tabelle",
  "name": "Länder-Codes",
  "file_type": "static",
  "columns": ["code", "land"],
  "initial_data": [
    { "code": "DE", "land": "Deutschland" },
    { "code": "AT", "land": "Österreich" }
  ]
}
```

---

## 5. `mappings` – Auswertungs-/Transformationslogik

Ein Mapping besteht aus **Quell-/Verarbeitungsknoten** und **Zielen (`targets`)**. Für Reporting reicht: **ein SQL-Knoten → ein Dataset-Ziel**.

### 5.1 Grundgerüst eines Reporting-Mappings

```json
{
  "id": "mapping_kpi",
  "name": "Artikel-Kennzahlen",
  "canvas_nodes": [],
  "joins": [],
  "sql_nodes": [
    {
      "id": "sql1",
      "x": 120, "y": 40, "width": 350, "height": 244,
      "connection_id": "{{connection_jtl}}",
      "sql": "SELECT CAST(SUM(REPO.fAnzahl * REPO.fVkNetto) AS DECIMAL(18,2)) AS Gesamtumsatz\nFROM Rechnung.vRechnung RE\nJOIN Rechnung.tRechnungPosition REPO ON RE.kRechnung = REPO.kRechnung\nWHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date))",
      "mode": "transform",
      "output_field": "sql_1",
      "output_fields": ["Gesamtumsatz"]
    }
  ],
  "agg_nodes": [],
  "transform_nodes": [],
  "constant_nodes": [],
  "rest_nodes": [],
  "lookup_nodes": [],
  "calc_nodes": [],
  "switch_nodes": [],
  "sort_nodes": [],
  "targets": [
    {
      "id": "t1",
      "name": "Artikel-Kennzahlen",
      "target_type": "dataset",
      "target_connection_id": null,
      "target_table": "",
      "target_write_mode": "replace",
      "target_options": {},
      "fields": [
        {
          "source_field": "Gesamtumsatz",
          "target_field": "Gesamtumsatz",
          "target_type": "float",
          "source_dataset_id": "__sql__sql1",
          "transformer": { "type": "direct", "source_field": "Gesamtumsatz" }
        }
      ]
    }
  ]
}
```

**Wichtige Konventionen (unbedingt einhalten):**

- Mapping-`id`: Template-interne String-ID (z. B. `"mapping_kpi"`). Formulare referenzieren sie in Actions.
- **Alle** Node-Arrays angeben (auch leere): `canvas_nodes`, `joins`, `sql_nodes`, `agg_nodes`, `transform_nodes`, `constant_nodes`, `rest_nodes`, `lookup_nodes`, `calc_nodes`, `switch_nodes`, `sort_nodes`. Nicht benötigte einfach als `[]`.
- Der SQL-Knoten braucht `"mode": "transform"` (sonst wird das Ergebnis nicht als Datenquelle behandelt).
- **`source_dataset_id` im Ziel-Feld muss `"__sql__" + <sql-node-id>` sein.** Bei `"id": "sql1"` also `"__sql__sql1"`. Das ist die kritischste Verknüpfung – hier passieren die häufigsten Fehler.
- Jede **Spalte, die dein SQL zurückgibt** und die du im Dashboard nutzen willst, braucht einen Eintrag in `output_fields` **und** ein Feld in `targets[].fields`.

### 5.2 SQL-Knoten (`sql_nodes`)

| Feld | Bedeutung |
|------|-----------|
| `id` | Knoten-ID, z. B. `"sql1"`. Bestimmt `source_dataset_id` = `"__sql__sql1"`. |
| `connection_id` | `"{{connection_jtl}}"` – die Datenbank-Verbindung. |
| `sql` | Das SQL-Statement. `\n` für Zeilenumbrüche. Platzhalter `{{...}}` erlaubt. |
| `mode` | Immer `"transform"` für Reporting. |
| `output_field` | Interner Name, konventionell `"sql_1"`. |
| `output_fields` | Array der Spaltennamen, die das SELECT liefert. |
| `x`, `y`, `width`, `height` | Canvas-Position (Optik). Übliche Werte: `x:120, y:40, width:350, height:244`. |

> **SQL-Dialekt:** Die JTL-Wawi läuft auf **Microsoft SQL Server (T-SQL)**. Nutze `TOP n` (nicht `LIMIT`), `DATEADD`/`DATEDIFF`/`GETDATE()`, `CAST(... AS DECIMAL(18,2))`, `ISNULL(...)`, `CONVERT(char(7), datum, 120)` für Jahr-Monat, Fensterfunktionen (`SUM() OVER (...)`) für ABC-Analysen. Vergib den Ausgabespalten sprechende Aliase (`AS Umsatz`) – diese Aliase sind die Spaltennamen für Widgets.

### 5.3 Ziele (`targets`)

Für Reporting **immer**:

```json
{
  "id": "t1",
  "name": "<Zielname>",
  "target_type": "dataset",
  "target_connection_id": null,
  "target_table": "",
  "target_write_mode": "replace",
  "target_options": {},
  "fields": [ /* eine Feldzuordnung pro Spalte */ ]
}
```

Feldzuordnung (`fields[]`):

```json
{
  "source_field": "Umsatz",
  "target_field": "Umsatz",
  "target_type": "float",
  "source_dataset_id": "__sql__sql1",
  "transformer": { "type": "direct", "source_field": "Umsatz" }
}
```

- `source_field` = Spaltenname/Alias aus dem SQL.
- `target_field` = Name im Ziel-Dataset (meist identisch).
- `target_type` = `"string"`, `"integer"`, `"float"` (Kennzahlen `float`, Texte/Datumsstrings `string`).
- `transformer` = `{ "type": "direct", "source_field": "<source_field>" }` (unverändert übernehmen).

**Andere Ziel-Typen** (nur wenn ausdrücklich gewünscht – Reporting braucht sie nicht):

| `target_type` | Zweck | Zusätzlich nötig |
|---------------|-------|------------------|
| `"dataset"` | In Datenmonster-Dataset schreiben (Standard fürs Reporting). | – |
| `"db"` | In DB-Tabelle schreiben. **Achtung: Schreibzugriff auf Produktiv-WaWi!** | `target_connection_id`, `target_table`, `target_write_mode` = `insert`/`truncate_insert`/`update`/`upsert`/`delete`; für update/upsert/delete `target_options.key_columns`. |
| `"csv"`, `"xlsx"`, `"json"`, `"xml"` | Dateiexport. | ggf. Format-Optionen in `target_options`. |

> Für Dataset-Ziele steuert `target_write_mode` bzw. `target_options.dataset_write_mode` das Verhalten: `"replace"` (überschreiben – Standard fürs Reporting), `"append"`, `"upsert"`.

### 5.4 Optionale Knoten (nur für komplexere Mappings)

Diese sind für reines Reporting **nicht nötig** (SQL erledigt alles). Kurzüberblick, falls doch gebraucht:

- `canvas_nodes` – repräsentieren Datasets als Quelle (`{ "id": "<ds-id>", "dataset_id": "<ds-id>", "dataset_columns": [...], "x": 40, "y": 80 }`). Nur bei Dataset-basierten Mappings statt SQL.
- `joins` – Verknüpfung mehrerer Datasets.
- `agg_nodes` – Aggregation (GROUP BY) außerhalb von SQL.
- `transform_nodes` – Feldtransformationen.
- `constant_nodes` – Konstanten (`const_type`: `now`/`today`/`date`/`datetime`/`uuid`/`year`).
- `rest_nodes` – REST-Anreicherung pro Zeile.
- `lookup_nodes` / `switch_nodes` – Nachschlagen/Verzweigen (referenzieren Dataset-IDs).
- `calc_nodes` – Berechnete Felder.
- `sort_nodes` – Sortierung.

Wenn du sie nicht brauchst: als leeres Array `[]` mitgeben.

---

## 6. `forms` – Formulare & Dashboards

Ein Formular kann **Eingabeformular**, **Dashboard** oder beides sein. Es besteht aus einem `schema` mit vier Teilen:

```json
{
  "name": "Umsatz nach Artikel",
  "schema": {
    "fields":  [ /* Eingabefelder + Layout (optional) */ ],
    "layout":  [ /* meist leer */ ],
    "actions": [ /* führen Mappings/Pipelines aus */ ],
    "widgets": [ /* zeigen Ergebnisse an */ ]
  },
  "portal_config": {}
}
```

Für ein **Dashboard** brauchst du nur `actions` + `widgets` (Felder/Layout leer). Für ein **Eingabeformular** nutzt du `fields` (+ optional einen `button` mit Action).

### 6.1 `actions` – Datenquellen der Widgets

Eine Action führt beim Klick ein Mapping (oder eine Pipeline) aus; ihr Ergebnis speist die verknüpften Widgets.

```json
{
  "id": "act_kpi",
  "type": "run_mapping",
  "mapping_id": "mapping_kpi",
  "pipeline_id": null,
  "label": "Kennzahlen"
}
```

| Feld | Bedeutung |
|------|-----------|
| `id` | Action-ID (Widgets referenzieren sie via `action_id`). |
| `type` | `"run_mapping"` oder `"run_pipeline"`. |
| `mapping_id` | **Die Template-interne Mapping-`id`** (z. B. `"mapping_kpi"`). Beim Install automatisch auf die echte ID umgeschrieben. |
| `pipeline_id` | Bei `run_mapping` `null`; bei `run_pipeline` die Pipeline-ID. |
| `label` | Button-Beschriftung. |

> **Kritisch:** `mapping_id` in der Action muss **exakt** der `id` eines Mappings in `mappings[]` entsprechen – sonst findet der Installer keine Zuordnung.

### 6.2 `widgets` – Anzeige

Jedes Widget hat `id`, `type`, `label`, `action_id` (verweist auf eine Action) und `config`. `config.width` ist die Breite im **12-Spalten-Raster** (1–12).

**Widget-Typen:** `kpi`, `bar`, `line`, `pie`, `table`, `eingangsrechnung`.

#### KPI-Kachel (`kpi`)
```json
{
  "id": "w_kpi_umsatz", "type": "kpi", "label": "Gesamtumsatz netto",
  "action_id": "act_kpi",
  "config": {
    "width": 3,
    "column": "Gesamtumsatz",
    "aggregation": "first",
    "prefix": "€ ", "suffix": "", "decimals": 2
  }
}
```
- `column`: anzuzeigende Spalte. `aggregation`: `first` | `sum` | `avg` | `count` | `max` | `min`. `prefix`/`suffix`/`decimals` formatieren die Zahl. (Für einen einzelnen SQL-Aggregatwert `"first"` verwenden; für „Anzahl Zeilen" `"count"` auf einer beliebigen Spalte.)

#### Balkendiagramm (`bar`)
```json
{
  "id": "w_bar", "type": "bar", "label": "Top 15 Artikel nach Umsatz",
  "action_id": "act_top",
  "config": { "width": 8, "x_column": "Artikelname", "y_columns": ["Umsatz"], "stacked": false }
}
```
- `x_column`: Kategorie/Zeit-Achse. `y_columns`: Array der Wert-Spalten. `stacked`: Balken stapeln.

#### Liniendiagramm (`line`)
```json
{
  "id": "w_line", "type": "line", "label": "Umsatzentwicklung",
  "action_id": "act_umsatz_monat",
  "config": { "width": 12, "x_column": "Monat", "y_columns": ["Umsatz"], "curved": true }
}
```
- Wie `bar`, aber `curved` statt `stacked` (geglättete Linie).

#### Kreisdiagramm (`pie`)
```json
{
  "id": "w_pie", "type": "pie", "label": "Umsatzanteil",
  "action_id": "act_top",
  "config": { "width": 4, "label_column": "Artikelname", "value_column": "Umsatz", "donut": true }
}
```
- `label_column`: Kategorie. `value_column`: Wert. `donut`: als Donut anzeigen.

#### Tabelle (`table`)
```json
{
  "id": "w_tabelle", "type": "table", "label": "Positionsdetails",
  "action_id": "act_tabelle",
  "config": { "width": 12 }
}
```
- Zeigt alle Spalten des Ergebnisses. Nur `width` nötig.

#### Eingangsrechnungs-Freigabe (`eingangsrechnung`)
Spezial-Widget für den DATEV/JTL-Eingangsrechnungs-Workflow. `config.connection_id` = Ziel-WaWi-Verbindung. Nur verwenden, wenn ausdrücklich gefordert.

> **Balken-/Linien-/Kreis-Widgets** unterstützen optional `config.drilldown` (Klick auf ein Segment lädt Detaildaten). Für die Erstgenerierung weglassen.

### 6.3 `fields` – Eingabefelder & Layout (optional)

Nur für echte Eingabeformulare nötig. Jedes Feld:

```json
{
  "id": "f_name", "type": "text", "row": 0, "colSpan": 6,
  "label": "Name", "name": "name", "required": false,
  "placeholder": "", "default": "", "options": [], "content": ""
}
```

**Feldtypen:**

| Gruppe | `type` | Hinweise |
|--------|--------|----------|
| Eingabe | `text`, `textarea`, `number`, `date`, `time`, `file` | `name` = technischer Feldname (Pflicht bei Eingabefeldern). `placeholder` bei text/textarea/number. |
| Auswahl | `checkbox`, `switch`, `dropdown`, `multiselect`, `radio` | `dropdown`/`multiselect`/`radio` brauchen `options: [{ "value": "...", "label": "..." }]`. |
| Aktion | `button` | `action_id` verweist auf eine Action; kein `name`. |
| Layout | `heading`, `label`, `divider`, `container` | `heading`/`label` nutzen `content` als Text. Kein `name`/`required`. |

- `row`: Zeilenindex; `colSpan`: Breite im 12er-Raster.
- `required: true` markiert Pflichtfelder (nur Eingabefelder).
- Ein **Button** löst eine Action aus – so kombinierst du Eingaben mit Auswertung (die Eingabewerte können als SQL-Parameter genutzt werden, sofern das Mapping darauf ausgelegt ist).

### 6.4 `portal_config`

Leer lassen (`{}`). Portal-Veröffentlichung (`slug`, `published`) wird beim Install **bewusst nicht** übernommen – der Nutzer veröffentlicht manuell.

---

## 7. `pipelines` – Automatisierung (optional)

Nur für automatisierte Abläufe (z. B. nächtlicher Export). Für Reporting-Dashboards **nicht** nötig. Der kanonische Schlüssel ist das **Array `pipelines`** – jeder Eintrag ist eine Pipeline (Objekt). Ein Template darf mehrere Pipelines enthalten; der Installer legt alle an.

```json
"pipelines": [
  {
    "name": "Nächtlicher Export",
    "nodes": [
      { "id": "n1", "type": "mapping", "config": { "mapping_id": "{{mapping_kpi}}" }, "x": 200, "y": 100 }
    ],
    "connections": [
      { "from_node": "n1", "from_port": "out", "to_node": "n2", "to_port": "in" }
    ],
    "scheduler": { "cron": "0 3 * * *", "description": "täglich 3 Uhr" }
  }
]
```

- Mapping-Knoten referenzieren Mappings als `"mapping_id": "{{mapping_<id>}}"` (Platzhalter mit doppelten geschweiften Klammern; wird beim Install aufgelöst).
- Ist `scheduler.cron` gesetzt und kein `trigger`-Knoten vorhanden, fügt der Installer automatisch einen Trigger-Knoten davor ein.

> **Abwärtskompatibilität:** Ältere Templates verwenden statt des Arrays ein Singular-Objekt `"pipeline": { ... }`. Der Installer akzeptiert das weiterhin (Fallback, nur genutzt wenn `pipelines` fehlt/leer). **Neue Templates verwenden das Array `pipelines`.**

---

## 8. Verknüpfungs-Übersicht (die kritischen IDs)

Damit ein Template funktioniert, müssen diese Referenzen zusammenpassen:

```
config_required[].key  ──{{key}}──►  überall (SQL, connection_id, URLs, ...)

sql_nodes[].id "sql1"  ──►  targets[].fields[].source_dataset_id = "__sql__sql1"
sql_nodes[].output_fields  ⊇  alle in targets[].fields verwendeten source_field
                                und alle in Widgets referenzierten Spalten

mappings[].id "mapping_x"  ──►  forms[].schema.actions[].mapping_id = "mapping_x"
actions[].id "act_x"       ──►  forms[].schema.widgets[].action_id = "act_x"
widgets[].config.column / x_column / y_columns / label_column / value_column
                            ──►  müssen SQL-Alias-Namen (output_fields) sein
```

---

## 9. Checkliste vor der Ausgabe

Die generierende KI soll **eine einzige, valide JSON-Datei** ausgeben und Folgendes sicherstellen:

- [ ] Gültiges JSON (keine Kommentare, keine trailing commas, korrekt escapte `\n` in SQL-Strings).
- [ ] `template_id` in `snake_case`, eindeutig.
- [ ] Für jede DB-Verbindung ein `config_required`-Eintrag `type: "connection"`; in SQL-Knoten als `connection_id: "{{...}}"` referenziert.
- [ ] Jeder verwendete `{{platzhalter}}` hat einen `config_required`-Eintrag (außer den Connection-Platzhaltern, die du selbst als `connection`-Eintrag anlegst).
- [ ] Jedes Mapping: alle Node-Arrays vorhanden (leere als `[]`), SQL-Knoten mit `mode: "transform"`.
- [ ] `source_dataset_id` = `"__sql__" + sql-node-id` in **jedem** Ziel-Feld.
- [ ] Jede im Widget genutzte Spalte kommt als Alias im SQL vor **und** steht in `output_fields` **und** in `targets[].fields`.
- [ ] Jede Action `mapping_id` = existierende Mapping-`id`; jedes Widget `action_id` = existierende Action-`id`.
- [ ] T-SQL-Dialekt (MS SQL Server / JTL-Wawi): `TOP n`, `GETDATE()`, `DATEADD`, `CAST(... AS DECIMAL(18,2))`.
- [ ] Widget-`config.width` je Zeile sinnvoll aufs 12er-Raster verteilt.
- [ ] `pipelines: []` und `portal_config: {}` gesetzt, falls nicht gebraucht.

---

## 10. Vollständiges Minimalbeispiel (Dashboard mit KPI + Balken + Tabelle)

```json
{
  "template_id": "jtl_umsatz_nach_kunde_demo",
  "template_name": "JTL – Umsatz nach Kunde (Demo)",
  "description": "Dashboard: Gesamtumsatz und Top-Kunden aus der JTL-Wawi.",
  "category": "jtl-reporting",
  "version": "1.0",
  "author": "Datenmonster",
  "hinweise": [
    "Beim Installieren die JTL-Datenbankverbindung (MS SQL) auswählen – Zugangsdaten werden nicht mitgeliefert.",
    "Formular öffnen und die Auswerten-Buttons klicken, damit die Widgets Daten laden."
  ],
  "config_required": [
    { "key": "connection_jtl", "label": "JTL-Datenbankverbindung (MS SQL Server)", "type": "connection", "default": "" },
    { "key": "monate", "label": "Zeitraum rückwirkend in Monaten", "type": "text", "default": "12" }
  ],
  "datasets": [],
  "mappings": [
    {
      "id": "mapping_kpi",
      "name": "Umsatz-Kennzahl",
      "canvas_nodes": [], "joins": [],
      "sql_nodes": [
        {
          "id": "sql1", "x": 120, "y": 40, "width": 350, "height": 244,
          "connection_id": "{{connection_jtl}}",
          "sql": "SELECT CAST(SUM(REPO.fAnzahl * REPO.fVkNetto) AS DECIMAL(18,2)) AS Umsatz\nFROM Rechnung.vRechnung RE\nJOIN Rechnung.tRechnungPosition REPO ON RE.kRechnung = REPO.kRechnung\nWHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date))",
          "mode": "transform", "output_field": "sql_1", "output_fields": ["Umsatz"]
        }
      ],
      "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
      "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
      "targets": [
        {
          "id": "t1", "name": "Umsatz-Kennzahl", "target_type": "dataset",
          "target_connection_id": null, "target_table": "", "target_write_mode": "replace", "target_options": {},
          "fields": [
            { "source_field": "Umsatz", "target_field": "Umsatz", "target_type": "float",
              "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Umsatz" } }
          ]
        }
      ]
    },
    {
      "id": "mapping_top_kunden",
      "name": "Top 15 Kunden",
      "canvas_nodes": [], "joins": [],
      "sql_nodes": [
        {
          "id": "sql1", "x": 120, "y": 40, "width": 350, "height": 244,
          "connection_id": "{{connection_jtl}}",
          "sql": "SELECT TOP 15\n    ISNULL(RE.cFirma, RE.cName) AS Kunde,\n    CAST(SUM(REPO.fAnzahl * REPO.fVkNetto) AS DECIMAL(18,2)) AS Umsatz\nFROM Rechnung.vRechnung RE\nJOIN Rechnung.tRechnungPosition REPO ON RE.kRechnung = REPO.kRechnung\nWHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date))\nGROUP BY ISNULL(RE.cFirma, RE.cName)\nORDER BY Umsatz DESC",
          "mode": "transform", "output_field": "sql_1", "output_fields": ["Kunde", "Umsatz"]
        }
      ],
      "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
      "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
      "targets": [
        {
          "id": "t1", "name": "Top 15 Kunden", "target_type": "dataset",
          "target_connection_id": null, "target_table": "", "target_write_mode": "replace", "target_options": {},
          "fields": [
            { "source_field": "Kunde", "target_field": "Kunde", "target_type": "string",
              "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Kunde" } },
            { "source_field": "Umsatz", "target_field": "Umsatz", "target_type": "float",
              "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Umsatz" } }
          ]
        }
      ]
    }
  ],
  "pipelines": [],
  "forms": [
    {
      "name": "Umsatz nach Kunde",
      "schema": {
        "fields": [], "layout": [],
        "actions": [
          { "id": "act_kpi", "type": "run_mapping", "mapping_id": "mapping_kpi", "pipeline_id": null, "label": "Kennzahl" },
          { "id": "act_top", "type": "run_mapping", "mapping_id": "mapping_top_kunden", "pipeline_id": null, "label": "Top-Kunden" }
        ],
        "widgets": [
          { "id": "w_kpi", "type": "kpi", "label": "Gesamtumsatz netto", "action_id": "act_kpi",
            "config": { "width": 4, "column": "Umsatz", "aggregation": "first", "prefix": "€ ", "decimals": 2 } },
          { "id": "w_bar", "type": "bar", "label": "Top 15 Kunden nach Umsatz", "action_id": "act_top",
            "config": { "width": 8, "x_column": "Kunde", "y_columns": ["Umsatz"], "stacked": false } },
          { "id": "w_table", "type": "table", "label": "Kundenliste", "action_id": "act_top",
            "config": { "width": 12 } }
        ]
      },
      "portal_config": {}
    }
  ]
}
```

---

## 11. Hinweise zur JTL-Wawi (Datenkontext für sinnvolle SQL-Abfragen)

Häufig genutzte Tabellen/Views (MS SQL Server, Schema meist `dbo` bzw. `Rechnung`):

- **Umsatz:** `Rechnung.vRechnung` (Kopf: `kRechnung`, `dErstellt`, `cFirma`, `cName`) join `Rechnung.tRechnungPosition` (`kRechnung`, `cArtNr`, `cName`, `fAnzahl`, `fVkNetto`).
- **Einkauf:** `dbo.tEingangsrechnung` (`kEingangsrechnung`, `dErstellt`, `kLieferant`) join `dbo.tEingangsrechnungPos` (`kEingangsrechnung`, `kArtikel`, `fMenge`, `fEKNetto`); Lieferant über `dbo.tLieferant` (`kLieferant`, `cFirma`).
- **Artikel/Bestand:** `dbo.tArtikel` (`kArtikel`, `cArtNr`, `fEKNetto`), `dbo.tlagerbestand` (`kArtikel`, `fLagerbestand`), Bezeichnung über `dbo.tArtikelBeschreibung` (`kArtikel`, `cName`, `kSprache`, `kPlattform` – i. d. R. `= 1`).

> Diese Schema-Stellen können je nach JTL-Version abweichen. In `hinweise` immer erwähnen, dass der Nutzer bei abweichender Version die geflaggten Stellen prüfen soll.
```

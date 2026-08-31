# Datenmonster – Template-Format (Referenz für Template-Generierung)

> **Zweck dieses Dokuments:** Vollständige, in sich geschlossene Beschreibung des Datenmonster-Template-Formats (JSON). Es enthält alles, was nötig ist, um mit einer externen KI (z. B. ChatGPT) ein komplettes, installierbares Template inklusive Datasets, Mappings und **Formularen/Dashboards** zu erzeugen – ohne Zugriff auf den Quellcode.
>
> **So verwendest du es:** Gib dieses Dokument der KI als Kontext/Systemprompt mit und beschreibe dann, welches Template du brauchst (welche Auswertung, welche Datenquelle, welche Widgets). Die KI gibt **eine einzelne JSON-Datei** aus. Diese lädst du in Datenmonster unter *Templates → Hochladen* hoch und installierst sie in ein Projekt.

> **Aktuelle Format-Version:** `1.0` – jedes generierte Template setzt `"format_version": "1.0"` (siehe §2).
>
> *Stand dieser Referenz: 27.08.2026. Neu gegenüber der vorigen Fassung: die Knotenarten
> `python_nodes`, `expr_nodes`, `quality_nodes`, `param_nodes` und `ai_nodes` werden jetzt mit
> übertragen (§5.4), Warnregeln (`alert_rules`, §7a) und Berichte (`reports`) sind dokumentiert,
> ebenso die vollständigen Aktions- und Widget-Typen (§6.1/§6.2) und der REST-Knoten mit
> Anfragerumpf (§5.5).*

---

## 0. Regeln für KI-Generatoren (verbindlich)

Diese Regeln gelten für **jedes** Modell (ChatGPT, Claude, Gemini, Qwen …), das aus diesem Dokument ein Template erzeugt. Sie sorgen dafür, dass die Ausgabe modellübergreifend konsistent und ohne Nacharbeit installierbar ist. **Bei Konflikt haben diese Regeln Vorrang vor allem anderen im Dokument.**

**Ausgabeformat**
1. **Gib ausschließlich die JSON-Datei aus** – kein einleitender Text, keine Erklärung, kein Markdown-Codefence, keine abschließende Bemerkung. Die Antwort beginnt mit `{` und endet mit `}`.
2. **Niemals Kommentare im JSON** – JSON kennt keine Kommentare (`//` oder `/* */` sind ungültig). Erklärungen gehören, wenn überhaupt, in das `hinweise`-Array.
3. **Gültiges, striktes JSON** – doppelte Anführungszeichen, keine trailing commas, keine unquoted Keys, keine Python-/JS-Literale (`None`/`True`/`undefined` → `null`/`true`).
4. **Immer UTF-8**, ohne BOM. Umlaute/Sonderzeichen direkt als UTF-8 ausgeben (kein unnötiges `\uXXXX`-Escaping). In SQL-Strings Zeilenumbrüche als `\n` schreiben.

**Feld- und Struktur-Disziplin**
5. **Keine zusätzlichen Eigenschaften erfinden** – nur die in diesem Dokument beschriebenen Schlüssel verwenden. Keine ausgedachten Felder, Node-Typen, Widget-Typen oder Action-Typen.
6. **Alle definierten Arrays immer vorhanden**, auch wenn leer (`[]`). Das gilt insbesondere für **alle** Mapping-Node-Arrays (`canvas_nodes`, `joins`, `sql_nodes`, `agg_nodes`, `transform_nodes`, `constant_nodes`, `rest_nodes`, `lookup_nodes`, `calc_nodes`, `switch_nodes`, `sort_nodes`) sowie `datasets`, `mappings`, `pipelines`, `forms`.
7. **`format_version` immer setzen** – auf die oben genannte aktuelle Format-Version.
8. **IDs ausschließlich in `snake_case`** (`[a-z0-9_]`): `template_id`, Mapping-`id`, Dataset-`id`, Action-`id`, Widget-`id`, `config_required[].key`.

**Inhaltliche Vorgaben**
9. **SQL ausschließlich als T-SQL** (Microsoft SQL Server / JTL-Wawi): `TOP n` statt `LIMIT`, `GETDATE()`, `DATEADD`/`DATEDIFF`, `CAST(... AS DECIMAL(18,2))`, `ISNULL(...)`. Jede Ausgabespalte bekommt einen Alias (`AS Umsatz`).
10. **Referenzielle Integrität** (die häufigste Fehlerquelle):
    - Jede `action_id` eines Widgets muss auf eine **existierende Action** zeigen.
    - Jede `mapping_id` einer Action muss auf ein **existierendes Mapping** (dessen `id`) zeigen.
    - `targets[].fields[].source_dataset_id` muss `"__sql__" + <sql-node-id>` sein.
    - Jede in einem Widget referenzierte Spalte muss als SQL-Alias existieren **und** in `output_fields` **und** in `targets[].fields` stehen.
    - Jeder verwendete `{{platzhalter}}` hat einen `config_required`-Eintrag.
11. **Keine Zugangsdaten** ausgeben – DB-Verbindungen ausschließlich über `config_required` (`type: "connection"`) + `{{connection_...}}`-Platzhalter. Niemals Hosts, Benutzer, Passwörter, Ports einsetzen.

**Vor der Ausgabe**
12. **Konsistenzprüfung durchführen** – vor dem Ausgeben die Checkliste in §9 vollständig gegen das erzeugte JSON abarbeiten. Erst ausgeben, wenn alle Punkte erfüllt sind.

---

## 1. Was ist ein Template?

Ein Template ist **eine JSON-Datei**, die ein „Bündel" fertiger Datenmonster-Objekte beschreibt:

- **Datasets** – Datenquellen (SQL-Abfrage, REST-API oder statische Daten)
- **Mappings** – Transformations-/Auswertungslogik (SQL-Knoten, Feldzuordnungen → Ziel)
- **Pipelines** (optional) – automatisierte Abläufe mit Scheduler
- **Forms** – Formulare und **Dashboards** (Eingabefelder, Buttons/Aktionen, Widgets/Charts)
- **Knowledge** (optional) – Projektwissen für die KI: die Regeln, mit denen der Assistent zu diesen Daten richtiges SQL schreibt (§7b)

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
  "format_version": "1.0",
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
  "forms": [ ... ],
  "alert_rules": [ ... ],
  "reports": []
}
```

| Feld | Pflicht | Bedeutung |
|------|---------|-----------|
| `format_version` | **ja** | Version des **Template-Formats/dieser Spezifikation** (aktuell `"1.0"`). Erlaubt Datenmonster, künftige Formatänderungen zu erkennen und ältere Templates zu migrieren. **Nicht** mit `version` verwechseln. |
| `template_id` | **ja** | Eindeutige technische ID, `snake_case`, nur `[a-z0-9_]`. Beim erneuten Upload mit gleicher ID wird das bestehende Template **überschrieben**. |
| `template_name` | ja | Anzeigename im Katalog. |
| `description` | empfohlen | Kurzbeschreibung. |
| `category` | empfohlen | Freitext-Kategorie, z. B. `"jtl-reporting"`. Default `"general"`. |
| `version` | empfohlen | Version **dieses konkreten Templates** (Inhalt), z. B. `"1.0"`, `"2.0"`. Unabhängig von `format_version`. |
| `author` | optional | z. B. `"Datenmonster"`. |
| `hinweise` | empfohlen | Array aus Strings. Wird dem Nutzer beim Installieren angezeigt. |
| `config_required` | siehe §3 | Vom Nutzer beim Install abgefragte Werte (v. a. DB-Verbindung, Zeiträume). |
| `datasets` | Array | Kann leer sein (`[]`), wenn Mappings ihre Daten über SQL-Knoten holen. |
| `mappings` | Array | Die Auswertungslogik. |
| `pipelines` | Array | Meist `[]`. |
| `forms` | Array | Formulare/Dashboards. |
| `alert_rules` | Array | Unternehmenswarnungen (§7a). Optional, meist `[]`. |
| `reports` | Array | Eigenständige Berichte (`{name, widgets}`). Wird selten gebraucht – Dashboards laufen über `forms`. Optional, meist `[]`. |

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
- Für anspruchsvollere Mappings kommen `python_nodes`, `expr_nodes`, `quality_nodes`, `param_nodes` und `ai_nodes` dazu (§5.4). Sie sind optional; wer sie nicht braucht, lässt sie weg.
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

### 5.2.1 Zwei Arten von Platzhaltern: `{{key}}` (Install-Zeit) vs. `:name` (Laufzeit)

Es gibt **zwei** grundverschiedene Platzhalter-Mechanismen – nicht verwechseln:

| Syntax | Wann ersetzt | Quelle | Wofür |
|--------|--------------|--------|-------|
| `{{key}}` | **einmalig beim Installieren** | `config_required`-Wert des Nutzers | Verbindungs-ID, feste Grenzwerte/Zeiträume, die pro Installation gelten (z. B. `DATEADD(DAY, -{{ladenhueter_tage}}, GETDATE())`). Wird als Literal in den SQL-Text geschrieben. |
| `:name` | **bei jeder Ausführung** | Wert eines **Formularfelds** (`field.name` = `name`) | Interaktive Filter, die der Nutzer im Dashboard ändert – Zeitraum, Warengruppe, Drilldown. Wird als **gebundener Parameter** übergeben (SQL-Injection-sicher, nie String-Interpolation). |

**Regel für interaktive Dashboards:** Filter, die der Nutzer zur Laufzeit verstellt, laufen über `:name` und ein passendes **Formularfeld** mit `name: "<name>"` (siehe §6.3, u. a. `daterange`, `db_dropdown`). Feste, pro Installation gültige Werte laufen über `{{key}}` + `config_required`.

```sql
-- :von / :bis kommen aus einem daterange-Feld, :kwarengruppe aus einem db_dropdown-Feld.
-- Einfachauswahl (Feld ohne "multiple"): :kwarengruppe ist ein Skalar, "alle" via NULLIF.
WHERE RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)
  AND (NULLIF(:kwarengruppe, '') IS NULL OR A.kWarengruppe = CAST(NULLIF(:kwarengruppe, '') AS INT))

-- Mehrfachauswahl (db_dropdown mit "multiple": true): :kwarengruppe ist eine Liste.
-- Das Backend expandiert sie zu einer IN-Liste (:kwarengruppe → :kwarengruppe__0, __1 …)
-- und bindet automatisch das Begleit-Flag :kwarengruppe_empty (1 = nichts gewählt = alle).
WHERE RE.dErstellt >= :von AND RE.dErstellt < DATEADD(DAY, 1, :bis)
  AND (:kwarengruppe_empty = 1 OR A.kWarengruppe IN (:kwarengruppe))
```

> **Wichtig:** Jeder im SQL verwendete `:name` **muss** durch ein Formularfeld gedeckt sein (dessen Feldwert bei jeder Ausführung mitgeschickt wird), sonst bleibt der Parameter ungebunden und das SQL schlägt fehl. Für „alle"-Auswahl bei Einfachfeldern leere Werte mit `NULLIF(:name, '')` abfangen; bei Mehrfachauswahl das automatisch gebundene `:name_empty`-Flag im Muster `(:name_empty = 1 OR col IN (:name))` nutzen. `:year`/`:month` haben einen eingebauten Fallback (letzter voller Kalendermonat), falls kein Feld sie liefert.

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

### 5.4.1 Knoten für anspruchsvollere Mappings

Diese fünf gingen früher beim Ex- und Import verloren; seit August 2026 werden sie
übertragen. Für reines Reporting braucht man sie nicht – für Integrationen (Feldwerte
zerlegen, Eingaben prüfen, Laufzeitwerte einspeisen) sind sie das Mittel der Wahl.

**`param_nodes` – Laufzeitwerte ins Mapping holen**

Stellt Werte bereit, die beim Ausführen von außen kommen (Formularfeld, Pipeline-Start,
API-Aufruf). Anders als `:name` im SQL wirken sie auf der Zeilenebene und stehen damit
auch Ausdrücken und Python zur Verfügung.

```json
{ "id": "p1", "x": 40, "y": 40, "label": "Laufzeit",
  "fields": [ { "name": "stichtag", "type": "text", "label": "Stichtag", "default": "" } ] }
```

`type` ist `"text"` oder `"number"` (bei `number` wird der Wert in eine Zahl gewandelt).
Fehlt der Wert beim Lauf, greift `default`.

**`expr_nodes` – berechnete Felder aus einer Formel**

```json
{ "id": "e1", "x": 300, "y": 40,
  "output_fields": [ { "name": "Ganzname", "expr": "concat({Vorname}, ' ', {Nachname})" } ] }
```

Feldbezug in Ausdrücken mit einfachen geschweiften Klammern: `{Feldname}`.

**`quality_nodes` – Werte prüfen**

Ergänzt je Zeile `__dq_valid__` (wahr/falsch) und `__dq_errors__` (Liste der Verstöße).
Die Zeilen werden **nicht** entfernt – aussteuern muss man selbst, etwa über einen
Filter im Ziel oder eine `CASE`-Spalte.

```json
{ "id": "q1", "x": 300, "y": 200, "label": "Eingangsprüfung",
  "rules": [
    { "field": "Email", "type": "email",  "message": "Keine gültige Adresse" },
    { "field": "PLZ",   "type": "plz_de" },
    { "field": "ArtNr", "type": "regex", "pattern": "^[0-9]{4,10}$" }
  ] }
```

Zulässige `type`-Werte: `required`, `number`, `email`, `plz_de`, `phone`, `iban`, `ean`,
`vat_id`, `regex` (mit `pattern`), `date`, `url`.

**`python_nodes` – eigene Logik je Datensatz**

```json
{ "id": "py1", "x": 560, "y": 40,
  "script": "row['Ort'] = (row.get('Ort') or '').strip().title()\nreturn row" }
```

Das Skript bekommt die Zeile als `row` und gibt sie mit `return row` zurück. Verfügbar
sind `math`, `re`, `json`, `decimal`, `statistics`, `string`, `datetime`, `date`,
`timedelta` sowie die üblichen eingebauten Funktionen. **Nicht** verfügbar sind
`import`, Dateizugriff und Netzwerk; je Zeile gilt eine Zeitgrenze.

> ⚠️ **Ein Template mit `python_nodes` bringt ausführbaren Code mit.** Er läuft beim
> Ausführen des Mappings auf dem Server des Installierenden. Datenmonster weist beim
> Installieren darauf hin und protokolliert es. Nutze Python nur, wenn keine der
> anderen Knotenarten reicht – und beschreibe in `hinweise[]`, was das Skript tut.

**`ai_nodes` – Sprachmodell je Zeile**

```json
{ "id": "ai1", "x": 560, "y": 200,
  "prompt_template": "Ordne den Artikel '{{Artikelname}}' einer Warengruppe zu.",
  "output_fields": [ { "name": "Warengruppe", "type": "string" } ],
  "batch_size": 10 }
```

Feldbezug hier mit **doppelten** geschweiften Klammern. `model` ist optional; ohne
Angabe greift das eingestellte Modell. Bedenke, dass jeder Lauf echte Modellaufrufe
auslöst – bei Datenmonster AI kostet das Guthaben.

### 5.5 `rest_nodes` – fremde Schnittstellen ansprechen

Der REST-Knoten kann seit August 2026 auch **schreiben**. Er läuft über denselben Weg
wie REST-Quellen und Pipeline, samt Wiederholung bei Drosselung und Schutz vor Aufrufen
auf interne Adressen.

```json
{ "id": "r1", "x": 560, "y": 360,
  "url": "https://api.example.com/orders",
  "method": "POST",
  "mode": "single",
  "input_fields": [ { "field": "Auftragsnr", "placeholder": "{Auftragsnr}" } ],
  "body_type": "json",
  "body_content": "{\"name\": \"{{Auftragsnr}}\", \"menge\": {{Menge}}}",
  "auth_type": "bearer",
  "auth_config": { "token": "" },
  "data_path": "",
  "response_mappings": [ { "json_path": "id", "output_field": "externe_id" } ],
  "status_field": "http_status",
  "error_field": "http_fehler",
  "store_response": false }
```

| Feld | Bedeutung |
|------|-----------|
| `method` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE` |
| `mode` | `"single"` (ein Aufruf je Zeile) oder `"batch"` (alle Werte in einem Aufruf) |
| `input_fields` | Felder, deren Werte eingesetzt werden. `{Feld}` und `{{Feld}}` funktionieren beide |
| `{{json:Feld}}` | setzt den Wert **unmaskiert** ein – für JSON, das die Datenbank schon fertig gebaut hat (siehe unten) |
| `body_type` / `body_content` | `none`, `json`, `form`, `xml`, `raw`. Werte im JSON-Rumpf werden JSON-gerecht maskiert |
| `auth_type` / `auth_config` | `none`, `basic`, `bearer`, `apikey`, `oauth2_cc`, `oauth2_refresh` |
| `response_mappings` | `json_path` → `output_field` |
| `status_field` / `error_field` | optionale Spalten für Statuscode und Fehlertext |
| `store_response` | ob die Antwort im Systemprotokoll aufgehoben wird (kann personenbezogene Daten enthalten) |
| `timeout` | Sekunden, Vorgabe 30 |

> **Zugangsdaten gehören nicht ins Template.** Beim Export werden `token`, `password`,
> `key_value`, `client_secret` geleert; das Verfahren bleibt stehen. Lege für Geheimnisse
> einen `config_required`-Eintrag an oder lass den Installierenden sie im Knoten eintragen.
>
> Im Einzelmodus wird das Ergebnis je Eingabewert nur einmal geholt – **außer** bei
> `POST`/`PUT`/`PATCH`/`DELETE`: dort läuft jede Zeile für sich, sonst würden zwei gleich
> aussehende Zeilen nur einen Aufruf auslösen. Je Knoten und Lauf sind höchstens
> 1000 Aufrufe zulässig.

#### Listen im Rumpf: `{{json:Feld}}`

Werte in einem JSON-Rumpf werden maskiert – aus `Meyer "Bau" GmbH` wird
`Meyer \"Bau\" GmbH`, damit der Rumpf gültig bleibt. Für eine **Liste**, etwa die
Positionen eines Auftrags, ist das falsch: sie käme als Text an, nicht als Array.

Dafür gibt es `{{json:Feld}}`. Der Wert wird unverändert eingesetzt und muss selbst
gültiges JSON sein; ist er es nicht, bricht dieser eine Aufruf mit einer klaren Meldung
ab, statt einen kaputten Rumpf loszuschicken. Beide Formen dürfen im selben Rumpf stehen.

Die Liste baut man am besten schon in SQL – der MS SQL Server kann das seit 2016:

```sql
SELECT
    A.cAuftragsNr AS name,
    ISNULL((SELECT POS.cArtNr AS item,
                   CAST(POS.fAnzahl AS DECIMAL(18,3)) AS amount
            FROM Verkauf.tAuftragPosition POS
            WHERE POS.kAuftrag = A.kAuftrag AND POS.nType = 1
            FOR JSON PATH), '[]') AS items_json
FROM Verkauf.tAuftrag A
```

Im Knoten dann:

```json
{ "body_type": "json",
  "body_content": "{\"name\": \"{{name}}\", \"items\": {{json:items_json}}}" }
```

Zwei Kleinigkeiten aus der Praxis: `ISNULL(..., '[]')` fängt Aufträge ohne Positionen ab
(ohne das liefert `FOR JSON` `NULL`, und im Rumpf steht dann `null`), und `CAST(... AS
DECIMAL(18,3))` verhindert Mengen wie `30.0000000000000`. In URL und Kopfzeilen wirkt
`{{json:…}}` nicht – dort gehört kein JSON hin.

---

## 6. `forms` – Formulare & Dashboards

Ein Formular kann **Eingabeformular**, **Dashboard** oder beides sein. Es besteht aus einem `schema` mit bis zu fünf Teilen (`result_tabs` ist optional):

```json
{
  "name": "Umsatz nach Artikel",
  "schema": {
    "fields":      [ /* Eingabe-/Filterfelder + Layout (optional) */ ],
    "layout":      [ /* meist leer */ ],
    "actions":     [ /* führen Mappings/Pipelines aus */ ],
    "widgets":     [ /* zeigen Ergebnisse an */ ],
    "result_tabs": [ /* optional: Widgets in Reiter gruppieren (§6.2.1) */ ]
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
| `type` | Siehe Tabelle unten. Für Dashboards fast immer `"run_mapping"`. |
| `mapping_id` | **Die Template-interne Mapping-`id`** (z. B. `"mapping_kpi"`). Beim Install automatisch auf die echte ID umgeschrieben. |
| `pipeline_id` | Bei `run_mapping` `null`; bei `run_pipeline` die Pipeline-ID. |
| `label` | Button-Beschriftung. |

> **Kritisch:** `mapping_id` in der Action muss **exakt** der `id` eines Mappings in `mappings[]` entsprechen – sonst findet der Installer keine Zuordnung.

**Die vier Aktions-Typen:**

| `type` | Wirkung |
|--------|---------|
| `run_mapping` | Führt das Mapping **lesend** aus und liefert das Ergebnis an die Widgets. **Die Ziele des Mappings werden dabei nicht geschrieben.** Der Normalfall für Dashboards. |
| `export_mapping` | Führt das Mapping **schreibend** aus: alle Ziele werden bedient und Dateien erzeugt (z. B. `.idev`, CSV). Nötig überall dort, wo ein Klick tatsächlich etwas erzeugen oder fortschreiben soll. |
| `run_pipeline` | Startet eine Pipeline. Statt `mapping_id` wird `pipeline_id` gesetzt. |
| `run_alerts` | Wertet die Unternehmenswarnungen aus (§7a) und speist ein `alerts`-Widget. Über `options.cockpits` bzw. `options.rule_keys` lässt sich eingrenzen, welche Regeln laufen. |

> **Häufiger Fehler:** Ein Knopf, der Daten schreiben soll, bekommt `run_mapping`. Dann
> passiert nichts – ohne Fehlermeldung, weil der lesende Lauf ja gelingt. Für schreibende
> Abläufe `export_mapping` oder `run_pipeline` verwenden.

```json
{ "id": "act_warnungen", "type": "run_alerts", "mapping_id": null, "pipeline_id": null,
  "label": "Warnungen prüfen", "options": { "cockpits": ["gf"] } }
```

### 6.2 `widgets` – Anzeige

Jedes Widget hat `id`, `type`, `label`, `action_id` (verweist auf eine Action) und `config`. `config.width` ist die Breite im **12-Spalten-Raster** (1–12).

**Widget-Typen:**

| Typ | Zweck | braucht `action_id` |
|-----|-------|---------------------|
| `kpi` | Kennzahl, optional mit Vorjahresvergleich | ja |
| `bar` / `line` / `pie` | Diagramme | ja |
| `table` | Tabelle, sortierbar, mit Drilldown | ja |
| `ai_summary` | KI-Kurzanalyse über die Zahlen des Dashboards | ja |
| `tasklist` | Aufgabenliste mit Ampel; Klick öffnet die Detailliste | ja |
| `alerts` | Unternehmenswarnungen; gehört zu einer `run_alerts`-Aktion (§7a) | ja |
| `kostenstruktur` | Maske für die monatlichen Fixkosten | nein |
| `eingangsrechnung` | E-Rechnung einlesen und freigeben | nein |
| `ean_research` | EAN-Recherche beim Hersteller | nein |
| `hersteller_navigator` | Hersteller → Artikel → Vorschlag | ja |

Die drei Widgets ohne `action_id` (`kostenstruktur`, `eingangsrechnung`, `ean_research`)
sind eigenständig: sie holen ihre Daten selbst und erscheinen sofort, ohne dass ein
Mapping laufen muss.

#### KPI-Kachel (`kpi`)
```json
{
  "id": "w_kpi_umsatz", "type": "kpi", "label": "Umsatz netto",
  "action_id": "act_kpi",
  "config": {
    "width": 4,
    "column": "UmsatzNetto",
    "aggregation": "first",
    "prefix": "€ ", "suffix": "", "decimals": 2,
    "compare_column": "UmsatzNettoVJ",
    "compare_label": "Vorjahr",
    "invert_delta": false
  }
}
```
- `column`: anzuzeigende Spalte. `aggregation`: `first` | `sum` | `avg` | `count` | `max` | `min`. `prefix`/`suffix`/`decimals` formatieren die Zahl. (Für einen einzelnen SQL-Aggregatwert `"first"` verwenden; für „Anzahl Zeilen" `"count"` auf einer beliebigen Spalte.)
- **Vergleichswert (optional):** `compare_column` = zweite Spalte **aus derselben SQL-Zeile** (z. B. der Vorjahreswert). Die KPI zeigt dann Delta (Pfeil ↑↓ + %) und den Vergleichswert an. `compare_label` beschriftet ihn (Default `"Vorperiode"`). `invert_delta: true` färbt einen Rückgang grün – für Kennzahlen, bei denen weniger besser ist (z. B. Storno-Quote). Das SQL muss beide Werte als Aliase liefern (also z. B. `AS UmsatzNetto` **und** `AS UmsatzNettoVJ`), beide in `output_fields`/`targets[].fields`.

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

#### KI-Kurzanalyse (`ai_summary`)
```json
{
  "id": "w_ai_uebersicht", "type": "ai_summary", "label": "KI-Kurzanalyse der Kennzahlen",
  "action_id": "act_overview_kpi",
  "config": { "width": 12, "instruction": "Fokus auf Entwicklung zum Vorjahr und Handlungsbedarf." }
}
```
- Formuliert aus dem **Ergebnis der verknüpften Action** (Spalten + Zeilen) eine kurze deutsche Management-Zusammenfassung (2–4 Sätze) per KI. **Verbraucht keine eigene DB-Abfrage** – lege es auf die **gleiche `action_id`** wie eine bereits vorhandene KPI-/Tabellen-Action (Datenwiederverwendung), z. B. die Übersichts-KPI-Zeile.
- Bei **einer** Ergebniszeile (KPI-Zeile) werden Vorjahres-Deltas serverseitig berechnet; erkennt Vergleichsspalten automatisch am Namensschema `<Spalte>` + `<Spalte>VJ` bzw. `…Vorjahr`. Vergib deine Vergleichsspalten entsprechend, dann werden Prozentwerte korrekt formuliert.
- `config.instruction` (optional): zusätzliche Fokus-Anweisung an die KI. `config.width` wie üblich.
- **Voraussetzung:** Die KI-Integration muss unter *Systemeinstellungen* aktiv sein (Ollama). Ist sie aus, zeigt das Widget einen Hinweis statt Text. Das Ergebnis wird pro Datenstand gecacht (erneutes Öffnen ist sofort da).

#### Eingangsrechnungs-Freigabe (`eingangsrechnung`)
Spezial-Widget für den DATEV/JTL-Eingangsrechnungs-Workflow. `config.connection_id` = Ziel-WaWi-Verbindung. Nur verwenden, wenn ausdrücklich gefordert.

> **Balken-/Linien-/Kreis-Widgets** unterstützen optional `config.drilldown` (Klick auf ein Segment lädt Detaildaten). Für die Erstgenerierung weglassen.

#### Mehrere Serien (Vergleichslinien/-balken)

`line`- und `bar`-Widgets akzeptieren mehrere `y_columns`. So baust du z. B. „Aktuell vs. Vorjahr":
das SQL liefert pro X-Wert (z. B. Monat) zwei Spalten (`Umsatz`, `UmsatzVorjahr`), das Widget setzt
`"y_columns": ["Umsatz", "UmsatzVorjahr"]`. Ab zwei Serien wird automatisch eine Legende gezeigt.

### 6.2.1 `result_tabs` – Ergebnis-Register (Reiter)

Ein Dashboard kann seine Widgets in **Reiter** gruppieren (wie im Screenshot „Umsatz / Lager / …").
`result_tabs` ist ein **optionaler fünfter Schlüssel** im `schema` (neben `fields`, `layout`, `actions`, `widgets`):

```json
"result_tabs": [
  { "id": "tab_umsatz", "label": "Umsatz",
    "action_ids": ["act_umsatz_kpi", "act_umsatz_verlauf", "act_umsatz_auftraege"] },
  { "id": "tab_lager", "label": "Lager & Kapitalbindung",
    "action_ids": ["act_lager_kpi", "act_kapital_wg", "act_lager_tabelle"] }
]
```

- Jeder Reiter bündelt Actions über `action_ids`. Ein Widget erscheint im Reiter, dessen `action_ids` seine `action_id` enthalten.
- **Alle** Actions laufen gemeinsam (z. B. beim Klick auf ein Zeitraum-Preset) – die Reiter steuern nur die **Anzeige**, nicht die Ausführung.
- `id` in `snake_case`, `label` ist der Reitertext. Ohne `result_tabs` werden alle Widgets untereinander gezeigt.

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
| Filter (Dashboard) | `daterange`, `db_dropdown` | Interaktive Filter, die Laufzeit-Parameter (`:name`) setzen und die Widgets aktualisieren. Siehe unten. |
| Aktion | `button` | `action_id` verweist auf eine Action; kein `name`. |
| Layout | `heading`, `label`, `divider`, `container` | `heading`/`label` nutzen `content` als Text. Kein `name`/`required`. |

- `row`: Zeilenindex; `colSpan`: Breite im 12er-Raster.
- `required: true` markiert Pflichtfelder (nur Eingabefelder).
- Ein **Button** löst eine Action aus – so kombinierst du Eingaben mit Auswertung (die Eingabewerte können als SQL-Parameter genutzt werden, sofern das Mapping darauf ausgelegt ist).

#### Dashboard-Filter: `daterange` (Zeitraum mit Presets)

Setzt **zwei** Laufzeit-Parameter (`config.param_from`/`param_to`, Default `von`/`bis`) und aktualisiert die Widgets. Rendert einen **Kalender-Popover** zur Bereichsauswahl plus Preset-Buttons. Ideal als Kopfzeile eines Dashboards zusammen mit einem Vorjahresvergleich.

```json
{
  "id": "f_zeitraum", "type": "daterange", "row": 0, "colSpan": 8,
  "label": "Zeitraum", "name": "zeitraum",
  "action_ids": ["act_umsatz_kpi", "act_umsatz_verlauf"],
  "config": { "param_from": "von", "param_to": "bis", "default": "this_year", "auto_run": true }
}
```

- Rendert einen Kalender-Popover (Bereichsauswahl per Klick auf Start-/Endtag) + Preset-Buttons: `this_month`, `last_month`, `this_year`, `last_year`, `days_30`, `months_12`.
- `config.default` = Preset, mit dem das Dashboard **beim Öffnen automatisch** lädt. `auto_run: true` löst bei jeder Änderung die Actions aus.
- `action_ids` = welche Actions ausgelöst werden (leer/fehlt → alle Actions des Formulars).
- Das SQL bindet die Werte als `:von` / `:bis` (siehe §5.2.1). Für einen Vorjahresvergleich im selben SQL: `DATEADD(YEAR, -1, :von)` … `DATEADD(YEAR, -1, :bis)`.

#### Dashboard-Filter: `db_dropdown` (Auswahl aus der DB, z. B. Warengruppe)

Dropdown, dessen Optionen **live aus der JTL-DB** geladen werden – ohne SQL im Template (aus Sicherheitsgründen). Der Feld-`name` ist der Laufzeit-Parameter.

```json
{
  "id": "f_warengruppe", "type": "db_dropdown", "row": 0, "colSpan": 4,
  "label": "Warengruppe", "name": "kwarengruppe",
  "action_ids": ["act_umsatz_kpi", "act_umsatz_verlauf"],
  "config": { "connection_id": "{{connection_jtl}}", "kind": "warengruppe",
              "placeholder": "— alle Warengruppen —", "multiple": true, "auto_run": true }
}
```

- `config.kind`: vordefinierte Lookup-Art. Verfügbar: `"warengruppe"` (aus `dbo.tWarengruppe`), `"kategorie"` (aus `dbo.tkategorie`). Weitere Arten werden serverseitig hinterlegt.
- `config.connection_id`: `"{{connection_jtl}}"` (wird beim Install aufgelöst).
- `config.multiple`: `true` → **Mehrfachauswahl** (Checkbox-Popover); der Feldwert ist eine **Liste**. Setze dann auch das Feld-`default` auf `[]`. Ohne `multiple` ist es ein Einfach-Dropdown mit skalarem Wert.
- Der Feld-`name` (z. B. `kwarengruppe`) ist der `:name`, den das SQL bindet.
  - **Einfachauswahl:** Leerauswahl → leerer String; im SQL mit `NULLIF(:kwarengruppe, '') IS NULL` als „alle" behandeln.
  - **Mehrfachauswahl:** Liste; im SQL das Muster `(:kwarengruppe_empty = 1 OR A.kWarengruppe IN (:kwarengruppe))` nutzen (Backend expandiert die IN-Liste und bindet `:kwarengruppe_empty` automatisch; leere Auswahl = alle).
- `auto_run: true` aktualisiert die Widgets bei Auswahl.

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

## 7a. `alert_rules` – Unternehmenswarnungen

Eine Warnregel ist **Daten, kein Code**: Die Zahl kommt aus einem ganz normalen Mapping,
die Regel entscheidet nur, ab wann daraus eine Warnung wird und wie dringend sie ist.
Es wird nichts geschätzt oder vom Modell erfunden.

```json
"alert_rules": [
  {
    "rule_key": "gf_offene_posten_ueberfaellig",
    "name": "Überfällige Forderungen",
    "description": "Rechnungen über Zahlungsziel",
    "category": "Liquidität",
    "cockpit": "gf",
    "severity": "warnung",
    "mapping_name": "GF – Offene Posten überfällig",
    "condition": { "mode": "count", "min_count": 1, "value_column": "Betrag" },
    "facts": [ { "label": "Offener Betrag", "column": "Betrag", "unit": "€" } ],
    "title_template": "{anzahl} überfällige Forderungen",
    "subtitle": "Mahnlauf prüfen",
    "drilldown": { "mapping_name": "GF – Offene Posten Detail", "title": "Überfällige Rechnungen" },
    "sort": 100
  }
]
```

| Feld | Bedeutung |
|------|-----------|
| `rule_key` | **Pflicht.** Eindeutiger Schlüssel. Beim erneuten Installieren wird darüber abgeglichen; was der Anwender an `active`, `severity` und `sort` verstellt hat, bleibt erhalten. |
| `name` | **Pflicht.** Anzeigename. |
| `mapping_name` | Name des auswertenden Mappings. **Bevorzugt**, weil Mapping-IDs je Installation verschieden sind – und weil eine Regel auf ein Mapping aus einem *anderen* Template zeigen darf. |
| `mapping_id` | Alternativ die Template-interne Mapping-`id`; der Installer setzt die echte ID ein. |
| `category` | Freitext, gruppiert die Anzeige (z. B. „Liquidität"). |
| `cockpit` | Herkunfts-Cockpit; eine `run_alerts`-Aktion kann darüber eingrenzen. |
| `severity` | `kritisch`, `warnung`, `hinweis`, `info`, `positiv`. |
| `severity_levels` | Eskalation, erster Treffer gewinnt: `[{"metric": "wert", "op": ">=", "value": 10000, "severity": "kritisch"}]`. Als `metric` stehen `anzahl`, `wert` und `summe` zur Verfügung. |
| `condition` | Die eigentliche Regel, siehe unten. |
| `facts` | Die nachvollziehbaren Zahlen hinter der Warnung: `[{"label": "…", "column": "…", "unit": "€"}]`. Der Anwender muss sehen, **warum** gewarnt wird. |
| `title_template` | Überschrift mit Platzhaltern, z. B. `"{anzahl} überfällige Forderungen"`. |
| `subtitle` | Handlungshinweis im Klartext. |
| `drilldown` | `{mapping_name oder mapping_id, title, hidden_columns}` – die Liste hinter der Warnung. |
| `params` | Zusätzliche Laufzeitparameter für das Mapping. |
| `action_kind` | Art der KI-Handlungsempfehlung, falls gewünscht. |
| `active`, `sort` | Vorbelegung; im Betrieb vom Anwender änderbar. |

**Die drei `condition.mode`:**

```json
{ "mode": "count", "min_count": 1, "value_column": "Betrag" }
```
Eine Warnung, sobald die Ergebnisliste Zeilen hat – die SQL-Abfrage selbst definiert also,
was ein Problem ist. Anzahl und Summe erscheinen im Text.

```json
{ "mode": "kpi", "column": "Umsatz", "op": "<", "compare_column": "UmsatzVJ", "factor": 0.95 }
```
Vergleicht Werte **einer** Kennzahlenzeile. Statt `compare_column` kann über
`"value_config": "<schluessel>"` ein zentral gepflegter Schwellwert herangezogen werden.

```json
{ "mode": "rows", "limit": 5, "label_column": "Kunde", "value_column": "Betrag" }
```
Jede Zeile wird zu einer eigenen Warnung – für Einzelfälle.

> **Schwellwerte gehören nicht ins Template.** Nutze `condition.value_config` und
> verweise damit auf die zentrale Schwellwertverwaltung des Projekts. Fest verdrahtete
> Grenzwerte kann der Anwender später nicht anpassen.
>
> **Fehlt das Mapping**, auf das eine Regel zeigt, ist das kein Fehler: die Regel meldet
> sich im Lauf als „nicht verfügbar". Ein Template darf also Regeln für Auswertungen
> mitbringen, die erst mit einem anderen Template kommen.

Damit die Warnungen im Dashboard erscheinen, braucht das Formular eine `run_alerts`-Aktion
und ein `alerts`-Widget, das darauf zeigt (§6.1/§6.2).

---

## 7b. `knowledge` – Projektwissen für die KI

Ein Template bringt nicht nur Auswertungen mit, sondern auch das **Wissen, das die KI
braucht, um zu diesen Daten brauchbares SQL zu schreiben**. Ohne diese Regeln greift der
KI-Assistent im Mapping-Editor zur falschen Tabelle: „gekauft" landet dann bei
`Verkauf.tAuftrag` statt bei `Rechnung.vRechnung`, „Kundennummer" bei `kKunde` statt bei
`cKundennr`. Die Einträge landen in derselben Wissensdatenbank, die auch über
*Systemeinstellungen → KI-Wissen* gepflegt wird.

```json
"knowledge": [
  {
    "category": "rule",
    "title": "JTL – \"gekauft\" heißt Rechnung, nicht Auftrag",
    "content": "Umgangssprachliche Kundenfragen meinen RECHNUNGEN: \"was hat der Kunde gekauft\", \"letzter Kauf\", \"schlafende Kunden\". Quelle ist immer Rechnung.vRechnung (Belegdatum dErstellt, ISNULL(nStorno,0) = 0), NICHT Verkauf.tAuftrag.",
    "always_include": true,
    "scope": "global"
  }
]
```

| Feld | Bedeutung |
|------|-----------|
| `title` | **Pflicht.** Zugleich der Abgleichsschlüssel: beim erneuten Installieren wird ein gleichnamiger Eintrag aktualisiert statt gedoppelt. |
| `content` | **Pflicht.** Die Regel im Klartext. Konkret und überprüfbar – Tabellen, Spalten, Bedingungen ausschreiben. |
| `category` | `rule`, `field_mapping`, `table`, `format` oder `other`. Nur zur Gruppierung. |
| `always_include` | `true` = Grundregel, geht in **jeden** KI-Kontext. `false` (Standard) = wird nur bei passenden Stichwörtern ausgewählt. |
| `scope` | `global` (Standard) oder `project` – bei `project` bindet der Installer den Eintrag an das Zielprojekt. |

**Sparsam mit `always_include`.** Grundregeln überspringen die Relevanzauswahl und
verbrauchen in jedem Prompt Platz. Nimm es nur für Regeln, die wirklich immer gelten.

**Eine Regel muss den Gegenfall ausschließen.** Die Stichwortauswahl zieht auch
widersprechendes Wissen mit in den Kontext. Eine Regel „nimm X" verliert gegen einen
danebenstehenden Eintrag, der Y empfiehlt – schreibe deshalb dazu, *wann* die Alternative
richtig ist („Verkauf.tAuftrag nimmst du nur, wenn ausdrücklich von Auftrag oder Angebot
die Rede ist").

> **Kein Erfinden.** Schreibe nur Regeln, die gegen eine echte Datenbank geprüft sind.
> Falsches Wissen ist schlimmer als keines: es wird ungeprüft in jedes generierte SQL
> übernommen.

**Ein Template darf auch nur aus Wissen bestehen.** `datasets`, `mappings` und
`forms` bleiben dann leer — beim Installieren entstehen keine Objekte im Projekt,
nur Regeln in der Wissensdatenbank. So ist das Modul „JTL-Wissen für die KI"
(`jtl_wissen_paket`) gebaut, das im Shop einzeln erhältlich ist.

Beim **Deinstallieren** des Templates werden nur die Einträge gelöscht, die dieses
Template selbst angelegt hat – vorher vorhandene Regeln bleiben unberührt. Der Schalter
`enabled` wird bei einer Aktualisierung nie überschrieben: was der Anwender abgeschaltet
hat, bleibt aus.

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

- [ ] Nur die JSON-Datei ausgegeben (kein Text/Markdown drumherum), gültiges JSON (keine Kommentare, keine trailing commas, korrekt escapte `\n` in SQL-Strings), UTF-8.
- [ ] `format_version` auf die aktuelle Format-Version gesetzt.
- [ ] Keine erfundenen Felder/Typen (nur dokumentierte Schlüssel und Node-/Widget-/Action-Typen).
- [ ] Alle IDs in `snake_case`; `template_id` eindeutig.
- [ ] Für jede DB-Verbindung ein `config_required`-Eintrag `type: "connection"`; in SQL-Knoten als `connection_id: "{{...}}"` referenziert.
- [ ] Jeder verwendete `{{platzhalter}}` hat einen `config_required`-Eintrag (außer den Connection-Platzhaltern, die du selbst als `connection`-Eintrag anlegst).
- [ ] Jedes Mapping: alle Node-Arrays vorhanden (leere als `[]`), SQL-Knoten mit `mode: "transform"`.
- [ ] `source_dataset_id` = `"__sql__" + sql-node-id` in **jedem** Ziel-Feld.
- [ ] Jede im Widget genutzte Spalte kommt als Alias im SQL vor **und** steht in `output_fields` **und** in `targets[].fields`. Das gilt auch für `compare_column` bei KPI-Kacheln.
- [ ] Jede Action `mapping_id` = existierende Mapping-`id`; jedes Widget `action_id` = existierende Action-`id`; jede `result_tabs[].action_ids` = existierende Action-`id`.
- [ ] Jeder Laufzeit-`:name` im SQL ist durch ein **Formularfeld** gedeckt (Feld-`name` bzw. `daterange`-`param_from`/`param_to`); feste Installations-Werte dagegen als `{{key}}` + `config_required` (nicht `:name`).
- [ ] T-SQL-Dialekt (MS SQL Server / JTL-Wawi): `TOP n`, `GETDATE()`, `DATEADD`, `CAST(... AS DECIMAL(18,2))`.
- [ ] Widget-`config.width` je Zeile sinnvoll aufs 12er-Raster verteilt.
- [ ] `pipelines: []` und `portal_config: {}` gesetzt, falls nicht gebraucht.
- [ ] Jede Aktion hat den passenden Typ: `run_mapping` liest nur, Schreibendes braucht `export_mapping` oder `run_pipeline` (§6.1).
- [ ] Widgets ohne `action_id` sind nur `kostenstruktur`, `eingangsrechnung` und `ean_research`; alle übrigen brauchen eine (§6.2).
- [ ] `alert_rules[]`: jede Regel hat einen eindeutigen `rule_key`, zeigt per `mapping_name` auf ihre Auswertung und begründet sich über `facts` (§7a). Grenzwerte über `condition.value_config` statt fest verdrahtet.
- [ ] Keine Zugangsdaten im Template – weder in `rest_nodes`, noch in `datasets[].rest_config`, noch in `config_required[].default`.
- [ ] `python_nodes` nur verwendet, wenn keine andere Knotenart reicht; in `hinweise[]` erklärt, was das Skript tut (§5.4.1).

---

## 10. Vollständiges Minimalbeispiel (Dashboard mit KPI + Balken + Tabelle)

```json
{
  "format_version": "1.0",
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

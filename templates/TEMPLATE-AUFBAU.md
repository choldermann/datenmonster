# Datenmonster – Aufbau eines funktionierenden Dashboard-Templates

Diese Anleitung beschreibt das JSON-Format eines Datenmonster-Templates **exakt so, wie der
Installer es liest** (`backend/app/api/templates.py`). Dashboards sind **Formulare** – es gibt
keinen separaten Report-Bereich. Ein Dashboard besteht aus:

1. **Mappings** – je Widget eine SQL-Abfrage (aggregiert!), die Zeilen liefert.
2. Einem **Formular** mit
   - **Actions** (`run_mapping`), die je ein Mapping ausführen, und
   - **Widgets** (KPI/Bar/Line/Pie/Tabelle), die das Ergebnis einer Action anzeigen.

> Falsche Feldnamen führen **nicht** zu einem Fehler – das Widget bleibt einfach leer. Feldnamen
> 1:1 aus dieser Doku übernehmen.

---

## 0. Die wichtigste Regel: im SQL aggregieren

Ein Action-Lauf liefert **maximal ~500 Zeilen** an das Widget zurück, und es gibt **keine**
serverseitige Aggregation über einen ganzen Datenbestand. Deshalb:

- Ein KPI „Gesamtumsatz" darf **nicht** über Rohzeilen summieren (nur die ersten 500 → falsche
  Summe). Stattdessen: eine Query `SELECT SUM(...) AS Gesamtumsatz` (1 Zeile), das Widget nimmt den
  Wert mit `aggregation: "first"`.
- Ein Balkendiagramm „Top Kunden" → `SELECT TOP 15 Kunde, SUM(...) AS Umsatz ... GROUP BY Kunde`.
- **Jedes Widget bekommt seine eigene, fertig aggregierte Query.** Die Widgets rechnen nichts mehr,
  sie zeichnen nur.

Ausnahme: Mehrere Widgets dürfen sich **eine** Action teilen, wenn dieselbe Ergebnismenge passt
(z. B. Balken + Torte über „Top Artikel" oder mehrere KPIs aus einer Kennzahlen-Query).

---

## 1. Lebenszyklus

1. **Hochladen** (`POST /api/templates/upload`, UI „Template hochladen"): registriert die JSON-Datei
   als `Template`. Schlüssel ist `template_id`; gleiche `template_id` erneut hochladen = Update.
2. **Installieren** (`POST /api/templates/install`): legt im gewählten Projekt (`project_id`) die
   Mappings und das Formular an. Es wird **kein** Projekt angelegt → mehrere Templates können in
   dasselbe Projekt.

---

## 2. Top-Level-Struktur

```jsonc
{
  "template_id":   "jtl_umsatz_nach_kunde",   // PFLICHT, eindeutig (Upload scheitert ohne)
  "template_name": "JTL – Umsatz nach Kunde",
  "description":   "Dashboard-Formular: Top-Kunden, Umsatz nach Land",
  "category":      "jtl-reporting",
  "version":       "2.0",
  "author":        "Datenmonster",
  "hinweise":      [ "Zeilen, die dem Nutzer beim Installieren angezeigt werden." ],
  "config_required": [ /* §3 */ ],
  "datasets":      [],            // für SQL-Dashboards leer – Daten kommen aus den Mappings
  "mappings":      [ /* §4 */ ],
  "pipelines":     [],
  "forms":         [ /* §5 */ ]   // genau EIN Eintrag = das Dashboard
}
```

> **Kein `reports`-Schlüssel mehr.** Ein `reports`-Block in alten Templates wird beim Installieren
> ignoriert.

---

## 3. `config_required` – Nutzer-Eingaben & Platzhalter

Jeder Eintrag erzeugt ein Eingabefeld im Install-Dialog; der Wert ersetzt `{{key}}` überall im
Template.

```jsonc
"config_required": [
  { "key": "connection_jtl", "label": "JTL-Datenbankverbindung (MS SQL)", "type": "connection", "default": "" },
  { "key": "monate",         "label": "Zeitraum in Monaten",              "type": "text",       "default": "24" }
]
```

| Platzhalter | Wo | Auflösung |
|---|---|---|
| `{{beliebig}}` | jeder String (SQL, Labels …) | Text-Replace |
| `{{connection_X}}` | **nur** in `connection_id` / `target_connection_id` | echte Verbindungs-ID |

> Der `key` einer Verbindung **muss** mit `connection_` beginnen. Zugangsdaten werden nie ins
> Template geschrieben – der Nutzer wählt beim Installieren eine vorhandene Verbindung.

---

## 4. `mappings` – die Datenquellen (ein SQL-Node je Mapping)

Jedes Mapping führt **eine** SQL-Abfrage aus und gibt deren Spalten als Ergebniszeilen zurück. Die
Struktur ist fix – am besten unverändert übernehmen und nur `id`, `name`, das SQL und die `fields`
anpassen:

```jsonc
{
  "id":   "mapping_kpi",              // template-interne ID (Action referenziert sie)
  "name": "Umsatz-Kennzahlen",
  "canvas_nodes": [], "joins": [],
  "sql_nodes": [
    {
      "id": "sql1", "x": 120, "y": 40, "width": 350, "height": 244,
      "connection_id": "{{connection_jtl}}",     // Verbindungs-Platzhalter
      "mode": "transform",                        // PFLICHT (siehe Kasten unten)
      "output_field": "sql_1",
      "output_fields": ["Gesamtumsatz"],          // = die SELECT-Aliase
      "sql": "SELECT CAST(SUM(REPO.fAnzahl*REPO.fVkNetto) AS DECIMAL(18,2)) AS Gesamtumsatz FROM ... WHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date))"
    }
  ],
  "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
  "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
  "targets": [
    {
      "id": "t1", "name": "Umsatz-Kennzahlen", "target_type": "dataset",
      "target_connection_id": null, "target_table": "", "target_write_mode": "replace",
      "target_options": {},
      "fields": [
        // je Ausgabespalte des SELECT genau ein Eintrag:
        { "source_field": "Gesamtumsatz", "target_field": "Gesamtumsatz", "target_type": "float",
          "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Gesamtumsatz" } }
      ]
    }
  ]
}
```

> **⚠️ `mode: "transform"` ist PFLICHT.** Nur damit läuft ein SQL-Node ohne Canvas-Dataset direkt
> gegen die DB-Verbindung, bindet `:param`-Werte aus dem Formular und wendet automatisch ein
> Preview-Limit an. **Fehlt `mode`, kommt das Mapping leer zurück** („Keine Datasets auf dem Canvas").
> `output_fields` = Liste der SELECT-Aliase (optional, fällt sonst auf die Ergebnisspalten zurück).

Regeln:
- **`source_dataset_id` in jedem Feld = `"__sql__sql1"`** (Präfix `__sql__` + SQL-Node-ID). So findet
  die Engine die Spalte im SQL-Ergebnis.
- Für **jede** SELECT-Ausgabespalte genau einen `fields`-Eintrag; `source_field` = `target_field` =
  der SELECT-Alias. `transformer` immer `{ "type": "direct", "source_field": "<alias>" }`.
- `target_type`: `"float"` (Zahl/Geld), `"integer"`, `"string"` – rein informativ (beim Anzeigen wird
  nicht geschrieben, `target_write_mode` ist egal).
- `{{monate}}` u. Ä. im SQL, `{{connection_jtl}}` in `connection_id`.
- Der Lese-Lauf schreibt **nichts** ins Ziel (Vorschaumodus). `target_type: "dataset"` ist nur ein
  neutraler Platzhalter.

---

## 5. `forms` – das Dashboard (Actions + Widgets)

Genau **ein** Formular-Eintrag. Das `schema` hat vier Listen; für Dashboards zählen `actions` und
`widgets` (`fields`/`layout` bleiben leer).

```jsonc
"forms": [
  {
    "name": "JTL Umsatz nach Kunde",
    "portal_config": {},
    "schema": {
      "fields": [], "layout": [],
      "actions": [
        { "id": "act_kpi", "type": "run_mapping", "mapping_id": "mapping_kpi", "pipeline_id": null, "label": "Kennzahlen" }
      ],
      "widgets": [
        { "id": "w_kpi_umsatz", "type": "kpi", "label": "Gesamtumsatz", "action_id": "act_kpi",
          "config": { "width": 4, "column": "Gesamtumsatz", "aggregation": "first", "prefix": "€ ", "decimals": 2 } }
      ]
    }
  }
]
```

### 5.1 Actions

```jsonc
{ "id": "act_kpi", "type": "run_mapping", "mapping_id": "mapping_kpi", "pipeline_id": null, "label": "Kennzahlen" }
```
- `mapping_id` = die **template-interne Mapping-ID** (String, z. B. `"mapping_kpi"`). Der Installer
  ersetzt sie durch die echte ID.
- `label` wird im Formular als Auswerten-Button angezeigt.

### 5.2 Widgets

Grundgerüst: `{ "id", "type", "label", "action_id", "config" }`
- `action_id` verweist auf eine Action-`id` (kein Platzhalter, reiner Formular-interner Bezug).
- `config.width` = Breite im **12-Spalten-Raster**. Widgets werden zeilenweise gefüllt; sobald die
  Summe 12 übersteigt, beginnt eine neue Zeile. Pro Zeile auf Summe = 12 achten.

Gültige `type`-Werte: `kpi`, `bar`, `line`, `pie`, `table`.
**Kein `map`/`heatmap`** – die gibt es im Formular-Editor nicht.

**`kpi`** (eine Kennzahl – erwartet i. d. R. eine 1-Zeilen-Query):
```jsonc
"config": { "width": 4, "column": "Gesamtumsatz",
            "aggregation": "first",   // first | sum | avg | count | max | min
            "prefix": "€ ", "suffix": "", "decimals": 2 }
```

**`bar`** / **`line`**:
```jsonc
"config": { "width": 8, "x_column": "Kunde", "y_columns": ["Umsatz"],
            "stacked": false,   // nur bar
            "curved": true }    // nur line
```

**`pie`**:
```jsonc
"config": { "width": 4, "label_column": "Land", "value_column": "Umsatz", "donut": true }
```

**`table`** (zeigt alle Spalten der Ergebnismenge):
```jsonc
"config": { "width": 12 }
```

> Feldnamen unbedingt beachten: KPI nutzt `column`, Bar/Line `x_column` + `y_columns` (Array!),
> Pie `label_column` + `value_column`. Die Spaltennamen sind die **SELECT-Aliase** des Mappings.

### 5.3 Drilldown (optional)

Klick auf einen Balken/Punkt/Kuchenstück → Detail-Mapping ausführen. In der Widget-`config`:
```jsonc
"drilldown": { "type": "mapping", "mapping_id": 42, "param": "artnr" }
```
Der geklickte Wert (bar/line `x_column`, pie `label_column`) wird als SQL-Parameter `:param` an das
Mapping übergeben (`... WHERE cArtNr = :artnr`). Endpoint: `POST /api/forms/drilldown` (führt das
Mapping ohne Ziel-Write aus). `mapping_id` ist hier die **echte** Integer-ID – am einfachsten nach
der Installation im Editor setzen.

---

## 6. Minimalbeispiel (kopierbar, ein KPI + ein Balken)

```json
{
  "template_id": "beispiel_umsatz",
  "template_name": "Beispiel – Umsatz",
  "description": "Minimales funktionierendes Dashboard-Formular",
  "category": "jtl-reporting",
  "version": "1.0",
  "author": "Du",
  "hinweise": ["JTL-Verbindung wählen, dann im Formular die Auswerten-Buttons klicken."],
  "config_required": [
    { "key": "connection_jtl", "label": "JTL-Datenbankverbindung", "type": "connection", "default": "" },
    { "key": "monate", "label": "Zeitraum in Monaten", "type": "text", "default": "12" }
  ],
  "datasets": [],
  "pipelines": [],
  "mappings": [
    {
      "id": "mapping_kpi", "name": "Gesamtumsatz",
      "canvas_nodes": [], "joins": [],
      "sql_nodes": [{ "id": "sql1", "x": 120, "y": 40, "width": 350, "height": 244, "connection_id": "{{connection_jtl}}", "mode": "transform", "output_field": "sql_1", "output_fields": ["Umsatz"],
        "sql": "SELECT CAST(SUM(REPO.fAnzahl*REPO.fVkNetto) AS DECIMAL(18,2)) AS Umsatz FROM Rechnung.vRechnung RE JOIN Rechnung.tRechnungPosition REPO ON RE.kRechnung = REPO.kRechnung WHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date))" }],
      "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
      "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
      "targets": [{ "id": "t1", "name": "Gesamtumsatz", "target_type": "dataset",
        "target_connection_id": null, "target_table": "", "target_write_mode": "replace", "target_options": {},
        "fields": [{ "source_field": "Umsatz", "target_field": "Umsatz", "target_type": "float",
          "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Umsatz" } }] }]
    },
    {
      "id": "mapping_top", "name": "Top Kunden",
      "canvas_nodes": [], "joins": [],
      "sql_nodes": [{ "id": "sql1", "x": 120, "y": 40, "width": 350, "height": 244, "connection_id": "{{connection_jtl}}", "mode": "transform", "output_field": "sql_1", "output_fields": ["Kunde", "Umsatz"],
        "sql": "SELECT TOP 10 RE.cFirma AS Kunde, CAST(SUM(REPO.fAnzahl*REPO.fVkNetto) AS DECIMAL(18,2)) AS Umsatz FROM Rechnung.vRechnung RE JOIN Rechnung.tRechnungPosition REPO ON RE.kRechnung = REPO.kRechnung WHERE RE.dErstellt >= DATEADD(MONTH, -{{monate}}, CAST(GETDATE() AS date)) GROUP BY RE.cFirma ORDER BY Umsatz DESC" }],
      "agg_nodes": [], "transform_nodes": [], "constant_nodes": [], "rest_nodes": [],
      "lookup_nodes": [], "calc_nodes": [], "switch_nodes": [], "sort_nodes": [],
      "targets": [{ "id": "t1", "name": "Top Kunden", "target_type": "dataset",
        "target_connection_id": null, "target_table": "", "target_write_mode": "replace", "target_options": {},
        "fields": [
          { "source_field": "Kunde", "target_field": "Kunde", "target_type": "string",
            "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Kunde" } },
          { "source_field": "Umsatz", "target_field": "Umsatz", "target_type": "float",
            "source_dataset_id": "__sql__sql1", "transformer": { "type": "direct", "source_field": "Umsatz" } }
        ] }]
    }
  ],
  "forms": [
    {
      "name": "Beispiel Umsatz",
      "portal_config": {},
      "schema": {
        "fields": [], "layout": [],
        "actions": [
          { "id": "act_kpi", "type": "run_mapping", "mapping_id": "mapping_kpi", "pipeline_id": null, "label": "Umsatz" },
          { "id": "act_top", "type": "run_mapping", "mapping_id": "mapping_top", "pipeline_id": null, "label": "Top Kunden" }
        ],
        "widgets": [
          { "id": "w_kpi", "type": "kpi", "label": "Gesamtumsatz", "action_id": "act_kpi",
            "config": { "width": 4, "column": "Umsatz", "aggregation": "first", "prefix": "€ ", "decimals": 2 } },
          { "id": "w_bar", "type": "bar", "label": "Top Kunden", "action_id": "act_top",
            "config": { "width": 8, "x_column": "Kunde", "y_columns": ["Umsatz"], "stacked": false } }
        ]
      }
    }
  ]
}
```

---

## 7. Checkliste

- [ ] `template_id` eindeutig; **kein** `reports`-Schlüssel
- [ ] DB-Verbindung als `config_required` `type:"connection"` mit `connection_`-Präfix
- [ ] Je Widget-Datenmenge ein Mapping mit **aggregiertem** SQL (KPIs: 1-Zeilen-`SUM`/`COUNT`; Charts: `GROUP BY`)
- [ ] **Jeder SQL-Node hat `"mode": "transform"`** (sonst kommt das Mapping leer zurück)
- [ ] Jedes Mapping: `sql_nodes[0].connection_id = "{{connection_jtl}}"`, jede SELECT-Spalte als `fields`-Eintrag mit `source_dataset_id: "__sql__sql1"`
- [ ] Jede Action `type:"run_mapping"` referenziert eine **Mapping-Template-ID** als `mapping_id`
- [ ] Jedes Widget hat ein gültiges `action_id`; Config-Feldnamen exakt (`column` / `x_column`+`y_columns` / `label_column`+`value_column`)
- [ ] Spaltennamen in Widgets = SELECT-Aliase der Mappings
- [ ] `config.width` je Zeile summiert auf 12
- [ ] Zeitraum über `{{monate}}` parametrisiert, nicht hartkodiert

> **Häufigster Fehler:** KPI/Chart summiert clientseitig über eine unaggregierte Query → falsche
> Werte oder leer. Immer im SQL aggregieren (§0).

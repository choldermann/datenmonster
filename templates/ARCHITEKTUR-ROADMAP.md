# Datenmonster – Architektur-Roadmap: von Templates zur BI-Plattform

Dieses Dokument entwirft die Weiterentwicklung des Template-Systems zu einer BI-Plattform
(Collections, Marketplace, Versionierung, Abhängigkeiten, Preflight, Demo-Modus, SQL-Assist,
KI-Generierung, Meta-Templates, Health Checks).

**Leitprinzipien (nicht verhandelbar):**
1. **Additiv & optional.** Jede Neuerung ist ein *optionaler* Schlüssel. Ein heutiges Template ohne
   die neuen Felder installiert unverändert weiter. Rückwärtskompatibilität > alles.
2. **Das Template bleibt reines JSON.** Kein Code im Template. Neue Fähigkeiten = deklarative
   Metadaten, die *Services* interpretieren.
3. **Ein Format, viele Erzeuger.** Assistent und KI erzeugen dasselbe Template-JSON, das der normale
   Installer verarbeitet. So kann kein Erzeuger die Runtime brechen.
4. **Vorhandenes wiederverwenden** statt parallel neu bauen (Lizenz-/Plugin-System für Marketplace,
   `ai_service` für KI).

---

## 0. Ausgangslage (Ist-Stand, unverändert erhalten)

Ein Template ist ein JSON mit: `template_id`, `template_name`, `description`, `category`, `version`,
`author`, `config_required`, `datasets`, `mappings`, `pipelines`, `forms`. Der Installer löst
`{{platzhalter}}` + `{{connection_X}}` auf, legt die Objekte im Projekt an und protokolliert die
erzeugten IDs (`Template.installations`). Dashboards = Formulare mit Actions (`run_mapping`) +
Widgets; Daten kommen aus `mode:"transform"`-SQL-Nodes ([[reference_mapping_sql_source]]).

Diese Struktur wird **nicht** verändert – nur erweitert.

---

## 1. Schichtenmodell

Alles Neue ordnet sich in Schichten, die *aufeinander* aufbauen, aber einzeln nutzbar sind:

```
7  Meta-Templates / Semantische Schicht   (Cross-ERP – LETZTE Priorität)
6  KI-Generierung + Dashboard-Assistent   (Erzeuger von Template-JSON)
5  SQL-Intelligenz (Validierung, Vorschläge)  (Editor-Tooling)
4  Demo-Modus                             (Daten ohne DB)
3  Preflight / Installationsprüfung       (DB-Kompatibilität vor Install)
2  Collections + Dependencies             (Bündel + Reihenfolge)
1  Template-Envelope (requires, version, depends_on)  (deklarative Metadaten)
0  Template (heute)                       (unverändert)
```

Schichten 1–3 sind billig, additiv und hoch-wertvoll. Schicht 7 ist teuer und riskant – bewusst
zuletzt.

---

## 2. Schicht 1 – Template-Envelope (optionale Metadaten)

Ein optionaler Block `requires` + die schon vorhandenen `version`/`depends_on` machen Versionierung,
Abhängigkeiten und Preflight möglich – **ohne** Änderung an mappings/forms.

```jsonc
{
  "template_id": "jtl_vertrieb",
  "version": "1.2.0",                 // SemVer, existiert bereits
  "depends_on": [                     // NEU, optional
    { "template_id": "jtl_core", "version": ">=1.0.0" }
  ],
  "requires": {                       // NEU, optional – Grundlage für Preflight (§4)
    "database": "jtl",                // logischer DB-Typ
    "db_version": ">=1.10",           // Versionsbereich (SemVer-Range)
    "tables":  ["Rechnung.vRechnung", "Rechnung.tRechnungPosition"],
    "columns": { "Rechnung.vRechnung": ["kRechnung", "dErstellt", "cLandISO"] },
    "privileges": ["SELECT"]
  }
  // ... datasets/mappings/forms wie bisher
}
```

- `depends_on`: gerichteter Graph; der Installer installiert in **topologischer Reihenfolge** und
  teilt `config_required` (z. B. dieselbe `connection_jtl`) über alle Mitglieder.
- `requires`: rein deklarativ. Wird von Preflight (§4) gelesen. Fehlt der Block → keine Prüfung
  (heutiges Verhalten).

> **Kritisch:** `db_version` NICHT hart pro JTL-Version pflegen (1.10/1.11/1.12 als separate
> Templates = Wartungshölle). Stattdessen **Versionsbereiche** + Preflight, der das *tatsächliche*
> Schema prüft. Ein Template deckt eine Spanne ab; nur bei echtem Schema-Bruch eine zweite Variante.

---

## 3. Schicht 2 – Collections (neues Artefakt, KEIN Template-Schema-Umbau)

Eine Collection ist ein **eigenes kleines Manifest**, das Templates per ID referenziert – Templates
selbst wissen nichts von Collections (lose Kopplung).

```jsonc
{
  "collection_id": "jtl_reporting",
  "name": "JTL Reporting Collection",
  "database": "jtl",
  "version": "1.0.0",
  "shared_config": ["connection_jtl"],      // 1× abfragen, an alle Member geben
  "members": [
    { "template_id": "jtl_core",        "required": true },
    { "template_id": "jtl_geschaeftsfuehrer" },
    { "template_id": "jtl_vertrieb" },
    { "template_id": "jtl_lager" },
    { "template_id": "jtl_health_checks" }
  ]
}
```

„Ein-Klick-Install" = Collection installieren → Installer löst `depends_on` auf, fragt `shared_config`
**einmal** ab, installiert alle Member. Backend: neuer Endpoint `POST /api/collections/install` +
`Collection`-Modell. Template-Installer wird wiederverwendet, nicht dupliziert.

---

## 4. Schicht 3 – Preflight / Installationsprüfung (hoher USP, geringes Risiko)

Vor dem Install ein **read-only Introspektionslauf** gegen die gewählte Verbindung, der `requires`
gegen die reale DB prüft: Tabellen/Views (`INFORMATION_SCHEMA`), Spalten, Datentypen, Rechte,
DB-Version. Ergebnis = Kompatibilitätsmatrix (grün/gelb/rot) mit konkreter Meldung
(„Spalte `tArtikel.fEKNetto` fehlt – Template braucht sie für den Bestandswert").

Das adressiert direkt den häufigsten Fehlermodus (leere Widgets durch Schema-Abweichung) und ist
technisch simpel (nur Katalog-Queries + Vergleich). **Empfehlung: gleich nach dem Fundament-Test
bauen** – es macht jedes weitere Template robuster und ist Voraussetzung für den Marketplace
(Käufer sieht vor dem Kauf, ob es zu seiner DB passt).

---

## 5. Schicht 4 – Demo-Modus (Daten ohne DB)

Jeder SQL-Node/jedes Mapping bekommt optional eingebettete Beispieldaten:

```jsonc
"sql_nodes": [{
  "id": "sql1", "mode": "transform", "connection_id": "{{connection_jtl}}",
  "sql": "SELECT ...",
  "demo_rows": [                       // NEU, optional
    { "Kunde": "Muster GmbH", "Umsatz": 12500.00 },
    { "Kunde": "Beispiel AG",  "Umsatz":  9800.00 }
  ]
}]
```

Wird ein Template im **Demo-Modus** installiert (oder ist keine Verbindung gewählt), liefert die
`run_mapping`-Action die `demo_rows` statt SQL auszuführen. Ein Schalter in `_execute_form`
(„demo → SQL überspringen, demo_rows zurückgeben"). Rückwärtskompatibel: ohne `demo_rows` verhält
sich alles wie heute. Ermöglicht Marketplace-Vorschauen, Onboarding und Screenshots.

---

## 6. Schicht 5 – SQL-Intelligenz (Editor-Tooling, keine Runtime-Änderung)

Baut auf `output_fields` (jeder Node kennt seine Rückgabefelder). Optional `output_types` ergänzen
(aus einem Sample-Run ableitbar). Damit:

- **Widget-Vorschläge (Heuristik, keine KI nötig):** 1 Zeile × 1 Zahl → KPI; Kategorie + Zahl → Bar;
  Datum/Monat + Zahl → Line; Kategorie + Anteil → Pie; viele Spalten → Tabelle.
- **Feld-/Typprüfung:** Widget-`config` (z. B. `value_column`) gegen `output_fields` validieren →
  Warnung „Spalte gibt es nicht" schon im Editor (fängt genau den stillen Leer-Bug ab).
- **SQL-Validierung/Autocomplete:** braucht eine Verbindung → über Preflight-Introspektion
  (Tabellen-/Spaltenkatalog) speisen.

Das ist reine Editor-Ergonomie; Templates und Runtime bleiben unberührt.

---

## 7. Schicht 6 – KI-Generierung + Assistent (Erzeuger, keine neue Runtime)

**Zentrale Einsicht:** KI und Assistent sind **Produzenten des bestehenden Template-JSON**, kein
neues Ausführungssystem. „Zeige Top 20 Kunden 3 Jahre" → LLM erzeugt ein Template (Mapping mit
`mode:transform`-SQL + Action + Widget) → normaler Installer + Preflight. Dadurch:

- Kein Sonder-Runtime, kein Kompatibilitätsrisiko.
- Preflight validiert die KI-SQL gegen die echte DB, bevor irgendwas läuft.
- Nutzt `ai_service`/Ollama ([[ai_integration_plan]]) + `output_fields` für Struktur.

**Assistent** (DB → Software → Bereich → Diagramme → Dashboard) = geführter Wizard, der dieselben
Bausteine zusammensetzt – im einfachsten Fall aus einem Katalog vorgefertigter Mapping-/Widget-
Snippets, im Ausbau KI-gestützt.

---

## 8. Schicht 7 – Meta-Templates / semantische Schicht (LETZTE Priorität – kritisch hinterfragt)

Die Idee „Template beschreibt nur *Kunde/Umsatz/Datum*, System findet Tabellen selbst" ist die
**schwierigste und am wenigsten dringende** der ganzen Liste:

- Zahlt sich nur bei **mehreren ERPs** aus – ihr habt genau eines (JTL).
- KI-basiertes Schema-Matching ist fehleranfällig und schwer testbar (Korrektheit bei Geld/Umsatz
  ist kritisch).

**Empfehlung – pragmatischer Mittelweg statt KI-Magie:** eine **semantische Feld-Bibliothek pro
Datenbank**. Für JTL einmal von Hand gepflegt:

```jsonc
// semantics/jtl.json  – kanonisches Konzept → JTL-SQL-Fragment
{ "umsatz": "SUM(REPO.fAnzahl * REPO.fVkNetto)",
  "kunde":  "ISNULL(RE.cFirma, RE.cName)",
  "datum":  "RE.dErstellt" }
```

Ein Meta-Template referenziert Konzepte (`{{sem:umsatz}}`), ein Resolver setzt die DB-spezifischen
Fragmente ein. Deterministisch, testbar, degradiert sauber (heute nur JTL, später Lexware/SAP als
weitere Wörterbücher). **Wichtig: diese Schicht darf das heutige Schema NICHT jetzt formen** – erst
angehen, wenn ein zweites ERP real ansteht. Sonst optimierst du für einen Fall, den es nicht gibt.

---

## 9. Marketplace – vorhandene Infrastruktur nutzen

Der Marketplace ist primär **Distribution + Lizenzierung + Signierung**, nicht Template-Format. Das
Lizenz-/Auslieferungssystem existiert bereits (monstersuite, Plugin-Distribution
[[plugin_distribution]]). Template-seitig genügt: der Envelope (§2) + eine Signatur/Checksumme +
`author`/`version`. Also **andocken statt neu bauen**. Erst relevant, wenn genug eigene Templates
stehen (Henne-Ei: Marketplace ohne Inhalte ist leer).

---

## 10. Kritische Priorisierung & Roadmap

**Reihenfolge nach (Wert ÷ Risiko), nicht nach Reihenfolge im Wunschzettel:**

| Phase | Inhalt | Warum jetzt / später |
|---|---|---|
| **0** | Fundament-Test (3 Templates gegen echte JTL) + Laufzeit-Primitive (Zeitraum/Filter/Drilldown) | Blockiert alles. Ohne Daten kein Sinn. |
| **1** | Envelope (`requires`, `depends_on`) + **Preflight** | Billig, additiv, adressiert den Haupt-Fehlermodus, Basis für Versionierung/Marketplace. |
| **2** | **Collections** + Dependency-Install | Kern deiner Vision, geringes Risiko, reiner Installer-Aufsatz. |
| **3** | **Demo-Modus** | Enttoppelt von DB, ermöglicht Onboarding/Vorschau/Marketplace. |
| **4** | SQL-Intelligenz (Widget-Vorschläge, Feldprüfung) | Editor-Ergonomie, kein Runtime-Risiko. |
| **5** | Health-Check-Kategorie + Ampel-Widget | Hoher USP, passt auf heutige Architektur. |
| **6** | KI-Generierung + Assistent | Erzeugt Template-JSON, nutzt `ai_service` + Preflight. |
| **7** | Meta-Templates / Cross-ERP | Nur wenn 2. ERP real; als semantisches Wörterbuch, nicht KI-Matching. |

**Bewusst zurückgestellt / hinterfragt:**
- Cross-ERP-Abstraktion jetzt: **nein** (nur JTL vorhanden – YAGNI, würde das Schema verbiegen).
- Pro-JTL-Version je ein Template: **nein** (Versionsbereiche + Preflight statt Kombinatorik).
- Marketplace vor Inhalten: **nein** (erst Templates, dann Schaufenster).
- Neues KI-Runtime: **nein** (KI erzeugt bestehendes Format).

---

## 11. Rückwärtskompatibilitäts-Garantien

- Alle neuen Felder (`requires`, `depends_on`, `demo_rows`, `output_types`) sind **optional**; Fehlen =
  heutiges Verhalten.
- Collections/Preflight/Demo sind **zusätzliche** Endpoints/Services; der bestehende
  `POST /api/templates/install` bleibt unverändert.
- Keine Umbenennung/Entfernung bestehender Schlüssel. Erweiterungen werden hier + in
  `TEMPLATE-AUFBAU.md` dokumentiert.

Verwandt: [[idea_jtl_reporting_collection]], [[reference_mapping_sql_source]],
[[plugin_distribution]], [[ai_integration_plan]].

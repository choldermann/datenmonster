# Datenmonster Part 10 – Session-Dokumentation

## Transcript
- Part10: (diese Session)
- Part9: /mnt/transcripts/2026-04-04-... (siehe Part 9 Doku)

---

## Was in dieser Session umgesetzt wurde

### 1. Primary Key + Autoincrement (Backend)

**`backend/app/api/datasets.py`**

- `DatasetColumnDef` um `is_primary: bool` und `autoincrement: bool` erweitert
- `create_dataset_manual` speichert `is_primary`/`autoincrement` in `column_types`
- `save_rows` Endpoint: Autoincrement-Felder werden automatisch mit `MAX+1` befüllt; bestehende `is_primary`/`autoincrement` Flags werden bei Typ-Inferenz nicht überschrieben
- Neuer Endpoint `PUT /{dataset_id}/column_types` – speichert vollständige Struktur inkl. `is_primary`/`autoincrement` (der bestehende `PATCH` bleibt für einfache Typ-Änderungen)

**Datenstruktur `column_types`:**
```json
{
  "id": { "type": "integer", "raw": "int64", "is_primary": true, "autoincrement": true },
  "name": { "type": "string", "raw": "object", "is_primary": false, "autoincrement": false }
}
```

### 2. Upsert-Modus im Mapping-Service

**`backend/app/services/mapping_service.py`** – `_write_target()` Dataset-Zweig:

- `replace` – wie bisher, Dataset wird komplett ersetzt
- `append` – Autoincrement-Felder werden auch beim Anhängen korrekt befüllt (MAX+1)
- `upsert` (neu) – liest `is_primary`-Felder aus `column_types`, vergleicht Keys → UPDATE wenn Key existiert, INSERT sonst
- `column_types` werden beim Schreiben nicht mehr blind überschrieben – `is_primary`/`autoincrement` bleiben erhalten

**Upsert-Logik:**
```python
# Key-Felder = is_primary=True, autoincrement=False
existing_by_key[key] = row  # überschreibt oder fügt hinzu
```

### 3. DB-Schema mit Primary Keys + Typen

**`backend/app/api/connections.py`** – `/columns` Endpoint erweitert:

- Gibt jetzt zusätzlich `column_details` zurück: `[{ name, type, raw, is_primary, nullable }]`
- Primary Keys werden per SQLAlchemy Inspector (`get_pk_constraint`) ermittelt
- Typ-Mapping: SQLAlchemy-Typen → `integer / decimal / date / boolean / string`
- Rückwärtskompatibel: `columns` (nur Namen) bleibt erhalten

```json
{
  "columns": ["id", "name"],
  "column_details": [
    { "name": "id", "type": "integer", "raw": "INTEGER", "is_primary": true, "nullable": false },
    { "name": "name", "type": "string", "raw": "VARCHAR(255)", "is_primary": false, "nullable": true }
  ]
}
```

### 4. Frontend – EditDatasetModal (neu)

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`**

- Komplett überarbeitet mit zwei Tabs: "Name" und "Spalten & Schlüssel"
- Tab "Spalten & Schlüssel": jede Spalte mit Typ-Dropdown, 🔑-Button zum Toggle als Primary Key, Autoincrement-Checkbox (nur bei `is_primary=true` + Typ Ganzzahl)
- Speichert via `PUT /api/datasets/{id}/column_types`
- `Dashboard.jsx`: Pencil-Button öffnet jetzt immer `EditDatasetModal` (auch für `static` Datasets)

### 5. Frontend – ManualDatasetModal (erweitert)

- 🔑-Button pro Spalte (toggle `is_primary`)
- Autoincrement-Checkbox erscheint kontextabhängig (nur Integer + is_primary)
- `is_primary=false` → `autoincrement` wird automatisch zurückgesetzt
- Typ-Wechsel weg von Integer → `autoincrement` wird zurückgesetzt

### 6. Mapping Editor – Quell-Nodes (DatasetNode)

**`frontend/src/components/mapping/DatasetNode.jsx`**

- 🔑 Symbol vor Feldnamen bei `is_primary=true` – als fester 14px-Slot (bündige Ausrichtung)
- Verbindungspunkt links vom Typ-Badge: **grau** = nicht verbunden, **orange** = Join-Verbindung
- Rechter Kreis: **gold leuchtend** = Feld gemappt, **grau** = nicht verbunden, **gelb leuchtend** = Pending-Select

### 7. Mapping Editor – Zielfeld-Liste (MappingEditor)

**`frontend/src/pages/MappingEditor.jsx`**

- Neuer State `targetColumnTypes` – wird aus `activeTarget.target_column_types` gelesen
- Zielfeld-Zeilen zeigen feste Slots: `[🔑 16px] [TYP 28px] [Feldname flex]`
- Typ-Badge (INT/STR/DEC/DAT/BOL) aus DB-Schema oder Dataset `column_types`
- Transformer-Editor aus Zielfeldern entfernt (kein Aufklappen mehr bei Klick)
- Kein `isEditing`-State mehr für Zielfelder

### 8. Mapping Editor – Feld-Picker (Modals)

**`frontend/src/components/mapping/Modals.jsx`**

- `FieldPickerModal` lädt `column_details` vom Backend
- Pro Spalte: 🔑 Symbol + Typ-Badge sichtbar
- `handleFieldPickerConfirm` speichert `target_column_types` direkt im Target-Objekt
- `target_column_types` wird beim Speichern des Mappings mit persistiert

### 9. Mapping Editor – Upsert write_mode

**`frontend/src/components/mapping/Modals.jsx`**

- Dritte Option in der Schreibmodus-Auswahl: "Upsert" (neben Überschreiben + Anfügen)
- Beschreibung: "Update wenn Primary Key existiert, sonst Insert"

### 10. DataExplorer – 🔑 in Spaltenüberschrift

**`frontend/src/components/dashboard/panels/DatasetsPanel.jsx`**

- 🔑 Symbol links vom Spaltennamen in der Tabellenüberschrift wenn `is_primary=true`

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/app/api/datasets.py` | `is_primary`/`autoincrement`, `save_rows` Autoincrement, `PUT /column_types` |
| `backend/app/api/connections.py` | `/columns` liefert `column_details` mit Typen + PKs |
| `backend/app/services/mapping_service.py` | Upsert-Logik, Autoincrement beim Append, column_types nicht überschreiben |
| `frontend/src/components/dashboard/panels/DatasetsPanel.jsx` | EditDatasetModal neu, ManualDatasetModal erweitert, DataExplorer 🔑 |
| `frontend/src/pages/Dashboard.jsx` | Pencil öffnet immer EditDatasetModal |
| `frontend/src/pages/MappingEditor.jsx` | targetColumnTypes, feste Slots, Transformer-Editor entfernt |
| `frontend/src/components/mapping/DatasetNode.jsx` | 🔑 Slot, Verbindungspunkte überarbeitet |
| `frontend/src/components/mapping/Modals.jsx` | FieldPicker mit 🔑+Typ, target_column_types speichern, Upsert-Option |

---

## Deployment-Cheatsheet

```bash
# Backend-Dateien
docker cp datasets.py datenmonster-backend:/app/app/api/datasets.py
docker cp connections.py datenmonster-backend:/app/app/api/connections.py
docker cp mapping_service.py datenmonster-backend:/app/app/services/mapping_service.py

# Frontend-Dateien (Vite HMR, kein Neustart nötig)
cp DatasetsPanel.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/components/dashboard/panels/DatasetsPanel.jsx
cp Dashboard.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/pages/Dashboard.jsx
cp MappingEditor.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/pages/MappingEditor.jsx
cp DatasetNode.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/components/mapping/DatasetNode.jsx
cp Modals.jsx ~/Nextcloud/Documents/Datenmonster/frontend/src/components/mapping/Modals.jsx

# Logs prüfen
docker compose logs backend --tail=10
```

---

## Nächste Features (Part 11+)

### Phase 1 – Stabilität & schnelle Wins
- ⬜ SFTP mit Wildcard-Import (filename_filter existiert bereits)
- ⬜ Installer Script

### Phase 2 – Neue Features
- ⬜ Benachrichtigungen (Mail, WhatsApp, Telegram)
- ⬜ PDF Tabellen auslesen
- ⬜ Google Sheets Connector
- ⬜ IMAP / E-Mail Quelle
- ⬜ Webscraping
- ⬜ WooCommerce Connector
- ⬜ Lexoffice / sevDesk Connector
- ⬜ DATEV-Export

### Phase 3 – Wachstum
- ⬜ Dokumentation & Online-Handbuch
- ⬜ Lizenzkey-System
- ⬜ YouTube Videoserie
- ⬜ JTL Technologiepartnerschaft

---

## Wichtige Hinweise für Part 11

- `target_column_types` wird erst befüllt wenn der Feld-Picker einmal neu geöffnet wird (DB-Targets). Bestehende Mappings müssen einmal die Felder neu auswählen.
- `mapping_service.py` ist ~90KB – vor Änderungen vollständig lesen!
- Autoincrement greift nur bei `save_rows` (manueller Zeileneditor). Im Mapping-Service beim Append ebenfalls implementiert.
- Immer `db_logger` für neue Features verwenden.
- Deployment: Dateien mit root-Owner → `sudo chown $USER` nötig bei direktem Schreiben ins Projektverzeichnis.

# monstersuite Plugin-Auslieferungs-API (Vertrag)

Dieser Vertrag beschreibt die **serverseitigen** Endpunkte, die auf
`monstersuite.de` implementiert werden müssen, damit Datenmonster-Instanzen
kostenpflichtige Tier-2-Plugins (z.B. `estatistik-core`) **lizenzgeprüft**
herunterladen können ("Variante 2": `docker save`-Tarball → `docker load`).

Die **Client-Seite** (Datenmonster Backend + Plugin-Manager + Plugins-Panel) ist
bereits umgesetzt:
- `GET  /api/plugins/store` (Backend) ruft `POST /api/v1/plugins/catalog` auf.
- `POST /api/plugins/tier2/{id}/install` (Backend) ruft `POST /api/v1/plugins/download`
  auf, streamt das Tarball an den Plugin-Manager (`POST /plugins/{id}/load-image` →
  `docker load`) und registriert das Plugin.

Auth-Modell: **Lizenz-als-Credential**, kein Customer-Login (identisch zu
`/api/v1/licenses/*`). Der Lizenzschlüssel im Request ist das Zugriffstoken.

---

## 1. `POST /api/v1/plugins/catalog`

Liefert die für die Lizenz freigeschalteten, installierbaren Tier-2-Plugins mit
vollständigem Manifest.

**Request** (JSON):
```json
{
  "license_key": "DM-XXXX-...",
  "email": "kunde@example.de",
  "machine_id": "<sha256[:32]>",
  "hostname": "kundenserver",
  "product": "datenmonster",
  "version": "1.2.3"
}
```

**Prüfung** (analog `_resolve` in `monstersuite/backend/routers/api_v1.py`):
- Lizenz gültig, nicht suspended/expired.
- `product`-Slug der Lizenz == `datenmonster`.
- Feature `plugin_tier2` in den Plan-Features (`_features(lic, db)`), ODER ein
  per-Plugin-Entitlement (siehe unten).

**Response 200** (JSON) — Liste ODER `{ "plugins": [...] }`; der Client normalisiert beides:
```json
{
  "plugins": [
    {
      "id": "estatistik-core",
      "name": "eSTATISTIK.core / Intrastat",
      "version": "0.1.0",
      "docker_image": "dm-plugin-estatistik:0.1.0",
      "description": "...",
      "author": "Holdermann IT",
      "license": "professional",
      "capabilities": ["target"],
      "config_schema": [ /* wie im Plugin-manifest.json */ ],
      "source_type_id": "", "source_type_label": "", "source_type_icon": "container",
      "target_type_id": "estatistik_intrastat", "target_type_label": "eSTATISTIK Intrastat"
    }
  ]
}
```
Das Manifest muss **1:1** den Feldern von `Tier2RegisterBody`
(`backend/app/api/plugins.py`) entsprechen — der Client registriert damit das Plugin.

**Wichtig:** `docker_image` **muss** dem Image-Tag im ausgelieferten Tarball
(Endpunkt 2) entsprechen, sonst findet der Plugin-Manager das geladene Image nicht.

**Fehler:** `{ "error": "invalid_key|expired|wrong_product|not_entitled", "message": "..." }`
mit passendem HTTP-Status (401/402/403). Bei fehlender Berechtigung liefert der Client
eine leere Liste bzw. den Upgrade-Hinweis.

---

## 2. `POST /api/v1/plugins/download`

Streamt das `docker save`-Tarball des Plugin-Images.

**Request** (JSON): wie Endpunkt 1, zusätzlich `"plugin_id": "estatistik-core"`.

**Prüfung:** identisch zu Endpunkt 1 + das Plugin muss für diese Lizenz freigeschaltet sein.

**Response 200:** binärer Stream des Tarballs.
- `Content-Type: application/gzip` (das Tarball ist `docker save … | gzip`).
- `Content-Disposition: attachment; filename="estatistik-core-0.1.0.tar.gz"`.
- Optional `X-Plugin-Version: 0.1.0`.
- Der Client streamt den Body 1:1 in eine Temp-Datei und reicht ihn an den
  Plugin-Manager weiter (`docker load` akzeptiert gzip-komprimierte Tarballs).

**Fehler:** `402`/`403` mit JSON `{ "error": "...", "message": "..." }` (nicht berechtigt),
`404` (Plugin/Version nicht im Storage). Der Client reicht Status + Text durch.

---

## Storage-Ingestion (woher monstersuite die Tarballs bekommt)

Das Image wird in der **Datenmonster-CI** gebaut (`.github/workflows/…`), per
`docker save <image> | gzip` in ein versioniertes Tarball gepackt und als
Release-Artefakt bereitgestellt. monstersuite muss dieses Tarball in seinen Storage
übernehmen — empfohlen:

- Storage-Layout `plugins/<plugin_id>/<version>/image.tar.gz` (z.B. lokales Volume
  oder Objektspeicher).
- Ein Datenmodell `PluginArtifact(product_id, plugin_id, version, file_path,
  manifest_json, min_plan/feature)` in `monstersuite/backend/models.py`, plus ein
  Admin-Upload (oder ein CI-Push-Endpunkt mit Admin-Token) zum Befüllen.
- Der Katalog-Endpunkt liest die Manifeste aus `PluginArtifact.manifest_json`
  (die neueste Version je Plugin), der Download-Endpunkt streamt `file_path`.

## Entitlement-Optionen

- **Grob:** Feature `plugin_tier2` schaltet alle Tier-2-Plugins frei (einfachster Start).
- **Fein:** per-Plugin-Feature (z.B. `plugin_estatistik`) in `ProductFeature`/`ProductPlan`,
  das der Katalog/Download individuell prüft. Empfohlen, sobald es mehrere Paid-Plugins gibt.

## Test / Referenz

Für lokale Tests der Client-Seite existiert ein Mock (Wegwerf-FastAPI), der
`/api/v1/plugins/catalog` (Manifest von estatistik-core) und `/api/v1/plugins/download`
(lokal per `docker save` erzeugtes Tarball) ohne echte Lizenzprüfung bedient und über
`LICENSE_SERVER_URL` angebunden wird.

# monstersuite Template-Auslieferungs-API (Vertrag)

Beschreibt die Endpunkte auf `monstersuite.de`, über die Datenmonster-Instanzen
**gekaufte Templates** lizenzgeprüft in ihren Katalog holen (In-App-Template-Store).
Analog zum Plugin-Vertrag (`monstersuite-plugin-api.md`), aber mit einem anderen
Berechtigungsmodell: nicht Lizenz-*Feature*, sondern **Kauf des Shop-Produkts**.

Beide Seiten sind umgesetzt (Stand 2026-08-10).

## Rollenverteilung

| Objekt | Wo | Bedeutung |
|---|---|---|
| `ShopTemplate` | monstersuite | Das **verkaufte Produkt**: Name, Preis, Beschreibung, Landingpage |
| `TemplateArtifact` | monstersuite | Die **auslieferbare Datei** (Template-JSON) + wer sie freischaltet |
| `Template` | Datenmonster | Das lokal installierbare Template im Katalog der Instanz |

Ein Bundle-Produkt ist kein Sonderfall: Es ist ein `ShopTemplate`, dessen Slug
bei mehreren Artefakten in `shop_slugs` steht.

## Auth-Modell

Wie bei `/api/v1/plugins/*` und `/api/v1/licenses/*`: **die Lizenz ist das Credential**,
kein Customer-Login. Body-Felder: `license_key`, `email`, `machine_id`, `hostname`,
`product`, `version` (Datenmonster: `license_auth_body()` in `backend/app/api/license.py`).
Beide Pfade stehen in `AUTH_EXCLUDED` (`main.py`).

Berechtigt ist ein Template, wenn **eine** der Bedingungen gilt:

1. `is_free = true` → jede gültige Lizenz,
2. `min_feature` ist im Feature-Set der Lizenz (wie bei Plugins),
3. der **Kunde hinter der Lizenz** hat ein Shop-Produkt erworben, dessen Slug in
   `shop_slugs` steht. Als Erwerb zählen:
   - `Purchase` mit `status = completed` (PayPal-Einmalkauf),
   - `Subscription` mit `status = active`,
   - `OrderRequest` mit `status = paid` (manuelle Rechnung),
   - `OrderRequest` mit `status = pending`, **solange die zugehörige Testlizenz
     gültig ist** (14-Tage-Test). Läuft sie ab, endet die Berechtigung.

Ohne gültige Lizenz ist **nichts** berechtigt — auch kein `is_free`-Template, sonst
verspräche der Katalog einen Download, den `/download` mit 401 abweist.

## `POST /api/v1/templates/catalog`

Liefert **alle** veröffentlichten Templates, jeweils mit `entitled`. Bewusst nicht
nur die berechtigten: der Client soll auch zeigen können, was noch zu kaufen wäre.
Eine ungültige Lizenz ist kein 4xx, sondern `error` im Body (der Katalog bleibt sichtbar).

```json
{
  "templates": [
    {
      "template_id": "jtl_gf_cockpit",
      "name": "JTL Geschäftsführer-Cockpit",
      "description": "…", "category": "jtl", "version": "1.0",
      "entitled": true, "is_free": false,
      "offers": [{"slug": "jtl-gf-cockpit", "name": "GF-Cockpit",
                  "price_yearly": 199.0, "price": 0.0}]
    }
  ],
  "error": "invalid_key", "message": "…"
}
```

## `POST /api/v1/templates/download`

Body zusätzlich: `template_id`. Antwort ist die Template-JSON
(`Content-Type: application/json`, Header `X-Template-Version`).

| Status | Bedeutung |
|---|---|
| 200 | Datei folgt |
| 400 | `template_id` fehlt |
| 401 | Lizenz ungültig / gesperrt / abgelaufen |
| 402 | Lizenz gültig, aber Template nicht erworben (`not_entitled`) |
| 404 | Template unbekannt oder Datei fehlt im Storage |

## Admin (Bearer-Token, Reiter „Shop → Template-Dateien")

- `POST /api/admin/template-artifacts/upload` — Multipart: `file` (Template-JSON),
  `shop_slugs` (JSON-Array), `is_free`, `is_published`. **Metadaten werden aus der
  JSON gelesen** (`template_id`, `template_name`, `description`, `category`, `version`);
  es gibt keine zweite Wahrheit neben der Datei. Upsert nach (`template_id`, `version`),
  Ablage unter `UPLOADS_DIR/templates/<template_id>/<version>/template.json`.
- `GET /api/admin/template-artifacts`, `PUT /api/admin/template-artifacts/{id}`
  (`shop_slugs`, `min_feature`, `is_free`, `is_published`), `DELETE …/{id}`.

## Client-Seite (Datenmonster)

- `GET /api/templates/store` → Katalog + `installed` / `local_version` / `update_available`
  (Abgleich mit der lokalen `templates`-Tabelle). Wirft nie: `error = no_license`
  bzw. `catalog_unreachable: …`.
- `POST /api/templates/store/{template_id}/install` → lädt die JSON und legt sie per
  Upsert nach `template_id` im lokalen Katalog ab. **Installiert noch nichts ins
  Projekt** — das macht danach wie gewohnt `POST /api/templates/install`.
- UI: Abschnitt „Template-Store" oben im Vorlagen-Panel (`TemplatesPanel.tsx`).

## Test

`monstersuite/backend/tests/test_template_store.py` prüft die Berechtigung gegen
eine frische sqlite-DB (Käufer / Bundle-Abonnent / Bestellanfrage / Fremder /
abgelaufene Testlizenz), inklusive des Shop-Download-Gates `_has_access`:

```sh
docker run --rm -v $PWD/backend:/app:ro -v $PWD/backend/tests:/test -w /test python:3.11-slim \
  sh -c "pip install -q -r /app/requirements.txt aiosqlite; python test_template_store.py"
```

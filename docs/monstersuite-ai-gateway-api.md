# monstersuite AI-Gateway & Credit-System (Vertrag + Datenmodell)

Dieser Vertrag beschreibt den **zentralen AI-Gateway** auf `monstersuite.de`, über
den Datenmonster-Instanzen die kostenpflichtige **„Datenmonster AI"** (Betreiber-
OpenAI-Zugang) nutzen, sowie das **Credit-/Abrechnungssystem**, das dahinter läuft.

Er ist das **Design-Artefakt** für die Umsetzung (Slice 1: „Vertrag + Datenmodell
zuerst"). Erst wenn dieser Vertrag steht, wird auf beiden Seiten dagegen gebaut.

Schwesterdokument: `docs/monstersuite-plugin-api.md` (Plugin-Auslieferung) — dieselbe
Auth- und Aufrufmechanik.

---

## 0. Grundprinzipien & Rollenverteilung

| | **Datenmonster** (pro Kunde selbst-gehostet) | **monstersuite** (zentral, Betreiber) |
|---|---|---|
| DB | SQLite (`datenmonster.db`) | Postgres (async SQLAlchemy) |
| KI heute | nur Ollama (`ai_service.py`) | — |
| Rolle neu | dünner **Client** (`DatamonsterProvider`) | **Gateway + OpenAI-Key + Ledger + Pricing** |

**Warum zentral?** Datenmonster läuft beim Kunden; ein dort hinterlegter OpenAI-Key
wäre für den Kunden-Admin lesbar. Deshalb: OpenAI-Key, Ledger, Pricing und Usage
liegen **ausschließlich** in monstersuite. Jede Instanz ruft den Gateway per
**Lizenzschlüssel als Credential** auf (identisch zu `/api/v1/licenses/*` und
`/api/v1/plugins/*`).

**Invarianten (nicht verhandelbar):**
- Der OpenAI-Key verlässt **niemals** den monstersuite-Server (nicht ins Frontend,
  nicht in Antworten, nicht in Logs).
- **Kein** Prompt- und **kein** Antwort-Inhalt wird persistiert (nur Metadaten).
- Alle Geld-/Credit-Werte als **Decimal/Numeric**, nie Float.
- Jede Abbuchung ist **idempotent** über `ai_request_id` (UUID) — Retries buchen nie doppelt.
- Bestehende Ollama-Funktionalität bleibt unverändert lauffähig.

---

## 1. Auth-Modell (Lizenz-als-Credential)

Jeder Request an den Gateway trägt denselben Body wie die Lizenz-/Plugin-APIs
(erzeugt Datenmonster-seitig von `license_auth_body(db)` in `backend/app/api/license.py`):

```json
{
  "license_key": "DM-XXXX-...",
  "email":       "kunde@example.de",
  "machine_id":  "<sha256[:32]>",
  "hostname":    "kundenserver",
  "product":     "datenmonster",
  "version":     "1.2.3"
}
```

**Server-Prüfung** (analog `_authorize` in `backend/routers/plugins_v1.py`):
1. `license_key` existiert, `status == active`, nicht `expired` (`valid_until`).
2. `product`-Slug der Lizenz == `datenmonster` (sonst `wrong_product`).
3. Feature `ai_datenmonster` in den Plan-Features **oder** ein Guthabenkonto existiert
   (Kauf schaltet frei). Ohne Berechtigung → `not_entitled`.

Der **Tenant** ist die **Lizenz** (`licenses.id`). 1 Lizenz = 1 Guthabenkonto.
Es wird **keine** parallele Kundenverwaltung angelegt — `customer_id` wird aus der
Lizenz mitgeführt (Reporting/Admin), Abrechnungseinheit bleibt die Lizenz.

---

## 2. Endpoints (Übersicht)

Alle unter `POST/GET https://monstersuite.de/api/v1/ai/...`. Fehlerformat einheitlich:
`{ "error": "<code>", "message": "<text>" }` mit passendem HTTP-Status.

| Methode & Pfad | Zweck | Auth |
|---|---|---|
| `POST /api/v1/ai/generate` | KI-Anfrage ausführen (SSE-Stream), abrechnen | Lizenz |
| `GET  /api/v1/ai/balance`  | aktuelles Guthaben + Monatsverbrauch | Lizenz |
| `GET  /api/v1/ai/usage`    | Verbrauchs-/Transaktionsverlauf (Dashboard) | Lizenz |
| `GET  /api/v1/ai/packages` | verfügbare Credit-Pakete (S/M/L) | Lizenz |
| `GET  /api/v1/ai/models`   | für die Lizenz nutzbare Modelle + Request-Types | Lizenz |

Admin-Endpunkte (Betreiber, Login-Auth in monstersuite, **nicht** Teil des Client-Vertrags):
`/api/admin/ai/overview`, `/api/admin/ai/credit-adjust`, `/api/admin/ai/pricing`,
`/api/admin/ai/packages` — siehe §9.

---

## 3. `POST /api/v1/ai/generate`  (Kern)

Führt eine KI-Anfrage über den Betreiber-OpenAI-Zugang aus und rechnet sie ab.
Antwortet als **SSE-Stream** (wie Datenmonsters bestehende `_sse_stream`), damit die
Frontend-Streaming-UI unverändert weiterläuft.

**Request** (zusätzlich zum Auth-Body):
```json
{
  "ai_request_id": "9f1c...-uuid",         // Pflicht, Idempotenzschlüssel
  "request_type":  "SQL_GENERATION",       // siehe §7
  "model":         "auto",                 // "auto" | konkretes Modell (Whitelist)
  "messages":      [ {"role":"system","content":"..."},
                     {"role":"user","content":"..."} ],
  "options": {                             // optional, serverseitig geklemmt
    "temperature": 0.4,
    "max_output_tokens": 1000,             // hartes Server-Limit greift zusätzlich
    "json": false
  }
}
```
- `messages` folgt der OpenAI-Chat-Struktur. Datenmonster mappt sein internes
  `system` + `messages` genau hierauf.
- Prompts werden **verarbeitet, aber nie gespeichert** (§20).

**Ablauf serverseitig (transaktionssicher):**
1. Auth (§1) → Lizenz + Konto laden.
2. **Idempotenz-Check:** existiert `ai_usage.ai_request_id` bereits mit `success=true`?
   → gespeichertes Ergebnis-Meta zurückgeben, **nicht** erneut aufrufen/abbuchen.
3. **Kostenschutz** (§8): Rate-Limit, Tages-/Monatslimit, Konto-Guthaben > Mindest-
   reserve. Reicht das Guthaben grundsätzlich nicht → `insufficient_credits` (402),
   **kein** OpenAI-Call.
4. Modellwahl: `auto` → `pick_model(request_type)` (Routing-Hook, §Auto). Sonst
   Whitelist-Prüfung.
5. **Reservierung:** vorläufige Credits (konservative Obergrenze aus `max_output_tokens`)
   per Ledger-Buchung `AI_USAGE` (pending) sperren → verhindert Überziehung bei
   parallelen Requests (§6 Race Conditions).
6. OpenAI-Call **mit `stream_options.include_usage=true`** → echte Token-Usage im
   Abschluss-Chunk. Tokens werden **nicht geschätzt**, wenn echte Usage vorliegt (§7 Spec).
7. Nach Abschluss: `provider_cost` aus `ai_model_pricing` (gültiger Satz zum
   Request-Zeitpunkt, mitgeschrieben), `customer_cost` + `credits_used` aus
   `calculate_credit_cost()` (§8).
8. **Korrektur der Reservierung** auf den echten Betrag (Gegen-/Nachbuchung), Konto
   aktualisieren, `ai_usage` schreiben. Alles in **einer** DB-Transaktion mit
   Row-Lock (`SELECT ... FOR UPDATE`) auf dem Konto.

**SSE-Events** (jede Zeile `data: {json}\n\n`):
```
data: {"type":"meta","model":"gpt-4o-mini","request_type":"SQL_GENERATION"}
data: {"type":"token","content":"SELECT"}
data: {"type":"token","content":" * FROM ..."}
data: {"type":"usage","input_tokens":812,"cached_input_tokens":128,
        "output_tokens":143,"credits_used":3,"balance_after":2838}
data: {"type":"done"}
```
Der Datenmonster-Client reicht `token`-Events 1:1 an die bestehende Streaming-UI
weiter und wertet `usage`/`done` fürs Guthaben-Update aus.

**Fehlerverhalten (§12):** Timeout, Provider nicht erreichbar, Rate-Limit, ungültige
Antwort, Abbruch → **keine** Credit-Abbuchung, sofern `provider_cost == 0`. Die
Reservierung (Schritt 5) wird **freigegeben** (Gegenbuchung `REFUND`/Storno). Der
Fehler wird trotzdem in `ai_usage` protokolliert (`success=false`, `error_code`).
SSE: `data: {"type":"error","error":"provider_timeout","message":"..."}`.

Error-Codes: `insufficient_credits` (402), `rate_limited` (429), `provider_error`
(502), `provider_timeout` (504), `not_entitled` (403), `wrong_product` (403),
`invalid_key`/`expired` (401), `bad_request` (400).

---

## 4. `GET /api/v1/ai/balance`

Liefert Kontostand + Monatsaggregat für die KI-Einstellungen-Kachel im Frontend.
```json
{
  "balance": 2841,
  "currency_label": "Credits",
  "month": { "credits_used": 359, "requests": 127 },
  "low_balance": false
}
```

## 5. `GET /api/v1/ai/usage`

Dashboard-Daten (Query: `?from=&to=&limit=`). Nur **Metadaten**.
```json
{
  "balance": 2841,
  "month": { "credits_used": 359, "requests": 127 },
  "by_model":        [ {"model":"gpt-4o-mini","credits":210,"requests":98} ],
  "by_request_type": [ {"request_type":"SQL_GENERATION","credits":140,"requests":40} ],
  "by_day":          [ {"day":"2026-08-01","credits":22} ],
  "transactions":    [ {"ts":"...","type":"AI_USAGE","credits":-3,
                        "balance_after":2838,"reference":"<ai_request_id>",
                        "description":"SQL_GENERATION / gpt-4o-mini"} ]
}
```

## 6. `GET /api/v1/ai/packages`

Admin-konfigurierbare Pakete (keine Codewerte). Kaufprozess selbst ist **noch nicht**
Teil dieses Vertrags — nur die Anzeige + eine `checkout_url`-Schnittstelle wird vorbereitet.
```json
{ "packages": [
  {"code":"S","name":"Starter","price_eur":"10.00","credits":1000,"sort":1},
  {"code":"M","name":"Medium", "price_eur":"25.00","credits":3000,"sort":2},
  {"code":"L","name":"Large",  "price_eur":"50.00","credits":7500,"sort":3}
]}
```

---

## 7. Request-Types

Erweiterbare Enumeration; steuert später Modellwahl und Credit-Tarif:
`CHAT`, `SQL_GENERATION`, `SQL_ANALYSIS`, `SQL_EXPLAIN`, `DATA_ANALYSIS`,
`ARTICLE_DESCRIPTION`, `CLASSIFICATION`, `MAPPING_ASSISTANT`, `TRANSFORMATION`,
`EXPRESSION`, `ERROR_EXPLAIN`, `SUMMARY`, `OTHER`.

Datenmonster setzt den Typ pro `ai.py`-Endpunkt (z.B. `/generate-sql` →
`SQL_GENERATION`, `/summarize-data` → `SUMMARY`).

---

## 8. Preise & Credit-Berechnung (zentral, konfigurierbar)

- **`ai_model_pricing`** (§Datenmodell) hält Provider-Preise **versioniert**
  (`valid_from`/`valid_to`). Bei jedem Request wird der **verwendete** Preissatz in
  `ai_usage` festgeschrieben → historische Daten ändern sich nie bei späteren Preis-
  anpassungen.
- **`provider_cost`** = tatsächliche OpenAI-Kosten (input/cached/output-Tokens ×
  jeweiliger Satz). **`customer_cost`** = interner Verkaufspreis. Beide gespeichert →
  Deckungsbeitrag auswertbar.
- **`calculate_credit_cost(provider, model, in_tok, cached_tok, out_tok, request_type)`**
  zentral, nicht im Code verstreut. Berücksichtigt Marge/Multiplikator, Mindestverbrauch
  (z.B. ≥ 1 Credit), Modell-/Typ-Faktor. Konfigurierbar über `ai_credit_policy`
  (Key/Value oder Tabelle), nicht hart kodiert.
- Credits sind **nicht** an OpenAI-Tokens gekoppelt.

Start-Modelle: `gpt-4o-mini` (günstig, Default) und `gpt-4o` (komplexe SQL/Analyse).

---

## 9. Administrator-Bereich (monstersuite, Login-Auth)

Globale KI-Übersicht: Anzahl AI-Kunden, Requests gesamt, verbrauchte Credits,
`provider_cost`, `customer_cost`, **Deckungsbeitrag**; Aufschlüsselung nach
Provider/Modell/Kunde/Request-Type. Admin kann Credits **hinzufügen/abziehen/korrigieren**
— **immer** über eine Ledger-Buchung (`ADMIN_CREDIT`/`ADMIN_DEBIT`), nie durch
Überschreiben des Kontostands. Pakete + Pricing sind hier pflegbar.

---

## Datenmodell (monstersuite, Postgres — async SQLAlchemy)

Konventionen wie `backend/models.py`: Integer-PKs, `server_default=func.now()`,
`Numeric` für Geld/Credits. **Ledger ist append-only** — Korrekturen nur per
Gegenbuchung.

### `ai_credit_account` — Guthabenkonto (1 je Lizenz)
| Feld | Typ | Hinweis |
|---|---|---|
| id | Integer PK | |
| license_id | FK licenses.id, **unique** | Abrechnungseinheit / Tenant |
| customer_id | FK customers.id | Reporting (aus Lizenz abgeleitet) |
| balance | Numeric(16,4) | aktuelles Guthaben (Credits) |
| total_purchased | Numeric(16,4) | Summe je gekaufter Credits |
| total_consumed | Numeric(16,4) | Summe je verbrauchter Credits |
| created_at / updated_at | DateTime | |

### `ai_credit_transactions` — Ledger (append-only)
| Feld | Typ | Hinweis |
|---|---|---|
| id | Integer PK | |
| account_id | FK ai_credit_account.id | |
| license_id | FK licenses.id | denormalisiert für Reporting |
| ts | DateTime server_default now | |
| transaction_type | String | PURCHASE \| AI_USAGE \| REFUND \| ADMIN_CREDIT \| ADMIN_DEBIT |
| credits | Numeric(16,4) | vorzeichenbehaftet (+Kauf / −Verbrauch) |
| balance_before | Numeric(16,4) | |
| balance_after | Numeric(16,4) | |
| reference | String | i.d.R. `ai_request_id` bzw. Kauf-/Admin-Ref |
| description | String | z.B. „SQL_GENERATION / gpt-4o-mini" |

**Idempotenz:** UNIQUE(`account_id`,`reference`,`transaction_type`) verhindert
Doppelbuchung bei Retries.

### `ai_usage` — Aufruf-Metadaten (KEINE Prompts/Antworten)
| Feld | Typ | Hinweis |
|---|---|---|
| id | Integer PK | |
| ai_request_id | String, **unique** | Idempotenz-Anker (UUID vom Client) |
| license_id / customer_id | FK | |
| ts | DateTime | |
| provider | String | `openai_datamonster` \| `ollama` |
| model | String | |
| request_type | String | §7 |
| input_tokens / cached_input_tokens / output_tokens / total_tokens | Integer | echte Provider-Werte |
| provider_cost | Numeric(14,8) | sehr kleine Beträge möglich |
| customer_cost | Numeric(14,8) | |
| credits_used | Numeric(16,4) | |
| pricing_ref | Integer/String | verwendeter `ai_model_pricing`-Satz (Snapshot) |
| duration_ms | Integer | |
| success | Boolean | |
| error_code | String, nullable | §12 |

### `ai_model_pricing` — Preistabelle (versioniert)
| Feld | Typ | Hinweis |
|---|---|---|
| id | Integer PK | |
| provider | String | |
| model | String | |
| input_price_per_million | Numeric(14,6) | EUR bzw. USD (Feld `currency`) |
| cached_input_price_per_million | Numeric(14,6) | |
| output_price_per_million | Numeric(14,6) | |
| currency | String(3) | Default „USD"; Umrechnung zentral |
| valid_from | DateTime | |
| valid_to | DateTime, nullable | offen = aktueller Satz |
| enabled | Boolean | |

### `ai_package` — Credit-Pakete (admin-konfigurierbar)
| Feld | Typ | Hinweis |
|---|---|---|
| id | Integer PK | |
| code | String | S \| M \| L (erweiterbar) |
| name | String | |
| price_eur | Numeric(10,2) | |
| credits | Numeric(16,4) | Startwerte 1000/3000/7500 — **nicht im Code** |
| enabled | Boolean | |
| sort_order | Integer | |

### `ai_credit_policy` — Tarif-/Schutzparameter (Key/Value)
Marge/Multiplikator, Mindestverbrauch, Modell-/Typ-Faktoren, Limits (Output-Token,
Requests/Tag, Kosten/Tag+Monat, Rate-Limit). Admin-pflegbar, damit §8/§21 ohne
Codeänderung justierbar sind.

---

## Kostenschutz (§21) — serverseitig, hart

Unabhängig vom Frontend, weil Datenmonster **automatisierte Pipelines** hat, die
unkontrolliert KI-Aufrufe erzeugen könnten:
- max. Output-Token pro Request (klemmt `options.max_output_tokens`).
- Request-Limit pro Lizenz (Minute/Stunde) → `rate_limited`.
- Tages-/Monats-Kostenlimit pro Lizenz → sanftes `insufficient_credits` bzw. Sperre.
- Schutz gegen Workflow-Endlosschleifen (Burst-Erkennung je `machine_id`).

---

## Datenmonster-Client (Vertragsseite, Kurzfassung)

Kein Big-Bang. Provider-Abstraktion, bestehende Signaturen erhalten:
- `AIProvider`-Interface: `stream(messages, system, params, request_type, ai_request_id)`,
  `health_check()`. `AIService` (Ollama) wird zu `OllamaProvider` (unverändertes Verhalten,
  `provider_cost=0`, optional lokales Usage-Log).
- `DatamonsterProvider`: ruft `POST /api/v1/ai/generate` mit `license_auth_body(db)` +
  UUID, streamt SSE durch, hebt `usage`/`error`-Events heraus.
- `build_ai_service(db)` wählt anhand `SystemSetting.ai_provider` (`ollama` |
  `datenmonster`). Alle `ai.py`-Endpunkte bleiben unverändert; sie setzen künftig nur
  ihren `request_type`.
- Frontend: Anbieterwahl (Ollama vs. Datenmonster AI) + Guthaben/Verbrauch (`/balance`)
  + „Guthaben aufladen" (Schnittstelle, kein Checkout).

---

## Offen / später (bewusst nicht in Slice 1)

- Bezahlanbindung (PayPal ist in monstersuite vorhanden — `paypal_helper.py`) →
  `PURCHASE`-Buchung nach erfolgreichem Kauf; nur Schnittstelle vorbereiten.
- Auto-Modellwahl-Routing (`pick_model`) als Hook vorhanden, Logik minimal.
- Weitere Provider (Anthropic, Gemini) — durch `provider`-Feld + Interface offen.
- Extraktion zu einem eigenständigen MonsterSuite-Credit-Service (kein Microservice jetzt).

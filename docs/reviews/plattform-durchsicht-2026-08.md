# Datenmonster – Durchsicht der Plattform

Stand: 27.08.2026 · Commit `0c67d63` · reine Bestandsaufnahme, nichts geändert

Umfang: 37.900 Zeilen Python (Backend), 43.900 Zeilen React (Frontend),
307 API-Endpunkte, 15 Knotenarten, 9 Formulare, 187 Mappings in der laufenden
Installation.

Jeder Befund unten ist **belegt** – mit Datei und Zeile, und wo möglich mit einem
Versuch gegen die laufende Instanz. Wo ich nur einen Verdacht habe, steht das
ausdrücklich dabei. Was ich **nicht** geprüft habe, steht in §7.

---

## 0. Das Wichtigste in Kürze

Die Plattform ist deutlich solider, als ich erwartet hatte. Zwei Beispiele, bei
denen ich einen Fund vermutete und keinen gefunden habe: Von 307 Endpunkten sind
genau **zwei** ohne Anmeldepflicht – Login und Health, also die richtigen. Und der
Login hat einen Brute-Force-Schutz (10 Versuche in 5 Minuten, dann 15 Minuten
Sperre, `auth.py:13-35`), den viele Eigenentwicklungen nicht haben.

Die Schwächen liegen woanders – in dieser Reihenfolge:

| # | Befund | Schwere | Aufwand |
|---|--------|---------|---------|
| **1** | Die Portal-Rolle wird serverseitig nicht durchgesetzt. Ein Kunde sieht fremde Pipelines, das Systemprotokoll und Servermetriken | **hoch** | mittel |
| **2** | `pipelines`, `dispatcher` und `exports` prüfen keinen Projektzugriff | **hoch** | klein |
| **3** | Keine automatisierten Tests – bei 82.000 Zeilen | **hoch** | groß, aber teilbar |
| **4** | Kein Backup-Verfahren; die Daten liegen allein im Docker-Volume | **hoch** | klein |
| **5** | Keine echten Datenbank-Migrationen: 51 `ALTER TABLE` mit verschlucktem Fehler | mittel | mittel |
| **6** | 6 bekannte Schwachstellen in npm-Paketen, davon 2 hoch (u. a. SSRF in axios) | mittel | klein |
| **7** | Dataset-`upsert`/`append` sind wirkungslos (stiller Rückfall auf Replace) | mittel | klein |
| **8** | Alles läuft im Arbeitsspeicher, ohne Zeilen- oder Ressourcengrenze | mittel | mittel |
| **9** | 91 Stellen mit stillschweigend verschlucktem Fehler | mittel | mittel |
| **10** | Zugangstoken 7 Tage gültig, ohne Widerruf; Passwort ab 6 Zeichen | niedrig | klein |

---

## 1. Die Portal-Rolle ist eine reine Oberflächen-Entscheidung

**Belegt durch einen Versuch gegen die laufende Instanz.** Ich habe einen
Benutzer mit `is_portal_only = True` angelegt, mich angemeldet und die
Editor-Schnittstellen aufgerufen (der Benutzer ist wieder gelöscht):

| Aufruf | Ergebnis |
|--------|----------|
| `GET /api/pipelines/` | **200 – vier Pipelines aus drei fremden Projekten**, mit vollständiger Konfiguration: Zeitpläne, Mapping-Verweise, E-Mail-Knoten |
| `GET /api/pipelines/1` | **200 – volle Detailansicht** eines Projekts, dem der Benutzer nicht angehört |
| `GET /api/logs/` | **200 – das komplette Systemprotokoll** (22 Einträge, Projektnamen, Template-Namen, Fehlertexte) |
| `GET /api/monitoring/system` | **200 – CPU, RAM, Plattenbelegung** des Servers |
| `GET /api/mappings/`, `/datasets/`, `/connections/`, `/projects/`, `/exports/` | 200, aber **leer** – diese filtern korrekt |

Die Ursache: `is_portal_only` wird im gesamten Backend an **genau einer** Stelle
ausgewertet (`api/intrastat.py:66`). Sonst steht das Kennzeichen nur im
Anmelde-Token, und das Frontend leitet Portal-Benutzer auf `/portal` um. Wer die
API direkt anspricht – ein Browser-Werkzeug reicht – umgeht das.

**Warum das zählt:** Das Portal ist ausdrücklich dafür gedacht, Formulare an
Kunden zu geben (siehe `Anleitung.md` §12). Ein Kunde ist damit ein angemeldeter
Benutzer auf derselben Instanz wie die eigenen Auswertungen.

**Vorschlag:** Eine Abhängigkeit `require_kein_portal_nutzer`, die an allen
Editor-Routern hängt – analog zu `get_current_user`, aber als Router-weite
`dependencies=[...]` beim `include_router`, damit sie nicht je Endpunkt vergessen
werden kann. Ausnahmen bleiben `portal`, `auth`, `forms` (Lauf), `ai` und
`business_config`.

---

## 2. Drei Module prüfen keinen Projektzugriff

Zählung der Rechteprüfungen je Modul (`require_editor`, `can_read_project`,
`get_accessible_project_ids`):

| Modul | Prüfungen | Endpunkte |
|-------|-----------|-----------|
| `mappings.py` | 11 | 11 |
| `connections.py` | 12 | 16 |
| `ftp_sources.py` | 7 | 7 |
| `alerts.py` | 10 | 9 |
| `datasets.py` | 16 | 24 |
| **`forms.py`** | **2** | 11 |
| **`pipelines.py`** | **0** | 9 |
| **`dispatcher.py`** | **0** | 5 |
| **`exports.py`** | **0** | 4 |

`pipelines.py:118-141` im Klartext: `list_pipelines` filtert nur, wenn eine
`project_id` mitgegeben wird – ohne Parameter kommt alles. `get_pipeline`,
`update_pipeline`, `delete_pipeline`, `run_pipeline` und `toggle_pipeline`
schlagen die Pipeline allein über die ID nach.

Das heißt: **Jeder angemeldete Benutzer kann eine fremde Pipeline lesen, ändern,
starten und löschen**, sofern er die ID kennt – und die sind fortlaufend. Gelesen
habe ich das belegt (Tabelle oben); Ändern und Starten habe ich aus naheliegenden
Gründen nicht ausprobiert, der Code lässt daran aber keinen Zweifel.

**Vorschlag:** Dasselbe Muster wie in `mappings.py` – `require_editor` bei
schreibenden, `can_read_project` bei lesenden Zugriffen, `get_accessible_project_ids`
in den Listen. Das ist überschaubare Fleißarbeit, kein Umbau.

---

## 3. Keine automatisierten Tests

`pytest` steht nicht in `backend/requirements.txt`, im Repository gibt es keine
einzige Testdatei (außerhalb von `node_modules`). Die drei CI-Abläufe
(`.github/workflows/`) bauen und veröffentlichen, sie prüfen nichts.

**Was das praktisch bedeutet**, zeigt diese Sitzung selbst: Vier der Fehler, die
wir heute gefunden haben, hätte ein einziger Test gefunden –

- `MappingContext.from_orm` lud zwei Knotenarten nicht (ein Vergleich der
  Dataclass-Felder gegen die Modellspalten, fünf Zeilen)
- Der Template-Installer übertrug fünf Knotenarten nicht (dasselbe Muster)
- Dataset-`upsert` fiel still auf Replace zurück
- Der REST-Knoten schickte nie einen Anfragerumpf

**Vorschlag, in dieser Reihenfolge:**
1. `pytest` + ein Dutzend Tests für die **Vollständigkeitsinvarianten** – „jede
   Knotenart des Modells kommt im Kontext an, wird ausgeführt, wird exportiert
   und wieder importiert". Diese Klasse von Fehlern ist hier nachweislich die
   häufigste, und sie ist am billigsten zu testen.
2. Tests für die Verschlüsselungs- und Maskierungswege (die Fälle, die ich heute
   von Hand durchgespielt habe – sie gehören festgeschrieben).
3. Ein Rauchtest, der ein Template installiert, ein Mapping ausführt und wieder
   aufräumt.
4. Erst danach Breite.

Ein Test-Lauf in der CI vor `build-push` verhindert, dass so etwas überhaupt
ausgeliefert wird.

---

## 4. Kein Backup-Verfahren

Die gesamte Anwendungsdatenbank liegt im Docker-Volume `datenmonster-data`
(`docker-compose.yml`), also **nicht** im Projektordner. Es gibt im Repository
kein Sicherungs- oder Rückspielverfahren – weder ein Skript, noch einen
Dienst, noch eine Anleitung.

Darin stehen: alle Mappings, Formulare, Warnregeln, Zeitpläne, die
Wissensdatenbank, die Schema-Kataloge und – verschlüsselt – sämtliche
Zugangsdaten. Ein verlorenes Volume ist der Verlust der gesamten
Einrichtungsarbeit; die Cockpits ließen sich aus den Templates neu installieren,
alles Handgemachte nicht.

Erschwerend: Die Verschlüsselung hängt am `SECRET_KEY` aus der `.env`. Eine
Sicherung des Volumes **ohne** die `.env` ist wertlos, weil sich die Zugangsdaten
daraus nicht mehr entschlüsseln lassen.

**Vorschlag:** Ein `backup`-Dienst im Compose oder ein Skript, das
`sqlite3 .backup` nutzt (nicht einfach die Datei kopieren – bei laufendem
Schreibzugriff ist das Ergebnis unbrauchbar), die `.env` mitsichert und
rollierend aufbewahrt. Dazu ein dokumentierter Rückspielweg. Aufwand: gering,
Wirkung: bewahrt vor dem Totalverlust.

---

## 5. Datenbank-Schema wird per Hand fortgeschrieben

`main.py:38-270` legt beim Start das Schema an (`Base.metadata.create_all`) und
führt danach **51 einzelne `ALTER TABLE`- und `CREATE TABLE`-Anweisungen** aus,
jede in einem `try/except Exception: pass` (`main.py:271-274`).

Das funktioniert, weil ein „Spalte existiert bereits" so verschluckt wird. Es
hat aber drei Nachteile:

- **Jeder andere Fehler wird ebenfalls verschluckt.** Schlägt eine Migration aus
  einem echten Grund fehl, startet die Anwendung trotzdem – und scheitert später
  an einer Stelle, die mit der Ursache nichts zu tun hat.
- **Es gibt keine Rückrichtung** und keine Reihenfolge-Garantie.
- **Die Liste wächst monoton** und ist inzwischen 230 Zeilen lang.

Zudem kann `create_all` bestehende Tabellen **nicht** ändern – jede Änderung an
einer vorhandenen Spalte (Typ, NOT NULL, Umbenennung) braucht ohnehin Handarbeit.

**Vorschlag:** Alembic einführen, den heutigen Stand als Ausgangsversion
einfrieren und die bestehende Liste dort belassen, wo sie ist (sie muss für
Altinstallationen weiterlaufen). Neue Änderungen dann nur noch als Migration.
Mittlerer Aufwand, aber der richtige Zeitpunkt ist vor dem nächsten größeren
Schema-Schritt – nicht danach.

---

## 6. Abhängigkeiten

**Frontend:** `npm audit --production` meldet 6 Schwachstellen, davon zwei hoch:

| Paket | Art |
|-------|-----|
| **axios** (hoch) | SSRF durch Umgehung der NO_PROXY-Namensnormalisierung |
| **form-data** (hoch) | CRLF-Einschleusung über nicht maskierte Feldnamen |
| @remix-run/router, react-router, react-router-dom (mittel) | offene Weiterleitung, teils bis XSS |
| follow-redirects (mittel) | gibt eigene Authentifizierungs-Kopfzeilen an fremde Domänen weiter |

Die axios-Lücke ist besonders unangenehm, weil sie dieselbe Angriffsklasse
betrifft, gegen die das Backend mit `net_guard` sorgfältig geschützt ist.

**Backend:** 24 der 31 Zeilen in `requirements.txt` sind auf feste Versionen
festgelegt – gut. Ein `pip-audit` habe ich nicht laufen lassen (nicht installiert);
das sollte nachgeholt werden.

**Vorschlag:** `npm audit fix` ausführen und danach das Frontend testen (React
Router ist ein Hauptversionssprung wert zu prüfen). Beides – npm und pip – in die
CI aufnehmen, damit neue Meldungen auffallen.

---

## 7. Datenintegrität: Dataset-`upsert` ist wirkungslos

Ausführlich in `docs/plans/shipman-fulfillment-template.md` §1.6 beschrieben,
hier nur die Kurzfassung: `mapping_writer.py:45-113` liest den Dataset-Speicher
mit `json.load()`, gespeichert wird aber Parquet (`file_service.py:447`). Der
Lesefehler wird verschluckt, das Ergebnis ist ein stilles **Replace**.

Wer heute ein Mapping mit `append` oder `upsert` auf ein Dataset laufen lässt,
verliert bei jedem Lauf die Vorgeschichte, ohne dass irgendwo ein Fehler steht.
In der laufenden Installation nutzt das derzeit niemand – der Fehler ist also
folgenlos, aber scharf.

**Vorschlag:** Beheben (Parquet lesen statt `json.load`) und mit einem Test
festschreiben. Wichtig: Der Fix ändert das Verhalten bestehender Mappings, die
heute faktisch als Replace laufen – deshalb bewusst und mit Ankündigung.

---

## 8. Betriebsgrenzen: alles im Arbeitsspeicher

Jeder Lauf lädt seine Daten vollständig in den Speicher (`fetch_full()` in allen
Konnektoren, `connectors/base.py:27`). Es gibt eine `iter_chunks`-Schnittstelle,
die aber standardmäßig einfach `fetch_full()` in einem Stück liefert
(`base.py:47-49`). Zeilenobergrenzen gibt es keine, und die
Ressourcengrenzen im Compose sind auskommentiert (`docker-compose.yml:75-76`).

Praktisch: Ein Mapping über eine große Tabelle kann den Container an die
Speichergrenze bringen. Da alles in einem Prozess läuft, reißt das auch alle
anderen Läufe und die Oberfläche mit.

**Vorschlag:** Zwei kleine Schritte mit großer Wirkung – eine konfigurierbare
Zeilenobergrenze je Lauf mit klarer Meldung statt stillem Anwachsen, und
`mem_limit` im Compose, damit im Zweifel ein Lauf stirbt und nicht der Server.
Echtes Chunking wäre der saubere Weg, ist aber ein größerer Umbau.

---

## 9. Fehler, die niemand sieht

91 Stellen mit `except Exception: pass` (zusätzlich 2 nackte `except:`).
Schwerpunkte: `connections.py` (14), `mapping_service.py` (7), `datasets.py` (7),
`scheduler_service.py` (6), `ftp_service.py` (6).

Manche davon sind richtig – ein Protokollierungsfehler soll keinen ETL-Lauf
beenden, und genau so habe ich es heute selbst gebaut. Viele sind es nicht:
Der Dataset-`upsert`-Fehler (§7) hat **drei Jahre** überlebt, weil ein
`except Exception: existing = []` ihn zugedeckt hat.

**Vorschlag:** Kein Großreinemachen, sondern eine Regel für Neues – wer
schluckt, protokolliert wenigstens auf `debug`. Und die 20 Stellen in
`connections.py`/`datasets.py` gezielt durchsehen, weil dort Nutzerdaten
verarbeitet werden.

---

## 10. Anmeldung und Sitzungen

Was gut ist: Brute-Force-Schutz am Login (`auth.py:13-35`), bcrypt für Passwörter
(`core/security.py:19`), Sicherheits-Kopfzeilen inklusive HSTS und CSP
(`main.py:376-395`), CORS auf eine Positivliste beschränkt, und der
SSRF-Schutz für alle ausgehenden Aufrufe (`core/net_guard.py`) ist
überdurchschnittlich sorgfältig gemacht.

Was ich anders machen würde:

| Punkt | Heute | Vorschlag |
|-------|-------|-----------|
| Token-Laufzeit | **7 Tage** (`config.py:31`) | 8–24 Stunden mit stiller Erneuerung |
| Token-Widerruf | keiner – ein gestohlener Token gilt bis zum Ablauf | Sitzungstabelle oder `token_version` am Benutzer, die beim Passwortwechsel hochzählt |
| Passwortlänge | **6 Zeichen** (`api/auth.py:44`) | mindestens 10, und Abgleich gegen eine Liste der häufigsten |
| Ablage im Browser | `localStorage` (`api/client.js:8`) | vertretbar; ein `httpOnly`-Cookie wäre besser, ist aber ein größerer Umbau |
| Passwortwechsel | beendet andere Sitzungen nicht | mit dem Widerruf oben zusammen lösen |

---

## 11. Kleinere Beobachtungen

- **Der Health-Endpunkt prüft nichts** (`main.py:460`): Er gibt bedingungslos
  `{"status": "ok"}` zurück – auch wenn die Datenbank weg ist. Docker meldet den
  Container dann als gesund, während nichts mehr geht. Ein Blick in die
  Datenbank und auf den Zeitplandienst gehört dort hinein.
- **Der Zieltabellenname wird nicht maskiert** (`export_service.py:521-579`):
  Spalten werden gequotet (`[{c}]`) und Werte gebunden, der Tabellenname wird
  interpoliert. Ausnutzbar nur mit Editor-Rechten, und wer die hat, darf ohnehin
  SQL ausführen – deshalb keine Rechteausweitung, aber sauberer wäre eine Prüfung
  gegen die tatsächlich vorhandenen Tabellen.
- **Sehr große Dateien**: `api/ai.py` (2.393 Zeilen), `services/mapping_service.py`
  (2.295), `pages/MappingEditor.tsx` (2.363), `ApiStudioPanel.tsx` (2.114). Das ist
  kein Fehler, aber jede Änderung darin ist teurer als nötig – `ai.py` etwa
  bündelt 40 Endpunkte sehr unterschiedlicher Aufgaben.
- **Ein `dangerouslySetInnerHTML`** im Frontend (`XmlTemplateEditor.tsx`) – die
  einzige Stelle, sollte auf die Datenquelle geprüft werden.
- **Kein Zeitplan-Aufräumen sichtbar**: `JobRun`-Einträge und `system_logs`
  wachsen; für Warnläufe gibt es ein Aufräumen (`alert_service.py:463`), für die
  übrigen habe ich keines gefunden. Bei SQLite wächst die Datei sonst unbegrenzt.

---

## 12. Was ich nicht geprüft habe

Damit die Durchsicht nicht mehr verspricht, als sie hält:

- **Das Frontend im Betrieb** – ich habe nicht geklickt, sondern Code gelesen und
  gebaut. Bedienbarkeit, Barrierefreiheit und Verhalten bei Fehlern in der
  Oberfläche sind offen.
- **Die Plugin-Strecke** (`plugin-manager`, Tier-2-Container) – nur oberflächlich.
  Ein Plugin bringt fremden Code auf den Server; das verdient eine eigene Prüfung.
- **Der KI-Bereich** (`api/ai.py`, 2.393 Zeilen) – nur die Anbieterwahl und
  Guthabenlogik, nicht die Prompt-Behandlung. Ob Nutzereingaben dort sauber vom
  Systemprompt getrennt sind (Prompt-Injection), habe ich nicht untersucht.
- **`pip-audit`** für die Python-Abhängigkeiten – nicht installiert.
- **Lasttest / Nebenläufigkeit** – ob zwei gleichzeitige Läufe auf demselben
  Dataset sich ins Gehege kommen, ist offen. Der Verdacht besteht (§8), belegt
  ist er nicht.
- **Das Update- und Lizenzverfahren** gegen monsterSuite – nur gelesen.

---

## 13. Vorschlag für die Reihenfolge

**Zuerst, weil klein und wirksam:**
1. Backup einrichten (§4) – schützt vor dem einzigen wirklich irreversiblen Schaden
2. Projektzugriff in `pipelines`/`dispatcher`/`exports` nachziehen (§2)
3. `npm audit fix` (§6)

**Dann, weil es die Grundlage für alles Weitere ist:**
4. `pytest` + die Vollständigkeitstests (§3) – zusammen mit dem Fix für
   Dataset-`upsert` (§7), der damit gleich abgesichert ist
5. Portal-Rolle serverseitig durchsetzen (§1)

**Danach, in Ruhe:**
6. Alembic (§5), Token-Laufzeit und Widerruf (§10), Zeilenobergrenze und
   `mem_limit` (§8), Health-Endpunkt (§11)

Die Punkte 1–3 sind zusammen etwa ein Arbeitstag. Punkt 4 ist die eigentliche
Investition – und die, die sich am schnellsten auszahlt, wenn ich mir ansieht,
wie viele der heute gefundenen Fehler ein Test verhindert hätte.

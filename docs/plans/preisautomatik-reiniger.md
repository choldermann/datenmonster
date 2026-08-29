# Preisautomatik, Schritt 1: Ladenhüter-Rabatte („Reiniger")

Entwurf, noch nicht umgesetzt. Grundlage: `doku/jtl-preis-schema.md`
(Preisschema verifiziert am 2026-08-29 an PPS und HaKo).

## 1. Ziel und Abgrenzung

Artikel, die zu lange liegen, bekommen automatisch einen befristeten Rabatt;
verkauft sich der Artikel wieder, endet der Rabatt. Anwenden über
**Sonderpreise** (`tArtikelSonderpreis` + `tSonderpreise`), nicht über den
Grundpreis — der bleibt unangetastet. Das ist der entscheidende Sicherheitsgewinn:
Ein Sonderpreis ist befristet, gruppenbezogen und löst sich über `dEnde` von
selbst auf. Ein falscher Grundpreis tut das nicht.

**Pilot ist PPS.** Nur dort existiert eine gepflegte Preisstruktur (5
Kundengruppen mit je ~830 Artikeln). Bei HaKo hängen 6.240 von 7.200 Kunden in
„Neukunde" — dort wäre die Automatik ein Werkzeug ohne Werkstück.

Nicht in diesem Schritt: Kalkulation von Grundpreisen, Marktplätze, Repricer.

## 2. Anwenden: zwei Wege, eine Schnittstelle

Das Rechnen und das Nachhalten sind das Produkt; das Anwenden ist der letzte,
kleinste Schritt und bekommt deshalb **zwei austauschbare Rückseiten**:

- **Weg A — CSV für die JTL-Ameise.** Wir erzeugen die Importdatei, der Anwender
  importiert sie. Die Ameise kann Sonderpreise, Kundengruppen- und
  kundenspezifische Preise. Der Mensch bleibt im Ablauf, JTLs eigene Schicht
  validiert, kein Schreibzugriff nötig.
- **Weg B — Direktschreiben** in `tSonderpreise`/`tArtikelSonderpreis`. Der
  Trigger `tgr_tSonderpreise_INSUP` meldet den Artikel selbst an POS und
  Webshops; ein eigener Abgleich ist nicht nötig.

Weg A ist kein Wegwerfcode — er bleibt die Betriebsart für Kunden, die uns nicht
in die Datenbank lassen. Weg B kommt später, ohne dass sich am Modell etwas
ändert.

**Beide Wege lesen vorher und kontrollieren nachher.** Wir haben Lesezugriff:
Vor dem Anwenden lesen wir den Ist-Preis (das ist der Vorher-Wert im Journal),
nach dem Anwenden lesen wir erneut und gleichen ab — ist die Änderung
angekommen, bei wie vielen Artikeln nicht? Diese Soll/Ist-Kontrolle ist der
Unterschied zwischen „CSV erzeugt" und „Preis geändert".

## 3. Datenmodell

Vier Tabellen (SQLAlchemy-Modelle in `backend/app/models/preisregel.py`;
`Base.metadata.create_all` legt sie beim Start an, keine Migration nötig).

### `price_rulesets` — Regelwerk
| Feld | Zweck |
|---|---|
| `id`, `project_id`, `connection_id` | Ein Regelwerk gehört zu **einem Mandanten**, weil Preise je Wawi verschieden sind |
| `name`, `description`, `active` | |
| `scope` (JSON) | Welche Artikel: Warengruppen, Hersteller, Mindestbestand, Ausschlussliste |
| `kundengruppen` (JSON), `shops` (JSON) | Für welche Gruppen/Shops der Rabatt gilt |
| `min_marge_prozent`, `nie_unter_ek` | **Sicherheitsnetz**, siehe §6 |
| `laufzeit_tage` | Wie lange ein erzeugter Sonderpreis gilt (`dEnde`) |
| `preisendung` | Optional: auf x,x9 runden |

### `price_rules` — Stufen innerhalb eines Regelwerks
| Feld | Zweck |
|---|---|
| `id`, `ruleset_id`, `sort`, `active` | Erste zutreffende Stufe gewinnt (absteigend sortiert) |
| `kind` | `"ladenhueter"` — später `"kalkulation"` u. a. |
| `condition` (JSON) | `{"tage_ohne_verkauf_ab": 60}` |
| `action` (JSON) | `{"typ": "rabatt_prozent", "wert": 10}` |

### `price_runs` — Lauf
`id`, `ruleset_id`, `connection_id`, `started_at`, `finished_at`,
`triggered_by` (scheduler/manuell), `status`, `kandidaten`, `vorschlaege`,
`params` (JSON), `error`.

### `price_changes` — Änderungsjournal (das Rückgrat)
| Feld | Zweck |
|---|---|
| `run_id`, `ruleset_id`, `rule_id`, `connection_id` | Herkunft — beantwortet „warum kostet der Artikel das?" |
| `k_artikel`, `c_artnr`, `artikelname` | Name mitgeschrieben, damit das Journal lesbar bleibt, wenn der Artikel sich ändert |
| `k_kundengruppe`, `k_shop` | Ein Vorschlag je Artikel × Gruppe × Shop |
| `preis_alt`, `preis_alt_quelle` | Basis der Rechnung; Quelle ist `fVKNetto`, `tPreisDetail` oder ein bestehender Sonderpreis |
| `preis_neu`, `gueltig_von`, `gueltig_bis` | |
| `zustand` | `vorgeschlagen` → `freigegeben` → `angewandt` → `zurueckgenommen`; daneben `verworfen` (Sicherheitsnetz) und `fehlgeschlagen` |
| `weg` | `ameise` oder `direkt` |
| `export_file_id` | Verweis auf die erzeugte CSV (vorhandene Export-Infrastruktur) |
| `angewandt_am`, `angewandt_von` | |
| `kontrolliert_am`, `ist_preis`, `abweichung` | Ergebnis der Soll/Ist-Kontrolle |
| `begruendung` | Klartext: „112 Tage ohne Verkauf, Stufe 90 Tage → −20 %" |

Rücknahme erzeugt **keinen** Löschvorgang, sondern einen neuen Datensatz, der
den Sonderpreis beendet (`dEnde` auf gestern bzw. `nAktiv = 0`). Das Journal
bleibt vollständig.

## 4. Ablauf

1. **Nachtlauf** über den vorhandenen Zeitplaner → neuer `price_run`.
2. **Kandidaten** aus einem ganz normalen Mapping („Preisautomatik –
   Ladenhüter-Kandidaten"): kArtikel, ArtNr, Name, Tage ohne Verkauf, Bestand,
   EK, aktueller Preis je Kundengruppe. SQL bleibt SQL, nicht in Python.
3. **Regeln anwenden** in Python — deterministisch und testbar, keine KI.
4. **Sicherheitsnetz** prüfen; was durchfällt, wird als `verworfen` mit
   Begründung gespeichert, nicht stillschweigend übersprungen.
5. **Anzeigen** als Cockpit-Reiter „Preisautomatik" mit Tabelle und Drilldown.
6. **Freigeben** als Formular-Aktion (alles oder Auswahl).
7. **Anwenden** über Weg A oder B.
8. **Kontrollieren** beim nächsten Lauf; Abweichungen werden zu einer Warnung
   in der bestehenden Alert-Engine.

## 5. Was wir dafür NICHT neu bauen

| Braucht es | Vorhanden |
|---|---|
| Kandidatenermittlung | Mapping + SQL-Knoten |
| Nachtlauf | `scheduler_service` |
| Anzeige, Drilldown, Export | Formular-Widgets, `/api/forms/drilldown`, Export-Dienst |
| Warnung bei Abweichung | Alert-Engine (`alert_rules`) |
| Regel-Editor | Muster: `KostenWidget` — ein Widget im Formular, das Domänendaten über eine eigene API pflegt, mandantenbewusst |
| Mandantentrennung | `mandant_service` |
| Preisauflösung | `Preisliste.vPreislisteNetto` (JTLs eigene View) |

Neu ist ausschließlich die Fachlogik: vier Modelle, ein Dienst
(`preisregel_service`), ein API-Modul, ein Regel-Widget, ein Ergebnis-Reiter.

## 6. Invarianten (nicht verhandelbar)

- **Nie unter Einstandspreis** und nie unter der eingestellten Mindestmarge.
  Ein Vorschlag, der das verletzt, wird `verworfen` und ist im Bericht sichtbar.
- **Grundpreise werden in diesem Schritt nicht angefasst** — ausschließlich
  Sonderpreise.
- **Kein Vorschlag ohne Vorher-Wert.** Konnte der Ist-Preis nicht gelesen
  werden, entsteht kein Vorschlag.
- **Nichts wird ohne Freigabe angewandt.** Automatische Freigabe ist eine
  bewusste Einstellung je Regelwerk, kein Standard.
- **Ein zweiter Lauf schlägt nicht erneut vor, was schon angewandt ist** —
  darum der Zustand im Journal.
- **Ausgeschlossene Artikel bleiben ausgeschlossen** (Ausschlussliste aus dem
  `scope`, Muster wie bei den Intrastat-Ausschlussartikeln).

## 7. Offene Punkte

- ~~Zeitraum beim Sonderpreis-Import~~ **geklärt am 2026-08-29 an einem echten
  Artikelstammdaten-Export:** Die Ameise kennt `Sonderpreise aktivieren vom
  (Startdatum)`, `Bis einschließlich (Enddatum)` und `Bis Anzahl im Lager
  kleiner als` — je ARTIKEL, genau wie `tArtikelSonderpreis` der Kopf ist. Die
  Preise stehen je Kundengruppe in einer eigenen Spalte
  (`Sonderpreise: <Gruppe> netto`), kanalabweichende Preise als
  `Verkaufskanal [<Shop>]: Sonderpreis: <Gruppe> netto` — Singular im Kanalfall,
  Plural im Wawi-Fall. Der Entwurf trägt damit unverändert: Der Rabatt läuft
  über das Enddatum von selbst aus, und eine Rücknahme setzt das Enddatum auf
  gestern, statt eine leere Zelle deuten zu müssen.

- Behandlung bereits bestehender Sonderpreise: übersteuern, in Ruhe lassen oder
  als Konflikt melden? Vorschlag: in Ruhe lassen und als Hinweis ausweisen —
  bei PPS sind 439 Sonderpreise von Hand gepflegt.
- Vorher aufräumen: 90 der 439 aktiven PPS-Sonderpreise sind abgelaufen und
  stehen trotzdem auf aktiv. Das gehört bereinigt, bevor eine Automatik
  darüberläuft (`Dashboard.vAbgelaufeneSonderpreise` liefert sie fertig).

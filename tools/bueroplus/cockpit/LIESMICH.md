# Erzeugen der Vorlage „büro+ – GF-Cockpit“

`templates/bueroplus_gf_cockpit.json` wird hieraus erzeugt – nicht von Hand ändern.

```
python3 tools/bueroplus/cockpit/bauen.py templates/bueroplus_gf_cockpit.json tools/bueroplus/cockpit/felder.json
```

- `bauen.py` – Reiter Übersicht, Warnregeln, Formular; bindet `artikel_sql.py` (Reiter Artikel & Warengruppen) ein.
- `felder.json` – Ergebnisspalten je Mapping aus einem Testlauf gegen echte Daten
  (für `output_fields` / `targets.fields`). Neue oder geänderte Abfragen erst gegen die Datenbank
  ausführen und die Spalten hier nachtragen.
- Platzhalter: `{{connection_bp}}`, `{{lieferschein_tage}}`, `{{angebot_tage}}`, `{{ek_faktor}}`, `{{listenpreis}}`.

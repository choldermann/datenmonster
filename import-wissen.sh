#!/usr/bin/env bash
# Holt die KI-Wissensdatenbank aus der alten datenmonster.db in die laufende Instanz.
#
#   ./import-wissen.sh ~/dm-uploads/datenmonster.db                    # nur KI-Gedächtnis
#   ./import-wissen.sh ~/dm-uploads/datenmonster.db --connection-id 1  # + Schema-Wissen
#   ./import-wissen.sh ~/dm-uploads/datenmonster.db --dry-run          # nur zählen
#
# Überträgt ausschließlich Klartext-Wissen (kein Passwort, keine Verbindung) – der
# alte SECRET_KEY wird dafür nicht gebraucht. Wiederholbar: bereits vorhandene
# Einträge werden übersprungen.
set -euo pipefail
cd "$(dirname "$0")"

DB="${1:?Bitte Pfad zur alten datenmonster.db angeben}"; shift
[ -f "$DB" ] || { echo "Nicht gefunden: $DB" >&2; exit 1; }

docker ps --format '{{.Names}}' | grep -qx datenmonster-backend || {
  echo "datenmonster-backend läuft nicht – erst 'docker compose up -d'." >&2; exit 1; }

docker cp "$DB" datenmonster-backend:/tmp/alt.db
docker cp import_wissen.py datenmonster-backend:/tmp/import_wissen.py
docker exec datenmonster-backend python /tmp/import_wissen.py /tmp/alt.db "$@"
docker exec datenmonster-backend rm -f /tmp/alt.db /tmp/import_wissen.py

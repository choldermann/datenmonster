#!/usr/bin/env bash
#
# Datenmonster – Sicherung und Rückspielung
#
# Die Anwendungsdaten liegen nicht im Projektordner, sondern im Docker-Volume
# datenmonster-data: die Datenbank mit allen Mappings, Formularen, Warnregeln,
# Zeitplänen und – verschlüsselt – den Zugangsdaten, dazu die Dateien der
# Datasets. Ein verlorenes Volume ist der Verlust der gesamten Einrichtungsarbeit.
#
# Die Datenbank wird über die SQLite-Sicherungsschnittstelle kopiert, nicht mit
# `cp`: Bei laufendem Schreibzugriff wäre eine einfache Dateikopie unbrauchbar.
#
# Wichtig: Die .env wird mitgesichert. Ohne sie ist die Sicherung wertlos, weil
# sich die Zugangsdaten ohne den SECRET_KEY nicht mehr entschlüsseln lassen.
# Damit enthält das Archiv Geheimnisse – es gehört an einen geschützten Ort.
#
# Verwendung:
#   ./backup.sh                      Sicherung anlegen
#   ./backup.sh --list               vorhandene Sicherungen anzeigen
#   ./backup.sh --restore <archiv>   Sicherung zurückspielen (fragt nach)
#
set -euo pipefail

VERZEICHNIS="${DM_BACKUP_DIR:-./backups}"
BEHALTEN="${DM_BACKUP_KEEP:-14}"          # so viele Sicherungen bleiben liegen
DIENST="backend"
cd "$(dirname "$0")"

fehler() { echo "FEHLER: $*" >&2; exit 1; }

# Vom EXIT-trap benutzt – muss ausserhalb der Funktionen sichtbar sein,
# sonst bricht `set -u` beim Aufräumen ab.
arbeit=""
aufraeumen() { [ -n "${arbeit:-}" ] && rm -rf "$arbeit"; }
trap aufraeumen EXIT

docker compose ps "$DIENST" --format '{{.Status}}' 2>/dev/null | grep -q "Up" \
  || fehler "Der Dienst '$DIENST' läuft nicht – ohne ihn kommt man nicht an die Daten."

# ── Sicherung anlegen ────────────────────────────────────────────────────────
sicherung_anlegen() {
  mkdir -p "$VERZEICHNIS"
  local stempel archiv
  stempel="$(date +%Y%m%d_%H%M%S)"
  archiv="$VERZEICHNIS/datenmonster_$stempel.tar.gz"
  arbeit="$(mktemp -d)"

  echo "Sichere die Datenbank (im laufenden Betrieb konsistent) ..."
  # sqlite3 gibt es im Container nicht, die Python-Schnittstelle tut dasselbe.
  docker compose exec -T "$DIENST" python - <<'PY'
import sqlite3, os
quelle = "/app/uploads/datenmonster.db"
ziel   = "/tmp/datenmonster_sicherung.db"
if not os.path.exists(quelle):
    raise SystemExit(f"Datenbank nicht gefunden: {quelle}")
mit = sqlite3.connect(quelle)
nach = sqlite3.connect(ziel)
with nach:
    mit.backup(nach)          # konsistent, auch wenn gerade geschrieben wird
nach.close(); mit.close()
print(f"  {os.path.getsize(ziel) // 1024} KB gesichert")
PY

  docker compose cp "$DIENST:/tmp/datenmonster_sicherung.db" "$arbeit/datenmonster.db" >/dev/null
  docker compose exec -T "$DIENST" rm -f /tmp/datenmonster_sicherung.db

  echo "Sichere die Dataset-Dateien ..."
  mkdir -p "$arbeit/uploads"
  # Nur die Nutzdaten – die von Hand angelegten .db.bak-* bleiben aussen vor.
  local dateien
  dateien="$(docker compose exec -T "$DIENST" sh -c \
    "find /app/uploads -maxdepth 1 -type f \\( -name 'dataset_*' -o -name '*.xml' -o -name '*.csv' \\) 2>/dev/null" \
    | tr -d '\r')"
  if [ -n "$dateien" ]; then
    while IFS= read -r datei; do
      [ -z "$datei" ] && continue
      docker compose cp "$DIENST:$datei" "$arbeit/uploads/$(basename "$datei")" >/dev/null 2>&1 || true
    done <<< "$dateien"
    echo "  $(ls -1 "$arbeit/uploads" | wc -l) Datei(en)"
  else
    echo "  keine gefunden"
  fi

  if [ -f .env ]; then
    cp .env "$arbeit/.env"
    echo "Sichere die .env (enthält den SECRET_KEY – ohne ihn sind die Zugangsdaten verloren)"
  else
    echo "WARNUNG: keine .env gefunden. Ohne sie lassen sich Zugangsdaten nicht zurückholen." >&2
  fi

  { echo "erstellt=$(date -Iseconds)"
    echo "version=$(cat VERSION 2>/dev/null || echo unbekannt)"
    echo "commit=$(git rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  } > "$arbeit/SICHERUNG.txt"

  tar -czf "$archiv" -C "$arbeit" .
  chmod 600 "$archiv"          # enthält Geheimnisse
  echo
  echo "Fertig: $archiv ($(du -h "$archiv" | cut -f1))"

  local zuviel
  zuviel="$(ls -1t "$VERZEICHNIS"/datenmonster_*.tar.gz 2>/dev/null | tail -n +$((BEHALTEN + 1)) || true)"
  if [ -n "$zuviel" ]; then
    echo "$zuviel" | xargs rm -f
    echo "Ältere Sicherungen entfernt (es bleiben die letzten $BEHALTEN)."
  fi
}

# ── Vorhandene anzeigen ──────────────────────────────────────────────────────
sicherungen_anzeigen() {
  [ -d "$VERZEICHNIS" ] || { echo "Noch keine Sicherungen in $VERZEICHNIS"; return; }
  echo "Sicherungen in $VERZEICHNIS:"
  ls -1t "$VERZEICHNIS"/datenmonster_*.tar.gz 2>/dev/null | while read -r f; do
    printf "  %-52s %s\n" "$(basename "$f")" "$(du -h "$f" | cut -f1)"
  done || echo "  (keine)"
}

# ── Zurückspielen ────────────────────────────────────────────────────────────
zurueckspielen() {
  local archiv="$1"
  [ -f "$archiv" ] || fehler "Archiv nicht gefunden: $archiv"

  echo "ACHTUNG: Das ersetzt die aktuelle Datenbank und die Dataset-Dateien."
  echo "Archiv: $archiv"
  tar -xzOf "$archiv" ./SICHERUNG.txt 2>/dev/null | sed 's/^/  /' || true
  echo
  read -r -p "Wirklich zurückspielen? Dann 'ja' eingeben: " antwort
  [ "$antwort" = "ja" ] || { echo "Abgebrochen."; exit 0; }

  arbeit="$(mktemp -d)"
  tar -xzf "$archiv" -C "$arbeit"

  echo "Halte das Backend an ..."
  docker compose stop "$DIENST" >/dev/null

  echo "Spiele die Datenbank zurück ..."
  docker compose cp "$arbeit/datenmonster.db" "$DIENST:/app/uploads/datenmonster.db" >/dev/null
  if [ -d "$arbeit/uploads" ]; then
    for datei in "$arbeit/uploads"/*; do
      [ -e "$datei" ] || continue
      docker compose cp "$datei" "$DIENST:/app/uploads/$(basename "$datei")" >/dev/null
    done
    echo "  Dataset-Dateien zurückgespielt"
  fi

  echo "Starte das Backend ..."
  docker compose start "$DIENST" >/dev/null
  echo
  echo "Fertig. Die .env aus dem Archiv wurde NICHT automatisch zurückgespielt –"
  echo "prüfe sie von Hand, falls sich der SECRET_KEY unterscheidet:"
  echo "  tar -xzOf '$archiv' ./.env | head"
}

case "${1:-}" in
  --list|-l)      sicherungen_anzeigen ;;
  --restore|-r)   [ $# -ge 2 ] || fehler "Verwendung: $0 --restore <archiv>"; zurueckspielen "$2" ;;
  "")             sicherung_anlegen ;;
  *)              fehler "Unbekannte Option: $1 (siehe Kopf des Skripts)" ;;
esac

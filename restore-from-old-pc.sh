#!/usr/bin/env bash
# Spielt die vom alten PC gesicherten Daten zurück.
#
#   Aufruf:  ./restore-from-old-pc.sh ~/dm-uploads [~/dm-plugins-data]
#
# Erwartet die per "docker cp" gesicherten VERZEICHNISSE (nicht tar.gz):
#   dm-uploads       ← docker cp datenmonster-backend:/app/uploads        (enthält datenmonster.db)
#   dm-plugins-data  ← docker cp datenmonster-plugin-manager:/data
#
# Läuft komplett über "docker cp" – kein Hilfs-Image (alpine), keine Host-Pfade
# unter /var/lib/docker. Funktioniert daher auch mit Docker Desktop / Snap.
#
# WICHTIG: Vorher den SECRET_KEY aus der alten .env in die hiesige .env eintragen.
# Aus ihm wird der Fernet-Key für gespeicherte Verbindungs-Passwörter abgeleitet
# (backend/app/core/config.py:23-25). Ohne den alten Key sind JTL-SQL- und
# Mail-Zugangsdaten in der zurückgespielten DB nicht mehr entschlüsselbar.
set -euo pipefail

cd "$(dirname "$0")"

SRC="${1:?Bitte das gesicherte uploads-Verzeichnis angeben, z.B. ~/dm-uploads}"
PLUGIN_SRC="${2:-}"

[ -d "$SRC" ] || { echo "Kein Verzeichnis: $SRC" >&2; exit 1; }
[ -f "$SRC/datenmonster.db" ] || { echo "In $SRC liegt keine datenmonster.db – falscher Ordner?" >&2; exit 1; }

echo "→ Quelle: $SRC"
ls -la "$SRC"

if ! grep -q '^SECRET_KEY=' .env 2>/dev/null; then
  echo "FEHLER: .env hat keinen SECRET_KEY." >&2; exit 1
fi
echo
echo "→ Aktueller SECRET_KEY in .env: $(grep '^SECRET_KEY=' .env | cut -c1-25)…"
read -rp "  Ist das der Key vom ALTEN PC? [j/N] " ok
[[ "$ok" =~ ^[jJyY]$ ]] || { echo "Abbruch – erst den alten SECRET_KEY in die .env eintragen." >&2; exit 1; }

echo "→ Backend stoppen"
docker compose stop backend

echo "→ Sicherheitskopie des aktuellen Stands"
BAK="pre-restore-$(date +%Y%m%d-%H%M%S)"
docker cp datenmonster-backend:/app/uploads "./$BAK"
echo "  gesichert nach ./$BAK"

echo "→ Alten Stand einspielen"
docker cp "$SRC/." datenmonster-backend:/app/uploads/

if [ -n "$PLUGIN_SRC" ] && [ -d "$PLUGIN_SRC" ]; then
  echo "→ Plugin-Manager-Daten einspielen"
  docker compose stop plugin-manager
  docker cp "$PLUGIN_SRC/." datenmonster-plugin-manager:/data/
  docker compose start plugin-manager
fi

echo "→ Backend starten"
docker compose start backend

echo "→ Warten auf Gesundheit"
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then echo "  Backend ok"; break; fi
  sleep 2
done

echo
echo "→ Inhalt prüfen (Login als admin)"
PW="$(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2-)"
TOKEN="$(curl -s -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=$PW" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("access_token",""))')"
if [ -n "$TOKEN" ]; then
  for e in projects connections mappings forms; do
    printf "  %-12s " "$e"
    curl -s "http://localhost:8000/api/$e/" -H "Authorization: Bearer $TOKEN" \
      | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"{len(d)} Einträge" if isinstance(d,list) else d)'
  done
else
  echo "  Login fehlgeschlagen – ADMIN_PASSWORD in .env setzt das Passwort bei jedem Start neu."
fi

echo
echo "Fertig. Frontend: http://localhost:5174"
echo "Falls Verbindungs-Passwörter nicht funktionieren: falscher SECRET_KEY. Rückweg:"
echo "  docker compose stop backend && docker cp ./$BAK/. datenmonster-backend:/app/uploads/ && docker compose start backend"

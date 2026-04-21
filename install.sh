#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Datenmonster Installer
# Holdermann IT – https://datenmonster.com
#
# Unterstützte Systeme:
#   - Ubuntu 20.04 / 22.04 / 24.04
#   - Debian 11 / 12
#   - macOS 12+ (Monterey und neuer)
#
# Verwendung:
#   curl -fsSL https://install.datenmonster.com/install.sh | bash
#   oder:
#   bash install.sh [--dir /pfad/zum/installationsverzeichnis] [--port 5173] [--no-start]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ─── Farben ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ─── Konfiguration (überschreibbar via Parameter) ─────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-$HOME/datenmonster}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
AUTO_START=true
AUTO_YES=false
GITHUB_REPO="https://github.com/HoldermannIT/datenmonster"
GITHUB_ARCHIVE="https://datenmonster.com/install/datenmonster.zip"

# ─── Parameter parsen ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --dir)        INSTALL_DIR="$2"; shift 2 ;;
    --port)       FRONTEND_PORT="$2"; shift 2 ;;
    --no-start)   AUTO_START=false; shift ;;
    --yes|-y)     AUTO_YES=true; shift ;;
    --help|-h)
      echo "Verwendung: install.sh [--dir PFAD] [--port PORT] [--no-start]"
      echo "  --dir       Installationsverzeichnis (Standard: ~/datenmonster)"
      echo "  --port      Frontend-Port (Standard: 5173)"
      echo "  --no-start  Nur installieren, nicht starten"
      exit 0
      ;;
    *) echo "Unbekannter Parameter: $1"; exit 1 ;;
  esac
done

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

print_banner() {
  echo ""
  echo -e "${CYAN}${BOLD}"
  echo "  ██████╗  █████╗ ████████╗███████╗███╗   ██╗"
  echo "  ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝████╗  ██║"
  echo "  ██║  ██║███████║   ██║   █████╗  ██╔██╗ ██║"
  echo "  ██║  ██║██╔══██║   ██║   ██╔══╝  ██║╚██╗██║"
  echo "  ██████╔╝██║  ██║   ██║   ███████╗██║ ╚████║"
  echo "  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═══╝"
  echo ""
  echo "  ███╗   ███╗ ██████╗ ███╗   ██╗███████╗████████╗███████╗██████╗"
  echo "  ████╗ ████║██╔═══██╗████╗  ██║██╔════╝╚══██╔══╝██╔════╝██╔══██╗"
  echo "  ██╔████╔██║██║   ██║██╔██╗ ██║███████╗   ██║   █████╗  ██████╔╝"
  echo "  ██║╚██╔╝██║██║   ██║██║╚██╗██║╚════██║   ██║   ██╔══╝  ██╔══██╗"
  echo "  ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║███████║   ██║   ███████╗██║  ██║"
  echo "  ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"
  echo -e "${NC}"
  echo -e "  ${BOLD}ETL & Datenintegration – by Holdermann IT${NC}"
  echo -e "  ${BLUE}https://datenmonster.com${NC}"
  echo ""
}

log_step() { echo -e "\n${BLUE}${BOLD}▶ $1${NC}"; }
log_ok()   { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_err()  { echo -e "${RED}✗ $1${NC}" >&2; }
log_info() { echo -e "  ${CYAN}$1${NC}"; }

die() { log_err "$1"; exit 1; }

# Zufälliges Passwort (32 Zeichen)
gen_password() {
  LC_ALL=C tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 32 || true
}

# ─── OS-Erkennung ─────────────────────────────────────────────────────────────

detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    PKG_MGR="brew"
  elif [[ -f /etc/os-release ]]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian|linuxmint|pop)
        OS="debian"
        PKG_MGR="apt"
        ;;
      fedora|rhel|centos|rocky|almalinux)
        OS="rhel"
        PKG_MGR="dnf"
        ;;
      *)
        OS="linux"
        PKG_MGR="unknown"
        ;;
    esac
  else
    OS="unknown"
    PKG_MGR="unknown"
  fi
  log_info "Erkanntes System: ${OS} (${PKG_MGR})"
}

# ─── Voraussetzungen prüfen / installieren ────────────────────────────────────

check_command() {
  command -v "$1" &>/dev/null
}

install_docker_debian() {
  log_info "Installiere Docker via apt..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release

  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

  # Aktuellen User zur docker-Gruppe hinzufügen
  sudo usermod -aG docker "$USER" || true
  log_ok "Docker installiert"
}

install_docker_macos() {
  if check_command brew; then
    log_info "Installiere Docker Desktop via Homebrew..."
    brew install --cask docker
    log_warn "Bitte Docker Desktop manuell starten und dann dieses Script erneut ausführen."
    exit 0
  else
    die "Homebrew nicht gefunden. Bitte Docker Desktop manuell installieren: https://www.docker.com/products/docker-desktop/"
  fi
}

check_dependencies() {
  log_step "Prüfe Voraussetzungen"

  # Docker
  if check_command docker; then
    DOCKER_VERSION=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    log_ok "Docker gefunden (v${DOCKER_VERSION})"
  else
    log_warn "Docker nicht gefunden – wird installiert..."
    case "$OS" in
      debian) install_docker_debian ;;
      macos)  install_docker_macos ;;
      *)      die "Bitte Docker manuell installieren: https://docs.docker.com/get-docker/" ;;
    esac
  fi

  # Docker Compose (v2 als Plugin oder standalone)
  if docker compose version &>/dev/null 2>&1; then
    log_ok "Docker Compose v2 gefunden"
    COMPOSE_CMD="docker compose"
  elif check_command docker-compose; then
    log_ok "Docker Compose v1 gefunden"
    COMPOSE_CMD="docker-compose"
  else
    die "Docker Compose nicht gefunden. Bitte manuell installieren."
  fi

  # Docker läuft?
  if ! docker info &>/dev/null; then
    die "Docker-Daemon läuft nicht. Bitte Docker starten und erneut versuchen."
  fi

  # curl oder wget
  if check_command curl; then
    DOWNLOAD_CMD="curl -fsSL"
  elif check_command wget; then
    DOWNLOAD_CMD="wget -qO-"
  else
    die "curl oder wget wird benötigt."
  fi

  # unzip
  if ! check_command unzip; then
    log_warn "unzip nicht gefunden – wird installiert..."
    case "$PKG_MGR" in
      apt) sudo apt-get install -y -qq unzip ;;
      brew) brew install unzip ;;
      dnf) sudo dnf install -y unzip ;;
    esac
  fi

  # git (optional, für spätere Updates)
  if check_command git; then
    log_ok "Git gefunden"
  else
    log_warn "Git nicht gefunden (optional, wird für Updates benötigt)"
  fi
}

# ─── Download & Entpacken ─────────────────────────────────────────────────────

download_datenmonster() {
  log_step "Lade Datenmonster herunter"

  if [[ -d "$INSTALL_DIR" ]]; then
    log_warn "Verzeichnis $INSTALL_DIR existiert bereits."
    read -rp "  Überschreiben? [j/N] " confirm
    if [[ "$confirm" != "j" && "$confirm" != "J" && "$confirm" != "y" && "$confirm" != "Y" ]]; then
      log_info "Installation abgebrochen."
      exit 0
    fi
    # Backup der .env falls vorhanden
    if [[ -f "$INSTALL_DIR/.env" ]]; then
      cp "$INSTALL_DIR/.env" "/tmp/datenmonster_env_backup"
      log_info "Bestehende .env gesichert"
    fi
    rm -rf "$INSTALL_DIR"
  fi

  mkdir -p "$INSTALL_DIR"

  # Download via git clone (bevorzugt) oder ZIP-Fallback
  if check_command git; then
    log_info "Klone Repository..."
    git clone --depth 1 "$GITHUB_REPO.git" "$INSTALL_DIR" 2>/dev/null \
      || { log_warn "Git clone fehlgeschlagen, versuche ZIP-Download..."; download_zip; }
  else
    download_zip
  fi

  log_ok "Datenmonster heruntergeladen nach: $INSTALL_DIR"
}

download_zip() {
  local tmp_zip="/tmp/datenmonster_install.zip"
  log_info "Lade ZIP von GitHub..."
  if check_command curl; then
    curl -fsSL "$GITHUB_ARCHIVE" -o "$tmp_zip"
  else
    wget -q "$GITHUB_ARCHIVE" -O "$tmp_zip"
  fi
  unzip -q "$tmp_zip" -d "/tmp/datenmonster_extract"
  # GitHub benennt das Verzeichnis main-branch
  local extracted_dir
  extracted_dir=$(find /tmp/datenmonster_extract -maxdepth 1 -mindepth 1 -type d | head -1)
  cp -r "$extracted_dir/." "$INSTALL_DIR/"
  rm -rf "$tmp_zip" "/tmp/datenmonster_extract"
}

# ─── Konfiguration & .env ─────────────────────────────────────────────────────

configure() {
  log_step "Konfiguriere Datenmonster"

  local env_file="$INSTALL_DIR/.env"

  # Bestehende .env wiederherstellen falls Backup vorhanden
  if [[ -f "/tmp/datenmonster_env_backup" ]]; then
    cp "/tmp/datenmonster_env_backup" "$env_file"
    rm -f "/tmp/datenmonster_env_backup"
    log_ok ".env aus vorheriger Installation wiederhergestellt"
    return
  fi

  # Neue .env generieren
  local SECRET_KEY
  local ADMIN_PASSWORD
  SECRET_KEY=$(gen_password)
  ADMIN_PASSWORD=$(gen_password)

  cat > "$env_file" << EOF
# Datenmonster Konfiguration
# Generiert am: $(date)
# ACHTUNG: Diese Datei enthält Passwörter – nicht in Git einchecken!

# ─── Ports ────────────────────────────────────────────────────────────────────
FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}

# ─── Sicherheit ───────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ─── Admin-Account ────────────────────────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# ─── Datenbank ────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite:////data/datenmonster.db

# ─── Upload-Verzeichnis ───────────────────────────────────────────────────────
UPLOAD_DIR=/data/uploads
EOF

  log_ok ".env mit zufälligen Passwörtern generiert"
  log_info "Admin-Passwort: ${BOLD}${ADMIN_PASSWORD}${NC}"
  log_warn "Das Passwort wird nur einmal angezeigt – bitte jetzt notieren!"

  # Passwort auch in separate Datei schreiben für sicheres Ablesen
  echo "$ADMIN_PASSWORD" > "$INSTALL_DIR/.admin_password"
  chmod 600 "$INSTALL_DIR/.admin_password"
  log_info "Passwort auch gespeichert in: $INSTALL_DIR/.admin_password"
}

# ─── docker-compose.yml anpassen ──────────────────────────────────────────────

patch_compose() {
  local compose_file="$INSTALL_DIR/docker-compose.yml"
  if [[ ! -f "$compose_file" ]]; then
    log_warn "docker-compose.yml nicht gefunden – überspringe Port-Anpassung"
    return
  fi

  # Port anpassen falls nicht Standard
  if [[ "$FRONTEND_PORT" != "5173" ]]; then
    sed -i.bak "s/5173:5173/${FRONTEND_PORT}:5173/g" "$compose_file"
    log_info "Frontend-Port auf ${FRONTEND_PORT} gesetzt"
  fi
  if [[ "$BACKEND_PORT" != "8000" ]]; then
    sed -i.bak "s/8000:8000/${BACKEND_PORT}:8000/g" "$compose_file"
    log_info "Backend-Port auf ${BACKEND_PORT} gesetzt"
  fi
}

# ─── Container bauen & starten ────────────────────────────────────────────────

start_containers() {
  log_step "Baue und starte Container"
  log_info "Das kann beim ersten Start 3-5 Minuten dauern..."

  cd "$INSTALL_DIR"

  # Build
  $COMPOSE_CMD build --quiet 2>&1 | while IFS= read -r line; do
    echo -e "  ${line}"
  done

  # Start
  $COMPOSE_CMD up -d

  log_ok "Container gestartet"
}

# ─── Warten bis Backend erreichbar ist ───────────────────────────────────────

wait_for_backend() {
  log_step "Warte auf Backend..."
  local max_attempts=30
  local attempt=0
  local url="http://localhost:${BACKEND_PORT}/api/health"

  while [[ $attempt -lt $max_attempts ]]; do
    if curl -sf "$url" &>/dev/null; then
      log_ok "Backend ist erreichbar"
      return 0
    fi
    attempt=$((attempt + 1))
    echo -ne "  Versuch ${attempt}/${max_attempts}...\r"
    sleep 3
  done

  log_warn "Backend antwortet noch nicht – möglicherweise läuft der Start noch."
  log_info "Prüfe mit: docker compose logs backend --tail=20"
}

# ─── Admin-User anlegen ───────────────────────────────────────────────────────

setup_admin() {
  log_step "Richte Admin-Account ein"

  local env_file="$INSTALL_DIR/.env"
  local admin_user admin_pass
  admin_user=$(grep "ADMIN_USERNAME=" "$env_file" | cut -d'=' -f2)
  admin_pass=$(grep "ADMIN_PASSWORD=" "$env_file" | cut -d'=' -f2)

  # Warten bis API antwortet
  local url="http://localhost:${BACKEND_PORT}"
  sleep 2

  # Admin anlegen via API (falls noch nicht vorhanden)
  local response
  response=$(curl -sf -X POST "${url}/api/auth/setup" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"${admin_user}\", \"password\": \"${admin_pass}\"}" 2>/dev/null || echo "skip")

  if [[ "$response" == "skip" ]]; then
    log_warn "Admin-Setup-Endpoint nicht erreichbar – Admin wird beim ersten Start automatisch angelegt"
  else
    log_ok "Admin-Account eingerichtet"
  fi
}

# ─── Abschluss ────────────────────────────────────────────────────────────────

print_success() {
  local admin_pass
  admin_pass=$(cat "$INSTALL_DIR/.admin_password" 2>/dev/null || echo "siehe $INSTALL_DIR/.env")

  echo ""
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  ✓ Datenmonster erfolgreich installiert!${NC}"
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════${NC}"
  echo ""
  echo -e "  ${BOLD}URL:${NC}           http://localhost:${FRONTEND_PORT}"
  echo -e "  ${BOLD}Benutzer:${NC}      admin"
  echo -e "  ${BOLD}Passwort:${NC}      ${YELLOW}${admin_pass}${NC}"
  echo ""
  echo -e "  ${BOLD}Installation:${NC}  ${INSTALL_DIR}"
  echo ""
  echo -e "  ${CYAN}Nützliche Befehle:${NC}"
  echo -e "  cd ${INSTALL_DIR}"
  echo -e "  docker compose logs -f          # Live-Logs"
  echo -e "  docker compose restart          # Neustart"
  echo -e "  docker compose down             # Stoppen"
  echo -e "  docker compose up -d            # Starten"
  echo ""
  echo -e "  ${BOLD}Dokumentation:${NC}  https://datenmonster.com/docs"
  echo -e "  ${BOLD}Support:${NC}        https://datenmonster.com/support"
  echo ""
}

# ─── Update-Funktion ──────────────────────────────────────────────────────────

do_update() {
  log_step "Aktualisiere Datenmonster"

  if [[ ! -d "$INSTALL_DIR" ]]; then
    die "Datenmonster nicht gefunden unter: $INSTALL_DIR – bitte zuerst installieren."
  fi

  cd "$INSTALL_DIR"

  # .env sichern
  cp .env /tmp/datenmonster_env_backup

  if [[ -d ".git" ]]; then
    log_info "Aktualisiere via git pull..."
    git pull origin main
  else
    log_info "Lade neue Version herunter..."
    download_zip
  fi

  # .env wiederherstellen
  cp /tmp/datenmonster_env_backup .env
  rm -f /tmp/datenmonster_env_backup

  # Container neu bauen
  $COMPOSE_CMD build --quiet
  $COMPOSE_CMD up -d

  log_ok "Update abgeschlossen"
}

# ─── Hauptprogramm ────────────────────────────────────────────────────────────

main() {
  print_banner

  # Update-Modus?
  if [[ "${1:-}" == "update" ]]; then
    detect_os
    do_update
    exit 0
  fi

  echo -e "${BOLD}Installationsverzeichnis:${NC} $INSTALL_DIR"
  echo -e "${BOLD}Frontend-Port:${NC}            $FRONTEND_PORT"
  echo -e "${BOLD}Backend-Port:${NC}             $BACKEND_PORT"
  echo ""
  if [[ "$AUTO_YES" != "true" ]]; then
    read -rp "Fortfahren? [J/n] " confirm
    if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
      echo "Installation abgebrochen."
      exit 0
    fi
  fi

  detect_os
  check_dependencies
  download_datenmonster
  configure
  patch_compose

  if [[ "$AUTO_START" == true ]]; then
    start_containers
    wait_for_backend
    setup_admin
    print_success
  else
    echo ""
    log_ok "Installation abgeschlossen (--no-start: Container nicht gestartet)"
    log_info "Starten mit: cd $INSTALL_DIR && docker compose up -d"
  fi
}

main "$@"

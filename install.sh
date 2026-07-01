#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Datenmonster Installer
# Holdermann IT – https://datenmonster.com
#
# Verwendung:
#   curl -fsSL https://raw.githubusercontent.com/choldermann/datenmonster/main/install.sh | bash
#   oder:
#   bash install.sh [--dir /pfad] [--port 5174] [--no-start] [--yes]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-$HOME/datenmonster}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
AUTO_START=true
AUTO_YES=false
GITHUB_RAW="https://raw.githubusercontent.com/choldermann/datenmonster/main"

while [[ $# -gt 0 ]]; do
  case $1 in
    --dir)      INSTALL_DIR="$2"; shift 2 ;;
    --port)     FRONTEND_PORT="$2"; shift 2 ;;
    --no-start) AUTO_START=false; shift ;;
    --yes|-y)   AUTO_YES=true; shift ;;
    --help|-h)
      echo "Verwendung: install.sh [--dir PFAD] [--port PORT] [--no-start] [--yes]"
      exit 0 ;;
    *) echo "Unbekannter Parameter: $1"; exit 1 ;;
  esac
done

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
die()      { log_err "$1"; exit 1; }

gen_password() {
  LC_ALL=C tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 32 || true
}

detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"; PKG_MGR="brew"
  elif [[ -f /etc/os-release ]]; then
    . /etc/os-release
    case "$ID" in
      ubuntu|debian|linuxmint|pop) OS="debian"; PKG_MGR="apt" ;;
      fedora|rhel|centos|rocky|almalinux) OS="rhel"; PKG_MGR="dnf" ;;
      *) OS="linux"; PKG_MGR="unknown" ;;
    esac
  else
    OS="unknown"; PKG_MGR="unknown"
  fi
  log_info "Erkanntes System: ${OS}"
}

install_docker_debian() {
  log_info "Installiere Docker via apt..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg
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
  sudo usermod -aG docker "$USER" || true
  log_ok "Docker installiert"
}

check_dependencies() {
  log_step "Prüfe Voraussetzungen"

  if command -v docker &>/dev/null; then
    log_ok "Docker $(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1) gefunden"
  else
    log_warn "Docker nicht gefunden – wird installiert..."
    case "$OS" in
      debian) install_docker_debian ;;
      *) die "Bitte Docker manuell installieren: https://docs.docker.com/get-docker/" ;;
    esac
  fi

  if docker compose version &>/dev/null 2>&1; then
    log_ok "Docker Compose v2 gefunden"
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose &>/dev/null; then
    log_ok "Docker Compose v1 gefunden"
    COMPOSE_CMD="docker-compose"
  else
    die "Docker Compose nicht gefunden."
  fi

  if ! docker info &>/dev/null; then
    die "Docker-Daemon läuft nicht. Bitte Docker starten und erneut versuchen."
  fi
}

download_config() {
  log_step "Lade Konfiguration von GitHub"

  if [[ -d "$INSTALL_DIR" ]]; then
    log_warn "Verzeichnis $INSTALL_DIR existiert bereits."
    if [[ "$AUTO_YES" != "true" ]]; then
      read -rp "  Fortfahren (bestehende Konfiguration bleibt erhalten)? [J/n] " confirm </dev/tty
      if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
        log_info "Installation abgebrochen."
        exit 0
      fi
    fi
    # .env sichern
    if [[ -f "$INSTALL_DIR/.env" ]]; then
      cp "$INSTALL_DIR/.env" "/tmp/datenmonster_env_backup"
      log_info "Bestehende .env gesichert"
    fi
  fi

  mkdir -p "$INSTALL_DIR/data"
  cd "$INSTALL_DIR"

  curl -fsSL "${GITHUB_RAW}/docker-compose.yml" -o docker-compose.yml
  log_ok "docker-compose.yml geladen"
}

configure() {
  log_step "Konfiguriere Datenmonster"

  local env_file="$INSTALL_DIR/.env"

  if [[ -f "/tmp/datenmonster_env_backup" ]]; then
    cp "/tmp/datenmonster_env_backup" "$env_file"
    rm -f "/tmp/datenmonster_env_backup"
    log_ok ".env aus vorheriger Installation wiederhergestellt"
    return
  fi

  local SECRET_KEY ADMIN_PASSWORD
  SECRET_KEY=$(gen_password)
  ADMIN_PASSWORD=$(gen_password)

  # Server-IP für CORS ermitteln
  local SERVER_IP
  SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

  cat > "$env_file" << EOF
# Datenmonster Konfiguration
# Generiert am: $(date)

# ─── Ports ────────────────────────────────────────────────────────────────────
FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}

# ─── Sicherheit ───────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}

# ─── Admin-Account ────────────────────────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# ─── CORS (Browser-Zugriff auf Backend) ───────────────────────────────────────
ALLOWED_ORIGINS=http://${SERVER_IP}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}

# ─── GitHub Token (optional, erhöht Rate-Limit für Update-Check) ──────────────
GITHUB_TOKEN=
EOF

  log_ok ".env mit zufälligen Passwörtern generiert"
  log_info "Admin-Passwort: ${BOLD}${ADMIN_PASSWORD}${NC}"
  log_warn "Das Passwort wird nur einmal angezeigt – bitte jetzt notieren!"

  echo "$ADMIN_PASSWORD" > "$INSTALL_DIR/.admin_password"
  chmod 600 "$INSTALL_DIR/.admin_password"
  log_info "Passwort auch gespeichert in: $INSTALL_DIR/.admin_password"
}

patch_compose() {
  local compose_file="$INSTALL_DIR/docker-compose.yml"
  [[ ! -f "$compose_file" ]] && return

  if [[ "$FRONTEND_PORT" != "5174" ]]; then
    sed -i.bak "s/5174:80/${FRONTEND_PORT}:80/g" "$compose_file"
    log_info "Frontend-Port auf ${FRONTEND_PORT} gesetzt"
  fi
  if [[ "$BACKEND_PORT" != "8000" ]]; then
    sed -i.bak "s/8000:8000/${BACKEND_PORT}:8000/g" "$compose_file"
    log_info "Backend-Port auf ${BACKEND_PORT} gesetzt"
  fi
  rm -f "${compose_file}.bak"
}

start_containers() {
  log_step "Lade Container-Images und starte Datenmonster"
  log_info "Das kann beim ersten Start 5-10 Minuten dauern (Ollama-Image ~1,5 GB)..."

  cd "$INSTALL_DIR"

  $COMPOSE_CMD pull
  $COMPOSE_CMD up -d

  log_ok "Container gestartet"
}

wait_for_backend() {
  log_step "Warte auf Backend..."
  local max_attempts=40
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

  log_warn "Backend antwortet noch nicht. Prüfe mit: docker compose logs backend --tail=20"
}

setup_admin() {
  log_step "Richte Admin-Account ein"

  local env_file="$INSTALL_DIR/.env"
  local admin_user admin_pass
  admin_user=$(grep "ADMIN_USERNAME=" "$env_file" | cut -d'=' -f2)
  admin_pass=$(grep "ADMIN_PASSWORD=" "$env_file" | cut -d'=' -f2)

  sleep 2

  local response
  response=$(curl -sf -X POST "http://localhost:${BACKEND_PORT}/api/auth/setup" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"${admin_user}\", \"password\": \"${admin_pass}\"}" 2>/dev/null || echo "skip")

  if [[ "$response" == "skip" ]]; then
    log_warn "Admin wird beim ersten Start automatisch angelegt"
  else
    log_ok "Admin-Account eingerichtet"
  fi
}

print_success() {
  local admin_pass
  admin_pass=$(cat "$INSTALL_DIR/.admin_password" 2>/dev/null || echo "siehe $INSTALL_DIR/.env")

  local server_ip
  server_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

  echo ""
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}${BOLD}  ✓ Datenmonster erfolgreich installiert!${NC}"
  echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════${NC}"
  echo ""
  echo -e "  ${BOLD}URL:${NC}           http://${server_ip}:${FRONTEND_PORT}"
  echo -e "  ${BOLD}Benutzer:${NC}      admin"
  echo -e "  ${BOLD}Passwort:${NC}      ${YELLOW}${admin_pass}${NC}"
  echo ""
  echo -e "  ${BOLD}Installation:${NC}  ${INSTALL_DIR}"
  echo ""
  echo -e "  ${CYAN}Nützliche Befehle:${NC}"
  echo -e "  cd ${INSTALL_DIR}"
  echo -e "  docker compose logs -f          # Live-Logs"
  echo -e "  docker compose pull && docker compose up -d  # Manuelles Update"
  echo -e "  docker compose down             # Stoppen"
  echo ""
  echo -e "  ${BOLD}Dokumentation:${NC}  https://datenmonster.com/docs"
  echo ""
}

main() {
  print_banner

  echo -e "${BOLD}Installationsverzeichnis:${NC} $INSTALL_DIR"
  echo -e "${BOLD}Frontend-Port:${NC}            $FRONTEND_PORT"
  echo -e "${BOLD}Backend-Port:${NC}             $BACKEND_PORT"
  echo ""
  if [[ "$AUTO_YES" != "true" ]]; then
    read -rp "Fortfahren? [J/n] " confirm </dev/tty
    if [[ "$confirm" == "n" || "$confirm" == "N" ]]; then
      echo "Installation abgebrochen."
      exit 0
    fi
  fi

  detect_os
  check_dependencies
  download_config
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

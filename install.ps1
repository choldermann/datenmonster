# ─────────────────────────────────────────────────────────────────────────────
# Datenmonster Installer für Windows
# Holdermann IT – https://datenmonster.com
#
# Voraussetzungen:
#   - Windows 10/11 (64-bit)
#   - PowerShell 5.1 oder neuer
#   - Internetverbindung
#
# Verwendung (als Administrator in PowerShell):
#   irm https://install.datenmonster.com/install.ps1 | iex
#   oder:
#   .\install.ps1 [-InstallDir "C:\datenmonster"] [-FrontendPort 5173] [-NoStart]
# ─────────────────────────────────────────────────────────────────────────────

param(
    [string]$InstallDir = "$env:USERPROFILE\datenmonster",
    [int]$FrontendPort = 5173,
    [int]$BackendPort = 8000,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

# ─── Farben & Ausgabe ─────────────────────────────────────────────────────────

function Write-Banner {
    $banner = @"

  ██████╗  █████╗ ████████╗███████╗███╗   ██╗
  ██╔══██╗██╔══██╗╚══██╔══╝██╔════╝████╗  ██║
  ██║  ██║███████║   ██║   █████╗  ██╔██╗ ██║
  ██║  ██║██╔══██║   ██║   ██╔══╝  ██║╚██╗██║
  ██████╔╝██║  ██║   ██║   ███████╗██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═══╝

  MONSTER – ETL & Datenintegration
  by Holdermann IT – https://datenmonster.com
"@
    Write-Host $banner -ForegroundColor Cyan
}

function Write-Step   { param($msg) Write-Host "`n▶ $msg" -ForegroundColor Blue }
function Write-Ok     { param($msg) Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "✗ $msg" -ForegroundColor Red }
function Write-Info   { param($msg) Write-Host "  $msg" -ForegroundColor Cyan }

function New-Password {
    $chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#%^&*"
    -join ((1..32) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

# ─── Admin-Prüfung ────────────────────────────────────────────────────────────

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ─── Docker prüfen / installieren ────────────────────────────────────────────

function Test-DockerInstalled {
    try { docker --version | Out-Null; return $true }
    catch { return $false }
}

function Install-Docker {
    Write-Info "Docker Desktop wird heruntergeladen..."
    $installerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    $installerPath = "$env:TEMP\DockerDesktopInstaller.exe"

    Write-Info "Lade Docker Desktop Installer herunter (~500 MB)..."
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

    Write-Info "Installiere Docker Desktop..."
    Start-Process -FilePath $installerPath -Args "install --quiet" -Wait

    Write-Warn "Docker Desktop wurde installiert."
    Write-Warn "Bitte Windows neu starten und dann dieses Script erneut ausführen."
    Write-Warn "Nach dem Neustart: Docker Desktop starten und warten bis es läuft."
    Read-Host "Drücke Enter zum Beenden"
    exit 0
}

function Get-ComposeCommand {
    # Docker Compose v2 (Plugin)
    try { docker compose version | Out-Null; return "docker compose" }
    catch {}
    # Docker Compose v1 (standalone)
    try { docker-compose --version | Out-Null; return "docker-compose" }
    catch {}
    return $null
}

# ─── Voraussetzungen ─────────────────────────────────────────────────────────

function Test-Dependencies {
    Write-Step "Prüfe Voraussetzungen"

    # Windows Version
    $winVer = [System.Environment]::OSVersion.Version
    if ($winVer.Major -lt 10) {
        throw "Windows 10 oder neuer erforderlich."
    }
    Write-Ok "Windows Version OK"

    # WSL2 / Hyper-V
    $wsl = Get-WindowsOptionalFeature -Online -FeatureName "VirtualMachinePlatform" -ErrorAction SilentlyContinue
    if ($wsl -and $wsl.State -ne "Enabled") {
        Write-Warn "WSL2 / Virtualisierung nicht aktiv – Docker Desktop benötigt dies."
        Write-Info "Aktiviere mit: wsl --install"
    }

    # Docker
    if (Test-DockerInstalled) {
        $dockerVersion = docker --version
        Write-Ok "Docker gefunden: $dockerVersion"
    } else {
        Write-Warn "Docker nicht gefunden – wird installiert..."
        Install-Docker
    }

    # Docker läuft?
    try {
        docker info | Out-Null
        Write-Ok "Docker-Daemon läuft"
    } catch {
        throw "Docker-Daemon läuft nicht. Bitte Docker Desktop starten und erneut versuchen."
    }

    # Docker Compose
    $script:ComposeCmd = Get-ComposeCommand
    if (-not $script:ComposeCmd) {
        throw "Docker Compose nicht gefunden."
    }
    Write-Ok "Docker Compose gefunden"
}

# ─── Download ─────────────────────────────────────────────────────────────────

function Get-Datenmonster {
    Write-Step "Lade Datenmonster herunter"

    if (Test-Path $InstallDir) {
        Write-Warn "Verzeichnis $InstallDir existiert bereits."
        $confirm = Read-Host "Überschreiben? [j/N]"
        if ($confirm -notmatch "^[jJyY]$") {
            Write-Info "Installation abgebrochen."
            exit 0
        }
        # .env sichern
        if (Test-Path "$InstallDir\.env") {
            Copy-Item "$InstallDir\.env" "$env:TEMP\datenmonster_env_backup"
            Write-Info "Bestehende .env gesichert"
        }
        Remove-Item $InstallDir -Recurse -Force
    }

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

    $zipUrl = "https://github.com/HoldermannIT/datenmonster/archive/refs/heads/main.zip"
    $zipPath = "$env:TEMP\datenmonster.zip"
    $extractPath = "$env:TEMP\datenmonster_extract"

    Write-Info "Lade ZIP von GitHub..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

    Write-Info "Entpacke..."
    if (Test-Path $extractPath) { Remove-Item $extractPath -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

    # GitHub benennt das Verzeichnis nach dem Branch
    $extractedDir = Get-ChildItem $extractPath -Directory | Select-Object -First 1
    Copy-Item "$($extractedDir.FullName)\*" $InstallDir -Recurse -Force

    Remove-Item $zipPath, $extractPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Ok "Datenmonster heruntergeladen nach: $InstallDir"
}

# ─── Konfiguration ────────────────────────────────────────────────────────────

function New-Configuration {
    Write-Step "Konfiguriere Datenmonster"

    $envFile = "$InstallDir\.env"

    # Bestehende .env wiederherstellen
    if (Test-Path "$env:TEMP\datenmonster_env_backup") {
        Copy-Item "$env:TEMP\datenmonster_env_backup" $envFile
        Remove-Item "$env:TEMP\datenmonster_env_backup" -Force
        Write-Ok ".env aus vorheriger Installation wiederhergestellt"
        return
    }

    $secretKey = New-Password
    $adminPassword = New-Password

    $envContent = @"
# Datenmonster Konfiguration
# Generiert am: $(Get-Date -Format "dd.MM.yyyy HH:mm")

# Ports
FRONTEND_PORT=$FrontendPort
BACKEND_PORT=$BackendPort

# Sicherheit
SECRET_KEY=$secretKey
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# Admin-Account
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$adminPassword

# Datenbank
DATABASE_URL=sqlite:////data/datenmonster.db

# Upload-Verzeichnis
UPLOAD_DIR=/data/uploads
"@

    Set-Content -Path $envFile -Value $envContent -Encoding UTF8

    # Passwort separat speichern
    Set-Content -Path "$InstallDir\.admin_password" -Value $adminPassword -Encoding UTF8

    Write-Ok ".env generiert"
    Write-Host ""
    Write-Host "  Admin-Passwort: " -NoNewline
    Write-Host $adminPassword -ForegroundColor Yellow
    Write-Warn "Das Passwort wird nur einmal angezeigt – bitte jetzt notieren!"
    Write-Info "Passwort gespeichert in: $InstallDir\.admin_password"
}

# ─── Container starten ───────────────────────────────────────────────────────

function Start-Containers {
    Write-Step "Baue und starte Container"
    Write-Info "Das kann beim ersten Start 3-5 Minuten dauern..."

    Set-Location $InstallDir

    # Build
    Invoke-Expression "$($script:ComposeCmd) build"

    # Start
    Invoke-Expression "$($script:ComposeCmd) up -d"

    Write-Ok "Container gestartet"
}

# ─── Warten auf Backend ───────────────────────────────────────────────────────

function Wait-ForBackend {
    Write-Step "Warte auf Backend..."
    $url = "http://localhost:$BackendPort/api/health"
    $maxAttempts = 30

    for ($i = 1; $i -le $maxAttempts; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Ok "Backend ist erreichbar"
                return
            }
        } catch {}
        Write-Host "  Versuch $i/$maxAttempts..." -NoNewline
        Write-Host "`r" -NoNewline
        Start-Sleep -Seconds 3
    }
    Write-Warn "Backend antwortet noch nicht – möglicherweise läuft der Start noch."
}

# ─── Abschluss ────────────────────────────────────────────────────────────────

function Write-Success {
    $adminPass = Get-Content "$InstallDir\.admin_password" -ErrorAction SilentlyContinue
    if (-not $adminPass) { $adminPass = "siehe $InstallDir\.env" }

    Write-Host ""
    Write-Host "════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  ✓ Datenmonster erfolgreich installiert!" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Write-Host "  URL:           " -NoNewline; Write-Host "http://localhost:$FrontendPort" -ForegroundColor Cyan
    Write-Host "  Benutzer:      admin"
    Write-Host "  Passwort:      " -NoNewline; Write-Host $adminPass -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Installation:  $InstallDir"
    Write-Host ""
    Write-Host "  Nützliche Befehle:" -ForegroundColor Cyan
    Write-Host "  cd $InstallDir"
    Write-Host "  docker compose logs -f          # Live-Logs"
    Write-Host "  docker compose restart          # Neustart"
    Write-Host "  docker compose down             # Stoppen"
    Write-Host "  docker compose up -d            # Starten"
    Write-Host ""
    Write-Host "  Dokumentation:  https://datenmonster.com/docs" -ForegroundColor Cyan
    Write-Host ""
}

# ─── Hauptprogramm ────────────────────────────────────────────────────────────

function Main {
    Write-Banner

    Write-Host "Installationsverzeichnis: $InstallDir"
    Write-Host "Frontend-Port:            $FrontendPort"
    Write-Host "Backend-Port:             $BackendPort"
    Write-Host ""

    $confirm = Read-Host "Fortfahren? [J/n]"
    if ($confirm -match "^[nN]$") {
        Write-Host "Installation abgebrochen."
        exit 0
    }

    Test-Dependencies
    Get-Datenmonster
    New-Configuration

    if (-not $NoStart) {
        Start-Containers
        Wait-ForBackend
        Write-Success
    } else {
        Write-Ok "Installation abgeschlossen (--NoStart: Container nicht gestartet)"
        Write-Info "Starten mit: cd $InstallDir; docker compose up -d"
    }
}

Main

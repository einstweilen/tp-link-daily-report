#!/usr/bin/env bash
#
# Installationsskript für tp-report.py
# Dieses Skript führt die Schritte zur lokalen Einrichtung aus.
#



# Farben
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# Hilfsfunktionen
info() { echo -e "  ${BLUE}ℹ${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
error() { echo -e "  ${RED}✗${NC} $1"; }
step() { echo -e "\n${BOLD}==> $1${NC}"; }
prompt_text() { echo -ne "  ${YELLOW}?${NC} $1"; }

main() {
    echo -e "${BOLD}==== tp-report Installation ====${NC}"

    BASE_URL="https://raw.githubusercontent.com/einstweilen/tp-link-daily-report/main"
    TARGET_DIR="tp-report"

    # 1. Schritt: Prüfen, ob wir uns bereits im Projektordner befinden (z.B. nach git clone)
    if [ ! -f "tp-report.py" ]; then
        # Falls nein: In den Zielordner wechseln oder diesen erstellen
        if [ "$(basename "$(pwd)")" != "$TARGET_DIR" ]; then
            if [ ! -d "$TARGET_DIR" ]; then
                info "Erstelle Verzeichnis $TARGET_DIR..."
                mkdir -p "$TARGET_DIR"
            fi
            cd "$TARGET_DIR"
        fi

        # Falls die Hauptdatei immer noch fehlt, laden wir sie (und den Rest) herunter
        if [ ! -f "tp-report.py" ]; then
            # Dateien dynamisch via GitHub API ermitteln und herunterladen
            API_URL="https://api.github.com/repos/einstweilen/tp-link-daily-report/contents"
            
            info "Ermittle Dateiliste von GitHub..."
            FILES=$(curl -s "$API_URL" | grep '"name":' | cut -d'"' -f4 | grep -v '^\.')

            if [ -z "$FILES" ]; then
                error "Dateiliste konnte nicht geladen werden (GitHub API Limit?)."
                FILES="tp-report.py requirements.txt config-report.ini.sample setup_ai_key.sh tp-report-setup-guide.md"
                info "Nutze Fallback-Dateiliste."
            fi
            
            for file in $FILES; do
                if [ ! -f "$file" ]; then
                    info "Lade $file herunter..."
                    curl -sL "$BASE_URL/$file" -o "$file"
                fi
            done
        fi
    fi

    # Pre-flight Checks
    if ! command -v python3 &> /dev/null; then
        error "Python 3 ist nicht installiert. Bitte zuerst installieren."
        exit 1
    fi

    step "[1/7] Erstelle virtuelle Umgebung..."
    if [ ! -f ".venv/bin/activate" ]; then
        if [ -d ".venv" ]; then
            info "Bereinige unvollständige virtuelle Umgebung..."
            rm -rf .venv
        fi
        
        if ! python3 -m venv .venv 2>/tmp/venv_error.log; then
            PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            info "Virtuelle Umgebung konnte nicht erstellt werden ('python$PY_VER-venv' fehlt?)."
            
            if command -v apt-get &> /dev/null; then
                info "Versuche 'python$PY_VER-venv' automatisch via apt zu installieren..."
                prompt_text "Darf das System per 'sudo apt' aktualisiert und das Paket installiert werden? [J/N]: "
                read -r INSTALL_VENV < /dev/tty
                if [[ "$INSTALL_VENV" =~ ^[jJ] ]]; then
                    sudo apt-get update && sudo apt-get install -y "python$PY_VER-venv"
                    info "Versuche erneut, die virtuelle Umgebung zu erstellen..."
                    if ! python3 -m venv .venv 2>/tmp/venv_error.log; then
                        cat /tmp/venv_error.log
                        error "Erneuter Versuch fehlgeschlagen. Bitte manuell prüfen."
                        rm -f /tmp/venv_error.log
                        exit 1
                    fi
                else
                    cat /tmp/venv_error.log
                    error "Installation abgelehnt. Bitte manuell installieren mit:"
                    echo -e "${BOLD}sudo apt update && sudo apt install python$PY_VER-venv${NC}"
                    rm -f /tmp/venv_error.log
                    exit 1
                fi
            else
                cat /tmp/venv_error.log
                error "Fehlendes Paket 'python$PY_VER-venv'. Automatisierte Installation nur für apt/Debian möglich."
                rm -f /tmp/venv_error.log
                exit 1
            fi
        fi
        rm -f /tmp/venv_error.log
    fi
    info "Aktiviere virtuelle Umgebung..."
    source .venv/bin/activate
    success "Virtuelle Umgebung bereit."

    step "[2/7] Installiere Abhängigkeiten..."
    if [ -f "requirements.txt" ]; then
        info "pip install (Details: .install_report.log)..."
        touch .install_report.log
        if ! pip install --upgrade pip >> .install_report.log 2>&1; then
            error "pip-Upgrade fehlgeschlagen. Details:"
            cat .install_report.log
            exit 1
        fi
        if ! pip install -r requirements.txt --prefer-binary >> .install_report.log 2>&1; then
            error "Installation der Abhängigkeiten fehlgeschlagen. Details:"
            cat .install_report.log
            exit 1
        fi
        success "Abhängigkeiten installiert."
    else
        error "requirements.txt nicht gefunden!"
        exit 1
    fi

    step "[3/7] Überprüfe Konfigurationsdatei..."
    CONFIG_FILE="config-report.ini"
    if [ ! -f "$CONFIG_FILE" ]; then
        if [ -f "config-report.ini.sample" ]; then
            cp config-report.ini.sample "$CONFIG_FILE"
            success "$CONFIG_FILE wurde aus der Vorlage erstellt."
        else
            info "Erzeuge Standard-Konfiguration via Script..."
            python3 tp-report.py --update || true
            success "$CONFIG_FILE wurde erzeugt."
        fi
    else
        success "$CONFIG_FILE existiert bereits."
    fi

    step "[4/7] Interaktive Router-Konfiguration"
    while true; do
        prompt_text "Wie lautet die IP-Adresse des Routers? [192.168.1.1]: "
        read -r ROUTER_IP < /dev/tty
        ROUTER_IP=${ROUTER_IP:-192.168.1.1}
        
        prompt_text "Bitte das Passwort für das Web-Interface (GUI) eingeben: "
        read -rs GUI_PASS < /dev/tty
        echo ""

        info "Trage Daten in $CONFIG_FILE ein..."
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s/routerip = .*/routerip = $ROUTER_IP/g" "$CONFIG_FILE"
            sed -i '' "/^\[Router\]/,/^\[/{s/^password = .*/password = $GUI_PASS/}" "$CONFIG_FILE"
        else
            sed -i "s/routerip = .*/routerip = $ROUTER_IP/g" "$CONFIG_FILE"
            sed -i "/^\[Router\]/,/^\[/{s/^password = .*/password = $GUI_PASS/}" "$CONFIG_FILE"
        fi

        info "Teste Login mit den angegebenen Daten..."
        python_test_code="
import sys, configparser
try:
    from tplinkrouterc6u.client.ex import TPLinkEXClientGCM
    import logging
    config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    config.read('$CONFIG_FILE')
    router = TPLinkEXClientGCM(config['Router']['routerip'], config['Router']['password'], 'user', logging.getLogger(), verify_ssl=False)
    router.authorize()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
"
        if python3 -c "$python_test_code"; then
             success "Login am Router erfolgreich!"
             break
        else
             error "Login fehlgeschlagen. Bitte IP und Passwort prüfen."
             prompt_text "Soll die Eingabe wiederholt werden? (J/n) " 
             read -r retry < /dev/tty
             if [[ "$retry" =~ ^[nN] ]]; then
                  info "Überspringe Konfiguration. $CONFIG_FILE später manuell anpassen!"
                  break
             fi
        fi
    done

    step "[5/7] KI Analyse Einrichtung"
    prompt_text "KI Datenanalyse im Report verwenden? (Gemini API Key benötigt) [J/N]: "
    read -r AI_SETUP < /dev/tty
    if [[ "$AI_SETUP" =~ ^[jJ] ]]; then
        if [ -f "setup_ai_key.sh" ]; then
            chmod +x setup_ai_key.sh
            ./setup_ai_key.sh
        else
            error "setup_ai_key.sh nicht gefunden!"
        fi
    else
        info "Übersprungen: Keine KI-Analyse gewünscht."
    fi

    step "[6/7] Cronjobs einrichten"
    prompt_text "Automatischen Jobs für Update & Report in die crontab eintragen? (J/N): " 
    read -r CRON_SETUP < /dev/tty
    
    if [[ "$CRON_SETUP" =~ ^[jJ] ]]; then
        TMP_CRON=$(mktemp)
        crontab -l > "$TMP_CRON" 2>/dev/null || true
        
        # Hourly Update
        info "Hinzugefügt: Stündliches Datenupdate (--update)"
        echo "0 * * * * cd \"$(pwd)\" && \"$(pwd)/.venv/bin/python3\" tp-report.py --update >> .cron_update.log 2>&1" >> "$TMP_CRON"
        
        # Daily Report
        prompt_text "Zu welcher Uhrzeit soll der tägliche Bericht gesendet werden? [06:10]: "
        read -r REPORT_TIME < /dev/tty
        REPORT_TIME=${REPORT_TIME:-06:10}
        H=$(echo $REPORT_TIME | cut -d: -f1)
        M=$(echo $REPORT_TIME | cut -d: -f2)
        
        info "Hinzugefügt: Täglich um $REPORT_TIME Uhr Bericht senden (--report-send)"
        echo "$M $H * * * cd \"$(pwd)\" && \"$(pwd)/.venv/bin/python3\" tp-report.py --report-send >> .cron_report.log 2>&1" >> "$TMP_CRON"

        crontab "$TMP_CRON"
        rm -f "$TMP_CRON"
        success "Cronjobs erfolgreich eingerichtet!"
    else
        info "Übersprungen."
    fi

    step "[7/7] Installation testen..."
    info "Führe Test-Update aus..."
    python3 tp-report.py --update
    
    echo -e "\n${BOLD}==== Installation abgeschlossen! ====${NC}\n"
    info "Bitte die E-Mail Einstellungen in $CONFIG_FILE anpassen,"
    info "damit der Bericht versendet werden kann."
    echo ""
}

main "$@"

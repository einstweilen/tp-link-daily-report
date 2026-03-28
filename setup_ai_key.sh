#!/usr/bin/env bash
# KI API KEY Setup Script for Daily Report
# Targets config-report.ini

# Farben
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info() { echo -e "  ${BLUE}ℹ${NC} $1"; }
success() { echo -e "  ${GREEN}✓${NC} $1"; }
error() { echo -e "  ${RED}✗${NC} $1"; }
step() { echo -e "\n${BOLD}==> $1${NC}"; }
prompt_text() { echo -ne "  ${YELLOW}?${NC} $1"; }

CONFIG_FILE="config-report.ini"

echo -e "\n${BOLD}==== KI-Analyse Einrichtung (Daily Report) ====${NC}"

if [ ! -f "$CONFIG_FILE" ]; then
    error "$CONFIG_FILE nicht gefunden. Bitte zuerst das Haupt-Setup ausführen."
    exit 1
fi

EXISTING_KEY=$(grep "^ai_api_key" "$CONFIG_FILE" | cut -d '=' -f2- | tr -d ' ' | tr -d '\r\n')
if [[ "$EXISTING_KEY" != AIza* ]]; then
    EXISTING_KEY=""
fi

while true; do
    API_KEY=""
    if [[ -n "$EXISTING_KEY" ]]; then
        LAST_FOUR="${EXISTING_KEY: -4}"
        info "Es ist bereits ein Gemini API Key in $CONFIG_FILE hinterlegt (\"AIza…$LAST_FOUR\")"
        prompt_text "Diesen Key verwenden (J/N): "
        read -n 1 -r USE_EXISTING < /dev/tty
        echo ""
        if [[ "$USE_EXISTING" =~ ^[jJ] ]]; then
            API_KEY="$EXISTING_KEY"
            EXISTING_KEY=""
        else
            EXISTING_KEY=""
        fi
    fi

    if [[ -z "$API_KEY" ]]; then
        echo "  [V] Ein Google Gemini API Key ist bereits vorhanden"
        echo "  [G] Einen kostenlosen Google Gemini Key generieren"
        echo ""
        echo "  [N] Nein, keine KI Analyse der Routerdaten durchführen"
        echo ""

        prompt_text "Bitte Option wählen (V/G/N): "
        read -n 1 -r AI_CHOICE < /dev/tty
        echo ""
        AI_CHOICE=$(echo "$AI_CHOICE" | tr '[:lower:]' '[:upper:]')

        if [[ "$AI_CHOICE" != "G" && "$AI_CHOICE" != "V" ]]; then
            info "KI-Analyse wird deaktiviert."
            if grep -q "^\[AI\]" "$CONFIG_FILE"; then
                if [[ "$(uname)" == "Darwin" ]]; then
                    sed -i '' "s/^\[AI\]/\[noAI\]/g" "$CONFIG_FILE"
                else
                    sed -i "s/^\[AI\]/\[noAI\]/g" "$CONFIG_FILE"
                fi
                info "Vorhandener Key deaktiviert (Config-Sektion in [noAI] umbenannt)."
            fi
            exit 0
        fi

        if [[ "$AI_CHOICE" == "G" ]]; then
            URL="https://aistudio.google.com/app/apikey"
            info "Es erfolgt eine Weiterleitung zu Google."
            info "Sollte kein Webbrowser konfiguriert sein, den Key am Desktoprechner unter"
            info "$URL anlegen und später hier einfügen."
            if command -v open &> /dev/null; then open "$URL"; elif command -v xdg-open &> /dev/null; then xdg-open "$URL" >/dev/null 2>&1; fi
        fi

        echo ""
        info "Feld leerlassen um keinen Key zu hinterlegen."
        prompt_text "Bitte den API Key einfügen: "
        read -r RAW_API_KEY < /dev/tty
        API_KEY=$(echo -n "$RAW_API_KEY" | tr -d '\r\n[:space:]')
        echo ""
    fi

    if [[ -z "$API_KEY" ]]; then
        info "Kein Key eingegeben. KI-Setup abgebrochen."
        exit 0
    fi

    # Validierung des Formats
    PROVIDER="gemini"
    if [[ "$API_KEY" != AIza* ]]; then
        error "Das Format des API Keys wurde nicht erkannt."
        info "Google Gemini Schlüssel müssen zwingend mit 'AIza' beginnen."
        continue
    fi

    info "Teste Google Gemini API Key..."
    cat << 'EOF' > .test_api_daily.py
import sys
import urllib.request
import urllib.error
import urllib.parse
import json

api_key = sys.argv[1]
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"

try:
    data = json.dumps({"contents": [{"parts":[{"text": "Hallo"}]}]}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        sys.exit(0)
except urllib.error.HTTPError as e:
    print(f"HTTP Fehler: {e.code}")
    print(f"Fehlerhafte URL: {url}")
    try:
        err_msg = e.read().decode('utf-8', errors='ignore')
        print(f"Details vom Server: {err_msg}")
    except:
        pass
    sys.exit(1)
except Exception as e:
    print(f"Verbindungsfehler: {e}")
    sys.exit(1)
EOF

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    if python3 .test_api_daily.py "$API_KEY"; then
        success "API Key erfolgreich validiert!"
        rm -f .test_api_daily.py
        break
    else
        error "Der eingegebene API Key ist ungültig oder es gab einen Netzwerkfehler. Bitte erneut versuchen."
        rm -f .test_api_daily.py
    fi
done

info "Speichere API-Key in $CONFIG_FILE..."

# Reaktivierung, falls [noAI] existiert
if grep -q "^\[noAI\]" "$CONFIG_FILE"; then
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s/^\[noAI\]/\[AI\]/g" "$CONFIG_FILE"
    else
        sed -i "s/^\[noAI\]/\[AI\]/g" "$CONFIG_FILE"
    fi
fi

if ! grep -q "^\[AI\]" "$CONFIG_FILE"; then
    echo -e "\n[AI] # AI = Modul aktiviert noAI = Modul deaktiviert\nai_provider = $PROVIDER\nai_api_key = $API_KEY" >> "$CONFIG_FILE"
else
    if grep -q "^ai_provider" "$CONFIG_FILE"; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s/^ai_provider.*/ai_provider = $PROVIDER/g" "$CONFIG_FILE"
            sed -i '' "s/^ai_api_key.*/ai_api_key = $API_KEY/g" "$CONFIG_FILE"
        else
            sed -i "s/^ai_provider.*/ai_provider = $PROVIDER/g" "$CONFIG_FILE"
            sed -i "s/^ai_api_key.*/ai_api_key = $API_KEY/g" "$CONFIG_FILE"
        fi
    else
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "/^\[AI\]/a\\
ai_provider = $PROVIDER\\
ai_api_key = $API_KEY" "$CONFIG_FILE"
        else
            sed -i "/^\[AI\]/a ai_provider = $PROVIDER\nai_api_key = $API_KEY" "$CONFIG_FILE"
        fi
    fi
fi

success "KI-Setup vollständig abgeschlossen."

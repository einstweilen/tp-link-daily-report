# Installations-Anleitung: TP-Link Report

Diese Anleitung beschreibt die Einrichtung des `tp-report.py` Skripts, welches täglich einen detaillierten Statusbericht aller durch die [Third-Party-Router API von Alexandr Erohin ](https://github.com/AlexandrErohin/TP-Link-Archer-C6U) unterstützten Router per E-Mail versendet.<br>
Es ist die abgespeckte Version des `vx-info.py` Skripts. Die Datenstruktur ist identisch, so dass man bei Bedarf auf die größere Version 

## Installation

Im Terminal
```bash
curl -sL https://raw.githubusercontent.com/einstweilen/tp-link-vx231v/main/install_report.sh | bash
```
ausführen, das Skript lädt den Installer herunter, erstellt das Verzeichnis `tp-report` und richtet alles Notwendige ein.

---

## Manuelle Einrichtung & Konfiguration

Für eine manuelle Anpassung finden sich hier die Details zu den Dateien:

### 1. Konfigurationsdatei: `config-report.ini`
Nach dem ersten Start (oder durch `install_report.sh`) existiert diese Datei. Die wichtigsten Sektionen sind:

*   **[Router]**: IP-Adresse und Passwort des Routers.
*   **[Email]**: Hier sind die SMTP-Daten einzutragen, damit der E-Mail-Versand möglich ist.
*   **[AI]**: Hier wird der Gemini API Key gespeichert, falls die automatische Analyse gewünscht ist.
*   **[Events]**: Festlegung, welche Ereignisse im Bericht erscheinen sollen (z.B. Ausschluss von DHCP-Leases).

### 2. KI-Analyse einrichten
Der Daily Report kann die Leitungsdaten (SNR, Fehler, Reconnects) von einer KI analysieren lassen. Dazu ist ein kostenloser API Key von Google AI Studio erforderlich:

1.  Aufruf von [Google AI Studio](https://aistudio.google.com/app/apikey).
2.  Erstellung eines neuen API Keys.
3.  Ausführung von `./setup_ai_key.sh` oder direkter Eintrag des Keys in der `config-report.ini` unter `ai_api_key`.

### 3. Cronjobs (Geplante Aufgaben)
Damit der Bericht täglich erstellt wird, müssen zwei Befehle regelmäßig ausgeführt werden:

*   **Daten-Update (stündlich empfohlen):**
    `python3 tp-report.py --update`
*   **Bericht senden (täglich gewünschte Uhrzeit):**
    `python3 tp-report.py --report-send`

Standardmäßig wird dies durch `install_report.sh` automatisch in der `crontab` eingerichtet.

---

## Befehlsübersicht
Das Skript kann jederzeit manuell aufgerufen werden:

| Befehl | Beschreibung |
| :--- | :--- |
| `tp-report.py --update` | Abruf aktueller Daten vom Router und Speicherung in der DB. |
| `tp-report.py --report-show` | Generierung des HTML-Berichts und sofortige Anzeige im Browser. |
| `tp-report.py --report-send` | Generierung des Berichts und Versendung per E-Mail. |
| `tp-report.py --de` / `--en` | Umschalten der Berichtssprache. |


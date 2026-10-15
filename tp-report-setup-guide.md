# Installations-Anleitung: TP-Link Report

Diese Anleitung beschreibt die Einrichtung des `tp-report.py` Skripts, welches täglich einen detaillierten Statusbericht aller durch die [Third-Party-Router API von Alexandr Erohin ](https://github.com/AlexandrErohin/TP-Link-Archer-C6U) unterstützten Router per E-Mail versendet.<br>
Es ist die abgespeckte Version des [`vx-info.py`](https://github.com/einstweilen/tp-link-vx231v/) Skripts. Die Datenstruktur ist bei beiden Skripten identisch, so dass man beliebig zwischen den beiden wechseln kann.

## Installation

Im Terminal
```bash
curl -sL https://raw.githubusercontent.com/einstweilen/tp-link-daily-report/main/install_report.sh | bash
```
ausführen, das Skript lädt den Installer herunter, erstellt das Verzeichnis `tp-report` und richtet alles Notwendige ein.
Neben den Python-Paketen (u. a. `playwright`) wird dabei einmalig **Chromium** für den Headless-Browser installiert - das dauert ein paar Minuten und benötigt ca. 150 MB. Nachinstallieren lässt sich das jederzeit mit `playwright install chromium`.

---

## Manuelle Einrichtung & Konfiguration

Für eine manuelle Anpassung finden sich hier die Details zu den Dateien:

### 1. Konfigurationsdatei: `config-report.ini`
Nach dem ersten Start (oder durch `install_report.sh`) existiert diese Datei. Die einzlenen Sektionen sind:

*   **[Router]**: IP-Adresse und Passwort des Routers.
*   **[Database]**: SQLite Datenbank, kompatibel zu vx-info.py
*   **[Email]**: SMTP-Daten für den E-Mail-Versand
*   **[Modul]**: Ein-/Ausschalten der Report-Bausteine (KI-Analyse, Charts, Anwesenheit, ...) sowie `collect_clients` - siehe unten
*   **[Charts]**: Festlegung, welcher DSL-Parameter im Bericht erscheinen sollen
*   **[Events]**: Festlegung, welche Ereignisse im Bericht erscheinen sollen
*   **[WebUI]**: Steuerung des Headless-Browsers (Aufwecken der Router-Tabellen, DSL-Fehlerzähler) - siehe unten
*   **[AI]**: API Key für die automatische Analyse - Deaktivierung durch Umbenennen in [noAI]
*   **[Language]**: Ausgabesprache des Tagesreports

Die Datei enthält Zugangsdaten und ist per `.gitignore` vom Repository ausgeschlossen. Zweckmäßig ist
`chmod 600 config-report.ini` (nur der Eigentümer darf lesen und schreiben); `install_report.sh` setzt das
automatisch.

### Datenabruf und Laufzeit

Das Skript liest die Routerdaten in dieser Reihenfolge:

1.  **Router-API** (JSON über HTTPS) - System/Firmware, DSL-Werte, Clients, Routerlog. Das ist der Normalfall und dauert wenige Sekunden.
2.  **Weboberfläche** (Headless-Browser) - nur wenn nötig: Die aktuelle Firmware liefert DSL-/Clientdaten erst, nachdem die Oberfläche sie angefragt hat (das Skript „weckt" sie dann einmal kurz auf), und die DSL-Fehlerzähler (CRC) gibt es ausschließlich dort.
3.  **Lokaler ARP-Scan** - Ping-Sweep der eigenen Subnetze plus ARP-Tabelle, ohne SNMP und ohne Router-Login. Damit bleiben die Clients auch dann vollständig, wenn die Client-Tabellen des Routers leer sind. Einzeltest: `python3 -m arp_scan`.

Diese Schalter verkürzen die Laufzeit deutlich:

| Schlüssel | Wirkung |
| :--- | :--- |
| `[Modul] collect_clients = False` | keine Client-Abfrage, kein Netzplan-Aufwecken, kein ARP-Scan (schnellster Lauf; sinnvoll, wenn z. B. `vx-info.py` dieselbe Datenbank mit Clientdaten füllt) |
| `[WebUI] crc_source = aus` | CRC-Werte nicht per Browser nachlesen (bleiben `0`) |
| `[WebUI] warmup = aus` | Router-Tabellen nie per Browser aufwecken (dann ggf. keine DSL-Werte in diesem Lauf) |

Mit beiden Abschaltungen läuft ein `--update` in ca. 4 Sekunden (statt 2-3 Minuten mit Browser).

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
| `tp-report.py -show` | Generierung des HTML-Berichts und lokale Anzeige im Browser. |
| `tp-report.py -send` | Generierung des Berichts und Versendung per E-Mail. |
| `tp-report.py --de` / `--en` | Umschalten der Berichtssprache. |

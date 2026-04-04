# TP-Link Status Report

### Getestet mit dem TP-Link VX231v, andere TP-Link Router können abweichen

### 1. Expressvariante: [TP-Link Daily Report](tp-report-setup-guide.md)
Ein Python-Skript (`tp-report.py`) zur automatisierten Erfassung der DSL, Client und Logdaten des Routers. Es erstellt einen täglichen Statusreport und versendet diesen per E-Mail.

**Inhalte:**
* Datenabruf von DSL-Werten und der verbundenen Clients via [Router API von Alexandr Erohin ](https://github.com/AlexandrErohin/TP-Link-Archer-C6U)
* Speicherung der Daten in einer Datenbank
* Automatisierte Generierung und Versand von täglichen Statusreports
  <details>
      <summary>
          <span><img src="https://github.com/einstweilen/tp-link-daily-report/main/images/beispiel-statusreport-sml.jpg" alt="Vorschau Statusreport"></span>
          <br>
          <i>Anklicken für vollständigen Statusreport</i>
      </summary>
      <br>
      <img src="https://github.com/einstweilen/tp-link-daily-report/main/images/beispiel-statusreport.jpg" alt="Beispiel Statusreport">
  </details>
* Die Reportsprache kann zwischen Deutsch und Englisch umgeschaltet werden
* mehr zu den Einzelbestandteilen des Reports siehe<br>
[Details zum Statusreport](https://einstweilen.github.io/tp-link-daily-report/report/)
<br>

**Schnelle Installation:**
```bash
curl -sL https://raw.githubusercontent.com/einstweilen/tp-link-daily-report/main/install_report.sh | bash
```
<br>

<details>
<summary>Beispielablauf der Schnellen Installation</summary>

```
curl -sL https://raw.githubusercontent.com/einstweilen/tp-link-daily-report/main/install_report.sh | bash
==== tp-report Installation ====
  ℹ Erstelle Verzeichnis tp-report...
  ℹ Ermittle Dateiliste von GitHub...
  ℹ Lade README.md herunter...
  ℹ Lade config-report.ini.sample herunter...
  ℹ Lade install_report.sh herunter...
  ℹ Lade requirements.txt herunter...
  ℹ Lade setup_ai_key.sh herunter...
  ℹ Lade tp-report-setup-guide.md herunter...
  ℹ Lade tp-report.py herunter...

==> [1/7] Erstelle virtuelle Umgebung...
  ℹ Aktiviere virtuelle Umgebung...
  ✓ Virtuelle Umgebung bereit.

==> [2/7] Installiere Abhängigkeiten...
  ℹ pip install (Details: .install_report.log)...
  ✓ Abhängigkeiten installiert.

==> [3/7] Überprüfe Konfigurationsdatei...
  ✓ config-report.ini wurde aus der Vorlage erstellt.

==> [4/7] Interaktive Router-Konfiguration
  ? Wie lautet die IP-Adresse des Routers? [192.168.1.1]: 192.168.178.1
  ? Bitte das Passwort für das Web-Interface (GUI) eingeben: 
  ℹ Trage Daten in config-report.ini ein...
  ℹ Teste Login mit den angegebenen Daten...
  ✓ Login am Router erfolgreich!

==> [5/7] KI Analyse Einrichtung
  ? KI Datenanalyse im Report verwenden? (Gemini API Key benötigt) [J/N]: j

==== KI-Analyse Einrichtung (Daily Report) ====
  [V] Ein Google Gemini API Key ist bereits vorhanden
  [G] Einen kostenlosen Google Gemini Key generieren

  [N] Nein, keine KI Analyse der Routerdaten durchführen

  ? Bitte Option wählen (V/G/N): v

  ℹ Feld leerlassen um keinen Key zu hinterlegen.
  ? Bitte den API Key einfügen: AIzaDerGoogleGemini-APIkey

  ℹ Teste Google Gemini API Key...
  ✓ API Key erfolgreich validiert!
  ℹ Speichere API-Key in config-report.ini...
  ✓ KI-Setup vollständig abgeschlossen.

==> [6/7] Cronjobs einrichten
  ? Automatischen Jobs für Update & Report in die crontab eintragen? (J/N): n
  ℹ Übersprungen.

==> [7/7] Installation testen...
  ℹ Führe Test-Update aus...
API Login OK. Hole Daten...
428 Events gespeichert.
Update abgeschlossen.

==== Installation abgeschlossen! ====

  ℹ Bitte die E-Mail Einstellungen in config-report.ini anpassen,
  ℹ damit der Bericht versendet werden kann.

```
</details>
<br>

Die Expressvariante ist für Nutzer, die nur einen täglichen Statusbericht per E-Mail erhalten möchten.<br>
Wer tiefer in die Konfiguration einsteigen möchte, sieht sich die [große Lösung VX-Info Tracker](https://github.com/einstweilen/tp-link-vx231v/blob/main/vx-info.md) an.<br>
Beide Varianten nutzen die gleiche Datenstruktur, ein Wechsel ist jederzeit möglich, bereits erfaßte Daten lassen sich weiterverwenden.
<br>
Bei der Expressvariante wird nur die Datenerfassung per Third-Party-API unterstützt, wenn die z.B. nach einem Firmware Update nicht mehr funktionieren sollte, kann man auf die große Lösung wechseln, die die Daten auch per Scraping der Routeroberfläche und optional auch per SNMP/Telnet erfassen kann und automatisch immer die schnellste verfügbare Methode nutzt.

[Zur Installationsanleitung: TP-Link Report](tp-report-setup-guide.md)

---

### 2. Große Lösung: [Router Monitoring: VX-Info Tracker](https://github.com/einstweilen/tp-link-vx231v/blob/main/vx-info.md)
Ein Set aus Python-Skripten (`vx-info.py`) zur automatisierten Erfassung und Darstellung der Routerdaten.
Der Hauptunterschied zur Expressvariante ist, dass hier die Daten auf drei verschiedenen Wegen erfasst werden können:
* die Third-Party-API (wie bei der Expressvariante)
* das Web-Interface des Routers (GUI-Scraping mit playwright)
* und bei aktiviertem Superadmin-Account auch per SNMP und Telnet

<details>
<summary>Mehr Infos</summary>

Die drei Varianten kann man gezielt auswählen oder überläßt dem Script die Auswahl der besten Methode mit automatischem Fallback auf die nächstbeste Methode, wenn die bevorzugte Methode nicht verfügbar ist.

Wenn man dann zusätzlich das Routerlog per rsyslog parallel lokal mitschreibt, hat man alle Daten, die man für eine umfassende Analyse benötigt auch dann wenn z.B. durch einen Stromausfall Lücken im Routerlog entstehen würden oder wenn der Router aufgrund eines Fehlers nicht mehr erreichbar wäre und ein Hard Reset erforderlich wäre.

Die von der Expressvariante gewonnenen Daten können weitergenutzt werden, wenn man später auf die große Lösung wechseln möchte. Idealerweise legt man dann im Verzeichnis vom VX231v Tracker einen Symlink zur bestehenden router_data.db Datei an, um die Historie weiter nutzen zu können.

</details>


**Inhalte:**
*   Automatisierte Generierung von HTML-Statusreports (wie Status Report)

  <details>
      <summary>
          <span><img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport-sml.jpg" alt="Vorschau Statusreport"></span>
          <br>
          <i>Anklicken für vollständigen Statusreport</i>
      </summary>
      <br>
      <img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport.jpg" alt="Beispiel Statusreport">
  </details>

*   ZUSÄTZLICH: Lokales Browser-Dashboard zur Visualisierung

  <details>
      <summary>
          <span><img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-dashboard-sml.jpg" alt="Vorschau Dashboard"></span>
          <br>
          <i>Anklicken für vollständiges Dashboard</i>
      </summary>
      <br>
      <img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-dashboard.jpg" alt="Beispiel Browser-Dashboard">
  </details>

<br>

[Zur Installationsanleitung: VX-Info Tracker](https://github.com/einstweilen/tp-link-vx231v/blob/main/vx-info.md)

---

**Getestet unter MacOS und Debian/DietPi auf einem Raspberry Pi Zero 2W**
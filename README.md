# TP-Link VX231v Tools

## Getestet mit dem TP-Link VX231v, andere TP-Link Router können abweichen

### 1. Expressvariante: [TP-Link Daily Report](tp-report/tp-report-setup-guide.md)
Ein Python-Skript (`tp-report.py`) zur automatisierten Erfassung der DSL, Client und Logdaten des Routers. Es erstellt einen täglichen Statusreport und versendet diesen per E-Mail.

**Inhalte:**
* Datenabruf von DSL-Werten und der verbundenen Clients via [Router API von Alexandr Erohin ](https://github.com/AlexandrErohin/TP-Link-Archer-C6U)
* Speicherung der Daten in einer Datenbank
* Automatisierte Generierung und Versand von täglichen Statusreports
  <details>
      <summary>
          <span><img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport-sml.jpg" alt="Vorschau Statusreport"></span>
          <br>
          <i>Anklicken für vollständigen Statusreport</i>
      </summary>
      <br>
      <img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport.jpg" alt="Beispiel Statusreport">
  </details>
* Die Reportsprache kann zwischen Deutsch und Englisch umgeschaltet werden
* mehr zu den Einzelbestandteilen des Reports siehe<br>
[Details zum Statusreport](https://einstweilen.github.io/tp-link-vx231v/report/)
<br>

**Schnelle Installation:**
```bash
curl -sL https://raw.githubusercontent.com/einstweilen/tp-link-vx231v/main/install_report.sh | bash
```
<br>
Die Expressvariante ist ideal für Nutzer, die nur einen täglichen Statusbericht per E-Mail erhalten möchten.<br>
Wer tiefer in die Konfiguration einsteigen möchte, sieht sich die [große Lösung VX-Info Tracker](vx-info.md) an.<br>
Beide Varianten nutzen die gleiche Datenstruktur, ein Wechsel ist jederzeit möglich, bereits erfaßte Daten lassen sich weiterverwenden.
<br>
Bei der Expressvariante wird nur die Datenerfassung per Third-Party-API unterstützt, wenn die z.B. nach einem Firmware Update nicht mehr funktionieren sollte, kann man auf die große Lösung wechseln, die die Daten auch per Scraping der Routeroberfläche und optional auch per SNMP/Telnet erfassen kann und automatisch immer die schnellste verfügbare Methode nutzt.

[Zur Installationsanleitung: TP-Link Report](tp-report-setup-guide.md)

---

### 2. Große Lösung: [Router Monitoring: VX-Info Tracker](vx-info.md)
Ein Set aus Python-Skripten (`vx-info.py`) zur automatisierten Erfassung und Darstellung der Routerdaten.
Der Hauptunterschied zur Expressvariante ist, dass hier die Daten auf drei verschiedenen Wegen erfasst werden können:
* die Third-Party-API (wie bei der Expressvariante)
* das Web-Interface des Routers (GUI-Scraping mit playwright)
* und bei aktiviertem Superadmin-Account auch per SNMP und Telnet

  <details>
      <summary>
      Mehr Infos
      </summary>
Die drei Varianten kann man gezielt auswählen oder überläßt dem Script die Auswahl der besten Methode mit automatischem Fallback auf die nächstbeste Methode, wenn die bevorzugte Methode nicht verfügbar ist.
<br>
Wenn man dann zusätzlich das Routerlog per rsyslog parallel lokal mitschreibt, hat man alle Daten, die man für eine umfassende Analyse benötigt auch dann wenn z.B. durch einen Stromausfall Lücken im Routerlog entstehen würden oder wenn der Router aufgrund eines Fehlers nicht mehr erreichbar wäre und ein Hard Reset erforderlich wäre.

Die von der Epressvariante gewonnenen Daten können weitergenutzt werden, wenn man später auf die große Lösung wechseln möchte. Idealerweise legt man dann im Verzeichnis vom VX231v Tracker einen Symlink zur bestehenden router_data.db Datei an, um die Historie weiter nutzen zu können.
      
  </details>


**Inhalte:**
* Datenabruf von DSL-Werten und der verbundenen Clients via API, Web-Scraping und optional SNMP, Telnet
* Speicherung der Daten in einer Datenbank
* Automatisierte Generierung von HTML-Statusreports
  <details>
      <summary>
          <span><img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport-sml.jpg" alt="Vorschau Statusreport"></span>
          <br>
          <i>Anklicken für vollständigen Statusreport</i>
      </summary>
      <br>
      <img src="https://github.com/einstweilen/tp-link-vx231v/blob/main/images/beispiel-statusreport.jpg" alt="Beispiel Statusreport">
  </details>
* Lokales Browser-Dashboard zur Visualisierung
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
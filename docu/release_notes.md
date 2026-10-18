# Release Notes

Funktionellen Änderungen, Features und wichtigen Verbesserungen des TP-Link Status Report Projekts im Überblick.

## 18.10.2026

**Ereignisliste auf das Wesentliche reduziert (eigene Abrufe und Routine ausgeblendet)**

* Neuer Schalter `[Events] hide_own_activity` (Standard `True`): Ausgeblendet werden die eigenen
  Abrufe (`httpd`/`cloud_https` von der eigenen IP), `tmpd` ("Logout all users."), die
  HTTP-Erfolgsmeldungen und die An-/Abmeldungen der WLAN-Clients (`mapAgent`/`mapController`).
  **Fehler bleiben sichtbar** (`Login failed!`, `Connection Fail …`); `pppd`/`cos`-Routine bleibt
  ebenfalls drin.
* Eigene IP wird automatisch ermittelt; `[Events] own_ips` überschreibt sie (Komma-getrennt).
* Alte Konfigurationen wirken weiter: `VoIP` blendet jetzt auch `voip_client` aus, `DHCPD`/`dhcpd`
  ist immer aus, `Mesh` meint nur noch die Sitzungen (Fehlermeldungen der WLAN-Clients bleiben).
* Die Regeln liegen als `routerlog.event_where()` in `routerlog.py` - identisch in beiden
  Projekten. Damit ist auch angeglichen, dass tp-report die WLAN-Clientereignisse bisher **nicht**
  automatisch ausgeblendet hat (~66 Zeilen/24 h zusätzlich).
* Messung am Referenz-Router (24 h): 712 Ereignisse → 53 Zeilen (vorher 692).

## 17.10.2026

**Anpassung an das neue Router-Log (Firmware 0.26.0)**

* Neuer Parser für die RFC5424-Zeilen (`mapAgent`/`mapController`/`dhcpd`/`pppd`/`httpd`) inkl.
  Structured Data (MAC/IP) - beide Varianten (API mit lokalem Kopf, HTTP-Download mit UTC-Zeit)
  und weiterhin die alten Formate.
* `events` erhält `msgid`, `mac`, `ip`, `sd` (automatische Migration); Anwesenheit wird aus
  diesen Feldern gebaut, Doppelmeldungen von `mapAgent`/`mapController` werden entprellt.
* Das Formatwissen liegt in `routerlog.py` neben `tp-report.py` (liefert `install_report.sh` mit).
* Ganzzahlige Config-Werte mit Inline-Kommentar funktionieren jetzt (`config_int`), Log-Download
  nutzt zuerst den Datei-Download.
* `backfill_events.py` ergänzt `msgid`/`mac`/`ip` für Ereignisse vor 0.26.0 (idempotent,
  `--dry-run`), damit Abfragen über die ganze Historie einheitlich sind.

## 15.10.2026
- **Feature**: Firmware-Hinweis zeigt jetzt **alle** neueren Versionen statt nur der neuesten. Beim Sprung von 0.24 auf 0.26 wird damit auch der notwendige Zwischenschritt 0.25 mit seinen Release Notes angezeigt - inklusive der Reihenfolge (`0.25.0 ➜ 0.26.0`), in der aktualisiert werden muss.
- **Anpassung**: Nach der Router-Firmware-Umstellung liefert der Router DSL-/Clientdaten erst, wenn die Weboberfläche sie angefragt hat. Das Skript erkennt leere Tabellen, weckt sie einmal kurz über die Weboberfläche (nur die DSL-Seite) und liest danach erneut.
- **Neu**: Lokale ARP-Erkennung (`arp_scan.py`) als Client-Quelle - Ping-Sweep der eigenen Subnetze plus ARP-Tabelle, ohne SNMP und ohne Router-Login. Sie kann auch direkt getestet werden: `python3 -m arp_scan`.
- **Konfiguration**: Neue Schalter in der `config-report.ini`: `[WebUI] warmup`/`crc_source`/`user` und `[Modul] collect_clients`. Details: [Installations-Anleitung](../tp-report-setup-guide.md).
- **Schneller**: Chromium wird nur noch bei Bedarf gestartet (einmal pro Lauf statt zweimal), lädt keine Bilder/Schriften und läuft mit niedriger Priorität - Laufzeiten von 4 s statt 2-3 Minuten bei abgeschalteter Client-Erfassung.

## 27.06.2026
- **Bugfix**: Gastnetz-Clients werden in der Anwesenheitsauswertung nicht mehr fälschlich als Heimnetz angezeigt.
- **Bugfix**: SNR-Tagesschwankungen werden jetzt als PNG-Grafik dargestellt und sind auch in Google Mail auf Android sichtbar.

## 11.04.2026
- **Feature**: Automatischer Fix von falschen Event-Zeitstempeln nach einem Router-Reboot integriert.

## 07.04.2026
- **Konfiguration**: Parameter in der `config-report.ini` für bessere Verständlichkeit beschriftet.
- **Dokumentation**: Installationsanleitung grundlegend überarbeitet und Informationen zum AI-Modell aktualisiert.

## 04.04.2026
- **UI/UX**: Schriftgrößen in den generierten Grafiken für bessere Lesbarkeit optimiert.

## 28.03.2026
- **Refactoring**: Installationsskript verschlankt und effizienter gestaltet.
- **UI/UX**: Text- und Layoutanpassungen im generierten Report vorgenommen.
- **Initial Commit**: Veröffentlichung des TP-Link Router Report System

---

[Zurück zur Übersicht](../README.md) | [Dokumentation](statusreport_doku.md)

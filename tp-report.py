#!/usr/bin/env python3
"""
TP-Link Daily Report
"""

import argparse
import configparser
import json
import sqlite3
import sys
import time
import os
import re

try:
    import routerlog          # Logformat-Auswertung (liegt neben dieser Datei)
except ImportError:
    raise SystemExit("Fehler: routerlog.py fehlt. Bitte install_report.sh erneut ausfuehren "
                     "(oder routerlog.py neben tp-report.py kopieren).")

# Typ-Filter für SQL-Abfragen - gepflegt in routerlog.py (gilt für alt und neu)
PPP_TYPES_SQL = routerlog.sql_in(routerlog.PPP_EVENT_TYPES)
HTTPD_TYPES_SQL = routerlog.sql_in(routerlog.HTTPD_EVENT_TYPES)
HIDDEN_TYPES_SQL = routerlog.sql_in(routerlog.HIDDEN_EVENT_TYPES)
import logging
import base64
import io
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# lokales Modul (liegt neben diesem Skript): ARP-Erkennung ohne SNMP/Router-Login
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from arp_scan import get_local_arp_clients
except ImportError:
    # z.B. ältere Installation, bei der arp_scan.py noch fehlt: Skript bleibt lauffähig
    def get_local_arp_clients(*_args, **_kwargs):
        print("Hinweis: arp_scan.py nicht gefunden - lokale ARP-Clienterkennung deaktiviert"
              " (Datei aus dem Repository nachladen).")
        return []

try:
    from tplinkrouterc6u.client.ex import TPLinkEXClientGCM
    from tplinkrouterc6u.common.exception import ClientException
    from tplinkrouterc6u.common.package_enum import Connection
except ImportError:
    TPLinkEXClientGCM = None
    ClientException = Exception
    Connection = None

# ---------------------------------------------------------------------------
# TRANSLATIONS
# ---------------------------------------------------------------------------
TRANSLATIONS = {
    'de': {
        'title': 'Router Statusreport',
        'subject': 'Täglicher',
        'conn_overview': 'Verbindungsübersicht vom',
        'from_date': 'vom',
        'unknown': 'unbekannt',
        'hours': 'Stunden',
        'minutes': 'Minuten',
        'days': 'Tagen',
        'connected_since': 'Verbunden seit',
        'current': 'Aktuelle',
        'data_rate_down': 'Datenrate Down',
        'up': 'Up',
        'last_ip_change': 'IP-Wechsel vor',
        'firmware': 'Firmware:',
        'last_reboot': 'Letzter Routerneustart vor',
        'fw_notice': 'Firmware Hinweis',
        'fw_installed': 'Aktuell installiert',
        'fw_available': 'Online verfügbar:',
        'fw_order': 'Bitte in dieser Reihenfolge aktualisieren:',
        'rn': 'Release Notes',
        'at_a_glance': 'Auf einen Blick',
        'line_analysis': 'Leitungsanalyse',
        'event_overview': 'Reconnects',
        'presence': 'Anwesenheit',
        'home_network': 'Aktuell aktive Clients',
        'event_log_level': 'Ereignislog der letzten 24h bis Level',
        'event_log_full': 'Vollständiges Ereignislog der letzten 24h',
        'event_log_without': 'Ereignislog der letzten 24h ohne',
        'fallback_log': 'Ereignislog (letzte 24h)',
        'footer': 'Automatisch generiert und ohne Unterschrift gültig',
        'generated_in': 'Der Bericht wurde generiert und liegt unter',
        'mail_success': 'E-Mail erfolgreich versendet.',
        'mail_error': 'Versandfehler:',
        'warning': 'Warnung:',
        'pado_timeout_msg': 'PADO-Timeouts (Schwere Discovery-Störung). IPv6/RFC 4638 prüfen oder Provider-Störung melden.',
        'planned_reboot': 'Geplanter Neustart (Zeitplan)',
        'manual_reset': 'Benutzer / System Reset',
        'provider_drop': 'Trennungsanforderung (ISP)',
        'delayed_reconnect': 'Verzögerter Reconnect (Ggfs. Sync-Verlust)',
        'unplanned_drop': 'Ungeplante Provider-Trennung',
        'dns_error_window': 'DNS-Auflösungsfehler im Zeitfenster',
        'signal_error_before_drop': 'Signalstörung vor Abbruch (Fiel auf {snr})',
        'massive_crc_burst': 'Massiver CRC-Fehler-Burst vor Trennung (+{crc} Fehler)',
        'profile_fallback': 'Profil-Rückfall! Mit {diff} weniger Download neu verbunden',
        'hint': 'HINWEIS:',
        'duration': 'Dauer:',
        'no_disconnects_level': 'Keine Verbindungsabbrüche auf diesem Schweregrad (Level {level}) im Auswertungszeitraum gefunden.',
        'line_stable': 'Die Leitungswerte sind im Analysezeitraum unauffällig. Keine signifikanten Störungen erkannt.',
        'daily_fluctuations': 'Tagesschwankungen',
        'last_3_months': '(letzte 3 Monate)',
        'max_hourly_fluctuation': 'Max. stündliche Schwankung (Delta):',
        'lower_is_better': '(Je geringer, desto stabiler)',
        'no_data': 'Keine Daten',
        'snr_stats_hours': '{hours} Stunden Max {max} Min {min} Median {median}',
        'median_7d': 'Median der letzten {days} Tage {median}',
        'stats_3m': '3 Monats Max {max} Min {min} Median {median}'
    },
    'en': {
        'title': 'Router Status Report',
        'subject': 'Daily',
        'conn_overview': 'Connection Overview from',
        'from_date': 'from',
        'unknown': 'unknown',
        'hours': 'hours',
        'minutes': 'minutes',
        'days': 'days',
        'connected_since': 'Connected since',
        'current': 'Current',
        'data_rate_down': 'Data rate Down',
        'up': 'Up',
        'last_ip_change': 'IP change',
        'firmware': 'Firmware:',
        'last_reboot': 'Last router reboot',
        'fw_notice': 'Firmware Notice',
        'fw_installed': 'Currently installed',
        'fw_available': 'Available online:',
        'fw_order': 'Please update in this order:',
        'rn': 'Release Notes',
        'at_a_glance': 'At a glance',
        'line_analysis': 'Line analysis',
        'event_overview': 'Reconnects',
        'presence': 'Presence',
        'home_network': 'Currently active clients',
        'event_log_level': 'Event log (last 24h) up to level',
        'event_log_full': 'Complete event log (last 24h)',
        'event_log_without': 'Event log (last 24h) excluding',
        'fallback_log': 'Event log (last 24h)',
        'footer': 'Auto-generated and valid without signature',
        'generated_in': 'Report generated at',
        'mail_success': 'Email sent successfully.',
        'mail_error': 'Mail error:',
        'warning': 'Warning:',
        'pado_timeout_msg': 'PADO timeouts (Severe discovery disruption). Check IPv6/RFC 4638 or report ISP issue.',
        'planned_reboot': 'Planned reboot (Schedule)',
        'manual_reset': 'User / System Reset',
        'provider_drop': 'Disconnect request (ISP)',
        'delayed_reconnect': 'Delayed reconnect (Possible sync loss)',
        'unplanned_drop': 'Unplanned ISP disconnect',
        'dns_error_window': 'DNS resolution errors in time window',
        'signal_error_before_drop': 'Signal drop before disconnect (Fell to {snr})',
        'massive_crc_burst': 'Massive CRC error burst before disconnect (+{crc} errors)',
        'profile_fallback': 'Profile fallback! Reconnected with {diff} less download',
        'hint': 'NOTE:',
        'duration': 'Duration:',
        'no_disconnects_level': 'No connection drops found at this severity level (Level {level}) during the analysis period.',
        'line_stable': 'Line values are unremarkable during the analysis period. No significant disruptions detected.',
        'daily_fluctuations': 'Daily Fluctuations',
        'last_3_months': '(last 3 months)',
        'max_hourly_fluctuation': 'Max. hourly fluctuation (Delta):',
        'lower_is_better': '(Lower is more stable)',
        'no_data': 'No data',
        'snr_stats_hours': '{hours} hours Max {max} Min {min} Median {median}',
        'median_7d': 'Median of the last {days} days {median}',
        'stats_3m': '3 months Max {max} Min {min} Median {median}'
    }
}
# ---------------------------------------------------------------------------
# CONFIG MANAGER
# ---------------------------------------------------------------------------
class ConfigManager:
    def __init__(self, config_file='config-report.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
        
        if not os.path.exists(self.config_file):
            self.create_default_config()
            print(f"[{config_file}] wurde erstellt. Bitte passe die Werte (IP, Zugangsdaten) an.")
            sys.exit(0)
            
        self.config.read(self.config_file)
        
    def create_default_config(self):
        self.config['Router'] = {
            'router_ip': '192.168.0.1',
            'password': 'DEIN_ROUTER_PASSWORT'
        }
        self.config['Database'] = {'db_name': 'router_data.db'}
        self.config['WebUI'] = {
            'user': 'admin',
            'warmup': 'auto',
            'crc_source': 'gui'
        }
        self.config['Email'] = {
            'smtp_server': 'smtp.example.com',
            'smtp_port': '587',
            'sender_email': 'sender@example.com',
            'sender_password': 'PASSWORD',
            'recipient_email': 'recipient@example.com'
        }
        self.config['Charts'] = {
            'hours_back': '48',
            'table_1': 'dsl',
            'field_1': 'downstream_noise_margin',
            'label_1': 'SNR Downstream (dB)',
            'moving_average_days': '7'
        }
        self.config['Events'] = {
            'hours_back': '24',
            'exclude_types': 'VoIP',   # Zusatztypen; Clientereignisse filtert der Code selbst
            'show_level': '4'
        }
        self.config['Statistics'] = {
            'reconnects': 'True',
            'PADO_timeouts': 'False'
        }
        self.config['Reports'] = {
            'cleanup_reports': '7'
        }
        self.config['AI'] = {
            'ai_provider': 'gemini',
            'ai_api_key': 'DEIN_GEMINI_API_KEY'
        }
        self.config['Language'] = {'lang': 'de'}
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def get_lang(self):
        return self.config.get('Language', 'lang', fallback='de')

    def set_lang(self, lang):
        if 'Language' not in self.config:
            self.config['Language'] = {}
        self.config['Language']['lang'] = lang
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

# ---------------------------------------------------------------------------
# TP-LINK API CLIENT
# ---------------------------------------------------------------------------
class RouterAPI:
    def __init__(self, ip, username, password, debug=False):
        # Die Router-Firmware (Stand Sep 2026) erzwingt HTTPS: über http:// liefert der
        # Router nur die GDPR-/Willkommensseite und der Login scheitert mit
        # "Unknown error rsa_key!". Deshalb hier https:// als Standard
        # (Zertifikat ist selbst signiert, login() verwendet verify_ssl=False).
        self.host = ip if str(ip).startswith(('http://', 'https://')) else f"https://{ip}"
        self.username = username
        self.password = password
        self.debug = debug
        self.router = None
        self.logger = logging.getLogger("tplink_api")
        if self.debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.ERROR)

    def _log(self, msg):
        if self.debug:
            print(f"[API] {msg}")

    def login(self):
        if not TPLinkEXClientGCM:
            print("Fehler: tplinkrouterc6u Bibliothek nicht installiert.")
            return False
            
        usernames = [self.username]
        if self.username != "user":
            usernames.append("user")
            
        for test_user in usernames:
            self._log(f"Login Versuch mit '{test_user}' ...")
            try:
                self.router = TPLinkEXClientGCM(self.host, self.password, test_user, self.logger, verify_ssl=False)
                self.router.authorize()
                self._log("Login erfolgreich.")
                return True
            except Exception as e:
                self._log(f"Login fehlgeschlagen für '{test_user}': {e}")
        
        print("Kritischer Fehler: API Login fehlgeschlagen mit allen Benutzerkombinationen.")
        return False

    def _act(self, kind, oid, stack=None, attrs=None):
        """Einen einzelnen OID abfragen (None, wenn keine Daten).

        Wichtig: Bei Sammelabfragen entfernt die Library OIDs ohne Daten aus der
        Ergebnisliste -> die Positionen der übrigen Werte verschieben sich.
        """
        try:
            if stack:
                item = self.router.ActItem(kind, oid, stack, attrs=attrs or [])
            else:
                item = self.router.ActItem(kind, oid, attrs=attrs or [])
            _, values = self.router.req_act([item])
            return values[0] if values else None
        except Exception as e:
            self._log(f"OID {oid} konnte nicht gelesen werden: {e}")
            return None

    def get_system_info(self):
        """Nur die System-/Geräteinfos lesen (ein OID, schnell).

        Wird verwendet, wenn die Client-Erfassung abgeschaltet ist
        ([Modul] collect_clients = aus) - so bleibt der Report-Header aktuell.
        """
        if not self.router and not self.login():
            return {}
        dev_info = self._act(self.router.ActItem.GET, 'DEV2_DEV_INFO', attrs=[
            'modelName', 'softwareVersion', 'hardwareVersion', 'serialNumber', 'upTime'
        ])
        return self._system_info(dev_info)

    def _system_info(self, dev_info):
        """DEV2_DEV_INFO-Dict -> system-Dict für die Datenbank."""
        if not isinstance(dev_info, dict):
            dev_info = {}
        uptime = int(float(dev_info.get('upTime', 0) or 0))
        return {
            'model': dev_info.get('modelName', 'N/A'),
            'firmware': dev_info.get('softwareVersion', 'N/A'),
            'hardware': dev_info.get('hardwareVersion', 'N/A'),
            'serial': dev_info.get('serialNumber', 'N/A'),
            'uptime_seconds': uptime,
            'uptime_days': round(uptime / 86400, 1) if uptime > 0 else 0.0
        }

    def get_clients(self):
        if not self.router and not self.login():
            return {'error': 'Login failed'}

        try:
            # Die Firmware ab Build 260908 liefert über DEV2_HOST_ENTRY, DEV2_ADT_LAN und
            # DEV2_ADT_WIFI_CLIENT keine Daten mehr ("data": null) - get_status()
            # scheitert damit. Die Weboberfläche nutzt die APDEV-Associationslisten,
            # die hier direkt abgefragt werden (jeweils einzeln, siehe _act()).
            dev_info = self._act(self.router.ActItem.GET, 'DEV2_DEV_INFO', attrs=[
                'modelName', 'softwareVersion', 'hardwareVersion', 'serialNumber', 'upTime'
            ])
            wlan_clients = self.router._to_list(self._act(self.router.ActItem.GL, 'DEV2_WIFI_APDEV_ASSOCDEV'))
            lan_clients = self.router._to_list(self._act(self.router.ActItem.GL, 'DEV2_WIFI_APDEV_ETHASSOCDEV'))
            dev_info = dev_info if isinstance(dev_info, dict) else {}
            if not dev_info and not wlan_clients and not lan_clients:
                self._log("Router lieferte keine Client-/Systemdaten (OIDs leer).")

            result = {
                'timestamp': time.time(),
                'system': self._system_info(dev_info),
                'wlan': [],
                'lan': []
            }

            # Feldnamen wie in der Weboberfläche
            for c in wlan_clients:
                mac = str(c.get('MACAddress', '')).replace("-", ":").upper()
                if not mac:
                    continue
                result['wlan'].append({
                    'mac': mac,
                    'hostname': c.get('X_TP_HostName', ''),
                    'ip': c.get('X_TP_IPAddress', ''),
                    'is_connected': 1 if str(c.get('active', '1')) == '1' else 0,
                    'signal_strength': int(float(c.get('signalStrength', 0) or 0)),
                    'download_rate_mbps': int(float(c.get('lastDataDownlinkRate', 0) or 0)) // 1000,
                    'upload_rate_mbps': int(float(c.get('lastDataUplinkRate', 0) or 0)) // 1000,
                    'link_speed_mbps': 0,
                    'bytes_total': 0  # liefert die API nicht
                })

            for c in lan_clients:
                mac = str(c.get('MACAddress', '')).replace("-", ":").upper()
                if not mac:
                    continue
                # Nur LAN-Clients liefern echte Byte-Zähler (WLAN-Clients: bytes = 0,
                # Firmware füllt sie nicht). 32-Bit-Zähler -> nur Momentaufnahme.
                rx = int(float(c.get('bytesReceived', 0) or 0))
                tx = int(float(c.get('bytesSent', 0) or 0))
                result['lan'].append({
                    'mac': mac,
                    'hostname': c.get('X_TP_HostName', ''),
                    'ip': c.get('IPAddress', ''),
                    'is_connected': 1 if str(c.get('active', '1')) == '1' else 0,
                    'signal_strength': 0,
                    'download_rate_mbps': 0,
                    'upload_rate_mbps': 0,
                    'link_speed_mbps': int(float(c.get('linkSpeed', 0) or 0)),
                    'bytes_received': rx,
                    'bytes_sent': tx,
                    'bytes_total': rx + tx
                })

            return result
        except Exception as e:
            return {'error': str(e)}

    def close(self):
        """Sitzung beenden - der Router erlaubt nur eine Admin-Sitzung (wichtig vor
        einem Wechsel zur Weboberfläche)."""
        if self.router:
            try:
                self.router.logout()
            except Exception:
                pass
            self.router = None

    def get_dsl_data(self):
        if not self.router and not self.login(): return {}
        try:
            # Einzelabfragen (siehe _act()): Sammelabfragen verschieben bei leeren OIDs
            # die Ergebnisliste und würden falsche Werte zuordnen.
            line = self._act(self.router.ActItem.GET, 'DEV2_DSL_LINE', '1,0,0,0,0,0', attrs=[
                'upstreamMaxBitRate', 'downstreamMaxBitRate',
                'upstreamNoiseMargin', 'downstreamNoiseMargin',
                'upstreamAttenuation', 'downstreamAttenuation'
            ])
            channel = self._act(self.router.ActItem.GET, 'DEV2_DSL_CHANNEL', '1,0,0,0,0,0', attrs=[
                'upstreamCurrRate', 'downstreamCurrRate'
            ])
            wan_values = self._act(self.router.ActItem.GL, 'DEV2_ADT_WAN', attrs=[
                'connIPv4Address', 'connIPv6Address', 'connStatusV4', 'connStatusV6'
            ])
            # Einzelne OIDs können leer zurückkommen (Router-/Firmwarezustand)
            line = line if isinstance(line, dict) else {}
            channel = channel if isinstance(channel, dict) else {}
            if not line and not channel:
                self._log("DSL-OIDs (DEV2_DSL_LINE/DEV2_DSL_CHANNEL) lieferten keine Daten.")
                return {}
            
            wan = {}
            for w in self.router._to_list(wan_values):
                if w.get('connStatusV4') == 'Connected' or w.get('connStatusV6') == 'Connected':
                    wan = w; break
            if not wan and wan_values:
                wan = wan_values[0] if isinstance(wan_values, list) else wan_values
            
            up_curr = int(float(channel.get('upstreamCurrRate', 0)))
            down_curr = int(float(channel.get('downstreamCurrRate', 0)))
            up_max = int(float(line.get('upstreamMaxBitRate', 0)))
            down_max = int(float(line.get('downstreamMaxBitRate', 0)))

            # Die neue Router-Firmware liefert upstreamCurrRate/downstreamCurrRate = 0.
            # Wie in vx-info.py auf die Maximalrate zurückfallen, damit keine 0 im
            # Report/in der Datenbank landet.
            if up_curr <= 0:
                up_curr = up_max
            if down_curr <= 0:
                down_curr = down_max
            
            return {
                "Aktuelle Upload-Rate (kbit/s)": up_curr,
                "Aktuelle Download-Rate (kbit/s)": down_curr,
                "Maximale Upload-Rate (kbit/s)": up_max,
                "Maximale Download-Rate (kbit/s)": down_max,
                "Signal-Rausch-Abstand Upload (dB)": int(float(line.get('upstreamNoiseMargin', 0))) / 10,
                "Signal-Rausch-Abstand Download (dB)": int(float(line.get('downstreamNoiseMargin', 0))) / 10,
                "Leitungsdämpfung Upload (dB)": int(float(line.get('upstreamAttenuation', 0))) / 10,
                "Leitungsdämpfung Download (dB)": int(float(line.get('downstreamAttenuation', 0))) / 10,
                "ip4_curr": wan.get('connIPv4Address', ''),
                "ip6_curr": wan.get('connIPv6Address', ''),
                "ucrc": 0, "dcrc": 0 # API liefert CRC nicht immer zuverlässig im Quick-Fetch
            }
        except Exception as e:
            self._log(f"Fehler DSL-Daten: {e}")
            return {}

    def downloadrouterlog_to_memory(self):
        if not self.router and not self.login(): return None
        try:
            # Der Datei-Download (/cgi/log?down) ist auf der aktuellen Firmware
            # zuverlässig; der verschlüsselte Weg scheitert dort mit "Incorrect padding".
            text = self._downloadrouterlog_http_fallback()
            if text:
                return text
            self._log("HTTP-Download ohne Ergebnis, versuche verschlüsselten API-Weg...")
            url = self.router._get_url('cgi/log')
            code, response = self.router._request(url, data_str="", encrypt=True)
            return routerlog.clean_log_text(response) if code == 200 else None
        except Exception as e:
            self._log(f"Verschlüsselter Log-Download fehlgeschlagen ({e}), versuche HTTP-Fallback...")
            return self._downloadrouterlog_http_fallback()

    def _downloadrouterlog_http_fallback(self):
        """Fallback: Log als Dateidownload über cgi/log?down (wie Playwright, ohne AES-GCM)."""
        try:
            import ssl
            import urllib.request

            base_url = self.router.host
            logurl = f"{base_url}/cgi/log?down"
            self._log(f"HTTP-Fallback Log-Download: {logurl}")

            cookie_str = "; ".join([f"{c.name}={c.value}" for c in self.router.req.cookies])
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'text/plain,*/*;q=0.8',
                'Referer': base_url,
                'Cookie': cookie_str
            }
            if self.router._token:
                headers['TokenID'] = self.router._token

            context = ssl._create_unverified_context()
            req = urllib.request.Request(logurl, headers=headers)
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                logcontent = response.read().decode('utf-8')

            if logcontent and len(logcontent) > 20:
                self._log(f"HTTP-Fallback erfolgreich: {len(logcontent)} Zeichen.")
                return routerlog.clean_log_text(logcontent)
            return None
        except Exception as e:
            self._log(f"HTTP-Fallback fehlgeschlagen: {e}")
            return None

# ---------------------------------------------------------------------------
# WEBGUI (Headless-Browser: Router-Tabellen aufwecken + DSL-Fehlerzähler)
# ---------------------------------------------------------------------------
class RouterBrowser:
    """Nur für Dinge, die die JSON-API nicht kann.

    Die Firmware (Stand Okt 2026) füllt ihre DSL-/Client-Tabellen erst, wenn die
    Weboberfläche sie angefragt hat - ohne das liefert die API dauerhaft leer.
    Außerdem gibt es die DSL-Fehlerzähler (UCRC/DCRC) ausschließlich dort.
    """

    def __init__(self, ip, username, password, debug=False):
        self.ip = ip
        self.username = username
        self.password = password
        self.debug = debug
        self.playwright = None
        self.browser = None
        self.page = None

    def _log(self, msg):
        if self.debug:
            print(f"[WebUI] {msg}")

    def login(self, timeout_ms=15000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("Hinweis: 'playwright' fehlt - Weboberfläche nicht verfügbar."
                  " Installation: pip install -r requirements.txt && playwright install chromium")
            return False
        try:
            self.playwright = sync_playwright().start()
            # Sparsame Einstellungen (Chromium ist auf einem Pi der teuerste Teil)
            self.browser = self.playwright.chromium.launch(headless=True, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                '--disable-gpu', '--disable-software-rasterizer', '--disable-extensions',
                '--disable-background-networking', '--disable-sync', '--disable-default-apps',
                '--disable-translate', '--no-first-run', '--mute-audio',
                '--js-flags=--max-old-space-size=256'])
            context = self.browser.new_context(ignore_https_errors=True,
                                               viewport={'width': 1280, 'height': 800})
            # Bilder/Medien/Schriften blocken - spart CPU und RAM (JS/CSS bleiben nötig)
            try:
                context.route('**/*', lambda route: route.abort()
                              if route.request.resource_type in ('image', 'media', 'font')
                              else route.continue_())
            except Exception:
                pass
            self.page = context.new_page()
            self.page.set_default_timeout(30000)

            response = self.page.goto(f"https://{self.ip}", wait_until='load')
            status = response.status if response else None
            # Mehrere Versuche: auf langsamen Geräten ist das Login-JS noch nicht bereit
            for attempt in (1, 2, 3):
                try:
                    form = self.page.wait_for_selector('#pc-login-user', state='attached', timeout=timeout_ms)
                except Exception:
                    if self._logged_in(timeout_ms=3000):
                        self._log("Bereits angemeldet.")
                        return True
                    print(f"Warnung: Loginformular nicht gefunden (HTTP {status})."
                          " Läuft noch eine andere Admin-Sitzung?")
                    return False
                try:
                    self._log(f"Login-Versuch {attempt}...")
                    self.page.evaluate(f"document.getElementById('pc-login-user').value = '{self.username}';")
                    self.page.evaluate(f"document.getElementById('pc-login-password').value = '{self.password}';")
                    time.sleep(1.0)
                    self.page.evaluate("const b = document.getElementById('pc-login-btn'); if (b) b.click();")
                    time.sleep(2)
                    if self.page.evaluate("() => !!(document.body && document.body.innerText"
                                          " && document.body.innerText.toLowerCase().includes('gleichzeitig anmelden'))"):
                        self.page.evaluate("document.querySelector('.btn-msg-ok')?.click();")
                        time.sleep(1)
                    if self._logged_in(timeout_ms=8000):
                        return True
                except Exception as e:
                    # z. B. "Execution context was destroyed" während einer Navigation
                    self._log(f"Versuch {attempt} abgebrochen: {e}")
                try:
                    self.page.reload(wait_until='load')
                    time.sleep(1.5)
                except Exception:
                    pass
            print("Warnung: Login in der Weboberfläche fehlgeschlagen.")
            return False
        except Exception as e:
            print(f"Warnung: Weboberfläche nicht nutzbar: {e}")
            return False

    def _logged_in(self, timeout_ms=15000):
        """Eingeloggten Zustand erkennen - Elementnamen sind je Firmware unterschiedlich,
        deshalb zusätzlich der Text-Fallback ('Ausloggen'/'Log out')."""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            try:
                if self.page.query_selector('#topLogout, ul#ul-nav, #logOut, .logout, a[href*="logout"]'):
                    return True
                text = (self.page.evaluate("() => document.body ? document.body.innerText : ''") or '').lower()
                if 'ausloggen' in text or 'log out' in text or 'logout' in text:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _page_text(self, limit=200):
        """Sichtbarer Text der Seite (mit Schutz gegen noch nicht geladenes DOM)."""
        try:
            text = self.page.evaluate("() => document.body ? document.body.innerText : ''") or ''
        except Exception:
            return ''
        return " ".join(text.split())[:limit]

    def _read_ids(self, ids):
        try:
            return self.page.evaluate("""(ids) => {
                const out = {};
                for (const [k, id] of Object.entries(ids)) {
                    const el = document.getElementById(id);
                    out[k] = el ? (el.textContent || '').trim() : '';
                }
                return out;
            }""", ids)
        except Exception:
            return {}

    def _open_dsl_page(self, timeout=5000):
        try:
            self.page.locator("ul#ul-nav li").filter(has_text="Erweiterte Einstellungen").first.click(timeout=timeout)
            time.sleep(1.5)
            return True
        except Exception:
            return False

    def _open_netzplan(self, timeout_ms=15000):
        """Netzplan-Seite öffnen und warten, bis der Router die Mesh-Daten geliefert hat."""
        try:
            self.page.evaluate("""() => {
                const n = Array.from(document.querySelectorAll('li, a, span.text')).find(
                    el => el && el.innerText && el.innerText.trim().toLowerCase() === 'netzplan');
                if (n) n.click();
            }""")
        except Exception:
            return False
        start = time.time()
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                ready = self.page.evaluate("""() => {
                    const d = window.easyMeshApDeviceList, w = window.easyMeshApWifiStaList,
                          l = window.easyMeshApEthernetStaList;
                    return (Array.isArray(d) && d.length > 0) || (Array.isArray(w) && w.length > 0)
                        || (Array.isArray(l) && l.length > 0);
                }""")
            except Exception:
                ready = False
            if ready:
                self._log("Mesh-Daten geladen.")
                return True
            time.sleep(0.5)
        self._log("Mesh-Daten nicht innerhalb des Zeitlimits geladen.")
        return False

    def wake_up(self, include_clients=True):
        """Router zum Sammeln bewegen.

        include_clients=False: nur die DSL-Seite anfragen (schnell); das Öffnen des
        Netzplans inkl. Warten auf die Mesh-Daten entfällt (nur für Clientdaten nötig).
        """
        self._log(f"Wecke Router-Tabellen (DSL{', Netzplan' if include_clients else ''})...")
        if not all(self._read_ids({"a": "downstreamCurrRate", "b": "downstreamNoiseMargin"}).values()):
            self._open_dsl_page()
        if include_clients:
            self._open_netzplan()
        time.sleep(1)
        return True

    def get_dsl_error_counters(self):
        """DSL-Fehlerzähler (UCRC/DCRC) - gibt es nur in der Weboberfläche."""
        ids = {"ucrc": "UCRC", "dcrc": "DCRC"}
        values = self._read_ids(ids)
        if not all(values.values()):
            # Werte erscheinen erst kurz nach dem Wechsel auf die DSL-Seite
            self._open_dsl_page()
            deadline = time.time() + 12
            while time.time() < deadline:
                values = self._read_ids(ids)
                if all(values.values()):
                    break
                time.sleep(1.0)
        if not all(values.values()):
            self._log("Fehlerzähler (UCRC/DCRC) nicht gefunden.")
            return None
        return values

    def close(self):
        try:
            if self.page:
                try:
                    self.page.locator('#topLogout').click(timeout=8000)
                    self.page.locator('.btn-msg-ok').click(timeout=5000)
                    time.sleep(1)
                except Exception:
                    pass
        finally:
            try:
                if self.browser: self.browser.close()
            except Exception:
                pass
            try:
                if self.playwright: self.playwright.stop()
            except Exception:
                pass
            self.page = self.browser = self.playwright = None

# ---------------------------------------------------------------------------
# DATABASE MANAGER
# ---------------------------------------------------------------------------
class DatabaseManager:
    def __init__(self, db_path="router_data.db"):
        self.db_path = db_path
        self._create_tables()

    def get_hostname_by_mac(self, mac):
        """Zuletzt bekannten Hostnamen zu einer MAC liefern (für den ARP-Scan)."""
        if not mac:
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT hostname FROM clients WHERE mac = ? AND hostname IS NOT NULL"
                    " AND hostname NOT IN ('', 'Unknown', 'unknown')"
                    " ORDER BY time_ut DESC LIMIT 1", (mac,)).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Nur Basis-Tabellen (minimiert gegenüber Full-Version, aber kompatibel)
            cursor.execute('''CREATE TABLE IF NOT EXISTS system (
                id INTEGER PRIMARY KEY AUTOINCREMENT, time_ut INTEGER, model TEXT,
                firmware TEXT, hardware TEXT, serial TEXT, uptime_seconds INTEGER, uptime_days REAL)''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_time_ut ON system (time_ut)")

            cursor.execute('''CREATE TABLE IF NOT EXISTS dsl (
                id INTEGER PRIMARY KEY AUTOINCREMENT, time_ut INTEGER, upstream_curr_rate INTEGER,
                downstream_curr_rate INTEGER, upstream_max_rate INTEGER, downstream_max_rate INTEGER,
                upstream_noise_margin REAL, downstream_noise_margin REAL, upstream_attenuation REAL,
                downstream_attenuation REAL, ucrc INTEGER, dcrc INTEGER, ip4_curr TEXT, ip6_curr TEXT)''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_dsl_time_ut ON dsl (time_ut)")

            cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
                mac TEXT PRIMARY KEY, time_ut INTEGER, type TEXT, hostname TEXT, ip TEXT,
                signal_strength INTEGER, wifi_standard TEXT, is_connected BOOLEAN,
                download_rate_mbps INTEGER, upload_rate_mbps INTEGER, lan_port INTEGER,
                link_speed_mbps INTEGER, bytes_received INTEGER, bytes_sent INTEGER, bytes_total INTEGER)''')

            cursor.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, time_ut INTEGER, level_id INTEGER,
                type TEXT, event_text TEXT, UNIQUE (time_ut, level_id, type, event_text))''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_time_ut ON events (time_ut)")

            # Migration (Firmware 0.26.0): strukturierte Log-Daten (MAC/IP/Meldungs-ID)
            cursor.execute("PRAGMA table_info(events)")
            cols = {row[1] for row in cursor.fetchall()}
            for col, decl in (("msgid", "TEXT"), ("mac", "TEXT"), ("ip", "TEXT"), ("sd", "TEXT")):
                if col not in cols:
                    cursor.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_msgid_mac ON events (time_ut, msgid, mac)")

    def _run_query(self, sql, params=None):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params or [])
                if sql.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')): conn.commit()
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                return cols, [list(r) for r in cursor.fetchall()]
        except Exception as e:
            return [], []

    def insert_system(self, system_data, timestamp):
        if not system_data or system_data.get('firmware') == 'N/A': return
        
        # Check the most recent entry for firmware and serial match
        _, rows = self._run_query("SELECT id, firmware, serial FROM system ORDER BY id DESC LIMIT 1")
        
        if rows:
            last_id, last_fw, last_sn = rows[0]
            if last_fw == system_data.get('firmware') and last_sn == system_data.get('serial'):
                # Match found: Update existing entry with newer time and uptime
                self._run_query('''UPDATE system SET time_ut = ?, uptime_seconds = ?, uptime_days = ? WHERE id = ?''',
                                (int(timestamp), system_data.get('uptime_seconds', 0), system_data.get('uptime_days', 0.0), last_id))
                return

        # No match or no data: Create new entry (original behavior)
        self._run_query('''INSERT INTO system (time_ut, model, firmware, hardware, serial, uptime_seconds, uptime_days)
                           VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                        (int(timestamp), system_data.get('model', ''), system_data.get('firmware', ''),
                         system_data.get('hardware', ''), system_data.get('serial', ''),
                         system_data.get('uptime_seconds', 0), system_data.get('uptime_days', 0.0)))

    def insert_dsl(self, data, timestamp):
        if not data: return
        self._run_query('''INSERT INTO dsl (time_ut, upstream_curr_rate, downstream_curr_rate, upstream_max_rate,
                           downstream_max_rate, upstream_noise_margin, downstream_noise_margin, upstream_attenuation,
                           downstream_attenuation, ucrc, dcrc, ip4_curr, ip6_curr)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (int(timestamp), data.get('Aktuelle Upload-Rate (kbit/s)', 0), data.get('Aktuelle Download-Rate (kbit/s)', 0),
                         data.get('Maximale Upload-Rate (kbit/s)', 0), data.get('Maximale Download-Rate (kbit/s)', 0),
                         data.get('Signal-Rausch-Abstand Upload (dB)', 0.0), data.get('Signal-Rausch-Abstand Download (dB)', 0.0),
                         data.get('Leitungsdämpfung Upload (dB)', 0.0), data.get('Leitungsdämpfung Download (dB)', 0.0),
                         int(float(data.get('ucrc', 0) or 0)), int(float(data.get('dcrc', 0) or 0)),
                         data.get('ip4_curr', ''), data.get('ip6_curr', '')))

    def insert_clients(self, clients_data):
        if 'error' in clients_data: return
        ts = clients_data.get('timestamp', time.time())
        self._run_query("UPDATE clients SET is_connected = 0")
        
        batch = []
        for ctype, clist in [('wlan', clients_data.get('wlan', [])), ('lan', clients_data.get('lan', []))]:
            for c in clist:
                batch.append((c['mac'], int(ts), ctype, c.get('hostname', ''), c.get('ip', ''),
                              c.get('signal_strength', 0), 1, c.get('bytes_total', 0),
                              int(c.get('bytes_received', 0)), int(c.get('bytes_sent', 0))))
                
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany("INSERT OR REPLACE INTO clients (mac, time_ut, type, hostname, ip, signal_strength, is_connected, bytes_total, bytes_received, bytes_sent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)

    # --- Log-Import -----------------------------------------------------------
    # Formatwissen und Zeitstempel-Korrektur liegen in routerlog.py (identisch in beiden
    # Projekten) - hier bleibt nur das Speichern in der Datenbank.
    def insert_events_from_log(self, logcontent_or_path):
        from pathlib import Path
        if isinstance(logcontent_or_path, str) and '\n' in logcontent_or_path:
            lines = logcontent_or_path.splitlines()
        else:
            logpath = Path('logs') / logcontent_or_path
            if not logpath.exists():
                return 0
            with open(logpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        events, ignored = [], 0
        for line in lines:
            if not line.strip():
                continue
            event = routerlog.parse_line(line)
            if event:
                events.append(event)
            else:
                ignored += 1

        if ignored:
            print(f"Log: {ignored} Zeile(n) ohne erkennbares Format uebersprungen.")
        if not events:
            return 0

        events = routerlog.prepare_events(events)
        inserted, dupes, last_state = 0, 0, {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for e in events:
                time_ut = e['time_ut']
                state = routerlog.wifi_state(e.get('msgid'), e['event_text'])
                mac = e.get('mac')
                if mac and state:
                    prev = last_state.get((mac, state))
                    if prev is not None and abs(time_ut - prev) <= routerlog.DEDUPE_WINDOW_S:
                        dupes += 1
                        continue
                    last_state[(mac, state)] = time_ut

                cursor.execute(
                    "INSERT OR IGNORE INTO events "
                    "(time_ut, level_id, type, event_text, msgid, mac, ip, sd) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (time_ut, e['level_id'], e['type'], e['event_text'],
                     e.get('msgid'), mac, e.get('ip'), e.get('sd')),
                )
                inserted += cursor.rowcount
        if dupes:
            print(f"Log: {dupes} doppelte WLAN-Ereignisse entprellt.")
        return inserted

    def _parse_router_log_line(self, line):
        """Kompatibilitaets-Wrapper - Formatwissen liegt in routerlog.parse_line()."""
        return routerlog.parse_line(line)

    def _normalize_router_log_timestamps(self, events):
        """Kompatibilitaets-Wrapper - siehe routerlog.normalize_timestamps()."""
        return routerlog.normalize_timestamps(events)

    def purge_old_events(self, days, event_types, debug=False):
        if days <= 0 or not event_types: return
        cutoff = int(time.time()) - (days * 86400)
        placeholders = ",".join(["?"] * len(event_types))
        params = [cutoff] + event_types

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if debug:
                    sql_sel = f"SELECT datetime(time_ut, 'unixepoch', 'localtime'), type, event_text FROM events WHERE time_ut < ? AND type COLLATE NOCASE IN ({placeholders})"
                    cursor.execute(sql_sel, params)
                    for r in cursor.fetchall():
                        print(f"  -> Lösche: [{r[0]}] {r[1]:<8} | {r[2]}")

                cursor.execute(f"DELETE FROM events WHERE time_ut < ? AND type COLLATE NOCASE IN ({placeholders})", params)
                if cursor.rowcount > 0:
                    print(f"Cleanup: {cursor.rowcount} {event_types} Einträge älter als {days} Tage gelöscht.")
        except Exception as e:
            print(f"Cleanup Fehler: {e}")

# ---------------------------------------------------------------------------
# REPORTER
# ---------------------------------------------------------------------------
class Reporter:
    def __init__(self, config_mgr, db_mgr, lang='de'):
        self.config = config_mgr.config
        self.db = db_mgr
        self.db_path = db_mgr.db_path
        self.lang = lang
        self.t = TRANSLATIONS.get(lang, TRANSLATIONS['de'])
        self.router = None
        self.debug = False

    def _log(self, msg):
        if self.debug:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Report-Debug] {msg}")

    def _run_query(self, sql, params=None):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data_rows = cursor.fetchall()
            conn.close()
            return columns, [list(r) for r in data_rows]
        except Exception as e:
            self._log(f"SQL-Fehler: {e}")
            return [], []

    def _format_bytes(self, bytes_val):
        try:
            val = float(bytes_val)
        except (ValueError, TypeError):
            return "0 B"
        if val >= 1073741824: return f"{val / 1073741824:.2f} GB"
        if val >= 1048576: return f"{val / 1048576:.2f} MB"
        if val >= 1024: return f"{val / 1024:.2f} KB"
        return f"{val:.0f} Bytes"

    def _get_latest_model_name(self):
        _, rows = self.db._run_query("SELECT model FROM system ORDER BY time_ut DESC LIMIT 1")
        return rows[0][0] if rows else "Router"

    def _get_firmware_entries(self):
        """Alle Firmware-Einträge der TP-Link-Downloadseite (neueste zuerst).

        TP-Link listet dort jede Version als eigene Tabelle - bisher wurde nur die
        erste (= neueste) ausgewertet. Rückgabe: Liste von dicts mit
        title, version (Tupel), version_str, date_ut, notes_html, link.
        """
        import urllib.request
        url = "https://www.tp-link.com/de/support/download/vx231v/#Firmware"
        entries = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8', errors='ignore')

            for table_content in re.findall(
                    r'<table[^>]*class="download-resource-table"[^>]*>(.*?)</table>', content, re.S | re.I):
                title_match = re.search(r'<th[^>]*class="download-resource-name"[^>]*>.*?<p>(.*?)</p>',
                                        table_content, re.S | re.I)
                title = title_match.group(1).strip() if title_match else "Unbekannt"

                link_match = re.search(r'href="([^"]+\.zip)"', table_content, re.I)
                link = link_match.group(1).strip() if link_match else None

                date_ut = 0
                date_match = re.search(r'Datum der Veröffentlichung:.*?</span>\s*<span>(.*?)</span>',
                                       table_content, re.S | re.I)
                if date_match:
                    try:
                        date_ut = int(datetime.strptime(date_match.group(1).strip(), '%Y-%m-%d').timestamp())
                    except Exception:
                        pass

                notes_html = ""
                more_row = re.search(r'<tr[^>]*class="more-info"[^>]*>(.*?)</tr>', table_content, re.S | re.I)
                if more_row:
                    td_match = re.search(r'<td[^>]*class="more"[^>]*>(.*?)</td>', more_row.group(1), re.S | re.I)
                    if td_match:
                        notes_html = td_match.group(1).strip()

                # Version aus Titel (bevorzugt) oder Dateiname: ..._V1_0.26.0 Build ...
                version_str = ""
                for source in (title, link.split('/')[-1] if link else ""):
                    m = re.search(r'_V?\d+_((\d+\.)+\d+)', source) or re.search(r'_V?(\d+\.\d[\d\.]*)_', source)
                    if m:
                        version_str = m.group(1)
                        break

                entries.append({'title': title, 'version_str': version_str,
                                'version': self._extract_version_tuple(version_str),
                                'date_ut': date_ut, 'notes_html': notes_html, 'link': link})
        except Exception as e:
            self._log(f"Firmware-Scraping fehlgeschlagen: {e}")
        return entries

    def _extract_version_tuple(self, fw_str, fallback_str=None):
        """Versionsnummer in ein vergleichbares Tupel wandeln.

        Online:  '0.26.0'   (aus ..._V1_0.26.0 Build ...)
        Lokal:   '231.0.26' (Router-softwareVersion) -> (0, 26)
        """
        if not fw_str:
            return (0,)

        def to_tuple(text):
            m = re.search(r'(\d+(?:\.\d+)+)', text)
            if not m:
                return None
            parts = [int(p) for p in m.group(1).split('.')]
            while len(parts) > 2 and parts[-1] == 0:
                parts.pop()
            return tuple(parts) if parts else None

        # Lokale Schreibweise 231.x.y -> führende Geräteversion entfernen
        if fw_str.startswith('231.'):
            m = re.match(r'^231\.((\d+\.)*\d+)', fw_str)
            if m:
                return to_tuple(m.group(1)) or (0,)

        result = to_tuple(fw_str)
        if result:
            return result
        if fallback_str:
            m = re.search(r'_V?[\d\.]+_((\d+\.)+\d+)', fallback_str)
            if m:
                return to_tuple(m.group(1)) or (0,)
        return (0,)

    def _get_latest_firmware_info(self):
        import urllib.request
        url = "https://www.tp-link.com/de/support/download/vx231v/#Firmware"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8', errors='ignore')
            table_match = re.search(r'<table[^>]*class="download-resource-table"[^>]*>(.*?)</table>', content, re.S | re.I)
            if not table_match: return None, None, None, None
            table_content = table_match.group(1)
            title_match = re.search(r'<th[^>]*class="download-resource-name"[^>]*>.*?<p>(.*?)</p>', table_content, re.S | re.I)
            title = title_match.group(1).strip() if title_match else "Unbekannt"
            
            dl_link_match = re.search(r'href="([^"]+\.zip)"', table_content, re.I)
            dl_link = dl_link_match.group(1).strip() if dl_link_match else None
            
            date_match = re.search(r'Datum der Veröffentlichung:.*?</span>\s*<span>(.*?)</span>', table_content, re.S | re.I)
            date_ut = 0
            if date_match:
                try: date_ut = int(datetime.strptime(date_match.group(1).strip(), '%Y-%m-%d').timestamp())
                except: pass
            more_row = re.search(r'<tr[^>]*class="more-info"[^>]*>(.*?)</tr>', table_content, re.S | re.I)
            notes_html = ""
            if more_row:
                td_match = re.search(r'<td[^>]*class="more"[^>]*>(.*?)</td>', more_row.group(1), re.S | re.I)
                if td_match: notes_html = td_match.group(1).strip()
            return title, date_ut, notes_html, dl_link
        except Exception as e:
            self._log(f"Firmware-Scraping fehlgeschlagen: {e}")
            return None, None, None, None

    def _check_firmware_update(self):
        """Neuere Firmware-Versionen zur installierten ermitteln.

        TP-Link veröffentlicht teils mehrere Versionen gleichzeitig (z. B. 0.25.0 und
        0.26.0 - letztere verlangt laut Release Notes zuerst 0.25.0). Deshalb werden
        ALLE Einträge der Downloadseite ausgewertet, deren Version neuer ist.

        Rückgabe: (anzeigen?, vorherige_version, installierte_version, eintraege)
        eintraege: Liste der neueren Versionen (neueste zuerst); im 48-h-Fall
        (Version ist aktuell, gerade aktualisiert) die Notizen zur installierten Version.
        """
        entries = self._get_firmware_entries()
        _, rows = self.db._run_query("SELECT firmware, time_ut FROM system ORDER BY id DESC LIMIT 2")
        if not rows or len(rows) < 1:
            return False, None, None, []

        act_fw = rows[0][0]
        old_fw = rows[1][0] if len(rows) > 1 else None
        old_ts = int(rows[1][1]) if len(rows) > 1 else 0
        act_v = self._extract_version_tuple(act_fw)

        if act_v != (0,):
            newer = [e for e in entries if e['version'] != (0,) and act_v < e['version']]
            if newer:
                return True, old_fw, act_fw, newer

            # Installierte Version ist aktuell -> 48 h lang die Release Notes zeigen
            cutoff = (datetime.now() - timedelta(hours=48)).timestamp()
            if old_fw and old_fw != act_fw and old_ts > cutoff:
                # Wie beim Sprung 0.24 -> 0.26: alle Versionen zeigen, die seit dem
                # vorherigen Stand dazugekommen sind (Zwischenschritte inklusive).
                old_v = self._extract_version_tuple(old_fw)
                if old_v != (0,) and old_v < act_v:
                    match = [e for e in entries if e['version'] != (0,) and old_v < e['version']]
                else:
                    match = [e for e in entries if e['version'] == act_v]
                return True, old_fw, act_fw, match or entries[:1]

        return False, old_fw, act_fw, []

    def _build_client_sessions(self, hours=24):
        """Client-Sitzungen aus den Log-Ereignissen (Formatwissen: routerlog.py)."""
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        _, rows = self.db._run_query(routerlog.SESSION_SQL, params=[start_ts])

        router_ip = self.config.get('Router', 'router_ip', fallback='192.168.1.1')
        parts = router_ip.split('.')
        return routerlog.build_client_sessions(rows, self._home_subnet())


    def _get_connected_clients(self, hours=24):
        client_activity = self._build_client_sessions(hours=hours)
        current_time = datetime.now().timestamp()

        # Active calculation
        active_macs = set()
        for mac, sessions in client_activity.items():
            if not sessions: continue
            last_end = sessions[-1]['end']
            if current_time - last_end <= 300:
                active_macs.add(mac)

        # ADDITION: Include clients explicitly marked as connected by the last API fetch
        sql_conn = "SELECT mac FROM clients WHERE is_connected = 1 AND mac IS NOT NULL"
        _, conn_rows = self.db._run_query(sql_conn)
        for r in conn_rows:
            if r[0]:
                active_macs.add(r[0].upper())

        router_ip = self.config.get('Router', 'router_ip', fallback='192.168.1.1')
        parts = router_ip.split('.')
        home_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.%" if len(parts) == 4 else "192.168.1.%"

        sql_home = "SELECT hostname, ip, type, lan_port, mac FROM clients WHERE ip LIKE ?"
        _, home_rows = self.db._run_query(sql_home, [home_subnet])
        sql_guest = "SELECT hostname, ip, type, lan_port, mac FROM clients WHERE ip NOT LIKE ? AND ip IS NOT NULL AND ip != ''"
        _, guest_rows = self.db._run_query(sql_guest, [home_subnet])

        def ip_sort_key(ip_str):
            if not ip_str: return (0,0,0,0)
            try:
                return tuple(int(x) for x in ip_str.split('.'))
            except:
                return (0,0,0,0)

        home_rows.sort(key=lambda x: ip_sort_key(x[1]))
        guest_rows.sort(key=lambda x: ip_sort_key(x[1]))

        home_active = [r for r in home_rows if r[4] and r[4].upper() in active_macs]
        guest_active = [r for r in guest_rows if r[4] and r[4].upper() in active_macs]

        # Anwesenheitszeit pro MAC aufsummieren
        presence_seconds = {}
        for mac, sessions in client_activity.items():
            total = sum(
                (s['end'] or current_time) - s['start']
                for s in sessions
            )
            presence_seconds[mac.upper()] = total

        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        for mac in active_macs:
            if mac not in presence_seconds:
                presence_seconds[mac] = int(current_time) - start_ts

        return {'home': home_active, 'guest': guest_active, 'presence_seconds': presence_seconds}

    def _get_data_volume_clients(self):
        sql = "SELECT hostname, ip, (bytes_received + bytes_sent) as total_bytes, bytes_sent, bytes_received FROM clients WHERE bytes_received > 0 OR bytes_sent > 0 ORDER BY total_bytes DESC"
        _, rows = self.db._run_query(sql)
        return rows

    def _get_events(self, hours=24, exclude_types=None, show_level=4):
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        # Alle Filterregeln (Ausschlusstypen, eigene Abrufe, Routine) liegen zentral
        # in routerlog.py und gelten dadurch in beiden Projekten identisch.
        where, params = routerlog.event_where(self.config, exclude_types, show_level)
        sql = (f"SELECT time_ut, type, event_text, level_id FROM events WHERE time_ut >= ? {where} "
               "ORDER BY time_ut DESC")
        _, rows = self.db._run_query(sql, [start_ts] + params)
        return [[datetime.fromtimestamp(int(r[0])).strftime('%d.%m.%y %H:%M:%S'), f"{r[3]} {r[1]}", r[2]] for r in rows]

    def _get_connection_status(self):
        # Verbunden seit: neuester erfolgreicher PPP-Connect
        sql_evt = (f"SELECT time_ut FROM events WHERE type IN ({PPP_TYPES_SQL}) AND event_text LIKE '%AuthAck%' "
                   "ORDER BY time_ut DESC LIMIT 1")
        _, r_evt = self.db._run_query(sql_evt)
        sql_dsl = "SELECT ip4_curr, ip6_curr, downstream_curr_rate, upstream_curr_rate FROM dsl ORDER BY time_ut DESC LIMIT 1"
        _, r_dsl = self.db._run_query(sql_dsl)
        conn_since = datetime.fromtimestamp(int(r_evt[0][0])) if r_evt else None
        ip4, ip6, down, up = (r_dsl[0][0], r_dsl[0][1], r_dsl[0][2], r_dsl[0][3]) if r_dsl else (None, None, None, None)
        return conn_since, ip4, ip6, down, up

    def _get_ip_changes(self, limit=2):
        sql = """
              WITH ValidLogs AS (SELECT id, ip4_curr, ip6_curr, time_ut \
                                 FROM dsl \
                                 WHERE (ip4_curr IS NOT NULL AND ip4_curr != '') \
                                    OR (ip6_curr IS NOT NULL AND ip6_curr != '')),
                   CalcChanges AS (SELECT id, \
                                          ip4_curr, \
                                          ip6_curr, \
                                          time_ut, \
                                          LAG(ip4_curr) OVER (ORDER BY id) AS ip4_prev, LAG(ip6_curr) OVER (ORDER BY id) AS ip6_prev \
                                   FROM ValidLogs)
              SELECT time_ut, \
                     ip4_curr, \
                     ip6_curr
              FROM CalcChanges
              WHERE ip4_curr IS NOT ip4_prev \
                 OR ip6_curr IS NOT ip6_prev
              ORDER BY id DESC LIMIT ? \
              """
        _, rows = self.db._run_query(sql, [limit])
        return [
            [
                int(r[0]),
                datetime.fromtimestamp(int(r[0])).strftime('%d.%m.%y %H:%M:%S'),
                r[1],
            ]
            for r in rows
        ]

    def _get_last_ip_change(self, current_ip, is_ipv6=False):
        if not current_ip: return None, None
        col = "ip6_curr" if is_ipv6 else "ip4_curr"
        sql_prev = f"SELECT id, {col} FROM dsl WHERE {col} != ? AND {col} != '' AND {col} IS NOT NULL ORDER BY id DESC LIMIT 1"
        _, prev_rows = self.db._run_query(sql_prev, [current_ip])
        if not prev_rows: return None, None
        prev_id, prev_ip = prev_rows[0]
        sql_chg = f"SELECT time_ut FROM dsl WHERE id > ? AND {col} = ? ORDER BY id ASC LIMIT 1"
        _, chg_rows = self.db._run_query(sql_chg, [prev_id, current_ip])
        if chg_rows: return int(chg_rows[0][0]), prev_ip
        return None, None

    def _analyze_ppp_events(self, hours=24):
        main_query = f"""
        WITH RawData AS (
            SELECT time_ut, datetime(time_ut, 'unixepoch', 'localtime') AS ts, 
                   strftime('%H:%M', datetime(time_ut, 'unixepoch', 'localtime')) AS clock, 
                   date(time_ut, 'unixepoch', 'localtime') AS d_date, event_text,
            CASE 
                WHEN event_text LIKE '%User request%' THEN 1 
                WHEN event_text LIKE '%LCP down%' THEN 2 
                WHEN event_text LIKE '%AuthAck%' THEN 3 
                ELSE 4 
            END as p
            FROM events 
            WHERE type IN ({PPP_TYPES_SQL}) AND (event_text LIKE '%User request%' OR event_text LIKE '%LCP down%' OR event_text LIKE '%AuthAck%')
        ),
        Deduplicated AS (
            SELECT * FROM (SELECT *, ROW_NUMBER() OVER(PARTITION BY time_ut ORDER BY p) as rn FROM RawData) WHERE rn = 1
        ),
        Schedules AS (
            SELECT clock, COUNT(DISTINCT d_date) as freq FROM Deduplicated 
            WHERE event_text LIKE '%User request%' GROUP BY clock HAVING freq >= 2
        )
        SELECT d.ts, d.time_ut, d.event_text,
            CASE 
                WHEN d.event_text LIKE '%AuthAck%' THEN 'UP'
                WHEN d.event_text LIKE '%User request%' AND s.clock IS NOT NULL THEN 'ROUTER_SCHED'
                WHEN d.event_text LIKE '%User request%' THEN 'MANUAL'
                WHEN d.event_text LIKE '%LCP down%' THEN 'PROVIDER_DROP'
            END AS category
        FROM Deduplicated d LEFT JOIN Schedules s ON d.clock = s.clock
        WHERE category IS NOT NULL ORDER BY d.time_ut ASC;
        """
        try:
            _, rows = self.db._run_query(main_query)
        except Exception as e:
            self._log(f"Fehler in _analyze_ppp_events: {e}")
            return []

        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        
        processed_events = []
        last_disconnect = None
        for r in rows:
            ts, time_ut, text, cat = r
            if cat in ['ROUTER_SCHED', 'MANUAL', 'PROVIDER_DROP']:
                last_disconnect = {'ts': ts, 'time_ut': time_ut, 'category': cat}
            elif cat == 'UP' and last_disconnect:
                duration = time_ut - last_disconnect['time_ut']
                processed_events.append({
                    'disconnect_ut': last_disconnect['time_ut'],
                    'disconnect_ts': last_disconnect['ts'],
                    'category': last_disconnect['category'],
                    'duration': duration,
                    'up_ut': time_ut,
                    'up_ts': ts
                })
                last_disconnect = None
                
        return [e for e in processed_events if e['up_ut'] >= start_ts or e['disconnect_ut'] >= start_ts]

    def _get_connection_analysis(self, hours=24):
        threshold_slow_reconnect = 45
        events = self._analyze_ppp_events(hours)
        min_level = routerlog.config_int(self.config, 'Analyse', 'report_disconnects_level', 1)
        
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        start_ts_dsl = int((datetime.now() - timedelta(hours=hours + 2)).timestamp())

        try:
            _, pado_rows = self.db._run_query("SELECT COUNT(*) FROM events WHERE event_text LIKE '%PADO Timeout%' AND time_ut >= ?", [start_ts])
            pado_count = pado_rows[0][0] if pado_rows else 0

            _, dns_rows = self.db._run_query(f"SELECT datetime(time_ut, 'unixepoch', 'localtime') as ts FROM events WHERE type IN ({HTTPD_TYPES_SQL}) AND event_text LIKE '%failed%' AND time_ut >= ?", [start_ts])
            dns_errors = [r[0] for r in dns_rows]
            
            _, dsl_rows = self.db._run_query(
                "SELECT time_ut, downstream_noise_margin, downstream_curr_rate, dcrc FROM dsl WHERE time_ut >= ? ORDER BY time_ut ASC", 
                [start_ts_dsl]
            )
        except Exception:
            pado_count = 0
            dns_errors = []
            dsl_rows = []
        
        html_output = ""
        has_issues = False
        recs_list = []
        
        if pado_count > 10:
            recs_list.append(f"<li><span style='color: #d32f2f; font-weight: bold;'>{self.t['warning']}</span> {pado_count} {self.t['pado_timeout_msg']}</li>")
            if min_level <= 3:
                has_issues = True
            
        event_html = ""
        for evt in events:
            trigger = evt['category']
            duration = evt['duration']
            ts = evt['disconnect_ts']
            severity = 0
            
            trigger_labels = {
                'ROUTER_SCHED': self.t['planned_reboot'],
                'MANUAL': self.t['manual_reset'],
                'PROVIDER_DROP': self.t['provider_drop']
            }
            trigger_lbl = trigger_labels.get(trigger, trigger)
            
            recommendations = []
            if duration > threshold_slow_reconnect:
                recommendations.append(self.t['delayed_reconnect'])
                severity = max(severity, 2)
            if trigger == 'PROVIDER_DROP':
                recommendations.append(self.t['unplanned_drop'])
            
            if any(ts[:16] == d[:16] or evt['up_ts'][:16] == d[:16] for d in dns_errors):
                recommendations.append(self.t['dns_error_window'])
                severity = max(severity, 2)
                
            # DSL Korrelation
            closest_before = None
            closest_after = None
            for row in dsl_rows:
                dsl_ut = row[0]
                if dsl_ut <= evt['disconnect_ut']:
                    closest_before = row
                if dsl_ut >= evt['up_ut'] and closest_after is None:
                    closest_after = row
                    
            if closest_before:
                dsl_snr_before = closest_before[1]
                dsl_rate_before = closest_before[2]
                dsl_crc_before = closest_before[3]
                
                # SNR Check
                if isinstance(dsl_snr_before, (int, float)) and dsl_snr_before > 0 and dsl_snr_before < 6.0:
                    recommendations.append(self.t['signal_error_before_drop'].replace('{snr}', f"{dsl_snr_before} dB"))
                    severity = max(severity, 3)
                    
                # CRC Burst Check
                idx = dsl_rows.index(closest_before)
                if idx > 0:
                    prev_row = dsl_rows[idx - 1]
                    prev_crc = prev_row[3]
                    if isinstance(dsl_crc_before, (int, float)) and isinstance(prev_crc, (int, float)):
                        crc_diff = dsl_crc_before - prev_crc
                        if crc_diff > 1000:
                            recommendations.append(self.t['massive_crc_burst'].replace('{crc}', str(int(crc_diff))))
                            severity = max(severity, 3)
                            
                # Rate Check (Bandbreitenverlust nach Reconnect)
                if closest_after:
                    dsl_rate_after = closest_after[2]
                    if isinstance(dsl_rate_before, (int, float)) and isinstance(dsl_rate_after, (int, float)):
                        if dsl_rate_before > 0 and dsl_rate_after > 0:
                            if dsl_rate_after < (dsl_rate_before * 0.9):
                                diff_mbps = (dsl_rate_before - dsl_rate_after) / 1000.0
                                recommendations.append(self.t['profile_fallback'].replace('{diff}', f"{diff_mbps:.1f} Mbit/s"))
                                severity = max(severity, 2)
            
            if severity >= min_level:
                rec_str = f" | <span style='color: #ed6c02; font-weight: bold;'>{self.t['hint']}</span> " + ", ".join(recommendations) if recommendations else ""
                
                if recommendations:
                    has_issues = True
                    event_html += f"<div style='margin-bottom: 5px;'>[{ts}] {trigger_lbl} | {self.t['duration']} {duration}s{rec_str}</div>"
                else:
                    event_html += f"<div style='margin-bottom: 5px; color: #555;'>[{ts}] {trigger_lbl} | {self.t['duration']} {duration}s</div>"

        if not has_issues and not event_html:
            return ""
            html_output = f"<div style='color: #388e3c;'>{self.t['line_stable']}</div>"
        else:
            if recs_list:
                html_output += "<ul style='margin-top: 0; margin-bottom: 10px; padding-left: 20px;'>" + "".join(recs_list) + "</ul>"
            if event_html:
                html_output += f"<div style='font-family: monospace; font-size: 13px; background-color: #f5f5f5; padding: 10px; border-radius: 3px; border: 1px solid #e0e0e0;'>{event_html}</div>"

        return html_output

    def _generate_timeline(self, hours=24):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        """
        Generiert einen kompakten, visuellen Zeitstrahl für die letzten 24 Stunden.
        Markiert nur relevante Ereignisse (Internet weg/da, Systemfehler, DSL Sync).
        Gibt Base64-String des Bildes zurück oder None, wenn keine relevanten Events vorliegen.
        """
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())

        sql = "SELECT time_ut, type, event_text FROM events WHERE time_ut >= ? ORDER BY time_ut ASC"
        _, rows = self.db._run_query(sql, params=[start_ts])

        if not rows:
            return None

        ppp_events = self._analyze_ppp_events(hours)
        ppp_evt_map = {e['disconnect_ut']: e for e in ppp_events}

        timeline_events = []

        # Keywords für Kategorisierung
        # (Priorität: Rot > Gelb > Grün)
        for r in rows:
            try:
                ts = int(r[0])
                evt_type = r[1]
                text = r[2]
                dt = datetime.fromtimestamp(ts)

                category = None
                color = None
                marker = None
                label = None
                duration_text = None

                if ts in ppp_evt_map:
                    evt = ppp_evt_map[ts]
                    cat = evt['category']
                    if cat == 'ROUTER_SCHED':
                        color = '#8e24aa'
                        marker = 's'
                        label = 'Zeitplan'
                    elif cat == 'MANUAL':
                        color = '#ff9800'
                        marker = 'D'
                        label = 'Manuell'
                    elif cat == 'PROVIDER_DROP':
                        color = '#d32f2f'
                        marker = 'x'
                        label = 'Provider'
                    
                    category = "Down"
                    duration_text = f"{evt['duration']}s"

                if not category:
                    # 1. DISCONNECTS / FEHLER (ROT)
                    if "LCP down" in text or "DSL Link Status is DOWN" in text or "User request" in text:
                        category = "Down"
                        color = "#d32f2f"  # Rot
                        marker = "x"
                        label = "Down"
                    # 2. SYNC / WARNUNG (GELB)
                    elif "Initializing" in text or "EstablishingLink" in text or "dns disconnected" in text:
                        category = "Sync"
                        color = "#fbc02d"  # Gelb/Orange
                        marker = "o"
                        label = "Sync"
                    # 3. CONNECT / OK (GRÜN - Optional, gut für Feedback "Wieder da")
                    elif "DSL Link Status is UP" in text or ("ConfAck" in text and "addr" in text):
                        category = "Up"
                        color = "#388e3c"  # Grün
                        marker = "|"
                        label = "Up"
                    # System Reboots (Kritisch)
                    elif evt_type == "System" and "Log" not in text:
                        pass

                if category:
                    timeline_events.append({
                        'dt': dt,
                        'color': color,
                        'marker': marker,
                        'label': label,
                        'duration_text': duration_text
                    })

            except:
                continue

        if not timeline_events:
            pass

        # --- PLOTTING ---
        fig, ax = plt.subplots(figsize=(10, 1.2))  # Breite 10, Höhe 1.2 Zoll

        # X-Achse Limits (letzte hours Stunden)
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        ax.set_xlim(start_time, end_time)

        # Basis-Linie (Zeitstrahl)
        ax.axhline(y=0, color='#9e9e9e', linewidth=2, zorder=1)

        # Events zeichnen
        # x (Zeit) und c (Farbe) für Scatter Plot
        for evt in timeline_events:
            ax.scatter(evt['dt'], 0, color=evt['color'], marker=evt['marker'], s=100, zorder=2, label=evt['label'])
            if evt.get('duration_text'):
                ax.annotate(evt['duration_text'], (evt['dt'], 0), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=8, color=evt['color'], rotation=0)

        # Formatierung
        ax.set_ylim(-0.5, 0.5)  # Vertikal fixiert
        ax.get_yaxis().set_visible(False)  # Keine Y-Achse

        # X-Achse formatieren
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))  # Alle 3 Stunden ein Tick
        plt.xticks(fontsize=10, color='#666')

        # Rahmen entfernen
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(False)  # Linie macht axhline

        # Legende
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        if by_label:
            ax.legend(by_label.values(), by_label.keys(), loc='center left', bbox_to_anchor=(1, 0.5), frameon=False,
                      fontsize=10)

        plt.tight_layout()

        # Base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', transparent=False)
        buf.seek(0)
        img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)

        return img_str

    def debug_print_timeline_data(self):
        """
        Numerische Auflistung der Reconnect-Blöcke für die Fehlerdiagnose.
        """
        evt_hours = routerlog.config_int(self.config, 'Events', 'hours_back', 24)
        start_ts = int((datetime.now() - timedelta(hours=evt_hours)).timestamp())
        end_ts = int(datetime.now().timestamp())

        start_str = datetime.fromtimestamp(start_ts).strftime('%d.%m.%Y %H:%M')
        end_str = datetime.fromtimestamp(end_ts).strftime('%d.%m.%Y %H:%M')

        sql = f"""
              SELECT time_ut, type, event_text
              FROM events
              WHERE time_ut >= ?
                AND type NOT IN ({HIDDEN_TYPES_SQL})
              ORDER BY time_ut ASC
              """
        _, rows = self.db._run_query(sql, [start_ts])

        reconnects = []
        current_reconnect = None

        for r in rows:
            ts, typ, txt = int(r[0]), r[1], r[2]
            is_down = "User request" in txt or any(
                k in txt for k in ["LCP down", "DSL Link Status is DOWN", "TermReq", "Timeout waiting for PADO"])
            is_up = "DSL Link Status is UP" in txt or ("ConfAck" in txt and "addr" in txt) or "PAP AuthAck" in txt

            if is_down:
                if current_reconnect is None:
                    current_reconnect = {
                        'type': 'User-indiziert' if "User request" in txt else 'ISP-indiziert',
                        'events': []
                    }

            if current_reconnect is not None:
                current_reconnect['events'].append((ts, typ, txt))
                if is_up:
                    reconnects.append(current_reconnect)
                    current_reconnect = None

        print(f"\nEventübersicht von {start_str} bis {end_str}")
        print(f"es wurden {len(reconnects)} Reconnects identifiziert\n")

        for i, rec in enumerate(reconnects, 1):
            print(f"{i}. Reconnect {rec['type']}-Block")
            for ts_val, typ_val, txt_val in rec['events']:
                ts_str = datetime.fromtimestamp(ts_val).strftime('%d.%m. %H:%M:%S')
                print(f"{ts_str} {typ_val:<8} {txt_val}")
            print("-" * 40)

    def _generate_client_gantt(self, hours=24):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        client_activity = self._build_client_sessions(hours=hours)

        # Namen aus clients-Tabelle
        try:
            _, c_rows = self.db._run_query("SELECT mac, hostname FROM clients")
            mac_to_name = {r[0].upper(): r[1] for r in c_rows if r[0] and r[1]}
        except:
            mac_to_name = {}

        current_time = datetime.now().timestamp()
        start_ts = current_time - hours * 3600

        # Dauerhaft verbundene Clients ergänzen:
        # Clients mit is_connected=1, die keine DHCP-Sessions haben, werden als
        # durchgehende Linie über den gesamten Auswertungszeitraum dargestellt.
        try:
            _, always_rows = self.db._run_query(
                "SELECT mac FROM clients WHERE is_connected = 1 AND mac IS NOT NULL"
            )
            for row in always_rows:
                mac = row[0].upper() if row[0] else None
                if mac and mac not in client_activity:
                    router_ip = self.config.get('Router', 'router_ip', fallback='192.168.1.1')
                    parts = router_ip.split('.')
                    home_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}." if len(parts) == 4 else "192.168.1."
                    _, ip_rows = self.db._run_query(
                        "SELECT ip FROM clients WHERE mac = ?", params=(mac,)
                    )
                    ip = ip_rows[0][0] if ip_rows and ip_rows[0][0] else ""
                    net = 'home' if ip.startswith(home_subnet) else 'guest'
                    client_activity[mac] = [{'start': start_ts, 'end': current_time, 'network': net}]
        except Exception as e:
            self._log(f"Fehler beim Ergänzen dauerhaft verbundener Clients: {e}")

        active_clients = {k: v for k, v in client_activity.items() if v}
        if not active_clients:
            return None

        # Helper to get formatted name
        def get_formatted_name(m):
            name = mac_to_name.get(m, m).strip()
            # Anwesenheitszeit berechnen
            sessions = active_clients.get(m, [])
            total_secs = int(sum((s['end'] or current_time) - s['start'] for s in sessions))
            h = total_secs // 3600 + (1 if total_secs % 3600 > 0 else 0)
            if h > 0:
                name = f"{name} ({h} h)"
            if len(name) > 18:
                name = name[:13] + "…" + name[-4:]
            return name

        # Sortieren alphabetisch nach Name, rückwärts, damit Matplotlib A-Z von oben nach unten zeichnet
        def sort_key(m):
            return get_formatted_name(m).lower()

        sorted_macs = sorted(active_clients.keys(), key=sort_key, reverse=True)

        # Plotting
        # Schmalere Balken (0.4 statt 0.6) und engere Abstände (0.25 statt 0.4)
        fig_height = max(2, len(sorted_macs) * 0.25)
        fig, ax = plt.subplots(figsize=(10, fig_height))

        y_ticks = []
        y_labels = []

        COLOR_HOME = '#4acbd6'
        COLOR_GUEST = '#ff9800'

        for i, mac in enumerate(sorted_macs):
            sessions = active_clients[mac]

            client_label = get_formatted_name(mac)

            y_ticks.append(i)
            y_labels.append(client_label)

            for sess in sessions:
                start = datetime.fromtimestamp(sess['start'])
                end = datetime.fromtimestamp(sess['end'])
                duration = (end - start).total_seconds()

                if duration <= 0:
                    continue

                net = sess.get('network', 'home')
                bar_color = COLOR_GUEST if net == 'guest' else COLOR_HOME

                ax.barh(i, end - start, left=start, height=0.4,
                        color=bar_color, alpha=0.7, edgecolor=bar_color)

        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, fontsize=10)
        ax.tick_params(axis='y', which='both', length=0)

        end_dt = datetime.fromtimestamp(current_time)
        start_dt = end_dt - timedelta(hours=hours)
        ax.set_xlim(start_dt, end_dt)

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        
        # Zeitschritte auf der X-Achse optimieren (alle 6 Stunden bei mehr als 24h)
        if hours > 24:
            ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
        else:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=10))

        ax.grid(True, axis='x', linestyle='--', alpha=0.5)

        # 00:00 Uhr Linie durchgehend, aber im exakt gleichen Stil (Dicke/Farbe/Transparenz) wie das Grid
        for tick_date in mdates.HourLocator(interval=1).tick_values(start_dt, end_dt):
            dt = mdates.num2date(tick_date)
            if dt.hour == 0 and dt.minute == 0:
                ax.axvline(x=dt, color='#b0b0b0', linestyle='-', linewidth=0.8, alpha=0.5, zorder=1)

        ax.set_title(f"Türkis=Heimnetz, Orange=Gastnetz", fontsize=11, pad=10)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)

        return img_str

    def _generate_snr_variance_img(self, table_name, field_name, label_name):
        three_months_start = int((datetime.now() - timedelta(days=90)).timestamp())
        _, rows = self.db._run_query(f"SELECT time_ut, {field_name} FROM {table_name} WHERE time_ut >= ? AND {field_name} > 0", [three_months_start])
        
        if not rows:
            return ""
            
        hourly_data = {h: [] for h in range(24)}
        for ts, val in rows:
            try:
                hour = datetime.fromtimestamp(int(ts)).hour
                hourly_data[hour].append(float(val))
            except:
                pass
                
        hourly_avg = {}
        for h, vals in hourly_data.items():
            if vals:
                hourly_avg[h] = sum(vals) / len(vals)
                
        if not hourly_avg:
            return ""
            
        hourly_data = {h: [] for h in range(24)}
        for ts, val in rows:
            try:
                hour = datetime.fromtimestamp(int(ts)).hour
                hourly_data[hour].append(float(val))
            except:
                pass
                
        hourly_avg = {}
        for h, vals in hourly_data.items():
            if vals:
                hourly_avg[h] = sum(vals) / len(vals)
                
        if not hourly_avg:
            return ""
            
        min_avg = min(hourly_avg.values())
        max_avg = max(hourly_avg.values())
        delta = max_avg - min_avg
        
        # PNG-Bild via matplotlib generieren
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        
        fig, ax = plt.subplots(figsize=(10, 0.8))
        ax.set_xlim(0, 24)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        for h in range(24):
            avg = hourly_avg.get(h, None)
            if avg is None:
                color = '#eeeeee'
            else:
                if max_avg > min_avg:
                    score = (avg - min_avg) / delta
                else:
                    score = 0.5
                # Niedriger SNR = rot (schlecht), hoher SNR = grün (gut)
                r = min(1.0, (1 - score) * 2)
                g = min(1.0, score * 2)
                b = 0.0
                color = (r, g, b)
            
            rect = mpatches.Rectangle((h, 0), 1, 1, linewidth=0.5, edgecolor='white', facecolor=color)
            ax.add_patch(rect)
        
        # Titel (kompakt, über dem Chart)
        title = f"{self.t['daily_fluctuations']} {label_name} {self.t['last_3_months']}"
        ax.text(12, 1.6, title, fontsize=11, ha='center', va='bottom', fontweight='bold', color='#4acbd6')
        
        # Delta-Angabe
        delta_text = f"{self.t['max_hourly_fluctuation']} {delta:.2f} dB"
        ax.text(12, 1.2, delta_text, fontsize=9, ha='center', va='bottom', color='#555')
        
        # Stundenmarkierungen
        for hour_pos, label in [(0, '00:00'), (6, '06:00'), (12, '12:00'), (18, '18:00'), (24, '24:00')]:
            ax.text(hour_pos, -0.3, label, fontsize=8, ha='center', va='top', color='#888')
        
        plt.subplots_adjust(left=0.02, right=0.98, top=0.65, bottom=0.2)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight', transparent=False, facecolor='white')
        buf.seek(0)
        img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        plt.close(fig)
        
        return img_str
    
    def _calculate_median(self, data):
        if not data: return 0.0
        sorted_data = sorted(data)
        n = len(sorted_data)
        if n % 2 == 1:
            return sorted_data[n // 2]
        else:
            return (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2.0

    def _get_snr_stats(self, table, field, hours_back):
        now = datetime.now()
        moving_avg_days = routerlog.config_int(self.config, 'Charts', 'moving_average_days', 7)
        
        # 1. hours_back stats
        start_hb = int((now - timedelta(hours=hours_back)).timestamp())
        _, hb_rows = self.db._run_query(f"SELECT {field} FROM {table} WHERE time_ut >= ? AND {field} > 0", [start_hb])
        hb_vals = [float(r[0]) for r in hb_rows]
        hb_stats = {
            'max': max(hb_vals) if hb_vals else 0.0,
            'min': min(hb_vals) if hb_vals else 0.0,
            'median': self._calculate_median(hb_vals)
        }

        # 2. X-day median (default 7)
        start_xd = int((now - timedelta(days=moving_avg_days)).timestamp())
        _, dx_rows = self.db._run_query(f"SELECT {field} FROM {table} WHERE time_ut >= ? AND {field} > 0", [start_xd])
        dx_vals = [float(r[0]) for r in dx_rows]
        median_xd = self._calculate_median(dx_vals)

        # 3. 3-month stats
        start_3m = int((now - timedelta(days=90)).timestamp())
        _, m3_rows = self.db._run_query(f"SELECT {field} FROM {table} WHERE time_ut >= ? AND {field} > 0", [start_3m])
        m3_vals = [float(r[0]) for r in m3_rows]
        m3_stats = {
            'max': max(m3_vals) if m3_vals else 0.0,
            'min': min(m3_vals) if m3_vals else 0.0,
            'median': self._calculate_median(m3_vals)
        }
        
        return hb_stats, median_xd, m3_stats, moving_avg_days

    def _generate_charts(self, hours=24):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        charts = []
        
        moving_avg_days = routerlog.config_int(self.config, 'Charts', 'moving_average_days', 7)
        
        for i in range(1, 5):
            table = self.config.get('Charts', f'table_{i}', fallback=None)
            field = self.config.get('Charts', f'field_{i}', fallback=None)
            label = self.config.get('Charts', f'label_{i}', fallback=field)
            if not table or not field: continue
            
            # Haupt-Daten für den Anzeige-Zeitraum
            start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
            _, rows = self.db._run_query(f"SELECT time_ut, {field} FROM {table} WHERE time_ut >= ? ORDER BY time_ut", [start_ts])
            if not rows: continue
            
            ts, vs = [], []
            for r in rows:
                try:
                    v = float(r[1])
                    if v != 0:
                        ts.append(datetime.fromtimestamp(int(r[0])))
                        vs.append(v)
                except: continue
            if not vs: continue
            
            fig, ax = plt.subplots(figsize=(12, 4))
            # ax.plot(ts, vs, color='#4acbd6', linewidth=2, marker='o', markerfacecolor='#93365e', markeredgecolor='#93365e', markersize=6, label=label)
            ax.plot(ts, vs, color='#4acbd6', linewidth=2, marker='o', markerfacecolor='#4acbd6', markeredgecolor='#4acbd6', markersize=6, label=label)
            ax.fill_between(ts, vs, min(vs)-0.1, color='#4acbd6', alpha=0.1)
            
            # SPEZIALFALL: SNR Downstream (meist i=1) - Gleitender Durchschnitt
            if i == 1:
                # Hole Daten für gleitenden Durchschnitt (Anzeigezeitraum + N Tage Puffer davor)
                ma_start_ts = int((datetime.now() - timedelta(hours=hours, days=moving_avg_days)).timestamp())
                _, ma_rows = self.db._run_query(f"SELECT time_ut, {field} FROM {table} WHERE time_ut >= ? AND {field} > 0 ORDER BY time_ut", [ma_start_ts])
                
                if ma_rows:
                    ma_ts_all = [int(r[0]) for r in ma_rows]
                    ma_vs_all = [float(r[1]) for r in ma_rows]
                    
                    ma_curve_ts = []
                    ma_curve_vs = []
                    
                    # Für jeden Punkt im Anzeige-Zeitraum berechne Durchschnitt der letzten N Tage
                    window_sec = moving_avg_days * 24 * 3600
                    
                    # Effizienterer gleitender Durchschnitt (einfachere Implementierung ohne neue Imports)
                    for target_t in [int(r[0]) for r in rows]:
                        window_vals = [ma_vs_all[j] for j, ts_val in enumerate(ma_ts_all) if (target_t - window_sec) <= ts_val <= target_t]
                        if window_vals:
                            ma_curve_ts.append(datetime.fromtimestamp(target_t))
                            ma_curve_vs.append(sum(window_vals) / len(window_vals))
                    
                    if ma_curve_vs:
                        ax.plot(ma_curve_ts, ma_curve_vs, color='#666666', linestyle='--', linewidth=1.5, alpha=0.9, label=f'Ø {moving_avg_days} Tage')
                
                ax.legend(loc='lower left', fontsize=10, frameon=True)
                        
            ax.grid(True, linestyle='--', linewidth=0.5, color='#ddd')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.\n%H:%M'))
            
            # Y-Achse optimieren: Fokus auf die aktuellen Werte
            if vs:
                v_min, v_max = min(vs), max(vs)
                margin = (v_max - v_min) * 0.2 if v_max > v_min else 1.0
                ax.set_ylim(v_min - margin, v_max + margin)

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            buf.seek(0)
            charts.append((label, base64.b64encode(buf.getvalue()).decode('utf-8')))
            plt.close(fig)
        return charts

    def _run_ai_analysis(self, hours=48):
        import csv
        import subprocess
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        cols, rows = self.db._run_query("SELECT datetime(time_ut, 'unixepoch', 'localtime'), downstream_curr_rate, downstream_noise_margin, dcrc FROM dsl WHERE time_ut >= ? ORDER BY time_ut ASC", [start_ts])
        if not rows: return None
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(cols)
        writer.writerows(rows)
        exclude = [t.strip() for t in self.config.get('Events', 'exclude_types', fallback='').split(',') if t.strip()]
        filtered_events = self._get_events(hours=48, exclude_types=exclude)
        events_as_text = ", ".join(str(event) for event in filtered_events)
        prompt = """Du bist ein Senior-Diagnostiker für DSL-/VDSL-Leitungen. Deine Aufgabe ist ausschließlich die Erkennung technischer Auffälligkeiten und Verschlechterungen in den übergebenen Leitungs- und Ereignisdaten.
        Ziel:
        Bewerte, ob die Daten auf eine instabile oder verschlechterte Leitung hindeuten. Erstelle keinen allgemeinen Statusreport und keine Beschreibung des Reports.

        Bewertungslogik:
        Beurteile die Daten als Gesamtsystem. Ein einzelnes Routineereignis ist kein Problem, solange keine weiteren Auffälligkeiten es stützen.
        Als unkritisch gelten insbesondere:
        - eine einzelne tägliche Leitungsrennung,
        - geplante oder regelmäßig wiederkehrende Router-Trennungen,
        - normale Reconnects ohne Verschlechterung der DSL-Werte.

        Als relevant gelten nur Muster oder Kombinationen wie:
        - sinkender oder dauerhaft niedriger Downstream-SNR,
        - steigende Fehlerwerte oder Fehler-Bursts,
        - ungewöhnlich häufige Reconnects,
        - verlängerte Wiederverbindungszeiten,
        - Profilrückfall oder reduzierte Sync-Rate nach Trennung,
        - zeitliche Korrelation mehrerer negativer Signale.

        Ausgabe-Regeln:
        - Wenn keine belastbare Auffälligkeit vorliegt, antworte exakt: Verbindung ist stabil.
        - Wenn eine Auffälligkeit vorliegt, antworte mit maximal drei kurzen Sätzen als Fließtext.
        - Beschreibe nur Befund und wahrscheinlichste technische Ursache.
        - Erwähne nur Ereignisse, die zur Diagnose beitragen.
        - Keine Aufzählungen.
        - Keine Rohdatenwiederholung.
        - Keine Erwähnung fehlender Firmware, Updates oder belangloser Routineereignisse.
        - Keine Spekulationen ohne Datengrundlage.
        - Wenn die Evidenz schwach oder uneinheitlich ist, benenne das ausdrücklich knapp, z. B. 'Hinweis auf …, aber nicht eindeutig'.

        Qualitätskontrolle vor Ausgabe:
        - Prüfe, ob die Antwort entweder exakt 'Verbindung ist stabil.' ist oder aus höchstens drei Sätzen besteht.
        - Entferne jeden Satz ohne direkten Diagnosewert.
        """
        
        if self.lang == 'en':
            prompt += "\nIMPORTANT: You MUST provide your final response purely in ENGLISH language."
        else:
            prompt += "\nWICHTIG: Erstelle deine finale Antwort zwingend auf DEUTSCH."

        prompt += "\n\nCSV Daten:\n" + output.getvalue() + events_as_text

        provider = self.config.get('AI', 'ai_provider', fallback=None)
        api_key = self.config.get('AI', 'ai_api_key', fallback=None)
        
        if provider == "gemini" and api_key:
            try:
                import urllib.request
                import urllib.parse
                import json
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={urllib.parse.quote(api_key)}"
                data = json.dumps({"contents": [{"parts":[{"text": prompt}]}]}).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    res_json = json.loads(response.read().decode('utf-8'))
                    try:
                        out = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                        if out: return out
                    except (KeyError, IndexError):
                        self._log("Fehler beim Parsen der Gemini API Antwort.")
            except Exception as e:
                self._log(f"Fehler bei Gemini API-Analyse: {e}")
                
        try:
            res = subprocess.run(["shortcuts", "run", "ai-cloud"], input=prompt.encode('utf-8'), capture_output=True, timeout=60)
            if res.returncode == 0:
                out = res.stdout.decode('utf-8', errors='ignore').strip()
                if out: return out
        except Exception as e:
            self._log(f"Fehler beim Aufruf des Apple Shortcuts 'ai-cloud': {e}")
            
        return None

    def _get_reconnect_stats(self, hours):
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        sql = (f"SELECT time_ut, type, event_text FROM events WHERE time_ut >= ? "
               f"AND type NOT IN ({HIDDEN_TYPES_SQL}) ORDER BY time_ut ASC")
        _, rows = self.db._run_query(sql, [start_ts])
        reconnects = 0
        current_reconnect = None
        for r in rows:
            ts, typ, txt = int(r[0]), r[1], r[2]
            is_down = "User request" in txt or any(
                k in txt for k in ["LCP down", "DSL Link Status is DOWN", "TermReq", "Timeout waiting for PADO"])
            is_up = "DSL Link Status is UP" in txt or ("ConfAck" in txt and "addr" in txt) or "PAP AuthAck" in txt

            if is_down:
                if current_reconnect is None:
                    current_reconnect = True
            if current_reconnect:
                if is_up:
                    reconnects += 1
                    current_reconnect = None
        return reconnects

    def _get_router_uptime(self):
        _, rows = self.db._run_query("SELECT uptime_seconds FROM system ORDER BY time_ut DESC LIMIT 1")
        if rows:
            seconds = int(rows[0][0])
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return days, hours
        return None

    def _home_subnet(self):
        """Heimnetz-Präfix für die Heim/Gast-Unterscheidung (aus routerip)."""
        router_ip = self.config.get('Router', 'router_ip', fallback='192.168.1.1')
        parts = router_ip.split('.')
        return f"{parts[0]}.{parts[1]}.{parts[2]}." if len(parts) == 4 else "192.168.1."

    def generate_report(self, send_email=True, show_browser=False):
        import smtplib
        from email.mime.image import MIMEImage
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        import tempfile
        import webbrowser
        import os

        self._log("Generiere Report...")
        if self.debug:
            self.debug_print_timeline_data()
        model_name = self._get_latest_model_name()
        date_str = datetime.now().strftime('%d.%m.%Y')
        hours_back = routerlog.config_int(self.config, 'Charts', 'hours_back', 24)
        evt_hours = routerlog.config_int(self.config, 'Events', 'hours_back', 24)
        exclude = [t.strip() for t in self.config.get('Events', 'exclude_types', fallback='').split(',') if t.strip()]
        conn_since, ip4, ip6, down, up = self._get_connection_status()
        uptime_data = self._get_router_uptime()
        latest_ips = self._get_ip_changes(10)
        fw_upd, fw_old, fw_act, fw_entries = self._check_firmware_update()
        ai_text = ""
        if self.config.getboolean('Modul', 'ai_analysis', fallback=True):
            ai_text = self._run_ai_analysis(evt_hours)
        conn_analysis_html = self._get_connection_analysis(evt_hours)
        timeline = self._generate_timeline(evt_hours)
        gantt = self._generate_client_gantt(evt_hours)
        clients = self._get_connected_clients(evt_hours)
        traffic = self._get_data_volume_clients()
        charts = self._generate_charts(hours_back)
        show_level = routerlog.config_int(self.config, 'Events', 'show_level', 4)
        events = self._get_events(24, exclude, show_level)
        
        msg_root = MIMEMultipart('mixed')
        msg_root['Subject'] = f"{self.t['subject']} {model_name} {self.t['conn_overview']} {date_str}"
        msg_root['From'] = self.config.get('Email', 'sender_email')
        msg_root['To'] = self.config.get('Email', 'recipient_email')
        msg_rel = MIMEMultipart('related')
        msg_root.attach(msg_rel)
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
        <body style="color: #000000; background-color: #f0eee6; font-family: Arial, Helvetica, sans-serif;">
            <table width="100%" align="center" style="border:solid 2px #eeeeee; border-collapse: collapse; max-width: 900px; background: white;">
                <tr><td width="100%" align="center" style="background-color: #4acbd6; font-size: 18pt; color: white; padding: 15px;">
                    {self.t['subject']} {model_name} {self.t['title']}<br><span style="font-size: 12pt;">{self.t['from_date']} {date_str}</span>
                </td></tr>"""

        if conn_since or ip4 or ip6:
            s_since = conn_since.strftime('%d.%m.%Y %H:%M') if conn_since else self.t['unknown']
            
            time_diff_str = ""
            if conn_since:
                diff = datetime.now() - conn_since
                total_seconds = int(diff.total_seconds())
                hours_since = total_seconds // 3600
                minutes_since = (total_seconds % 3600) // 60
                time_diff_str = f" ({hours_since} {self.t['hours']} {minutes_since} {self.t['minutes']})"
                
            s_down = f"{float(down)/1000:.1f}".replace('.', ',') + " Mbit/s" if down else "n/a"
            s_up = f"{float(up)/1000:.1f}".replace('.', ',') + " Mbit/s" if up else "n/a"
            
            prev_ip4_str = ""
            if ip4:
                chg_time_ip4, prev_ip4 = self._get_last_ip_change(ip4, is_ipv6=False)
                if chg_time_ip4 and prev_ip4:
                    diff = datetime.now() - datetime.fromtimestamp(chg_time_ip4)
                    prev_ip4_str = f" &nbsp;&nbsp;&nbsp; <b>{self.t['last_ip_change']}</b> {diff.days} {self.t['days']} {diff.seconds // 3600} {self.t['hours']} ({prev_ip4})"

            prev_ip6_str = ""
            if ip6:
                chg_time_ip6, prev_ip6 = self._get_last_ip_change(ip6, is_ipv6=True)
                if chg_time_ip6 and prev_ip6:
                    diff = datetime.now() - datetime.fromtimestamp(chg_time_ip6)
                    short_prev_ip6 = ':'.join(prev_ip6.split(':')[:4]) + ':…' if len(prev_ip6.split(':')) > 4 else prev_ip6
                    prev_ip6_str = f" &nbsp;&nbsp;&nbsp; <b>{self.t['last_ip_change']}</b> {diff.days} {self.t['days']} {diff.seconds // 3600} {self.t['hours']} ({short_prev_ip6})"

            ipv4_str = f"IPv4 {ip4}{prev_ip4_str}" if ip4 else f"IPv4 {self.t['unknown']}"
            ipv6_str = f"IPv6 {ip6}{prev_ip6_str}" if ip6 else f"IPv6 {self.t['unknown']}"
            
            html += f"<tr><td style='padding: 20px; font-size: 13px; color: #333;'><b>{self.t['connected_since']}</b> {s_since}{time_diff_str}<br><b>{self.t['current']}</b> {ipv4_str}<br><b>{self.t['current']}</b> {ipv6_str}<br><b>{self.t['current']}"
            
            if uptime_data:
                u_days, u_hours = uptime_data
                html += f"<br><b>{self.t['firmware']}</b> {fw_act} <b>{self.t['last_reboot']}</b> {u_days} {self.t['days']} {u_hours} {self.t['hours']}"
                
            html += "</td></tr>"
            
        if fw_upd and fw_entries:
            def _ver_label(entry):
                return entry.get('version_str') or '.'.join(str(p) for p in entry.get('version', ())) or entry.get('title', '')

            # "Verfügbar"-Zeile nur, wenn tatsächlich neuere Versionen vorliegen
            act_v = self._extract_version_tuple(fw_act)
            has_newer = any(e['version'] != (0,) and e['version'] > act_v for e in fw_entries)
            available_line = ""
            if has_newer:
                available_line = (f"{self.t['fw_available']} <strong>"
                                  + ", ".join(_ver_label(e) for e in fw_entries) + "</strong><br>")

            # Reihenfolge (älteste neuere zuerst) - wichtig, wenn ein Zwischenschritt nötig ist
            order_line = ""
            if has_newer and len(fw_entries) > 1:
                ascending = sorted(fw_entries, key=lambda e: e['version'])
                order_line = (f"<div style='margin-top: 10px;'><strong>{self.t['fw_order']}</strong> "
                              + " &#10142; ".join(_ver_label(e) for e in ascending) + "</div>")

            notes_blocks = ""
            for e in fw_entries:
                ds = datetime.fromtimestamp(e['date_ut']).strftime('%d.%m.%Y') if e.get('date_ut') else self.t['unknown']
                notes_blocks += (f"<div style=\"border-top: 1px solid #ffcc80; margin-top: 10px; padding-top: 10px;\">"
                                 f"<strong>{self.t['rn']} {_ver_label(e)} ({ds}):</strong><br>{e.get('notes_html') or ''}</div>")

            html += f"""<tr><td style="padding: 20px;"><div style="border: 2px solid #ff9800; background-color: #fff3e0; padding: 15px; border-radius: 5px;">
                <h3 style="margin-top: 0; color: #e65100;">{self.t['fw_notice']}</h3><div style="font-size: 14px; color: #333;">
                {self.t['fw_installed']} <span style="color: #2e7d32; font-weight: bold;">{fw_act}</span><br>
                {available_line}{order_line}{notes_blocks}</div></div></td></tr>"""
        
        # 1. AI Analyse
        if self.config.getboolean('Modul', 'ai_analysis', fallback=True):
            if ai_text:
                html += f"<tr><td style='padding: 20px;'><div style='border: 2px solid #4acbd6; background-color: #f9ffff; padding: 15px; border-radius: 5px;'><h3 style='margin-top: 0; color: #008ba3;'>{self.t['at_a_glance']}</h3><div style='font-size: 14px; color: #333;'>{ai_text}</div></div></td></tr>"
            
        # 2. Eventübersichtschart
        if self.config.getboolean('Modul', 'reconnects', fallback=True):
            if timeline:
                img_src = "cid:timeline_img" if send_email else f"data:image/png;base64,{timeline}"
                html += f"<tr><td style='padding: 0 20px 20px 20px;'><div style='border: 1px solid #ddd; background-color: #fff; padding: 10px; border-radius: 5px;'><div style='font-size: 12px; font-weight: bold; color: #666;'>{self.t['event_overview']}</div><img src='{img_src}' style='width: 100%; max-width: 860px;'></div></td></tr>"
            
        # 3. Leitungsanalyse
        if self.config.getboolean('Modul', 'line_analysis', fallback=True):
            if conn_analysis_html:
                padding_top = "0px" if timeline else "20px"
                html += f"<tr><td style='padding: 20px; padding-top: {padding_top};'><div style='border: 1px solid #b0bec5; background-color: #fcfcfc; padding: 15px; border-radius: 5px;'><h3 style='margin-top: 0; color: #455a64;'>{self.t['line_analysis']}</h3><div style='font-size: 14px; color: #333;'>{conn_analysis_html}</div></div></td></tr>"
            
        # 4. Chart Downstreamstörabstand (SNR Chart + Stats)
        if self.config.getboolean('Modul', 'downstream_chart', fallback=True):
            for idx, (lbl, chart_data) in enumerate(charts):
                img_src = f"cid:chart_{idx}" if send_email else f"data:image/png;base64,{chart_data}"
                html += f"<tr><td style='padding: 10px 20px;'><table width='100%'><tr><td style='background-color: #4acbd6; color: white; padding: 5px;'>{lbl}</td></tr><tr><td style='text-align: center;'><img src='{img_src}' style='width: 100%; max-width: 860px;'></td></tr></table></td></tr>"
            
                # Zusatz-Statistiken für den ersten Chart (SNR Downstream)
                if idx == 0:
                    t_table = self.config.get('Charts', 'table_1', fallback='dsl')
                    t_field = self.config.get('Charts', 'field_1', fallback='downstream_noise_margin')
                    hb_stats, median_xd, m3_stats, ma_days = self._get_snr_stats(t_table, t_field, hours_back)
                    
                    stats_html = f"<div style='font-size: 13px; color: #333; margin-top: 5px; margin-bottom: 15px; font-family: sans-serif; line-height: 1.6; background: #f9f9f9; padding: 10px; border-left: 4px solid #4acbd6;'>"
                    stats_html += self.t['snr_stats_hours'].format(hours=hours_back, max=f"{hb_stats['max']:.1f}", min=f"{hb_stats['min']:.1f}", median=f"{hb_stats['median']:.1f}") + "<br>"
                    stats_html += self.t['stats_3m'].format(max=f"{m3_stats['max']:.1f}", min=f"{m3_stats['min']:.1f}", median=f"{m3_stats['median']:.1f}")
                    stats_html += "</div>"
                    html += f"<tr><td style='padding: 0 20px;'>{stats_html}</td></tr>"

        # 5. Tagesschwankungschart (SNR Heatmap)
        variance_img = None
        if self.config.getboolean('Modul', 'snr_heatmap', fallback=True):
            t_table = self.config.get('Charts', 'table_1', fallback='dsl')
            t_field = self.config.get('Charts', 'field_1', fallback='downstream_noise_margin')
            t_label = self.config.get('Charts', 'label_1', fallback=t_field)
            variance_img = self._generate_snr_variance_img(t_table, t_field, t_label)
            if variance_img:
                img_src = f"cid:snr_variance_img" if send_email else f"data:image/png;base64,{variance_img}"
                html += f"<tr><td style='padding: 10px 20px;'><table width='100%'><tr><td style='text-align: center;'><img src='{img_src}' style='width: 100%; max-width: 860px;'></td></tr></table></td></tr>"

        # 6. Anwesenheits GANTT Chart
        if self.config.getboolean('Modul', 'presence', fallback=True):
            if gantt:
                img_src = f"cid:gantt_img" if send_email else f"data:image/png;base64,{gantt}"
                html += f"<tr><td style='padding: 10px 20px;'><table width='100%'><tr><td style='background-color: #4acbd6; color: white; padding: 5px;'>{self.t['presence']}</td></tr><tr><td><img src='{img_src}' style='width: 100%; max-width: 860px;'></td></tr></table></td></tr>"
                
        # 7. Heimnetzübersicht aktiver Clients
        if self.config.getboolean('Modul', 'client_presence', fallback=True):
            if clients['home']:
                html += f"<tr><td style='padding: 10px 20px;'><table width='100%' style='border-collapse: collapse;'><tr><td style='background-color: #4acbd6; color: white; padding: 5px;'>{self.t['home_network']}</td></tr><tr><td><table width='100%' style='font-size: 13px;'>"
                for i, c in enumerate(clients['home']):
                    bg = "#ffffff" if i % 2 == 0 else "#f9f9f9"
                    typ = f"LAN {c[3]}" if str(c[2]).lower() == 'lan' and c[3] else c[2]
                    html += f"<tr style='background-color: {bg};'><td>{c[0]}</td><td style='color: #666;'>{c[1]}</td><td>{typ}</td></tr>"
            html += "</table></td></tr></table></td></tr>"

        # 8. Eventlog
        if self.config.getboolean('Modul', 'event_log', fallback=True):   
            if events:
                all_levels = [
                    "0 Notfall", "1 Alarm", "2 Kritisch", "3 Fehler", 
                    "4 Vorsicht", "5 Hinweis", "6 Info", "7 Debug"
                ]
                
                if show_level <= 7:
                    visible_levels = all_levels[:show_level + 1]
                else:
                    visible_levels = all_levels
                    
                legend_html = " &bull; ".join(visible_levels)
                
                if 0 <= show_level <= 7:
                    level_text = all_levels[show_level]
                    header_text = f"{self.t['event_log_level']} {level_text}"
                elif show_level == 8:
                    header_text = self.t['event_log_full']
                elif show_level == 9:
                    if exclude:
                        header_text = f"{self.t['event_log_without']} {', '.join(exclude)}"
                    else:
                        header_text = self.t['event_log_full']
                else:
                    header_text = self.t['fallback_log']
                    
                html += f"<tr><td style='padding: 10px 20px;'><table width='100%'><tr><td style='background-color: #4acbd6; color: white; padding: 5px;'>{header_text}</td></tr><tr><td><table width='100%' style='font-size: 11px; color: #555;'>"
                for i, e in enumerate(events):
                    bg = "#ffffff" if i % 2 == 0 else "#f9f9f9"
                    html += f"<tr style='background-color: {bg};'><td width='140'>{e[0]}</td><td width='80'>{e[1]}</td><td>{e[2]}</td></tr>"
                
                html += "<tr><td colspan='3' style='padding-top: 5px; font-size: 10px; color: #888; text-align: center; border-top: 1px solid #eee;'>"
                html += legend_html
                html += "</td></tr>"
                
                html += "</table></td></tr></table></td></tr>"
        html += f"</table><p style='padding: 20px; text-align: center; font-size: 10pt; color: #999;'>{self.t['footer']}</p></body></html>"
        
        try:
            os.makedirs('reports', exist_ok=True)
            timestamp = datetime.now().strftime('%y%m%d_%H%M')
            filename = f"tp-report_{timestamp}.html"
            rel_path = os.path.join('reports', filename)
            with open(rel_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"{self.t['generated_in']} {rel_path}")
            
            self._cleanup_old_reports()

            if show_browser:
                try:
                    abs_path = os.path.abspath(rel_path)
                    webbrowser.open('file://' + abs_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"Fehler beim Erstellen des Reports: {e}")
        
        if send_email:
            msg_rel.attach(MIMEText(html, 'html'))
            if timeline:
                img = MIMEImage(base64.b64decode(timeline))
                img.add_header('Content-ID', '<timeline_img>')
                msg_rel.attach(img)
            if gantt:
                img = MIMEImage(base64.b64decode(gantt))
                img.add_header('Content-ID', '<gantt_img>')
                msg_rel.attach(img)
            if variance_img:
                img = MIMEImage(base64.b64decode(variance_img))
                img.add_header('Content-ID', '<snr_variance_img>')
                msg_rel.attach(img)
            for idx, (_, data) in enumerate(charts):
                img = MIMEImage(base64.b64decode(data))
                img.add_header('Content-ID', f'<chart_{idx}>')
                msg_rel.attach(img)
            try:
                srv = smtplib.SMTP(self.config.get('Email', 'smtp_server'), routerlog.config_int(self.config, 'Email', 'smtp_port'))
                srv.starttls()
                srv.login(self.config.get('Email', 'sender_email'), self.config.get('Email', 'sender_password'))
                srv.send_message(msg_root)
                srv.quit()
                print(self.t['mail_success'])
            except Exception as e:
                print(f"{self.t['mail_error']} {e}")

    def _cleanup_old_reports(self):
        import time
        from pathlib import Path
        cleanup_days = routerlog.config_int(self.config, 'Reports', 'cleanup_reports', 0)
        if cleanup_days > 0:
            reports_dir = Path('reports')
            if reports_dir.exists() and reports_dir.is_dir():
                now = time.time()
                deleted_count = 0
                for f in reports_dir.glob('tp-report*.html'):
                    if f.is_file():
                        file_age_days = (now - f.stat().st_mtime) / (24 * 3600)
                        if file_age_days > cleanup_days:
                            try:
                                f.unlink()
                                deleted_count += 1
                                self._log(f"Gelöschter alter Report: {f.name}")
                            except Exception as e:
                                self._log(f"Fehler beim Löschen des Reports {f.name}: {e}")
                if deleted_count > 0:
                    print(f"Es wurden {deleted_count} alte Report(s) gelöscht (älter als {cleanup_days} Tage).")

# ---------------------------------------------------------------------------
# CLIENT-QUELLEN ZUSAMMENFÜHREN
# ---------------------------------------------------------------------------
def merge_client_sources(gui_clients, arp_clients):
    """Führt die ARP-Liste (stabile Basis) mit den API-Daten zusammen.

    Die WLAN-/Mesh-Tabellen des Routers sind gelegentlich komplett leer; die
    lokale ARP-Erkennung (Ping-Sweep + ARP-Tabelle, ohne SNMP) liefert dann
    weiterhin die Geräte im Netz. API-Werte (Signal, Raten, Bytes, Status)
    überschreiben die ARP-Platzhalter, sofern vorhanden.
    """
    result = dict(gui_clients or {})

    api_by_mac = {}
    for ctype in ('wlan', 'lan'):
        for c in (gui_clients or {}).get(ctype, []) or []:
            mac = c.get('mac')
            if mac:
                api_by_mac[mac] = (ctype, c)

    merged_wlan, merged_lan = [], []
    enriched = added = 0

    for arp in arp_clients or []:
        hit = api_by_mac.pop(arp.get('mac'), None)
        if hit is None:
            merged_wlan.append(arp)          # nur im ARP vorhanden
            added += 1
            continue
        ctype, api_client = hit
        merged = dict(arp)
        for key, value in api_client.items():
            if value not in (None, ''):
                merged[key] = value          # API-Werte haben Vorrang
        enriched += 1
        (merged_wlan if ctype == 'wlan' else merged_lan).append(merged)

    for ctype, c in api_by_mac.values():
        (merged_wlan if ctype == 'wlan' else merged_lan).append(c)

    result['wlan'] = merged_wlan
    result['lan'] = merged_lan
    print(f"Clients: ARP {len(arp_clients or [])} | angereichert {enriched} |"
          f" nur im ARP {added} -> wlan {len(merged_wlan)}, lan {len(merged_lan)}")
    return result


# ---------------------------------------------------------------------------
# MAIN CLI
# ---------------------------------------------------------------------------
def main():
    # Niedrigere Priorität: der Lauf soll den Pi nicht ausbremsen
    try:
        os.nice(10)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="TP-Link Report Script")
    parser.add_argument('--update', action='store_true', help='Holt Daten via API und speichert sie')
    parser.add_argument('--report-send', '--send', action='store_true', help='Generiert und versendet Report')
    parser.add_argument('--report-show', '--show', action='store_true', help='Generiert und speichert HTML Report')
    parser.add_argument('--de', action='store_true', help='Report auf Deutsch')
    parser.add_argument('--en', action='store_true', help='Report in English')
    parser.add_argument('--debug', action='store_true', help='Debug-Modus aktivieren')
    args = parser.parse_args()

    config_mgr = ConfigManager()
    
    if args.de: config_mgr.set_lang('de')
    if args.en: config_mgr.set_lang('en')
    
    lang = config_mgr.get_lang()
    db_name = config_mgr.config.get('Database', 'db_name', fallback='router_data.db')
    db = DatabaseManager(db_name)

    # ACTION: UPDATE
    if args.update or args.report_show or args.report_send:
        router_ip = config_mgr.config.get('Router', 'router_ip', fallback='192.168.1.1')
        router_pw = config_mgr.config.get('Router', 'password', fallback='')
        api = RouterAPI(router_ip, "user", router_pw, debug=args.debug)
        if api.login():
            print("API Login OK. Hole Daten...")
            # [Modul] collect_clients = aus  ->  keine Client-Abfrage (spart Aufwecken,
            # Netzplan-Wartezeit und den lokalen ARP-Scan; Clients kommen dann aus dem
            # stündlichen vx231v-Lauf in derselben Datenbank).
            collect_clients = config_mgr.config.getboolean('Modul', 'collect_clients', fallback=True)
            c_data = api.get_clients() if collect_clients else {'wlan': [], 'lan': []}
            dsl_data = api.get_dsl_data()

            # Die neue Firmware füllt ihre Tabellen erst nach einem Besuch der
            # Weboberfläche -> bei leeren DSL-Daten einmal aufwecken und neu lesen.
            # Danach (Sitzung ist dann beendet) gleich die Fehlerzähler mitnehmen.
            warmup = config_mgr.config.get('WebUI', 'warmup', fallback='auto').strip().lower()
            crc_source = config_mgr.config.get('WebUI', 'crc_source', fallback='gui').strip().lower()
            need_crc = crc_source not in ('aus', 'off', 'nein', 'no')
            clients_empty = collect_clients and not (c_data.get('wlan') or c_data.get('lan'))
            need_wake = (not dsl_data or clients_empty) and warmup not in ('aus', 'off', 'nein', 'no')

            if need_wake or need_crc:
                if need_wake:
                    print("Hinweis: Router-Tabellen leer (DSL/Clients) -> wecke sie per Weboberfläche...")
                api.close()   # Router erlaubt nur eine Admin-Sitzung
                browser = RouterBrowser(router_ip,
                                        config_mgr.config.get('WebUI', 'user', fallback='admin'),
                                        router_pw, debug=args.debug)
                if browser.login():
                    if need_wake:
                        browser.wake_up(include_clients=collect_clients)
                    counters = browser.get_dsl_error_counters() if need_crc else None
                    browser.close()
                    if need_wake:
                        # Der Router gibt die Sitzung nach dem Browser-Logout erst kurz
                        # danach frei -> Neuanmeldung mehrfach versuchen.
                        for attempt in (1, 2, 3):
                            if api.login():
                                c_data = api.get_clients() if collect_clients else {'wlan': [], 'lan': []}
                                dsl_data = api.get_dsl_data()
                                break
                            print(f"  (Neuanmeldung {attempt}/3 fehlgeschlagen)")
                            time.sleep(3)
                        print(f"Nach dem Aufwecken: {len(c_data.get('wlan', [])) + len(c_data.get('lan', []))} Clients,",
                              "DSL-Daten vorhanden" if dsl_data else "weiterhin keine DSL-Daten")
                    if counters and dsl_data:
                        dsl_data.update(counters)

            if not collect_clients:
                sys_info = api.get_system_info()
                if sys_info:
                    db.insert_system(sys_info, time.time())
                    print(f"Systemdaten gespeichert: {sys_info.get('model')} / Firmware {sys_info.get('firmware')}")
                print("Client-Erfassung ist abgeschaltet ([Modul] collect_clients = aus).")
            elif 'error' not in c_data:
                # ARP-Erkennung im eigenen Netz (ohne SNMP) als stabile Basis,
                # damit Clients auch bei leerer Router-Tabelle erfasst werden
                c_data = merge_client_sources(c_data, get_local_arp_clients(db_manager=db))
                if len(c_data.get('wlan', [])) + len(c_data.get('lan', [])) == 0:
                    # Weder Router noch ARP lieferten Clients - insert_clients() würde
                    # sonst zuerst alle Clients auf is_connected=0 setzen.
                    print("Warnung: Weder Router noch ARP lieferten Clients."
                          " Speichere keine Clientdaten, um die Anwesenheitsdaten nicht"
                          " zu verfälschen.")
                else:
                    db.insert_system(c_data.get('system', {}), time.time())
                    db.insert_clients(c_data)
            else:
                print(f"Warnung: Client-Abfrage fehlgeschlagen: {c_data['error']}")
                
            if dsl_data:
                db.insert_dsl(dsl_data, time.time())
                print(f"DSL gespeichert: down {dsl_data.get('Aktuelle Download-Rate (kbit/s)')} kbit/s,"
                      f" SNR {dsl_data.get('Signal-Rausch-Abstand Download (dB)')} dB")
            else:
                print("Hinweis: keine DSL-Daten erhalten - kein DSL-Eintrag gespeichert.")

            log_txt = api.downloadrouterlog_to_memory()
            if log_txt:
                added = db.insert_events_from_log(log_txt)
                print(f"{added} Events gespeichert.")
            print("Update abgeschlossen.")
        else:
            print("Update abgebrochen: API Fehler.")

    # ACTION: REPORT
    if args.report_show or args.report_send:
        # DB-Cleanup für ausgeschlossene Event-Typen vor der Report-Erstellung
        cleanup_days = config_mgr.config.getint('Events', 'cleanup_excludes', fallback=0)
        if cleanup_days > 0:
            exclude_raw = config_mgr.config.get('Events', 'exclude_types', fallback='')
            types_to_purge = routerlog.expand_exclude_types(
                [t.strip() for t in exclude_raw.split(',') if t.strip()])
            if types_to_purge:
                db.purge_old_events(cleanup_days, types_to_purge, debug=args.debug)

        rep = Reporter(config_mgr, db, lang)
        rep.debug = args.debug
        rep.generate_report(send_email=args.report_send, show_browser=args.report_show)


if __name__ == "__main__":
    main()

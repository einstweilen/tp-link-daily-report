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
import logging
import base64
import io
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
            'exclude_types': 'Mesh, DHCPD',
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
        self.host = ip
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

    def get_clients(self):
        if not self.router and not self.login():
            return {'error': 'Login failed'}

        try:
            status = self.router.get_status()
            acts = [
                self.router.ActItem(self.router.ActItem.GET, 'DEV2_DEV_INFO', attrs=[
                    'modelName', 'softwareVersion', 'hardwareVersion', 'serialNumber', 'upTime'
                ]),
                self.router.ActItem(self.router.ActItem.GL, 'DEV2_ADT_WIFI_CLIENT', attrs=[
                    'MACAddress', 'signalStrength', 'packetsSent', 'packetsReceived', 'band'
                ])
            ]
            _, values = self.router.req_act(acts)
            
            dev_info = values[0]
            wlan_details = {c['MACAddress'].upper(): c for c in self.router._to_list(values[1])}
            uptime = int(float(dev_info.get('upTime', 0)))
            
            result = {
                'timestamp': time.time(),
                'system': {
                    'model': dev_info.get('modelName', 'N/A'),
                    'firmware': dev_info.get('softwareVersion', 'N/A'),
                    'hardware': dev_info.get('hardwareVersion', 'N/A'),
                    'serial': dev_info.get('serialNumber', 'N/A'),
                    'uptime_seconds': uptime,
                    'uptime_days': round(uptime / 86400, 1) if uptime > 0 else 0.0
                },
                'wlan': [],
                'lan': []
            }
            
            for device in status.devices:
                mac = str(device._macaddr).replace("-", ":").upper()
                is_wlan = False
                if Connection and hasattr(device, 'type'):
                    is_wlan = device.type in [Connection.HOST_2G, Connection.HOST_5G, Connection.GUEST_2G, Connection.GUEST_5G]
                
                cdata = {
                    'mac': mac, 'hostname': device.hostname, 'ip': str(device._ipaddr), 'is_connected': 1
                }
                
                if is_wlan:
                    detail = wlan_details.get(mac, {})
                    cdata.update({
                        'signal_strength': int(float(detail.get('signalStrength', 0))),
                        'bytes_total': int(float(detail.get('packetsReceived', 0))) * 1000, 
                        'download_rate_mbps': 0, 'upload_rate_mbps': 0, 'link_speed_mbps':0
                    })
                    result['wlan'].append(cdata)
                else:
                    cdata.update({'bytes_total': 0, 'signal_strength': 0, 'download_rate_mbps': 0, 'upload_rate_mbps': 0, 'link_speed_mbps':0})
                    result['lan'].append(cdata)
                    
            return result
        except Exception as e:
            return {'error': str(e)}

    def get_dsl_data(self):
        if not self.router and not self.login(): return {}
        try:
            acts = [
                self.router.ActItem(self.router.ActItem.GET, 'DEV2_DSL_LINE', '1,0,0,0,0,0', attrs=[
                    'upstreamMaxBitRate', 'downstreamMaxBitRate', 
                    'upstreamNoiseMargin', 'downstreamNoiseMargin',
                    'upstreamAttenuation', 'downstreamAttenuation'
                ]),
                self.router.ActItem(self.router.ActItem.GET, 'DEV2_DSL_CHANNEL', '1,0,0,0,0,0', attrs=[
                    'upstreamCurrRate', 'downstreamCurrRate'
                ]),
                self.router.ActItem(self.router.ActItem.GL, 'DEV2_ADT_WAN', attrs=[
                    'connIPv4Address', 'connIPv6Address', 'connStatusV4', 'connStatusV6'
                ])
            ]
            _, values = self.router.req_act(acts)
            line, channel = values[0], values[1]
            
            wan = {}
            for w in self.router._to_list(values[2]):
                if w.get('connStatusV4') == 'Connected' or w.get('connStatusV6') == 'Connected':
                    wan = w; break
            if not wan and values[2]:
                wan = values[2][0] if isinstance(values[2], list) else values[2]
            
            up_curr = int(float(channel.get('upstreamCurrRate', 0)))
            down_curr = int(float(channel.get('downstreamCurrRate', 0)))
            up_max = int(float(line.get('upstreamMaxBitRate', 0)))
            down_max = int(float(line.get('downstreamMaxBitRate', 0)))
            
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
            url = self.router._get_url('cgi/log')
            code, response = self.router._request(url, data_str="", encrypt=True)
            if code == 200:
                return re.sub(r"(202\d-)", r"\n\1", response, count=1)
            return self._downloadrouterlog_http_fallback()
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
                return re.sub(r"(202\d-)", r"\n\1", logcontent, count=1)
            return None
        except Exception as e:
            self._log(f"HTTP-Fallback fehlgeschlagen: {e}")
            return None

# ---------------------------------------------------------------------------
# DATABASE MANAGER
# ---------------------------------------------------------------------------
class DatabaseManager:
    def __init__(self, db_path="router_data.db"):
        self.db_path = db_path
        self._create_tables()

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
                           downstream_attenuation, ip4_curr, ip6_curr)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (int(timestamp), data.get('Aktuelle Upload-Rate (kbit/s)', 0), data.get('Aktuelle Download-Rate (kbit/s)', 0),
                         data.get('Maximale Upload-Rate (kbit/s)', 0), data.get('Maximale Download-Rate (kbit/s)', 0),
                         data.get('Signal-Rausch-Abstand Upload (dB)', 0.0), data.get('Signal-Rausch-Abstand Download (dB)', 0.0),
                         data.get('Leitungsdämpfung Upload (dB)', 0.0), data.get('Leitungsdämpfung Download (dB)', 0.0),
                         data.get('ip4_curr', ''), data.get('ip6_curr', '')))

    def insert_clients(self, clients_data):
        if 'error' in clients_data: return
        ts = clients_data.get('timestamp', time.time())
        self._run_query("UPDATE clients SET is_connected = 0")
        
        batch = []
        for ctype, clist in [('wlan', clients_data.get('wlan', [])), ('lan', clients_data.get('lan', []))]:
            for c in clist:
                batch.append((c['mac'], int(ts), ctype, c.get('hostname', ''), c.get('ip', ''),
                              c.get('signal_strength', 0), 1, c.get('bytes_total', 0)))
                
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany("INSERT OR REPLACE INTO clients (mac, time_ut, type, hostname, ip, signal_strength, is_connected, bytes_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", batch)

    def insert_events_from_log(self, text):
        if not text: return 0
        added = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for line in text.splitlines():
                s = line.strip()
                if len(s) > 20 and s.startswith('202'):
                    try:
                        dt = datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
                        rest = s[20:]
                        if rest.startswith('['):
                            rb = rest.find(']')
                            lvl = int(rest[1:rb])
                            payload = rest[rb+1:].strip()
                            sep = payload.find(': ')
                            if sep > 0:
                                typ, msg = payload[:sep].strip(), payload[sep+2:].strip()
                                cursor.execute("INSERT OR IGNORE INTO events (time_ut, level_id, type, event_text) VALUES (?, ?, ?, ?)",
                                               (int(dt.timestamp()), lvl, typ, msg))
                                added += cursor.rowcount
                    except: pass
        return added

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
        rn_title, rn_date, rn_txt, dl_link = self._get_latest_firmware_info()
        _, rows = self.db._run_query("SELECT firmware, time_ut FROM system ORDER BY id DESC LIMIT 2")
        if not rows or len(rows) < 1: 
            return False, None, None, None, None, None
            
        act_fw, act_ts = rows[0][0], int(rows[0][1])
        old_fw = rows[1][0] if len(rows) > 1 else None
        old_ts = int(rows[1][1]) if len(rows) > 1 else 0
        
        def extract_version_tuple(fw_str, fallback_str=None):
            if not fw_str: return (0,)
            import re
            
            # Check online standard structure: e.g. VX231v(DE)v1_0.23.0_...
            # The version is between the first and second underscore.
            m = re.search(r'^[^_]+_([^_]+)_', fw_str)
            if m:
                ver_str = m.group(1)
                parts = [int(p) for p in ver_str.split('.') if p.isdigit()]
                while len(parts) > 2 and parts[-1] == 0:
                    parts.pop()
                if parts:
                    return tuple(parts)
            
            # Check local standard structure: e.g. 231.0.23 / 231.0.19
            if fw_str.startswith('231.') or fw_str.startswith('0.'):
                m = re.search(r'^\d+\.((\d+\.)*\d+)', fw_str)
                if m:
                    parts = [int(p) for p in m.group(1).split('.') if p.isdigit()]
                    while len(parts) > 2 and parts[-1] == 0:
                        parts.pop()
                    if parts:
                        return tuple(parts)
                        
            # Use fallback (rn_title) if parsing the link failed but it's an online check
            if fallback_str:
                m = re.search(r'_V?[\d\.]+_((\d+\.)+\d+)', fallback_str)
                if m:
                    parts = [int(p) for p in m.group(1).split('.') if p.isdigit()]
                    while len(parts) > 2 and parts[-1] == 0:
                        parts.pop()
                    if parts:
                        return tuple(parts)
                
            return (0,)

        act_v = extract_version_tuple(act_fw)
        filename = dl_link.split('/')[-1] if dl_link else ""
        web_v = extract_version_tuple(filename, fallback_str=rn_title)
        
        if act_v < web_v and web_v != (0,):
            return True, old_fw, act_fw, rn_title, rn_date, rn_txt
            
        if act_v == web_v and web_v != (0,):
            cutoff = (datetime.now() - timedelta(hours=48)).timestamp()
            if old_fw and old_fw != act_fw and old_ts > cutoff:
                return True, old_fw, act_fw, rn_title, rn_date, rn_txt
                
        return False, old_fw, act_fw, rn_title, rn_date, rn_txt

    def _build_client_sessions(self, hours=24):
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        sql = "SELECT time_ut, type, event_text FROM events WHERE time_ut >= ? AND type IN ('Mesh', 'DHCPD') ORDER BY time_ut ASC"
        _, rows = self.db._run_query(sql, params=[start_ts])

        def extract_mac(text):
            s = (text or "").upper().replace("-", ":")
            allowed = "0123456789ABCDEF:"
            tokens = []
            cur = []
            for ch in s:
                if ch in allowed:
                    cur.append(ch)
                else:
                    if cur:
                        tokens.append("".join(cur))
                        cur = []
            if cur:
                tokens.append("".join(cur))

            for tok in tokens:
                parts = tok.split(":")
                if len(parts) == 6 and all(len(p) == 2 and all(c in "0123456789ABCDEF" for c in p) for p in parts):
                    return ":".join(parts)
            return None

        router_ip = self.config.get('Router', 'router_ip', fallback='192.168.1.1')
        parts = router_ip.split('.')
        home_subnet = f"{parts[0]}.{parts[1]}.{parts[2]}." if len(parts) == 4 else "192.168.1."

        def detect_network_type(text):
            m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text)
            if m:
                ip = m.group(1)
                return 'home' if ip.startswith(home_subnet) else 'guest'
            return None

        current_time = datetime.now().timestamp()
        
        # PHASE 1: DHCP Correlation (DISCOVER -> OFFER)
        mac_network_assignments = {}
        pending_discovers = {} 
        pending_offers = {} 

        for r in rows:
            ts = int(r[0])
            text = r[2]
            event_type = r[1]

            if event_type == 'DHCPD':
                if 'Recv DISCOVER from' in text:
                    mac = extract_mac(text)
                    if mac:
                        if mac not in pending_discovers:
                            pending_discovers[mac] = []
                        pending_discovers[mac].append(ts)
                elif 'Send OFFER with ip' in text or 'Send ACK to' in text:
                    net_type = detect_network_type(text)
                    if net_type:
                        if net_type not in pending_offers:
                            pending_offers[net_type] = []
                        pending_offers[net_type].append(ts)

        TIME_WINDOW = 10 
        for mac, discover_times in pending_discovers.items():
            for disc_ts in discover_times:
                for net_type, offer_times in pending_offers.items():
                    for offer_ts in offer_times:
                        if abs(offer_ts - disc_ts) <= TIME_WINDOW:
                            if mac not in mac_network_assignments:
                                mac_network_assignments[mac] = []
                            mac_network_assignments[mac].append((disc_ts, net_type))
                            break

        # PHASE 2: Session Builder
        client_activity = {}
        for r in rows:
            ts = int(r[0])
            text = r[2]
            mac = extract_mac(text)
            if not mac: continue

            if mac not in client_activity:
                client_activity[mac] = []

            is_start = "Add Client" in text or "REQUEST" in text or "DISCOVER" in text
            is_end = "Del Client" in text
            sessions = client_activity[mac]

            if is_start:
                if not sessions or sessions[-1]['end'] is not None:
                    network = 'home'
                    if mac in mac_network_assignments:
                        closest = None
                        min_diff = float('inf')
                        for assign_ts, net in mac_network_assignments[mac]:
                            diff = abs(ts - assign_ts)
                            if diff <= TIME_WINDOW and diff < min_diff:
                                min_diff = diff
                                closest = net
                        if closest:
                            network = closest
                    sessions.append({'start': ts, 'end': None, 'network': network})
            elif is_end:
                if sessions and sessions[-1]['end'] is None:
                    sessions[-1]['end'] = ts

        for mac, sessions in client_activity.items():
            if sessions and sessions[-1]['end'] is None:
                sessions[-1]['end'] = current_time

        return client_activity

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
        params = [start_ts]
        exclude_clause = ""
        
        if show_level == 9:
            if exclude_types:
                exclude_clause = f"AND type COLLATE NOCASE NOT IN ({','.join('?' for _ in exclude_types)})"
                params.extend(exclude_types)
        else:
            if exclude_types:
                # Zeige Events, die NICHT in exclude_types stehen ODER die ein Fehler/Warnung (<= 4) sind.
                # UND zeige generell nur Events, die <= show_level sind.
                exclude_clause = f"AND (type COLLATE NOCASE NOT IN ({','.join('?' for _ in exclude_types)}) OR level_id <= 4) AND level_id <= ?"
                params.extend(exclude_types)
                params.append(show_level)
            else:
                exclude_clause = "AND level_id <= ?"
                params.append(show_level)
            
        sql = f"SELECT time_ut, type, event_text, level_id FROM events WHERE time_ut >= ? {exclude_clause} ORDER BY time_ut DESC"
        _, rows = self.db._run_query(sql, params)
        return [[datetime.fromtimestamp(int(r[0])).strftime('%d.%m.%y %H:%M:%S'), f"{r[3]} {r[1]}", r[2]] for r in rows]

    def _get_connection_status(self):
        # Verbunden seit: neuester erfolgreicher PPP-Connect
        sql_evt = "SELECT time_ut FROM events WHERE type = 'PPP' AND event_text LIKE '%PAP AuthAck%' ORDER BY time_ut DESC LIMIT 1"
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
        main_query = """
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
            WHERE type = 'PPP' AND (event_text LIKE '%User request%' OR event_text LIKE '%LCP down%' OR event_text LIKE '%AuthAck%')
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
        min_level = self.config.getint('Analyse', 'report_disconnects_level', fallback=1)
        
        start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
        start_ts_dsl = int((datetime.now() - timedelta(hours=hours + 2)).timestamp())

        try:
            _, pado_rows = self.db._run_query("SELECT COUNT(*) FROM events WHERE event_text LIKE '%PADO Timeout%' AND time_ut >= ?", [start_ts])
            pado_count = pado_rows[0][0] if pado_rows else 0

            _, dns_rows = self.db._run_query("SELECT datetime(time_ut, 'unixepoch', 'localtime') as ts FROM events WHERE type = 'Httpd' AND event_text LIKE '%failed%' AND time_ut >= ?", [start_ts])
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
        evt_hours = self.config.getint('Events', 'hours_back', fallback=24)
        start_ts = int((datetime.now() - timedelta(hours=evt_hours)).timestamp())
        end_ts = int(datetime.now().timestamp())

        start_str = datetime.fromtimestamp(start_ts).strftime('%d.%m.%Y %H:%M')
        end_str = datetime.fromtimestamp(end_ts).strftime('%d.%m.%Y %H:%M')

        sql = """
              SELECT time_ut, type, event_text
              FROM events
              WHERE time_ut >= ?
                AND type NOT IN ('Mesh', 'DHCPD')
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

    def _generate_snr_variance_html(self, table_name, field_name, label_name):
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
            
        min_avg = min(hourly_avg.values())
        max_avg = max(hourly_avg.values())
        delta = max_avg - min_avg
        
        html = f'''
        <div style="border: 1px solid #ddd; background-color: #fcfcfc; padding: 15px; border-radius: 5px; margin-bottom: 5px;">
            <div style="font-size: 14px; font-weight: bold; color: #4acbd6; margin-bottom: 5px; font-family: sans-serif;">{self.t['daily_fluctuations']} {label_name} <span style="font-size: 12px; font-weight: normal; color: #666;">{self.t['last_3_months']}</span></div>
            <div style="font-size: 12px; color: #555; margin-bottom: 10px; font-family: sans-serif;">
                {self.t['max_hourly_fluctuation']} <strong>{delta:.2f}</strong> 
                <span style="color: #888; font-size: 11px;">{self.t['lower_is_better']}</span>
            </div>
            <div style="display: flex; width: 100%; height: 30px; border-radius: 3px; overflow: hidden; border: 1px solid #ccc;">
        '''
        
        for h in range(24):
            avg = hourly_avg.get(h, None)
            if avg is None:
                color = "#eeeeee"
                title = f"{h:02d}:00 - {self.t['no_data']}"
            else:
                if max_avg > min_avg:
                    score = (avg - min_avg) / delta
                else:
                    score = 0.5
                hue = int(score * 120)
                color = f"hsl({hue}, 100%, 45%)"
                title = f"{h:02d}:00 - Ø {avg:.2f}"
            
            html += f'<div style="flex: 1; background-color: {color};" title="{title}"></div>'
            
        html += '''
            </div>
            <div style="display: flex; justify-content: space-between; width: 100%; font-size: 10px; color: #888; margin-top: 4px; font-family: sans-serif;">
                <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span>
            </div>
        </div>
        '''
        return html

        return html
    
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
        moving_avg_days = self.config.getint('Charts', 'moving_average_days', fallback=7)
        
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
        
        moving_avg_days = self.config.getint('Charts', 'moving_average_days', fallback=7)
        
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
        prompt = """Du bist ein Senior-Diagnostiker für Breitbandtechnik. Deine Aufgabe ist eine Anomalie-Erkennung, kein Statusreport.
        Analyse-Vorgabe: Betrachte die übergebenen DSL-Daten als Gesamtsystem. Ignoriere Einzelaspekte (wie die 3-Uhr-Trennung),
        sofern sie nicht in Kombination mit anderen Werten auf eine instabile Leitung hindeuten.
        Ausgabe-Regeln:        
        Relevanz-Filter: Antworte nur, wenn die Datenlage eine technische Verschlechterung oder ein drohendes Problem nahelegt.
        Wenn alles stabil ist, antworte ausschließlich mit: 'Verbindung ist stabil.'
        Synthese-Pflicht: Fasse deine Erkenntnisse in maximal zwei bis drei Sätzen als Fließtext zusammen.
        Verbotsliste: Keine Aufzählungen, keine Wiederholung von Rohdaten, keine Kommentare zu Routine-Events (Eine Trennung pro Tag ist O.K.!)oder fehlenden Updates.
        Fokus: Benenne nur das 'Warum' der Störung (z.B. 'Kombination aus sinkendem SNR und steigenden Fehlern deutet auf Leitungsstörung hin').
        TOP PRIO!!! Prüfe, ob Du tatsächlich maximal drei Sätze verwendet hast, sonst erneut bearbeiten!
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
        sql = "SELECT time_ut, type, event_text FROM events WHERE time_ut >= ? AND type NOT IN ('Mesh', 'DHCPD') ORDER BY time_ut ASC"
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
        hours_back = self.config.getint('Charts', 'hours_back', fallback=24)
        evt_hours = self.config.getint('Events', 'hours_back', fallback=24)
        exclude = [t.strip() for t in self.config.get('Events', 'exclude_types', fallback='').split(',') if t.strip()]
        conn_since, ip4, ip6, down, up = self._get_connection_status()
        uptime_data = self._get_router_uptime()
        latest_ips = self._get_ip_changes(10)
        fw_upd, fw_old, fw_act, rn_t, rn_d, rn_txt = self._check_firmware_update()
        ai_text = ""
        if self.config.getboolean('Modul', 'ai_analysis', fallback=True):
            ai_text = self._run_ai_analysis(evt_hours)
        conn_analysis_html = self._get_connection_analysis(evt_hours)
        timeline = self._generate_timeline(evt_hours)
        gantt = self._generate_client_gantt(evt_hours)
        clients = self._get_connected_clients(evt_hours)
        traffic = self._get_data_volume_clients()
        charts = self._generate_charts(hours_back)
        show_level = self.config.getint('Events', 'show_level', fallback=4)
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
            
            html += f"<tr><td style='padding: 20px; font-size: 13px; color: #333;'><b>{self.t['connected_since']}</b> {s_since}{time_diff_str}<br><b>{self.t['current']}</b> {ipv4_str}<br><b>{self.t['current']}</b> {ipv6_str}<br><b>{self.t['current']} {self.t['data_rate_down']}</b> {s_down} <b>{self.t['up']}</b> {s_up}."
            
            if uptime_data:
                u_days, u_hours = uptime_data
                html += f"<br><b>{self.t['firmware']}</b> {fw_act} <b>{self.t['last_reboot']}</b> {u_days} {self.t['days']} {u_hours} {self.t['hours']}"
                
            html += "</td></tr>"
            
        if fw_upd:
            rn_ds = datetime.fromtimestamp(rn_d).strftime('%d.%m.%Y') if rn_d else self.t['unknown']
            html += f"""<tr><td style="padding: 20px;"><div style="border: 2px solid #ff9800; background-color: #fff3e0; padding: 15px; border-radius: 5px;">
                <h3 style="margin-top: 0; color: #e65100;">{self.t['fw_notice']}</h3><div style="font-size: 14px; color: #333;">
                {self.t['fw_installed']} <span style="color: #2e7d32; font-weight: bold;">{fw_act}</span><br>
                {self.t['fw_available']} <strong>{rn_t}</strong><br>
                <div style="border-top: 1px solid #ffcc80; margin-top: 10px; padding-top: 10px;"><strong>{self.t['rn']} ({rn_ds}):</strong><br>{rn_txt}</div></div></div></td></tr>"""
        
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
        if self.config.getboolean('Modul', 'snr_heatmap', fallback=True):
            t_table = self.config.get('Charts', 'table_1', fallback='dsl')
            t_field = self.config.get('Charts', 'field_1', fallback='downstream_noise_margin')
            t_label = self.config.get('Charts', 'label_1', fallback=t_field)
            variance_html = self._generate_snr_variance_html(t_table, t_field, t_label)
            if variance_html:
                html += f"<tr><td style='padding: 10px 20px;'>{variance_html}</td></tr>"

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
            for idx, (_, data) in enumerate(charts):
                img = MIMEImage(base64.b64decode(data))
                img.add_header('Content-ID', f'<chart_{idx}>')
                msg_rel.attach(img)
            try:
                srv = smtplib.SMTP(self.config.get('Email', 'smtp_server'), self.config.getint('Email', 'smtp_port'))
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
        cleanup_days = self.config.getint('Reports', 'cleanup_reports', fallback=0)
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
# MAIN CLI
# ---------------------------------------------------------------------------
def main():
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
            c_data = api.get_clients()
            if 'error' not in c_data:
                db.insert_system(c_data.get('system', {}), time.time())
                db.insert_clients(c_data)
                
            dsl_data = api.get_dsl_data()
            if dsl_data: db.insert_dsl(dsl_data, time.time())
                
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
            types_to_purge = [t.strip() for t in exclude_raw.split(',') if t.strip()]
            if types_to_purge:
                db.purge_old_events(cleanup_days, types_to_purge, debug=args.debug)

        rep = Reporter(config_mgr, db, lang)
        rep.debug = args.debug
        rep.generate_report(send_email=args.report_send, show_browser=args.report_show)


if __name__ == "__main__":
    main()

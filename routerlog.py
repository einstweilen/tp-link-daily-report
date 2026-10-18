"""Parser und Auswerte-Helfer für das Router-Log des TP-Link VX231v.

Dieses Modul ist die **einzige** Stelle, die das Logformat kennt. Es wird von
beiden Projekten identisch genutzt (VX231v: ``core/routerlog.py``, tp-report:
``routerlog.py`` direkt neben ``tp-report.py``) - wie schon bei ``arp_scan.py``.

Abgedeckte Formate:

* **ab Firmware 0.26.0** (RFC5424-Stil mit lokalem Kopf)::

      17/10/2026 20:41:38 [5] Other: <293> 1 2026-10-17T18:41:38.386Z VX231v \
cloud_https 2105 CLOUD_EVENT_NOTIFY [cloud-info@11863 event_type="14"] Meldung ...

* **ab Firmware 0.26.0, HTTP-Download** (``/cgi/log?down``, ohne lokalen Kopf, UTC)::

      2026-10-16T16:01:44.980Z VX231v httpd 1770 HTTPD_EVENT [httpd@11863 ...] Login failed!

* **bis Firmware 0.24, nativ**::

      2026-10-10 10:23:47 [6] DHCPD: Recv DISCOVER from 94:45:60:73:72:8D

* **bis Firmware 0.24, rsyslog (ISO8601)**::

      2026-03-10T10:23:47.381632+01:00 192.168.178.1  DHCPD: Recv DISCOVER from ...

Wichtig: MAC/IP stehen ab 0.26.0 in den *Structured Data* (``staMac``, ``MAC``,
``client_mac``, ``offered_ip``, ``ack_ip``), nicht mehr im Meldungstext.
"""

import re
import socket
from datetime import datetime, timezone

# --- Formate -----------------------------------------------------------------

#: Neues Format (FW >= 0.26.0): lokaler Kopf + RFC5424-Kern
NEW_LOG_RE = re.compile(
    r'^(?P<d>\d{2})/(?P<mo>\d{2})/(?P<y>\d{4}) '
    r'(?P<H>\d{2}):(?P<M>\d{2}):(?P<S>\d{2}) '
    r'\[(?P<lvl>\d+)\] (?P<cat>[^:]+): <(?P<pri>\d+)> (?P<ver>\d+) '
    r'(?P<ts>\S+) (?P<host>\S+) (?P<app>\S+) (?P<pid>\S+) (?P<msgid>\S+)(?P<rest>.*)$'
)

#: Variante B (HTTP-Download von /cgi/log?down): nur der RFC5424-Kern mit UTC-Zeit
NEW_LOG_HTTP_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z) '
    r'(?P<host>\S+) (?P<app>\S+) (?P<pid>\S+) (?P<msgid>\S+)(?P<rest>.*)$'
)

#: Paare innerhalb eines Structured-Data-Blocks:  key="value"
SD_PAIR_RE = re.compile(r'([A-Za-z0-9_\-]+)="([^"]*)"')

#: Erlaubte Typ-/App-Namen (verhindert, dass halbe Sätze als Typ in der DB landen)
TYPE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_\-]*$')

MAC_RE = re.compile(r'^[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}$')

#: Structured-Data-Schlüssel, in denen eine Client-MAC steht (Reihenfolge = Priorität)
MAC_SD_KEYS = ("stamac", "client_mac", "sta_mac", "mac", "devicemac")

#: Structured-Data-Schlüssel für eine vom Router vergebene IP
IP_SD_KEYS = ("offered_ip", "ack_ip", "assigned_ip")

# --- Ereignis-Kategorien ------------------------------------------------------

#: Meldungs-IDs, aus denen Client-Sitzungen gebaut werden
CLIENT_MSGIDS = ("WIFI_EVENT", "DHCP_DISCOVER", "DHCP_REQUEST", "DHCP_OFFER", "DHCP_ACK")

#: App-Namen der Client-Ereignisse ab Firmware 0.26.0
CLIENT_APPS = ("mapAgent", "mapController", "dhcpd")

#: Typ-Namen der Client-Ereignisse bis Firmware 0.24
LEGACY_CLIENT_TYPES = ("Mesh", "DHCPD")

#: Ereignisse, die in der Ereignisliste nicht erscheinen (nur Anwesenheit/Statistik)
HIDDEN_EVENT_TYPES = LEGACY_CLIENT_TYPES + CLIENT_APPS

#: Dial-up-Ereignisse (Alt- und Neu-Typ)
PPP_EVENT_TYPES = ("PPP", "pppd")

#: HTTP-Zugriffe/Login-Fehler (Alt- und Neu-Typ)
HTTPD_EVENT_TYPES = ("Httpd", "httpd")

#: Textmarker einer Anmeldung (WLAN) - auch für den Ereignisfilter genutzt
WIFI_UP_MARKERS = ("is associated", "connected success", "add client")

#: Textmarker einer Abmeldung (WLAN)
WIFI_DOWN_MARKERS = ("disassociated", "disconnected", "del client")

# --- Ereignisfilter der Ereignisliste (Regeln A-E) ----------------------------

#: Regel A: Typen, bei denen ein Zugriff mit eigener IP als eigener Abruf gilt
OWN_ACTIVITY_TYPES = ("httpd", "cloud_https")

#: Regel E: immer ausgeblendet - reine DHCP-Routine (neu und Alt-Typ)
ALWAYS_HIDDEN_TYPES = ("dhcpd", "DHCPD")

#: Regel B: Eigen-Routine (Abmeldung aller Sitzungen bei jedem eigenen Login)
OWN_ROUTINE_TYPES = ("tmpd",)

#: Regel C: HTTP-Meldungen ohne Aussage - Fehlschläge bleiben sichtbar
ROUTINE_HTTPD_TEXTS = (
    "Login success!",
    "Logout success!",
    "Log file exported.",
    "The last login is expired, set to anonymous.",
)

#: Regel D: von diesen Typen nur An-/Abmeldungen ausblenden (Fehler bleiben sichtbar)
SESSION_EVENT_TYPES = ("mapAgent", "mapController", "Mesh")

#: Regel E: Alias-Tabelle - alte Config-Schreibweise (NOCASE) -> App-Name im neuen Format
TYPE_ALIASES = {
    "voip": ("voip_client",),
    "mesh": ("mapAgent", "mapController"),
    "dhcpd": ("dhcpd", "DHCPD"),
}

#: Alias-Einträge, die nur die Sitzungsmeldungen meinen: die Typen selbst bleiben in
#: der Ausschlussliste (historische Zeilen heißen so), die neuen App-Namen filtert
#: Regel D - dadurch bleiben deren Fehlermeldungen ("Connection Fail ...") sichtbar.
SESSION_ONLY_ALIASES = ("mesh",)

#: Zeitfenster, in dem DHCP-Antwort und WLAN-Ereignis zusammengehören (Sekunden)
MATCH_WINDOW_S = 10

#: Zeitfenster für die Paarung DHCP-Anfrage -> Antwort (real: wenige Millisekunden)
DHCP_PAIR_WINDOW_S = 2

#: Zeitfenster, in dem gleichartige WLAN-Ereignisse als Doppelmeldung gelten
DEDUPE_WINDOW_S = 2

#: Ersatz-Level, wenn die Log-Variante keinen Level mitliefert (Variante B)
DEFAULT_LEVEL = 5


def sql_in(values):
    """Baut eine SQL-Werteliste aus internen Konstanten (kein Nutzereingabe-Risiko)."""
    return ", ".join("'%s'" % v for v in values)


#: SQL für die Rohdaten der Client-Sitzungen (Platzhalter: Startzeit)
SESSION_SQL = (
    "SELECT time_ut, type, event_text, msgid, mac, ip FROM events "
    "WHERE time_ut >= ? AND (msgid IN (%s) OR (msgid IS NULL AND type IN (%s))) "
    "ORDER BY time_ut ASC" % (sql_in(CLIENT_MSGIDS), sql_in(LEGACY_CLIENT_TYPES))
)


# --- Aufbereitung des Log-Downloads -------------------------------------------

def clean_log_text(text):
    """Bereitet einen Log-Download auf.

    Ab Firmware 0.26.0 liefert der Router die Zeilen bereits getrennt, aber mit
    Artefakten (Statuszeile ``0``, abgeschnittene Kopfzeile). Ältere Stände
    lieferten alles ohne Zeilenumbrüche - dort werden die Umbrüche vor den
    Zeitstempeln ergänzt.
    """
    if not text:
        return text
    text = re.sub(
        r'(?<!\n)(?=(?:\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} )|(?:202\d-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}))',
        '\n', text,
    )
    cleaned = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('BBA Platform version'):   # Kopfzeile des HTTP-Downloads
            continue
        if re.fullmatch(r'\d+', stripped):          # Statuszeile des Downloads ("0")
            continue
        if re.search(r'<\d+>\s*\d+\s*$', stripped) and len(stripped.split()) < 12:
            continue                                # abgeschnittene Kopfzeile ohne Meldung
        cleaned.append(line.rstrip())
    return '\n'.join(cleaned)


# --- Zeilen-Parser ------------------------------------------------------------

def parse_structured_data(sd):
    """Liefert ``(mac, ip)`` aus einem RFC5424-Structured-Data-Block."""
    if not sd:
        return None, None
    pairs = {k.lower(): v for k, v in SD_PAIR_RE.findall(sd)}
    mac = next((pairs[k] for k in MAC_SD_KEYS if pairs.get(k)), None)
    ip = next((pairs[k] for k in IP_SD_KEYS if pairs.get(k)), None)
    if mac:
        mac = mac.replace('-', ':').upper()
        if not MAC_RE.match(mac):
            mac = None
    return mac, ip


def parse_line(line):
    """Parst eine Log-Zeile in ein Ereignis-Dict oder liefert ``None``.

    Rückgabe-Keys: ``dt``, ``time_ut``, ``level_id``, ``type``, ``event_text``,
    ``msgid``, ``mac``, ``ip``, ``sd`` (die letzten vier sind bei Alt-Zeilen ``None``).
    """
    s = (line or '').strip()
    if len(s) < 19:
        return None

    # Rohframes aus rsyslog tragen syslog-Kopf und Router-Kategorie:
    #   "<13> Security: <285> 1 2026-10-17T18:59:40.687Z VX231v httpd 1770 ..."
    stripped = _strip_syslog_header(s)

    for candidate in (s, stripped):
        if not candidate or len(candidate) < 19:
            continue
        event = _parse_new_format(candidate)
        if event:
            return event

    return _parse_legacy_iso(s) or _parse_legacy_native(s)


def _strip_syslog_header(s):
    """Entfernt ``<PRI>``, RFC5424-Version und Router-Kategorie vom Zeilenanfang."""
    for _ in range(4):
        new = re.sub(r'^<\d+>\d*\s*', '', s)                    # <13>, <285>1
        new = re.sub(r'^[A-Za-z][A-Za-z0-9_\-]*:\s+', '', new)    # "Security: "
        new = re.sub(r'^\d{1,2}\s+(?=\d{4}-\d{2}-\d{2}T)', '', new)  # RFC5424-Version "1 "
        if new == s:
            break
        s = new
    return s


def _parse_new_format(s):
    """Format ab Firmware 0.26.0 (lokaler Kopf + RFC5424-Kern)."""
    m = NEW_LOG_RE.match(s)
    if not m:
        return _parse_new_format_http(s)
    try:
        dt = datetime(
            int(m.group('y')), int(m.group('mo')), int(m.group('d')),
            int(m.group('H')), int(m.group('M')), int(m.group('S')),
        )
        app, msgid = m.group('app').strip(), m.group('msgid').strip()
        if not TYPE_RE.match(app):
            return None

        rest = m.group('rest').strip()
        sd, msg = None, rest
        if rest.startswith('['):            # Structured Data vorhanden
            depth, end = 0, None
            for i, ch in enumerate(rest):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                return None
            sd = rest[:end + 1]
            msg = rest[end + 1:].strip()
        elif rest.startswith('-'):          # RFC5424: kein SD
            msg = rest[1:].strip()

        mac, ip = parse_structured_data(sd)
        return {
            'dt': dt,
            'time_ut': int(dt.timestamp()),
            'level_id': int(m.group('lvl')),
            'type': app,
            'event_text': msg,
            'msgid': msgid,
            'mac': mac,
            'ip': ip,
            'sd': sd,
        }
    except (ValueError, TypeError):
        return None


def _parse_new_format_http(s):
    """Variante B: RFC5424-Kern ohne lokalen Kopf (HTTP-Download), Zeitstempel in UTC."""
    m = NEW_LOG_HTTP_RE.match(s)
    if not m:
        return None
    try:
        raw_ts = m.group('ts')[:-1]                     # 'Z' entfernen
        fmt = '%Y-%m-%dT%H:%M:%S.%f' if '.' in raw_ts else '%Y-%m-%dT%H:%M:%S'
        dt = datetime.strptime(raw_ts, fmt).replace(tzinfo=timezone.utc).astimezone()
        app, msgid = m.group('app').strip(), m.group('msgid').strip()
        if not TYPE_RE.match(app):
            return None

        rest = m.group('rest').strip()
        sd, msg = None, rest
        if rest.startswith('['):
            depth, end = 0, None
            for i, ch in enumerate(rest):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                return None
            sd = rest[:end + 1]
            msg = rest[end + 1:].strip()
        elif rest.startswith('-'):
            msg = rest[1:].strip()

        mac, ip = parse_structured_data(sd)
        return {
            'dt': dt,
            'time_ut': int(dt.timestamp()),
            'level_id': DEFAULT_LEVEL,   # Variante B liefert keinen Level mit
            'type': app,
            'event_text': msg,
            'msgid': msgid,
            'mac': mac,
            'ip': ip,
            'sd': sd,
        }
    except (ValueError, TypeError):
        return None


def _parse_legacy_iso(s):
    """Rsyslog-Format (bis FW 0.24): 2026-03-10T10:23:47.381632+01:00 192.168.178.1  DHCPD: ..."""
    if len(s) < 19 or s[10] != 'T':
        return None
    parts = s.split(None, 2)
    if len(parts) < 3:
        return None
    payload = parts[2]
    sep = payload.find(': ')
    if sep <= 0:
        return None
    evt_type = payload[:sep].strip()
    if not TYPE_RE.match(evt_type):
        return None
    try:
        dt = datetime.fromisoformat(parts[0])
    except ValueError:
        return None
    return {
        'dt': dt,
        'time_ut': int(dt.timestamp()),
        'level_id': 8,          # rsyslog liefert keinen Level mit (8 = rsyslog)
        'type': evt_type,
        'event_text': payload[sep + 2:].strip(),
        'msgid': None, 'mac': None, 'ip': None, 'sd': None,
    }


def _parse_legacy_native(s):
    """Natives Format (bis FW 0.24): 2026-10-10 10:23:47 [6] DHCPD: Text..."""
    try:
        dt = datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    rest = s[20:].strip()
    if not rest.startswith('['):
        return None
    rb = rest.find(']')
    if rb <= 1:
        return None
    try:
        level_id = int(rest[1:rb])
    except ValueError:
        return None
    payload = rest[rb + 1:].strip()
    sep = payload.find(': ')
    if sep <= 0:
        return None
    evt_type = payload[:sep].strip()
    if not TYPE_RE.match(evt_type):
        return None
    return {
        'dt': dt,
        'time_ut': int(dt.timestamp()),
        'level_id': level_id,
        'type': evt_type,
        'event_text': payload[sep + 2:].strip(),
        'msgid': None, 'mac': None, 'ip': None, 'sd': None,
    }


# --- Zeitstempel-Korrektur ----------------------------------------------------

def prepare_events(events):
    """Bereitet geparste Ereignisse fürs Speichern auf.

    Die Boot-Zeitstempel-Heuristik gilt nur für **Alt-Zeilen** (bis FW 0.24, ohne `msgid`):
    dort konnte die Router-Uhr falsch stehen. Zeilen ab 0.26.0 haben absolute Zeitstempel
    und werden unverändert übernommen - sonst würde eine lange Log-Pause (> 6 h) alle
    früheren Ereignisse fälschlich verschieben.
    """
    legacy = [e for e in events if not e.get('msgid')]
    modern = [e for e in events if e.get('msgid')]
    return normalize_timestamps(legacy) + modern


def normalize_timestamps(events):
    """Korrigiert Boot-Zeitstempel: der erste große Zeitsprung gilt als Anker,
    alle Einträge davor werden um dasselbe Delta verschoben."""
    if len(events) < 2:
        return events

    min_anchor_jump_seconds = 6 * 3600
    max_future_skew_seconds = 600

    corrected = [dict(e) for e in events]
    now_ut = int(datetime.now().timestamp())

    for idx in range(1, len(corrected)):
        prev_ev, curr_ev = corrected[idx - 1], corrected[idx]
        delta = curr_ev['time_ut'] - prev_ev['time_ut']

        if delta < min_anchor_jump_seconds:
            continue
        if curr_ev['time_ut'] > (now_ut + max_future_skew_seconds):
            continue
        if delta <= 0:
            continue

        for k in range(0, idx):
            corrected[k]['time_ut'] += delta
            corrected[k]['dt'] = datetime.fromtimestamp(corrected[k]['time_ut'])

        if corrected[idx - 1]['time_ut'] > corrected[idx]['time_ut']:
            return events
        return corrected

    return events


# --- Client-Sitzungen ---------------------------------------------------------

def wifi_state(msgid, text):
    """Richtung eines WLAN-Ereignisses: ``'up'``, ``'down'`` oder ``None``."""
    if (msgid or '').upper() != 'WIFI_EVENT':
        return None
    m = (text or '').lower()
    if any(marker in m for marker in WIFI_DOWN_MARKERS):
        return 'down'
    if any(marker in m for marker in WIFI_UP_MARKERS):
        return 'up'
    return None


def extract_mac(text):
    """MAC aus Freitext (Alt-Format, z. B. ``Recv DISCOVER from 94:45:60:73:72:8D``)."""
    s = (text or '').upper().replace('-', ':')
    cur = []
    for ch in s + ' ':
        if ch in '0123456789ABCDEF:':
            cur.append(ch)
            continue
        if cur:
            token, cur = ''.join(cur), []
            parts = token.split(':')
            if len(parts) == 6 and all(len(p) == 2 for p in parts):
                return ':'.join(parts)
    return None


def _first_ip(text):
    m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text or '')
    return m.group(1) if m else None


def legacy_event_fields(evt_type, event_text):
    """Leitet ``msgid``/``mac``/``ip`` aus einer Zeile im Alt-Format (bis FW 0.24) ab.

    Wird für den einmaligen Backfill der Historie genutzt, damit Abfragen über
    ``msgid``/``mac``/``ip`` einheitlich über alle Zeiträume laufen. ``type`` bleibt
    unverändert (historische Absenderbezeichnung).
    """
    t = event_text or ''
    typ = (evt_type or '').strip()
    mac = extract_mac(t)

    if typ == 'Mesh':
        if 'Add Client' in t or 'Del Client' in t:
            return {'msgid': 'WIFI_EVENT', 'mac': mac, 'ip': None}
    elif typ == 'DHCPD':
        if 'Recv DISCOVER' in t:
            return {'msgid': 'DHCP_DISCOVER', 'mac': mac, 'ip': None}
        if 'Recv REQUEST' in t:
            return {'msgid': 'DHCP_REQUEST', 'mac': mac, 'ip': None}
        if 'Send OFFER' in t:
            return {'msgid': 'DHCP_OFFER', 'mac': None, 'ip': _first_ip(t)}
        if 'Send ACK' in t:
            return {'msgid': 'DHCP_ACK', 'mac': None, 'ip': _first_ip(t)}
    elif typ == 'PPP':
        return {'msgid': 'PPP', 'mac': None, 'ip': None}
    elif typ == 'Httpd':
        return {'msgid': 'HTTPD_EVENT', 'mac': None, 'ip': None}
    return {'msgid': None, 'mac': mac, 'ip': None}


def build_client_sessions(rows, home_subnet, now=None):
    """Baut Client-Sitzungen aus Log-Ereignissen.

    ``rows`` sind Zeilen der Form ``(time_ut, type, event_text, msgid, mac, ip)``
    (siehe :data:`SESSION_SQL`). Rückgabe: ``{mac: [{start, end, network}, ...]}``.
    """
    now = datetime.now().timestamp() if now is None else now

    def network_of_ip(ip):
        if not ip:
            return None
        return 'home' if ip.startswith(home_subnet) else 'guest'

    starts, ends, network_hints = [], [], []
    dhcp_asks, dhcp_answers = [], []      # (ts, mac) bzw. (ts, ip) für die Paarung
    for row in rows:
        ts, typ, text, msgid, mac, ip = (list(row) + [None] * 6)[:6]
        ts = int(ts)
        typ, text = typ or '', text or ''
        msgid = (msgid or '').upper()
        mac = (mac or '').upper() or extract_mac(text)

        if msgid == 'WIFI_EVENT':
            state = wifi_state(msgid, text)
            if state == 'up' and mac:
                starts.append((ts, mac))
            elif state == 'down' and mac:
                ends.append((ts, mac))
            continue

        if msgid in ('DHCP_DISCOVER', 'DHCP_REQUEST'):
            if mac:
                starts.append((ts, mac))
                dhcp_asks.append((ts, mac))
            continue
        if msgid in ('DHCP_OFFER', 'DHCP_ACK'):
            if ip:
                dhcp_answers.append((ts, ip))
            net = network_of_ip(ip)
            if net:
                network_hints.append((ts, net))
            continue

        # Alt-Format (bis Firmware 0.24): Marker stehen im Text
        text_low = text
        if typ == 'DHCPD':
            if 'Recv DISCOVER' in text_low or 'Recv REQUEST' in text_low:
                if mac:
                    starts.append((ts, mac))
                    dhcp_asks.append((ts, mac))
            elif 'Send OFFER' in text_low or 'Send ACK' in text_low:
                m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', text_low)
                net = network_of_ip(m.group(1)) if m else None
                if net:
                    network_hints.append((ts, net))
        elif typ == 'Mesh':
            if 'Add Client' in text_low:
                if mac:
                    starts.append((ts, mac))
            elif 'Del Client' in text_low:
                if mac:
                    ends.append((ts, mac))

    # DHCP-Antworten sind nur Millisekunden von der Anfrage entfernt -> clientgenau paaren,
    # damit bei gleichzeitigen Verbindungen (z. B. Mac + Pixel) nicht der falsche
    # OFFER (Heim/Gast) zugeordnet wird.
    mac_network = {}
    claimed = set()                       # jede DHCP-Antwort gehört zu genau einer Anfrage
    for ans_ts, ip in sorted(dhcp_answers):
        net = network_of_ip(ip)
        if not net:
            continue
        candidates = [(abs(ask_ts - ans_ts), idx, ask_mac)
                      for idx, (ask_ts, ask_mac) in enumerate(dhcp_asks)
                      if abs(ask_ts - ans_ts) <= DHCP_PAIR_WINDOW_S and idx not in claimed]
        if not candidates:
            continue
        # Reihenfolge im Log ist DISCOVER -> OFFER: bevorzugt die vorangehende Anfrage
        before = [c for c in candidates if dhcp_asks[c[1]][0] <= ans_ts]
        _, idx, ask_mac = min(before) if before else min(candidates)
        claimed.add(idx)
        mac_network.setdefault(ask_mac, []).append((ans_ts, net))

    def network_for(ts, mac=None, previous=None):
        """Netzart einer Sitzung: eigenes DHCP-Paar, sonst das zuletzt bekannte Netz des
        Clients, sonst eine zeitnahe DHCP-Antwort irgendeines Clients."""
        def nearest(source):
            best, best_diff = None, MATCH_WINDOW_S + 1
            for hint_ts, net in source:
                diff = abs(hint_ts - ts)
                if diff <= MATCH_WINDOW_S and diff < best_diff:
                    best, best_diff = net, diff
            return best

        own = nearest(mac_network.get(mac, []) if mac else [])
        if own:
            return own
        if previous:
            return previous
        return nearest(network_hints) or 'home'

    # Start- und End-Ereignisse chronologisch mischen (0 = Anmeldung, 1 = Abmeldung),
    # damit An-/Abmeldungen im richtigen Verhältnis zueinander stehen.
    timeline = [(ts, 0, mac) for ts, mac in starts] + [(ts, 1, mac) for ts, mac in ends]
    sessions_by_mac = {}
    last_network = {}
    for ts, kind, mac in sorted(timeline):
        sessions = sessions_by_mac.setdefault(mac, [])
        if kind == 0:                    # Anmeldung
            if sessions and sessions[-1]['end'] is None:
                continue                 # Sitzung läuft bereits
            net = network_for(ts, mac, last_network.get(mac))
            sessions.append({'start': ts, 'end': None, 'network': net})
            last_network[mac] = net
        elif sessions and sessions[-1]['end'] is None:   # Abmeldung
            sessions[-1]['end'] = ts

    for sessions in sessions_by_mac.values():
        if sessions and sessions[-1]['end'] is None:
            sessions[-1]['end'] = now
    # MACs mit ausschließlich Abmeldungen (ohne Anmeldung im Zeitraum) nicht ausliefern
    return {mac: sessions for mac, sessions in sessions_by_mac.items() if sessions}


# --- Konfiguration ------------------------------------------------------------

def config_int(config, section, key, default=0):
    """Ganzzahl aus der Konfiguration - tolerant gegen Inline-Kommentare.

    ``configparser`` liefert bei ``cleanup_reports = 7 # Tage`` den Wert
    ``"7 # Tage"``; ``getint()`` scheitert daran. Beide Projekte lesen solche
    Werte über diesen Helfer.
    """
    raw = str(config.get(section, key, fallback=str(default)))
    raw = raw.split('#', 1)[0].strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def config_bool(config, section, key, default=True):
    """Schalter aus der Konfiguration (``True``/``ja``/``an``/``1`` …)."""
    raw = _config_value(config, section, key).split('#', 1)[0].strip().lower()
    if not raw:
        return default
    return raw in ('1', 'true', 'yes', 'ja', 'on', 'wahr', 'an')


def _config_value(config, section, key, default=''):
    """Rohwert aus der Konfiguration - ohne Fehler bei fehlender Section."""
    try:
        if not config.has_section(section):
            return default
        return str(config.get(section, key, fallback=default))
    except (AttributeError, TypeError):
        return default


def router_host(config):
    """Router-Adresse aus der Konfiguration (beide Projekte nutzen andere Schlüssel)."""
    for key in ('routerip', 'router_ip', 'host'):
        value = _config_value(config, 'Router', key).split('#', 1)[0].strip()
        if value:
            return value
    return None


# --- Ereignisfilter: eigene Abrufe und Routine ausblenden ---------------------

def local_ip_addresses(target_host=None):
    """Eigene IPv4-Adressen dieses Rechners (für Regel A der Ereignisliste).

    ``socket.gethostbyname(hostname)`` liefert auf dem Pi nur ``127.0.1.1``, deshalb
    wird die Adresse über einen verbindungslosen UDP-Socket zum Router ermittelt
    (es werden keine Pakete gesendet). Die Namensauflösung bleibt als Rückfall.
    """
    found = []
    targets = [t for t in (target_host, '8.8.8.8') if t]
    for target in targets:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((target, 80))
            ip = sock.getsockname()[0]
        except OSError:
            continue
        finally:
            if sock is not None:
                sock.close()
        if ip and not ip.startswith('127.') and ip not in found:
            found.append(ip)
    if not found:
        try:
            ip = socket.gethostbyname(socket.gethostname())
            if ip and not ip.startswith('127.'):
                found.append(ip)
        except OSError:
            pass
    return found


def own_ip_list(config=None, section='Events', key='own_ips'):
    """Eigene IP-Adressen für Regel A: aus der Konfiguration, sonst automatisch."""
    raw = _config_value(config, section, key).split('#', 1)[0]
    ips = [part for part in re.split(r'[,;\s]+', raw) if part]
    if ips:
        return ips
    return local_ip_addresses(router_host(config))


def expand_exclude_types(values):
    """Erweitert Typ-Listen aus der Konfiguration um die Namen des neuen Formats (Regel E).

    Der eingetragene Name bleibt erhalten (historische Zeilen heißen so) und die
    App-Namen des neuen Formats kommen hinzu - ``VoIP`` wirkt damit auf ``voip_client``,
    ``DHCPD`` auf ``dhcpd``. ``Mesh`` meinte schon immer die WLAN-An-/Abmeldungen: diese
    blendet Regel D aus (samt den neuen App-Namen), damit deren Fehlermeldungen
    (``Connection Fail ...``) sichtbar bleiben.
    """
    expanded = []
    for value in values or []:
        name = (value or '').strip()
        if not name:
            continue
        if name not in expanded:
            expanded.append(name)
        if name.lower() in SESSION_ONLY_ALIASES:
            continue
        for target in TYPE_ALIASES.get(name.lower(), ()):
            if target not in expanded:
                expanded.append(target)
    return expanded


def sql_marks(values):
    """Platzhalter für ``IN (...)`` - passend zu den Werten als Parameter."""
    return ", ".join("?" for _ in values)


def event_where(config=None, exclude_types=None, show_level=4):
    """SQL-Bedingung und Parameter für die Ereignisliste (Regeln A-E).

    Rückgabe: ``(clause, params)``. ``clause`` beginnt mit ``AND`` und wird an
    ``WHERE time_ut >= ?`` angehängt; die Parameter gehören in derselben Reihenfolge
    in die Parameterliste. Beide Projekte filtern ihre Ereignisliste ausschließlich
    über diesen Helfer, damit die Regeln identisch bleiben.
    """
    params, parts = [], []

    excluded = expand_exclude_types(exclude_types)
    if show_level == 9:
        # 9 = alles anzeigen, nur die Ausschlusstypen filtern
        if excluded:
            parts.append("AND type COLLATE NOCASE NOT IN (%s)" % sql_marks(excluded))
            params.extend(excluded)
    elif excluded:
        # Fehler/Warnungen (Level <= 4) bleiben sichtbar, obwohl ihr Typ gefiltert ist
        parts.append("AND (type COLLATE NOCASE NOT IN (%s) OR level_id <= 4) AND level_id <= ?"
                     % sql_marks(excluded))
        params.extend(excluded)
        params.append(show_level)
    else:
        parts.append("AND level_id <= ?")
        params.append(show_level)

    hidden = ["type COLLATE NOCASE IN (%s)" % sql_in(ALWAYS_HIDDEN_TYPES)]   # Regel E
    if config_bool(config, 'Events', 'hide_own_activity', True):
        hidden.append("type COLLATE NOCASE IN (%s)" % sql_in(OWN_ROUTINE_TYPES))   # Regel B

        ips = own_ip_list(config)                                                  # Regel A
        if ips:
            matches = []
            for ip in ips:
                matches.append("(IFNULL(event_text, '') LIKE ? OR IFNULL(sd, '') LIKE ?)")
                params.extend(['%%%s%%' % ip, '%%%s%%' % ip])
            hidden.append("(type COLLATE NOCASE IN (%s) AND (%s))"
                          % (sql_in(OWN_ACTIVITY_TYPES), " OR ".join(matches)))

        hidden.append("(type COLLATE NOCASE = 'httpd' AND TRIM(event_text) IN (%s))"
                      % sql_in(ROUTINE_HTTPD_TEXTS))                               # Regel C

        matches = []
        for marker in WIFI_UP_MARKERS + WIFI_DOWN_MARKERS:                          # Regel D
            matches.append("IFNULL(event_text, '') LIKE ?")
            params.append('%%%s%%' % marker)
        hidden.append("(type COLLATE NOCASE IN (%s) AND (%s))"
                      % (sql_in(SESSION_EVENT_TYPES), " OR ".join(matches)))

    parts.append("AND NOT (%s)" % " OR ".join(hidden))
    return " ".join(parts), params

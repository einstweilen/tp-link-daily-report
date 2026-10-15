"""
Lokale ARP-Erkennung von Netzwerk-Clients - ohne SNMP und ohne Router-Zugang.

Hintergrund: Die WLAN-/Mesh-Tabellen des Routers sind gelegentlich komplett leer
und die SNMP-ARP-Tabelle setzt einen superadmin-Account plus net-snmp voraus.
Diese Erkennung fragt stattdessen die Geräte im eigenen Netz direkt an
(paralleler Ping-Sweep der lokalen Subnetze) und liest anschließend die
Kernel-ARP-Tabelle des eigenen Rechners (`arp -an` bzw. `ip neigh show`).

Voraussetzung: Das Skript läuft im selben Netzsegment. Geräte, die weder auf Ping
noch auf sonstigen Verkehr antworten (z. B. schlafende Telefone), können fehlen.

Aufruf als CLI:
    python3 -m core.arp_scan          # Geräte im lokalen Netz auflisten
    python3 -m core.arp_scan --no-sweep   # nur vorhandene ARP-Einträge zeigen
"""

import ipaddress
import platform
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ARP_SCAN_TIMEOUT_S = 1          # Timeout je Ping
ARP_SCAN_WORKERS = 64           # parallele Pings
ARP_SCAN_MAX_HOSTS = 1024       # Schutz vor /8-/16-Sweeps

_SKIP_MACS = ('ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00')


def _run(cmd, timeout=15):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout if proc.returncode == 0 else ''
    except Exception:
        return ''


def normalize_mac(mac):
    """MAC nach XX:XX:XX:XX:XX:XX normalisieren (macOS kürzt führende Nullen)."""
    parts = re.split(r'[:-]', (mac or '').strip())
    if len(parts) != 6 or not all(re.fullmatch(r'[0-9a-fA-F]{1,2}', p) for p in parts):
        return ''
    return ':'.join(p.zfill(2).upper() for p in parts)


def local_interfaces():
    """Lokale IPv4-Interfaces als (name, ip, netz)."""
    interfaces = []
    try:
        if platform.system() == 'Darwin':
            current = None
            for line in _run(['ifconfig']).splitlines():
                m = re.match(r'^(\w+):', line)
                if m:
                    current = m.group(1)
                    continue
                m = re.search(r'inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-fA-F]+)', line)
                if m and current and not current.startswith(('lo', 'utun', 'tun', 'ipsec', 'tailscale')):
                    net = ipaddress.IPv4Network(
                        f"{m.group(1)}/{ipaddress.IPv4Address(int(m.group(2), 16))}", strict=False)
                    interfaces.append((current, m.group(1), net))
        else:
            for line in _run(['ip', '-4', '-o', 'addr', 'show']).splitlines():
                m = re.match(r'\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+/\d+)', line)
                if m and not m.group(1).startswith(('lo', 'tun', 'wg', 'tailscale')):
                    net = ipaddress.IPv4Network(m.group(2), strict=False)
                    interfaces.append((m.group(1), m.group(2).split('/')[0], net))
    except Exception:
        return []

    result = []
    for name, ip, net in interfaces:
        if net.is_loopback or net.is_link_local or net.num_addresses < 4:
            continue
        if net.num_addresses > ARP_SCAN_MAX_HOSTS:
            continue
        result.append((name, ip, net))
    return result


def local_subnets():
    """Lokale IPv4-Subnetze (ohne Loopback/Link-Local/Tunnel)."""
    return [(name, net) for name, _ip, net in local_interfaces()]


def own_addresses(subnets=None):
    """Eigene Adressen + Netz-/Broadcastadressen (fallen aus der Clientliste)."""
    own = {ip for _name, ip, _net in local_interfaces()}
    nets = subnets if subnets is not None else local_subnets()
    for _name, net in nets:
        own.add(str(net.network_address))
        own.add(str(net.broadcast_address))
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            own.add(info[4][0])
    except Exception:
        pass
    return own


def _ping(ip):
    if platform.system() == 'Darwin':
        cmd = ['ping', '-c', '1', '-W', str(ARP_SCAN_TIMEOUT_S * 1000), '-t', str(ARP_SCAN_TIMEOUT_S), str(ip)]
    else:
        cmd = ['ping', '-c', '1', '-W', str(ARP_SCAN_TIMEOUT_S), str(ip)]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=ARP_SCAN_TIMEOUT_S * 3)
    except Exception:
        pass


def ping_sweep(subnets=None, workers=ARP_SCAN_WORKERS):
    """Pingt alle Hosts der Subnetze parallel an (weckt die ARP-Einträge)."""
    targets = []
    for _name, net in (subnets if subnets is not None else local_subnets()):
        targets.extend(str(h) for h in net.hosts())
    if not targets:
        return 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_ping, targets))
    return len(targets)


def read_arp_cache():
    """ARP-Tabelle des eigenen Rechners als {ip: mac}."""
    entries = {}
    if platform.system() == 'Darwin':
        for line in _run(['arp', '-an']).splitlines():
            m = re.search(r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)', line)
            if m:
                mac = normalize_mac(m.group(2))
                if mac:
                    entries[m.group(1)] = mac
        return entries

    # Linux: iproute2 bevorzugt, sonst net-tools
    out = _run(['ip', 'neigh', 'show'])
    for line in out.splitlines():
        m = re.match(r'(\d+\.\d+\.\d+\.\d+)\s+.*?lladdr\s+([0-9a-fA-F:]+)', line)
        if m:
            mac = normalize_mac(m.group(2))
            if mac:
                entries[m.group(1)] = mac
    if not entries:
        for line in _run(['arp', '-an']).splitlines():
            m = re.search(r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)', line)
            if m:
                mac = normalize_mac(m.group(2))
                if mac:
                    entries[m.group(1)] = mac
    return entries


def default_gateways():
    """IP und MAC des Standard-Gateways (Router) - wird aus der Clientliste entfernt."""
    out = _run(['netstat', '-rn'])
    ips = set()
    if platform.system() == 'Darwin':
        for line in out.splitlines():
            if line.startswith('default'):
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if m:
                    ips.add(m.group(1))
    else:
        if not out:
            out = _run(['ip', 'route', 'show', 'default'])
        for line in out.splitlines():
            m = re.search(r'default via (\d+\.\d+\.\d+\.\d+)', line)
            if m:
                ips.add(m.group(1))

    cache = read_arp_cache()
    macs = {cache[ip].lower() for ip in ips if ip in cache}
    return ips, macs


def get_local_arp_clients(db_manager=None, subnets=None, sweep=True, resolve_names=True):
    """Clients aus dem lokalen ARP-Scan (ohne SNMP, ohne Router-Zugang)."""
    nets = subnets if subnets is not None else local_subnets()
    if sweep:
        ping_sweep(nets)

    gw_ips, gw_macs = default_gateways()
    skip_ips = own_addresses(nets) | gw_ips
    clients = []
    for ip, mac in sorted(read_arp_cache().items(),
                          key=lambda kv: tuple(int(x) for x in kv[0].split('.'))):
        if mac.lower() in _SKIP_MACS or mac.lower() in gw_macs:
            continue
        if mac.startswith(('01:00:5E', '33:33')):
            continue
        if ip in skip_ips:
            continue
        if nets and not any(ipaddress.IPv4Address(ip) in net for _name, net in nets):
            continue

        name = db_manager.get_hostname_by_mac(mac) if db_manager else None
        if not name and resolve_names:
            try:
                name = socket.gethostbyaddr(ip)[0]
            except Exception:
                name = None
        clients.append({
            'mac': mac,
            'hostname': name or 'Unknown',
            'ip': ip,
            'is_connected': 1,
            'signal_strength': 0,
            'wifi_standard': 'ARP-Scan',
            'download_rate_mbps': 0,
            'upload_rate_mbps': 0,
            'bytes_total': 0
        })
    return clients


def main(argv=None):
    import time
    args = list(sys.argv[1:] if argv is None else argv)
    sweep = '--no-sweep' not in args

    nets = local_subnets()
    print("Lokale Subnetze: " + (", ".join(f"{n} ({i})" for i, n in nets) or "keine gefunden"))
    start = time.time()
    clients = get_local_arp_clients(sweep=sweep)
    print(f"{'IP':16} {'MAC':18} Hostname")
    for c in clients:
        print(f"{c['ip']:16} {c['mac']:18} {c['hostname']}")
    print(f"\n{len(clients)} Client(s) in {time.time() - start:.1f}s"
          f"{' (Ping-Sweep aktiv)' if sweep else ' (ohne Sweep, nur ARP-Cache)'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

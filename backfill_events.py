#!/usr/bin/env python3
"""Trägt `msgid`, `mac` und `ip` für Ereignisse aus der Zeit vor Firmware 0.26.0 nach.

Ab 0.26.0 stehen diese Felder direkt im Log; ältere Zeilen haben sie nicht. Damit
Abfragen über die gesamte Historie einheitlich laufen, leitet dieses Werkzeug die
Felder einmalig aus dem Ereignistext ab (`routerlog.legacy_event_fields`).
`type` bleibt unverändert, das Skript ist beliebig oft ausführbar (idempotent).

    python3 tools/backfill_events.py --db /pfad/router_data.db --dry-run
    python3 tools/backfill_events.py --db /pfad/router_data.db
"""

import argparse
import os
import sqlite3
import sys
from collections import Counter

# Projektverzeichnis in den Suchpfad (Skript liegt in tools/ bzw. neben tp-report.py)
_here = os.path.dirname(os.path.abspath(__file__))
for _p in (_here, os.path.dirname(_here)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:                                     # VX231v (Paket "core")
    from core import routerlog
except ImportError:                      # tp-report (Modul neben dem Skript)
    import routerlog


def main():
    ap = argparse.ArgumentParser(description="Backfill für Ereignisse vor Firmware 0.26.0")
    ap.add_argument("--db", required=True, help="Pfad zur router_data.db")
    ap.add_argument("--dry-run", action="store_true", help="nur zählen, nichts schreiben")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    cols = {row[1] for row in cur.execute("PRAGMA table_info(events)")}
    missing = [c for c in ("msgid", "mac", "ip") if c not in cols]
    if missing:
        sys.exit(f"Spalten fehlen ({', '.join(missing)}) - bitte die Anwendung einmal starten "
                 "(die Migration legt sie an).")

    rows = cur.execute("SELECT id, type, event_text FROM events WHERE msgid IS NULL").fetchall()
    stats, changed = Counter(), 0
    for event_id, evt_type, evt_text in rows:
        fields = routerlog.legacy_event_fields(evt_type, evt_text)
        if not (fields["msgid"] or fields["mac"] or fields["ip"]):
            continue
        stats[fields["msgid"] or "(nur mac)"] += 1
        changed += 1
        if not args.dry_run:
            cur.execute(
                "UPDATE events SET msgid = ?, mac = ?, ip = ? WHERE id = ? AND msgid IS NULL",
                (fields["msgid"], fields["mac"], fields["ip"], event_id),
            )

    if not args.dry_run:
        con.commit()

    print(f"{'[dry-run] ' if args.dry_run else ''}{changed} von {len(rows)} Altzeilen "
          f"{'würden' if args.dry_run else 'wurden'} ergänzt:")
    for msgid, count in stats.most_common():
        print(f"   {msgid:16} {count:6}")
    rest = cur.execute("SELECT COUNT(*) FROM events WHERE msgid IS NULL").fetchone()[0]
    print(f"ohne msgid (nicht zuordenbar): {rest}")


if __name__ == "__main__":
    main()

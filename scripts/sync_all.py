"""
One command that brings the whole lake current -- run it by hand, from cron, or from CI:

    python3 scripts/sync_all.py            # only what changed upstream
    python3 scripts/sync_all.py --force    # re-pull everything

nflverse (schedule, weekly stats, depth charts, official injuries, headshots) via backend/lake_sync.py, then every
ESPN agent once (scoreboard, lines, injuries, standings, grades, MY BOO reports). The running site does the same on
its own: boo_staff starts at boot and the Lake Clerk repeats hourly (every 30 min while games are live).
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import lake_sync, boo_staff

print("== nflverse ==")
r = lake_sync.run(force="--force" in sys.argv)
print(json.dumps({k: r[k] for k in ("week", "rolled", "notes", "errors", "integrity")}, indent=2))
print("== ESPN staff ==")
for a in boo_staff.AGENTS:
    if a["id"] in ("lake_clerk", "hermes_liaison"):
        continue
    boo_staff.run_agent(a)
    st = boo_staff._read("staff_status.json", {}).get(a["id"], {})
    print(f"{a['id']:18} {'ok ' if not st.get('errors') else 'ERR'} {st.get('note') or st.get('last_error')}")

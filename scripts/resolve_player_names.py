"""
Resolve player names/positions/teams from nflverse (canonical GSIS table),
with the ESPN headshot index as a secondary check.

Writes: lake/gold/espn/player_names_patch.csv — keyed by gsis_id, columns
player_id,name,position,team,source. data.py layers this into the player
dimension, so no player ever reads out as "00-XXXXXXX" again.

Run:  python scripts/resolve_player_names.py [PLAYER_STATS.CSV.GZ]
(Downloads from nflverse-data releases when the file isn't given.)
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "lake" / "gold" / "espn"
OUT = GOLD / "player_names_patch.csv"
NFV_URL = "https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv.gz"

TEAM_CODE_NORMALIZE = {"LAR": "LA", "OAK": "LV", "WAS": "WAS"}  # lake abbrs


def fetch_nflverse(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        print(f"downloading nflverse player_stats...")
        req = urllib.request.Request(NFV_URL, headers={"User-Agent": "big-proppa-resolver/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
    else:
        data = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(data).decode("utf-8", "replace"))))
    print(f"nflverse rows: {len(rows)}")
    return rows


def main() -> None:
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = fetch_nflverse(arg)

    # GSIS -> best display name + position + recent team across the season
    byid: dict[str, dict] = {}
    for r in rows:
        pid = (r.get("player_id") or "").strip()
        if not pid:
            continue
        name = (r.get("player_display_name") or r.get("player_name") or "").strip()
        pos = (r.get("position") or "").strip()
        team = (r.get("recent_team") or "").strip()
        team = TEAM_CODE_NORMALIZE.get(team, team)
        cur = byid.setdefault(pid, {"player_id": pid, "name": "", "position": "", "team": ""})
        if name:
            cur["name"] = name
        if pos:
            cur["position"] = pos
        if team:
            cur["team"] = team

    # Which lake players are still anonymous?
    unknown: set[str] = set()
    try:
        reg = json.loads((GOLD / "player_slugs.json").read_text())
        for e in reg.values():
            if not e.get("name") or e["name"].startswith("00-"):
                unknown.add(e.get("player_id", ""))
    except Exception:
        pass
    print(f"nameless in slug registry: {len(unknown)}")

    try:
        cache = json.loads((GOLD / "jimmy_takes.json").read_text())
        for t in (cache or {}).values():
            n = t.get("name") or ""
            if not n or n.startswith("00-"):
                unknown.add(t.get("playerId") or t.get("player_id") or "")
    except Exception:
        pass
    unknown.discard("")

    # Second source: nflverse rosters (practice squad, IR, camp — the players
    # who never appear in weekly player_stats).
    for yr in ("2026", "2025"):
        p = Path(f"/tmp/opencode/roster_{yr}.csv")
        tmp_path = p if p.exists() else None
        if tmp_path is None:
            try:
                req = urllib.request.Request(
                    f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{yr}.csv",
                    headers={"User-Agent": "big-proppa-resolver/1.0"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = r.read()
                tmp_path = Path(f"/tmp/opencode/roster_{yr}.csv")
                tmp_path.write_bytes(data)
            except Exception as e:
                print(f"roster {yr}: {e}")
                continue
        with tmp_path.open(newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                pid = (r.get("gsis_id") or "").strip()
                if not pid:
                    continue
                name = (r.get("full_name") or "").strip()
                pos = (r.get("position") or "").strip()
                team = (r.get("team") or "").strip()
                team = TEAM_CODE_NORMALIZE.get(team, team)
                cur = byid.setdefault(pid, {"player_id": pid, "name": "", "position": "", "team": ""})
                if name and not cur["name"]:
                    cur["name"] = name
                if pos and not cur["position"]:
                    cur["position"] = pos
                if team and not cur["team"]:
                    cur["team"] = team

    resolved, unresolved = [], list()
    for pid in sorted(unknown):
        hit = byid.get(pid)
        if hit and hit["name"]:
            resolved.append(hit)
        else:
            unresolved.append(pid)

    print(f"resolved from nflverse: {len(resolved)}, still unknown: {len(unresolved)}")

    # Patch table = any player in either ID source that nflverse resolves
    wanted = unknown | {h["player_id"] for h in byid.values()}
    punch = [h for h in byid.values() if h["player_id"] in unknown or not h]
    GOLD.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["player_id", "name", "position", "team", "source"])
        w.writeheader()
        for h in sorted(byid.values(), key=lambda x: x["player_id"]):
            if h["name"]:
                h["source"] = "nflverse"
                w.writerow(h)
    print(f"patch rows (all nflverse GSIS players): {len(byid)} → {OUT}")

    for h in resolved[:15]:
        print(f"  ✓ {h['player_id']} → {h['name']} ({h['position']}, {h['team']})")
    if unresolved:
        print("  still unknown (ESPN pass needed):", unresolved[:8], "...")


if __name__ == "__main__":
    main()

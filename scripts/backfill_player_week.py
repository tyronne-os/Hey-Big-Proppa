"""
Backfill lake/gold/nfl/player_*_week.csv with any 2026 (player, week) rows that nflverse's
stats_player_week_2026.csv has but the gold files lack (e.g. a team whose game finished after the last pull).
Only appends missing rows; never edits existing ones. Derived columns follow the gold conventions:
scoring excludes passing TDs; scrimmage = rushing + receiving.

    curl -sSLfo /tmp/stats_player_week_2026.csv https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_2026.csv
    python3 scripts/backfill_player_week.py /tmp/stats_player_week_2026.csv
"""
import csv, datetime as dt, glob, sys
from pathlib import Path

GOLD = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"
src = list(csv.DictReader(open(sys.argv[1])))
run = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def f(r, k):
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


def num(x):
    return str(int(x)) if float(x).is_integer() else str(round(x, 4))


def derived(name, r):
    if name == "player_scoring_week":
        tds = sum(f(r, k) for k in ("rushing_tds", "receiving_tds", "def_tds", "special_teams_tds", "fumble_recovery_tds", "pt_return_tds"))
        two = sum(f(r, k) for k in ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions", "def_2pt_made"))
        return {"total_tds": num(tds), "total_points": num(6 * tds + 2 * two + f(r, "pat_made") + 3 * f(r, "fg_made") + 2 * f(r, "def_safeties"))}
    if name == "player_scrimmage_week":
        t = f(r, "carries") + f(r, "receptions")
        y = f(r, "rushing_yards") + f(r, "receiving_yards")
        return {"touches": num(t), "scrimmage_yards": num(y), "scrimmage_tds": num(f(r, "rushing_tds") + f(r, "receiving_tds")),
                "yards_per_touch": num(y / t) if t else "0", "scrimmage_first_downs": num(f(r, "rushing_first_downs") + f(r, "receiving_first_downs")),
                "scrimmage_fumbles": num(f(r, "rushing_fumbles") + f(r, "receiving_fumbles"))}
    return {}


for path in sorted(glob.glob(str(GOLD / "player_*_week.csv"))):
    name = Path(path).stem
    rows = list(csv.DictReader(open(path)))
    cols = list(rows[0].keys())
    have = {(r["player_id"], r["season"], r["week"]) for r in rows}
    add = []
    for r in src:
        if not r["player_id"] or (r["player_id"], r["season"], r["week"]) in have:
            continue
        o = {c: r.get(c, "") for c in cols}
        o.update(derived(name, r))
        o["ingest_run_id"] = run
        add.append(o)
    if add:
        with open(path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writerows(add)
    print(name, "added", len(add))

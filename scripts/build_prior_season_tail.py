"""
Last season's closing stretch, for the L10.

Reads nflverse's weekly player stats for the prior season (lake/bronze/nflverse/stats_player_week_<season>.csv,
downloaded from github.com/nflverse/nflverse-data releases, tag stats_player) and keeps each player's last
7 regular-season games in lake/gold/nfl/player_week_prior_tail.csv. The Targets board puts those games in
front of this season's, so a player's L10 is full from week 1 and last season's games roll off as this
season's weeks are played. The team column is the team he played for at the time.

    python3 scripts/build_prior_season_tail.py --season 2025
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = 7
COLS = ["season", "week", "game_id", "player_id", "player_name", "position", "team", "opponent_team",
        "targets", "receptions", "receiving_yards", "receiving_tds", "receiving_air_yards", "receiving_yards_after_catch",
        "receiving_10", "receiving_16", "receiving_20", "receiving_40", "target_share", "air_yards_share", "wopr",
        "carries", "rushing_yards", "rushing_tds", "rushing_10", "rushing_12", "rushing_20", "rushing_40",
        "fantasy_points_ppr"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2025)
    a = ap.parse_args()
    src = ROOT / "lake" / "bronze" / "nflverse" / f"stats_player_week_{a.season}.csv"
    by: dict[str, list[dict]] = defaultdict(list)
    with open(src, newline="") as f:
        for r in csv.DictReader(f):
            if r["season_type"] == "REG" and r.get("position") in ("WR", "TE", "RB", "QB", "FB"):
                by[r["player_id"]].append(r)
    out = []
    for pid, rows in by.items():
        rows.sort(key=lambda r: int(r["week"]))
        out += rows[-KEEP:]
    dst = ROOT / "lake" / "gold" / "nfl" / "player_week_prior_tail.csv"
    with open(dst, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} rows, {len(by)} players -> {dst}")


if __name__ == "__main__":
    main()

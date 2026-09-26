"""
Pull FanDuel ALTERNATE prop ladders for this week's NFL slate into the lake.

    lake/gold/nfl/fanduel_alt_lines.csv

The lake's regular prop feed carries one FanDuel line per prop. SPY BOY needs the
ladder (e.g. over 39.5 / 49.5 / 59.5 receiving yards, each with its own price) so
it can take the rung where the Big Proppa Line is 75%+ but the price still pays.

Cost: The Odds API charges 1 credit per event per market (the events list is free).
A full slate is about 16 events x 4 markets = 64 credits, so this is a MANUAL script:
no endpoint or page load ever calls it. It stops before dipping under --reserve.

    backend/.venv/bin/python scripts/refresh_fanduel_alts.py            # whole slate
    backend/.venv/bin/python scripts/refresh_fanduel_alts.py --dry-run  # list only, 0 credits

Key is read from THE_ODDS_API_KEY in the environment and never printed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import bpl  # noqa: E402
import data  # noqa: E402

BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
MARKETS = {
    "player_pass_yds_alternate": "passyds",
    "player_rush_yds_alternate": "rushyds",
    "player_reception_yds_alternate": "recyds",
    "player_receptions_alternate": "recs",
}
OUT = ROOT / "lake" / "gold" / "nfl" / "fanduel_alt_lines.csv"
COLS = ["fetched_at_utc", "event_id", "away", "home", "market_slug", "player_name", "side", "line", "price_american"]


def call(path: str, **params) -> tuple[object, int | None]:
    params["apiKey"] = os.environ["THE_ODDS_API_KEY"]
    url = f"{BASE}{path}?" + "&".join(f"{k}={v}" for k, v in params.items())
    with urllib.request.urlopen(url, timeout=25) as r:
        left = r.headers.get("x-requests-remaining")
        return json.loads(r.read()), int(left) if left is not None else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reserve", type=int, default=150, help="stop before remaining credits fall under this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not os.environ.get("THE_ODDS_API_KEY"):
        sys.exit("THE_ODDS_API_KEY is not set (run: set -a; . ~/.api_keys_env; set +a)")

    names = {r["full_name"]: r["abbr_lake"] for r in data.load("team_abbr_map")}
    slate = {frozenset((t, g["opp"])) for t, g in bpl.next_games().items()}
    events, left = call(f"/sports/{SPORT}/events")
    todo = []
    for e in events:
        pair = frozenset((names.get(e["home_team"]), names.get(e["away_team"])))
        if pair in slate:
            todo.append(e)
    print(f"{len(todo)} events in this week's slate x {len(MARKETS)} markets = {len(todo) * len(MARKETS)} credits; {left} available")
    if args.dry_run:
        return

    rows, spent = [], 0
    now = datetime.now(timezone.utc).isoformat()
    for e in todo:
        for market, slug in MARKETS.items():
            if left is not None and left - 1 < args.reserve:
                print(f"reserve of {args.reserve} reached, stopping early")
                break
            body, left = call(f"/sports/{SPORT}/events/{e['id']}/odds", regions="us", bookmakers="fanduel",
                              markets=market, oddsFormat="american")
            spent += 1
            for bk in body.get("bookmakers", []):
                for m in bk.get("markets", []):
                    for o in m.get("outcomes", []):
                        rows.append({"fetched_at_utc": now, "event_id": e["id"], "away": names.get(e["away_team"]),
                                     "home": names.get(e["home_team"]), "market_slug": slug,
                                     "player_name": o.get("description", ""), "side": o.get("name", "").lower(),
                                     "line": o.get("point"), "price_american": o.get("price")})
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} ladder rungs to {OUT.relative_to(ROOT)}; spent {spent} credits; {left} remaining")


if __name__ == "__main__":
    main()

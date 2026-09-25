#!/usr/bin/env python3
"""
DraftKings4 (RapidAPI) pull -- rationed to fit a 300-total-request budget
through week 8 of the 2026 season, per user's evaluation plan (2026-09-25):
run this for free through week 8, then meet to decide which POND earned a
real subscription.

Budget math (confirmed against the real x-ratelimit-requests-limit header):
    weeks 1-8 = 121 games total
    2 pulls/game (pre-game + post-game) = 242 calls
    296 remaining at last check -> fits with ~54 calls of headroom

STATUS: work in progress, not yet finished. A known bug was found (the
budget-remaining header lookup silently returned None due to a case-
sensitivity issue reading r.headers) and the fix was interrupted mid-edit.
Do not treat the budget_before() check as reliable until that's confirmed
fixed and re-tested end to end.

Two modes, matching the user's exact ask ("one when the lake updates, then
two pulls on game day"):
    --mode weekly   : one lightweight pull -- the week's game list only
                       (1 call total, not per game -- confirms schedule/lines
                       exist, does not burn budget on markets we won't grade
                       until game day)
    --mode pregame  : one full-market pull per game NOT YET STARTED this week
    --mode postgame : one full-market pull per game ALREADY FINISHED this week
                       (captures closing-adjacent state for later comparison)

Each event call returns ALL ~268 markets in one shot (confirmed) -- do not
call per-market, that would multiply the cost for no reason.

This is a temporary evaluation key (per the user: "delete and replace" before
going live) -- treat every call as budget-limited on purpose. The script
tracks remaining budget itself.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_draftkings4.py --mode weekly
    PYTHONPATH=.pylibs python3 scripts/ingest_draftkings4.py --mode pregame
    PYTHONPATH=.pylibs python3 scripts/ingest_draftkings4.py --mode postgame
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "draftkings4"
BUDGET_LOG = REPO / "lake" / "bronze" / "draftkings4" / "_budget_log.jsonl"
HOST = "draftkings4.p.rapidapi.com"
BASE = f"https://{HOST}"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def load_key() -> str:
    import os
    key = os.environ.get("RAPIDAPI_KEY")
    if key:
        return key
    env_file = pathlib.Path.home() / ".rapidapi_env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "RAPIDAPI_KEY" in line and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: RAPIDAPI_KEY not found in env or ~/.rapidapi_env.\n"
          "  set -a; . ~/.rapidapi_env; set +a", file=sys.stderr)
    sys.exit(2)


def api_get(path: str, key: str) -> tuple[dict, dict]:
    req = urllib.request.Request(
        f"{BASE}/{path}",
        headers={"x-rapidapi-host": HOST, "x-rapidapi-key": key},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        # r.headers is an email.message.Message -- .get() is case-insensitive
        # on it directly. dict(r.headers) preserves the server's exact casing
        # (X-RateLimit-Requests-Remaining), which a lowercase .get() key would
        # miss -- confirmed this was silently swallowing the real value.
        remaining = r.headers.get("x-ratelimit-requests-remaining")
        body = json.loads(r.read())
    if remaining is not None:
        log(f"  budget remaining after this call: {remaining}")
    else:
        log("  WARNING: rate-limit header not found in response")
    record_budget_use(path, remaining)
    return body, dict(r.headers)


def record_budget_use(path: str, remaining: str | None) -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    with BUDGET_LOG.open("a") as fh:
        fh.write(json.dumps({
            "at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "path": path,
            "remaining_after": remaining,
        }) + "\n")


def check_budget_before(estimated_calls: int) -> bool:
    if not BUDGET_LOG.exists():
        log(f"No budget log yet -- proceeding, but track this run's usage.")
        return True
    lines = BUDGET_LOG.read_text().splitlines()
    if not lines:
        return True
    last = json.loads(lines[-1])
    remaining = last.get("remaining_after")
    if remaining is None:
        return True
    remaining = int(remaining)
    log(f"Budget check: {remaining} remaining, this run needs ~{estimated_calls}")
    if estimated_calls > remaining:
        log(f"REFUSING to proceed: would exceed remaining budget "
            f"({estimated_calls} needed > {remaining} left). Run a smaller "
            f"batch or wait.")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["weekly", "pregame", "postgame"])
    ap.add_argument("--force", action="store_true",
                    help="skip the pre-flight budget check (not recommended)")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_draftkings4.py --mode ...",
              file=sys.stderr)
        return 2

    key = load_key()

    if not DB.exists():
        print(f"ERROR: {DB} not found.", file=sys.stderr)
        return 2

    con = duckdb.connect(str(DB), read_only=True)

    if args.mode == "weekly":
        # One call total: fetch the NFL leagues list, log that this week's
        # games are visible on DraftKings. Does NOT pull per-game markets --
        # that's deliberately deferred to pregame/postgame to not burn budget
        # on lines that will change before kickoff anyway.
        if not args.force and not check_budget_before(1):
            con.close()
            return 1
        log("mode=weekly -- 1 call: confirming this week's NFL slate is live on DK")
        body, _ = api_get("american-football/leagues?page=1&limit=10", key)
        nfl = next((lg for lg in body.get("leagues", []) if lg["name"] == "NFL"), None)
        n_events = len(nfl.get("events", [])) if nfl else 0
        log(f"DraftKings currently lists {n_events} NFL events.")
        _save_bronze("weekly", body)
        con.close()
        return 0

    # pregame / postgame: need this week's schedule + played status from OUR
    # lake (source of truth for kickoff time), then one DK call per matching game.
    today = con.execute(
        "SELECT CAST(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago' AS DATE)"
    ).fetchone()[0]
    current_week = con.execute(
        "SELECT week FROM silver.nfl_schedule WHERE game_date <= ? "
        "ORDER BY game_date DESC LIMIT 1", [today]
    ).fetchone()
    week = current_week[0] if current_week else 1

    if args.mode == "pregame":
        games = con.execute(
            "SELECT game_id, away_team, home_team FROM silver.nfl_schedule "
            "WHERE week = ? AND (home_score IS NULL)", [week]
        ).fetchall()
    else:
        games = con.execute(
            "SELECT game_id, away_team, home_team FROM silver.nfl_schedule "
            "WHERE week = ? AND home_score IS NOT NULL", [week]
        ).fetchall()

    n = len(games)
    log(f"mode={args.mode}  week={week}  {n} matching game(s) in our lake")
    if n == 0:
        log("Nothing to pull -- correct, not an error (e.g. no games finished yet).")
        con.close()
        return 0

    if not args.force and not check_budget_before(n):
        con.close()
        return 1

    # We don't yet have a lake-side mapping from our game_id to DK's eventId --
    # that bridge doesn't exist yet (same category of gap as the ESPN/nflverse
    # id mismatch found earlier). Fetch DK's current NFL event list once and
    # match by team names, which IS reliable (confirmed team naming is
    # consistent, e.g. "CAR Panthers", "CLE Browns").
    body, _ = api_get("american-football/leagues?page=1&limit=10", key)
    nfl = next((lg for lg in body.get("leagues", []) if lg["name"] == "NFL"), None)
    dk_events = nfl.get("events", []) if nfl else []

    def dk_match(away: str, home: str) -> dict | None:
        for e in dk_events:
            if away in e.get("away", "") and home in e.get("home", ""):
                return e
        return None

    fetched = skipped = 0
    for game_id, away, home in games:
        ev = dk_match(away, home)
        if not ev:
            log(f"  SKIP {away} @ {home} -- no DK event match found (team-name mismatch?)")
            skipped += 1
            continue
        detail, _ = api_get(f"american-football/events/{ev['eventId']}", key)
        _save_bronze(f"{args.mode}_{game_id}", detail)
        n_markets = len(detail.get("data", {}).get("markets", []))
        log(f"  {away} @ {home} -> {n_markets} markets pulled")
        fetched += 1

    log(f"done: {fetched} pulled, {skipped} skipped (no match)")
    con.close()
    return 0


def _save_bronze(name: str, body: dict) -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BRONZE / f"{stamp}_{name}.json"
    dest.write_text(json.dumps(body))


if __name__ == "__main__":
    raise SystemExit(main())

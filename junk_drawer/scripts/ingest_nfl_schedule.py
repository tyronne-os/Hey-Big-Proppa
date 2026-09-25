#!/usr/bin/env python3
"""
Load the real NFL schedule (nflverse 'schedules' release) -- the backbone the
Match Page's "is there a game today" logic depends on.

Fixes a confirmed gap: silver.nfl_game (from sql/nfl_pfr_schema.sql) has
home_team/away_team/kickoff_utc as NULL for every row. This is a separate,
correctly-populated table rather than patching that one, since other tables
(nfl_td_log, player-week tables) already join on nfl_game.game_id and
shouldn't be disturbed.

Source: https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
Confirmed live 2026-09-25: 272 games for the 2026 season, real dates/times,
game-level odds (spread/total/moneyline) populated for upcoming games too.
temp/wind are ONLY populated for already-played games (recorded conditions,
not a forecast) -- confirmed, not assumed.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_schedule.py
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_schedule.py --season 2026
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import pathlib
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "nflverse"
SCHEMA_FILE = REPO / "sql" / "nfl_schedule_schema.sql"
URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def num(sql_expr: str, sql_type: str) -> str:
    return f"TRY_CAST(NULLIF(NULLIF({sql_expr}, ''), 'NA') AS {sql_type})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026,
                    help="filter to one season (default 2026 -- project scope is "
                         "current season only; pass --season 0 to load all seasons)")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nfl_schedule.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    dest = run_dir / "games.csv"

    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*") if (p / "games.csv").exists())
        if not prior:
            print("ERROR: no prior bronze pull; run without --skip-download",
                  file=sys.stderr)
            return 2
        dest = prior[-1] / "games.csv"
        log(f"reuse   {dest}")
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "frontal-lobe2/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        dest.write_bytes(body)
        log(f"fetched {dest.name} ({len(body):,} bytes, "
            f"sha {hashlib.sha256(body).hexdigest()[:12]})")

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(SCHEMA_FILE.read_text())

    load_all = args.season == 0
    season_filter = "" if load_all else f"AND CAST(season AS INTEGER) = {args.season}"
    con.execute("DELETE FROM silver.nfl_schedule")  # always full reload -- 272 rows, cheap,
    # avoids exactly the leftover-season bug found during this build (a
    # season-scoped DELETE left prior unscoped-load rows for other seasons
    # sitting in the table after a later --season-filtered run).

    con.execute(f"""
        INSERT INTO silver.nfl_schedule
        SELECT
            game_id,
            CAST(season AS INTEGER),
            game_type,
            CAST(week AS INTEGER),
            TRY_CAST(gameday AS DATE),
            weekday,
            gametime,
            away_team, home_team,
            {num('away_score', 'INTEGER')},
            {num('home_score', 'INTEGER')},
            location,
            {num('home_score', 'INTEGER')} - {num('away_score', 'INTEGER')},
            {num('total', 'INTEGER')},
            CASE WHEN overtime IN ('1','TRUE','true') THEN true
                 WHEN overtime IN ('0','FALSE','false','') THEN false ELSE NULL END,
            roof, surface, stadium_id, stadium,
            {num('temp', 'INTEGER')},
            {num('wind', 'INTEGER')},
            {num('spread_line', 'DOUBLE')},
            {num('away_spread_odds', 'INTEGER')},
            {num('home_spread_odds', 'INTEGER')},
            {num('total_line', 'DOUBLE')},
            {num('over_odds', 'INTEGER')},
            {num('under_odds', 'INTEGER')},
            {num('away_moneyline', 'INTEGER')},
            {num('home_moneyline', 'INTEGER')},
            CASE WHEN div_game IN ('1','TRUE','true') THEN true
                 WHEN div_game IN ('0','FALSE','false','') THEN false ELSE NULL END,
            away_qb_name, home_qb_name, away_coach, home_coach, referee,
            '{run_id}'
        FROM read_csv_auto('{dest}', SAMPLE_SIZE=-1, ALL_VARCHAR=TRUE)
        WHERE 1=1 {season_filter}
    """)

    n = con.execute("SELECT count(*) FROM silver.nfl_schedule").fetchone()[0]
    seasons = con.execute(
        "SELECT season, count(*) FROM silver.nfl_schedule GROUP BY 1 ORDER BY 1"
    ).fetchall()
    log(f"loaded {n:,} schedule rows")
    for s, c in seasons:
        log(f"  season {s}: {c} games")

    upcoming = con.execute(
        """SELECT count(*) FROM silver.nfl_schedule
           WHERE game_date >= CURRENT_DATE AND spread_line IS NOT NULL"""
    ).fetchone()[0]
    log(f"upcoming games with a spread line already posted: {upcoming}")

    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

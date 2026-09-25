#!/usr/bin/env python3
"""
Build NFL touchdown scoring logs for ALL 32 teams from one play-by-play pull.

Recreates these two PFR team-page charts without visiting 32 team pages:
    /teams/<abbr>/<season>.htm#all_team_td_log   (touchdowns scored)
    /teams/<abbr>/<season>.htm#all_opp_td_log    (touchdowns allowed)

Both charts are two perspectives on the same touchdown event, so we store one row
per TD play and expose two views (see sql/nfl_td_logs.sql).

Source: nflverse play_by_play_<season>.csv.gz (open data). PFR itself is behind a
Cloudflare bot challenge and its ToS prohibits harvesting -- see docs/PFR_SOURCE_NOTE.md.

Usage:
    python3 scripts/ingest_nfl_td_logs.py                   # 2026
    python3 scripts/ingest_nfl_td_logs.py --season 2026
    python3 scripts/ingest_nfl_td_logs.py --skip-download    # reuse bronze copy
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import pathlib
import shutil
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "nflverse"
SCHEMA_FILES = [REPO / "sql" / "nfl_pfr_schema.sql", REPO / "sql" / "nfl_td_logs.sql"]
PBP_URL = ("https://github.com/nflverse/nflverse-data/releases/download/pbp/"
           "play_by_play_{season}.csv.gz")


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def fetch_pbp(season: int, run_dir: pathlib.Path, skip: bool) -> pathlib.Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    gz = run_dir / f"play_by_play_{season}.csv.gz"
    csv_path = run_dir / f"play_by_play_{season}.csv"
    if skip and csv_path.exists():
        log(f"reuse   {csv_path.name} ({csv_path.stat().st_size:,} bytes)")
        return csv_path
    url = PBP_URL.format(season=season)
    req = urllib.request.Request(url, headers={"User-Agent": "frontal-lobe2/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    gz.write_bytes(body)
    log(f"fetched {gz.name} ({len(body):,} bytes, sha {hashlib.sha256(body).hexdigest()[:12]})")
    with gzip.open(gz, "rb") as fi, csv_path.open("wb") as fo:
        shutil.copyfileobj(fi, fo)
    log(f"expanded -> {csv_path.name} ({csv_path.stat().st_size:,} bytes)")
    return csv_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    season = args.season

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable. Install into a local dir and set PYTHONPATH:\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nfl_td_logs.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    if args.skip_download:
        existing = sorted(p for p in BRONZE.glob("*") if p.is_dir()
                          and (p / f"play_by_play_{season}.csv").exists())
        if not existing:
            return_msg = "no prior bronze pbp found; run without --skip-download first"
            print(f"ERROR: {return_msg}", file=sys.stderr)
            return 2
        run_dir = existing[-1]

    log(f"run_id={run_id}  season={season}")
    csv_path = fetch_pbp(season, run_dir, args.skip_download)

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    for f in SCHEMA_FILES:
        con.execute(f.read_text())
    log(f"schema applied -> {DB}")

    con.execute("DELETE FROM silver.nfl_td_log WHERE season = ?", [season])

    # Derive the log straight from play-by-play. Note on defense_team: on an
    # offensive TD the conceding team is defteam; on a defensive/return TD the
    # scoring team IS the defense, so the conceding side is posteam.
    con.execute(
        """
        INSERT INTO silver.nfl_td_log
        SELECT
            CAST(season AS INTEGER),
            CAST(week AS INTEGER),
            season_type,
            game_id,
            CAST(play_id AS INTEGER),
            TRY_CAST(game_date AS DATE),
            td_team,
            CASE WHEN td_team = posteam THEN defteam ELSE posteam END,
            td_team = posteam,
            td_player_id,
            td_player_name,
            CASE WHEN pass_touchdown   = 1 THEN 'pass'
                 WHEN rush_touchdown   = 1 THEN 'rush'
                 WHEN return_touchdown = 1 THEN 'return'
                 ELSE 'other' END,
            CAST(qtr AS INTEGER),
            CAST(time AS VARCHAR),
            CAST(drive AS INTEGER),
            CAST(yardline_100 AS INTEGER),
            yardline_100 <= 20,
            goal_to_go = 1,
            CAST(down AS INTEGER),
            down = 3,
            passer_player_id,
            passer_player_name,
            CAST(posteam_score_post AS INTEGER),
            CAST(defteam_score_post AS INTEGER),
            "desc",
            ?
        FROM read_csv_auto(?, SAMPLE_SIZE=-1)
        WHERE touchdown = 1 AND td_team IS NOT NULL
        """,
        [run_id, str(csv_path)],
    )

    n = con.execute("SELECT count(*) FROM silver.nfl_td_log WHERE season=?", [season]).fetchone()[0]
    teams = con.execute(
        "SELECT count(DISTINCT scoring_team) FROM silver.nfl_td_log WHERE season=?", [season]
    ).fetchone()[0]
    wks = con.execute(
        "SELECT min(week), max(week) FROM silver.nfl_td_log WHERE season=?", [season]
    ).fetchone()
    log(f"loaded {n:,} TD plays | {teams} teams | weeks {wks[0]}-{wks[1]}")

    breakdown = con.execute(
        """SELECT td_type, count(*) c,
                  sum(CASE WHEN is_red_zone THEN 1 ELSE 0 END) rz,
                  sum(CASE WHEN is_goal_to_go THEN 1 ELSE 0 END) g2g
           FROM silver.nfl_td_log WHERE season=? GROUP BY 1 ORDER BY c DESC""",
        [season],
    ).fetchall()
    for t, c, rz, g2g in breakdown:
        log(f"  {t:7s} {c:4d}  red_zone={rz:4d}  goal_to_go={g2g:4d}")

    con.execute(
        "INSERT INTO bronze.ingestion_runs VALUES (?,?,?,?,?,?,?,?,?)",
        [run_id, "nflverse_pbp", "api", "nfl",
         dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc),
         n, "success", None],
    )
    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

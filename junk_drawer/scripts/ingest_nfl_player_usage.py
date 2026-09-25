#!/usr/bin/env python3
"""
Player usage pond loader -- opportunities (targets + carries) and depth charts.

Builds the two base tables the indicator sits on:
    silver.nfl_target_event          <- nflverse pbp (every targeted pass)
    silver.nfl_depth_chart_snapshot  <- nflverse depth_charts (the coach's
                                        own stated hierarchy, point-in-time)

The pond measures INTRA-TEAM confidence: every share is computed against the
player's own team totals, never league-wide. See sql/nfl_player_usage_schema.sql
for the reasoning and docs/PLAYER_USAGE_INDEX.md for the indicator design.

Both sources are nflverse (CC-BY-4.0, already trusted in this lake). PFR is
never fetched -- 403 behind Cloudflare, and its ToS bars harvesting. See
docs/PFR_SOURCE_NOTE.md.

Set-based and idempotent, like every other loader here: the season's rows are
deleted then re-inserted, so re-running weekly through the season is safe.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py --season 2026
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py --skip-download
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
SCHEMA_FILES = [
    REPO / "sql" / "nfl_pfr_schema.sql",
    REPO / "sql" / "nfl_schedule_schema.sql",
    REPO / "sql" / "nfl_player_usage_schema.sql",
]
BASE = "https://github.com/nflverse/nflverse-data/releases/download"
PBP_URL = BASE + "/pbp/play_by_play_{season}.csv.gz"
DEPTH_URL = BASE + "/depth_charts/depth_charts_{season}.csv"
UA = {"User-Agent": "frontal-lobe2/1.0"}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def fetch(url: str, dest: pathlib.Path, skip: bool) -> pathlib.Path:
    if skip and dest.exists():
        log(f"reuse   {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()
    dest.write_bytes(body)
    log(f"fetched {dest.name} ({len(body):,} bytes, "
        f"sha {hashlib.sha256(body).hexdigest()[:12]})")
    return dest


def fetch_pbp(season: int, run_dir: pathlib.Path, skip: bool) -> pathlib.Path:
    """pbp ships gzipped; expand to plain CSV so read_csv_auto can stream it."""
    csv_path = run_dir / f"play_by_play_{season}.csv"
    if skip and csv_path.exists():
        log(f"reuse   {csv_path.name} ({csv_path.stat().st_size:,} bytes)")
        return csv_path
    gz = fetch(PBP_URL.format(season=season),
               run_dir / f"play_by_play_{season}.csv.gz", skip)
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
        print("ERROR: duckdb not importable. This box has an externally-managed\n"
              "Python (PEP 668). Install locally and set PYTHONPATH:\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*") if p.is_dir()
                       and (p / f"play_by_play_{season}.csv").exists())
        if not prior:
            print("ERROR: no prior bronze pbp pull; run without --skip-download",
                  file=sys.stderr)
            return 2
        run_dir = prior[-1]
    run_dir.mkdir(parents=True, exist_ok=True)

    log(f"run_id={run_id}  season={season}")
    pbp_csv = fetch_pbp(season, run_dir, args.skip_download)
    depth_csv = fetch(DEPTH_URL.format(season=season),
                      run_dir / f"depth_charts_{season}.csv", args.skip_download)

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    for f in SCHEMA_FILES:
        con.execute(f.read_text())
    log(f"schema applied -> {DB}")

    # ---- opportunities: targets + carries --------------------------------
    # An opportunity is a coaching decision to put the ball in a named
    # player's hands. Targets and carries are loaded by the same statement
    # (UNION ALL) so the stress ladder is defined once and applied identically
    # to both -- a WR's 3rd-down target and a RB's 3rd-down carry have to be
    # graded on the same scale or the spine comparison is meaningless.
    #
    # Excluded on purpose: sacks, scrambles, throwaways, spikes, kneels. None
    # has an intended recipient in the data, so none is a decision to trust
    # anyone.
    #
    # THE STRESS LADDER, defined once here:
    #   3 MAX      goal to go | inside the 5 | 4th down | one-score game
    #              inside 5 minutes
    #   2 HIGH     red zone | 3rd down | 2 yards or fewer to go
    #   1 MODERATE 2nd and 7+ | trailing by 9-16
    #   0 NEUTRAL  everything else
    STRESS = """
        CASE
          WHEN goal_to_go = 1 OR yardline_100 <= 5 OR down = 4
               OR (qtr >= 4 AND abs(TRY_CAST(score_differential AS INTEGER)) <= 8
                   AND TRY_CAST(game_seconds_remaining AS INTEGER) <= 300) THEN 3
          WHEN yardline_100 <= 20 OR down = 3
               OR TRY_CAST(ydstogo AS INTEGER) <= 2                        THEN 2
          WHEN (down = 2 AND TRY_CAST(ydstogo AS INTEGER) >= 7)
               OR TRY_CAST(score_differential AS INTEGER) BETWEEN -16 AND -9 THEN 1
          ELSE 0
        END
    """
    TWO_MIN = ("TRY_CAST(half_seconds_remaining AS INTEGER) <= 120")

    con.execute("DELETE FROM silver.nfl_opportunity_event WHERE season = ?", [season])
    con.execute(
        f"""
        INSERT INTO silver.nfl_opportunity_event
        -- targets
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), season_type,
               game_id, CAST(play_id AS INTEGER), 'target',
               posteam, defteam,
               receiver_player_id, receiver_player_name,
               passer_player_id, passer_player_name,
               CAST(yardline_100 AS INTEGER),
               yardline_100 <= 20, yardline_100 <= 10, yardline_100 <= 5,
               goal_to_go = 1,
               TRY_CAST(air_yards AS INTEGER), pass_location, NULL, NULL,
               CAST(down AS INTEGER), TRY_CAST(ydstogo AS INTEGER),
               CAST(qtr AS INTEGER),
               TRY_CAST(game_seconds_remaining AS INTEGER),
               TRY_CAST(score_differential AS INTEGER),
               {STRESS}, ({STRESS}) >= 2, {TWO_MIN},
               false, false,          -- scramble/designed-run: N/A on a target
               complete_pass = 1,
               TRY_CAST(yards_gained AS INTEGER),
               TRY_CAST(yards_after_catch AS INTEGER),
               pass_touchdown = 1, first_down = 1, interception = 1,
               "desc", ?
        FROM read_csv_auto(?, SAMPLE_SIZE=-1)
        WHERE pass_attempt = 1 AND receiver_player_id IS NOT NULL
          AND posteam IS NOT NULL

        UNION ALL
        -- carries
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), season_type,
               game_id, CAST(play_id AS INTEGER), 'rush',
               posteam, defteam,
               rusher_player_id, rusher_player_name,
               NULL, NULL,
               CAST(yardline_100 AS INTEGER),
               yardline_100 <= 20, yardline_100 <= 10, yardline_100 <= 5,
               goal_to_go = 1,
               NULL, NULL, run_location, run_gap,
               CAST(down AS INTEGER), TRY_CAST(ydstogo AS INTEGER),
               CAST(qtr AS INTEGER),
               TRY_CAST(game_seconds_remaining AS INTEGER),
               TRY_CAST(score_differential AS INTEGER),
               {STRESS}, ({STRESS}) >= 2, {TWO_MIN},
               -- A designed run is a called play (sneak, keeper, draw) and
               -- counts as a coaching decision. A scramble is a collapsed
               -- pocket and does not. Flagged, never dropped.
               qb_scramble = 1, COALESCE(qb_scramble, 0) <> 1,
               true,
               TRY_CAST(yards_gained AS INTEGER),
               NULL,
               rush_touchdown = 1, first_down = 1, false,
               "desc", ?
        FROM read_csv_auto(?, SAMPLE_SIZE=-1)
        WHERE rush_attempt = 1 AND rusher_player_id IS NOT NULL
          AND posteam IS NOT NULL
        """,
        [run_id, str(pbp_csv), run_id, str(pbp_csv)],
    )
    n_opp = con.execute("SELECT count(*) FROM silver.nfl_opportunity_event WHERE season=?",
                        [season]).fetchone()[0]
    for t, n, hs, i20, i5 in con.execute(
        """SELECT opportunity_type, count(*), sum(is_high_stress::INT),
                  sum(is_inside_20::INT), sum(is_inside_5::INT)
           FROM silver.nfl_opportunity_event WHERE season=? GROUP BY 1 ORDER BY 1""",
        [season]).fetchall():
        log(f"  {t:7s} {n:6,}  high_stress={hs:5,}  inside20={i20:4,}  inside5={i5:4,}")
    lad = con.execute(
        """SELECT stress_level, count(*) FROM silver.nfl_opportunity_event
           WHERE season=? GROUP BY 1 ORDER BY 1 DESC""", [season]).fetchall()
    log("  stress ladder: " + "  ".join(f"L{l}={c:,}" for l, c in lad))
    wk = con.execute("SELECT count(DISTINCT posteam), min(week), max(week) "
                     "FROM silver.nfl_opportunity_event WHERE season=?",
                     [season]).fetchone()
    log(f"  {n_opp:,} opportunities | {wk[0]} teams | weeks {wk[1]}-{wk[2]}")
    n_tgt = n_opp

    # ---- depth chart snapshots -------------------------------------------
    # dt arrives as ISO-8601 with a literal Z. Cast to TIMESTAMPTZ explicitly
    # so a real instant is stored -- not local time wearing a UTC label, which
    # is the bug this lake already hit once on gold.nfl_prop_line_rotowire.
    con.execute("DELETE FROM silver.nfl_depth_chart_snapshot WHERE ingest_run_id IS NOT NULL")
    con.execute(
        f"""
        INSERT INTO silver.nfl_depth_chart_snapshot
        SELECT DISTINCT ON (dt, team, pos_abb, pos_rank, player_name)
            CAST(dt AS TIMESTAMPTZ), team, pos_grp, pos_abb, pos_name,
            TRY_CAST(pos_slot AS INTEGER), CAST(pos_rank AS INTEGER),
            gsis_id, CAST(espn_id AS VARCHAR), player_name, ?
        FROM read_csv_auto(?, SAMPLE_SIZE=-1)
        WHERE team IS NOT NULL AND pos_abb IS NOT NULL AND pos_rank IS NOT NULL
          AND player_name IS NOT NULL   -- a depth slot with no player named is
                                        -- an unfilled row in the source, not data
        """,
        [run_id, str(depth_csv)],
    )
    d = con.execute(
        """SELECT count(*), count(DISTINCT snapshot_at), count(DISTINCT team),
                  min(snapshot_at), max(snapshot_at)
           FROM silver.nfl_depth_chart_snapshot""").fetchone()
    log(f"depth chart: {d[0]:,} rows | {d[1]} snapshots | {d[2]} teams | "
        f"{d[3]} -> {d[4]}")

    # ---- verification: the joins that actually matter --------------------
    pg = con.execute(
        "SELECT count(*), count(DISTINCT game_id), count(DISTINCT team) "
        "FROM silver.v_nfl_depth_chart_pregame WHERE season=?", [season]).fetchone()
    log(f"point-in-time depth rows: {pg[0]:,} across {pg[1]} games, {pg[2]} teams")

    matched = con.execute(
        """SELECT count(*) FILTER (WHERE depth_rank IS NOT NULL), count(*)
           FROM gold.v_nfl_player_usage_components WHERE season=?""", [season]).fetchone()
    log(f"players with a matched depth rank: {matched[0]:,} / {matched[1]:,}")

    n_idx = con.execute("SELECT count(*) FROM gold.v_nfl_player_usage_index WHERE season=?",
                        [season]).fetchone()[0]
    log(f"indicator rows: {n_idx:,}")

    con.execute("DELETE FROM bronze.ingestion_runs WHERE run_id = ?", [run_id])
    con.execute(
        "INSERT INTO bronze.ingestion_runs VALUES (?,?,?,?,?,?,?,?,?)",
        [run_id, "nflverse_pbp+depth_charts", "api", "nfl",
         dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc),
         n_tgt, "success", None],
    )
    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

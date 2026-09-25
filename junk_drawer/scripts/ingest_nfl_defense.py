#!/usr/bin/env python3
"""
Defense pond loader.

Every stat in this pond except points-by-half is already sitting in
silver.nfl_team_week, silver.nfl_pfr_adv_defense_week, silver.nfl_player_defense_week,
or silver.nfl_schedule -- all of which are loaded by earlier scripts. This
loader's only job is the one thing nflverse does not publish as a team-week
aggregate: points allowed split by half.

Built from the same play_by_play_<season>.csv.gz already pulled for the TD log
and the usage pond -- one more pass over a file already on disk, not a new
download. Derived from scoring plays (touchdown, field goals, extra points,
two-point conversions, safeties), attributed to whichever team was NOT on
offense at the moment of the score (the defense is who allowed it).

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py --season 2026
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py --skip-download
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
    REPO / "sql" / "nfl_defense_schema.sql",
]
PBP_URL = ("https://github.com/nflverse/nflverse-data/releases/download/pbp/"
           "play_by_play_{season}.csv.gz")
UA = {"User-Agent": "frontal-lobe2/1.0"}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def fetch_pbp(season: int, run_dir: pathlib.Path, skip: bool) -> pathlib.Path:
    csv_path = run_dir / f"play_by_play_{season}.csv"
    if skip and csv_path.exists():
        log(f"reuse   {csv_path.name} ({csv_path.stat().st_size:,} bytes)")
        return csv_path
    gz = run_dir / f"play_by_play_{season}.csv.gz"
    req = urllib.request.Request(PBP_URL.format(season=season), headers=UA)
    with urllib.request.urlopen(req, timeout=600) as r:
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
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py",
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

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    for f in SCHEMA_FILES:
        con.execute(f.read_text())
    log(f"schema applied -> {DB}")

    # Points allowed by half: every scoring play (TD, FG, XP, 2pt, safety)
    # attributed to the DEFENSE -- whichever team did not score. qtr 1-2 =
    # half 1; qtr 3-4 and any overtime (qtr >= 5) fold into half 2, which is
    # the correct read for a 2nd-half prop -- OT points are still 2nd-half-or-
    # later defensive failure, not a separate bucket nobody bets on.
    con.execute("DELETE FROM silver.nfl_points_by_half WHERE season = ?", [season])
    con.execute(
        f"""
        INSERT INTO silver.nfl_points_by_half
        WITH scores AS (
            SELECT season, week, game_id, qtr, posteam, defteam,
                   CASE WHEN touchdown = 1 AND td_team = posteam THEN 6
                        WHEN touchdown = 1 AND td_team = defteam THEN 6
                        ELSE 0 END
                   + CASE WHEN field_goal_result = 'made' THEN 3 ELSE 0 END
                   + CASE WHEN extra_point_result = 'good' THEN 1 ELSE 0 END
                   + CASE WHEN two_point_conv_result = 'success' THEN 2 ELSE 0 END
                   + CASE WHEN safety = 1 THEN 2 ELSE 0 END          AS pts,
                   -- who actually gets credit: normally the offense (posteam).
                   -- On a defensive/return TD (td_team = defteam) or a safety,
                   -- the team ON DEFENSE at the snap is the one who scored, and
                   -- the offense (posteam) is who ALLOWED it.
                   CASE WHEN (touchdown = 1 AND td_team = defteam) OR safety = 1
                        THEN posteam ELSE defteam END                AS conceding_team,
                   CASE WHEN (touchdown = 1 AND td_team = defteam) OR safety = 1
                        THEN defteam ELSE posteam END                AS scoring_team
            FROM read_csv_auto(?, SAMPLE_SIZE=-1)
            WHERE season = {season}
              AND (touchdown = 1 OR field_goal_result = 'made'
                   OR extra_point_result = 'good' OR two_point_conv_result = 'success'
                   OR safety = 1)
              AND posteam IS NOT NULL AND defteam IS NOT NULL
        )
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), game_id,
               conceding_team, scoring_team,
               CASE WHEN CAST(qtr AS INTEGER) <= 2 THEN 1 ELSE 2 END,
               sum(pts), ?
        FROM scores
        WHERE pts > 0
        GROUP BY season, week, game_id, conceding_team, scoring_team,
                 CASE WHEN CAST(qtr AS INTEGER) <= 2 THEN 1 ELSE 2 END
        """,
        [str(pbp_csv), run_id],
    )
    n = con.execute("SELECT count(*) FROM silver.nfl_points_by_half WHERE season=?",
                    [season]).fetchone()[0]
    h1, h2 = con.execute(
        """SELECT sum(points_allowed) FILTER (WHERE half=1),
                  sum(points_allowed) FILTER (WHERE half=2)
           FROM silver.nfl_points_by_half WHERE season=?""", [season]).fetchone()
    log(f"points_by_half: {n:,} rows | total pts 1st-half={h1} 2nd-half={h2}")

    # sanity check: total points allowed here should equal schedule totals
    # (within rounding for any pick-six/return that shifts scoring_team) --
    # verify rather than assume.
    check = con.execute(
        f"""
        WITH ours AS (
            SELECT team, sum(points_allowed) AS pts FROM silver.nfl_points_by_half
            WHERE season={season} GROUP BY team
        ), theirs AS (
            SELECT home_team AS team, sum(away_score) AS pts FROM silver.nfl_schedule
            WHERE season={season} AND home_score IS NOT NULL GROUP BY home_team
            UNION ALL
            SELECT away_team, sum(home_score) FROM silver.nfl_schedule
            WHERE season={season} AND home_score IS NOT NULL GROUP BY away_team
        ), theirs_agg AS (SELECT team, sum(pts) AS pts FROM theirs GROUP BY team)
        SELECT count(*) FROM ours o JOIN theirs_agg t ON t.team=o.team
        WHERE abs(o.pts - t.pts) > 6
        """).fetchone()[0]
    if check:
        log(f"  WARNING: {check} teams have a points-by-half total that "
            f"disagrees with the schedule by more than 6 points -- likely a "
            f"defensive/return TD misattribution. Inspect before trusting "
            f"points_allowed_2nd_half for those teams.")
    else:
        log("  verified: points-by-half totals agree with schedule final scores")

    n_ib = con.execute("SELECT count(*) FROM gold.v_nfl_defense_ib_score WHERE season=?",
                       [season]).fetchone()[0]
    log(f"IB score rows: {n_ib} teams")

    con.execute("DELETE FROM bronze.ingestion_runs WHERE run_id = ?", [run_id])
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

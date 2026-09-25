#!/usr/bin/env python3
"""
Load NFL current-season stats into the PFR-style schema (players + teams).

Covers the seven PFR chart families the project targets:
    passing | rushing | receiving | scrimmage | defense | scoring | kicking
plus returns and PFR's advanced pass/rush/rec/def tables.

Source: nflverse open data. NOT scraped from Pro-Football-Reference -- PFR sits
behind a Cloudflare bot challenge and its ToS prohibits harvesting. nflverse
republishes the same stats, including a mirror of PFR's advanced tables.
See docs/PFR_SOURCE_NOTE.md.

All loads are set-based (DuckDB reads the CSV directly) and idempotent: the
season's rows are deleted then re-inserted, so re-running mid-season is safe.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py --season 2026
    PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py --skip-download
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
SCHEMA_FILES = [REPO / "sql" / "nfl_pfr_schema.sql", REPO / "sql" / "nfl_td_logs.sql"]
BASE = "https://github.com/nflverse/nflverse-data/releases/download"

FEEDS = {
    "player_week": "stats_player/stats_player_week_{season}.csv",
    "team_week": "stats_team/stats_team_week_{season}.csv",
    "adv_pass": "pfr_advstats/advstats_week_pass_{season}.csv",
    "adv_rush": "pfr_advstats/advstats_week_rush_{season}.csv",
    "adv_rec": "pfr_advstats/advstats_week_rec_{season}.csv",
    "adv_def": "pfr_advstats/advstats_week_def_{season}.csv",
}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def download(season: int, run_dir: pathlib.Path, skip: bool) -> dict[str, pathlib.Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, pathlib.Path] = {}
    for key, tmpl in FEEDS.items():
        rel = tmpl.format(season=season)
        dest = run_dir / pathlib.PurePosixPath(rel).name
        out[key] = dest
        if skip and dest.exists():
            log(f"reuse   {dest.name} ({dest.stat().st_size:,} bytes)")
            continue
        req = urllib.request.Request(f"{BASE}/{rel}",
                                     headers={"User-Agent": "frontal-lobe2/1.0"})
        with urllib.request.urlopen(req, timeout=180) as r:
            body = r.read()
        dest.write_bytes(body)
        log(f"fetched {dest.name} ({len(body):,} bytes, "
            f"sha {hashlib.sha256(body).hexdigest()[:12]})")
    return out


def col(name: str, cast: str = "INTEGER") -> str:
    """Safe numeric projection: nflverse writes '' and 'NA' for missing."""
    return f"TRY_CAST(NULLIF(NULLIF(CAST({name} AS VARCHAR),''),'NA') AS {cast})"


# key columns shared by every player table
PKEY = """CAST(season AS INTEGER), CAST(week AS INTEGER),
          COALESCE(season_type,'REG'), game_id, player_id, team, opponent_team"""

# (table, [ (source_col, sql_type) ]) -- order matches the schema definition
PLAYER_LOADS: list[tuple[str, list[tuple[str, str]]]] = [
    ("silver.nfl_player_passing_week", [
        ("completions", "INTEGER"), ("attempts", "INTEGER"),
        ("passing_yards", "INTEGER"), ("passing_tds", "INTEGER"),
        ("passing_interceptions", "INTEGER"), ("sacks_suffered", "DOUBLE"),
        ("sack_yards_lost", "INTEGER"), ("sack_fumbles", "INTEGER"),
        ("sack_fumbles_lost", "INTEGER"), ("passing_air_yards", "INTEGER"),
        ("passing_yards_after_catch", "DOUBLE"), ("passing_first_downs", "INTEGER"),
        ("passing_epa", "DOUBLE"), ("passing_cpoe", "DOUBLE"),
        ("passing_2pt_conversions", "INTEGER"), ("pacr", "DOUBLE"),
        ("passing_10", "INTEGER"), ("passing_16", "INTEGER"),
        ("passing_20", "INTEGER"), ("passing_40", "INTEGER"),
    ]),
    ("silver.nfl_player_rushing_week", [
        ("carries", "INTEGER"), ("rushing_yards", "INTEGER"),
        ("rushing_tds", "INTEGER"), ("rushing_fumbles", "INTEGER"),
        ("rushing_fumbles_lost", "INTEGER"), ("rushing_first_downs", "INTEGER"),
        ("rushing_epa", "DOUBLE"), ("rushing_2pt_conversions", "INTEGER"),
        ("rushing_10", "INTEGER"), ("rushing_12", "INTEGER"),
        ("rushing_20", "INTEGER"), ("rushing_40", "INTEGER"),
    ]),
    ("silver.nfl_player_receiving_week", [
        ("receptions", "INTEGER"), ("targets", "INTEGER"),
        ("receiving_yards", "INTEGER"), ("receiving_tds", "INTEGER"),
        ("receiving_fumbles", "INTEGER"), ("receiving_fumbles_lost", "INTEGER"),
        ("receiving_air_yards", "INTEGER"), ("receiving_yards_after_catch", "DOUBLE"),
        ("receiving_first_downs", "INTEGER"), ("receiving_epa", "DOUBLE"),
        ("receiving_2pt_conversions", "INTEGER"), ("receiving_10", "INTEGER"),
        ("receiving_16", "INTEGER"), ("receiving_20", "INTEGER"),
        ("receiving_40", "INTEGER"), ("racr", "DOUBLE"),
        ("target_share", "DOUBLE"), ("air_yards_share", "DOUBLE"), ("wopr", "DOUBLE"),
    ]),
    ("silver.nfl_player_defense_week", [
        ("def_tackles_solo", "INTEGER"), ("def_tackles_with_assist", "INTEGER"),
        ("def_tackle_assists", "INTEGER"), ("def_tackles_for_loss", "INTEGER"),
        ("def_tackles_for_loss_yards", "DOUBLE"), ("def_fumbles_forced", "INTEGER"),
        ("def_sacks", "DOUBLE"), ("def_sack_yards", "DOUBLE"),
        ("def_qb_hits", "INTEGER"), ("def_interceptions", "INTEGER"),
        ("def_interception_yards", "INTEGER"), ("def_pass_defended", "INTEGER"),
        ("def_tds", "INTEGER"), ("def_fumbles", "INTEGER"),
        ("def_safeties", "INTEGER"), ("def_punt_blocks", "INTEGER"),
        ("def_pat_blocks", "INTEGER"), ("def_fg_blocks", "INTEGER"),
        ("def_2pt_atts", "INTEGER"), ("def_2pt_made", "INTEGER"),
    ]),
    ("silver.nfl_player_returns_week", [
        ("punt_returns", "INTEGER"), ("punt_return_yards", "INTEGER"),
        ("kickoff_returns", "INTEGER"), ("kickoff_return_yards", "INTEGER"),
        ("special_teams_tds", "INTEGER"),
    ]),
    ("silver.nfl_player_kicking_week", [
        ("fg_made", "INTEGER"), ("fg_att", "INTEGER"), ("fg_missed", "INTEGER"),
        ("fg_blocked", "INTEGER"), ("fg_long", "INTEGER"), ("fg_pct", "DOUBLE"),
        ("fg_made_0_19", "INTEGER"), ("fg_made_20_29", "INTEGER"),
        ("fg_made_30_39", "INTEGER"), ("fg_made_40_49", "INTEGER"),
        ("fg_made_50_59", "INTEGER"), ("fg_made_60_", "INTEGER"),
        ("fg_missed_0_19", "INTEGER"), ("fg_missed_20_29", "INTEGER"),
        ("fg_missed_30_39", "INTEGER"), ("fg_missed_40_49", "INTEGER"),
        ("fg_missed_50_59", "INTEGER"), ("fg_missed_60_", "INTEGER"),
        ("fg_made_distance", "DOUBLE"), ("fg_missed_distance", "DOUBLE"),
        ("fg_blocked_distance", "DOUBLE"),
        ("gwfg_made", "INTEGER"), ("gwfg_att", "INTEGER"),
        ("gwfg_missed", "INTEGER"), ("gwfg_blocked", "INTEGER"),
        ("gwfg_distance", "DOUBLE"),
        ("pat_made", "INTEGER"), ("pat_att", "INTEGER"), ("pat_missed", "INTEGER"),
        ("pat_blocked", "INTEGER"), ("pat_pct", "DOUBLE"),
        ("pt_att", "INTEGER"), ("pt_yards", "INTEGER"), ("pt_net_yards", "INTEGER"),
        ("pt_long", "INTEGER"), ("pt_blocked", "INTEGER"),
        ("pt_inside_20", "INTEGER"), ("pt_out_of_bounds", "INTEGER"),
        ("pt_downed", "INTEGER"), ("pt_touchback", "INTEGER"),
        ("pt_fair_caught", "INTEGER"), ("pt_returned", "INTEGER"),
        ("pt_return_yards", "INTEGER"),
    ]),
]

TEAM_COLS: list[tuple[str, str]] = [
    ("completions", "INTEGER"), ("attempts", "INTEGER"), ("passing_yards", "INTEGER"),
    ("passing_tds", "INTEGER"), ("passing_interceptions", "INTEGER"),
    ("sacks_suffered", "DOUBLE"), ("sack_yards_lost", "INTEGER"),
    ("passing_air_yards", "INTEGER"), ("passing_yards_after_catch", "DOUBLE"),
    ("passing_first_downs", "INTEGER"), ("passing_epa", "DOUBLE"),
    ("passing_cpoe", "DOUBLE"),
    ("carries", "INTEGER"), ("rushing_yards", "INTEGER"), ("rushing_tds", "INTEGER"),
    ("rushing_first_downs", "INTEGER"), ("rushing_epa", "DOUBLE"),
    ("receptions", "INTEGER"), ("targets", "INTEGER"), ("receiving_yards", "INTEGER"),
    ("receiving_tds", "INTEGER"), ("receiving_air_yards", "INTEGER"),
    ("receiving_yards_after_catch", "DOUBLE"), ("receiving_first_downs", "INTEGER"),
    ("receiving_epa", "DOUBLE"),
    ("def_tackles_solo", "INTEGER"), ("def_sacks", "DOUBLE"),
    ("def_sack_yards", "DOUBLE"), ("def_qb_hits", "INTEGER"),
    ("def_interceptions", "INTEGER"), ("def_pass_defended", "INTEGER"),
    ("def_tds", "INTEGER"), ("def_safeties", "INTEGER"),
    ("def_fumbles_forced", "INTEGER"), ("def_tackles_for_loss", "INTEGER"),
    ("special_teams_tds", "INTEGER"), ("fumble_recovery_tds", "INTEGER"),
    ("fg_made", "INTEGER"), ("fg_att", "INTEGER"), ("fg_long", "INTEGER"),
    ("fg_pct", "DOUBLE"), ("pat_made", "INTEGER"), ("pat_att", "INTEGER"),
    ("pat_pct", "DOUBLE"),
    ("pt_att", "INTEGER"), ("pt_yards", "INTEGER"), ("pt_net_yards", "INTEGER"),
    ("pt_inside_20", "INTEGER"),
    ("punt_returns", "INTEGER"), ("punt_return_yards", "INTEGER"),
    ("kickoff_returns", "INTEGER"), ("kickoff_return_yards", "INTEGER"),
    ("penalties", "INTEGER"), ("penalty_yards", "INTEGER"),
    ("fumbles_total", "INTEGER"), ("fumbles_lost_total", "INTEGER"),
    ("timeouts", "INTEGER"),
]

ADV_LOADS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("silver.nfl_pfr_adv_passing_week", "adv_pass", [
        ("passing_drops", "INTEGER"), ("passing_drop_pct", "DOUBLE"),
        ("passing_bad_throws", "INTEGER"), ("passing_bad_throw_pct", "DOUBLE"),
        ("times_sacked", "INTEGER"), ("times_blitzed", "INTEGER"),
        ("times_hurried", "INTEGER"), ("times_hit", "INTEGER"),
        ("times_pressured", "INTEGER"), ("times_pressured_pct", "DOUBLE"),
    ]),
    ("silver.nfl_pfr_adv_rushing_week", "adv_rush", [
        ("carries", "INTEGER"), ("rushing_yards_before_contact", "DOUBLE"),
        ("rushing_yards_before_contact_avg", "DOUBLE"),
        ("rushing_yards_after_contact", "DOUBLE"),
        ("rushing_yards_after_contact_avg", "DOUBLE"),
        ("rushing_broken_tackles", "INTEGER"), ("receiving_broken_tackles", "INTEGER"),
    ]),
    ("silver.nfl_pfr_adv_receiving_week", "adv_rec", [
        ("rushing_broken_tackles", "INTEGER"), ("receiving_broken_tackles", "INTEGER"),
        ("receiving_drop", "INTEGER"), ("receiving_drop_pct", "DOUBLE"),
        ("receiving_int", "INTEGER"), ("receiving_rat", "DOUBLE"),
    ]),
    ("silver.nfl_pfr_adv_defense_week", "adv_def", [
        ("def_ints", "INTEGER"), ("def_targets", "INTEGER"),
        ("def_completions_allowed", "INTEGER"), ("def_completion_pct", "DOUBLE"),
        ("def_yards_allowed", "INTEGER"), ("def_yards_allowed_per_cmp", "DOUBLE"),
        ("def_yards_allowed_per_tgt", "DOUBLE"),
        ("def_receiving_td_allowed", "INTEGER"),
        ("def_passer_rating_allowed", "DOUBLE"), ("def_adot", "DOUBLE"),
        ("def_air_yards_completed", "INTEGER"), ("def_yards_after_catch", "DOUBLE"),
        ("def_times_blitzed", "INTEGER"), ("def_times_hurried", "INTEGER"),
        ("def_times_hitqb", "INTEGER"), ("def_sacks", "DOUBLE"),
        ("def_pressures", "INTEGER"), ("def_tackles_combined", "INTEGER"),
        ("def_missed_tackles", "INTEGER"), ("def_missed_tackle_pct", "DOUBLE"),
    ]),
]


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
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*") if p.is_dir()
                       and (p / f"stats_player_week_{season}.csv").exists())
        if not prior:
            print("ERROR: no prior bronze pull found; run without --skip-download",
                  file=sys.stderr)
            return 2
        run_dir = prior[-1]

    log(f"run_id={run_id}  season={season}")
    p = download(season, run_dir, args.skip_download)

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    for f in SCHEMA_FILES:
        con.execute(f.read_text())
    log(f"schema applied -> {DB}")

    pw = str(p["player_week"])
    tw = str(p["team_week"])
    SRC_P = f"read_csv_auto('{pw}', SAMPLE_SIZE=-1)"
    SRC_T = f"read_csv_auto('{tw}', SAMPLE_SIZE=-1)"

    # ---- dimensions -------------------------------------------------------
    con.execute("DELETE FROM silver.nfl_player")
    con.execute(f"""
        INSERT INTO silver.nfl_player
        SELECT DISTINCT ON (player_id)
               player_id, NULL, player_name,
               COALESCE(player_display_name, player_name, player_id),
               position, position_group, headshot_url
        FROM {SRC_P} WHERE player_id IS NOT NULL
    """)
    con.execute("DELETE FROM silver.nfl_game WHERE season = ?", [season])
    con.execute(f"""
        INSERT INTO silver.nfl_game
        SELECT DISTINCT ON (game_id)
               game_id, NULL, CAST(season AS INTEGER), CAST(week AS INTEGER),
               COALESCE(season_type,'REG'), NULL, NULL, NULL
        FROM {SRC_P} WHERE game_id IS NOT NULL
    """)
    np_ = con.execute("SELECT count(*) FROM silver.nfl_player").fetchone()[0]
    ng = con.execute("SELECT count(*) FROM silver.nfl_game WHERE season=?",
                     [season]).fetchone()[0]
    log(f"dimensions: players={np_:,}  games={ng:,}")

    # ---- per-category player tables --------------------------------------
    for table, cols in PLAYER_LOADS:
        con.execute(f"DELETE FROM {table} WHERE season = ?", [season])
        proj = ", ".join(col(c, t) for c, t in cols)
        con.execute(f"""
            INSERT INTO {table}
            SELECT {PKEY}, {proj}, '{run_id}'
            FROM {SRC_P} WHERE player_id IS NOT NULL
        """)
        n = con.execute(f"SELECT count(*) FROM {table} WHERE season=?",
                        [season]).fetchone()[0]
        log(f"  {table:44s} {n:>6,} rows")

    # scrimmage: rushing + receiving combined (PFR presents it as its own chart)
    con.execute("DELETE FROM silver.nfl_player_scrimmage_week WHERE season = ?", [season])
    con.execute(f"""
        INSERT INTO silver.nfl_player_scrimmage_week
        WITH s AS (
            SELECT season, week, COALESCE(season_type,'REG') AS st, game_id, player_id,
                   team, opponent_team,
                   COALESCE({col('carries')},0)                   AS car,
                   COALESCE({col('receptions')},0)                AS rec,
                   COALESCE({col('rushing_yards')},0)             AS ry,
                   COALESCE({col('receiving_yards')},0)           AS recy,
                   COALESCE({col('rushing_tds')},0)               AS rtd,
                   COALESCE({col('receiving_tds')},0)             AS rectd,
                   COALESCE({col('rushing_first_downs')},0)       AS rfd,
                   COALESCE({col('receiving_first_downs')},0)     AS recfd,
                   COALESCE({col('rushing_fumbles')},0)           AS rfum,
                   COALESCE({col('receiving_fumbles')},0)         AS recfum,
                   {col('targets')}                               AS tgt
            FROM {SRC_P} WHERE player_id IS NOT NULL
        )
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), st, game_id, player_id,
               team, opponent_team,
               car + rec                              AS touches,
               ry + recy                              AS scrimmage_yards,
               rtd + rectd                            AS scrimmage_tds,
               CASE WHEN car + rec > 0
                    THEN ROUND((ry + recy) * 1.0 / (car + rec), 4) END,
               rfd + recfd, rfum + recfum,
               car, ry, rtd, rec, tgt, recy, rectd,
               '{run_id}'
        FROM s
    """)
    n = con.execute("SELECT count(*) FROM silver.nfl_player_scrimmage_week WHERE season=?",
                    [season]).fetchone()[0]
    log(f"  {'silver.nfl_player_scrimmage_week':44s} {n:>6,} rows")

    # scoring: every route to points. Passing TDs are thrown, not scored by the
    # passer, so they are reported but excluded from total_tds / total_points.
    con.execute("DELETE FROM silver.nfl_player_scoring_week WHERE season = ?", [season])
    con.execute(f"""
        INSERT INTO silver.nfl_player_scoring_week
        WITH s AS (
            SELECT season, week, COALESCE(season_type,'REG') AS st, game_id, player_id,
                   team, opponent_team,
                   COALESCE({col('passing_tds')},0)                AS ptd,
                   COALESCE({col('rushing_tds')},0)                AS rtd,
                   COALESCE({col('receiving_tds')},0)              AS rectd,
                   COALESCE({col('def_tds')},0)                    AS dtd,
                   COALESCE({col('special_teams_tds')},0)          AS sttd,
                   COALESCE({col('fumble_recovery_tds')},0)        AS frtd,
                   COALESCE({col('pt_return_tds')},0)              AS prtd,
                   COALESCE({col('passing_2pt_conversions')},0)    AS p2,
                   COALESCE({col('rushing_2pt_conversions')},0)    AS r2,
                   COALESCE({col('receiving_2pt_conversions')},0)  AS rec2,
                   COALESCE({col('def_2pt_made')},0)               AS d2,
                   COALESCE({col('pat_made')},0)                   AS pat,
                   COALESCE({col('fg_made')},0)                    AS fg,
                   COALESCE({col('def_safeties')},0)               AS saf,
                   {col('fantasy_points','DOUBLE')}                AS fp,
                   {col('fantasy_points_ppr','DOUBLE')}            AS fppr
            FROM {SRC_P} WHERE player_id IS NOT NULL
        )
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), st, game_id, player_id,
               team, opponent_team,
               ptd, rtd, rectd, dtd, sttd, frtd, prtd,
               rtd + rectd + dtd + sttd + frtd        AS total_tds,
               p2, r2, rec2, d2, pat, fg, saf,
               6*(rtd + rectd + dtd + sttd + frtd) + 2*(p2 + r2 + rec2 + d2)
                 + pat + 3*fg + 2*saf                 AS total_points,
               fp, fppr, '{run_id}'
        FROM s
    """)
    n = con.execute("SELECT count(*) FROM silver.nfl_player_scoring_week WHERE season=?",
                    [season]).fetchone()[0]
    log(f"  {'silver.nfl_player_scoring_week':44s} {n:>6,} rows")

    # ---- team weekly ------------------------------------------------------
    con.execute("DELETE FROM silver.nfl_team_week WHERE season = ?", [season])
    proj = ", ".join(col(c, t) for c, t in TEAM_COLS)
    con.execute(f"""
        INSERT INTO silver.nfl_team_week
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER),
               COALESCE(season_type,'REG'), game_id, team, opponent_team,
               {proj}, '{run_id}'
        FROM {SRC_T}
    """)
    n = con.execute("SELECT count(*) FROM silver.nfl_team_week WHERE season=?",
                    [season]).fetchone()[0]
    log(f"  {'silver.nfl_team_week':44s} {n:>6,} rows")

    # ---- PFR advanced stats ----------------------------------------------
    for table, key, cols in ADV_LOADS:
        src = f"read_csv_auto('{p[key]}', SAMPLE_SIZE=-1)"
        con.execute(f"DELETE FROM {table} WHERE season = ?", [season])
        proj = ", ".join(col(c, t) for c, t in cols)
        con.execute(f"""
            INSERT INTO {table}
            SELECT DISTINCT ON (season, week, pfr_player_id, team)
                   CAST(season AS INTEGER), CAST(week AS INTEGER), game_type,
                   game_id, pfr_game_id, pfr_player_id, pfr_player_name,
                   team, opponent, {proj}, '{run_id}'
            FROM {src} WHERE pfr_player_id IS NOT NULL
        """)
        n = con.execute(f"SELECT count(*) FROM {table} WHERE season=?",
                        [season]).fetchone()[0]
        log(f"  {table:44s} {n:>6,} rows")

    # link PFR ids onto the player dim (advanced feeds key on pfr_player_id)
    con.execute("""
        UPDATE silver.nfl_player AS p
        SET pfr_player_id = m.pfr_player_id
        FROM (SELECT DISTINCT ON (pfr_player_name) pfr_player_name, pfr_player_id
              FROM silver.nfl_pfr_adv_defense_week) AS m
        WHERE p.player_display_name = m.pfr_player_name
          AND p.pfr_player_id IS NULL
    """)
    linked = con.execute(
        "SELECT count(*) FROM silver.nfl_player WHERE pfr_player_id IS NOT NULL"
    ).fetchone()[0]
    log(f"pfr_player_id linked for {linked:,} players")

    con.execute("DELETE FROM bronze.ingestion_runs WHERE run_id = ?", [run_id])
    con.execute(
        "INSERT INTO bronze.ingestion_runs VALUES (?,?,?,?,?,?,?,?,?)",
        [run_id, "nflverse", "api", "nfl",
         dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc),
         None, "success", None],
    )
    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

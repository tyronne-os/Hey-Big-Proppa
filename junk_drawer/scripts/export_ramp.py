#!/usr/bin/env python3
"""
Export the NFL ramp's silver/gold tables to itemized, per-chart CSVs + a manifest.

Loading (ingest_*.py) and exporting are separate steps on purpose: if export
breaks, the database (source of truth) is untouched and can be re-exported once
fixed. See docs/RAMP_ARCHITECTURE.md.

Usage:
    PYTHONPATH=.pylibs python3 scripts/export_ramp.py
"""
from __future__ import annotations

import csv
import datetime as dt
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
OUT = REPO / "lake" / "gold" / "nfl"

# (chart_name, source object, grain, source_name)
CHARTS = [
    ("player_passing_week", "silver.nfl_player_passing_week",
     "one row per player per week", "nflverse"),
    ("player_rushing_week", "silver.nfl_player_rushing_week",
     "one row per player per week", "nflverse"),
    ("player_receiving_week", "silver.nfl_player_receiving_week",
     "one row per player per week", "nflverse"),
    ("player_scrimmage_week", "silver.nfl_player_scrimmage_week",
     "one row per player per week", "nflverse"),
    ("player_defense_week", "silver.nfl_player_defense_week",
     "one row per player per week", "nflverse"),
    ("player_scoring_week", "silver.nfl_player_scoring_week",
     "one row per player per week", "nflverse"),
    ("player_kicking_week", "silver.nfl_player_kicking_week",
     "one row per player per week", "nflverse"),
    ("player_returns_week", "silver.nfl_player_returns_week",
     "one row per player per week", "nflverse"),
    ("pfr_adv_passing_week", "silver.nfl_pfr_adv_passing_week",
     "one row per player per week", "nflverse (PFR mirror)"),
    ("pfr_adv_rushing_week", "silver.nfl_pfr_adv_rushing_week",
     "one row per player per week", "nflverse (PFR mirror)"),
    ("pfr_adv_receiving_week", "silver.nfl_pfr_adv_receiving_week",
     "one row per player per week", "nflverse (PFR mirror)"),
    ("pfr_adv_defense_week", "silver.nfl_pfr_adv_defense_week",
     "one row per player per week", "nflverse (PFR mirror)"),
    ("team_week", "silver.nfl_team_week",
     "one row per team per week", "nflverse"),
    ("td_log", "silver.nfl_td_log",
     "one row per touchdown play", "nflverse (play-by-play)"),
    ("td_team_summary", "silver.v_nfl_td_team_summary",
     "one row per team per season, scored vs allowed", "nflverse (derived)"),
    ("anytime_td_scorers", "silver.v_nfl_anytime_td_scorers",
     "one row per player per season", "nflverse (derived)"),
    ("prop_line_rotowire", "gold.nfl_prop_line_rotowire",
     "one row per player/game/book/market/pull (append-only)", "rotowire"),
    ("prop_best_price", "gold.v_nfl_prop_best_price",
     "one row per player/game/market, best price across tracked books", "rotowire (derived)"),
    ("prop_line_movement", "gold.v_nfl_prop_line_movement",
     "one row per player/market/book with 2+ snapshots", "rotowire (derived)"),
    ("injury_report_official", "silver.nfl_injury_report",
     "one row per player per week (league practice/game report)", "nflverse"),
    ("injury_narrative", "silver.nfl_injury_narrative",
     "one row per player per snapshot (why-it-matters context)", "espn"),
    ("news_article", "silver.nfl_news_article",
     "one row per article (headline + summary)", "espn"),
    ("news_article_tag", "silver.nfl_news_article_tag",
     "one row per article/subject tag (links articles to players/teams)", "espn"),
    ("transaction", "silver.nfl_transaction",
     "one row per roster move", "espn"),
    ("schedule", "silver.nfl_schedule",
     "one row per game, 2026 season", "nflverse"),
    ("match_page_today", "gold.v_match_page_today",
     "one row per matchup happening today (empty on non-game days)", "derived"),
    ("matchup_weather_signal", "gold.v_matchup_weather_signal",
     "one row per game, raw weather signal (no impact scoring)", "nflverse (derived)"),
    ("matchup_game_odds", "gold.v_matchup_game_odds",
     "one row per game with a posted spread/total line", "nflverse (derived)"),
    # --- player usage / situational-confidence pond --------------------------
    # NOTE: silver.nfl_depth_chart_snapshot is deliberately NOT exported. It is
    # 560k rows / 63MB, which is a raw source mirror rather than a chart, and it
    # would blow past GitHub's 50MB file warning on every commit. It lives in
    # the database; depth_chart_pregame below is the resolved, useful slice.
    ("opportunity_event", "silver.nfl_opportunity_event",
     "one row per opportunity (target or carry) with stress level",
     "nflverse (play-by-play)"),
    ("opportunity_spine", "silver.v_nfl_opportunity_spine",
     "one row per player per game -- position-gated opportunity + intra-team share",
     "nflverse (derived)"),
    ("stress_split", "silver.v_nfl_stress_split",
     "one row per player per season -- share when calm vs under stress, and the delta",
     "nflverse (derived)"),
    ("redzone_tiers", "silver.v_nfl_redzone_tiers",
     "one row per player per season -- Inside 20/10/5 tiers, intra-team share",
     "nflverse (derived)"),
    ("opportunity_location_map", "silver.v_nfl_opportunity_location_map",
     "one row per player/side/depth-or-gap -- where the ball actually went",
     "nflverse (derived)"),
    ("depth_chart_pregame", "silver.v_nfl_depth_chart_pregame",
     "one row per game/team/depth slot, latest snapshot before kickoff",
     "nflverse (depth_charts, derived)"),
    ("player_usage_components", "gold.v_nfl_player_usage_components",
     "one row per player per season -- all five layers, facts only, no weighting",
     "nflverse (derived)"),
    ("player_usage", "gold.v_nfl_player_usage_index",
     "one row per player per season -- weighted indicator + role (HEURISTIC, not backtested)",
     "nflverse (derived)"),
    ("player_usage_by_team", "gold.v_nfl_player_usage_by_team",
     "one row per player, ranked within his own team", "nflverse (derived)"),
    ("player_usage_td_correlation", "gold.v_nfl_player_usage_td_correlation",
     "one row per player -- confidence read vs. actual TDs scored (if this, then that also)",
     "nflverse (derived)"),
    # --- defense pond ---------------------------------------------------------
    ("points_by_half", "silver.nfl_points_by_half",
     "one row per team per game per half -- points allowed", "nflverse (play-by-play, derived)"),
    ("team_defense_season", "silver.v_nfl_team_defense_season",
     "one row per team per season -- rankings in defense/sacks/INTs/turnovers, win %",
     "nflverse (derived)"),
    ("individual_sacks", "silver.v_nfl_individual_sacks",
     "one row per defender per season with sacks -- who gets the sacks", "nflverse (derived)"),
    ("individual_interceptions", "silver.v_nfl_individual_interceptions",
     "one row per defender per season with INTs -- who intercepts the ball", "nflverse (derived)"),
    ("defense_ib_score", "gold.v_nfl_defense_ib_score",
     "one row per team per season -- QB-comfort toxicity index, 1-5 category (HEURISTIC)",
     "nflverse (derived)"),
    ("matchup_toxicity", "gold.v_nfl_matchup_toxicity",
     "one row per scheduled game -- each offense's opposing defense toxicity",
     "nflverse (derived)"),
    ("team_ats_current", "silver.v_nfl_team_ats_current",
     "one row per team, last-5/last-10 ATS cover %% as of most recent game", "nflverse (derived, computed not sourced)"),
]

MANIFEST_COLS = ["chart_name", "source_table_or_view", "grain", "row_count",
                  "last_exported_at_utc", "source_name", "status"]


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def main() -> int:
    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/export_ramp.py",
              file=sys.stderr)
        return 2

    if not DB.exists():
        print(f"ERROR: {DB} not found. Run the ingest scripts first.", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)

    manifest = []
    ok = failed = 0
    for chart_name, source, grain, source_name in CHARTS:
        dest = OUT / f"{chart_name}.csv"
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            rel = con.execute(f"SELECT * FROM {source}")
            cols = [d[0] for d in rel.description]
            data = rel.fetchall()
            with dest.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                w.writerows(data)
            status = "ok" if data else "empty"
            manifest.append([chart_name, source, grain, len(data), now,
                             source_name, status])
            log(f"  {chart_name:26s} {len(data):>6,} rows  <- {source}")
            ok += 1
        except Exception as e:  # noqa: BLE001 - one bad chart must not stop the rest
            manifest.append([chart_name, source, grain, 0, now, source_name,
                             f"error: {e}"])
            log(f"  FAILED {chart_name} <- {source}: {e}")
            failed += 1

    index_path = OUT / "_index.csv"
    with index_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(MANIFEST_COLS)
        w.writerows(manifest)

    con.close()
    log(f"done: {ok} charts exported, {failed} failed. Manifest -> {index_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

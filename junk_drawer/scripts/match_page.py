#!/usr/bin/env python3
"""
THE MATCH PAGE -- the lead entry point for this lake and every ramp to come.

Runs the exact hardcoded chain, in order:
    1. what is today (anchored to America/New_York, the NFL's own scheduling tz)
    2. are there any NFL games today (yes/no)
    3. if yes, list the matchups
    4. for each matchup: inactives (proxy), weather signal, game odds, prop odds

No model logic here -- this is deliberately dumb, deterministic SQL, per the
user's explicit request. Impact scoring of any signal below is deferred to a
later "logic engine" phase.

Usage:
    PYTHONPATH=.pylibs python3 scripts/match_page.py              # today
    PYTHONPATH=.pylibs python3 scripts/match_page.py --date 2026-09-27
    PYTHONPATH=.pylibs python3 scripts/match_page.py --json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD; default is today (America/New_York)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/match_page.py",
              file=sys.stderr)
        return 2

    if not DB.exists():
        print(f"ERROR: {DB} not found. Run the ingest scripts first.", file=sys.stderr)
        return 2

    con = duckdb.connect(str(DB), read_only=True)

    # ---- STEP 1: what is today -------------------------------------------
    if args.date:
        target_date = args.date
        today_row = (target_date, None, None)
    else:
        today_row = con.execute("SELECT * FROM gold.v_today").fetchone()
        target_date = str(today_row[0])

    # ---- STEP 2: are there games today (yes/no) --------------------------
    game_count = con.execute(
        "SELECT count(*) FROM silver.nfl_schedule WHERE game_date = ?", [target_date]
    ).fetchone()[0]
    has_games = game_count > 0

    result = {
        "as_of_date": target_date,
        "has_games_today": has_games,
        "game_count": game_count,
        "matchups": [],
    }

    if not args.json:
        section("STEP 1 -- WHAT IS TODAY")
        print(f"  Date (America/Chicago -- New Orleans, US Central): {target_date}")
        section("STEP 2 -- ARE THERE NFL GAMES TODAY?")
        print(f"  {'YES' if has_games else 'NO'} -- {game_count} game(s)")

    if not has_games:
        if not args.json:
            print("\n  No matchups to report. Chain ends here -- this is a "
                  "correct answer, not an error.")
        else:
            print(json.dumps(result, indent=2, default=str))
        con.close()
        return 0

    # ---- STEP 3: list the matchups ----------------------------------------
    matchups = con.execute(
        """
        SELECT game_id, season, week, game_date, weekday, game_time_local,
               strftime(game_date + CAST(game_time_local AS TIME)
                        - INTERVAL 1 HOUR, '%H:%M') AS game_time_cst,
               away_team, home_team, roof, surface, div_game
        FROM silver.nfl_schedule
        WHERE game_date = ?
        ORDER BY game_time_local
        """,
        [target_date],
    ).fetchall()

    if not args.json:
        section("STEP 3 -- MATCHUPS (times shown in CST, New Orleans)")
        for m in matchups:
            gid, season, week, gdate, wd, gtime_et, gtime_cst, away, home, roof, surface, div = m
            print(f"  {away} @ {home}   {wd} {gtime_cst} CST ({gtime_et} ET)   "
                  f"({roof}/{surface})"
                  f"{'  [division game]' if div else ''}")

    # ---- STEP 4: per-matchup bundle ---------------------------------------
    for m in matchups:
        gid, season, week, gdate, wd, gtime_et, gtime_cst, away, home, roof, surface, div = m
        matchup_bundle = {"game_id": gid, "away_team": away, "home_team": home}

        weather = con.execute(
            "SELECT temp_actual, wind_actual, is_outdoor_venue, "
            "weather_flag_hardcoded_threshold FROM gold.v_matchup_weather_signal "
            "WHERE game_id = ?",
            [gid],
        ).fetchone()

        game_odds = con.execute(
            "SELECT spread_line, away_spread_odds, home_spread_odds, total_line, "
            "over_odds, under_odds, away_moneyline, home_moneyline "
            "FROM gold.v_matchup_game_odds WHERE game_id = ?",
            [gid],
        ).fetchone()

        inactives = con.execute(
            "SELECT team, full_name, position, report_status, report_primary_injury "
            "FROM gold.v_matchup_inactives WHERE game_id = ?",
            [gid],
        ).fetchall()

        prop_odds = con.execute(
            "SELECT player_name, market_slug, line, best_over_book, best_over_price, "
            "best_under_book, best_under_price FROM gold.v_matchup_prop_odds "
            "WHERE game_id = ? LIMIT 10",
            [gid],
        ).fetchall()

        matchup_bundle["weather"] = weather
        matchup_bundle["game_odds"] = game_odds
        matchup_bundle["inactives"] = inactives
        matchup_bundle["prop_odds"] = prop_odds
        result["matchups"].append(matchup_bundle)

        if not args.json:
            section(f"MATCHUP: {away} @ {home}  ({gid})")

            print("  -- WEATHER SIGNAL (raw signal only; impact scoring is a "
                  "later phase) --")
            if weather:
                temp, wind, outdoor, flag = weather
                print(f"     outdoor venue: {outdoor}   recorded temp: {temp or 'n/a'}   "
                      f"recorded wind: {wind or 'n/a'}")
                print(f"     flag: {flag}")

            print("\n  -- GAME ODDS (nflverse schedule feed) --")
            if game_odds:
                sl, aso, hso, tl, oo, uo, aml, hml = game_odds
                print(f"     spread: {sl} (away {aso}, home {hso})   "
                      f"total: {tl} (over {oo}, under {uo})")
                print(f"     moneyline: away {aml}, home {hml}")
            else:
                print("     (no game-level line posted yet for this matchup)")

            print(f"\n  -- INACTIVES / INJURY STATUS (practice-report proxy, "
                  f"NOT the final inactives list) -- {len(inactives)} flagged --")
            for team, name, pos, status, injury in inactives[:12]:
                print(f"     {status or '?':13s} {name:22s} {pos or '':4s} "
                      f"({team}) {injury or ''}")

            print(f"\n  -- PLAYER PROP ODDS (RotoWire, best price tracked "
                  f"books) -- {len(prop_odds)} shown --")
            for name, market, line, ob, op, ub, up in prop_odds:
                line_str = f"{line}" if line is not None else "ML"
                print(f"     {name:22s} {market:12s} {line_str:8} "
                      f"Over {op} ({ob})  Under {up} ({ub})")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n{'=' * 78}\nEND OF MATCH PAGE -- built entirely from the lake\n")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

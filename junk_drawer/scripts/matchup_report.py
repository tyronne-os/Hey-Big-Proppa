#!/usr/bin/env python3
"""
Assemble a full matchup report bundle for two teams from the lake alone --
injuries (official + narrative), current news, transactions, recent team form,
and involved players' prop lines. This is the "could a beat writer file a
story right now" proof: no browser tab, no live lookup, just the lake.

Usage:
    PYTHONPATH=.pylibs python3 scripts/matchup_report.py BUF NE
    PYTHONPATH=.pylibs python3 scripts/matchup_report.py BUF NE --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def fetch_team_bundle(con, team: str) -> dict:
    # Use the latest week that actually has a report_status populated, not just
    # the latest week number -- the current week's Wed/Thu practice report can
    # exist before Friday's status designations are posted, which would
    # otherwise silently show blank statuses instead of real ones.
    latest_season, latest_week = con.execute(
        """
        SELECT season, week FROM silver.nfl_injury_report
        WHERE report_status IS NOT NULL
        ORDER BY season DESC, week DESC LIMIT 1
        """
    ).fetchone()

    official_injuries = con.execute(
        """
        SELECT full_name, position, report_status, report_primary_injury,
               practice_status
        FROM silver.nfl_injury_report
        WHERE team = ? AND season = ? AND week = ?
        ORDER BY CASE report_status WHEN 'Out' THEN 0 WHEN 'Doubtful' THEN 1
                                     WHEN 'Questionable' THEN 2 ELSE 3 END,
                 full_name
        """,
        [team, latest_season, latest_week],
    ).fetchall()

    narrative_injuries = con.execute(
        """
        SELECT player_name, status, injury_type, return_date, long_comment
        FROM silver.nfl_injury_narrative
        WHERE team = ?
          AND fetched_at_utc = (SELECT max(fetched_at_utc) FROM silver.nfl_injury_narrative)
        ORDER BY CASE status WHEN 'Out' THEN 0 WHEN 'Doubtful' THEN 1
                              WHEN 'Questionable' THEN 2 ELSE 3 END
        """,
        [team],
    ).fetchall()

    news = con.execute(
        """
        SELECT DISTINCT a.headline, a.description, a.published_at
        FROM silver.nfl_news_article a
        JOIN silver.nfl_news_article_tag t ON t.espn_article_id = a.espn_article_id
        WHERE t.team = ?
        ORDER BY a.published_at DESC
        LIMIT 8
        """,
        [team],
    ).fetchall()

    transactions = con.execute(
        """
        SELECT description, transaction_date
        FROM silver.nfl_transaction
        WHERE team = ?
        ORDER BY transaction_date DESC
        LIMIT 5
        """,
        [team],
    ).fetchall()

    recent_form = con.execute(
        """
        SELECT week, passing_yards, passing_tds, rushing_yards, rushing_tds,
               receiving_yards, receiving_tds, def_sacks, def_interceptions
        FROM silver.nfl_team_week
        WHERE team = ?
        ORDER BY week DESC
        LIMIT 3
        """,
        [team],
    ).fetchall()

    top_props = con.execute(
        """
        SELECT player_name, market_slug, line, best_over_book, best_over_price,
               best_under_book, best_under_price, best_moneyline_book,
               best_moneyline_price
        FROM gold.v_nfl_prop_best_price
        WHERE player_name IN (
            SELECT DISTINCT player_name FROM gold.nfl_prop_line_rotowire
            WHERE team = ?
        )
        ORDER BY player_name, market_slug
        LIMIT 15
        """,
        [team],
    ).fetchall()

    return {
        "team": team,
        "as_of_season": latest_season,
        "as_of_week": latest_week,
        "official_injuries": official_injuries,
        "narrative_injuries": narrative_injuries,
        "news": news,
        "transactions": transactions,
        "recent_form": recent_form,
        "top_props": top_props,
    }


def print_bundle(bundle: dict) -> None:
    team = bundle["team"]
    section(f"{team} -- OFFICIAL INJURY REPORT (last week with a posted status: "
            f"season {bundle['as_of_season']}, week {bundle['as_of_week']})")
    if not bundle["official_injuries"]:
        print("  (no injury-report entries)")
    for name, pos, status, primary, practice in bundle["official_injuries"]:
        print(f"  {status or '?':13s} {name:22s} {pos or '':4s} "
              f"{primary or '':18s} practice: {practice or 'n/a'}")

    section(f"{team} -- INJURY CONTEXT (why it matters)")
    if not bundle["narrative_injuries"]:
        print("  (no narrative injury data)")
    for name, status, itype, ret, comment in bundle["narrative_injuries"]:
        print(f"  * {name} ({status}, {itype}) -- return: {ret or 'TBD'}")
        if comment:
            print(f"    {comment}")

    section(f"{team} -- RECENT NEWS")
    if not bundle["news"]:
        print("  (no recent articles)")
    for headline, desc, pub in bundle["news"]:
        print(f"  [{pub}] {headline}")

    section(f"{team} -- TRANSACTIONS")
    if not bundle["transactions"]:
        print("  (no recent transactions)")
    for desc, tdate in bundle["transactions"]:
        print(f"  [{tdate}] {desc}")

    section(f"{team} -- RECENT TEAM FORM (last 3 weeks)")
    if not bundle["recent_form"]:
        print("  (no team-week data)")
    for row in bundle["recent_form"]:
        wk, pyd, ptd, ryd, rtd, recyd, rectd, sacks, ints = row
        print(f"  Wk{wk}: pass {pyd}yd/{ptd}TD  rush {ryd}yd/{rtd}TD  "
              f"rec {recyd}yd/{rectd}TD  def: {sacks} sacks, {ints} INT")

    section(f"{team} -- KEY PLAYER PROP LINES (best price, tracked books)")
    if not bundle["top_props"]:
        print("  (no prop lines found for this team's players)")
    for name, market, line, ob, op, ub, up, mb, mp in bundle["top_props"]:
        if line is not None:
            print(f"  {name:22s} {market:12s} {line:<8} "
                  f"Over {op} ({ob})  Under {up} ({ub})")
        else:
            print(f"  {name:22s} {market:12s} {'ML':8s} "
                  f"Best price {mp} ({mb})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("team_a")
    ap.add_argument("team_b")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/matchup_report.py TEAM_A TEAM_B",
              file=sys.stderr)
        return 2

    if not DB.exists():
        print(f"ERROR: {DB} not found. Run the ingest scripts first.", file=sys.stderr)
        return 2

    con = duckdb.connect(str(DB), read_only=True)
    a = fetch_team_bundle(con, args.team_a.upper())
    b = fetch_team_bundle(con, args.team_b.upper())
    con.close()

    if args.json:
        print(json.dumps({"team_a": a, "team_b": b}, default=str, indent=2))
        return 0

    print(f"\n{'#' * 70}")
    print(f"#  MATCHUP REPORT: {args.team_a.upper()} @ {args.team_b.upper()}")
    print(f"{'#' * 70}")
    print_bundle(a)
    print_bundle(b)
    print(f"\n{'=' * 70}\nEND OF BUNDLE -- built entirely from the lake, no live lookups\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

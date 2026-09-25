#!/usr/bin/env python3
"""
Pull NFL player prop lines from RotoWire's own first-party betting tables.

Source: https://www.rotowire.com/betting/nfl/player-props.php
Confirmed 2026-09-25:
  - robots.txt allows /betting/ (only /users/login.php and /account/ disallowed)
  - the real lines are embedded as JSON directly in the page's static HTML --
    a plain GET returns them in the response body, no JS execution needed
  - `isPaywalled = true` in the page's own JS only gates RotoWire's CSV *export*
    button ("must be a paid subscriber" to download this table"). It does not
    hide the data itself, which is visible to any visitor and is what this
    script reads.
  - The page also embeds an unrelated third-party "Props.Cash" demo widget
    (weather-context feed from a personal Val Town endpoint). That widget is
    NOT used here -- only RotoWire's own tables, identified by the
    `const prop = "<slug>";  ... data: [...]` pattern repeated once per market.

This is a snapshot puller: every run appends a new pull_id snapshot rather than
overwriting, so line movement (open vs. current) is preserved for CLV analysis.
Run it a few times a week; RotoWire updates this page multiple times daily.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_rotowire_props.py
    PYTHONPATH=.pylibs python3 scripts/ingest_rotowire_props.py --skip-download
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "rotowire"
SCHEMA_FILE = REPO / "sql" / "nfl_props_schema.sql"
URL = "https://www.rotowire.com/betting/nfl/player-props.php"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")

# market slug -> the American-odds field suffixes RotoWire uses in the record.
# TD-scorer props are moneyline-only (no line/over/under); everything else has
# a numeric line plus separate Over/Under prices.
TD_SCORER_MARKETS = {"firsttd", "anytd", "lasttd", "twotd", "threetd"}

# User asked to limit scope to books they actually use: FanDuel, DraftKings,
# Caesars (bet365 requested too, but it is NOT present on this RotoWire page --
# confirmed 2026-09-25, only these 10 books appear in the source data at all:
# betr, betrivers, caesars, draftkings, fanduel, fanatics, mgm, hardrock,
# thescore, circasports). If bet365 coverage is needed later it requires a
# different source; flagging rather than silently guessing at a field name.
BOOKS = ["draftkings", "fanduel", "caesars"]


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def fetch_page(run_dir: pathlib.Path, skip: bool) -> str:
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / "player-props.html"
    if skip and dest.exists():
        log(f"reuse   {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest.read_text(encoding="utf-8", errors="ignore")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    dest.write_bytes(body)
    log(f"fetched {dest.name} ({len(body):,} bytes, "
        f"sha {hashlib.sha256(body).hexdigest()[:12]})")
    return body.decode("utf-8", errors="ignore")


def extract_market_blocks(html: str) -> list[tuple[str, str, list[dict]]]:
    """Find every `const prop = "<slug>"; ... propName = "<name>"; ... data: [...]`
    block and return (slug, name, records)."""
    out = []
    for m in re.finditer(
        r'const prop = "(\w+)";\s*\n\s*const propName = "([^"]+)";', html
    ):
        slug, name = m.group(1), m.group(2)
        j = html.find("data: [", m.end())
        if j == -1 or j - m.end() > 20000:
            log(f"  WARN: no data[] found near prop={slug}, skipping")
            continue
        start = j + len("data: ")
        records = _extract_json_array(html, start)
        if records is None:
            log(f"  WARN: could not parse JSON array for prop={slug}, skipping")
            continue
        out.append((slug, name, records))
    return out


def _extract_json_array(text: str, start: int) -> list[dict] | None:
    """Brace/bracket-match a JSON array starting at `start` (a '[') and parse it.
    Needed because the array can be large/nested; a naive regex would break on
    nested braces inside string values."""
    if text[start] != "[":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as e:
                    log(f"  JSON parse error: {e}")
                    return None
    return None


def american(v) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def to_line(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_rotowire_props.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*") if p.is_dir()
                       and (p / "player-props.html").exists())
        if not prior:
            print("ERROR: no prior bronze pull; run without --skip-download",
                  file=sys.stderr)
            return 2
        run_dir = prior[-1]

    log(f"run_id={run_id}")
    html = fetch_page(run_dir, args.skip_download)

    blocks = extract_market_blocks(html)
    log(f"found {len(blocks)} market blocks in page")
    if not blocks:
        print("ERROR: 0 market blocks extracted -- page structure may have "
              "changed. Inspect a fresh HTML pull before assuming the site "
              "is down.", file=sys.stderr)
        return 1

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(SCHEMA_FILE.read_text())

    # Build a team -> earliest-upcoming-kickoff lookup from our own schedule,
    # so every row can be tagged is_pregame at load time instead of guessing
    # later. Confirmed real bug otherwise: two snapshots taken after a game's
    # kickoff produced fake "line movement" that was actually live in-game
    # re-pricing (e.g. Drake London recyds 60.5 -> 174.5 in under 3 hours).
    kickoff_rows = con.execute(
        """
        SELECT team, min(kickoff_utc) FROM (
            SELECT home_team AS team,
                   timezone('America/New_York', game_date + CAST(game_time_local AS TIME))
                   AS kickoff_utc
            FROM silver.nfl_schedule WHERE home_score IS NULL
            UNION ALL
            SELECT away_team,
                   timezone('America/New_York', game_date + CAST(game_time_local AS TIME))
            FROM silver.nfl_schedule WHERE home_score IS NULL
        ) GROUP BY team
        """
    ).fetchall()
    next_kickoff = dict(kickoff_rows)
    log(f"loaded next-kickoff time for {len(next_kickoff)} teams from our own schedule")

    fetched_at = dt.datetime.now(dt.timezone.utc)

    def is_pregame_for(team: str | None) -> bool | None:
        if not team or team not in next_kickoff:
            return None
        return fetched_at < next_kickoff[team]

    rows = []
    for slug, name, records in blocks:
        is_td = slug in TD_SCORER_MARKETS
        n_rows_for_slug = 0
        for rec in records:
            game_id = rec.get("gameID")
            player_id = rec.get("playerID")
            player_name = rec.get("name")
            team = rec.get("team")
            opp = rec.get("opp")
            pregame_flag = is_pregame_for(team)
            for book in BOOKS:
                if f"{book}_{slug}" not in rec:
                    continue
                val = rec.get(f"{book}_{slug}")
                if val is None:
                    continue
                if is_td:
                    rows.append((
                        run_id, fetched_at, game_id, player_id, player_name,
                        team, opp, slug, book, None, None, None,
                        american(val), pregame_flag, "rotowire",
                    ))
                else:
                    rows.append((
                        run_id, fetched_at, game_id, player_id, player_name,
                        team, opp, slug, book, to_line(val),
                        american(rec.get(f"{book}_{slug}Over")),
                        american(rec.get(f"{book}_{slug}Under")),
                        None, pregame_flag, "rotowire",
                    ))
                n_rows_for_slug += 1
        log(f"  {slug:12s} {name:20s} {len(records):4d} players  "
            f"{n_rows_for_slug:5d} book-lines")

    # Bulk-load via a temp CSV + read_csv_auto instead of executemany, which is
    # slow per-call in DuckDB's Python driver even at a few thousand rows.
    con.execute("DELETE FROM gold.nfl_prop_line_rotowire WHERE pull_id = ?", [run_id])
    if rows:
        import csv as _csv
        import tempfile
        cols = ["pull_id", "fetched_at_utc", "game_id", "player_id", "player_name",
                "team", "opponent", "market_slug", "book_slug", "line",
                "over_price_american", "under_price_american",
                "moneyline_american", "is_pregame", "source_name"]
        with tempfile.NamedTemporaryFile(
            "w", newline="", suffix=".csv", delete=False
        ) as tf:
            w = _csv.writer(tf)
            w.writerow(cols)
            w.writerows(rows)
            tmp_path = tf.name
        con.execute(f"""
            INSERT INTO gold.nfl_prop_line_rotowire
            SELECT pull_id, fetched_at_utc::TIMESTAMPTZ, game_id, player_id,
                   player_name, team, opponent, market_slug, book_slug,
                   line::DOUBLE, over_price_american::INTEGER,
                   under_price_american::INTEGER, moneyline_american::INTEGER,
                   CASE is_pregame WHEN 'True' THEN true WHEN 'False' THEN false ELSE NULL END,
                   source_name
            FROM read_csv_auto('{tmp_path}', header=true, ALL_VARCHAR=TRUE)
        """)
        pathlib.Path(tmp_path).unlink(missing_ok=True)
    log(f"loaded {len(rows):,} prop-line rows for pull_id={run_id}")

    total = con.execute("SELECT count(*) FROM gold.nfl_prop_line_rotowire").fetchone()[0]
    players = con.execute(
        "SELECT count(DISTINCT player_id) FROM gold.nfl_prop_line_rotowire"
    ).fetchone()[0]
    log(f"lake totals: {total:,} rows across all pulls, {players:,} distinct players")

    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

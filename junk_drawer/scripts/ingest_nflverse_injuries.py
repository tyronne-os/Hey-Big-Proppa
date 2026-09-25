#!/usr/bin/env python3
"""
Load the official weekly NFL injury report from nflverse.

This is the league-mandated practice/game-status report (Questionable/Doubtful/
Out, practice participation), by team by week. It is NOT the final inactives
list -- that's only released ~90 minutes before kickoff and isn't covered by
this feed. This is the last official signal before that point (usually the
Friday report). See docs/REPORT_ROOM.md.

Source: nflverse-data injuries release, confirmed live 2026-09-25.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_nflverse_injuries.py
    PYTHONPATH=.pylibs python3 scripts/ingest_nflverse_injuries.py --season 2026
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import pathlib
import sys
import tempfile
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "nflverse"
SCHEMA_FILE = REPO / "sql" / "nfl_report_room_schema.sql"
URL_TMPL = ("https://github.com/nflverse/nflverse-data/releases/download/"
            "injuries/injuries_{season}.csv")


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


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
              "  PYTHONPATH=.pylibs python3 scripts/ingest_nflverse_injuries.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / run_id
    dest = run_dir / f"injuries_{season}.csv"

    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*")
                       if (p / f"injuries_{season}.csv").exists())
        if not prior:
            print("ERROR: no prior bronze pull; run without --skip-download",
                  file=sys.stderr)
            return 2
        dest = prior[-1] / f"injuries_{season}.csv"
        log(f"reuse   {dest}")
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL_TMPL.format(season=season),
                                     headers={"User-Agent": "frontal-lobe2/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        dest.write_bytes(body)
        log(f"fetched {dest.name} ({len(body):,} bytes, "
            f"sha {hashlib.sha256(body).hexdigest()[:12]})")

    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(SCHEMA_FILE.read_text())

    con.execute("DELETE FROM silver.nfl_injury_report WHERE season = ?", [season])
    con.execute(f"""
        INSERT INTO silver.nfl_injury_report
        SELECT CAST(season AS INTEGER), CAST(week AS INTEGER), season_type,
               game_type, team, gsis_id, position, full_name,
               report_primary_injury, report_secondary_injury, report_status,
               practice_primary_injury, practice_secondary_injury,
               practice_status, '{run_id}'
        FROM read_csv_auto('{dest}', SAMPLE_SIZE=-1)
        WHERE CAST(season AS INTEGER) = {season}
    """)
    n = con.execute("SELECT count(*) FROM silver.nfl_injury_report WHERE season=?",
                    [season]).fetchone()[0]
    weeks = con.execute(
        "SELECT min(week), max(week) FROM silver.nfl_injury_report WHERE season=?",
        [season],
    ).fetchone()
    by_status = con.execute("""
        SELECT report_status, count(*) FROM silver.nfl_injury_report
        WHERE season=? AND report_status IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
    """, [season]).fetchall()
    log(f"loaded {n:,} injury-report rows, weeks {weeks[0]}-{weeks[1]}")
    for status, cnt in by_status:
        log(f"  {status:14s} {cnt:4d}")

    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

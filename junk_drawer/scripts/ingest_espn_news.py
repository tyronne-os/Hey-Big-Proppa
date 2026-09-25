#!/usr/bin/env python3
"""
Pull ESPN NFL injuries (narrative), news, and transactions into the report room.

Source host: site.web.api.espn.com -- confirmed reachable 2026-09-25. The more
commonly documented host (site.api.espn.com) returned HTTP 403 in this
environment. Same "unofficial/undocumented, can change without notice" caveat
already flagged for ESPN elsewhere in this project applies here too -- this is
just a different, currently-working host, not a sanctioned API.

Endpoints used (all confirmed live with real 2026 data):
    /apis/site/v2/sports/football/nfl/injuries        -- narrative context per player
    /apis/site/v2/sports/football/nfl/news            -- league-wide headlines
    /apis/site/v2/sports/football/nfl/news?team=<abbr> -- team-scoped headlines
    /apis/site/v2/sports/football/nfl/transactions    -- roster moves

Append-only for news/transactions (new articles accumulate); injuries table is
a point-in-time snapshot keyed by (athlete_id, fetched_at) so re-running
captures status changes over the week without losing history.

Usage:
    PYTHONPATH=.pylibs python3 scripts/ingest_espn_news.py
    PYTHONPATH=.pylibs python3 scripts/ingest_espn_news.py --teams buf,kc,phi
    PYTHONPATH=.pylibs python3 scripts/ingest_espn_news.py --skip-download
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
BRONZE = REPO / "lake" / "bronze" / "espn"
SCHEMA_FILE = REPO / "sql" / "nfl_report_room_schema.sql"
BASE = "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

ALL_TEAMS = [
    "ari", "atl", "bal", "buf", "car", "chi", "cin", "cle", "dal", "den",
    "det", "gb", "hou", "ind", "jax", "kc", "lac", "lar", "lv", "mia",
    "min", "ne", "no", "nyg", "nyj", "phi", "pit", "sea", "sf", "tb",
    "ten", "was",
]


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def fetch_json(url: str, dest: pathlib.Path, skip: bool) -> dict | None:
    if skip and dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        log(f"  FAILED {url}: {e}")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return json.loads(body)


def parse_date(s: str | None) -> dt.datetime | None:
    """ESPN timestamps are ISO8601 but sometimes omit seconds
    (e.g. '2026-09-24T02:12Z'), which DuckDB's TIMESTAMP cast rejects.
    Normalize to a real datetime here instead of pushing strings into SQL."""
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    for fmt_try in (s, s.rsplit("+", 1)[0] + "+00:00" if "+" in s else s):
        try:
            return dt.datetime.fromisoformat(fmt_try)
        except ValueError:
            continue
    # last resort: pad missing seconds (YYYY-MM-DDTHH:MM+00:00 -> ...:00+00:00)
    try:
        date_part, offset = s.split("+")
        if date_part.count(":") == 1:
            date_part += ":00"
        return dt.datetime.fromisoformat(date_part + "+" + offset)
    except (ValueError, IndexError):
        log(f"  WARN: could not parse timestamp {s!r}, storing NULL")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", default=",".join(ALL_TEAMS),
                    help="comma-separated ESPN team abbrevs for team-scoped news")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    teams = [t.strip() for t in args.teams.split(",") if t.strip()]

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/ingest_espn_news.py",
              file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = BRONZE / (run_id if not args.skip_download else "latest")
    if args.skip_download:
        prior = sorted(p for p in BRONZE.glob("*") if p.is_dir()
                       and (p / "injuries.json").exists())
        if not prior:
            print("ERROR: no prior bronze pull; run without --skip-download",
                  file=sys.stderr)
            return 2
        run_dir = prior[-1]
    log(f"run_id={run_id}  bronze_dir={run_dir}")

    fetched_at = dt.datetime.now(dt.timezone.utc)

    # ---- injuries (narrative, all 32 teams in one call) --------------------
    inj_data = fetch_json(f"{BASE}/injuries", run_dir / "injuries.json", args.skip_download)
    injury_rows = []
    if inj_data:
        for team_block in inj_data.get("injuries", []):
            team_abbr = None  # ESPN's injuries payload doesn't include abbr directly here
            team_name = team_block.get("displayName")
            for p in team_block.get("injuries", []):
                ath = p.get("athlete", {}) or {}
                details = p.get("details", {}) or {}
                injury_rows.append((
                    str(ath.get("id") or p.get("id") or ""),
                    ath.get("displayName"),
                    (ath.get("team") or {}).get("abbreviation") or team_name,
                    p.get("status"),
                    details.get("type"),
                    details.get("location"),
                    details.get("side"),
                    details.get("returnDate"),
                    p.get("shortComment"),
                    p.get("longComment"),
                    parse_date(p.get("date")),
                    fetched_at,
                    "espn",
                ))
        log(f"injuries: {len(injury_rows)} player rows across "
            f"{len(inj_data.get('injuries', []))} teams")
    else:
        log("injuries: fetch failed, skipping this section")

    # ---- league-wide news ----------------------------------------------------
    news_data = fetch_json(f"{BASE}/news", run_dir / "news_league.json", args.skip_download)
    article_rows: dict[str, tuple] = {}
    tag_rows: list[tuple] = []

    def absorb_articles(payload: dict | None) -> None:
        if not payload:
            return
        for a in payload.get("articles", []):
            aid = str(a.get("id"))
            article_rows[aid] = (
                aid, a.get("headline"), a.get("description"), a.get("type"),
                parse_date(a.get("published")), parse_date(a.get("lastModified")),
                bool(a.get("premium", False)), fetched_at, "espn",
            )
            for cat in a.get("categories", []):
                ctype = cat.get("type")
                if ctype == "athlete":
                    athlete_id = str(cat.get("athleteId"))
                    tag_id = hashlib.sha1(f"{aid}|athlete|{athlete_id}".encode()).hexdigest()
                    tag_rows.append((tag_id, aid, "athlete", athlete_id, None,
                                     cat.get("description")))
                elif ctype == "team":
                    abbr = (cat.get("team") or {}).get("abbreviation")
                    tag_id = hashlib.sha1(f"{aid}|team|{abbr}".encode()).hexdigest()
                    tag_rows.append((tag_id, aid, "team", None, abbr, cat.get("description")))
                elif ctype == "league":
                    tag_id = hashlib.sha1(f"{aid}|league".encode()).hexdigest()
                    tag_rows.append((tag_id, aid, "league", None, None, cat.get("description")))

    absorb_articles(news_data)
    log(f"league news: {len(news_data.get('articles', [])) if news_data else 0} articles")

    for abbr in teams:
        team_news = fetch_json(f"{BASE}/news?team={abbr}",
                               run_dir / f"news_{abbr}.json", args.skip_download)
        absorb_articles(team_news)

    log(f"total distinct articles after team pulls: {len(article_rows)}")

    # ---- transactions ----------------------------------------------------
    txn_data = fetch_json(f"{BASE}/transactions", run_dir / "transactions.json",
                          args.skip_download)
    txn_rows = []
    if txn_data:
        for t in txn_data.get("transactions", []):
            team_abbr = None
            team_obj = t.get("team")
            if isinstance(team_obj, dict):
                team_abbr = team_obj.get("abbreviation")
            txn_rows.append((
                str(t.get("id") or t.get("guid") or hash(json.dumps(t, sort_keys=True))),
                team_abbr,
                t.get("description") or t.get("shortText") or "",
                parse_date(t.get("date")),
                fetched_at,
                "espn",
            ))
        log(f"transactions: {len(txn_rows)} rows")
    else:
        log("transactions: fetch failed, skipping this section")

    # ---- load ----------------------------------------------------
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute(SCHEMA_FILE.read_text())

    if injury_rows:
        con.executemany(
            "INSERT INTO silver.nfl_injury_narrative VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            injury_rows,
        )
    if article_rows:
        con.executemany(
            "INSERT OR REPLACE INTO silver.nfl_news_article VALUES "
            "(?,?,?,?,?,?,?,?,?)",
            list(article_rows.values()),
        )
    if tag_rows:
        con.executemany(
            "INSERT OR REPLACE INTO silver.nfl_news_article_tag VALUES (?,?,?,?,?,?)",
            tag_rows,
        )
    if txn_rows:
        con.executemany(
            "INSERT OR REPLACE INTO silver.nfl_transaction VALUES (?,?,?,?,?,?)",
            txn_rows,
        )

    n_inj = con.execute("SELECT count(*) FROM silver.nfl_injury_narrative").fetchone()[0]
    n_news = con.execute("SELECT count(*) FROM silver.nfl_news_article").fetchone()[0]
    n_tags = con.execute("SELECT count(*) FROM silver.nfl_news_article_tag").fetchone()[0]
    n_txn = con.execute("SELECT count(*) FROM silver.nfl_transaction").fetchone()[0]
    log(f"lake totals: injuries={n_inj:,} news_articles={n_news:,} "
        f"tags={n_tags:,} transactions={n_txn:,}")

    con.close()
    log(f"done -> {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

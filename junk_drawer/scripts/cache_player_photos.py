#!/usr/bin/env python3
"""
One-time download of NFL player headshots for local, offline reuse all season.

Source: headshot_url on silver.nfl_player, itself sourced from nflverse's
stats_player_week feed (an NFL.com/Cloudinary-hosted URL, not scraped -- it's a
field nflverse already publishes). Confirmed present for 1,301 of 1,306 players
in the current load.

Images don't change mid-season, so this runs once, then the loader (or a manual
re-run) only fetches players not already cached -- safe to re-run anytime.

Requests a 200px-wide version (Cloudinary transform `w_200`) instead of the
original (confirmed ~3400x2450 / ~4MB per photo) since this is for chart/card
display, not print. Confirmed via HEAD request: w_200 -> ~9KB, image/png.

Usage:
    PYTHONPATH=.pylibs python3 scripts/cache_player_photos.py
    PYTHONPATH=.pylibs python3 scripts/cache_player_photos.py --width 400
    PYTHONPATH=.pylibs python3 scripts/cache_player_photos.py --force   # re-download all
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import pathlib
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / "lake" / "nfl.duckdb"
PHOTO_DIR = REPO / "lake" / "gold" / "nfl" / "player_photos"
INDEX_CSV = PHOTO_DIR / "_index.csv"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {msg}", flush=True)


def with_width(url: str, width: int) -> str:
    """Insert/replace a Cloudinary width transform in an f_auto,q_auto URL."""
    if "/image/upload/" not in url:
        return url  # not a Cloudinary URL we recognize; use as-is
    return re.sub(
        r"(/image/upload/)([^/]*)(/)",
        lambda m: f"{m.group(1)}{m.group(2)},w_{width}{m.group(3)}",
        url,
        count=1,
    )


def load_index() -> dict[str, dict]:
    if not INDEX_CSV.exists():
        return {}
    with INDEX_CSV.open(newline="", encoding="utf-8") as fh:
        return {r["player_id"]: r for r in csv.DictReader(fh)}


def save_index(rows: dict[str, dict]) -> None:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["player_id", "player_display_name", "local_path", "source_url",
              "width", "sha256", "bytes", "content_type", "downloaded_at_utc",
              "status"]
    with INDEX_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(rows.values(), key=lambda x: x["player_id"]):
            w.writerow({k: r.get(k, "") for k in fields})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=200,
                    help="Cloudinary width transform (default 200px)")
    ap.add_argument("--force", action="store_true",
                    help="re-download even if already cached")
    ap.add_argument("--workers", type=int, default=16,
                    help="concurrent download threads (default 16)")
    args = ap.parse_args()

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb not importable.\n"
              "  pip install --target=.pylibs duckdb\n"
              "  PYTHONPATH=.pylibs python3 scripts/cache_player_photos.py",
              file=sys.stderr)
        return 2

    if not DB.exists():
        print(f"ERROR: {DB} not found. Run scripts/ingest_nfl_2026.py first.",
              file=sys.stderr)
        return 2

    con = duckdb.connect(str(DB), read_only=True)
    players = con.execute(
        "SELECT player_id, player_display_name, headshot_url "
        "FROM silver.nfl_player WHERE headshot_url IS NOT NULL"
    ).fetchall()
    con.close()
    log(f"{len(players)} players with a headshot_url in the lake")

    index = {} if args.force else load_index()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    todo = []
    for player_id, name, url in players:
        dest = PHOTO_DIR / f"{player_id}.png"
        if not args.force and player_id in index and dest.exists():
            continue
        todo.append((player_id, name, url))
    skipped = len(players) - len(todo)
    log(f"downloading {len(todo)} new/missing photos with {args.workers} workers "
        f"({skipped} already cached)")

    def fetch_one(item):
        player_id, name, url = item
        dest = PHOTO_DIR / f"{player_id}.png"
        sized_url = with_width(url, args.width)
        req = urllib.request.Request(sized_url, headers={"User-Agent": "frontal-lobe2/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            return player_id, {
                "player_id": player_id, "player_display_name": name,
                "local_path": "", "source_url": url, "width": args.width,
                "sha256": "", "bytes": 0, "content_type": "",
                "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": f"error: {e}",
            }
        dest.write_bytes(body)
        return player_id, {
            "player_id": player_id, "player_display_name": name,
            "local_path": str(dest.relative_to(REPO)), "source_url": url,
            "width": args.width, "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body), "content_type": ctype,
            "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "status": "ok",
        }

    fetched = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch_one, item) for item in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            player_id, row = fut.result()
            index[player_id] = row
            if row["status"] == "ok":
                fetched += 1
            else:
                failed += 1
                log(f"  FAILED {player_id} ({row['player_display_name']}): {row['status']}")
            if i % 200 == 0:
                log(f"  ...{i}/{len(todo)} processed")

    save_index(index)
    log(f"done: fetched={fetched}  skipped(cached)={skipped}  failed={failed}")
    log(f"index -> {INDEX_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Precompute Jimmy's take for every registered player slug.

Pulls each player's chart payload from the live API (already-built data),
runs the deterministic take generator locally, and writes the cache file the
backend serves from: lake/gold/espn/jimmy_takes.json

Run:  python scripts/seed_jimmy_takes.py [BASE_URL]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import jimmy_take as jt  # deterministic generator, identical to the served port

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://AIBRUH-big-proppa-live.hf.space").rstrip("/")
OUT = ROOT / "lake" / "gold" / "espn" / "jimmy_takes.json"


def get_json(path: str, timeout: float = 45) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def one(args: tuple[str, str, str]) -> tuple[str, dict | None]:
    pid, market, label = args
    chart = get_json(f"/api/chart/player_props?player_id={urllib.parse.quote(pid)}&market={urllib.parse.quote(market)}")
    if chart and not chart.get("error"):
        take = jt.generate(chart)
        take["playerId"] = pid
        take["name"] = chart.get("name") or chart["name"]
        return pid, take
    return pid, None


def main() -> None:
    # load existing cache
    try:
        cache: dict = json.loads(OUT.read_text())
    except Exception:
        cache = {}

    print("fetching slug registry...")
    reg = get_json("/api/slug/list")
    slugs = (reg or {}).get("slugs") or {}

    jobs, seen = [], set()
    for slug, e in slugs.items():
        pid, market = e.get("player_id"), e.get("market") or "rushyds"
        if not pid or pid in seen:
            continue
        seen.add(pid)
        jobs.append((pid, market, e.get("name") or ""))

    print(f"{len(jobs)} players to compute ({len(cache)} already cached)...")
    todo = [j for j in jobs if j[0] not in cache or not (cache.get(j[0]) or {}).get("prediction")]
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(one, j): j for j in todo}
        for fut in as_completed(futs):
            try:
                pid, take = fut.result()
            except Exception:
                continue
            if take and take.get("prediction"):
                cache[pid] = take
            done += 1
            if done % 40 == 0:
                print(f"  {done}/{len(todo)}")
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(cache, indent=1, sort_keys=True))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache, indent=1, sort_keys=True))
    print(f"DONE: {len(cache)} takes → {OUT}")


if __name__ == "__main__":
    main()

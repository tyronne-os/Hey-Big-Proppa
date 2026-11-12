"""
Seed the player slug registry + generate the Google-protocol sitemap backup.

Reads every featured player off the live API (Leaders categories + Targets board),
mints a deterministic slug for each, registers it with the live backend so every
/p/<slug> URL resolves from now on, then writes:
  - lake/gold/espn/player_slugs.json   (registry backup)
  - sitemap.xml                        (Google sitemap protocol backup)

Run:  python scripts/seed_player_sitemap.py [BASE_URL]
      BASE_URL default: https://AIBRUH-big-proppa-live.hf.space
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://AIBRUH-big-proppa-live.hf.space").rstrip("/")

LEADER_CATS = {"RUSHING": "rushyds", "RECEIVING": "recyds", "PASSING": "passyds", "SCORING": "passyds"}


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as r:
        return json.load(r)


def post(path: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}{path}?{q}", method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-") or "x"


def main() -> None:
    players: dict[str, dict] = {}
    for cat, market in LEADER_CATS.items():
        try:
            rows = get(f"/api/chart/leaders?category={urllib.parse.quote(cat)}").get("rows") or []
        except Exception as e:
            print(f"  ! {cat}: {e}")
            continue
        for r in rows:
            if r.get("playerId") and r.get("name"):
                key = r["playerId"]
                players.setdefault(key, {"playerId": key, "name": r["name"], "team": r.get("team") or "", "market": market})

    try:
        for r in (get("/api/targets").get("rows") or []):
            if r.get("playerId") and r.get("name"):
                key = r["playerId"]
                players.setdefault(key, {"playerId": key, "name": r["name"], "team": r.get("team") or "", "market": "recs"})
    except Exception as e:
        print(f"  ! targets: {e}")

    print(f"{len(players)} featured players found.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    registry: dict[str, dict] = {}

    # Keep any slugs the live site already minted so URLs never change under a crawler.
    try:
        registry.update(get("/api/slug/list").get("slugs") or {})
    except Exception:
        pass

    for p in players.values():
        slug = f"{ts}-{slugify(p['name'])}-{slugify(p['team'] or 'fa')}"
        if slug in registry:
            continue
        try:
            post("/api/slug/register", {
                "slug": slug,
                "player_id": p["playerId"],
                "market": p["market"],
                "name": p["name"],
                "team": p["team"],
            })
            registry[slug] = {"player_id": p["playerId"], "market": p["market"], "name": p["name"], "team": p["team"]}
        except Exception as e:
            print(f"  ! {p['name']}: {e}")

    print(f"{len(registry)} slugs in registry.")

    # ── Backup 1: registry JSON (seeds any rebuild) ──
    out = ROOT / "lake" / "gold" / "espn"
    out.mkdir(parents=True, exist_ok=True)
    (out / "player_slugs.json").write_text(json.dumps(registry, indent=2, sort_keys=True))

    # ── Backup 2: Google sitemap protocol XML ──
    today = datetime.now(timezone.utc).date().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for slug, e in sorted(registry.items()):
        lines.append("<url>"
                     f"<loc>{BASE}/p/{slug}</loc>"
                     f"<lastmod>{today}</lastmod>"
                     "<changefreq>weekly</changefreq>"
                     "<priority>0.8</priority>"
                     "</url>")
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n")

    print(f"Backed up → lake/gold/espn/player_slugs.json + sitemap.xml")


if __name__ == "__main__":
    main()

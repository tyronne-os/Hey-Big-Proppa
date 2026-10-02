"""
College football through ESPN's public API -- only what MY COLLEGE FOOTBALL cares about: the AP/Coaches Top 25 and the SEC.

  slate()   FBS scoreboard filtered to games with a ranked team or an SEC team (rank, logos, odds, broadcast, upset flags)
  polls()   AP + Coaches polls with week-over-week movement and the SEC marked
  feeds()   transfer-portal news, SEC news (SEC-team-tagged + search), and matchup news attached to each slate game
  build()   one snapshot of all three; written to lake/gold/espn/cfb_snapshot.json so the page keeps working if ESPN is down
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import espn

_DIR = Path(__file__).parent.parent / "lake/gold/espn"
_SNAP = _DIR / "cfb_snapshot.json"

# ESPN team ids of the 16 SEC members (2026). Verified at build time against ESPN's own groups=8 scoreboard.
SEC = {"333": "ALA", "8": "ARK", "2": "AUB", "57": "FLA", "61": "UGA", "96": "UK", "99": "LSU", "344": "MSST",
       "142": "MIZ", "201": "OU", "145": "MISS", "2579": "SC", "2633": "TENN", "251": "TEX", "245": "TAMU", "238": "VAN"}


def _tag(g: dict) -> dict:
    a, h = g["away_info"], g["home_info"]
    g["sec"] = a["id"] in SEC or h["id"] in SEC
    g["top25"] = bool(a["rank"] or h["rank"])
    # upset watch: an unranked (or lower-ranked) team is ahead of a ranked team, or ranked team trailing late
    lead_a, lead_h = g["away_score"] > g["home_score"], g["home_score"] > g["away_score"]
    ra, rh = a["rank"] or 99, h["rank"] or 99
    g["upset_alert"] = g["status"] in ("LIVE", "HALFTIME", "OT", "FINAL") and ((lead_a and ra > rh) or (lead_h and rh > ra)) and min(ra, rh) <= 25
    g["matchup_of_week"] = bool(a["rank"] and h["rank"])
    return g


def slate() -> list[dict]:
    games = espn.scoreboard_lg("cfb", "groups=80&limit=400", ttl=30) + espn.scoreboard_lg("cfb", "groups=8&limit=100", ttl=30)
    seen, out = set(), []
    for g in games:
        if g["game_id"] in seen:
            continue
        seen.add(g["game_id"])
        _tag(g)
        if g["sec"] or g["top25"]:
            out.append(g)
    order = {"LIVE": 0, "OT": 0, "HALFTIME": 0, "PRE": 1, "FINAL": 2}
    out.sort(key=lambda g: (order.get(g["status"], 3), g["start"]))
    return out


def polls() -> list[dict]:
    body = espn._fetch(espn._SITE.format("college-football") + "/rankings", ttl=900)
    out = []
    for r in (body or {}).get("rankings", [])[:2]:                       # AP Top 25, AFCA Coaches
        rows = []
        for t in r.get("ranks", []):
            tm = t.get("team") or {}
            prev, cur = t.get("previous") or 0, t.get("current")
            rows.append({"rank": cur, "prev": prev, "move": (prev - cur) if prev else None, "team": tm.get("abbreviation", ""),
                         "name": tm.get("location") or tm.get("name", ""), "logo": tm.get("logo", ""), "record": t.get("recordSummary", ""),
                         "points": t.get("points"), "first_votes": t.get("firstPlaceVotes"), "sec": str(tm.get("id")) in SEC})
        out.append({"name": r.get("name", ""), "headline": r.get("shortHeadline") or r.get("headline", ""), "updated": r.get("lastUpdated", ""),
                    "ranks": rows, "dropped": [(d.get("team") or {}).get("abbreviation", "") for d in r.get("droppedOut", [])]})
    return out


def feeds(games: list[dict] | None = None) -> dict:
    sec_names = ("SEC", "Alabama", "Georgia", "Texas", "LSU", "Tennessee", "Ole Miss", "Auburn", "Florida", "Oklahoma", "Missouri", "Arkansas",
                 "Kentucky", "Vanderbilt", "South Carolina", "Mississippi State", "Texas A&M", "Aggies", "Crimson Tide", "Bulldogs")
    national = espn.news("cfb", 100)
    portal_raw = espn.search_news("transfer portal", 20) + espn.search_news("SEC transfer portal", 10)
    sec_raw = espn.search_news("SEC", 20)
    portal, sec, seen = [], [], set()
    def add(bucket, a, tag):
        if a["link"] and a["link"] not in seen:
            seen.add(a["link"]); bucket.append({**a, "tag": tag})
    cfb_only = lambda a: "college-football" in a["link"]
    for a in portal_raw:
        if cfb_only(a) and any(k in (a["headline"] + " " + a["description"]).lower() for k in ("portal", "transfer")):
            add(portal, a, "PORTAL")
    for a in national:
        blob = (a["headline"] + " " + a["description"]).lower()
        if "transfer portal" in blob or "portal" in blob:
            add(portal, a, "PORTAL")
    for a in national:
        if any(t in SEC for t in a["teams"]) or any(n in a["headline"] for n in sec_names):
            add(sec, a, "SEC")
    for a in sec_raw:
        if cfb_only(a):
            add(sec, a, "SEC")
    for bucket in (portal, sec):
        bucket.sort(key=lambda a: a["published"], reverse=True)
    # matchup news: attach up to 2 articles to each slate game by team tag or team nickname in the headline
    matchup = {}
    for g in games or []:
        ids = {g["away_info"]["id"], g["home_info"]["id"]}
        names = [g["away_info"]["name"], g["home_info"]["name"]]
        hits = [a for a in national + sec_raw if (set(a["teams"]) & ids) or any(n and n in a["headline"] for n in names)]
        if hits:
            matchup[g["game_id"]] = [{"headline": a["headline"], "link": a["link"]} for a in hits[:2]]
    return {"portal": portal[:25], "sec": sec[:25], "matchup": matchup}


def build() -> dict:
    g = slate()
    snap = {"built": time.time(), "games": g, "polls": polls(), "feeds": feeds(g)}
    _DIR.mkdir(parents=True, exist_ok=True)
    if g or snap["polls"]:
        tmp = _SNAP.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap))
        tmp.replace(_SNAP)
    return snap


def latest(max_age: int = 120) -> dict:
    """Fresh snapshot if recent, else rebuild; falls back to the last good file when ESPN is unreachable."""
    try:
        cur = json.loads(_SNAP.read_text())
        if time.time() - cur.get("built", 0) < max_age:
            return {**cur, "stale": False}
    except (OSError, ValueError):
        cur = None
    try:
        snap = build()
        if snap["games"] or snap["polls"]:
            return {**snap, "stale": False}
    except Exception:
        pass
    return {**cur, "stale": True} if cur else {"games": [], "polls": [], "feeds": {"portal": [], "sec": [], "matchup": {}}, "stale": True, "built": 0}

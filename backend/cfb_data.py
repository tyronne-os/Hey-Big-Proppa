"""
CFB data layer — thin wrapper around the CFBD API.

Auth: Bearer token from CFBD_API_KEY env var.
All calls return [] / {} / None on any error so callers degrade gracefully.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import urllib.request
import urllib.parse
import json

_BASE = "https://api.collegefootballdata.com"
_TIMEOUT = 12


def _key() -> str | None:
    return os.environ.get("CFBD_API_KEY")


def _get(path: str, params: dict | None = None) -> Any:
    key = _key()
    if not key:
        return None
    url = f"{_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read())
    except Exception:
        return None


def available() -> bool:
    return bool(_key())


# ---------------------------------------------------------------------------
# Current season / week helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _current_season() -> int:
    """
    Latest season with real CFBD game data (team names populated).
    Checks the current calendar year first, falls back until it finds data.
    """
    import datetime
    y = datetime.date.today().year
    m = datetime.date.today().month
    start = y if m >= 8 else y - 1
    for candidate in (start, start - 1, start - 2):
        sample = _get("/games", {"year": candidate, "week": 1, "seasonType": "regular"})
        if sample and any(g.get("homeTeam") for g in sample):
            return candidate
    return start  # best guess if API is down


@lru_cache(maxsize=1)
def current_week_games() -> list[dict]:
    """Games scheduled for the current (or next upcoming) week — real data only."""
    year = _current_season()
    raw = _get("/games", {"year": year, "seasonType": "regular"})
    if not raw:
        return []
    # keep only FBS games with team names (guards against placeholder/empty rows)
    real = [g for g in raw
            if g.get("homeTeam") and g.get("awayTeam")
            and g.get("homeClassification") == "fbs"
            and g.get("awayClassification") == "fbs"]
    # unfinished = not completed yet
    unfinished = [g for g in real if not g.get("completed")]
    if not unfinished:
        # all games completed — show last completed week
        completed = [g for g in real if g.get("completed")]
        if not completed:
            return []
        max_week = max(g["week"] for g in completed)
        return [g for g in completed if g["week"] == max_week]
    min_week = min(g["week"] for g in unfinished)
    return [g for g in unfinished if g["week"] == min_week]


@lru_cache(maxsize=1)
def current_week() -> int | None:
    games = current_week_games()
    return games[0]["week"] if games else None


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def ap_poll() -> dict[str, int]:
    """
    Returns {team_name: rank} for the current AP top 25.
    Team names match CFBD's school names (e.g. "Ohio State", "Georgia").
    """
    year = _current_season()
    week = current_week()
    if week is None:
        return {}
    # try current week, fall back to week-1 if not published yet
    for w in (week, max(1, week - 1)):
        data = _get("/rankings", {"year": year, "week": w, "seasonType": "regular"})
        if not data:
            continue
        for poll_week in data:
            for poll in (poll_week.get("polls") or []):
                if poll.get("poll") == "AP Top 25":
                    return {r["school"]: r["rank"] for r in poll.get("ranks", [])}
    return {}


# ---------------------------------------------------------------------------
# Team game history (for performance comparison)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def team_recent_games(team: str, n: int = 3) -> list[dict]:
    """
    Last n completed games for a team this season (or last season if early).
    Returns list of dicts with keys: week, points_for, points_against, win, opponent.
    """
    year = _current_season()
    week = current_week()
    raw = _get("/games", {"year": year, "seasonType": "regular", "team": team})
    if not raw:
        # try prior season
        raw = _get("/games", {"year": year - 1, "seasonType": "regular", "team": team}) or []

    completed = []
    for g in raw:
        # only completed FBS games strictly before the current week
        if not g.get("completed"):
            continue
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
            continue
        if week and g.get("week", 0) >= week:
            continue
        is_home = g.get("homeTeam") == team
        pts_for  = g.get("homePoints") if is_home else g.get("awayPoints")
        pts_vs   = g.get("awayPoints") if is_home else g.get("homePoints")
        if pts_for is None or pts_vs is None:
            continue
        completed.append({
            "week":           g["week"],
            "points_for":     int(pts_for),
            "points_against": int(pts_vs),
            "win":            int(pts_for) > int(pts_vs),
            "opponent":       g.get("awayTeam") if is_home else g.get("homeTeam"),
        })

    # sort descending (most recent first), take n
    completed.sort(key=lambda g: g["week"], reverse=True)
    return completed[:n]


# ---------------------------------------------------------------------------
# Betting lines
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def current_week_lines() -> dict[int, dict]:
    """
    Returns {game_id: {spread, over_under, home_moneyline, away_moneyline, provider}}
    for this week's games. Uses the first provider that has all fields.
    """
    year = _current_season()
    week = current_week()
    if week is None:
        return {}
    raw = _get("/lines", {"year": year, "week": week, "seasonType": "regular"})
    if not raw:
        return {}

    out: dict[int, dict] = {}
    preferred = ("consensus", "DraftKings", "ESPN Bet", "FanDuel")

    for game in raw:
        gid = game.get("id")
        lines_list = game.get("lines") or []
        if not lines_list:
            continue
        # pick preferred provider, else first
        line = None
        for pref in preferred:
            line = next((l for l in lines_list if l.get("provider") == pref), None)
            if line:
                break
        if not line:
            line = lines_list[0]

        try:
            out[gid] = {
                "spread":          float(line.get("spread") or 0),
                "over_under":      float(line.get("overUnder") or 0),
                "home_moneyline":  line.get("homeMoneyline"),
                "away_moneyline":  line.get("awayMoneyline"),
                "provider":        line.get("provider", "unknown"),
                "formatted_spread": line.get("formattedSpread", ""),
            }
        except (TypeError, ValueError):
            continue

    return out

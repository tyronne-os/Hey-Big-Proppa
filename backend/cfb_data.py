"""
CFB data layer — thin wrapper around the CFBD API.

Auth: Bearer token from CFBD_API_KEY env var.
All calls return [] / {} / None on any error so callers degrade gracefully.

Signal inventory (2026):
  sp_ratings()       → SP+ overall/offense/defense ratings (Bill Connelly model)
  advanced_stats()   → PPA, success rate, explosiveness, havoc, line yards
  elo_ratings()      → Elo per team
  talent_composite() → Recruiting talent composite
  pregame_wp()       → Model win probability per game_id
  current_week_lines() → Spread, total, moneylines (consensus preferred)
  team_recent_games()  → Last-N completed game results
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

# TTL cache for signal endpoints — avoids poisoning lru_cache with empty API failure results
_signal_cache: dict[str, tuple[Any, float]] = {}
_SIGNAL_TTL = 900  # 15 minutes


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


def _get_cached(path: str, params: dict | None = None, ttl: int = _SIGNAL_TTL) -> Any:
    """Like _get() but uses a TTL dict cache — never caches None/empty results."""
    cache_key = path + str(sorted((params or {}).items()))
    entry = _signal_cache.get(cache_key)
    if entry:
        data, expires = entry
        if time.time() < expires:
            return data
    result = _get(path, params)
    if result:  # only cache non-empty, non-None results
        _signal_cache[cache_key] = (result, time.time() + ttl)
    return result


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


# ---------------------------------------------------------------------------
# SP+ ratings — Bill Connelly's most predictive CFB model
# ---------------------------------------------------------------------------

def sp_ratings() -> dict[str, dict]:
    """
    {team: {overall, offense_rank, offense_rating, defense_rank, defense_rating}}
    SP+ overall: positive = better, scale roughly -30 to +35.
    """
    year = _current_season()
    raw = _get_cached("/ratings/sp", {"year": year}) or []
    out: dict[str, dict] = {}
    for r in raw:
        team = r.get("team", "")
        if not team:
            continue
        off = r.get("offense") or {}
        dfe = r.get("defense") or {}
        out[team] = {
            "overall":        r.get("rating"),
            "overall_rank":   r.get("ranking"),
            "offense_rank":   off.get("ranking"),
            "offense_rating": off.get("rating"),
            "defense_rank":   dfe.get("ranking"),
            "defense_rating": dfe.get("rating"),
            "sos":            r.get("sos"),
        }
    return out


# ---------------------------------------------------------------------------
# Advanced stats — PPA, success rate, explosiveness, havoc
# ---------------------------------------------------------------------------

def advanced_stats() -> dict[str, dict]:
    """
    {team: {off_ppa, def_ppa, off_success, def_success,
            off_explosiveness, def_explosiveness,
            off_havoc, def_havoc, off_stuff_rate, def_stuff_rate,
            off_line_yards, off_open_field_yards}}
    PPA > 0 on offense = efficient; PPA < 0 on defense = holding opponents.
    """
    year = _current_season()
    raw = _get_cached("/stats/season/advanced", {"year": year, "excludeGarbageTime": "true"}) or []
    out: dict[str, dict] = {}
    for r in raw:
        team = r.get("team", "")
        if not team:
            continue
        off = r.get("offense") or {}
        dfe = r.get("defense") or {}
        out[team] = {
            "off_ppa":              off.get("ppa"),
            "off_success":          off.get("successRate"),
            "off_explosiveness":    off.get("explosiveness"),
            "off_havoc":            (off.get("havoc") or {}).get("total"),
            "off_stuff_rate":       off.get("stuffRate"),
            "off_line_yards":       off.get("lineYards"),
            "off_open_field_yards": off.get("openFieldYards"),
            "def_ppa":              dfe.get("ppa"),
            "def_success":          dfe.get("successRate"),
            "def_explosiveness":    dfe.get("explosiveness"),
            "def_havoc":            (dfe.get("havoc") or {}).get("total"),
            "def_stuff_rate":       dfe.get("stuffRate"),
        }
    return out


# ---------------------------------------------------------------------------
# Elo ratings
# ---------------------------------------------------------------------------

def elo_ratings() -> dict[str, float]:
    """{team: elo} — 1500 = average, higher = better."""
    year = _current_season()
    week = current_week()
    params: dict = {"year": year}
    if week:
        params["week"] = week
    raw = _get_cached("/ratings/elo", params) or []
    return {r["team"]: r["elo"] for r in raw if r.get("team") and r.get("elo")}


# ---------------------------------------------------------------------------
# Talent composite
# ---------------------------------------------------------------------------

def talent_composite() -> dict[str, float]:
    """{team: talent_score} — composite recruiting talent (higher = better)."""
    year = _current_season()
    raw = _get_cached("/talent", {"year": year}) or []
    return {r["team"]: r["talent"] for r in raw if r.get("team") and r.get("talent")}


# ---------------------------------------------------------------------------
# Pregame win probability (model-driven, per game_id)
# ---------------------------------------------------------------------------

def pregame_wp() -> dict[int, dict]:
    """
    {game_id: {home_team, away_team, home_wp, spread}}
    Model win probability from CFBD's SP+-calibrated model.
    """
    year = _current_season()
    week = current_week()
    if week is None:
        return {}
    raw = _get_cached("/metrics/wp/pregame", {"year": year, "week": week, "seasonType": "regular"}) or []
    out: dict[int, dict] = {}
    for r in raw:
        gid = r.get("gameId")
        if gid:
            out[gid] = {
                "home_team": r.get("homeTeam", ""),
                "away_team": r.get("awayTeam", ""),
                "home_wp":   r.get("homeWinProbability"),
                "spread":    r.get("spread"),
            }
    return out

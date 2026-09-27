"""
Tank01 NFL API — live data gateway.

Endpoints used:
  getNFLGamesForDate          → real kickoff times for the slate
  getNFLInjuryList            → injury designations (OUT/IR/Q/D/O/LP)
  getInactivePlayersByGameWeek → final inactives (90 min pre-kick)
  getNFLDepthCharts           → starter/backup positions
  getDailyScoreboard          → live in-game scores
  getPlayerInformation        → espnID for headshots
  getFantasyPointProjections  → projected stats (projection signal)
  getDFSSalaries              → FD/DK salary (market-consensus signal)
  getNFLTeamRoster            → full roster with espnID
  getWeeklyNFLSchedule        → full-week schedule with game IDs

Auth: x-rapidapi-key header from $TANK01_API_KEY (never printed/logged).
Base: https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com

All functions return [] or {} on failure — callers treat None/empty as
"data unavailable, fall back to lake-only", never as an error.

Results are in-process cached for 10 minutes to avoid burning rate limits.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Any

import requests

_BASE = "https://tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
_HOST = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"

# Simple TTL cache: (result, expire_ts)
_cache: dict[str, tuple[Any, float]] = {}
_TTL = 600  # 10 minutes


def _headers() -> dict[str, str]:
    key = os.environ.get("TANK01_API_KEY", "")
    return {
        "x-rapidapi-key":  key,
        "x-rapidapi-host": _HOST,
    }


def _get(endpoint: str, params: dict | None = None, ttl: int = _TTL) -> Any:
    """GET helper with TTL cache. Returns parsed JSON or None on failure."""
    cache_key = endpoint + str(sorted((params or {}).items()))
    cached = _cache.get(cache_key)
    if cached and time.time() < cached[1]:
        return cached[0]

    if not os.environ.get("TANK01_API_KEY"):
        return None

    try:
        r = requests.get(
            f"{_BASE}/{endpoint}",
            headers=_headers(),
            params=params or {},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        _cache[cache_key] = (data, time.time() + ttl)
        return data
    except Exception:
        return None


# ── CST helper ───────────────────────────────────────────────────────────────
from zoneinfo import ZoneInfo

_CST = ZoneInfo("America/Chicago")  # New Orleans: Central time, daylight saving handled


def _to_cst(iso_or_epoch: str | int | None) -> str:
    if not iso_or_epoch:
        return ""
    try:
        text = str(iso_or_epoch)
        try:
            dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
        except ValueError:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(_CST).strftime("%-I:%M %p CT")
    except Exception:
        return ""


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def available() -> bool:
    """True if TANK01_API_KEY is set in the environment."""
    return bool(os.environ.get("TANK01_API_KEY"))


def get_games_for_date(date_str: str | None = None) -> list[dict]:
    """
    Returns list of games for a date (YYYYMMDD, default today).
    Each game: {gameID, home, away, gameTime (CST), gameDate, homeScore, awayScore, gameStatus}
    """
    raw = _get("getNFLGamesForDate", {"gameDate": date_str or _today_str()})
    if not raw:
        return []
    games = raw.get("body", []) or []
    out = []
    for g in games:
        out.append({
            "gameID":      g.get("gameID", ""),
            "home":        g.get("home", ""),
            "away":        g.get("away", ""),
            "gameDate":    g.get("gameDate", ""),
            "gameTime":    _to_cst(g.get("gameTime_epoch") or g.get("gameTimeEpoch") or g.get("gameTime")),
            "gameTimeEpoch": g.get("gameTime_epoch") or g.get("gameTimeEpoch"),
            "gameStatus":  g.get("gameStatus", ""),
            "homeScore":   g.get("homeScore"),
            "awayScore":   g.get("awayScore"),
        })
    return out


def get_weekly_schedule(season: int | None = None, season_type: str = "reg") -> list[dict]:
    """All games in the current week's schedule with kickoff times."""
    params: dict = {"seasonType": season_type}
    if season:
        params["season"] = str(season)
    raw = _get("getWeeklyNFLSchedule", params)
    if not raw:
        return []
    body = raw.get("body", {}) or {}
    out = []
    for week_key, games in body.items():
        if isinstance(games, list):
            for g in games:
                out.append({
                    "week":      week_key,
                    "gameID":    g.get("gameID", ""),
                    "home":      g.get("home", ""),
                    "away":      g.get("away", ""),
                    "gameDate":  g.get("gameDate", ""),
                    "gameTime":  _to_cst(g.get("gameTime_epoch") or g.get("gameTimeEpoch") or g.get("gameTime")),
                    "gameStatus": g.get("gameStatus", ""),
                })
    return out


def get_injury_list() -> list[dict]:
    """
    Returns current injury designations.
    Each: {playerID, name, team, position, injuryStatus, injuryDescription}
    Statuses: OUT, IR, Q (Questionable), D (Doubtful), O (Out), LP (Limited Practice)
    """
    raw = _get("getNFLInjuryList", ttl=300)  # 5 min TTL on injury data
    if not raw:
        return []
    body = raw.get("body", []) or []
    out = []
    for p in body:
        status = (p.get("injuryStatus") or "").upper()
        out.append({
            "playerID":          p.get("playerID", ""),
            "espnID":            p.get("espnID", ""),
            "name":              p.get("playerName", p.get("name", "")),
            "team":              p.get("team", ""),
            "position":          p.get("position", ""),
            "injuryStatus":      status,
            "injuryDescription": p.get("injuryDescription", ""),
        })
    return out


def get_inactive_players(game_week: int | None = None) -> list[dict]:
    """Official inactives list. Available ~90 min before kickoff."""
    params = {}
    if game_week:
        params["gameWeek"] = str(game_week)
    raw = _get("getInactivePlayersByGameWeek", params, ttl=120)  # 2 min TTL
    if not raw:
        return []
    body = raw.get("body", []) or []
    out = []
    for item in body:
        team = item.get("team", "")
        for p in (item.get("inactivePlayers") or []):
            out.append({
                "playerID": p.get("playerID", ""),
                "espnID":   p.get("espnID", ""),
                "name":     p.get("playerName", p.get("name", "")),
                "team":     team,
                "position": p.get("position", ""),
            })
    return out


def get_depth_charts(team: str | None = None) -> dict[str, dict]:
    """
    Returns depth chart per team.
    Structure: {team: {position: [{rank, playerID, name, espnID}]}}
    """
    params = {}
    if team:
        params["teamAbv"] = team
    raw = _get("getNFLDepthCharts", params)
    if not raw:
        return {}
    body = raw.get("body", {}) or {}
    # API may return a list of {teamAbv, depthChart: {pos: [players]}} objects
    # or a dict keyed by team abbreviation directly
    if isinstance(body, list):
        body = {
            item.get("teamAbv", item.get("team", f"team_{i}")): item.get("depthChart", item)
            for i, item in enumerate(body)
            if isinstance(item, dict)
        }
    out: dict[str, dict] = {}
    for team_abbr, positions in body.items():
        if not isinstance(positions, dict):
            continue
        out[team_abbr] = {}
        for pos, players in positions.items():
            if not isinstance(players, list):
                continue
            out[team_abbr][pos] = [
                {
                    "rank":     i + 1,
                    "playerID": p.get("playerID", ""),
                    "espnID":   p.get("espnID", ""),
                    "name":     p.get("playerName", p.get("name", "")),
                }
                for i, p in enumerate(players)
            ]
    return out


def get_daily_scoreboard(date_str: str | None = None) -> list[dict]:
    """Live in-progress scores. Polled every 2 min on game days."""
    raw = _get("getDailyScoreboard", {"gameDate": date_str or _today_str()}, ttl=120)
    if not raw:
        return []
    body = raw.get("body", {}) or {}
    games_raw = body.get("scoreboard", body) if isinstance(body, dict) else body
    if isinstance(games_raw, dict):
        games_raw = list(games_raw.values())
    out = []
    for g in (games_raw or []):
        if not isinstance(g, dict):
            continue
        out.append({
            "gameID":    g.get("gameID", ""),
            "home":      g.get("home", ""),
            "away":      g.get("away", ""),
            "homeScore": g.get("homePts") or g.get("homeScore"),
            "awayScore": g.get("awayPts") or g.get("awayScore"),
            "quarter":   g.get("quarter") or g.get("qtr"),
            "clock":     g.get("gameClock") or g.get("clock"),
            "status":    g.get("gameStatus", ""),
        })
    return out


def get_player_info(player_id: str) -> dict:
    """
    Single player info including espnID (for headshot CDN URL).
    Returns {} if not found or API unavailable.
    """
    raw = _get("getPlayerInformation", {"playerID": player_id})
    if not raw:
        return {}
    body = raw.get("body", {}) or {}
    if isinstance(body, list):
        body = body[0] if body else {}
    espn_id = body.get("espnID", "")
    return {
        "playerID":  body.get("playerID", player_id),
        "espnID":    espn_id,
        "name":      body.get("playerName", body.get("name", "")),
        "team":      body.get("team", ""),
        "position":  body.get("pos", body.get("position", "")),
        "photoUrl":  (f"https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{espn_id}.png&w=96&h=70" if espn_id else None),
        "jerseyNum": body.get("jerseyNum", ""),
        "height":    body.get("height", ""),
        "weight":    body.get("weight", ""),
        "college":   body.get("college", ""),
        "exp":       body.get("exp", ""),
    }


_photo_index: tuple[dict[str, list[tuple[str, str]]], float] | None = None


def player_photos() -> dict[str, list[tuple[str, str]]]:
    """normalized player name -> [(team, ESPN headshot url)] from one getNFLPlayerList call.
    The built index is memoized for an hour (rebuilding it per player made the leaders API crawl)."""
    global _photo_index
    if _photo_index and time.time() < _photo_index[1]:
        return _photo_index[0]
    import data
    raw = _get("getNFLPlayerList", ttl=86400)
    body = (raw or {}).get("body") if isinstance(raw, dict) else None
    out: dict[str, list[tuple[str, str]]] = {}
    for p in body or []:
        if p.get("espnHeadshot") and p.get("longName"):
            out.setdefault(data.normalize_name(p["longName"]), []).append((p.get("team", ""), p["espnHeadshot"]))
    if out:
        _photo_index = (out, time.time() + 3600)
    return out


def get_fantasy_projections(week: int | None = None, season_type: str = "reg") -> list[dict]:
    """
    Fantasy point projections — used as 4th Jimmy signal.
    Each: {playerID, name, team, position, projectedPts, projStats: {rushYds, recYds, passYds, ...}}
    """
    params: dict = {"seasonType": season_type}
    if week:
        params["week"] = str(week)
    raw = _get("getFantasyPointProjections", params)
    if not raw:
        return []
    body = raw.get("body", []) or []
    if isinstance(body, dict):
        # sometimes keyed by playerID
        body = list(body.values())
    out = []
    for p in body:
        if not isinstance(p, dict):
            continue
        proj_stats = p.get("stats") or {}
        out.append({
            "playerID":    p.get("playerID", ""),
            "espnID":      p.get("espnID", ""),
            "name":        p.get("playerName", p.get("name", "")),
            "team":        p.get("team", ""),
            "position":    p.get("pos", p.get("position", "")),
            "projectedPts": _f(p.get("fantasyPoints") or p.get("projectedPts")),
            "projRushYds":  _f(proj_stats.get("rushYds")),
            "projRecYds":   _f(proj_stats.get("recYds")),
            "projPassYds":  _f(proj_stats.get("passYds")),
            "projRec":      _f(proj_stats.get("receptions") or proj_stats.get("rec")),
            "projCarries":  _f(proj_stats.get("rushAtt") or proj_stats.get("carries")),
            "projTDs":      _f(proj_stats.get("totalTD") or proj_stats.get("TDs")),
        })
    return out


def get_dfs_salaries(slate: str = "FanDuel") -> list[dict]:
    """
    DFS salary data — used as market consensus signal.
    slate: "FanDuel" | "DraftKings"
    Each: {playerID, name, team, position, salary, avgPts}
    """
    raw = _get("getDFSSalaries", {"slate": slate})
    if not raw:
        return []
    body = raw.get("body", []) or []
    if isinstance(body, dict):
        body = list(body.values())
    out = []
    for p in body:
        if not isinstance(p, dict):
            continue
        out.append({
            "playerID": p.get("playerID", ""),
            "name":     p.get("playerName", p.get("name", "")),
            "team":     p.get("team", ""),
            "position": p.get("pos", p.get("position", "")),
            "salary":   _f(p.get("salary")),
            "avgPts":   _f(p.get("avgPoints") or p.get("avgPts")),
            "slate":    slate,
        })
    return out


def get_nfl_standings() -> dict[str, list[dict]]:
    """
    NFL standings by division.
    Returns: {"AFC East": [{team, wins, losses, ties, pct, div, conf}], ...}
    Tank01 getNFLTeams returns team records; we regroup by division.
    """
    raw = _get("getNFLTeams", {"teamStats": "true", "sortBy": "wins"})
    if not raw:
        return {}
    body = raw.get("body", []) or []
    if isinstance(body, dict):
        body = list(body.values())

    divisions: dict[str, list[dict]] = {}
    for t in body:
        if not isinstance(t, dict):
            continue
        conf = (t.get("conferenceAbv") or t.get("conf") or "").upper()
        div_name = (t.get("division") or "").title()
        if not div_name:
            continue
        key = f"{conf} {div_name}"
        wins   = int(t.get("wins") or t.get("totalWins") or 0)
        losses = int(t.get("losses") or t.get("totalLosses") or 0)
        ties   = int(t.get("ties") or t.get("totalTies") or 0)
        gp = wins + losses + ties
        pct = round(wins / gp, 3) if gp > 0 else 0.0
        divisions.setdefault(key, []).append({
            "team":   t.get("teamAbv", t.get("teamAbbv", "")),
            "name":   t.get("teamName", ""),
            "city":   t.get("teamCity", ""),
            "wins":   wins,
            "losses": losses,
            "ties":   ties,
            "pct":    pct,
            "divW":   int(t.get("divisionWins") or 0),
            "divL":   int(t.get("divisionLosses") or 0),
            "confW":  int(t.get("conferenceWins") or 0),
            "confL":  int(t.get("conferenceLosses") or 0),
            "streak": t.get("streak", ""),
            "color1": t.get("primaryColor", ""),
            "logo":   t.get("espnLogo1", t.get("nflComLogo1", "")),
        })

    # Sort each division by win percentage descending
    for key in divisions:
        divisions[key].sort(key=lambda r: (-r["pct"], -r["wins"]))

    return divisions


def injury_map_by_player_id() -> dict[str, dict]:
    """Fast lookup: playerID → injury entry."""
    return {p["playerID"]: p for p in get_injury_list() if p["playerID"]}


def starters_by_player_id() -> dict[str, bool]:
    """
    Returns a set of playerIDs who are listed as depth-chart starters
    (rank == 1 at their primary position).
    """
    charts = get_depth_charts()
    starters: dict[str, bool] = {}
    for team_chart in charts.values():
        for pos_list in team_chart.values():
            if pos_list:
                starters[pos_list[0]["playerID"]] = True
    return starters


def projection_by_player_id() -> dict[str, dict]:
    """Fast lookup: playerID → projection entry."""
    return {p["playerID"]: p for p in get_fantasy_projections() if p["playerID"]}


def salary_by_player_id(slate: str = "FanDuel") -> dict[str, dict]:
    """Fast lookup: playerID → DFS salary entry."""
    return {p["playerID"]: p for p in get_dfs_salaries(slate) if p["playerID"]}


# ── helpers ───────────────────────────────────────────────────────────────────
def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None

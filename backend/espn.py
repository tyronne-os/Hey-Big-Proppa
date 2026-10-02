"""
ESPN public API wrapper — free, no auth, covers scores + full player box scores.

Scoreboard endpoint (week's 16 games):
  https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
  Returns: game list with STATUS_FINAL, scores, odds.

Game summary endpoint (per game):
  https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={id}
  Returns: full player box scores, drives, win prob, DraftKings odds.

No API key required.  Rate: 1 call per request, TTL-cached 60s (scoreboard),
600s (summary for FINAL games, 45s for live).
"""
from __future__ import annotations

import time
import threading
from typing import Optional
import urllib.request
import json
from datetime import datetime

import data

_LOCK = threading.Lock()
# {cache_key: (expires_ts, data)}
_cache: dict[str, tuple[float, object]] = {}

_SB_URL  = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_SUM_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={}"
_UA      = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def _fetch(url: str, ttl: int = 60) -> dict | None:
    with _LOCK:
        entry = _cache.get(url)
        if entry and entry[0] > time.time():
            return entry[1]           # type: ignore[return-value]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
        with _LOCK:
            _cache[url] = (time.time() + ttl, body)
        return body
    except Exception:
        return None


def _f(x, d: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


# ---------------------------------------------------------------------------
# scoreboard
# ---------------------------------------------------------------------------

def get_scoreboard() -> list[dict]:
    """
    Returns one dict per NFL game this week:
      game_id   : ESPN event id (string)
      away      : team abbreviation e.g. "PIT"
      home      : team abbreviation e.g. "CLE"
      away_score: int
      home_score: int
      status    : "FINAL" | "LIVE" | "HALFTIME" | "PRE" | "OT"
      final     : bool
      period    : int (quarter)
      clock     : str
      odds_spread : e.g. "PIT -2.5" or ""
      odds_ou     : float or None
    """
    body = _fetch(_SB_URL, ttl=60)
    if not body:
        return []
    out = []
    for ev in body.get("events", []):
        comp_list = ev.get("competitions", [ev])
        comp = comp_list[0] if comp_list else {}
        st = comp.get("status") or ev.get("status") or {}
        st_type = (st.get("type") or {}).get("name", "")
        st_desc = (st.get("type") or {}).get("description", "")
        period  = int((st.get("period") or 0))
        clock   = str(st.get("displayClock") or "")

        if "FINAL" in st_type.upper():
            status = "FINAL"
        elif "HALFTIME" in st_type.upper() or "HALFTIME" in st_desc.upper():
            status, period = "HALFTIME", 2
        elif "OT" in st_type.upper() or period >= 5:
            status = "OT"
        elif "IN_PROGRESS" in st_type.upper() or "LIVE" in st_type.upper():
            status = "LIVE"
        else:
            status = "PRE"

        competitors = comp.get("competitors", [])
        away_c = next((c for c in competitors if c.get("homeAway") == "away"), {})
        home_c = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_team = (away_c.get("team") or {}).get("abbreviation", "")
        home_team = (home_c.get("team") or {}).get("abbreviation", "")
        away_score = int(_f(away_c.get("score")))
        home_score = int(_f(home_c.get("score")))

        odds_list = comp.get("odds") or ev.get("odds") or []
        odds_spread = ""
        odds_ou: float | None = None
        if odds_list:
            o = odds_list[0]
            odds_spread = str(o.get("details") or "")
            raw_ou = o.get("overUnder")
            if raw_ou:
                try:
                    odds_ou = float(raw_ou)
                except (TypeError, ValueError):
                    pass

        out.append({
            "game_id":   str(ev.get("id", "")),
            "away":      away_team,
            "home":      home_team,
            "away_score": away_score,
            "home_score": home_score,
            "status":    status,
            "final":     status == "FINAL",
            "period":    period,
            "clock":     clock,
            "odds_spread": odds_spread,
            "odds_ou":   odds_ou,
        })
    return out


def final_games() -> list[dict]:
    """Games with STATUS_FINAL on the current week's scoreboard."""
    return [g for g in get_scoreboard() if g["final"]]


# ---------------------------------------------------------------------------
# game summary → player box score
# ---------------------------------------------------------------------------

_STAT_MAP = {
    # (category name, label) → our key
    "passing":      {"YDS": "passyds", "TD": "passtd", "C/ATT": "att", "INT": "int"},
    "rushing":      {"YDS": "rushyds", "CAR": "carries", "TD": "rushtd"},
    "receiving":    {"YDS": "recyds", "REC": "recs", "TD": "rectd", "TGTS": "tgt"},
    "kicking":      {"PTS": "kickpts"},
}


def _parse_player_stats(boxscore: dict) -> dict[tuple[str, str], dict]:
    """
    boxscore.players list → {(normalized_name, team_abbrev): stat_dict}
    same shape as from_tank01's 'players' dict.
    """
    players: dict[tuple[str, str], dict] = {}
    for team_entry in boxscore.get("players", []):
        team_abbr = (team_entry.get("team") or {}).get("abbreviation", "")
        for cat in team_entry.get("statistics", []):
            cat_name = (cat.get("name") or "").lower()
            labels   = [l.upper() for l in (cat.get("labels") or [])]
            for athlete in cat.get("athletes", []):
                a_obj = athlete.get("athlete") or {}
                raw_name = a_obj.get("displayName", "")
                norm_name = data.normalize_name(raw_name)
                key = (norm_name, team_abbr)
                if key not in players:
                    players[key] = {
                        "rushyds": 0.0, "carries": 0.0, "rushtd": 0.0,
                        "recyds":  0.0, "recs":    0.0, "rectd":  0.0, "tgt": 0.0,
                        "passyds": 0.0, "passtd":  0.0, "att":    0.0,
                        "kickpts": 0.0, "int":     0.0,
                    }
                mapping = _STAT_MAP.get(cat_name, {})
                stats_raw = athlete.get("stats") or []
                for label, our_key in mapping.items():
                    if label in labels:
                        idx = labels.index(label)
                        if idx < len(stats_raw):
                            # C/ATT passatt handling
                            val_str = stats_raw[idx]
                            if "/" in str(val_str):
                                try:
                                    players[key][our_key] = float(str(val_str).split("/")[1])
                                except (IndexError, ValueError):
                                    pass
                            else:
                                players[key][our_key] = _f(val_str)
    return players


def get_game_summary(espn_event_id: str) -> dict | None:
    """
    Fetch the full game summary for one ESPN event.  Returns normalised live dict:
      game_id, status, period, clock, home, away, home_pts, away_pts, players, first_td
    Shape is identical to from_tank01() so espn_source() is a drop-in replacement.
    Returns None if the event cannot be fetched.
    """
    url = _SUM_URL.format(espn_event_id)
    # cache 600s for final games, 45s for live
    body = _fetch(url, ttl=45)
    if not body:
        return None

    # Pull status from header
    header   = body.get("header", {})
    comps    = header.get("competitions", [])
    hcomp    = comps[0] if comps else {}
    hstatus  = (hcomp.get("status") or {}).get("type") or {}
    st_name  = hstatus.get("name", "")
    period_h = int(_f(hcomp.get("period") or hcomp.get("status", {}).get("period") or 0))
    clock_h  = str((hcomp.get("status") or {}).get("displayClock") or "")

    if "FINAL" in st_name.upper():
        status = "FINAL"
        # bump TTL to 600s for final games so we don't keep refetching
        _cache[url] = (time.time() + 600, body)
    elif "HALFTIME" in st_name.upper():
        status, period_h = "HALFTIME", 2
    elif period_h >= 5:
        status = "OT"
    elif "IN_PROGRESS" in st_name.upper() or "LIVE" in st_name.upper():
        status = "LIVE"
    else:
        status = "PRE"

    hcompetitors = hcomp.get("competitors", [])
    away_c = next((c for c in hcompetitors if not c.get("homeAway") == "home"), {})
    home_c = next((c for c in hcompetitors if c.get("homeAway") == "home"), {})
    # fallback on order
    if not away_c and len(hcompetitors) == 2:
        away_c, home_c = hcompetitors[0], hcompetitors[1]
    away_team  = (away_c.get("team") or {}).get("abbreviation", "")
    home_team  = (home_c.get("team") or {}).get("abbreviation", "")
    away_score = _f((away_c.get("score") or 0))
    home_score = _f((home_c.get("score") or 0))

    players = _parse_player_stats(body.get("boxscore") or {})

    # first TD scorer from scoring plays — ESPN scoringPlays don't include the scorer's name,
    # so first_td stays None (the engine treats it as "not yet known", same as mid-game).
    first_td = None

    return {
        "game_id":   espn_event_id,
        "status":    status,
        "period":    period_h,
        "clock":     clock_h,
        "home":      home_team,
        "away":      away_team,
        "home_pts":  home_score,
        "away_pts":  away_score,
        "players":   players,
        "first_td":  first_td,
    }


# ---------------------------------------------------------------------------
# lake-game → ESPN event matching
# ---------------------------------------------------------------------------

@data.lru_cache if hasattr(data, 'lru_cache') else (lambda f: f)
def _team_abbr_map() -> dict[str, str]:
    """Map common alternate abbreviations → canonical ESPN abbrev."""
    return {
        "JAX": "JAX", "JAC": "JAX",
        "WSH": "WSH", "WAS": "WSH",
        "LV":  "LV",  "OAK": "LV",
        "LAR": "LAR", "LA":  "LAR",
        "LAC": "LAC",
        "NE":  "NE",  "NEP": "NE",
        "NO":  "NO",  "NOS": "NO",
        "KC":  "KC",  "KCC": "KC",
        "TB":  "TB",  "TBB": "TB",
        "GB":  "GB",  "GBP": "GB",
        "SF":  "SF",  "SFO": "SF",
        "SEA": "SEA",
        "DEN": "DEN",
        "MIN": "MIN",
        "CHI": "CHI",
        "DET": "DET",
        "CLE": "CLE",
        "PIT": "PIT",
        "BAL": "BAL",
        "CIN": "CIN",
        "BUF": "BUF",
        "MIA": "MIA",
        "NYJ": "NYJ",
        "NYG": "NYG",
        "PHI": "PHI",
        "DAL": "DAL",
        "ARI": "ARI",
        "ATL": "ATL",
        "CAR": "CAR",
        "HOU": "HOU",
        "IND": "IND",
        "TEN": "TEN",
    }


def _canon(abbr: str) -> str:
    return _team_abbr_map().get(abbr.upper(), abbr.upper())


def find_espn_event(lake_game: dict) -> str | None:
    """
    Match a lake schedule row to an ESPN event id via team abbreviations.
    Returns ESPN event id string, or None if not found.
    """
    away = _canon(lake_game.get("away_team", ""))
    home = _canon(lake_game.get("home_team", ""))
    for g in get_scoreboard():
        if _canon(g["away"]) == away and _canon(g["home"]) == home:
            return g["game_id"]
    return None


# ---------------------------------------------------------------------------
# drop-in source for slip_alerts.poll()
# ---------------------------------------------------------------------------

def espn_source(lake_game: dict) -> dict | None:
    """
    Drop-in replacement for tank01_source.
    Looks up the ESPN event id by team abbreviation and returns a normalised
    live-game dict, or None if the event is not on the current scoreboard.
    """
    eid = find_espn_event(lake_game)
    if not eid:
        return None
    summary = get_game_summary(eid)
    if not summary:
        return None
    # Patch the game_id back to the lake's format so eval_slip can match
    summary["game_id"] = lake_game.get("game_id", eid)
    return summary


# ---------------------------------------------------------------------------
# convenience: odds for MY BOO / RAMP
# ---------------------------------------------------------------------------

def odds_by_team() -> dict[str, dict]:
    """
    {team_abbr: {spread, ou, moneyline_fav, away, home, espn_id}} for this week's games.
    Populated from the scoreboard (basic) plus game summary for games that have odds.
    """
    out: dict[str, dict] = {}
    for g in get_scoreboard():
        entry = {"spread": g["odds_spread"], "ou": g["odds_ou"],
                 "away": g["away"], "home": g["home"], "espn_id": g["game_id"]}
        out[g["away"]] = entry
        out[g["home"]] = entry
    return out


# ---------------------------------------------------------------------------
# standings, team stats, ATS, injuries, derived power ratings (all free)
# ---------------------------------------------------------------------------
_STAND_URL = "https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings?season={}"


def get_standings(season: int | None = None) -> dict[str, dict]:
    """{team_abbr: {wins, losses, ties, pf, pa, diff, games, streak, home, road, div, conf}} from ESPN standings."""
    season = season or datetime.now().year
    body = _fetch(_STAND_URL.format(season), ttl=600)
    out: dict[str, dict] = {}
    for conf in (body or {}).get("children", []):
        for e in (conf.get("standings") or {}).get("entries", []):
            abbr = (e.get("team") or {}).get("abbreviation", "")
            st = {s["name"]: s for s in e.get("stats", [])}
            val = lambda k: _f((st.get(k) or {}).get("value"))
            disp = lambda k: (st.get(k) or {}).get("displayValue", "")
            w, l, t = val("wins"), val("losses"), val("ties")
            out[abbr] = {"wins": int(w), "losses": int(l), "ties": int(t), "games": int(w + l + t),
                         "pf": val("pointsFor"), "pa": val("pointsAgainst"), "diff": val("pointDifferential") or val("differential"),
                         "streak": disp("streak"), "home": disp("Home"), "road": disp("Road"),
                         "div": disp("vs. Div."), "conf": disp("vs. Conf."), "seed": int(val("playoffSeed"))}
    return out


def derive_power_ratings() -> dict[str, dict]:
    """
    Our own live power rating from ESPN standings, no scraping: points-per-game margin vs league average,
    shrunk toward zero early in the season (few games = noisy). Same scale as TeamRankings (points above average).
    {team: {rating, rank, ppg, papg, games}}
    """
    st = get_standings()
    rows = {t: s for t, s in st.items() if s["games"] > 0}
    if not rows:
        return {}
    raw = {t: (s["pf"] - s["pa"]) / s["games"] for t, s in rows.items()}
    out = {}
    for t, s in rows.items():
        shrink = s["games"] / (s["games"] + 4)          # 3 games -> 0.43, 10 games -> 0.71, 17 -> 0.81
        out[t] = {"rating": round(raw[t] * shrink, 2), "ppg": round(s["pf"] / s["games"], 1),
                  "papg": round(s["pa"] / s["games"], 1), "games": s["games"]}
    for i, t in enumerate(sorted(out, key=lambda k: -out[k]["rating"]), 1):
        out[t]["rank"] = i
    return out


def ats_records() -> dict[str, list]:
    """{team_abbr: [record,...]} from the againstTheSpread block of each scoreboard game's summary (empty until ESPN fills it)."""
    out: dict[str, list] = {}
    for g in get_scoreboard():
        body = _fetch(_SUM_URL.format(g["game_id"]), ttl=600)
        for e in (body or {}).get("againstTheSpread", []):
            abbr = (e.get("team") or {}).get("abbreviation", "")
            recs = [{"type": (r.get("type") or r.get("name") or ""), "record": r.get("summary") or r.get("displayValue") or ""}
                    for r in e.get("records", [])]
            if abbr and recs:
                out[abbr] = recs
    return out


def injuries() -> dict[str, list[dict]]:
    """{team_abbr: [{player, status, detail}]} from each scoreboard game's summary (injury report block)."""
    out: dict[str, list[dict]] = {}
    for g in get_scoreboard():
        body = _fetch(_SUM_URL.format(g["game_id"]), ttl=600)
        for t in (body or {}).get("injuries", []):
            abbr = (t.get("team") or {}).get("abbreviation", "")
            out[abbr] = [{"player": (i.get("athlete") or {}).get("displayName", ""), "status": i.get("status", ""),
                          "detail": (i.get("details") or {}).get("type") or i.get("type", {}).get("description", "")}
                         for i in t.get("injuries", [])]
    return out


def team_game_stats(espn_event_id: str) -> dict[str, dict]:
    """{team_abbr: {stat_name: value}} - total yards, 1st downs, 3rd-down eff, turnovers, possession ... for one game."""
    body = _fetch(_SUM_URL.format(espn_event_id), ttl=600)
    out = {}
    for t in ((body or {}).get("boxscore") or {}).get("teams", []):
        out[(t.get("team") or {}).get("abbreviation", "")] = {s["name"]: s.get("displayValue") for s in t.get("statistics", [])}
    return out


def ticker() -> list[dict]:
    """Compact rows for the scrolling banner: one per game, LIVE first, then upcoming, then finals."""
    order = {"LIVE": 0, "OT": 0, "HALFTIME": 0, "PRE": 1, "FINAL": 2}
    return sorted(get_scoreboard(), key=lambda g: order.get(g["status"], 3))

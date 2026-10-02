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

LG = {"nfl": "nfl", "cfb": "college-football"}
_SITE = "https://site.api.espn.com/apis/site/v2/sports/football/{}"
_SEARCH = "https://site.web.api.espn.com/apis/search/v2?query={}&limit={}&type=article"


def headshot(athlete_id, lg: str = "nfl") -> str:
    return f"https://a.espncdn.com/i/headshots/{'nfl' if lg == 'nfl' else 'college-football'}/players/full/{athlete_id}.png"


def team_logo(team_id, abbr: str, lg: str = "nfl") -> str:
    if lg == "nfl":
        return f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr.lower()}.png"
    return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png"


def _status(st: dict) -> tuple[str, int, str]:
    t = (st.get("type") or {})
    name, desc = t.get("name", "").upper(), t.get("description", "").upper()
    period, clock = int(st.get("period") or 0), str(st.get("displayClock") or "")
    if "FINAL" in name:
        return "FINAL", period, clock
    if "HALFTIME" in name or "HALFTIME" in desc:
        return "HALFTIME", 2, clock
    if "IN_PROGRESS" in name or "LIVE" in name:
        return ("OT" if period >= 5 else "LIVE"), period, clock
    if any(k in name for k in ("POSTPONED", "CANCELED", "DELAYED", "SUSPENDED")):
        return "PRE", period, desc.title()
    return "PRE", period, clock


def scoreboard_lg(lg: str = "nfl", query: str = "", ttl: int = 60) -> list[dict]:
    """One normalized row per game for NFL ('nfl') or college ('cfb'); query e.g. 'groups=80&limit=400'."""
    body = _fetch(_SITE.format(LG[lg]) + "/scoreboard" + (f"?{query}" if query else ""), ttl=ttl)
    out = []
    for ev in (body or {}).get("events", []):
        comp = (ev.get("competitions") or [ev])[0]
        status, period, clock = _status(comp.get("status") or ev.get("status") or {})
        cs = comp.get("competitors", [])
        away = next((c for c in cs if c.get("homeAway") == "away"), {})
        home = next((c for c in cs if c.get("homeAway") == "home"), {})
        def side(c):
            t = c.get("team") or {}
            r = (c.get("curatedRank") or {}).get("current")
            recs = c.get("records") or []
            return {"abbr": t.get("abbreviation", ""), "id": str(t.get("id", "")), "name": t.get("shortDisplayName") or t.get("displayName", ""),
                    "logo": t.get("logo") or team_logo(t.get("id"), t.get("abbreviation", ""), lg),
                    "rank": r if r and r <= 25 else None, "score": int(_f(c.get("score"))), "record": (recs[0].get("summary") if recs else "")}
        a, h = side(away), side(home)
        o = (comp.get("odds") or ev.get("odds") or [{}])[0]
        ou = o.get("overUnder")
        sit = comp.get("situation") or {}
        out.append({"game_id": str(ev.get("id", "")), "lg": lg, "away": a["abbr"], "home": h["abbr"],
                    "away_score": a["score"], "home_score": h["score"], "status": status, "final": status == "FINAL",
                    "period": period, "clock": clock, "odds_spread": str(o.get("details") or ""), "odds_ou": _f(ou, None) if ou else None,
                    "away_info": a, "home_info": h, "start": ev.get("date", ""),
                    "broadcast": ", ".join(n for b in comp.get("broadcasts", []) for n in b.get("names", [])),
                    "venue": (comp.get("venue") or {}).get("fullName", ""),
                    "situation": sit.get("downDistanceText") or "", "red_zone": bool(sit.get("isRedZone")),
                    "possession": str(sit.get("possession") or "")})
    return out


def get_scoreboard() -> list[dict]:
    """
    NFL week scoreboard, one dict per game: game_id, away, home, away_score, home_score,
    status (FINAL|LIVE|HALFTIME|OT|PRE), final, period, clock, odds_spread, odds_ou
    plus logos/ranks/records (away_info, home_info), start, broadcast, venue, situation.
    """
    return scoreboard_lg("nfl")


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


# ---------------------------------------------------------------------------
# play-by-play, win probability, top performers (headshots), news
# ---------------------------------------------------------------------------

def _summary(event_id: str, lg: str, live: bool) -> dict | None:
    return _fetch(_SITE.format(LG[lg]) + f"/summary?event={event_id}", ttl=10 if live else 300)


def top_performers(body: dict, lg: str = "nfl") -> list[dict]:
    """Category leaders from the box score, with ESPN headshots: [{team, cat, name, id, headshot, line}]."""
    out = []
    for te in (body.get("boxscore") or {}).get("players", []):
        abbr = (te.get("team") or {}).get("abbreviation", "")
        for cat in te.get("statistics", []):
            if cat.get("name") not in ("passing", "rushing", "receiving"):
                continue
            ath = (cat.get("athletes") or [None])[0]
            if not ath:
                continue
            a = ath.get("athlete") or {}
            line = ", ".join(f"{v} {l}" for l, v in zip(cat.get("labels") or [], ath.get("stats") or []) if l in ("C/ATT", "YDS", "TD", "INT", "CAR", "REC"))
            out.append({"team": abbr, "cat": cat["name"], "name": a.get("displayName", ""), "id": str(a.get("id", "")),
                        "headshot": (a.get("headshot") or {}).get("href") or headshot(a.get("id"), lg), "line": line})
    return out


def game_detail(event_id: str, lg: str = "nfl", limit: int = 80) -> dict | None:
    """Everything the live game drawer needs: score, newest-first play-by-play, win-probability series, top performers."""
    body = _summary(event_id, lg, live=True)
    if not body:
        return None
    hc = ((body.get("header") or {}).get("competitions") or [{}])[0]
    status, period, clock = _status(hc.get("status") or {})
    ids, info = {}, {}
    for c in hc.get("competitors", []):
        t = c.get("team") or {}
        ids[str(t.get("id"))] = t.get("abbreviation", "")
        info[c.get("homeAway")] = {"abbr": t.get("abbreviation", ""), "name": t.get("displayName", ""), "score": int(_f(c.get("score"))),
                                   "logo": t.get("logos", [{}])[0].get("href") if t.get("logos") else team_logo(t.get("id"), t.get("abbreviation", ""), lg),
                                   "rank": (c.get("rank") if isinstance(c.get("rank"), int) and c.get("rank", 99) <= 25 else None)}
    drives = body.get("drives") or {}
    dlist = list(drives.get("previous", [])) + ([drives["current"]] if drives.get("current") else [])
    plays = []
    for d in dlist:
        for p in d.get("plays", []):
            end = p.get("end") or {}
            plays.append({"id": str(p.get("id", "")), "text": p.get("text", ""), "type": (p.get("type") or {}).get("text", ""),
                          "period": (p.get("period") or {}).get("number", 0), "clock": (p.get("clock") or {}).get("displayValue", ""),
                          "team": ids.get(str(((p.get("start") or {}).get("team") or {}).get("id")), ""),
                          "down": end.get("downDistanceText") or "", "yards": p.get("statYardage"),
                          "scoring": bool(p.get("scoringPlay")), "away_score": p.get("awayScore"), "home_score": p.get("homeScore"),
                          "seq": int(_f(p.get("sequenceNumber"), 0))})
    plays.sort(key=lambda p: p["seq"])
    last = plays[-1] if plays else {}
    wp = [round(_f(w.get("homeWinPercentage")) * 100, 1) for w in (body.get("winprobability") or [])]
    if len(wp) > 90:
        step = len(wp) / 90
        wp = [wp[int(i * step)] for i in range(90)] + [wp[-1]]
    return {"game_id": event_id, "lg": lg, "status": status, "period": period, "clock": clock, "away": info.get("away", {}), "home": info.get("home", {}),
            "situation": last.get("down", "") if status in ("LIVE", "OT") else "", "plays": plays[::-1][:limit], "total_plays": len(plays),
            "win_prob_home": wp, "performers": top_performers(body, lg),
            "spread": ((body.get("pickcenter") or [{}])[0] or {}).get("details", ""), "ou": ((body.get("pickcenter") or [{}])[0] or {}).get("overUnder")}


def news(lg: str = "cfb", limit: int = 50) -> list[dict]:
    """ESPN news articles: [{id, headline, description, published, link, image, teams:[team ids], teamNames:[...]}]."""
    body = _fetch(_SITE.format(LG[lg]) + f"/news?limit={limit}", ttl=300)
    out = []
    for a in (body or {}).get("articles", []):
        cats = a.get("categories", [])
        out.append({"id": str(a.get("id") or a.get("dataSourceIdentifier") or a.get("headline")), "headline": a.get("headline", ""),
                    "description": a.get("description", ""), "published": a.get("published", ""),
                    "link": ((a.get("links") or {}).get("web") or {}).get("href", ""),
                    "image": (a.get("images") or [{}])[0].get("url", ""),
                    "teams": [str(c.get("teamId") or (c.get("team") or {}).get("id")) for c in cats if c.get("type") == "team" and (c.get("teamId") or c.get("team"))],
                    "teamNames": [c.get("description", "") for c in cats if c.get("type") == "team"]})
    return out


def search_news(query: str, limit: int = 15) -> list[dict]:
    """ESPN article search (used for 'transfer portal' and 'SEC')."""
    from urllib.parse import quote
    body = _fetch(_SEARCH.format(quote(query), limit), ttl=600)
    out = []
    for g in (body or {}).get("results", []):
        for c in g.get("contents", []):
            link = c.get("link")
            link = link.get("web") if isinstance(link, dict) else (link or "")
            img = c.get("image")
            img = (img.get("default") or img.get("url") or "") if isinstance(img, dict) else (img or "")
            out.append({"id": str(c.get("id") or link), "headline": c.get("displayName") or c.get("title") or "",
                        "description": c.get("description") or c.get("subtitle") or "", "published": c.get("date") or c.get("lastModified") or "",
                        "link": link, "image": img, "teams": [], "teamNames": []})
    return out

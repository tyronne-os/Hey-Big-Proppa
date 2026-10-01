"""
BIG PROPPA LINE (BPL) -- the official Big Proppa line. Lake data only.

A sportsbook number is never an input. Books appear only AFTER the line is
built, as the comparison column (SL). No LLM touches this file's output.

Method (identical for NFL player props, NFL game totals and CFB game totals):

    baseline = recency-weighted per-game average this season, shrunk toward the
               previous-season per-game average with K_PRIOR games of weight
    opp      = 1 + OPP_WEIGHT * (opponent allowed per game / league average - 1),
               where opponent allowed is shrunk toward its previous season (K_OPP)
    home     = calibrated home/away multiplier
    BPL      = baseline * opp * home, rounded to the nearest 0.5

Constants below are FROZEN. They were fit once, walk-forward, on 2024-2025 NFL
play by play (2023 feeding priors) by scripts/build_bpl_calibration.py.
The home/away multiplier also converts the projected average into the 50/50
point (the median), because that is what a line is: yardage is right-skewed,
so an average-based line would sit over the book on nearly every player.
Backtest (lower error is better; over rate should be ~50%):
    rush yds    error 24.22 vs 25.57 plain average (-5.3%)  over 48.6%
    rec yds     error 23.66 vs 25.71 (-8.0%)                 over 49.0%
    receptions  error  1.70 vs  1.81 (-6.2%)                 over 49.3%
    pass yds    error 61.81 vs 64.38 (-4.0%)                 over 50.8%
    team points error  7.57 vs  7.96 (-5.0%)                 over 49.7%
    game totals (sum of both teams)                          over 49.4%
CFB uses the same method with its own constants (FBS vs FBS, 2024-2025 CFBD):
    team points error  9.30 vs 11.03 (-15.7%)                over 49.7%
    game totals                                              over 50.8%
Change a constant only by rerunning the calibration.
"""
from __future__ import annotations

import datetime as dt
import statistics
from functools import lru_cache

import data

BPL_VERSION = "BPL 1.0 (2026-09-26)"

PARAMS: dict[str, dict] = {
    "rushyds": {"decay": 0.9, "k_prior": 2, "k_opp": 4, "opp_weight": 0.25, "home": {0: 0.8663, 1: 0.8925}},
    "recyds":  {"decay": 0.9, "k_prior": 4, "k_opp": 2, "opp_weight": 0.50, "home": {0: 0.8352, 1: 0.8828}},
    "recs":    {"decay": 0.8, "k_prior": 3, "k_opp": 4, "opp_weight": 0.50, "home": {0: 0.9007, 1: 0.9092}},
    "passyds": {"decay": 1.0, "k_prior": 2, "k_opp": 2, "opp_weight": 0.25, "home": {0: 0.9938, 1: 1.0261}},
    "points":  {"decay": 1.0, "k_prior": 4, "k_opp": 6, "opp_weight": 0.50, "home": {0: 0.9704, 1: 1.0395}},
    # CFB, FBS vs FBS (scripts/build_bpl_cfb_calibration.py). home key: 1 home, 0 neutral, -1 away
    "cfb_points": {"decay": 0.9, "k_prior": 3, "k_opp": 4, "opp_weight": 0.75, "home": {1: 1.0532, 0: 0.9813, -1: 0.9268}},
}

# market -> (weekly gold csv, stat column, opponent-allowed category)
NFL_MARKETS = {
    "rushyds": ("player_rushing_week", "rushing_yards", "rush_yds"),
    "recyds":  ("player_receiving_week", "receiving_yards", "pass_yds"),
    "recs":    ("player_receiving_week", "receptions", "completions"),
    "passyds": ("player_passing_week", "passing_yards", "pass_yds"),
}
# team_week column behind each allowed category
_TEAM_WEEK_COL = {"rush_yds": "rushing_yards", "pass_yds": "passing_yards", "completions": "completions"}

LEADER_MARKET = {"RUSHING": "rushyds", "RECEIVING": "recyds", "PASSING": "passyds"}


# ---------------------------------------------------------------------------
# Core -- shared by every sport and market
# ---------------------------------------------------------------------------

def round_half(x: float) -> float:
    return round(x * 2) / 2


def core_line(market: str, history: list[float], prior: float | None,
              opp_history: list[float], opp_prior: float | None,
              league_allowed: float, home: int | None) -> dict | None:
    """history/opp_history oldest -> newest. Returns the line plus its parts."""
    p = PARAMS[market]
    if not history and prior is None:
        return None
    n = len(history)
    weights = [p["decay"] ** (n - 1 - i) for i in range(n)]
    s = sum(w * v for w, v in zip(weights, history))
    w = sum(weights)
    baseline = (s + p["k_prior"] * prior) / (w + p["k_prior"]) if prior is not None else s / w

    if opp_prior is not None:
        opp_allowed = (sum(opp_history) + p["k_opp"] * opp_prior) / (len(opp_history) + p["k_opp"])
    elif opp_history:
        opp_allowed = sum(opp_history) / len(opp_history)
    else:
        opp_allowed = league_allowed
    opp = 1 + p["opp_weight"] * (opp_allowed / league_allowed - 1) if league_allowed else 1.0
    home_mult = p["home"].get(home, 1.0) if home is not None else 1.0

    raw = baseline * opp * home_mult
    return {
        "line": round_half(raw),
        "raw": round(raw, 2),
        "baseline": round(baseline, 2),
        "oppFactor": round(opp, 4),
        "homeFactor": home_mult,
        "oppAllowed": round(opp_allowed, 2),
    }


def diff_pct(bpl: float | None, sl: float | None) -> float | None:
    if bpl is None or not sl:
        return None
    return round((bpl - sl) / sl * 100, 1)


# ---------------------------------------------------------------------------
# NFL lake inputs
# ---------------------------------------------------------------------------

def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@lru_cache(maxsize=1)
def _current_season() -> int:
    return max(int(r["season"]) for r in data.load("schedule"))


@lru_cache(maxsize=8)
def _player_history(market: str) -> dict[str, list[dict]]:
    src, col, _ = NFL_MARKETS[market]
    season = str(_current_season())
    out: dict[str, list[dict]] = {}
    for r in data.load(src):
        if r.get("season") != season or r.get("season_type", "REG") != "REG":
            continue
        out.setdefault(r["player_id"], []).append({
            "week": int(r["week"]), "value": _f(r.get(col)),
            "team": r.get("team", ""), "opp": r.get("opponent_team", ""),
        })
    for games in out.values():
        games.sort(key=lambda g: g["week"])
    return out


@lru_cache(maxsize=1)
def _player_priors() -> dict[tuple[str, str], float]:
    return {(r["market"], r["player_id"]): _f(r["per_game"]) for r in data.load("bpl_player_prior")}


@lru_cache(maxsize=1)
def _team_priors() -> dict[str, dict]:
    return {r["team"]: r for r in data.load("bpl_team_prior")}


@lru_cache(maxsize=1)
def _team_allowed_history() -> dict[str, dict[str, list[float]]]:
    """defense team -> category -> allowed per game this season (oldest first)."""
    season = str(_current_season())
    rows = sorted((r for r in data.load("team_week") if r.get("season") == season), key=lambda r: int(r["week"]))
    out: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        d = out.setdefault(r["opponent_team"], {c: [] for c in _TEAM_WEEK_COL})
        for cat, col in _TEAM_WEEK_COL.items():
            d[cat].append(_f(r.get(col)))
    return out


def _league_allowed(cat: str) -> float:
    vals = [_f(t.get(f"allowed_{cat}")) for t in _team_priors().values()]
    return sum(vals) / len(vals) if vals else 0.0


@lru_cache(maxsize=1)
def _last_played_week() -> dict[str, int]:
    """team -> latest week with box-score stats (the schedule score can lag a day)."""
    season = str(_current_season())
    out: dict[str, int] = {}
    for src in ("player_rushing_week", "player_passing_week"):
        for r in data.load(src):
            if r.get("season") == season:
                out[r["team"]] = max(out.get(r["team"], 0), int(r["week"]))
    return out


@lru_cache(maxsize=1)
def next_games() -> dict[str, dict]:
    """team -> its next unplayed game {opp, home, week, gameId, totalLine}."""
    played = _last_played_week()
    out: dict[str, dict] = {}
    for g in sorted(data.load("schedule"), key=lambda r: (int(r["week"]), r.get("game_date", ""))):
        if g.get("game_type") != "REG" or g.get("home_score") not in ("", None):
            continue
        if g.get("game_date", "9999") < dt.date.today().isoformat():
            continue
        if int(g["week"]) <= max(played.get(g["home_team"], 0), played.get(g["away_team"], 0)):
            continue
        for team, opp, home in ((g["home_team"], g["away_team"], 1), (g["away_team"], g["home_team"], 0)):
            out.setdefault(team, {"opp": opp, "home": home, "week": int(g["week"]),
                                  "gameId": g["game_id"], "totalLine": _f(g.get("total_line")) or None})
    return out


def _opp_allowed_blend(team: str, cat: str) -> float:
    p = _team_priors().get(team)
    prior = _f(p.get(f"allowed_{cat}")) if p else None
    hist = _team_allowed_history().get(team, {}).get(cat, [])
    k = 3
    if prior is not None:
        return (sum(hist) + k * prior) / (len(hist) + k)
    return sum(hist) / len(hist) if hist else _league_allowed(cat)


@lru_cache(maxsize=8)
def defense_ranks(cat: str) -> dict[str, int]:
    """1 = stingiest defense in this category (fewest allowed per game, prior-blended)."""
    teams = set(_team_priors()) | set(_team_allowed_history())
    ordered = sorted(teams, key=lambda t: _opp_allowed_blend(t, cat))
    return {t: i for i, t in enumerate(ordered, start=1)}


@lru_cache(maxsize=1)
def _book_lines() -> dict[tuple[str, str, str], dict]:
    """(market, normalized name, team) -> consensus (median) sportsbook line across books."""
    raw: dict[tuple[str, str, str], list[tuple[str, float]]] = {}
    for r in data.load("prop_line_rotowire"):
        if r.get("market_slug") not in NFL_MARKETS or not r.get("line"):
            continue
        key = (r["market_slug"], data.normalize_name(r.get("player_name", "")), r.get("team", ""))
        raw.setdefault(key, []).append((r.get("book_slug", ""), _f(r["line"])))
    return {k: {"line": statistics.median(v for _, v in rows), "books": sorted({b for b, _ in rows})}
            for k, rows in raw.items()}


# ---------------------------------------------------------------------------
# NFL public API
# ---------------------------------------------------------------------------

def nfl_player_line(player_id: str, market: str, name: str = "", team: str = "") -> dict:
    """Full BPL row for one player and market."""
    _, _, cat = NFL_MARKETS[market]
    games = _player_history(market).get(player_id, [])
    team = team or (games[-1]["team"] if games else "")
    values = [g["value"] for g in games]
    nxt = next_games().get(team)

    row: dict = {
        "market": market,
        "seasonAvg": round(sum(values) / len(values), 1) if values else None,
        "l5": [{"week": g["week"], "opp": g["opp"], "value": g["value"]} for g in games[-5:]],
        "nextOpp": None, "nextOppHome": None, "nextOppRank": None,
        "sportsbookLine": None, "books": [], "bpl": None, "diffPct": None, "parts": None,
        "version": BPL_VERSION,
    }
    if nxt:
        opp = nxt["opp"]
        row["nextOpp"] = opp
        row["nextOppHome"] = bool(nxt["home"])
        row["nextOppRank"] = defense_ranks(cat).get(opp)
        p = _team_priors().get(opp)
        parts = core_line(
            market, values, _player_priors().get((market, player_id)),
            _team_allowed_history().get(opp, {}).get(cat, []),
            _f(p.get(f"allowed_{cat}")) if p else None,
            _league_allowed(cat), nxt["home"],
        )
        if parts:
            row["bpl"] = parts["line"]
            row["parts"] = parts
    book = _book_lines().get((market, data.normalize_name(name), team)) if name else None
    if book:
        row["sportsbookLine"] = book["line"]
        row["books"] = book["books"]
    row["diffPct"] = diff_pct(row["bpl"], row["sportsbookLine"])
    return row


@lru_cache(maxsize=1)
def _team_points_history() -> dict[str, dict[str, list[float]]]:
    season = str(_current_season())
    out: dict[str, dict[str, list[float]]] = {}
    games = sorted((g for g in data.load("schedule") if g.get("season") == season and g.get("home_score") not in ("", None)),
                   key=lambda g: int(g["week"]))
    for g in games:
        hs, as_ = _f(g["home_score"]), _f(g["away_score"])
        for team, scored, allowed in ((g["home_team"], hs, as_), (g["away_team"], as_, hs)):
            d = out.setdefault(team, {"scored": [], "allowed": []})
            d["scored"].append(scored)
            d["allowed"].append(allowed)
    return out


def nfl_team_points(team: str, opp: str, home: int) -> dict | None:
    hist = _team_points_history()
    pri = _team_priors()
    league = sum(_f(t["allowed_points"]) for t in pri.values()) / len(pri) if pri else 0.0
    tp, op = pri.get(team), pri.get(opp)
    return core_line("points", hist.get(team, {}).get("scored", []), _f(tp["scored_points"]) if tp else None,
                     hist.get(opp, {}).get("allowed", []), _f(op["allowed_points"]) if op else None, league, home)


def nfl_game_totals() -> list[dict]:
    """BPL combined-score total for every unplayed game in the next week, vs the book total."""
    seen, out = set(), []
    for team, g in next_games().items():
        if g["gameId"] in seen or not g["home"]:
            continue
        seen.add(g["gameId"])
        home_pts = nfl_team_points(team, g["opp"], 1)
        away_pts = nfl_team_points(g["opp"], team, 0)
        if not home_pts or not away_pts:
            continue
        total = round_half(home_pts["raw"] + away_pts["raw"])
        out.append({
            "gameId": g["gameId"], "week": g["week"], "home": team, "away": g["opp"],
            "homePoints": home_pts["raw"], "awayPoints": away_pts["raw"],
            "bpl": total, "sportsbookLine": g["totalLine"], "diffPct": diff_pct(total, g["totalLine"]),
            "version": BPL_VERSION,
        })
    return sorted(out, key=lambda r: (r["week"], r["gameId"]))


# ---------------------------------------------------------------------------
# CFB -- same core, CFBD game scores as the lake input
# ---------------------------------------------------------------------------

def _cfb_team_points(games: list[dict]) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = {}
    for g in sorted(games, key=lambda g: g.get("week", 0)):
        if not g.get("completed") or g.get("homePoints") is None or g.get("awayPoints") is None:
            continue
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
            continue
        hs, as_ = float(g["homePoints"]), float(g["awayPoints"])
        for team, scored, allowed in ((g["homeTeam"], hs, as_), (g["awayTeam"], as_, hs)):
            d = out.setdefault(team, {"scored": [], "allowed": []})
            d["scored"].append(scored)
            d["allowed"].append(allowed)
    return out


_cfb_points_cache: dict[int, tuple[dict, float]] = {}


def _cfb_points_for(year: int) -> dict[str, dict[str, list[float]]]:
    import time
    import cfb_data
    hit = _cfb_points_cache.get(year)
    if hit and time.time() < hit[1]:
        return hit[0]
    parsed: dict = {}
    for _ in range(2):  # CFBD sometimes fails the first cold call
        parsed = _cfb_team_points(cfb_data._get_cached("/games", {"year": year, "seasonType": "regular"}) or [])
        if parsed:
            break
    if parsed:
        _cfb_points_cache[year] = (parsed, time.time() + 900)
    return parsed


def cfb_game_total(home: str, away: str, neutral: bool = False) -> dict | None:
    import cfb_data
    year = cfb_data._current_season()
    cur = _cfb_points_for(year)
    prev = _cfb_points_for(year - 1)
    if not prev:
        return None

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    league = mean([v for t in prev.values() for v in t["allowed"]])

    def side(team, opp, home_flag):
        return core_line("cfb_points", cur.get(team, {}).get("scored", []), mean(prev.get(team, {}).get("scored", [])),
                         cur.get(opp, {}).get("allowed", []), mean(prev.get(opp, {}).get("allowed", [])),
                         league, 0 if neutral else home_flag)

    h, a = side(home, away, 1), side(away, home, -1)
    if not h or not a:
        return None
    return {"home": home, "away": away, "homePoints": h["raw"], "awayPoints": a["raw"],
            "bpl": round_half(h["raw"] + a["raw"]), "version": BPL_VERSION}

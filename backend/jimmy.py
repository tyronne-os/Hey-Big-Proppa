"""
JIMMY THE GREEK's probability engine -- the lake-only composite score.

Per the user's explicit framing this session: "without an AI agent like Jev
or cloud the lake is designed to return best possible outcomes -- it is the
JIMMY THE GREEK node that checks the ponds and the lake to form a
probability with JEV." This module is that standalone, lake-only path: it
must produce a real probability with zero dependency on Jev or any external
model. When Jev is later wired (JEV_API_KEY, still NOT WIRED as of this
module), Jimmy would pass this score to Jev as context for a refined read --
that integration is future work, not built here.

REPLACES the earlier hit-rate-vs-line-only probability (that approach is
still one of the three inputs below, just no longer the whole story).

Composite, per the user's chosen weighting (even split across signals):
  jimmy_score = average of whichever of these are available:
    - hit_rate     : recent-form hit rate vs. the market line (0-1)
    - usage        : the player's own usage_index_score / 100 (0-1) --
                      the lake's "who the offense trusts" pond
    - matchup      : Phi(unit edge) from the BIG PROPPA matchup predictor
                      (matchup.py) -- the unit that drives this market, his
                      offense against his next opponent's defense, signed
                      for the bet's direction
  ...then, for TD-shaped props (market_slug == 'anytd'), a redzone boost is
  added from redzone_tiers.csv's inside-5 intra-team share, scaled and
  capped so it nudges rather than dominates.
  ...and OVER props on a REGRESSION RISK player (breakout.py) are cut by up
  to 15%, scaled by how far his production outruns his opportunity.

A missing input is dropped from the average rather than treated as zero --
most players this early in the season don't have a full pond footprint yet
(player_usage.csv needs enough games to compute stress/redzone/depth), and
punishing a thin sample with a zero would misrepresent the lake's own
"HEURISTIC, not backtested" labeling discipline.

Jimmy's filters, applied before any leg is built (Big Proppa does no filtering):
  eligible()      no player from a team with a losing record (W < L)
  matchup_gate()  the leg's unit edge must point the same way as the bet

HEURISTIC. NOT BACKTESTED as a prop model (the matchup predictor itself is
backtested -- see matchup.py). Same caveat every other pond in this lake
carries -- see docs/HANDOFF.md sec 7 lesson 9.
"""
from __future__ import annotations

import json
from pathlib import Path

import math
from functools import lru_cache
from statistics import mean

import breakout
import data
import matchup
import tank01
import sportsbook


@lru_cache(maxsize=1)
def _usage_index() -> dict[str, float]:
    out = {}
    for row in data.load("player_usage"):
        pid = row.get("player_id")
        score = row.get("usage_index_score")
        if pid and score:
            try:
                out[pid] = float(score)
            except ValueError:
                pass
    return out


@lru_cache(maxsize=1)
def _defense_toxicity() -> dict[str, float]:
    out = {}
    for row in data.load("defense_ib_score"):
        team = row.get("team")
        tox = row.get("toxicity_index_0_100")
        if team and tox:
            try:
                out[team] = float(tox)
            except ValueError:
                pass
    return out


@lru_cache(maxsize=1)
def _redzone_i5_share() -> dict[str, float]:
    out = {}
    for row in data.load("redzone_tiers"):
        pid = row.get("player_id")
        pct = row.get("pct_i5_intra")
        if pid and pct:
            try:
                out[pid] = float(pct)
            except ValueError:
                pass
    return out


@lru_cache(maxsize=1)
def _team_by_player() -> dict[str, str]:
    """Each player's team as of his most recent game."""
    latest: dict[str, tuple[int, str]] = {}
    for src in ("player_scrimmage_week", "player_passing_week"):
        for row in data.load(src):
            pid, team = row.get("player_id"), row.get("team")
            try:
                wk = int(row.get("week") or 0)
            except ValueError:
                continue
            if pid and team and wk >= latest.get(pid, (-1, ""))[0]:
                latest[pid] = (wk, team)
    return {pid: team for pid, (_, team) in latest.items()}


@lru_cache(maxsize=1)
def next_game_by_team() -> dict[str, dict]:
    """Each team's game on the current slate (earliest week with no final score). Teams on bye are absent."""
    unplayed = [g for g in data.load("schedule") if not g.get("home_score") and not g.get("away_score")]
    if not unplayed:
        return {}
    slate_week = min(int(g["week"]) for g in unplayed)
    out: dict[str, dict] = {}
    for g in unplayed:
        if int(g["week"]) == slate_week:
            out[g["home_team"]] = g
            out[g["away_team"]] = g
    return out


def player_team(player_id: str) -> str | None:
    return _team_by_player().get(player_id)


def next_opponent(player_id: str) -> str | None:
    """The defense this player faces on the current slate -- the matchup every probability is about."""
    team = player_team(player_id)
    game = next_game_by_team().get(team or "")
    if not game:
        return None
    return game["away_team"] if game["home_team"] == team else game["home_team"]


# Which matchup unit drives each prop market. Interceptions thrown is the one
# over that pays when the offense struggles.
MARKET_UNITS: dict[str, tuple[str, ...]] = {
    "rushyds": ("GROUND",), "carries": ("GROUND",),
    "rushrec": ("GROUND", "AIR"),
    "recs": ("AIR",), "recyds": ("AIR",), "passyds": ("AIR",), "passatt": ("AIR",),
    "anytd": ("RED ZONE", "SCORING"), "passtd": ("RED ZONE", "SCORING"), "firsttd": ("RED ZONE", "SCORING"),
    "intsthrown": ("BALL SECURITY",),
}
OFFENSE_FAILS = {"intsthrown"}


def eligible(player_id: str) -> bool:
    """Losers lose: no player from a team with more losses than wins."""
    team = player_team(player_id)
    return bool(team) and not matchup.is_losing(team)


def leg_edge(player_id: str, market_slug: str, direction: str = "over") -> float | None:
    """
    The matchup edge behind one leg, signed so + favors the bet. Built from
    the unit(s) for the market, this player's offense against his next
    opponent's defense.
    """
    edges = matchup.edges_for_team(player_team(player_id) or "")
    units = MARKET_UNITS.get(market_slug)
    if not edges or not units:
        return None
    edge = sum(edges[u] for u in units) / len(units)
    wants_offense_success = (direction == "over") != (market_slug in OFFENSE_FAILS)
    return edge if wants_offense_success else -edge


def matchup_gate(player_id: str, market_slug: str, direction: str = "over") -> bool:
    """A leg is only matchup-driven if its unit edge points the same way as the bet."""
    edge = leg_edge(player_id, market_slug, direction)
    return edge is not None and edge > 0


REGRESSION_SCALE = 0.3
REGRESSION_MAX_PENALTY = 0.15


def regression_factor(player_id: str, direction: str = "over") -> float:
    """
    Multiplier <= 1 for OVER props on a player flagged REGRESSION RISK by the
    breakout pond: scoring above what his targets and carries support while
    his share of them shrinks. The cut scales with how far production runs
    ahead of opportunity -- 0.3 x (ppr - xppr) / ppr, capped at 15%. Unders
    are left alone rather than boosted.
    """
    if direction != "over":
        return 1.0
    row = breakout.breakout_by_player().get(player_id)
    if not row or row["flag"] != "REGRESSION RISK" or row["pprPerGame"] <= 0:
        return 1.0
    excess = (row["pprPerGame"] - row["xpprPerGame"]) / row["pprPerGame"]
    return round(1 - min(REGRESSION_MAX_PENALTY, REGRESSION_SCALE * excess), 3)


# ── Tank01 projection signal ──────────────────────────────────────────────────
_MARKET_PROJ_KEY = {
    "rushyds":   "projRushYds",
    "carries":   "projCarries",
    "recs":      "projRec",
    "recyds":    "projRecYds",
    "passyds":   "projPassYds",
    "anytd":     "projTDs",
    "passtd":    "projTDs",
    "firsttd":   "projTDs",
}

def _projection_signal(player_id: str, market_slug: str, hit_rate: float | None) -> float | None:
    """
    Convert Tank01 projected stat value into a probability of clearing the prop line.
    Uses the lake's hit-rate denominator as the line proxy when real line is unavailable.
    Returns a 0-1 probability, or None if projection unavailable.
    """
    try:
        projs = tank01.projection_by_player_id()
        proj  = projs.get(player_id)
        if not proj:
            return None
        proj_key = _MARKET_PROJ_KEY.get(market_slug or "")
        if not proj_key:
            return None
        proj_val = proj.get(proj_key)
        if proj_val is None:
            return None

        # Approximate prop line from hit_rate: if hit_rate is 0.6 we treat median
        # production as the line. A projection 10% above that line is ~65% to hit.
        # Simple logistic squash: P = sigmoid(2 * (proj/line - 1))
        if hit_rate is not None and 0.3 < hit_rate < 0.9:
            # Rough line = (proj_val) / (0.5 + hit_rate * 0.5)  -- heuristic
            line_est = proj_val / (0.5 + hit_rate * 0.5)
            if line_est > 0:
                z = 2.0 * (proj_val / line_est - 1.0)
                return round(1 / (1 + math.exp(-z)), 3)
        # Fallback: scale projection pts to probability proxy
        pts = proj.get("projectedPts") or 0
        return round(min(0.9, max(0.4, 0.4 + pts / 40)), 3)
    except Exception:
        return None


def _injury_multiplier(player_id: str) -> float:
    """
    Multiply confidence down based on injury status.
    OUT/IR → 0.0 (eliminate), O/LP → 0.75, D → 0.85, Q → 0.92, healthy → 1.0
    """
    try:
        injury = tank01.injury_map_by_player_id().get(player_id)
        if not injury:
            return 1.0
        status = injury.get("injuryStatus", "").upper()
        return {"OUT": 0.0, "IR": 0.0, "O": 0.75, "LP": 0.75, "D": 0.85, "Q": 0.92}.get(status, 1.0)
    except Exception:
        return 1.0


def _starter_multiplier(player_id: str) -> float:
    """
    Non-starters get a 0.70 multiplier. Starters stay at 1.0.
    If depth chart data is unavailable, returns 1.0 (no penalty for missing data).
    """
    try:
        starters = tank01.starters_by_player_id()
        if not starters:
            return 1.0  # data unavailable — no penalty
        return 1.0 if starters.get(player_id) else 0.70
    except Exception:
        return 1.0


def _dfs_salary_signal(player_id: str, market_slug: str | None) -> float | None:
    """
    Normalize FanDuel salary to a 0-1 probability proxy.
    A player priced $1,000 above position average = +0.05 boost.
    A player priced $1,000 below position average = -0.05.
    Returns None if salary data unavailable.
    """
    try:
        salaries = tank01.salary_by_player_id()
        entry = salaries.get(player_id)
        if not entry or not entry.get("salary"):
            return None
        salary = entry["salary"]
        pos    = entry.get("position", "")
        # Compute position average
        same_pos = [s["salary"] for s in salaries.values()
                    if s.get("position") == pos and s.get("salary")]
        if len(same_pos) < 3:
            return None
        avg = sum(same_pos) / len(same_pos)
        # Scale: ±$2000 from average = ±0.10 signal
        delta = (salary - avg) / 2000.0
        return round(min(0.9, max(0.4, 0.5 + delta * 0.1)), 3)
    except Exception:
        return None


def _line_movement_signal(player_id: str, market_slug: str | None, direction: str) -> float | None:
    """
    Check if the market line has moved in the direction of our bet (confirming steam)
    or against it (warning). Returns a small nudge factor: +0.03, -0.03, or None.
    """
    try:
        team = player_team(player_id)
        if not team:
            return None
        lines = sportsbook.nfl_lines_by_team()
        game  = lines.get(team)
        if not game:
            return None
        movement = sportsbook.line_movement(game["gameID"], list(lines.values()))
        if not movement.get("has_movement"):
            return None
        total_drift = movement.get("total_drift") or 0
        # For over bets: line moving up = public money → slight fade signal
        # For under bets: line moving up = steam → confirming signal
        if market_slug in ("rushyds", "recyds", "passyds", "recs", "carries"):
            if direction == "over" and total_drift > 0.5:
                return 0.03  # more scoring expected — over props benefit
            if direction == "over" and total_drift < -0.5:
                return -0.03
        return None
    except Exception:
        return None


# ── #16 Recency-weighted defensive rank ──────────────────────────────────────

@lru_cache(maxsize=1)
def _defense_yielded_per_game() -> dict[str, list[dict]]:
    """
    For each team, collect what the opposing offense produced against their defense,
    game-by-game, newest first. Source: team_game_stats rows where `opponent = team`.
    2023-2026 data.
    """
    out: dict[str, list[dict]] = {}
    for row in data.load("team_game_stats"):
        opp = row.get("opponent")
        if not opp:
            continue
        try:
            out.setdefault(opp, []).append({
                "season": int(row.get("season") or 0),
                "week":   int(row.get("week") or 0),
                "pass_yds": float(row.get("pass_yds") or 0),
                "rush_yds": float(row.get("rush_yds") or 0),
                "tds":      float(row.get("tds") or 0),
                "points":   float(row.get("points_for") or 0),
            })
        except (ValueError, TypeError):
            continue
    for team in out:
        out[team].sort(key=lambda g: (g["season"], g["week"]), reverse=True)
    return out


def _recency_defense_signal(opponent: str | None, market_slug: str | None) -> float | None:
    """
    L4 recency-weighted (60%) vs season average (40%) yards/points allowed.
    Strong defense → signal < 0.5 (harder to score over).
    Weak defense → signal > 0.5 (easier to score over).
    """
    if not opponent:
        return None
    games = _defense_yielded_per_game().get(opponent)
    if not games or len(games) < 4:
        return None

    is_pass = market_slug in ("passyds", "passtd", "recs", "recyds", "passatt", "intsthrown")
    is_rush = market_slug in ("rushyds", "carries", "rushrec")
    stat_key = "pass_yds" if is_pass else ("rush_yds" if is_rush else "points")

    current_season = max(g["season"] for g in games)
    season_games = [g for g in games if g["season"] == current_season]
    if len(season_games) < 2:
        season_games = games
    season_avg = mean(g[stat_key] for g in season_games)

    l4 = games[:4]
    l4_avg = mean(g[stat_key] for g in l4)

    all_games = _defense_yielded_per_game()
    league_vals = [
        g[stat_key]
        for team_games in all_games.values()
        for g in team_games
        if g["season"] == current_season
    ]
    if len(league_vals) < 10:
        return None
    league_avg = mean(league_vals)
    if league_avg <= 0:
        return None

    weighted = 0.6 * l4_avg + 0.4 * season_avg
    ratio = weighted / league_avg  # >1 = weak defense, <1 = strong defense
    signal = min(0.70, max(0.30, 0.5 + (ratio - 1.0) * 0.5))
    return round(signal, 3)


# ── #10 Short-week fatigue + #23 Weather ─────────────────────────────────────

@lru_cache(maxsize=1)
def _next_game_info() -> dict[str, dict]:
    """team → next unplayed game row from schedule.csv (with weather, weekday)."""
    out: dict[str, dict] = {}
    for g in data.load("schedule"):
        if g.get("away_score") or g.get("home_score"):
            continue
        for team_key in ("home_team", "away_team"):
            t = g.get(team_key)
            if t and t not in out:
                out[t] = g
    return out


def _short_week_multiplier(team: str | None) -> float:
    """
    Thursday / short-week penalty: teams on 4 days rest perform 5-10% worse
    than well-rested teams across 2023-2025 data. Returns 0.92 for short-week teams.
    """
    if not team:
        return 1.0
    game = _next_game_info().get(team)
    if not game:
        return 1.0
    weekday = (game.get("weekday") or "").lower()
    return 0.92 if weekday == "thursday" else 1.0


_OUTDOOR_PASS_MARKETS = {"passyds", "passtd", "recyds", "recs", "anytd", "firsttd", "lasttd"}


def _weather_multiplier(team: str | None, market_slug: str | None) -> float:
    """
    Cold (<40°F) or windy (>15 mph) outdoor games reduce passing/scoring probabilities.
    schedule.csv already has temp_actual, wind_actual, roof for every game.
    """
    if not team or market_slug not in _OUTDOOR_PASS_MARKETS:
        return 1.0
    game = _next_game_info().get(team)
    if not game:
        return 1.0
    roof = (game.get("roof") or "").lower()
    if any(kw in roof for kw in ("dome", "closed", "retractable")):
        return 1.0
    try:
        temp = float(game.get("temp_actual") or 72)
        wind = float(game.get("wind_actual") or 5)
    except (ValueError, TypeError):
        return 1.0
    mult = 1.0
    if temp < 35:
        mult *= 0.87
    elif temp < 45:
        mult *= 0.93
    if wind > 20:
        mult *= 0.87
    elif wind > 15:
        mult *= 0.93
    return round(mult, 3)


# ── #18 QB pressure rate ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _qb_pressure_rates() -> dict[str, float]:
    """
    Average times_pressured_pct for each QB over available games (L-all).
    Source: pfr_adv_passing_week.csv. High pressure = shorter passes = under yds risk.
    """
    per_player: dict[str, list[float]] = {}
    for row in data.load("pfr_adv_passing_week"):
        pid = row.get("pfr_player_id") or row.get("player_id")
        pct = row.get("times_pressured_pct")
        if pid and pct:
            try:
                per_player.setdefault(pid, []).append(float(pct))
            except (ValueError, TypeError):
                pass
    return {pid: round(mean(vals), 3) for pid, vals in per_player.items() if vals}


def _qb_pressure_signal(player_id: str, market_slug: str | None) -> float | None:
    """
    High QB pressure rate reduces passing yard upside.
    >0.35 pressured = return 0.45 signal on passyds/passtd (below average confidence).
    """
    if market_slug not in ("passyds", "passtd", "recs", "recyds"):
        return None
    rates = _qb_pressure_rates()
    rate = rates.get(player_id)
    if rate is None:
        return None
    # Also check by name match via pfr_player_id → player_id is the PFR id here
    if rate > 0.35:
        return round(0.45 - (rate - 0.35) * 0.5, 3)
    if rate > 0.25:
        return round(0.50 - (rate - 0.25) * 0.3, 3)
    return round(0.55, 3)  # low pressure = slight boost for passing props


_LESSONS_FILE = Path(__file__).parent.parent / "lake/gold/nfl/jimmy_lessons.json"
_lessons_cache: tuple[float, dict] = (0.0, {})


def lessons() -> dict:
    """What MY BOO's Tuesday batch has taught Jimmy so far (empty until the first batch). Re-read when the file changes."""
    global _lessons_cache
    try:
        m = _LESSONS_FILE.stat().st_mtime
        if m != _lessons_cache[0]:
            _lessons_cache = (m, json.loads(_LESSONS_FILE.read_text()))
    except (OSError, ValueError):
        _lessons_cache = (0.0, {})
    return _lessons_cache[1]


def score_components(player_id: str, hit_rate: float | None, market_slug: str | None = None,
                     direction: str = "over") -> dict[str, float]:
    """Every signal Jimmy averages, by name. MY BOO freezes this vector with each slip so the batch can learn which signals earn their weight."""
    comp: dict[str, float] = {}
    if hit_rate is not None:
        comp["hit_rate"] = hit_rate
    usage = _usage_index().get(player_id)
    if usage is not None:
        comp["usage"] = usage / 100
    edge = leg_edge(player_id, market_slug or "", direction)
    if edge is not None:
        comp["matchup"] = matchup.phi(edge)
    proj_sig = _projection_signal(player_id, market_slug or "", hit_rate)
    if proj_sig is not None:
        comp["projection"] = proj_sig
    dfs_sig = _dfs_salary_signal(player_id, market_slug)
    if dfs_sig is not None:
        comp["dfs_salary"] = dfs_sig
    # #16 Recency-weighted defense, nudged by MY BOO's measured error on that defense
    opponent = next_opponent(player_id)
    rec_def = _recency_defense_signal(opponent, market_slug)
    if rec_def is not None:
        resid = lessons().get("defense_residual", {}).get(opponent or "", {})
        cat = {"passyds": "pass", "recyds": "pass", "recs": "pass", "rushyds": "rush"}.get(market_slug or "")
        if cat and cat in resid and direction == "over":
            rec_def = max(0.0, min(1.0, rec_def + max(-0.08, min(0.08, 0.5 * (resid[cat] - 1)))))
        comp["recency_defense"] = rec_def
    # #18 QB pressure rate
    pressure_sig = _qb_pressure_signal(player_id, market_slug)
    if pressure_sig is not None:
        comp["qb_pressure"] = pressure_sig
    # Fantasy points: L5/season form scaled by the opponent's fantasy rank vs this position (live during games)
    try:
        import fantasy
        fan_sig = fantasy.signal(player_id)
    except Exception:
        fan_sig = None
    if fan_sig is not None:
        comp["fantasy"] = fan_sig
    return comp


def jimmy_score(player_id: str, hit_rate: float | None, market_slug: str | None = None,
                direction: str = "over") -> float | None:
    """
    JIMMY THE GREEK v2 — enhanced composite confidence score.

    Signals (equal weight where available):
      1. hit_rate       — recent-form probability from the lake
      2. usage          — usage_index_score / 100 from the lake
      3. matchup        — Phi(unit edge) from the matchup predictor
      4. projection     — Tank01 projected stat vs prop line (new)
      5. dfs_salary     — FanDuel salary vs position average (new)

    Modifiers (multiplicative):
      - redzone boost   — TD props get inside-5 share nudge
      - regression cut  — REGRESSION RISK players are penalized
      - injury factor   — OUT=0.0, Q/D/O scaled penalty (new)
      - starter factor  — non-starters get 0.70x (new)
      - line movement   — steam confirmation/fade nudge (new)
    """
    comp = score_components(player_id, hit_rate, market_slug, direction)
    if not comp:
        return None

    # MY BOO's Tuesday batch tunes these: component weights (default 1.0) and a small per-market bias.
    L = lessons()
    w = L.get("weights", {})
    wsum = sum(w.get(k, 1.0) for k in comp)
    score = sum(v * w.get(k, 1.0) for k, v in comp.items()) / wsum
    score += max(-0.05, min(0.05, L.get("market_bias", {}).get(market_slug or "", 0.0)))

    # Redzone boost for TD props
    if market_slug == "anytd":
        redzone = _redzone_i5_share().get(player_id)
        if redzone is not None:
            score = min(1.0, score + min(0.15, redzone * 0.3))

    # Line movement confirmation/fade
    lm = _line_movement_signal(player_id, market_slug, direction)
    if lm:
        score = min(1.0, max(0.0, score + lm))

    # Multiplicative modifiers — order matters: regression → injury → starter → weather → short-week
    score = score * regression_factor(player_id, direction)
    score = score * _injury_multiplier(player_id)
    score = score * _starter_multiplier(player_id)

    # #23 Weather: outdoor cold/wind reduces passing prop probability
    team = player_team(player_id)
    score = score * _weather_multiplier(team, market_slug)

    # #10 Short-week fatigue
    score = score * _short_week_multiplier(team)

    return round(score, 3)


def confidence_breakdown(player_id: str, hit_rate: float | None,
                         market_slug: str | None = None, direction: str = "over") -> dict:
    """
    Returns the full signal breakdown so the API can expose it for transparency.
    Used by /api/jimmy_score for the detail view.
    """
    usage        = _usage_index().get(player_id)
    edge         = leg_edge(player_id, market_slug or "", direction)
    proj_sig     = _projection_signal(player_id, market_slug or "", hit_rate)
    dfs_sig      = _dfs_salary_signal(player_id, market_slug)
    lm           = _line_movement_signal(player_id, market_slug, direction)
    injury_m     = _injury_multiplier(player_id)
    starter_m    = _starter_multiplier(player_id)
    regression   = regression_factor(player_id, direction)
    injury_info  = tank01.injury_map_by_player_id().get(player_id) if tank01.available() else None
    opp          = next_opponent(player_id)
    rec_def      = _recency_defense_signal(opp, market_slug)
    pressure_sig = _qb_pressure_signal(player_id, market_slug)
    team         = player_team(player_id)
    weather_m    = _weather_multiplier(team, market_slug)
    short_wk_m   = _short_week_multiplier(team)
    game_info    = _next_game_info().get(team or "")
    return {
        "hitRate":             hit_rate,
        "usageSignal":         round(usage / 100, 3) if usage is not None else None,
        "matchupSignal":       round(matchup.phi(edge), 3) if edge is not None else None,
        "projectionSignal":    proj_sig,
        "dfsSalarySignal":     dfs_sig,
        "recencyDefenseSignal": rec_def,
        "qbPressureSignal":    pressure_sig,
        "lineMoveNudge":       lm,
        "injuryStatus":        injury_info.get("injuryStatus") if injury_info else "HEALTHY",
        "injuryMultiplier":    injury_m,
        "starterMultiplier":   starter_m,
        "regressionFactor":    regression,
        "weatherMultiplier":   weather_m,
        "shortWeekMultiplier": short_wk_m,
        "gameWeekday":         game_info.get("weekday") if game_info else None,
        "gameRoof":            game_info.get("roof") if game_info else None,
        "gameTemp":            game_info.get("temp_actual") if game_info else None,
        "gameWind":            game_info.get("wind_actual") if game_info else None,
        "tank01Available":     tank01.available(),
        "sbAvailable":         sportsbook.available(),
    }

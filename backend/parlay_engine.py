"""
BIG PROPPA Correlation Engine -- finds profitable correlated parlays from the
lake's ponds, applying the 20 RotoWire-style queries across all active players.

LOGIC OVERVIEW
==============
Four correlation types, each built from a different pond combination:

  COACHES SON  -- single player with high inside-5 trust + AGREEMENT TD
                  correlation + multiple correlated prop legs (yards, recs,
                  TD). The name comes from the user's framing: "in inside the
                  20-yard line is his coach's highest trust level." These are
                  the guys the QB looks for in clutch short-yardage.

  IB CASCADE   -- QB facing an IB 2.0 score of 5 (scripts/build_ib2.py: the
                  opponent's pass rush against this offense's protection).
                  Two correlated QB legs: Under passyds + Over intsthrown.
                  The IB shift on each is read from ib2_bucket_rates.csv
                  (2023-2025 outcomes at that score), not a hand-set
                  multiplier. The old check-down "recs Over" leg is gone:
                  check-down backs caught fewer balls vs IB 5, not more.

  VOLUME STACK -- same offensive unit, two players whose totals move together
                  (QB passyds + WR1 recyds; or QB passtd + TE anytd). Positive
                  same-game correlation: if the QB throws for yards, the WR
                  who catches them also goes over.

  SINGLE HERO  -- one player where 3 or more markets all clear 85% jimmy
                  probability independently (e.g. a dominant RB: rushyds +
                  rushrec + carries; or a target-hog WR: recyds + recs + anytd).

THE 20 QUERIES
==============
Mapped from the user's RotoWire-inspired list. Each query defines:
  pos       : position filter (QB/RB/WR/TE/K/ALL)
  market    : market_slug from the prop lake
  threshold : the line from the user's query (None = use FanDuel line)
  direction : 'over' or 'under' (most queries are 'over')
  label     : human-readable description

FanDuel price is required for any leg to appear in a real parlay.
A player who clears the threshold but has no FanDuel price is dropped.
All probabilities are Jimmy's lake-only composite (HEURISTIC, NOT BACKTESTED).
Min 2 legs per parlay. Min 30% profit boost implied by the combined odds.
"""
from __future__ import annotations

from functools import lru_cache

import breakout
import data
import jev
import jimmy
import matchup
import red_zone
from odds import compute_parlay

WAGER = 5.0
MIN_PROB = 0.85         # standard Jimmy-score floor (hit-rate driven)
MIN_MATCHUP_PROB = 0.68 # pond-only floor: usage + matchup component (no hit-rate history needed)
MIN_PROFIT_MULT = 1.30  # combined decimal odds must imply >= 30% profit boost


# ---------------------------------------------------------------------------
# The 20 queries
# ---------------------------------------------------------------------------

QUERIES: list[dict] = [
    {"pos": "QB", "market": "passtd",      "threshold": 2.5,  "dir": "over",  "label": "Over 2.5 Pass TDs"},
    {"pos": "QB", "market": "passyds",     "threshold": 225.5,"dir": "under", "label": "Under 225.5 Pass Yards"},
    {"pos": "QB", "market": "intsthrown",  "threshold": 0.5,  "dir": "over",  "label": "Over 0.5 Interceptions"},
    {"pos": "QB", "market": "passatt",     "threshold": 32.5, "dir": "over",  "label": "Over 32.5 Pass Attempts"},
    {"pos": "RB", "market": "rushyds",     "threshold": 75.5, "dir": "over",  "label": "Over 75.5 Rush Yards"},
    {"pos": "RB", "market": "anytd",       "threshold": 2.0,  "dir": "over",  "label": "2+ Touchdowns"},
    {"pos": "RB", "market": "carries",     "threshold": 15.5, "dir": "over",  "label": "Over 15.5 Carries"},
    {"pos": "RB", "market": "recs",        "threshold": 3.5,  "dir": "under", "label": "Under 3.5 Receptions"},
    {"pos": "RB", "market": "rushrec",     "threshold": 85.5, "dir": "over",  "label": "Over 85.5 Rush+Rec Yards"},
    {"pos": "WR", "market": "recyds",      "threshold": 80.5, "dir": "over",  "label": "Over 80.5 Rec Yards"},
    {"pos": "WR", "market": "recs",        "threshold": 6.5,  "dir": "over",  "label": "Over 6.5 Receptions"},
    {"pos": "WR", "market": "anytd",       "threshold": 0.5,  "dir": "over",  "label": "Anytime TD"},
    {"pos": "TE", "market": "recyds",      "threshold": 60.5, "dir": "over",  "label": "Over 60.5 Rec Yards"},
    {"pos": "TE", "market": "recs",        "threshold": 4.5,  "dir": "over",  "label": "Over 4.5 Receptions"},
    {"pos": "TE", "market": "anytd",       "threshold": 0.5,  "dir": "over",  "label": "Anytime TD"},
    {"pos": "K",  "market": "kickpts",     "threshold": 1.5,  "dir": "over",  "label": "Over 1.5 FG Made"},
    {"pos": "ALL","market": "firsttd",     "threshold": None, "dir": "ml",    "label": "First TD Scorer"},
    {"pos": "RB", "market": "rushyds",     "threshold": 75.5, "dir": "over",  "label": "Over 75.5 Rush Yards"},  # shared with #5
    {"pos": "QB", "market": "passyds",     "threshold": 250.0,"dir": "over",  "label": "Over 250 Pass Yards"},
]


# ---------------------------------------------------------------------------
# Stat source map for market slugs not in data.MARKET_TO_STAT
# ---------------------------------------------------------------------------

_EXTRA_STAT_SOURCE = {
    "carries":     ("player_rushing_week",   "carries"),
    "intsthrown":  ("player_passing_week",   "passing_interceptions"),
    "passatt":     ("player_passing_week",   "attempts"),
    "passtd":      ("player_passing_week",   "passing_tds"),
    "rushrec":     ("player_scrimmage_week", "rushing_yards"),  # added to rec below
    "kickpts":     ("player_kicking_week",   "fg_made"),
}


# ---------------------------------------------------------------------------
# Cached pond lookups
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _td_correlation() -> dict[str, dict]:
    out = {}
    for row in data.load("player_usage_td_correlation"):
        pid = row.get("player_id")
        if pid:
            out[pid] = row
    return out


@lru_cache(maxsize=1)
def _redzone() -> dict[str, dict]:
    out = {}
    for row in data.load("redzone_tiers"):
        pid = row.get("player_id")
        if pid:
            out.setdefault(pid, row)  # keep first (most recent)
    return out


@lru_cache(maxsize=1)
def _ib_scores() -> dict[str, dict]:
    out = {}
    for row in data.load("defense_ib_score"):
        team = row.get("team")
        if team:
            out[team] = row
    return out


@lru_cache(maxsize=1)
def _ib2_matchups() -> dict[tuple[str, str], dict]:
    """(defense, offense) -> IB 2.0 row for this week's slate (scripts/build_ib2.py)."""
    return {(r["defteam"], r["posteam"]): r for r in data.load("ib2_matchups_current")}


@lru_cache(maxsize=1)
def _ib2_calibration() -> dict[int, dict]:
    """IB 2.0 score -> what actually happened at that score, 2023-2025 (ib2_bucket_rates.csv)."""
    return {int(r["ib2_score"]): {k: float(v) for k, v in r.items()} for r in data.load("ib2_bucket_rates")}


@lru_cache(maxsize=1)
def _matchup_toxicity_rows() -> dict[str, dict]:
    """game_id -> {home_defense_ib_score, away_defense_ib_score, ...}"""
    out = {}
    for row in data.load("matchup_toxicity"):
        gid = row.get("game_id")
        if gid:
            out[gid] = row
    return out


@lru_cache(maxsize=1)
def _schedule_upcoming() -> list[dict]:
    """Games with no scores yet (upcoming this week)."""
    out = []
    for g in data.load("schedule"):
        if not g.get("away_score") and not g.get("home_score"):
            out.append(g)
    return out


@lru_cache(maxsize=1)
def _depth_chart() -> dict[str, list[dict]]:
    """team -> sorted list of depth chart rows."""
    out: dict[str, list[dict]] = {}
    for row in data.load("depth_chart_pregame"):
        t = row.get("team")
        if t:
            out.setdefault(t, []).append(row)
    return out


@lru_cache(maxsize=1)
def _usage_by_player() -> dict[str, dict]:
    out = {}
    for row in data.load("player_usage"):
        pid = row.get("player_id")
        if pid:
            out[pid] = row
    return out


# ---------------------------------------------------------------------------
# Helper: get weekly stat totals for a player+market
# ---------------------------------------------------------------------------

_PASS_MARKETS = {"passyds", "passtd", "passatt", "intsthrown"}
_ML_MARKETS = {"anytd", "firsttd", "lasttd"}
_MARKET_LABEL = {
    "passyds": "Pass Yds", "passtd": "Pass TDs", "passatt": "Pass Attempts",
    "intsthrown": "Interceptions", "recyds": "Rec Yds", "recs": "Receptions",
    "rushyds": "Rush Yds", "rushrec": "Rush+Rec Yds",
}


@lru_cache(maxsize=1)
def _qb_pass_volume() -> dict[str, float]:
    """
    Passing-trust stand-in for QBs, 0-100. player_usage scores QBs on the
    rushing pond (their carries), which says nothing about passing props.
    Starters (>=80% of their team's attempts in games played) are ranked by
    attempts per game; the percentile is the score. Non-starters get none.
    """
    team_att: dict[tuple[str, str], float] = {}
    rows = data.load("player_passing_week")
    for r in rows:
        key = (r.get("game_id", ""), r.get("team", ""))
        team_att[key] = team_att.get(key, 0) + float(r.get("attempts") or 0)

    per_qb: dict[str, list[float]] = {}
    for r in rows:
        pid = r.get("player_id")
        att = float(r.get("attempts") or 0)
        tot = team_att.get((r.get("game_id", ""), r.get("team", "")), 0)
        if pid and tot:
            s = per_qb.setdefault(pid, [0.0, 0.0, 0])
            s[0] += att
            s[1] += tot
            s[2] += 1
    starters = {pid: a / g for pid, (a, t, g) in per_qb.items() if g and a / t >= 0.8}
    ranked = sorted(starters, key=starters.get)
    n = len(ranked)
    return {pid: round(100 * (i + 1) / n, 1) for i, pid in enumerate(ranked)} if n else {}


def _matchup_score(player_id: str, market: str | None = None, direction: str = "over") -> float:
    """
    Pond-only matchup quality: (usage / 100 + Phi(unit edge for this leg)) / 2.

    The 'top 10% offense vs bottom 10% defense' signal -- a trusted player
    whose unit wins its matchup justifies a leg even when hit-rate history is thin.
    Passing markets use the QB passing-volume stand-in instead of player_usage.
    Over props on a REGRESSION RISK player take Jimmy's regression cut here too,
    so the fallback can't let a flagged player skip it.
    """
    if market in _PASS_MARKETS and player_id in _qb_pass_volume():
        u = _qb_pass_volume()[player_id] / 100
    else:
        u = float(_usage_by_player().get(player_id, {}).get("usage_index_score") or 0) / 100
    edge = jimmy.leg_edge(player_id, market or "", direction)
    m = matchup.phi(edge) if edge is not None else 0.5
    return round((u + m) / 2 * jimmy.regression_factor(player_id, direction), 3)


def _qualifies(prob: float | None, player_id: str, market: str | None = None, direction: str = "over") -> bool:
    """Clears the 85% Jimmy score, or the pond-only matchup score clears 68% (thin early-season samples)."""
    if prob is not None and prob >= MIN_PROB:
        return True
    return _matchup_score(player_id, market, direction) >= MIN_MATCHUP_PROB


def _games_for(player_id: str, market_slug: str) -> list[dict]:
    """Return week-grain game rows [{week, value, opponent}]."""
    if market_slug == "anytd":
        return data.anytime_td_games(player_id)
    if market_slug == "rushrec":
        rush = data.weekly_games(player_id, "player_rushing_week", "rushing_yards")
        rec  = data.weekly_games(player_id, "player_scrimmage_week", "receiving_yards")
        # merge by week
        rec_by_wk = {g["week"]: g["value"] for g in rec}
        return [{"week": g["week"], "opponent": g["opponent"],
                 "value": g["value"] + rec_by_wk.get(g["week"], 0)} for g in rush]
    src_stat = _EXTRA_STAT_SOURCE.get(market_slug) or data.MARKET_TO_STAT.get(market_slug)
    if not src_stat:
        return []
    src, col = src_stat
    return data.weekly_games(player_id, src, col)


def _hit_rate(games: list[dict], threshold: float, window: int = 10) -> float | None:
    recent = sorted(games, key=lambda g: g["week"])[-window:]
    if not recent:
        return None
    return round(sum(1 for g in recent if g["value"] >= threshold) / len(recent), 3)


def _hit_rate_under(games: list[dict], threshold: float, window: int = 10) -> float | None:
    recent = sorted(games, key=lambda g: g["week"])[-window:]
    if not recent:
        return None
    return round(sum(1 for g in recent if g["value"] < threshold) / len(recent), 3)


# ---------------------------------------------------------------------------
# IB adjustment: amplify or dampen Jimmy score based on matchup pressure
# ---------------------------------------------------------------------------

def _ib_shift(ib_score: int, market_slug: str, direction: str) -> float:
    """
    Additive probability shift for an IB 2.0 matchup score, read straight off what
    happened at that score in 2023-2025 (ib2_bucket_rates.csv), relative to the
    all-games average. Only markets the backtest actually measured move:
      passyds  -- pass yards vs the spread/total-implied expectation
      intsthrown -- chance the QB throws 1+ interception
    Check-down receptions, pass attempts and pass TDs showed no IB effect (check-down
    backs actually caught FEWER balls vs IB 5), so they are left alone.
    """
    cal = _ib2_calibration()
    row = cal.get(ib_score)
    if not row or not cal:
        return 0.0
    if market_slug == "passyds":
        under_edge = row["pass_under_lines_rate"] - 0.5
        return under_edge if direction == "under" else -under_edge
    if market_slug == "intsthrown":
        base = sum(r["qb_int_1plus_rate"] * r["games"] for r in cal.values()) / sum(r["games"] for r in cal.values())
        edge = row["qb_int_1plus_rate"] - base
        return edge if direction == "over" else -edge
    return 0.0


def _ib_adjust(base_prob: float, ib_score: int, market_slug: str, direction: str) -> float:
    return round(min(0.97, max(0.0, base_prob + _ib_shift(ib_score, market_slug, direction))), 3)


# ---------------------------------------------------------------------------
# FanDuel price lookup for the engine
# ---------------------------------------------------------------------------

def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _fd_offer(name: str, market_slug: str, direction: str) -> tuple[float, float] | None:
    """
    (line, american_price) from FanDuel only. fanduel_line_for falls back to
    other books when FanDuel has no row; the engine refuses that fallback.
    Yes/no TD markets are priced from the moneyline, with an implied 0.5 line.
    """
    row = data.fanduel_line_for(name, market_slug)
    if not row or row.get("book") != "fanduel":
        return None
    if market_slug in _ML_MARKETS:
        price, line = _num(row.get("moneyline_price")), 0.5
    else:
        price = _num(row.get("under_price" if direction == "under" else "over_price"))
        line = _num(row.get("line"))
    if price is None or line is None:
        return None
    return line, price


def _prop_label(market_slug: str, direction: str, line: float) -> str:
    if market_slug == "anytd":
        return "Anytime TD Scorer"
    return f"{direction.title()} {line:g} {_MARKET_LABEL.get(market_slug, market_slug)}"


# ---------------------------------------------------------------------------
# Per-player probability for a given query
# ---------------------------------------------------------------------------

def _player_prob(player_id: str, market_slug: str, threshold: float | None,
                 direction: str, ib_score: int = 3) -> tuple[float | None, float | None]:
    """
    Returns (jimmy_prob, raw_hit_rate) for player + query, with IB adjustment.
    threshold=None (firsttd/anytd) uses 0.5 as the hit-rate threshold.
    """
    eff_threshold = threshold if threshold is not None else 0.5
    games = _games_for(player_id, market_slug)
    if direction == "under":
        raw_hr = _hit_rate_under(games, eff_threshold)
    else:
        raw_hr = _hit_rate(games, eff_threshold)

    base = jimmy.jimmy_score(player_id, raw_hr, market_slug=market_slug, direction=direction)
    if base is None:
        return None, raw_hr

    adjusted = _ib_adjust(base, ib_score, market_slug, direction)
    return adjusted, raw_hr


# ---------------------------------------------------------------------------
# Build a single leg dict
# ---------------------------------------------------------------------------

def _leg(player_id: str, name: str, team: str, market: str, direction: str,
         label: str, prob: float, l5: float | None, price: float,
         correlation_note: str = "") -> dict:
    if market in red_zone.TD_MARKETS:       # HARD RULE: no touchdown-scorer legs, ever (see red_zone.py)
        raise ValueError(f"TD-scorer market '{market}' is banned; use red_zone.effort_leg")
    flag = breakout.breakout_by_player().get(player_id, {}).get("flag")
    if flag in ("BREAKOUT CANDIDATE", "REGRESSION RISK"):
        correlation_note = f"{correlation_note} | {flag}" if correlation_note else flag
    offer = _fd_offer(name, market, direction)
    line = offer[0] if offer else None

    # Jev's independent read, only for legs that already cleared the pond-only
    # gate -- not the broad scan every finder runs first. Keeps usage to one
    # call per final leg (cached per player+market+direction), never per
    # candidate examined.
    if jev.available():
        usage_score = float(_usage_by_player().get(player_id, {}).get("usage_index_score") or 0) or None
        edge = jimmy.leg_edge(player_id, market, direction)
        opponent = jimmy.next_opponent(player_id)
        jev_prob = jev.leg_probability(player_id, name, team, market, direction, line, l5,
                                       usage_score, edge, opponent)
        if jev_prob is not None:
            prob = round((prob + jev_prob) / 2, 3)
            tag = f"Jev {jev_prob:.0%}"
            correlation_note = f"{correlation_note} | {tag}" if correlation_note else tag

    return {
        "line": line,
        "playerId": player_id,
        "name": name,
        "team": team,
        "market": market,
        "direction": direction,
        "prop": label,
        "probability": round(prob, 3),
        "l5": round(l5, 3) if l5 is not None else prob,
        "odds": price,
        "photoUrl": data.photo_url(player_id),
        "correlationNote": correlation_note,
    }


# ---------------------------------------------------------------------------
# Slip builder
# ---------------------------------------------------------------------------

def _slip(slip_id: str, title: str, correlation_type: str, legs: list[dict],
          insight: str = "") -> dict:
    if len(legs) < 2:
        return {}
    math = compute_parlay([lg["odds"] for lg in legs], wager=WAGER, boost=0.30)
    if math.combined_decimal < MIN_PROFIT_MULT:
        return {}
    return {
        "id": slip_id,
        "title": title,
        "correlationType": correlation_type,
        "insight": insight,
        "legs": legs,
        "wager": WAGER,
        "boost": 0.30,
        "combinedDecimalOdds": math.combined_decimal,
        "payout": math.payout,
        "boostedPayout": math.boosted_payout,
        "boostedAmericanOdds": math.boosted_american,
    }


def _measure(player_id: str, name: str, market: str, direction: str, ib_score: int) -> dict | None:
    """
    Probability measured against the same FanDuel line the leg is priced at.
    None if FanDuel doesn't offer it, or Jimmy filters the leg out: a player
    from a losing team, or a unit edge pointing against the bet.
    """
    if not jimmy.eligible(player_id) or not jimmy.matchup_gate(player_id, market, direction):
        return None
    offer = _fd_offer(name, market, direction)
    if not offer:
        return None
    line, price = offer
    prob, _ = _player_prob(player_id, market, line, direction, ib_score)
    l5 = (_hit_rate_under if direction == "under" else _hit_rate)(_games_for(player_id, market), line, window=5)
    return {"line": line, "price": price, "prob": prob, "l5": l5, "label": _prop_label(market, direction, line)}


def _opp_ib(player_id: str) -> tuple[str | None, dict, int]:
    """IB 2.0 matchup score (this opponent's pass rush vs this player's offense); IB 1.0 if not built."""
    opp = jimmy.next_opponent(player_id)
    ib2 = _ib2_matchups().get((opp or "", jimmy.player_team(player_id) or ""))
    if ib2:
        return opp, ib2, int(ib2["ib2_score"])
    row = _ib_scores().get(opp or "", {})
    return opp, row, int(row.get("ib_score") or 3)


# ---------------------------------------------------------------------------
# COACHES SON finder
# ---------------------------------------------------------------------------

def find_coaches_son(dim: dict[str, dict]) -> list[dict]:
    """
    Players with high inside-5 trust AND AGREEMENT TD correlation.
    Build a 3-leg parlay: yards OVER + recs OVER + anytd.
    """
    results = []
    redzone = _redzone()
    td_corr = _td_correlation()

    for pid, info in dim.items():
        pos = info.get("position")
        if pos not in ("RB", "WR", "TE"):
            continue

        rz = redzone.get(pid, {})
        pct_i5 = float(rz.get("pct_i5_intra") or 0)
        if pct_i5 < 0.18:
            continue

        tc = td_corr.get(pid, {})
        flag = tc.get("correlation_flag", "")
        if "AGREEMENT" not in flag:
            continue

        usage = _usage_by_player().get(pid, {})
        if float(usage.get("usage_index_score") or 0) < 55:
            continue

        name = info["name"]
        team = info.get("team", "")
        opp, _, ib_score = _opp_ib(pid)
        if not opp:
            continue
        legs = []
        yds_market = "rushrec" if pos == "RB" else "recyds"
        plan = [
            (yds_market, f"Inside-5 share {pct_i5:.0%} | {flag} | wins its matchup vs {opp}"),
            ("recs", "Check-down/slot target in stress situations"),
        ]
        for market, note in plan:
            m = _measure(pid, name, market, "over", ib_score)
            if m and _qualifies(m["prob"], pid, market):
                legs.append(_leg(pid, name, team, market, "over", m["label"],
                                 max(m["prob"] or 0, _matchup_score(pid, market)), m["l5"], m["price"], note))

        if len(legs) < 2:
            continue

        insight = (
            f"{name} ({pos}) is a COACHES SON: {pct_i5:.0%} inside-5 share, "
            f"{flag}, usage role '{usage.get('usage_role', '')}', facing {opp}. "
            f"If the first two legs land, the TD leg follows from the same opportunity well."
        )
        slip = _slip(f"coaches-son-{pid}", f"COACHES SON · {name}", "COACHES_SON", legs, insight)
        if slip:
            results.append(slip)

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# IB CASCADE finder
# ---------------------------------------------------------------------------

def find_ib_cascade(dim: dict[str, dict]) -> list[dict]:
    """
    QB facing CAT 4-5 defense → distress props for QB + check-down target.
    """
    results = []

    for qb_pid, qb_info in dim.items():
        if qb_info.get("position") != "QB" or qb_pid not in _qb_pass_volume():
            continue
        opp, ib_row, ib_score = _opp_ib(qb_pid)
        # 2023-2025: only the top IB 2.0 score moved pass yards past the lines; 4 did not.
        if not opp or ib_score < 5:
            continue

        qb_name = qb_info["name"]
        qb_team = qb_info.get("team", "")
        cal = _ib2_calibration().get(ib_score, {})

        # Both legs are the same bad afternoon for the QB, so they correlate. No IB floor:
        # each leg must clear on Jimmy's own number, which already carries the calibrated IB shift.
        legs = []
        for market, direction in [("passyds", "under"), ("intsthrown", "over")]:
            m = _measure(qb_pid, qb_name, market, direction, ib_score)
            if m and _qualifies(m["prob"], qb_pid, market, direction):
                eff = m["prob"] if m["prob"] is not None else _matchup_score(qb_pid, market, direction)
                legs.append(_leg(qb_pid, qb_name, qb_team, market, direction, m["label"], eff, m["l5"], m["price"],
                                 f"IB 2.0 score {ib_score} vs {opp}"))

        if len(legs) < 2:
            continue

        insight = (
            f"{qb_name} faces {opp}, an IB 2.0 score of {ib_score}: {opp}'s pressure rate "
            f"{float(ib_row.get('pre_pressure_rate') or 0):.0%} against a line allowing "
            f"{float(ib_row.get('pre_off_pressure_allowed') or 0):.0%}. In 2023-2025 matchups at this score the QB "
            f"threw 1+ INT {cal.get('qb_int_1plus_rate', 0):.0%} of the time and passing went under the "
            f"lines-implied number {cal.get('pass_under_lines_rate', 0):.0%} of the time."
        )
        slip = _slip(f"ib-cascade-{qb_pid}", f"IB CASCADE · {qb_name} vs {opp}", "IB_CASCADE", legs, insight)
        if slip:
            results.append(slip)

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# VOLUME STACK finder
# ---------------------------------------------------------------------------

def find_volume_stack(dim: dict[str, dict]) -> list[dict]:
    """
    Same-offense positive correlations: QB passyds + a WR's recyds, or one
    RB's rushyds + rushrec (FanDuel has no carries market).
    """
    results = []

    by_team: dict[str, dict[str, list[str]]] = {}
    for pid, info in dim.items():
        by_team.setdefault(info.get("team", ""), {}).setdefault(info.get("position", ""), []).append(pid)

    for team, pos_map in by_team.items():
        # Pattern A: starting QB passyds OVER + WR recyds OVER
        for qb_pid in pos_map.get("QB", []):
            if qb_pid not in _qb_pass_volume():
                continue
            qb_name = dim[qb_pid]["name"]
            opp, _, ib = _opp_ib(qb_pid)
            if not opp:
                continue
            qm = _measure(qb_pid, qb_name, "passyds", "over", ib)
            if not qm:
                continue
            qb_eff = max(qm["prob"] or 0, _matchup_score(qb_pid, "passyds"))
            if qb_eff < MIN_MATCHUP_PROB:
                continue

            wr_ids = sorted(pos_map.get("WR", []),
                            key=lambda p: float(_usage_by_player().get(p, {}).get("usage_index_score") or 0),
                            reverse=True)
            for wr_pid in wr_ids[:3]:
                wr_name = dim[wr_pid]["name"]
                wm = _measure(wr_pid, wr_name, "recyds", "over", ib)
                if not wm:
                    continue
                wr_eff = max(wm["prob"] or 0, _matchup_score(wr_pid, "recyds"))
                if wr_eff < MIN_MATCHUP_PROB:
                    continue
                legs = [
                    _leg(qb_pid, qb_name, team, "passyds", "over", qm["label"], qb_eff, qm["l5"], qm["price"],
                         f"Volume game vs {opp}: QB & WR totals move together"),
                    _leg(wr_pid, wr_name, team, "recyds", "over", wm["label"], wr_eff, wm["l5"], wm["price"],
                         "Same-game volume: WR yardage tracks QB yardage"),
                ]
                slip = _slip(
                    f"vol-stack-qb-wr-{qb_pid}-{wr_pid}", f"VOLUME STACK · {qb_name} + {wr_name}", "VOLUME_STACK", legs,
                    f"If {qb_name} clears {qm['line']:g} passing yards against {opp}, {wr_name} is a primary "
                    f"beneficiary. Same-game volume props: both go up together when the offense is clicking.",
                )
                if slip:
                    results.append(slip)
                break

        # Pattern B: one RB's rushyds OVER + rushrec OVER
        for rb_pid in pos_map.get("RB", []):
            rb_name = dim[rb_pid]["name"]
            opp, _, ib = _opp_ib(rb_pid)
            if not opp:
                continue
            rush = _measure(rb_pid, rb_name, "rushyds", "over", ib)
            both = _measure(rb_pid, rb_name, "rushrec", "over", ib)
            if not (rush and both):
                continue
            rush_eff = max(rush["prob"] or 0, _matchup_score(rb_pid, "rushyds"))
            both_eff = max(both["prob"] or 0, _matchup_score(rb_pid, "rushrec"))
            if min(rush_eff, both_eff) < MIN_MATCHUP_PROB:
                continue
            legs = [
                _leg(rb_pid, rb_name, team, "rushyds", "over", rush["label"], rush_eff, rush["l5"], rush["price"],
                     f"Workload vs {opp}: the carries drive both numbers"),
                _leg(rb_pid, rb_name, team, "rushrec", "over", both["label"], both_eff, both["l5"], both["price"],
                     "Rushing yards are the bulk of rush+rec yards"),
            ]
            slip = _slip(
                f"vol-stack-rb-{rb_pid}", f"VOLUME STACK · {rb_name} Bell-Cow", "VOLUME_STACK", legs,
                f"{rb_name} is a featured back facing {opp}. When the game plan calls for the run, "
                f"rushing yards and rush+rec yards land together.",
            )
            if slip:
                results.append(slip)
            break

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:4]


# ---------------------------------------------------------------------------
# SINGLE HERO finder
# ---------------------------------------------------------------------------

_HERO_MARKETS: dict[str, list[str]] = {
    "QB": ["passyds", "rushyds"],
    "WR": ["recyds", "recs"],
    "TE": ["recyds", "recs"],
    "RB": ["rushyds", "rushrec", "recs"],
}


def find_single_hero(dim: dict[str, dict]) -> list[dict]:
    """
    One player with 3+ distinct FanDuel-priced prop legs that all qualify.
    """
    results = []

    for pid, info in dim.items():
        markets = _HERO_MARKETS.get(info.get("position", ""), [])
        if not markets:
            continue
        name = info["name"]
        team = info.get("team", "")
        opp, _, ib = _opp_ib(pid)
        if not opp:
            continue
        role = _usage_by_player().get(pid, {}).get("usage_role", "")

        legs = []
        for market in markets:
            m = _measure(pid, name, market, "over", ib)
            if m and _qualifies(m["prob"], pid, market):
                eff = max(m["prob"] or 0, _matchup_score(pid, market))
                legs.append(_leg(pid, name, team, market, "over", m["label"], eff, m["l5"], m["price"], role))

        if len(legs) < 3:
            continue
        legs = sorted(legs, key=lambda lg: lg["probability"], reverse=True)[:3]

        insight = (
            f"{name} ({info.get('position')}) qualifies on three FanDuel lines against {opp}. "
            f"Usage role: {role or 'n/a'}. All three props are driven by the same opportunity."
        )
        slip = _slip(f"single-hero-{pid}", f"SINGLE HERO · {name}", "SINGLE_HERO", legs, insight)
        if slip:
            results.append(slip)

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_engine() -> list[dict]:
    """
    Run all four correlation patterns and return the combined list of
    correlated parlays, de-duplicated by player overlap.
    """
    dim = data.player_dimension()

    # HARD RULE: TD-scorer queries never run. Finders read QUERIES, so strip the banned markets in place.
    QUERIES[:] = [q for q in QUERIES if q["market"] not in red_zone.TD_MARKETS]

    coaches_son = find_coaches_son(dim)
    ib_cascade  = find_ib_cascade(dim)
    vol_stack   = find_volume_stack(dim)
    single_hero = find_single_hero(dim)

    all_slips = coaches_son + ib_cascade + vol_stack + single_hero

    # De-dup: drop slips whose player_id set is a subset of an already-included slip
    seen_pid_sets: list[frozenset] = []
    unique = []
    for slip in all_slips:
        pids = frozenset(lg["playerId"] for lg in slip["legs"])
        if any(pids <= seen for seen in seen_pid_sets):
            continue
        seen_pid_sets.append(pids)
        unique.append(slip)

    for s in unique:
        s["legs"] = red_zone.strip_td_legs(s["legs"])
    return [s for s in unique if len(s["legs"]) >= 2]

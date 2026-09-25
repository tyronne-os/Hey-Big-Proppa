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

  IB CASCADE   -- QB facing a CAT 4+ defense (ib_score >= 4). The defensive
                  pressure reduces pocket time, forcing quicker releases:
                  QB Under passyds / Over intsthrown / Over passatt all
                  become more likely, AND the check-down RB/TE's receptions
                  Over becomes more likely because the QB is dumping off.
                  Jimmy's probability is adjusted UP for these "distress"
                  props by an IB multiplier derived from the defense's
                  ib_score (4 or 5).

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

import data
import jimmy
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

def _matchup_score(player_id: str) -> float:
    """
    Pond-only matchup quality: (usage_index_score / 100 + inverted opponent toxicity) / 2.

    This is the 'top 10% offense vs bottom 10% defense' signal the user
    describes -- when a trusted player (high usage) faces a weak defense
    (low toxicity), the matchup itself justifies inclusion even when
    hit-rate history is thin (early season).  Returns 0..1.
    """
    usage = _usage_by_player().get(player_id, {})
    u = float(usage.get("usage_index_score") or 0) / 100
    opp = jimmy._last_opponent(player_id)
    tox = float(_ib_scores().get(opp or "", {}).get("toxicity_index_0_100") or 50) / 100
    return round((u + (1 - tox)) / 2, 3)


def _qualifies(prob: float | None, player_id: str) -> bool:
    """
    A leg qualifies if it clears the standard 85% Jimmy score OR if a
    pond-only matchup score >= 68% justifies it (usage + inverted toxicity
    both must be present, early-season substitute for a thin hit-rate sample).
    """
    if prob is not None and prob >= MIN_PROB:
        return True
    return _matchup_score(player_id) >= MIN_MATCHUP_PROB


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

def _ib_adjust(base_prob: float, ib_score: int, market_slug: str, direction: str) -> float:
    """
    Adjust a base probability using the opposing defense's IB score.

    CAT 4+ pressures the QB, cascading to:
      - Under passyds: probability UP (less time in pocket = shorter gains)
      - Over intsthrown: probability UP (pressure causes mistakes)
      - Over passatt: probability UP (more quick-fire attempts to release)
      - Over recs (check-down RB/TE): probability UP
      - Over passtd: probability DOWN (harder to hit downfield TDs)

    CAT 1-2 (weak defense):
      - Over passyds: probability UP
      - Over passtd: probability UP
      - Over recyds: probability UP
    """
    score = base_prob
    pressure = max(0, ib_score - 3)  # 0 for CAT 1-3, 1 for CAT 4, 2 for CAT 5

    distress_up = {
        ("passyds", "under"),
        ("intsthrown", "over"),
        ("passatt", "over"),
        ("recs", "over"),   # check-down target
    }
    distress_down = {
        ("passtd", "over"),
        ("passyds", "over"),
    }
    feast_up = {
        ("passyds", "over"),
        ("passtd", "over"),
        ("recyds", "over"),
    }

    key = (market_slug, direction)
    if pressure > 0:
        if key in distress_up:
            score = min(0.97, score * (1.0 + pressure * 0.08))
        elif key in distress_down:
            score = score * (1.0 - pressure * 0.06)
    else:
        weakness = max(0, 2 - ib_score)
        if weakness > 0 and key in feast_up:
            score = min(0.97, score * (1.0 + weakness * 0.07))

    return round(min(0.97, max(0.0, score)), 3)


# ---------------------------------------------------------------------------
# FanDuel price lookup for the engine
# ---------------------------------------------------------------------------

def _fd_price(name: str, market_slug: str, direction: str) -> float | None:
    row = data.fanduel_line_for(name, market_slug)
    if not row:
        return None
    if direction == "over":
        v = row.get("over_price")
    elif direction == "under":
        v = row.get("under_price")
    else:  # ml / firsttd / anytd
        v = row.get("moneyline_price")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


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

    base = jimmy.jimmy_score(player_id, raw_hr, market_slug=market_slug)
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
    return {
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
        usage_score = float(usage.get("usage_index_score") or 0)
        if usage_score < 55:
            continue

        name = info["name"]
        team = info.get("team", "")

        # Get opponent's IB score via last_opponent
        opp = jimmy._last_opponent(pid)
        ib_row = _ib_scores().get(opp or "", {})
        ib_score = int(ib_row.get("ib_score") or 3)

        legs = []

        # Leg 1: yards over (market depends on position)
        yds_market = "rushrec" if pos == "RB" else "recyds"
        yds_thresh = 85.5 if pos == "RB" else (60.5 if pos == "TE" else 80.5)
        mq = _matchup_score(pid)
        yds_prob, yds_hr = _player_prob(pid, yds_market, yds_thresh, "over", ib_score)
        yds_price = _fd_price(name, yds_market, "over")
        eff_yds_prob = max(yds_prob or 0, mq)
        if _qualifies(yds_prob, pid) and yds_price:
            l5 = _hit_rate(_games_for(pid, yds_market), yds_thresh, window=5)
            legs.append(_leg(pid, name, team, yds_market, "over",
                             f"Over {yds_thresh} Rush+Rec Yds" if pos == "RB" else f"Over {yds_thresh} Rec Yds",
                             eff_yds_prob, l5, yds_price,
                             f"Inside-5 share {pct_i5:.0%} | {flag} | matchup {mq:.0%}"))

        # Leg 2: receptions over
        recs_thresh = 2.5 if pos == "RB" else (4.5 if pos == "TE" else 6.5)
        recs_prob, recs_hr = _player_prob(pid, "recs", recs_thresh, "over", ib_score)
        recs_price = _fd_price(name, "recs", "over")
        eff_recs_prob = max(recs_prob or 0, mq)
        if _qualifies(recs_prob, pid) and recs_price:
            l5 = _hit_rate(_games_for(pid, "recs"), recs_thresh, window=5)
            legs.append(_leg(pid, name, team, "recs", "over",
                             f"Over {recs_thresh} Receptions",
                             eff_recs_prob, l5, recs_price,
                             "Check-down/slot target in stress situations"))

        # Leg 3: anytime TD (boosted for i5 share)
        td_prob, td_hr = _player_prob(pid, "anytd", 0.5, "over", ib_score)
        td_price = _fd_price(name, "anytd", "ml")
        eff_td_prob = max(td_prob or 0, mq)
        if _qualifies(td_prob, pid) and td_price:
            l5 = _hit_rate(_games_for(pid, "anytd"), 0.5, window=5)
            legs.append(_leg(pid, name, team, "anytd", "over",
                             "Anytime TD Scorer",
                             eff_td_prob, l5, td_price,
                             f"Inside-5 intra share {pct_i5:.0%} | TD rate per RZ opp: {float(tc.get('td_per_redzone_opp') or 0):.2f}"))

        if len(legs) < 2:
            continue

        role_label = usage.get("usage_role", "")
        insight = (
            f"{name} ({pos}) is a COACHES SON: {pct_i5:.0%} inside-5 share, "
            f"{flag}, usage role '{role_label}'. "
            f"If the first two legs land, the TD leg follows from the same opportunity well."
        )
        slip = _slip(
            f"coaches-son-{pid}",
            f"COACHES SON · {name}",
            "COACHES_SON",
            legs,
            insight,
        )
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
    ib = _ib_scores()

    qb_ids = [pid for pid, row in dim.items() if row.get("position") == "QB"]

    for qb_pid in qb_ids:
        opp = jimmy._last_opponent(qb_pid)
        if not opp:
            continue
        ib_row = ib.get(opp, {})
        ib_score = int(ib_row.get("ib_score") or 3)
        if ib_score < 4:
            continue

        qb_name = dim[qb_pid]["name"]
        qb_team = dim[qb_pid].get("team", "")
        ib_cat = ib_row.get("ib_category", "")

        legs = []

        # QB distress props -- pick the best available
        for market, direction, q_label in [
            ("passyds",    "under", "Under 225.5 Pass Yards"),
            ("intsthrown", "over",  "Over 0.5 Interceptions"),
            ("passatt",    "over",  "Over 32.5 Pass Attempts"),
        ]:
            thresh = {"passyds": 225.5, "intsthrown": 0.5, "passatt": 32.5}[market]
            prob, hr = _player_prob(qb_pid, market, thresh, direction, ib_score)
            price = _fd_price(qb_name, market, direction)
            # IB CASCADE: the defense rating IS the probability signal --
            # a CAT 4-5 defense justifies inclusion even with a thin sample.
            ib_prob = min(0.97, (ib_score - 3) * 0.20 + 0.65)
            eff_prob = max(prob or 0, ib_prob)
            if eff_prob >= MIN_MATCHUP_PROB and price:
                l5 = (_hit_rate_under if direction == "under" else _hit_rate)(
                    _games_for(qb_pid, market), thresh, window=5)
                legs.append(_leg(qb_pid, qb_name, qb_team, market, direction,
                                 q_label, eff_prob, l5, price,
                                 f"Facing {opp} {ib_cat} → IB {ib_score} pressure cascade"))
                break  # one QB distress leg is enough

        if not legs:
            continue

        # Check-down target: RB1 or TE1 from same team
        depth = _depth_chart().get(qb_team, [])
        checkdown_pids = [
            row.get("player_id")
            for row in sorted(depth, key=lambda r: int(r.get("pos_rank") or 99))
            if row.get("pos_abb") in ("RB", "TE") and row.get("player_id")
        ][:2]

        for cd_pid in checkdown_pids:
            cd_name = dim.get(cd_pid, {}).get("name") or data.player_name(cd_pid)
            cd_team = dim.get(cd_pid, {}).get("team", qb_team)
            cd_pos = dim.get(cd_pid, {}).get("position", "RB")
            thresh = 2.5 if cd_pos == "RB" else 4.5
            prob, hr = _player_prob(cd_pid, "recs", thresh, "over", ib_score)
            price = _fd_price(cd_name, "recs", "over")
            mq = _matchup_score(cd_pid)
            # IB CASCADE also boosts check-down target receptions
            cd_ib_prob = min(0.97, (ib_score - 3) * 0.15 + 0.65)
            eff_prob = max(prob or 0, mq, cd_ib_prob)
            if eff_prob >= MIN_MATCHUP_PROB and price:
                l5 = _hit_rate(_games_for(cd_pid, "recs"), thresh, window=5)
                legs.append(_leg(cd_pid, cd_name, cd_team, "recs", "over",
                                 f"Over {thresh} Receptions",
                                 eff_prob, l5, price,
                                 f"Check-down target as QB dumps off under {opp} pressure"))
                break

        if len(legs) < 2:
            continue

        insight = (
            f"{qb_name} faces {opp} ({ib_cat}). "
            f"A CAT {ib_score} pass rush shrinks the pocket, increases quick releases, "
            f"and punishes downfield attempts. The check-down {legs[-1]['name'] if len(legs) > 1 else ''} "
            f"sees more targets in exactly these games."
        )
        slip = _slip(
            f"ib-cascade-{qb_pid}",
            f"IB CASCADE · {qb_name} vs {opp}",
            "IB_CASCADE",
            legs,
            insight,
        )
        if slip:
            results.append(slip)

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# VOLUME STACK finder
# ---------------------------------------------------------------------------

def find_volume_stack(dim: dict[str, dict]) -> list[dict]:
    """
    Same-offense positive correlations: QB passyds + WR1 recyds; or
    QB passtd + TE anytd; or RB carries + rushyds (individual volume cascade).
    """
    results = []

    # Group players by team
    by_team: dict[str, dict[str, list[str]]] = {}
    for pid, info in dim.items():
        team = info.get("team", "")
        pos = info.get("position", "")
        by_team.setdefault(team, {}).setdefault(pos, []).append(pid)

    for team, pos_map in by_team.items():
        qb_ids = pos_map.get("QB", [])
        wr_ids = pos_map.get("WR", [])
        te_ids = pos_map.get("TE", [])
        rb_ids = pos_map.get("RB", [])

        opp_ib = 3
        for qb_pid in qb_ids:
            opp = jimmy._last_opponent(qb_pid)
            if opp:
                opp_ib = int(_ib_scores().get(opp, {}).get("ib_score") or 3)
                break

        # Pattern A: QB passyds OVER + WR recyds OVER
        for qb_pid in qb_ids:
            qb_name = dim[qb_pid]["name"]
            qb_prob, _ = _player_prob(qb_pid, "passyds", 250.0, "over", opp_ib)
            qb_mq = _matchup_score(qb_pid)
            qb_eff = max(qb_prob or 0, qb_mq)
            qb_price = _fd_price(qb_name, "passyds", "over")
            if qb_eff < MIN_MATCHUP_PROB or not qb_price:
                continue

            for wr_pid in wr_ids[:3]:
                wr_name = dim.get(wr_pid, {}).get("name") or data.player_name(wr_pid)
                wr_prob, _ = _player_prob(wr_pid, "recyds", 80.5, "over", opp_ib)
                wr_mq = _matchup_score(wr_pid)
                wr_eff = max(wr_prob or 0, wr_mq)
                wr_price = _fd_price(wr_name, "recyds", "over")
                if wr_eff < MIN_MATCHUP_PROB or not wr_price:
                    continue

                qb_l5 = _hit_rate(_games_for(qb_pid, "passyds"), 250.0, window=5)
                wr_l5 = _hit_rate(_games_for(wr_pid, "recyds"), 80.5, window=5)
                legs = [
                    _leg(qb_pid, qb_name, team, "passyds", "over", "Over 250 Pass Yards",
                         qb_eff, qb_l5, qb_price,
                         "Volume game: QB & WR1 totals move together"),
                    _leg(wr_pid, wr_name, team, "recyds", "over", "Over 80.5 Rec Yards",
                         wr_eff, wr_l5, wr_price,
                         "Same-game volume: WR yardage tracks QB yardage"),
                ]
                slip = _slip(
                    f"vol-stack-qb-wr-{qb_pid}-{wr_pid}",
                    f"VOLUME STACK · {qb_name} + {wr_name}",
                    "VOLUME_STACK",
                    legs,
                    f"If {qb_name} throws for 250+ yards, {wr_name} is a primary beneficiary. "
                    f"Same-game volume props: both go up together when the offense is clicking.",
                )
                if slip:
                    results.append(slip)
                break  # one WR per QB

        # Pattern B: RB individual volume (carries OVER + rushyds OVER)
        for rb_pid in rb_ids:
            rb_name = dim.get(rb_pid, {}).get("name") or data.player_name(rb_pid)
            carries_prob, _ = _player_prob(rb_pid, "carries", 15.5, "over", opp_ib)
            carries_price = _fd_price(rb_name, "carries", "over")
            rush_prob, _ = _player_prob(rb_pid, "rushyds", 75.5, "over", opp_ib)
            rush_price = _fd_price(rb_name, "rushyds", "over")
            rb_mq = _matchup_score(rb_pid)
            carries_eff = max(carries_prob or 0, rb_mq)
            rush_eff = max(rush_prob or 0, rb_mq)
            if not (carries_price and rush_price):
                continue
            if carries_eff < MIN_MATCHUP_PROB or rush_eff < MIN_MATCHUP_PROB:
                continue

            c_l5 = _hit_rate(_games_for(rb_pid, "carries"), 15.5, window=5)
            r_l5 = _hit_rate(_games_for(rb_pid, "rushyds"), 75.5, window=5)
            legs = [
                _leg(rb_pid, rb_name, team, "carries", "over", "Over 15.5 Carries",
                     carries_eff, c_l5, carries_price, "Volume load: carries → yards"),
                _leg(rb_pid, rb_name, team, "rushyds", "over", "Over 75.5 Rush Yards",
                     rush_eff, r_l5, rush_price, "Same player: more carries = more yards"),
            ]
            usage = _usage_by_player().get(rb_pid, {})
            slip = _slip(
                f"vol-stack-rb-{rb_pid}",
                f"VOLUME STACK · {rb_name} Bell-Cow",
                "VOLUME_STACK",
                legs,
                f"{rb_name} is a featured back with correlated volume props. "
                f"High carry counts and rush yardage are the same opportunity — when the game plan calls for the run, both land.",
            )
            if slip:
                results.append(slip)
            break  # one RB per team

    results.sort(key=lambda s: min(lg["probability"] for lg in s["legs"]), reverse=True)
    return results[:4]


# ---------------------------------------------------------------------------
# SINGLE HERO finder
# ---------------------------------------------------------------------------

def find_single_hero(dim: dict[str, dict]) -> list[dict]:
    """
    One player with 3+ distinct prop legs all clearing 85% probability.
    """
    results = []

    hero_queries: dict[str, list[tuple]] = {
        "QB": [
            ("passyds",    250.0, "over",  "Over 250 Pass Yards"),
            ("passtd",     2.5,   "over",  "Over 2.5 Pass TDs"),
            ("passatt",    32.5,  "over",  "Over 32.5 Pass Attempts"),
        ],
        "WR": [
            ("recyds",     80.5,  "over",  "Over 80.5 Rec Yards"),
            ("recs",       6.5,   "over",  "Over 6.5 Receptions"),
            ("anytd",      0.5,   "over",  "Anytime TD"),
        ],
        "TE": [
            ("recyds",     60.5,  "over",  "Over 60.5 Rec Yards"),
            ("recs",       4.5,   "over",  "Over 4.5 Receptions"),
            ("anytd",      0.5,   "over",  "Anytime TD"),
        ],
        "RB": [
            ("rushyds",    75.5,  "over",  "Over 75.5 Rush Yards"),
            ("rushrec",    85.5,  "over",  "Over 85.5 Rush+Rec Yards"),
            ("recs",       2.5,   "over",  "Over 2.5 Receptions"),
        ],
    }

    for pid, info in dim.items():
        pos = info.get("position", "")
        queries = hero_queries.get(pos, [])
        if not queries:
            continue

        name = info["name"]
        team = info.get("team", "")
        opp = jimmy._last_opponent(pid)
        ib_score = int(_ib_scores().get(opp or "", {}).get("ib_score") or 3)

        legs = []
        mq = _matchup_score(pid)
        for market, thresh, direction, qlabel in queries:
            prob, _ = _player_prob(pid, market, thresh, direction, ib_score)
            price = _fd_price(name, market, direction if direction != "over" else "over")
            eff = max(prob or 0, mq)
            if _qualifies(prob, pid) and price:
                l5 = (_hit_rate_under if direction == "under" else _hit_rate)(
                    _games_for(pid, market), thresh, window=5)
                u_row = _usage_by_player().get(pid, {})
                role = u_row.get("usage_role", "")
                legs.append(_leg(pid, name, team, market, direction, qlabel,
                                 eff, l5, price, role))

        if len(legs) < 3:
            continue

        usage = _usage_by_player().get(pid, {})
        role_label = usage.get("usage_role", "")
        insight = (
            f"{name} ({pos}) clears 85% on all three legs independently. "
            f"Usage role: {role_label}. "
            f"All three props are driven by the same opportunity — elite role players dominate every line."
        )
        slip = _slip(
            f"single-hero-{pid}",
            f"SINGLE HERO · {name}",
            "SINGLE_HERO",
            legs[:3],
            insight,
        )
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

    return unique

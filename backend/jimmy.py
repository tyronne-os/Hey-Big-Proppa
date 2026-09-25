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
    - matchup      : 1 - (opponent defense toxicity_index_0_100 / 100) --
                      inverted, since a tougher opposing defense should
                      LOWER an offensive player's probability
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

HEURISTIC. NOT BACKTESTED. Same caveat every other pond in this lake
carries -- see docs/HANDOFF.md sec 7 lesson 9.
"""
from __future__ import annotations

from functools import lru_cache

import breakout
import data


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


def jimmy_score(player_id: str, hit_rate: float | None, market_slug: str | None = None,
                direction: str = "over") -> float | None:
    components: list[float] = []

    if hit_rate is not None:
        components.append(hit_rate)

    usage = _usage_index().get(player_id)
    if usage is not None:
        components.append(usage / 100)

    opponent = next_opponent(player_id)
    toxicity = _defense_toxicity().get(opponent) if opponent else None
    if toxicity is not None:
        components.append(1 - toxicity / 100)

    if not components:
        return None

    score = sum(components) / len(components)

    if market_slug == "anytd":
        redzone = _redzone_i5_share().get(player_id)
        if redzone is not None:
            score = min(1.0, score + min(0.15, redzone * 0.3))

    return round(score * regression_factor(player_id, direction), 3)

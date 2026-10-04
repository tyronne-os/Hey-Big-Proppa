"""
RED ZONE EFFORT -- the prop we bet instead of "who scores".

Who gets the touchdown is the offensive coordinator's call at the goal line. The stats cannot see it, and
on Thursday 2026-10-01 (PIT @ CLE) every touchdown leg we took lost while 15 of 17 effort legs cashed:
Jaylen Warren ran for 93 yards and caught 3 passes, and the touchdowns went to three other players.

So from NFL week 4 on, the engine does not offer touchdown-scorer predictions. In each slot where a TD leg
used to go, it puts that player's EFFORT leg: the yardage rung it takes to drive the ball to the red zone,
picked so it pays about what his touchdown paid. Concretely: the biggest alternate yardage rung (rushing for
running backs and quarterbacks, receiving for receivers and tight ends) that the Big Proppa Line still rates
at least as likely as FanDuel rates his touchdown. Same payout neighbourhood, but now the bet rides on work
the numbers can measure.

Prices: when the lake holds FanDuel's alternate rung for this game it is used as-is. Otherwise the leg shows
a fair price (estimated, marked as such) and the bettor takes the matching rung in the FanDuel app.
"""
from __future__ import annotations

import math

import bpl
import data

# User directive 2026-10-02: no touchdown-scorer queries or predictions for NFL week 4, and the player-prop
# philosophy moves from "who scores" to "the effort it takes to reach the red zone". Change this one number to
# move the policy.
TD_PROPS_OFF_FROM_WEEK = 4
TD_MARKETS = {"anytd", "firsttd", "lasttd", "passtd"}
HAIRCUT = 0.05                       # same caution SPY BOY applies to model probabilities

EFFORT_MARKET = {"RB": "rushyds", "QB": "rushyds", "WR": "recyds", "TE": "recyds", "FB": "rushyds"}
LABEL = {"rushyds": "RUSHING YARDS", "recyds": "RECEIVING YARDS", "passyds": "PASSING YARDS"}


def td_props_off(week: int | None, sport: str = "NFL") -> bool:
    return sport == "NFL" and week is not None and int(week) >= TD_PROPS_OFF_FROM_WEEK


def td_blocked(week: int | None = None) -> bool:
    """HARD RULE gate used at every leg-building and ticket-intake point. A touchdown-scorer leg is blocked
    whenever the week is week 4+ OR unknown -- an unknown week must never let a TD leg through."""
    return week is None or int(week) >= TD_PROPS_OFF_FROM_WEEK


def strip_td_legs(legs: list[dict]) -> list[dict]:
    """Drop any touchdown-scorer leg (including combos that contain one)."""
    return [l for l in legs if not _has_td(l)]


def _rungs(market: str) -> list[float]:
    if market == "passyds":
        return [x + 0.5 for x in range(149, 400, 25)]
    return [x + 0.5 for x in range(9, 200, 10)]


def _american(p: float) -> int:
    d = 1 / p
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


def _implied(american: float) -> float:
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def _fanduel_ladder(pid: str, market: str, game_id: str | None) -> dict[float, int]:
    """FanDuel's alternate rungs for this player, market and game (line -> american odds)."""
    out: dict[float, int] = {}
    try:
        from jimmy_bpl import cached_sides
        for s in cached_sides():
            if (s.get("playerId") == pid and s.get("market") == market and s.get("alt") and s["direction"] == "over"
                    and (not game_id or s.get("gameId") == game_id)):
                out[float(s["line"])] = int(s["odds"])
    except Exception:
        pass
    return out


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def effort_leg(pid: str, name: str, team: str, td_odds: float | None, game_id: str | None = None,
               position: str | None = None, market: str | None = None) -> dict | None:
    """The yardage rung that pays like this player's touchdown, scored by the Big Proppa Line."""
    from jimmy_bpl import p_over
    pos = position or data.player_dimension().get(pid, {}).get("position", "")
    market = market or EFFORT_MARKET.get(pos)
    if not market or not td_odds:
        return None
    row = bpl.nfl_player_line(pid, market, name, team)
    raw = (row.get("parts") or {}).get("raw")
    if not raw:
        return None
    td_odds = float(td_odds)
    p_td = _implied(td_odds)
    pick = None                                     # (rung, model p, odds, estimated?)
    ladder = _fanduel_ladder(pid, market, game_id)
    # 1) a real FanDuel rung that pays at least ~what his TD paid, with the best edge on the BPL
    best_edge = None
    for rung, odds in ladder.items():
        p = p_over(market, raw, rung)
        if p is None or _dec(odds) < 0.85 * _dec(td_odds):
            continue
        edge = p - _implied(odds)
        if best_edge is None or edge > best_edge:
            best_edge, pick = edge, (rung, p, odds, False)
    # 2) no usable ladder: the biggest rung the BPL still rates at least as likely as his TD, at his TD price
    if not pick:
        for rung in _rungs(market):
            p = p_over(market, raw, rung)
            if p is not None and p >= p_td:
                pick = (rung, p, int(td_odds), True)
    if not pick:
        return None
    rung, p, odds, est = pick
    p_used = max(0.01, round(p - HAIRCUT, 4))
    return {
        "playerId": pid, "name": name, "team": team, "pos": pos,
        "prop": f"RED ZONE EFFORT: {math.ceil(rung)}+ {LABEL[market]}",
        "market": market, "line": rung, "direction": "over",
        "odds": int(odds), "oddsEstimated": est,
        "probability": p_used, "l5": p_used,
        "replaces": f"{name} anytime TD ({'+' if td_odds > 0 else ''}{int(td_odds)})",
        "correlationNote": (f"Takes the place of his touchdown leg ({'+' if td_odds > 0 else ''}{int(td_odds)}). "
                            f"Big Proppa Line {row.get('bpl')}: {round(p * 100)}% to clear {math.ceil(rung)}+ "
                            f"vs {round(p_td * 100)}% FanDuel gave his TD."
                            + (" Estimated price: take the matching rung in the FanDuel app." if est else " FanDuel alternate rung price.")),
        "photoUrl": data.photo_url(pid),
    }


def _has_td(leg: dict) -> bool:
    return leg.get("market") in TD_MARKETS or any(c.get("market") in TD_MARKETS for c in leg.get("components") or [])


def swap_td_legs(legs: list[dict], game_id: str | None = None) -> list[dict]:
    """Replace every touchdown leg with that player's effort leg; drop the ones with no effort read.
    A combo leg with a TD inside it ("85.5 rec yds + anytime TD") becomes one bigger yardage rung that pays
    like the whole combo."""
    out = []
    for l in legs:
        if not _has_td(l):
            out.append(l)
            continue
        yard = next((c["market"] for c in l.get("components") or [] if c.get("market") in LABEL), None)
        e = effort_leg(l.get("playerId", ""), l.get("name", ""), l.get("team", ""), l.get("odds"),
                       game_id or l.get("gameId"), l.get("pos"), market=yard)
        if e:
            if l.get("components"):
                e["replaces"] = f"{l['name']}: {l.get('prop', 'combo with a TD')}"
            out.append(e)
    return out

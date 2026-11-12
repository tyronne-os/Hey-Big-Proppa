"""
Combination guardrails for BETTER-VERSE: the stricter of FanDuel's and DraftKings' parlay rules.

A slip is a list of menu items (betterverse_data.menu). validate() says whether either book would refuse it;
price() returns the decimal odds a book would pay, including the same-game-parlay haircut books apply when
legs from one game move together.
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

MAX_LEGS = 10            # FD 25 / DK 20 allowed; nobody real goes past 10 in a season sim
SGP_BASE = 0.92          # every multi-leg same-game group gets priced below the naive product
SGP_CORR = 0.85          # extra haircut per positively-correlated pair inside one game
SGP_FLOOR = 0.55

QB_STACK = {"pass_yds", "pass_tds", "completions", "pass_att"}
CATCHER = {"rec_yds", "receptions", "anytime_td", "rush_rec_yds"}
YARDAGE_OVERS = {"pass_yds", "rec_yds", "rush_yds", "rush_rec_yds", "receptions", "completions", "pass_att", "pass_tds"}
OVERLAP = {frozenset({"rush_yds", "rush_rec_yds"}), frozenset({"rec_yds", "rush_rec_yds"}),
           frozenset({"completions", "pass_att"})}


def validate(legs: list[dict]) -> tuple[bool, str]:
    if not 1 <= len(legs) <= MAX_LEGS:
        return False, "leg count"
    seen_player_mk: set = set()
    per_game: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    player_mks: dict[str, set] = defaultdict(set)
    for leg in legs:
        mk, gid = leg["market"], leg["game_id"]
        if leg["player_id"]:
            key = (leg["player_id"], mk)
            if key in seen_player_mk:
                return False, "same player, same market twice (incl. over+under)"
            seen_player_mk.add(key)
            for other in player_mks[leg["player_id"]]:
                if frozenset({mk, other}) in OVERLAP:
                    return False, "overlapping stat on one player (e.g. rush yds + rush+rec yds)"
            player_mks[leg["player_id"]].add(mk)
        per_game[gid][mk].append(leg)
    for gid, mks in per_game.items():
        for mk in ("spread", "ml", "total"):
            if len(mks.get(mk, [])) > 1:
                return False, f"two {mk} legs in one game"
        if mks.get("spread") and mks.get("ml"):
            return False, "spread + moneyline in one game"
    return True, "ok"


def _correlated(a: dict, b: dict) -> bool:
    if a["game_id"] != b["game_id"]:
        return False
    ma, mb = a["market"], b["market"]
    same_team = a["team"] == b["team"]
    up = lambda x: x["side"] in ("over", "yes")
    if same_team and up(a) and up(b) and ({ma, mb} & QB_STACK) and ({ma, mb} & CATCHER):
        return True                                           # QB + his receiver
    if "total" in (ma, mb) and ma != mb:
        tot, oth = (a, b) if ma == "total" else (b, a)
        if tot["side"] == "over" and up(oth) and oth["market"] in YARDAGE_OVERS | {"anytime_td"}:
            return True                                       # game over + any player over
    if "ml" in (ma, mb) or "spread" in (ma, mb):
        line, oth = (a, b) if ma in ("ml", "spread") else (b, a)
        if oth["player_id"] and line["team"] == oth["team"] and up(oth):
            return True                                       # team wins + its player goes over
    return False


def price(legs: list[dict]) -> tuple[float, bool]:
    """(decimal odds, is_sgp)."""
    dec = 1.0
    for leg in legs:
        dec *= leg["dec"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for leg in legs:
        groups[leg["game_id"]].append(leg)
    sgp = False
    for g in groups.values():
        if len(g) < 2:
            continue
        sgp = True
        sub = 1.0
        for leg in g:
            sub *= leg["dec"]
        factor = SGP_BASE * SGP_CORR ** sum(_correlated(x, y) for x, y in combinations(g, 2))
        factor = max(SGP_FLOOR, factor)
        dec = dec / sub * max(1.01, 1 + (sub - 1) * factor)
    return round(dec, 4), sgp


def signature(legs: list[dict], sgp: bool) -> str:
    """The shape of a slip, independent of who is on it: e.g. 'anytime_td:yes x3' or 'ml:fav|spread:dog +SGP'."""
    parts: dict[str, int] = defaultdict(int)
    for leg in legs:
        parts[f"{leg['market']}:{leg['side']}"] += 1
    body = "|".join(f"{k} x{n}" if n > 1 else k for k, n in sorted(parts.items()))
    return body + (" +SGP" if sgp else "")

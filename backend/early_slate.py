"""
EARLY-GAMES SLATE -- the featured Sunday tickets, built from one kickoff window at a time.

Three featured slips (TAKE IT by default) + two Crazy Horses (FAKE IT by default):
  WR 60 CLUB    5 receivers in an 8-target role (targets/game from player_usage) priced at 60+ receiving yards
  RB COMBO      5 backs, each a combo leg: 50+ rushing yards AND 3+ receptions
  OVERS         the 5 early games the Big Proppa Line likes most to go OVER the game total
  CRAZY HORSE   two tickets of 8 high-probability effort props each (no player on both horses)

HARD RULE (red_zone.py): no touchdown-scorer legs. Every market here is yardage, receptions or game total.
Probabilities come from the Big Proppa Line (jimmy_bpl.p_over) minus the same 5-point haircut SPY BOY uses.
Prices: FanDuel's main line when this exact line is posted, otherwise an ESTIMATED price from the haircut
probability (marked oddsEstimated; take the matching rung in the FanDuel app).
The 50% profit boost is the display promotion from odds.compute_parlay (fictitious until the book confirms it).

New window next: call build("evening") -- same code, later kickoffs.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import bpl
import data
import jimmy_bpl
import red_zone
from odds import compute_parlay

WAGER = 5.0
BOOST = 0.50
HAIRCUT = 0.05
WINDOWS = {"early": ("12:00", "13:30"), "evening": ("16:00", "23:59")}   # stadium-local kickoff
CACHE_SECONDS = 300
_cache: dict[str, tuple[float, dict]] = {}


def _slate_games(window: str, today: str | None = None) -> list[dict]:
    lo, hi = WINDOWS[window]
    day = today or datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    out = []
    for r in data.load("schedule"):
        if r["game_date"] == day and lo <= r["game_time_local"] <= hi:
            out.append({"gameId": r["game_id"], "away": r["away_team"], "home": r["home_team"], "time": r["game_time_local"]})
    return out


def _targets_per_game() -> dict[str, float]:
    out = {}
    for r in data.load("player_usage"):
        try:
            if r.get("spine_metric") == "targets" and float(r.get("games") or 0) > 0:
                out[r["player_id"]] = float(r["spine_opps"]) / float(r["games"])
        except (KeyError, ValueError):
            continue
    return out


def _price(side_by_key: dict, pid: str, market: str, rung: float, p_used: float) -> tuple[int, bool]:
    """FanDuel's posted price when this exact line is on the board, else a fair price from the haircut probability."""
    s = side_by_key.get((pid, market, "over", float(rung)))
    if s:
        return int(s["odds"]), False
    return red_zone._american(max(0.05, min(0.95, p_used))), True


def _prop_leg(pid, name, team, game_id, market, rung, sides_idx) -> dict | None:
    row = bpl.nfl_player_line(pid, market, name, team)
    raw = (row.get("parts") or {}).get("raw")
    if not raw:
        return None
    p = jimmy_bpl.p_over(market, raw, rung)
    if p is None:
        return None
    p_used = round(max(0.01, p - HAIRCUT), 4)
    odds, est = _price(sides_idx, pid, market, rung, p_used)
    label = {"recyds": "REC YDS", "rushyds": "RUSH YDS", "recs": "RECEPTIONS", "passyds": "PASS YDS"}[market]
    return {"playerId": pid, "name": name, "team": team, "market": market, "direction": "over", "line": rung,
            "prop": f"{math.ceil(rung)}+ {label}", "odds": odds, "oddsEstimated": est, "probability": p_used,
            "l5": p_used, "gameId": game_id, "bpl": row.get("bpl"), "photoUrl": data.photo_url(pid),
            "correlationNote": f"Big Proppa Line {row.get('bpl')}: {round(p * 100)}% to clear {math.ceil(rung)}+ ({round(p_used * 100)}% after haircut)."
                               + (" Estimated price: take the matching rung in the FanDuel app." if est else " FanDuel posted price.")}


def _slip(sid: str, title: str, series: str, legs: list[dict], insight: str, default_choice: str, stake: float = WAGER) -> dict | None:
    legs = red_zone.strip_td_legs(legs)
    if not legs:
        return None
    m = compute_parlay([l["odds"] for l in legs], wager=stake, boost=BOOST)
    p = math.prod(l["probability"] for l in legs)
    return {"id": sid, "title": title, "correlationType": series, "insight": insight, "legs": legs,
            "wager": stake, "boost": BOOST, "combinedDecimalOdds": m.combined_decimal, "payout": m.payout,
            "boostedPayout": m.boosted_payout, "boostedAmericanOdds": m.boosted_american,
            "hitProbability": round(p, 4), "confidence": round(100 * sum(l["probability"] for l in legs) / len(legs)),
            "week": legs[0].get("week"), "defaultChoice": default_choice, "tier": "EARLY GAMES"}


def build(window: str = "early", today: str | None = None, force: bool = False) -> dict:
    key = f"{window}:{today}"
    hit = _cache.get(key)
    if hit and not force and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    games = _slate_games(window, today)
    ids = {g["gameId"] for g in games}
    sides = [s for s in jimmy_bpl.cached_sides() if s["gameId"] in ids]
    idx = {(s["playerId"], s["market"], s["direction"], float(s["line"])): s for s in sides}
    week = sides[0]["week"] if sides else None
    tpg = _targets_per_game()
    pool = {}                                   # (pid, market) -> (name, team, gameId) for every priced player prop
    for s in sides:
        if not s.get("sport") and s["market"] in ("recyds", "rushyds", "recs", "passyds"):
            pool[(s["playerId"], s["market"])] = (s["name"], s["team"], s["gameId"])
    dim = data.player_dimension()
    pos = lambda pid: dim.get(pid, {}).get("position")   # noqa: E731

    # 1) WR 60 CLUB: 8-target role, 60+ receiving yards
    wrs = []
    for (pid, m), (name, team, gid) in pool.items():
        if m != "recyds" or pos(pid) != "WR" or tpg.get(pid, 0) < 7.0:
            continue
        leg = _prop_leg(pid, name, team, gid, "recyds", 59.5, idx)
        if leg:
            leg["week"] = week
            leg["correlationNote"] = f"{tpg[pid]:.1f} targets a game. " + leg["correlationNote"]
            wrs.append(leg)
    wrs = sorted(wrs, key=lambda l: -l["probability"])[:5]

    # 2) RB COMBO: 50+ rush yards AND 3+ receptions, one combo leg per back
    rbs = []
    for (pid, m), (name, team, gid) in pool.items():
        if m != "rushyds" or pos(pid) != "RB" or (pid, "recs") not in pool:
            continue
        a, b = _prop_leg(pid, name, team, gid, "rushyds", 49.5, idx), _prop_leg(pid, name, team, gid, "recs", 2.5, idx)
        if not (a and b):
            continue
        p = round(a["probability"] * b["probability"], 4)
        dec = math.prod(1 + (o / 100 if o > 0 else 100 / -o) for o in (a["odds"], b["odds"]))
        comp = lambda x: {k: x[k] for k in ("market", "direction", "line", "odds", "probability")}   # noqa: E731
        rbs.append({"playerId": pid, "name": name, "team": team, "market": "rushyds", "direction": "over", "line": 49.5,
                    "prop": "50+ RUSH YDS + 3+ REC", "odds": round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1)),
                    "oddsEstimated": a["oddsEstimated"] or b["oddsEstimated"], "probability": p, "l5": p, "gameId": gid, "week": week,
                    "components": [comp(a), comp(b)], "photoUrl": data.photo_url(pid),
                    "correlationNote": f"Both must land: {round(a['probability'] * 100)}% for 50+ rushing yards x {round(b['probability'] * 100)}% for 3+ catches. "
                                       "Price is the two legs multiplied."})
    rbs = sorted(rbs, key=lambda l: -l["probability"])[:5]

    # 3) OVERS: the 5 early games the BPL likes most to go over the total
    overs = [dict(s, probability=round(s["modelP"] - HAIRCUT, 4), photoUrl=None) for s in sides
             if s["market"] == "nfl_total" and s["direction"] == "over"]
    overs = sorted(overs, key=lambda l: -l["probability"])[:5]
    for l in overs:
        l["correlationNote"] = l.get("note") or l.get("correlationNote", "")

    # 4) CRAZY HORSES: 8 high-probability effort props each, no player on both
    ranked, seen = [], set()
    for s in sorted(sides, key=lambda s: -s["modelP"]):
        if s.get("sport") or s["market"] not in ("recyds", "rushyds", "recs", "passyds") or s["direction"] != "over":
            continue
        if s["playerId"] in seen:
            continue
        seen.add(s["playerId"])
        p_used = round(min(s["modelP"] - HAIRCUT, s["bookP"] + 0.10), 4)
        ranked.append({"playerId": s["playerId"], "name": s["name"], "team": s["team"], "market": s["market"], "direction": "over",
                       "line": s["line"], "prop": s["prop"], "odds": s["odds"], "oddsEstimated": False, "probability": p_used, "l5": p_used,
                       "gameId": s["gameId"], "week": week, "photoUrl": data.photo_url(s["playerId"]),
                       "correlationNote": f"Big Proppa Line {s['bpl']:g} vs FanDuel line {s['line']:g}. {s['recentHits']}/{s['recentGames']} recent games cleared it."})
    ranked.sort(key=lambda l: -l["probability"])
    horses = []
    for chunk in (ranked[0:16:2], ranked[1:16:2]):            # alternate picks so both horses share the strongest legs fairly
        h = _slip(f"CRZ-{window.upper()}-{len(horses) + 1}", f"CRAZY HORSE {len(horses) + 1} · {len(chunk)}-LEG", "CRAZY_HORSE", chunk,
                  f"{len(chunk)} of the likeliest effort props on the {window} slate, every one a yardage or reception line. "
                  "A lottery ticket: the legs multiply, so the payout is the point. No touchdown legs.", "FAKE IT")
        if h:
            horses.append(h)

    slips = [s for s in (
        _slip(f"EARLY-WR-{week}", "WR 60 CLUB", "FEATURED", wrs,
              "Five receivers in an 8-target role, each priced at 60+ receiving yards.", "TAKE IT"),
        _slip(f"EARLY-RB-{week}", "RB WORKHORSES", "FEATURED", rbs,
              "Five backs who need 50+ rushing yards and 3+ catches. Each leg is that combo.", "TAKE IT"),
        _slip(f"EARLY-OVR-{week}", "EARLY OVERS", "FEATURED", overs,
              "The five early games the Big Proppa Line rates most likely to finish over the posted total.", "TAKE IT"),
    ) if s]
    out = {"window": window, "week": week, "games": games, "slips": slips, "crazyHorses": horses,
           "boostNote": "50% profit boost is a display promotion; confirm the boost in your book."}
    _cache[key] = (time.time(), out)
    return out

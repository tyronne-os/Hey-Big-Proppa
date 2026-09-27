"""
JIMMY (BPL mode) -- the featured single-player parlay.

One running back on one ticket: anytime touchdown + 70 rushing yards + 3 receptions, all FanDuel prices,
for the RB the model likes best. Rushing and reception legs come from FanDuel's alternate ladders (the rung
nearest 70 yards and the 3+ reception rung) and are scored by the Big Proppa Line with the same 5-point
haircut and FanDuel-credit cap SPY BOY uses. The touchdown leg has no model behind it (the lake has no TD
model), so it carries FanDuel's own implied probability and claims no edge.

Same-game caveat: these legs are positively correlated, so FanDuel's same-game price will be LOWER than the
product of the three prices shown here. The payout on the card is an estimate for that reason.
"""
from __future__ import annotations

import math

import data

STAKE = 10.0
RUSH_TARGET = 70
MIN_P = 0.30


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _american(decimal: float) -> int:
    return int(round((decimal - 1) * 100)) if decimal >= 2 else int(round(-100 / (decimal - 1)))


def _p(leg: dict, haircut: float = 0.05, credit: float = 0.25) -> float:
    return min(leg["modelP"] - haircut, leg["bookP"] + credit)


def _fanduel_td(name: str) -> float | None:
    row = data.best_price_for(name, "anytd")
    if not row or row.get("best_moneyline_book") != "fanduel" or not row.get("best_moneyline_price"):
        return None
    try:
        return float(row["best_moneyline_price"])
    except ValueError:
        return None


def featured(sides: list[dict]) -> dict | None:
    by: dict[tuple[str, str], list[dict]] = {}
    for l in sides:
        if not l.get("sport") and l["direction"] == "over":
            by.setdefault((l["playerId"], l["market"]), []).append(l)
    dim = data.player_dimension()
    best = None
    for pid, d in dim.items():
        if d.get("position") != "RB":
            continue
        td_price = _fanduel_td(d["name"])
        rush = [l for l in by.get((pid, "rushyds"), []) if 50 <= l["line"] <= 90 and _p(l) >= MIN_P]
        rec = [l for l in by.get((pid, "recs"), []) if l["line"] == 2.5 and _p(l) >= MIN_P]
        if td_price is None or not rush or not rec:
            continue
        r = min(rush, key=lambda l: abs(l["line"] - (RUSH_TARGET - 0.5)))
        c = rec[0]
        td_p = 1 / _dec(td_price)
        score = _p(r) * _p(c) * td_p
        if best is None or score > best[0]:
            best = (score, pid, d, r, c, td_price, td_p)
    if not best:
        return None
    _, pid, d, r, c, td_price, td_p = best
    legs = [
        {"playerId": pid, "name": d["name"], "team": d["team"], "market": "anytd", "direction": "over", "line": 0.5,
         "prop": "ANYTIME TOUCHDOWN", "probability": round(td_p, 3), "l5": round(td_p, 3), "odds": int(td_price),
         "correlationNote": "FanDuel's own implied probability; the lake has no touchdown model, so no edge is claimed.", "photoUrl": data.photo_url(pid)},
        {"playerId": pid, "name": d["name"], "team": d["team"], "market": "rushyds", "direction": "over", "line": r["line"],
         "prop": f"{math.ceil(r['line'])}+ RUSHING YARDS", "probability": round(_p(r), 3), "l5": round(_p(r), 3), "odds": r["odds"],
         "correlationNote": r["correlationNote"] if "correlationNote" in r else f"BPL {r['bpl']:g} vs FanDuel rung {r['line']:g}", "photoUrl": data.photo_url(pid)},
        {"playerId": pid, "name": d["name"], "team": d["team"], "market": "recs", "direction": "over", "line": c["line"],
         "prop": f"{math.ceil(c['line'])}+ RECEPTIONS", "probability": round(_p(c), 3), "l5": round(_p(c), 3), "odds": c["odds"],
         "correlationNote": f"BPL {c['bpl']:g} vs FanDuel rung {c['line']:g}", "photoUrl": data.photo_url(pid)},
    ]
    dec = math.prod(_dec(l["odds"]) for l in legs)
    p = math.prod(l["probability"] for l in legs)
    return {
        "id": f"FEAT-{pid[-6:]}", "title": f"{d['name']} · SAME-PLAYER PARLAY", "correlationType": "FEATURED",
        "player": {"name": d["name"], "team": d["team"], "position": d.get("position", "RB"), "photoUrl": data.photo_url(pid)},
        "legs": legs, "wager": STAKE, "boost": 0.0, "combinedDecimalOdds": round(dec, 4),
        "payout": round(STAKE * dec, 2), "boostedPayout": round(STAKE * dec, 2), "boostedAmericanOdds": _american(dec),
        "hitProbability": round(p, 4), "confidence": round(100 * sum(l["probability"] for l in legs) / 3),
        "insight": ("Legs multiplied: FanDuel prices same-player parlays lower than this because the legs move together, so treat the payout "
                    "as an upper estimate. The lake has no 2+ touchdown price, so the touchdown leg is anytime."),
        "week": None,
    }

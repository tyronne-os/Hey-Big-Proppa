"""
JIMMY (BPL mode) -- deterministic parlay builder. No LLM.

Jimmy no longer invents picks. He reads the official BIG PROPPA LINE (bpl.py),
compares it to the FanDuel line, and only groups legs where the lake says the
price is wrong:

  1. Leg probability. The BPL is a 50/50 line. How far the FanDuel line sits
     from it becomes a hit probability through the 2024-2025 backtest
     distribution of actual / BPL (lake/gold/nfl/bpl_residual_quantiles.csv):
         P(over L) = share of backtest games where actual / BPL > L / BPL
  2. Leg value.  EV = P(side) * FanDuel decimal price - 1. A leg qualifies only
     at EV >= MIN_LEG_EV, so the vig has to be beaten before anything is grouped.
     Guards: no Out/Doubtful/Questionable players, 2+ games this season, the player
     inside the population the backtest was fit on, and apparent edges above
     MAX_LEG_EV held out as probable news the lake has not seen.
  3. Tickets.    2 to 5 legs, never two legs from the same game (FanDuel prices a
     standard parlay as the product of its legs only when the legs are
     independent). Ranked by ticket EV = product(P) * product(decimal) - 1.
  4. Stake.      Quarter-Kelly share of bankroll, shown per ticket.

FanDuel is the only book used for prices. Every ticket is logged to MY BOO as a
SIM order once (TAKE IT on the Big Proppa page promotes it to POW).

Honest limits: the BPL was backtested for accuracy, but the lake has no
historical FanDuel prop lines, so the edge against the book itself is not yet
proven. MY BOO's graded SIM record is how it gets proven.
"""
from __future__ import annotations

import bisect
import hashlib
import itertools
from functools import lru_cache

import bpl
import data

# The previous Jimmy (LLM hunt, nuggets, deep dive, correlation engine) is paused,
# not deleted. Set to False to bring the LLM paths back.
JIMMY_LLM_PAUSED = True

BOOK = "fanduel"
MIN_LEG_EV = 0.05          # a leg must beat FanDuel's price by 5%
# An apparent edge above this is almost always news the lake does not have yet
# (injury, role change, depth chart). Those legs are held out, not bet.
MAX_LEG_EV = 0.25
MIN_LEG_P, MAX_LEG_P = 0.40, 0.75
MIN_GAMES_THIS_SEASON = 2
# the backtest only fit players at or above these per-game baselines; outside
# that population the hit probabilities are not calibrated
MIN_BASELINE = {"rushyds": 25.0, "recyds": 25.0, "recs": 2.5, "passyds": 150.0}
EXCLUDE_STATUS = {"Out", "Doubtful", "Questionable"}
MAX_CANDIDATES = 14        # best legs considered for combination
TICKET_SIZES = (2, 3, 4, 5)
TICKETS_PER_SIZE = 2
STAKE = 10.0

MARKET_LABEL = {"rushyds": "RUSH YDS", "recyds": "REC YDS", "recs": "RECEPTIONS", "passyds": "PASS YDS"}


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _american(decimal: float) -> int:
    return int(round((decimal - 1) * 100)) if decimal >= 2 else int(round(-100 / (decimal - 1)))


@lru_cache(maxsize=1)
def _quantiles() -> dict[str, tuple[list[float], list[float]]]:
    out: dict[str, tuple[list[float], list[float]]] = {}
    for r in data.load("bpl_residual_quantiles"):
        qs, rs = out.setdefault(r["market"], ([], []))
        qs.append(float(r["q"]))
        rs.append(float(r["ratio"]))
    return out


def p_over(market: str, bpl_raw: float, line: float) -> float | None:
    """Backtest share of games that finished above `line`, given this BPL."""
    table = _quantiles().get(market)
    if not table or bpl_raw <= 0:
        return None
    qs, ratios = table
    x = line / bpl_raw
    if x <= ratios[0]:
        return 1 - qs[0]
    if x >= ratios[-1]:
        return 1 - qs[-1]
    i = bisect.bisect_left(ratios, x)
    r0, r1, q0, q1 = ratios[i - 1], ratios[i], qs[i - 1], qs[i]
    cdf = q0 + (q1 - q0) * ((x - r0) / (r1 - r0) if r1 > r0 else 0)
    return round(1 - cdf, 4)


@lru_cache(maxsize=1)
def _injured() -> set[str]:
    """gsis ids on the latest official injury report as Out, Doubtful or Questionable."""
    rows = data.load("injury_report_official")
    if not rows:
        return set()
    latest = max((int(r["season"]), int(r["week"])) for r in rows)
    return {r["gsis_id"] for r in rows
            if (int(r["season"]), int(r["week"])) == latest and r.get("report_status") in EXCLUDE_STATUS}


@lru_cache(maxsize=1)
def _player_index() -> dict[tuple[str, str], str]:
    return {(data.normalize_name(d["name"]), d["team"]): pid for pid, d in data.player_dimension().items()}


def candidate_legs() -> list[dict]:
    """Every FanDuel prop in a BPL market, scored against the BPL. Qualifying legs only."""
    idx = _player_index()
    nxt = bpl.next_games()
    legs: list[dict] = []
    for r in data.load("prop_line_rotowire"):
        market = r.get("market_slug")
        if r.get("book_slug") != BOOK or market not in bpl.NFL_MARKETS or not r.get("line"):
            continue
        team = r.get("team", "")
        game = nxt.get(team)
        if not game or game["opp"] != r.get("opponent", "").lstrip("@"):
            continue  # stale prop for a game already played
        pid = idx.get((data.normalize_name(r.get("player_name", "")), team))
        if not pid:
            continue
        if pid in _injured():
            continue
        row = bpl.nfl_player_line(pid, market, r["player_name"], team)
        parts = row.get("parts")
        if not parts or len(row["l5"]) < MIN_GAMES_THIS_SEASON or parts["baseline"] < MIN_BASELINE[market]:
            continue
        line = float(r["line"])
        po = p_over(market, parts["raw"], line)
        if po is None:
            continue
        for side, p, price in (("over", po, r.get("over_price_american")), ("under", 1 - po, r.get("under_price_american"))):
            if not price:
                continue
            american = float(price)
            dec = _dec(american)
            ev = p * dec - 1
            if not (MIN_LEG_EV <= ev <= MAX_LEG_EV) or not (MIN_LEG_P <= p <= MAX_LEG_P):
                continue
            gap = bpl.diff_pct(row["bpl"], line)
            legs.append({
                "playerId": pid, "name": r["player_name"], "team": team, "market": market,
                "direction": side, "line": line, "odds": int(american), "decimal": round(dec, 4),
                "probability": round(p, 4), "impliedProbability": round(1 / dec, 4), "ev": round(ev, 4),
                "bpl": row["bpl"], "gapPct": gap, "gameId": game["gameId"], "week": game["week"],
                "prop": f"{side.upper()} {line:g} {MARKET_LABEL[market]}",
                "l5": row["seasonAvg"] or 0,
                "correlationNote": (f"BPL {row['bpl']:g} vs FanDuel {line:g} ({gap:+.1f}%) · "
                                    f"hit {p:.0%} vs FanDuel implied {1 / dec:.0%} · EV {ev:+.0%}"),
            })
    # one side per player-market (the better EV), best first
    best: dict[tuple[str, str], dict] = {}
    for leg in legs:
        k = (leg["playerId"], leg["market"])
        if k not in best or leg["ev"] > best[k]["ev"]:
            best[k] = leg
    return sorted(best.values(), key=lambda l: -l["ev"])


def _ticket(legs: tuple[dict, ...]) -> dict:
    dec = 1.0
    p = 1.0
    for leg in legs:
        dec *= leg["decimal"]
        p *= leg["probability"]
    ev = p * dec - 1
    kelly = max(0.0, (p * dec - 1) / (dec - 1)) / 4
    sig = "|".join(sorted(f"{l['playerId']}:{l['market']}:{l['direction']}:{l['line']}" for l in legs))
    tid = hashlib.sha1(sig.encode()).hexdigest()[:8].upper()
    payout = round(STAKE * dec, 2)
    american = _american(dec)
    return {
        "id": f"BPL-{tid}",
        "title": f"BPL {len(legs)}-LEG {'+' if american > 0 else ''}{american}",
        "correlationType": "BPL_EDGE",
        "insight": (f"Hit chance {p:.1%} vs FanDuel implied {1 / dec:.1%} · ticket EV {ev:+.0%} · "
                    f"quarter-Kelly {kelly:.1%} of bankroll. One leg per game."),
        "legs": [{k: v for k, v in l.items() if k != "decimal"} for l in legs],
        "wager": STAKE, "boost": 0.0,
        "combinedDecimalOdds": round(dec, 4), "payout": payout, "boostedPayout": payout,
        "boostedAmericanOdds": american,
        "hitProbability": round(p, 4), "expectedValue": round(ev, 4), "kellyPct": round(kelly * 100, 2),
        "week": legs[0]["week"], "book": BOOK, "version": bpl.BPL_VERSION,
    }


def build_parlays() -> list[dict]:
    pool = candidate_legs()[:MAX_CANDIDATES]
    out: list[dict] = []
    for size in TICKET_SIZES:
        combos = [c for c in itertools.combinations(pool, size) if len({l["gameId"] for l in c}) == size]
        ranked = sorted((_ticket(c) for c in combos), key=lambda t: -t["expectedValue"])
        out.extend(ranked[:TICKETS_PER_SIZE])
    return out


def log_to_myboo(slips: list[dict]) -> None:
    """MY BOO notes every ticket Jimmy posts, once, as a SIM order."""
    import myboo
    season = bpl._current_season()
    for s in slips:
        myboo.create_ticket(
            "SIM", s["title"] + f" · {s['id']}",
            [{"player_name": l["name"], "team": l["team"], "market": l["market"], "direction": l["direction"],
              "line": l["line"], "odds": l["odds"], "probability": l["probability"], "game_date": ""} for l in s["legs"]],
            season, s["week"], s["boostedAmericanOdds"], s["wager"], f"JIMMY BPL · EV {s['expectedValue']:+.0%}",
        )

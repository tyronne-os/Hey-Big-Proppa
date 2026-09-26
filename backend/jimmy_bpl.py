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

SPY BOY is the aggressive series (see spy_boy_legs). FanDuel is the only book used for prices. Every ticket is logged to MY BOO as a
SIM order once (TAKE IT on the Big Proppa page promotes it to POW).

Honest limits: the BPL was backtested for accuracy, but the lake has no
historical FanDuel prop lines, so the edge against the book itself is not yet
proven. MY BOO's graded SIM record is how it gets proven.
"""
from __future__ import annotations

import bisect
import hashlib
import itertools
import math
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
# SPY BOY (aggressive series): leg floor 75% vs the safe series' 85%
SPY_MIN_P = 0.75
# Measured shortfall of the BPL's over-probabilities on 2026 receiving/rushing tails
# (scripts/check_bpl_live.py: predicted 4-8 pts above actual, zero-stat games included).
SPY_HAIRCUT = 0.05
SPY_MAX_CREDIT = 0.25      # credit at most +25 pts over FanDuel's own probability
SPY_MIN_BOOK = 0.60        # FanDuel itself must price the leg at 60%+ (the model is not the only voice)
SPY_MIN_RECENT = 0.80      # leg must have cleared in 80%+ of this season's games
SPY_SIZES = (3, 4, 5)
SPY_MIN_DECIMAL = 4.0      # +300 or better, otherwise it is not an aggressive ticket
SPY_KELLY_CAP = 0.02       # stake never above 2% of bankroll
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


def _side_dicts(pid: str, name: str, team: str, game: dict, market: str, line: float, row: dict,
                offers: list[tuple[str, float, float, float]], alt: bool) -> list[dict]:
    """offers: (side, decimal, american, book probability). Scores each side against the BPL."""
    parts = row["parts"]
    po = p_over(market, parts["raw"], line)
    if po is None:
        return []
    recent = [g["value"] for g in row["l5"]]
    gap = bpl.diff_pct(row["bpl"], line)
    out = []
    for side, dec, px, book_p in offers:
        p = po if side == "over" else 1 - po
        hits = sum(1 for v in recent if (v > line if side == "over" else v < line))
        out.append({
            "playerId": pid, "name": name, "team": team, "market": market,
            "direction": side, "line": line, "odds": int(px), "decimal": round(dec, 4),
            "modelP": round(p, 4), "bookP": round(book_p, 4), "recentHits": hits, "recentGames": len(recent),
            "bpl": row["bpl"], "gapPct": gap, "gameId": game["gameId"], "week": game["week"],
            "prop": f"{side.upper()} {line:g} {MARKET_LABEL[market]}" + (" (ALT)" if alt else ""),
            "l5": row["seasonAvg"] or 0, "alt": alt,
        })
    return out


def _scored_sides() -> list[dict]:
    """
    Every FanDuel prop side in a BPL market that passes the data guards (next game,
    healthy, 2+ games this season, inside the calibrated population), scored two ways:
    the BPL hit probability and FanDuel's own probability. Main lines use the no-vig
    pair; alternate rungs (fanduel_alt_lines.csv) use the price-implied probability.
    """
    idx = _player_index()
    nxt = bpl.next_games()
    injured = _injured()
    rows: dict[tuple[str, str], dict | None] = {}

    def usable(pid: str, name: str, team: str, market: str) -> dict | None:
        if pid in injured:
            return None
        key = (pid, market)
        if key not in rows:
            row = bpl.nfl_player_line(pid, market, name, team)
            ok = row.get("parts") and len(row["l5"]) >= MIN_GAMES_THIS_SEASON and row["parts"]["baseline"] >= MIN_BASELINE[market]
            rows[key] = row if ok else None
        return rows[key]

    out: list[dict] = []
    for r in data.load("prop_line_rotowire"):
        market = r.get("market_slug")
        if r.get("book_slug") != BOOK or market not in bpl.NFL_MARKETS or not r.get("line"):
            continue
        team = r.get("team", "")
        game = nxt.get(team)
        if not game or game["opp"] != r.get("opponent", "").lstrip("@"):
            continue  # stale prop for a game already played
        pid = idx.get((data.normalize_name(r.get("player_name", "")), team))
        over_px, under_px = r.get("over_price_american"), r.get("under_price_american")
        if not pid or not over_px or not under_px:
            continue
        row = usable(pid, r["player_name"], team, market)
        if not row:
            continue
        d_over, d_under = _dec(float(over_px)), _dec(float(under_px))
        book_over = (1 / d_over) / (1 / d_over + 1 / d_under)
        out += _side_dicts(pid, r["player_name"], team, game, market, float(r["line"]), row,
                           [("over", d_over, float(over_px), book_over), ("under", d_under, float(under_px), 1 - book_over)], False)

    for r in data.load("fanduel_alt_lines"):
        market = r.get("market_slug")
        if market not in bpl.NFL_MARKETS or r.get("side") != "over" or not r.get("line") or not r.get("price_american"):
            continue
        for team in (r["home"], r["away"]):
            pid = idx.get((data.normalize_name(r["player_name"]), team))
            game = nxt.get(team)
            if pid and game:
                row = usable(pid, r["player_name"], team, market)
                if row:
                    dec = _dec(float(r["price_american"]))
                    out += _side_dicts(pid, r["player_name"], team, game, market, float(r["line"]), row,
                                       [("over", dec, float(r["price_american"]), 1 / dec)], True)
                break
    return out


def _finish_leg(leg: dict, p: float) -> dict:
    ev = p * leg["decimal"] - 1
    return {**leg, "probability": round(p, 4), "impliedProbability": round(1 / leg["decimal"], 4), "ev": round(ev, 4),
            "correlationNote": (f"BPL {leg['bpl']:g} vs FanDuel {leg['line']:g} ({leg['gapPct']:+.1f}%) · "
                                f"hit {p:.0%} vs FanDuel implied {1 / leg['decimal']:.0%} · "
                                f"{leg['recentHits']}/{leg['recentGames']} recent games cleared it")}


def _best_per_market(legs: list[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for leg in legs:
        k = (leg["playerId"], leg["market"])
        if k not in best or (leg["ev"], leg["modelP"]) > (best[k]["ev"], best[k]["modelP"]):
            best[k] = leg
    return sorted(best.values(), key=lambda l: (-l["ev"], -l["modelP"]))


def candidate_legs() -> list[dict]:
    """Value legs: FanDuel price beaten by 5-25% on the BPL hit probability."""
    legs = []
    for l in _scored_sides():
        if l["alt"]:
            continue
        leg = _finish_leg(l, l["modelP"])
        if MIN_LEG_EV <= leg["ev"] <= MAX_LEG_EV and MIN_LEG_P <= l["modelP"] <= MAX_LEG_P:
            legs.append(leg)
    return _best_per_market(legs)


def spy_boy_legs() -> list[dict]:
    """
    SPY BOY legs need three voices to agree: the BPL says 75%+, FanDuel's own price
    says 60%+, and the leg cleared in at least 80% of the player's games this season
    (so a stale prior cannot carry it). The BPL probability is cut by SPY_HAIRCUT
    first, and credit is capped at 25 points over FanDuel.
    Main lines and FanDuel alternate rungs both qualify; the best rung per
    player-market wins.
    """
    legs = []
    for l in _scored_sides():
        p_used = min(l["modelP"] - SPY_HAIRCUT, l["bookP"] + SPY_MAX_CREDIT)
        recent_ok = l["recentGames"] >= MIN_GAMES_THIS_SEASON and l["recentHits"] / l["recentGames"] >= SPY_MIN_RECENT
        if p_used >= SPY_MIN_P and l["bookP"] >= SPY_MIN_BOOK and recent_ok:
            legs.append(_finish_leg(l, p_used))
    return _best_per_market(legs)


def _ticket(legs: tuple[dict, ...], series: str = "BPL_EDGE", kelly_cap: float | None = None) -> dict:
    dec = 1.0
    p = 1.0
    for leg in legs:
        dec *= leg["decimal"]
        p *= leg["probability"]
    ev = p * dec - 1
    kelly = max(0.0, (p * dec - 1) / (dec - 1)) / 4
    if kelly_cap is not None:
        kelly = min(kelly, kelly_cap)
    sig = "|".join(sorted(f"{l['playerId']}:{l['market']}:{l['direction']}:{l['line']}" for l in legs))
    tid = hashlib.sha1(sig.encode()).hexdigest()[:8].upper()
    payout = round(STAKE * dec, 2)
    american = _american(dec)
    spy = series == "SPY_BOY"
    return {
        "id": f"{'SPY' if spy else 'BPL'}-{tid}",
        "title": f"{'SPY BOY' if spy else 'BPL'} {len(legs)}-LEG {'+' if american > 0 else ''}{american}",
        "correlationType": series,
        "insight": (f"Hit chance {p:.1%} vs FanDuel implied {1 / dec:.1%} · ticket EV {ev:+.0%} · "
                    f"stake {kelly:.1%} of bankroll{' (capped)' if kelly_cap is not None else ''}. One leg per game."
                    + (" Every leg: BPL 75%+ after a 5-pt haircut, FanDuel price 60%+, cleared in 80%+ of recent games." if spy else "")),
        "legs": [{k: v for k, v in l.items() if k != "decimal"} for l in legs],
        "wager": STAKE, "boost": 0.0,
        "combinedDecimalOdds": round(dec, 4), "payout": payout, "boostedPayout": payout,
        "boostedAmericanOdds": american,
        "hitProbability": round(p, 4), "expectedValue": round(ev, 4), "kellyPct": round(kelly * 100, 2),
        "week": legs[0]["week"], "book": BOOK, "version": bpl.BPL_VERSION,
    }


def _tickets(pool: list[dict], sizes, per_size: int, series: str, min_dec: float = 0.0, kelly_cap: float | None = None) -> list[dict]:
    out: list[dict] = []
    for size in sizes:
        combos = [c for c in itertools.combinations(pool, size) if len({l["gameId"] for l in c}) == size]
        ranked = sorted((_ticket(c, series, kelly_cap) for c in combos if math.prod(l["decimal"] for l in c) >= min_dec),
                        key=lambda t: -t["expectedValue"])
        out.extend(ranked[:per_size])
    return out


def build_parlays() -> list[dict]:
    return _tickets(candidate_legs()[:MAX_CANDIDATES], TICKET_SIZES, TICKETS_PER_SIZE, "BPL_EDGE")


def build_spy_boy() -> list[dict]:
    """The aggressive series: 3-5 high-probability legs stacked for a +300 or better payout."""
    return _tickets(spy_boy_legs()[:MAX_CANDIDATES], SPY_SIZES, 1, "SPY_BOY", SPY_MIN_DECIMAL, SPY_KELLY_CAP)


# The weekly question board: which bet types Jimmy can price from FanDuel data in the lake.
# The rest need FanDuel markets the lake does not carry yet (or same-game combo pricing).
QUESTION_BOARD = {
    "live": [
        "QB pass yards over/under", "QB rush yards over", "RB rush yards over/under",
        "WR/TE receiving yards over/under", "WR/TE/RB receptions over/under",
    ],
    "waiting_on_fanduel_data": [
        "QB pass TDs (only 29 lines in the lake, count model not calibrated)", "QB interceptions", "QB completions/attempts",
        "RB carries", "RB rush+rec yards (30 lines, not calibrated)", "longest reception", "kicker points / FGs",
        "sacks", "anytime / first / last TD (moneyline only, no TD model)",
    ],
    "needs_same_game_pricing": [
        "any 'AND' combo (yards AND TD, QB yards AND WR yards, stat AND team win): FanDuel prices these with its own "
        "correlation, which is not in the lake, so a payout cannot be computed honestly",
    ],
}


def log_to_myboo(slips: list[dict]) -> None:
    """MY BOO notes every ticket Jimmy posts, once, as a SIM order."""
    import myboo
    season = bpl._current_season()
    for s in slips:
        myboo.create_ticket(
            "SIM", s["title"] + f" · {s['id']}",
            [{"player_name": l["name"], "team": l["team"], "market": l["market"], "direction": l["direction"],
              "line": l["line"], "odds": l["odds"], "probability": l["probability"], "game_date": ""} for l in s["legs"]],
            season, s["week"], s["boostedAmericanOdds"], s["wager"], f"JIMMY {'SPY BOY' if s['correlationType'] == 'SPY_BOY' else 'BPL'} · EV {s['expectedValue']:+.0%}",
        )

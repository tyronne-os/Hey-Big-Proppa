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

College legs (jimmy_cfb_bpl.py: FanDuel total/spread/moneyline vs the BPL team-points model) join the
same pools. SPY BOY is the aggressive series (see spy_boy_legs). FanDuel is the only book used for prices. Every ticket is logged to MY BOO as a
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
import threading
import time
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

    import jimmy_cfb_bpl
    import jimmy_nfl_games
    out += jimmy_nfl_games.nfl_sides()
    out += jimmy_cfb_bpl.cfb_sides(next(iter(nxt.values()))["week"] if nxt else 0)
    return out


def _finish_leg(leg: dict, p: float) -> dict:
    ev = p * leg["decimal"] - 1
    note = leg.pop("note", None)
    return {**leg, "probability": round(p, 4), "impliedProbability": round(1 / leg["decimal"], 4), "ev": round(ev, 4),
            "correlationNote": note or (f"BPL {leg['bpl']:g} vs FanDuel {leg['line']:g} ({leg['gapPct']:+.1f}%) · "
                                f"hit {p:.0%} vs FanDuel implied {1 / leg['decimal']:.0%} · "
                                f"{leg['recentHits']}/{leg['recentGames']} recent games cleared it")}


def _best_per_market(legs: list[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for leg in legs:
        k = (leg["playerId"], leg["market"])
        if k not in best or (leg["ev"], leg["modelP"]) > (best[k]["ev"], best[k]["modelP"]):
            best[k] = leg
    return sorted(best.values(), key=lambda l: (-l["ev"], -l["modelP"]))


# Leg tiers. The board must never be empty: the strict tier is tried first, and each looser
# tier only fills the ticket sizes that are still missing. Every ticket says which tier it came from.
TIERS = (
    {"name": "VALUE", "min_ev": MIN_LEG_EV, "max_ev": MAX_LEG_EV, "p": (MIN_LEG_P, MAX_LEG_P), "note": None},
    {"name": "LEAN", "min_ev": 0.0, "max_ev": 0.35, "p": (0.35, 0.85),
     "note": "LEAN: not enough legs cleared a full 5% price edge, so any positive-edge leg fills the board."},
    {"name": "BEST AVAILABLE", "min_ev": -0.10, "max_ev": 0.60, "p": (0.30, 0.90),
     "note": "BEST AVAILABLE: no price edge is left on this slate. These are the most likely legs, not value plays."},
)
SPY_RELAXED = {"min_p": 0.70, "min_book": 0.55, "min_recent": 0.67, "min_decimal": 3.0}
CRAZY_STAKE = 5.0
CRAZY_KELLY_CAP = 0.005


def _tier_legs(sides: list[dict], tier: dict) -> list[dict]:
    lo, hi = tier["p"]
    legs = []
    for l in sides:
        if l["alt"]:
            continue
        leg = _finish_leg(dict(l), l["modelP"])
        if tier["min_ev"] <= leg["ev"] <= tier["max_ev"] and lo <= l["modelP"] <= hi:
            legs.append(leg)
    return _best_per_market(legs)


def candidate_legs(sides: list[dict] | None = None) -> list[dict]:
    """Value legs: FanDuel price beaten by 5-25% on the BPL hit probability."""
    return _tier_legs(sides if sides is not None else _scored_sides(), TIERS[0])


def _spy_legs(sides: list[dict], min_p: float, min_book: float, min_recent: float) -> list[dict]:
    legs = []
    for l in sides:
        p_used = min(l["modelP"] - SPY_HAIRCUT, l["bookP"] + SPY_MAX_CREDIT)
        recent_ok = l["recentGames"] >= MIN_GAMES_THIS_SEASON and l["recentHits"] / l["recentGames"] >= min_recent
        if p_used >= min_p and l["bookP"] >= min_book and recent_ok:
            legs.append(_finish_leg(dict(l), p_used))
    return _best_per_market(legs)


def spy_boy_legs(sides: list[dict] | None = None) -> list[dict]:
    """
    SPY BOY legs need three voices to agree: the BPL says 75%+, FanDuel's own price
    says 60%+, and the leg cleared in at least 80% of the player's games this season
    (so a stale prior cannot carry it). The BPL probability is cut by SPY_HAIRCUT
    first, and credit is capped at 25 points over FanDuel.
    Main lines and FanDuel alternate rungs both qualify; the best rung per
    player-market wins.
    """
    return _spy_legs(sides if sides is not None else _scored_sides(), SPY_MIN_P, SPY_MIN_BOOK, SPY_MIN_RECENT)


def _ticket(legs: tuple[dict, ...], series: str = "BPL_EDGE", kelly_cap: float | None = None,
            stake: float = STAKE, tier: dict | None = None) -> dict:
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
    payout = round(stake * dec, 2)
    american = _american(dec)
    prefix = {"SPY_BOY": "SPY", "CRAZY_HORSE": "CRZ"}.get(series, "BPL")
    label = {"SPY_BOY": "SPY BOY", "CRAZY_HORSE": "CRAZY HORSE"}.get(series, "BPL")
    sports = {l.get("sport") for l in legs}
    tag = " CFB" if sports == {"CFB"} else " GAMES" if sports == {"NFL"} else ""
    sign = "+" if american > 0 else ""
    title = (f"CRAZY HORSE WEEK {legs[0]['week']} · {len(legs)}-LEG {sign}{american}" if series == "CRAZY_HORSE"
             else f"{label}{tag} {len(legs)}-LEG {sign}{american}")
    insight = (f"Hit chance {p:.1%} vs FanDuel implied {1 / dec:.1%} · ticket EV {ev:+.0%} · "
               f"stake {kelly:.1%} of bankroll{' (capped)' if kelly_cap is not None else ''}. One leg per game."
               + (" Every leg: BPL 75%+ after a 5-pt haircut, FanDuel price 60%+, cleared in 80%+ of recent games." if series == "SPY_BOY" else ""))
    if tier and tier.get("note"):
        insight = f"{tier['note']} {insight}"
    return {
        "id": f"{prefix}-{tid}", "title": title, "correlationType": series, "insight": insight,
        "tier": tier["name"] if tier else "VALUE",
        "legs": [{k: v for k, v in l.items() if k != "decimal"} for l in legs],
        "wager": stake, "boost": 0.0,
        "combinedDecimalOdds": round(dec, 4), "payout": payout, "boostedPayout": payout,
        "boostedAmericanOdds": american,
        "hitProbability": round(p, 4), "expectedValue": round(ev, 4), "kellyPct": round(kelly * 100, 2),
        "confidence": confidence(legs),
        "week": legs[0]["week"], "book": BOOK, "version": bpl.BPL_VERSION,
    }


def confidence(legs) -> int:
    """Confidence score 0-100: the average per-leg hit probability. (Hit chance is the product of the legs
    and shrinks fast with every leg added; this is how sure the model is of a typical leg on the ticket.)"""
    ps = [l["probability"] for l in legs]
    return round(100 * sum(ps) / len(ps)) if ps else 0


def add_photos(slip: dict | None) -> dict | None:
    if slip:
        for l in slip["legs"]:
            l["photoUrl"] = None if l.get("sport") else data.photo_url(l["playerId"])
    return slip


def _tickets(pool: list[dict], sizes, per_size: int, series: str, min_dec: float = 0.0, kelly_cap: float | None = None,
             tier: dict | None = None) -> list[dict]:
    out: list[dict] = []
    for size in sizes:
        combos = [c for c in itertools.combinations(pool, size) if len({l["gameId"] for l in c}) == size]
        ranked = sorted((_ticket(c, series, kelly_cap, tier=tier) for c in combos if math.prod(l["decimal"] for l in c) >= min_dec),
                        key=lambda t: -t["expectedValue"])
        out.extend(ranked[:per_size])
    return out


def build_parlays(sides: list[dict] | None = None) -> list[dict]:
    """
    Conservative series. Tiers fill in order until every ticket size (2-5 legs) has its tickets,
    then college-only and NFL-game-only tickets are added so each slate is always represented.
    """
    sides = sides if sides is not None else _scored_sides()
    out: list[dict] = []
    ids: set[str] = set()
    have = {n: 0 for n in TICKET_SIZES}

    def take(tickets: list[dict], cap: dict[int, int]) -> None:
        for t in tickets:
            n = len(t["legs"])
            if t["id"] in ids or cap.get(n, 0) <= 0:
                continue
            cap[n] -= 1
            ids.add(t["id"])
            out.append(t)

    room = {n: TICKETS_PER_SIZE for n in TICKET_SIZES}
    for tier in TIERS:
        pool = _tier_legs(sides, tier)[:MAX_CANDIDATES]
        take(_tickets(pool, TICKET_SIZES, TICKETS_PER_SIZE * 4, "BPL_EDGE", tier=tier), room)
        if not any(room.values()):
            break

    for sport in ("CFB", "NFL"):
        for tier in TIERS[:2]:
            pool = [l for l in _tier_legs(sides, tier) if l.get("sport") == sport][:MAX_CANDIDATES]
            before = len(out)
            take(_tickets(pool, (2, 3, 4), 3, "BPL_EDGE", tier=tier), {2: 1, 3: 1, 4: 1})
            if len(out) > before:
                break
    return out


SPY_TICKET_LEGS = 5   # never more than five legs on a SPY BOY ticket


def _group_spy(pool: list[dict], min_dec: float, kelly_cap: float | None, tier: dict | None) -> list[dict]:
    """
    Group the qualifying SPY BOY legs into up to three tickets of at most five legs (A, B, C), biggest payouts first.
    Each game keeps its qualifying legs ranked by price; ticket A takes the best-paying leg from each game (five
    best-paying games), B takes each game's second-best leg, C its third. One leg per game on any ticket, so a
    ticket never stacks two legs from the same game. A ticket with under three legs or under the payout floor is dropped.
    """
    per_game: dict[str, list[dict]] = {}
    for l in sorted(pool, key=lambda l: -l["decimal"]):
        per_game.setdefault(l["gameId"], []).append(l)
    out = []
    for layer, letter in enumerate("ABC"):
        legs = sorted((g[layer] for g in per_game.values() if len(g) > layer), key=lambda l: -l["decimal"])
        chunk = tuple(legs[:SPY_TICKET_LEGS])
        if len(chunk) < 3 or math.prod(l["decimal"] for l in chunk) < min_dec:
            continue
        t = _ticket(chunk, "SPY_BOY", kelly_cap, tier=tier)
        t["title"] = f"SPY BOY {letter} · {len(chunk)}-LEG {'+' if t['boostedAmericanOdds'] > 0 else ''}{t['boostedAmericanOdds']}"
        t["group"] = letter
        out.append(t)
    return out


def build_spy_boy(sides: list[dict] | None = None) -> list[dict]:
    """The aggressive series: qualifying legs grouped five to a ticket for the biggest payouts (relaxed if the strict gate finds none)."""
    sides = sides if sides is not None else _scored_sides()
    strict = _group_spy(_spy_legs(sides, SPY_MIN_P, SPY_MIN_BOOK, SPY_MIN_RECENT), SPY_MIN_DECIMAL, SPY_KELLY_CAP, None)
    if strict:
        return strict
    r = SPY_RELAXED
    tier = {"name": "RELAXED", "note": "RELAXED SPY BOY: no leg met all three strict voices this week, so the bar drops to BPL 70%, FanDuel 55%, 2 of 3 recent games."}
    return _group_spy(_spy_legs(sides, r["min_p"], r["min_book"], r["min_recent"]), r["min_decimal"], SPY_KELLY_CAP, tier)


CRAZY_LEGS = 10


def crazy_horse(sides: list[dict] | None = None) -> dict | None:
    """
    The featured long shot: the likeliest leg of ten different games, every leg high probability, $5 to win big.
    One leg per game (the leg with the highest probability after the same 5-point haircut and FanDuel-credit
    cap SPY BOY uses), at the highest floor that still leaves ten games (75%, 70%, 65%, 60%, then 55%).
    A lottery ticket, not a value play: ten legs multiply, so the hit chance is small however good each leg is.
    """
    sides = sides if sides is not None else _scored_sides()
    for floor in (0.75, 0.70, 0.65, 0.60, 0.55):
        best: dict[str, dict] = {}
        for l in sides:
            p_used = min(l["modelP"] - SPY_HAIRCUT, l["bookP"] + SPY_MAX_CREDIT) if not l.get("sport") else l["modelP"]
            if l["alt"] or p_used < floor:
                continue
            leg = _finish_leg(dict(l), p_used)
            if leg["ev"] < -0.15:
                continue
            if l["gameId"] not in best or leg["probability"] > best[l["gameId"]]["probability"]:
                best[l["gameId"]] = leg
        if len(best) >= CRAZY_LEGS:
            legs = tuple(sorted(best.values(), key=lambda l: -l["probability"])[:CRAZY_LEGS])
            t = _ticket(legs, "CRAZY_HORSE", CRAZY_KELLY_CAP, stake=CRAZY_STAKE)
            t["floor"] = floor
            t["insight"] = (f"The likeliest leg of {CRAZY_LEGS} different games, every one rated {floor:.0%}+ by the Big Proppa Line after a 5-point haircut. "
                            f"Model hit chance {t['hitProbability']:.1%}: ${CRAZY_STAKE:g} pays ${t['payout']:,.2f} if every leg lands. "
                            "A lottery ticket, not a value play. Ten legs multiply, so the payout is the point, not the edge.")
            return t
    return None


def scan(sides: list[dict], slips: list[dict], horse: dict | None) -> dict:
    """Deep-scan funnel: what was read, what each gate kept, and what the board ended up with."""
    from collections import Counter
    games = lambda ls: len({l["gameId"] for l in ls})  # noqa: E731
    kind = Counter("college game" if l.get("sport") == "CFB" else "NFL game" if l.get("sport") == "NFL"
                   else "player prop (FanDuel alt ladder)" if l["alt"] else "player prop (main line)" for l in sides)
    return {
        "week": sides[0]["week"] if sides else None,
        "sidesScored": len(sides), "byKind": dict(kind), "gamesCovered": games(sides),
        "tiers": [{"tier": t["name"], "legs": len(ls), "games": games(ls)} for t in TIERS for ls in [_tier_legs(sides, t)]],
        "spyLegsStrict": len(_spy_legs(sides, SPY_MIN_P, SPY_MIN_BOOK, SPY_MIN_RECENT)),
        "spyLegsRelaxed": len(_spy_legs(sides, SPY_RELAXED["min_p"], SPY_RELAXED["min_book"], SPY_RELAXED["min_recent"])),
        "tickets": dict(Counter(f"{s['correlationType']} / {s.get('tier', 'VALUE')}" for s in slips)),
        "crazyHorseLegs": len(horse["legs"]) if horse else 0,
    }


_cache: dict = {"sides": None, "sides_at": 0.0, "all": None, "all_at": 0.0}
_cache_lock = threading.Lock()
CACHE_SECONDS = 300


def cached_sides(force: bool = False) -> list[dict]:
    """Scored legs for the whole slate, rebuilt at most every 5 minutes (scoring reads big tables)."""
    with _cache_lock:
        if force or _cache["sides"] is None or time.time() - _cache["sides_at"] > CACHE_SECONDS:
            sides = _scored_sides()
            if sides or _cache["sides"] is None:
                _cache["sides"], _cache["sides_at"] = sides, time.time()
        return _cache["sides"]


def build_all(force: bool = False) -> dict:
    with _cache_lock:
        fresh = _cache["all"] is not None and time.time() - _cache["all_at"] <= CACHE_SECONDS
    if fresh and not force:
        return _cache["all"]
    sides = cached_sides(force)
    slips = build_parlays(sides) + build_spy_boy(sides)
    horse = crazy_horse(sides)
    import jimmy_featured
    for t in slips:
        add_photos(t)
    add_photos(horse)
    built = {"slips": slips, "crazyHorse": horse, "featured": jimmy_featured.featured(sides), "scan": scan(sides, slips, horse)}
    with _cache_lock:
        _cache["all"], _cache["all_at"] = built, time.time()
    return built


# The weekly question board: which bet types Jimmy can price from FanDuel data in the lake.
# The rest need FanDuel markets the lake does not carry yet (or same-game combo pricing).
QUESTION_BOARD = {
    "live": [
        "QB pass yards over/under", "QB rush yards over", "RB rush yards over/under",
        "WR/TE receiving yards over/under", "WR/TE/RB receptions over/under",
        "college game total over/under, spread cover, moneyline (FanDuel main lines, BPL team-points model)",
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
            season, s["week"], s["boostedAmericanOdds"], s["wager"], f"JIMMY {({'SPY_BOY': 'SPY BOY', 'CRAZY_HORSE': 'CRAZY HORSE'}).get(s['correlationType'], 'BPL')} · EV {s['expectedValue']:+.0%}",
        )

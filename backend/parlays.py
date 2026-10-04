"""
Big Proppa Parlays -- the 4 tickets, per HANDOFF_CLAUDE_CODE.md sec 0 / sec 4.

Probability is JIMMY THE GREEK's lake-only composite score (see jimmy.py) --
hit-rate-vs-threshold, usage_index_score, and opponent defense toxicity,
evenly weighted, per the user's explicit choice this session (this REPLACES
the earlier hit-rate-only v1). HOT DOGS! is the one exception: it's a
team bet on certified Hot Dogs (hot_dog.py), priced from the reference game
line, with the Hot Dog backtest's hit rate as its probability.

Every leg still needs a REAL FanDuel price from prop_best_price.csv; a
player who clears the threshold but has no tracked FanDuel price for that
market is dropped rather than shown with a fabricated odds number. Only legs
with probability >= 0.85 are returned -- the >=85% filter is enforced here,
server-side, per the handoff's explicit instruction (not just in the client
for show).
"""
from __future__ import annotations

import data
import hot_dog
import jimmy
import jimmy_bpl
from odds import compute_parlay

WAGER = 5.0
BOOST = 0.50


def _fanduel_price(player_name: str, market_slug: str, want: str = "over") -> tuple[float | None, str | None]:
    row = data.best_price_for(player_name, market_slug)
    if not row:
        return None, None
    book_col = {
        "over": ("best_over_price", "best_over_book"),
        "moneyline": ("best_moneyline_price", "best_moneyline_book"),
    }[want]
    price_col, book_col_name = book_col
    price = row.get(price_col)
    book = row.get(book_col_name)
    if not price or book != "fanduel":
        return None, None
    try:
        return float(price), book
    except ValueError:
        return None, None


def _hit_rate_at_threshold(games: list[dict], threshold: float, window: int = 10) -> float | None:
    games_sorted = sorted(games, key=lambda g: g["week"])[-window:]
    if not games_sorted:
        return None
    hits = sum(1 for g in games_sorted if g["value"] >= threshold)
    return round(hits / len(games_sorted), 3)


def _l5_rate(games: list[dict], threshold: float) -> float | None:
    return _hit_rate_at_threshold(games, threshold, window=5)


def hot_dogs() -> dict:
    """
    Certified Hot Dogs only (hot_dog.py): sportsbook underdogs with a winning
    record that beat the favorite on 3+ of 5 last-5-game stats. The bet type is
    the one certified dogs hit more often in the 2023-2025 backtest, and each
    leg's probability is that backtest hit rate -- not a guess.
    """
    bt = hot_dog.backtest()
    bet, hit_rate = bt.get("chosenBet"), bt.get("certifiedHitRate")
    legs = []
    for g in hot_dog.slate():
        if not g["certified"] or not bet:
            continue
        price = g["price"]
        if bet == "moneyline":
            prop, odds_val = "Wins outright (moneyline)", price["moneyline"]
        else:
            prop, odds_val = f"{price['spread']:+g} covers the spread", price["spreadOdds"]
        legs.append({
            "teamId": g["underdog"],
            "name": g["underdog"],
            "prop": f"{prop} vs {g['favorite']} · wins {g['statsWon']} of 5",
            "market": bet,
            "line": price["spread"] if bet == "spread" else None,
            "gameId": g["gameId"],
            "statsWon": g["statsWon"],
            "l5": hit_rate,
            "probability": hit_rate,
            "odds": odds_val,
        })
    legs.sort(key=lambda leg: leg["statsWon"], reverse=True)
    return _slip("hot-dogs", "HOT DOGS!", legs[:3])


def beast_mode() -> dict:
    """2 RBs, 2+ total TDs (rushing + receiving) in a game."""
    import red_zone
    if red_zone.td_blocked():           # HARD RULE: no TD-scorer slip (see red_zone.py)
        return _slip("beast-mode", "BEAST MODE", [])
    dim = data.player_dimension()
    rb_ids = [pid for pid, row in dim.items() if row.get("position") == "RB"]
    legs = []
    for pid in rb_ids:
        if not jimmy.eligible(pid) or not jimmy.matchup_gate(pid, "anytd"):
            continue
        games = data.anytime_td_games(pid)  # total_tds per week
        hit_rate = _hit_rate_at_threshold(games, threshold=2)
        l5 = _l5_rate(games, threshold=2)
        prob = jimmy.jimmy_score(pid, hit_rate, market_slug="anytd")
        if prob is None or prob < 0.85:
            continue
        price, book = _fanduel_price(dim[pid]["name"], "anytd", want="moneyline")
        if price is None:
            continue
        legs.append({
            "playerId": pid,
            "name": dim[pid]["name"],
            "prop": "2+ total TDs",
            "l5": l5 if l5 is not None else prob,
            "probability": prob,
            "odds": price,
            "photoUrl": data.photo_url(pid),
        })
    legs.sort(key=lambda leg: leg["probability"], reverse=True)
    return _slip("beast-mode", "BEAST MODE", legs[:3])


def hot_boys() -> dict:
    """Receivers by targets -- hit-rate on the recs (receptions) FanDuel line."""
    dim = data.player_dimension()
    wr_te_ids = [pid for pid, row in dim.items() if row.get("position") in ("WR", "TE")]
    legs = []
    for pid in wr_te_ids:
        if not jimmy.eligible(pid) or not jimmy.matchup_gate(pid, "recs"):
            continue
        chart = data.player_prop_chart(pid, "recs")
        if chart.get("line") is None:
            continue
        hit_rate = chart["splits"][1]["hitRate"]  # L10
        l5 = chart["splits"][0]["hitRate"]
        prob = jimmy.jimmy_score(pid, hit_rate, market_slug="recs")
        if prob is None or prob < 0.85:
            continue
        price, book = _fanduel_price(dim[pid]["name"], "recs", want="over")
        if price is None:
            continue
        legs.append({
            "playerId": pid,
            "name": dim[pid]["name"],
            "prop": f"Over {chart['line']} receptions",
            "l5": l5 if l5 is not None else prob,
            "probability": prob,
            "odds": price,
            "photoUrl": data.photo_url(pid),
        })
    legs.sort(key=lambda leg: leg["probability"], reverse=True)
    return _slip("hot-boys", "HOT BOYS", legs[:3])


def top_gun() -> dict:
    """QBs, 250+ passing yards."""
    dim = data.player_dimension()
    qb_ids = [pid for pid, row in dim.items() if row.get("position") == "QB"]
    legs = []
    for pid in qb_ids:
        if not jimmy.eligible(pid) or not jimmy.matchup_gate(pid, "passyds"):
            continue
        games = data.weekly_games(pid, "player_passing_week", "passing_yards")
        hit_rate = _hit_rate_at_threshold(games, threshold=250)
        l5 = _l5_rate(games, threshold=250)
        prob = jimmy.jimmy_score(pid, hit_rate, market_slug="passyds")
        if prob is None or prob < 0.85:
            continue
        price, book = _fanduel_price(dim[pid]["name"], "passyds", want="over")
        if price is None:
            continue
        legs.append({
            "playerId": pid,
            "name": dim[pid]["name"],
            "prop": "250+ pass yds",
            "l5": l5 if l5 is not None else prob,
            "probability": prob,
            "odds": price,
            "photoUrl": data.photo_url(pid),
        })
    legs.sort(key=lambda leg: leg["probability"], reverse=True)
    return _slip("top-gun", "TOP GUN", legs[:3])


def totals() -> dict:
    """
    Certified Hot Dog games only (hot_dog.py): whichever side of the total
    (over/under) certified dogs hit more often in the 2023-2025 backtest.
    """
    bt = hot_dog.backtest()
    bet, hit_rate = bt.get("chosenTotalBet"), bt.get("totalHitRate")
    legs = []
    for g in hot_dog.slate():
        if not g["certified"] or not bet:
            continue
        price = g["price"]
        odds_val = price["overOdds"] if bet == "over" else price["underOdds"]
        legs.append({
            "gameId": g["gameId"],
            "name": f"{g['underdog']} vs {g['favorite']}",
            "prop": f"{bet.upper()} {price['totalLine']:g} total points · certified dog game ({g['statsWon']} of 5)",
            "market": "total",
            "direction": bet,
            "line": price["totalLine"],
            "statsWon": g["statsWon"],
            "l5": hit_rate,
            "probability": hit_rate,
            "odds": odds_val,
        })
    legs.sort(key=lambda leg: leg["statsWon"], reverse=True)
    return _slip("totals", "TOTALS!", legs[:3])


def _slip(slip_id: str, title: str, legs: list[dict]) -> dict:
    math_result = compute_parlay([leg["odds"] for leg in legs], wager=WAGER, boost=BOOST)
    return {
        "id": slip_id,
        "title": title,
        "legs": legs,
        "wager": WAGER,
        "boost": BOOST,
        "combinedDecimalOdds": math_result.combined_decimal,
        "payout": math_result.payout,
        "boostedPayout": math_result.boosted_payout,
        "boostedAmericanOdds": math_result.boosted_american,
        "confidence": round(100 * sum(l["probability"] for l in legs) / len(legs)) if legs else 0,
    }


# ---------------------------------------------------------------------------
# Big Proppa Line versions of the five themed slips.
#
# The functions above gate every leg on Jimmy's old 85% composite and came back empty most
# weeks. They are kept for reference (LEGACY_SLIPS). The live slips keep the same five themes but
# read the scored FanDuel legs (jimmy_bpl.cached_sides) and always return the best legs available,
# each on a different game, ranked by the Big Proppa Line hit chance.
# ---------------------------------------------------------------------------

def _p_used(leg: dict) -> float:
    """Game legs already carry their own calibration (college sd measured, NFL trusted half);
    player props get the same 5-pt haircut and FanDuel-credit cap SPY BOY uses."""
    if leg.get("sport"):
        return leg["modelP"]
    return min(leg["modelP"] - jimmy_bpl.SPY_HAIRCUT, leg["bookP"] + jimmy_bpl.SPY_MAX_CREDIT)


def _themed_leg(leg: dict) -> dict:
    p = _p_used(leg)
    is_game = bool(leg.get("sport"))
    return {
        "playerId": leg["playerId"], "teamId": leg["playerId"], "name": leg["name"], "team": leg.get("team", ""),
        "direction": leg.get("direction", "over"),
        "prop": leg["prop"],
        "market": leg["market"], "line": leg["line"], "gameId": leg["gameId"],
        "l5": round(leg["recentHits"] / leg["recentGames"], 3) if leg["recentGames"] else p,
        "probability": round(p, 3), "odds": leg["odds"],
        "photoUrl": None if is_game else data.photo_url(leg["playerId"]),
    }


def _pick(sides: list[dict], keep, score, n: int = 3) -> list[dict]:
    """Best `n` legs matching `keep`, one per game and one per player, highest score first."""
    pool = sorted((l for l in sides if not l["alt"] and keep(l)), key=score, reverse=True)
    out, games, players = [], set(), set()
    for l in pool:
        if l["gameId"] in games or l["playerId"] in players:
            continue
        games.add(l["gameId"])
        players.add(l["playerId"])
        out.append(_themed_leg(l))
        if len(out) == n:
            break
    return out


def _bpl_slip(slip_id: str, title: str, keep, score) -> dict:
    return _slip(slip_id, title, _pick(jimmy_bpl.cached_sides(), keep, score))


def bpl_hot_dogs() -> dict:
    """Underdogs the Big Proppa Line likes: moneyline legs paying plus money, best expected value first."""
    return _bpl_slip("hot-dogs", "HOT DOGS!", lambda l: l["market"] in ("nfl_ml", "cfb_ml") and l["odds"] > 0,
                     lambda l: l["modelP"] * l["decimal"])


def bpl_totals() -> dict:
    """Game totals (NFL and college): the likeliest side of each total."""
    return _bpl_slip("totals", "TOTALS!", lambda l: l["market"] in ("nfl_total", "cfb_total"), _p_used)


def bpl_beast_mode() -> dict:
    """Running backs: rushing-yard overs the model likes most."""
    return _bpl_slip("beast-mode", "BEAST MODE", lambda l: l["market"] == "rushyds" and l["direction"] == "over", _p_used)


def bpl_hot_boys() -> dict:
    """Receivers: reception overs the model likes most."""
    return _bpl_slip("hot-boys", "HOT BOYS", lambda l: l["market"] == "recs" and l["direction"] == "over", _p_used)


def bpl_top_gun() -> dict:
    """Quarterbacks: passing-yard overs the model likes most."""
    return _bpl_slip("top-gun", "TOP GUN", lambda l: l["market"] == "passyds" and l["direction"] == "over", _p_used)


LEGACY_SLIPS = {
    "hot_dogs": hot_dogs,
    "totals": totals,
    "beast_mode": beast_mode,
    "hot_boys": hot_boys,
    "top_gun": top_gun,
}

SLIPS = {
    "hot_dogs": bpl_hot_dogs,
    "totals": bpl_totals,
    "beast_mode": bpl_beast_mode,
    "hot_boys": bpl_hot_boys,
    "top_gun": bpl_top_gun,
}

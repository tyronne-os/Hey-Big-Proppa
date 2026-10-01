"""
THROWDOWN THURSDAY / MONDAY NIGHT THROWDOWN
============================================
When there is exactly one game on the current night's slate (Thursday or
Monday primetime), this module takes over the parlays page with a deep-dive
single-game breakdown. Returns 10+ themed parlay slips, the Crazy Horse pick,
and a 50% SGP boost callout — all locked to that one game.

Detection: today is Thursday or Monday AND next_games() has at least one game
scheduled for tonight. During a full week, the front-end also passes
?game_id= to force a specific game for review purposes.
"""
from __future__ import annotations

import datetime
import statistics
from functools import lru_cache
from typing import Optional

import bpl
import data
from jimmy_bpl import SPY_HAIRCUT, SPY_MAX_CREDIT, cached_sides, _dec

# Branding by weekday
BRANDS = {
    "Thursday": {"title": "THROWDOWN THURSDAY", "subtitle": "ONE GAME. ALL THE MONEY."},
    "Monday":   {"title": "MONDAY NIGHT THROWDOWN", "subtitle": "THE WHOLE WEEK BUILT FOR TONIGHT."},
}
DEFAULT_BRAND = {"title": "THROWDOWN NIGHT", "subtitle": "ONE GAME. ALL THE MONEY."}
WAGER = 5.0
BOOST = 0.50


# ── Helpers ────────────────────────────────────────────────────────────────

def _dec_price(american: str | float | None) -> float | None:
    try:
        return _dec(float(american)) if american and str(american).strip() else None
    except (ValueError, TypeError):
        return None


def _am(decimal: float) -> int:
    if decimal >= 2:
        return int(round((decimal - 1) * 100))
    return int(round(-100 / (decimal - 1)))


def _prob_from_american(american: str | float | None) -> float | None:
    d = _dec_price(american)
    return round(1 / d, 4) if d and d > 0 else None


def _prop_rows_for_game(game_id: str, market: str, book: str = "fanduel") -> list[dict]:
    """All prop rows for a market in a specific game (matching via team membership)."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    rows = data.load("prop_line_rotowire")
    return [
        r for r in rows
        if r.get("market_slug") == market
        and r.get("book_slug") == book
        and r.get("team") in game_teams
    ]


def _kicker_history(pid: str) -> list[int]:
    """FG made per game, last 5 games."""
    rows = [r for r in data.load("player_kicking_week")
            if r.get("player_id") == pid and r.get("season_type") == "REG"]
    rows.sort(key=lambda r: (int(r["season"]), int(r["week"])))
    return [int(r["fg_made"]) for r in rows[-5:]]


def _game_info(game_id: str) -> Optional[dict]:
    """Return schedule row for a game_id."""
    for r in data.load("schedule"):
        if r.get("game_id") == game_id:
            return r
    return None


# ── Slip builders ─────────────────────────────────────────────────────────

def _anytime_scorers(game_id: str) -> dict:
    """Any player who can score a TD tonight, ranked by FanDuel implied probability."""
    legs = []
    for r in _prop_rows_for_game(game_id, "anytd"):
        ml = r.get("moneyline_american")
        d = _dec_price(ml)
        if not d:
            continue
        prob = round(1 / d, 4)
        pid = data.normalize_name(r["player_name"])
        legs.append({
            "playerId": pid,
            "name": r["player_name"],
            "team": r["team"],
            "prop": "Anytime TD scorer",
            "market": "anytd",
            "odds": int(float(ml)),
            "probability": prob,
            "l5": prob,
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("anytime-td", "ANYTIME TD SCORERS", legs[:4])


def _first_td(game_id: str) -> dict:
    """Who scores FIRST tonight."""
    legs = []
    for r in _prop_rows_for_game(game_id, "firsttd"):
        ml = r.get("moneyline_american")
        d = _dec_price(ml)
        if not d:
            continue
        prob = round(1 / d, 4)
        pid = data.normalize_name(r["player_name"])
        legs.append({
            "playerId": pid,
            "name": r["player_name"],
            "team": r["team"],
            "prop": "First TD scorer",
            "market": "firsttd",
            "odds": int(float(ml)),
            "probability": prob,
            "l5": prob,
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("first-td", "FIRST TD SCORER", legs[:3])


def _qb_passing_td(game_id: str) -> dict:
    """QBs: 2+ passing TDs tonight."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    legs = []
    rows = data.load("prop_line_rotowire")
    for r in rows:
        if r.get("market_slug") != "passtd" or r.get("book_slug") != "fanduel":
            continue
        if r.get("team") not in game_teams:
            continue
        line = r.get("line")
        if not line:
            continue
        try:
            line_f = float(line)
        except (ValueError, TypeError):
            continue
        if line_f < 1.5:
            continue  # want the 2+ TD line
        over_px = r.get("over_price_american")
        d = _dec_price(over_px)
        if not d:
            continue
        pid = data.normalize_name(r["player_name"])
        legs.append({
            "playerId": pid,
            "name": r["player_name"],
            "team": r["team"],
            "prop": f"Over {line_f:g} passing TDs",
            "market": "passtd",
            "line": line_f,
            "odds": int(float(over_px)),
            "probability": round(1 / d, 4),
            "l5": round(1 / d, 4),
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("qb-pass-td", "QB PASSING TDs", legs[:2])


def _qb_rush_td(game_id: str) -> dict:
    """Which QB might score on the ground tonight."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}

    # Use anytd for QBs (they're in the anytd pool)
    dim = data.player_dimension()
    qb_ids = {pid for pid, row in dim.items() if row.get("position") == "QB"}

    legs = []
    for r in _prop_rows_for_game(game_id, "anytd"):
        pid_lookup = data.normalize_name(r["player_name"])
        # Find gsis id
        gsis = next((pid for pid, row in dim.items()
                     if data.normalize_name(row.get("name", "")) == pid_lookup
                     and row.get("team") == r.get("team")), None)
        if not gsis or gsis not in qb_ids:
            continue
        ml = r.get("moneyline_american")
        d = _dec_price(ml)
        if not d:
            continue
        prob = round(1 / d, 4)
        legs.append({
            "playerId": pid_lookup,
            "name": r["player_name"],
            "team": r["team"],
            "prop": "QB rushing/anytime TD",
            "market": "anytd",
            "odds": int(float(ml)),
            "probability": prob,
            "l5": prob,
            "photoUrl": data.photo_url(pid_lookup) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("qb-rush-td", "QB RUNNING TD", legs[:2])


def _qb_combo(game_id: str) -> dict:
    """QB with 2 pass TDs AND 15+ rush yards — the combo parlay."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    scored_sides = cached_sides()
    rush_sides = {s["name"]: s for s in scored_sides
                  if s.get("gameId") == game_id and s.get("market") == "rushyds" and not s.get("alt")}

    rows = data.load("prop_line_rotowire")
    legs = []
    for r in rows:
        if r.get("market_slug") != "passtd" or r.get("book_slug") != "fanduel":
            continue
        if r.get("team") not in game_teams:
            continue
        line = r.get("line")
        try:
            line_f = float(line) if line else 0
        except (ValueError, TypeError):
            line_f = 0
        if line_f < 1.5:
            continue
        over_px = r.get("over_price_american")
        d_pass = _dec_price(over_px)
        if not d_pass:
            continue
        p_pass = round(1 / d_pass, 4)
        # Find rush yards side for this QB
        rush_side = rush_sides.get(r["player_name"])
        if rush_side:
            p_rush = min(rush_side["modelP"] - SPY_HAIRCUT, rush_side["bookP"] + SPY_MAX_CREDIT)
            p_combo = round(p_pass * p_rush, 4)
            combined_dec = d_pass * rush_side["decimal"]
            combo_payout = round(5 * combined_dec, 2)
        else:
            p_combo = p_pass
            combined_dec = d_pass
            combo_payout = round(5 * d_pass, 2)
        pid = data.normalize_name(r["player_name"])
        legs.append({
            "playerId": pid,
            "name": r["player_name"],
            "team": r["team"],
            "prop": f"2+ pass TDs + 15+ rush yds",
            "market": "combo",
            "odds": _am(combined_dec),
            "probability": p_combo,
            "l5": p_combo,
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("qb-combo", "QB COMBO ALERT", legs[:2])


def _rb_trifecta(game_id: str) -> dict:
    """RB with 3+ receptions, TD, and 60+ rush yards."""
    dim = data.player_dimension()
    rb_ids = {pid for pid, row in dim.items() if row.get("position") == "RB"}
    scored_sides = cached_sides()

    anytd_rows = {data.normalize_name(r["player_name"]) + "_" + r["team"]: r
                  for r in _prop_rows_for_game(game_id, "anytd")}

    legs = []
    for side in scored_sides:
        if side.get("gameId") != game_id:
            continue
        if side.get("market") != "recs" or side.get("alt"):
            continue
        gsis = side["playerId"]
        if gsis not in rb_ids:
            continue
        if side["line"] < 2.5:
            continue  # want 3+

        # Rush yards side
        rush_side = next((s for s in scored_sides
                          if s["playerId"] == gsis and s["market"] == "rushyds"
                          and s["line"] >= 55 and not s["alt"]), None)
        if not rush_side:
            continue

        # TD probability (from anytd moneyline)
        key = data.normalize_name(side["name"]) + "_" + side["team"]
        td_row = anytd_rows.get(key)
        td_dec = _dec_price(td_row["moneyline_american"]) if td_row else None
        p_td = round(1 / td_dec, 4) if td_dec else 0.25

        p_recs = min(side["modelP"] - SPY_HAIRCUT, side["bookP"] + SPY_MAX_CREDIT)
        p_rush = min(rush_side["modelP"] - SPY_HAIRCUT, rush_side["bookP"] + SPY_MAX_CREDIT)
        p_combo = round(p_recs * p_rush * p_td, 4)

        combined_dec = side["decimal"] * rush_side["decimal"] * (td_dec or 3.0)
        legs.append({
            "playerId": gsis,
            "name": side["name"],
            "team": side["team"],
            "prop": f"{side['line']:g}+ recs, {rush_side['line']:g}+ rush yds, TD",
            "market": "rb-trifecta",
            "odds": _am(combined_dec),
            "probability": p_combo,
            "l5": p_combo,
            "photoUrl": data.photo_url(gsis) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("rb-trifecta", "RB TRIFECTA", legs[:2])


def _wr_jackpot(game_id: str) -> dict:
    """WR with TD, 80+ rec yards, 7+ targets."""
    dim = data.player_dimension()
    wr_ids = {pid for pid, row in dim.items() if row.get("position") in ("WR", "TE")}
    scored_sides = cached_sides()
    anytd_rows = {data.normalize_name(r["player_name"]) + "_" + r["team"]: r
                  for r in _prop_rows_for_game(game_id, "anytd")}

    legs = []
    for side in scored_sides:
        if side.get("gameId") != game_id:
            continue
        if side.get("market") != "recyds" or side.get("alt"):
            continue
        gsis = side["playerId"]
        if gsis not in wr_ids:
            continue
        if side["line"] < 75:
            continue  # want 80+

        key = data.normalize_name(side["name"]) + "_" + side["team"]
        td_row = anytd_rows.get(key)
        td_dec = _dec_price(td_row["moneyline_american"]) if td_row else None
        p_td = round(1 / td_dec, 4) if td_dec else 0.20

        p_yds = min(side["modelP"] - SPY_HAIRCUT, side["bookP"] + SPY_MAX_CREDIT)
        p_combo = round(p_yds * p_td, 4)
        combined_dec = side["decimal"] * (td_dec or 4.0)

        legs.append({
            "playerId": gsis,
            "name": side["name"],
            "team": side["team"],
            "prop": f"{side['line']:g}+ rec yds + TD",
            "market": "wr-jackpot",
            "odds": _am(combined_dec),
            "probability": p_combo,
            "l5": p_combo,
            "photoUrl": data.photo_url(gsis) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("wr-jackpot", "WR JACKPOT", legs[:2])


def _kicker_triple(game_id: str) -> dict:
    """Which kicker hits 3+ field goals tonight."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    dim = data.player_dimension()
    k_ids = {pid: row for pid, row in dim.items()
             if row.get("position") == "K" and row.get("team") in game_teams}

    legs = []
    for pid, row in k_ids.items():
        history = _kicker_history(pid)
        if not history:
            continue
        rate_3plus = sum(1 for fg in history if fg >= 3) / len(history)
        # Simple approximation: 3+ FG hit rate from history
        if rate_3plus < 0.10:
            continue
        # Approximate implied odds (+200 to +400 range for 3+ FGs)
        implied_dec = 1 / max(rate_3plus, 0.10)
        legs.append({
            "playerId": pid,
            "name": row.get("name", pid),
            "team": row.get("team", ""),
            "prop": "3+ field goals",
            "market": "kicker",
            "odds": _am(implied_dec),
            "probability": round(rate_3plus, 4),
            "l5": round(statistics.mean(history), 1),
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("kicker-triple", "KICKER GOES 3-FOR-3", legs[:2])


def _game_total(game_id: str) -> dict:
    """Over/under the game total with BPL-backed probability."""
    game = bpl.next_games()
    # Find the game's two sides from scored_sides
    sides = [s for s in cached_sides()
             if s.get("gameId") == game_id and s.get("market") == "nfl_total"]
    if not sides:
        return _slip("game-total", "FINAL SCORE TOTAL", [])

    # Pick the more likely side
    best = max(sides, key=lambda s: s["modelP"])
    label = "OVER" if best["direction"] == "over" else "UNDER"
    leg = {
        "playerId": game_id,
        "name": best["name"],
        "team": "TOTAL",
        "prop": f"{label} {best['line']:g} total points",
        "market": "nfl_total",
        "line": best["line"],
        "direction": best["direction"],
        "odds": best["odds"],
        "probability": round(best["modelP"], 4),
        "l5": round(best["modelP"], 4),
        "photoUrl": None,
    }
    return _slip("game-total", "FINAL SCORE PREDICTION", [leg])


def _upset_potential(game_id: str) -> dict:
    """Underdog moneyline — the upset that pays."""
    sides = [s for s in cached_sides()
             if s.get("gameId") == game_id and s.get("market") == "nfl_ml"]
    if not sides:
        return _slip("upset", "UPSET POTENTIAL", [])

    # Pick the underdog (positive odds side)
    underdogs = [s for s in sides if s["odds"] > 0]
    if not underdogs:
        underdogs = sorted(sides, key=lambda s: s["odds"])[:1]

    legs = []
    for s in underdogs[:1]:
        p = round(s["modelP"], 4)
        legs.append({
            "playerId": game_id,
            "name": s["name"],
            "team": s.get("team", ""),
            "prop": f"{s['name']} MONEYLINE",
            "market": "nfl_ml",
            "odds": s["odds"],
            "probability": p,
            "l5": p,
            "photoUrl": None,
        })
    return _slip("upset", "UPSET POTENTIAL", legs)


def _alt_line(game_id: str) -> dict:
    """Alternate spread reducing the underdog's number."""
    rows = data.load("fanduel_alt_lines")
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}

    # Get game spread to find underdog
    info = _game_info(game_id)
    if not info:
        return _slip("alt-line", "ALTERNATIVE LINE", [])

    away, home = info["away_team"], info["home_team"]
    away_ml = float(info.get("away_moneyline") or 0)
    underdog_team = away if away_ml > 0 else home

    # Find alt lines for underdog reducing their spread
    alt_rows = [r for r in rows
                if r.get("market_slug") in ("nfl_spread", "cfb_spread")
                and (r.get("home") == underdog_team or r.get("away") == underdog_team)
                and r.get("side") == "over"]
    if not alt_rows:
        return _slip("alt-line", "ALTERNATIVE LINE", [])

    # Pick the line closest to -3 (giving fewer points to the underdog)
    alt_rows.sort(key=lambda r: abs(float(r.get("line", 0)) + 3))
    best = alt_rows[0]
    d = _dec_price(best.get("price_american"))
    if not d:
        return _slip("alt-line", "ALTERNATIVE LINE", [])

    leg = {
        "playerId": game_id,
        "name": f"{underdog_team} covers {float(best['line']):+.1f}",
        "team": underdog_team,
        "prop": f"ALT SPREAD: {underdog_team} {float(best['line']):+.1f}",
        "market": "nfl_spread",
        "line": float(best["line"]),
        "odds": int(float(best["price_american"])),
        "probability": round(1 / d, 4),
        "l5": round(1 / d, 4),
        "photoUrl": None,
    }
    return _slip("alt-line", "ALTERNATIVE LINE — REDUCE THE SPOT", [leg])


def _crazy_horse(game_id: str) -> dict:
    """The Crazy Horse pick for tonight — highest EV leg from this game."""
    from jimmy_bpl import candidate_legs
    sides = cached_sides()
    game_sides = [s for s in sides if s.get("gameId") == game_id and not s.get("alt")]
    if not game_sides:
        return _slip("crazy-horse", "THE CRAZY HORSE", [])

    cands = candidate_legs(game_sides)
    if not cands:
        # Fall back to best available
        from jimmy_bpl import _scored_sides, _tier_legs, TIERS
        cands = _tier_legs(game_sides, TIERS[2])

    if not cands:
        return _slip("crazy-horse", "THE CRAZY HORSE", [])

    best = cands[0]
    leg = {
        "playerId": best["playerId"],
        "name": best["name"],
        "team": best.get("team", ""),
        "prop": best["prop"],
        "market": best["market"],
        "line": best["line"],
        "odds": best["odds"],
        "probability": round(best.get("probability", best["modelP"]), 4),
        "l5": round(best.get("recentHits", 0) / max(best.get("recentGames", 1), 1), 3),
        "ev": round(best.get("ev", 0), 4),
        "photoUrl": data.photo_url(best["playerId"]) if hasattr(data, "photo_url") else None,
        "correlationNote": best.get("correlationNote", ""),
    }
    return _slip("crazy-horse", "THE CRAZY HORSE", [leg])


# ── Slip formatter ────────────────────────────────────────────────────────

def _slip(slip_id: str, title: str, legs: list[dict]) -> dict:
    from odds import compute_parlay
    if legs:
        try:
            math = compute_parlay([l["odds"] for l in legs], wager=WAGER, boost=BOOST)
            combined = math.combined_decimal
            payout = math.payout
            boosted = math.boosted_payout
            boosted_am = math.boosted_american
        except Exception:
            combined, payout, boosted, boosted_am = 1.0, WAGER, WAGER, 100
    else:
        combined, payout, boosted, boosted_am = 1.0, WAGER, WAGER, 100

    return {
        "id": slip_id,
        "title": title,
        "legs": legs,
        "wager": WAGER,
        "boost": BOOST,
        "combinedDecimalOdds": combined,
        "payout": payout,
        "boostedPayout": boosted,
        "boostedAmericanOdds": boosted_am,
        "confidence": round(100 * sum(l["probability"] for l in legs) / len(legs)) if legs else 0,
    }


# ── Main entry point ──────────────────────────────────────────────────────

def detect_throwdown_game() -> Optional[str]:
    """
    Returns the game_id if tonight is Thursday or Monday and there is a
    primetime game scheduled. Returns None for full-slate weekends.
    """
    today = datetime.date.today()
    weekday = today.strftime("%A")
    if weekday not in BRANDS:
        return None

    sched = data.load("schedule")
    today_str = today.isoformat()
    tonight = [r for r in sched if r.get("game_date") == today_str]
    if not tonight:
        return None

    # Return the latest-starting game for tonight (primetime)
    tonight.sort(key=lambda r: r.get("game_time_local", "20:00"))
    return tonight[-1]["game_id"]


def build(game_id: Optional[str] = None) -> dict:
    """
    Build the full THROWDOWN THURSDAY deep-dive for `game_id`.
    If game_id is None, auto-detect via detect_throwdown_game().
    Returns None in the 'game' key when no throwdown game is found.
    """
    if not game_id:
        game_id = detect_throwdown_game()
    if not game_id:
        return {"active": False, "game": None}

    nxt = bpl.next_games()
    game_teams = [t for t, g in nxt.items() if g["gameId"] == game_id]
    if len(game_teams) < 2:
        return {"active": False, "game": None}

    info = _game_info(game_id)
    weekday = info.get("weekday", "Thursday") if info else "Thursday"
    brand = BRANDS.get(weekday, DEFAULT_BRAND)

    away, home = info["away_team"], info["home_team"] if info else (game_teams[0], game_teams[1])
    away_ml = info.get("away_moneyline") if info else None
    home_ml = info.get("home_moneyline") if info else None
    total_line = info.get("total_line") if info else None
    away_qb = info.get("away_qb_name", "") if info else ""
    home_qb = info.get("home_qb_name", "") if info else ""

    slips = {
        "anytime_td":    _anytime_scorers(game_id),
        "first_td":      _first_td(game_id),
        "qb_pass_td":    _qb_passing_td(game_id),
        "qb_rush_td":    _qb_rush_td(game_id),
        "qb_combo":      _qb_combo(game_id),
        "rb_trifecta":   _rb_trifecta(game_id),
        "wr_jackpot":    _wr_jackpot(game_id),
        "kicker_triple": _kicker_triple(game_id),
        "game_total":    _game_total(game_id),
        "upset":         _upset_potential(game_id),
        "alt_line":      _alt_line(game_id),
        "crazy_horse":   _crazy_horse(game_id),
    }

    return {
        "active": True,
        "brand": brand,
        "game": {
            "gameId": game_id,
            "away": away,
            "home": home,
            "awayML": away_ml,
            "homeML": home_ml,
            "totalLine": total_line,
            "awayQB": away_qb,
            "homeQB": home_qb,
            "weekday": weekday,
        },
        "slips": slips,
        "boost": BOOST,
        "boostCallout": "FanDuel 50% SGP BOOST active tonight. Stack any 3+ legs from this game for the boost.",
    }

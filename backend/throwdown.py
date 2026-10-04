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
import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

import bpl
import data
from jimmy_bpl import SPY_HAIRCUT, SPY_MAX_CREDIT, cached_sides, _dec

# Branding by weekday
BRANDS = {
    "Thursday": {"title": "THROWDOWN THURSDAY",      "subtitle": "ONE GAME. ALL THE MONEY."},
    "Monday":   {"title": "MONDAY NIGHT THROWDOWN",  "subtitle": "THE WHOLE WEEK BUILT FOR TONIGHT."},
    "Sunday":   {"title": "SUNDAY NIGHT FOOTBALL",   "subtitle": "THE GAME OF THE WEEK. ALL THE PROPS."},
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


def _game_time_utc(info: dict | None) -> str | None:
    """Return kickoff as UTC ISO string. game_time_local is Eastern (EDT=UTC-4 in Oct)."""
    if not info:
        return None
    gd = info.get("game_date", "")
    gt = info.get("game_time_local", "")
    if not gd or not gt:
        return None
    try:
        naive = datetime.datetime.fromisoformat(f"{gd}T{gt}:00")
        utc = naive + datetime.timedelta(hours=4)   # EDT = UTC-4
        return utc.isoformat() + "Z"
    except Exception:
        return None


def _prop_rows_for_game(game_id: str, market: str, book: str = "fanduel") -> list[dict]:
    """All prop rows for a market in a specific game (matching via team membership)."""
    nxt = bpl.next_games()
    game_teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    latest: dict[tuple, dict] = {}
    for r in data.load("prop_line_rotowire"):
        if r.get("market_slug") != market or r.get("book_slug") != book or r.get("team") not in game_teams:
            continue
        k = (r.get("player_name"), r.get("line"))
        if k not in latest or r["pull_id"] > latest[k]["pull_id"]:
            latest[k] = r
    return list(latest.values())


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


def _first_td_raw(game_id: str) -> list[dict]:
    """Raw first-TD-scorer legs (not wrapped in a slip — for use inside multi-leg combos)."""
    dim = data.player_dimension()
    name_to_gsis = {
        (data.normalize_name(r.get("name", "")), r.get("team", "")): (pid, r.get("position", ""))
        for pid, r in dim.items()
    }
    legs = []
    for r in _prop_rows_for_game(game_id, "firsttd"):
        ml = r.get("moneyline_american")
        d = _dec_price(ml)
        if not d:
            continue
        prob = round(1 / d, 4)
        norm = data.normalize_name(r["player_name"])
        gsis, pos = name_to_gsis.get((norm, r.get("team", "")), (norm, ""))
        legs.append({
            "playerId": gsis,
            "name": r["player_name"],
            "team": r["team"],
            "pos": pos,
            "prop": "First TD scorer",
            "market": "firsttd",
            "odds": int(float(ml)),
            "probability": prob,
            "l5": prob,
            "photoUrl": data.photo_url(gsis),
        })
    legs.sort(key=lambda l: -l["probability"])
    return legs


def _first_td(game_id: str) -> dict:
    """Legacy wrapper kept for callers that expect a slip dict."""
    legs = _first_td_raw(game_id)
    return _slip("first-td", "FIRST TD SCORER", legs[:1], "Only one player scores first, so this is a single-leg shot.")


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
            continue
        pid = data.normalize_name(r["player_name"])
        legs.append({
            "playerId": pid,
            "name": r["player_name"],
            "team": r["team"],
            "prop": f"2+ pass TDs + 15+ rush yds",
            "market": "combo",
            "components": [{"market": "passtd", "direction": "over", "line": line_f - 0.0},
                           {"market": "rushyds", "direction": "over", "line": (rush_side or {}).get("line", 15)}],
            "odds": _am(combined_dec),
            "probability": p_combo,
            "l5": p_combo,
            "photoUrl": data.photo_url(pid) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("qb-combo", "QB COMBO ALERT", legs[:2], "" if legs else "No QB has a posted rushing-yards line to price the 15-yard leg tonight.")


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
            "components": [{"market": "recs", "direction": "over", "line": side["line"]},
                           {"market": "rushyds", "direction": "over", "line": rush_side["line"]},
                           {"market": "anytd", "direction": "over", "line": 0.5}],
            "odds": _am(combined_dec),
            "probability": p_combo,
            "l5": p_combo,
            "photoUrl": data.photo_url(gsis) if hasattr(data, "photo_url") else None,
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("rb-trifecta", "RB TRIFECTA", legs[:2])


def _wr_jackpot(game_id: str) -> dict:
    """Best receiving-yards overs among WR/TE tonight, paired with their anytime-TD price."""
    nxt = bpl.next_games()
    teams = {t for t, g in nxt.items() if g["gameId"] == game_id}
    td = {r["player_name"]: r for r in _prop_rows_for_game(game_id, "anytd")}
    legs = []
    for s_ in cached_sides():
        if s_.get("team") not in teams or s_["market"] != "recyds" or s_["direction"] != "over" or s_.get("alt"):
            continue
        if s_["line"] < 40:
            continue
        t = td.get(s_["name"])
        d_td = _dec_price(t["moneyline_american"]) if t else None
        if not d_td:
            continue
        p = round(s_["modelP"] * (1 / d_td), 4)
        legs.append({
            "playerId": s_["playerId"], "name": s_["name"], "team": s_["team"],
            "prop": f"Over {s_['line']:g} rec yds + anytime TD", "market": "wr-jackpot",
            "components": [{"market": "recyds", "direction": "over", "line": s_["line"]},
                           {"market": "anytd", "direction": "over", "line": 0.5}],
            "odds": _am(s_["decimal"] * d_td), "probability": p, "l5": round(s_["l5"], 3) if isinstance(s_.get("l5"), float) else p,
            "photoUrl": data.photo_url(s_["playerId"]),
        })
    legs.sort(key=lambda l: -l["probability"])
    return _slip("wr-jackpot", "RECEIVER JACKPOT", legs[:3])


def _kicker_triple(game_id: str) -> dict:
    """Kicker over on kicking points (9+ points = three field goals) from live FanDuel/DK/Caesars lines."""
    legs = []
    for book in ("fanduel", "draftkings", "caesars"):
        for r in _prop_rows_for_game(game_id, "kickpts", book):
            if not r.get("line") or not r.get("over_price_american"):
                continue
            line = float(r["line"])
            d = _dec_price(r["over_price_american"])
            if not d or line < 7.5:
                continue
            legs.append({
                "playerId": data.normalize_name(r["player_name"]), "name": r["player_name"], "team": r["team"],
                "prop": f"Over {line:g} kicking pts ({book})", "market": "kickpts", "line": line, "direction": "over",
                "odds": int(float(r["over_price_american"])), "probability": round(1 / d, 4), "l5": round(1 / d, 4),
                "photoUrl": None,
            })
    legs.sort(key=lambda l: (-l["probability"]))
    best: dict[str, dict] = {}
    for l in legs:
        best.setdefault(l["name"], l)
    return _slip("kicker-triple", "KICKER GOES 3-FOR-3", list(best.values())[:2])


def _game_total(game_id: str) -> dict:
    """Over/under the game total with BPL-backed probability."""
    game = bpl.next_games()
    # Find the game's two sides from scored_sides
    sides = [s for s in cached_sides()
             if s.get("gameId") == game_id and s.get("market") == "nfl_total"]
    if not sides:
        return _slip("game-total", "FINAL SCORE TOTAL", [])

    # Pick the more likely side
    sides = [s for s in sides if s["direction"] == "over"]
    if not sides:
        return _slip("game-total", "FINAL SCORE PREDICTION", [], "No model edge on the over tonight.")
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
    """Underdog moneyline straight from the schedule's market price."""
    info = _game_info(game_id)
    if not info:
        return _slip("upset", "UPSET POTENTIAL", [])
    try:
        a, h = float(info["away_moneyline"]), float(info["home_moneyline"])
    except (ValueError, TypeError):
        return _slip("upset", "UPSET POTENTIAL", [], "No moneyline posted yet.")
    team, ml = (info["away_team"], a) if a > h else (info["home_team"], h)
    p = round(1 / _dec(ml), 4)
    leg = {"playerId": team, "name": f"{team} to win outright", "team": team, "prop": f"{team} MONEYLINE",
           "market": "nfl_ml", "odds": int(ml), "probability": p, "l5": p, "photoUrl": None}
    return _slip("upset", "UPSET POTENTIAL", [leg])


def _alt_line(game_id: str) -> dict:
    return _slip("alt-line", "ALTERNATIVE LINE", [],
                 "Alt-spread prices are not in the lake yet. Wire a spread-ladder source to price this.")


def _defense_wins(game_id: str) -> dict:
    """3-leg UNDER parlay: players facing the game's stronger defense expected to fall short.

    Strategy: find the defense with the better rank (lower rank_scoring_defense), then
    pick the 3 highest-probability UNDER props for players on the opposing offense.
    """
    # Find both teams
    nxt = bpl.next_games()
    game_teams = [t for t, g in nxt.items() if g["gameId"] == game_id]
    if len(game_teams) < 2:
        return _slip("defense-wins", "DEFENSE WINS TONIGHT", [])

    # Load season-level defensive rankings (lower rank = better defense)
    def_rows = {r["team"]: r for r in data.load("team_defense_season")}
    ranks = {}
    for t in game_teams:
        row = def_rows.get(t, {})
        try:
            ranks[t] = int(row.get("rank_scoring_defense", 99))
        except (ValueError, TypeError):
            ranks[t] = 99

    # Better defense = lower rank_scoring_defense
    better_def = min(ranks, key=lambda t: ranks[t])
    target_offense = [t for t in game_teams if t != better_def][0]
    def_rank = ranks[better_def]

    # Pull UNDER props for the target_offense players from scored_sides
    sides = cached_sides()
    unders = [s for s in sides
              if s.get("gameId") == game_id
              and s.get("direction") == "under"
              and s.get("team") == target_offense
              and not s.get("alt")
              and s["market"] in ("recyds", "recs", "rushyds", "passyds")]

    # Score each: use model probability
    for s in unders:
        s["_p"] = min(s["modelP"] - SPY_HAIRCUT, s["bookP"] + SPY_MAX_CREDIT)

    label_map = {"recyds": "rec yds", "recs": "recs", "rushyds": "rush yds", "passyds": "pass yds"}

    def _make_leg(s: dict) -> dict:
        pid = s["playerId"]
        return {
            "playerId": pid,
            "name": s["name"],
            "team": s["team"],
            "pos": "",
            "prop": f"Under {s['line']:g} {label_map.get(s['market'], s['market'])}",
            "market": s["market"],
            "line": s["line"],
            "direction": "under",
            "odds": s["odds"],
            "probability": round(s["_p"], 4),
            "l5": round(s["_p"], 4),
            "photoUrl": data.photo_url(pid),
        }

    # Force the QB passing-yards under as the anchor leg (adds the big-number swing)
    dim = data.player_dimension()
    qb_ids = {pid for pid, r in dim.items() if r.get("position") == "QB"}
    qb_passyds_under = next(
        (s for s in sorted(unders, key=lambda x: x["_p"])   # take any QB passyds under
         if s["market"] == "passyds" and s["playerId"] in qb_ids), None
    )

    # Top 3 non-QB unders, one per player
    unders.sort(key=lambda s: -s["_p"])
    seen_p: set[str] = set()
    legs: list[dict] = []
    for s in unders:
        if s["market"] == "passyds" and s["playerId"] in qb_ids:
            continue  # QB passyds handled separately
        if s["name"] in seen_p:
            continue
        seen_p.add(s["name"])
        legs.append(_make_leg(s))
        if len(legs) == 3:
            break

    # Append QB passyds under at the end (so it shows as the 4th leg)
    if qb_passyds_under:
        legs.append(_make_leg(qb_passyds_under))

    note = (
        f"{better_def} ranks #{def_rank} in scoring defense this season. "
        f"{target_offense} faces the wall — book prices the over, our model and that defense say under."
    ) if legs else "Not enough defensive data to price unders tonight."

    return _slip("defense-wins", "DEFENSE WINS TONIGHT", legs, note)


def _crazy_horse(game_id: str) -> dict:
    """The Crazy Horse pick for tonight — highest EV leg from this game."""
    from jimmy_bpl import candidate_legs
    sides = cached_sides()
    game_sides = [s for s in sides if s.get("gameId") == game_id and not s.get("alt") and s.get("direction") == "over"]
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

def _td_legs(game_id: str, market: str) -> list[dict]:
    # Build lookup: (normalized_name, team) → (gsis_id, position)
    dim = data.player_dimension()
    name_to_gsis: dict[tuple, tuple] = {
        (data.normalize_name(r.get("name", "")), r.get("team", "")): (pid, r.get("position", ""))
        for pid, r in dim.items()
    }
    out = []
    for r in _prop_rows_for_game(game_id, market):
        d = _dec_price(r.get("moneyline_american"))
        if not d:
            continue
        norm = data.normalize_name(r["player_name"])
        gsis, position = name_to_gsis.get((norm, r.get("team", "")), (norm, ""))
        out.append({
            "playerId": gsis,
            "name": r["player_name"],
            "team": r["team"],
            "pos": position,
            "prop": "Anytime TD scorer",
            "market": market,
            "line": 0.5,
            "direction": "over",
            "odds": int(float(r["moneyline_american"])),
            "probability": round(1 / d, 4),
            "l5": round(1 / d, 4),
            "photoUrl": data.photo_url(gsis),
        })
    return out


def _pool(game_id: str) -> list[dict]:
    teams = {t for t, g in bpl.next_games().items() if g["gameId"] == game_id}
    pos = {pid: r.get("position", "") for pid, r in data.player_dimension().items()}
    label = {"recyds": "rec yds", "recs": "receptions", "rushyds": "rush yds", "passyds": "pass yds"}
    out = []
    for s_ in cached_sides():
        if s_.get("team") not in teams or s_["direction"] != "over" or s_.get("alt") or s_["market"] not in label:
            continue
        p = min(s_["modelP"] - SPY_HAIRCUT, s_["bookP"] + SPY_MAX_CREDIT)
        out.append({"playerId": s_["playerId"], "name": s_["name"], "team": s_["team"], "pos": pos.get(s_["playerId"], ""),
                    "prop": f"Over {s_['line']:g} {label[s_['market']]}", "market": s_["market"], "line": s_["line"],
                    "direction": "over", "odds": s_["odds"], "probability": round(p, 4), "l5": round(p, 4),
                    "photoUrl": data.photo_url(s_["playerId"])})
    return out


def _slip(slip_id: str, title: str, legs: list[dict], note: str = "") -> dict:
    from odds import compute_parlay
    seen: set = set()
    legs = [l for l in legs if not ((l["name"], l["prop"]) in seen or seen.add((l["name"], l["prop"])))]
    if len(legs) < 2:
        legs, note = [], note or "Not enough high-probability legs to build a parlay yet."
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
        "note": note,
        "hitProbability": round(__import__("math").prod(l["probability"] for l in legs), 4) if legs else 0,
    }


# ── Main entry point ──────────────────────────────────────────────────────

def detect_throwdown_game() -> Optional[str]:
    """
    Returns the game_id if tonight is Thursday or Monday and there is a
    primetime game scheduled. Returns None for full-slate weekends.
    """
    # Use Central time (New Orleans). HF servers run UTC; ZoneInfo handles DST automatically.
    from zoneinfo import ZoneInfo
    today = datetime.datetime.now(ZoneInfo("America/Chicago")).date()
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


def detect_sunday_night_game() -> Optional[str]:
    """
    Returns the game_id for Sunday Night Football (the latest-kicking-off Sunday game).
    Works any day of the week — useful for previewing before Sunday arrives.
    """
    from zoneinfo import ZoneInfo
    today = datetime.datetime.now(ZoneInfo("America/Chicago")).date()
    sched = data.load("schedule")
    # Find the nearest Sunday (today if Sunday, else next Sunday)
    days_ahead = (6 - today.weekday()) % 7  # weekday() Mon=0 ... Sun=6
    sunday = today + datetime.timedelta(days=days_ahead)
    sunday_str = sunday.isoformat()
    games = [r for r in sched if r.get("game_date") == sunday_str and r.get("game_type") == "REG"]
    if not games:
        return None
    games.sort(key=lambda r: r.get("game_time_local", "20:00"))
    return games[-1]["game_id"]


# ── archive: the last Thursday / Monday game stays viewable until the next one ──────────────
HISTORY_DIR = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "throwdown_history"
_archive_lock = threading.Lock()


def latest_game(weekday: str) -> Optional[dict]:
    """Most recent primetime game on `weekday` (Thursday / Monday) that has kicked off or is today."""
    today = bpl.today_central()
    rows = [r for r in data.load("schedule")
            if r.get("game_type") == "REG" and r.get("game_date", "9999") <= today
            and datetime.date.fromisoformat(r["game_date"]).strftime("%A") == weekday]
    if not rows:
        return None
    day = max(r["game_date"] for r in rows)
    todays = sorted((r for r in rows if r["game_date"] == day), key=lambda r: r.get("game_time_local", "20:00"))
    return todays[-1]


def save_snapshot(res: dict) -> None:
    """Freeze a live build so the page can be reopened after the game."""
    if not res.get("active"):
        return
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        (HISTORY_DIR / f"{res['game']['gameId']}.json").write_text(json.dumps(res, default=str))
    except OSError:
        pass


def archived(weekday: str) -> dict:
    """
    The most recent `weekday` Throwdown. Served from the frozen snapshot when one exists; otherwise
    rebuilt as of that game's own date (board and odds as the lake holds them) and frozen.
    """
    g = latest_game(weekday)
    if not g:
        return {"active": False, "game": None}
    path = HISTORY_DIR / f"{g['game_id']}.json"
    if path.exists():
        try:
            return {**json.loads(path.read_text()), "archived": True}
        except (OSError, ValueError):
            pass
    with _archive_lock:
        bpl.AS_OF = g["game_date"]
        try:
            cached_sides(force=True)
            res = build(g["game_id"])
        finally:
            bpl.AS_OF = None
            cached_sides(force=True)
    save_snapshot(res)
    return {**res, "archived": True} if res.get("active") else res


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

    pool = _pool(game_id)
    td_legs = _td_legs(game_id, "anytd")
    ft = _first_td_raw(game_id)          # raw legs list — use directly in combos
    kick = _kicker_triple(game_id)["legs"]
    dog = _upset_potential(game_id)["legs"]

    # Raw game-total-over leg (single leg, for combining into multi-leg slips)
    _gt_sides = [s for s in cached_sides() if s.get("gameId") == game_id and s.get("market") == "nfl_total" and s["direction"] == "over"]
    if _gt_sides:
        _gt = max(_gt_sides, key=lambda s: s["modelP"])
        _total_leg: list[dict] = [{
            "playerId": game_id, "name": _gt["name"], "team": "TOTAL",
            "prop": f"OVER {_gt['line']:g} total points", "market": "nfl_total",
            "line": _gt["line"], "direction": "over",
            "odds": _gt["odds"], "probability": round(_gt["modelP"], 4),
            "l5": round(_gt["modelP"], 4), "photoUrl": None,
        }]
    else:
        _total_leg = []
    total = _total_leg
    spec = [x for k in (_rb_trifecta, _wr_jackpot, _qb_combo) for x in k(game_id)["legs"][:1]]
    allp = sorted(pool + td_legs, key=lambda l: -l["probability"])

    def top(src, n, per=2, **kw):
        out, count = [], {}
        for l in src:
            if kw.get("pos") and l.get("pos") not in kw["pos"]:
                continue
            if kw.get("mk") and l["market"] not in kw["mk"]:
                continue
            if kw.get("team") and l["team"] != kw["team"]:
                continue
            if count.get(l["name"], 0) >= per:
                continue
            count[l["name"]] = count.get(l["name"], 0) + 1
            out.append(l)
            if len(out) == n:
                break
        return out

    underdog = dog[0]["team"] if dog else None
    slips = {
        "ladder_3":    _slip("ladder-3",    "SAFE 3",            top(allp, 3, per=1),  "Highest-probability legs on the board."),
        "ladder_5":    _slip("ladder-5",    "STACKED 5",         top(allp, 5, per=2)),
        "ladder_7":    _slip("ladder-7",    "LOADED 7",          top(allp, 7, per=2)),
        "ladder_9":    _slip("ladder-9",    "THE MONEY 9",       top(allp, 9, per=2),  "Same high-probability pool, more legs, bigger payout."),
        "anytime_td":  _slip("anytime-td",  "ANYTIME TD STACK",  top(td_legs, 5, per=1)),
        # First TD scorer + game going OVER = 2-leg combo
        "first_td":    _slip("first-td",    "FIRST SCORE + OVER", ft[:1] + total,
                             "If they score first the game tends to open up — ride the over with it."),
        "air_raid":    _slip("air-raid",    "AIR RAID",          top(pool, 5, per=1, mk=("recyds", "recs", "passyds"))),
        "ground_pound":_slip("ground-pound","GROUND & POUND",    top(pool, 3, per=1, mk=("rushyds",)) + top(td_legs, 2, per=1, pos=("RB",))),
        "qb_power":    _slip("qb-power",    "QB POWER HOUR",     top(pool, 2, per=1, pos=("QB",), mk=("passyds",)) + total + top(td_legs, 1, per=1, pos=("QB",))),
        "kicker_night":_slip("kicker-night","KICKER'S NIGHT",    kick + total + top(allp, 2, per=1)),
        "upset":       _slip("upset",       "UPSET SPECIAL",     dog + (top(pool, 2, per=1, team=underdog) + top(td_legs, 1, per=1, team=underdog) if underdog else top(allp, 2, per=1))),
        "homework":    _slip("homework",    "THE HOMEWORK SPECIAL", spec + total,
                             "QB combo, RB trifecta, receiver jackpot and the over. This is the $1,000 ticket."),
        "defense_wins":_defense_wins(game_id),
        "alt_line":    _alt_line(game_id),
    }

    # No touchdown-scorer legs from NFL week 4 on: every TD slot becomes that player's RED ZONE EFFORT leg.
    import red_zone
    if red_zone.td_props_off(int(info["week"]) if info and info.get("week") else None):
        titles = {"anytime_td": "RED ZONE EFFORT", "first_td": "EFFORT + OVER"}
        notes = {"anytime_td": "Instead of guessing who scores, ride the yards it takes to get to the red zone. Each leg pays like that player's TD.",
                 "first_td": "Best effort leg on the board plus the game going over."}
        for k, sl in list(slips.items()):
            legs = sl["legs"]
            if k == "first_td":
                eff = red_zone.swap_td_legs(_td_legs(game_id, "anytd"), game_id)
                legs = sorted(eff, key=lambda l: -l["probability"])[:1] + total
            elif any(red_zone._has_td(l) for l in legs):
                legs = red_zone.swap_td_legs(legs, game_id)
            else:
                continue
            if len(legs) < 2:                      # a swap can leave a slip short: top up with the best effort legs
                have = {l["name"] for l in legs}
                legs = legs + [l for l in sorted(pool, key=lambda l: -l["probability"]) if l["name"] not in have][:2 - len(legs)]
            slips[k] = _slip(sl["id"], titles.get(k, sl["title"]), legs, notes.get(k, sl.get("note", "")))

    # Crazy Horse: 7-leg mega parlay built from the best legs already on the page.
    # One player per leg — dedupe across all above slips, ranked by probability.
    _ch_pool: list[dict] = []
    for _k in ("ladder_5", "anytime_td", "air_raid", "ground_pound", "qb_power", "first_td"):
        _ch_pool.extend(slips.get(_k, {}).get("legs", []))
    _ch_pool.sort(key=lambda l: -l["probability"])
    _ch_seen: set[str] = set()
    _ch_legs: list[dict] = []
    for _l in _ch_pool:
        if _l["name"] not in _ch_seen:
            _ch_seen.add(_l["name"])
            _ch_legs.append(_l)
        if len(_ch_legs) == 8:
            break
    slips["crazy_horse"] = _slip(
        "crazy-horse", "THE CRAZY HORSE", _ch_legs,
        "Every confident leg from tonight's slips stacked into one. This is the big number.",
    )
    for sl in slips.values():
        for lg in sl["legs"]:
            lg["gameId"] = game_id
    week = int(info["week"]) if info and info.get("week") else 0
    try:
        import myboo
        meta = myboo.track_slips([{**sl, "id": f"TD-{k}"} for k, sl in slips.items()], 2026, week, "THROWDOWN")
        for k, sl in slips.items():
            sl.update(meta.get(f"TD-{k}", {}))
    except Exception:
        pass
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
            "week": week,
            "gameTimeUTC": _game_time_utc(info),
        },
        "slips": slips,
        "boost": BOOST,
        "boostCallout": "FanDuel 50% SGP BOOST active tonight. Stack any 3+ legs from this game for the boost.",
    }

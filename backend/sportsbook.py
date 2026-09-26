"""
Sportsbook — live odds from The Odds API v4.

Endpoints used:
  /sports/americanfootball_nfl/odds   → NFL game lines (spread, total, ML)
  /sports/americanfootball_nfl/events/{id}/odds → per-event player props
  /sports/americanfootball_ncaaf/odds → CFB game lines

Auth: ?apiKey=$THE_ODDS_API_KEY (never printed/logged).
Base: https://api.the-odds-api.com/v4

IMPORTANT: The Odds API deducts quota per call. All results are cached for
10 minutes. Never call these functions in a hot path — use the cached wrappers
exposed at the bottom.

The module also stores an "opening line snapshot" at first call each week so
line movement can be computed. These snapshots live in memory only (process
restart clears them). A future upgrade should persist to the lake.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache

import requests

_BASE = "https://api.the-odds-api.com/v4"
_TTL  = 600   # 10 min default
_cache: dict[str, tuple[object, float]] = {}
_open_lines: dict[str, dict] = {}   # game_key → opening-line snapshot


# ── internal helpers ──────────────────────────────────────────────────────────

def _key() -> str:
    return os.environ.get("THE_ODDS_API_KEY", "")


def _get(path: str, params: dict | None = None, ttl: int = _TTL) -> object:
    """GET with TTL cache; returns parsed JSON or None on failure."""
    cache_key = path + str(sorted((params or {}).items()))
    cached = _cache.get(cache_key)
    if cached and time.time() < cached[1]:
        return cached[0]

    api_key = _key()
    if not api_key:
        return None

    full_params = {"apiKey": api_key, **(params or {})}
    try:
        r = requests.get(f"{_BASE}{path}", params=full_params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        _cache[cache_key] = (data, time.time() + ttl)
        return data
    except Exception:
        return None


def available() -> bool:
    """True if THE_ODDS_API_KEY is set."""
    return bool(_key())


# ── odds normalization ────────────────────────────────────────────────────────

def _parse_bookmaker_lines(bookmakers: list[dict], markets: list[str]) -> dict:
    """
    Collapses a list of bookmaker objects into one consensus dict.
    For each market, takes the median price across books (rounded).
    Returns: {market_key: {outcome_name: price, ...}}
    """
    import statistics

    by_market: dict[str, dict[str, list[float]]] = {}
    for bk in (bookmakers or []):
        for mkt in (bk.get("markets") or []):
            key = mkt.get("key", "")
            if key not in markets:
                continue
            by_market.setdefault(key, {})
            for outcome in (mkt.get("outcomes") or []):
                name  = outcome.get("name", "")
                price = outcome.get("price")
                point = outcome.get("point")
                if price is not None:
                    full_name = f"{name}|{point}" if point is not None else name
                    by_market[key].setdefault(full_name, []).append(float(price))

    out: dict[str, dict] = {}
    for mkt_key, outcomes in by_market.items():
        out[mkt_key] = {}
        for name, prices in outcomes.items():
            median = statistics.median(prices)
            out[mkt_key][name] = _american_from_decimal(median) if abs(median) < 100 else int(round(median))
    return out


def _american_from_decimal(d: float) -> int:
    """Convert decimal odds (e.g. 1.91) to American (e.g. -110)."""
    if d >= 2.0:
        return int(round((d - 1) * 100))
    return int(round(-100 / (d - 1)))


def _decimal_from_american(a: float) -> float:
    if a > 0:
        return 1 + a / 100
    return 1 + 100 / abs(a)


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def get_nfl_lines(markets: str = "h2h,spreads,totals") -> list[dict]:
    """
    Current NFL lines across all bookmakers, consensus prices.
    Returns list of game dicts:
      {gameID, commence, home, away,
       ml_home, ml_away,
       spread_home, spread_home_odds, spread_away, spread_away_odds,
       total_line, over_odds, under_odds,
       books: [bookmaker names]}
    """
    raw = _get("/sports/americanfootball_nfl/odds", {
        "regions": "us",
        "markets": markets,
        "oddsFormat": "american",
    })
    if not raw:
        return []
    out = []
    for event in (raw or []):
        game_id   = event.get("id", "")
        home      = event.get("home_team", "")
        away      = event.get("away_team", "")
        commence  = event.get("commence_time", "")
        bookies   = event.get("bookmakers", [])
        books     = [b["key"] for b in bookies]
        lines     = _parse_bookmaker_lines(bookies, ["h2h", "spreads", "totals"])
        h2h       = lines.get("h2h", {})
        spreads   = lines.get("spreads", {})
        totals    = lines.get("totals", {})

        home_ml = h2h.get(home)
        away_ml = h2h.get(away)

        # spreads keyed like "Team|-3.5"
        spread_h = next((v for k, v in spreads.items() if k.startswith(home + "|")), None)
        spread_h_val = next((float(k.split("|")[1]) for k in spreads if k.startswith(home + "|")), None)
        spread_a = next((v for k, v in spreads.items() if k.startswith(away + "|")), None)
        spread_a_val = next((float(k.split("|")[1]) for k in spreads if k.startswith(away + "|")), None)

        total_line = next((float(k.split("|")[1]) for k in totals if "Over|" in k or "Over" in k), None)
        if total_line is None:
            for k in totals:
                try:
                    total_line = float(k.split("|")[1])
                    break
                except Exception:
                    pass

        over_odds  = totals.get(f"Over|{total_line}")  or totals.get("Over")
        under_odds = totals.get(f"Under|{total_line}") or totals.get("Under")

        game = {
            "gameID":         game_id,
            "commence":       commence,
            "home":           home,
            "away":           away,
            "ml_home":        home_ml,
            "ml_away":        away_ml,
            "spread_home":    spread_h_val,
            "spread_home_odds": spread_h,
            "spread_away":    spread_a_val,
            "spread_away_odds": spread_a,
            "total_line":     total_line,
            "over_odds":      over_odds,
            "under_odds":     under_odds,
            "books":          books,
        }
        out.append(game)

        # Store opening line snapshot if we haven't seen this game yet
        if game_id not in _open_lines:
            _open_lines[game_id] = {
                "total_line":  total_line,
                "spread_home": spread_h_val,
                "ml_home":     home_ml,
                "ml_away":     away_ml,
            }

    return out


def get_cfb_lines(markets: str = "h2h,spreads,totals") -> list[dict]:
    """CFB game lines — same structure as get_nfl_lines."""
    raw = _get("/sports/americanfootball_ncaaf/odds", {
        "regions": "us",
        "markets": markets,
        "oddsFormat": "american",
    })
    if not raw:
        return []
    out = []
    for event in (raw or []):
        game_id  = event.get("id", "")
        home     = event.get("home_team", "")
        away     = event.get("away_team", "")
        bookies  = event.get("bookmakers", [])
        lines    = _parse_bookmaker_lines(bookies, ["h2h", "spreads", "totals"])
        h2h      = lines.get("h2h", {})
        spreads  = lines.get("spreads", {})
        totals   = lines.get("totals", {})
        total_line = next((float(k.split("|")[1]) for k in totals if "|" in k), None)
        spread_h_val = next((float(k.split("|")[1]) for k in spreads if k.startswith(home + "|")), None)
        out.append({
            "gameID":      game_id,
            "home":        home,
            "away":        away,
            "ml_home":     h2h.get(home),
            "ml_away":     h2h.get(away),
            "spread_home": spread_h_val,
            "total_line":  total_line,
            "over_odds":   totals.get("Over"),
            "under_odds":  totals.get("Under"),
        })
    return out


def get_nfl_props(event_id: str, markets: str = "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_anytime_td") -> list[dict]:
    """
    Player prop lines for one event. Returns flat list:
      {playerName, market, line, over_odds, under_odds}
    """
    raw = _get(f"/sports/americanfootball_nfl/events/{event_id}/odds", {
        "regions":    "us",
        "markets":    markets,
        "oddsFormat": "american",
    })
    if not raw:
        return []

    out: dict[str, dict] = {}
    for bk in (raw.get("bookmakers") or []):
        for mkt in (bk.get("markets") or []):
            mkt_key = mkt.get("key", "")
            for outcome in (mkt.get("outcomes") or []):
                player_name = outcome.get("description", outcome.get("name", ""))
                direction   = outcome.get("name", "").upper()  # "Over" / "Under"
                price       = outcome.get("price")
                point       = outcome.get("point")
                if not player_name or price is None:
                    continue
                prop_key = f"{player_name}|{mkt_key}"
                if prop_key not in out:
                    out[prop_key] = {
                        "playerName": player_name,
                        "market":     mkt_key,
                        "line":       point,
                        "over_odds":  None,
                        "under_odds": None,
                    }
                if direction == "OVER":
                    if out[prop_key]["over_odds"] is None:
                        out[prop_key]["over_odds"] = price
                    if point is not None:
                        out[prop_key]["line"] = point
                elif direction == "UNDER":
                    if out[prop_key]["under_odds"] is None:
                        out[prop_key]["under_odds"] = price

    return list(out.values())


def line_movement(game_id: str, current_lines: list[dict] | None = None) -> dict:
    """
    Compare current line to opening-line snapshot.
    Returns: {total_drift, spread_drift, ml_home_drift, has_movement}
    """
    opening = _open_lines.get(game_id)
    if not opening:
        return {"has_movement": False}
    current = next((g for g in (current_lines or []) if g["gameID"] == game_id), None)
    if not current:
        return {"has_movement": False}

    total_now   = current.get("total_line")
    total_open  = opening.get("total_line")
    total_drift = round(total_now - total_open, 1) if (total_now and total_open) else None

    spread_now  = current.get("spread_home")
    spread_open = opening.get("spread_home")
    spread_drift = round(spread_now - spread_open, 1) if (spread_now and spread_open) else None

    has = bool((total_drift and abs(total_drift) >= 0.5) or (spread_drift and abs(spread_drift) >= 0.5))
    return {
        "has_movement":   has,
        "total_open":     total_open,
        "total_current":  total_now,
        "total_drift":    total_drift,
        "spread_open":    spread_open,
        "spread_current": spread_now,
        "spread_drift":   spread_drift,
    }


def best_line(team_name: str, market: str = "h2h") -> dict | None:
    """
    Find the best available price for a team across all books.
    market: "h2h" | "spreads"
    Returns: {bookmaker, price, eventID} or None
    """
    raw = _get("/sports/americanfootball_nfl/odds", {
        "regions":    "us",
        "markets":    market,
        "oddsFormat": "american",
    })
    if not raw:
        return None
    best_price: float | None = None
    best_book: str | None = None
    best_event: str | None = None
    for event in (raw or []):
        for bk in (event.get("bookmakers") or []):
            for mkt in (bk.get("markets") or []):
                if mkt.get("key") != market:
                    continue
                for outcome in (mkt.get("outcomes") or []):
                    if team_name.lower() in outcome.get("name", "").lower():
                        price = float(outcome.get("price", -9999))
                        if best_price is None or price > best_price:
                            best_price = price
                            best_book  = bk.get("key")
                            best_event = event.get("id")
    if best_book:
        return {"bookmaker": best_book, "price": int(round(best_price)), "eventID": best_event}
    return None


# ── convenience indexes ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _nfl_lines_cached() -> list[dict]:
    """Cached wrapper; use this inside other modules."""
    return get_nfl_lines()


def nfl_lines_by_team() -> dict[str, dict]:
    """Quick lookup: team_name → game line dict."""
    lines = get_nfl_lines()
    out: dict[str, dict] = {}
    for g in lines:
        out[g["home"]] = g
        out[g["away"]] = g
    return out


def nfl_props_by_player(event_id: str) -> dict[str, list[dict]]:
    """Quick lookup: player_name → list of prop lines."""
    out: dict[str, list[dict]] = {}
    for prop in get_nfl_props(event_id):
        out.setdefault(prop["playerName"], []).append(prop)
    return out


def implied_probability(american_odds: int) -> float:
    """Convert American odds to implied probability (0-1)."""
    if american_odds > 0:
        return round(100 / (american_odds + 100), 4)
    return round(abs(american_odds) / (abs(american_odds) + 100), 4)

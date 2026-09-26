"""
JIMMY (BPL mode) -- college legs. FanDuel is the only price source, the Big Proppa
Line (bpl.cfb_game_total: expected points for each team) is the only opinion.

For every upcoming FBS game FanDuel has on the board (moneyline, spread, total):
    margin_mu = home BPL points - away BPL points
    total_mu  = home BPL points + away BPL points
    P(side)   = normal CDF around those means, with the error spread measured in the
                2024-2025 walk-forward backtest (scripts/build_bpl_cfb_calibration.py):
                sd of (actual - predicted) is 16.6 points for both totals and margins,
                and the normal fit is close (50.3% of games inside 0.67 sd, 68.6% inside 1 sd).

The legs come back in the same shape as jimmy_bpl's NFL legs, so both series
(BPL_EDGE and SPY BOY) and MY BOO treat them identically. Lines cost 3 Odds API
credits per pull, cached 30 minutes, and never pulled when credits are under the reserve.
"""
from __future__ import annotations

import math
import os
import time
from datetime import datetime, timezone

import requests

import bpl

SIGMA = 16.6
MIN_CFB_GAMES = 2          # FBS-vs-FBS games this season; the calibration was fit from 1 game on, shrunk toward last season
CACHE_SECONDS = 1800
CREDIT_RESERVE = 150
LEAD_SECONDS = 300         # skip games starting within 5 minutes; the price will be gone before a bet lands
MARKET_LABEL = {"cfb_total": "GAME TOTAL", "cfb_spread": "SPREAD", "cfb_ml": "MONEYLINE"}

_cache: dict = {"at": 0.0, "events": [], "remaining": None}


def _cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _fanduel_events() -> list[dict]:
    if time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["events"]
    key = os.environ.get("THE_ODDS_API_KEY", "")
    left = _cache["remaining"]
    if not key or (left is not None and left - 3 < CREDIT_RESERVE):
        return _cache["events"]
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds", timeout=15,
                         params={"apiKey": key, "regions": "us", "bookmakers": "fanduel",
                                 "markets": "h2h,spreads,totals", "oddsFormat": "american"})
        r.raise_for_status()
    except requests.RequestException:
        return _cache["events"]
    rem = r.headers.get("x-requests-remaining")
    _cache.update(at=time.time(), events=r.json(), remaining=int(rem) if rem is not None else None)
    return _cache["events"]


def _neutral_pairs(year: int) -> set[frozenset]:
    import cfb_data
    games = cfb_data._get_cached("/games", {"year": year, "seasonType": "regular"}) or []
    return {frozenset((g["homeTeam"], g["awayTeam"])) for g in games if g.get("neutralSite")}


def _resolver(teams: set[str]):
    """Odds API names carry a mascot ('Georgia Bulldogs'); CFBD names do not. Longest CFBD prefix wins."""
    ordered = sorted(teams, key=len, reverse=True)

    def resolve(name: str) -> str | None:
        return next((t for t in ordered if name == t or name.startswith(t + " ")), None)
    return resolve


def _margins(team: str, cur: dict) -> list[float]:
    d = cur.get(team) or {"scored": [], "allowed": []}
    return [s - a for s, a in zip(d["scored"], d["allowed"])]


def _leg(gid: str, home: str, away: str, week: int, market: str, direction: str, line: float, team: str,
         price: float, model_p: float, book_p: float, recent: list[bool], bpl_val: float, note: str) -> dict:
    prop = {"cfb_total": f"{direction.upper()} {line:g} GAME TOTAL",
            "cfb_spread": f"{team} {line:+g} SPREAD",
            "cfb_ml": f"{team} MONEYLINE"}[market]
    return {
        "playerId": f"CFB:{gid}", "name": f"{away} @ {home}", "team": team or "TOTAL", "market": market,
        "direction": direction, "line": line, "odds": int(price), "decimal": round(_dec(price), 4),
        "modelP": round(model_p, 4), "bookP": round(book_p, 4),
        "recentHits": sum(recent), "recentGames": len(recent), "bpl": bpl_val, "gapPct": 0.0,
        "gameId": f"CFB:{gid}", "week": week, "prop": prop, "l5": 0, "alt": False, "sport": "CFB", "note": note,
    }


def cfb_sides(week: int) -> list[dict]:
    import cfb_data
    year = cfb_data._current_season()
    cur = bpl._cfb_points_for(year)
    if not cur or not bpl._cfb_points_for(year - 1):
        return []
    resolve = _resolver(set(cur) | set(bpl._cfb_points_for(year - 1)))
    neutral = _neutral_pairs(year)
    cutoff = datetime.now(timezone.utc).timestamp() + LEAD_SECONDS
    out: list[dict] = []
    for e in _fanduel_events():
        start = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).timestamp()
        home, away = resolve(e["home_team"]), resolve(e["away_team"])
        book = next((b for b in e.get("bookmakers", []) if b["key"] == "fanduel"), None)
        if start < cutoff or not home or not away or not book:
            continue
        if min(len(cur.get(home, {}).get("scored", [])), len(cur.get(away, {}).get("scored", []))) < MIN_CFB_GAMES:
            continue
        model = bpl.cfb_game_total(home, away, frozenset((home, away)) in neutral)
        if not model:
            continue
        margin_mu = model["homePoints"] - model["awayPoints"]
        total_mu = model["homePoints"] + model["awayPoints"]
        hm, am = _margins(home, cur), _margins(away, cur)
        totals = [s + a for t in (home, away) for s, a in zip(cur[t]["scored"], cur[t]["allowed"])]
        mk = {m["key"]: {o["name"] + (f"|{o['point']}" if "point" in o else ""): o for o in m["outcomes"]} for m in book["markets"]}
        gid = e["id"]

        tot = mk.get("totals", {})
        over = next((o for k, o in tot.items() if k.startswith("Over")), None)
        under = next((o for k, o in tot.items() if k.startswith("Under")), None)
        if over and under and over.get("point") == under.get("point"):
            line = float(over["point"])
            d_o, d_u = _dec(over["price"]), _dec(under["price"])
            book_o = (1 / d_o) / (1 / d_o + 1 / d_u)
            p_o = 1 - _cdf((line - total_mu) / SIGMA)
            note = f"BPL total {model['bpl']:g} vs FanDuel {line:g}"
            for side, px, mp, bp, rec in (("over", over["price"], p_o, book_o, [t > line for t in totals]),
                                          ("under", under["price"], 1 - p_o, 1 - book_o, [t < line for t in totals])):
                out.append(_leg(gid, home, away, week, "cfb_total", side, line, "", px, mp, bp, rec, model["bpl"],
                                f"{note} · hit {mp:.0%} vs FanDuel implied {1 / _dec(px):.0%} · {sum(rec)}/{len(rec)} team games cleared it"))

        sp = mk.get("spreads", {})
        h_sp = next((o for k, o in sp.items() if k.split("|")[0] == e["home_team"]), None)
        a_sp = next((o for k, o in sp.items() if k.split("|")[0] == e["away_team"]), None)
        if h_sp and a_sp:
            s_h = float(h_sp["point"])
            d_h, d_a = _dec(h_sp["price"]), _dec(a_sp["price"])
            book_h = (1 / d_h) / (1 / d_h + 1 / d_a)
            p_h = _cdf((margin_mu + s_h) / SIGMA)
            for team, px, mp, bp, sline, rec in (
                    (home, h_sp["price"], p_h, book_h, s_h, [m + s_h > 0 for m in hm]),
                    (away, a_sp["price"], 1 - p_h, 1 - book_h, -s_h, [m - s_h > 0 for m in am])):
                out.append(_leg(gid, home, away, week, "cfb_spread", "cover", sline, team, px, mp, bp, rec, round(margin_mu if team == home else -margin_mu, 1),
                                f"BPL margin {home} {margin_mu:+.1f} vs FanDuel {home} {s_h:+g} · cover {mp:.0%} vs FanDuel implied {1 / _dec(px):.0%} · "
                                f"{sum(rec)}/{len(rec)} of {team}'s games cleared it"))

        ml = mk.get("h2h", {})
        h_ml, a_ml = ml.get(e["home_team"]), ml.get(e["away_team"])
        if h_ml and a_ml:
            d_h, d_a = _dec(h_ml["price"]), _dec(a_ml["price"])
            book_h = (1 / d_h) / (1 / d_h + 1 / d_a)
            p_h = _cdf(margin_mu / SIGMA)
            for team, px, mp, bp, rec in ((home, h_ml["price"], p_h, book_h, [m > 0 for m in hm]),
                                          (away, a_ml["price"], 1 - p_h, 1 - book_h, [m > 0 for m in am])):
                out.append(_leg(gid, home, away, week, "cfb_ml", "win", 0.0, team, px, mp, bp, rec, round(margin_mu if team == home else -margin_mu, 1),
                                f"BPL margin {home} {margin_mu:+.1f} · win {mp:.0%} vs FanDuel implied {1 / _dec(px):.0%} · "
                                f"{sum(rec)}/{len(rec)} of {team}'s games won"))
    return out

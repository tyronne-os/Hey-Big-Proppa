"""
JIMMY (BPL mode) -- NFL game legs: total, spread and moneyline, priced by FanDuel.

FanDuel's prices come from the same Tank01 pull that feeds THE ODDS pond
(odds_pond.nfl_raw_games, cached), so this costs no extra API calls. The only opinion is the
Big Proppa Line's team-points model (bpl.nfl_game_totals): a projected home and away score.

    P(side) = normal CDF around the projected margin / total, sd 13.5 points
              (7.57 team-points backtest error -> about 1.25 * 7.57 * sqrt(2) for a two-team sum)
    trusted = 50% + (P - 50%) * TRUST      Vegas is sharper than a model fed two games of this
                                           season, so only half of the gap is believed.

Legs come back in the shape jimmy_bpl expects and share the game id of that game's player props,
so the one-leg-per-game rule keeps a game total and a player prop out of the same ticket.
"""
from __future__ import annotations

import math
import time

import bpl
import odds_pond

SIGMA = 13.5
TRUST = 0.5
LEAD_SECONDS = 300
MIN_GAMES = 2


def _cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _leg(game: dict, home: str, away: str, market: str, direction: str, line: float, team: str, name: str,
         price: float, raw_p: float, book_p: float, recent: list[bool], bpl_val: float, note: str) -> dict:
    p = 0.5 + (raw_p - 0.5) * TRUST
    prop = {"nfl_total": f"{direction.upper()} {line:g} GAME TOTAL",
            "nfl_spread": f"{name} {line:+g} SPREAD",
            "nfl_ml": f"{name} MONEYLINE"}[market]
    gid = f"NFLG:{game['gameId']}"
    return {
        "playerId": gid, "name": f"{away} @ {home}", "team": name if market != "nfl_total" else "TOTAL", "market": market,
        "direction": direction, "line": line, "odds": int(price), "decimal": round(_dec(price), 4),
        "modelP": round(p, 4), "bookP": round(book_p, 4), "recentHits": sum(recent), "recentGames": len(recent),
        "bpl": bpl_val, "gapPct": 0.0, "gameId": game["gameId"], "week": game["week"], "prop": prop, "l5": 0, "alt": False,
        "sport": "NFL", "note": f"{note} · raw {raw_p:.0%}, {p:.0%} trusting Vegas half · FanDuel implied {1 / _dec(price):.0%} · "
                                f"{sum(recent)}/{len(recent)} of this season's games cleared it",
    }


def nfl_sides() -> list[dict]:
    teams = odds_pond._teams()
    nxt = bpl.next_games()
    model = {(t["home"], t["away"]): t for t in bpl.nfl_game_totals()}
    hist = bpl._team_points_history()
    cutoff = time.time() + LEAD_SECONDS
    out: list[dict] = []
    for r in odds_pond.nfl_raw_games():
        if r["epoch"] and r["epoch"] < cutoff:
            continue
        home = teams.get(r["home"], {}).get("lake")
        away = teams.get(r["away"], {}).get("lake")
        m, g, fd = model.get((home, away)), nxt.get(home), r["books"].get("fanduel")
        if not (home and away and m and g and fd):
            continue
        hh, ah = hist.get(home, {"scored": [], "allowed": []}), hist.get(away, {"scored": [], "allowed": []})
        if min(len(hh["scored"]), len(ah["scored"])) < MIN_GAMES:
            continue
        margin_mu = m["homePoints"] - m["awayPoints"]
        total_mu = m["homePoints"] + m["awayPoints"]
        hm = [s - a for s, a in zip(hh["scored"], hh["allowed"])]
        am = [s - a for s, a in zip(ah["scored"], ah["allowed"])]
        totals = [s + a for h in (hh, ah) for s, a in zip(h["scored"], h["allowed"])]
        hn, an = teams[r["home"]]["name"], teams[r["away"]]["name"]

        line = _f(fd.get("totalOver"))
        po, pu = _f(fd.get("totalOverOdds")), _f(fd.get("totalUnderOdds"))
        if line is not None and po and pu:
            book_o = (1 / _dec(po)) / (1 / _dec(po) + 1 / _dec(pu))
            p_o = 1 - _cdf((line - total_mu) / SIGMA)
            note = f"BPL total {total_mu:.1f} vs FanDuel {line:g}"
            for side, px, rp, bp, rec in (("over", po, p_o, book_o, [t > line for t in totals]),
                                          ("under", pu, 1 - p_o, 1 - book_o, [t < line for t in totals])):
                out.append(_leg(g, hn, an, "nfl_total", side, line, "", "", px, rp, bp, rec, round(total_mu, 1), note))

        s_h = _f(fd.get("homeTeamSpread"))
        ph, pa = _f(fd.get("homeTeamSpreadOdds")), _f(fd.get("awayTeamSpreadOdds"))
        if s_h is not None and ph and pa:
            book_h = (1 / _dec(ph)) / (1 / _dec(ph) + 1 / _dec(pa))
            p_h = _cdf((margin_mu + s_h) / SIGMA)
            note = f"BPL margin {home} {margin_mu:+.1f} vs FanDuel {home} {s_h:+g}"
            for name, px, rp, bp, sl, rec in ((hn, ph, p_h, book_h, s_h, [x + s_h > 0 for x in hm]),
                                             (an, pa, 1 - p_h, 1 - book_h, -s_h, [x - s_h > 0 for x in am])):
                out.append(_leg(g, hn, an, "nfl_spread", "cover", sl, "", name, px, rp, bp, rec, round(margin_mu if name == hn else -margin_mu, 1), note))

        mh, ma = _f(fd.get("homeTeamML")), _f(fd.get("awayTeamML"))
        if mh and ma:
            book_h = (1 / _dec(mh)) / (1 / _dec(mh) + 1 / _dec(ma))
            p_h = _cdf(margin_mu / SIGMA)
            note = f"BPL margin {home} {margin_mu:+.1f}"
            for name, px, rp, bp, rec in ((hn, mh, p_h, book_h, [x > 0 for x in hm]), (an, ma, 1 - p_h, 1 - book_h, [x > 0 for x in am])):
                out.append(_leg(g, hn, an, "nfl_ml", "win", 0.0, "", name, px, rp, bp, rec, round(margin_mu if name == hn else -margin_mu, 1), note))
    return out

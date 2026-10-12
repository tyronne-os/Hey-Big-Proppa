"""
HEAD TO HEAD -- one matchup at a time: the Leaders boards restricted to the two rosters, ESPN's slate
and lines, a per-player ticket analysis, live ESPN box-score tracking, and the manual ticket store
that feeds the Monday / Thursday / Sunday parlay pages.

HARD RULE: no touchdown-scorer legs. Only the four yardage / reception markets in bpl.NFL_MARKETS can
be added to a ticket (red_zone.py stays the single source of truth for scorer logic elsewhere).

Everything is lake + ESPN. Prices come from FanDuel rows in prop_line_rotowire; game lines come from ESPN's
scoreboard. Alternate-line prices are model estimates and are always labelled as such.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import statistics
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import bpl
import data
import espn

CT = ZoneInfo("America/Chicago")
_SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_SUM = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={}"

MARKET_LABEL = {"rushyds": "Rushing Yards", "recyds": "Receiving Yards", "recs": "Receptions", "passyds": "Passing Yards"}
STAT_KEY = {"rushyds": "rushyds", "recyds": "recyds", "recs": "recs", "passyds": "passyds"}
ALT_STEP = {"rushyds": 10.0, "recyds": 10.0, "recs": 1.0, "passyds": 25.0}
SD_FLOOR = {"rushyds": 12.0, "recyds": 14.0, "recs": 1.1, "passyds": 38.0}
WAGER = 5.0
BOOST = 0.50

# (category, weekly gold csv, stat column, BPL/FanDuel market or None, unit)
CATEGORIES = [
    ("TARGETS", "player_receiving_week", "targets", None, "tgt"),
    ("RECEIVING", "player_receiving_week", "receiving_yards", "recyds", "yds"),
    ("RECEPTIONS", "player_receiving_week", "receptions", "recs", "rec"),
    ("RUSHING", "player_rushing_week", "rushing_yards", "rushyds", "yds"),
    ("PASSING", "player_passing_week", "passing_yards", "passyds", "yds"),
    ("SCORING", "player_scoring_week", "total_points", None, "pts"),
    ("FIELD GOALS", "player_kicking_week", "fg_made", None, "fg"),
    ("USAGE INDEX", "player_usage", "usage_index_score", None, "idx"),
    ("SACKS", "individual_sacks", "sacks", None, "sck"),
]
SEASON_GRAIN = {"player_usage", "individual_sacks"}

_LOCK = threading.Lock()
_TTL: dict[str, tuple[float, object]] = {}


def _cached(key: str, ttl: float, fn):
    now = time.time()
    with _LOCK:
        hit = _TTL.get(key)
        if hit and hit[0] > now:
            return hit[1]
    val = fn()
    with _LOCK:
        _TTL[key] = (now + ttl, val)
    return val


def _lake(abbr: str) -> str:
    return bpl._ABBR.get(abbr, abbr)


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _am(v) -> int | None:
    try:
        return int(float(str(v).replace("+", "")))
    except (TypeError, ValueError):
        return None


def _dec(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _implied(a: float) -> float:
    return 1 / _dec(a)


def _am_from_p(p: float) -> int:
    p = min(max(p, 0.02), 0.98)
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def _cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _fmt_am(a: int | None) -> str:
    return "" if a is None else (f"+{a}" if a > 0 else str(a))


# ---------------------------------------------------------------------------
# Slate -- ESPN schedule + lines (current week's unfinished games, then next week)
# ---------------------------------------------------------------------------

def _parse_event(ev: dict) -> dict:
    comp = (ev.get("competitions") or [ev])[0]
    cs = comp.get("competitors", [])
    away = next((c for c in cs if c.get("homeAway") == "away"), {})
    home = next((c for c in cs if c.get("homeAway") == "home"), {})

    def side(c):
        t = c.get("team") or {}
        recs = c.get("records") or []
        return {"abbr": _lake(t.get("abbreviation", "")), "espn": t.get("abbreviation", ""), "name": t.get("shortDisplayName") or t.get("displayName", ""),
                "logo": t.get("logo") or "", "score": int(_f(c.get("score"), 0) or 0), "record": recs[0].get("summary") if recs else ""}

    a, h = side(away), side(home)
    start = dt.datetime.strptime(ev["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    ct = start.astimezone(CT)
    wd = ct.strftime("%A").lower()
    day = "monday" if wd == "monday" else "thursday" if wd == "thursday" else "sunday"
    st = (comp.get("status") or {})
    stype = (st.get("type") or {}).get("name", "")
    state = ("FINAL" if "FINAL" in stype else "HALFTIME" if "HALF" in stype else "LIVE" if "PROGRESS" in stype or "END_PERIOD" in stype else "PRE")

    o = (comp.get("odds") or [{}])[0]
    ml = o.get("moneyline") or {}
    ps = o.get("pointSpread") or {}
    tot = o.get("total") or {}

    def close(node, side_):
        return ((node.get(side_) or {}).get("close") or {})

    def opened(node, side_):
        return ((node.get(side_) or {}).get("open") or {})

    total = _f(o.get("overUnder"))
    spread_home = _f(o.get("spread"))
    sp_open = _f(opened(ps, "home").get("line"))
    tot_open = _f(str(opened(tot, "over").get("line", "")).lstrip("ou"))
    implied = None
    if total is not None and spread_home is not None:
        implied = {h["abbr"]: round((total - spread_home) / 2, 1), a["abbr"]: round((total + spread_home) / 2, 1)}
    fav = None
    if spread_home is not None:
        fav = {"team": h["abbr"] if spread_home < 0 else a["abbr"] if spread_home > 0 else None, "points": abs(spread_home)}
    lines = {
        "provider": ((o.get("provider") or {}).get("displayName") or "") if o else "",
        "details": o.get("details", "") if o else "",
        "spreadHome": spread_home, "favorite": fav, "total": total,
        "mlAway": _am(close(ml, "away").get("odds")), "mlHome": _am(close(ml, "home").get("odds")),
        "spreadAwayOdds": _am(close(ps, "away").get("odds")), "spreadHomeOdds": _am(close(ps, "home").get("odds")),
        "overOdds": _am(close(tot, "over").get("odds")), "underOdds": _am(close(tot, "under").get("odds")),
        "spreadOpen": sp_open, "totalOpen": tot_open,
        "spreadMove": None if sp_open is None or spread_home is None else round(spread_home - sp_open, 1),
        "totalMove": None if tot_open is None or total is None else round(total - tot_open, 1),
        "implied": implied,
    } if o else None
    w = comp.get("weather") or {}
    venue = comp.get("venue") or {}
    sit = comp.get("situation") or {}
    hour12 = ct.hour % 12 or 12
    return {
        "id": str(ev.get("id", "")), "away": a, "home": h,
        "kickoff": {"utc": start.isoformat().replace("+00:00", "Z"), "ct": f"{ct.strftime('%a')} {hour12}:{ct.minute:02d}{'a' if ct.hour < 12 else 'p'} CT",
                    "dateLabel": f"{ct.strftime('%a %b')} {ct.day}", "hourCt": ct.hour, "weekday": ct.strftime("%A")},
        "day": day, "state": state,
        "clock": (st.get("displayClock") or "") if state in ("LIVE", "HALFTIME") else "", "period": int(_f(st.get("period"), 0) or 0),
        "statusDetail": (st.get("type") or {}).get("shortDetail", ""),
        "downDistance": sit.get("downDistanceText") or "", "redZone": bool(sit.get("isRedZone")),
        "lines": lines,
        "weather": {"text": w.get("displayValue") or w.get("conditionId") or "", "temp": w.get("temperature"), "wind": _f((w.get("wind") or {}).get("speed")) if isinstance(w.get("wind"), dict) else None} if w else None,
        "indoor": bool(venue.get("indoor")), "venue": venue.get("fullName", ""),
        "broadcast": ", ".join(n for b in comp.get("broadcasts", []) for n in b.get("names", [])),
    }


def _events(week: int | None, season_type: int | None) -> tuple[list[dict], int | None, int | None]:
    url = _SB
    if week:
        url += f"?week={week}&seasontype={season_type or 2}"
    body = espn._fetch(url, ttl=60)
    if not body:
        return [], week, season_type
    wk = (body.get("week") or {}).get("number")
    ty = (body.get("season") or {}).get("type")
    return [_parse_event(e) for e in body.get("events", [])], wk, ty


def slate() -> dict:
    def build():
        cur, wk, ty = _events(None, None)
        nxt, _, _ = _events((wk or 0) + 1, ty) if wk else ([], None, None)
        seen, games = set(), []
        now = dt.datetime.now(dt.timezone.utc)
        for g in cur + nxt:
            if g["id"] in seen:
                continue
            seen.add(g["id"])
            start = dt.datetime.fromisoformat(g["kickoff"]["utc"].replace("Z", "+00:00"))
            if g["state"] == "FINAL" and now - start > dt.timedelta(hours=10):
                continue
            games.append(g)
        games.sort(key=lambda g: g["kickoff"]["utc"])
        for g in games[:1]:
            wd, hr = g["kickoff"]["weekday"], g["kickoff"]["hourCt"]
            g["night"] = ("MONDAY NIGHT FOOTBALL" if wd == "Monday" else "THURSDAY NIGHT FOOTBALL" if wd == "Thursday"
                          else "SUNDAY NIGHT FOOTBALL" if wd == "Sunday" and hr >= 17 else None)
        return {"week": wk, "source": "ESPN", "games": games, "asOf": dt.datetime.now(CT).strftime("%a %I:%M %p CT"), "ok": bool(games)}
    return _cached("slate", 60, build)


def find_game(game_id: str) -> dict | None:
    return next((g for g in slate()["games"] if g["id"] == str(game_id)), None)


def game_for_team(team: str) -> dict | None:
    return next((g for g in slate()["games"] if team in (g["away"]["abbr"], g["home"]["abbr"]) and g["state"] != "FINAL"), None)


# ---------------------------------------------------------------------------
# Lake history, FanDuel lines, injuries
# ---------------------------------------------------------------------------

def _hist(src: str, col: str) -> dict[str, list[dict]]:
    def build():
        out: dict[str, list[dict]] = {}
        for r in data.load(src):
            pid = r.get("player_id")
            if not pid:
                continue
            out.setdefault(pid, []).append({"season": int(r.get("season") or 0), "week": int(r.get("week") or 0),
                                            "opp": r.get("opponent_team", ""), "team": r.get("team", ""), "value": _f(r.get(col), 0.0) or 0.0})
        for rows in out.values():
            rows.sort(key=lambda x: (x["season"], x["week"]))
        return out
    return _cached(f"hist:{src}:{col}", 180, build)


def _fd_lines() -> dict[tuple[str, str, str], dict]:
    """(market, normalized name, team) -> FanDuel main line + both prices from the latest pull (other books only as a fallback)."""
    def build():
        grouped: dict[tuple, dict[str, list[dict]]] = {}
        for r in data.load("prop_line_rotowire"):
            m = r.get("market_slug")
            if m not in bpl.NFL_MARKETS or not r.get("line"):
                continue
            key = (m, data.normalize_name(r.get("player_name", "")), _lake(r.get("team", "")))
            grouped.setdefault(key, {}).setdefault(r.get("pull_id", ""), []).append(r)
        pref = {"fanduel": 0, "draftkings": 1, "caesars": 2}
        out = {}
        for key, pulls in grouped.items():
            pid = max(pulls)
            rows = sorted(pulls[pid], key=lambda x: pref.get(x.get("book_slug", ""), 9))
            book = rows[0].get("book_slug", "")
            mine = [x for x in rows if x.get("book_slug") == book]

            def balance(x):
                o, u = _am(x.get("over_price_american")), _am(x.get("under_price_american"))
                return abs(_implied(o) - _implied(u)) if o and u else 9
            row = min(mine, key=balance)
            out[key] = {"line": _f(row["line"]), "overPrice": _am(row.get("over_price_american")), "underPrice": _am(row.get("under_price_american")),
                        "book": "FanDuel" if book == "fanduel" else book.title(), "isFanDuel": book == "fanduel", "pull": pid,
                        "opp": bpl._opp_code(row.get("opponent", ""))}
        return out
    return _cached("fd", 120, build)


def _badge(status: str) -> str:
    s = (status or "").lower()
    return ("OUT" if "out" in s else "IR" if "reserve" in s else "D" if "doubt" in s else "Q" if "question" in s else "DTD" if "day" in s else (status or "")[:3].upper())


def _injuries(game_id: str) -> dict[str, dict]:
    body = espn._fetch(_SUM.format(game_id), ttl=600) or {}
    out = {}
    for t in body.get("injuries", []):
        for i in t.get("injuries", []):
            nm = data.normalize_name((i.get("athlete") or {}).get("displayName", ""))
            st = i.get("status") or ""
            out[nm] = {"status": st, "badge": _badge(st), "detail": (i.get("details") or {}).get("type") or ""}
    return out


# ---------------------------------------------------------------------------
# Boards -- the Leaders categories, restricted to one game's two rosters, ranked by last five games
# ---------------------------------------------------------------------------

def _row(pid: str, dim: dict, vals: list[dict], market: str | None, game: dict, inj: dict) -> dict:
    d = dim.get(pid, {})
    name, team = d.get("name") or data.player_name(pid), (vals[-1]["team"] if vals else d.get("team", ""))
    l5 = vals[-5:]
    nums = [v["value"] for v in vals]
    row = {
        "playerId": pid, "name": name, "team": team, "pos": d.get("position", ""), "photoUrl": data.photo_url(pid),
        "gp": len(vals), "l5": [{"week": v["week"], "opp": v["opp"], "value": v["value"]} for v in l5],
        "l5Avg": round(sum(v["value"] for v in l5) / len(l5), 1) if l5 else None,
        "l5Total": round(sum(v["value"] for v in l5), 1) if l5 else None,
        "seasonAvg": round(sum(nums) / len(nums), 1) if nums else None, "seasonTotal": round(sum(nums), 1) if nums else None,
        "market": market, "line": None, "overPrice": None, "underPrice": None, "book": None, "bpl": None, "diffPct": None,
        "l5Over": None, "oppRank": None, "injury": inj.get(data.normalize_name(name)),
    }
    if market:
        fd = _fd_lines().get((market, data.normalize_name(name), team))
        b = bpl.nfl_player_line(pid, market, name, team)
        row["bpl"], row["oppRank"] = b.get("bpl"), b.get("nextOppRank")
        if fd:
            row.update(line=fd["line"], overPrice=fd["overPrice"], underPrice=fd["underPrice"], book=fd["book"])
            row["diffPct"] = bpl.diff_pct(b.get("bpl"), fd["line"])
            row["l5Over"] = sum(1 for v in l5 if v["value"] > fd["line"])
    return row


def boards(game_id: str) -> dict:
    g = find_game(game_id)
    if not g:
        return {"ok": False, "error": "game not on the ESPN slate"}

    def build():
        teams = {g["away"]["abbr"], g["home"]["abbr"]}
        dim = data.player_dimension()
        inj = _injuries(game_id)
        cats = []
        for cat, src, col, market, unit in CATEGORIES:
            rows = []
            if src in SEASON_GRAIN:
                for r in data.load(src):
                    if _lake(r.get("team", "")) not in teams:
                        continue
                    pid, val = r.get("player_id", ""), _f(r.get(col), 0.0) or 0.0
                    if val <= 0:
                        continue
                    base = _row(pid, dim, [{"season": 2026, "week": 0, "opp": "", "team": r.get("team", ""), "value": val}], None, g, inj)
                    base.update(l5=[], l5Avg=None, l5Total=None, seasonAvg=val, seasonTotal=val, gp=int(_f(r.get("games"), 0) or 0))
                    if pid not in dim:
                        base["name"] = r.get("player_name") or base["name"]
                    base["pos"] = r.get("position") or base["pos"]
                    rows.append(base)
                rows.sort(key=lambda r: -(r["seasonTotal"] or 0))
            else:
                for pid, vals in _hist(src, col).items():
                    if _lake(vals[-1]["team"]) not in teams:
                        continue
                    if sum(v["value"] for v in vals) <= 0:
                        continue
                    rows.append(_row(pid, dim, vals, market, g, inj))
                rows.sort(key=lambda r: (-(r["l5Avg"] or 0), -(r["seasonTotal"] or 0)))
            per_team: dict[str, int] = {}
            kept = []
            for r in rows:
                t = _lake(r["team"])
                per_team[t] = per_team.get(t, 0) + 1
                if per_team[t] <= 8:
                    kept.append(r)
            for i, r in enumerate(kept, 1):
                r["rank"] = i
            split = {}
            for t in teams:
                top = [(r["l5Avg"] if r["l5Avg"] is not None else r["seasonTotal"]) or 0 for r in kept if _lake(r["team"]) == t][:3]
                split[t] = round(sum(top), 1)
            cats.append({"category": cat, "unit": unit, "market": market, "seasonGrain": src in SEASON_GRAIN, "rows": kept, "teamSplit": split})
        import jev
        items = [(r["playerId"] + ":" + r["market"], r["playerId"], r["name"], r["team"], r["market"], r["line"])
                 for c in cats for r in c["rows"] if r.get("market") and r.get("line")]
        ov, pending = jev.leader_overlay(items, wait=6.0)
        for c in cats:
            for r in c["rows"]:
                if r.get("market") and r["playerId"] + ":" + r["market"] in ov:
                    r["jev"] = ov[r["playerId"] + ":" + r["market"]]
        return {"ok": True, "game": g, "categories": cats, "jevPending": pending}
    return _cached(f"boards:{game_id}", 20, build)


# ---------------------------------------------------------------------------
# Player analysis -- the ticket-builder brain
# ---------------------------------------------------------------------------

def _script(market: str, team: str, g: dict | None) -> dict:
    """Game-script read from ESPN's spread and total: who is chasing, how many points the team is implied to score."""
    if not g or not g.get("lines"):
        return {"score": 0, "note": "No ESPN line posted yet.", "implied": None, "spread": None, "total": None}
    ln = g["lines"]
    sp_home, total = ln.get("spreadHome"), ln.get("total")
    is_home = team == g["home"]["abbr"]
    team_spread = None if sp_home is None else (sp_home if is_home else -sp_home)
    implied = (ln.get("implied") or {}).get(team)
    score, bits = 0.0, []
    if team_spread is not None:
        if market == "rushyds":
            score += max(-1, min(1, -team_spread / 9))
            bits.append(f"{'favored' if team_spread < 0 else 'underdog'} by {abs(team_spread):g}: " + ("run-heavy script" if team_spread < -3 else "likely chasing, fewer carries" if team_spread > 3 else "balanced script"))
        else:
            score += max(-1, min(1, team_spread / 9))
            bits.append(f"{'favored' if team_spread < 0 else 'underdog'} by {abs(team_spread):g}: " + ("trailing script lifts pass volume" if team_spread > 3 else "lead can shrink pass volume late" if team_spread < -6 else "neutral pass script"))
    if implied is not None:
        bits.append(f"implied team total {implied:g}")
        score += max(-0.5, min(0.5, (implied - 22.5) / 10))
    w = g.get("weather") or {}
    wind = w.get("wind")
    if market in ("passyds", "recyds", "recs") and wind and not g.get("indoor") and wind >= 15:
        score -= 0.5
        bits.append(f"wind {wind:g} mph hurts the passing game")
    if g.get("indoor"):
        bits.append("indoors")
    return {"score": round(max(-1.5, min(1.5, score)), 2), "note": " · ".join(bits), "implied": implied, "spread": team_spread, "total": total}


def _alts(market: str, line: float, mu: float, sd: float) -> list[dict]:
    step, out = ALT_STEP[market], []
    for k in range(-3, 4):
        alt = round(line + k * step, 1)
        if alt <= 0:
            continue
        po = 1 - _cdf((alt - mu) / sd)
        # model price with a 4.5% hold folded in -- an ESTIMATE, never a posted FanDuel alt price
        po_v, pu_v = min(0.97, po * 1.045), min(0.97, (1 - po) * 1.045)
        out.append({"line": alt, "step": k, "base": k == 0, "pOver": round(po, 3), "pUnder": round(1 - po, 3),
                    "overAmerican": _am_from_p(po_v), "underAmerican": _am_from_p(pu_v), "est": True})
    return out


def analyze(player_id: str, market: str, game_id: str | None = None) -> dict:
    if market not in MARKET_LABEL:
        return {"ok": False, "ticketable": False, "reason": "Touchdown and scorer props are not wagered here. Pick a yardage or reception market."}
    dim = data.player_dimension().get(player_id, {})
    name = dim.get("name") or data.player_name(player_id)
    hist = bpl._player_history(market).get(player_id, [])
    team = dim.get("team", "") or (hist[-1]["team"] if hist else "")
    b = bpl.nfl_player_line(player_id, market, name, team)
    g = find_game(game_id) if game_id else game_for_team(team)
    fd = _fd_lines().get((market, data.normalize_name(name), team))
    vals = [h["value"] for h in hist]
    l5 = vals[-5:]
    out = {"ok": True, "playerId": player_id, "name": name, "team": team, "pos": dim.get("position", ""), "photoUrl": data.photo_url(player_id),
           "market": market, "marketLabel": MARKET_LABEL[market], "gameId": g["id"] if g else None,
           "matchup": f"{g['away']['abbr']} @ {g['home']['abbr']}" if g else None, "day": g["day"] if g else None,
           "kickoff": g["kickoff"]["ct"] if g else None, "l5": [{"week": h["week"], "opp": h["opp"], "value": h["value"]} for h in hist[-5:]],
           "seasonAvg": b.get("seasonAvg"), "bpl": b.get("bpl"), "nextOpp": b.get("nextOpp"), "nextOppRank": b.get("nextOppRank")}
    out["script"] = _script(market, team, g)
    inj = _injuries(g["id"]) if g else {}
    out["injury"] = inj.get(data.normalize_name(name))
    if not fd or fd["line"] is None:
        out.update(ticketable=False, reason="No FanDuel line is posted for this player yet. Check back closer to kickoff.", fd=None)
        return out
    line = fd["line"]
    out["fd"] = {"line": line, "overPrice": fd["overPrice"], "underPrice": fd["underPrice"], "book": fd["book"], "isFanDuel": fd["isFanDuel"], "pull": fd["pull"]}
    if not vals:
        out.update(ticketable=bool(fd["overPrice"] and fd["underPrice"]), reason="No game history in the lake yet, so the model has nothing to read.")
        return out

    l5avg = sum(l5) / len(l5)
    mu = (0.6 * b["bpl"] + 0.4 * l5avg) if b.get("bpl") is not None else l5avg
    mu *= 1 + 0.03 * out["script"]["score"]
    sd = max(statistics.pstdev(vals) if len(vals) > 1 else 0.0, SD_FLOOR[market], 0.28 * mu)
    p_over = 1 - _cdf((line - mu) / sd)
    hit_rate = sum(1 for v in l5 if v > line) / len(l5)
    jev_p, jev_read, w = None, None, 0.25
    try:
        import jev
        import jev_ledger
        w = jev_ledger.weight("prop")
        jev_read = jev.prop_read(player_id, name, team, market, line)
        jev_p = jev_read["p"] if jev_read else None
    except Exception:
        jev_p, jev_read = None, None
    if jev_p is not None:
        p_over = (1 - w) * p_over + w * jev_p
    sides = {}
    for d_, p_, px in (("over", p_over, fd["overPrice"]), ("under", 1 - p_over, fd["underPrice"])):
        if px is None:
            sides[d_] = None
            continue
        ev = p_ * _dec(px) - 1
        sides[d_] = {"p": round(p_, 3), "profitZone": p_ >= 0.85, "price": px, "priceText": _fmt_am(px), "implied": round(_implied(px), 3), "edge": round(p_ - _implied(px), 3),
                     "ev": round(ev, 3), "fairAmerican": _am_from_p(p_), "payout5": round(WAGER * _dec(px), 2)}
    live = [s for s in (("over", sides["over"]), ("under", sides["under"])) if s[1]]
    best = max(live, key=lambda s: s[1]["ev"]) if live else None
    verdict, thin = "NO PRICE", None
    if best:
        ev = best[1]["ev"]
        verdict = "STRONG" if ev >= 0.10 else "LEAN" if ev >= 0.03 else "PASS"
        if verdict == "STRONG" and len(vals) < 4:
            verdict = "LEAN"
            thin = f"Only {len(vals)} game{'s' if len(vals) != 1 else ''} of 2026 data, so a STRONG read is capped at LEAN."
    # safer-line finder: the alt on the recommended side with >=62% hit chance that still pays the most
    alts = _alts(market, line, mu, sd)
    if jev_read:
        import jev
        for a_ in alts:
            jp = jev.prop_p_over(jev_read, a_["line"])
            po = (1 - w) * a_["pOver"] + w * jp
            a_.update(pOver=round(po, 3), pUnder=round(1 - po, 3), overAmerican=_am_from_p(min(0.97, po * 1.045)), underAmerican=_am_from_p(min(0.97, (1 - po) * 1.045)))
    sweet = None
    if best:
        key = "pOver" if best[0] == "over" else "pUnder"
        cands = [a for a in alts if a[key] >= 0.62 and not a["base"]]
        if cands:
            pick = max(cands, key=lambda a: _dec(a["overAmerican"] if best[0] == "over" else a["underAmerican"]))
            sweet = {"direction": best[0], "line": pick["line"], "p": pick[key], "american": pick["overAmerican"] if best[0] == "over" else pick["underAmerican"]}
    # profit zone: the line on the favored side where the hit chance reaches 85%+, paying the most
    fav = "over" if p_over >= 0.5 else "under"
    pz_key = "pOver" if fav == "over" else "pUnder"
    pz = [a_ for a_ in alts if a_[pz_key] >= 0.85]
    pz_line = None
    if pz:
        pick = max(pz, key=lambda a_: _dec(a_["overAmerican"] if fav == "over" else a_["underAmerican"]))
        pz_line = {"direction": fav, "line": pick["line"], "p": pick[pz_key], "american": pick["overAmerican"] if fav == "over" else pick["underAmerican"],
                   "est": not pick["base"]}
    warn = [thin] if thin else []
    if out["injury"] and out["injury"]["badge"] in ("OUT", "IR"):
        warn.append(f"{name} is listed {out['injury']['status'].upper()}. Do not build on him.")
    elif out["injury"]:
        warn.append(f"Injury report: {out['injury']['status']} ({out['injury']['detail'] or 'no detail'}). Confirm he plays.")
    if not fd["isFanDuel"]:
        warn.append(f"No FanDuel row for this player, so the price shown is {fd['book']}'s.")
    if g and g["state"] in ("LIVE", "HALFTIME", "FINAL"):
        warn.append("This game has already started. Lines may have moved or closed.")
    out.update(ticketable=bool(best) and not (out["injury"] and out["injury"]["badge"] in ("OUT", "IR")),
               projection=round(mu, 1), sd=round(sd, 1), jevP=None if jev_p is None else round(jev_p, 3), jevActive=jev_p is not None,
               jev=None if not jev_read else {"p": jev_read["p"], "expected": jev_read["expected"], "weight": w, "factors": jev_read.get("factors", []),
                                               "bands": [{"label": l, "p": round(p_, 3)} for l, p_ in zip(jev_read["labels"], jev_read["bands"])]},
               sides=sides, recommended=best[0] if best else None, verdict=verdict,
               grade={"pick": fav, "confidence": round(max(p_over, 1 - p_over) * 100, 1), "profitZone": max(p_over, 1 - p_over) >= 0.85},
               profitZoneLine=pz_line,
               hits={"l5Over": sum(1 for v in l5 if v > line), "l5": len(l5), "seasonOver": sum(1 for v in vals if v > line), "season": len(vals)},
               alts=alts, sweet=sweet, warnings=warn)
    return out


# ---------------------------------------------------------------------------
# Live tracking -- ESPN box score vs each leg's line
# ---------------------------------------------------------------------------

def _elapsed_fraction(state: str, period: int, clock: str) -> float:
    if state == "PRE":
        return 0.0
    if state == "FINAL":
        return 1.0
    if state == "HALFTIME":
        return 0.5
    try:
        m, s = clock.split(":")
        left = int(m) + int(s) / 60
    except (ValueError, AttributeError):
        left = 15.0
    return min(1.0, ((min(period, 4) - 1) * 15 + (15 - left)) / 60) if period <= 4 else 1.0


def live_game(game_id: str) -> dict:
    g = find_game(game_id)
    s = espn.get_game_summary(str(game_id))
    if not s:
        return {"ok": False, "state": g["state"] if g else "PRE", "fraction": 0.0, "players": {}}
    players = {}
    for (nm, tm), st in (s.get("players") or {}).items():
        players[f"{nm}|{_lake(tm)}"] = st
    state = s["status"]
    return {"ok": True, "state": state, "period": s["period"], "clock": s["clock"], "away": _lake(s["away"]), "home": _lake(s["home"]),
            "awayScore": int(s["away_pts"]), "homeScore": int(s["home_pts"]), "fraction": _elapsed_fraction(state, s["period"], s["clock"]), "players": players}


def leg_live(leg: dict, lg: dict) -> dict:
    if not lg.get("ok"):
        return {"state": lg.get("state", "PRE"), "status": "PENDING", "current": None, "pct": 0, "pace": None}
    st = lg["players"].get(f"{data.normalize_name(leg['name'])}|{leg['team']}") or {}
    cur = float(st.get(STAT_KEY[leg["market"]], 0.0))
    frac, line, over, final = lg["fraction"], float(leg["line"]), leg["direction"] == "over", lg["state"] == "FINAL"
    pace = round(cur / frac, 1) if frac >= 0.08 else None
    if lg["state"] == "PRE":
        status = "PENDING"
    elif final:
        status = "WON" if (cur > line if over else cur < line) else "LOST"
    elif over:
        status = "HIT" if cur > line else ("ON PACE" if pace is not None and pace >= line else "BEHIND" if pace is not None else "LIVE")
    else:
        status = "BUSTED" if cur > line else ("ON PACE" if pace is not None and pace <= line else "AT RISK" if pace is not None else "LIVE")
    return {"state": lg["state"], "status": status, "current": cur, "pct": round(min(cur / line, 1.5), 3) if line else 0, "pace": pace,
            "clock": lg.get("clock", ""), "period": lg.get("period", 0), "score": f"{lg.get('away', '')} {lg.get('awayScore', 0)} - {lg.get('homeScore', 0)} {lg.get('home', '')}"}


# ---------------------------------------------------------------------------
# Manual tickets -- legs the user picks on the Head to Head / player pages land on the day's parlay page
# ---------------------------------------------------------------------------

_FILE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "espn" / "h2h_tickets.json"
_FILE_LOCK = threading.Lock()
DAYS = ("monday", "thursday", "sunday")


def token() -> str:
    h = os.environ.get("BP_PASSCODE_HASH", "2796c527960920c161bf5712c873aaa7e3b66d1301ae584045b0634695fed96d")
    return hashlib.sha256((h + ":tickets").encode()).hexdigest()[:40]


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save(obj: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(_FILE)


def _correlation(legs: list[dict]) -> list[dict]:
    notes = []
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if a["gameId"] != b["gameId"]:
                continue
            same_team = a["team"] == b["team"]
            if a["playerId"] == b["playerId"]:
                notes.append({"kind": "good" if a["direction"] == b["direction"] else "conflict",
                              "text": f"{a['name']}: {a['prop']} and {b['prop']} are the same player, so they rise and fall together."})
                continue
            qb_pass = next((x for x in (a, b) if x["market"] == "passyds" and x["pos"] == "QB"), None)
            other = b if qb_pass is a else a
            if qb_pass and same_team and other["market"] in ("recyds", "recs"):
                if qb_pass["direction"] == other["direction"]:
                    notes.append({"kind": "good", "text": f"STACK: {qb_pass['name']} {qb_pass['direction'].upper()} passing with {other['name']} {other['direction'].upper()} {other['prop'].lower()}. Positively correlated."})
                else:
                    notes.append({"kind": "conflict", "text": f"CONFLICT: {qb_pass['name']} passing {qb_pass['direction'].upper()} but {other['name']} {other['prop'].lower()} {other['direction'].upper()}. They fight each other."})
            elif qb_pass and same_team and other["market"] == "rushyds" and qb_pass["direction"] == other["direction"] == "over":
                notes.append({"kind": "caution", "text": f"{qb_pass['name']} passing OVER and {other['name']} rushing OVER share one offense. They tend to trade volume."})
            elif same_team and a["market"] == b["market"] == "recyds" and a["direction"] == b["direction"] == "over":
                notes.append({"kind": "caution", "text": f"{a['name']} and {b['name']} both need the same QB to go off. Shared risk."})
    return notes


def _summarize(day: str, tk: dict, live: bool = True) -> dict:
    from odds import compute_parlay
    legs = tk.get("legs", [])
    stake = float(tk.get("stake") or WAGER)
    lg_cache: dict[str, dict] = {}
    out_legs = []
    for l in legs:
        L = dict(l)
        if live:
            gid = str(l["gameId"])
            if gid not in lg_cache:
                lg_cache[gid] = live_game(gid)
            L["live"] = leg_live(l, lg_cache[gid])
        out_legs.append(L)
    odds = [l["odds"] for l in legs if l.get("odds")]
    m = compute_parlay(odds, wager=stake, boost=BOOST) if odds else None
    p = math.prod(l.get("modelP") or 0.5 for l in legs) if legs else None
    return {"day": day, "stake": stake, "boost": BOOST, "legs": out_legs, "legCount": len(legs),
            "profitZoneLegs": sum(1 for l in legs if (l.get("modelP") or 0) >= 0.85),
            "combinedDecimal": m.combined_decimal if m else 1.0, "payout": m.payout if m else stake, "boostedPayout": m.boosted_payout if m else stake,
            "boostedAmerican": m.boosted_american if m else 0, "hitProbability": None if p is None else round(p, 4),
            "notes": _correlation(legs), "anyLive": any((l.get("live") or {}).get("state") in ("LIVE", "HALFTIME") for l in out_legs),
            "updated": tk.get("updated")}


def get_ticket(day: str, live: bool = True) -> dict:
    day = day if day in DAYS else "monday"
    with _FILE_LOCK:
        tk = _load().get(day, {"legs": []})
    return _summarize(day, tk, live)


def add_leg(player_id: str, market: str, direction: str, game_id: str | None = None, alt_line: float | None = None, day: str | None = None) -> dict:
    if market not in MARKET_LABEL:
        return {"ok": False, "error": "Touchdown and scorer props are not allowed on tickets."}
    if direction not in ("over", "under"):
        return {"ok": False, "error": "direction must be over or under"}
    a = analyze(player_id, market, game_id)
    if not a.get("ticketable"):
        return {"ok": False, "error": a.get("reason") or "This player cannot be added right now."}
    line, side = a["fd"]["line"], a["sides"][direction]
    price, p, est = side["price"], side["p"], False
    if alt_line is not None and abs(alt_line - line) > 1e-9:
        alt = next((x for x in a["alts"] if abs(x["line"] - alt_line) < 1e-9), None)
        if not alt:
            return {"ok": False, "error": "That alternate line is not on the ladder."}
        line, est = alt["line"], True
        price = alt["overAmerican"] if direction == "over" else alt["underAmerican"]
        p = alt["pOver"] if direction == "over" else alt["pUnder"]
    day = day if day in DAYS else (a.get("day") or "monday")
    leg = {"id": f"{player_id}:{market}", "playerId": player_id, "name": a["name"], "team": a["team"], "pos": a["pos"], "photoUrl": a["photoUrl"],
           "market": market, "prop": MARKET_LABEL[market], "direction": direction, "line": line, "odds": price, "oddsText": _fmt_am(price),
           "oddsEstimated": est, "book": a["fd"]["book"], "modelP": p, "confidence": round(p * 100, 1), "profitZone": p >= 0.85, "verdict": a["verdict"], "gameId": a["gameId"], "matchup": a["matchup"],
           "kickoff": a["kickoff"], "addedAt": dt.datetime.now(CT).isoformat(timespec="seconds")}
    with _FILE_LOCK:
        db = _load()
        tk = db.setdefault(day, {"legs": [], "stake": WAGER})
        tk["legs"] = [l for l in tk["legs"] if l["id"] != leg["id"]] + [leg]
        tk["updated"] = leg["addedAt"]
        _save(db)
    return {"ok": True, "day": day, "ticket": get_ticket(day)}


def _mutate(day: str, fn) -> dict:
    day = day if day in DAYS else "monday"
    with _FILE_LOCK:
        db = _load()
        tk = db.setdefault(day, {"legs": [], "stake": WAGER})
        fn(tk)
        tk["updated"] = dt.datetime.now(CT).isoformat(timespec="seconds")
        _save(db)
    return {"ok": True, "day": day, "ticket": get_ticket(day)}


def remove_leg(day: str, leg_id: str) -> dict:
    return _mutate(day, lambda tk: tk.update(legs=[l for l in tk["legs"] if l["id"] != leg_id]))


def clear_ticket(day: str) -> dict:
    return _mutate(day, lambda tk: tk.update(legs=[]))


def set_stake(day: str, stake: float) -> dict:
    return _mutate(day, lambda tk: tk.update(stake=max(1.0, min(float(stake), 10000.0))))

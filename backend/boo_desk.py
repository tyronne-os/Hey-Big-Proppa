"""
MY BOO's desk -- time awareness, matchup awareness and the scorecard.

She documents every slip, so she has to know, at any moment (Central time, New Orleans):
  * what time it is and what kind of day it is (prep day, game day, live, post-game recording)
  * which NFL and college games are on today, which are live or final, and what is next
  * which slips are riding on which game, and which are waiting to be recorded
  * how the logic is scoring: effort legs (yards, catches, totals) vs coach's-call legs (TDs)

Schedules and live status come from ESPN's public scoreboard (no key) for both NFL and FBS college
football. Slip grading itself still runs off the Tank01 box score (slip_alerts.py).
"""
from __future__ import annotations

import csv
import gzip
import json
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import myboo

CT = ZoneInfo("America/Chicago")
ESPN_TO_LAKE = {"WSH": "WAS", "LAR": "LA"}        # ESPN abbreviations that differ from the lake's
SEC_CONFERENCE_ID = "8"
TD_MARKETS = {"anytd", "firsttd", "lasttd"}
_cache: dict[str, tuple[float, list[dict]]] = {}

MARKET_NAME = {
    "rushyds": "Rushing yards", "recyds": "Receiving yards", "recs": "Receptions", "passyds": "Passing yards",
    "passtd": "Passing TDs", "nfl_total": "Game total", "nfl_ml": "Moneyline", "nfl_spread": "Spread",
    "kickpts": "Kicker points", "carries": "Carries",
}


# ---------------------------------------------------------------------------
# ESPN scoreboard (NFL + FBS)
# ---------------------------------------------------------------------------

def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw)


def _status(ev: dict) -> tuple[str, str]:
    st = ev.get("status", {}).get("type", {})
    name, state = st.get("name", ""), st.get("state", "")
    if st.get("completed") or state == "post":
        return "FINAL", st.get("shortDetail") or "Final"
    if "HALFTIME" in name:
        return "HALFTIME", "Halftime"
    if state == "in":
        return "LIVE", st.get("shortDetail") or "Live"
    return "PRE", ""


def _parse(ev: dict, league: str) -> dict:
    comp = ev["competitions"][0]
    kick = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(CT)
    status, detail = _status(ev)
    sides = {}
    for c in comp.get("competitors", []):
        rank = (c.get("curatedRank") or {}).get("current")
        sides[c["homeAway"]] = {
            "abbr": c["team"].get("abbreviation", ""), "name": c["team"].get("shortDisplayName") or c["team"].get("displayName", ""),
            "score": int(c["score"]) if str(c.get("score", "")).isdigit() else None,
            "rank": rank if rank and rank <= 25 else None,
            "sec": str(c["team"].get("conferenceId", "")) == SEC_CONFERENCE_ID,
        }
    odds = (comp.get("odds") or [{}])[0]
    away, home = sides.get("away", {}), sides.get("home", {})
    return {
        "league": league, "espnId": ev.get("id"), "label": f"{away.get('abbr')} @ {home.get('abbr')}",
        "kickoffCT": kick.strftime("%a %b %-d · %-I:%M %p CT"), "kickoffISO": kick.isoformat(), "dateCT": kick.date().isoformat(),
        "status": status, "detail": detail, "away": away, "home": home,
        "line": odds.get("details"), "total": odds.get("overUnder"),
        "ranked": bool(away.get("rank") or home.get("rank")), "sec": bool(away.get("sec") or home.get("sec")),
    }


def _day(league: str, day: datetime) -> list[dict]:
    """One day of games (ESPN only accepts a single date). Cached 60 s while live, 10 min otherwise."""
    key = f"{league}:{day:%Y%m%d}"
    hit = _cache.get(key)
    if hit and time.time() < hit[0]:
        return hit[1]
    path = "nfl" if league == "NFL" else "college-football"
    extra = "&groups=80" if league == "CFB" else ""          # 80 = FBS
    try:
        data = _fetch(f"https://site.api.espn.com/apis/site/v2/sports/football/{path}/scoreboard?dates={day:%Y%m%d}&limit=300{extra}")
        week = (data.get("week") or {}).get("number")
        games = [{**_parse(e, league), "week": week} for e in data.get("events", [])]
    except Exception:
        games = hit[1] if hit else []
    live = any(g["status"] in ("LIVE", "HALFTIME") for g in games)
    _cache[key] = (time.time() + (60 if live else 600), games)
    return games


def _games(league: str, start: datetime, days: int) -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    for i in range(days + 1):
        for g in _day(league, start + timedelta(days=i)):
            if g["espnId"] not in seen:
                seen.add(g["espnId"])
                games.append(g)
    return sorted(games, key=lambda g: g["kickoffISO"])


# ---------------------------------------------------------------------------
# the clock
# ---------------------------------------------------------------------------

def _league_view(league: str, now: datetime) -> dict:
    start = now - timedelta(days=1)                  # catch last night's late finals
    games = _games(league, start, 8)
    today = now.date().isoformat()
    todays = [g for g in games if g["dateCT"] == today]
    live = [g for g in games if g["status"] in ("LIVE", "HALFTIME")]
    upcoming = [g for g in games if g["status"] == "PRE"]
    nxt = upcoming[0] if upcoming else None
    days = [g["dateCT"] for g in upcoming]
    # college's real slate is Saturday; Thursday/Friday games are the appetizer
    sat = next((x for x in days if datetime.fromisoformat(x).weekday() == 5), None) if league == "CFB" else None
    slate_day = sat or (nxt["dateCT"] if nxt else None)
    slate = [g for g in upcoming if g["dateCT"] == slate_day] if slate_day else []
    view = {
        "week": (nxt or (games[-1] if games else {})).get("week"),
        "today": todays, "live": live, "next": nxt,
        "nextSlate": {"date": slate_day, "count": len(slate), "ranked": sum(g["ranked"] for g in slate),
                      "sec": sum(g["sec"] for g in slate),
                      "games": [g for g in slate if league == "NFL" or g["ranked"] or g["sec"]][:16]},
        "lastFinal": next((g for g in reversed(games) if g["status"] == "FINAL"), None),
    }
    return view


def _lake_id(g: dict) -> str:
    a, h = (ESPN_TO_LAKE.get(g[s]["abbr"], g[s]["abbr"]) for s in ("away", "home"))
    return f"{a}_{h}"


def _ticket_games(finals: set[str]) -> tuple[dict[str, dict], list[dict]]:
    """game_id -> {open, settled, real} for every game a ticket rides on, plus the slips waiting to record
    (still open although every game they ride on is final)."""
    tickets = {t["ticket_id"]: t for t in myboo.load_tickets_raw()}
    out: dict[str, dict] = {}
    try:
        with open(myboo._LEGS_FILE, newline="") as f:
            legs = list(csv.DictReader(f))
    except OSError:
        return out, []
    games_of: dict[str, set[str]] = defaultdict(set)
    for l in legs:
        if l.get("game_id") and l["ticket_id"] in tickets:
            games_of[l["ticket_id"]].add(l["game_id"])
    for tid, gids in games_of.items():
        st = tickets[tid]["status"]
        for gid in gids:
            row = out.setdefault(gid, {"gameId": gid, "label": gid.split("_", 2)[-1].replace("_", " @ ", 1), "open": 0, "settled": 0, "real": 0})
            row["open" if st in ("OPEN", "IN_PROGRESS") else "settled"] += 1
            row["real"] += tickets[tid]["order_type"] == "POW"
    waiting = [{"ticketId": tid, "name": tickets[tid]["name"], "games": sorted(gids)}
               for tid, gids in games_of.items()
               if tickets[tid]["status"] in ("OPEN", "IN_PROGRESS") and all(g.split("_", 2)[-1] in finals for g in gids)]
    return out, waiting


def clock() -> dict:
    now = datetime.now(CT)
    nfl, cfb = _league_view("NFL", now), _league_view("CFB", now)
    finals = {_lake_id(g) for g in _games("NFL", now - timedelta(days=6), 7) if g["status"] == "FINAL"}
    slips, waiting = _ticket_games(finals)
    live_n = len(nfl["live"]) + len(cfb["live"])
    open_n = sum(1 for t in myboo.load_tickets_raw() if t["status"] in ("OPEN", "IN_PROGRESS"))
    if live_n:
        mode, line = "LIVE", f"{live_n} game{'s' if live_n != 1 else ''} live. I am watching every slip and will ring when one is ready to record."
    elif waiting:
        mode, line = "RECORDING", f"{len(waiting)} slip{'s' if len(waiting) != 1 else ''} rode on games that are final and still need recording. Recording them now from the box score."
    elif nfl["today"] or cfb["today"]:
        mode, line = "GAME DAY", "Games on the board today. Theses are frozen when a slip is logged; I grade from the opening kick."
    else:
        nxt = min((g for g in (nfl["next"], cfb["next"]) if g), key=lambda g: g["kickoffISO"], default=None)
        mode = "PREP DAY"
        line = (f"No games today. Next up: {nxt['label']} ({'NFL' if nxt['league'] == 'NFL' else 'college'}), {nxt['kickoffCT']}."
                if nxt else "No games on the board this week.")
    return {
        "nowCT": now.isoformat(), "display": now.strftime("%a %b %-d · %-I:%M %p CT"), "weekday": now.strftime("%A"),
        "mode": mode, "line": line, "nfl": nfl, "cfb": cfb,
        "slips": {"open": open_n, "waitingToRecord": waiting, "byGame": sorted(slips.values(), key=lambda r: r["gameId"])},
    }


# ---------------------------------------------------------------------------
# scorecard -- how the logic is actually doing, leg by leg
# ---------------------------------------------------------------------------

def scorecard(game_id: str | None = None, week: int | None = None) -> dict:
    tickets = {t["ticket_id"]: t for t in myboo.load_tickets_raw()}
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = [l for l in csv.DictReader(f) if l["status"] in ("HIT", "MISS") and l["ticket_id"] in tickets]
    if game_id:
        legs = [l for l in legs if l["game_id"] == game_id]
    if week:
        legs = [l for l in legs if str(tickets[l["ticket_id"]]["week"]) == str(week)]
    out = {}
    for kind, label in (("POW", "REAL MONEY"), ("SIM", "BIG PROPPA BOARD (PAPER)")):
        mine = [l for l in legs if tickets[l["ticket_id"]]["order_type"] == kind]
        groups: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        effort, td = [0, 0], [0, 0]
        for l in mine:
            hit = l["status"] == "HIT"
            if l["market"] in TD_MARKETS:
                td[0] += hit; td[1] += 1
                key = "Touchdown scorer (coach's call)"
            else:
                effort[0] += hit; effort[1] += 1
                key = f"{MARKET_NAME.get(l['market'], l['market'])} {l['direction']}"
            groups[key][0] += hit; groups[key][1] += 1
        tix = {l["ticket_id"] for l in mine}
        settled = [tickets[t] for t in tix if tickets[t]["status"] in ("SETTLED_WIN", "SETTLED_LOSS")]
        td_killed = 0
        for t in settled:
            misses = [l for l in mine if l["ticket_id"] == t["ticket_id"] and l["status"] == "MISS"]
            if t["status"] == "SETTLED_LOSS" and misses and all(l["market"] in TD_MARKETS for l in misses):
                td_killed += 1
        staked = sum(float(t["stake_units"] or 0) for t in settled)
        returned = sum(float(t["result_units"] or 0) for t in settled)
        out[kind] = {
            "label": label, "slips": len(settled), "won": sum(t["status"] == "SETTLED_WIN" for t in settled),
            "staked": round(staked, 2), "returned": round(returned, 2), "net": round(returned - staked, 2),
            "effort": {"hit": effort[0], "total": effort[1]}, "td": {"hit": td[0], "total": td[1]},
            "killedOnlyByTd": td_killed,
            "markets": [{"market": k, "hit": h, "total": n} for k, (h, n) in sorted(groups.items(), key=lambda kv: -kv[1][1])],
        }
    pow_, sim = out["POW"], out["SIM"]
    pct = lambda d: f"{round(100 * d['hit'] / d['total'])}%" if d["total"] else "n/a"   # noqa: E731
    headline = (f"Effort legs: {pow_['effort']['hit']}/{pow_['effort']['total']} on real money ({pct(pow_['effort'])}), "
                f"{sim['effort']['hit']}/{sim['effort']['total']} on the board ({pct(sim['effort'])}). "
                f"Touchdown legs: {pow_['td']['hit']}/{pow_['td']['total']} real, {sim['td']['hit']}/{sim['td']['total']} board. "
                f"{pow_['killedOnlyByTd'] + sim['killedOnlyByTd']} losing slips died only on a TD leg.")
    return {"gameId": game_id, "week": week, "headline": headline, **out}

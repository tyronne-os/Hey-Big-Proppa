"""
THE ODDS pond -- Vegas lines for every game on the board, kept in the lake.

Two gold tables (lake/gold/nfl/):

  odds_line_history   append-only. One row per (league, game, book) each time that
                      book's spread / total / moneyline CHANGED. The first row a game
                      ever gets is its "open" as far as this lake knows.
  odds_board          current state, one row per game: consensus + FanDuel lines,
                      the open, the moves since open, last change time.

Sources
  NFL   Tank01 getNFLBettingOdds (8 books per game) + getNFLGamesForDate (kickoff).
        Consensus = median across books; FanDuel kept separately.
  CFB   CFBD lines for ranked (Top 25) games via cfb_jimmy.cfb_game_slate().
        Tank01's key does not include the college API.

Refresh is lazy: a request refreshes if the pond is older than TTL_SECONDS.
Nothing here is a model. The watch tool (watch()) is the only place the Big Proppa
Line touches this pond, and it only reads it.
"""
from __future__ import annotations

import csv
import math
import statistics
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import bpl
import data
import tank01

GOLD = data.GOLD
BOARD = GOLD / "odds_board.csv"
HISTORY = GOLD / "odds_line_history.csv"
INDEX = GOLD / "_index.csv"
ET = ZoneInfo("America/New_York")
TTL_SECONDS = 600

BOARD_COLS = ["league", "game_id", "game_date", "game_time_et", "kickoff_epoch", "away", "home", "away_name", "home_name",
              "away_rank", "home_rank", "books", "spread_home", "total", "ml_home", "ml_away",
              "fd_spread_home", "fd_total", "fd_ml_home", "fd_ml_away",
              "open_spread_home", "open_total", "open_ml_home", "spread_move", "total_move",
              "last_change_utc", "updated_at_utc", "source"]
HISTORY_COLS = ["league", "game_id", "snapshot_at_utc", "book", "spread_home", "total", "ml_home", "ml_away"]
MARKETS = ("spread_home", "total", "ml_home", "ml_away")

_lock = threading.Lock()
_last_refresh: dict[str, float] = {}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _half(x: float | None) -> float | None:
    return None if x is None else round(x * 2) / 2


def _fmt(v: float | None) -> str:
    return "" if v is None else f"{v:g}"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def _display_name(full: str) -> str:
    return full.replace("Los Angeles", "LA").replace("New York", "NY")


# Tank01's odds endpoint says LAR / WSH where its games endpoint (and the lake) say LA / WAS.
_ALIAS = {"LAR": "LA", "WSH": "WAS"}


@lru_cache(maxsize=1)
def _teams() -> dict[str, dict]:
    """Tank01 abbreviation (either spelling) -> {lake, name}."""
    out = {r["abbr_tank01"]: {"lake": r["abbr_lake"], "name": _display_name(r["full_name"])} for r in data.load("team_abbr_map")}
    for alias, canon in _ALIAS.items():
        out[alias] = out[canon]
    return out


def _canon(abbr: str) -> str:
    return _ALIAS.get(abbr, abbr)


def _et_time(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, ET).strftime("%-I:%M %p")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# refresh -- NFL (Tank01)
# ---------------------------------------------------------------------------

def _nfl_dates() -> list[str]:
    """Game dates (YYYYMMDD) of the next slate still to be played, from the lake schedule."""
    today = datetime.now(ET).date().isoformat()
    rows = [r for r in data.load("schedule") if r.get("game_type") == "REG" and r.get("game_date", "") >= today
            and r.get("home_score") in ("", None)]
    if not rows:
        return []
    week = min(int(r["week"]) for r in rows)
    return sorted({r["game_date"].replace("-", "") for r in rows if int(r["week"]) == week})


def _consensus(books: dict[str, dict]) -> dict:
    def med(key):
        vals = [v for v in (_f(b.get(key)) for b in books.values()) if v is not None]
        return statistics.median(vals) if vals else None

    return {"spread_home": _half(med("homeTeamSpread")), "total": _half(med("totalOver")),
            "ml_home": None if med("homeTeamML") is None else round(med("homeTeamML")),
            "ml_away": None if med("awayTeamML") is None else round(med("awayTeamML"))}


def _book_line(b: dict | None) -> dict:
    if not b:
        return {k: None for k in MARKETS}
    return {"spread_home": _f(b.get("homeTeamSpread")), "total": _f(b.get("totalOver")),
            "ml_home": _f(b.get("homeTeamML")), "ml_away": _f(b.get("awayTeamML"))}


def _nfl_snapshots() -> list[dict]:
    teams = _teams()
    out = []
    for d in _nfl_dates():
        odds = (tank01._get("getNFLBettingOdds", {"gameDate": d}, ttl=TTL_SECONDS) or {}).get("body") or {}
        games = {f"{d}_{_canon(g.get('away', ''))}@{_canon(g.get('home', ''))}": g
                 for g in ((tank01._get("getNFLGamesForDate", {"gameDate": d}, ttl=3600) or {}).get("body") or [])}
        for gid, g in odds.items():
            if not isinstance(g, dict):
                continue
            books = {k: v for k, v in g.items() if isinstance(v, dict)}
            if not books:
                continue
            away, home = teams.get(g.get("awayTeam"), {}), teams.get(g.get("homeTeam"), {})
            epoch = _f((games.get(f"{d}_{_canon(g.get('awayTeam', ''))}@{_canon(g.get('homeTeam', ''))}") or {}).get("gameTime_epoch"))
            out.append({
                "league": "nfl", "game_id": gid, "game_date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                "kickoff_epoch": epoch, "game_time_et": _et_time(epoch) if epoch else "",
                "away": _canon(g.get("awayTeam", "")), "home": _canon(g.get("homeTeam", "")),
                "away_name": away.get("name", g.get("awayTeam", "")), "home_name": home.get("name", g.get("homeTeam", "")),
                "away_rank": None, "home_rank": None, "books": len(books),
                "consensus": _consensus(books), "fanduel": _book_line(books.get("fanduel")),
                "source": "tank01", "updated_epoch": _f(g.get("last_updated_e_time")),
            })
    return out


# ---------------------------------------------------------------------------
# refresh -- College Top 25 (CFBD lines)
# ---------------------------------------------------------------------------

def _cfb_time_et(start_date: str, cst_text: str) -> tuple[float | None, str]:
    """cfb_jimmy times are fixed CST (UTC-6, no daylight saving), e.g. '5:00 PM CST' -> epoch + ET label."""
    try:
        naive = datetime.strptime(f"{start_date} {cst_text.replace(' CST', '').strip()}", "%Y-%m-%d %I:%M %p")
    except ValueError:
        return None, cst_text
    epoch = naive.replace(tzinfo=timezone(timedelta(hours=-6))).timestamp()
    return epoch, _et_time(epoch)


def _cfb_snapshots() -> list[dict]:
    import cfb_jimmy
    slate = cfb_jimmy.cfb_game_slate() or cfb_jimmy.cfb_game_slate()
    out = []
    for g in slate:
        if g.get("spread") is None and not g.get("total"):
            continue
        home_fav = g["favorite"] == g["home"]
        spread_home = g["spread"] if home_fav else (-g["spread"] if g["spread"] is not None else None)
        fav_ml, dog_ml = g.get("favMl"), g.get("dogMl")
        ml_home, ml_away = (fav_ml, dog_ml) if home_fav else (dog_ml, fav_ml)
        epoch, label = _cfb_time_et(g.get("startDate", ""), g.get("gameTime", ""))
        line = {"spread_home": spread_home, "total": g.get("total"), "ml_home": ml_home, "ml_away": ml_away}
        out.append({
            "league": "cfb", "game_id": str(g["gameId"]), "game_date": g.get("startDate", ""),
            "kickoff_epoch": epoch, "game_time_et": label, "away": g["away"], "home": g["home"],
            "away_name": g["away"], "home_name": g["home"], "away_rank": g.get("awayRank"), "home_rank": g.get("homeRank"),
            "books": 1, "consensus": line, "fanduel": {k: None for k in MARKETS},
            "source": f"cfbd/{g.get('provider', '')}".rstrip("/"), "updated_epoch": None,
        })
    return out


# ---------------------------------------------------------------------------
# pond writes
# ---------------------------------------------------------------------------

def _apply(league: str, snaps: list[dict]) -> None:
    now = _now_utc()
    history = _read(HISTORY)
    latest: dict[tuple, dict] = {}
    for r in history:
        latest[(r["league"], r["game_id"], r["book"])] = r
    new_rows = []
    for s in snaps:
        for book, line in (("consensus", s["consensus"]), ("fanduel", s["fanduel"])):
            if all(line[k] is None for k in MARKETS):
                continue
            prev = latest.get((league, s["game_id"], book))
            cur = {k: _fmt(line[k]) for k in MARKETS}
            if prev and all(prev[k] == cur[k] for k in MARKETS):
                continue
            row = {"league": league, "game_id": s["game_id"], "snapshot_at_utc": now, "book": book, **cur}
            new_rows.append(row)
            latest[(league, s["game_id"], book)] = row
    if new_rows:
        history.extend(new_rows)
        _write(HISTORY, HISTORY_COLS, history)

    opens: dict[str, dict] = {}
    changes: dict[str, str] = {}
    for r in history:
        if r["league"] == league and r["book"] == "consensus":
            opens.setdefault(r["game_id"], r)
            changes[r["game_id"]] = r["snapshot_at_utc"]

    board = [r for r in _read(BOARD) if r["league"] != league]
    for s in snaps:
        c, fd, op = s["consensus"], s["fanduel"], opens.get(s["game_id"], {})
        o_spread, o_total, o_ml = _f(op.get("spread_home")), _f(op.get("total")), _f(op.get("ml_home"))
        board.append({
            "league": league, "game_id": s["game_id"], "game_date": s["game_date"], "game_time_et": s["game_time_et"],
            "kickoff_epoch": "" if s["kickoff_epoch"] is None else int(s["kickoff_epoch"]),
            "away": s["away"], "home": s["home"], "away_name": s["away_name"], "home_name": s["home_name"],
            "away_rank": s["away_rank"] or "", "home_rank": s["home_rank"] or "", "books": s["books"],
            "spread_home": _fmt(c["spread_home"]), "total": _fmt(c["total"]), "ml_home": _fmt(c["ml_home"]), "ml_away": _fmt(c["ml_away"]),
            "fd_spread_home": _fmt(fd["spread_home"]), "fd_total": _fmt(fd["total"]), "fd_ml_home": _fmt(fd["ml_home"]), "fd_ml_away": _fmt(fd["ml_away"]),
            "open_spread_home": _fmt(o_spread), "open_total": _fmt(o_total), "open_ml_home": _fmt(o_ml),
            "spread_move": _fmt(None if c["spread_home"] is None or o_spread is None else round(c["spread_home"] - o_spread, 2)),
            "total_move": _fmt(None if c["total"] is None or o_total is None else round(c["total"] - o_total, 2)),
            "last_change_utc": changes.get(s["game_id"], now), "updated_at_utc": now, "source": s["source"],
        })
    _write(BOARD, BOARD_COLS, board)
    _touch_index(len(board), len(history), now)


def _touch_index(board_rows: int, history_rows: int, now: str) -> None:
    rows = _read(INDEX)
    if not rows:
        return
    cols = list(rows[0].keys())
    for r in rows:
        if r["chart_name"] == "odds_board":
            r["row_count"], r["last_exported_at_utc"], r["status"] = board_rows, now, "ok"
        elif r["chart_name"] == "odds_line_history":
            r["row_count"], r["last_exported_at_utc"], r["status"] = history_rows, now, "ok"
    _write(INDEX, cols, rows)


def refresh(league: str, force: bool = False) -> None:
    with _lock:
        if not force and time.time() - _last_refresh.get(league, 0) < TTL_SECONDS:
            return
        snaps = _nfl_snapshots() if league == "nfl" else _cfb_snapshots() if league == "cfb" else []
        _last_refresh[league] = time.time()
        if snaps:
            _apply(league, snaps)


# ---------------------------------------------------------------------------
# read side: board, sidebar lists, watch
# ---------------------------------------------------------------------------

def _cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# CFB sd: measured on the 2024-25 backtest (scripts/build_bpl_cfb_calibration.py).
# NFL sd 13.5: the NFL team-points backtest error is 7.57 (bpl.py), which for a two-team total
# or margin is about 1.25 * 7.57 * sqrt(2) = 13.4. Not measured on game totals directly.
SIGMA = {"nfl": 13.5, "cfb": 16.6}
# Vegas is sharper than a model fed two games of this season, so only half of the model's gap
# from 50% is trusted. Money play = 60%+ after that (about 70% raw); watch = 54%+.
TRUST = 0.5
MONEY_P, WATCH_P, WATCH_MOVE = 0.60, 0.54, 2.0
MAX_SPREAD = 21.0   # beyond this the model's margin tails are not calibrated, so no spread pick


def _model(league: str, g: dict) -> dict | None:
    if league == "cfb":
        m = bpl.cfb_game_total(g["home"], g["away"])
        return m and {"home": m["homePoints"], "away": m["awayPoints"]}
    home, away = _teams().get(g["home"], {}).get("lake"), _teams().get(g["away"], {}).get("lake")
    for t in bpl.nfl_game_totals():
        if t["home"] == home and t["away"] == away:
            return {"home": t["homePoints"], "away": t["awayPoints"]}
    return None


def _watch_one(league: str, g: dict, model: dict | None) -> dict:
    spread, total = _f(g["spread_home"]), _f(g["total"])
    sm, tm = _f(g["spread_move"]) or 0.0, _f(g["total_move"]) or 0.0
    picks = []
    if model:
        sd = SIGMA[league]
        margin_mu, total_mu = model["home"] - model["away"], model["home"] + model["away"]
        if total is not None:
            p_over = 1 - _cdf((total - total_mu) / sd)
            picks += [(p_over, f"OVER {total:g}", f"Big Proppa total {total_mu:.1f} vs Vegas {total:g}"),
                      (1 - p_over, f"UNDER {total:g}", f"Big Proppa total {total_mu:.1f} vs Vegas {total:g}")]
        if spread is not None and abs(spread) <= MAX_SPREAD:
            p_home = _cdf((margin_mu + spread) / sd)
            picks += [(p_home, f"{g['home_name']} {spread:+g}", f"Big Proppa margin {g['home']} {margin_mu:+.1f} vs Vegas {spread:+g}"),
                      (1 - p_home, f"{g['away_name']} {-spread:+g}", f"Big Proppa margin {g['home']} {margin_mu:+.1f} vs Vegas {spread:+g}")]
    picks = [(0.5 + (p - 0.5) * TRUST, name, why, p) for p, name, why in picks]
    best = max(picks, key=lambda p: p[0]) if picks else None
    reasons = []
    level = None
    if best and best[0] >= MONEY_P:
        level = "money"
    elif (best and best[0] >= WATCH_P) or abs(sm) >= WATCH_MOVE or abs(tm) >= WATCH_MOVE:
        level = "watch"
    if best and best[0] >= WATCH_P:
        reasons.append(f"{best[1]}: {best[3]:.0%} on the Big Proppa Line ({best[0]:.0%} trusting Vegas half). {best[2]}")
    if abs(tm) >= WATCH_MOVE:
        reasons.append(f"Total moved {tm:+g} since open")
    if abs(sm) >= WATCH_MOVE:
        reasons.append(f"Spread moved {sm:+g} since open")
    return {"level": level, "pick": best[1] if best else None, "probability": round(best[0], 3) if best else None,
            "reasons": reasons}


def _num(v: str):
    f = _f(v)
    return None if f is None else (int(f) if f == int(f) and abs(f) >= 100 else f)


def board(league: str) -> dict:
    refresh(league)
    now = time.time()
    rows = [r for r in _read(BOARD) if r["league"] == league]
    games = []
    for r in sorted(rows, key=lambda r: (_f(r["kickoff_epoch"]) or 9e12, r["game_id"])):
        epoch = _f(r["kickoff_epoch"])
        g = {
            "id": r["game_id"], "date": r["game_date"], "time": r["game_time_et"], "epoch": epoch,
            "started": bool(epoch and epoch < now),
            "away": r["away"], "home": r["home"], "awayName": r["away_name"], "homeName": r["home_name"],
            "awayRank": int(_f(r["away_rank"])) if _f(r["away_rank"]) else None, "homeRank": int(_f(r["home_rank"])) if _f(r["home_rank"]) else None, "books": _num(r["books"]),
            "spreadHome": _f(r["spread_home"]), "total": _f(r["total"]), "mlHome": _num(r["ml_home"]), "mlAway": _num(r["ml_away"]),
            "fd": {"spreadHome": _f(r["fd_spread_home"]), "total": _f(r["fd_total"]), "mlHome": _num(r["fd_ml_home"]), "mlAway": _num(r["fd_ml_away"])},
            "openSpreadHome": _f(r["open_spread_home"]), "openTotal": _f(r["open_total"]),
            "spreadMove": _f(r["spread_move"]) or 0.0, "totalMove": _f(r["total_move"]) or 0.0,
            "lastChange": r["last_change_utc"], "source": r["source"],
        }
        g["watch"] = _watch_one(league, r, _model(league, {"home": r["home"], "away": r["away"]}))
        if g["started"]:
            g["watch"]["level"] = None  # nothing left to bet once a game has kicked off
        games.append(g)
    return {"league": league, "games": games, "sidebar": _sidebar(games),
            "updatedAt": max((r["updated_at_utc"] for r in rows), default=None),
            "trackingSince": min((h["snapshot_at_utc"] for h in _read(HISTORY) if h["league"] == league), default=None)}


def _label(g: dict) -> str:
    return f"{g['awayName']} at {g['homeName']}"


def _sidebar(games: list[dict]) -> dict:
    live = [g for g in games if not g["started"]] or games
    moves = []
    for g in live:
        if g["spreadMove"]:
            moves.append({"game": _label(g), "market": "Spread", "value": abs(g["spreadMove"]), "signed": g["spreadMove"]})
        if g["totalMove"]:
            moves.append({"game": _label(g), "market": "Total", "value": abs(g["totalMove"]), "signed": g["totalMove"]})
    moves.sort(key=lambda m: -m["value"])

    def fav(g):  # favorite's spread as a negative number
        return -abs(g["spreadHome"]) if g["spreadHome"] is not None else None

    spreads = [g for g in live if g["spreadHome"] is not None]
    totals = [g for g in live if g["total"] is not None]
    entry = lambda g, v: {"game": _label(g), "value": v}
    recent = _recent_changes(games)
    return {
        "moves": moves[:10],
        "recent": recent,
        "biggestSpreads": [entry(g, fav(g)) for g in sorted(spreads, key=lambda g: -abs(g["spreadHome"]))[:5]],
        "smallestSpreads": [entry(g, fav(g)) for g in sorted(spreads, key=lambda g: abs(g["spreadHome"]))[:5]],
        "highestTotals": [entry(g, g["total"]) for g in sorted(totals, key=lambda g: -g["total"])[:5]],
        "lowestTotals": [entry(g, g["total"]) for g in sorted(totals, key=lambda g: g["total"])[:5]],
    }


def _recent_changes(games: list[dict]) -> list[dict]:
    by_id = {g["id"]: g for g in games}
    prev: dict[str, dict] = {}
    out = []
    for h in _read(HISTORY):
        if h["book"] != "consensus" or h["game_id"] not in by_id:
            continue
        p = prev.get(h["game_id"])
        if p:
            when = datetime.fromisoformat(h["snapshot_at_utc"]).astimezone(ET).strftime("%-I:%M%p")
            for key, name in (("spread_home", "Spread"), ("total", "Total")):
                if p[key] != h[key]:
                    out.append({"game": _label(by_id[h["game_id"]]), "market": name, "at": when, "epoch": h["snapshot_at_utc"],
                                "from": _f(p[key]), "to": _f(h[key])})
        prev[h["game_id"]] = h
    return sorted(out, key=lambda r: r["epoch"], reverse=True)[:8]

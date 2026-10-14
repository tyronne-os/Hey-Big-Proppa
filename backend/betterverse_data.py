"""
BETTER-VERSE: the weekly betting menu.

For every regular-season week of 2024/2025 this builds every market a bettor could have clicked on Friday,
already graded against what really happened:

  game markets   spread / moneyline / total, with the real closing odds from schedule.csv
  player props   pass yds, pass TDs, completions, attempts, INTs, rush yds, rec yds, receptions,
                 rush+rec yds, anytime TD

Prop lines use only games played before that week: median of the last six x a per-market shade "k" fitted
once on the 2023 season (out of sample) so overs land near the real-world ~48%, set at the nearest half point,
priced at -115 each side. Anytime TD is priced from the player's prior scoring rate plus book margin.
"""
from __future__ import annotations

import csv
import io
import math
import statistics
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path

_GOLD = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"
CACHE = _GOLD / "betterverse_cache"
URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv"
KEEP = ("player_id", "player_display_name", "position", "week", "team", "opponent_team",
        "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
        "carries", "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds")
SKILL = {"QB", "RB", "WR", "TE"}
SEASONS = (2024, 2025)
PROP_DEC = 1 + 100 / 115            # -115
_LOCK = threading.Lock()

PROPS = {
    "pass_yds":     {"pos": {"QB"},             "floor": 150, "k": 1.00, "label": "Pass Yds"},
    "pass_tds":     {"pos": {"QB"},             "floor": 0.6, "k": 1.00, "label": "Pass TDs"},
    "completions":  {"pos": {"QB"},             "floor": 12,  "k": 1.00, "label": "Completions"},
    "pass_att":     {"pos": {"QB"},             "floor": 20,  "k": 1.01, "label": "Pass Att"},
    "ints":         {"pos": {"QB"},             "floor": 0,   "k": 1.00, "label": "INTs", "fixed": 0.5},
    "rush_yds":     {"pos": {"RB", "QB"},       "floor": 25,  "k": 0.98, "label": "Rush Yds"},
    "rec_yds":      {"pos": {"WR", "TE", "RB"}, "floor": 20,  "k": 0.93, "label": "Rec Yds"},
    "receptions":   {"pos": {"WR", "TE", "RB"}, "floor": 2,   "k": 0.95, "label": "Receptions"},
    "rush_rec_yds": {"pos": {"RB"},             "floor": 40,  "k": 0.98, "label": "Rush+Rec Yds"},
}
TD_LABEL = "Anytime TD"
GAME_MARKETS = ("spread", "ml", "total")
ALL_MARKETS = GAME_MARKETS + tuple(PROPS) + ("anytime_td",)


def _n(v) -> float:
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def stat(row: dict, market: str) -> float:
    if market == "pass_yds":
        return _n(row["passing_yards"])
    if market == "pass_tds":
        return _n(row["passing_tds"])
    if market == "completions":
        return _n(row["completions"])
    if market == "pass_att":
        return _n(row["attempts"])
    if market == "ints":
        return _n(row["passing_interceptions"])
    if market == "rush_yds":
        return _n(row["rushing_yards"])
    if market == "rec_yds":
        return _n(row["receiving_yards"])
    if market == "receptions":
        return _n(row["receptions"])
    if market == "rush_rec_yds":
        return _n(row["rushing_yards"]) + _n(row["receiving_yards"])
    if market == "anytime_td":
        return _n(row["rushing_tds"]) + _n(row["receiving_tds"])
    raise KeyError(market)


def american_to_dec(a, default: float = -110) -> float:
    a = _n(a) or default
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


# --------------------------------------------------------------------------- player stats
def _path(year: int) -> Path:
    return CACHE / f"stats_{year}.csv"


def _download(year: int) -> None:
    req = urllib.request.Request(URL.format(year=year), headers={"User-Agent": "big-proppa-betterverse/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        text = r.read().decode("utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=KEEP)
    w.writeheader()
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("season_type") == "REG" and row.get("position") in SKILL:
            w.writerow({k: row.get(k, "") for k in KEEP})
    tmp = _path(year).with_suffix(".tmp")
    tmp.write_text(out.getvalue())
    tmp.replace(_path(year))


@lru_cache(maxsize=4)
def stats(year: int) -> dict:
    """{"games": {(pid, week): row}, "weeks": {pid: [weeks]}, "players": {pid: meta}}"""
    with _LOCK:
        if not _path(year).exists():
            _download(year)
    games, weeks, players = {}, {}, {}
    with _path(year).open(newline="") as fh:
        for row in csv.DictReader(fh):
            pid, wk = row["player_id"], int(row["week"])
            games[(pid, wk)] = row
            weeks.setdefault(pid, []).append(wk)
            players[pid] = {"name": row["player_display_name"], "pos": row["position"]}
    for w in weeks.values():
        w.sort()
    return {"games": games, "weeks": weeks, "players": players}


def _prior_rows(year: int, pid: str, week: int, n: int) -> list[dict]:
    cur = stats(year)
    rows = [cur["games"][(pid, w)] for w in cur["weeks"].get(pid, []) if w < week]
    if len(rows) < n and year - 1 >= 2023:
        prev = stats(year - 1)
        rows = [prev["games"][(pid, w)] for w in prev["weeks"].get(pid, [])] + rows
    return rows[-n:]


def _has_role(row: dict) -> bool:
    pos = row["position"]
    if pos == "QB":
        return _n(row["attempts"]) >= 15
    if pos == "RB":
        return _n(row["carries"]) >= 6 or _n(row["targets"]) >= 3
    return _n(row["targets"]) >= 3


# --------------------------------------------------------------------------- schedule
@lru_cache(maxsize=1)
def schedule() -> list[dict]:
    with (_GOLD / "schedule.csv").open(newline="") as fh:
        return [r for r in csv.DictReader(fh)
                if r["game_type"] == "REG" and int(r["season"]) in SEASONS and r["home_score"] != ""]


def weeks(year: int) -> list[int]:
    return sorted({int(g["week"]) for g in schedule() if int(g["season"]) == year})


# --------------------------------------------------------------------------- menu
@lru_cache(maxsize=64)
def menu(year: int, week: int) -> tuple[dict, ...]:
    """Every market on the Friday board for that week, graded. hit: 1 win, 0 loss, None void/push."""
    items: list[dict] = []
    team_game: dict[str, tuple[str, str, bool]] = {}

    for g in schedule():
        if int(g["season"]) != year or int(g["week"]) != week:
            continue
        gid, home, away = g["game_id"], g["home_team"], g["away_team"]
        team_game[home] = (gid, away, True)
        team_game[away] = (gid, home, False)
        margin = _n(g["home_score"]) - _n(g["away_score"])      # home perspective
        total = _n(g["home_score"]) + _n(g["away_score"])
        spread = _n(g["spread_line"])                            # home expected margin (+ = home favored)
        home_fav = spread > 0 or (spread == 0 and _n(g["home_moneyline"]) < _n(g["away_moneyline"]))

        # spread: home -spread vs away +spread
        for side, team, is_home in (("home", home, True), ("away", away, False)):
            m = margin if is_home else -margin
            line = -spread if is_home else spread             # bettor's handicap, e.g. -3.5
            res = m + line
            fav = home_fav == is_home
            items.append(dict(market="spread", game_id=gid, team=team, player_id="", player="",
                              side="fav" if fav else "dog", line=line,
                              dec=american_to_dec(g["home_spread_odds" if is_home else "away_spread_odds"]),
                              hit=None if res == 0 else int(res > 0), actual=m, pop=0.62 if fav else 0.38))
            ml = _n(g["home_moneyline" if is_home else "away_moneyline"])
            if ml:
                items.append(dict(market="ml", game_id=gid, team=team, player_id="", player="",
                                  side="fav" if fav else "dog", line=0.0, dec=american_to_dec(ml),
                                  hit=None if margin == 0 else int(m > 0), actual=m, pop=0.7 if fav else 0.3))
        tl = _n(g["total_line"])
        if tl:
            for side, odds in (("over", g["over_odds"]), ("under", g["under_odds"])):
                res = (total - tl) if side == "over" else (tl - total)
                items.append(dict(market="total", game_id=gid, team=f"{away}@{home}", player_id="", player="",
                                  side=side, line=tl, dec=american_to_dec(odds),
                                  hit=None if res == 0 else int(res > 0), actual=total,
                                  pop=0.65 if side == "over" else 0.35))

    cur = stats(year)
    for pid, meta in cur["players"].items():
        prior = _prior_rows(year, pid, week, 8)
        if len(prior) < 3 or not _has_role(prior[-1]):
            continue
        cur_weeks = [w for w in cur["weeks"].get(pid, []) if w < week]
        if week > 2 and (not cur_weeks or cur_weeks[-1] < week - 2):
            continue
        team = prior[-1]["team"]
        if cur_weeks:
            team = cur["games"][(pid, cur_weeks[-1])]["team"]
        if team not in team_game:
            continue                                          # bye week
        gid, opp, _ = team_game[team]
        row = cur["games"].get((pid, week))                   # None -> did not play -> void
        last6 = prior[-6:]
        for mk, spec in PROPS.items():
            if meta["pos"] not in spec["pos"]:
                continue
            vals = [stat(r, mk) for r in last6]
            med = statistics.median(vals)
            if med < spec["floor"]:
                continue
            line = spec.get("fixed", round(med * spec["k"] - 0.5) + 0.5)
            act = None if row is None else stat(row, mk)
            for side in ("over", "under"):
                hit = None if act is None else int(act > line if side == "over" else act < line)
                items.append(dict(market=mk, game_id=gid, team=team, player_id=pid, player=meta["name"],
                                  side=side, line=line, dec=PROP_DEC, hit=hit, actual=act,
                                  pop=min(1.0, med / max(spec["floor"], 1) / 4) * (1.0 if side == "over" else 0.45)))
        td_games = sum(stat(r, "anytime_td") > 0 for r in prior)
        p = (td_games + 1.0) / (len(prior) + 4.0)
        if meta["pos"] != "QB" and p >= 0.12:
            dec = max(1.4, min(10.0, 1 / min(0.85, p * 1.10)))
            act = None if row is None else stat(row, "anytime_td")
            items.append(dict(market="anytime_td", game_id=gid, team=team, player_id=pid, player=meta["name"],
                              side="yes", line=0.5, dec=round(dec, 3),
                              hit=None if act is None else int(act > 0), actual=act, pop=min(1.0, p * 1.8)))

    for i, it in enumerate(items):
        it["mid"] = f"{year}-{week:02d}-{i}"
        it["dec"] = round(float(it["dec"]), 4)
    return tuple(items)


def preload(year: int) -> None:
    stats(year)
    stats(year - 1)
    for w in weeks(year):
        menu(year, w)

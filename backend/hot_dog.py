"""
HOT DOG INDICATOR -- is this underdog dangerous?

The underdog is the sportsbook underdog (vig-removed moneyline below 50%).
Its last 5 games before the matchup are compared with the favorite's last 5
(reaching into last season when this one has fewer), on five stats:

  win %                 higher wins
  opponent scoring      points allowed per game, lower wins
  3rd-down %            conversions / attempts, higher wins
  turnover %            (INTs + fumbles lost) / drives, lower wins
  defense rank          the heat map's defensive profile ranked 1-32, lower wins

A CERTIFIED HOT DOG wins at least 3 of the 5 AND has a winning record (W > L).
A team without 5 prior games in the pond (2023+) can't be certified.

scripts/backtest_hot_dogs.py runs this rule over 2023-2025 (hot_dog_history.csv
is the pond, hot_dog_backtest.csv the results) and picks the bet -- moneyline
or spread -- that certified dogs hit more often.
"""
from __future__ import annotations

from functools import lru_cache

import data
import matchup

WINDOW = 5
MIN_STATS_WON = 3

# (key, label, better) -- better is +1 when higher is better for the team, -1 when lower is.
STATS = [
    ("win_pct", "Win %", 1),
    ("opp_ppg", "Opp points / game", -1),
    ("third_down_pct", "3rd-down %", 1),
    ("turnover_pct", "Turnovers / drive", -1),
    ("def_rank", "Defense rank", -1),
]
defense_ranks = matchup.defense_ranks  # moved to matchup.py -- shared with the heat map's OFF/DEF rank display


def window_stats(rows: list[dict], team: str, season: int, week: int, n: int = WINDOW) -> dict | None:
    """The team's last n games strictly before (season, week), across seasons in the pond."""
    prior = sorted((g for g in rows if g["team"] == team and (g["season"], g["week"]) < (season, week)),
                   key=lambda g: (g["season"], g["week"]))[-n:]
    if len(prior) < n:
        return None
    att = sum(g["third_down_att"] for g in prior)
    drives = sum(g["drives"] for g in prior)
    return {
        "win_pct": sum(g["win"] for g in prior) / n,
        "opp_ppg": sum(g["points_against"] for g in prior) / n,
        "third_down_pct": sum(g["third_down_conv"] for g in prior) / att if att else 0.0,
        "turnover_pct": sum(g["ints_thrown"] + g["fumbles_lost"] for g in prior) / drives if drives else 0.0,
    }


def compare(dog: dict, fav: dict) -> tuple[list[dict], int]:
    rows = []
    for key, label, better in STATS:
        dog_wins = (dog[key] - fav[key]) * better > 0
        rows.append({"key": key, "label": label, "dog": round(dog[key], 3), "fav": round(fav[key], 3),
                     "dogWins": dog_wins})
    return rows, sum(r["dogWins"] for r in rows)


def certify(stats_won: int, record: tuple[int, int, int]) -> bool:
    return stats_won >= MIN_STATS_WON and record[0] > record[1]


def home_win_prob(home_ml: float, away_ml: float) -> float:
    """Vig-removed home win probability from American moneylines."""
    imp = lambda ml: 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)  # noqa: E731
    h, a = imp(home_ml), imp(away_ml)
    return h / (h + a)


def dog_spread(spread_line: float, dog_is_home: bool) -> float:
    """nflverse spread_line is the home team's margin as favorite; the dog's handicap is its mirror."""
    return -spread_line if dog_is_home else spread_line


def evaluate(rows: list[dict], z, season: int, week: int, dog: str, fav: str,
             dog_record: tuple[int, int, int]) -> dict:
    d, f = window_stats(rows, dog, season, week), window_stats(rows, fav, season, week)
    if d is None or f is None or z is None:
        return {"certifiable": False, "stats": [], "statsWon": 0, "certified": False}
    ranks = defense_ranks(z)
    d["def_rank"], f["def_rank"] = ranks.get(dog, 32), ranks.get(fav, 32)
    stats, won = compare(d, f)
    return {"certifiable": True, "stats": stats, "statsWon": won, "certified": certify(won, dog_record)}


# ---------------------------------------------------------------------------
# Backtest results and this week's slate
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def backtest() -> dict:
    rows = data.load("hot_dog_backtest")
    out: dict = {"groups": [r for r in rows if r["group"] not in ("chosen_bet", "chosen_total_bet")]}
    chosen = next((r for r in rows if r["group"] == "chosen_bet"), None)
    if chosen:
        out["chosenBet"] = chosen["bet"]
        out["certifiedHitRate"] = float(chosen["hit_rate"])
    total_chosen = next((r for r in rows if r["group"] == "chosen_total_bet"), None)
    if total_chosen:
        out["chosenTotalBet"] = total_chosen["bet"]
        out["totalHitRate"] = float(total_chosen["hit_rate"])
    cert = next((r for r in out["groups"] if r["group"] == "certified hot dogs"), None)
    if cert:
        # Informational only -- no FanDuel cash-out price exists in the lake to grade this against.
        out["ledRate"] = float(cert["led_rate"]) if cert.get("led_rate") else None
        out["cover3Rate"] = float(cert["cover3_rate"]) if cert.get("cover3_rate") else None
        out["cover7Rate"] = float(cert["cover7_rate"]) if cert.get("cover7_rate") else None
    return out


@lru_cache(maxsize=1)
def slate() -> list[dict]:
    import jimmy

    games = {g["game_id"]: g for g in jimmy.next_game_by_team().values()}
    m = matchup.model()
    if not games or not m:
        return []
    odds = {o["game_id"]: o for o in data.load("matchup_game_odds")}
    rows = matchup.pond_rows()
    season = int(next(iter(games.values()))["season"])
    week = int(next(iter(games.values()))["week"])
    z = matchup.week_z(rows, season, week, m["k"], m["r"])
    records = matchup.team_records()
    bt = backtest()

    out = []
    for gid, g in sorted(games.items()):
        o = odds.get(gid)
        try:
            hml, aml, spread = float(o["home_moneyline"]), float(o["away_moneyline"]), float(o["spread_line"])
            total_line = float(o["total_line"])
        except (TypeError, ValueError, KeyError):
            continue
        home, away = g["home_team"], g["away_team"]
        dog_is_home = home_win_prob(hml, aml) < 0.5
        dog, fav = (home, away) if dog_is_home else (away, home)
        dog_rec = records.get(dog, (0, 0, 0))
        result = evaluate(rows, z, season, week, dog, fav, dog_rec)
        out.append({
            "gameId": gid,
            "underdog": dog,
            "favorite": fav,
            "dogRecord": "-".join(map(str, dog_rec)),
            "favRecord": "-".join(map(str, records.get(fav, (0, 0, 0)))),
            "dogWinning": dog_rec[0] > dog_rec[1],
            **result,
            "price": {
                "moneyline": hml if dog_is_home else aml,
                "spread": dog_spread(spread, dog_is_home),
                "spreadOdds": float(o["home_spread_odds" if dog_is_home else "away_spread_odds"] or -110),
                "totalLine": total_line,
                "overOdds": float(o.get("over_odds") or -110),
                "underOdds": float(o.get("under_odds") or -110),
                "source": "reference line (nflverse schedule), not a live FanDuel price",
            },
            "recommendedBet": bt.get("chosenBet"),
            "recommendedTotalBet": bt.get("chosenTotalBet"),
        })
    return out

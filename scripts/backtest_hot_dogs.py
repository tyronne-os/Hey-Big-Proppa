"""
Backtest the HOT DOG indicator (backend/hot_dog.py) on 2023-2025.

Every regular-season game where both teams have 5 prior games in the pond:
the sportsbook underdog (closing moneylines, vig removed, from
lake/bronze/nflverse/games.csv) is compared with the favorite exactly as the
live indicator does, using only games before kickoff. Outcomes recorded per
game: did the dog win outright; did it cover the closing spread; did it ever
hold the lead (pbp scoring margin, informational -- no cash-out price exists
in the lake to bet this); did it cover two flat alt-lines, +3 and +7,
independent of the actual closing spread; did the game go over or under the
closing total (all pushes excluded from rates).

Writes:
  lake/gold/nfl/hot_dog_history.csv   one row per underdog game (the new pond)
  lake/gold/nfl/hot_dog_backtest.csv  hit rates by group, plus the chosen bets:
                                      whichever of moneyline/spread, and
                                      separately over/under, certified dogs
                                      hit more often (POW is hit rate, not cash)

Run from the repo root after build_team_game_stats.py and fit_matchup_model.py:
    backend/.venv/bin/python scripts/backtest_hot_dogs.py
"""
from __future__ import annotations

import csv
import sys
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

import hot_dog  # noqa: E402
import matchup  # noqa: E402
from build_team_game_stats import BRONZE, GOLD, RELEASES, RELOCATED, download, register_chart  # noqa: E402

SEASONS = (2023, 2024, 2025)


def load_lines() -> dict[str, dict]:
    path = BRONZE / "games.csv"
    if not path.exists():
        download(f"{RELEASES}/schedules/games.csv", path)
    out = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["game_type"] != "REG" or int(r["season"]) not in SEASONS:
                continue
            try:
                out[r["game_id"]] = {
                    "home": RELOCATED.get(r["home_team"], r["home_team"]),
                    "away": RELOCATED.get(r["away_team"], r["away_team"]),
                    "home_ml": float(r["home_moneyline"]), "away_ml": float(r["away_moneyline"]),
                    "spread": float(r["spread_line"]),
                    "total_line": float(r["total_line"]), "total_actual": float(r["total"]),
                }
            except ValueError:
                continue
    return out


def load_lead_margins() -> dict[str, tuple[float, float]]:
    """game_id -> (home's max lead, away's max lead), from each season's pbp scoring margin."""
    out: dict[str, tuple[float, float]] = {}
    for season in SEASONS:
        path = BRONZE / f"pbp_{season}.csv.gz"
        if not path.exists():
            download(f"{RELEASES}/pbp/play_by_play_{season}.csv.gz", path)
        pbp = pd.read_csv(path, usecols=["game_id", "total_home_score", "total_away_score"], low_memory=False)
        diff = pbp["total_home_score"] - pbp["total_away_score"]
        for gid, g in diff.groupby(pbp["game_id"]):
            out[gid] = (float(g.max()), float(-g.min()))
    return out


def record_before(rows: list[dict], team: str, season: int, week: int) -> tuple[int, int, int]:
    w = l = t = 0
    for g in rows:
        if g["team"] == team and g["season"] == season and g["week"] < week:
            w, l, t = w + (g["win"] == 1.0), l + (g["win"] == 0.0), t + (g["win"] == 0.5)
    return w, l, t


def rate(hits: list[bool]) -> tuple[int, int, str]:
    n = len(hits)
    return sum(hits), n, f"{sum(hits) / n:.3f}" if n else ""


def main() -> None:
    model = matchup.model()
    rows = matchup.game_rows(list(csv.DictReader((GOLD / "team_game_stats.csv").open(encoding="utf-8"))))
    by_key = {(g["game_id"], g["team"]): g for g in rows}
    lines = load_lines()
    leads = load_lead_margins()
    z_cache: dict[tuple[int, int], dict | None] = {}

    history = []
    for gid, ln in sorted(lines.items()):
        home_row = by_key.get((gid, ln["home"]))
        if not home_row:
            continue
        season, week = home_row["season"], home_row["week"]
        p_home = hot_dog.home_win_prob(ln["home_ml"], ln["away_ml"])
        if p_home == 0.5:
            continue
        dog_is_home = p_home < 0.5
        dog, fav = (ln["home"], ln["away"]) if dog_is_home else (ln["away"], ln["home"])
        if (season, week) not in z_cache:
            z_cache[(season, week)] = matchup.week_z(rows, season, week, model["k"], model["r"])
        rec = record_before(rows, dog, season, week)
        res = hot_dog.evaluate(rows, z_cache[(season, week)], season, week, dog, fav, rec)
        if not res["certifiable"]:
            continue
        margin = by_key[(gid, dog)]["margin"]
        spread = hot_dog.dog_spread(ln["spread"], dog_is_home)
        home_lead, away_lead = leads.get(gid, (0.0, 0.0))
        dog_lead = home_lead if dog_is_home else away_lead
        total_diff = ln["total_actual"] - ln["total_line"]
        row = {
            "season": season, "week": week, "game_id": gid, "underdog": dog, "favorite": fav,
            "dog_home": int(dog_is_home), "dog_moneyline": ln["home_ml"] if dog_is_home else ln["away_ml"],
            "dog_spread": spread, "dog_record": "-".join(map(str, rec)), "dog_winning": int(rec[0] > rec[1]),
            "stats_won": res["statsWon"], "certified": int(res["certified"]), "dog_margin": int(margin),
            "won_outright": int(margin > 0),
            "covered": "push" if margin + spread == 0 else int(margin + spread > 0),
            "dog_led": int(dog_lead > 0),
            "covered_3": "push" if margin + 3 == 0 else int(margin + 3 > 0),
            "covered_7": "push" if margin + 7 == 0 else int(margin + 7 > 0),
            "total_line": ln["total_line"], "total_actual": ln["total_actual"],
            "over_hit": "push" if total_diff == 0 else int(total_diff > 0),
        }
        for s in res["stats"]:
            row[f"dog_{s['key']}"], row[f"fav_{s['key']}"] = s["dog"], s["fav"]
        history.append(row)

    groups = {
        "certified hot dogs": [h for h in history if h["certified"]],
        "all underdogs": history,
        "underdogs with a winning record": [h for h in history if h["dog_winning"]],
        "underdogs winning 3+ of 5 (any record)": [h for h in history if h["stats_won"] >= 3],
    }
    for s in SEASONS:
        groups[f"certified hot dogs {s}"] = [h for h in history if h["certified"] and h["season"] == s]

    report = []
    for name, hs in groups.items():
        ml_hits, ml_n, ml_rate = rate([bool(h["won_outright"]) for h in hs])
        sp = [h["covered"] for h in hs if h["covered"] != "push"]
        sp_hits, sp_n, sp_rate = rate([bool(c) for c in sp])
        led_hits, led_n, led_rate = rate([bool(h["dog_led"]) for h in hs])
        c3 = [h["covered_3"] for h in hs if h["covered_3"] != "push"]
        c3_hits, c3_n, c3_rate = rate([bool(c) for c in c3])
        c7 = [h["covered_7"] for h in hs if h["covered_7"] != "push"]
        c7_hits, c7_n, c7_rate = rate([bool(c) for c in c7])
        ou = [h["over_hit"] for h in hs if h["over_hit"] != "push"]
        over_hits, over_n, over_rate = rate([bool(o) for o in ou])
        under_hits = over_n - over_hits
        under_rate = f"{under_hits / over_n:.3f}" if over_n else ""
        report.append({
            "group": name, "games": len(hs), "outright_wins": ml_hits, "outright_rate": ml_rate,
            "covers": sp_hits, "cover_games": sp_n, "cover_rate": sp_rate,
            "led_games": led_hits, "led_rate": led_rate,
            "cover3_games": c3_hits, "cover3_of": c3_n, "cover3_rate": c3_rate,
            "cover7_games": c7_hits, "cover7_of": c7_n, "cover7_rate": c7_rate,
            "over_games": over_hits, "under_games": under_hits, "ou_of": over_n,
            "over_rate": over_rate, "under_rate": under_rate,
        })

    cert = report[0]
    ml, sp = float(cert["outright_rate"] or 0), float(cert["cover_rate"] or 0)
    bet, hit = ("moneyline", ml) if ml > sp else ("spread", sp)
    report.append({"group": "chosen_bet", "bet": bet, "hit_rate": f"{hit:.3f}",
                   "games": cert["games"], "note": "higher certified hit rate; POW counts tickets won, not cash"})

    over_r, under_r = float(cert["over_rate"] or 0), float(cert["under_rate"] or 0)
    total_bet, total_hit = ("over", over_r) if over_r > under_r else ("under", under_r)
    report.append({"group": "chosen_total_bet", "bet": total_bet, "hit_rate": f"{total_hit:.3f}",
                   "games": cert["ou_of"], "note": "higher certified hit rate of over/under vs. closing total"})

    hist_cols = list(history[0].keys()) if history else []
    with (GOLD / "hot_dog_history.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=hist_cols)
        w.writeheader()
        w.writerows(history)
    cols = ["group", "games", "outright_wins", "outright_rate", "covers", "cover_games", "cover_rate",
            "led_games", "led_rate", "cover3_games", "cover3_of", "cover3_rate",
            "cover7_games", "cover7_of", "cover7_rate", "over_games", "under_games", "ou_of",
            "over_rate", "under_rate", "bet", "hit_rate", "note"]
    with (GOLD / "hot_dog_backtest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in report:
            w.writerow({c: r.get(c, "") for c in cols})

    register_chart("hot_dog_history", "scripts/backtest_hot_dogs.py",
                   "one row per underdog game, 2023-2025, with both teams' last-5 stats", len(history),
                   "team_game_stats + closing lines (derived)")
    register_chart("hot_dog_backtest", "scripts/backtest_hot_dogs.py", "one row per backtest group",
                   len(report), "hot_dog_history (derived)")

    for r in report:
        print({k: v for k, v in r.items() if v != ""})


if __name__ == "__main__":
    main()

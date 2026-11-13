"""
DAY PICKS — combine the 15/10 Rule with the Rotowire player prop categories.

Pipeline:
  1. bet_logic finds the day's 15/10 matchups (top-15% offense vs bottom-10% defense).
  2. For each 15/10 matchup, pull the OFFENSE's Rotowire players.
  3. Score each player's probability of DOMINATING the relevant prop category
     (rush yards, rec yards, receptions, passing yards, anytime TD).
  4. Rank by that probability and explain WHY (the weak defense they face + their volume).

The categories stay the same every day; the players change. This surfaces who pays off.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import bet_logic
import data

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"

# category -> (source csv, stat col) for the relevant prop.
_CAT_SOURCE = {
    "rush": ("player_rushing_week", "rushing_yards"),
    "pass": ("player_passing_week", "passing_yards"),
    "recyds": ("player_receiving_week", "receiving_yards"),
    "recs": ("player_receiving_week", "receptions"),
}
# position that dominates each category
_CAT_POS = {"rush": ("RB", "FB"), "pass": ("QB",), "recyds": ("WR", "TE"), "recs": ("WR", "TE", "RB")}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _load(name: str) -> list[dict]:
    with open(BASE / name) as f:
        return list(csv.DictReader(f))


def _week_games(player_id: str, src: str, col: str) -> list[float]:
    out = []
    for r in _load(src + ".csv"):
        if r.get("player_id") == player_id:
            out.append(_num(r.get(col)))
    return out


def _season_avg(player_id: str, category: str) -> float:
    src, col = _CAT_SOURCE[category]
    vals = _week_games(player_id, src, col)
    return sum(vals) / len(vals) if vals else 0.0


def _season_games(player_id: str, category: str) -> int:
    src, col = _CAT_SOURCE[category]
    return len(_week_games(player_id, src, col))


def _team_players(team: str, category: str) -> list[dict]:
    """All Rotowire-tracked players on a team who dominate the category."""
    dim = data.player_dimension()
    pos = _CAT_POS.get(category, ())
    out = []
    for pid, v in dim.items():
        if v.get("team") != team:
            continue
        if v.get("position") not in pos:
            continue
        out.append({"playerId": pid, "name": v.get("name", pid),
                    "position": v.get("position", ""), "team": team})
    return out


def _td_rate(player_id: str) -> float:
    """Anytime TD rate from player_scoring_week (2026)."""
    td = 0
    games = 0
    seen = set()
    for r in _load("player_scoring_week.csv"):
        if r.get("player_id") != player_id:
            continue
        games += 1
        if _num(r.get("total_tds")) >= 1:
            td += 1
    return td / games if games else 0.0


def day_picks() -> dict:
    """Run the pipeline: 15/10 matchups -> Rotowire players -> domination probability."""
    res = bet_logic.bet_hunt()
    ts = bet_logic._team_stats()
    opp = bet_logic._upcoming_opponents()
    cats = ["rush", "pass", "recyds", "recs"]

    # Rebuild 15/10 matchups WITHOUT the Rule-3 filter so we can see all of them,
    # but still annotate whether the offense has something to live for.
    matchups = []
    for cat in ("rush", "pass"):
        top15 = bet_logic._top15(ts, cat)
        bot10 = bet_logic._bottom10(ts, cat)
        for off in top15:
            def_team = opp.get(off)
            if def_team in bot10:
                rec = ts[off]["record"]
                matchups.append({
                    "category": cat, "offense": off, "weakDefense": def_team,
                    "living": rec["wins"] > rec["losses"], "record": rec,
                })

    picks = []
    for m in matchups:
        off = m["offense"]
        weak = m["weakDefense"]
        cat = m["category"]
        # The dominating prop for this matchup: rush -> rushing yards; pass -> passing yards.
        players = _team_players(off, cat)
        scored = []
        for p in players:
            avg = _season_avg(p["playerId"], cat)
            g = _season_games(p["playerId"], cat)
            if avg <= 0 or g < 4:
                continue
            scored.append({
                "playerId": p["playerId"], "name": p["name"], "position": p["position"],
                "team": off, "category": cat, "seasonAvg": round(avg, 1), "games": g,
                "opponent": weak,
                "tdRate": round(_td_rate(p["playerId"]), 3),
            })
        scored.sort(key=lambda x: -x["seasonAvg"])
        for s in scored[:5]:
            # rank within the matchup's offense by season avg (1 = top)
            s["rankInOffense"] = scored.index(s) + 1
            s["why"] = (f"{s['name']} is the {'top' if s['rankInOffense']==1 else str(s['rankInOffense'])} "
                        f"{s['position']} for {off} vs a bottom-10% {cat} defense ({weak}); "
                        f"{s['seasonAvg']} {cat} yds/game, {s['tdRate']:.0%} anytime TD.")
            picks.append(s)

    # Also surface the domination picks for the day's weak defenses generally.
    return {
        "sourceStatus": "ok",
        "fifteenTenMatchups": matchups,
        "picks": picks,
        "note": "Categories stay the same; players change. Highest season-avg player in each 15/10 offense is the domination pick.",
    }


if __name__ == "__main__":
    res = day_picks()
    print("sourceStatus:", res["sourceStatus"])
    print("\n=== 15/10 MATCHUPS (offense vs bottom-10 defense) ===")
    for m in res["fifteenTenMatchups"]:
        flag = " ★ LIVE FOR" if m["living"] else " (losing record)"
        print(f"  {m['category'].upper()}: {m['offense']} vs {m['weakDefense']}  [{m['record']['wins']}-{m['record']['losses']}]{flag}")
    print("\n=== DOMINATION PICKS (Rotowire players) ===")
    for p in res["picks"]:
        print(f"  {p['name']:<22} ({p['team']} {p['position']}) {p['category']} avg={p['seasonAvg']} vs {p['opponent']} TD={p['tdRate']:.0%}  #{p['rankInOffense']}")
    print("\n=== WHY ===")
    for p in res["picks"][:10]:
        print(f"  {p['why']}")

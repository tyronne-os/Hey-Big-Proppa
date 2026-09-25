"""
Leaders categories -- season aggregates over the weekly gold CSVs.

RUSHING / RECEIVING / PASSING / SCORING / FIELD GOALS are summed here from
the *_week.csv exports (which are always views over week-grain data per
docs/HANDOFF.md sec 5.1 -- season totals are never stored directly). SACKS
already ships as a season-grain gold object (individual_sacks.csv) and is
used as-is. DIVISIONS uses W-L computed from the real schedule.csv joined to
a static division map -- division alignment is fixed NFL structure, not lake
data, so it is not something any pond generates.
"""
from __future__ import annotations

from collections import defaultdict

import breakout
import data

DIVISIONS = {
    "AFC East": ["BUF", "MIA", "NE", "NYJ"],
    "AFC North": ["BAL", "CIN", "CLE", "PIT"],
    "AFC South": ["HOU", "IND", "JAX", "TEN"],
    "AFC West": ["DEN", "KC", "LV", "LAC"],
    "NFC East": ["DAL", "NYG", "PHI", "WAS"],
    "NFC North": ["CHI", "DET", "GB", "MIN"],
    "NFC South": ["ATL", "CAR", "NO", "TB"],
    "NFC West": ["ARI", "LA", "SEA", "SF"],
}


def _sum_by_player(src: str, stat_col: str) -> dict[str, dict]:
    totals: dict[str, dict] = {}
    for row in data.load(src):
        pid = row.get("player_id")
        if not pid:
            continue
        try:
            val = float(row.get(stat_col) or 0)
        except ValueError:
            val = 0.0
        entry = totals.setdefault(pid, {"value": 0.0, "gp": 0, "team": row.get("team", "")})
        entry["value"] += val
        entry["gp"] += 1
        entry["team"] = row.get("team", entry["team"])
    return totals


def _rank(totals: dict[str, dict]) -> list[dict]:
    dim = data.player_dimension()
    rows = sorted(totals.items(), key=lambda kv: kv[1]["value"], reverse=True)
    out = []
    for i, (pid, t) in enumerate(rows, start=1):
        out.append({
            "rank": i,
            "playerId": pid,
            "name": dim.get(pid, {}).get("name", data.player_name(pid)),
            "team": t["team"],
            "gp": t["gp"],
            "value": round(t["value"], 1),
        })
    return out


CATEGORY_SOURCES = {
    "RUSHING": ("player_rushing_week", "rushing_yards"),
    "RECEIVING": ("player_receiving_week", "receiving_yards"),
    "PASSING": ("player_passing_week", "passing_yards"),
    "SCORING": ("player_scoring_week", "total_points"),
    "FIELD GOALS": ("player_kicking_week", "fg_made"),
}


def leaders(category: str) -> dict:
    category = category.upper()

    if category == "BREAKOUT":
        table = breakout.breakout_table()
        return {
            "category": category,
            "sourceStatus": data.chart_status("player_receiving_week"),
            "rows": [
                {
                    "rank": i,
                    "playerId": r["playerId"],
                    "name": r["name"],
                    "team": r["team"],
                    "gp": r["games"],
                    "value": r["breakoutScore"],
                    "role": f"{r['flag']} · {r['position']} · {r['xpprPerGame']} xPPR vs {r['pprPerGame']} PPR",
                }
                for i, r in enumerate(table, start=1)
            ],
        }

    if category == "DEFENSE TOXICITY":
        rows = sorted(data.load("defense_ib_score"), key=lambda r: float(r.get("toxicity_index_0_100") or 0), reverse=True)
        return {
            "category": category,
            "sourceStatus": data.chart_status("defense_ib_score"),
            "rows": [
                {
                    "rank": i,
                    "playerId": r.get("team", ""),
                    "name": r.get("team", ""),
                    "team": r.get("team", ""),
                    "gp": int(r.get("games_played") or 0),
                    "value": float(r.get("toxicity_index_0_100") or 0),
                    "role": r.get("ib_category", ""),
                }
                for i, r in enumerate(rows, start=1)
            ],
        }

    if category == "USAGE INDEX":
        rows = sorted(data.load("player_usage"), key=lambda r: float(r.get("usage_index_score") or 0), reverse=True)
        return {
            "category": category,
            "sourceStatus": data.chart_status("player_usage"),
            "rows": [
                {
                    "rank": i,
                    "playerId": r.get("player_id", ""),
                    "name": r.get("player_name", ""),
                    "team": r.get("team", ""),
                    "gp": int(r.get("games") or 0),
                    "value": float(r.get("usage_index_score") or 0),
                    "role": r.get("usage_role", ""),
                }
                for i, r in enumerate(rows, start=1)
            ],
        }

    if category == "SACKS":
        rows = data.load("individual_sacks")
        ranked = sorted(rows, key=lambda r: float(r.get("sacks") or 0), reverse=True)
        return {
            "category": category,
            "sourceStatus": data.chart_status("individual_sacks"),
            "rows": [
                {
                    "rank": i,
                    "playerId": r.get("player_id", ""),
                    "name": r.get("player_name", ""),
                    "team": r.get("team", ""),
                    "gp": int(r.get("games") or 0),
                    "value": float(r.get("sacks") or 0),
                }
                for i, r in enumerate(ranked, start=1)
            ],
        }

    if category == "DIVISIONS":
        wins: dict[str, int] = defaultdict(int)
        losses: dict[str, int] = defaultdict(int)
        for g in data.load("schedule"):
            if not g.get("home_score") or not g.get("away_score"):
                continue
            try:
                hs, aws = int(g["home_score"]), int(g["away_score"])
            except ValueError:
                continue
            if hs > aws:
                wins[g["home_team"]] += 1
                losses[g["away_team"]] += 1
            elif aws > hs:
                wins[g["away_team"]] += 1
                losses[g["home_team"]] += 1
        divisions = []
        for div_name, teams in DIVISIONS.items():
            standings = sorted(
                ({"team": t, "wins": wins[t], "losses": losses[t]} for t in teams),
                key=lambda s: s["wins"], reverse=True,
            )
            divisions.append({"division": div_name, "standings": standings})
        return {"category": category, "sourceStatus": data.chart_status("schedule"), "divisions": divisions}

    src, stat_col = CATEGORY_SOURCES.get(category, (None, None))
    if src is None:
        return {"category": category, "sourceStatus": "error", "rows": [], "error": "unknown category"}
    return {
        "category": category,
        "sourceStatus": data.chart_status(src),
        "rows": _rank(_sum_by_player(src, stat_col)),
    }

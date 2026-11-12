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

import bpl
import breakout
import data
import matchup

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
        gp = max(t["gp"], 1)  # avoid div-by-zero
        per_game = t["value"] / gp
        out.append({
            "rank": i,
            "playerId": pid,
            "name": dim.get(pid, {}).get("name", data.player_name(pid)),
            "team": t["team"],
            "gp": t["gp"],
            "value": round(per_game, 2),
            "total": round(t["value"], 1),  # season total (e.g. total TDs on the year)
        })
    return out


BPL_ROWS = 100
CATEGORY_ROWS = {}                 # every BPL category returns 100 so the page can show 50, 75 or 100

CATEGORY_SOURCES = {
    "RUSHING": ("player_rushing_week", "rushing_yards"),
    "RUSHING ATTEMPTS": ("player_rushing_week", "carries"),
    "RECEIVING": ("player_receiving_week", "receiving_yards"),
    "RECEPTIONS": ("player_receiving_week", "receptions"),
    "PASSING": ("player_passing_week", "passing_yards"),
    "PASSING ATTEMPTS": ("player_passing_week", "attempts"),
    "SCORING": ("player_scoring_week", "total_tds"),
    "FIELD GOALS": ("player_kicking_week", "fg_made"),
    "TARGETS": ("player_receiving_week", "targets"),
    "COMBO": ("player_combo_week", "all_purpose_yards"),
}


def leaders(category: str) -> dict:
    out = _leaders(category)
    dim = data.player_dimension()
    for r in out.get("rows") or []:
        if str(r.get("playerId", "")).startswith("00-"):
            r["name"] = dim.get(r["playerId"], {}).get("name") or r["name"]
            r.setdefault("photoUrl", data.photo_url(r["playerId"]))
    # BIG PROPPA column = JEV's projection, SAFE BET = the line cut 15% with JEV's chance of clearing it
    items = [(r["playerId"], r["playerId"], r["name"], r["team"], r["bpl"]["market"], r["bpl"]["sportsbookLine"])
             for r in out.get("rows") or [] if r.get("bpl") and r["bpl"].get("sportsbookLine") and r["bpl"].get("market")]
    if items:
        import jev
        ov, pending = jev.leader_overlay(items)
        for r in out["rows"]:
            if r["playerId"] in ov:
                r["bpl"]["jev"] = ov[r["playerId"]]
        out["jevPending"] = pending
    return out


def _leaders(category: str) -> dict:
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

    if category == "COMBO":
        # Combine rushing_yards + receiving_yards = all-purpose yards
        rushing = data.load("player_rushing_week")
        receiving = data.load("player_receiving_week")
        # Sum yards per player
        totals: dict[str, dict] = {}
        for row in rushing:
            pid = row.get("player_id")
            if not pid:
                continue
            try:
                val = float(row.get("rushing_yards") or 0)
            except ValueError:
                val = 0.0
            entry = totals.setdefault(pid, {"value": 0.0, "gp": 0, "team": row.get("team", "")})
            entry["value"] += val
            entry["gp"] += 1
            entry["team"] = row.get("team", entry["team"])
        for row in receiving:
            pid = row.get("player_id")
            if not pid:
                continue
            try:
                val = float(row.get("receiving_yards") or 0)
            except ValueError:
                val = 0.0
            if pid in totals:
                totals[pid]["value"] += val
                totals[pid]["gp"] = max(totals[pid]["gp"], 1)
            else:
                totals[pid] = {"value": val, "gp": 1, "team": row.get("team", "")}
        dim = data.player_dimension()
        rows = sorted(totals.items(), key=lambda kv: kv[1]["value"], reverse=True)
        out = []
        for i, (pid, t) in enumerate(rows, start=1):
            per_game = t["value"] / max(t["gp"], 1)
            out.append({
                "rank": i,
                "playerId": pid,
                "name": dim.get(pid, {}).get("name", data.player_name(pid)),
                "team": t["team"],
                "gp": t["gp"],
                "value": round(per_game, 2),
            })
        return {
            "category": category,
            "sourceStatus": data.chart_status("player_rushing_week"),
            "rows": out,
        }

    if category == "DIVISIONS":
        records = matchup.team_records()
        divisions = []
        for div_name, teams in DIVISIONS.items():
            standings = sorted(
                ({"team": t, "wins": records.get(t, (0, 0, 0))[0], "losses": records.get(t, (0, 0, 0))[1]} for t in teams),
                key=lambda s: s["wins"], reverse=True,
            )
            divisions.append({"division": div_name, "standings": standings})
        return {"category": category, "sourceStatus": data.chart_status("schedule"), "divisions": divisions}

    if category == "L5":
        # Last 5 games TD tracking
        scoring = data.load("player_scoring_week")
        # Group by player_id and collect their games
        player_games: dict[str, list[dict]] = {}
        for row in scoring:
            pid = row.get("player_id")
            if not pid:
                continue
            if pid not in player_games:
                player_games[pid] = []
            player_games[pid].append(row)
        
        # For each player, sort by week (descending) and take last 5 games
        totals: dict[str, dict] = {}
        dim = data.player_dimension()
        
        for pid, games in player_games.items():
            # Sort by week number descending (most recent first)
            games_sorted = sorted(games, key=lambda r: int(r.get("week") or 0), reverse=True)
            # Take last 5 games (most recent 5)
            last5 = games_sorted[:5]
            # Sum total_tds from last 5 games
            total_tds = sum(float(g.get("total_tds") or 0) for g in last5)
            if total_tds > 0 or True:  # Include all players who have any data
                entry = totals.setdefault(pid, {"value": 0.0, "gp": len(last5), "team": "", "name": dim.get(pid, {}).get("name", data.player_name(pid))})
                entry["value"] += total_tds
                entry["gp"] = len(last5)
                # Get team from the most recent game
                entry["team"] = games_sorted[0].get("team", "") if games_sorted else ""
        
        rows = sorted(totals.items(), key=lambda kv: kv[1]["value"], reverse=True)
        out = []
        for i, (pid, t) in enumerate(rows, start=1):
            per_game = t["value"] / max(t["gp"], 1)
            out.append({
                "rank": i,
                "playerId": pid,
                "name": t.get("name", ""),
                "team": t.get("team", ""),
                "gp": t["gp"],
                "value": round(per_game, 2),
            })
        return {
            "category": category,
            "sourceStatus": data.chart_status("player_scoring_week"),
            "rows": out,
        }

    if category == "RB REC":
        # Running backs' receiving: pays well to predict receptions.
        # Columns: receptions (value), targets, rec yards, rec TDs, longest (40+ yd receptions as proxy).
        dim = data.player_dimension()
        totals: dict[str, dict] = {}
        for row in data.load("player_receiving_week"):
            pid = row.get("player_id")
            if not pid:
                continue
            if dim.get(pid, {}).get("position") not in ("RB", "FB"):
                continue
            def _f(k: str) -> float:
                try:
                    return float(row.get(k) or 0)
                except ValueError:
                    return 0.0
            entry = totals.setdefault(pid, {
                "value": 0.0, "gp": 0, "team": row.get("team", ""),
                "targets": 0.0, "yards": 0.0, "tds": 0.0, "longest": 0.0,
            })
            entry["value"] += _f("receptions")
            entry["targets"] += _f("targets")
            entry["yards"] += _f("receiving_yards")
            entry["tds"] += _f("receiving_tds")
            entry["longest"] += _f("receiving_40")
            entry["gp"] += 1
            entry["team"] = row.get("team", entry["team"])
        rows = sorted(totals.items(), key=lambda kv: kv[1]["value"], reverse=True)
        out = []
        for i, (pid, t) in enumerate(rows[:50], start=1):
            gp = max(t["gp"], 1)
            out.append({
                "rank": i,
                "playerId": pid,
                "name": dim.get(pid, {}).get("name", data.player_name(pid)),
                "team": t["team"],
                "gp": t["gp"],
                "value": round(t["value"] / gp, 2),
                "total": round(t["value"], 1),
                "targets": round(t["targets"] / gp, 2),
                "yards": round(t["yards"] / gp, 1),
                "tds": round(t["tds"] / gp, 2),
                "longest": round(t["longest"] / gp, 2),
            })
        return {
            "category": category,
            "sourceStatus": data.chart_status("player_receiving_week"),
            "rows": out,
        }

    src, stat_col = CATEGORY_SOURCES.get(category, (None, None))
    if src is None:
        return {"category": category, "sourceStatus": "error", "rows": [], "error": "unknown category"}
    rows = _rank(_sum_by_player(src, stat_col))
    market = bpl.LEADER_MARKET.get(category)
    if market:
        rows = [r for r in rows if r["value"] > 0][:CATEGORY_ROWS.get(category, BPL_ROWS)]
        for r in rows:
            r["bpl"] = bpl.nfl_player_line(r["playerId"], market, r["name"], r["team"])
    return {
        "category": category,
        "sourceStatus": data.chart_status(src),
        "rows": rows,
        "bplVersion": bpl.BPL_VERSION if market else None,
    }

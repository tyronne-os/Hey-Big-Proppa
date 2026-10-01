"""
Matchup heat map: two teams side by side across 11 team-level metrics, each
ranked against all 32 NFL teams from the lake (team_game_stats, points_by_half,
schedule). Rank 1 = strongest -> green on the front end.
"""
from __future__ import annotations

from collections import defaultdict

import data

SEASON = "2026"

# key, label, unit, higher_is_better
METRICS = [
    ("turnovers_pg", "Turnovers per game", "", False),
    ("pass_ypg", "Passing yards per game", "", True),
    ("rush_ypg", "Rushing yards per game", "", True),
    ("def_rank", "Defense ranked in NFL (pts allowed)", "rank", False),
    ("off_rank", "Offense ranked in NFL (pts scored)", "rank", False),
    ("margin_pg", "Win margin per game", "", True),
    ("third_pct", "3rd down conversion", "%", True),
    ("opp_third_pct", "Opponent 3rd down conversion", "%", False),
    ("second_half_rank", "2nd half scoring ranked in NFL", "rank", False),
    ("rz_pct", "Red zone scoring (TD %)", "%", True),
    ("opp_rz_pct", "Opponent red zone scoring (TD %)", "%", False),
]


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _rank(values: dict[str, float], high_good: bool) -> dict[str, int]:
    order = sorted(values, key=lambda t: -values[t] if high_good else values[t])
    return {t: i + 1 for i, t in enumerate(order)}


def _team_table() -> dict[str, dict]:
    games = [r for r in data.load("team_game_stats") if r.get("season") == SEASON]
    by_game: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in games:
        by_game[r["game_id"]][r["team"]] = r

    acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in games:
        t = r["team"]
        opp = by_game[r["game_id"]].get(r["opponent"])
        a = acc[t]
        a["g"] += 1
        a["to"] += _f(r["ints_thrown"]) + _f(r["fumbles_lost"])
        a["pass"] += _f(r["pass_yds"])
        a["rush"] += _f(r["rush_yds"])
        a["pf"] += _f(r["points_for"])
        a["pa"] += _f(r["points_against"])
        a["margin"] += _f(r["margin"])
        a["3a"] += _f(r["third_down_att"])
        a["3c"] += _f(r["third_down_conv"])
        a["rzt"] += _f(r["rz_trips"])
        a["rztd"] += _f(r["rz_tds"])
        if opp:
            a["o3a"] += _f(opp["third_down_att"])
            a["o3c"] += _f(opp["third_down_conv"])
            a["orzt"] += _f(opp["rz_trips"])
            a["orztd"] += _f(opp["rz_tds"])

    # 2nd-half points scored = opponents' 2nd-half points_allowed in that game
    sh: dict[str, float] = defaultdict(float)
    for r in data.load("points_by_half"):
        if r.get("season") == SEASON and r.get("half") == "2":
            sh[r["opponent"]] += _f(r["points_allowed"])

    out: dict[str, dict] = {}
    for t, a in acc.items():
        g = a["g"] or 1
        out[t] = {
            "turnovers_pg": a["to"] / g,
            "pass_ypg": a["pass"] / g,
            "rush_ypg": a["rush"] / g,
            "pf": a["pf"] / g,
            "pa": a["pa"] / g,
            "margin_pg": a["margin"] / g,
            "third_pct": 100 * a["3c"] / a["3a"] if a["3a"] else 0.0,
            "opp_third_pct": 100 * a["o3c"] / a["o3a"] if a["o3a"] else 0.0,
            "rz_pct": 100 * a["rztd"] / a["rzt"] if a["rzt"] else 0.0,
            "opp_rz_pct": 100 * a["orztd"] / a["orzt"] if a["orzt"] else 0.0,
            "sh_pg": sh.get(t, 0.0) / g,
        }
    return out


def _qb(team: str, name: str) -> dict:
    pid = None
    norm = data.normalize_name(name) if name else ""
    for p, r in data.player_dimension().items():
        if r.get("team") == team and data.normalize_name(r.get("name", "")) == norm:
            pid = p
            break
    return {"name": name or "TBD", "photoUrl": data.photo_url(pid) if pid else None}


def build(away: str, home: str, away_qb: str = "", home_qb: str = "") -> dict:
    tbl = _team_table()
    teams = list(tbl)
    ranks = {
        "turnovers_pg": _rank({t: tbl[t]["turnovers_pg"] for t in teams}, False),
        "pass_ypg": _rank({t: tbl[t]["pass_ypg"] for t in teams}, True),
        "rush_ypg": _rank({t: tbl[t]["rush_ypg"] for t in teams}, True),
        "def_rank": _rank({t: tbl[t]["pa"] for t in teams}, False),
        "off_rank": _rank({t: tbl[t]["pf"] for t in teams}, True),
        "margin_pg": _rank({t: tbl[t]["margin_pg"] for t in teams}, True),
        "third_pct": _rank({t: tbl[t]["third_pct"] for t in teams}, True),
        "opp_third_pct": _rank({t: tbl[t]["opp_third_pct"] for t in teams}, False),
        "second_half_rank": _rank({t: tbl[t]["sh_pg"] for t in teams}, True),
        "rz_pct": _rank({t: tbl[t]["rz_pct"] for t in teams}, True),
        "opp_rz_pct": _rank({t: tbl[t]["opp_rz_pct"] for t in teams}, False),
    }
    n = len(teams) or 1
    # rank-type rows display the rank itself as the value
    value_from_rank = {"def_rank", "off_rank", "second_half_rank"}

    def cell(team: str, key: str) -> dict | None:
        if team not in tbl:
            return None
        rk = ranks[key][team]
        val = rk if key in value_from_rank else round(tbl[team][key], 1)
        return {"value": val, "rank": rk, "strength": round(1 - (rk - 1) / max(n - 1, 1), 3)}

    rows = []
    for key, label, unit, _hi in METRICS:
        rows.append({"key": key, "label": label, "unit": unit,
                     "away": cell(away, key), "home": cell(home, key)})
    return {
        "season": SEASON,
        "teamsRanked": n,
        "away": {"team": away, "qb": _qb(away, away_qb)},
        "home": {"team": home, "qb": _qb(home, home_qb)},
        "rows": rows,
    }

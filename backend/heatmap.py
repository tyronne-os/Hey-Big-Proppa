"""
Matchup heat map: two teams side by side across 11 team-level metrics, each
ranked against all 32 NFL teams from the lake (team_game_stats, points_by_half,
schedule). Rank 1 = strongest -> green on the front end.

Also exports game_lines() — moneyline, total, and JEV-endorsed alternate unders
for the underdog, meaning lines where the total is reduced to increase the odds
on the under, but only when JEV agrees the under still clears.
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


def _dec(american: float) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def game_lines(away: str, home: str) -> dict:
    """
    Moneyline, posted total, and JEV-endorsed alternate under lines for this game.

    Alternate unders: drop the posted total by 2.5, 5, and 7.5 points. For each,
    ask JEV whether the under still clears given the teams' defensive profiles.
    Only surfaces lines where JEV probability >= 0.50. Fewer points = better odds
    on the under = higher payout, but only when JEV agrees.
    """
    import jimmy_nfl_games
    import jev as _jev
    import math

    JEV_MIN_P = 0.50
    ALT_DROPS = [2.5, 5.0, 7.5]

    # Find this game's FanDuel prices
    raw = None
    for r in jimmy_nfl_games._games():
        if {r["home"], r["away"]} == {home, away}:
            raw = r
            break
    if not raw:
        return {"available": False}

    fd = raw["fd"]

    def _f(v):
        try: return float(v)
        except: return None

    hml, aml = _f(fd.get("homeTeamML")), _f(fd.get("awayTeamML"))
    total = _f(fd.get("totalOver"))
    over_px, under_px = _f(fd.get("totalOverOdds")), _f(fd.get("totalUnderOdds"))

    if hml is None or aml is None:
        return {"available": False}

    # Identify underdog: higher American odds (more positive) = underdog
    home_is_dog = hml > aml
    dog_team = home if home_is_dog else away
    fav_team = away if home_is_dog else home
    dog_ml = hml if home_is_dog else aml
    fav_ml = aml if home_is_dog else hml

    # Moneyline cards
    def ml_card(team: str, american: float, label: str) -> dict:
        dec = _dec(american)
        sign = "+" if american > 0 else ""
        return {
            "team": team, "american": int(american), "display": f"{sign}{int(american)}",
            "decimal": round(dec, 3), "impliedPct": round(100 / dec, 1), "label": label,
        }

    moneylines = [
        ml_card(fav_team, fav_ml, "FAVORITE"),
        ml_card(dog_team, dog_ml, "UNDERDOG"),
    ]

    # Total — over/under at posted line
    total_line = None
    if total and over_px and under_px:
        total_line = {
            "line": total,
            "over": {"american": int(over_px), "display": f"+{int(over_px)}" if over_px > 0 else str(int(over_px)),
                     "decimal": round(_dec(over_px), 3)},
            "under": {"american": int(under_px), "display": f"+{int(under_px)}" if under_px > 0 else str(int(under_px)),
                      "decimal": round(_dec(under_px), 3)},
        }

    # Alternate under lines: JEV must agree
    alt_unders = []
    if total and _jev.available():
        # Use defensive heatmap data to estimate usage/edge for the game
        tbl = _team_table()
        home_d = tbl.get(home, {})
        away_d = tbl.get(away, {})
        # matchup edge proxy: average of both defenses' points-allowed rank (lower pa = stronger defense)
        avg_pa = ((home_d.get("pa", 25) + away_d.get("pa", 25)) / 2)
        # Normalize to a 0-100 usage-style score: 14 pa = 100, 35 pa = 0
        def_strength = max(0.0, min(100.0, round(100 * (35 - avg_pa) / 21, 1)))
        # matchup edge as z-score proxy: below-avg scoring = negative offense edge
        matchup_edge = round((avg_pa - 22.5) / 7.0, 2)  # 22.5 = league avg scoring, 7 = sd

        for drop in ALT_DROPS:
            alt_line = round(total - drop, 1)
            game_id = f"ALT:{away}@{home}:{alt_line}"
            jev_p = _jev.leg_probability(
                game_id, f"{away} @ {home}", home, "nfl_total", "under", alt_line,
                hit_rate=None,
                usage_score=def_strength,
                matchup_edge=matchup_edge,
                opponent=away,
            )
            if jev_p is not None and jev_p >= JEV_MIN_P:
                # Alt under price — no live FanDuel price; estimate via normal CDF shift
                # Each 2.5pt drop from posted total moves the under probability roughly +6%
                SIGMA = 13.5
                base_under_p = 1 - (0.5 + (1 / (_dec(under_px) if under_px else 2) - 0.5))
                delta_p = 1 - (0.5 * (1 + math.erf((alt_line - total + 0.0) / (SIGMA * math.sqrt(2)))))
                est_p = min(0.85, max(0.30, delta_p))
                # estimated american odds at this probability
                if est_p >= 0.5:
                    est_am = int(round(-100 * est_p / (1 - est_p)))
                else:
                    est_am = int(round(100 * (1 - est_p) / est_p))
                alt_unders.append({
                    "line": alt_line,
                    "drop": drop,
                    "jevP": round(jev_p, 3),
                    "estAmerican": est_am,
                    "estDisplay": f"+{est_am}" if est_am > 0 else str(est_am),
                    "estDecimal": round(_dec(est_am), 3),
                    "note": f"JEV {jev_p:.0%} confident UNDER {alt_line} clears · {drop:+.1f}pts from posted line → better odds",
                })

    return {
        "available": True,
        "moneylines": moneylines,
        "total": total_line,
        "altUnders": alt_unders,
        "jevActive": _jev.available(),
        "underdogTeam": dog_team,
    }


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

    lines = game_lines(away, home)

    return {
        "active": True,
        "season": SEASON,
        "teamsRanked": n,
        "away": {"team": away, "qb": _qb(away, away_qb)},
        "home": {"team": home, "qb": _qb(home, home_qb)},
        "rows": rows,
        "gameLines": lines,
    }

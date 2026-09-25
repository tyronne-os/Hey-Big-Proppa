"""
BIG PROPPA MATCHUP HEAT MAP -- team-vs-team predictor built only from the
team_game_stats pond (the TeamRankings stats, computed from nflverse play-by-
play). No betting lines or consensus picks are inputs.

HOW A MATCHUP IS SCORED
=======================
1. Profile. For every team, each stat is a season-to-date rate using only
   games before the week being predicted, shrunk toward a prior worth K games.
   The prior is last season's rate regressed R of the way to the league mean
   (in the pond's first season, the league average of games already played).
   The pond is modern era only, 2023 onward.
   Every stat is num / den (per-game stats use games as den), so ratios like
   red-zone TD % shrink on trips, not games.
2. z-scores across the league that week.
3. Five unit matchups, each one team's offense against the other's defense.
   The unit edge is the mean of its stats' z-scores, signed so + favors the
   offense. See UNITS.
4. Prediction. margin = HOME * home + sum(beta_u * (edge_home_u - edge_away_u))
   and win probability = Phi(margin / SIGMA).

K, R, the betas, HOME, SIGMA and the active stat list are fitted by
scripts/fit_matchup_model.py on past seasons and stored in
lake/gold/nfl/matchup_model.csv; the backtest is in matchup_backtest.csv.

Backtest (trained 2023, tuned on 2024, 2025 held out untouched):
  all 272 games          64.2% right   (Vegas favorite 65.5%, always-home 53.1%)
  model >= 75% confident 38 of 43, 88.4%   (Vegas at >= 75%: 79.7% of 74)
One season of holdout -- the 75%+ bucket is 43 games, so treat its rate as a
range (roughly mid-70s to mid-90s), not a promise. matchup_backtest.csv has the
full table, the tuning grid and the redundancy test (no stat was dropped: each
one helped 2024 validation).
"""
from __future__ import annotations

import math
from functools import lru_cache
from statistics import mean, pstdev

import data

FIELDS = [
    "points_for", "points_against", "margin", "tds", "rz_trips", "rz_tds", "rush_att", "rush_yds",
    "rush_tds", "pass_tds", "dropbacks", "completions", "pass_yds", "sacks_taken", "ints_thrown",
    "fumbles", "fumbles_lost", "def_passes_defended", "def_tackles_solo", "def_tackles_total",
    "third_down_att", "third_down_conv", "drives",
]

# stat -> (numerator, denominator). "opp:" reads the opponent's row for that game; "G" counts games.
STATS: dict[str, tuple[str, str]] = {
    "ppg": ("points_for", "G"),
    "tds_pg": ("tds", "G"),
    "margin_pg": ("margin", "G"),
    "rz_td_pct": ("rz_tds", "rz_trips"),
    "rush_ypg": ("rush_yds", "G"),
    "rush_td_pct": ("rush_tds", "off_tds"),
    "comp_pg": ("completions", "G"),
    "pass_ypg": ("pass_yds", "G"),
    "pass_tds_pg": ("pass_tds", "G"),
    "sack_pct": ("sacks_taken", "dropbacks"),
    "ints_pg": ("ints_thrown", "G"),
    "fumbles_pg": ("fumbles", "G"),
    "opp_ppg": ("points_against", "G"),
    "opp_tds_pg": ("opp:tds", "G"),
    "opp_rz_td_pct": ("opp:rz_tds", "opp:rz_trips"),
    "opp_rush_ypg": ("opp:rush_yds", "G"),
    "opp_rush_tds_pg": ("opp:rush_tds", "G"),
    "opp_rush_td_pct": ("opp:rush_tds", "opp:off_tds"),
    "opp_comp_pg": ("opp:completions", "G"),
    "opp_pass_ypg": ("opp:pass_yds", "G"),
    "opp_pass_tds_pg": ("opp:pass_tds", "G"),
    "def_sack_pct": ("opp:sacks_taken", "opp:dropbacks"),
    "def_ints_pg": ("opp:ints_thrown", "G"),
    "def_pd_pg": ("def_passes_defended", "G"),
    "def_tackles_pg": ("def_tackles_total", "G"),
    "def_solo_pg": ("def_tackles_solo", "G"),
}

# unit -> [(stat, side, sign)]. side "off" = the attacking team's profile, "def" = the defending
# team's profile. sign makes + good for the attacking offense.
UNITS: dict[str, list[tuple[str, str, int]]] = {
    "SCORING": [("ppg", "off", 1), ("tds_pg", "off", 1), ("margin_pg", "off", 1),
                ("opp_ppg", "def", 1), ("opp_tds_pg", "def", 1), ("margin_pg", "def", -1)],
    "RED ZONE": [("rz_td_pct", "off", 1), ("opp_rz_td_pct", "def", 1)],
    "GROUND": [("rush_ypg", "off", 1), ("rush_td_pct", "off", 1), ("opp_rush_ypg", "def", 1),
               ("opp_rush_tds_pg", "def", 1), ("opp_rush_td_pct", "def", 1)],
    "AIR": [("comp_pg", "off", 1), ("pass_ypg", "off", 1), ("pass_tds_pg", "off", 1),
            ("opp_comp_pg", "def", 1), ("opp_pass_ypg", "def", 1), ("opp_pass_tds_pg", "def", 1)],
    "BALL SECURITY": [("sack_pct", "off", -1), ("ints_pg", "off", -1), ("fumbles_pg", "off", -1),
                      ("def_sack_pct", "def", -1), ("def_ints_pg", "def", -1), ("def_pd_pg", "def", -1),
                      ("def_tackles_pg", "def", 1), ("def_solo_pg", "def", 1)],
}
UNIT_NAMES = list(UNITS)


def entry_key(stat: str, side: str) -> str:
    return f"{stat}:{side}"


ALL_ENTRIES = [entry_key(s, side) for unit in UNITS.values() for s, side, _ in unit]


# ---------------------------------------------------------------------------
# Pond -> per-game rows with the opponent's values attached
# ---------------------------------------------------------------------------

def game_rows(raw: list[dict]) -> list[dict]:
    rows = []
    for r in raw:
        g = {"season": int(r["season"]), "week": int(r["week"]), "game_id": r["game_id"],
             "team": r["team"], "opponent": r["opponent"], "home": int(r["home"]), "win": float(r["win"])}
        for f in FIELDS:
            g[f] = float(r[f] or 0)
        g["off_tds"] = g["rush_tds"] + g["pass_tds"]
        rows.append(g)
    by_key = {(g["game_id"], g["team"]): g for g in rows}
    for g in rows:
        opp = by_key[(g["game_id"], g["opponent"])]
        for f in FIELDS + ["off_tds"]:
            g[f"opp:{f}"] = opp[f]
    return rows


@lru_cache(maxsize=1)
def pond_rows() -> list[dict]:
    return game_rows(data.load("team_game_stats"))


def _num_den(g: dict, stat: str) -> tuple[float, float]:
    n, d = STATS[stat]
    return g[n], (1.0 if d == "G" else g[d])


# ---------------------------------------------------------------------------
# Profiles: shrunk season-to-date rates as of the start of a week
# ---------------------------------------------------------------------------

def season_totals(rows: list[dict], season: int, before_week: int | None = None) -> dict[str, dict[str, list[float]]]:
    """team -> stat -> [num, den] summed over that team's games in season (optionally before a week)."""
    out: dict[str, dict[str, list[float]]] = {}
    for g in rows:
        if g["season"] != season or (before_week is not None and g["week"] >= before_week):
            continue
        t = out.setdefault(g["team"], {s: [0.0, 0.0] for s in STATS})
        t.setdefault("_games", [0.0, 0.0])[0] += 1
        for s in STATS:
            n, d = _num_den(g, s)
            t[s][0] += n
            t[s][1] += d
    return out


def priors(prev: dict[str, dict[str, list[float]]], r: float) -> dict[str, dict[str, tuple[float, float]]]:
    """Per-game prior num/den for each team: last season regressed r of the way to the league."""
    if not prev:
        return {}
    league = {s: (mean(t[s][0] / t["_games"][0] for t in prev.values()),
                  mean(t[s][1] / t["_games"][0] for t in prev.values())) for s in STATS}
    out = {}
    for team, t in prev.items():
        gms = t["_games"][0]
        out[team] = {s: ((1 - r) * t[s][0] / gms + r * league[s][0],
                         (1 - r) * t[s][1] / gms + r * league[s][1]) for s in STATS}
    out["_league"] = league
    return out


def profiles(cur: dict[str, dict[str, list[float]]], prior: dict, teams: list[str], k: float) -> dict[str, dict[str, float]]:
    out = {}
    for team in teams:
        t = cur.get(team, {})
        p = prior.get(team) or prior.get("_league")
        vals = {}
        for s in STATS:
            num, den = t.get(s, [0.0, 0.0])
            pn, pd = p[s] if p else (0.0, 0.0)
            tot = den + k * pd
            vals[s] = (num + k * pn) / tot if tot else 0.0
        out[team] = vals
    return out


def zscores(prof: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    z: dict[str, dict[str, float]] = {t: {} for t in prof}
    for s in STATS:
        vals = [p[s] for p in prof.values()]
        mu, sd = mean(vals), pstdev(vals)
        for t, p in prof.items():
            z[t][s] = (p[s] - mu) / sd if sd else 0.0
    return z


def unit_edges(z: dict[str, dict[str, float]], attacker: str, defender: str, active: set[str]) -> dict[str, float]:
    edges = {}
    for unit, entries in UNITS.items():
        vals = [sign * z[attacker if side == "off" else defender][s]
                for s, side, sign in entries if entry_key(s, side) in active]
        edges[unit] = mean(vals) if vals else 0.0
    return edges


def week_z(rows: list[dict], season: int, week: int, k: float, r: float) -> dict[str, dict[str, float]] | None:
    """League z-scores as of the start of a week; None when there is nothing to judge from yet."""
    cur = season_totals(rows, season, before_week=week)
    prev = season_totals(rows, season - 1)
    if prev:
        prior = priors(prev, r)
    elif cur:
        # First season in the pond: shrink toward the league average of games already played.
        prior = priors(cur, 1.0)
    else:
        return None
    teams = sorted({g["team"] for g in rows if g["season"] == season} | set(cur))
    return zscores(profiles(cur, prior, teams, k))


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Fitted model
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def model() -> dict:
    rows = data.load("matchup_model")
    if not rows:
        return {}
    m: dict = {"active": set(), "beta": {}}
    for r in rows:
        p, v = r["param"], r["value"]
        if p == "active":
            m["active"].add(v)
        elif p.startswith("beta:"):
            m["beta"][p[5:]] = float(v)
        else:
            try:
                m[p] = float(v)
            except ValueError:
                m[p] = v
    return m


def predict_margin(edges_home: dict[str, float], edges_away: dict[str, float], home_flag: int, m: dict) -> float:
    return m["home"] * home_flag + sum(m["beta"][u] * (edges_home[u] - edges_away[u]) for u in UNIT_NAMES)


# ---------------------------------------------------------------------------
# This week's slate
# ---------------------------------------------------------------------------

def team_records() -> dict[str, tuple[int, int, int]]:
    """W-L-T from schedule.csv finals (the lake's match-page source)."""
    rec: dict[str, list[int]] = {}
    for g in data.load("schedule"):
        hs, as_ = g.get("home_score"), g.get("away_score")
        if not hs or not as_:
            continue
        h, a = int(float(hs)), int(float(as_))
        for team, pf, pa in ((g["home_team"], h, a), (g["away_team"], a, h)):
            r = rec.setdefault(team, [0, 0, 0])
            r[0 if pf > pa else 1 if pf < pa else 2] += 1
    return {t: tuple(v) for t, v in rec.items()}


def is_losing(team: str) -> bool:
    w, l, _ = team_records().get(team, (0, 0, 0))
    return w < l


@lru_cache(maxsize=1)
def slate() -> list[dict]:
    import jimmy

    m = model()
    games = {g["game_id"]: g for g in jimmy.next_game_by_team().values()}
    if not m or not games:
        return []
    season = int(next(iter(games.values()))["season"])
    week = int(next(iter(games.values()))["week"])
    z = week_z(pond_rows(), season, week, m["k"], m["r"])
    if z is None:
        return []
    records = team_records()

    out = []
    for g in sorted(games.values(), key=lambda g: (g["game_date"], g.get("game_time_local", ""), g["game_id"])):
        home, away = g["home_team"], g["away_team"]
        if home not in z or away not in z:
            continue
        eh = unit_edges(z, home, away, m["active"])
        ea = unit_edges(z, away, home, m["active"])
        home_flag = 0 if g.get("location") == "Neutral" else 1
        margin = predict_margin(eh, ea, home_flag, m)
        p_home = phi(margin / m["sigma"])
        out.append({
            "gameId": g["game_id"], "season": season, "week": week,
            "gameDate": g["game_date"], "gameTime": g.get("game_time_local", ""),
            "home": {"team": home, "record": "-".join(map(str, records.get(home, (0, 0, 0)))),
                     "losing": is_losing(home), "edges": {u: round(v, 2) for u, v in eh.items()}},
            "away": {"team": away, "record": "-".join(map(str, records.get(away, (0, 0, 0)))),
                     "losing": is_losing(away), "edges": {u: round(v, 2) for u, v in ea.items()}},
            "predictedWinner": home if margin >= 0 else away,
            "winProbability": round(max(p_home, 1 - p_home), 3),
            "predictedMargin": round(abs(margin), 1),
        })
    return out


def edges_for_team(team: str) -> dict[str, float] | None:
    """This week's unit edges for a team's offense against its opponent's defense."""
    for game in slate():
        for side, other in (("home", "away"), ("away", "home")):
            if game[side]["team"] == team:
                return game[side]["edges"]
    return None

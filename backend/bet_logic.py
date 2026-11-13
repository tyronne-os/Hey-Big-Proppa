"""
BIG PROPPA BETTING LOGIC — the three rules.

Rule 1 — "Always know the weak defenses"
    Scan the day's matchups for the BOTTOM 10% in each defensive category:
      * can't stop the run  (rush yds allowed)
      * can't stop the pass (pass yds allowed / completion pct / yds per target)
      * gives up yards & points (total yds, points allowed)

Rule 2 — "The 15/10 Rule"
    Hunt matchups where a TOP-15% offense faces a BOTTOM-10% defense. That's where
    the profitable parlays live — the bottom-10% defense triggers the +6 point
    probability bump, so the joint probability is inflated.

Rule 3 — "Something to live for"
    Only bet on teams with a winning record / a reason to compete: playoff race,
    division race, undefeated, or a live storyline. Losers lose; we bet on teams
    with a bright future.

Data: lake/gold/nfl/team_game_stats.csv (offense/defense per game, 2026)
      lake/gold/nfl/team_defense_season.csv (defensive ranks + records)
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _load(name: str) -> list[dict]:
    with open(BASE / name) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Per-team offensive + defensive season averages (2026), from team_game_stats.
# A team's DEFENSE is what its OPPONENT gains; a team's OFFENSE is what it gains.
# ---------------------------------------------------------------------------
def _team_stats() -> dict[str, dict]:
    rows = _load("team_game_stats.csv")
    # group rows by game_id so we can read each team's OFFENSE and the OPPONENT's
    # offense (which is what the team's DEFENSE allowed).
    by_game: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("season") != "2026":
            continue
        by_game[r.get("game_id", "")].append(r)

    off = defaultdict(lambda: defaultdict(list))   # team -> cat -> [per-game gained]
    dfn = defaultdict(lambda: defaultdict(list))   # team -> cat -> [per-game allowed]
    rec = defaultdict(lambda: {"wins": 0, "losses": 0})
    for gid, game_rows in by_game.items():
        if len(game_rows) < 2:
            continue
        # one row per team in the game
        by_team = {r.get("team"): r for r in game_rows}
        for team, r in by_team.items():
            opp_row = by_team.get(r.get("opponent"))
            if not opp_row:
                continue
            # OFFENSE: what this team gained
            off[team]["rush"].append(_num(r.get("rush_yds")))
            off[team]["pass"].append(_num(r.get("pass_yds")))
            off[team]["pts"].append(_num(r.get("points_for")))
            off[team]["tot"].append(_num(r.get("rush_yds")) + _num(r.get("pass_yds")))
            # DEFENSE: what the OPPONENT gained against this team
            dfn[team]["rush"].append(_num(opp_row.get("rush_yds")))
            dfn[team]["pass"].append(_num(opp_row.get("pass_yds")))
            dfn[team]["pts"].append(_num(opp_row.get("points_for")))
            dfn[team]["tot"].append(_num(opp_row.get("rush_yds")) + _num(opp_row.get("pass_yds")))
            rec[team]["wins"] += _num(r.get("win"))
            rec[team]["losses"] += 1 - _num(r.get("win"))

    out = {}
    for team in set(off) | set(dfn):
        out[team] = {
            "off": {c: mean(v) for c, v in off[team].items() if v},
            "def": {c: mean(v) for c, v in dfn[team].items() if v},
            "record": dict(rec[team]),
        }
    return out


# ---------------------------------------------------------------------------
# Rule 1 + Rule 2 — rankings and the 15/10 matchup hunt.
# ---------------------------------------------------------------------------
def _rank(teams: dict[str, float], ascending: bool, pct: float) -> set[str]:
    """Return the top/bottom `pct` of teams by a metric."""
    n = len(teams)
    if n == 0:
        return set()
    ranked = sorted(teams.items(), key=lambda kv: kv[1], reverse=ascending)
    cnt = max(1, int(n * pct))
    return {t for t, _ in ranked[:cnt]}


def _bottom10(team_stats: dict[str, dict], category: str) -> set[str]:
    """Bottom-10% defenses for a category (worst = highest yards/points allowed)."""
    metric = {
        "rush": lambda s: s["def"].get("rush", 0),
        "pass": lambda s: s["def"].get("pass", 0),
        "pts": lambda s: s["def"].get("pts", 0),
        "tot": lambda s: s["def"].get("tot", 0),
    }[category]
    vals = {t: metric(s) for t, s in team_stats.items()}
    return _rank(vals, ascending=True, pct=0.10)  # worst 10% = highest allowed


def _top15(team_stats: dict[str, dict], category: str) -> set[str]:
    """Top-15% offenses for a category (best = highest gained)."""
    metric = {
        "rush": lambda s: s["off"].get("rush", 0),
        "pass": lambda s: s["off"].get("pass", 0),
        "pts": lambda s: s["off"].get("pts", 0),
        "tot": lambda s: s["off"].get("tot", 0),
    }[category]
    vals = {t: metric(s) for t, s in team_stats.items()}
    return _rank(vals, ascending=False, pct=0.15)  # best 15% = highest gained


# ---------------------------------------------------------------------------
# Rule 3 — "Something to live for": winning record / playoff / division race.
# ---------------------------------------------------------------------------
def _living(team_stats: dict[str, dict]) -> set[str]:
    """Teams with a winning record (a reason to compete)."""
    out = set()
    for t, s in team_stats.items():
        w, l = s["record"].get("wins", 0), s["record"].get("losses", 0)
        if w > l:  # winning record
            out.add(t)
    return out


def _upcoming_opponents() -> dict[str, str]:
    """team abbr -> opponent for the upcoming slate, from the live ESPN scoreboard."""
    try:
        import espn
        opp: dict[str, str] = {}
        for g in espn.get_scoreboard() or []:
            if g.get("status") != "PRE":
                continue
            opp[g.get("away")] = g.get("home")
            opp[g.get("home")] = g.get("away")
        return opp
    except Exception:
        # fallback: last-played opponent
        return {r.get("team"): r.get("opponent") for r in _load("team_game_stats.csv") if r.get("season") == "2026"}


# ---------------------------------------------------------------------------
# The bet hunt: 15/10 matchups, filtered by "something to live for".
# ---------------------------------------------------------------------------
def bet_hunt(category: str = "all") -> dict:
    """Find the day's profitable matchups: TOP-15% offense vs BOTTOM-10% defense."""
    ts = _team_stats()
    if not ts:
        return {"sourceStatus": "error", "rows": []}

    living = _living(ts)
    cats = ["rush", "pass", "pts", "tot"] if category == "all" else [category]
    # Map each team -> its opponent from the LIVE Sunday slate (upcoming matchups).
    opp = _upcoming_opponents()

    # 15/10 matchups: offense of team A is TOP-15%, opponent B's defense is BOTTOM-10%.
    matchups = []
    for cat in cats:
        top15 = _top15(ts, cat)
        bot10 = _bottom10(ts, cat)
        for off_team in top15:
            if off_team not in living:
                continue  # Rule 3
            def_team = opp.get(off_team)
            if def_team in bot10:
                matchups.append({
                    "category": cat,
                    "offense": off_team,
                    "weakDefense": def_team,
                    "offTier": "TOP 15%",
                    "defTier": "BOTTOM 10%",
                    "living": True,
                })

    # Per-team defensive weakness tiers.
    summary = []
    for t, s in ts.items():
        def_tiers = {c: ("BOTTOM 10%" if t in _bottom10(ts, c) else "ok")
                     for c in ("rush", "pass", "pts", "tot")}
        off_tier = {c: ("TOP 15%" if t in _top15(ts, c) else "ok")
                    for c in ("rush", "pass", "pts", "tot")}
        summary.append({
            "team": t, "record": s["record"], "opponent": opp.get(t),
            "offense": {c: round(s["off"].get(c, 0), 1) for c in ("rush", "pass", "pts", "tot")},
            "defense": {c: round(s["def"].get(c, 0), 1) for c in ("rush", "pass", "pts", "tot")},
            "defTier": def_tiers, "offTier": off_tier,
            "somethingToLiveFor": t in living,
        })
    summary.sort(key=lambda x: sum(1 for c in x["defTier"].values() if c == "BOTTOM 10%"), reverse=True)
    return {
        "sourceStatus": "ok",
        "weakDefenses": {c: sorted(_bottom10(ts, c)) for c in ("rush", "pass", "pts", "tot")},
        "topOffenses": {c: sorted(_top15(ts, c)) for c in ("rush", "pass", "pts", "tot")},
        "living": sorted(living),
        "fifteenTenMatchups": matchups,
        "rows": summary,
    }


def bottom10_defenses() -> dict[str, list[str]]:
    """Which teams can't stop the run, can't stop the pass, give up yards/points."""
    ts = _team_stats()
    return {c: sorted(_bottom10(ts, c)) for c in ("rush", "pass", "pts", "tot")}


if __name__ == "__main__":
    res = bet_hunt()
    print("sourceStatus:", res["sourceStatus"])
    print("\n=== RULE 1 · BOTTOM-10% DEFENSES ===")
    for c, teams in res["weakDefenses"].items():
        print(f"  can't stop {c:<5}: {', '.join(teams) if teams else 'none'}")
    print("\n=== TOP-15% OFFENSES ===")
    for c, teams in res["topOffenses"].items():
        print(f"  top {c:<5}: {', '.join(teams) if teams else 'none'}")
    print("\n=== RULE 2 · THE 15/10 MATCHUPS (top-15 offense vs bottom-10 defense) ===")
    for m in res["fifteenTenMatchups"]:
        print(f"  {m['category'].upper():<5} {m['offense']} (TOP 15% off) vs {m['weakDefense']} (BOTTOM 10% def) ★")
    if not res["fifteenTenMatchups"]:
        print("  (none this week)")
    print("\n=== RULE 3 · SOMETHING TO LIVE FOR (winning record) ===")
    print(" ", ", ".join(res["living"]))
    print("\n=== WEAKEST DEFENSES (ranked by # of bottom-10 categories) ===")
    for r in res["rows"][:12]:
        weak = [c for c, t in r["defTier"].items() if t == "BOTTOM 10%"]
        flag = " ★ SOMETHING TO LIVE FOR" if r["somethingToLiveFor"] else ""
        print(f"  {r['team']} ({r['record'].get('wins')}-{r['record'].get('losses')}) weak={weak}{flag}")

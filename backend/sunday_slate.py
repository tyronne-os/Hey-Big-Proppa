"""
Sunday Slate Thesis Engine.

Applies docs/CORRELATED_PARLAY_THESIS.md to EVERY player in the upcoming Sunday slate,
using the Rotowire player/prop categories. For each player it computes the thesis-driven
probability for the Rotowire markets, applies the weak-defense bump (+6 when the opponent
defense is bottom-10% for the category), and emits ranked 2-leg correlated parlays.

Rotowire market slugs (the bet categories):
  anytd, comp, firsttd, intsthrown, kickpts, lasttd, longrush,
  passatt, passtd, passyds, recs, recyds, rushrec, rushyds, sack, tackle

Data: lake/gold/nfl/betterverse_cache/stats_{2022..2025}.csv + player_*_week.csv (2026)
      lake/gold/nfl/team_defense_season.csv (defensive ranks for the +6 bump)
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import data  # name->id bridge, player_dimension

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"

# market slug -> (source csv, stat column)
STAT_SOURCE = {
    "rushyds": ("player_rushing_week", "rushing_yards"),
    "recyds": ("player_receiving_week", "receiving_yards"),
    "recs": ("player_receiving_week", "receptions"),
    "passyds": ("player_passing_week", "passing_yards"),
    "passtd": ("player_passing_week", "passing_tds"),
    "passatt": ("player_passing_week", "attempts"),
    "comp": ("player_passing_week", "completions"),
    "intsthrown": ("player_passing_week", "passing_interceptions"),
    "carries": ("player_rushing_week", "carries"),
    "kickpts": ("player_kicking_week", "fg_made"),
    "sack": ("player_defense_week", "def_sacks"),
    "tackle": ("player_defense_week", "def_tackles_solo"),
}
ML_MARKETS = {"anytd", "firsttd", "lasttd"}
NO_STAT = {"longrush"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _load(name: str) -> list[dict]:
    with open(BASE / name) as f:
        return list(csv.DictReader(f))


def _name_to_id() -> dict[str, str]:
    dim = data.player_dimension()
    out: dict[str, str] = {}
    for pid, v in dim.items():
        n = data.normalize_name(v.get("name", ""))
        if n:
            out.setdefault(n, pid)
    return out


# --------------------------------------------------------- weak-defense bump
_DEF_FILE = BASE / "team_defense_season.csv"


def _bottom10() -> dict[str, set[str]]:
    with open(_DEF_FILE) as f:
        rows = list(csv.DictReader(f))
    out: dict[str, set[str]] = {}
    for rc, label in (("rank_scoring_defense", "scoring"), ("rank_sacks", "sacks"),
                      ("rank_interceptions", "ints"), ("rank_turnovers_created", "turnovers")):
        worst = sorted(rows, key=lambda r: int(r.get(rc) or 0), reverse=True)
        cnt = max(1, int(len(rows) * 0.10))
        out[label] = {r["team"].upper() for r in worst[:cnt]}
    return out


def defense_boost(opponent: str, category: str) -> float:
    cat = (category or "").lower()
    opp = (opponent or "").upper()
    b = _bottom10()
    if cat in ("recyds", "recs", "passyds", "passtd", "passatt", "comp", "intsthrown"):
        return 0.06 if (opp in b["scoring"] or opp in b["ints"]) else 0.0
    if cat in ("rushyds", "rushrec", "carries"):
        return 0.06 if (opp in b["scoring"] or opp in b["sacks"]) else 0.0
    if cat == "kickpts":
        return 0.06 if opp in b["scoring"] else 0.0
    return 0.0


# --------------------------------------------------------- per-player weekly
def _build(rows, key):
    out = defaultdict(dict)
    for r in rows:
        out[(r["player_id"], r.get("season"), r.get("week"))].update(key(r))
    return out


_rush = _build(_load("player_rushing_week.csv"),
               lambda r: {"rush_yds": _num(r.get("rushing_yards")), "rush_td": _num(r.get("rushing_tds"))})
_rec = _build(_load("player_receiving_week.csv"),
              lambda r: {"recs": _num(r.get("receptions")), "rec_yds": _num(r.get("receiving_yards")),
                         "rec_td": _num(r.get("receiving_tds")), "targets": _num(r.get("targets"))})
_scor = _build(_load("player_scoring_week.csv"),
               lambda r: {"total_td": _num(r.get("total_tds"))})


def _player_games(player_id: str) -> list[dict]:
    """2026 weekly rows for a player, merged across rushing/receiving/scoring."""
    weeks = set()
    for src in (_rush, _rec, _scor):
        weeks |= {(player_id, w, wk) for (p, w, wk) in src if p == player_id}
    g = {}
    for (p, w, wk) in weeks:
        if w == "2026":
            row = {}
            row.update(_rush.get((p, w, wk), {}))
            row.update(_rec.get((p, w, wk), {}))
            row.update(_scor.get((p, w, wk), {}))
            g[(w, wk)] = row
    return list(g.values())


def _player_opponent(player_id: str) -> str:
    """The player's team's Sunday opponent (from the live slate)."""
    dim = data.player_dimension().get(player_id, {})
    team = dim.get("team", "")
    opp = _SUNDAY_OPP.get(team.upper(), "")
    if opp:
        return opp
    return ""  # no Sunday game -> exclude


def _build_sunday_map() -> dict[str, str]:
    """team abbr -> Sunday opponent, from the live ESPN scoreboard."""
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
        return {}


_SUNDAY_OPP = _build_sunday_map()


def _hit_rate(games, fn) -> float:
    if not games:
        return 0.0
    return sum(1 for g in games if fn(g)) / len(games)


# --------------------------------------------------------- the thesis
def player_legs(player_id: str, name: str, team: str, position: str) -> list[dict]:
    """Thesis-driven probabilities for the Rotowire categories for one player (2026)."""
    games = _player_games(player_id)
    if len(games) < 4:
        return []
    n = len(games)
    opp = _player_opponent(player_id)
    legs = []

    # Receiving (WR/TE/RB): checkdown reaction 3+rec & 40 yds, and 5+rec & 60 yds
    if position in ("WR", "TE", "RB", "FB"):
        legs.append(_mk(player_id, name, team, opp, "recs", "3+ receptions",
                        _hit_rate(games, lambda g: g.get("recs", 0) >= 3), n))
        legs.append(_mk(player_id, name, team, opp, "recyds", "3+ rec & 40 yds",
                        _hit_rate(games, lambda g: g.get("recs", 0) >= 3 and g.get("rec_yds", 0) >= 40), n))
        legs.append(_mk(player_id, name, team, opp, "recyds", "5+ rec & 60 yds",
                        _hit_rate(games, lambda g: g.get("recs", 0) >= 5 and g.get("rec_yds", 0) >= 60), n))
    # Rushing (RB/FB): bell-cow 70+ rush yds & TD
    if position in ("RB", "FB"):
        legs.append(_mk(player_id, name, team, opp, "rushyds", "70+ rush yds",
                        _hit_rate(games, lambda g: g.get("rush_yds", 0) >= 70), n))
        legs.append(_mk(player_id, name, team, opp, "rushyds", "70+ rush yds & 1+ TD",
                        _hit_rate(games, lambda g: g.get("rush_yds", 0) >= 70 and g.get("total_td", 0) >= 1), n))
    # Passing (QB): 250+ pass yds & 2+ TD
    if position == "QB":
        legs.append(_mk(player_id, name, team, opp, "passyds", "250+ pass yds",
                        _hit_rate(games, lambda g: g.get("pass_yds", 0) >= 250), n))
        legs.append(_mk(player_id, name, team, opp, "passtd", "2+ pass TD",
                        _hit_rate(games, lambda g: g.get("pass_td", 0) >= 2), n))
    # Anytime TD for skill positions
    if position in ("RB", "FB", "WR", "TE"):
        legs.append(_mk(player_id, name, team, opp, "anytd", "anytime TD",
                        _hit_rate(games, lambda g: g.get("total_td", 0) >= 1), n))

    # apply weak-defense bump and keep only meaningful legs
    for leg in legs:
        leg["hit"] = round(min(1.0, leg["hit"] + defense_boost(opp, leg["category"])), 3)
        leg["opp"] = opp
    legs = [l for l in legs if l["hit"] >= 0.50]
    legs.sort(key=lambda l: -l["hit"])
    return legs


def _mk(pid, name, team, opp, category, label, p, games):
    return {"player_id": pid, "name": name, "team": team, "category": category,
            "label": label, "hit": p, "games": games}


def slate_tickets(min_hit: float = 0.50) -> list[dict]:
    """Build 2-leg correlated parlays across the slate (same player = shared driver)."""
    name2id = _name_to_id()
    dim = data.player_dimension()
    all_legs: list[dict] = []
    for pid, info in dim.items():
        if info.get("position") not in ("QB", "RB", "FB", "WR", "TE"):
            continue
        nm = info.get("name", "")
        team = info.get("team", "")
        if not _SUNDAY_OPP.get(team.upper(), ""):
            continue  # not playing Sunday
        legs = player_legs(pid, nm, team, info.get("position", ""))
        all_legs.extend(legs)

    # Pair legs from the same player into 2-leg tickets.
    by_player = defaultdict(list)
    for l in all_legs:
        by_player[l["player_id"]].append(l)
    tickets = []
    for pid, plist in by_player.items():
        plist.sort(key=lambda x: -x["hit"])
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                a, b = plist[i], plist[j]
                if a["category"] == b["category"]:
                    continue
                joint = a["hit"] * b["hit"]
                if joint >= 0.60:
                    tickets.append({
                        "player": a["name"], "team": a["team"],
                        "legA": {"category": a["category"], "label": a["label"], "hit": a["hit"]},
                        "legB": {"category": b["category"], "label": b["label"], "hit": b["hit"]},
                        "jointP": round(joint, 3), "opp": a["opp"],
                    })
    tickets.sort(key=lambda t: -t["jointP"])
    return tickets


def top(n: int = 50) -> dict:
    tickets = slate_tickets()
    return {"count": len(tickets), "rows": tickets[:n]}


if __name__ == "__main__":
    res = top(40)
    print(f"Total qualifying 2-leg slate tickets: {res['count']}")
    print("\n=== TOP SLATE PARLAYS (thesis, Rotowire categories) ===")
    for t in res["rows"]:
        a, b = t["legA"], t["legB"]
        print(f"  {t['player']:<22} ({t['team']}) {a['label']} ({a['hit']:.0%}) + "
              f"{b['label']} ({b['hit']:.0%})  JOINT={t['jointP']:.0%} vs {t['opp']}")

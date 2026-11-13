"""
Unified Leg Builder — builds two-leg parlays from the FULL range of bet options
the sportsbooks / rotowire data expose.

Market slugs available in the lake (prop_best_price.csv / prop_line_rotowire.csv):
  anytd, comp, firsttd, intsthrown, kickpts, lasttd, longrush,
  passatt, passtd, passyds, recs, recyds, rushrec, rushyds, sack, tackle

Every option is resolved against its ACTUAL sportsbook line (from prop_best_price),
hit-rate is measured against the lake (matched by player name -> GSIS id), and the
correlated-parlay rubric (docs/CORRELATED_PARLAY_THESIS.md) gates which two legs pair.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

import data  # name->id bridge, normalize_name, player_dimension

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"

# market slug -> (source csv, stat column). ML markets use prices, not stats.
STAT_SOURCE = {
    "rushyds":  ("player_rushing_week",   "rushing_yards"),
    "recyds":   ("player_receiving_week", "receiving_yards"),
    "recs":     ("player_receiving_week", "receptions"),
    "passyds":  ("player_passing_week",   "passing_yards"),
    "passtd":   ("player_passing_week",   "passing_tds"),
    "passatt":  ("player_passing_week",   "attempts"),
    "comp":     ("player_passing_week",   "completions"),
    "intsthrown": ("player_passing_week", "passing_interceptions"),
    "carries":  ("player_rushing_week",   "carries"),
    "rushrec":  ("player_scrimmage_week", "rushing_yards"),   # + receiving_yards added below
    "kickpts":  ("player_kicking_week",   "fg_made"),
    "sack":     ("player_defense_week",   "def_sacks"),
    "tackle":   ("player_defense_week",   "def_tackles_solo"),
}
ML_MARKETS = {"anytd", "firsttd", "lasttd"}
NO_STAT = {"longrush"}  # no lake column; skip unless we add a proxy


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


def _player_games(market: str, player_id: str) -> list[dict]:
    """Return weekly {week, opponent, value} for a player+market from the lake."""
    if market in ML_MARKETS or market in NO_STAT:
        return []
    if market == "rushrec":
        rec_by_key = {r["player_id"] + "_" + r["game_id"]: r for r in _load("player_receiving_week.csv")}
        out = []
        for r in _load("player_rushing_week.csv"):
            if r.get("player_id") != player_id:
                continue
            rr = rec_by_key.get(r["player_id"] + "_" + r["game_id"], {})
            out.append({"week": r.get("week"), "opponent": r.get("opponent_team", ""),
                        "value": _num(r.get("rushing_yards")) + _num(rr.get("receiving_yards"))})
        return out
    src, col = STAT_SOURCE.get(market, (None, None))
    if src is None:
        return []
    out = []
    for r in _load(src + ".csv"):
        if r.get("player_id") != player_id:
            continue
        out.append({"week": r.get("week"), "opponent": r.get("opponent_team", ""),
                    "value": _num(r.get(col))})
    return out


def _player_opponent(player_id: str, market: str) -> str:
    """The opponent the player's team faces (most recent week in the lake)."""
    games = _player_games(market, player_id)
    if games:
        return games[-1].get("opponent", "")
    return ""


def _sportsbook_options() -> list[dict]:
    options = []
    with open(BASE / "prop_best_price.csv") as f:
        for r in csv.DictReader(f):
            market = r.get("market_slug", "")
            line = r.get("line")
            if not market or not line:
                continue
            options.append({
                "name": r.get("player_name", ""),
                "market": market, "line": float(line),
                "over_price": _num(r.get("best_over_price")),
                "under_price": _num(r.get("best_under_price")),
                "num_books": int(r.get("num_books") or 0),
            })
    return options


def _hit_rate(games: list[dict], line: float, over: bool) -> float:
    if not games:
        return 0.0
    if over:
        hits = sum(1 for g in games if g["value"] >= line)
    else:
        hits = sum(1 for g in games if g["value"] <= line)
    return hits / len(games)


# ---------------------------------------------------- weak-defense bump (+6)
# When the offense faces a defense ranked in the BOTTOM 10% for the bet category,
# add 6 points to the joint probability. rank 1 = best, 32 = worst; bottom 10% = worst 3.
_DEF_SEASON_FILE = BASE / "team_defense_season.csv"


def _bottom10_defenses() -> dict[str, set[str]]:
    """Bottom-10% defensive teams by category: {label: set(team_abbr)}."""
    with open(_DEF_SEASON_FILE) as f:
        rows = list(csv.DictReader(f))
    out: dict[str, set[str]] = {}
    for rc, label in (("rank_scoring_defense", "scoring"), ("rank_sacks", "sacks"),
                      ("rank_interceptions", "ints"), ("rank_turnovers_created", "turnovers")):
        worst = sorted(rows, key=lambda r: int(r.get(rc) or 0), reverse=True)
        cnt = max(1, int(len(rows) * 0.10))
        out[label] = {r["team"].upper() for r in worst[:cnt]}
    return out


def defense_boost(opponent: str, category: str) -> float:
    """+0.06 if the opposing defense is bottom-10% for the bet category, else 0."""
    cat = (category or "").lower()
    opp = (opponent or "").upper()
    bottom = _bottom10_defenses()
    if cat in ("recyds", "recs", "passyds", "passtd", "passatt", "comp", "intsthrown"):
        if opp in bottom["scoring"] or opp in bottom["ints"]:
            return 0.06
    if cat in ("rushyds", "rushrec", "carries"):
        if opp in bottom["scoring"] or opp in bottom["sacks"]:
            return 0.06
    if cat == "kickpts":
        if opp in bottom["scoring"]:
            return 0.06
    return 0.0


def leg_builder(min_books: int = 2, min_hit: float = 0.70, min_games: int = 5) -> list[dict]:
    """Enumerate all bet options, score each leg, and pair correlated legs."""
    name2id = _name_to_id()
    options = _sportsbook_options()
    # Dedup by (normalized name, market): keep the most-bet line.
    best: dict[tuple[str, str], dict] = {}
    for o in options:
        n = data.normalize_name(o["name"])
        key = (n, o["market"])
        if key not in best or o["num_books"] > best[key]["num_books"]:
            best[key] = o

    legs = []
    for (n, market), o in best.items():
        if o["num_books"] < min_books:
            continue
        if market in ML_MARKETS or market in NO_STAT:
            continue
        pid = name2id.get(n)
        if not pid:
            continue
        games = _player_games(market, pid)
        if len(games) < min_games:
            continue
        over_hr = _hit_rate(games, o["line"], True)
        under_hr = _hit_rate(games, o["line"], False)
        if over_hr >= under_hr and over_hr >= min_hit:
            side, hr, price = "over", over_hr, o["over_price"]
        elif under_hr >= min_hit:
            side, hr, price = "under", under_hr, o["under_price"]
        else:
            continue
        # Weak-defense bump: the offense's opponent this week.
        opp = _player_opponent(pid, market)
        boost = defense_boost(opp, market)
        legs.append({
            "player_id": pid, "name": o["name"], "market": market,
            "line": o["line"], "side": side, "hit": round(hr, 3),
            "price": price, "games": len(games), "opp": opp, "boost": boost,
        })

    # Pair correlated legs into 2-leg tickets (same player => shared volume/driver).
    tickets = []
    by_player: dict[str, list[dict]] = defaultdict(list)
    for l in legs:
        by_player[l["player_id"]].append(l)
    for pid, plist in by_player.items():
        plist.sort(key=lambda x: x["hit"], reverse=True)
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                a, b = plist[i], plist[j]
                if a["market"] == b["market"]:
                    continue
                joint = a["hit"] * b["hit"]
                # weak-defense bump: +6 points when the opposing defense is bottom-10%
                # for the leg category (capped at 1.0).
                joint = min(1.0, joint + max(a["boost"], b["boost"]))
                if joint >= 0.60:
                    tickets.append({
                        "player": a["name"], "player_id": pid,
                        "legA": {"market": a["market"], "line": a["line"], "side": a["side"],
                                 "hit": a["hit"], "games": a["games"], "boost": a["boost"]},
                        "legB": {"market": b["market"], "line": b["line"], "side": b["side"],
                                 "hit": b["hit"], "games": b["games"], "boost": b["boost"]},
                        "jointP": round(joint, 3), "opp": a["opp"],
                    })
    tickets.sort(key=lambda t: t["jointP"], reverse=True)
    return tickets


def buildable(pct: float = 0.15, min_games: int = 5) -> list[dict]:
    """Top `pct` of qualifying tickets (by joint probability), reliability-floored."""
    tickets = leg_builder(min_games=min_games)
    if not tickets:
        return []
    n = max(1, int(len(tickets) * pct))
    return tickets[:n]


def full(min_games: int = 5) -> list[dict]:
    """Entire qualifying list (the full batch)."""
    return leg_builder(min_games=min_games)


if __name__ == "__main__":
    full_list = full()
    build = buildable(0.15)
    print(f"Total qualifying tickets: {len(full_list)}")
    print(f"Buildable (top 15%): {len(build)}")
    print("\n=== BUILDABLE TOP 15% TWO-LEG PARLAYS ===")
    for t in build:
        a, b = t["legA"], t["legB"]
        print(f"  {t['player']:<24} {a['market']} {a['side']} {a['line']} ({a['hit']:.0%}) + "
              f"{b['market']} {b['side']} {b['line']} ({b['hit']:.0%})  joint={t['jointP']:.0%}")

"""
Correlated Two-Leg Parlay Engine.

Implements the rubric from docs/CORRELATED_PARLAY_THESIS.md:

  Two legs are high-probability when BOTH legs share one upstream variable
  (defensive pass-rush strength, or a stable bell-cow volume constant), and that
  variable is forecastable and stable.

Mechanisms:
  A) Checkdown Reaction  : RB REC >= 3 AND REC Yds >= 25   (top pass-rush defense forces short throws)
  B) Bell-Cow + TD       : RB Rush > 70 AND Anytime TD     (volume constant feeds both yards and TD)
  C) Short-Pass Volume   : Offense Pass Attempts > line AND RB Receptions >= 2

Every ticket is EXACTLY two legs. No player-prop is reused across tickets.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"
CACHE = BASE / "betterverse_cache"

NUM = ("carries", "rushing_yards", "rushing_tds", "receptions", "targets",
       "receiving_yards", "receiving_tds")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------- defense pass rush
def defense_pressure(season: int) -> dict[str, float]:
    """Pressure per game for each defensive team: sacks + QB hits + 0.5*TFL.

    Only the 2026 defense week CSV carries these columns. For 2022-2025 we
    return {} and the rubric falls back to the bell-cow volume trigger.
    """
    if season != 2026:
        return {}
    fp = BASE / "player_defense_week.csv"
    if not fp.exists():
        return {}
    press: dict[str, float] = defaultdict(float)
    games: dict[str, set] = defaultdict(set)
    with open(fp) as f:
        for r in csv.DictReader(f):
            team = r.get("team", "")
            if not team:
                continue
            press[team] += (_num(r.get("def_sacks")) + _num(r.get("def_qb_hits"))
                            + 0.5 * _num(r.get("def_tackles_for_loss")))
            games[team].add(r.get("game_id", ""))
    return {t: press[t] / len(games[t]) for t in press if games[t]}


def _top_pressure_teams(n: int = 10) -> set[str]:
    pr = defense_pressure(2026)
    return set(sorted(pr, key=lambda t: -pr[t])[:n])


def _med(vals):
    s = sorted(vals)
    n = len(s)
    return (s[n // 2] + s[(n - 1) // 2]) / 2 if n else 0


def _corr(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    return num / (dx * dy) if dx * dy else 0.0


# ---------------------------------------------------------------- data load
def _load_cache(year: int, names: dict) -> list[dict]:
    out = []
    with open(CACHE / f"stats_{year}.csv") as f:
        for r in csv.DictReader(f):
            if r.get("position", "").upper() not in ("RB", "FB"):
                continue
            if int(r.get("week", 0) or 0) > 18:
                continue
            names[r["player_id"]] = r.get("player_display_name", "")
            out.append({"player_id": r["player_id"], "season": year,
                        "team": r.get("team", ""), "opponent_team": r.get("opponent_team", ""),
                        **{k: _num(r.get(k)) for k in NUM}})
    return out


def _load_2026(names: dict) -> list[dict]:
    with open(BASE / "player_receiving_week.csv") as f:
        rec = {r["player_id"] + "_" + r["game_id"]: r for r in csv.DictReader(f)}
    out = []
    with open(BASE / "player_rushing_week.csv") as f:
        for r in csv.DictReader(f):
            key = r["player_id"] + "_" + r["game_id"]
            rr = rec.get(key, {})
            out.append({"player_id": r["player_id"], "season": 2026,
                        "team": r.get("team", ""), "opponent_team": r.get("opponent_team", ""),
                        "carries": _num(r.get("carries")),
                        "rushing_yards": _num(r.get("rushing_yards")),
                        "rushing_tds": _num(r.get("rushing_tds")),
                        "receptions": _num(rr.get("receptions")),
                        "targets": _num(rr.get("targets")),
                        "receiving_yards": _num(rr.get("receiving_yards")),
                        "receiving_tds": _num(rr.get("receiving_tds"))})
    return out


def _all_rows() -> tuple[list[dict], dict]:
    names: dict = {}
    rows = []
    for y in (2023, 2024, 2025):
        rows += _load_cache(y, names)
    rows += _load_2026(names)
    return rows, names


# ---------------------------------------------------------------- rubric
def _joint(games, leg_a, leg_b) -> float:
    n = len(games)
    if n == 0:
        return 0.0
    hits = sum(1 for g in games if leg_a(g) and leg_b(g))
    return hits / n


def analyze() -> list[dict]:
    """Run the rubric over all RB seasons and return ranked 2-leg tickets."""
    rows, names = _all_rows()
    by_player: dict = defaultdict(list)
    for r in rows:
        by_player[(r["player_id"], r["season"])].append(r)

    # Top pass-rush defensive teams (defense-strength trigger).
    top_pressure = _top_pressure_teams(12)

    tickets = []
    for (pid, season), games in by_player.items():
        n = len(games)
        if n < 9:
            continue
        car = [g["carries"] for g in games]
        rec = [g["receptions"] for g in games]
        rush = [g["rushing_yards"] for g in games]
        tgt = [g["targets"] for g in games]
        mc, mr, mrs = _med(car), _med(rec), _med(rush)
        name = names.get(pid, pid)

        # Defense-strength trigger: share of games vs a top pass-rush defense.
        # For seasons without defense data this is 0, so the bell-cow trigger carries the score.
        opp_press = sum(1 for g in games if g.get("opponent_team", "") in top_pressure)
        def_share = opp_press / n
        def_trigger = 1.0 if def_share >= 0.35 else (0.5 if def_share >= 0.15 else 0.0)

        # Step 1 trigger: bell-cow volume constant (carries >= 10/game) OR defense trigger
        trigger = 1.0 if (mc >= 10 or def_trigger >= 1.0) else 0.0
        # Step 2 leg 1 (volume/reaction)
        if mc >= 10 and mr >= 2:
            leg1_score = 2.0
        elif mc >= 8 and mr >= 2:
            leg1_score = 1.5
        elif mc >= 10:
            leg1_score = 1.0
        else:
            leg1_score = 0.0

        # Mechanism B: rush > 70 + any TD
        pB = _joint(games, lambda g: g["rushing_yards"] > 70,
                    lambda g: (g["rushing_tds"] + g["receiving_tds"]) >= 1)
        # Mechanism A: rec >= 3 + rec yds >= 25
        pA = _joint(games, lambda g: g["receptions"] >= 3,
                    lambda g: g["receiving_yards"] >= 25)

        for label, p, legA, legB in (
            ("RUSH>70+TD", pB, f"rush>70", "1+TD"),
            ("REC3+25", pA, "rec>=3", "recYds>=25"),
        ):
            # Step 3 leg 2 score from joint hit-rate
            if p >= 0.60:
                leg2_score = 2.0
            elif p >= 0.50:
                leg2_score = 1.5
            elif p >= 0.40:
                leg2_score = 1.0
            else:
                leg2_score = 0.0
            # Step 4 correlation gate: both legs share the volume/pressure driver
            gate = 1.0 if (mc >= 10 or mr >= 2) else 0.0
            # Step 5 line sanity
            sane = 1.0 if (legA in ("rush>70",) and mrs >= 60) or legA == "rec>=3" else 0.5
            composite = trigger + leg1_score + leg2_score + gate + sane
            if trigger >= 0.5 and (leg1_score + leg2_score) >= 3.0 and gate == 1.0:
                tickets.append({
                    "season": season, "name": name, "pid": pid, "n": n,
                    "mechanism": label, "legA": legA, "legB": legB,
                    "jointP": round(p, 3), "composite": round(composite, 2),
                    "carries": mc, "rec": mr, "tgt": _med(tgt), "rush": mrs,
                    "defTrigger": round(def_trigger, 2),
                })

    tickets.sort(key=lambda t: (t["jointP"], t["composite"]), reverse=True)
    return tickets


def top(n: int = 25) -> dict:
    tickets = analyze()
    return {"count": len(tickets), "rows": tickets[:n]}


if __name__ == "__main__":
    res = top(30)
    print(f"Total qualifying tickets: {res['count']}")
    print("\n=== TOP CORRELATED TWO-LEG PARLAYS (rubric-scored) ===")
    for t in res["rows"]:
        print(f"  S{t['season']} {t['name']:<22} [{t['mechanism']}] "
              f"A:{t['legA']} + B:{t['legB']}  joint={t['jointP']:.0%} "
              f"score={t['composite']} car={t['carries']} rec={t['rec']} rush={t['rush']} "
              f"defTrig={t['defTrigger']:.2f} n={t['n']}")

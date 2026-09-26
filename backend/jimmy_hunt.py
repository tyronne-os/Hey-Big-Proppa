"""
Jimmy the Greek's daily prop hunt + defense-exploit engine.

Two modes in one call:
  hunt()        — full question slate → best picks per question + ranked parlays
  exploit()     — same picks filtered to legs where the opponent has a specific
                  defensive weakness, re-ranked for high-confidence piles.

Refreshes once per UTC calendar day (in-process cache, no cron needed).

Questions skipped (no lake column): longest reception, last TD scorer, first TD.
"""
from __future__ import annotations

import itertools
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache

import data
import jimmy
import jev

# ---------------------------------------------------------------------------
# Question slates  (position, market_slug, direction, line, label, def_unit)
# def_unit is which defense_ib_score component to weight for weakness scoring:
#   "coverage" | "run_stop" | "pressure" | "scoring" | None
# ---------------------------------------------------------------------------
LIST_ONE: list[tuple[str, str, str, float, str, str | None]] = [
    ("QB", "passtd",          "over",  2.5,   "QB Over 2.5 Pass TDs",               "coverage"),
    ("QB", "passyds",         "under", 225.5, "QB Under 225.5 Pass Yards",           None),
    ("QB", "intsthrown",      "over",  0.5,   "QB Over 0.5 Interceptions",           "pressure"),
    ("QB", "passatt",         "over",  32.5,  "QB Over 32.5 Pass Attempts",          "pressure"),
    ("RB", "rushyds",         "over",  75.5,  "RB Over 75.5 Rush Yards",             "run_stop"),
    ("RB", "anytd",           "over",  1.5,   "RB 2+ Touchdowns",                    "scoring"),
    ("RB", "carries",         "over",  15.5,  "RB Over 15.5 Carries",                "run_stop"),
    ("RB", "recs",            "under", 3.5,   "RB Under 3.5 Receptions",             None),
    ("RB", "rushrec",         "over",  85.5,  "RB Over 85.5 Rush+Rec Yards",         "run_stop"),
    ("WR", "recyds",          "over",  80.5,  "WR Over 80.5 Rec Yards",              "coverage"),
    ("WR", "recs",            "over",  6.5,   "WR Over 6.5 Receptions",              "coverage"),
    ("WR", "anytd",           "over",  0.5,   "WR Anytime TD",                       "scoring"),
    ("TE", "recyds",          "over",  60.5,  "TE Over 60.5 Rec Yards",              "coverage"),
    ("TE", "recs",            "over",  4.5,   "TE Over 4.5 Receptions",              "coverage"),
    ("TE", "anytd",           "over",  0.5,   "TE Anytime TD",                       "scoring"),
    ("K",  "kickpts",         "over",  7.5,   "Kicker Over 7.5 Kicking Points",      "scoring"),
    ("RB", "_combo_rb_td_rec","over",  0.0,   "RB 2+ TDs AND Over 2.5 Receptions",  "scoring"),
    ("QB", "_combo_qb_yd_td", "over",  0.0,   "QB Over 250 Pass Yards AND 2+ TDs",  "coverage"),
]

LIST_TWO: list[tuple[str, str, str, float, str, str | None]] = [
    ("QB", "_combo_qb_yd3td", "over",  0.0,   "QB Over 275.5 Yards AND 3+ TDs",     "coverage"),
    ("QB", "completions",     "under", 18.5,  "QB Under 18.5 Completions",           None),
    ("QB", "rushyds",         "over",  22.5,  "QB Over 22.5 Rush Yards",             "run_stop"),
    ("QB", "intsthrown",      "over",  1.5,   "QB 2+ Interceptions",                 "pressure"),
    ("RB", "_combo_rb3way",   "over",  0.0,   "RB 80.5 Rush + 3 Rec + 1 TD",        "run_stop"),
    ("RB", "rushrec",         "over",  100.5, "RB Over 100.5 Combined Yards",        "run_stop"),
    ("RB", "carries",         "under", 11.5,  "RB Under 11.5 Rush Attempts",         None),
    ("WR", "_combo_wr_yd_td", "over",  0.0,   "WR 80.5 Rec Yards AND 1+ TD",        "coverage"),
    ("WR", "recs",            "over",  7.5,   "WR Over 7.5 Receptions",              "coverage"),
    ("WR", "recyds",          "under", 39.5,  "WR Under 39.5 Rec Yards",             None),
    ("WR", "_combo_wr_2td",   "over",  0.0,   "WR 100+ Rec Yards AND 2+ TDs",       "coverage"),
    ("TE", "_combo_te_yd_rec","over",  0.0,   "TE 50.5 Rec Yards AND 4+ Receptions","coverage"),
    ("TE", "anytd",           "over",  1.5,   "TE 2+ Touchdowns",                    "scoring"),
    ("TE", "recs",            "under", 2.5,   "TE Under 2.5 Receptions",             None),
    ("K",  "kickpts",         "over",  7.5,   "Kicker Over 7.5 Kicking Points",      "scoring"),
    ("DEF","sacks",           "over",  0.5,   "Defensive Player Over 0.5 Sacks",     "pressure"),
    ("ANY","_combo_any_2td_rec","over",0.0,   "Any Player 2+ TDs AND 50.5 Rec Yds", "scoring"),
    ("QB", "_combo_qb_yd_rush","over", 0.0,   "QB Over 250 Pass Yards AND 25.5 Rush Yards","run_stop"),
]

ALL_QUESTIONS = LIST_ONE + LIST_TWO

JEV_CANDIDATES   = 3
MAX_PARLAYS      = 30
MIN_LEGS         = 2
MAX_LEGS         = 4      # 5-leg combos from 36 picks = 13M+, 4-leg = 58K — keep it fast
PARLAY_LEGS_FEED = 1      # how many picks per question feed the parlay builder
WEAKNESS_GATE    = 0.55   # opponent weakness score threshold to qualify as an "exploit" leg
MIN_COMBINED     = 0.45   # legs below this are excluded from parlay building

# ---------------------------------------------------------------------------
# Column maps for weekly stat tables
# ---------------------------------------------------------------------------
_SRC_COL: dict[str, tuple[str, str]] = {
    "passyds":     ("player_passing_week",   "passing_yards"),
    "passtd":      ("player_passing_week",   "passing_tds"),
    "passatt":     ("player_passing_week",   "attempts"),
    "completions": ("player_passing_week",   "completions"),
    "intsthrown":  ("player_passing_week",   "passing_interceptions"),
    "rushyds":     ("player_rushing_week",   "rushing_yards"),
    "carries":     ("player_rushing_week",   "carries"),
    "recyds":      ("player_receiving_week", "receiving_yards"),
    "recs":        ("player_receiving_week", "receptions"),
    "anytd":       ("player_scoring_week",   "total_tds"),
}


def _weekly_values(player_id: str, market_slug: str) -> list[float]:
    if market_slug in ("rushrec", "_combo_rb3way"):
        rush = {r["week"]: float(r.get("rushing_yards") or 0)
                for r in data.load("player_rushing_week") if r.get("player_id") == player_id}
        rec  = {r["week"]: float(r.get("receiving_yards") or 0)
                for r in data.load("player_receiving_week") if r.get("player_id") == player_id}
        weeks = sorted(set(rush) | set(rec))
        return [rush.get(w, 0.0) + rec.get(w, 0.0) for w in weeks]

    if market_slug == "kickpts":
        rows = [r for r in data.load("player_scoring_week") if r.get("player_id") == player_id]
        return [float(r.get("fg_made") or 0) * 3 + float(r.get("pat_made") or 0) for r in rows]

    if market_slug == "sacks":
        # individual_sacks has season totals; use sacks/games as average
        rows = [r for r in data.load("individual_sacks") if r.get("player_id") == player_id]
        if not rows:
            return []
        row = rows[0]
        games = max(1, float(row.get("games") or 1))
        return [float(row.get("sacks") or 0) / games]

    entry = _SRC_COL.get(market_slug)
    if not entry:
        return []
    src, col = entry
    return [float(r.get(col) or 0)
            for r in data.load(src) if r.get("player_id") == player_id]


def _hit_rate(player_id: str, market_slug: str, line: float, direction: str) -> float | None:
    vals = _weekly_values(player_id, market_slug)[-10:]
    if not vals:
        return None
    hits = sum(1 for v in vals if (v >= line if direction == "over" else v < line))
    return round(hits / len(vals), 3)


# ---------------------------------------------------------------------------
# Defense weakness scoring
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _def_scores() -> dict[str, dict]:
    """team → defense_ib_score row as floats."""
    out = {}
    for row in data.load("defense_ib_score"):
        team = row.get("team")
        if not team:
            continue
        parsed = {}
        for k, v in row.items():
            if k == "team" or not v:
                continue
            try:
                parsed[k] = float(v)
            except (ValueError, TypeError):
                pass
        out[team] = parsed
    return out


_DEF_UNIT_COL = {
    "coverage": "coverage_component",
    "run_stop": "run_stop_component",
    "pressure": "pressure_component",
    "scoring":  "scoring_component",
}


def defense_weakness(opponent: str | None, def_unit: str | None) -> float | None:
    """
    0–1 score for how weak the opponent is for the given unit.
    1.0 = maximally weak (great spot), 0.0 = lockdown defense.
    Uses the defense_ib_score component (0–100), inverted and normalized.
    Returns None when no data or no relevant unit.
    """
    if not opponent or not def_unit:
        return None
    col = _DEF_UNIT_COL.get(def_unit)
    if not col:
        return None
    row = _def_scores().get(opponent)
    if not row or col not in row:
        return None
    return round((100.0 - row[col]) / 100.0, 3)


# ---------------------------------------------------------------------------
# Roster helpers
# ---------------------------------------------------------------------------
def _slate_roster() -> dict[str, list[dict]]:
    dim   = data.player_dimension()
    slate = jimmy.next_game_by_team()
    out: dict[str, list[dict]] = {}

    for pid, info in dim.items():
        team = info.get("team", "")
        pos  = (info.get("position") or "").upper()
        if not team or not pos or team not in slate:
            continue
        game = slate[team]
        opp  = game["away_team"] if game["home_team"] == team else game["home_team"]
        out.setdefault(pos, []).append({"player_id": pid, "name": info["name"],
                                        "team": team, "opponent": opp, "position": pos})

    # Kickers from player_scoring_week (fg_made ever > 0)
    kicker_ids = {r["player_id"] for r in data.load("player_scoring_week")
                  if float(r.get("fg_made") or 0) > 0}
    for pid in kicker_ids:
        if pid in dim:
            team = dim[pid].get("team", "")
            if team in slate:
                game = slate[team]
                opp  = game["away_team"] if game["home_team"] == team else game["home_team"]
                entry = {"player_id": pid, "name": dim[pid]["name"],
                         "team": team, "opponent": opp, "position": "K"}
                if entry not in out.get("K", []):
                    out.setdefault("K", []).append(entry)

    # Defensive pass-rushers from individual_sacks
    def_players = {}
    for row in data.load("individual_sacks"):
        pid = row.get("player_id")
        if pid and pid not in def_players and float(row.get("sacks") or 0) > 0:
            team = row.get("team", "")
            if team in slate:
                game = slate[team]
                opp  = game["away_team"] if game["home_team"] == team else game["home_team"]
                def_players[pid] = {"player_id": pid,
                                    "name":      row.get("player_name", pid),
                                    "team":      team, "opponent": opp, "position": "DEF"}
    out["DEF"] = list(def_players.values())

    # ANY = all skill positions combined (for cross-position combo questions)
    out["ANY"] = out.get("RB", []) + out.get("WR", []) + out.get("TE", [])

    return out


@lru_cache(maxsize=1)
def _usage_idx() -> dict[str, float]:
    from jimmy import _usage_index
    return _usage_index()


# ---------------------------------------------------------------------------
# Jimmy scoring — handles all combo slugs
# ---------------------------------------------------------------------------
def _jimmy_for(pid: str, market_slug: str, direction: str, line: float) -> float | None:
    def jscr(mkt: str, dir_: str, ln: float) -> float | None:
        hr = _hit_rate(pid, mkt, ln, dir_)
        return jimmy.jimmy_score(pid, hr, mkt, dir_)

    combos: dict[str, list[tuple[str, str, float]]] = {
        "_combo_qb_yd_td":    [("passyds", "over", 250.0), ("passtd",  "over", 2.0)],
        "_combo_qb_yd3td":    [("passyds", "over", 275.5), ("passtd",  "over", 2.5)],
        "_combo_qb_yd_rush":  [("passyds", "over", 250.0), ("rushyds", "over", 25.5)],
        "_combo_rb_td_rec":   [("anytd",   "over", 1.5),   ("recs",    "over", 2.5)],
        "_combo_rb3way":      [("rushyds", "over", 80.5),  ("recs",    "over", 3.0),  ("anytd", "over", 0.5)],
        "_combo_wr_yd_td":    [("recyds",  "over", 80.5),  ("anytd",   "over", 0.5)],
        "_combo_wr_2td":      [("recyds",  "over", 100.0), ("anytd",   "over", 1.5)],
        "_combo_te_yd_rec":   [("recyds",  "over", 50.5),  ("recs",    "over", 4.0)],
        "_combo_any_2td_rec": [("anytd",   "over", 1.5),   ("recyds",  "over", 50.5)],
    }
    if market_slug in combos:
        scores = [s for s in (jscr(m, d, l) for m, d, l in combos[market_slug]) if s is not None]
        return round(min(scores), 3) if scores else None

    hr = _hit_rate(pid, market_slug, line, direction)
    return jimmy.jimmy_score(pid, hr, market_slug, direction)


# ---------------------------------------------------------------------------
# JEV call for one leg
# ---------------------------------------------------------------------------
def _ask_jev(player: dict, market_slug: str, direction: str, line: float,
             jimmy_val: float) -> float | None:
    if market_slug.startswith("_combo") or not jev.available():
        return None
    return jev.leg_probability(
        player_id    = player["player_id"],
        name         = player["name"],
        team         = player["team"],
        market_slug  = market_slug,
        direction    = direction,
        line         = line,
        hit_rate     = jimmy_val,
        usage_score  = _usage_idx().get(player["player_id"]),
        matchup_edge = jimmy.leg_edge(player["player_id"], market_slug, direction),
        opponent     = player.get("opponent"),
    )


# ---------------------------------------------------------------------------
# Daily cache
# ---------------------------------------------------------------------------
_cache:      dict | None = None
_cache_date: str         = ""


def hunt() -> dict:
    global _cache, _cache_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _cache and _cache_date == today:
        return _cache
    result      = _run_hunt(today)
    _cache      = result
    _cache_date = today
    return result


def invalidate_cache() -> None:
    global _cache, _cache_date
    _cache = None
    _cache_date = ""


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------
def _has_data(player_id: str, market_slug: str) -> bool:
    """Quick check: does this player have any rows in the relevant table?"""
    if market_slug.startswith("_combo"):
        return True  # combo scoring handles missing data internally
    vals = _weekly_values(player_id, market_slug)
    return len(vals) > 0


def _score_candidates(players: list[dict], pos: str, market_slug: str,
                      direction: str, line: float, label: str, def_unit: str | None) -> list[dict]:
    """Score all candidates for one question; returns sorted list of pick dicts."""
    pre: list[tuple[float, dict]] = []
    for p in players:
        if pos not in ("K", "DEF", "ANY") and not jimmy.eligible(p["player_id"]):
            continue
        if not _has_data(p["player_id"], market_slug):
            continue
        j = _jimmy_for(p["player_id"], market_slug, direction, line)
        if j is not None:
            pre.append((j, p))

    if not pre:
        return []

    pre.sort(key=lambda x: x[0], reverse=True)
    top = pre[:JEV_CANDIDATES]

    def _build(j_score: float, player: dict) -> dict:
        weak = defense_weakness(player.get("opponent"), def_unit)
        jev_score = _ask_jev(player, market_slug, direction, line, j_score)
        if jev_score is not None:
            combined = round((j_score + jev_score) / 2, 3)
        elif weak is not None:
            combined = round(j_score * 0.7 + weak * 0.3, 3)
        else:
            combined = j_score
        return {
            "playerId":        player["player_id"],
            "name":            player["name"],
            "team":            player["team"],
            "opponent":        player.get("opponent"),
            "position":        pos,
            "jimmyScore":      j_score,
            "jevScore":        jev_score,
            "defWeakness":     weak,
            "combinedScore":   combined,
        }

    if jev.available() and not market_slug.startswith("_combo"):
        with ThreadPoolExecutor(max_workers=JEV_CANDIDATES) as pool:
            futures = {pool.submit(_build, j, p): i for i, (j, p) in enumerate(top)}
            picks   = [None] * len(top)
            for fut in as_completed(futures):
                picks[futures[fut]] = fut.result()
        picks = [p for p in picks if p]
    else:
        picks = [_build(j, p) for j, p in top]

    picks.sort(key=lambda p: p["combinedScore"], reverse=True)
    return picks


def _build_parlays(legs: list[dict], mode: str) -> list[dict]:
    """Generate 2-5 leg parlays. mode='all' or 'exploit' (exploit legs only)."""
    if mode == "exploit":
        legs = [l for l in legs if (l.get("defWeakness") or 0) >= WEAKNESS_GATE]

    parlays: list[dict] = []
    for n in range(MIN_LEGS, MAX_LEGS + 1):
        for combo in itertools.combinations(legs, n):
            pids = [leg["playerId"] for leg in combo]
            if len(set(pids)) != len(pids):
                continue
            scores   = [leg["combinedScore"] for leg in combo]
            geo_mean = round(math.exp(sum(math.log(max(s, 0.01)) for s in scores) / n), 3)
            combined = round(math.prod(max(s, 0.01) for s in scores), 4)
            avg_weak = None
            weak_vals = [leg["defWeakness"] for leg in combo if leg.get("defWeakness") is not None]
            if weak_vals:
                avg_weak = round(sum(weak_vals) / len(weak_vals), 3)
            parlays.append({
                "legs":          n,
                "geometricMean": geo_mean,
                "combinedScore": combined,
                "avgDefWeakness": avg_weak,
                "label": " · ".join(
                    f"{leg['name']} {leg['direction'].upper()} {leg['line']} ({leg['market']})"
                    for leg in combo
                ),
                "picks": list(combo),
            })

    parlays.sort(key=lambda p: p["geometricMean"], reverse=True)
    return parlays[:MAX_PARLAYS]


def _run_hunt(today: str) -> dict:
    roster  = _slate_roster()
    q_rows  = []
    all_legs: list[dict] = []
    skipped = []

    for pos, market, direction, line, label, def_unit in ALL_QUESTIONS:
        players = roster.get(pos, [])
        if not players:
            skipped.append({"question": label, "reason": f"no {pos} on slate"})
            continue

        picks = _score_candidates(players, pos, market, direction, line, label, def_unit)
        if not picks:
            skipped.append({"question": label, "reason": "all players ineligible or no score"})
            continue

        q_rows.append({
            "question":  label,
            "position":  pos,
            "market":    market,
            "direction": direction,
            "line":      line,
            "defUnit":   def_unit,
            "players":   picks,
        })

        for pick in picks[:PARLAY_LEGS_FEED]:
            if pick["combinedScore"] >= MIN_COMBINED:
                all_legs.append({
                    **pick,
                    "question":  label,
                    "market":    market,
                    "direction": direction,
                    "line":      line,
                })

    return {
        "date":          today,
        "generatedAt":   datetime.now(timezone.utc).isoformat(),
        "jevActive":     jev.available(),
        "questions":     q_rows,
        "parlays":       _build_parlays(all_legs, "all"),
        "exploitParlays": _build_parlays(all_legs, "exploit"),
        "skipped":       skipped,
    }

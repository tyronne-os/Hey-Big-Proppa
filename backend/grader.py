"""
CRAZY HORSE Post-Game Grader — #15 + #25

Records CRAZY HORSE picks at generation time and grades them once
results are in. Writes to lake/gold/nfl/crazy_horse_picks.csv.

Grade logic:
  player_prop legs  → actual stat value from player_*_week.csv vs the line
  hot_dog / game    → result from schedule.csv (won, covered)

Season hit-rate dashboard reads the same CSV.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

_PICKS_FILE = Path(__file__).parent.parent / "lake/gold/nfl/crazy_horse_picks.csv"

_COLS = [
    "pick_id", "generated_at", "horse_type", "season", "week",
    "player_id", "player_name", "team", "market", "direction",
    "line", "odds", "probability", "game_date",
    "actual_value", "result", "graded_at",
]


def _ensure_file():
    if not _PICKS_FILE.exists():
        _PICKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_PICKS_FILE, "w", newline="") as f:
            csv.writer(f).writerow(_COLS)


def record_pick(horse_type: str, leg: dict, season: int, week: int) -> str:
    """
    Save a single pick to the CSV. Returns the pick_id.
    leg must have: playerId, name, team, market, direction, line, odds, probability, gameDate
    """
    _ensure_file()
    pick_id = f"{horse_type[:6]}-{leg.get('playerId','?')}-{leg.get('market','?')}-{int(datetime.now(timezone.utc).timestamp())}"
    row = {
        "pick_id":      pick_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horse_type":   horse_type,
        "season":       season,
        "week":         week,
        "player_id":    leg.get("playerId", ""),
        "player_name":  leg.get("name", ""),
        "team":         leg.get("team", ""),
        "market":       leg.get("market", ""),
        "direction":    leg.get("direction", "over"),
        "line":         leg.get("line", ""),
        "odds":         leg.get("odds", -110),
        "probability":  leg.get("probability", ""),
        "game_date":    leg.get("gameDate", ""),
        "actual_value": "",
        "result":       "PENDING",
        "graded_at":    "",
    }
    with open(_PICKS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writerow(row)
    return pick_id


def _load_actual_stats() -> dict[tuple[str, str, str], float]:
    """
    Build (player_id, market, week) → actual stat value from the lake.
    Covers receiving, rushing, passing, scrimmage.
    """
    lake = Path(__file__).parent.parent / "lake/gold/nfl"
    stat_map: dict[tuple[str, str, str], float] = {}

    sources = [
        ("player_receiving_week.csv",  {"recyds": "receiving_yards", "recs": "receptions"}),
        ("player_rushing_week.csv",    {"rushyds": "rushing_yards", "carries": "carries"}),
        ("player_passing_week.csv",    {"passyds": "passing_yards", "passtd": "passing_tds",
                                        "passatt": "attempts", "intsthrown": "passing_interceptions"}),
        ("player_scrimmage_week.csv",  {"rushrec": "scrimmage_yards"}),
        ("player_scoring_week.csv",    {"anytd": "rushing_tds"}),  # approximation
    ]
    for fname, market_cols in sources:
        fpath = lake / fname
        if not fpath.exists():
            continue
        try:
            with open(fpath) as f:
                for row in csv.DictReader(f):
                    pid  = row.get("player_id", "")
                    week = row.get("week", "")
                    for market, col in market_cols.items():
                        val = row.get(col)
                        if val:
                            try:
                                stat_map[(pid, market, week)] = float(val)
                            except ValueError:
                                pass
        except Exception:
            pass
    return stat_map


def grade_pending(current_week: int) -> dict:
    """
    Grade all PENDING picks for weeks <= current_week - 1.
    Returns {graded: int, hits: int, misses: int}.
    """
    _ensure_file()
    stats = _load_actual_stats()
    rows = []
    graded = hits = misses = 0

    with open(_PICKS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("result") != "PENDING":
                rows.append(row)
                continue
            try:
                pick_week = int(row.get("week") or 0)
            except ValueError:
                rows.append(row)
                continue
            if pick_week >= current_week:
                rows.append(row)
                continue

            pid     = row.get("player_id", "")
            market  = row.get("market", "")
            line    = row.get("line", "")
            direction = row.get("direction", "over")
            actual = stats.get((pid, market, str(pick_week)))
            if actual is None:
                rows.append(row)
                continue

            try:
                line_f = float(line) if line else 0.5
            except ValueError:
                line_f = 0.5

            hit = (actual >= line_f) if direction == "over" else (actual < line_f)
            row["actual_value"] = str(actual)
            row["result"]       = "HIT" if hit else "MISS"
            row["graded_at"]    = datetime.now(timezone.utc).isoformat()
            graded += 1
            if hit:
                hits += 1
            else:
                misses += 1
            rows.append(row)

    with open(_PICKS_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        w.writerows(rows)

    return {"graded": graded, "hits": hits, "misses": misses}


def season_stats() -> dict:
    """
    Season-to-date hit-rate summary per horse_type and overall.
    Reads from crazy_horse_picks.csv.
    """
    _ensure_file()
    by_type: dict[str, dict] = {}
    total_hits = total_graded = total_pending = 0

    with open(_PICKS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            horse_type = row.get("horse_type", "UNKNOWN")
            result     = row.get("result", "PENDING")
            bucket = by_type.setdefault(horse_type, {"hits": 0, "misses": 0, "pending": 0})
            if result == "HIT":
                bucket["hits"] += 1
                total_hits += 1
                total_graded += 1
            elif result == "MISS":
                bucket["misses"] += 1
                total_graded += 1
            else:
                bucket["pending"] += 1
                total_pending += 1

    summary = []
    for horse_type, b in sorted(by_type.items()):
        graded = b["hits"] + b["misses"]
        summary.append({
            "horseType":  horse_type,
            "hits":       b["hits"],
            "misses":     b["misses"],
            "pending":    b["pending"],
            "graded":     graded,
            "hitRate":    round(b["hits"] / graded, 3) if graded else None,
        })

    return {
        "totalHits":    total_hits,
        "totalGraded":  total_graded,
        "totalPending": total_pending,
        "seasonHitRate": round(total_hits / total_graded, 3) if total_graded else None,
        "byHorseType":  summary,
    }


def hot_dog_season_stats() -> dict:
    """
    Season hit-rate from hot_dog_history.csv — the HOT DOG underdog picks.
    Computes running win rates for underdogs + covers.
    2023-2026 historical data.
    """
    lake = Path(__file__).parent.parent / "lake/gold/nfl/hot_dog_history.csv"
    if not lake.exists():
        return {"error": "hot_dog_history.csv not found"}

    by_season: dict[str, dict] = {}
    overall = {"wins": 0, "covers": 0, "total": 0}

    with open(lake, newline="") as f:
        for row in csv.DictReader(f):
            season = row.get("season", "")
            won_outright  = row.get("won_outright", "0")
            covered       = row.get("covered", "0")
            bucket = by_season.setdefault(season, {"wins": 0, "covers": 0, "total": 0})
            bucket["total"] += 1
            overall["total"] += 1
            try:
                if float(won_outright):
                    bucket["wins"] += 1
                    overall["wins"] += 1
                if float(covered):
                    bucket["covers"] += 1
                    overall["covers"] += 1
            except (ValueError, TypeError):
                pass

    seasons = []
    for season, b in sorted(by_season.items()):
        seasons.append({
            "season":      season,
            "total":       b["total"],
            "wins":        b["wins"],
            "covers":      b["covers"],
            "winRate":     round(b["wins"] / b["total"], 3) if b["total"] else None,
            "coverRate":   round(b["covers"] / b["total"], 3) if b["total"] else None,
        })

    return {
        "overall": {
            "total":     overall["total"],
            "wins":      overall["wins"],
            "covers":    overall["covers"],
            "winRate":   round(overall["wins"] / overall["total"], 3) if overall["total"] else None,
            "coverRate": round(overall["covers"] / overall["total"], 3) if overall["total"] else None,
        },
        "bySeason": seasons,
    }

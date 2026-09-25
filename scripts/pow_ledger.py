"""
POW ledger -- Parlay Orders Won, Big Proppa's measure of success.

A week's board fails if fewer than 75% of the tickets posted win. Cash won is
not the measure.

  snapshot            record this week's engine board (every ticket and leg,
                      with its FanDuel line and odds) and the matchup
                      predictor's pick for every game, before kickoff
  grade --week N      after the weekly stats refresh, grade each leg from the
                      lake's box scores and each game pick from schedule finals

A leg wins when the stat clears its line in the bet's direction; a player with
no box-score row that week is void, as a sportsbook would grade it. HOT DOGS!
team legs are graded on the final score: the moneyline needs an outright win,
the spread needs margin + spread > 0. TOTALS! legs are graded on the combined
final score against the total line. A ticket wins when every non-void leg wins.

Writes lake/gold/nfl/pow_ledger.csv. Run from the repo root:
    backend/.venv/bin/python scripts/pow_ledger.py snapshot
    backend/.venv/bin/python scripts/pow_ledger.py grade --week 3
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

import data  # noqa: E402
import matchup  # noqa: E402
import parlay_engine  # noqa: E402
import parlays  # noqa: E402
from build_team_game_stats import GOLD, register_chart  # noqa: E402

LEDGER = GOLD / "pow_ledger.csv"
COLS = [
    "season", "week", "kind", "ticket_id", "correlation_type", "title", "leg_index", "game_id", "player_id", "player_name",
    "team", "market", "direction", "line", "odds", "probability", "predicted_winner", "win_probability",
    "snapshot_at_utc", "actual", "result", "graded_at_utc",
]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    if path == LEDGER:
        register_chart("pow_ledger", "scripts/pow_ledger.py", "one row per posted leg or game pick",
                       len(rows), "Big Proppa board + lake box scores")


def snapshot(path: Path) -> None:
    games = matchup.slate()
    if not games:
        raise SystemExit("no slate this week -- nothing to snapshot")
    season, week = games[0]["season"], games[0]["week"]
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    rows = read(path)
    if any(r["season"] == str(season) and r["week"] == str(week) and r["result"] for r in rows):
        raise SystemExit(f"{season} week {week} is already graded -- not overwriting it")
    rows = [r for r in rows if not (r["season"] == str(season) and r["week"] == str(week))]

    new = []
    for slip in parlay_engine.run_engine():
        for i, leg in enumerate(slip["legs"]):
            new.append({
                "season": season, "week": week, "kind": "leg", "ticket_id": slip["id"],
                "correlation_type": slip["correlationType"], "title": slip["title"], "leg_index": i,
                "player_id": leg["playerId"], "player_name": leg["name"], "team": leg["team"],
                "market": leg["market"], "direction": leg["direction"], "line": leg["line"],
                "odds": leg["odds"], "probability": leg["probability"], "snapshot_at_utc": now,
            })
    hot = parlays.hot_dogs()
    for i, leg in enumerate(hot["legs"]):
        new.append({
            "season": season, "week": week, "kind": "leg", "ticket_id": hot["id"], "correlation_type": "HOT_DOGS",
            "title": hot["title"], "leg_index": i, "game_id": leg["gameId"], "team": leg["teamId"],
            "market": leg["market"], "direction": "over", "line": leg["line"] if leg["line"] is not None else "",
            "odds": leg["odds"], "probability": leg["probability"], "snapshot_at_utc": now,
        })
    tot = parlays.totals()
    for i, leg in enumerate(tot["legs"]):
        new.append({
            "season": season, "week": week, "kind": "leg", "ticket_id": tot["id"], "correlation_type": "TOTALS",
            "title": tot["title"], "leg_index": i, "game_id": leg["gameId"],
            "market": leg["market"], "direction": leg["direction"], "line": leg["line"],
            "odds": leg["odds"], "probability": leg["probability"], "snapshot_at_utc": now,
        })
    for g in games:
        new.append({
            "season": season, "week": week, "kind": "game", "ticket_id": g["gameId"],
            "title": f"{g['away']['team']} @ {g['home']['team']}", "predicted_winner": g["predictedWinner"],
            "win_probability": g["winProbability"], "snapshot_at_utc": now,
        })
    write(path, rows + new)
    tickets = len({r["ticket_id"] for r in new if r["kind"] == "leg"})
    print(f"snapshot {season} week {week}: {tickets} tickets, {len(games)} game picks -> {path.name}")


def _grade_team_leg(r: dict) -> tuple[str, str]:
    """HOT DOGS! legs: the dog's final margin against the moneyline or its spread."""
    g = next((g for g in data.load("schedule") if g["game_id"] == r["game_id"]), None)
    if not g or not g.get("home_score") or not g.get("away_score"):
        return "", ""
    hs, as_ = float(g["home_score"]), float(g["away_score"])
    margin = hs - as_ if g["home_team"] == r["team"] else as_ - hs
    edge = margin if r["market"] == "moneyline" else margin + float(r["line"])
    return str(int(margin)), "push" if edge == 0 else ("won" if edge > 0 else "lost")


def _grade_total_leg(r: dict) -> tuple[str, str]:
    """TOTALS! legs: combined final score against the total line."""
    g = next((g for g in data.load("schedule") if g["game_id"] == r["game_id"]), None)
    if not g or not g.get("home_score") or not g.get("away_score"):
        return "", ""
    total = float(g["home_score"]) + float(g["away_score"])
    line = float(r["line"])
    if total == line:
        return str(total), "push"
    hit = total > line if r["direction"] == "over" else total < line
    return str(total), "won" if hit else "lost"


def _grade_leg(r: dict) -> tuple[str, str]:
    if r["market"] in ("spread", "moneyline"):
        return _grade_team_leg(r)
    if r["market"] == "total":
        return _grade_total_leg(r)
    games = [g for g in parlay_engine._games_for(r["player_id"], r["market"]) if g["week"] == int(r["week"])]
    if not games:
        return "", "void"
    actual, line = games[0]["value"], float(r["line"])
    if actual == line:
        return str(actual), "push"
    won = actual > line if r["direction"] == "over" else actual < line
    return str(actual), "won" if won else "lost"


def _winners(season: str, week: str) -> dict[str, str]:
    out = {}
    for g in data.load("schedule"):
        if g["season"] != season or g["week"] != week or not g.get("home_score") or not g.get("away_score"):
            continue
        hs, as_ = float(g["home_score"]), float(g["away_score"])
        out[g["game_id"]] = g["home_team"] if hs > as_ else g["away_team"] if as_ > hs else "TIE"
    return out


def grade(path: Path, week: int, season: int | None) -> None:
    rows = read(path)
    season = season or max(int(r["season"]) for r in rows)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    winners = _winners(str(season), str(week))
    graded = 0
    for r in rows:
        if r["season"] != str(season) or r["week"] != str(week):
            continue
        if r["kind"] == "leg":
            r["actual"], r["result"] = _grade_leg(r)
        else:
            actual = winners.get(r["ticket_id"])
            if not actual:
                continue
            r["actual"] = actual
            r["result"] = "push" if actual == "TIE" else ("won" if actual == r["predicted_winner"] else "lost")
        r["graded_at_utc"] = now
        graded += 1
    write(path, rows)
    print(f"graded {graded} rows for {season} week {week}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["snapshot", "grade"])
    ap.add_argument("--week", type=int)
    ap.add_argument("--season", type=int)
    ap.add_argument("--ledger", type=Path, default=LEDGER, help="alternate ledger file (for testing)")
    args = ap.parse_args()
    if args.action == "snapshot":
        snapshot(args.ledger)
    else:
        if args.week is None:
            ap.error("grade needs --week")
        grade(args.ledger, args.week, args.season)


if __name__ == "__main__":
    main()

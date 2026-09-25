"""
POW -- Parlay Orders Won. Summarizes lake/gold/nfl/pow_ledger.csv (written by
scripts/pow_ledger.py): per week and for the season, how many posted tickets
won, and how often the matchup predictor picked the winner.

A ticket wins when every non-void leg wins; a ticket whose legs are all void
is not counted. A graded week under 75% POW is a failure.
"""
from __future__ import annotations

from collections import defaultdict

import data

POW_TARGET = 0.75


def _ticket_result(results: list[str]) -> str | None:
    if any(r == "" for r in results):
        return None
    live = [r for r in results if r not in ("void", "push")]
    if not live:
        return None
    return "won" if all(r == "won" for r in live) else "lost"


def summary() -> dict:
    rows = data.load("pow_ledger")
    weeks: dict[tuple[int, int], dict] = {}
    legs_by_ticket: dict[tuple[int, int, str], list[str]] = defaultdict(list)

    for r in rows:
        key = (int(r["season"]), int(r["week"]))
        w = weeks.setdefault(key, {"posted": set(), "picks": 0, "picksGraded": 0, "picksWon": 0.0})
        if r["kind"] == "leg":
            w["posted"].add(r["ticket_id"])
            legs_by_ticket[(*key, r["ticket_id"])].append(r["result"])
        else:
            w["picks"] += 1
            if r["result"]:
                w["picksGraded"] += 1
                w["picksWon"] += 1.0 if r["result"] == "won" else 0.5 if r["result"] == "push" else 0.0

    out = []
    for (season, week), w in sorted(weeks.items()):
        results = [_ticket_result(legs_by_ticket[(season, week, t)]) for t in w["posted"]]
        graded = [x for x in results if x]
        won = sum(1 for x in graded if x == "won")
        pow_pct = won / len(graded) if graded else None
        out.append({
            "season": season, "week": week, "ticketsPosted": len(w["posted"]),
            "ticketsGraded": len(graded), "ticketsWon": won,
            "pow": round(pow_pct, 3) if pow_pct is not None else None,
            "failure": pow_pct is not None and pow_pct < POW_TARGET,
            "picks": w["picks"], "picksGraded": w["picksGraded"],
            "pickAccuracy": round(w["picksWon"] / w["picksGraded"], 3) if w["picksGraded"] else None,
        })

    graded_weeks = [w for w in out if w["ticketsGraded"]]
    t_graded = sum(w["ticketsGraded"] for w in graded_weeks)
    t_won = sum(w["ticketsWon"] for w in graded_weeks)
    return {
        "sourceStatus": data.chart_status("pow_ledger"),
        "target": POW_TARGET,
        "weeks": out,
        "season": {
            "ticketsGraded": t_graded, "ticketsWon": t_won,
            "pow": round(t_won / t_graded, 3) if t_graded else None,
            "failedWeeks": sum(1 for w in graded_weeks if w["failure"]),
        },
    }

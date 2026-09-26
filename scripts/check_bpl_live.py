"""
Weekly BPL reality check: how did last week's BPL probabilities do?

For every player who has played at least two 2026 games, predicts the LATEST played
week from the games before it (same frozen BPL constants, zero-stat games included)
and compares predicted vs actual over-rates at 30%, 50% and 70% of the BPL. A
persistent gap is what backend/jimmy_bpl.py SPY_HAIRCUT is set from.

    backend/.venv/bin/python scripts/check_bpl_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import bpl  # noqa: E402
import jimmy_bpl as j  # noqa: E402


def main() -> None:
    for m, (_, _, cat) in bpl.NFL_MARKETS.items():
        hist = bpl._player_history(m)
        teams_by_week: dict[int, set[str]] = {}
        for gs in hist.values():
            for g in gs:
                teams_by_week.setdefault(g["week"], set()).add(g["team"])
        latest = max((w for w, t in teams_by_week.items() if len(t) >= 24), default=0)  # full slates only
        res = {f: [0, 0.0] for f in (0.3, 0.5, 0.7)}
        n = zero = 0
        for pid, games in hist.items():
            before = [g for g in games if g["week"] < latest]
            target = [g for g in games if g["week"] == latest]
            if not before or not target:
                continue
            opp = target[0]["opp"]
            pr = bpl._team_priors().get(opp)
            allowed = bpl._team_allowed_history().get(opp, {}).get(cat, [])[:-1]
            parts = bpl.core_line(m, [g["value"] for g in before], bpl._player_priors().get((m, pid)), allowed,
                                  float(pr["allowed_" + cat]) if pr else None, bpl._league_allowed(cat), None)
            if not parts or parts["baseline"] < j.MIN_BASELINE[m]:
                continue
            raw = parts["baseline"] * parts["oppFactor"] * sum(bpl.PARAMS[m]["home"].values()) / 2
            n += 1
            zero += target[0]["value"] == 0
            for f in res:
                res[f][0] += target[0]["value"] > raw * f
                res[f][1] += j.p_over(m, raw, raw * f)
        if n:
            cells = "  ".join(f"@{int(f * 100)}% pred {res[f][1] / n:.2f} actual {res[f][0] / n:.2f}" for f in res)
            print(f"{m:<8} wk{latest} n={n:<4} zero-stat={zero:<3} {cells}")


if __name__ == "__main__":
    main()

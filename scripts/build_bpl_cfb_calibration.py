"""
Calibrate BIG PROPPA LINE constants for CFB team points (FBS vs FBS), walk-forward
on 2024-2025 CFBD games with the previous season as the prior. Same method as the
NFL calibration (scripts/build_bpl_calibration.py); only the constants differ.

Run from the repo root (needs CFBD_API_KEY):
    backend/.venv/bin/python scripts/build_bpl_cfb_calibration.py
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import cfb_data  # noqa: E402


def team_games(year: int) -> list[dict]:
    raw = cfb_data._get("/games", {"year": year, "seasonType": "regular"}) or []
    out = []
    for g in raw:
        if not g.get("completed") or g.get("homePoints") is None or g.get("awayPoints") is None:
            continue
        if g.get("homeClassification") != "fbs" or g.get("awayClassification") != "fbs":
            continue
        home = 0 if g.get("neutralSite") else 1
        out.append({"week": g["week"], "gid": g["id"], "team": g["homeTeam"], "opp": g["awayTeam"],
                    "scored": float(g["homePoints"]), "home": home})
        out.append({"week": g["week"], "gid": g["id"], "team": g["awayTeam"], "opp": g["homeTeam"],
                    "scored": float(g["awayPoints"]), "home": 0 if g.get("neutralSite") else -1})
    return sorted(out, key=lambda r: r["week"])


def season_means(games: list[dict]) -> tuple[dict, dict, float]:
    scored, allowed = {}, {}
    for r in games:
        scored.setdefault(r["team"], []).append(r["scored"])
        allowed.setdefault(r["opp"], []).append(r["scored"])
    m = lambda d: {k: sum(v) / len(v) for k, v in d.items() if len(v) >= 4}
    league = sum(r["scored"] for r in games) / len(games)
    return m(scored), m(allowed), league


def examples(year: int, prev: list[dict], cur: list[dict]) -> list[dict]:
    p_sc, p_al, league = season_means(prev)
    hist_sc, hist_al, out = {}, {}, []
    by_week: dict[int, list[dict]] = {}
    for r in cur:
        by_week.setdefault(r["week"], []).append(r)
    for wk in sorted(by_week):
        rows = by_week[wk]
        for r in rows:
            if hist_sc.get(r["team"]):
                out.append({"actual": r["scored"], "hist": list(hist_sc[r["team"]]), "prior": p_sc.get(r["team"]),
                            "opp_hist": list(hist_al.get(r["opp"], [])), "opp_prior": p_al.get(r["opp"]),
                            "league": league, "home": r["home"], "gid": r["gid"]})
        for r in rows:
            hist_sc.setdefault(r["team"], []).append(r["scored"])
            hist_al.setdefault(r["opp"], []).append(r["scored"])
    return out


def predict(e, d, kp, ko, ow):
    n = len(e["hist"])
    w = [d ** (n - 1 - i) for i in range(n)]
    s = sum(a * b for a, b in zip(w, e["hist"]))
    base = (s + kp * e["prior"]) / (sum(w) + kp) if e["prior"] is not None else s / sum(w)
    if e["opp_prior"] is not None:
        oa = (sum(e["opp_hist"]) + ko * e["opp_prior"]) / (len(e["opp_hist"]) + ko)
    elif e["opp_hist"]:
        oa = sum(e["opp_hist"]) / len(e["opp_hist"])
    else:
        oa = e["league"]
    return base * (1 + ow * (oa / e["league"] - 1))


def main() -> None:
    seasons = {y: team_games(y) for y in (2023, 2024, 2025)}
    exs = examples(2024, seasons[2023], seasons[2024]) + examples(2025, seasons[2024], seasons[2025])
    actual = [e["actual"] for e in exs]
    best = None
    for d, kp, ko, ow in itertools.product([0.6, 0.7, 0.8, 0.9, 1.0], [1, 2, 3, 4, 6, 8], [2, 4, 6, 8, 12], [0.25, 0.5, 0.75, 1.0]):
        pred = [predict(e, d, kp, ko, ow) for e in exs]
        mae = sum(abs(p - a) for p, a in zip(pred, actual)) / len(actual)
        if best is None or mae < best[0]:
            best = (mae, d, kp, ko, ow, pred)
    mae, d, kp, ko, ow, pred = best
    home = {}
    for h in (1, 0, -1):
        ratios = [a / p for e, a, p in zip(exs, actual, pred) if e["home"] == h and p > 0]
        n = len(ratios)
        home[h] = round(1 + (median(ratios) - 1) * n / (n + 200), 4) if ratios else 1.0
    final = [p * home[e["home"]] for e, p in zip(exs, pred)]
    naive = sum(abs(sum(e["hist"]) / len(e["hist"]) - a) for e, a in zip(exs, actual)) / len(actual)
    fmae = sum(abs(p - a) for p, a in zip(final, actual)) / len(actual)
    over = sum(a > p for p, a in zip(final, actual)) / len(actual)
    tot: dict = {}
    for e, a, p in zip(exs, actual, final):
        t = tot.setdefault(e["gid"], [0.0, 0.0, 0])
        t[0] += a; t[1] += p; t[2] += 1
    both = [t for t in tot.values() if t[2] == 2]
    print(f"n={len(exs)} naive_mae={naive:.2f} bpl_mae={fmae:.2f} over_rate={over:.3f}")
    print(f"game totals n={len(both)} over_rate={sum(t[0] > t[1] for t in both) / len(both):.3f} "
          f"mae={sum(abs(t[0] - t[1]) for t in both) / len(both):.2f}")
    print({"decay": d, "k_prior": kp, "k_opp": ko, "opp_weight": ow, "home": home})


if __name__ == "__main__":
    main()

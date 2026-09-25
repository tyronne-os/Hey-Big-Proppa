"""
Fit and backtest the BIG PROPPA matchup predictor (backend/matchup.py) on the
modern-era pond (team_game_stats, 2023 onward).

  train      2023          fit unit weights
  validate   2024          tune K (prior strength) and R (regression to mean),
                           and prune redundant stats
  holdout    2025          never touched while choosing anything; reported
  production 2023-2025     refit with the chosen settings, saved for 2026

Redundancy rule (the user's): drop a stat only if it adds nothing -- it is
either a player-page roll-up (tackles, passes defended) or correlates above
|0.9| with a stat already in its unit -- AND dropping it does not make
validation log-loss or accuracy worse.

Baselines on the holdout: always pick the home team, and the Vegas favorite
(moneyline, from lake/bronze/nflverse/games.csv -- a yardstick only, never an
input to the model).

Writes lake/gold/nfl/matchup_model.csv and matchup_backtest.csv.
Run from the repo root after build_team_game_stats.py:
    backend/.venv/bin/python scripts/fit_matchup_model.py
"""
from __future__ import annotations

import csv
import itertools
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "scripts"))

import matchup as mu  # noqa: E402
from build_team_game_stats import GOLD, RELOCATED, register_chart  # noqa: E402

TRAIN, VALIDATE, HOLDOUT = [2023], [2024], [2025]
K_GRID = [1, 2, 3, 4, 6, 8]
R_GRID = [0.2, 0.33, 0.5, 0.7]
PLAYER_PAGE = {"def_pd_pg:def", "def_tackles_pg:def", "def_solo_pg:def"}
BUCKETS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 1.01)]
EPS = 1e-12


def load_rows() -> list[dict]:
    with (GOLD / "team_game_stats.csv").open(newline="", encoding="utf-8") as fh:
        return mu.game_rows(list(csv.DictReader(fh)))


def games(rows: list[dict]) -> list[dict]:
    """One row per game from the home side (neutral: the side listed first)."""
    seen, out = set(), []
    for g in sorted(rows, key=lambda g: (-g["home"], g["team"])):
        if g["game_id"] in seen:
            continue
        seen.add(g["game_id"])
        out.append(g)
    return sorted(out, key=lambda g: (g["season"], g["week"], g["game_id"]))


class Features:
    """Cached z-scores per (season, week) for one (K, R) setting."""

    def __init__(self, rows: list[dict], k: float, r: float):
        self.rows, self.k, self.r, self.cache = rows, k, r, {}

    def z(self, season: int, week: int):
        key = (season, week)
        if key not in self.cache:
            self.cache[key] = mu.week_z(self.rows, season, week, self.k, self.r)
        return self.cache[key]

    def design(self, gms: list[dict], active: set[str]):
        X, y, win, kept = [], [], [], []
        for g in gms:
            z = self.z(g["season"], g["week"])
            if z is None:
                continue
            eh = mu.unit_edges(z, g["team"], g["opponent"], active)
            ea = mu.unit_edges(z, g["opponent"], g["team"], active)
            X.append([max(g["home"], 0)] + [eh[u] - ea[u] for u in mu.UNIT_NAMES])
            y.append(g["margin"])
            win.append(g["win"])
            kept.append(g)
        return np.array(X), np.array(y), np.array(win), kept


def fit(X, y):
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    sigma = float(np.std(y - X @ coef))
    return coef, sigma


def probs(X, coef, sigma):
    return np.array([mu.phi(m / sigma) for m in X @ coef])


def score(p, win):
    """(accuracy, log-loss). A tie counts as half right."""
    pick_home = p >= 0.5
    correct = np.where(win == 0.5, 0.5, (pick_home == (win == 1.0)).astype(float))
    pc = np.clip(p, EPS, 1 - EPS)
    ll = -np.mean(win * np.log(pc) + (1 - win) * np.log(1 - pc))
    return float(correct.mean()), float(ll), correct


def evaluate(feats: Features, active: set[str], train: list[dict], test: list[dict]):
    Xt, yt, _, _ = feats.design(train, active)
    coef, sigma = fit(Xt, yt)
    Xv, _, wv, kept = feats.design(test, active)
    p = probs(Xv, coef, sigma)
    acc, ll, correct = score(p, wv)
    return {"acc": acc, "ll": ll, "coef": coef, "sigma": sigma, "p": p, "win": wv, "correct": correct, "games": kept}


def entry_values(feats: Features, gms: list[dict], entry: str) -> np.ndarray:
    stat, side = entry.split(":")
    vals = []
    for g in gms:
        z = feats.z(g["season"], g["week"])
        if z is None:
            continue
        for att, dfn in ((g["team"], g["opponent"]), (g["opponent"], g["team"])):
            vals.append(z[att if side == "off" else dfn][stat])
    return np.array(vals)


def unit_of(entry: str) -> str:
    stat, side = entry.split(":")
    return next(u for u, es in mu.UNITS.items() if any(s == stat and sd == side for s, sd, _ in es))


def prune(feats: Features, train, validate, log: list[dict]) -> set[str]:
    active = set(mu.ALL_ENTRIES)
    base = evaluate(feats, active, train, validate)
    values = {e: entry_values(feats, train, e) for e in active}
    changed = True
    while changed:
        changed = False
        for e in sorted(active):
            unit = unit_of(e)
            mates = [m for m in active if m != e and unit_of(m) == unit]
            if not mates:
                continue
            corr = max(abs(float(np.corrcoef(values[e], values[m])[0, 1])) for m in mates)
            if e not in PLAYER_PAGE and corr <= 0.9:
                continue
            trial = evaluate(feats, active - {e}, train, validate)
            if trial["ll"] <= base["ll"] + EPS and trial["acc"] >= base["acc"] - EPS:
                why = "player-page roll-up" if e in PLAYER_PAGE else f"|r|={corr:.2f} with a unit-mate"
                log.append({"section": "pruned", "model": e, "note": f"{why}; validation log-loss "
                            f"{base['ll']:.4f}->{trial['ll']:.4f}, accuracy {base['acc']:.3f}->{trial['acc']:.3f}"})
                active.discard(e)
                base = trial
                changed = True
                break
    for e in sorted(set(mu.ALL_ENTRIES) - {x["model"] for x in log if x["section"] == "pruned"}):
        log.append({"section": "kept", "model": e, "note": unit_of(e)})
    return active


def vegas(gms: list[dict]) -> dict[str, float]:
    """Home win probability implied by the closing moneylines, vig removed."""
    out = {}
    with (REPO / "lake" / "bronze" / "nflverse" / "games.csv").open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                hm, am = float(r["home_moneyline"]), float(r["away_moneyline"])
            except ValueError:
                continue
            imp = lambda ml: 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)  # noqa: E731
            h, a = imp(hm), imp(am)
            out[(r["game_id"], RELOCATED.get(r["home_team"], r["home_team"]))] = h / (h + a)
    return out


def bucket_rows(name: str, p, correct) -> list[dict]:
    conf = np.maximum(p, 1 - p)
    rows = []
    for lo, hi in BUCKETS + [(0.75, 1.01)]:
        mask = (conf >= lo) & (conf < hi)
        n = int(mask.sum())
        label = f"{lo:.0%}+" if (lo, hi) == (0.75, 1.01) else f"{lo:.0%}-{min(hi, 1):.0%}"
        rows.append({"section": "bucket", "model": name, "split": "holdout 2025", "bucket": label,
                     "games": n, "correct": float(correct[mask].sum()) if n else 0,
                     "accuracy": round(float(correct[mask].mean()), 3) if n else ""})
    return rows


def main() -> None:
    rows = load_rows()
    gms = games(rows)
    split = lambda seasons: [g for g in gms if g["season"] in seasons]  # noqa: E731
    train, validate, holdout = split(TRAIN), split(VALIDATE), split(HOLDOUT)
    report: list[dict] = []

    # 1. Tune K and R on validation with every stat active.
    best = None
    for k, r in itertools.product(K_GRID, R_GRID):
        res = evaluate(Features(rows, k, r), set(mu.ALL_ENTRIES), train, validate)
        report.append({"section": "tuning", "model": f"K={k} R={r}", "split": "validate 2024",
                       "games": len(res["games"]), "accuracy": round(res["acc"], 3), "log_loss": round(res["ll"], 4)})
        if best is None or res["ll"] < best[0]["ll"]:
            best = (res, k, r)
    _, k, r = best
    feats = Features(rows, k, r)

    # 2. Prune redundant stats on validation.
    active = prune(feats, train, validate, report)

    # 3. Holdout: fit on train + validate, score 2025 once.
    hold = evaluate(feats, active, train + validate, holdout)
    report.append({"section": "summary", "model": "BIG PROPPA matchup", "split": "holdout 2025",
                   "games": len(hold["games"]), "correct": float(hold["correct"].sum()),
                   "accuracy": round(hold["acc"], 3), "log_loss": round(hold["ll"], 4)})
    report += bucket_rows("BIG PROPPA matchup", hold["p"], hold["correct"])

    home_p = np.array([0.57 if g["home"] > 0 else 0.5 for g in hold["games"]])
    acc, ll, correct = score(home_p, hold["win"])
    report.append({"section": "summary", "model": "always pick home", "split": "holdout 2025",
                   "games": len(hold["games"]), "correct": float(correct.sum()), "accuracy": round(acc, 3),
                   "log_loss": round(ll, 4), "note": "home win prob fixed at 57%"})

    vg = vegas(gms)
    idx = [i for i, g in enumerate(hold["games"]) if (g["game_id"], g["team"]) in vg]
    vp = np.array([vg[(hold["games"][i]["game_id"], hold["games"][i]["team"])] for i in idx])
    acc, ll, correct = score(vp, hold["win"][idx])
    report.append({"section": "summary", "model": "Vegas favorite", "split": "holdout 2025", "games": len(idx),
                   "correct": float(correct.sum()), "accuracy": round(acc, 3), "log_loss": round(ll, 4),
                   "note": "closing moneyline, vig removed; yardstick only"})
    report += bucket_rows("Vegas favorite", vp, correct)

    # 4. Production model: refit on every modern-era season.
    X, y, _, _ = feats.design(train + validate + holdout, active)
    coef, sigma = fit(X, y)
    params = [("k", k), ("r", r), ("sigma", round(sigma, 4)), ("home", round(float(coef[0]), 4))]
    params += [(f"beta:{u}", round(float(c), 4)) for u, c in zip(mu.UNIT_NAMES, coef[1:])]
    params += [("active", e) for e in sorted(active)]
    params += [("trained_on", "2023-2025"), ("holdout_accuracy_2025", round(hold["acc"], 3))]

    with (GOLD / "matchup_model.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["param", "value"])
        w.writerows(params)
    cols = ["section", "model", "split", "bucket", "games", "correct", "accuracy", "log_loss", "note"]
    with (GOLD / "matchup_backtest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in report:
            w.writerow({c: row.get(c, "") for c in cols})

    register_chart("matchup_model", "scripts/fit_matchup_model.py", "one row per model parameter",
                   len(params), "fitted on team_game_stats")
    register_chart("matchup_backtest", "scripts/fit_matchup_model.py", "one row per backtest result",
                   len(report), "fitted on team_game_stats")

    for row in report:
        if row["section"] in ("summary", "bucket", "pruned"):
            print({k2: v for k2, v in row.items() if v != ""})
    print(f"K={k} R={r} sigma={sigma:.2f} home={coef[0]:.2f} active={len(active)}/{len(mu.ALL_ENTRIES)}")
    print("betas", {u: round(float(c), 2) for u, c in zip(mu.UNIT_NAMES, coef[1:])})


if __name__ == "__main__":
    main()

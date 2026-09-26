"""
Calibrate the BIG PROPPA LINE (BPL) constants from 2023-2025 play by play.

The BPL never looks at a sportsbook. Each line is built from the lake only:

    baseline  = recency-weighted per-game average this season, shrunk toward
                the player's previous-season per-game average (K_PRIOR games of weight)
    opp       = 1 + OPP_WEIGHT * (opponent allowed per game / league allowed per game - 1)
                (opponent allowed is itself shrunk toward its previous season, K_OPP games)
    home      = home/away multiplier
    BPL       = baseline * opp * home, rounded to the nearest 0.5

This script walks forward through 2024-2025 (2023 only feeds priors), predicting
every player-game from information available before kickoff, grid-searches the
constants, and prints the frozen values to paste into backend/bpl.py. It also
writes the 2025 priors that the live 2026 lines need:

    lake/gold/nfl/bpl_player_prior.csv   player per-game means, previous season
    lake/gold/nfl/bpl_team_prior.csv     team allowed / scored per game, previous season
    lake/gold/nfl/bpl_calibration.csv    backtest MAE per market, BPL vs naive average
    lake/gold/nfl/bpl_residual_quantiles.csv  actual / BPL ratio quantiles (turns a line gap into a hit probability)

Run from the repo root:
    backend/.venv/bin/python scripts/build_bpl_calibration.py
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BRONZE = ROOT / "lake" / "bronze" / "nflverse"
GOLD = ROOT / "lake" / "gold" / "nfl"
SEASONS = (2023, 2024, 2025)
PRIOR_SEASON_FOR_LIVE = 2025

# market -> (player id col, value col, team-allowed category)
MARKETS = {
    "rushyds": ("rusher_player_id", "rushing_yards", "rush_yds"),
    "recyds": ("receiver_player_id", "receiving_yards", "pass_yds"),
    "recs": ("receiver_player_id", "complete_pass", "completions"),
    "passyds": ("passer_player_id", "passing_yards", "pass_yds"),
}
# only lines someone would actually bet: skip fringe players in the fit
MIN_BASELINE = {"rushyds": 25.0, "recyds": 25.0, "recs": 2.5, "passyds": 150.0}

COLS = ["game_id", "season", "week", "season_type", "posteam", "defteam", "home_team",
        "rusher_player_id", "receiver_player_id", "passer_player_id",
        "rushing_yards", "receiving_yards", "passing_yards", "complete_pass",
        "two_point_attempt", "total_home_score", "total_away_score"]


def load_pbp() -> pd.DataFrame:
    frames = []
    for s in SEASONS:
        df = pd.read_csv(BRONZE / f"play_by_play_{s}.csv.gz", usecols=COLS, low_memory=False)
        frames.append(df[(df.season_type == "REG") & (df.two_point_attempt.fillna(0) == 0)])
    return pd.concat(frames, ignore_index=True)


def player_games(pbp: pd.DataFrame) -> pd.DataFrame:
    out = []
    for m, (pid_col, val_col, _) in MARKETS.items():
        d = pbp[pbp[pid_col].notna()]
        g = d.groupby(["season", "week", "game_id", pid_col, "posteam", "defteam", "home_team"], as_index=False)[val_col].sum()
        g = g.rename(columns={pid_col: "player_id", val_col: "value"})
        g["market"] = m
        out.append(g)
    pg = pd.concat(out, ignore_index=True)
    pg["home"] = (pg.posteam == pg.home_team).astype(int)
    return pg.sort_values(["season", "week"]).reset_index(drop=True)


def team_games(pbp: pd.DataFrame) -> pd.DataFrame:
    agg = pbp.groupby(["season", "week", "game_id", "posteam", "defteam"], as_index=False).agg(
        rush_yds=("rushing_yards", "sum"), pass_yds=("passing_yards", "sum"), completions=("complete_pass", "sum"))
    finals = pbp.groupby("game_id").agg(home_team=("home_team", "first"),
                                         hs=("total_home_score", "max"), as_=("total_away_score", "max")).reset_index()
    agg = agg.merge(finals, on="game_id")
    agg["points"] = np.where(agg.posteam == agg.home_team, agg.hs, agg.as_)
    return agg.drop(columns=["hs", "as_", "home_team"])


def weighted_mean(values: list[float], decay: float) -> tuple[float, float]:
    """values oldest->newest; returns (weighted sum, weight sum)."""
    n = len(values)
    w = np.array([decay ** (n - 1 - i) for i in range(n)])
    return float(np.dot(w, values)), float(w.sum())


def build_examples(pg: pd.DataFrame, tg: pd.DataFrame) -> list[dict]:
    """Pre-kickoff information for every 2024-2025 player-game (weeks 2+)."""
    prior_player = pg.groupby(["season", "market", "player_id"]).value.agg(["mean", "count"]).reset_index()
    prior_player = prior_player[prior_player["count"] >= 4]
    pp = {(r.season, r.market, r.player_id): r["mean"] for _, r in prior_player.iterrows()}

    allowed = tg.groupby(["season", "defteam"])[["rush_yds", "pass_yds", "completions"]].mean()
    league = tg.groupby("season")[["rush_yds", "pass_yds", "completions"]].mean()

    tg_by_def = {k: v.sort_values("week") for k, v in tg.groupby(["season", "defteam"])}
    examples = []
    for (season, market, pid), grp in pg[pg.season >= 2024].groupby(["season", "market", "player_id"]):
        grp = grp.sort_values("week")
        vals = grp.value.tolist()
        cat = MARKETS[market][2]
        for i in range(1, len(grp)):
            row = grp.iloc[i]
            dg = tg_by_def.get((season, row.defteam))
            opp_hist = dg[dg.week < row.week][cat].tolist() if dg is not None else []
            prev_allowed = allowed[cat].get((season - 1, row.defteam))
            examples.append({
                "season": season, "market": market, "actual": row.value, "home": row.home,
                "hist": vals[:i], "prior": pp.get((season - 1, market, pid)),
                "opp_hist": opp_hist, "opp_prior": prev_allowed,
                "league": float(league.loc[season - 1, cat]),
            })
    return examples


def predict(ex: dict, decay: float, k_prior: float, k_opp: float, opp_w: float) -> float:
    s, w = weighted_mean(ex["hist"], decay)
    if ex["prior"] is not None:
        base = (s + k_prior * ex["prior"]) / (w + k_prior)
    else:
        base = s / w
    o_sum, o_n = sum(ex["opp_hist"]), len(ex["opp_hist"])
    if ex["opp_prior"] is not None and not np.isnan(ex["opp_prior"]):
        opp_allowed = (o_sum + k_opp * ex["opp_prior"]) / (o_n + k_opp)
    elif o_n:
        opp_allowed = o_sum / o_n
    else:
        opp_allowed = ex["league"]
    opp = 1 + opp_w * (opp_allowed / ex["league"] - 1)
    return base * opp


def fit_market(exs: list[dict]) -> dict:
    grid = itertools.product([0.6, 0.7, 0.8, 0.9, 1.0], [1, 2, 3, 4, 6, 8], [2, 4, 6, 8, 12], [0.0, 0.25, 0.5, 0.75, 1.0])
    actual = np.array([e["actual"] for e in exs])
    best = None
    for d, kp, ko, ow in grid:
        pred = np.array([predict(e, d, kp, ko, ow) for e in exs])
        mae = float(np.mean(np.abs(pred - actual)))
        if best is None or mae < best["mae"]:
            best = {"decay": d, "k_prior": kp, "k_opp": ko, "opp_weight": ow, "mae": mae, "pred": pred}
    return best


def multiplier_table(exs: list[dict], pred: np.ndarray, key: str, shrink_n: float = 200.0) -> dict:
    """
    Median actual/pred ratio per bucket, shrunk toward 1.0 by sample size.
    Median, not mean: a line is the 50/50 point, so half of games must go over.
    """
    df = pd.DataFrame({"k": [e[key] for e in exs], "a": [e["actual"] for e in exs], "p": pred})
    df = df[df.p > 0]
    out = {}
    for k, g in df.groupby("k"):
        ratio = float(np.median(g.a / g.p))
        n = len(g)
        out[int(k)] = round(1 + (ratio - 1) * n / (n + shrink_n), 4)
    return out


def main() -> None:
    pbp = load_pbp()
    pg = player_games(pbp)
    tg = team_games(pbp)
    examples = build_examples(pg, tg)

    rows = []
    params = {}
    quantiles: list[dict] = []
    for m in MARKETS:
        exs = [e for e in examples if e["market"] == m]
        # fit on the players a book would post a line for
        naive = np.array([np.mean(e["hist"]) for e in exs])
        keep = naive >= MIN_BASELINE[m]
        exs = [e for e, k in zip(exs, keep) if k]
        best = fit_market(exs)
        pred = best["pred"]
        home = multiplier_table(exs, pred, "home")
        pred_h = pred * np.array([home.get(e["home"], 1.0) for e in exs])
        final = pred_h
        actual = np.array([e["actual"] for e in exs])
        naive_mae = float(np.mean(np.abs(np.array([np.mean(e["hist"]) for e in exs]) - actual)))
        bpl_mae = float(np.mean(np.abs(final - actual)))
        ok = pred_h > 0
        for q in range(1, 100):
            quantiles.append({"market": m, "q": q / 100, "ratio": round(float(np.quantile(actual[ok] / pred_h[ok], q / 100)), 4)})
        params[m] = {k: best[k] for k in ("decay", "k_prior", "k_opp", "opp_weight")} | {"home": home}
        rows.append({"market": m, "n": len(exs), "naive_mae": round(naive_mae, 2), "bpl_mae": round(bpl_mae, 2),
                     "improvement_pct": round((naive_mae - bpl_mae) / naive_mae * 100, 1),
                     "over_rate": round(float(np.mean(actual > pred_h)), 3),
                     "bias": round(float(np.mean(pred_h - actual)), 2), **{k: best[k] for k in ("decay", "k_prior", "k_opp", "opp_weight")}})

    # team points (game totals): same method, points scored vs points allowed
    home_of = pbp.groupby("game_id").home_team.first().to_dict()
    tp = tg.rename(columns={"posteam": "player_id", "points": "value"})[["season", "week", "game_id", "player_id", "defteam", "value"]].copy()
    tp["market"] = "points"
    prior_pts = tg.groupby(["season", "posteam"]).points.mean()
    allowed_pts = tg.groupby(["season", "defteam"]).points.mean()
    league_pts = tg.groupby("season").points.mean()
    pexs = []
    for (season, team), grp in tp[tp.season >= 2024].groupby(["season", "player_id"]):
        grp = grp.sort_values("week")
        vals = grp.value.tolist()
        for i in range(1, len(grp)):
            r = grp.iloc[i]
            dhist = tg[(tg.season == season) & (tg.defteam == r.defteam) & (tg.week < r.week)].points.tolist()
            pexs.append({"actual": r.value, "hist": vals[:i], "prior": prior_pts.get((season - 1, team)),
                         "home": int(r.player_id == home_of.get(r.game_id)), "gid": r.game_id,
                         "opp_hist": dhist, "opp_prior": allowed_pts.get((season - 1, r.defteam)),
                         "league": float(league_pts.loc[season - 1])})
    best = fit_market(pexs)
    actual = np.array([e["actual"] for e in pexs])
    home = multiplier_table(pexs, best["pred"], "home")
    pred_h = best["pred"] * np.array([home.get(e["home"], 1.0) for e in pexs])
    naive_mae = float(np.mean(np.abs(np.array([np.mean(e["hist"]) for e in pexs]) - actual)))
    bpl_mae = float(np.mean(np.abs(pred_h - actual)))
    params["points"] = {k: best[k] for k in ("decay", "k_prior", "k_opp", "opp_weight")} | {"home": home}
    rows.append({"market": "points", "n": len(pexs), "naive_mae": round(naive_mae, 2), "bpl_mae": round(bpl_mae, 2),
                 "improvement_pct": round((naive_mae - bpl_mae) / naive_mae * 100, 1),
                 "over_rate": round(float(np.mean(actual > pred_h)), 3),
                 "bias": round(float(np.mean(pred_h - actual)), 2), **{k: best[k] for k in ("decay", "k_prior", "k_opp", "opp_weight")}})
    # combined-score totals: sum of both teams' 50/50 points lines vs actual total
    tot = pd.DataFrame({"g": [e["gid"] for e in pexs], "a": actual, "p": pred_h}).groupby("g").agg(a=("a", "sum"), p=("p", "sum"), n=("a", "size"))
    tot = tot[tot.n == 2]
    print(f"game totals: n={len(tot)} over_rate={float(np.mean(tot.a > tot.p)):.3f} mae={float(np.mean(np.abs(tot.a - tot.p))):.2f}")

    pd.DataFrame(rows).to_csv(GOLD / "bpl_calibration.csv", index=False)
    pd.DataFrame(quantiles).to_csv(GOLD / "bpl_residual_quantiles.csv", index=False)

    s = PRIOR_SEASON_FOR_LIVE
    pp = pg[pg.season == s].groupby(["market", "player_id"]).value.agg(["mean", "count"]).reset_index()
    pp = pp[pp["count"] >= 4].rename(columns={"mean": "per_game", "count": "games"})
    pp["season"] = s
    pp.round(3).to_csv(GOLD / "bpl_player_prior.csv", index=False)

    t_all = tg[tg.season == s].groupby("defteam")[["rush_yds", "pass_yds", "completions", "points"]].mean().add_prefix("allowed_")
    t_sc = tg[tg.season == s].groupby("posteam")[["points"]].mean().add_prefix("scored_")
    team = t_all.join(t_sc).reset_index().rename(columns={"defteam": "team"})
    team["season"] = s
    team.round(3).to_csv(GOLD / "bpl_team_prior.csv", index=False)

    print(pd.DataFrame(rows).to_string(index=False))
    print("\nFROZEN PARAMS (paste into backend/bpl.py):")
    import json
    print(json.dumps(params, indent=2, default=float))


if __name__ == "__main__":
    main()

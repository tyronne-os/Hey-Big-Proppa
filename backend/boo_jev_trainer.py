"""
MY BOO trains JEV in house.

Data: every graded leg on the BETTER-VERSE board for every real season (2023-2025), with leak-free pre-game features
(the player's last-six form, how far the line sits from it, game script from the spread and total, price and no-vig price)
plus the CROWD signal MY BOO's harvester accumulates (how often betters of each tier picked that leg across every run).

Model: scikit-learn HistGradientBoostingClassifier (https://github.com/scikit-learn/scikit-learn), small and regularised.
It is trained to predict whether a leg hits and is judged against the only fair baseline: the price's own no-vig probability.

Honest evaluation: leave-one-season-out. For each real season the model is trained on the others and scored on the one it never saw
(Brier score, log loss, and the ROI of betting its biggest-edge legs at their listed price). A model is PROMOTED only if it beats the
baseline on Brier AND is profitable at its top-edge legs in EVERY held-out season. Otherwise it is kept on file but not used:
the market may simply be efficient, and the trainer says so in its report.

IMPORTANT CAVEAT: BETTER-VERSE prop lines are synthetic (a player's own recent median, shaded), not historical sportsbook lines, which
we do not have for 2023-25. A model can therefore learn how that synthetic book differs from better information (form, game script)
without that meaning an edge against a real book, which prices matchup and script in already. Promotion here is a necessary gate, not
proof: before any model touches live JEV scoring it must be validated against real historical lines.

Files (lake/gold/nfl/boo_models/, mirrored to the private HF dataset): jev_inhouse_vNNN.joblib · jev_inhouse_vNNN.json · registry.json
Also exports the curriculum as chat-format SFT JSONL (messages) ready for Hugging Face TRL (https://github.com/huggingface/trl)
when JIMMY or JEV need language-model teaching on a GPU.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import betterverse_data as md

DIR = Path(__file__).parent.parent / "lake/gold/nfl/boo_models"
FEATURES = ["market_code", "side_code", "line", "dec", "implied", "p_novig", "is_prop", "n_prior", "mean6", "std6", "last3", "line_gap",
            "team_spread", "total", "is_home", "week", "crowd_per_run", "crowd_sharp_share"]
CATEGORICAL = ["market_code", "side_code"]
MARKETS = list(md.ALL_MARKETS)
SIDES = ["over", "under", "yes", "fav", "dog"]
MIN_BRIER_GAIN = 5e-4
TRAIN_EVERY_CYCLES = 6
_LOCK = threading.Lock()


# --------------------------------------------------------------------------- dataset
def build_dataset(seasons=None, max_week: int | None = None) -> pd.DataFrame:
    """One row per graded board leg, with features known before kickoff and the crowd counters."""
    import boo_harvest
    seasons = tuple(seasons or md.SEASONS)
    crowd = boo_harvest._read("crowd.json", {})
    runs_by_season = Counter(int(r["season"]) for (k, _), r in boo_harvest._collected().items() if k == "run" and r.get("season"))
    sched = {g["game_id"]: g for g in md.schedule()}
    rows = []
    for y in seasons:
        n_runs = max(1, runs_by_season.get(y, 0))
        for w in md.weeks(y):
            if max_week and w > max_week:
                continue
            for it in md.menu(y, w):
                if it["hit"] is None:
                    continue
                g = sched.get(it["game_id"], {})
                spread = float(g.get("spread_line") or 0)
                team = it["team"]
                is_home = 1 if team == g.get("home_team") else 0 if team == g.get("away_team") else -1
                tspread = spread if is_home == 1 else -spread if is_home == 0 else np.nan
                if it["player_id"]:
                    prior = md._prior_rows(y, it["player_id"], w, 6)
                    vals = [md.stat(r, it["market"]) for r in prior]
                    mean6, std6 = (float(np.mean(vals)), float(np.std(vals))) if vals else (np.nan, np.nan)
                    last3 = float(np.mean(vals[-3:])) if vals else np.nan
                    gap = (it["line"] - mean6) / (std6 + 1.0) if vals else np.nan
                    grp = f"{y}|{w}|{it['game_id']}|{it['player_id']}|{it['market']}|{it['line']}"
                else:
                    mean6 = std6 = last3 = gap = np.nan
                    prior = []
                    grp = f"{y}|{w}|{it['game_id']}|{it['market']}"
                c = crowd.get(f"{y}|{w}|{it['game_id']}|{it['player_id']}|{it['market']}|{it['side']}|{it['line']}", [0, 0, 0, 0, 0])
                rows.append(dict(
                    season=y, week=w, market=it["market"], side=it["side"], line=float(it["line"]), dec=float(it["dec"]),
                    implied=1.0 / float(it["dec"]), grp=grp, is_prop=int(bool(it["player_id"])), n_prior=len(prior), mean6=mean6, std6=std6,
                    last3=last3, line_gap=gap, team_spread=tspread, total=float(g.get("total_line") or np.nan) if g.get("total_line") else np.nan,
                    is_home=is_home, crowd_per_run=c[0] / n_runs, crowd_sharp_share=(c[1] / c[0]) if c[0] else 0.0, hit=int(it["hit"])))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    tot = df.groupby("grp")["implied"].transform("sum")
    cnt = df.groupby("grp")["implied"].transform("size")
    df["p_novig"] = np.where(cnt >= 2, df["implied"] / tot, df["implied"] / 1.10)      # one-sided anytime TD carries ~10% margin
    df["market_code"] = df["market"].map({m: i for i, m in enumerate(MARKETS)}).astype(int)
    df["side_code"] = df["side"].map({s: i for i, s in enumerate(SIDES)}).astype(int)
    return df


# --------------------------------------------------------------------------- training and honest evaluation
def _model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=150, max_depth=3, learning_rate=0.05, l2_regularization=1.0, min_samples_leaf=100,
                                          categorical_features=[FEATURES.index(c) for c in CATEGORICAL], random_state=0)


def _scores(y, p, base, dec, top_q: float = 0.9) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss
    p = np.clip(p, 1e-4, 1 - 1e-4)
    edge = p - base
    top = edge >= np.quantile(edge, top_q)
    roi = float(np.mean(y[top] * dec[top] - 1.0)) if top.any() else 0.0
    return dict(rows=int(len(y)), brier_model=round(float(brier_score_loss(y, p)), 5), brier_baseline=round(float(brier_score_loss(y, base)), 5),
                logloss_model=round(float(log_loss(y, p)), 5), logloss_baseline=round(float(log_loss(y, np.clip(base, 1e-4, 1 - 1e-4))), 5),
                top_edge_legs=int(top.sum()), top_edge_hit=round(float(y[top].mean()), 4) if top.any() else None,
                top_edge_implied=round(float(base[top].mean()), 4) if top.any() else None, top_edge_roi=round(roi, 4))


def train(df: pd.DataFrame | None = None, cycle: int | None = None) -> dict:
    """Leave-one-season-out evaluation, then a final fit on all seasons. Saves a versioned model and says whether it earned promotion."""
    import joblib
    with _LOCK:
        df = build_dataset() if df is None else df
        seasons = sorted(df["season"].unique()) if len(df) else []
        if len(seasons) < 2:
            return {"trained": False, "reason": "need at least two seasons of data"}
        X, y = df[FEATURES], df["hit"].to_numpy()
        folds = []
        for s in seasons:
            tr, te = (df["season"] != s).to_numpy(), (df["season"] == s).to_numpy()
            m = _model().fit(X[tr], y[tr])
            p = m.predict_proba(X[te])[:, 1]
            sc = _scores(y[te], p, df.loc[te, "p_novig"].to_numpy(), df.loc[te, "dec"].to_numpy())
            sc.update(held_out_season=int(s), brier_gain=round(sc["brier_baseline"] - sc["brier_model"], 5))
            folds.append(sc)
        beats = all(f["brier_gain"] >= MIN_BRIER_GAIN for f in folds)
        profitable = all(f["top_edge_roi"] > 0 for f in folds)
        promoted = bool(beats and profitable)
        final = _model().fit(X, y)
        reg = registry()
        ver = f"v{len(reg['versions']) + 1:03d}"
        DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(final, DIR / f"jev_inhouse_{ver}.joblib")
        report = {"version": ver, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rows": int(len(df)),
                  "seasons": [int(s) for s in seasons], "features": FEATURES, "model": "HistGradientBoostingClassifier (scikit-learn)",
                  "folds": folds, "promoted": promoted,
                  "gate": {"beats_baseline_in_every_season": bool(beats), "profitable_top_edge_in_every_season": bool(profitable),
                           "min_brier_gain": MIN_BRIER_GAIN},
                  "verdict": ("Promoted: beats the price in every held-out season and its biggest-edge legs were profitable in each."
                              if promoted else "Not promoted: " + ("it does not beat the price-implied baseline in every held-out season. " if not beats else "") +
                              ("Its biggest-edge legs were not profitable in every held-out season. " if not profitable else "") +
                              "The market looks efficient at these features; the model stays on file but is not used."),
                  "caveat": "Lines are synthetic (player median, shaded), not real sportsbook lines. Passing this gate is necessary, not sufficient: validate against real historical lines before any live use.",
                  "cycle": cycle}
        (DIR / f"jev_inhouse_{ver}.json").write_text(json.dumps(report, indent=1))
        reg["versions"].append({k: report[k] for k in ("version", "trained_at", "rows", "promoted", "cycle")})
        reg["latest"] = ver
        reg["promoted"] = ver if promoted else reg.get("promoted")
        (DIR / "registry.json").write_text(json.dumps(reg, indent=1))
    try:
        import boo_store
        threading.Thread(target=boo_store.push_dir, args=(DIR, "myboo/boo_models"), daemon=True).start()
    except Exception:
        pass
    return {"trained": True, **{k: report[k] for k in ("version", "rows", "promoted", "verdict")}, "folds": folds}


def registry() -> dict:
    try:
        return json.loads((DIR / "registry.json").read_text())
    except (OSError, ValueError):
        return {"latest": None, "promoted": None, "versions": []}


def maybe_train(cycle: int) -> dict | None:
    """Called after every harvest cycle: train when there is no model yet, or every TRAIN_EVERY_CYCLES cycles."""
    reg = registry()
    last = (reg["versions"][-1].get("cycle") if reg["versions"] else None)
    if reg["latest"] and last is not None and cycle - last < TRAIN_EVERY_CYCLES:
        return None
    return train(cycle=cycle)


def status() -> dict:
    reg = registry()
    out = {"model": "scikit-learn HistGradientBoostingClassifier", "versions": len(reg["versions"]), "latest": reg["latest"], "promoted": reg["promoted"]}
    if reg["latest"]:
        try:
            rep = json.loads((DIR / f"jev_inhouse_{reg['latest']}.json").read_text())
            out.update(trained_at=rep["trained_at"], rows=rep["rows"], verdict=rep["verdict"], caveat=rep.get("caveat"),
                       folds=[{k: f[k] for k in ("held_out_season", "brier_gain", "top_edge_roi", "top_edge_legs")} for f in rep["folds"]])
        except (OSError, ValueError):
            pass
    return out


def load_promoted():
    """The promoted model, or None. JEV only ever uses a model that earned promotion."""
    reg = registry()
    if not reg["promoted"]:
        return None
    import joblib
    p = DIR / f"jev_inhouse_{reg['promoted']}.joblib"
    return joblib.load(p) if p.exists() else None


# --------------------------------------------------------------------------- teaching: curriculum -> chat SFT (Hugging Face TRL format)
SYSTEM = ("You are MY BOO, Big Proppa's training authority. Answer from the curriculum release and its evidence. "
          "State the probability of profit, how often the slip hits versus what the price implies, and the caveat that results come from the tested real seasons.")


def curriculum_sft(release: str) -> str | None:
    import boo_curriculum
    rel = boo_curriculum.get(release)
    if rel is None:
        return None
    q = {"shape": "Should I build a {t} parlay?", "style_tier": "What do you think of the {t} betting style?",
         "n_legs": "How do {t}s perform?", "sgp": "How do {t}s perform?", "tier": "How do {t} betters do?"}
    rows = []
    for u in rel["units"]:
        for l in u["lessons"]:
            e = l["evidence"]
            ask = ("Should I copy this win? " + l["title"]) if l["kind"] == "case" else q.get(l["kind"], "What does the data say about {t}?").format(t=l["title"])
            ans = l["rule"] + (f" Evidence: {e['slips']:,} slips across {e['studies']} stud{'y' if e['studies'] == 1 else 'ies'}." if "roi" in e else "")
            if l["verdict"] == "teach":
                ans = "Yes, it is one of the better-supported parlay types. " + ans
            elif l["verdict"] in ("fragile", "avoid"):
                ans = "I would not build it. " + ans
            rows.append(json.dumps({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ask},
                                                 {"role": "assistant", "content": ans}],
                                    "meta": {"release": release, "lesson": l["id"], "verdict": l["verdict"], "unit": u["id"]}}))
    return "\n".join(rows) + "\n"

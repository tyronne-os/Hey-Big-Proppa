"""
BETTER-VERSE STRATEGY LAB: which parlay strategy actually made the most money?

One universe is one roster of betters; their luck is part of the story. This pools MANY universes (different rosters
and different random picks) over BOTH real seasons, so a strategy is judged on thousands of bettor-seasons instead of
a handful. Nothing is filtered: lucky and unlucky betters all count, exactly as the money fell.

For every strategy (style x tier, tier, style, legs per slip, same-game vs cross-game, exact slip shape) it reports
  * pooled ROI (profit per $ staked) with a 95% confidence interval from a bootstrap over bettor-seasons,
  * probability rankings: P(profit), P(profit in BOTH seasons) and P(beat the field) from the same bootstrap, slip hit probability with a 95% Wilson range
    against the probability the price implies, and an overall rank by P(profit),
  * profit per slip, slip hit rate, share of bettor-seasons that finished in profit,
  * ROI in each real season, whether it beat the whole field in BOTH seasons, and whether it was in profit in both.

Honest limit: the NFL results are the same two real seasons in every universe, so extra universes average out the
betters' randomness but not what really happened in 2024-25. The "beat the field in both seasons" flag is the
check against a strategy that only fit one season.

Output: lake/gold/nfl/betterverse_studies/<study_id>/study.json (not committed; mirrored to the private HF dataset).
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time

import numpy as np
import pandas as pd

import betterverse_bettors as mb
import betterverse_obsidian as ob
import betterverse_sim as sim

OUT = sim.md._GOLD / "betterverse_studies"
SEASONS = (2024, 2025)
BOOT = 300
SCHEMA = "boo.bv_study.v1"
_RID = re.compile(r"st_u\d+_n\d+_s-?\d+")
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()
COLS = ["season", "week", "bettor_id", "archetype", "tier", "combo_signature", "n_legs", "sgp",
        "stake", "payout", "won", "decimal_odds"]


def study_id(universes: int, bettors: int, seed: int) -> str:
    return f"st_u{universes}_n{bettors}_s{seed}"


def valid(sid: str) -> bool:
    return bool(_RID.fullmatch(sid or ""))


def _table(g: pd.DataFrame, col: str, label, min_slips: int, rng: np.random.Generator,
           field_roi: float, field_by_season: dict, top: int | None = None) -> list[dict]:
    keys = g[col].value_counts()
    keys = keys[keys >= min_slips]
    if top:
        keys = keys.head(top)
    rows = []
    for key in keys.index:
        d = g[g[col] == key]
        u = d.groupby("unit", sort=False).agg(stake=("stake", "sum"), ret=("payout", "sum"), season=("season", "first"))
        st, rt = u["stake"].to_numpy(), u["ret"].to_numpy()
        tot_s, tot_r = st.sum(), rt.sum()
        roi = (tot_r - tot_s) / tot_s
        idx = rng.integers(0, len(st), (BOOT, len(st)))
        boot = (rt[idx].sum(1) - st[idx].sum(1)) / st[idx].sum(1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        seas = {int(sn): float((dd["payout"].sum() - dd["stake"].sum()) / dd["stake"].sum()) for sn, dd in d.groupby("season")}
        both = len(seas) == len(field_by_season) and all(seas[s] > field_by_season[s] for s in seas)
        useason = u["season"].to_numpy()
        p_by = {}
        for sn in np.unique(useason):                      # resample inside each real season on its own
            m = useason == sn
            s_, r_ = st[m], rt[m]
            ii = rng.integers(0, len(s_), (BOOT, len(s_)))
            p_by[int(sn)] = float((((r_[ii].sum(1) - s_[ii].sum(1)) / s_[ii].sum(1)) > 0).mean())
        p_both = float(np.prod(list(p_by.values()))) if len(p_by) == len(field_by_season) else float((boot > 0).mean())
        n, hr = len(d), float(d["won"].mean())
        z = 1.96
        wc = (hr + z * z / (2 * n)) / (1 + z * z / n)
        wh = z * np.sqrt(hr * (1 - hr) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        implied = float(d["imp"].mean())
        rows.append(dict(
            p_profit=round(float((boot > 0).mean()), 4), p_both_seasons=round(p_both, 4),
            p_profit_by_season={str(k): round(v, 4) for k, v in p_by.items()}, p_beat_field=round(float((boot > field_roi).mean()), 4),
            hit_lo=round(float(max(0.0, wc - wh)), 4), hit_hi=round(float(min(1.0, wc + wh)), 4),
            implied=round(implied, 4), edge_pts=round(hr - implied, 4),
            key=str(key), label=label(key), slips=int(len(d)), units=int(len(u)), staked=round(float(tot_s), 2),
            roi=round(float(roi), 4), ci_lo=round(float(lo), 4), ci_hi=round(float(hi), 4),
            edge_vs_field=round(float(roi - field_roi), 4), profit_per_slip=round(float((tot_r - tot_s) / len(d)), 3),
            hit_rate=round(float(d["won"].mean()), 4), profitable_share=round(float((rt > st).mean()), 4),
            avg_legs=round(float(d["n_legs"].mean()), 2), by_season={str(k): round(v, 4) for k, v in seas.items()},
            beats_field_both_seasons=bool(both), beats_field_95=bool(lo > field_roi), profitable_95=bool(lo > 0),
            profitable_both_seasons=bool(len(seas) == len(field_by_season) and all(v > 0 for v in seas.values()))))
    rows.sort(key=lambda r: -r["roi"])
    for i, r in enumerate(sorted(rows, key=lambda r: (-r["p_both_seasons"], -r["p_profit"], -r["roi"])), start=1):
        r["rank_p"] = i                                  # 1 = most likely to make money in BOTH real seasons
    return rows


def run_study(universes: int = 20, bettors: int = 150, seed: int = 100, progress=None) -> dict:
    t0 = time.time()
    frames, idents = [], []
    total = universes * len(SEASONS)
    done = 0
    for u in range(universes):
        for season in SEASONS:
            _, _, _, slips, bdf = sim._run(season, bettors, seed + u, None, keep_legs=False)
            sl = slips[slips["won"].notna()][COLS].copy()
            sl["won"] = sl["won"].astype(bool)
            sl["universe"] = u
            frames.append(sl)
            idents.append(bdf[["bettor_id", "username", "tier", "tier_label", "archetype", "label", "unit", "final_bankroll"]]
                          .assign(universe=u, season=season))
            done += 1
            if progress:
                progress(done / total, f"universe {u + 1}/{universes} · {season}")
    g = pd.concat(frames, ignore_index=True)
    ident = pd.concat(idents, ignore_index=True)
    g["imp"] = 1.0 / g["decimal_odds"]
    g["unit"] = g["universe"].astype(str) + "-" + g["season"].astype(str) + "-" + g["bettor_id"].astype(str)
    g["style_tier"] = g["archetype"] + "|" + g["tier"]
    g["sgp_label"] = np.where(g["sgp"], "sgp", "cross")
    g["n_legs_k"] = g["n_legs"].clip(upper=8).astype(int)

    field_roi = float((g["payout"].sum() - g["stake"].sum()) / g["stake"].sum())
    field_by_season = {int(s): float((d["payout"].sum() - d["stake"].sum()) / d["stake"].sum()) for s, d in g.groupby("season")}
    rng = np.random.default_rng(seed)
    arch_label = {k: v["label"] for k, v in mb.ARCHETYPES.items()}
    tier_label = {k: v["label"] for k, v in mb.TIERS.items()}

    def style_tier_label(k):
        a, t = k.split("|")
        return f"{arch_label[a]} · {tier_label[t]}"

    dims = {
        "style_tier": _table(g, "style_tier", style_tier_label, 150, rng, field_roi, field_by_season),
        "tier": _table(g, "tier", lambda k: tier_label[k], 150, rng, field_roi, field_by_season),
        "archetype": _table(g, "archetype", lambda k: arch_label[k], 150, rng, field_roi, field_by_season),
        "n_legs": _table(g, "n_legs_k", lambda k: f"{k}{'+' if k == 8 else ''}-leg slip", 150, rng, field_roi, field_by_season),
        "sgp": _table(g, "sgp_label", lambda k: "Same-game parlay" if k == "sgp" else "Cross-game slip", 150, rng, field_roi, field_by_season),
        "shape": _table(g, "combo_signature", ob._shape, 150, rng, field_roi, field_by_season, top=60),
    }

    net = g.groupby(["universe", "season", "bettor_id"]).agg(slips=("won", "size"), staked=("stake", "sum"), returned=("payout", "sum")).reset_index()
    best_slip = g.sort_values("payout", ascending=False).drop_duplicates(["universe", "season", "bettor_id"])[
        ["universe", "season", "bettor_id", "combo_signature", "decimal_odds", "payout"]].rename(
        columns={"combo_signature": "best_signature", "decimal_odds": "best_odds", "payout": "best_payout"})
    w = ident.merge(net, on=["universe", "season", "bettor_id"], how="left").merge(best_slip, on=["universe", "season", "bettor_id"], how="left")
    w["net"] = w["final_bankroll"] - sim.START_BANKROLL
    cols = ["username", "tier_label", "label", "unit", "season", "universe", "final_bankroll", "net", "slips", "best_signature", "best_odds", "best_payout"]
    top_winners = w.sort_values("net", ascending=False).head(25)[cols].round(2).to_dict("records")
    rookie_winners = w[w["tier"].isin(["casual", "degen"])].sort_values("net", ascending=False).head(15)[cols].round(2).to_dict("records")

    ss = g.groupby(["style_tier", "combo_signature"]).agg(slips=("won", "size"), staked=("stake", "sum"), ret=("payout", "sum"), wins=("won", "sum")).reset_index()
    ss = ss[ss["slips"] >= 30]
    style_shapes = {}
    for key, d in ss.groupby("style_tier"):
        d = d.sort_values("slips", ascending=False).head(6)
        style_shapes[key] = [dict(shape=r.combo_signature, slips=int(r.slips), wins=int(r.wins), roi=round(float((r.ret - r.staked) / r.staked), 4))
                             for r in d.itertuples()]

    st = dims["style_tier"]
    proven = [r for r in st if r["profitable_both_seasons"] and r["profitable_95"]]
    profit = [r for r in st if r["profitable_95"]]
    headlines = [
        f"{len(g):,} slips from {len(w):,} bettor-seasons ({universes} universes × {len(SEASONS)} real seasons). The house kept "
        f"{-field_roi:.1%} of every dollar staked."]
    if st:
        b = st[0]
        headlines.append(f"Most money per $ staked: {b['label']} at {b['roi']:+.1%} ROI (95% CI {b['ci_lo']:+.1%} to {b['ci_hi']:+.1%}) "
                         f"over {b['slips']:,} slips{'; ahead of the field in both seasons' if b['beats_field_both_seasons'] else ''}"
                         f"{' — proven' if b['profitable_95'] else ' — promising, not yet proven (the interval still includes losing money)'}.")
    if profit:
        headlines.append(f"{len(profit)} strateg{'y' if len(profit) == 1 else 'ies'} turned a profit with 95% confidence: "
                         + ", ".join(r["label"] for r in profit[:4]) + ".")
    else:
        headlines.append("No strategy turned a profit with 95% confidence at these prices.")
    if proven:
        headlines.append("Made money with 95% confidence AND finished in profit in both real seasons: " + ", ".join(r["label"] for r in proven[:4]) + ".")
    ranked = sorted(dims["shape"] + st, key=lambda r: (-r["p_both_seasons"], -r["p_profit"], -r["roi"]))
    if ranked:
        t = ranked[0]
        headlines.append(f"Most likely to make money: {t['label']} "
                         f"({t['p_both_seasons']:.0%} chance of profit in both real seasons, {t['hit_rate']:.0%} of slips hit vs {t['implied']:.0%} implied by the price).")
    if st:
        worst = st[-1]
        headlines.append(f"Money losers: {worst['label']} ({worst['roi']:+.1%} ROI, {worst['hit_rate']:.0%} slip hit rate).")

    return sim._clean(dict(
        schema=SCHEMA, study_id=study_id(universes, bettors, seed), universes=universes, bettors_per_universe=bettors,
        seasons=list(SEASONS), seed=seed, bettor_seasons=int(len(w)), slips=int(len(g)), seconds=round(time.time() - t0, 1),
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        field=dict(roi=round(field_roi, 4), by_season={str(k): round(v, 4) for k, v in field_by_season.items()}),
        headlines=headlines, dims=dims, style_shapes=style_shapes, top_winners=top_winners, rookie_winners=rookie_winners,
        caveat="Every universe replays the same two real NFL seasons, so more universes average out the betters' randomness, "
               "not what actually happened in 2024-25. Trust strategies that win in both seasons."))


def _write(sid: str, result: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f".{sid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    (tmp / "study.json").write_text(json.dumps(result, indent=1))
    shutil.rmtree(OUT / sid, ignore_errors=True)
    tmp.rename(OUT / sid)


def start(universes: int = 20, bettors: int = 150, seed: int = 100) -> dict:
    sid = study_id(universes, bettors, seed)
    with _LOCK:
        cur = _RUNS.get(sid)
        if cur and cur["state"] == "running":
            return cur
        if (OUT / sid / "study.json").exists():
            _RUNS[sid] = dict(study_id=sid, state="done", progress=1.0, error=None)
            return _RUNS[sid]
        _RUNS[sid] = st = dict(study_id=sid, state="running", progress=0.0, label="starting", error=None, started=time.time())

    def go():
        try:
            res = run_study(universes, bettors, seed, lambda p, label: st.update(progress=round(p, 3), label=label))
            _write(sid, res)
            st.update(state="done", progress=1.0, finished=time.time())
            try:
                import boo_store
                boo_store.push_dir(OUT / sid, f"myboo/betterverse_studies/{sid}")
            except Exception:
                pass
        except Exception as e:
            st.update(state="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=go, daemon=True, name=f"study-{sid}").start()
    return st


def status(sid: str) -> dict:
    if not valid(sid):
        return dict(study_id=sid, state="missing")
    if sid in _RUNS:
        return _RUNS[sid]
    return dict(study_id=sid, state="done", progress=1.0) if (OUT / sid / "study.json").exists() else dict(study_id=sid, state="missing")


def load(sid: str) -> dict | None:
    if not valid(sid):
        return None
    p = OUT / sid / "study.json"
    return json.loads(p.read_text()) if p.exists() else None


def studies() -> list[dict]:
    out = []
    if OUT.exists():
        for d in sorted(OUT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            f = d / "study.json"
            if d.is_dir() and f.exists():
                s = json.loads(f.read_text())
                out.append({k: s[k] for k in ("study_id", "universes", "bettors_per_universe", "bettor_seasons", "slips", "seconds", "created")})
    return out

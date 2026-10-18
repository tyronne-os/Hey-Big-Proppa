"""
BETTER-VERSE STRATEGY LAB: which parlay strategy actually made the most money?

One universe is one roster of betters; their luck is part of the story. This pools MANY universes (different rosters
and different random picks) over EVERY tested real season, so a strategy is judged on thousands of bettor-seasons instead of
a handful. Nothing is filtered: lucky and unlucky betters all count, exactly as the money fell.

For every strategy (style x tier, tier, style, legs per slip, same-game vs cross-game, exact slip shape) it reports
  * pooled ROI (profit per $ staked) with a 95% confidence interval from a bootstrap over bettor-seasons,
  * probability rankings: P(profit), P(profit in EVERY tested season) and P(beat the field) from the same bootstrap, slip hit probability with a 95% Wilson range
    against the probability the price implies, and an overall rank by P(profit),
  * profit per slip, slip hit rate, share of bettor-seasons that finished in profit,
  * ROI in each real season, whether it beat the whole field in EVERY season, and whether it was in profit in every season.

Honest limit: the NFL results are the same real seasons in every universe, so extra universes average out the
betters' randomness but not what really happened in the real seasons. The "profit in every season" flag is the
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
SEASONS = sim.md.SEASONS                 # every real season the Better-Verse can test: 2023, 2024, 2025
BOOT = 300
SCHEMA = "boo.bv_study.v1"
_RID = re.compile(r"st_u\d+_n\d+_s-?\d+_y\d{4}(?:-\d{4})*")
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()
COLS = ["season", "week", "bettor_id", "archetype", "tier", "combo_signature", "n_legs", "sgp",
        "stake", "payout", "won", "decimal_odds"]


def study_id(universes: int, bettors: int, seed: int, seasons=None) -> str:
    return f"st_u{universes}_n{bettors}_s{seed}_y" + "-".join(str(y) for y in (seasons or SEASONS))


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
            p_profit=round(float((boot > 0).mean()), 4), p_all_seasons=round(p_both, 4),
            p_profit_by_season={str(k): round(v, 4) for k, v in p_by.items()}, p_beat_field=round(float((boot > field_roi).mean()), 4),
            hit_lo=round(float(max(0.0, wc - wh)), 4), hit_hi=round(float(min(1.0, wc + wh)), 4),
            implied=round(implied, 4), edge_pts=round(hr - implied, 4),
            key=str(key), label=label(key), slips=int(len(d)), units=int(len(u)), staked=round(float(tot_s), 2),
            roi=round(float(roi), 4), ci_lo=round(float(lo), 4), ci_hi=round(float(hi), 4),
            edge_vs_field=round(float(roi - field_roi), 4), profit_per_slip=round(float((tot_r - tot_s) / len(d)), 3),
            hit_rate=round(float(d["won"].mean()), 4), profitable_share=round(float((rt > st).mean()), 4),
            avg_legs=round(float(d["n_legs"].mean()), 2), by_season={str(k): round(v, 4) for k, v in seas.items()},
            beats_field_all_seasons=bool(both), beats_field_95=bool(lo > field_roi), profitable_95=bool(lo > 0),
            profitable_all_seasons=bool(len(seas) == len(field_by_season) and all(v > 0 for v in seas.values()))))
    rows.sort(key=lambda r: -r["roi"])
    for i, r in enumerate(sorted(rows, key=lambda r: (-r["p_all_seasons"], -r["p_profit"], -r["roi"])), start=1):
        r["rank_p"] = i                                  # 1 = most likely to make money in EVERY tested season
    return rows


def run_study(universes: int = 20, bettors: int = 150, seed: int = 100, progress=None, seasons=None) -> dict:
    t0 = time.time()
    seasons = tuple(sorted(seasons or SEASONS))
    frames, idents = [], []
    total = universes * len(seasons)
    done = 0
    for u in range(universes):
        for season in seasons:
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
    proven = [r for r in st if r["profitable_all_seasons"] and r["profitable_95"]]
    profit = [r for r in st if r["profitable_95"]]
    headlines = [
        f"{len(g):,} slips from {len(w):,} bettor-seasons ({universes} universes × {len(seasons)} real seasons: {', '.join(map(str, seasons))}). The house kept "
        f"{-field_roi:.1%} of every dollar staked."]
    if st:
        b = st[0]
        headlines.append(f"Most money per $ staked: {b['label']} at {b['roi']:+.1%} ROI (95% CI {b['ci_lo']:+.1%} to {b['ci_hi']:+.1%}) "
                         f"over {b['slips']:,} slips{'; ahead of the field in every season' if b['beats_field_all_seasons'] else ''}"
                         f"{' — proven' if b['profitable_95'] else ' — promising, not yet proven (the interval still includes losing money)'}.")
    if profit:
        headlines.append(f"{len(profit)} strateg{'y' if len(profit) == 1 else 'ies'} turned a profit with 95% confidence: "
                         + ", ".join(r["label"] for r in profit[:4]) + ".")
    else:
        headlines.append("No strategy turned a profit with 95% confidence at these prices.")
    if proven:
        headlines.append("Made money with 95% confidence AND finished in profit in every tested season: " + ", ".join(r["label"] for r in proven[:4]) + ".")
    ranked = sorted(dims["shape"] + st, key=lambda r: (-r["p_all_seasons"], -r["p_profit"], -r["roi"]))
    if ranked:
        t = ranked[0]
        headlines.append(f"Most likely to make money: {t['label']} "
                         f"({t['p_all_seasons']:.0%} chance of profit in every tested season, {t['hit_rate']:.0%} of slips hit vs {t['implied']:.0%} implied by the price).")
    if st:
        worst = st[-1]
        headlines.append(f"Money losers: {worst['label']} ({worst['roi']:+.1%} ROI, {worst['hit_rate']:.0%} slip hit rate).")

    return sim._clean(dict(
        schema=SCHEMA, study_id=study_id(universes, bettors, seed, seasons), universes=universes, bettors_per_universe=bettors,
        seasons=list(seasons), seed=seed, bettor_seasons=int(len(w)), slips=int(len(g)), seconds=round(time.time() - t0, 1),
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        field=dict(roi=round(field_roi, 4), by_season={str(k): round(v, 4) for k, v in field_by_season.items()}),
        headlines=headlines, dims=dims, style_shapes=style_shapes, top_winners=top_winners, rookie_winners=rookie_winners,
        caveat=f"Every universe replays the same real NFL seasons ({', '.join(map(str, seasons))}), so more universes average out the betters' randomness, "
               "not what actually happened. Trust strategies that win in every season."))

def _write(sid: str, result: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f".{sid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    (tmp / "study.json").write_text(json.dumps(result, indent=1))
    shutil.rmtree(OUT / sid, ignore_errors=True)
    tmp.rename(OUT / sid)
    try:                                                    # MY BOO collects every study automatically
        import boo_harvest
        boo_harvest.on_study(sid)
    except Exception:
        pass


def start(universes: int = 20, bettors: int = 150, seed: int = 100, seasons=None) -> dict:
    seasons = tuple(sorted(seasons or SEASONS))
    sid = study_id(universes, bettors, seed, seasons)
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
            res = run_study(universes, bettors, seed, lambda p, label: st.update(progress=round(p, 3), label=label), seasons)
            _write(sid, res)
            st.update(state="done", progress=1.0, finished=time.time())
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
                out.append({k: s.get(k) for k in ("study_id", "seasons", "universes", "bettors_per_universe", "bettor_seasons", "slips", "seconds", "created")})
    return out


def compare(a_id: str, b_id: str, min_p: float = 0.5) -> dict | None:
    """How a strategy's standing changed between two studies (e.g. 2 seasons vs 3): rank, chance of profit in every season, ROI."""
    A, B = load(a_id), load(b_id)
    if A is None or B is None:
        return None
    out = {}
    for dim in ("shape", "style_tier", "n_legs", "sgp", "tier"):
        a = {r["key"]: r for r in A["dims"].get(dim, [])}
        b = {r["key"]: r for r in B["dims"].get(dim, [])}
        rows = []
        for k in sorted(set(a) | set(b)):
            ra, rb = a.get(k), b.get(k)
            pa, pb = (ra or {}).get("p_all_seasons"), (rb or {}).get("p_all_seasons")
            status = ("held" if (pa or 0) >= min_p and (pb or 0) >= min_p else "dropped" if (pa or 0) >= min_p else
                      "rose" if (pb or 0) >= min_p else "never-promising")
            rows.append(dict(key=k, label=(rb or ra)["label"], status=status,
                             rank_a=(ra or {}).get("rank_p"), rank_b=(rb or {}).get("rank_p"), p_all_a=pa, p_all_b=pb,
                             roi_a=(ra or {}).get("roi"), roi_b=(rb or {}).get("roi"),
                             hit_a=(ra or {}).get("hit_rate"), hit_b=(rb or {}).get("hit_rate"),
                             implied_b=(rb or {}).get("implied"), slips_a=(ra or {}).get("slips"), slips_b=(rb or {}).get("slips")))
        rows.sort(key=lambda r: (-(r["p_all_b"] or 0), -(r["p_all_a"] or 0)))
        out[dim] = rows
    tally = {s: sum(1 for r in out["shape"] if r["status"] == s) for s in ("held", "dropped", "rose", "never-promising")}
    return sim._clean(dict(a=dict(study_id=a_id, seasons=A["seasons"], slips=A["slips"], field=A["field"]),
                           b=dict(study_id=b_id, seasons=B["seasons"], slips=B["slips"], field=B["field"]), shape_tally=tally, dims=out))

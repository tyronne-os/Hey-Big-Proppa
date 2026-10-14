"""
THE BOOKIE MULTIVERSE engine: N bettors x one NFL season, every slip graded against what really happened.

Output (lake/gold/nfl/multiverse/<run_id>/), ready for MY BOO to ingest as-is:
  legs.parquet      boo.mv_leg.v1   one row per leg
  slips.parquet     boo.mv_slip.v1  one row per slip
  bettors.parquet   boo.mv_bettor.v1 one row per bettor's season
  insights.json     archetype leaderboard, slip-shape table (never-won / consistent flags), market edges
  manifest.json     seed, season, counts, schema versions

Same (season, bettors, seed, mix) -> identical files. No network, no model calls: pure numpy/pandas.
"""
from __future__ import annotations

import hashlib
import re
import json
import shutil
import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import multiverse_bettors as mb
import multiverse_data as md
import multiverse_rules as rules

OUT = md._GOLD / "multiverse"
START_BANKROLL = 100.0
MIN_N = 30                       # a slip shape needs this many tickets before it gets a verdict
SCHEMAS = {"legs": "boo.mv_leg.v1", "slips": "boo.mv_slip.v1", "bettors": "boo.mv_bettor.v1", "insights": "boo.mv_insights.v1"}
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()


def run_id(season: int, n: int, seed: int, mix: dict | None) -> str:
    h = hashlib.sha1(json.dumps(mix or {}, sort_keys=True).encode()).hexdigest()[:6]
    return f"mv{season}_n{n}_s{seed}_{h}"


# --------------------------------------------------------------------------- per-week pools
class _Week:
    def __init__(self, season: int, week: int):
        self.items = list(md.menu(season, week))
        self.market = np.array([i["market"] for i in self.items])
        self.side = np.array([i["side"] for i in self.items])
        self.game = np.array([i["game_id"] for i in self.items])
        self.pop = np.clip(np.array([i["pop"] for i in self.items], dtype=float), 0.05, 1.0)
        self.games = sorted(set(self.game))
        self._pool: dict[str, np.ndarray] = {}

    def pool(self, arch: str) -> np.ndarray:
        if arch not in self._pool:
            a = mb.ARCHETYPES[arch]
            ok = np.ones(len(self.items), dtype=bool)
            if a["markets"]:
                ok &= np.isin(self.market, list(a["markets"]))
            if a["sides"]:
                ok &= np.isin(self.side, list(a["sides"]))
            self._pool[arch] = np.flatnonzero(ok)
        return self._pool[arch]


def _weights(wk: _Week, idx: np.ndarray, b: mb.Bettor) -> np.ndarray:
    w = wk.pop[idx] ** b.pop_bias
    up = np.isin(wk.side[idx], ["over", "yes", "fav"])
    w = w * np.where(up, b.over_lean, 1 - b.over_lean)
    return w / w.sum()


def _build_slip(wk: _Week, b: mb.Bettor, rng: np.random.Generator) -> list[dict] | None:
    a = mb.ARCHETYPES[b.archetype]
    idx = wk.pool(b.archetype)
    if a["sgp"] == "single":
        g = wk.games[int(rng.integers(len(wk.games)))]
        idx = idx[wk.game[idx] == g]
    if len(idx) == 0:
        return None
    k = int(rng.integers(b.legs_lo, b.legs_hi + 1))
    k = min(k, len(idx))
    order = rng.choice(idx, size=min(len(idx), k * 6), replace=False, p=_weights(wk, idx, b))
    legs: list[dict] = []
    games: set = set()
    for j in order:
        it = wk.items[int(j)]
        if it["game_id"] in games:
            if a["sgp"] == "never" or (a["sgp"] == "spread" and rng.random() < 0.85):
                continue
        if rules.validate(legs + [it])[0]:
            legs.append(it)
            games.add(it["game_id"])
            if len(legs) == k:
                break
    return legs if len(legs) >= min(2, k) else None


# --------------------------------------------------------------------------- run
def simulate(season: int, n: int = 500, seed: int = 7, mix: dict | None = None, progress=None) -> dict:
    t0 = time.time()
    rid = run_id(season, n, seed, mix)
    bettors = mb.roster(n, seed, mix)
    weeks = md.weeks(season)
    wk_cache = {w: _Week(season, w) for w in weeks}
    rngs = [np.random.default_rng(b.seed) for b in bettors]
    bank = np.full(n, START_BANKROLL)
    staked = np.zeros(n)
    returned = np.zeros(n)
    peak = bank.copy()
    max_dd = np.zeros(n)
    bust_week = np.zeros(n, dtype=int)
    last_net = np.zeros(n)
    leg_rows, slip_rows = [], []
    slip_id = 0

    for wi, w in enumerate(weeks):
        wk = wk_cache[w]
        for b in bettors:
            i = b.bettor_id
            if bust_week[i]:
                continue
            rng = rngs[i]
            n_slips = int(rng.integers(b.slips_lo, b.slips_hi + 1))
            mult = b.chase if last_net[i] < 0 else 1.0
            week_net = 0.0
            for _ in range(n_slips):
                stake = round(min(bank[i], max(1.0, bank[i] * b.stake_pct * mult)), 2)
                if stake < 1.0:
                    break
                legs = _build_slip(wk, b, rng)
                if not legs:
                    continue
                live = [l for l in legs if l["hit"] is not None]
                dec, sgp = rules.price(live) if live else (1.0, False)
                full_dec, full_sgp = rules.price(legs)
                if not live:
                    won, payout = None, stake                    # every leg void: refund
                else:
                    won = all(l["hit"] == 1 for l in live)
                    payout = round(stake * dec, 2) if won else 0.0
                bank[i] = round(bank[i] - stake + payout, 2)
                staked[i] += stake
                returned[i] += payout
                week_net += payout - stake
                sig = rules.signature(legs, full_sgp)
                slip_rows.append(dict(
                    run_id=rid, season=season, week=w, bettor_id=i, archetype=b.archetype, slip_id=slip_id,
                    n_legs=len(legs), n_live=len(live), combo_signature=sig, sgp=full_sgp,
                    decimal_odds=full_dec, settled_odds=dec, implied_prob=round(1 / full_dec, 5),
                    stake=stake, payout=payout, won=won, bankroll_after=bank[i]))
                for li, l in enumerate(legs):
                    leg_rows.append(dict(
                        run_id=rid, season=season, week=w, bettor_id=i, archetype=b.archetype, slip_id=slip_id,
                        leg_idx=li, market=l["market"], side=l["side"], player_id=l["player_id"], player=l["player"],
                        team=l["team"], game_id=l["game_id"], line=l["line"], price=l["dec"],
                        implied_prob=round(1 / l["dec"], 5), actual=l["actual"],
                        hit=l["hit"], void=l["hit"] is None, same_game=full_sgp, slip_won=won))
                slip_id += 1
            last_net[i] = week_net
            peak[i] = max(peak[i], bank[i])
            max_dd[i] = max(max_dd[i], (peak[i] - bank[i]) / peak[i] if peak[i] else 0)
            if bank[i] < 1.0:
                bust_week[i] = w
        if progress:
            progress((wi + 1) / len(weeks), w)

    legs_df = pd.DataFrame(leg_rows)
    slips_df = pd.DataFrame(slip_rows)
    won_ct = slips_df.groupby("bettor_id")["won"].apply(lambda s: int((s == True).sum())) if len(slips_df) else pd.Series(dtype=int)  # noqa: E712
    slip_ct = slips_df.groupby("bettor_id").size() if len(slips_df) else pd.Series(dtype=int)
    bettors_df = pd.DataFrame([dict(
        run_id=rid, season=season, **b.dict(), label=mb.ARCHETYPES[b.archetype]["label"],
        final_bankroll=bank[b.bettor_id], staked=round(staked[b.bettor_id], 2), returned=round(returned[b.bettor_id], 2),
        roi=round((returned[b.bettor_id] - staked[b.bettor_id]) / staked[b.bettor_id], 4) if staked[b.bettor_id] else 0.0,
        max_drawdown=round(max_dd[b.bettor_id], 4), bust_week=int(bust_week[b.bettor_id]) or None,
        slips=int(slip_ct.get(b.bettor_id, 0)), slips_won=int(won_ct.get(b.bettor_id, 0)),
    ) for b in bettors])

    ins = insights(legs_df, slips_df, bettors_df)
    ins.update(run_id=rid, season=season, bettors=n, seed=seed, seconds=round(time.time() - t0, 2))
    _write(rid, legs_df, slips_df, bettors_df, ins, dict(
        run_id=rid, season=season, bettors=n, seed=seed, mix=mix or {}, schemas=SCHEMAS,
        rows={"legs": len(legs_df), "slips": len(slips_df), "bettors": len(bettors_df)},
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), seconds=ins["seconds"],
        start_bankroll=START_BANKROLL, pricing="real 2024-25 closing game odds; props -115; anytime TD prior-rate + margin; SGP haircut"))
    return ins


def _clean(o):
    """NaN/inf -> None, numpy scalars -> python, so every file and response is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def _f(x) -> float:
    return round(float(x), 4)


def insights(legs: pd.DataFrame, slips: pd.DataFrame, bettors: pd.DataFrame) -> dict:
    graded = slips[slips["won"].notna()].copy()
    graded["won"] = graded["won"].astype(bool)

    arch = []
    for name, g in bettors.groupby("archetype"):
        s = graded[graded["archetype"] == name]
        a = mb.ARCHETYPES[name]
        arch.append(dict(
            archetype=name, label=a["label"], desc=a["desc"], bettors=len(g),
            roi=_f((g["returned"].sum() - g["staked"].sum()) / max(g["staked"].sum(), 1e-9)),
            median_final=_f(g["final_bankroll"].median()), profitable_share=_f((g["final_bankroll"] > START_BANKROLL).mean()),
            bust_rate=_f(g["bust_week"].notna().mean()), slip_hit_rate=_f(s["won"].mean() if len(s) else 0),
            avg_legs=_f(s["n_legs"].mean() if len(s) else 0), avg_odds=_f(s["decimal_odds"].median() if len(s) else 0),
            best_bettor=int(g.loc[g["final_bankroll"].idxmax(), "bettor_id"]), best_final=_f(g["final_bankroll"].max())))
    arch.sort(key=lambda r: -r["roi"])

    combos = []
    for sig, g in graded.groupby("combo_signature"):
        n = len(g)
        wins = int(g["won"].sum())
        hit, imp = g["won"].mean(), g["implied_prob"].mean()
        roi = (g["payout"].sum() - g["stake"].sum()) / g["stake"].sum()
        wk_win = int(g[g["won"]]["week"].nunique())
        combos.append(dict(signature=sig, n=n, wins=wins, hit_rate=_f(hit), implied=_f(imp), edge=_f(hit - imp),
                           roi=_f(roi), weeks_with_win=wk_win, avg_legs=_f(g["n_legs"].mean()),
                           never_won=bool(n >= MIN_N and wins == 0),
                           consistent=bool(n >= MIN_N and hit - imp >= 0.05 and wk_win >= 8)))
    combos.sort(key=lambda r: (-r["n"]))

    live = legs[~legs["void"]].copy()
    live["hit"] = live["hit"].astype(float)
    markets = []
    for (mk, side), g in live.groupby(["market", "side"]):
        markets.append(dict(market=mk, side=side, n=len(g), hit_rate=_f(g["hit"].mean()),
                            implied=_f(g["implied_prob"].mean()), edge=_f(g["hit"].mean() - g["implied_prob"].mean()),
                            void_rate=_f(legs[(legs["market"] == mk) & (legs["side"] == side)]["void"].mean())))
    markets.sort(key=lambda r: -r["edge"])

    by_legs = [dict(n_legs=int(k), n=len(g), hit_rate=_f(g["won"].mean()), implied=_f(g["implied_prob"].mean()),
                    roi=_f((g["payout"].sum() - g["stake"].sum()) / g["stake"].sum()))
               for k, g in graded.groupby("n_legs")]
    sgp = [dict(sgp=bool(k), n=len(g), hit_rate=_f(g["won"].mean()),
                roi=_f((g["payout"].sum() - g["stake"].sum()) / g["stake"].sum())) for k, g in graded.groupby("sgp")]
    weekly = [dict(week=int(k), slips=len(g), hit_rate=_f(g["won"].mean()), staked=_f(g["stake"].sum()),
                   paid=_f(g["payout"].sum())) for k, g in graded.groupby("week")]

    # player-level: which legs cashed most consistently (min 20 picks)
    pl = live[live["player_id"] != ""].groupby(["player", "market", "side"]).agg(n=("hit", "size"), hit_rate=("hit", "mean"),
                                                                                implied=("implied_prob", "mean")).reset_index()
    pl = pl[pl["n"] >= 20]
    pl["edge"] = pl["hit_rate"] - pl["implied"]
    hot = pl.sort_values("edge", ascending=False).head(15).round(4).to_dict("records")
    cold = pl.sort_values("edge").head(15).round(4).to_dict("records")

    top = bettors.sort_values("final_bankroll", ascending=False).head(10)[
        ["bettor_id", "archetype", "label", "final_bankroll", "roi", "slips", "slips_won"]].to_dict("records")
    never = [c for c in combos if c["never_won"]]
    steady = sorted([c for c in combos if c["consistent"]], key=lambda c: -c["edge"])
    total_stake = graded["stake"].sum()
    headlines = []
    if arch:
        headlines.append(f"Best archetype: {arch[0]['label']} ({arch[0]['roi']:+.1%} ROI); worst: {arch[-1]['label']} ({arch[-1]['roi']:+.1%}).")
    headlines.append(f"{(bettors['final_bankroll'] > START_BANKROLL).mean():.0%} of bettors finished up; "
                     f"{bettors['bust_week'].notna().mean():.0%} went broke.")
    if never:
        headlines.append(f"{len(never)} slip shapes were played {MIN_N}+ times and never cashed once.")
    if steady:
        headlines.append(f"{len(steady)} slip shapes beat their implied odds by 5+ pts across 8+ weeks — led by '{steady[0]['signature']}'.")
    if markets:
        headlines.append(f"Sharpest single leg: {markets[0]['market']} {markets[0]['side']} ({markets[0]['edge']:+.1%} vs implied).")

    return dict(
        schema=SCHEMAS["insights"], headlines=headlines,
        totals=dict(slips=len(slips), graded=len(graded), legs=len(legs), staked=_f(total_stake),
                    paid=_f(graded["payout"].sum()),
                    house_hold=_f(1 - graded["payout"].sum() / total_stake) if total_stake else 0,
                    slip_hit_rate=_f(graded["won"].mean() if len(graded) else 0)),
        archetypes=arch, combos=combos[:200], never_won=never, consistent=steady,
        markets=markets, by_legs=by_legs, sgp=sgp, weekly=weekly, hot_legs=hot, cold_legs=cold, top_bettors=top)


def _write(rid: str, legs, slips, bettors, ins: dict, manifest: dict) -> None:
    d = OUT / rid
    tmp = OUT / f".{rid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    legs.to_parquet(tmp / "legs.parquet", index=False)
    slips.to_parquet(tmp / "slips.parquet", index=False)
    bettors.to_parquet(tmp / "bettors.parquet", index=False)
    (tmp / "insights.json").write_text(json.dumps(_clean(ins), indent=1, default=str))
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)


# --------------------------------------------------------------------------- background runs + reads
def start(season: int, n: int = 500, seed: int = 7, mix: dict | None = None) -> dict:
    rid = run_id(season, n, seed, mix)
    with _LOCK:
        cur = _RUNS.get(rid)
        if cur and cur["state"] == "running":
            return cur
        if (OUT / rid / "insights.json").exists():
            _RUNS[rid] = dict(run_id=rid, state="done", progress=1.0, week=None, error=None)
            return _RUNS[rid]
        _RUNS[rid] = st = dict(run_id=rid, state="running", progress=0.0, week=None, error=None, started=time.time())

    def go():
        try:
            def prog(p, w):
                st.update(progress=round(p, 3), week=w)
            simulate(season, n, seed, mix, prog)
            st.update(state="done", progress=1.0, finished=time.time())
            try:
                import boo_store
                boo_store.push_dir(OUT / rid, f"myboo/multiverse/{rid}")
            except Exception:
                pass
        except Exception as e:  # surfaced to the UI, never swallowed silently
            st.update(state="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=go, daemon=True, name=f"multiverse-{rid}").start()
    return st


_RID = re.compile(r"mv\d{4}_n\d+_s-?\d+_[0-9a-f]{6}")


def valid(rid: str) -> bool:
    return bool(_RID.fullmatch(rid or ""))


def status(rid: str) -> dict:
    if not valid(rid):
        return dict(run_id=rid, state="missing")
    if rid in _RUNS:
        return _RUNS[rid]
    if (OUT / rid / "insights.json").exists():
        return dict(run_id=rid, state="done", progress=1.0)
    return dict(run_id=rid, state="missing")


def runs() -> list[dict]:
    out = []
    if OUT.exists():
        for d in sorted(OUT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            m = d / "manifest.json"
            if d.is_dir() and m.exists():
                out.append(json.loads(m.read_text()))
    live = [r for r in _RUNS.values() if r["state"] == "running"]
    return live + out


def load_insights(rid: str) -> dict | None:
    if not valid(rid):
        return None
    p = OUT / rid / "insights.json"
    return json.loads(p.read_text()) if p.exists() else None


def bettor(rid: str, bettor_id: int) -> dict | None:
    if not valid(rid):
        return None
    d = OUT / rid
    if not (d / "slips.parquet").exists():
        return None
    b = pd.read_parquet(d / "bettors.parquet")
    row = b[b["bettor_id"] == bettor_id]
    if row.empty:
        return None
    s = pd.read_parquet(d / "slips.parquet")
    s = s[s["bettor_id"] == bettor_id]
    l = pd.read_parquet(d / "legs.parquet")
    l = l[l["bettor_id"] == bettor_id]
    legs_by = defaultdict(list)
    for r in l.to_dict("records"):
        legs_by[r["slip_id"]].append(r)
    slips = [dict(r, legs=legs_by[r["slip_id"]]) for r in s.to_dict("records")]
    return _clean(dict(bettor=row.iloc[0].to_dict(), slips=slips))

"""
BETTER-VERSE engine: N betters x one NFL season, every slip graded against what really happened.

Output (lake/gold/nfl/betterverse/<run_id>/), ready for MY BOO to ingest as-is:
  legs.parquet      boo.bv_leg.v1      one row per leg
  slips.parquet     boo.bv_slip.v1     one row per slip
  bettors.parquet   boo.bv_bettor.v1   one row per better's season (username, tier, ideology, rules, proof metrics)
  insights.json     leaderboard, tier comparison, archetype table, slip-shape table, market edges
  manifest.json     seed, season, counts, schema versions

Same (season, bettors, seed, mix) -> identical files. No network, no model calls: pure numpy/pandas.

Leaderboard: it ranks real winnings. Nothing is filtered or re-weighted, so a rookie who got hot ranks exactly where
the money puts them, and the deep dive shows how they won. A luck-adjusted PROOF score (ROI on a bad-luck replay of a
better's own slips) is available as a second view. Whether a *strategy* really makes money is answered by
betterverse_study.py, which pools many universes and both seasons.
Table limits: each better picks a $5 or $10 base bet; max bet $10 until the bankroll reaches $500, $20 until $1,000,
then bets are free.
Sharps learn only from games played before the week they bet (plus last season), never from the week being graded.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import betterverse_bettors as mb
import betterverse_data as md
import betterverse_rules as rules

OUT = md._GOLD / "betterverse"
START_BANKROLL = 100.0
MIN_N = 30                       # a slip shape needs this many tickets before it gets a verdict
BOOT_REPLAYS = 300               # bad-luck replays per better when scoring proof
BOOT_PERCENTILE = 10
MIN_PROOF_SLIPS = 15             # fewer settled slips than this and a better is ranked "provisional"
LEARN_MIN_N = 300                # graded legs a market/side needs before a sharp trusts its measured edge
LEARN_SHRINK = 400               # pseudo-legs of "no edge" a measured edge is pulled toward
SCHEMAS = {"legs": "boo.bv_leg.v1", "slips": "boo.bv_slip.v1", "bettors": "boo.bv_bettor.v1", "insights": "boo.bv_insights.v1"}
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()


def run_id(season: int, n: int, seed: int, mix: dict | None) -> str:
    h = hashlib.sha1(json.dumps(mix or {}, sort_keys=True).encode()).hexdigest()[:6]
    return f"bv{season}_n{n}_s{seed}_{h}"


# --------------------------------------------------------------------------- what a sharp has learned by week w
def _accumulate(cum: dict, items) -> None:
    for it in items:
        if it["hit"] is None:
            continue
        c = cum[(it["market"], it["side"])]
        c[0] += 1
        c[1] += it["hit"]
        c[2] += 1.0 / it["dec"]


def _edge_tables(season: int, weeks: list[int]) -> dict[int, dict]:
    """{week: {(market, side): shrunk measured edge}} using only results that were public before that week."""
    cum: dict = defaultdict(lambda: [0, 0.0, 0.0])
    if season - 1 in md.SEASONS:
        for w in md.weeks(season - 1):
            _accumulate(cum, md.menu(season - 1, w))
    tables: dict[int, dict] = {}
    for w in weeks:
        tables[w] = {k: (h - imp) / n * n / (n + LEARN_SHRINK) for k, (n, h, imp) in cum.items() if n >= LEARN_MIN_N}
        _accumulate(cum, md.menu(season, w))
    return tables


# --------------------------------------------------------------------------- per-week pools
class _Week:
    def __init__(self, season: int, week: int, edge: dict):
        self.items = list(md.menu(season, week))
        self.market = np.array([i["market"] for i in self.items])
        self.side = np.array([i["side"] for i in self.items])
        self.game = np.array([i["game_id"] for i in self.items])
        self.pop = np.clip(np.array([i["pop"] for i in self.items], dtype=float), 0.05, 1.0)
        self.est = np.array([edge.get((i["market"], i["side"]), np.nan) for i in self.items], dtype=float)
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
    if b.learns:
        w = np.exp(wk.est[idx] * 40)
    else:
        w = wk.pop[idx] ** b.pop_bias
        up = np.isin(wk.side[idx], ["over", "yes", "fav"])
        w = w * np.where(up, b.over_lean, 1 - b.over_lean)
    return w / w.sum()


def _build_slip(wk: _Week, b: mb.Bettor, rng: np.random.Generator) -> list[dict] | None:
    a = mb.ARCHETYPES[b.archetype]
    if b.learns:
        idx = np.flatnonzero(wk.est >= b.edge_min)       # NaN (unmeasured market) never qualifies
    else:
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
def _run(season: int, n: int, seed: int, mix: dict | None, progress=None, keep_legs: bool = True):
    """Play one season for one roster. Returns (run_id, bettors, legs, slips, per-better metrics)."""
    rid = run_id(season, n, seed, mix)
    bettors = mb.roster(n, seed, mix)
    weeks = md.weeks(season)
    tables = _edge_tables(season, weeks)
    wk_cache = {w: _Week(season, w, tables[w]) for w in weeks}
    rngs = [np.random.default_rng(b.seed) for b in bettors]
    bank = np.full(n, START_BANKROLL)
    peak = bank.copy()
    max_dd = np.zeros(n)
    bust_week = np.zeros(n, dtype=int)
    last_net = np.zeros(n)
    bet_weeks = np.zeros(n, dtype=int)
    active_weeks = np.zeros(n, dtype=int)
    leg_rows, slip_rows = [], []
    slip_id = 0

    for wi, w in enumerate(weeks):
        wk = wk_cache[w]
        for b in bettors:
            i = b.bettor_id
            if bust_week[i]:
                continue
            active_weeks[i] += 1
            rng = rngs[i]
            n_slips = int(rng.integers(b.slips_lo, b.slips_hi + 1))
            mult = b.chase if last_net[i] < 0 else 1.0
            week_net, made = 0.0, 0
            for _ in range(n_slips):
                stake = mb.stake_for(b, bank[i], mult)
                if stake < 1.0:
                    break
                legs = _build_slip(wk, b, rng)
                if not legs:
                    continue
                bank_before = bank[i]
                live = [l for l in legs if l["hit"] is not None]
                dec, sgp = rules.price(live) if live else (1.0, False)
                full_dec, full_sgp = rules.price(legs)
                if not live:
                    won, payout = None, stake                    # every leg void: refund
                else:
                    won = all(l["hit"] == 1 for l in live)
                    payout = round(stake * dec, 2) if won else 0.0
                bank[i] = round(bank[i] - stake + payout, 2)
                week_net += payout - stake
                made += 1
                sig = rules.signature(legs, full_sgp)
                slip_rows.append(dict(
                    run_id=rid, season=season, week=w, bettor_id=i, archetype=b.archetype, tier=b.tier, slip_id=slip_id,
                    n_legs=len(legs), n_live=len(live), combo_signature=sig, sgp=full_sgp,
                    decimal_odds=full_dec, settled_odds=dec, implied_prob=round(1 / full_dec, 5),
                    bankroll_before=round(bank_before, 2), stake=stake, stake_pct=round(stake / bank_before, 4), payout=payout, won=won, bankroll_after=bank[i]))
                for li, l in (enumerate(legs) if keep_legs else ()):
                    leg_rows.append(dict(
                        run_id=rid, season=season, week=w, bettor_id=i, archetype=b.archetype, tier=b.tier, slip_id=slip_id,
                        leg_idx=li, market=l["market"], side=l["side"], player_id=l["player_id"], player=l["player"],
                        team=l["team"], game_id=l["game_id"], line=l["line"], price=l["dec"],
                        implied_prob=round(1 / l["dec"], 5), actual=l["actual"],
                        hit=l["hit"], void=l["hit"] is None, same_game=full_sgp, slip_won=won))
                slip_id += 1
            bet_weeks[i] += bool(made)
            last_net[i] = week_net
            peak[i] = max(peak[i], bank[i])
            max_dd[i] = max(max_dd[i], (peak[i] - bank[i]) / peak[i] if peak[i] else 0)
            if bank[i] < 1.0:
                bust_week[i] = w
        if progress:
            progress((wi + 1) / len(weeks), w)

    legs_df = pd.DataFrame(leg_rows)
    slips_df = pd.DataFrame(slip_rows)
    base = pd.DataFrame([dict(
        run_id=rid, season=season, **{k: v for k, v in b.dict().items()}, label=mb.ARCHETYPES[b.archetype]["label"],
        tier_label=mb.TIERS[b.tier]["label"], final_bankroll=bank[b.bettor_id],
        max_drawdown=round(max_dd[b.bettor_id], 4), bust_week=int(bust_week[b.bettor_id]) or None,
        sit_outs=int(active_weeks[b.bettor_id] - bet_weeks[b.bettor_id])) for b in bettors])
    return rid, bettors, legs_df, slips_df, _metrics(slips_df, base)


def simulate(season: int, n: int = 150, seed: int = 7, mix: dict | None = None, progress=None) -> dict:
    t0 = time.time()
    rid, _, legs_df, slips_df, bettors_df = _run(season, n, seed, mix, progress)
    ins = insights(legs_df, slips_df, bettors_df)
    ins.update(run_id=rid, season=season, bettors=n, seed=seed, seconds=round(time.time() - t0, 2))
    _write(rid, legs_df, slips_df, bettors_df, ins, dict(
        run_id=rid, season=season, bettors=n, seed=seed, mix=mix or {}, schemas=SCHEMAS,
        rows={"legs": len(legs_df), "slips": len(slips_df), "bettors": len(bettors_df)},
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), seconds=ins["seconds"],
        start_bankroll=START_BANKROLL, pricing="real 2024-25 closing game odds; props -115; anytime TD prior-rate + margin; SGP haircut"))
    return _clean(ins)


# --------------------------------------------------------------------------- per-better proof metrics
def _metrics(slips: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    """Join each better's identity with the numbers the leaderboard ranks on."""
    b = base.copy()
    g = slips[slips["won"].notna()].copy()
    g["won"] = g["won"].astype(bool)
    wk = g.assign(net=g["payout"] - g["stake"]).groupby(["bettor_id", "week"])["net"].sum()
    prof_weeks = (wk > 0).groupby("bettor_id").mean()
    agg = g.groupby("bettor_id").agg(
        slips=("won", "size"), slips_won=("won", "sum"), staked=("stake", "sum"), returned=("payout", "sum"),
        avg_legs=("n_legs", "mean"), avg_stake_pct=("stake_pct", "mean"))
    b = b.merge(agg, left_on="bettor_id", right_index=True, how="left")
    b["profit_weeks"] = b["bettor_id"].map(prof_weeks)
    for c in ("slips", "slips_won"):
        b[c] = b[c].fillna(0).astype(int)
    for c in ("staked", "returned", "avg_legs", "avg_stake_pct"):
        b[c] = b[c].fillna(0.0)
    b["roi"] = np.where(b["staked"] > 0, (b["returned"] - b["staked"]) / b["staked"].replace(0, np.nan), 0.0)
    b["hit_rate"] = np.where(b["slips"] > 0, b["slips_won"] / b["slips"].replace(0, np.nan), 0.0)
    proof = {}
    for i, d in g.groupby("bettor_id"):
        st, pay = d["stake"].to_numpy(), d["payout"].to_numpy()
        if len(st) < MIN_PROOF_SLIPS:
            continue
        idx = np.random.default_rng(1234 + int(i)).integers(0, len(st), (BOOT_REPLAYS, len(st)))
        proof[i] = float(np.percentile((pay[idx].sum(1) - st[idx].sum(1)) / st[idx].sum(1), BOOT_PERCENTILE))
    b["proof"] = b["bettor_id"].map(proof)
    b["rank_proof"] = b["proof"].rank(ascending=False, method="min")
    b["rank_bankroll"] = b["final_bankroll"].rank(ascending=False, method="min")
    return b.round(4)


def _clean(o):
    """NaN/inf -> None, numpy scalars/arrays -> python, so every file and response is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_clean(v) for v in o.tolist()]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def _f(x) -> float:
    return round(float(x), 4)


def _tier_rows(b: pd.DataFrame, g: pd.DataFrame) -> list[dict]:
    out = []
    for tier, t in b.groupby("tier"):
        s = g[g["tier"] == tier]
        staked = t["staked"].sum()
        out.append(dict(
            tier=tier, label=mb.TIERS[tier]["label"], note=mb.TIERS[tier]["note"], order=mb.TIERS[tier]["order"],
            bettors=len(t), roi=_f((t["returned"].sum() - staked) / staked) if staked else 0.0,
            median_final=_f(t["final_bankroll"].median()), profitable_share=_f((t["final_bankroll"] > START_BANKROLL).mean()),
            bust_rate=_f(t["bust_week"].notna().mean()), avg_proof=_f(t["proof"].mean()) if t["proof"].notna().any() else None,
            slip_hit_rate=_f(s["won"].mean()) if len(s) else 0.0, avg_legs=_f(t["avg_legs"].mean()),
            avg_stake_pct=_f(t["avg_stake_pct"].mean()), sit_outs=_f(t["sit_outs"].mean()),
            top_username=str(t.loc[t["final_bankroll"].idxmax(), "username"]), top_final=_f(t["final_bankroll"].max())))
    return sorted(out, key=lambda r: r["order"])


LEADER_COLS = ["bettor_id", "username", "tier", "tier_label", "archetype", "label", "bio", "rules", "unit", "final_bankroll", "roi",
               "proof", "rank_proof", "rank_bankroll", "slips", "slips_won", "hit_rate", "avg_legs", "avg_stake_pct",
               "max_drawdown", "profit_weeks", "sit_outs", "bust_week"]


def insights(legs: pd.DataFrame, slips: pd.DataFrame, bettors: pd.DataFrame) -> dict:
    graded = slips[slips["won"].notna()].copy()
    graded["won"] = graded["won"].astype(bool)

    tiers = _tier_rows(bettors, graded)
    leaderboard = bettors.sort_values(["rank_bankroll", "rank_proof"], na_position="last")[LEADER_COLS].to_dict("records")

    arch = []
    for name, g in bettors.groupby("archetype"):
        s = graded[graded["archetype"] == name]
        a = mb.ARCHETYPES[name]
        staked = g["staked"].sum()
        arch.append(dict(
            archetype=name, label=a["label"], desc=a["desc"], bettors=len(g),
            roi=_f((g["returned"].sum() - staked) / staked) if staked else 0.0,
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

    sharp_legs = live[live["tier"] == "sharp"]
    sharp_playbook = [dict(market=mk, side=side, n=len(g), hit_rate=_f(g["hit"].mean()), edge=_f(g["hit"].mean() - g["implied_prob"].mean()))
                      for (mk, side), g in sharp_legs.groupby(["market", "side"]) if len(g) >= 10]
    sharp_playbook.sort(key=lambda r: -r["n"])

    by_legs = [dict(n_legs=int(k), n=len(g), hit_rate=_f(g["won"].mean()), implied=_f(g["implied_prob"].mean()),
                    roi=_f((g["payout"].sum() - g["stake"].sum()) / g["stake"].sum()))
               for k, g in graded.groupby("n_legs")]
    sgp = [dict(sgp=bool(k), n=len(g), hit_rate=_f(g["won"].mean()),
                roi=_f((g["payout"].sum() - g["stake"].sum()) / g["stake"].sum())) for k, g in graded.groupby("sgp")]
    weekly = [dict(week=int(k), slips=len(g), hit_rate=_f(g["won"].mean()), staked=_f(g["stake"].sum()),
                   paid=_f(g["payout"].sum())) for k, g in graded.groupby("week")]

    pl = live[live["player_id"] != ""].groupby(["player", "market", "side"]).agg(n=("hit", "size"), hit_rate=("hit", "mean"),
                                                                                implied=("implied_prob", "mean")).reset_index()
    pl = pl[pl["n"] >= 20]
    pl["edge"] = pl["hit_rate"] - pl["implied"]
    hot = pl.sort_values("edge", ascending=False).head(15).round(4).to_dict("records")
    cold = pl.sort_values("edge").head(15).round(4).to_dict("records")

    never = [c for c in combos if c["never_won"]]
    steady = sorted([c for c in combos if c["consistent"]], key=lambda c: -c["edge"])
    total_stake = graded["stake"].sum()
    headlines = []
    by_tier = {t["tier"]: t for t in tiers}
    if "sharp" in by_tier and "degen" in by_tier:
        s, d = by_tier["sharp"], by_tier["degen"]
        verdict = "Discipline paid" if s["roi"] > d["roi"] else "Discipline did NOT beat the knee-jerk bettors this season"
        headlines.append(f"{verdict}: Sharps {s['roi']:+.1%} ROI vs Degens {d['roi']:+.1%}; "
                         f"{s['profitable_share']:.0%} of Sharps finished up vs {d['profitable_share']:.0%} of Degens.")
    winners = bettors.sort_values("final_bankroll", ascending=False)
    if len(winners):
        top = winners.iloc[0]
        headlines.append(f"#1 on the winnings board: {top['username']} ({top['tier_label']}, {top['label']}) turned $100 into "
                         f"${top['final_bankroll']:,.2f} ({top['roi']:+.1%} ROI over {int(top['slips'])} slips).")
        per_tier = [f"{t['label']} {t['top_username']} ${t['top_final']:,.0f}" for t in tiers]
        headlines.append("Top winner in each tier: " + " · ".join(per_tier) + ".")
    headlines.append(f"{(bettors['final_bankroll'] > START_BANKROLL).mean():.0%} of betters finished up; "
                     f"{bettors['bust_week'].notna().mean():.0%} went broke.")
    if never:
        headlines.append(f"{len(never)} slip shapes were played {MIN_N}+ times and never cashed once.")
    if steady:
        headlines.append(f"{len(steady)} slip shapes beat their implied odds by 5+ pts across 8+ weeks — led by '{steady[0]['signature']}'.")

    return dict(
        schema=SCHEMAS["insights"], headlines=headlines,
        totals=dict(slips=len(slips), graded=len(graded), legs=len(legs), staked=_f(total_stake),
                    paid=_f(graded["payout"].sum()),
                    house_hold=_f(1 - graded["payout"].sum() / total_stake) if total_stake else 0,
                    slip_hit_rate=_f(graded["won"].mean() if len(graded) else 0)),
        tiers=tiers, leaderboard=leaderboard, archetypes=arch, combos=combos[:200], never_won=never, consistent=steady,
        markets=markets, sharp_playbook=sharp_playbook, by_legs=by_legs, sgp=sgp, weekly=weekly, hot_legs=hot, cold_legs=cold)


def _write(rid: str, legs, slips, bettors, ins: dict, manifest: dict) -> None:
    d = OUT / rid
    tmp = OUT / f".{rid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    legs.to_parquet(tmp / "legs.parquet", index=False)
    slips.to_parquet(tmp / "slips.parquet", index=False)
    bettors.to_parquet(tmp / "bettors.parquet", index=False)
    (tmp / "insights.json").write_text(json.dumps(_clean(ins), indent=1, default=str))
    (tmp / "manifest.json").write_text(json.dumps(_clean(manifest), indent=1, default=str))
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)
    try:                                                    # MY BOO collects every run automatically
        import boo_harvest
        boo_harvest.on_run(rid)
    except Exception:
        pass


# --------------------------------------------------------------------------- background runs + reads
_RID = re.compile(r"bv\d{4}_n\d+_s-?\d+_[0-9a-f]{6}")


def valid(rid: str) -> bool:
    return bool(_RID.fullmatch(rid or ""))


def start(season: int, n: int = 150, seed: int = 7, mix: dict | None = None) -> dict:
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
        except Exception as e:  # surfaced to the UI, never swallowed silently
            st.update(state="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=go, daemon=True, name=f"betterverse-{rid}").start()
    return st


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


def career(rids: list[str]) -> dict | None:
    """The same betters across several seasons: pooled slips, pooled proof score, one board."""
    if not rids or not all(valid(r) and (OUT / r / "slips.parquet").exists() for r in rids):
        return None
    base = pd.read_parquet(OUT / rids[0] / "bettors.parquet")[
        ["bettor_id", "username", "tier", "tier_label", "archetype", "label", "bio", "rules", "unit"]]
    finals = {r: pd.read_parquet(OUT / r / "bettors.parquet").set_index("bettor_id") for r in rids}
    slips = pd.concat([pd.read_parquet(OUT / r / "slips.parquet") for r in rids], ignore_index=True)
    # compare identities across seasons: a different roster (seed/n/mix) would not be the same people
    for r in rids[1:]:
        if not (finals[r]["username"].reindex(base["bettor_id"]).values == base["username"].values).all():
            return None
    b = base.copy()
    b["season"] = 0
    b["final_bankroll"] = b["bettor_id"].map(lambda i: float(np.mean([finals[r].loc[i, "final_bankroll"] for r in rids])))
    b["max_drawdown"] = b["bettor_id"].map(lambda i: float(max(finals[r].loc[i, "max_drawdown"] for r in rids)))
    b["bust_week"] = b["bettor_id"].map(lambda i: next((finals[r].loc[i, "bust_week"] for r in rids if pd.notna(finals[r].loc[i, "bust_week"])), None))
    b["sit_outs"] = b["bettor_id"].map(lambda i: int(sum(finals[r].loc[i, "sit_outs"] for r in rids)))
    b["tier"] = b["tier"].astype(str)
    m = _metrics(slips, b)
    graded = slips[slips["won"].notna()].copy()
    graded["won"] = graded["won"].astype(bool)
    seasons = sorted(int(finals[r].iloc[0]["season"]) for r in rids)
    per = {r: finals[r] for r in rids}
    lb = m.sort_values(["rank_bankroll", "rank_proof"], na_position="last")[LEADER_COLS].to_dict("records")
    for row in lb:
        row["by_season"] = [dict(season=int(per[r].iloc[0]["season"]), roi=float(per[r].loc[row["bettor_id"], "roi"]),
                                 final_bankroll=float(per[r].loc[row["bettor_id"], "final_bankroll"])) for r in rids]
    return _clean(dict(runs=rids, seasons=seasons, tiers=_tier_rows(m, graded), leaderboard=lb))


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

    weeks = sorted(set(pd.read_parquet(d / "slips.parquet", columns=["week"])["week"]))
    last = s.groupby("week")["bankroll_after"].last()
    curve, cur = [], START_BANKROLL
    for w in weeks:
        cur = float(last[w]) if w in last.index else cur
        curve.append(dict(week=int(w), bankroll=cur, bet=bool(w in last.index)))
    lv = l[~l["void"]]
    mix = [dict(market=mk, side=sd, n=len(g), hit_rate=float(g["hit"].astype(float).mean()),
                edge=float(g["hit"].astype(float).mean() - g["implied_prob"].mean()))
           for (mk, sd), g in lv.groupby(["market", "side"])]
    mix.sort(key=lambda r: -r["n"])
    return _clean(dict(bettor=row.iloc[0].to_dict(), slips=slips, curve=curve, market_mix=mix))

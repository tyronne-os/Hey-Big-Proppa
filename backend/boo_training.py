"""
MY BOO trains Jimmy.

Every graded slip becomes training data. Every Tuesday at 6 AM Central (New Orleans), after the week's last
game, MY BOO runs one batch over everything she has recorded and hands Jimmy his lessons:

  1. TRAINING PACKAGE   one JSON line per graded leg (boo.leg.v1) and per slip (boo.slip.v1), the full report text
                        included, written to lake/gold/nfl/boo_training/week_NN_*.jsonl for Jimmy / Big Proppa to ingest.
  2. CALIBRATION        was a 65% leg really 65%? Hit rate against Jimmy's own score, by market and by bucket.
  3. SIGNAL WEIGHTS     which of Jimmy's signals (hit rate, usage, matchup, defense, fantasy ...) actually predicted
                        the hit. The weights that earn it go up, the ones that do not go down (bounded, shrunk).
  4. DEFENSE CORRECTIONS how far each defense's real output was from the rank the model gave it.
  5. MISS TAXONOMY      why legs missed: coach's call, volume collapse, defense overperformed, efficiency, near miss.
  6. USAGE DRIFT        how each player's real workload compared with the baseline Jimmy used.
  7. RETIRED MARKETS    what the evidence says to stop betting (touchdown-scorer legs from week 4).

The result is lake/gold/nfl/jimmy_lessons.json, which jimmy.jimmy_score() reads on every call. Nothing here
guesses: with too few legs a lesson stays neutral, and every adjustment is shrunk toward neutral and capped,
so one bad night cannot wreck the model. The previous lessons are kept (jimmy_lessons.vN.json) so any batch can
be rolled back by deleting the newest.
"""
from __future__ import annotations

import csv
import json
import math
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import myboo
import slip_recap

CT = ZoneInfo("America/Chicago")
_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
TRAIN_DIR = _GOLD / "boo_training"
LESSONS = _GOLD / "jimmy_lessons.json"
BATCHES = TRAIN_DIR / "batches.json"
_LOCK = threading.RLock()

# how much evidence a lesson needs before it is allowed to move anything
MIN_WEIGHT_N, MIN_BIAS_N = 30, 25
WEIGHT_RANGE, BIAS_CAP = (0.7, 1.3), 0.05
TD_MARKETS = slip_recap.TD_MARKETS


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _now() -> datetime:
    return datetime.now(CT)


# ---------------------------------------------------------------------------
# 1. the training package
# ---------------------------------------------------------------------------

def examples() -> tuple[list[dict], list[dict]]:
    """(legs, slips): every graded leg and every recorded slip, in the boo.leg.v1 / boo.slip.v1 shapes."""
    recaps = slip_recap._load_json(slip_recap._RECAPS_FILE)
    tickets = {t["ticket_id"]: t for t in myboo.load_tickets_raw()}
    legs_out, slips_out = [], []
    for tid, rc in recaps.items():
        t = tickets.get(tid)
        if not t or rc.get("stage") != "FINAL" or not rc.get("hindsight"):
            continue
        feats = rc.get("features") or {}
        ths, facts = feats.get("legs") or [], feats.get("facts") or []
        game, wi = feats.get("game"), feats.get("whatif")
        dfn = {(d["defense"], d["cat"]): d for d in feats.get("defense_audit") or []}
        h = rc["hindsight"]
        for th, f in zip(ths, facts):
            if f.get("status") not in ("HIT", "MISS"):
                continue
            actual, line = _f(f.get("actual")), _f(th.get("line"))
            used, avg = _f(f.get("used")), _f(f.get("usage_avg"))
            cat = "pass" if th.get("attack_cat") == "pass_yds" else "rush" if th.get("attack_cat") == "rush_yds" else None
            d = dfn.get((th.get("opp"), cat)) if cat else None
            legs_out.append({
                "schema": "boo.leg.v1", "ticket_id": tid, "order_type": t.get("order_type"), "season": rc.get("season"),
                "week": rc.get("week"), "game_id": th.get("game_id"), "player": th["player"], "player_id": th.get("player_id"),
                "team": th["team"], "opp": th.get("opp"), "market": th["market"], "direction": th.get("direction"),
                "line": line, "odds": th.get("odds"), "model_prob": th.get("prob"), "implied": th.get("implied"),
                "edge": th.get("edge"), "jimmy_score": th.get("jimmy_score"), "components": th.get("components"),
                "hit": 1 if f["status"] == "HIT" else 0, "actual": actual,
                "margin": round(actual - line, 2) if actual is not None and line is not None else None,
                "margin_pct": round((actual - line) / line, 3) if actual is not None and line else None,
                "usage": {"key": th.get("usage_key"), "avg": avg, "used": used,
                          "ratio": round(used / avg, 3) if used is not None and avg else None},
                "volume_held": f.get("volume_held"), "env_held": f.get("env_held"), "thesis_held": f.get("thesis_held"),
                "miss_type": f.get("miss_type"), "coach_call": th["market"] in TD_MARKETS,
                "attack": {"cat": cat, "rank": th.get("attack_rank"), "expected": th.get("attack_allowed"),
                           "actual": d["actual"] if d else None, "ratio": d["ratio"] if d else None},
                "game": game, "slip_verdict": h.get("label"),
            })
        slips_out.append({
            "schema": "boo.slip.v1", "ticket_id": tid, "order_type": t.get("order_type"), "season": rc.get("season"),
            "week": rc.get("week"), "name": rc.get("name"), "status": t["status"], "stake": _f(t.get("stake_units")),
            "payout_odds": _f(t.get("payout_odds")), "result_units": _f(t.get("result_units"), 0.0),
            "verdict": h.get("label"), "process_score": h.get("process_score"), "tags": h.get("tags"),
            "words": rc.get("word_count"), "whatif": wi, "game": game,
            "report": {"setup": rc.get("setup"), "facts": rc.get("facts"), "hindsight": h.get("line")},
        })
    return legs_out, slips_out


# ---------------------------------------------------------------------------
# 2-6. the analyses
# ---------------------------------------------------------------------------

def calibration(legs: list[dict]) -> dict:
    """Hit rate against Jimmy's own number, by market and by confidence bucket (Brier score = lower is better)."""
    by_m: dict[str, list[tuple[float, int]]] = defaultdict(list)
    buckets: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for l in legs:
        if l["coach_call"]:
            continue
        p = l["jimmy_score"] if l.get("jimmy_score") is not None else l.get("model_prob")
        if p is None:
            continue
        by_m[l["market"] + " " + (l["direction"] or "")].append((p, l["hit"]))
        buckets[f"{int(p * 10) * 10}-{int(p * 10) * 10 + 10}%"].append((p, l["hit"]))
    def row(xs):
        n = len(xs)
        return {"n": n, "predicted": round(sum(p for p, _ in xs) / n, 3), "observed": round(sum(h for _, h in xs) / n, 3),
                "brier": round(sum((p - h) ** 2 for p, h in xs) / n, 3)}
    return {"markets": {k: row(v) for k, v in sorted(by_m.items())}, "buckets": {k: row(v) for k, v in sorted(buckets.items())}}


def signal_weights(legs: list[dict]) -> tuple[dict, dict]:
    """Point-biserial correlation of each signal with the hit, shrunk by sample size, turned into a bounded weight."""
    series: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for l in legs:
        if l["coach_call"] or not l.get("components"):
            continue
        for k, v in l["components"].items():
            if v is not None:
                series[k].append((v, l["hit"]))
    weights, detail = {}, {}
    for k, xs in series.items():
        n = len(xs)
        vals, hits = [v for v, _ in xs], [h for _, h in xs]
        mv, mh = sum(vals) / n, sum(hits) / n
        sv = math.sqrt(sum((v - mv) ** 2 for v in vals) / n)
        sh = math.sqrt(sum((h - mh) ** 2 for h in hits) / n)
        r = (sum((v - mv) * (h - mh) for v, h in xs) / n / (sv * sh)) if sv > 0 and sh > 0 else 0.0
        shrunk = r * n / (n + 30)
        detail[k] = {"n": n, "corr": round(r, 3), "shrunk": round(shrunk, 3)}
        if n >= MIN_WEIGHT_N:
            weights[k] = round(max(WEIGHT_RANGE[0], min(WEIGHT_RANGE[1], 1 + 1.5 * shrunk)), 3)
    return weights, detail


def market_bias(cal: dict) -> dict:
    """Nudge a market's score by how far reality sat from Jimmy's number there, shrunk and capped."""
    out = {}
    for key, c in cal["markets"].items():
        if c["n"] < MIN_BIAS_N:
            continue
        market = key.split()[0]
        shifted = (c["observed"] - c["predicted"]) * c["n"] / (c["n"] + 40) * 0.5
        out[market] = round(max(-BIAS_CAP, min(BIAS_CAP, shifted)), 4)
    return out


def defense_residuals(legs: list[dict]) -> dict:
    """team -> {pass|rush: actual / expected}, averaged over games and shrunk toward 1.0."""
    seen: dict[tuple, float] = {}
    for l in legs:
        a = l["attack"]
        if l["opp"] and a["cat"] and a.get("ratio"):
            seen[(l["game_id"], l["opp"], a["cat"])] = a["ratio"]
    agg: dict[tuple, list[float]] = defaultdict(list)
    for (_, team, cat), r in seen.items():
        agg[(team, cat)].append(r)
    out: dict[str, dict] = defaultdict(dict)
    for (team, cat), rs in agg.items():
        n = len(rs)
        mean = sum(rs) / n
        out[team][cat] = round(max(0.7, min(1.3, 1 + (mean - 1) * n / (n + 3))), 3)
    return dict(out)


def usage_drift(legs: list[dict]) -> dict:
    by: dict[str, list[float]] = defaultdict(list)
    for l in legs:
        r = l["usage"]["ratio"]
        if r is not None and l["player_id"]:
            by[f"{l['player_id']}|{l['usage']['key']}"].append(r)
    return {k: {"ratio": round(sum(v) / len(v), 3), "games": len(v)} for k, v in by.items()}


def miss_taxonomy(legs: list[dict]) -> dict:
    out: dict[str, Counter] = defaultdict(Counter)
    for l in legs:
        if l["miss_type"]:
            out[l["market"]][l["miss_type"]] += 1
    return {m: dict(c) for m, c in out.items()}


def retired(legs: list[dict]) -> dict:
    td = [l for l in legs if l["coach_call"]]
    if not td:
        return {}
    by_kind = {"real": [l for l in td if l["order_type"] == "POW"], "board": [l for l in td if l["order_type"] != "POW"]}
    return {"touchdown_scorer": {
        "markets": sorted(TD_MARKETS), "legs": len(td), "hits": sum(l["hit"] for l in td),
        "real_money": f"{sum(l['hit'] for l in by_kind['real'])}/{len(by_kind['real'])}",
        "board": f"{sum(l['hit'] for l in by_kind['board'])}/{len(by_kind['board'])}",
        "rule": "Not offered from NFL week 4. Replaced by the RED ZONE EFFORT leg (red_zone.py).",
        "why": "Who scores is the offensive coordinator's call at the goal line, not something the stats can see."}}


def whatif_totals(slips: list[dict]) -> dict:
    """The touchdown tax, kept apart for real money and for the board's paper slips (the board's stakes are not real)."""
    def tally(group: list[dict]) -> dict:
        w = [s for s in group if s.get("whatif")]
        won = [s for s in w if s["whatif"]["would_have_cashed"]]
        return {"slips_with_a_td_leg": len(w), "would_have_cashed_without_it": len(won),
                "staked_on_those": round(sum(s["whatif"]["stake"] for s in won), 2),
                "profit_if_stripped": round(sum(s["whatif"]["stripped_profit"] for s in won), 2),
                "profit_if_the_td_had_hit": round(sum(s["whatif"]["full_profit_if_td_hit"] for s in won), 2)}
    return {"real": tally([s for s in slips if s["order_type"] == "POW"]),
            "board": tally([s for s in slips if s["order_type"] != "POW"]),
            "price_note": "stripped-leg prices are estimates from FanDuel's board"}


# ---------------------------------------------------------------------------
# the batch
# ---------------------------------------------------------------------------

def _complete_weeks() -> set[int]:
    """Weeks whose every regular-season game is before today (Central)."""
    today = _now().date().isoformat()
    last: dict[int, str] = {}
    for g in slip_recap._rows("schedule"):
        if g.get("game_type") == "REG" and g.get("week"):
            last[int(g["week"])] = max(last.get(int(g["week"]), ""), g.get("game_date", ""))
    return {w for w, d in last.items() if d and d < today}


def _load_batches() -> list[dict]:
    try:
        return json.loads(BATCHES.read_text())
    except (OSError, ValueError):
        return []


def run_batch(preview: bool = False, trigger: str = "manual") -> dict:
    """
    Build the training package and Jimmy's lessons from everything recorded.
    preview=True also uses weeks that are still in progress (marked partial); the Tuesday run uses complete weeks only.
    """
    with _LOCK:
        TRAIN_DIR.mkdir(parents=True, exist_ok=True)
        legs, slips = examples()
        complete = _complete_weeks()
        partial = sorted({l["week"] for l in legs if l["week"] not in complete})
        if not preview:
            legs = [l for l in legs if l["week"] in complete]
            slips = [s for s in slips if s["week"] in complete]
        weeks = sorted({l["week"] for l in legs})
        for w in weeks:                                           # 1. the package, one pair of files per week
            wl, ws = [l for l in legs if l["week"] == w], [s for s in slips if s["week"] == w]
            (TRAIN_DIR / f"week_{int(w):02d}_legs.jsonl").write_text("\n".join(json.dumps(x) for x in wl) + "\n")
            (TRAIN_DIR / f"week_{int(w):02d}_slips.jsonl").write_text("\n".join(json.dumps(x) for x in ws) + "\n")

        cal = calibration(legs)                                    # 2-7. the analyses
        weights, sig_detail = signal_weights(legs)
        prev = {}
        try:
            prev = json.loads(LESSONS.read_text())
        except (OSError, ValueError):
            pass
        version = int(prev.get("version", 0)) + 1
        if prev:
            (_GOLD / f"jimmy_lessons.v{prev['version']}.json").write_text(json.dumps(prev, indent=1))
        lessons = {
            "version": version, "built_at": _now().isoformat(), "trigger": trigger, "preview": preview,
            "through_week": max(weeks) if weeks else None, "partial_weeks": partial if preview else [],
            "legs": len(legs), "slips": len(slips),
            "weights": weights, "signal_detail": sig_detail, "market_bias": market_bias(cal),
            "defense_residual": defense_residuals(legs), "usage_drift": usage_drift(legs),
            "retired_markets": retired(legs), "miss_taxonomy": miss_taxonomy(legs), "calibration": cal,
            "whatif": whatif_totals(slips),
        }
        lessons["notes"] = _notes(lessons, prev)
        LESSONS.write_text(json.dumps(lessons, indent=1))
        report = _report(lessons, prev)
        (TRAIN_DIR / "latest_report.md").write_text(report)
        batches = _load_batches()
        batches.append({"version": version, "at": lessons["built_at"], "trigger": trigger, "preview": preview,
                        "weeks": weeks, "legs": len(legs), "slips": len(slips), "weights_moved": len(weights),
                        "biases_moved": len(lessons["market_bias"])})
        BATCHES.write_text(json.dumps(batches, indent=1))
    try:
        import boo_store
        threading.Thread(target=boo_store.push, kwargs={"force": True}, daemon=True).start()
    except Exception:
        pass
    return {"version": version, "legs": len(legs), "slips": len(slips), "weeks": weeks, "preview": preview, "report": report}


def _notes(L: dict, prev: dict) -> list[str]:
    n = []
    rt = L["retired_markets"].get("touchdown_scorer")
    if rt:
        n.append(f"Touchdown-scorer legs are {rt['hits']}/{rt['legs']} (real money {rt['real_money']}, board {rt['board']}). Retired from week 4; effort legs replace them.")
    c = L["calibration"]["markets"]
    for k, v in c.items():
        if v["n"] >= MIN_BIAS_N and abs(v["observed"] - v["predicted"]) >= 0.10:
            n.append(f"{k}: Jimmy said {round(v['predicted'] * 100)}%, reality was {round(v['observed'] * 100)}% over {v['n']} legs.")
    for k, w in sorted(L["weights"].items(), key=lambda kv: -abs(kv[1] - 1))[:3]:
        if abs(w - 1) >= 0.03:
            n.append(f"Signal '{k}' {'earned more' if w > 1 else 'lost'} weight ({w}x) on {L['signal_detail'][k]['n']} legs.")
    for team, d in L["defense_residual"].items():
        for cat, r in d.items():
            if abs(r - 1) >= 0.10:
                n.append(f"{team}'s {cat} defense runs {round(abs(r - 1) * 100)}% {'softer' if r > 1 else 'tougher'} than its rank.")
    if not n:
        n.append("Not enough graded legs yet to move any signal; every lesson stays neutral until the sample grows.")
    return n


def _report(L: dict, prev: dict) -> str:
    when = datetime.fromisoformat(L["built_at"]).strftime("%a %b %-d, %-I:%M %p CT")
    lines = [f"# WHAT JIMMY LEARNED: batch v{L['version']}", "",
             f"Built {when} by MY BOO" + (" (PREVIEW: includes weeks still in progress)" if L["preview"] else " (Tuesday batch, complete weeks only)") + ".",
             f"Training package: {L['legs']} graded legs from {L['slips']} slips through week {L['through_week']}.", "", "## Lessons"]
    lines += [f"- {x}" for x in L["notes"]]
    for label, key in (("Real money", "real"), ("The board (paper)", "board")):
        w = L["whatif"][key]
        if w["slips_with_a_td_leg"]:
            lines += ["", f"## The touchdown tax: {label}",
                      f"{w['slips_with_a_td_leg']} slips carried a touchdown leg; {w['would_have_cashed_without_it']} would have cashed without it, "
                      f"paying about ${w['profit_if_stripped']:g} profit on ${w['staked_on_those']:g} staked "
                      f"(${w['profit_if_the_td_had_hit']:g} had the touchdown also landed). {L['whatif']['price_note'][0].upper() + L['whatif']['price_note'][1:]}."]
    lines += ["", "## Miss taxonomy"]
    for m, c in L["miss_taxonomy"].items():
        lines.append(f"- {m}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1])))
    lines += ["", "## Calibration (Jimmy's number vs reality)"]
    for k, v in L["calibration"]["markets"].items():
        lines.append(f"- {k}: predicted {round(v['predicted'] * 100)}%, observed {round(v['observed'] * 100)}%, n={v['n']}, Brier {v['brier']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# the Tuesday schedule
# ---------------------------------------------------------------------------

def last_tuesday_6am(now: datetime | None = None) -> datetime:
    now = now or _now()
    d = now.replace(hour=6, minute=0, second=0, microsecond=0)
    d -= timedelta(days=(d.weekday() - 1) % 7)
    return d - timedelta(days=7) if d > now else d


def next_run(now: datetime | None = None) -> datetime:
    return last_tuesday_6am(now) + timedelta(days=7)


def maybe_run_tuesday() -> dict | None:
    """Called by the worker every minute. Runs the batch once after each Tuesday 6 AM CT, even if the worker was down at 6."""
    with _LOCK:
        due = last_tuesday_6am()
        done = [datetime.fromisoformat(b["at"]) for b in _load_batches() if not b["preview"] and b["trigger"] == "tuesday"]
        if done and max(done) >= due:
            return None
        if not (slip_recap._load_json(slip_recap._RECAPS_FILE)):
            return None
        return run_batch(preview=False, trigger="tuesday")


def status() -> dict:
    batches = _load_batches()
    try:
        L = json.loads(LESSONS.read_text())
    except (OSError, ValueError):
        L = None
    return {"nextTuesdayBatch": next_run().isoformat(), "nextTuesdayBatchCT": next_run().strftime("%a %b %-d, %-I:%M %p CT"),
            "batches": batches[-8:], "lessons": L,
            "report": (TRAIN_DIR / "latest_report.md").read_text() if (TRAIN_DIR / "latest_report.md").exists() else "",
            "package": sorted(p.name for p in TRAIN_DIR.glob("week_*.jsonl")) if TRAIN_DIR.exists() else []}

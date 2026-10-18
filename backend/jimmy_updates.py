"""
JIMMY training updates: one button sends MY BOO's pre-packaged training data to JIMMY as a numbered update.

JIMMY plays with a POLICY (how many legs, over or under for each prop type, how legs are ranked). An update is a numbered package
(JU-0001, JU-0002, ...) of numbered ITEMS (JU-0001.01, ...). Each item is one proposed change to that policy, with where it came from
(JIMMY's own graded boards across 2023-25 and the latest BETTER-VERSE curriculum release) and its measured impact on JIMMY's win
percentage, ROI and leg hit rate.

Items must earn their place. Every item is tested out of sample: for each real season, the item is re-derived from the OTHER two seasons
and scored on the one it never saw. Only items that do not make JIMMY worse out of sample are APPLIED; the rest are HELD BACK and
recorded as such. JIMMY then plays with the new policy (auto-play and /api/jimmy/recommend), each season he plays is stamped with
the update number that was live, and live results are tracked per update next to the backtest.

Win percentage here is the SLIP win rate (every live leg hit). Because a slip with fewer legs wins more often by arithmetic alone, the
report always shows ROI and the leg hit rate beside it, and items are accepted on those, not on the slip win rate.

Files (lake/gold/nfl/boo_jimmy/, mirrored to the private HF dataset): policy.json · timeline.json · live.jsonl · updates/JU-0001.{json,md,jsonl}
"""
from __future__ import annotations

import json
import math
import threading
import time
from functools import lru_cache
from pathlib import Path

import jimmy_history as jh

DIR = Path(__file__).parent.parent / "lake/gold/nfl/boo_jimmy"
YEARS = (2023, 2024, 2025)
PROPS = tuple(jh.PROPS)
WEEKS = range(1, 19)
BASE_POLICY = {"legs": 3, "direction": {p: "over" for p in PROPS}, "rank": "confidence"}      # what JIMMY's auto-play did before any update
WAGER = 5.0
SLIPS_PER_WEEK = 5                    # the most the game allows; five non-overlapping slips a week gives ~5x the sample of one
POOL_SIZE = 600                       # "every eligible prop": the pool the direction evidence is learned from
_LOCK = threading.RLock()


# --------------------------------------------------------------------------- policy
def _read(name: str, default):
    try:
        return json.loads((DIR / name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = DIR / (name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(DIR / name)


def current() -> dict:
    """The policy JIMMY plays with right now: {"version": "JU-0003" | "JU-0000", "policy": {...}}"""
    cur = _read("policy.json", None)
    return cur or {"version": "JU-0000", "policy": BASE_POLICY, "updated": None}


def version() -> str:
    return current()["version"]


@lru_cache(maxsize=1024)
def _board(year: int, week: int, size: int) -> tuple:
    return tuple(jh.board(year, week, size))


def pick(props: list[dict], policy: dict, exclude: set[str] | None = None) -> list[dict]:
    """JIMMY's slip from a board under a policy: best `legs` props by the confidence in the side he is betting."""
    cands = []
    for p in props:
        if exclude and p["player_id"] in exclude:
            continue
        over = policy["direction"].get(p["prop_type"], "over") == "over"
        cands.append((p["confidence"] if over else 100 - p["confidence"], over, p))
    cands.sort(key=lambda c: -c[0])
    return [{"player_id": p["player_id"], "team": p["team"], "prop_type": p["prop_type"], "line": p["line"], "is_over": over,
             "confidence": round(conf, 1)} for conf, over, p in cands[: int(policy["legs"])]]


# --------------------------------------------------------------------------- scoring a policy on real seasons
def evaluate(policy: dict, years=YEARS) -> dict:
    """Play the policy through whole real seasons: up to 5 non-overlapping slips a week from JIMMY's actual 16-prop board, $5 each, payout 2^legs."""
    tot = dict(slips=0, wins=0, legs=0, leg_hits=0, staked=0.0, returned=0.0)
    by: dict[str, dict] = {}
    for y in years:
        s = dict(slips=0, wins=0, legs=0, leg_hits=0, staked=0.0, returned=0.0)
        for w in WEEKS:
            board = list(_board(y, w, 16))
            used: set[str] = set()
            for _ in range(SLIPS_PER_WEEK):
                legs = pick(board, policy, used)
                if len(legs) < int(policy["legs"]):
                    break
                used |= {l["player_id"] for l in legs}
                res = []
                for l in legs:
                    a = jh.actual(y, l["player_id"], w, l["prop_type"])
                    if a is not None:
                        res.append((a > l["line"]) if l["is_over"] else (a < l["line"]))
                if not res:
                    continue
                won = all(res)
                s["slips"] += 1
                s["staked"] += WAGER
                s["legs"] += len(res)
                s["leg_hits"] += sum(res)
                if won:
                    s["wins"] += 1
                    s["returned"] += WAGER * 2 ** len(res)
        by[str(y)] = _fin(s)
        for k in tot:
            tot[k] += s[k]
    out = _fin(tot)
    out["by_season"] = by
    return out


def _fin(s: dict) -> dict:
    return {**{k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()},
            "win_pct": round(s["wins"] / s["slips"], 4) if s["slips"] else 0.0,
            "leg_hit_pct": round(s["leg_hits"] / s["legs"], 4) if s["legs"] else 0.0,
            "roi": round((s["returned"] - s["staked"]) / s["staked"], 4) if s["staked"] else 0.0}


# --------------------------------------------------------------------------- items derived from the data
def _wilson_lo(k: int, n: int, z: float = 1.96) -> float:
    if not n:
        return 0.0
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def _pool(years) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {p: [] for p in PROPS}
    for y in years:
        for w in WEEKS:
            for p in _board(y, w, POOL_SIZE):
                a = jh.actual(y, p["player_id"], w, p["prop_type"])
                if a is not None:
                    out[p["prop_type"]].append(int(a > p["line"]))
    return out


def _curriculum_directions() -> dict[str, dict]:
    """Single-market, single-side shapes the latest curriculum release teaches or watches that JIMMY can act on: {market: {side, lesson, verdict, release}}"""
    out: dict[str, dict] = {}
    try:
        import boo_curriculum
        rel = boo_curriculum.latest()
    except Exception:
        return out
    for u in (rel or {}).get("units", []):
        for l in u["lessons"]:
            if l["kind"] != "shape" or l["verdict"] not in ("teach", "watch") or "|" in l["key"]:
                continue
            m = l["key"].split(" ")[0]
            if ":" in m and m.split(":")[0] in PROPS and m.split(":")[1] in ("over", "under"):
                mk, side = m.split(":")
                if mk not in out or l["verdict"] == "teach":
                    out[mk] = {"side": side, "lesson": l["id"], "verdict": l["verdict"], "release": rel["release"]}
    return out


def derive(years, with_curriculum: bool = True) -> list[dict]:
    """Candidate items learned from `years`. Directions first, then slip size on top of them."""
    items: list[dict] = []
    pool = _pool(years)
    cur = _curriculum_directions() if with_curriculum else {}
    for p in PROPS:
        k, n = sum(pool[p]), len(pool[p])
        under_lo = _wilson_lo(n - k, n)
        sources = []
        side = None
        if n >= 150 and under_lo > 0.5:
            side = "under"
            sources.append(f"JIMMY board 2023-25: {n - k}/{n} unders hit ({(n - k) / n:.1%}, 95% lower bound {under_lo:.1%})")
        if p in cur and cur[p]["side"] == "under":
            side = "under"
            sources.append(f"curriculum {cur[p]['release']} {cur[p]['lesson']} ({cur[p]['verdict']})")
        if side:
            items.append({"id": f"direction:{p}", "kind": "DIRECTION", "market": p, "change": {"direction": {p: side}},
                          "title": f"Bet {jh.PROPS[p]['label']} UNDERS instead of overs",
                          "evidence": {"legs": n, "over_hit": round(k / n, 4) if n else None, "under_hit": round((n - k) / n, 4) if n else None,
                                       "under_hit_lower_95": round(under_lo, 4)},
                          "sources": sources, "lessons": [cur[p]["lesson"]] if p in cur and cur[p]["side"] == "under" else []})
    pol = apply(BASE_POLICY, items)
    table = {}
    for legs in range(1, 6):
        m = evaluate({**pol, "legs": legs}, years)
        table[legs] = {"win_pct": m["win_pct"], "roi": m["roi"], "leg_hit_pct": m["leg_hit_pct"]}
    best = max(table, key=lambda k: (table[k]["roi"], -k))
    if best != BASE_POLICY["legs"] and table[best]["roi"] - table[BASE_POLICY["legs"]]["roi"] >= 0.02:
        lessons = []
        try:
            import boo_curriculum
            rel = boo_curriculum.latest()
            lessons = [l["id"] for u in (rel or {}).get("units", []) for l in u["lessons"] if l["kind"] == "n_legs"][:6]
        except Exception:
            pass
        by_legs = ", ".join("%d: %+.0f%%" % (k, v["roi"] * 100) for k, v in table.items())
        items.append({"id": "legs", "kind": "SLIP_SIZE", "market": "*", "change": {"legs": best},
                      "title": f"Build {best}-leg slips instead of {BASE_POLICY['legs']}",
                      "evidence": {"roi_by_legs": table, "chosen": best},
                      "sources": [f"JIMMY board 2023-25: ROI by legs per slip ({by_legs})"],
                      "lessons": lessons})
    return items


def apply(policy: dict, items: list[dict]) -> dict:
    p = {"legs": policy["legs"], "direction": dict(policy["direction"]), "rank": policy["rank"]}
    for it in items:
        if "legs" in it["change"]:
            p["legs"] = it["change"]["legs"]
        p["direction"].update(it["change"].get("direction", {}))
    return p


# --------------------------------------------------------------------------- out-of-sample decision and impact
def _agg(parts: list[dict]) -> dict:
    s = dict(slips=0, wins=0, legs=0, leg_hits=0, staked=0.0, returned=0.0)
    for m in parts:
        for k in s:
            s[k] += m[k]
    return _fin(s)


def decide(items: list[dict]) -> tuple[list[dict], dict]:
    """Test every item out of sample, in order, on top of the items already accepted. Returns (items with impact+status, summary)."""
    folds = {h: {it["id"]: it for it in derive([y for y in YEARS if y != h])} for h in YEARS}

    def oos(ids: list[str]) -> dict:
        parts = []
        for h in YEARS:
            pol = apply(BASE_POLICY, [folds[h][i] for i in ids if i in folds[h]])
            parts.append(evaluate(pol, (h,)))
        return _agg(parts)

    accepted: list[str] = []
    cur = oos([])
    base_oos = cur
    for it in items:
        m = oos(accepted + [it["id"]])
        helps = m["roi"] >= cur["roi"] and m["leg_hit_pct"] >= cur["leg_hit_pct"] and (m["roi"] > cur["roi"] or m["leg_hit_pct"] > cur["leg_hit_pct"])
        it["impact"] = {"before": {k: cur[k] for k in ("win_pct", "leg_hit_pct", "roi", "slips")},
                        "after": {k: m[k] for k in ("win_pct", "leg_hit_pct", "roi", "slips")},
                        "delta": {k: round(m[k] - cur[k], 4) for k in ("win_pct", "leg_hit_pct", "roi")}, "basis": "out-of-sample, each season scored by a model that never saw it"}
        it["status"] = "APPLIED" if helps else "HELD"
        it["reason"] = ("Improved out-of-sample ROI/leg hit rate without hurting the other." if helps else
                        "Did not improve JIMMY out of sample, so it was held back.")
        if helps:
            accepted.append(it["id"])
            cur = m
    return items, {"baseline_oos": base_oos, "final_oos": cur, "accepted": accepted}


# --------------------------------------------------------------------------- the one button
def timeline() -> dict:
    return _read("timeline.json", {"updates": []})


def send_to_jimmy(trigger: str = "button", force: bool = False) -> dict:
    """Package what MY BOO knows, test every item, apply the ones that help, and record a numbered update."""
    with _LOCK:
        try:
            import boo_curriculum
            boo_curriculum.cut_release(trigger="train-button")
            rel = boo_curriculum.latest()
        except Exception:
            rel = None
        items = derive(YEARS)
        items, summ = decide(items)
        applied = [i for i in items if i["status"] == "APPLIED"]
        before = current()
        new_policy = apply(BASE_POLICY, applied)
        tl = timeline()
        if not tl["updates"]:
            base = evaluate(BASE_POLICY)
            tl["updates"].append({"update": "JU-0000", "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "curriculum_release": None,
                                  "policy": BASE_POLICY, "items_applied": 0, "items_held": 0, "in_sample": base,
                                  "out_of_sample": summ["baseline_oos"], "note": "Baseline: JIMMY's auto-play before any update (top 3 by confidence, all overs)."})
        if new_policy == before["policy"] and not force:
            _write("timeline.json", tl)
            return {"sent": False, "reason": "JIMMY is already on this policy; there is nothing new to send.", "version": before["version"]}
        n = len(tl["updates"])
        uid = f"JU-{n:04d}"
        for k, it in enumerate(items, 1):
            it["item"] = f"{uid}.{k:02d}"
        in_sample = evaluate(new_policy)
        prev = tl["updates"][-1]
        entry = {"update": uid, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trigger": trigger,
                 "curriculum_release": rel["release"] if rel else None, "policy": new_policy, "items_applied": len(applied),
                 "items_held": len(items) - len(applied), "in_sample": in_sample, "out_of_sample": summ["final_oos"],
                 "delta_vs_previous": {k: round(summ["final_oos"][k] - prev["out_of_sample"][k], 4) for k in ("win_pct", "leg_hit_pct", "roi")}}
        pkg = {**entry, "policy_before": before["policy"], "items": items,
               "note": "Out-of-sample = each real season scored by items derived from the other two. In-sample = the final policy replayed on all three."}
        (DIR / "updates").mkdir(parents=True, exist_ok=True)
        (DIR / "updates" / f"{uid}.json").write_text(json.dumps(pkg, indent=1))
        (DIR / "updates" / f"{uid}.md").write_text(_notes(pkg))
        (DIR / "updates" / f"{uid}.jsonl").write_text("\n".join(json.dumps({"schema": "boo.jimmy_update.item.v1", "update": uid, **i}) for i in items) + "\n")
        tl["updates"].append(entry)
        _write("timeline.json", tl)
        _write("policy.json", {"version": uid, "policy": new_policy, "updated": entry["created"]})
    try:
        import boo_store
        threading.Thread(target=boo_store.push_dir, args=(DIR, "myboo/boo_jimmy"), daemon=True).start()
    except Exception:
        pass
    return {"sent": True, "update": uid, "applied": len(applied), "held": len(items) - len(applied), "policy": new_policy,
            "out_of_sample": summ["final_oos"], "baseline_out_of_sample": summ["baseline_oos"], "delta_vs_previous": entry["delta_vs_previous"]}


def _notes(p: dict) -> str:
    pct = lambda x: f"{x * 100:.1f}%"
    o, d = p["out_of_sample"], p["delta_vs_previous"]
    md = [f"# JIMMY training update {p['update']}", "", f"Sent {p['created']} ({p['trigger']}) with curriculum release {p['curriculum_release'] or 'none'}.", "",
          f"**Out-of-sample result: win % {pct(o['win_pct'])} ({d['win_pct'] * 100:+.1f} pts) · leg hit rate {pct(o['leg_hit_pct'])} ({d['leg_hit_pct'] * 100:+.1f} pts) · "
          f"ROI {pct(o['roi'])} ({d['roi'] * 100:+.1f} pts)** over {o['slips']} slips.", "",
          f"{p['items_applied']} item(s) applied, {p['items_held']} held back.", "", "| Item | Kind | Change | Status | Win % | Leg hit | ROI |", "|---|---|---|---|---|---|---|"]
    for i in p["items"]:
        a, b = i["impact"]["before"], i["impact"]["after"]
        md.append(f"| {i['item']} | {i['kind']} | {i['title']} | {i['status']} | {pct(a['win_pct'])} → {pct(b['win_pct'])} | {pct(a['leg_hit_pct'])} → {pct(b['leg_hit_pct'])} | {pct(a['roi'])} → {pct(b['roi'])} |")
    md += ["", "Why each item: " + " ".join(f"**{i['item']}** {i['reason']}" for i in p["items"]), "", f"> {p['note']}", ""]
    return "\n".join(md)


def get_update(uid: str) -> dict | None:
    import re
    return _read(f"updates/{uid}.json", None) if re.fullmatch(r"JU-\d{4}", uid or "") else None


def update_notes(uid: str) -> str | None:
    import re
    p = DIR / "updates" / f"{uid}.md"
    return p.read_text() if re.fullmatch(r"JU-\d{4}", uid or "") and p.exists() else None


def update_rows(uid: str) -> str | None:
    import re
    p = DIR / "updates" / f"{uid}.jsonl"
    return p.read_text() if re.fullmatch(r"JU-\d{4}", uid or "") and p.exists() else None


# --------------------------------------------------------------------------- live tracking: every season JIMMY plays is stamped with the update that was live
def record_live(year: int, slips: list[dict], bankroll: float, ver: str, session: str) -> None:
    graded = [s for s in slips if s.get("result") is not None]
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "version": ver, "year": year, "session": session, "slips": len(graded),
           "wins": sum(1 for s in graded if s["result"]), "legs": sum(s["legs"] for s in graded), "legs_hit": sum(s["legs_hit"] for s in graded),
           "staked": round(sum(s["wager"] for s in graded), 2), "returned": round(sum(s["payout"] for s in graded), 2), "bankroll": bankroll}
    with _LOCK:
        DIR.mkdir(parents=True, exist_ok=True)
        with (DIR / "live.jsonl").open("a") as fh:
            fh.write(json.dumps(row) + "\n")


def live_summary() -> dict:
    out: dict[str, dict] = {}
    try:
        rows = [json.loads(l) for l in (DIR / "live.jsonl").read_text().splitlines() if l.strip()]
    except OSError:
        rows = []
    for r in rows:
        o = out.setdefault(r["version"], dict(seasons=0, slips=0, wins=0, legs=0, legs_hit=0, staked=0.0, returned=0.0))
        o["seasons"] += 1
        for k in ("slips", "wins", "legs", "legs_hit"):
            o[k] += r[k]
        o["staked"] += r["staked"]
        o["returned"] += r["returned"]
    for o in out.values():
        o["win_pct"] = round(o["wins"] / o["slips"], 4) if o["slips"] else None
        o["leg_hit_pct"] = round(o["legs_hit"] / o["legs"], 4) if o["legs"] else None
        o["roi"] = round((o["returned"] - o["staked"]) / o["staked"], 4) if o["staked"] else None
    return out


def status() -> dict:
    tl = timeline()
    return {"current": current(), "updates": tl["updates"], "live": live_summary()}

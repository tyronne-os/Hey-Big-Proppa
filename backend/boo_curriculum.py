"""
MY BOO's training curriculum: an aggregator that turns BETTER-VERSE results into itemized, numbered releases.

  evidence ledger   every Strategy Lab study MY BOO is sent is filed in evidence.jsonl (compact per-strategy stats).
  lessons           the same strategy or slip shape across studies is pooled and graded with explicit rules:
                      TEACH      chance of profit in BOTH real seasons >= 60% (and >= 50% in every study), in profit in each
                                 season, hit rate above the price-implied probability, >= 1,000 slips
                      WATCH      plausible but unproven (>= 30% chance of profit in every tested season)
                      FRAGILE    profitable overall (95% range above zero) but it lost money in at least one tested season
                      AVOID      confident loser: the whole 95% range is below zero, >= 1,000 slips
                      BENCHMARK  reference facts (legs per slip, same-game vs cross-game, tiers)
                      CASE       a big winner and why that win is not a template
  releases          R001, R002, ...: a snapshot of every lesson in five units, with what changed since the last release
                    (new / promoted / demoted / updated / retired), release notes (.md) and flat training rows (.jsonl).

A release is cut only when something changed, on demand, when a study is sent to MY BOO, and with the weekly Tuesday batch.
Nothing here guesses: a lesson needs sample size and replication to be taught, and it can be demoted when new evidence disagrees.

Files (lake/gold/nfl/boo_curriculum/, mirrored to the private HF dataset):
  evidence.jsonl · index.json · releases/R001.json · releases/R001.md · releases/R001.jsonl
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

import betterverse_bettors as mb

DIR = Path(__file__).parent.parent / "lake/gold/nfl/boo_curriculum"
SCHEMA = "boo.curriculum.v1"
LESSON_SCHEMA = "boo.curriculum.lesson.v1"
_LOCK = threading.RLock()
_REL = re.compile(r"R\d{3,}")

# grading rules (kept in one place so docs and tests quote the same numbers)
TEACH_P_ALL, TEACH_P_ALL_MIN, MIN_SLIPS = 0.60, 0.50, 1000
WATCH_P_ALL = 0.30
DIMS = ("shape", "style_tier", "n_legs", "sgp", "tier")
BENCHMARK_DIMS = ("n_legs", "sgp", "tier")
UNITS = [
    ("U1", "Foundations: how the house wins", "Reference numbers every slip is measured against.", ("benchmark",)),
    ("U2", "Parlay types that hold up", "Teach these: likely to make money in every tested season.", ("teach",)),
    ("U3", "Watch list", "Promising but not proven. Collect more evidence before teaching.", ("watch",)),
    ("U4", "Fragile: worked until it didn't", "Profitable overall, but lost money in at least one real season. Not taught.", ("fragile",)),
    ("U5", "Traps to avoid", "Confident losers. Stop building these.", ("avoid",)),
    ("U6", "When rookies win", "Big wins and why they are not templates.", ("case",)),
]
CAVEAT = ("Every study replays the same real NFL seasons, so extra studies average out the betters' randomness, not what really "
          "happened. A lesson taught on two seasons can fail on a third: that is what releases are for. Lessons are priors for MY BOO, JIMMY and JEV, not guarantees.")


def _path(*p: str) -> Path:
    return DIR.joinpath(*p)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# --------------------------------------------------------------------------- evidence
_KEEP = ("key", "label", "slips", "staked", "roi", "ci_lo", "ci_hi", "p_profit", "p_all_seasons", "p_profit_by_season", "hit_rate",
         "implied", "edge_pts", "by_season", "profitable_95", "profitable_all_seasons", "rank_p")


def _evidence_rows() -> list[dict]:
    try:
        return [json.loads(l) for l in _path("evidence.jsonl").read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def current_rows() -> list[dict]:
    """Evidence that still counts: a study is superseded by a later one with the same universes, betters and seed that tests a superset of its seasons."""
    rows = _evidence_rows()
    def covers(o, r):
        return (o is not r and o.get("seed") == r.get("seed") and o["universes"] == r["universes"] and o["bettors_per_universe"] == r["bettors_per_universe"]
                and set(r.get("seasons", [])) < set(o.get("seasons", [])))
    return [r for r in rows if not any(covers(o, r) for o in rows)]


def ingest_study(study_id: str) -> dict:
    """File a Strategy Lab study as evidence. Idempotent per study id."""
    import betterverse_study
    st = betterverse_study.load(study_id)
    if st is None:
        raise FileNotFoundError(study_id)
    return ingest_study_dict(st)


def ingest_study_dict(st: dict) -> dict:
    items = [{"dim": d, **{k: r[k] for k in _KEEP if k in r}} for d in DIMS for r in st["dims"].get(d, [])]
    arch_key = {v["label"]: k for k, v in mb.ARCHETYPES.items()}
    tier_key = {v["label"]: k for k, v in mb.TIERS.items()}
    st_roi = {r["key"]: r["roi"] for r in st["dims"].get("style_tier", [])}
    cases = []
    for w in st.get("rookie_winners", [])[:5]:
        sk = f"{arch_key.get(w['label'], '')}|{tier_key.get(w['tier_label'], '')}"
        cases.append({k: w[k] for k in ("username", "tier_label", "label", "unit", "season", "universe", "final_bankroll", "net", "slips",
                                        "best_signature", "best_odds", "best_payout")} | {"strategy_roi": st_roi.get(sk)})
    rec = {"study_id": st["study_id"], "ingested": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "universes": st["universes"],
           "bettors_per_universe": st["bettors_per_universe"], "bettor_seasons": st["bettor_seasons"], "slips": st["slips"],
           "seed": st.get("seed"), "seasons": st.get("seasons", []),
           "field": st["field"], "items": items, "cases": cases}
    with _LOCK:
        DIR.mkdir(parents=True, exist_ok=True)
        rows = [r for r in _evidence_rows() if r["study_id"] != rec["study_id"]] + [rec]
        tmp = _path("evidence.jsonl.tmp")
        tmp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        tmp.replace(_path("evidence.jsonl"))
    return {"study_id": rec["study_id"], "items": len(items), "studies_on_file": len(rows)}


# --------------------------------------------------------------------------- pooling and grading
def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def pool(rows: list[dict]) -> dict:
    """Pool one strategy's rows (one per study) into a single set of numbers."""
    slips = sum(r["slips"] for r in rows)
    staked = sum(r["staked"] for r in rows) or 1.0
    seasons: dict[str, list[tuple[float, int]]] = {}
    for r in rows:
        for s, v in (r.get("by_season") or {}).items():
            seasons.setdefault(s, []).append((v, r["slips"]))
    by_season = {s: sum(v * n for v, n in xs) / sum(n for _, n in xs) for s, xs in seasons.items()}
    w = lambda f: sum(r[f] * r["slips"] for r in rows) / slips
    pb = [r["p_all_seasons"] for r in rows]
    return {"label": rows[-1]["label"], "studies": len(rows), "slips": slips, "staked": round(staked, 2),
            "roi": sum(r["roi"] * r["staked"] for r in rows) / staked,
            "ci_lo": _mean(r["ci_lo"] for r in rows), "ci_hi": _mean(r["ci_hi"] for r in rows),
            "p_all": _mean(pb), "p_all_min": min(pb), "p_profit": _mean(r["p_profit"] for r in rows),
            "hit_rate": w("hit_rate"), "implied": w("implied"), "edge_pts": w("hit_rate") - w("implied"),
            "by_season": by_season, "profitable_95_all": all(r["profitable_95"] for r in rows),
            "replications": {"passed": sum(1 for r in rows if _teach_ok(r)), "total": len(rows)}}


def _teach_ok(r: dict) -> bool:
    return r["p_all_seasons"] >= TEACH_P_ALL and r["slips"] >= MIN_SLIPS and bool(r.get("profitable_all_seasons"))


def grade(a: dict, dim: str) -> str | None:
    if dim in BENCHMARK_DIMS:
        return "benchmark"
    seasons_ok = len(a["by_season"]) >= 2 and all(v > 0 for v in a["by_season"].values())
    if (a["p_all"] >= TEACH_P_ALL and a["p_all_min"] >= TEACH_P_ALL_MIN and seasons_ok and a["edge_pts"] > 0 and a["slips"] >= MIN_SLIPS):
        return "teach"
    if a["ci_hi"] < 0 and a["slips"] >= MIN_SLIPS:
        return "avoid"
    if a["ci_lo"] > 0 and a["slips"] >= MIN_SLIPS:
        return "fragile"
    if a["p_all"] >= WATCH_P_ALL:
        return "watch"
    return None


def _rule(verdict: str, a: dict, dim: str) -> str:
    t = a["label"]
    hit = f"{a['hit_rate']:.0%} of slips hit vs {a['implied']:.0%} implied by the price"
    if verdict == "teach":
        return f"Prefer {t}: {a['p_all']:.0%} chance of profit in every tested season; {hit}; ROI {a['roi']:+.1%}."
    if verdict == "watch":
        return f"Watch {t}: profit is plausible ({a['p_all']:.0%} in every season) but not proven; ROI {a['roi']:+.1%}, 95% range {a['ci_lo']:+.1%} to {a['ci_hi']:+.1%}."
    if verdict == "fragile":
        per = ", ".join(f"{y} {v:+.0%}" for y, v in sorted(a["by_season"].items()))
        return f"Don't trust {t}: ROI {a['roi']:+.1%} overall (95% range {a['ci_lo']:+.1%} to {a['ci_hi']:+.1%}) but it did not repeat: {per}."
    if verdict == "avoid":
        return f"Avoid {t}: it loses money with confidence (ROI {a['roi']:+.1%}, 95% range {a['ci_lo']:+.1%} to {a['ci_hi']:+.1%}); {hit}."
    return f"{t}: ROI {a['roi']:+.1%}; {a['hit_rate']:.0%} of slips hit vs {a['implied']:.0%} implied by the price."


def _apply(verdict: str, dim: str, key: str, a: dict) -> dict:
    action = {"teach": "prefer", "watch": "watch", "fragile": "distrust", "avoid": "avoid"}.get(verdict, "reference")
    base = {"scope": {"shape": "slip_shape", "style_tier": "strategy"}.get(dim, dim), "key": key, "action": action}
    if dim == "shape":
        base |= {"signature": key, "hit_prob": round(a["hit_rate"], 4), "implied_prob": round(a["implied"], 4), "edge_pts": round(a["edge_pts"], 4)}
    else:
        base |= {"roi": round(a["roi"], 4)}
    return base


def build_lessons() -> list[dict]:
    rows = current_rows()
    if not rows:
        return []
    groups: dict[tuple[str, str], list[dict]] = {}
    for rec in rows:
        for it in rec["items"]:
            groups.setdefault((it["dim"], it["key"]), []).append(it)
    out = []
    for (dim, key), rs in groups.items():
        a = pool(rs)
        v = grade(a, dim)
        if v is None:
            continue
        conf = None if v == "benchmark" else (round(1 - a["p_profit"], 3) if v == "avoid" else round(a["p_all"], 3))
        out.append({
            "id": f"L-{dim}-{_slug(key)}", "kind": dim, "key": key, "title": a["label"], "verdict": v, "confidence": conf,
            "rule": _rule(v, a, dim), "apply": _apply(v, dim, key, a),
            "evidence": {"studies": a["studies"], "slips": a["slips"], "roi": round(a["roi"], 4), "ci_lo": round(a["ci_lo"], 4), "ci_hi": round(a["ci_hi"], 4),
                         "p_all_seasons": round(a["p_all"], 4), "p_all_min": round(a["p_all_min"], 4), "p_profit": round(a["p_profit"], 4),
                         "hit_rate": round(a["hit_rate"], 4), "implied": round(a["implied"], 4), "edge_pts": round(a["edge_pts"], 4),
                         "by_season": {k: round(x, 4) for k, x in a["by_season"].items()}, "replications": a["replications"]}})
    latest = rows[-1]                                                # case studies come from the most recent study only
    for c in latest["cases"]:
        roi = c.get("strategy_roi")
        shape_name = c["best_signature"]
        out.append({
            "id": f"L-case-{_slug(c['username'])}-u{c['universe']}-{c['season']}", "kind": "case", "key": c["best_signature"],
            "title": f"{c['username']} ({c['tier_label']}, {c['label']})", "verdict": "case", "confidence": None,
            "rule": (f"{c['username']} turned $100 into ${c['final_bankroll']:,.2f} in {c['season']} with {shape_name} at {c['best_odds']:.0f}x "
                     f"(paid ${c['best_payout']:,.2f}). Their strategy overall returned {roi:+.1%}: a big win is not a template." if roi is not None else
                     f"{c['username']} turned $100 into ${c['final_bankroll']:,.2f} in {c['season']} with {shape_name} at {c['best_odds']:.0f}x."),
            "apply": {"scope": "case", "key": c["best_signature"], "action": "do_not_copy"},
            "evidence": {"studies": 1, "slips": c["slips"], "final_bankroll": c["final_bankroll"], "strategy_roi": roi, "season": c["season"]}})
    return out


# --------------------------------------------------------------------------- releases
def _load_json(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def index() -> dict:
    return _load_json(_path("index.json")) or {"schema": SCHEMA, "latest": None, "releases": []}


def get(release: str) -> dict | None:
    return _load_json(_path("releases", f"{release}.json")) if _REL.fullmatch(release or "") else None


def latest() -> dict | None:
    i = index()
    return get(i["latest"]) if i["latest"] else None


def notes(release: str) -> str | None:
    p = _path("releases", f"{release}.md")
    return p.read_text() if _REL.fullmatch(release or "") and p.exists() else None


def training_rows(release: str) -> str | None:
    p = _path("releases", f"{release}.jsonl")
    return p.read_text() if _REL.fullmatch(release or "") and p.exists() else None


def _diff(prev: dict | None, lessons: list[dict]) -> dict:
    d = {"new": [], "promoted": [], "demoted": [], "updated": [], "retired": []}
    status: dict[str, str] = {}
    if prev is None:
        for l in lessons:
            status[l["id"]] = "NEW"
        d["new"] = [l["id"] for l in lessons if l["verdict"] != "case"]
        d["changed"] = bool(lessons)
        return d | {"status": status}
    old = {l["id"]: l for u in prev["units"] for l in u["lessons"]}
    now = {l["id"]: l for l in lessons}
    ladder = {"avoid": 0, "fragile": 1, "watch": 2, "teach": 3}
    for i, l in now.items():
        o = old.get(i)
        if o is None:
            status[i] = "NEW"
            if l["verdict"] != "case":
                d["new"].append(i)
        elif l["verdict"] != o["verdict"] and l["verdict"] in ladder and o["verdict"] in ladder:
            up = ladder[l["verdict"]] > ladder[o["verdict"]]
            status[i] = "PROMOTED" if up else "DEMOTED"
            d["promoted" if up else "demoted"].append(i)
        elif l["verdict"] in ladder and (abs((l["confidence"] or 0) - (o["confidence"] or 0)) >= 0.10 or l["evidence"]["studies"] != o["evidence"]["studies"]):
            status[i] = "UPDATED"
            d["updated"].append(i)
        else:
            status[i] = "UNCHANGED"
    d["retired"] = [i for i, o in old.items() if i not in now and o["verdict"] != "case"]
    d["changed"] = any(d[k] for k in ("new", "promoted", "demoted", "updated", "retired"))
    return d | {"status": status}


def _units(lessons: list[dict], status: dict) -> list[dict]:
    units = []
    for uid, title, blurb, verdicts in UNITS:
        ls = [dict(l, status=status.get(l["id"], "NEW")) for l in lessons if l["verdict"] in verdicts]
        ls.sort(key=lambda l: (-(l["confidence"] or 0), l["title"]))
        units.append({"id": uid, "title": title, "blurb": blurb, "lessons": ls})
    return units


def _notes_md(rel: dict) -> str:
    s = rel["summary"]
    md = [f"# MY BOO training curriculum · {rel['release']}", "",
          f"Released {rel['created']} ({rel['trigger']}) from {len(rel['studies'])} Strategy Lab stud{'y' if len(rel['studies']) == 1 else 'ies'}: "
          f"{', '.join(rel['studies'])}.", "",
          f"**{s['teach']} to teach · {s['watch']} on the watch list · {s['fragile']} fragile · {s['avoid']} to avoid · {s['benchmark']} benchmarks · {s['case']} case studies**", ""]
    d = rel["diff"]
    if rel["previous"]:
        md += [f"## What changed since {rel['previous']}", "",
               f"- New lessons: {len(d['new'])}", f"- Promoted: {len(d['promoted'])}", f"- Demoted: {len(d['demoted'])}",
               f"- Updated (confidence moved 10+ points or new evidence): {len(d['updated'])}", f"- Retired: {len(d['retired'])}", ""]
        titles = {l["id"]: l["title"] for u in rel["units"] for l in u["lessons"]}
        for k in ("promoted", "demoted"):
            for i in d[k]:
                md.append(f"- **{k.title()}**: {titles.get(i, i)}")
        md.append("")
    else:
        md += ["First release.", ""]
    if rel.get("superseded"):
        md += [f"Evidence replaced by a later study that tests more seasons: {', '.join(rel['superseded'])}.", ""]
    for u in rel["units"]:
        md += [f"## {u['id']} · {u['title']}", "", f"*{u['blurb']}*", ""]
        if not u["lessons"]:
            md += ["Nothing qualifies yet.", ""]
            continue
        md += ["| Lesson | Verdict | Confidence | Evidence | Status |", "|---|---|---|---|---|"]
        for l in u["lessons"]:
            e = l["evidence"]
            ev = (f"{e['slips']:,} slips · {e['studies']} stud{'y' if e['studies'] == 1 else 'ies'} · ROI {e['roi']:+.1%}" if "roi" in e else f"{e.get('slips', '')} slips")
            conf = "" if l["confidence"] is None else f"{l['confidence']:.0%}"
            md.append(f"| {l['rule']} | {l['verdict']} | {conf} | {ev} | {l['status']} |")
        md.append("")
    md += ["## How lessons are graded", "",
           f"- **Teach**: chance of profit in every tested season ≥ {TEACH_P_ALL:.0%} (and ≥ {TEACH_P_ALL_MIN:.0%} in every study), in profit in each season, hit rate above the price-implied probability, ≥ {MIN_SLIPS:,} slips.",
           f"- **Watch**: ≥ {WATCH_P_ALL:.0%} chance of profit in every season, or a profit the 95% range supports.",
           f"- **Fragile**: profitable overall (95% range above zero, ≥ {MIN_SLIPS:,} slips) but it lost money in at least one tested season.",
           f"- **Avoid**: the whole 95% range is below zero, ≥ {MIN_SLIPS:,} slips.", "", f"> {CAVEAT}", ""]
    return "\n".join(md)


def cut_release(trigger: str = "manual", force: bool = False) -> dict:
    """Aggregate all evidence and, if anything changed (or force), write the next numbered release."""
    with _LOCK:
        lessons = build_lessons()
        if not lessons:
            return {"released": False, "reason": "no evidence on file"}
        prev = latest()
        diff = _diff(prev, lessons)
        if prev and not force and not diff["changed"]:
            return {"released": False, "reason": "no change since " + prev["release"], "latest": prev["release"]}
        n = (int(prev["release"][1:]) if prev else 0) + 1
        rid = f"R{n:03d}"
        status = diff.pop("status")
        units = _units(lessons, status)
        counts = {k: sum(1 for l in lessons if l["verdict"] == k) for k in ("teach", "watch", "fragile", "avoid", "benchmark", "case")}
        rel = {"schema": SCHEMA, "release": rid, "previous": prev["release"] if prev else None,
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trigger": trigger,
               "studies": [r["study_id"] for r in current_rows()], "superseded": [r["study_id"] for r in _evidence_rows() if r not in current_rows()], "summary": counts, "diff": diff, "units": units, "caveat": CAVEAT}
        (DIR / "releases").mkdir(parents=True, exist_ok=True)
        _path("releases", f"{rid}.json").write_text(json.dumps(rel, indent=1))
        _path("releases", f"{rid}.md").write_text(_notes_md(rel))
        rows = [json.dumps({"schema": LESSON_SCHEMA, "release": rid, "unit": u["id"], **{k: v for k, v in l.items()}}) for u in units for l in u["lessons"]]
        _path("releases", f"{rid}.jsonl").write_text("\n".join(rows) + "\n")
        idx = index()
        idx["releases"].append({"release": rid, "created": rel["created"], "trigger": trigger, "summary": counts, "studies": len(rel["studies"]),
                                "changes": {k: len(diff[k]) for k in ("new", "promoted", "demoted", "updated", "retired")}})
        idx["latest"] = rid
        _path("index.json").write_text(json.dumps(idx, indent=1))
    try:
        import boo_store
        threading.Thread(target=boo_store.push_dir, args=(DIR, "myboo/boo_curriculum"), daemon=True).start()
    except Exception:
        pass
    return {"released": True, "release": rid, "summary": counts, "changes": {k: len(diff[k]) for k in ("new", "promoted", "demoted", "updated", "retired")}}


def prior_for_shape(signature: str) -> dict | None:
    """What the latest release says to do with a slip shape ('prefer' / 'watch' / 'avoid'); None when MY BOO has no lesson on it."""
    rel = latest()
    if not rel:
        return None
    for u in rel["units"]:
        for l in u["lessons"]:
            if l["kind"] == "shape" and l["key"] == signature:
                return {"action": l["apply"]["action"], "confidence": l["confidence"], **{k: l["apply"][k] for k in ("hit_prob", "implied_prob", "edge_pts") if k in l["apply"]},
                        "release": rel["release"]}
    return None

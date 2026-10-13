"""
MY BOO's POST-GAME REPORT -- every ticket on a night, every leg on those tickets, graded and explained.

  legs          each unique prediction judged on its own: passed or failed, by how much, how many tickets carried it
  tickets       which cashed, which lost, which lost by a single leg, and which leg did it
  killers       contagion: one failed prediction copied across many tickets takes all of them down together
  what if       the ways the night would have paid: bench the killer, safe lines (-15%), JEV's veto, shorter tickets
  structure lab ticket shapes (ML + passing + rushing, three props, total + two props, same team...) replayed on every
                graded prediction in MY BOO's ledger -- which shape actually cashes most and pays best
  JEV           JEV against the Big Proppa Line on the same reads
  blueprint     the rules for the next primetime game, each with the numbers behind it, plus that game's candidates

Grades come from MY BOO's ledger after her own audit against the ESPN final (slip_alerts.regrade_game).
Everything is measured, nothing is assumed; small samples are labelled as such.
"""
from __future__ import annotations

import csv
import itertools
import math
import random
import time
from collections import Counter, defaultdict

import data
import myboo

TYPE = {"passyds": "PASSING", "rushyds": "RUSHING", "recyds": "RECEIVING YDS", "recs": "RECEPTIONS", "nfl_ml": "MONEYLINE",
        "nfl_total": "GAME TOTAL", "nfl_spread": "SPREAD", "kickpts": "KICKER", "anytd": "TD SCORER", "firsttd": "TD SCORER",
        "passtd": "PASS TDS", "carries": "CARRIES"}
PROP = {"passyds", "rushyds", "recyds", "recs"}
WORD = {"passyds": "pass yds", "rushyds": "rush yds", "recyds": "rec yds", "recs": "receptions", "kickpts": "kicking pts",
        "anytd": "anytime TD", "firsttd": "first TD", "passtd": "pass TDs", "carries": "carries"}
STAKE = 5.0
_CACHE: dict[str, tuple[float, dict]] = {}


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _dec(american) -> float:
    a = _f(american, 0.0) or 0.0
    if not a:
        return 1.0
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _am(dec: float) -> str:
    if dec <= 1:
        return "—"
    v = round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))
    return f"+{v}" if v > 0 else str(v)


def _ledger() -> tuple[dict[str, dict], list[dict]]:
    with open(myboo._TICKETS_FILE, newline="") as f:
        tickets = {t["ticket_id"]: t for t in csv.DictReader(f)}
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = list(csv.DictReader(f))
    return tickets, legs


def _key(l: dict) -> tuple:
    return (l.get("game_id", ""), l["player_name"], l.get("team", ""), l["market"], l.get("direction") or "over", _f(l.get("line"), 0.0))


def _label(k: tuple) -> str:
    _, name, team, mk, d, line = k
    if mk == "nfl_ml":
        return f"{team or name} moneyline"
    if mk == "nfl_total":
        return f"Game total {d} {line:g}"
    if mk == "nfl_spread":
        return f"{team or name} {line:+g}"
    return f"{name} {d} {line:g} {WORD.get(mk, mk)}"


def _safe_line(line: float, d: str) -> float:
    # 15% easier: overs drop, unders rise; to the nearest half point in the bettor's favor
    return max(0.5, math.floor(line * 0.85 * 2) / 2) if d == "over" else math.ceil(line * 1.15 * 2) / 2


def _passes(actual: float | None, line: float, d: str) -> bool | None:
    if actual is None:
        return None
    return actual > line if d == "over" else actual < line


def games() -> list[dict]:
    """Games with MY BOO tickets, newest first, with ticket counts (for the report's game picker)."""
    tickets, legs = _ledger()
    sched = {g["game_id"]: g for g in data.load("schedule")}
    by_g: dict[str, set] = defaultdict(set)
    for l in legs:
        if l.get("game_id"):
            by_g[l["game_id"]].add(l["ticket_id"])
    out = []
    for gid, tids in by_g.items():
        g = sched.get(gid, {})
        if len(tids) < 3:
            continue
        out.append({"gameId": gid, "date": g.get("game_date", ""), "weekday": g.get("weekday", ""), "away": g.get("away_team", ""),
                    "home": g.get("home_team", ""), "tickets": len(tids)})
    return sorted(out, key=lambda x: (x["date"], x["tickets"]), reverse=True)


def default_game() -> str | None:
    """The most recent finished game with a real card of tickets."""
    import datetime as dt
    today = dt.date.today().isoformat()
    for g in games():
        if g["date"] and g["date"] <= today and g["tickets"] >= 5:
            return g["gameId"]
    return None


# ---------------------------------------------------------------------------
# One night
# ---------------------------------------------------------------------------

def _jev_reads(game_id: str) -> dict[tuple, dict]:
    """JEV and BPL probabilities from the JEV ledger for this game's props, keyed like our legs (over side)."""
    try:
        import jev_ledger
        rows = [r for r in jev_ledger._load().values() if r.get("lakeGameId") == game_id]
    except Exception:
        rows = []
    out = {}
    for r in rows:
        mk = r.get("market")
        if r.get("kind") == "prop":
            out[(data.normalize_name(r.get("name", "")), mk, float(r["line"]))] = r
        elif r.get("kind") in ("total", "spread", "ml"):
            out[(r.get("kind"), float(r.get("line") or 0))] = r
    return out


def night(game_id: str) -> dict:
    tickets, legs = _ledger()
    sched = {g["game_id"]: g for g in data.load("schedule")}
    g = sched.get(game_id, {})
    # one game, one night: a ticket counts only if every leg is this game and it was not voided as a cross-game error
    all_by_t: dict[str, list[dict]] = defaultdict(list)
    for l in legs:
        all_by_t[l["ticket_id"]].append(l)
    tids = {tid for tid, ls in all_by_t.items()
            if ls and {x["game_id"] for x in ls} == {game_id} and tickets[tid]["status"] != "PUSH_VOID"}
    by_t: dict[str, list[dict]] = {tid: all_by_t[tid] for tid in tids}

    # distinct tickets: the board regenerates through the day, so identical leg sets are one ticket shown N times
    distinct: dict[tuple, dict] = {}
    for tid, ls in by_t.items():
        fp = tuple(sorted(_key(l) for l in ls))
        d = distinct.setdefault(fp, {"ids": [], "legs": ls, "ticket": tickets[tid]})
        d["ids"].append(tid)

    # every unique prediction on the night (this game only), graded once
    preds: dict[tuple, dict] = {}
    for fp, d in distinct.items():
        for l in d["legs"]:
            if l["game_id"] != game_id:
                continue
            k = _key(l)
            p = preds.setdefault(k, {"key": k, "label": _label(k), "type": TYPE.get(k[3], k[3].upper()), "market": k[3],
                                     "team": k[2], "direction": k[4], "line": k[5], "status": l["status"],
                                     "actual": _f(l.get("actual_value")), "odds": _f(l.get("odds")), "p": [], "tickets": 0,
                                     "killedAlone": 0, "killedShared": 0})
            p["tickets"] += 1
            if l.get("probability"):
                p["p"].append(_f(l["probability"], 0.5))

    jev = _jev_reads(game_id)
    for p in preds.values():
        p["p"] = round(sum(p["p"]) / len(p["p"]), 3) if p["p"] else None
        a, line, d = p["actual"], p["line"], p["direction"]
        p["margin"] = None if a is None or p["market"] in ("nfl_ml", "nfl_spread") else round(a - line, 1)
        p["marginPct"] = None if p["margin"] is None or not line else round(100 * p["margin"] / line, 1)
        sl = _safe_line(line, d) if p["market"] in PROP else None
        p["safeLine"] = sl
        p["safePass"] = _passes(a, sl, d) if sl is not None and p["status"] in ("HIT", "MISS") else None
        j = jev.get((data.normalize_name(p["key"][1]), p["market"], line)) if p["market"] in PROP else \
            jev.get(({"nfl_total": "total", "nfl_spread": "spread", "nfl_ml": "ml"}.get(p["market"], ""), line if p["market"] != "nfl_ml" else 0.0))
        if j:
            jp, bp = float(j["jevP"]), float(j["bplP"])
            if p["market"] in PROP and d == "under":
                jp, bp = 1 - jp, 1 - bp
            p["jevP"], p["bplP"] = round(jp, 3), round(bp, 3)
        else:
            p["jevP"] = p["bplP"] = None

    # ticket outcomes
    rows = []
    for fp, d in distinct.items():
        t, ls = d["ticket"], d["legs"]
        here = [l for l in ls if l["game_id"] == game_id]
        other = [l for l in ls if l["game_id"] != game_id]
        miss = [l for l in ls if l["status"] == "MISS"]
        pending = [l for l in ls if l["status"] == "PENDING"]
        outcome = "LOST" if miss else "WON" if not pending else ("ALIVE" if all(l["status"] == "HIT" for l in here) else "OPEN")
        dec = math.prod(_dec(l.get("odds")) for l in ls)
        rows.append({"ticketIds": d["ids"], "copies": len(d["ids"]), "name": t["name"].split(" · ")[0], "source": t.get("note", ""),
                     "legs": len(ls), "legsHere": len(here), "otherGameLegs": len(other), "hits": sum(l["status"] == "HIT" for l in ls),
                     "misses": [_label(_key(l)) for l in miss], "outcome": outcome, "odds": _am(dec), "decimal": round(dec, 2),
                     "payout": round(STAKE * dec, 2), "_miss": [_key(l) for l in miss], "_legs": [_key(l) for l in ls]})
        for k in {_key(l) for l in miss if l["game_id"] == game_id}:
            if len(miss) == 1:
                preds[k]["killedAlone"] += 1
            else:
                preds[k]["killedShared"] += 1

    decided = [r for r in rows if r["outcome"] in ("WON", "LOST")]
    won = [r for r in rows if r["outcome"] == "WON"]
    lost = [r for r in rows if r["outcome"] == "LOST"]
    one_away = [r for r in lost if len(r["_miss"]) == 1]
    graded = [p for p in preds.values() if p["status"] in ("HIT", "MISS")]

    def rate(ps):
        n = len(ps)
        return {"n": n, "passed": sum(p["status"] == "HIT" for p in ps), "rate": round(sum(p["status"] == "HIT" for p in ps) / n, 3) if n else None}

    by_type = {t: rate([p for p in graded if p["type"] == t]) for t in sorted({p["type"] for p in graded})}
    by_side = {d: rate([p for p in graded if p["direction"] == d]) for d in ("over", "under") if any(p["direction"] == d for p in graded)}
    buckets = []
    for lo, hi in ((0, .5), (.5, .6), (.6, .7), (.7, .85), (.85, 1.01)):
        ps = [p for p in graded if p["p"] is not None and lo <= p["p"] < hi]
        if ps:
            buckets.append({"band": f"{int(lo*100)}-{min(int(hi*100),100)}%", **rate(ps)})

    killers = sorted([p for p in graded if p["status"] == "MISS"], key=lambda p: (-p["killedAlone"], -p["tickets"]))
    by_size = []
    for n in sorted({r["legs"] for r in decided}):
        rs = [r for r in decided if r["legs"] == n]
        by_size.append({"legs": n, "tickets": len(rs), "won": sum(r["outcome"] == "WON" for r in rs)})

    # ---- what would have won
    def cash(r, judge) -> bool:
        return all(judge(k) for k in r["_legs"])

    status = {p["key"]: p for p in preds.values()}

    def truth(k):
        p = status.get(k)
        return p is None or p["status"] == "HIT"          # other-game legs: count as they stand (pending = not a loss here)

    whatif = []
    for p in killers[:6]:
        saved = [r for r in lost if r["_miss"] == [p["key"]]]
        if saved:
            whatif.append({"kind": "bench", "title": f"Leave out {p['label']}",
                           "detail": f"It was the only miss on {len(saved)} ticket{'s' if len(saved) != 1 else ''}. Without it those tickets cash "
                                     f"(paying {_am(sum(r['decimal'] / _dec(p['odds']) for r in saved) / len(saved))} on average instead of {_am(sum(r['decimal'] for r in saved) / len(saved))}).",
                           "ticketsSaved": len(saved)})
    safe_cash = [r for r in lost if cash(r, lambda k: (status[k]["safePass"] if k in status and status[k]["safePass"] is not None else truth(k)))]
    whatif.append({"kind": "safe", "title": "Safe lines on every prop (line cut 15%)",
                   "detail": f"{len(safe_cash)} of {len(lost)} losing tickets would have cashed with every player prop at its SAFE BET line. "
                             "Payouts shrink at the safer lines, so this trades price for hit rate.", "ticketsSaved": len(safe_cash)})
    jev_drop = []
    for r in lost:
        keep = [k for k in r["_legs"] if not (k in status and status[k]["jevP"] is not None and status[k]["jevP"] < 0.5)]
        if len(keep) >= 2 and len(keep) < len(r["_legs"]) and all(truth(k) for k in keep):
            jev_drop.append(r)
    if any(p["jevP"] is not None for p in preds.values()):
        whatif.append({"kind": "jev", "title": "Let JEV veto (drop any leg JEV gave under 50%)",
                       "detail": f"{len(jev_drop)} losing ticket{'s' if len(jev_drop) != 1 else ''} would have cashed after removing the legs JEV did not believe in.",
                       "ticketsSaved": len(jev_drop)})
    trim = []
    for r in lost:
        ks = sorted(r["_legs"], key=lambda k: -((status.get(k) or {}).get("p") or 0))[:3]
        if len(r["_legs"]) > 3 and all(truth(k) for k in ks):
            trim.append(r)
    whatif.append({"kind": "trim", "title": "Cut every ticket to its 3 most likely legs",
                   "detail": f"{len(trim)} of the {sum(1 for r in lost if r['legs'] > 3)} losing tickets longer than 3 legs would have cashed as 3-leggers.",
                   "ticketsSaved": len(trim)})
    top3 = killers[:3]
    exposure = {"topLegs": [{"label": p["label"], "tickets": p["tickets"], "share": round(p["tickets"] / max(1, len(rows)), 2), "result": p["status"]} for p in
                            sorted(preds.values(), key=lambda p: -p["tickets"])[:5]],
                "note": "When one prediction sits on a large share of tickets, a single miss takes all of them down together."}

    hs, as_ = _f(g.get("home_score")), _f(g.get("away_score"))
    from slip_alerts import final_box
    fb = final_box(game_id)
    if fb:
        hs, as_ = fb["home_pts"], fb["away_pts"]
    sp, tl = _f(g.get("spread_line")), _f(g.get("total_line"))
    facts = []
    if hs is not None and as_ is not None:
        facts.append(f"Final: {g.get('away_team')} {int(as_)} - {int(hs)} {g.get('home_team')}")
        if sp is not None:
            fav = g.get("home_team") if sp > 0 else g.get("away_team")
            dog = g.get("away_team") if fav == g.get("home_team") else g.get("home_team")
            dog_won = (as_ > hs and dog == g.get("away_team")) or (hs > as_ and dog == g.get("home_team"))
            facts.append(f"{dog} were the underdog and {'won outright' if dog_won else 'lost'}")
        if tl is not None:
            facts.append(f"Total {int(hs + as_)} vs {tl:g}: {'OVER' if hs + as_ > tl else 'UNDER'} by {abs(hs + as_ - tl):g}")

    clean = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}  # noqa: E731
    return {
        "gameId": game_id, "game": f"{g.get('away_team', '')} @ {g.get('home_team', '')}", "date": g.get("game_date", ""), "facts": facts,
        "legs": {"unique": len(preds), "graded": len(graded), **rate(graded), "byType": by_type, "bySide": by_side, "byConfidence": buckets,
                 "rows": sorted([{k: v for k, v in p.items() if k != "key"} for p in preds.values()], key=lambda p: (-p["tickets"], p["label"]))},
        "tickets": {"distinct": len(rows), "shown": sum(r["copies"] for r in rows), "won": len(won), "lost": len(lost),
                    "alive": sum(r["outcome"] == "ALIVE" for r in rows), "open": sum(r["outcome"] == "OPEN" for r in rows),
                    "lostByOne": len(one_away), "bySize": by_size,
                    "returned": round(sum(r["payout"] for r in won), 2), "staked": round(STAKE * len(decided), 2),
                    "rows": [clean(r) for r in sorted(rows, key=lambda r: ({"WON": 0, "ALIVE": 1, "OPEN": 2, "LOST": 3}[r["outcome"]], len(r["misses"]), -r["decimal"]))]},
        "killers": [{k: v for k, v in p.items() if k in ("label", "type", "tickets", "killedAlone", "killedShared", "actual", "line", "margin", "marginPct", "p", "jevP")} for p in killers[:8]],
        "whatIf": whatif, "exposure": exposure,
    }


# ---------------------------------------------------------------------------
# Structure lab -- ticket shapes replayed on every graded prediction in the ledger
# ---------------------------------------------------------------------------

def _graded_pool() -> dict[str, list[dict]]:
    """Unique graded predictions per game across MY BOO's whole ledger (TD-scorer legs excluded: not bet anymore)."""
    _, legs = _ledger()
    pos = {r.get("name", ""): r.get("position", "") for r in data.player_dimension().values()}
    pool: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for l in legs:
        if l["status"] not in ("HIT", "MISS") or l["market"] in ("anytd", "firsttd"):
            continue
        k = _key(l)
        line, d, a = k[5], k[4], _f(l.get("actual_value"))
        pool[l["game_id"]].setdefault(k, {"key": k, "market": k[3], "team": k[2], "dir": d, "hit": l["status"] == "HIT",
                                          "dec": _dec(l.get("odds")), "p": _f(l.get("probability"), 0.5), "pos": pos.get(k[1], ""),
                                          "safeHit": (_passes(a, _safe_line(line, d), d) if k[3] in PROP else None)})
    return {g: list(v.values()) for g, v in pool.items()}


TEMPLATES = [
    ("ML_PASS_RUSH", "1 moneyline + 1 passing prop + 1 rushing prop", [("nfl_ml",), ("passyds",), ("rushyds",)]),
    ("PASS_RUSH_REC", "1 passing + 1 rushing + 1 receiving/receptions prop", [("passyds",), ("rushyds",), ("recyds", "recs")]),
    ("TOTAL_2PROPS", "game total + 2 player props", [("nfl_total",), tuple(PROP), tuple(PROP)]),
    ("ML_2PROPS", "moneyline + 2 player props", [("nfl_ml",), tuple(PROP), tuple(PROP)]),
    ("THREE_PROPS", "any 3 player props", [tuple(PROP)] * 3),
    ("FIVE_PROPS", "any 5 player props", [tuple(PROP)] * 5),
]


def _combos(pool: list[dict], slots, rng: random.Random, cap: int = 2500, same_team: bool | None = None):
    cand = [[x for x in pool if x["market"] in s] for s in slots]
    if any(not c for c in cand):
        return []
    out, seen = [], set()
    total = math.prod(len(c) for c in cand)
    tries = min(cap * 4, total * 3 if total < cap else cap * 4)
    it = itertools.product(*cand) if total <= cap else (tuple(rng.choice(c) for c in cand) for _ in range(tries))
    for combo in it:
        ids = tuple(sorted(id(x) for x in combo))
        if len(set(ids)) < len(combo) or ids in seen:
            continue
        names = [x["key"][1] for x in combo if x["market"] in PROP]
        if len(names) != len(set(names)):                 # one leg per player
            continue
        teams = {x["team"] for x in combo if x["market"] in PROP}
        if same_team is True and len(teams) > 1:
            continue
        if same_team is False and len(teams) < 2:
            continue
        seen.add(ids)
        out.append(combo)
        if len(out) >= cap:
            break
    return out


def structure_lab() -> dict:
    hit = _CACHE.get("lab")
    if hit and hit[0] > time.time():
        return hit[1]
    pool = _graded_pool()
    rng = random.Random(7)
    rows = []
    variants = [(tid, name, slots, None, False) for tid, name, slots in TEMPLATES]
    variants += [("THREE_SAME_TEAM", "3 player props, same team", [tuple(PROP)] * 3, True, False),
                 ("THREE_BOTH_TEAMS", "3 player props, both teams", [tuple(PROP)] * 3, False, False),
                 ("PASS_RUSH_REC_SAFE", "1 passing + 1 rushing + 1 receiving, all at SAFE (-15%) lines", [("passyds",), ("rushyds",), ("recyds", "recs")], None, True)]
    for tid, name, slots, same, safe in variants:
        n = wins = 0
        ev = 0.0
        games_used = 0
        for gid, ps in pool.items():
            cs = _combos(ps, slots, rng, same_team=same)
            if not cs:
                continue
            games_used += 1
            for c in cs:
                ok = all((x["safeHit"] if safe and x["safeHit"] is not None else x["hit"]) for x in c)
                n += 1
                wins += ok
                if not safe:
                    ev += (STAKE * math.prod(x["dec"] for x in c) if ok else 0.0) - STAKE
        rows.append({"id": tid, "shape": name, "games": games_used, "combos": n, "winRate": round(wins / n, 3) if n else None,
                     "evPer5": round(ev / n, 2) if n and not safe else None, "safeLines": safe})
    # per-leg-type hit rate across the season (unique predictions)
    leg_rate = defaultdict(lambda: [0, 0])
    for ps in pool.values():
        for x in ps:
            t = TYPE.get(x["market"], x["market"])
            leg_rate[t][0] += x["hit"]
            leg_rate[t][1] += 1
    out = {"games": len(pool), "predictions": sum(len(v) for v in pool.values()),
           "shapes": sorted(rows, key=lambda r: (-(r["winRate"] or 0))),
           "legTypes": sorted([{"type": t, "passed": h, "n": n, "rate": round(h / n, 3)} for t, (h, n) in leg_rate.items()], key=lambda r: -r["rate"]),
           "note": "Every ticket shape built from MY BOO's own graded predictions (one leg per player, same game). "
                   "Win rate = share of those tickets where every leg hit. EV per $5 uses the posted prices and ignores same-game "
                   "correlation pricing. Small sample: weeks 3-5."}
    _CACHE["lab"] = (time.time() + 300, out)
    return out


# ---------------------------------------------------------------------------
# JEV and the blueprint
# ---------------------------------------------------------------------------

def _jev_summary(game_id: str) -> dict | None:
    try:
        import jev_reports
        g = next((r for r in jev_reports._load().get("reports", []) if r.get("espnId")), None)
        import slip_alerts
        sched = {x["game_id"]: x for x in slip_alerts.slip_recap._rows("schedule")}
        eid = (sched.get(game_id) or {}).get("espn")
        g = next((r for r in jev_reports._load().get("reports", []) if r.get("espnId") == eid), None)
        if not g:
            return None
        return {k: g.get(k) for k in ("graded", "jevRight", "bplRight", "blendRight", "headline", "bestCalls", "worstMisses")}
    except Exception:
        return None


def _next_primetime() -> dict | None:
    try:
        import h2h
        for g in h2h.slate()["games"]:
            if g["state"] == "PRE" and (g["kickoff"]["weekday"] in ("Thursday", "Monday") or (g["kickoff"]["weekday"] == "Sunday" and g["kickoff"]["hourCt"] >= 17)):
                return g
    except Exception:
        return None
    return None


def blueprint(n: dict, lab: dict) -> dict:
    rules = []
    by_id = {s["id"]: s for s in lab["shapes"]}
    solid = [s for s in lab["shapes"] if s["combos"] >= 200 and not s["safeLines"]]
    core = max(solid, key=lambda s: s["winRate"] or 0) if solid else None
    if core:
        rules.append({"rule": f"Build the core tickets as: {core['shape']}.",
                      "why": f"Best-supported shape: it cashed {round(100 * core['winRate'])}% of {core['combos']} replayed tickets on {core['games']} games "
                             f"({core['evPer5']:+.2f} per $5)."})
    mpr = by_id.get("ML_PASS_RUSH")
    if mpr and mpr["combos"]:
        thin = mpr["combos"] < 200
        rules.append({"rule": "1 moneyline + 1 passing prop + 1 rushing prop: " + ("worth one ticket, not the whole card yet." if thin else "use it as a core ticket."),
                      "why": f"It cashed {round(100 * mpr['winRate'])}% ({mpr['evPer5']:+.2f} per $5) on {mpr['combos']} replayed tickets from {mpr['games']} games"
                             + (" -- the best rate so far, but too few games to trust on its own." if thin else ".")})
    ev = [s for s in solid if s["evPer5"] is not None]
    pay = max(ev, key=lambda s: s["evPer5"]) if ev else None
    if pay and pay is not core:
        rules.append({"rule": f"For the bigger-payout ticket use: {pay['shape']}.",
                      "why": f"Best expected return among well-sampled shapes: {pay['evPer5']:+.2f} per $5 over {pay['combos']} replayed tickets."})
    a3, a5 = by_id.get("THREE_PROPS"), by_id.get("FIVE_PROPS")
    if a3 and a5 and a3["winRate"] is not None and a5["winRate"] is not None:
        rules.append({"rule": "Keep tickets at 3 legs; at most one 5+ leg ticket a night.",
                      "why": f"On the same predictions 3 props cashed {round(100 * a3['winRate'])}% vs {round(100 * a5['winRate'])}% for 5. "
                             f"Last night 3-leg-or-shorter tickets went {sum(x['won'] for x in n['tickets']['bySize'] if x['legs'] <= 3)}-"
                             f"{sum(x['tickets'] - x['won'] for x in n['tickets']['bySize'] if x['legs'] <= 3)}, longer ones "
                             f"{sum(x['won'] for x in n['tickets']['bySize'] if x['legs'] > 3)}-{sum(x['tickets'] - x['won'] for x in n['tickets']['bySize'] if x['legs'] > 3)}."})
    k = n["killers"][0] if n["killers"] else None
    if k and k["tickets"] >= 3:
        rules.append({"rule": "Cap any one prediction at 3 tickets.",
                      "why": f"{k['label']} sat on {k['tickets']} tickets and was the only miss on {k['killedAlone']}. Spread exposure so one leg cannot sink the card."})
    sr, nr = by_id.get("PASS_RUSH_REC_SAFE"), by_id.get("PASS_RUSH_REC")
    if sr and nr and sr["winRate"] and nr["winRate"] and sr["winRate"] > nr["winRate"]:
        rules.append({"rule": "Put props the model rates under 60% at their SAFE BET line (-15%).",
                      "why": f"Passing + rushing + receiving cashed {round(100 * sr['winRate'])}% at safe lines vs {round(100 * nr['winRate'])}% at posted lines ({sr['combos']} replayed tickets). Lower payout, far fewer dead tickets."})
    js = _jev_summary(n["gameId"])
    if js and js.get("graded"):
        if js["jevRight"] > js["bplRight"]:
            rules.append({"rule": "Drop any leg JEV rates under 50%.", "why": f"JEV out-picked the Big Proppa Line {js['jevRight']}-{js['bplRight']} on {js['graded']} graded reads."})
        else:
            rules.append({"rule": "Use JEV as the tiebreaker, not a veto, until it out-picks the Big Proppa Line.",
                          "why": f"On {js['graded']} graded reads the Big Proppa Line went {js['bplRight']}-{js['graded'] - js['bplRight']}, JEV {js['jevRight']}-{js['graded'] - js['jevRight']}. MY BOO keeps grading both every game."})
    rules.append({"rule": "No touchdown-scorer legs.", "why": "House rule: production legs only."})

    game = _next_primetime()
    cands = []
    if game:
        try:
            import jimmy_bpl
            lake_teams = {game["away"]["abbr"], game["home"]["abbr"]}
            sides = [s for s in jimmy_bpl.cached_sides() if s.get("team") in lake_teams or (s.get("name", "").split(" @ ")[0:1] and any(t in s.get("name", "") for t in lake_teams))]
            slots = [("MONEYLINE", lambda s: s["market"] == "nfl_ml"), ("PASSING", lambda s: s["market"] == "passyds" and s["direction"] == "over"),
                     ("RUSHING", lambda s: s["market"] == "rushyds" and s["direction"] == "over"),
                     ("RECEIVING", lambda s: s["market"] in ("recyds", "recs") and s["direction"] == "over"),
                     ("GAME TOTAL", lambda s: s["market"] == "nfl_total")]
            for name, fn in slots:
                pick = sorted([s for s in sides if fn(s) and not s.get("alt") and (s.get("jevP") is None or s["jevP"] >= 0.5)],
                              key=lambda s: -s["modelP"])[:2]
                for s in pick:
                    cands.append({"slot": name, "leg": f"{s['name']} {s.get('prop') or ''}".strip(), "odds": s["odds"], "modelP": round(s["modelP"], 3),
                                  "jevP": s.get("jevP"), "safeLine": _safe_line(s["line"], s["direction"]) if s["market"] in PROP else None})
        except Exception:
            cands = []
    note = None if cands else ("FanDuel has not posted lines for this game in the lake yet; candidates fill in once they are." if game else None)
    return {"rules": rules, "game": f"{game['away']['abbr']} @ {game['home']['abbr']} · {game['kickoff']['ct']}" if game else None,
            "candidates": cands, "candidatesNote": note}


def _next_week(game_id: str) -> int | None:
    g = next((x for x in data.load("schedule") if x["game_id"] == game_id), None)
    return int(g["week"]) + 1 if g else None


def report(game_id: str | None = None) -> dict:
    game_id = game_id or default_game()
    if not game_id:
        return {"ok": False, "error": "No finished game with MY BOO tickets yet."}
    key = f"rep:{game_id}"
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    n = night(game_id)
    lab = structure_lab()
    try:
        import jev_reports
        corrections = jev_reports.latest().get("corrections") or []
    except Exception:
        corrections = []
    out = {"ok": True, "owner": "MY BOO", "night": n, "lab": lab, "jev": _jev_summary(game_id), "blueprint": blueprint(n, lab),
           "games": games()[:12], "corrections": corrections}
    import boo_grail
    for key, fn in (("grail", lambda: boo_grail.hindsight(game_id)), ("tally", boo_grail.tally),
                    ("contagion", lambda: boo_grail.contagion(n)), ("template", lambda: boo_grail.template(_next_week(game_id))), ("tdPolicy", boo_grail.td_policy)):
        try:
            out[key] = fn()
        except Exception as exc:                      # a failed add-on never takes the report down
            out[key] = {"error": type(exc).__name__}
    try:
        import boo_eval
        out["evaluation"] = boo_eval.evaluate(out)
    except Exception as exc:
        out["evaluation"] = None
    _CACHE[key] = (time.time() + 120, out)
    return out

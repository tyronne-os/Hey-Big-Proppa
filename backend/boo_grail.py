"""
MY BOO's GRAIL DESK -- the time-machine ticket, the win/loss tally, and the template alert.

  hindsight   knowing the final, the three best tickets (5, 4 and 3 legs, $5 each, +30% boost, no leg reused, one
              leg per player per ticket) from the legs that were actually priced. Each leg is tagged SIGNAL (the
              pre-game average already cleared the line, or the TD scorer is an essential player) or LOTTERY.
              Touchdown legs are allowed only for essential players (red_zone.essential_td_ok).
  tally       distinct-ticket and unique-leg win/loss by week and for the season, from the audited ledger
              (voided cross-game tickets excluded)
  template    the GRAIL ALERT: a target-hog receiver (24%+ of team targets, 8+ a game), a volume QB (32+ attempts a
              game) facing a defense that allows 7.5+ yards per target. Each offense scores 0-4, a game scores out of 8,
              7+ trips GRAIL WATCH. The alert shows the back-tested hit rate and never claims the 85% profit zone.
  td policy   essential players vs everyone else: how often each scored in 2026

Everything is measured from the lake; small samples are labelled.
"""
from __future__ import annotations

import csv
import itertools
import math
import time
from collections import Counter, defaultdict

import data
import myboo
import red_zone

BOOST = 0.30
STAKE = 5.0
_CACHE: dict[str, tuple[float, object]] = {}


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _dec(a) -> float:
    a = _f(a)
    return 1.0 if not a else 1 + (a / 100 if a > 0 else 100 / -a)


def _pay(dec: float) -> float:
    return round(STAKE * (1 + (dec - 1) * (1 + BOOST)), 2)


def _cached(key: str, ttl: int, fn):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    val = fn()
    _CACHE[key] = (time.time() + ttl, val)
    return val


def _rows(name: str, season: str = "2026") -> list[dict]:
    with open(data.GOLD / name, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("season") == season and r.get("season_type", "REG") == "REG"]


def _short(full: str) -> str:
    p = (full or "").split()
    return f"{p[0][0]}.{' '.join(p[1:])}" if p else ""


# ---------------------------------------------------------------------------------------------- tally
def tally() -> dict:
    with open(myboo._TICKETS_FILE, newline="") as f:
        tickets = {t["ticket_id"]: t for t in csv.DictReader(f)}
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = list(csv.DictReader(f))
    by_t: dict[str, list[dict]] = defaultdict(list)
    for l in legs:
        by_t[l["ticket_id"]].append(l)
    weeks: dict[str, dict] = defaultdict(lambda: {"tw": 0, "tl": 0, "lw": 0, "ll": 0})
    seen: set = set()
    for tid, t in tickets.items():
        if t["status"] == "PUSH_VOID":
            continue
        ls = by_t.get(tid, [])
        out = "L" if any(x["status"] == "MISS" for x in ls) else "W" if ls and all(x["status"] == "HIT" for x in ls) else None
        if not out:
            continue
        fp = (t["week"], tuple(sorted((x["player_name"], x["market"], x["direction"], x["line"]) for x in ls)))
        if fp in seen:
            continue
        seen.add(fp)
        weeks[t["week"]]["tw" if out == "W" else "tl"] += 1
    seen = set()
    for tid, t in tickets.items():
        if t["status"] == "PUSH_VOID":
            continue
        for x in by_t.get(tid, []):
            if x["status"] not in ("HIT", "MISS"):
                continue
            k = (t["week"], x["player_name"], x["market"], x["direction"], x["line"], x["game_id"])
            if k in seen:
                continue
            seen.add(k)
            weeks[t["week"]]["lw" if x["status"] == "HIT" else "ll"] += 1
    rows = []
    for wk in sorted(weeks, key=int):
        w = weeks[wk]
        rows.append({"week": int(wk), **w, "ticketPct": round(100 * w["tw"] / max(1, w["tw"] + w["tl"])),
                     "legPct": round(100 * w["lw"] / max(1, w["lw"] + w["ll"]))})
    tot = {k: sum(r[k] for r in rows) for k in ("tw", "tl", "lw", "ll")}
    tot["ticketPct"] = round(100 * tot["tw"] / max(1, tot["tw"] + tot["tl"]))
    tot["legPct"] = round(100 * tot["lw"] / max(1, tot["lw"] + tot["ll"]))
    return {"weeks": rows, "season": tot,
            "note": "Distinct tickets (duplicates collapsed, voided cross-game tickets excluded); legs count each unique prediction once."}


# ---------------------------------------------------------------------------------------------- hindsight
def _td_prices(game_id: str) -> dict[str, int]:
    """Best anytime-TD price per player for this game from the newest Rotowire pull that has both teams."""
    sched = next((g for g in data.load("schedule") if g["game_id"] == game_id), None)
    if not sched:
        return {}
    teams = {sched["home_team"], sched["away_team"]}
    alias = {"LA": "LAR", "LAR": "LA"}
    teams |= {alias[t] for t in teams if t in alias}
    best: dict[str, int] = {}
    latest = ""
    try:
        with open(data.GOLD / "prop_line_rotowire.csv", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["market_slug"] == "anytd" and r["team"] in teams
                    and r["opponent"].lstrip("@") in teams]
    except OSError:
        return {}
    if rows:
        latest = max(r["pull_id"] for r in rows)
    for r in rows:
        if r["pull_id"] != latest:
            continue
        try:
            v = int(float(r["moneyline_american"]))
        except ValueError:
            continue
        if r["player_name"] not in best or v > best[r["player_name"]]:
            best[r["player_name"]] = v
    return best


def hindsight(game_id: str) -> dict | None:
    def build():
        import slip_alerts
        with open(myboo._TICKETS_FILE, newline="") as f:
            tickets = {t["ticket_id"]: t for t in csv.DictReader(f)}
        with open(myboo._LEGS_FILE, newline="") as f:
            legs = [l for l in csv.DictReader(f) if l["game_id"] == game_id and tickets[l["ticket_id"]]["status"] != "PUSH_VOID"]
        if not legs:
            return None
        pool: dict[tuple, dict] = {}
        for l in legs:
            if l["status"] != "HIT" or l["market"] in ("nfl_total", "nfl_ml", "nfl_spread"):
                continue
            k = (l["player_name"], l["market"], l["direction"], l["line"])
            pool.setdefault(k, {"player": l["player_name"], "team": l["team"], "market": l["market"], "dirn": l["direction"],
                                "line": _f(l["line"]), "odds": int(_f(l["odds"], -110)), "actual": _f(l["actual_value"])})
        # touchdown legs: only essential players who actually scored, at the best posted anytime-TD price
        tdp = _td_prices(game_id)
        box = slip_alerts.final_box(game_id)
        if box:
            for (nm, team), st in box["players"].items():
                if st.get("rushtd", 0) + st.get("rectd", 0) < 1:
                    continue
                full = next((n for n in tdp if n.lower() == nm), None)
                if full and red_zone.essential_td_ok(full, team):
                    pool[(full, "anytd", "yes", "0.5")] = {"player": full, "team": team, "market": "anytd", "dirn": "yes", "line": 0.5,
                                                          "odds": tdp[full], "actual": st["rushtd"] + st["rectd"]}
        items = sorted(pool.values(), key=lambda x: -_dec(x["odds"]))

        def combos(avail, n):
            out = []
            for c in itertools.combinations(avail[:16], n):
                if len({x["player"] for x in c}) == n:
                    out.append((math.prod(_dec(x["odds"]) for x in c), c))
            out.sort(key=lambda x: -x[0])
            return out[:6]

        best, sol = 0.0, None
        for a in combos(items, 5):
            r1 = [x for x in items if x not in a[1]]
            for b in combos(r1, 4):
                r2 = [x for x in r1 if x not in b[1]]
                for c in combos(r2, 3)[:2]:
                    s = sum(1 + (d[0] - 1) * (1 + BOOST) for d in (a, b, c))
                    if s > best:
                        best, sol = s, (a, b, c)
        if not sol:
            return None
        ids = {}
        for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")):
            if u["season"] == "2026":
                ids[(u["player_name"], u["team"])] = u["player_id"]
        wk = {"recyds": ("player_receiving_week.csv", "receiving_yards"), "rushyds": ("player_rushing_week.csv", "rushing_yards"),
              "passyds": ("player_passing_week.csv", "passing_yards"), "recs": ("player_receiving_week.csv", "receptions")}
        cache: dict[str, list[dict]] = {}
        sched = next((g for g in data.load("schedule") if g["game_id"] == game_id), {})
        wnum = int(sched.get("week") or 99)

        def sign(x):
            if x["market"] == "anytd":
                return ("SIGNAL", "essential starter: QB1 or top-3 usage")
            if x["market"] in wk:
                fn, col = wk[x["market"]]
                rows = cache.setdefault(fn, _rows(fn))
                tm = {"LAR": "LA"}.get(x["team"], x["team"])
                pid = ids.get((_short(x["player"]), tm))
                v = [_f(r[col]) for r in rows if r["player_id"] == pid and int(r["week"]) < wnum]
                if v:
                    avg = sum(v) / len(v)
                    cleared = avg > x["line"] if x["dirn"] == "over" else avg < x["line"]
                    return ("SIGNAL" if cleared else "LOTTERY", f"averaged {avg:.1f} over {len(v)} games vs a {x['line']:g} line")
            return ("LOTTERY", "no pre-game read on this one")

        tix = []
        for i, (dec, c) in enumerate(sol):
            lg = []
            for x in c:
                kind, why = sign(x)
                lg.append({**x, "kind": kind, "sign": why})
            tix.append({"name": ["5-LEG GRAIL", "4-LEG", "3-LEG"][i], "decimal": round(dec, 2), "pays": _pay(dec),
                        "signals": sum(1 for x in lg if x["kind"] == "SIGNAL"), "legs": lg})
        return {"stake": STAKE, "boost": BOOST, "tdFromBox": bool(box), "tickets": tix,
                "note": "Hindsight only: prices are the posted board and best anytime-TD prices; TD legs only for essential players."}

    return _cached(f"hind:{game_id}", 600, build)


# ---------------------------------------------------------------------------------------------- template
def template(week: int | None = None) -> dict:
    def build():
        U = {u["player_id"]: u["player_name"] for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")) if u["season"] == "2026"}
        rec, pas = _rows("player_receiving_week.csv"), _rows("player_passing_week.csv")
        y, t = defaultdict(float), defaultdict(float)
        tt, ptg, wk = defaultdict(float), defaultdict(lambda: defaultdict(float)), defaultdict(set)
        for r in rec:
            y[r["opponent_team"]] += _f(r["receiving_yards"])
            t[r["opponent_team"]] += _f(r["targets"])
            tt[r["team"]] += _f(r["targets"])
            ptg[r["team"]][r["player_id"]] += _f(r["targets"])
            wk[r["team"]].add(r["week"])
        ypt = {k: y[k] / t[k] for k in t if t[k] > 0}
        att = defaultdict(float)
        for r in pas:
            att[r["team"]] += _f(r["attempts"])
        side = {}
        for tm in ptg:
            n = len(wk[tm]) or 1
            pid, tg = max(ptg[tm].items(), key=lambda x: x[1])
            side[tm] = {"hog": U.get(pid, pid), "share": round(tg / tt[tm], 3), "tg": round(tg / n, 1), "att": round(att[tm] / n, 1)}
        sched = [g for g in data.load("schedule") if g["season"] == "2026" and g["game_type"] == "REG"]
        wnum = week or min((int(g["week"]) for g in sched if not g.get("home_score")), default=None)
        games = []
        for g in sched:
            if int(g["week"]) != wnum:
                continue
            a, h = g["away_team"], g["home_team"]
            parts, score = [], 0
            for off, de in ((a, h), (h, a)):
                s = side.get(off)
                if not s:
                    continue
                checks = [s["share"] >= 0.24, s["tg"] >= 8, s["att"] >= 32, ypt.get(de, 0) >= 7.5]
                score += sum(checks)
                parts.append({"team": off, **s, "oppYpt": round(ypt.get(de, 0), 2), "checks": sum(checks)})
            games.append({"game": f"{a} @ {h}", "gameId": g["game_id"], "day": g.get("weekday"), "score": score, "sides": parts,
                          "alert": score >= 7})
        games.sort(key=lambda x: (-x["score"], x["gameId"]))
        return {"week": wnum, "games": games, "rule": "hog 24%+ of targets and 8+ a game, QB 32+ attempts, defense 7.5+ yds per target; 7 of 8 trips GRAIL WATCH",
                "backtest": {"games": 115, "yds70Leaky": 0.67, "yds70All": 0.54, "recs70Leaky": 0.65,
                             "note": "Hog receiving yards over 70% of his own average, weeks 3-5, pre-game data only. Nothing reached 85%, so the alert never claims the profit zone."}}

    return _cached(f"tmpl:{week}", 600, build)


# ---------------------------------------------------------------------------------------------- TD policy evidence
def td_policy() -> dict:
    def build():
        td = [r for r in csv.DictReader(open(data.GOLD / "td_log.csv", newline="")) if r["season"] == "2026" and r["is_offensive_td"] == "True"]
        sc = Counter((r["scorer_player_name"], r["scoring_team"], r["game_id"]) for r in td)
        U = {u["player_id"]: u for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")) if u["season"] == "2026"}
        ess = hit_e = oth = hit_o = 0
        for r in _rows("player_scrimmage_week.csv"):
            u = U.get(r["player_id"])
            if not u or _f(r["touches"]) < 5:
                continue
            h = sc.get((u["player_name"], r["team"], r["game_id"]), 0) > 0
            if red_zone.essential_td_ok(u["player_name"], u["team"]):
                ess += 1
                hit_e += h
            else:
                oth += 1
                hit_o += h
        return {"rule": "Touchdown legs allowed only for essential players: the QB1, or a starter who is top 3 on his team in usage, 3+ games.",
                "essential": {"games": ess, "rate": round(hit_e / max(1, ess), 3)}, "others": {"games": oth, "rate": round(hit_o / max(1, oth), 3)}}

    return _cached("tdpolicy", 3600, build)


# ---------------------------------------------------------------------------------------------- contagion hero
def contagion(night: dict) -> dict | None:
    """28 Days Later outbreak report: patient zero (the prediction that wiped out the most tickets) and the infected."""
    ks = night.get("killers") or []
    if not ks:
        return None
    dim = data.player_dimension()
    by_name = {d["name"]: pid for pid, d in dim.items()}
    usage = {}
    for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")):
        if u["season"] == "2026":
            usage[(u["player_name"], u["team"])] = u

    def person(label: str) -> dict:
        name = label.split(" over ")[0].split(" under ")[0]
        pid = by_name.get(name)
        d = dim.get(pid, {}) if pid else {}
        u = usage.get((_short(name), {"LAR": "LA"}.get(d.get("team", ""), d.get("team", ""))), {})
        return {"name": name, "photoUrl": data.photo_url(pid) if pid else None, "team": d.get("team"), "pos": d.get("position"),
                "depth": u.get("depth_rank"), "usageRank": u.get("usage_rank_on_team")}

    z = ks[0]
    zp = person(z["label"])
    infected, seen = [], {zp["name"]}
    for k in ks[1:]:
        p = person(k["label"])
        if p["name"] in seen:
            continue
        seen.add(p["name"])
        infected.append({**p, "label": k["label"], "tickets": k["tickets"], "actual": k["actual"], "line": k["line"]})
        if len(infected) == 5:
            break
    multi = Counter()
    for k in ks:
        multi[person(k["label"])["name"]] += k["tickets"]
    dup_name, dup_n = next(((n, c) for n, c in multi.most_common() if sum(1 for k in ks if k["label"].startswith(n)) > 1), (None, 0))
    T = night["tickets"]
    small = [s for s in T["bySize"] if s["legs"] <= 3]
    big = [s for s in T["bySize"] if s["legs"] > 3]
    sw, st = sum(s["won"] for s in small), sum(s["tickets"] for s in small)
    bw, bt = sum(s["won"] for s in big), sum(s["tickets"] for s in big)
    role = f"the WR{zp['depth']}" if zp.get("pos") == "WR" and zp.get("depth") else f"a {zp.get('pos') or 'player'} ranked {zp.get('usageRank') or '?'} on his team in usage"
    paras = [
        f"Every outbreak starts with one idiot who thought a bite was a hickey. Ours was {zp['name']}, {role}, who we somehow decided was structural steel for {z['tickets']} tickets. "
        f"The ask was {z['label'].split(zp['name'])[-1].strip()}. He finished with {num(z['actual'])}. Patient Zero was the only dead leg on {z['killedAlone']} tickets that were otherwise perfectly healthy. "
        f"That's the opening scene where the monkey gets out of the lab, except the lab is us, and we're the monkey. 😡",
    ]
    if dup_name:
        paras.append(f"Then it jumped hosts. {dup_name} came down with it in more than one prop line, {dup_n} ticket slots in total, and neither line survived. "
                     + (f"{infected[0]['name']} went down on {infected[0]['tickets']} tickets at {num(infected[0]['actual'])} against a {num(infected[0]['line'])} line. " if infected and infected[0]["name"] != dup_name else "")
                     + "Everyone else coughed on the way to the finish line.")
    elif infected:
        paras.append(f"Then it jumped hosts. {infected[0]['name']} went down on {infected[0]['tickets']} tickets at {num(infected[0]['actual'])} against a {num(infected[0]['line'])} line, and the rest coughed on the way to the finish line.")
    paras.append(f"Notice what the infected have in common: we stacked the same few props on card after card, so one bad afternoon from one guy turns the whole herd. "
                 f"Day 28, the survivors are the short tickets: 3 legs or fewer went {sw} for {st}, while 4 or more went {bw} for {bt}. "
                 f"Quarantine rules for next time: one player, one prop, three legs, and nobody who isn't a target in the first place. 🧟")
    return {"kicker": f"OUTBREAK REPORT · {night['game']}", "headline": f"{z['tickets']} TICKETS LATER…", "sub": "THE INFECTION SPREADS",
            "zero": {**zp, "label": z["label"], "tickets": z["tickets"], "alone": z["killedAlone"], "actual": z["actual"], "line": z["line"]},
            "infected": infected, "commentary": paras}


def num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "?"
    return str(int(f)) if f == int(f) else f"{f:.1f}"

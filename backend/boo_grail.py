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
                return ("SIGNAL", "essential starter: QB1 or top-3 usage", None, 0)
            if x["market"] in wk:
                fn, col = wk[x["market"]]
                rows = cache.setdefault(fn, _rows(fn))
                tm = {"LAR": "LA"}.get(x["team"], x["team"])
                pid = ids.get((_short(x["player"]), tm))
                v = [_f(r[col]) for r in rows if r["player_id"] == pid and int(r["week"]) < wnum]
                if v:
                    avg = sum(v) / len(v)
                    cleared = avg > x["line"] if x["dirn"] == "over" else avg < x["line"]
                    return ("SIGNAL" if cleared else "LOTTERY", f"averaged {avg:.1f} over {len(v)} games vs a {x['line']:g} line", round(avg, 1), len(v))
            return ("LOTTERY", "no pre-game read on this one", None, 0)

        tix = []
        for i, (dec, c) in enumerate(sol):
            lg = []
            for x in c:
                kind, why, avg, gms = sign(x)
                lg.append({**x, "kind": kind, "sign": why, "avg": avg, "games": gms})
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


# ---------------------------------------------------------------------------------------------- prop of the day
TEAM_COLOR = {"ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D", "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14",
              "CLE": "#311D00", "DAL": "#041E42", "DEN": "#FB4F14", "DET": "#0076B6", "GB": "#203731", "HOU": "#03202F", "IND": "#002C5F",
              "JAX": "#006778", "KC": "#E31837", "LV": "#000000", "LAC": "#0080C6", "LA": "#003594", "MIA": "#008E97", "MIN": "#4F2683",
              "NE": "#002244", "NO": "#D3BC8D", "NYG": "#0B2265", "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SEA": "#002244",
              "SF": "#AA0000", "TB": "#D50A0A", "TEN": "#0C2340", "WAS": "#5A1414"}
PHOTO_TTL = 900


def _am(dec: float) -> int:
    return round((dec - 1) * 100) if dec >= 2 else -round(100 / (dec - 1))


def _price(p: float) -> int:
    """Estimated American price for a probability, with a 10% house edge built in."""
    return _am(1 / (p * 1.10))


def _card(game: dict, label: str, n_td: int, boost: float) -> dict | None:
    """One slip card for one game: three yardage legs plus the highest-probability anytime TDs (essential players only)."""
    away, home = game["away_team"], game["home_team"]
    dim = data.player_dimension()
    rec, pas, rus = (_rows(f) for f in ("player_receiving_week.csv", "player_passing_week.csv", "player_rushing_week.csv"))
    yds, tg = defaultdict(float), defaultdict(float)
    for r in rec:
        yds[r["opponent_team"]] += _f(r["receiving_yards"])
        tg[r["opponent_team"]] += _f(r["targets"])
    ypt = {k: yds[k] / tg[k] for k in tg if tg[k]}
    td = [r for r in csv.DictReader(open(data.GOLD / "td_log.csv", newline="")) if r["season"] == "2026" and r["is_offensive_td"] == "True"]

    def top(rows, team, col):
        c = Counter()
        for r in rows:
            if r["team"] == team:
                c[r["player_id"]] += _f(r[col])
        return c.most_common(1)[0][0] if c else None

    def avg(rows, pid, col):
        v = [_f(r[col]) for r in rows if r["player_id"] == pid]
        return (sum(v) / len(v), len(v)) if v else (0.0, 0)

    cands = []
    for team, opp in ((away, home), (home, away)):
        leaky = ypt.get(opp, 0) >= 7.5
        tt = sum(_f(r["targets"]) for r in rec if r["team"] == team)
        pid = top(rec, team, "targets")
        if pid:
            a, _n = avg(rec, pid, "receiving_yards")
            share = sum(_f(r["targets"]) for r in rec if r["team"] == team and r["player_id"] == pid) / max(tt, 1)
            cands.append({"pid": pid, "team": team, "mkt": "Rec Yds", "line": math.floor(a * 0.7 * 2) / 2 + 0.5, "p": 0.67 if leaky else 0.54,
                          "note": f"{share * 100:.0f}% of {team} targets · {opp} allow {ypt.get(opp, 0):.1f} yds/tgt"})
        pid = top(pas, team, "attempts")
        if pid:
            a, n = avg(pas, pid, "passing_yards")
            cands.append({"pid": pid, "team": team, "mkt": "Pass Yds", "line": math.floor(a * 0.8 / 5) * 5 + 0.5, "p": 0.66,
                          "note": f"averages {a:.0f} pass yds in {n} games"})
        pid = top(rus, team, "carries")
        if pid:
            a, _n = avg(rus, pid, "rushing_yards")
            cands.append({"pid": pid, "team": team, "mkt": "Rush Yds", "line": math.floor(a * 0.7 * 2) / 2 + 0.5, "p": 0.62,
                          "note": f"lead back, averages {a:.0f} rush yds"})
    picks, used = [], set()
    for c in sorted(cands, key=lambda x: -x["p"]):
        if c["pid"] in used or any(p["mkt"] == c["mkt"] for p in picks) or sum(1 for p in picks if p["team"] == c["team"]) >= 2:
            continue
        picks.append(c)
        used.add(c["pid"])
        if len(picks) == 3:
            break
    scorers = []
    for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")):
        team = {"LAR": "LA"}.get(u["team"], u["team"])
        if u["season"] != "2026" or team not in (away, home) or u["player_id"] in used or not red_zone.essential_td_ok(u["player_name"], team):
            continue
        try:
            g = int(u["games"])
        except ValueError:
            continue
        tds = sum(1 for r in td if r["scorer_player_name"] == u["player_name"] and r["scoring_team"] == team)
        scorers.append({"pid": u["player_id"], "team": team, "mkt": "Anytime TD", "line": None, "p": max(0.2, min(0.65, (tds + 0.8) / (g + 1.6))),
                        "note": f"essential {u['position']} · {tds} offensive TDs in {g} games"})
    scorers.sort(key=lambda x: -x["p"])
    picks += scorers[:n_td]
    if not picks:
        return None
    legs, dec = [], 1.0
    for c in picks:
        d = dim.get(c["pid"], {})
        odds = _price(c["p"])
        dec *= _dec(odds)
        legs.append({"name": d.get("name", c["pid"]), "team": c["team"], "color": TEAM_COLOR.get(c["team"], "#241e2c"),
                     "prop": c["mkt"] if c["line"] is None else f"{c['mkt']} {math.ceil(c['line'])}+", "note": c["note"], "odds": odds,
                     "p": round(c["p"], 2), "photoUrl": data.photo_url(c["pid"]), "photoFallback": data._enhance_cloudinary(data._headshots().get(c["pid"]))})
    stake = 10.0
    profit = stake * (dec - 1)
    boosted = profit * (1 + boost)
    return {"ok": True, "label": label, "game": f"{away} @ {home}", "date": game.get("gameday"), "legs": legs, "boost": int(round(boost * 100)),
            "parlayOdds": _am(dec), "stake": stake, "profit": round(profit, 2), "boostedProfit": round(boosted, 2), "pays": round(stake + boosted, 2),
            "hitChance": round(math.prod(l["p"] for l in legs), 3), "estimated": True,
            "footer": "ESTIMATED ODDS · LINES POST THIS WEEK · MODEL BUILT"}


CARD_BOOST = 0.50
DAYTAG = {"Thursday": "THUR", "Friday": "FRI", "Saturday": "SAT", "Sunday": "SUN", "Monday": "MON"}


def props_of_the_day() -> dict:
    """One slip card per upcoming game day (Thursday, Sunday, Monday...), each the best ticket for that day's best game.
    Sunday gets two touchdown legs and the game the Grail template likes most; the +50% profit boost applies to all."""
    def build():
        import datetime as dt
        today = dt.date.today().isoformat()
        sched = [g for g in data.load("schedule") if g.get("season") == "2026" and g.get("game_type") == "REG" and (g.get("gameday") or "") >= today]
        if not sched:
            return {"ok": False, "days": []}
        week = min(int(g["week"]) for g in sched)
        wk = [g for g in sched if int(g["week"]) == week]
        try:
            tmpl = {x["gameId"]: x["score"] for x in template(week)["games"]}
        except Exception:
            tmpl = {}
        days = []
        for day in sorted({g["gameday"] for g in wk}):
            games = [g for g in wk if g["gameday"] == day]
            game = max(games, key=lambda g: (tmpl.get(g["game_id"], 0), g.get("gametime") or ""))
            wd = game.get("weekday", "")
            tag = DAYTAG.get(wd, wd.upper()[:3])
            label = f"{tag} · WEEK {week}"
            card = _card(game, label, 2 if wd == "Sunday" else 1, CARD_BOOST)
            if card:
                card["day"] = tag
                days.append(card)
        return {"ok": bool(days), "week": week, "days": days}

    return _cached("potd-days", PHOTO_TTL, build)


def prop_of_the_day() -> dict:
    """Back-compat: the first upcoming day's card."""
    d = props_of_the_day()
    return d["days"][0] if d.get("days") else {"ok": False}


# ---------------------------------------------------------------------------------------------- knowledge graph
def _short_leg(label: str) -> str:
    out = label
    for a, b in ((" over ", " o"), (" under ", " u"), ("receptions", "rec"), ("rec yds", "rec yds"), ("rush yds", "rush"), ("pass yds", "pass"),
                 ("kicking pts", "kick")):
        out = out.replace(a, b)
    return out


def knowledge_graph(night: dict, contagion: dict | None, template: dict | None, blueprint: dict | None) -> dict | None:
    """How this game's misses turn into the next game's tickets, as a graph: misses -> what we learned -> rules -> next targets.
    Every node and edge is derived from the measured report, so it rebuilds for every game."""
    if not night or not contagion:
        return None
    nodes: list[dict] = []
    edges: list[list[str]] = []
    persons = [contagion["zero"]] + contagion["infected"]
    ks = night.get("killers") or []
    seen = set()
    miss_ids: dict[str, str] = {}
    for p in persons:
        if p["name"] in seen or len(seen) >= 5:
            continue
        seen.add(p["name"])
        nid = f"m{len(miss_ids)}"
        miss_ids[p["name"]] = nid
        nodes.append({"id": nid, "label": _short_leg(p.get("label") or p["name"]), "layer": 0, "weight": p.get("tickets", 1), "kind": "miss"})
    T = night["tickets"]
    big = [s for s in T["bySize"] if s["legs"] > 3]
    small = [s for s in T["bySize"] if s["legs"] <= 3]
    bw, bt = sum(s["won"] for s in big), sum(s["tickets"] for s in big)
    sw, st = sum(s["won"] for s in small), sum(s["tickets"] for s in small)

    def lesson(lid, label, sources):
        nodes.append({"id": lid, "label": label, "layer": 1, "weight": 1, "kind": "lesson"})
        for s in sources:
            edges.append([s, lid])

    low_depth = [miss_ids[p["name"]] for p in persons if p["name"] in miss_ids and str(p.get("depth") or "0").isdigit() and int(p["depth"]) >= 3]
    low_use = [miss_ids[p["name"]] for p in persons if p["name"] in miss_ids and str(p.get("usageRank") or "0").isdigit() and int(p["usageRank"]) >= 5]
    by_name: dict[str, int] = {}
    for k in ks:
        nm = k["label"].split(" over ")[0].split(" under ")[0]
        by_name[nm] = by_name.get(nm, 0) + 1
    dups = [miss_ids[n] for n, c in by_name.items() if c > 1 and n in miss_ids]
    top_id = next(iter(miss_ids.values()), None)
    if low_depth:
        lesson("l_depth", "Low on the depth chart", low_depth)
    if low_use and set(low_use) - set(low_depth):
        lesson("l_use", "Low-usage legs", low_use)
    if dups or top_id:
        lesson("l_dup", "Same prop on many tickets", dups or [top_id])
    if bt:
        nodes.append({"id": "m_long", "label": f"4+ leg tickets ({bw}/{bt})", "layer": 0, "weight": bt, "kind": "miss"})
        lesson("l_size", f"Long tickets die ({sw}/{st} short vs {bw}/{bt} long)", ["m_long"])
    rules = [("r_one", "1 player = 1 prop", ["l_dup"]), ("r_target", "Target-driven legs only", ["l_depth", "l_use"]),
             ("r_three", "3 legs max", ["l_size"]), ("r_core", "Total + 2 props core", ["l_size", "l_dup"])]
    ids = {n["id"] for n in nodes}
    for rid, label, srcs in rules:
        srcs = [s for s in srcs if s in ids]
        if srcs:
            nodes.append({"id": rid, "label": label, "layer": 2, "weight": 1, "kind": "rule"})
            for s in srcs:
                edges.append([s, rid])
    targets = []
    for g in ((template or {}).get("games") or [])[:3]:
        best = max(g["sides"], key=lambda s: s["share"] * s["oppYpt"], default=None)
        if best:
            targets.append((g["game"], best))
    for i, (game, s) in enumerate(targets):
        tid = f"t{i}"
        nodes.append({"id": tid, "label": f"{s['hog']} · {round(s['share'] * 100)}% of {s['team']} targets · {game}", "layer": 3, "weight": 1, "kind": "target"})
        for rid in ("r_target", "r_core"):
            if any(n["id"] == rid for n in nodes):
                edges.append([rid, tid])
    return {"nodes": nodes, "edges": edges}

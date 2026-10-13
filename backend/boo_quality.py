"""
THE QUALITY CARD -- Jimmy builds the primetime page under MY BOO's orders, JEV breaks the ties.

Quality, not quantity: five tickets, 3 and 5 legs, every one obeying the rules MY BOO wrote from her own post-game
reports (boo_postgame / boo_eval). Plain code, no LLM:

  ESSENTIAL ONLY     every player leg belongs to a player essential to his offense (QB1, or a starter top-3 in usage)
  ONE PLAYER, ONE PROP   a player appears with one market across the whole card (never the same guy's yards and catches)
  EXPOSURE CAP       no prediction on more than 3 tickets, so one bad afternoon cannot sink the card
  SHORT TICKETS      four 3-leg tickets and one 5-leg ticket (3-or-fewer went 17-5 on Monday, 4+ went 2-18)
  CORE SHAPE         game total + 2 props leads the card (the best-supported shape in her structure lab)
  SAFE LINES         a posted prop the model rates under 60% moves to its alternate rung near the line cut 15%
  TD RULE            touchdown legs only for essential players, highest scoring rate first
  JEV                JEV's read is the tiebreaker between legs the Big Proppa Line rates the same

Legs use FanDuel prices from the lake when they are posted. Until then the leg is model-built: the line is set from
the player's own 2026 numbers and the price is ESTIMATED (oddsEstimated: True), and the page says so.
"""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict

import data
import red_zone

EXPOSURE_CAP = 3
SAFE_CUT = 0.85
HOUSE = 1.10


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _price(p: float) -> int:
    d = 1 / max(0.05, min(0.95, p * HOUSE))
    return round((d - 1) * 100) if d >= 2 else -round(100 / (d - 1))


def _abbr(full: str) -> str:
    try:
        for r in csv.DictReader(open(data.GOLD / "team_abbr_map.csv", newline="")):
            if r["full_name"] == full:
                return r["abbr_lake"]
    except OSError:
        pass
    return full


def _rows(name: str) -> list[dict]:
    with open(data.GOLD / name, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("season") == "2026" and r.get("season_type", "REG") == "REG"]


def _short(full: str) -> str:
    p = (full or "").split()
    return f"{p[0][0]}.{' '.join(p[1:])}" if p else ""


LABEL = {"recyds": "rec yds", "rushyds": "rush yds", "passyds": "pass yds", "recs": "receptions"}


def _real_props(game_id: str) -> list[dict]:
    """Posted FanDuel props for this game, essential players only, safe-lined when the model is under 60%."""
    import throwdown
    from jimmy_bpl import cached_sides
    pool = [l for l in throwdown._pool(game_id) if red_zone.essential_td_ok(l["name"], l["team"])]
    alts = [s for s in cached_sides() if s.get("alt") and s.get("direction") == "over"]
    out = []
    for l in pool:
        leg = {**l, "oddsEstimated": False, "rule": "posted line"}
        if l["probability"] < 0.60:
            want = l["line"] * SAFE_CUT
            rungs = [s for s in alts if s["playerId"] == l["playerId"] and s["market"] == l["market"] and s["line"] <= want]
            if rungs:
                r = max(rungs, key=lambda s: s["line"])
                leg.update(line=r["line"], odds=r["odds"], probability=round(r["modelP"], 4), l5=round(r["modelP"], 4),
                           prop=f"Over {r['line']:g} {LABEL.get(l['market'], l['market'])}", rule="safe line (posted line cut 15%)")
            else:
                leg.update(rule=f"model {round(l['probability'] * 100)}%: take the {math.floor(want * 2) / 2:g} rung in the app if offered")
        out.append(leg)
    return out


def _model_props(game: dict) -> list[dict]:
    """Model-built legs from the lake when the book has not posted props: hog yardage, QB yards, lead-back yards."""
    away, home = game["away_team"], game["home_team"]
    dim = data.player_dimension()
    rec, pas, rus = _rows("player_receiving_week.csv"), _rows("player_passing_week.csv"), _rows("player_rushing_week.csv")
    yds, tg = defaultdict(float), defaultdict(float)
    for r in rec:
        yds[r["opponent_team"]] += _f(r["receiving_yards"])
        tg[r["opponent_team"]] += _f(r["targets"])
    ypt = {k: yds[k] / tg[k] for k in tg if tg[k]}
    out = []

    def ranked(rows, team, col, n):
        c = Counter()
        for r in rows:
            if r["team"] == team:
                c[r["player_id"]] += _f(r[col])
        return [pid for pid, _ in c.most_common(n)]

    def avg(rows, pid, col):
        v = [_f(r[col]) for r in rows if r["player_id"] == pid]
        return (sum(v) / len(v), len(v)) if v else (0.0, 0)

    def leg(pid, team, market, line, p, note):
        d = dim.get(pid, {})
        name = d.get("name", pid)
        return {"playerId": pid, "name": name, "team": team, "pos": d.get("position", ""), "market": market, "line": line,
                "direction": "over", "prop": f"Over {line:g} {LABEL[market]}", "odds": _price(p), "probability": round(p, 4),
                "l5": round(p, 4), "photoUrl": data.photo_url(pid), "oddsEstimated": True, "jevP": None,
                "rule": note}

    for team, opp in ((away, home), (home, away)):
        leaky = ypt.get(opp, 0) >= 7.5
        tt = sum(_f(r["targets"]) for r in rec if r["team"] == team) or 1
        for i, pid in enumerate(ranked(rec, team, "targets", 3)):
            a, n = avg(rec, pid, "receiving_yards")
            c, _ = avg(rec, pid, "receptions")
            share = sum(_f(r["targets"]) for r in rec if r["team"] == team and r["player_id"] == pid) / tt
            if not a or not red_zone.essential_td_ok(dim.get(pid, {}).get("name", ""), team):
                continue
            why = f"{share * 100:.0f}% of {team} targets; {opp} allow {ypt.get(opp, 0):.1f} yds/target"
            if i == 0:   # the target hog: yardage at 70% of his own average (67% hit vs leaky defenses in her backtest)
                out.append(leg(pid, team, "recyds", math.floor(a * 0.7 * 2) / 2 + 0.5, 0.67 if leaky else 0.54,
                               f"{why}; line at 70% of his {a:.0f}-yard average"))
            if c >= 2.5:  # every top-3 target earner: receptions at 70% of his average (65% hit vs leaky defenses)
                out.append(leg(pid, team, "recs", max(1.5, math.floor(c * 0.7) + 0.5), (0.65 if leaky else 0.55) - 0.02 * i,
                               f"{why}; catches at 70% of his {c:.1f} a game"))
        for pid in ranked(pas, team, "attempts", 1):
            a, n = avg(pas, pid, "passing_yards")
            if a:
                out.append(leg(pid, team, "passyds", math.floor(a * 0.8 / 5) * 5 + 0.5, 0.66, f"QB1, line at 80% of his {a:.0f}-yard average"))
        for pid in ranked(rus, team, "carries", 1):
            a, n = avg(rus, pid, "rushing_yards")
            if a and red_zone.essential_td_ok(dim.get(pid, {}).get("name", ""), team):
                out.append(leg(pid, team, "rushyds", math.floor(a * 0.7 * 2) / 2 + 0.5, 0.62, f"lead back, line at 70% of his {a:.0f}-yard average"))
    return out


def _td_pool(game: dict, game_id: str) -> list[dict]:
    """Essential players only, ranked by their 2026 scoring rate (smoothed). Posted anytime-TD price when the lake has it."""
    import throwdown
    away, home = game["away_team"], game["home_team"]
    posted = {}
    try:
        for l in throwdown._td_legs(game_id, "anytd"):
            posted[data.normalize_name(l["name"])] = l["odds"]
    except Exception:
        pass
    td = [r for r in csv.DictReader(open(data.GOLD / "td_log.csv", newline="")) if r["season"] == "2026" and r["is_offensive_td"] == "True"]
    dim = data.player_dimension()
    out = []
    for u in csv.DictReader(open(data.GOLD / "player_usage.csv", newline="")):
        team = {"LAR": "LA"}.get(u["team"], u["team"])
        if u["season"] != "2026" or team not in (away, home) or not red_zone.essential_td_ok(u["player_name"], team):
            continue
        try:
            g = int(u["games"])
        except ValueError:
            continue
        n = sum(1 for r in td if r["scorer_player_name"] == u["player_name"] and r["scoring_team"] == team)
        p = max(0.2, min(0.65, (n + 0.8) / (g + 1.6)))
        name = dim.get(u["player_id"], {}).get("name", u["player_name"])
        odds = posted.get(data.normalize_name(name))
        out.append({"playerId": u["player_id"], "name": name, "team": team, "pos": u["position"], "market": "anytd", "line": 0.5,
                    "direction": "over", "prop": "Anytime TD scorer", "odds": odds if odds else _price(p), "probability": round(p, 4),
                    "l5": round(p, 4), "photoUrl": data.photo_url(u["player_id"]), "oddsEstimated": odds is None, "jevP": None,
                    "rule": f"essential {u['position']}, {n} offensive TDs in {g} games"})
    return sorted(out, key=lambda l: -l["probability"])


def _game_legs(game_id: str) -> tuple[list[dict], list[dict]]:
    """The game total (side the model likes) and the moneyline (model favourite), at posted prices."""
    from jimmy_bpl import cached_sides
    sides = [s for s in cached_sides() if s.get("gameId") == game_id]
    tot = [s for s in sides if s["market"] == "nfl_total"]
    ml = [s for s in sides if s["market"] == "nfl_ml"]
    out_t, out_m = [], []
    if tot:
        s = max(tot, key=lambda s: s["modelP"])
        out_t.append({"playerId": game_id, "name": s["name"], "team": "TOTAL", "pos": "", "market": "nfl_total", "line": s["line"],
                      "direction": s["direction"], "prop": f"{s['direction'].upper()} {s['line']:g} total points", "odds": s["odds"],
                      "probability": round(s["modelP"], 4), "l5": round(s["modelP"], 4), "photoUrl": None, "oddsEstimated": False,
                      "jevP": s.get("jevP"), "rule": "game total: the core of the best-supported ticket shape"})
    if ml:
        s = max(ml, key=lambda s: s["modelP"])
        if s["modelP"] > 0.5:
            out_m.append({"playerId": game_id + ":ml", "name": s["team"], "team": _abbr(s["team"]), "pos": "", "market": "nfl_ml", "line": 0.0,
                          "direction": "win", "prop": "Moneyline", "odds": s["odds"], "probability": round(s["modelP"], 4),
                          "l5": round(s["modelP"], 4), "photoUrl": None, "oddsEstimated": False, "jevP": s.get("jevP"),
                          "rule": "model favourite to win"})
    return out_t, out_m


def _orders() -> dict:
    """MY BOO's orders for this card: the rules plus the opening of her latest written evaluation."""
    try:
        import boo_postgame
        import boo_reports
        cur = next((c for c in boo_reports.catalog() if c["current"]), None)
        if not cur:
            return {}
        r = boo_postgame.report(cur["gameId"])
        ev = r.get("evaluation") or {}
        return {"from": cur["label"], "evaluation": (ev.get("paragraphs") or [""])[0], "rules": [x["rule"] for x in (r.get("blueprint") or {}).get("rules", [])][:6]}
    except Exception:
        return {}


def card(game_id: str, game: dict) -> dict:
    props = _real_props(game_id)
    priced = bool(props)
    if not props:
        props = _model_props(game)
    tds = _td_pool(game, game_id)
    total, ml = _game_legs(game_id)
    key = lambda l: (-l["probability"], -(l.get("jevP") or l["probability"]))          # JEV breaks ties
    props.sort(key=key)

    market_of: dict[str, str] = {}       # one player, one prop across the whole card
    used: Counter = Counter()            # exposure per prediction

    def ok(l, slip, cap=EXPOSURE_CAP):
        pid = l["playerId"]
        if any(x["playerId"] == pid for x in slip):
            return False
        if pid in market_of and market_of[pid] != l["market"]:
            return False
        if used[(pid, l["market"], l["line"])] >= cap:
            return False
        return True

    def take(src, n, slip, per_team=2, mix=True):
        return _take(src, n, slip, per_team, mix, EXPOSURE_CAP)

    def _take(src, n, slip, per_team, mix, cap):
        for l in src:
            if len(slip) >= n:
                break
            if not ok(l, slip, cap):
                continue
            if l["team"] not in ("TOTAL",) and sum(1 for x in slip if x["team"] == l["team"]) >= per_team:
                continue
            if mix and any(x["market"] == l["market"] for x in slip if x["market"] in LABEL):
                continue
            slip.append(l)
        return slip

    def commit(slip):
        for l in slip:
            market_of[l["playerId"]] = l["market"]
            used[(l["playerId"], l["market"], l["line"])] += 1
        return slip

    plan = []

    def add(key, title, slip, n, note):
        """A ticket that cannot be filled under the rules is dropped, never padded: quality, not quantity."""
        if len(slip) == n:
            plan.append((key, title, commit(slip), note))

    add("q_core3", "MY BOO CORE 3", take(props, 3, list(total)), 3,
        "Game total plus the two best props: the shape that cashed most in her structure lab.")
    add("q_grail5", "THE GRAIL 5", take(props, 5, take(tds, len(total) + 1, list(total), mix=False), per_team=3), 5,
        "The one long ticket of the night: the total, the best essential TD and three props.")
    add("q_td3", "ESSENTIAL TD + 2", take(props, 3, take(tds, 1, [], mix=False)), 3,
        "The essential player most likely to score, plus two props from different players.")
    add("q_kings3", "TARGET KINGS 3", take(props, 3, []), 3,
        "The three highest-probability props from essential players, three different markets.")
    if ml:
        fav = ml[0]["team"]
        add("q_ml3", "MONEYLINE + 2", take([p for p in props if p["team"] == fav] + props, 3, list(ml)), 3,
            f"{ml[0]['name']} to win plus two props: the best-paying well-sampled shape.")
    one = one_man(game, props, tds)
    if one:
        legs, who = one
        for l in legs:
            used[(l["playerId"], l["market"], l["line"])] += 1
        plan.append(("q_oneman", f"ONE-MAN SHOW: {who.upper()}", legs,
                     f"Every leg rides the most productive player in this game. The one exception to one-player-one-prop, like the Crazy Horse: "
                     f"same-player legs move together, so FanDuel will price the ticket below the number shown."))
    est = any(l.get("oddsEstimated") for _, _, sl, _ in plan for l in sl)
    return {"plan": plan, "priced": priced, "estimated": est, "orders": _orders()}


def one_man(game: dict, props: list[dict], tds: list[dict]) -> tuple[list[dict], str] | None:
    """The single most productive essential player in the game (scrimmage yards a game plus 20 per touchdown a game),
    and a 3-to-5-leg ticket built only on him: his yardage, his catches or carries, his touchdown."""
    away, home = game["away_team"], game["home_team"]
    dim = data.player_dimension()
    rec, rus, pas = _rows("player_receiving_week.csv"), _rows("player_rushing_week.csv"), _rows("player_passing_week.csv")
    td = [r for r in csv.DictReader(open(data.GOLD / "td_log.csv", newline="")) if r["season"] == "2026" and r["is_offensive_td"] == "True"]
    yd, games, catches, carries = defaultdict(float), defaultdict(set), defaultdict(float), defaultdict(float)
    for r in rec:
        if r["team"] in (away, home):
            yd[(r["player_id"], r["team"])] += _f(r["receiving_yards"])
            catches[r["player_id"]] += _f(r["receptions"])
            games[r["player_id"]].add(r["week"])
    for r in rus:
        if r["team"] in (away, home):
            yd[(r["player_id"], r["team"])] += _f(r["rushing_yards"])
            carries[r["player_id"]] += _f(r["carries"])
            games[r["player_id"]].add(r["week"])
    qbs = {pid for pid, d in dim.items() if d.get("position") == "QB"}      # a receiver who threw one trick pass is not a QB
    best = None
    for (pid, team), y in yd.items():
        name = dim.get(pid, {}).get("name", "")
        if pid in qbs or not name or not red_zone.essential_td_ok(name, team):
            continue
        g = len(games[pid]) or 1
        n_td = sum(1 for r in td if r["scorer_player_name"] == _short(name) and r["scoring_team"] == team)
        score = y / g + 20 * n_td / g
        if not best or score > best[0]:
            best = (score, pid, team, name, g, n_td)
    if not best:
        return None
    _, pid, team, name, g, n_td = best
    pos = dim.get(pid, {}).get("position", "")
    legs = []
    base = {"playerId": pid, "name": name, "team": team, "pos": pos, "direction": "over", "photoUrl": data.photo_url(pid), "jevP": None}

    def posted(market):
        return next((l for l in props if l["playerId"] == pid and l["market"] == market and not l.get("oddsEstimated")), None)

    rec_y = sum(_f(r["receiving_yards"]) for r in rec if r["player_id"] == pid) / g
    rush_y = sum(_f(r["rushing_yards"]) for r in rus if r["player_id"] == pid) / g
    main = "recyds" if rec_y >= rush_y else "rushyds"
    avg_main = rec_y if main == "recyds" else rush_y
    for market, avg_v, p, why in ((main, avg_main, 0.62, f"averages {avg_main:.0f} {LABEL[main]} a game; line at 70%"),
                                  ("recs", catches[pid] / g, 0.62, f"averages {catches[pid] / g:.1f} catches; line at 70%")):
        if avg_v <= 0 or (market == "recs" and catches[pid] / g < 2.5):
            continue
        real = posted(market)
        if real:
            legs.append({**real, "rule": real.get("rule", "posted line")})
            continue
        line = max(1.5, math.floor(avg_v * 0.7) + 0.5) if market == "recs" else math.floor(avg_v * 0.7 * 2) / 2 + 0.5
        legs.append({**base, "market": market, "line": line, "prop": f"Over {line:g} {LABEL[market]}", "odds": _price(p), "probability": p,
                     "l5": p, "oddsEstimated": True, "rule": why})
    if main == "recyds" and rush_y >= 15:
        line = math.floor(rush_y * 0.7 * 2) / 2 + 0.5
        legs.append({**base, "market": "rushyds", "line": line, "prop": f"Over {line:g} rush yds", "odds": _price(0.58), "probability": 0.58,
                     "l5": 0.58, "oddsEstimated": True, "rule": f"also averages {rush_y:.0f} rush yds"})
    t = next((l for l in tds if l["playerId"] == pid), None)
    if t:
        legs.append(t)
    legs = legs[:5]
    return (legs, name) if len(legs) >= 3 else None

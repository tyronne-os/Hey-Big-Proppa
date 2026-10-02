"""
MY BOO slip recaps -- the standard write-up that rides with every bet slip.

Every slip gets the same three-part recap (200+ words, always):

  1. THE SETUP     -- written BEFORE kickoff: the strength of the defense we are
                      attacking, the offensive identity of the team, the thesis and
                      the nugget (the single leg the numbers like most).
  2. THE FACTS     -- straight from the post-game stats: pass attempts, rush
                      attempts, targets, player usage, actual vs line. Where the
                      thesis held and where it broke.
  3. HINDSIGHT     -- was the bet rooted in SCIENCE or SHIT? Process is graded
                      separately from the result, so a winning ticket built on luck
                      is called out and a losing ticket built on solid process is kept.

The setup is frozen the first time a ticket is seen (myboo_thesis.json) and never
rewritten, so the thought process stays measurable. Finished recaps are stored in
myboo_recaps.json with structured fields -- that is the training data for Jimmy
and Big Proppa. No LLM is involved; every sentence is built from lake numbers.
"""
from __future__ import annotations

import csv
import math
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import bpl
import data
import myboo

_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
_THESIS_FILE = _GOLD / "myboo_thesis.json"
_RECAPS_FILE = _GOLD / "myboo_recaps.json"
_LOCK = threading.RLock()

MIN_WORDS = 200
# Scoring props. Who scores is the offensive coordinator's call at the goal line, not something the
# stats can see, so these legs never count toward a SCIENCE verdict. The effort that gets a team to
# the red zone (yards, targets, touches) is what MY BOO grades.
TD_MARKETS = {"anytd", "firsttd", "lasttd"}
GAME_LEGS = {"nfl_total", "nfl_ml"}

USAGE_LABEL = {"tgt": "targets", "car": "carries", "att": "pass attempts", "touches": "touches"}

MARKET_LABEL = {
    "rushyds": "rushing yards", "recyds": "receiving yards", "recs": "receptions",
    "passyds": "passing yards", "passtd": "passing TDs", "anytd": "an anytime TD",
    "firsttd": "the first TD", "kickpts": "kicking points", "carries": "carries",
    "nfl_total": "game total points", "nfl_ml": "the moneyline",
}
# market -> the defensive categories that decide it (bpl.defense_ranks keys)
MARKET_CATS = {
    "rushyds": ["rush_yds"], "recyds": ["pass_yds"], "recs": ["completions"],
    "passyds": ["pass_yds"], "passtd": ["pass_yds"],
    "anytd": ["pass_yds", "rush_yds"], "firsttd": ["pass_yds", "rush_yds"],
    "nfl_total": ["pass_yds", "rush_yds"], "nfl_ml": ["pass_yds", "rush_yds"], "kickpts": [],
}
CAT_LABEL = {"pass_yds": "the pass", "rush_yds": "the run", "completions": "completions"}
CAT_NOUN = {"pass_yds": "pass defense", "rush_yds": "run defense", "completions": "completion defense"}
CAT_STAT = {"pass_yds": "pyds", "rush_yds": "ryds", "completions": "pyds"}

_PASS_FIRST, _RUN_LEAN = 0.63, 0.54   # pass-rate cut points for offensive identity


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _words(s: str) -> int:
    return len(s.split())


def _implied(american) -> float | None:
    a = _f(american)
    if not a:
        return None
    return 100 / (a + 100) if a > 0 else abs(a) / (abs(a) + 100)


_csv_cache: dict[str, tuple[float, list[dict]]] = {}


def _rows(name: str) -> list[dict]:
    p = _GOLD / f"{name}.csv"
    if not p.exists():
        return []
    m = p.stat().st_mtime
    hit = _csv_cache.get(name)
    if hit and hit[0] == m:
        return hit[1]
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    _csv_cache[name] = (m, rows)
    return rows


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _save_json(p: Path, obj: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    tmp.replace(p)


# ---------------------------------------------------------------------------
# lake aggregates -- team games, player usage, defensive samples
# ---------------------------------------------------------------------------

def _team_games(season: str) -> dict[tuple[int, str], dict]:
    """(week, team) -> {opp, att, car, tgt, pyds, ryds}. Built from the player weekly files."""
    out: dict[tuple[int, str], dict] = {}

    def bucket(r):
        k = (int(r["week"]), r["team"])
        return out.setdefault(k, {"opp": r.get("opponent_team", ""), "game_id": r.get("game_id", ""),
                                  "att": 0.0, "car": 0.0, "tgt": 0.0, "pyds": 0.0, "ryds": 0.0})

    for r in _rows("player_passing_week"):
        if r["season"] == season and r.get("season_type", "REG") == "REG":
            b = bucket(r); b["att"] += _f(r["attempts"], 0); b["pyds"] += _f(r["passing_yards"], 0)
    for r in _rows("player_rushing_week"):
        if r["season"] == season and r.get("season_type", "REG") == "REG":
            b = bucket(r); b["car"] += _f(r["carries"], 0); b["ryds"] += _f(r["rushing_yards"], 0)
    for r in _rows("player_receiving_week"):
        if r["season"] == season and r.get("season_type", "REG") == "REG":
            b = bucket(r); b["tgt"] += _f(r["targets"], 0)
    return out


def _player_weeks(season: str) -> dict[tuple[str, int], dict]:
    """(player_id, week) -> usage + production for that game."""
    out: dict[tuple[str, int], dict] = {}
    for fname, cols in (("player_passing_week", {"att": "attempts", "pyds": "passing_yards"}),
                        ("player_rushing_week", {"car": "carries", "ryds": "rushing_yards"}),
                        ("player_receiving_week", {"tgt": "targets", "rec": "receptions", "recyds": "receiving_yards"}),
                        ("player_scoring_week", {"td": "total_tds"})):
        for r in _rows(fname):
            if r["season"] != season or r.get("season_type", "REG") != "REG":
                continue
            d = out.setdefault((r["player_id"], int(r["week"])), {})
            d["team"] = r.get("team", d.get("team", ""))
            for k, c in cols.items():
                d[k] = d.get(k, 0.0) + _f(r.get(c), 0.0)
    return out


def _schedule_game(game_id: str, week: str, team: str) -> dict | None:
    for g in _rows("schedule"):
        if g["game_id"] == game_id:
            return g
    for g in _rows("schedule"):
        if str(g["week"]) == str(week) and team in (g["home_team"], g["away_team"]):
            return g
    return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _identity(tg: dict, team: str, before_week: int) -> dict | None:
    games = [v for (wk, t), v in tg.items() if t == team and wk < before_week]
    if not games:
        return None
    att, car, tgt = _mean(g["att"] for g in games), _mean(g["car"] for g in games), _mean(g["tgt"] for g in games)
    rate = att / (att + car) if att + car else 0.0
    label = "PASS-FIRST" if rate >= _PASS_FIRST else "RUN-LEANING" if rate <= _RUN_LEAN else "BALANCED"
    return {"games": len(games), "att": round(att, 1), "car": round(car, 1), "tgt": round(tgt, 1),
            "pass_rate": round(rate, 3), "label": label}


def _defense(tg: dict, team: str, before_week: int) -> dict:
    """What `team`'s defense has allowed this season, plus the model's prior-blended rank."""
    faced = [v for (wk, t), v in tg.items() if v["opp"] == team and wk < before_week]
    out = {"games": len(faced), "pass_yds": _mean(g["pyds"] for g in faced), "rush_yds": _mean(g["ryds"] for g in faced)}
    for cat in ("pass_yds", "rush_yds", "completions"):
        try:
            out[f"{cat}_rank"] = bpl.defense_ranks(cat).get(team)
            out[f"{cat}_blend"] = round(bpl._opp_allowed_blend(team, cat), 1)
            out[f"{cat}_league"] = round(bpl._league_allowed(cat), 1)
        except Exception:
            out[f"{cat}_rank"] = out[f"{cat}_blend"] = out[f"{cat}_league"] = None
    return out


def _def_adj(rank: int) -> str:
    return "stout" if rank <= 8 else "solid" if rank <= 16 else "leaky" if rank <= 24 else "soft"


def _def_label(rank: int | None) -> str:
    if rank is None:
        return "an unrated"
    return "a stout" if rank <= 8 else "an above-average" if rank <= 16 else "a below-average" if rank <= 24 else "a soft"


# ---------------------------------------------------------------------------
# SETUP -- frozen pre-game thesis
# ---------------------------------------------------------------------------

def _pid_lookup() -> dict[tuple[str, str], str]:
    ids: dict[tuple[str, str], str] = {}
    for pid, r in data.player_dimension().items():
        n = data.normalize_name(r.get("name", ""))
        ids[(n, r.get("team", ""))] = pid
        ids.setdefault((n, ""), pid)
    return ids


def _leg_thesis(leg: dict, week: int, season: str, tg: dict, pw: dict, ids: dict) -> dict:
    team = leg["team"]
    game = _schedule_game(leg.get("game_id", ""), str(week), team)
    opp = ""
    if game and leg["market"] not in GAME_LEGS:
        opp = game["away_team"] if game["home_team"] == team else game["home_team"]
    mk = leg["market"]
    pid = ids.get((myboo._norm(leg["player_name"]), team)) or ids.get((myboo._norm(leg["player_name"]), ""))
    cats = MARKET_CATS.get(mk, [])
    dfn = _defense(tg, opp, week) if opp else {}
    # the category the model is really attacking = the weakest defense among the relevant ones
    attack = max(cats, key=lambda c: dfn.get(f"{c}_rank") or 0) if cats else None
    prior = [v for (p, wk), v in pw.items() if p == pid and wk < week] if pid else []
    usage_key = {"rushyds": "car", "recyds": "tgt", "recs": "tgt", "passyds": "att", "passtd": "att"}.get(mk)
    if usage_key:
        use_avg = _mean(v.get(usage_key) for v in prior)
    elif mk in ("anytd", "firsttd"):
        use_avg = _mean((v.get("car", 0) + v.get("tgt", 0)) for v in prior) if prior else None
        usage_key = "touches"
    else:
        use_avg = None
    prob, imp = _f(leg.get("probability")), _implied(leg.get("odds"))
    comps, jscore = None, None          # Jimmy's full signal vector at the moment the slip is frozen (training data)
    if pid and mk not in GAME_LEGS and mk not in TD_MARKETS:
        try:
            import jimmy, jimmy_hunt
            hr = jimmy_hunt._hit_rate(pid, mk, _f(leg.get("line"), 0.5), leg.get("direction", "over"))
            comps = {k: round(v, 4) for k, v in jimmy.score_components(pid, hr, mk, leg.get("direction", "over")).items()}
            jscore = jimmy.jimmy_score(pid, hr, mk, leg.get("direction", "over"))
        except Exception:
            pass
    return {
        "player": leg["player_name"], "player_id": pid, "team": team, "opp": opp, "market": mk,
        "direction": leg.get("direction", "over"), "line": _f(leg.get("line")), "odds": _f(leg.get("odds")),
        "prob": prob, "implied": round(imp, 4) if imp else None,
        "edge": round(prob - imp, 4) if prob is not None and imp else None,
        "attack_cat": attack, "attack_rank": dfn.get(f"{attack}_rank") if attack else None,
        "attack_allowed": dfn.get(f"{attack}_blend") if attack else None,
        "attack_league": dfn.get(f"{attack}_league") if attack else None,
        "defense": {k: dfn.get(k) for k in ("games", "pass_yds", "rush_yds", "pass_yds_rank", "rush_yds_rank",
                                              "pass_yds_blend", "rush_yds_blend", "pass_yds_league", "rush_yds_league")},
        "components": comps, "jimmy_score": jscore,
        "usage_key": usage_key, "usage_avg": round(use_avg, 1) if use_avg is not None else None,
        "usage_games": len(prior), "game_id": (game or {}).get("game_id", leg.get("game_id", "")),
    }


def _nugget(legs: list[dict]) -> dict | None:
    """The leg the numbers like most: biggest edge, tie-broken by how soft the attacked defense is."""
    scored = [l for l in legs if l.get("edge") is not None]
    if not scored:
        return None
    return max(scored, key=lambda l: (l["edge"] + 0.004 * (l.get("attack_rank") or 0)))


def _setup_text(ticket: dict, legs: list[dict], identity: dict) -> str:
    title = ticket["name"].split(" · ")[0]
    paras: list[str] = []

    # 1. lead with the defense(s)
    seen: set[str] = set()
    lead: list[str] = []
    for l in legs:
        if not l["opp"] or l["opp"] in seen:
            continue
        seen.add(l["opp"])
        d = l["defense"]
        pr, rr = d.get("pass_yds_rank"), d.get("rush_yds_rank")
        bits = []
        if pr:
            bits.append(f"{_ord(pr)} of 32 against the pass ({d['pass_yds_blend']} yards a game allowed on the Big Proppa blend, league average {d['pass_yds_league']})")
        if rr:
            bits.append(f"{_ord(rr)} against the run ({d['rush_yds_blend']} allowed, league average {d['rush_yds_league']})")
        if bits:
            soft_cat = "pass" if (pr or 0) > (rr or 0) else "run"
            soft_rank = max(pr or 0, rr or 0)
            if pr and rr and abs(pr - rr) >= 10:
                strong = "pass" if pr < rr else "run"
                verdict = (f"a split defense, {_def_adj(min(pr, rr))} against the {strong} and {_def_adj(max(pr, rr))} "
                           f"against the {soft_cat}, so the soft spot is the {soft_cat}")
            elif soft_rank > 16:
                overall = round(((pr or soft_rank) + (rr or soft_rank)) / 2)
                verdict = f"{_def_label(overall)} unit overall, and the soft spot is the {soft_cat}"
            else:
                verdict = "a unit that gives up very little in either phase, so I am only taking the cleanest price"
            lead.append(f"{l['opp']} is {verdict}: " + " and ".join(bits) + ".")
    if lead:
        paras.append("I always read the defense first. " + " ".join(lead))
    else:
        paras.append("I always read the defense first, and for this slip the defensive sample is thin, so I leaned on the prior-season blend and kept the stakes flat.")

    # 2. offensive identity
    idents: list[str] = []
    for team in identity:
        idn = identity.get(team)
        if idn:
            idents.append(f"{team} has been {idn['label']} through {idn['games']} game{'s' if idn['games'] != 1 else ''}: {idn['att']} pass attempts and {idn['car']} rushes a game, {idn['tgt']} targets, a {round(idn['pass_rate'] * 100)}% pass rate.")
        else:
            idents.append(f"{team} has no completed games in the sample yet, so identity is an unknown I am pricing in.")
    paras.append("Offensive identity is where I build the case. " + " ".join(idents))

    # 3. the thought process, leg by leg
    thoughts = []
    for l in legs:
        lab = MARKET_LABEL.get(l["market"], l["market"])
        if l["market"] == "nfl_total":
            thoughts.append(f"The game total {l['direction']} {l['line']:g} points.")
            continue
        if l["market"] == "nfl_ml":
            thoughts.append(f"{l['team']} on the moneyline.")
            continue
        if l["market"] in TD_MARKETS:
            want = f"to score {lab}"
        else:
            want = f"{l['direction']} {l['line']:g} {lab}"
        if l["edge"] is None:
            edge = ""
        elif abs(l["edge"]) < 0.005:
            edge = f"; the price is fair at {round(l['prob'] * 100)}%, so the case rests on the matchup and the role, not on a price gap"
        else:
            edge = f"; my number is {round(l['prob'] * 100)}% against {round(l['implied'] * 100)}% priced in, a {abs(round(l['edge'] * 100, 1))}-point {'edge' if l['edge'] > 0 else 'deficit'}"
        use = f", on a {l['usage_avg']} {USAGE_LABEL.get(l['usage_key'], l['usage_key'])} average" if l["usage_avg"] is not None else ""
        thoughts.append(f"{l['player']} ({l['team']}) {want}{use}{edge}.")
    paras.append(f"The {title} thesis, leg by leg: " + " ".join(thoughts))
    tds = [l["player"] for l in legs if l["market"] in TD_MARKETS]
    if tds:
        paras.append(f"Coach's-call legs: {', '.join(dict.fromkeys(tds))} to score. Who gets the ball at the goal line is the offensive "
                     "coordinator's decision, not something the stats can see, so these legs ride on the play call. The science on this "
                     "slip lives in the effort legs, the yards and touches it takes to get to the red zone.")

    n = _nugget(legs)
    if n:
        spot = f"{n['opp']}'s {CAT_NOUN.get(n['attack_cat'], 'defense')} ({_ord(n['attack_rank'])} of 32)" if n.get("attack_rank") else f"{n['opp']}'s defense"
        if n["edge"] is not None and n["edge"] >= 0.02:
            paras.append(f"The nugget of gold is {n['player']}: {spot} gives the widest gap between price and probability on the board, and that is prospecting, not guessing. If this slip feeds us, that is the reason.")
        elif (n.get("attack_rank") or 99) <= 8:
            paras.append(f"This is a contrarian read: {spot} is one of the better units in the league, so the nugget is not the matchup, it is volume. {n['player']} gets the opportunities, and I am betting that opportunity beats quality here. If this slip feeds us, that is the lesson hindsight will confirm; if it starves us, the defense was the reason.")
        else:
            paras.append(f"No leg carries a real price edge on this slip, so the nugget is a matchup read: {n['player']} against {spot}. If this slip feeds us, it feeds us because the role and the matchup were right, and that is exactly what the hindsight will test.")
    # price check on the whole ticket
    probs = [l["prob"] for l in legs if l["prob"]]
    pay = _implied(ticket.get("payout_odds"))
    if probs and pay:
        names = [l["player"] for l in legs]
        if len(set(names)) < len(names):
            paras.append(f"Price check: several legs ride on the same player, so they are correlated and a simple multiplication of the legs would understate the real chance. The payout of +{ticket.get('payout_odds')} implies {round(pay * 100, 1)}%, and I am logging the full structure so hindsight can measure how often these correlated builds actually land.")
        else:
            combo = 1.0
            for p in probs:
                combo *= p
            paras.append(f"Price check: stacking the legs as independent gives {round(combo * 100, 1)}% to cash, while the payout of +{ticket.get('payout_odds')} implies {round(pay * 100, 1)}%. "
                         f"That {'is' if combo >= pay else 'is not'} a positive-value ticket on my numbers, and it is logged either way so the process can be graded afterward.")
    return "\n\n".join(paras)


def _slip_teams(legs: list[dict], tg: dict, week: int) -> list[str]:
    """Real teams on the slip. A game-total or moneyline leg contributes both teams of its game."""
    out: list[str] = []
    for l in legs:
        if l.get("market") in GAME_LEGS or l.get("team") in ("TOTAL", ""):
            g = _schedule_game(l.get("game_id", ""), str(week), "")
            if g:
                out += [g["away_team"], g["home_team"]]
        else:
            out.append(l["team"])
    return out


def _snapshot(ticket: dict, legs: list[dict], persist: bool = True) -> dict:
    season, week = str(ticket["season"]), int(ticket["week"])
    tg, pw, ids = _team_games(season), _player_weeks(season), _pid_lookup()
    lt = [_leg_thesis(l, week, season, tg, pw, ids) for l in legs]
    snap = {
        "ticket_id": ticket["ticket_id"], "frozen_at": datetime.now(timezone.utc).isoformat(),
        "sample_weeks_before": week, "legs": lt,
        "identity": {t: _identity(tg, t, week) for t in dict.fromkeys(_slip_teams(legs, tg, week))},
        "nugget": (_nugget(lt) or {}).get("player"),
    }
    return snap


def snapshot_open() -> int:
    """Freeze the pre-game thesis for every ticket that does not have one. Idempotent; never overwrites."""
    with _LOCK:
        store = _load_json(_THESIS_FILE)
        tickets = myboo.load_tickets_raw()
        with open(myboo._LEGS_FILE, newline="") as f:
            all_legs = list(csv.DictReader(f))
        by_t: dict[str, list[dict]] = {}
        for l in all_legs:
            by_t.setdefault(l["ticket_id"], []).append(l)
        n = 0
        for t in tickets:
            if t["ticket_id"] in store or not by_t.get(t["ticket_id"]):
                continue
            store[t["ticket_id"]] = _snapshot(t, by_t[t["ticket_id"]])
            n += 1
        if n:
            _save_json(_THESIS_FILE, store)
        return n


# ---------------------------------------------------------------------------
# FACTS + HINDSIGHT
# ---------------------------------------------------------------------------

def _leg_facts(th: dict, leg: dict, week: int, tg: dict, pw: dict) -> dict:
    """Post-game truth for one leg, and whether the pre-game thesis held."""
    mine, theirs = tg.get((week, th["team"])), tg.get((week, th["opp"]))
    p = pw.get((th["player_id"], week), {}) if th["player_id"] else {}
    uk = th["usage_key"]
    used = (p.get("car", 0) + p.get("tgt", 0)) if uk == "touches" else p.get(uk) if uk else None
    volume_held = None
    if used is not None and th["usage_avg"]:
        volume_held = used >= 0.85 * th["usage_avg"]
    env_held = None
    cat = th["attack_cat"]
    if mine and cat and th["attack_allowed"]:
        got = mine[CAT_STAT[cat]]
        env_held = got >= 0.9 * th["attack_allowed"] if th["direction"] == "over" else got <= 1.1 * th["attack_allowed"]
    known = [x for x in (volume_held, env_held) if x is not None]
    held = all(known) if known else None      # a leg only 'held' when BOTH the matchup and the player's usage played out
    if th["market"] in TD_MARKETS:
        held = None                           # coach's call: never graded as science
    return {"player": th["player"], "market": th["market"], "line": th["line"], "direction": th["direction"],
            "status": leg["status"], "actual": _f(leg.get("actual_value")), "used": used, "usage_key": uk,
            "usage_avg": th["usage_avg"], "volume_held": volume_held, "env_held": env_held, "thesis_held": held,
            "team_got": mine, "opp_got": theirs, "attack_cat": cat, "attack_allowed": th["attack_allowed"],
            "team": th["team"], "td_leg": th["market"] in TD_MARKETS,
            "scrimmage": (p.get("ryds", 0) + p.get("recyds", 0)) if p else None,
            "scorers": sorted(data.player_name(pid) for (pid, wk), v in pw.items()
                              if wk == week and v.get("team") == th["team"] and v.get("td", 0) > 0)}


def _result_phrase(f: dict) -> str:
    mk, act = f["market"], f["actual"]
    if mk == "firsttd":
        return "scored the game's first TD" if f["status"] == "HIT" else "was not the first to score"
    if mk == "anytd":
        n = int(act or 0)
        return f"scored {n} TD{'s' if n != 1 else ''}"
    if mk == "nfl_ml":
        return f"finished {act:+g} on the margin" if act is not None else "had no margin recorded"
    a = "n/a" if act is None else f"{act:g}"
    return f"finished with {a} {MARKET_LABEL.get(mk, mk)}"


def tm_name(f: dict) -> str:
    return 'the offense'


def _facts_text(snap: dict, facts: list[dict], week: int, final: dict | None, tg: dict, partial: str | None = None) -> str:
    paras: list[str] = []
    if partial:
        paras.append(f"Early record: this slip was decided at {partial} with the game still on, so these are partial-game numbers. The team-level read below is a snapshot, not a verdict, and this recap is rewritten from the full stat line at the final whistle.")
    if final:
        paras.append(f"Final: {final['away_team']} {final['away_score']}, {final['home_team']} {final['home_score']}.")
    for team, pre in snap["identity"].items():
        row = tg.get((week, team))
        if not row:
            continue
        rate = row["att"] / (row["att"] + row["car"]) if row["att"] + row["car"] else 0
        if partial:
            paras.append(f"{team} so far: {int(row['att'])} pass attempts, {int(row['car'])} rushes, {int(row['tgt'])} targets, {int(row['pyds'])} passing and {int(row['ryds'])} rushing yards.")
        elif pre:
            shift = rate - pre["pass_rate"]
            held = "the identity held" if abs(shift) < 0.08 else "the identity flipped" + (" toward the air" if shift > 0 else " toward the ground")
            paras.append(f"{team} threw {int(row['att'])} times and ran {int(row['car'])}, with {int(row['tgt'])} targets, a {round(rate * 100)}% pass rate against {round(pre['pass_rate'] * 100)}% coming in, so {held}. They produced {int(row['pyds'])} passing and {int(row['ryds'])} rushing yards.")
        else:
            paras.append(f"{team} threw {int(row['att'])} times and ran {int(row['car'])}, with {int(row['tgt'])} targets, a {round(rate * 100)}% pass rate, {int(row['pyds'])} passing and {int(row['ryds'])} rushing yards.")
    right, wrong = [], []
    for f in facts:
        use = ""
        if f["used"] is not None and f["usage_avg"]:
            use = f" on {int(f['used'])} {USAGE_LABEL.get(f['usage_key'], f['usage_key'])} against his average of {f['usage_avg']}"
        why = ""
        if f["status"] == "MISS" and f.get("td_leg"):
            yds = f" for {int(f['scrimmage'])} scrimmage yards" if f.get("scrimmage") else ""
            who = (f"{f['team']}'s touchdowns went to {', '.join(f['scorers'])}" if f.get("scorers")
                   else f"{f['team']} did not score an offensive touchdown")
            effort = "The effort was there" if f["volume_held"] else "The volume was light too"
            why = (f" {effort}: he handled the ball{yds}. {who}. That is a goal-line play call, not a stat, "
                   "and it is exactly why a scoring leg is not science.")
        elif f["status"] == "MISS":
            tm = f["team_got"]
            if f["volume_held"] is False:
                why = " The workload fell short of the baseline, so the role assumption was the thing that broke."
            elif f["volume_held"] and f["env_held"] and tm:
                why = f" The workload and the matchup were both there and {tm_name(f)} still moved the ball ({int(tm['ryds'])} rushing, {int(tm['pyds'])} passing), so the leak was efficiency or who else ate the production, not the read."
            elif f["env_held"] is False:
                why = " The defense played better than its numbers going in, which is the kind of miss that corrects the ranking."
        if f["market"] == "nfl_total":
            pts = "n/a" if f["actual"] is None else f"{f['actual']:g}"
            line = f"The game finished with {pts} total points (line {f['line']:g}) for a {f['status']}."
        else:
            line = f"{f['player']} {_result_phrase(f)}{use} (line {f['line']:g}) for a {f['status']}.{why}"
        (right if f["status"] == "HIT" else wrong).append(line)
    if right:
        paras.append("Where we got it right: " + " ".join(right))
    if wrong:
        paras.append("Where we got it wrong: " + " ".join(wrong))
    return "\n\n".join(paras)


def _dec_from_american(a: float) -> float:
    return 1 + (a / 100 if a > 0 else 100 / -a)


def _am_from_dec(d: float) -> int:
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


def _td_leg_price(th: dict) -> tuple[float, str]:
    """Decimal price of a touchdown leg: FanDuel's board price if the lake has it, else the ticket's own, else fair from the model."""
    try:
        row = data.best_price_for(th["player"], "anytd")
        if row and row.get("best_moneyline_price"):
            return _dec_from_american(float(row["best_moneyline_price"])), f"FanDuel's board price ({row['best_moneyline_price']})"
    except Exception:
        pass
    if th.get("odds"):
        return _dec_from_american(th["odds"]), "the price on the ticket"
    return 1 / max(th.get("prob") or 0.25, 0.05), "a fair-price estimate"


def _whatif(ticket: dict, snap_legs: list[dict], facts: list[dict]) -> dict | None:
    """Strip the touchdown legs and ask what the effort-only ticket would have done. The price of the stripped legs is estimated."""
    td = [(th, f) for th, f in zip(snap_legs, facts) if f.get("td_leg")]
    pay = _f(ticket.get("payout_odds"))
    if not td or not pay:
        return None
    full_dec = _dec_from_american(pay)
    prices = [_td_leg_price(th) for th, _ in td]
    stripped_dec = max(1.01, full_dec / math.prod(p for p, _ in prices))
    effort = [f for f in facts if not f.get("td_leg")]
    missed = [f for f in effort if f["status"] == "MISS"]
    stake = _f(ticket.get("stake_units"), 1.0)
    return {
        "td_players": list(dict.fromkeys(th["player"] for th, _ in td)), "price_source": prices[0][1],
        "full_american": int(pay), "stripped_american": _am_from_dec(stripped_dec),
        "stake": stake, "effort_legs": len(effort), "effort_missed": len(missed),
        "would_have_cashed": not missed, "stripped_profit": round(stake * (stripped_dec - 1), 2),
        "full_profit_if_td_hit": round(stake * (full_dec - 1), 2),
    }


def _whatif_text(w: dict) -> str:
    who = " and ".join(w["td_players"])
    if w["would_have_cashed"]:
        return (f" What-if: take out the {who} touchdown leg{'s' if len(w['td_players']) > 1 else ''} and the same ticket is "
                f"{w['effort_legs']} effort legs at about +{w['stripped_american']} (priced off {w['price_source']}). Every one of them cashed, "
                f"so it pays about ${w['stripped_profit']:g} profit on ${w['stake']:g}. The touchdown was the only thing between this slip and the money.")
    return (f" What-if: take out the {who} touchdown leg{'s' if len(w['td_players']) > 1 else ''} and the effort-only ticket would still "
            f"have lost, because {w['effort_missed']} of its {w['effort_legs']} effort legs missed too. The touchdown was not the only problem here.")


def _game_script(final: dict | None, tg: dict, week: int, snap: dict, game: dict | None) -> dict | None:
    teams = [t for t in snap["identity"]]
    rows = {t: tg.get((week, t)) for t in teams}
    if not final or not all(rows.values()) or len(teams) < 2:
        return None
    a, h = final["away_team"], final["home_team"]
    a_pts, h_pts = int(final["away_score"]), int(final["home_score"])
    margin = abs(a_pts - h_pts)
    plays = sum(r["att"] + r["car"] for r in rows.values())
    line = _f((game or {}).get("total_line"))
    shape = "one-score" if margin <= 8 else "two-score" if margin <= 16 else "blowout"
    winner = a if a_pts > h_pts else h
    return {"away": a, "home": h, "away_pts": a_pts, "home_pts": h_pts, "margin": margin, "winner": winner,
            "shape": shape, "plays": int(plays), "total_pts": a_pts + h_pts, "total_line": line,
            "pass_rate": {t: round(r["att"] / (r["att"] + r["car"]), 3) if r["att"] + r["car"] else None for t, r in rows.items()}}


def _game_script_text(g: dict) -> str:
    vs = ""
    if g["total_line"]:
        side = "over" if g["total_pts"] > g["total_line"] else "under"
        vs = f", {abs(g['total_pts'] - g['total_line']):g} {side} the {g['total_line']:g} total"
    rates = ", ".join(f"{t} passed on {round(r * 100)}% of its plays" for t, r in g["pass_rate"].items() if r is not None)
    return (f"Game script: {g['winner']} won a {g['shape']} game {max(g['away_pts'], g['home_pts'])}-{min(g['away_pts'], g['home_pts'])} "
            f"({g['total_pts']} points{vs}) over {g['plays']} offensive plays. {rates}.")


def _defense_audit(snap_legs: list[dict], tg: dict, week: int) -> list[dict]:
    """How each opposing defense actually did against the number the model expected it to allow."""
    seen: set = set()
    out = []
    for th in snap_legs:
        if not th.get("opp") or th.get("attack_cat") not in ("pass_yds", "rush_yds") or not th.get("attack_allowed"):
            continue        # completions are a count, not yards, so they cannot be compared with the yards actually allowed
        key = (th["opp"], th["attack_cat"])
        row = tg.get((week, th["team"]))
        if key in seen or not row:
            continue
        seen.add(key)
        actual = row[CAT_STAT[th["attack_cat"]]]
        out.append({"defense": th["opp"], "cat": "pass" if th["attack_cat"] == "pass_yds" else "rush", "rank": th["attack_rank"],
                    "expected": th["attack_allowed"], "actual": actual, "ratio": round(actual / th["attack_allowed"], 3) if th["attack_allowed"] else None})
    return out


def _defense_audit_text(rows: list[dict]) -> str:
    bits = []
    for r in rows:
        if not r["ratio"]:
            continue
        diff = round((r["ratio"] - 1) * 100)
        verdict = "about what the rank said" if abs(diff) < 10 else f"{abs(diff)}% {'worse' if diff > 0 else 'better'} than the rank said"
        bits.append(f"{r['defense']}'s {r['cat']} defense ({_ord(r['rank'])} of 32) was expected to allow {r['expected']:g} and allowed {r['actual']:g}, {verdict}")
    return ("Defense report card: " + "; ".join(bits) + ". These residuals go to the Tuesday batch to correct the rankings.") if bits else ""


def _miss_type(f: dict) -> str | None:
    """Why a leg missed, in a closed vocabulary Jimmy can learn from."""
    if f["status"] != "MISS":
        return None
    if f.get("td_leg"):
        return "COACH_CALL"
    if f["volume_held"] is False:
        return "VOLUME_COLLAPSE"
    if f["env_held"] is False:
        return "DEFENSE_OVERPERFORMED" if f["direction"] == "over" else "DEFENSE_UNDERPERFORMED"
    if f["actual"] is not None and f["line"] and abs(f["actual"] - f["line"]) <= 0.1 * f["line"]:
        return "NEAR_MISS"
    return "EFFICIENCY"


def _verdict(slip_status: str, facts: list[dict], snap: dict, partial: str | None = None) -> dict:
    if partial:
        won = slip_status == "SETTLED_WIN"
        return {"label": "EARLY CASH" if won else "EARLY KILL", "process_score": None, "process_ok": None, "outcome": slip_status,
                "tags": ["EARLY_LOCK"], "text": f"The result is locked at {partial}. Science or shit is decided at the final, once the full stat line is in and the usage and the defense can be graded for the whole game."}
    known = [f["thesis_held"] for f in facts if f["thesis_held"] is not None]
    score = round(sum(known) / len(known), 2) if known else None
    process_ok = (score >= 0.5) if score is not None else None
    won = slip_status == "SETTLED_WIN"
    lost = slip_status == "SETTLED_LOSS"
    if process_ok is None:
        label, line = "UNSCORED", "There was not enough pre-game sample to grade the process, so this one goes in the book as data only."
    elif won and process_ok:
        label, line = "SCIENCE", "This was rooted in science: the defense and the usage did what I said they would, and the ticket cashed. That is a dinner indicator, and the nugget goes in the repeat pile."
    elif won and not process_ok:
        label, line = "SHIT (LUCKY)", "It cashed, but the thesis did not hold, which makes it variance and not skill. Do not repeat it and do not count it as proof."
    elif lost and process_ok:
        label, line = "SCIENCE (BAD BEAT)", "The process was sound: the defense and the usage held and the number still did not fall. Keep the method, because over a long season this is how the edge pays."
    elif lost:
        label, line = "SHIT", "This was not rooted in science. The thesis broke on the facts, and the lesson is worth more than the stake."
    else:
        label, line = "OPEN", "Still live."
    td_miss = [f for f in facts if f.get("td_leg") and f["status"] == "MISS"]
    effort = [f for f in facts if not f.get("td_leg")]
    effort_missed = [f for f in effort if f["status"] == "MISS"]
    if lost and td_miss:
        hit = sum(f["status"] == "HIT" for f in effort)
        names = ", ".join(dict.fromkeys(f["player"] for f in td_miss))
        if not effort_missed:
            label = "SHIT (TD GAMBLE)"
            line = (f"Every effort leg cashed, {hit} of {len(effort)}, and the slip still died on {names} to score. "
                    "Who scores is the offensive coordinator's call at the goal line, not science. Take the effort prop "
                    "that pays the same (an alt yardage rung) and this ticket cashes.")
        else:
            label = "SHIT (TD GAMBLE)"
            line = (f"The slip leaned on {len(td_miss)} scoring leg{'s' if len(td_miss) != 1 else ''} ({names}) that the stats "
                    f"cannot see, and the effort legs went {hit} of {len(effort)}. Scoring legs are a coin flip on the play call; "
                    "build on the effort it takes to reach the red zone instead.")
        process_ok = False if not effort else process_ok
    elif won and any(f.get("td_leg") for f in facts) and label == "SCIENCE":
        line += " The scoring leg landed too, but that part was the play call, not the science."
    tags = []
    if process_ok:
        tags.append("PROCESS_HELD")
    if process_ok is False:
        tags.append("THESIS_BROKE")
    if any(f["volume_held"] is False for f in facts):
        tags.append("VOLUME_COLLAPSED")
    if any(f["env_held"] is False for f in facts):
        tags.append("DEFENSE_BEHAVED")
    if any(f.get("td_leg") for f in facts):
        tags.append("TD_GAMBLE")
    if won and process_ok and any((l.get("attack_rank") or 0) >= 25 for l in snap["legs"]):
        tags.append("FEAST_INDICATOR")
    return {"label": label, "process_score": score, "process_ok": process_ok, "outcome": slip_status, "tags": tags, "text": line}


def _pad(text: str, ticket: dict, legs: list[dict], snap: dict) -> str:
    """Guarantee the 200-word floor with real, data-backed context -- never filler."""
    extras = []
    for l in snap["legs"]:
        if l["usage_games"] and l["usage_avg"] is not None:
            extras.append(f"{l['player']} has {l['usage_games']} game{'s' if l['usage_games'] != 1 else ''} of usage in the book, averaging {l['usage_avg']} {USAGE_LABEL.get(l['usage_key'], l['usage_key'])}, which is the baseline the volume check was graded against.")
        if l["attack_rank"]:
            extras.append(f"{l['opp']}'s {CAT_NOUN.get(l['attack_cat'], 'defense')} sits {_ord(l['attack_rank'])} before this game, and that ranking is logged with the ticket so the model can be corrected if it was wrong.")
    extras.append("Every number in this recap is written to the training file, so the next version of Jimmy and Big Proppa learns from this exact slip, win or lose.")
    i = 0
    while _words(text) < MIN_WORDS and i < len(extras):
        text += "\n\n" + extras[i]
        i += 1
    return text


def build_recap(ticket: dict, legs: list[dict], snap: dict | None = None, overlay: dict | None = None) -> dict:
    """Assemble the three-part recap for one ticket. Pending slips get the setup only -- results are never invented."""
    season, week = str(ticket["season"]), int(ticket["week"])
    snap = snap or _snapshot(ticket, legs)
    graded = [l for l in legs if l["status"] in ("HIT", "MISS")]
    base = {"ticket_id": ticket["ticket_id"], "name": ticket["name"], "week": week, "season": season,
            "order_type": ticket.get("order_type"), "status": ticket["status"], "nugget": snap.get("nugget")}
    setup = _setup_text(ticket, snap["legs"], snap["identity"])
    if not graded:
        setup = _pad(setup, ticket, legs, snap)
        return {**base, "stage": "PREGAME", "setup": setup, "facts": "", "hindsight": None, "partial": None,
                "word_count": _words(setup), "features": {"legs": snap["legs"]}}
    tg, pw = _team_games(season), _player_weeks(season)
    partial = (overlay or {}).get("partial")
    if overlay:                       # live box score fills in games the lake has not ingested yet
        tg, pw = {**tg, **overlay["tg"]}, {**pw, **overlay["pw"]}
    th_by_key = {(t["player"], t["market"], t["line"]): t for t in snap["legs"]}
    facts = []
    for l in legs:
        th = th_by_key.get((l["player_name"], l["market"], _f(l.get("line")))) or _leg_thesis(l, week, season, tg, pw, _pid_lookup())
        facts.append(_leg_facts(th, l, week, tg, pw))
    game = _schedule_game(legs[0].get("game_id", ""), str(week), legs[0]["team"])
    final = game if game and game.get("home_score") not in ("", None) else None
    if not final and overlay and overlay.get("final"):
        final = overlay["final"]
    facts_text = _facts_text(snap, [f for f in facts if f["status"] in ("HIT", "MISS")], week, final, tg, partial)
    script = None if partial else _game_script(final, tg, week, snap, game)
    dfn = [] if partial else _defense_audit(snap["legs"], tg, week)
    if script:
        facts_text += "\n\n" + _game_script_text(script)
    if dfn and _defense_audit_text(dfn):
        facts_text += "\n\n" + _defense_audit_text(dfn)
    for f in facts:
        f["miss_type"] = _miss_type(f)
    v = _verdict(ticket["status"], [f for f in facts if f["status"] in ("HIT", "MISS")], snap, partial)
    hind = (f"Hindsight: {v['label']}. {v['text']} Process score {v['process_score'] if v['process_score'] is not None else 'n/a'} "
            f"(share of effort legs where both the defensive matchup and the player's usage played out the way I wrote them down; scoring legs are not graded).")
    wi = None if partial or ticket["status"] != "SETTLED_LOSS" else _whatif(ticket, snap["legs"], facts)
    if wi:
        hind += _whatif_text(wi)
    full = setup + "\n\n" + facts_text + "\n\n" + hind
    if _words(full) < MIN_WORDS:
        setup = _pad(setup, ticket, legs, snap)
        full = setup + "\n\n" + facts_text + "\n\n" + hind
    stage = "FINAL" if ticket["status"] in ("SETTLED_WIN", "SETTLED_LOSS") else "IN PROGRESS"
    return {**base, "stage": stage, "partial": partial, "setup": setup, "facts": facts_text, "hindsight": {**v, "line": hind},
            "word_count": _words(full), "features": {"legs": snap["legs"], "game": script, "defense_audit": dfn, "whatif": wi, "facts": [
                {k: f.get(k) for k in ("player", "market", "status", "actual", "used", "usage_avg", "volume_held", "env_held", "thesis_held", "miss_type", "scrimmage")} for f in facts]}}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def recaps(week: int | None = None, ticket_id: str | None = None) -> list[dict]:
    """All recaps, newest ticket first. Finished recaps are persisted as the training record."""
    with _LOCK:
        myboo.settle()
        snapshot_open()
        thesis = _load_json(_THESIS_FILE)
        saved = _load_json(_RECAPS_FILE)
        tickets = myboo.load_tickets_raw()
        with open(myboo._LEGS_FILE, newline="") as f:
            all_legs = list(csv.DictReader(f))
        by_t: dict[str, list[dict]] = {}
        for l in all_legs:
            by_t.setdefault(l["ticket_id"], []).append(l)
        out, dirty = [], False
        for t in sorted(tickets, key=lambda x: x["ticket_id"], reverse=True):
            if week is not None and str(t["week"]) != str(week):
                continue
            if ticket_id and t["ticket_id"] != ticket_id:
                continue
            legs = by_t.get(t["ticket_id"], [])
            if not legs:
                continue
            if t["ticket_id"] in saved and saved[t["ticket_id"]].get("stage") == "FINAL":
                out.append(saved[t["ticket_id"]])
                continue
            rc = build_recap(t, legs, thesis.get(t["ticket_id"]))
            if rc["stage"] == "FINAL":
                saved[t["ticket_id"]] = rc
                dirty = True
            out.append(rc)
        if dirty:
            _save_json(_RECAPS_FILE, saved)
        return out


# ---------------------------------------------------------------------------
# compliance -- every report is checked against agents/myboo/PROCEDURE.md
# ---------------------------------------------------------------------------
VERDICTS = {"SCIENCE", "SCIENCE (BAD BEAT)", "SHIT", "SHIT (LUCKY)", "SHIT (TD GAMBLE)", "EARLY CASH", "EARLY KILL", "UNSCORED", "OPEN"}
_OPENER = "I always read the defense first"


def audit(rc: dict, legs: list[dict] | None = None) -> list[str]:
    """Return every way this report breaks the zero-deviation procedure. An empty list means compliant."""
    bad: list[str] = []
    setup, facts, hind = rc.get("setup") or "", rc.get("facts") or "", rc.get("hindsight")
    if not setup.startswith(_OPENER):
        bad.append("THE SETUP must open with 'I always read the defense first.'")
    if rc.get("stage") != "PREGAME":
        if not facts.strip():
            bad.append("THE FACTS is missing")
        elif rc.get("stage") == "FINAL" and "Final:" not in facts:
            bad.append("THE FACTS must open with the final score")
        if not hind:
            bad.append("HINDSIGHT is missing")
        else:
            if hind.get("label") not in VERDICTS:
                bad.append(f"verdict '{hind.get('label')}' is not in the closed set")
            if rc.get("stage") == "FINAL" and hind.get("label") in ("EARLY CASH", "EARLY KILL"):
                bad.append("a final report cannot carry an early verdict")
    if rc.get("word_count", 0) < MIN_WORDS:
        bad.append(f"under the {MIN_WORDS}-word floor ({rc.get('word_count', 0)})")
    feats = (rc.get("features") or {}).get("legs") or []
    has_td = any(l.get("market") in TD_MARKETS for l in feats)
    if has_td and "Coach's-call legs" not in setup:
        bad.append("a touchdown leg is on the slip but the coach's-call paragraph is missing")
    if has_td and rc.get("stage") == "FINAL" and rc.get("status") == "SETTLED_LOSS":
        missed_td = any(f.get("market") in TD_MARKETS and f.get("status") == "MISS" for f in (rc.get("features") or {}).get("facts") or [])
        if missed_td and (hind or {}).get("label") not in ("SHIT (TD GAMBLE)", "SHIT"):
            bad.append("a missed touchdown leg must grade SHIT (TD GAMBLE), never science")
    if has_td and rc.get("stage") == "FINAL" and rc.get("status") == "SETTLED_LOSS":
        if (rc.get("features") or {}).get("whatif") and "What-if:" not in ((hind or {}).get("line") or ""):
            bad.append("a lost slip with a touchdown leg must end HINDSIGHT with the What-if counterfactual")
    return bad


def audit_all() -> dict:
    saved = _load_json(_RECAPS_FILE)
    bad = {tid: a for tid, rc in saved.items() if (a := audit(rc))}
    return {"checked": len(saved), "compliant": len(saved) - len(bad), "violations": bad}

"""
TARGETS RULES PREDICTIONS -- the Targets board, Jimmy's own target line, and the second look.

Why targets lead: a target is an opportunity the quarterback chose to give. It is the most stable thing a
receiver (or a pass-catching back) produces week to week, it does not depend on the goal-line play call, and
it is where catches, yards and big plays come from. On Thursday 2026-10-01 CLE faced a top pass defense, and
the production came from the depth of Watson's receiving options: the second and third looks.

For every pass catcher this module builds:
  * JIMMY'S TARGET LINE   projected targets = team pass attempts (own volume blended with what the opponent
                          allows) x target share (60% last 3 games, 40% season) x how this defense treats the
                          position. Projected receptions and receiving yards follow from catch rate and yards per catch.
  * PROJ DIFF             projected receptions minus FanDuel's receptions line (or minus his own average when
                          no line is posted). The board is ordered by it: biggest projected breakout first,
                          the player the defense is projected to shut down last.
  * D RANK                the opponent's rank in targets allowed to his position (1 = fewest allowed = toughest).
  * BIG-PLAY THREAT       chance of at least one 20+ yard catch, from his 20+ catch rate per target (shrunk to
                          the position) and his projected targets.
  * TARGET POWER INDEX    0-100, the lead stat Jimmy weighs: share 35%, projected targets 20%, air-yards share /
                          WOPR 15%, big-play rate 15%, fantasy points per target 10%, share trend 5%.
  * TEAM TARGET TREE      the top five targets on his team, who the SECOND LOOK is and why, and how each pair's
                          weekly targets move together (they rise together) or trade off (one eats the other's).

Data: lake weeks plus any game this week the lake has not ingested yet, read from the Tank01 box score and
play-by-play (so Thursday's game counts on Friday).
"""
from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import data

CT = ZoneInfo("America/Chicago")
POS = ("WR", "TE", "RB")
CATCH_PRIOR = {"WR": 0.63, "TE": 0.72, "RB": 0.78}
TPI_WEIGHTS = {"share": 0.35, "proj": 0.20, "air": 0.15, "bigplay": 0.15, "fppt": 0.10, "trend": 0.05}
_cache: dict = {"at": 0.0, "board": None}
CACHE_SECONDS = 300


def _date_to_ts(date_str: str) -> float:
    """Convert 'YYYY-MM-DD' game date to UTC epoch. Returns 0 on parse failure."""
    try:
        from datetime import timezone
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def _f(x, d=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _season() -> str:
    return str(max(int(r["season"]) for r in data.load("schedule")))


# ---------------------------------------------------------------------------
# weekly logs: lake + games the lake has not ingested yet
# ---------------------------------------------------------------------------

def _weekly() -> dict[str, list[dict]]:
    season = _season()
    out: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in data.load("player_receiving_week"):
        if r["season"] != season or r.get("season_type", "REG") != "REG":
            continue
        out[r["player_id"]][int(r["week"])] = {
            "week": int(r["week"]), "team": r["team"], "opp": r["opponent_team"], "game_id": r.get("game_id", ""),
            "tgt": _f(r["targets"]), "rec": _f(r["receptions"]), "yds": _f(r["receiving_yards"]), "td": _f(r["receiving_tds"]),
            "air": _f(r["receiving_air_yards"], None), "yac": _f(r["receiving_yards_after_catch"], None),
            "air_share": _f(r["air_yards_share"], None), "wopr": _f(r["wopr"], None),
            "rec20": _f(r["receiving_20"]), "rec40": _f(r["receiving_40"]), "rec10": _f(r["receiving_10"]), "src": "lake"}
    for row in _unlake_games():
        out[row["pid"]].setdefault(row["week"], row)
    return {pid: [w[k] for k in sorted(w)] for pid, w in out.items()}


def _unlake_games() -> list[dict]:
    """Completed games (before today, Central) the lake has no receiving rows for: totals from the Tank01 box,
    big plays from the play-by-play. Each final game is fetched once and kept in lake/gold/nfl/high_production/."""
    try:
        import big_plays
        import tank01
    except Exception:
        return []
    season = _season()
    in_lake = {r.get("game_id") for r in data.load("player_receiving_week") if r["season"] == season}
    today = datetime.now(CT).date().isoformat()
    rows = []
    for g in data.load("schedule"):
        if g.get("game_type") != "REG" or g["game_id"] in in_lake or g.get("game_date", "9999") >= today:
            continue
        hp = big_plays.stored(g["game_id"])
        if (not hp or not hp.get("final") or "box" not in hp) and tank01.available():
            # Only hit Tank01 for recent games (< 72 h old) — older unlaked games skip to avoid burning quota
            from datetime import timezone
            game_age_h = (datetime.now(timezone.utc).timestamp() - _date_to_ts(g.get("game_date", ""))) / 3600
            if game_age_h < 72:
                hp = big_plays.record(g, ttl=3600)
        if not hp or "box" not in hp:
            continue
        for pid, bx in hp["box"].items():
            pb = hp["players"].get(pid, {})
            team = bx["team"]
            rows.append({"pid": pid, "week": int(g["week"]), "team": team,
                         "opp": g["away_team"] if g["home_team"] == team else g["home_team"], "game_id": g["game_id"],
                         "tgt": bx["tgt"], "rec": bx["rec"], "yds": bx["yds"], "td": bx["td"],
                         "air": None, "yac": None, "air_share": None, "wopr": None,
                         "rec20": pb.get("rec20", 0), "rec40": pb.get("rec40", 0), "rec10": pb.get("rec10", 0), "src": "tank01"})
    return rows


def _prior_tail() -> dict[str, list[dict]]:
    """Last season's closing games (up to 7 per player) from player_week_prior_tail.csv: the front of each L10."""
    out: dict[str, list[dict]] = defaultdict(list)
    for r in data.load("player_week_prior_tail"):
        out[r["player_id"]].append({
            "season": int(r["season"]), "week": int(r["week"]), "team": r["team"], "opp": r["opponent_team"], "game_id": r.get("game_id", ""),
            "tgt": _f(r["targets"]), "rec": _f(r["receptions"]), "yds": _f(r["receiving_yards"]), "td": _f(r["receiving_tds"]),
            "air": _f(r["receiving_air_yards"], None), "yac": _f(r["receiving_yards_after_catch"], None),
            "air_share": _f(r["air_yards_share"], None), "wopr": _f(r["wopr"], None),
            "rec20": _f(r["receiving_20"]), "rec40": _f(r["receiving_40"]), "rec10": _f(r["receiving_10"]),
            "ppr": _f(r["fantasy_points_ppr"]), "src": f"{r['season']}"})
    for pid in out:
        out[pid].sort(key=lambda w: w["week"])
    return out


def _lines() -> dict[tuple[str, str], dict]:
    """(player_id, market) -> FanDuel line for his NEXT game (recs / recyds)."""
    import bpl
    nxt = bpl.next_games()
    ids = {(data.normalize_name(d["name"]), d["team"]): pid for pid, d in data.player_dimension().items()}
    best: dict[tuple[str, str], dict] = {}
    for r in data.load("prop_line_rotowire"):
        if r.get("book_slug") != "fanduel" or r.get("market_slug") not in ("recs", "recyds") or not r.get("line"):
            continue
        g = nxt.get(r.get("team", ""))
        if not g or g["opp"] != (r.get("opponent") or "").lstrip("@"):
            continue
        pid = ids.get((data.normalize_name(r["player_name"]), r["team"]))
        if not pid:
            continue
        key = (pid, r["market_slug"])
        if key not in best or r.get("fetched_at_utc", "") > best[key]["at"]:
            best[key] = {"line": _f(r["line"]), "over": r.get("over_price_american"), "under": r.get("under_price_american"),
                         "at": r.get("fetched_at_utc", "")}
    return best


# ---------------------------------------------------------------------------
# the board
# ---------------------------------------------------------------------------

def _pct_rank(values: dict[str, float]) -> dict[str, float]:
    order = sorted(values, key=lambda k: values[k])
    n = len(order)
    return {k: (i / (n - 1) if n > 1 else 0.5) for i, k in enumerate(order)}


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3 or len(set(a)) < 2 or len(set(b)) < 2:
        return None
    return round(statistics.correlation(a, b), 2)


def build() -> dict:
    import bpl
    logs = _weekly()
    prior = _prior_tail()
    season_now = int(_season())
    dim = data.player_dimension()
    nxt = bpl.next_games()
    lines = _lines()

    # team totals per (team, week) and pass attempts
    team_tgt: dict[tuple[str, int], float] = defaultdict(float)
    for pid, ws in logs.items():
        for w in ws:
            team_tgt[(w["team"], w["week"])] += w["tgt"]
    att: dict[str, list[float]] = defaultdict(list)          # team -> pass attempts per game (targets as the proxy)
    att_allowed: dict[str, list[float]] = defaultdict(list)  # defense -> targets it faced per game
    opp_of: dict[tuple[str, int], str] = {}
    for pid, ws in logs.items():
        for w in ws:
            opp_of[(w["team"], w["week"])] = w["opp"]
    for (team, wk), t in team_tgt.items():
        att[team].append(t)
        if (team, wk) in opp_of:
            att_allowed[opp_of[(team, wk)]].append(t)
    league_att = statistics.mean(v for vs in att.values() for v in vs) if att else 32.0

    # targets each defense allowed to each position, per game
    pos_allowed: dict[tuple[str, str], dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for pid, ws in logs.items():
        p = dim.get(pid, {}).get("position", "")
        if p in POS:
            for w in ws:
                pos_allowed[(w["opp"], p)][w["week"]] += w["tgt"]
    pos_avg = {}
    for p in POS:
        vals = [statistics.mean(d.values()) for (t, pp), d in pos_allowed.items() if pp == p and d]
        pos_avg[p] = statistics.mean(vals) if vals else 1.0
    d_rank: dict[str, dict[str, int]] = {}
    for p in POS:
        per = {t: statistics.mean(d.values()) for (t, pp), d in pos_allowed.items() if pp == p and d}
        d_rank[p] = {t: i + 1 for i, t in enumerate(sorted(per, key=lambda t: per[t]))}
        d_rank[p + "_val"] = per          # type: ignore[assignment]

    # position priors for big plays and fantasy per target
    pos_tot: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])   # tgt, rec, rec20, yds
    for pid, ws in logs.items():
        p = dim.get(pid, {}).get("position", "")
        if p in POS:
            for w in ws:
                t = pos_tot[p]; t[0] += w["tgt"]; t[1] += w["rec"]; t[2] += w["rec20"]; t[3] += w["yds"]
    bp_prior = {p: (v[2] / v[0] if v[0] else 0.05) for p, v in pos_tot.items()}
    ypr_prior = {p: (v[3] / v[1] if v[1] else 10.0) for p, v in pos_tot.items()}

    sched = {r["game_id"]: r for r in data.load("schedule")}
    try:
        import boo_desk
        now = datetime.now(CT)
        espn = {boo_desk._lake_id(g): g for g in boo_desk._games("NFL", now - boo_desk.timedelta(days=1), 8)}
    except Exception:
        espn = {}
    try:
        pass_rank, rush_rank = bpl.defense_ranks("pass_yds"), bpl.defense_ranks("rush_yds")
    except Exception:
        pass_rank, rush_rank = {}, {}

    def game_lines(team: str) -> dict | None:
        g = nxt.get(team)
        s = sched.get(g["gameId"]) if g else None
        if not s:
            return None
        home = s["home_team"] == team
        spread = _f(s.get("spread_line"), None)          # nflverse: positive = home favoured by that many
        out = {"gameId": s["game_id"], "date": s.get("game_date"), "weekday": s.get("weekday"), "time": s.get("game_time_local"),
               "home": s["home_team"], "away": s["away_team"], "source": "schedule",
               "spread": (None if spread is None else (-spread if home else spread)),
               "total": _f(s.get("total_line"), None),
               "ml": s.get("home_moneyline") if home else s.get("away_moneyline"),
               "oppMl": s.get("away_moneyline") if home else s.get("home_moneyline")}
        if out["total"] is None:                         # the schedule has no line yet: take ESPN's current one
            e = espn.get(f"{s['away_team']}_{s['home_team']}")
            if e:
                me, them = (e["home"], e["away"]) if home else (e["away"], e["home"])
                out.update(source="ESPN", total=_f(e.get("total"), None), spread=_f(me.get("spread"), None),
                           ml=me.get("ml"), oppMl=them.get("ml"))
        return out

    rows = []
    for pid, ws in logs.items():
        d = dim.get(pid, {})
        p = d.get("position", "")
        if p not in POS or not ws:
            continue
        team = ws[-1]["team"]
        games = [w for w in ws if w["team"] == team]
        n = len(games)
        tgts = [w["tgt"] for w in games]
        if n == 0 or sum(tgts) < 3:
            continue
        shares = [w["tgt"] / team_tgt[(team, w["week"])] for w in games if team_tgt[(team, w["week"])]]
        share_season = statistics.mean(shares) if shares else 0.0
        share_l3 = statistics.mean(shares[-3:]) if shares else 0.0
        share_blend = 0.6 * share_l3 + 0.4 * share_season
        g = nxt.get(team)
        opp = g["opp"] if g else None
        team_att = statistics.mean(att[team]) if att[team] else league_att
        opp_att = statistics.mean(att_allowed[opp]) if opp and att_allowed[opp] else league_att
        vol = 0.5 * team_att + 0.5 * opp_att
        pos_f = 1.0
        if opp and opp in d_rank[p + "_val"]:                              # type: ignore[operator]
            raw = d_rank[p + "_val"][opp] / pos_avg[p] if pos_avg[p] else 1.0   # type: ignore[index]
            wgt = len(pos_allowed[(opp, p)]) / (len(pos_allowed[(opp, p)]) + 3)
            pos_f = 1 + (raw - 1) * wgt
        proj_tgt = vol * share_blend * pos_f
        tot_t, tot_r, tot_y = sum(tgts), sum(w["rec"] for w in games), sum(w["yds"] for w in games)
        catch = (tot_r + 10 * CATCH_PRIOR[p]) / (tot_t + 10)
        ypr = (tot_y + 5 * ypr_prior.get(p, 10)) / (tot_r + 5) if tot_r + 5 else 10.0
        proj_rec = proj_tgt * catch
        proj_yds = proj_rec * ypr
        for w in games:
            w.setdefault("season", season_now)
        l10 = (prior.get(pid, []) + games)[-10:]
        rec20 = sum(w["rec20"] for w in games)
        # big-play potential rides the L10 high-production trend (last season's close counts until it rolls off)
        t10, b10 = sum(w["tgt"] for w in l10), sum(w["rec20"] for w in l10)
        bp_rate = (b10 + 0.3 * bp_prior.get(p, 0.05) * 10) / (t10 + 3)
        bp_threat = 1 - math.exp(-proj_tgt * bp_rate)
        first, last = l10[:-5], l10[-5:]
        pg = lambda ws: (sum(w["rec20"] for w in ws) / len(ws)) if ws else None   # noqa: E731
        trend = "rising" if first and pg(last) > pg(first) + 0.15 else "cooling" if first and pg(last) < pg(first) - 0.15 else "steady"
        air = [w["air_share"] for w in games if w["air_share"] is not None]
        wopr = [w["wopr"] for w in games if w["wopr"] is not None]
        airs = [w["air"] for w in games if w["air"] is not None]
        tgt_air = sum(w["tgt"] for w in games if w["air"] is not None)
        try:
            import fantasy
            fl = {x["week"]: x["ppr"] for x in (fantasy._logs().get(pid) or [])}
        except Exception:
            fl = {}
        fp = sum(fl.get(w["week"], 0.0) for w in games)
        line = lines.get((pid, "recs"))
        yline = lines.get((pid, "recyds"))
        avg_rec = tot_r / n
        diff = proj_rec - line["line"] if line else proj_rec - avg_rec
        base = line["line"] if line else avg_rec
        # hit rates against the line he faces now (or his own average when no line is posted)
        th = line["line"] if line else avg_rec
        hits = [1 if w["rec"] > th else 0 for w in games]
        h10 = [1 if w["rec"] > th else 0 for w in l10]
        streak = 0
        for h in reversed(h10):
            if not h:
                break
            streak += 1
        vs = [w for w in prior.get(pid, []) + games if w["opp"] == opp]
        rows.append({
            "playerId": pid, "name": d.get("name", pid), "team": team, "pos": p, "opp": opp, "home": bool(g and g["home"]),
            "games": n, "photoUrl": data.photo_url(pid),
            "tgtPerGame": round(tot_t / n, 1), "recPerGame": round(avg_rec, 1), "ydsPerGame": round(tot_y / n, 1),
            "shareSeason": round(share_season, 3), "shareL3": round(share_l3, 3), "shareTrend": round(share_l3 - share_season, 3),
            "airShare": round(statistics.mean(air), 3) if air else None, "wopr": round(statistics.mean(wopr), 3) if wopr else None,
            "adot": round(sum(airs) / tgt_air, 1) if tgt_air else None, "catchRate": round(tot_r / tot_t, 3) if tot_t else None,
            "bigPlays": int(rec20), "bigPlays40": int(sum(w["rec40"] for w in games)), "bigPlayRate": round(rec20 / tot_t, 3) if tot_t else 0,
            "fpPerTarget": round(fp / tot_t, 2) if tot_t and fl else None,
            "projTargets": round(proj_tgt, 1), "projRec": round(proj_rec, 1), "projYds": round(proj_yds, 1),
            "teamVolume": round(vol, 1), "posFactor": round(pos_f, 3),
            "line": line["line"] if line else None, "over": line["over"] if line else None, "under": line["under"] if line else None,
            "ydsLine": yline["line"] if yline else None,
            "projDiff": round(diff, 2), "projDiffPct": round(diff / base, 3) if base else 0.0, "lineBasis": "FanDuel" if line else "his average",
            "dRank": d_rank[p].get(opp) if opp else None, "dAllowed": round(d_rank[p + "_val"].get(opp, 0), 1) if opp else None,   # type: ignore[union-attr]
            "streak": streak, "game": game_lines(team),
            "oppPassRank": pass_rank.get(opp) if opp else None, "oppRushRank": rush_rank.get(opp) if opp else None,
            "hit": {"season": round(sum(hits) / n, 2), "l10": round(statistics.mean(h10), 2), "l10n": len(h10),
                    "l5": round(statistics.mean(h10[-5:]), 2), "l3": round(statistics.mean(h10[-3:]), 2),
                    "vsOpp": round(statistics.mean(1 if w["rec"] > th else 0 for w in vs), 2) if vs else None, "vsOppN": len(vs)},
            "bigPlayThreat": round(bp_threat, 3), "bigPlaysL10": int(b10), "bigTrend": trend,
            "priorGames": len([w for w in l10 if w.get("season") != season_now]),
            "rookie": len(prior.get(pid, [])) == 0,
            "log": [{"season": w.get("season", season_now), "week": w["week"], "team": w["team"], "opp": w["opp"], "tgt": int(w["tgt"]),
                     "rec": int(w["rec"]), "yds": int(w["yds"]), "big": int(w["rec20"]), "src": w["src"]} for w in l10],
        })

    # Target Power Index: percentile blend
    if rows:
        pr = {k: _pct_rank({r["playerId"]: v(r) for r in rows}) for k, v in {
            "share": lambda r: 0.6 * r["shareL3"] + 0.4 * r["shareSeason"],
            "proj": lambda r: r["projTargets"],
            "air": lambda r: r["wopr"] if r["wopr"] is not None else r["shareSeason"],
            "bigplay": lambda r: r["bigPlayRate"],
            "fppt": lambda r: r["fpPerTarget"] or 0.0,
            "trend": lambda r: r["shareTrend"]}.items()}
        for r in rows:
            r["tpi"] = round(100 * sum(TPI_WEIGHTS[k] * pr[k][r["playerId"]] for k in TPI_WEIGHTS))
    # NFL rank and team trees
    for i, r in enumerate(sorted(rows, key=lambda r: -r["tgtPerGame"])):
        r["nflRank"] = i + 1
    by_team: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_team[r["team"]].append(r)
    trees = {}
    for team, rs in by_team.items():
        rs.sort(key=lambda r: -(0.6 * r["shareL3"] + 0.4 * r["shareSeason"]))
        pos_count: dict[str, int] = defaultdict(int)
        for i, r in enumerate(rs):
            r["teamRank"] = i + 1
            pos_count[r["pos"]] += 1
            r["role"] = f"{r['pos']}{pos_count[r['pos']]}"
            r["look"] = ["FIRST LOOK", "SECOND LOOK", "THIRD LOOK"][i] if i < 3 else None
        top5 = rs[:5]
        weeks = sorted({w["week"] for r in top5 for w in r["log"]})
        series = {r["playerId"]: [next((w["tgt"] for w in r["log"] if w["week"] == wk), 0.0) for wk in weeks] for r in top5}
        pairs = []
        for i in range(len(top5)):
            for j in range(i + 1, len(top5)):
                a, b = top5[i], top5[j]
                c = _pearson(series[a["playerId"]], series[b["playerId"]])
                pairs.append({"a": a["name"], "b": b["name"], "r": c, "games": len(weeks),
                              "read": ("too few games" if c is None else "rise together" if c >= 0.4 else "trade off" if c <= -0.4 else "independent")
                                      + (" (early read)" if c is not None and len(weeks) < 6 else "")})
        trees[team] = {"team": team, "top": [{k: r[k] for k in ("playerId", "name", "pos", "role", "look", "teamRank", "nflRank",
                                                                 "tgtPerGame", "shareSeason", "shareL3", "bigPlays", "tpi", "projTargets")} for r in top5],
                       "secondLook": _second_look(top5), "pairs": pairs}
    for r in rows:
        r["teamTree"] = trees[r["team"]]
        r["flag"] = ("RB TARGETS" if r["pos"] == "RB" and r["teamRank"] <= 4
                     else "SECOND LOOK" if r["teamRank"] in (2, 3) else None)
    # biggest projected breakout (receptions over the line) first, the player the defense shuts down last
    rows.sort(key=lambda r: -r["projDiff"])
    for r in rows:
        r["regular"] = r["tgtPerGame"] >= 3 or r["line"] is not None
    return {"builtAt": datetime.now(CT).isoformat(), "week": next((g["week"] for g in nxt.values()), None),
            "rows": rows, "teams": trees,
            "method": "Jimmy's target line: team volume x 60/40 recent/season target share x the defense's treatment of the position. "
                      "Ordered by projected receptions over the FanDuel line (or his average when no line is posted)."}


def _second_look(top: list[dict]) -> dict | None:
    if len(top) < 2:
        return None
    a, b = top[0], top[1]
    why = [f"{round(b['shareSeason'] * 100)}% of the team's targets ({b['tgtPerGame']} a game), #{b['nflRank']} in the NFL"]
    if b["shareTrend"] >= 0.03:
        why.append(f"his share is climbing ({round(b['shareL3'] * 100)}% over the last 3)")
    if b["bigPlays"]:
        why.append(f"{b['bigPlays']} catch{'es' if b['bigPlays'] != 1 else ''} of 20+ yards")
    if b.get("adot"):
        why.append(f"{b['adot']} air yards per target")
    if a.get("dRank") and a["dRank"] <= 8:
        why.append(f"and {a['name']} draws a top-8 defense against his position this week, so the overflow runs to the second look")
    return {"name": b["name"], "playerId": b["playerId"], "pos": b["pos"], "behind": a["name"],
            "why": f"{b['name']} is the second look behind {a['name']}: " + ", ".join(why) + "."}


def board(force: bool = False) -> dict:
    if force or _cache["board"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
        _cache["board"], _cache["at"] = build(), time.time()
    return _cache["board"]


def player(pid: str) -> dict | None:
    return next((r for r in board()["rows"] if r["playerId"] == pid), None)


def signal(pid: str) -> float | None:
    """Target Power Index as a 0..1 signal for Jimmy (the lead-weighted component on catch markets)."""
    r = player(pid)
    return r["tpi"] / 100 if r and r.get("tpi") is not None else None


def digest() -> dict:
    """What Jimmy knows about targets right now, condensed for MY BOO's node."""
    b = board()
    reg = [r for r in b["rows"] if r["regular"]]
    pick = lambda r: {k: r[k] for k in ("name", "team", "role", "opp", "line", "projRec", "projDiff", "projTargets", "dRank", "tpi", "bigPlayThreat")}  # noqa: E731
    return {"builtAt": b["builtAt"], "week": b["week"], "players": len(b["rows"]),
            "breakouts": [pick(r) for r in reg[:10]], "shutDowns": [pick(r) for r in reg[-5:][::-1]],
            "rbTargets": [pick(r) for r in reg if r["flag"] == "RB TARGETS"][:8],
            "secondLooks": {t: v["secondLook"]["why"] for t, v in sorted(b["teams"].items()) if v.get("secondLook")},
            "method": b["method"]}

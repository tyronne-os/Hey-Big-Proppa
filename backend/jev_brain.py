"""
JEV BRAIN -- the scouting file JEV reads before every prop or game call.

Each read hands JEV the same evidence a sharp handicapper would pull, from the lake and live ESPN:

  player     form (L5, season), the BPL projection, target share, dependability ranking (usage role,
             share when the game is tight vs calm), depth rank, red-zone role, big-play counts
  defense    rank and allowance vs this exact stat, IB category, and HOW it gets scored on
             (touchdown transcripts: pass/rush split, 20+ yard scores, red zone, late game)
  offense    how the team scores (same transcripts), points, red zone and third-down rates, recent form
  injuries   status of each side's QB1, RB1, WR1, WR2 and TE1 -- ESPN's live report first, the official
             lake report as a fallback
  game       ESPN spread / total / implied team totals, home or away, rest days, roof and weather,
             division game and division standings, both head coaches and their history against each other

Nothing here is a probability. JEV forms the opinion; jev_ledger grades it against ESPN finals.
HARD RULE: touchdown-scorer props are never asked about. Touchdown transcripts are context only.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import bpl
import data
import h2h

SEASON = "2026"
_cached = h2h._cached


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _r(v, n=1):
    return None if v is None else round(v, n)


# ---------------------------------------------------------------------------
# Team intelligence
# ---------------------------------------------------------------------------

def _td_profiles() -> dict[str, dict]:
    """team -> {'off': ..., 'def': ...} built from this season's touchdown transcripts."""
    def build():
        games = defaultdict(set)
        for r in data.load("team_game_stats"):
            if r.get("season") == SEASON:
                games[r["team"]].add(r["game_id"])
        acc: dict[str, dict] = defaultdict(lambda: {"off": defaultdict(int), "def": defaultdict(int), "offPlays": [], "defPlays": []})
        rows = sorted((r for r in data.load("td_log") if r.get("season") == SEASON and r.get("season_type", "REG") == "REG"),
                      key=lambda r: (int(r.get("week") or 0), r.get("play_id", "")))
        for r in rows:
            for team, side in ((r.get("scoring_team"), "off"), (r.get("defense_team"), "def")):
                if not team:
                    continue
                a = acc[team][side]
                a["tds"] += 1
                a[r.get("td_type") or "other"] += 1
                if r.get("td_type") in ("pass", "rush") and (_f(r.get("yardline_100"), 0) or 0) >= 20:
                    a["big"] += 1
                if r.get("is_red_zone") in ("1", "True", "true"):
                    a["rz"] += 1
                if (_f(r.get("qtr"), 0) or 0) >= 4:
                    a["late"] += 1
                desc = (r.get("play_description") or "").split(") ", 1)[-1][:120]
                acc[team][f"{side}Plays"].append(f"wk{r.get('week')} vs {r.get('defense_team') if side == 'off' else r.get('scoring_team')}: {desc}")
        out = {}
        for team, a in acc.items():
            g = max(len(games.get(team, ())), 1)
            prof = {}
            for side in ("off", "def"):
                s = a[side]
                n = s["tds"] or 1
                prof[side] = {"tdsPerGame": round(s["tds"] / g, 2), "passTdPct": round(100 * s["pass"] / n), "rushTdPct": round(100 * s["rush"] / n),
                              "bigPlayTds20plus": s["big"], "redZoneTds": s["rz"], "fourthQuarterTds": s["late"],
                              "recentScores": a[f"{side}Plays"][-3:]}
            out[team] = prof
        return out
    return _cached("brain:td", 600, build)


def _team_table() -> dict[str, dict]:
    import heatmap
    return _cached("brain:teams", 600, heatmap._team_table)


def _season_rows() -> list[dict]:
    return [r for r in data.load("schedule") if r.get("season") == SEASON and r.get("game_type") == "REG"]


def _records() -> dict[str, dict]:
    """Current-season W-L, division W-L, ATS and over/under records from the lake schedule."""
    def build():
        div_of = {t: d for d, ts in _divisions().items() for t in ts}
        rec: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "dw": 0, "dl": 0, "ats_w": 0, "ats_l": 0, "over": 0, "under": 0, "margins": []})
        for g in sorted(_season_rows(), key=lambda r: int(r["week"])):
            hs, as_ = _f(g.get("home_score")), _f(g.get("away_score"))
            if hs is None or as_ is None:
                continue
            sp, tl = _f(g.get("spread_line")), _f(g.get("total_line"))
            for team, pf, pa, home in ((g["home_team"], hs, as_, True), (g["away_team"], as_, hs, False)):
                r = rec[team]
                r["w" if pf > pa else "l" if pf < pa else "t"] += 1
                r["margins"].append(int(pf - pa))
                if div_of.get(g["home_team"]) == div_of.get(g["away_team"]):
                    r["dw" if pf > pa else "dl"] += 1 if pf != pa else 0
                if sp is not None:
                    cover = (hs - as_ > sp) if home else (as_ - hs > -sp)
                    push = (hs - as_ == sp)
                    if not push:
                        r["ats_w" if cover else "ats_l"] += 1
                if tl is not None and hs + as_ != tl:
                    r["over" if hs + as_ > tl else "under"] += 1
        return dict(rec)
    return _cached("brain:records", 600, build)


def _divisions() -> dict[str, list[str]]:
    import leaders
    return leaders.DIVISIONS


def division(team: str) -> dict:
    recs = _records()
    for name, teams in _divisions().items():
        if team in teams:
            table = sorted(teams, key=lambda t: (-(recs.get(t, {}).get("w", 0) - recs.get(t, {}).get("l", 0)), t))
            return {"name": name, "standings": [f"{t} {recs.get(t, {}).get('w', 0)}-{recs.get(t, {}).get('l', 0)}" for t in table],
                    "place": table.index(team) + 1}
    return {}


def team_brief(team: str) -> dict:
    t = _team_table().get(team, {})
    rec = _records().get(team, {})
    td = _td_profiles().get(team, {})
    return {
        "record": f"{rec.get('w', 0)}-{rec.get('l', 0)}" + (f"-{rec['t']}" if rec.get("t") else ""),
        "divisionRecord": f"{rec.get('dw', 0)}-{rec.get('dl', 0)}", "atsRecord": f"{rec.get('ats_w', 0)}-{rec.get('ats_l', 0)}",
        "overUnderRecord": f"{rec.get('over', 0)} over / {rec.get('under', 0)} under", "lastMargins": rec.get("margins", [])[-3:],
        "pointsPerGame": _r(t.get("pf")), "pointsAllowedPerGame": _r(t.get("pa")),
        "passYdsPerGame": _r(t.get("pass_ypg")), "rushYdsPerGame": _r(t.get("rush_ypg")),
        "turnoversPerGame": _r(t.get("turnovers_pg"), 2), "thirdDownPct": _r(t.get("third_pct")), "oppThirdDownPct": _r(t.get("opp_third_pct")),
        "redZoneTdPct": _r(t.get("rz_pct")), "oppRedZoneTdPct": _r(t.get("opp_rz_pct")), "secondHalfPointsAllowedPerGame": _r(t.get("sh_pg")),
        "howTheyScore": td.get("off"), "howTheyGetScoredOn": td.get("def"),
    }


def coach_matchup(away: str, home: str) -> dict:
    """Both head coaches this week and every regular-season or playoff meeting between them since 1999."""
    def build():
        row = next((g for g in _season_rows() if {g["home_team"], g["away_team"]} == {home, away} and g.get("home_score") in ("", None)), None)
        if not row:
            return {}
        ca, ch = row.get("away_coach", ""), row.get("home_coach", "")
        meet = []
        for g in data.load("schedule"):
            if {g.get("away_coach"), g.get("home_coach")} == {ca, ch} and ca != ch and g.get("home_score") not in ("", None):
                hs, as_ = int(_f(g["home_score"], 0)), int(_f(g["away_score"], 0))
                winner = g["home_coach"] if hs > as_ else g["away_coach"] if as_ > hs else "tie"
                meet.append({"season": g["season"], "winner": winner, "total": hs + as_, "score": f"{g['away_team']} {as_} @ {g['home_team']} {hs}"})
        meet.sort(key=lambda m: m["season"])
        wins = {c: sum(1 for m in meet if m["winner"] == c) for c in (ca, ch)}
        return {"awayCoach": ca, "homeCoach": ch, "meetings": len(meet), "wins": wins,
                "avgTotalInMeetings": round(sum(m["total"] for m in meet) / len(meet), 1) if meet else None, "lastMeetings": meet[-3:],
                "divisionGame": row.get("div_game") == "1", "awayRestDays": _f(row.get("away_rest")), "homeRestDays": _f(row.get("home_rest")),
                "roof": row.get("roof"), "surface": row.get("surface"), "lakeGameId": row.get("game_id"), "espnId": row.get("espn")}
    return _cached(f"brain:coach:{away}@{home}", 1800, build)


# ---------------------------------------------------------------------------
# Key players and injuries (ESPN live, lake fallback)
# ---------------------------------------------------------------------------

ROLES = (("QB", 1, "QB1"), ("RB", 1, "RB1"), ("WR", 1, "WR1"), ("WR", 2, "WR2"), ("TE", 1, "TE1"))


def _depth(team: str) -> dict[str, dict]:
    def build():
        nxt = bpl.next_games().get(team)
        rows = [r for r in data.load("depth_chart_pregame") if r.get("team") == team]
        if nxt:
            mine = [r for r in rows if r.get("game_id") == nxt["gameId"]]
            rows = mine or rows
        if not rows:
            return {}
        latest = max(r.get("snapshot_at", "") for r in rows)
        rows = [r for r in rows if r.get("snapshot_at", "") == latest]
        out = {}
        for pos, rank, role in ROLES:
            hit = next((r for r in rows if r.get("pos_abb") == pos and r.get("pos_rank") == str(rank)), None)
            if hit:
                out[role] = {"playerId": hit.get("player_id"), "name": hit.get("player_name")}
        return out
    return _cached(f"brain:depth:{team}", 900, build)


def _official_status(team: str) -> dict[str, str]:
    def build():
        rows = [r for r in data.load("injury_report_official") if r.get("team") == team and r.get("season") == SEASON]
        if not rows:
            return {}
        wk = max(int(r.get("week") or 0) for r in rows)
        return {data.normalize_name(r.get("full_name", "")): r.get("report_status") for r in rows if int(r.get("week") or 0) == wk and r.get("report_status")}
    return _cached(f"brain:inj:{team}", 900, build)


def key_injuries(team: str) -> dict:
    """{'QB1': 'Josh Allen: healthy', 'WR1': 'X: Questionable (hamstring)', ...} for one team."""
    g = h2h.game_for_team(team)
    live = h2h._injuries(g["id"]) if g else {}
    off = _official_status(team)
    out, flagged = {}, []
    for role, p in _depth(team).items():
        nm = data.normalize_name(p["name"] or "")
        if nm in live:
            st = f"{live[nm]['status']}" + (f" ({live[nm]['detail']})" if live[nm].get("detail") else "")
        elif nm in off:
            st = f"{off[nm]} (official report)"
        else:
            st = "healthy"
        out[role] = f"{p['name']}: {st}"
        if st != "healthy":
            flagged.append(role)
    return {"keyPlayers": out, "flagged": flagged, "source": "ESPN injury report" if live else "official lake report"}


# ---------------------------------------------------------------------------
# Player intelligence
# ---------------------------------------------------------------------------

def _usage(pid: str) -> dict:
    row = _cached("brain:usage", 900, lambda: {r["player_id"]: r for r in data.load("player_usage") if r.get("season") == SEASON}).get(pid)
    if not row:
        return {}
    return {"dependabilityRanking": (row.get("usage_role") or "").title(), "usageIndex": _f(row.get("usage_index_score")),
            "shareOverall": _f(row.get("share_overall")), "shareWhenGameIsTight": _f(row.get("share_stress")), "shareWhenGameIsCalm": _f(row.get("share_calm")),
            "trustDeltaUnderPressure": _f(row.get("confidence_delta")), "depth": row.get("depth_pos"), "usageRankOnTeam": row.get("usage_rank_on_team"),
            "redZoneScore": _f(row.get("redzone_score"))}


def _targets(pid: str, team: str) -> dict:
    def team_targets():
        out: dict[tuple, float] = {}
        for r in data.load("team_week"):
            if r.get("season") == SEASON:
                out[(r["team"], int(r["week"]))] = _f(r.get("targets"), 0.0) or 0.0
        return out
    tt = _cached("brain:teamtgt", 900, team_targets)
    rows = [r for r in h2h._hist("player_receiving_week", "targets").get(pid, [])]
    if not rows:
        return {}
    l5 = rows[-5:]
    team_l5 = sum(tt.get((r["team"], r["week"]), 0) for r in l5)
    team_all = sum(tt.get((r["team"], r["week"]), 0) for r in rows)
    return {"targetsL5": [int(r["value"]) for r in l5], "targetShareL5Pct": round(100 * sum(r["value"] for r in l5) / team_l5, 1) if team_l5 else None,
            "targetShareSeasonPct": round(100 * sum(r["value"] for r in rows) / team_all, 1) if team_all else None}


def _big_plays(pid: str) -> dict:
    rec20 = sum(r["value"] for r in h2h._hist("player_receiving_week", "receiving_20").get(pid, []))
    rush20 = sum(r["value"] for r in h2h._hist("player_rushing_week", "rushing_20").get(pid, []))
    return {"catches20plusYds": int(rec20), "runs20plusYds": int(rush20)}


STAT_WORD = {"rushyds": "rushing yards", "recyds": "receiving yards", "recs": "receptions", "passyds": "passing yards"}


def prop_state(pid: str, name: str, team: str, market: str, line: float) -> dict | None:
    if market not in bpl.NFL_MARKETS:
        return None

    def build():
        b = bpl.nfl_player_line(pid, market, name, team)
        opp = b.get("nextOpp")
        if not opp:
            return None
        _, _, cat = bpl.NFL_MARKETS[market]
        hist = bpl._player_history(market).get(pid, [])
        vals = [h["value"] for h in hist]
        dim = data.player_dimension().get(pid, {})
        g = h2h.game_for_team(team)
        ln = (g or {}).get("lines") or {}
        cm = coach_matchup(opp, team) if not b.get("nextOppHome") else coach_matchup(team, opp)
        own = key_injuries(team)
        their = key_injuries(opp)
        role = next((r for r, p in _depth(team).items() if p.get("playerId") == pid), None)
        own_qb_note = None
        if market in ("recyds", "recs") and "QB1" in own["flagged"]:
            own_qb_note = "His starting QB is on the injury report."
        return {
            "player": {"name": name, "team": team, "position": dim.get("position", ""), "depthRole": role,
                       "last5": [{"week": h["week"], "opp": h["opp"], STAT_WORD[market]: h["value"]} for h in hist[-5:]],
                       "seasonAvg": _r(sum(vals) / len(vals)) if vals else None, "gamesThisSeason": len(vals),
                       "bigProppaProjection": b.get("bpl"), **_usage(pid), **(_targets(pid, team) if market in ("recyds", "recs") else {}), **_big_plays(pid)},
            "opponentDefense": {"team": opp, f"rankVs{cat}": b.get("nextOppRank"), "rankNote": "1 = stingiest of 32",
                                "allowedPerGameVsThisStat": _r(bpl._opp_allowed_blend(opp, cat)), **{k: v for k, v in team_brief(opp).items() if k in (
                                    "pointsAllowedPerGame", "oppRedZoneTdPct", "oppThirdDownPct", "secondHalfPointsAllowedPerGame", "howTheyGetScoredOn", "record")}},
            "ownOffense": {k: v for k, v in team_brief(team).items() if k in ("pointsPerGame", "passYdsPerGame", "rushYdsPerGame", "redZoneTdPct", "thirdDownPct", "turnoversPerGame", "howTheyScore", "record", "lastMargins")},
            "injuries": {"ownTeam": own["keyPlayers"], "opponent": their["keyPlayers"], "note": own_qb_note, "source": own["source"]},
            "game": {"home": bool(b.get("nextOppHome")), "spreadForHisTeam": None if ln.get("spreadHome") is None else (ln["spreadHome"] if g and team == g["home"]["abbr"] else -ln["spreadHome"]),
                     "total": ln.get("total"), "impliedTeamTotal": (ln.get("implied") or {}).get(team), "weather": (g or {}).get("weather"), "indoors": bool((g or {}).get("indoor")) or cm.get("roof") in ("dome", "closed"),
                     "divisionGame": cm.get("divisionGame"), "division": division(team), "coaches": {k: cm.get(k) for k in ("awayCoach", "homeCoach", "meetings", "wins", "avgTotalInMeetings")},
                     "restDays": cm.get("homeRestDays") if b.get("nextOppHome") else cm.get("awayRestDays")},
        }
    base = _cached(f"brain:prop:{pid}:{market}", 600, build)
    if not base:
        return None
    vals = [x[STAT_WORD[market]] for x in base["player"]["last5"]]
    return {**base, "question": {"stat": STAT_WORD[market], "line": line,
                                 "last5OverThisLine": f"{sum(1 for v in vals if v > line)} of {len(vals)}"}}


def game_state(away: str, home: str) -> dict:
    def build():
        g = next((x for x in h2h.slate()["games"] if x["away"]["abbr"] == away and x["home"]["abbr"] == home), None)
        ln = (g or {}).get("lines") or {}
        model = next((m for m in bpl.nfl_game_totals() if m["home"] == home and m["away"] == away), None)
        cm = coach_matchup(away, home)
        return {
            "game": {"away": away, "home": home, "spreadHome": ln.get("spreadHome"), "total": ln.get("total"), "impliedPoints": ln.get("implied"),
                     "moneyline": {"away": ln.get("mlAway"), "home": ln.get("mlHome")}, "lineMoveSinceOpen": {"spread": ln.get("spreadMove"), "total": ln.get("totalMove")},
                     "bigProppaProjection": {"home": model.get("homePoints"), "away": model.get("awayPoints")} if model else None,
                     "weather": (g or {}).get("weather"), "indoors": bool((g or {}).get("indoor")) or cm.get("roof") in ("dome", "closed"), "roof": cm.get("roof"), "surface": cm.get("surface"),
                     "divisionGame": cm.get("divisionGame"), "restDays": {"away": cm.get("awayRestDays"), "home": cm.get("homeRestDays")},
                     "coaches": {k: cm.get(k) for k in ("awayCoach", "homeCoach", "meetings", "wins", "avgTotalInMeetings", "lastMeetings")}},
            "away": {**team_brief(away), "division": division(away), "keyInjuries": key_injuries(away)["keyPlayers"]},
            "home": {**team_brief(home), "division": division(home), "keyInjuries": key_injuries(home)["keyPlayers"]},
        }
    return _cached(f"brain:game:{away}@{home}", 600, build)


def factors(state: dict | None) -> list[str]:
    """Short human-readable list of what JEV weighed -- shown next to its read on the ticket builder."""
    if not state:
        return []
    out = []
    p, d, inj, g = state.get("player", {}), state.get("opponentDefense", {}), state.get("injuries", {}), state.get("game", {})
    if p.get("dependabilityRanking"):
        out.append(f"Dependability: {p['dependabilityRanking']}" + (f", {p['shareWhenGameIsTight']:.0%} share when tight" if isinstance(p.get("shareWhenGameIsTight"), float) and p["shareWhenGameIsTight"] <= 1 else ""))
    if p.get("targetShareL5Pct") is not None:
        out.append(f"Target share L5: {p['targetShareL5Pct']}%")
    rank = next((v for k, v in d.items() if k.startswith("rankVs")), None)
    if rank:
        out.append(f"{d.get('team')} defense ranks {rank} of 32 vs this stat, allows {d.get('allowedPerGameVsThisStat')}/game")
    hs = d.get("howTheyGetScoredOn") or {}
    if hs:
        out.append(f"{d.get('team')} gives up {hs.get('tdsPerGame')} TDs/game ({hs.get('passTdPct')}% passing, {hs.get('bigPlayTds20plus')} from 20+ yds)")
    flagged = [f"{k} {v}" for k, v in (inj.get("ownTeam") or {}).items() if "healthy" not in v] + [f"opp {k} {v}" for k, v in (inj.get("opponent") or {}).items() if "healthy" not in v]
    if flagged:
        out.append("Injuries: " + "; ".join(flagged[:3]))
    if g.get("divisionGame"):
        out.append(f"Division game ({(g.get('division') or {}).get('name', '')})")
    c = g.get("coaches") or {}
    if c.get("meetings"):
        out.append(f"{c.get('awayCoach')} vs {c.get('homeCoach')}: {c['meetings']} meetings, avg total {c.get('avgTotalInMeetings')}")
    return out

"""
Fantasy-football points as a measurable signal.

Fantasy points are a single number that rolls every stat a player produces (yards, TDs,
receptions, turnovers) into one scale, which makes them a clean read on usage + efficiency.
They are computed here from the weekly gold tables, using the Tank01 default scoring:

  passing   0.04/yd, 4/TD, -1/INT        rushing / receiving  0.1/yd, 6/TD
  fumble lost -1, 2-pt conversion +2, reception 1 (PPR) / 0.5 (HALF) / 0 (STD)

Five variables come out of this module (shown on the single-player page, and the last one
feeds Jimmy's composite score):

  1. FPTS L5          average PPR points over the last 5 games
  2. FPTS L10         average PPR points over the last 10 games
  3. DEFENSE RANK     where the next opponent ranks at allowing fantasy points to this position
                      (1 = toughest, 32 = most generous)
  4. POSITION RANK    where the player ranks among his position by season-average PPR points
  5. FANTASY EDGE     matchup-adjusted projection vs his own baseline -> a 0..1 signal (0.5 = neutral)
"""
from __future__ import annotations

import math
from collections import defaultdict
from functools import lru_cache

import data

PPR = {"PPR": 1.0, "HALF": 0.5, "STD": 0.0}
SKILL_POS = ("QB", "RB", "WR", "TE")
MIN_GAMES = 2
# How hard the opponent factor pulls the projection. Defense rank is noisy early in a season,
# so it is shrunk toward neutral until there is a real sample.
OPP_SHRINK_GAMES = 6
RECENT_WEIGHT = 0.6  # L5 vs season average in the baseline


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _points(pass_row, rush_row, rec_row, ppr: float) -> float:
    p = 0.0
    if pass_row:
        p += 0.04 * _f(pass_row.get("passing_yards")) + 4 * _f(pass_row.get("passing_tds")) \
            - _f(pass_row.get("passing_interceptions")) - _f(pass_row.get("sack_fumbles_lost")) \
            + 2 * _f(pass_row.get("passing_2pt_conversions"))
    if rush_row:
        p += 0.1 * _f(rush_row.get("rushing_yards")) + 6 * _f(rush_row.get("rushing_tds")) \
            - _f(rush_row.get("rushing_fumbles_lost")) + 2 * _f(rush_row.get("rushing_2pt_conversions"))
    if rec_row:
        p += 0.1 * _f(rec_row.get("receiving_yards")) + 6 * _f(rec_row.get("receiving_tds")) \
            + ppr * _f(rec_row.get("receptions")) - _f(rec_row.get("receiving_fumbles_lost")) \
            + 2 * _f(rec_row.get("receiving_2pt_conversions"))
    return p


@lru_cache(maxsize=1)
def _logs() -> dict[str, list[dict]]:
    """player_id -> [{week, opp, team, ppr, half, std}] in week order (current season only)."""
    tables = {n: {} for n in ("pass", "rush", "rec")}
    for key, src in (("pass", "player_passing_week"), ("rush", "player_rushing_week"), ("rec", "player_receiving_week")):
        for r in data.load(src):
            if r.get("season_type", "REG") != "REG":
                continue
            tables[key][(r["player_id"], int(r.get("week") or 0), r.get("season", ""))] = r
    seasons = [k[2] for t in tables.values() for k in t]
    season = max(seasons) if seasons else ""
    keys = {(k[0], k[1]) for t in tables.values() for k in t if k[2] == season}
    out: dict[str, list[dict]] = defaultdict(list)
    for pid, wk in keys:
        g = lambda n: tables[n].get((pid, wk, season))  # noqa: E731
        src = g("pass") or g("rush") or g("rec")
        out[pid].append({
            "week": wk, "opp": src.get("opponent_team", ""), "team": src.get("team", ""),
            **{k.lower(): round(_points(g("pass"), g("rush"), g("rec"), v), 2) for k, v in PPR.items()},
            "attempts": _f((g("pass") or {}).get("attempts")),
        })
    for pid in out:
        out[pid].sort(key=lambda r: r["week"])
    return dict(out)


@lru_cache(maxsize=1)
def _positions() -> dict[str, str]:
    pos = {pid: (d.get("position") or "") for pid, d in data.player_dimension().items()}
    for pid, games in _logs().items():
        if not pos.get(pid) and sum(g["attempts"] for g in games) >= 10:
            pos[pid] = "QB"
    return pos


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 1) if vals else None


@lru_cache(maxsize=1)
def _defense_table() -> dict[str, dict]:
    """position -> {team: avg PPR points that defense allows per player-game, 'rank': {team: 1..32}}"""
    allowed: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    pos = _positions()
    for pid, games in _logs().items():
        p = pos.get(pid)
        if p not in SKILL_POS:
            continue
        for g in games:
            # Skip fringe appearances so a 0.0-point cameo does not make a defense look stout.
            if g["ppr"] <= 0 and p != "QB":
                continue
            if g["opp"]:
                allowed[p][g["opp"]].append(g["ppr"])
    table: dict[str, dict] = {}
    for p, teams in allowed.items():
        avg = {t: sum(v) / len(v) for t, v in teams.items() if v}
        order = sorted(avg, key=lambda t: avg[t])  # lowest allowed first = toughest = rank 1
        table[p] = {"avg": avg, "rank": {t: i + 1 for i, t in enumerate(order)}, "n": len(order),
                    "league": sum(avg.values()) / len(avg) if avg else 0.0}
    return table


@lru_cache(maxsize=1)
def _position_ranks() -> dict[str, tuple[int, int]]:
    by_pos: dict[str, list[tuple[str, float]]] = defaultdict(list)
    pos = _positions()
    for pid, games in _logs().items():
        p = pos.get(pid)
        if p in SKILL_POS and len(games) >= MIN_GAMES:
            by_pos[p].append((pid, sum(g["ppr"] for g in games) / len(games)))
    out = {}
    for p, rows in by_pos.items():
        rows.sort(key=lambda r: r[1], reverse=True)
        for i, (pid, _) in enumerate(rows):
            out[pid] = (i + 1, len(rows))
    return out


def _next_opponent(pid: str, games: list[dict]) -> str | None:
    try:
        import jimmy
        opp = jimmy.next_opponent(pid)
        if opp:
            return opp
    except Exception:
        pass
    return None


def _safe_live(player_id: str) -> dict | None:
    try:
        return live(player_id)
    except Exception:
        return None


def profile(player_id: str) -> dict | None:
    """The fantasy block shown on the single-player page. None when there is no usable sample."""
    games = _logs().get(player_id) or []
    pos = _positions().get(player_id, "")
    if len(games) < MIN_GAMES or pos not in SKILL_POS:
        return None

    ppr = [g["ppr"] for g in games]
    l5, l10 = _avg(ppr[-5:]), _avg(ppr[-10:])
    season = _avg(ppr)
    pr = _position_ranks().get(player_id)

    opp = _next_opponent(player_id, games)
    d = _defense_table().get(pos)
    opp_rank = opp_allowed = None
    opp_factor = 1.0
    if opp and d and opp in d["avg"]:
        opp_rank, opp_allowed = d["rank"][opp], round(d["avg"][opp], 1)
        raw = d["avg"][opp] / d["league"] if d["league"] else 1.0
        # shrink toward 1.0 while few weeks are in
        w = min(1.0, len(games) / OPP_SHRINK_GAMES)
        opp_factor = 1 + (raw - 1) * w * 0.8

    baseline = RECENT_WEIGHT * (sum(ppr[-5:]) / len(ppr[-5:])) + (1 - RECENT_WEIGHT) * (sum(ppr) / len(ppr))
    projection = round(baseline * opp_factor, 1)
    edge = projection / (sum(ppr) / len(ppr)) - 1 if sum(ppr) > 0 else 0.0
    signal = round(0.5 + 0.5 * math.tanh(2.0 * edge), 3)

    return {
        "position": pos,
        "season": season, "l5": l5, "l10": l10,
        "last": ppr[-1],
        "scoring": {k: _avg([g[k.lower()] for g in games[-5:]]) for k in PPR},
        "positionRank": pr[0] if pr else None, "positionPool": pr[1] if pr else None,
        "opponent": opp, "defenseRank": opp_rank, "defensePool": d["n"] if d else None,
        "defenseAllowed": opp_allowed, "defenseLeague": round(d["league"], 1) if d else None,
        "projection": projection, "oppFactor": round(opp_factor, 3),
        "signal": signal,
        "log": [{"week": g["week"], "opp": g["opp"], "ppr": g["ppr"]} for g in games],
        "games": len(games),
        "live": _safe_live(player_id),
    }


def _tank_ppr(p: dict) -> dict | None:
    """Pull Tank01's own fantasy numbers out of one playerStats entry (live, default scoring)."""
    fd = p.get("fantasyPointsDefault") or {}
    def num(*keys):
        for k in keys:
            try:
                return round(float(fd[k]), 1)
            except (KeyError, TypeError, ValueError):
                continue
        return None
    out = {"PPR": num("PPR", "ppr"), "HALF": num("halfPPR", "HalfPPR", "half_ppr", "half"),
           "STD": num("standard", "Standard", "std")}
    if out["PPR"] is None:
        try:
            out["PPR"] = round(float(p.get("fantasyPoints")), 1)
        except (TypeError, ValueError):
            return None
    return out


def live(player_id: str) -> dict | None:
    """
    Live fantasy points from Tank01's box score while the player's game is on (or just finished
    today, Central time). None when no game today, no key, or the feed does not carry him.
    """
    from zoneinfo import ZoneInfo
    import datetime as dt
    import tank01
    team = data.player_team(player_id)
    if not team:
        return None
    today = dt.datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    g = next((r for r in data.load("schedule")
              if r.get("game_date") == today and team in (r.get("home_team"), r.get("away_team"))), None)
    if not g:
        return None
    body = tank01.get_live_boxscore(f"{today.replace('-', '')}_{g['away_team']}@{g['home_team']}", fantasy=True)
    if not body:
        return None
    name = data.normalize_name(data.player_name(player_id))
    for p in (body.get("playerStats") or {}).values():
        if isinstance(p, dict) and p.get("team") == team and data.normalize_name(p.get("longName", "")) == name:
            pts = _tank_ppr(p)
            if not pts:
                return None
            status = str(body.get("gameStatus", ""))
            done = "complete" in status.lower() or "final" in status.lower()
            return {"points": pts, "status": "FINAL" if done else "LIVE", "period": str(body.get("currentPeriod", "")),
                    "clock": str(body.get("gameClock", "")),
                    "opponent": g["home_team"] if g["away_team"] == team else g["away_team"]}
    return None


def signal(player_id: str) -> float | None:
    """0..1 composite component for Jimmy (0.5 = neutral). None when there is no sample."""
    p = profile(player_id)
    return p["signal"] if p else None


def reset() -> None:
    for fn in (_logs, _positions, _defense_table, _position_ranks):
        fn.cache_clear()

"""
BREAKOUT signal -- flags players whose opportunity is rising faster than
their production, the leading indicator fantasy start/sit rankings chase.

Built only from lake ponds (no outside fantasy source):

  ppr        : actual PPR points per week, from player_receiving_week +
               player_rushing_week (rec 1, yds 0.1, TD 6, fumble lost -2).
  xppr       : expected PPR from opportunity alone -- targets and carries
               valued at the league-wide PPR rate per target / per carry for
               that position, computed from the same weeks.
  opp_share  : (targets + carries) / team (targets + carries), per week.

Per player:
  gap        = xppr/game - ppr/game  (positive = production lagging opportunity)
  share_trend= latest week's opp_share - mean of earlier weeks

breakout_score (0-100) = within-position percentiles of
  gap (40%) + share_trend (40%) + latest opp_share (20%).

Flags:
  BREAKOUT CANDIDATE  gap > 2 pts, share up 1+ pt, share at/above position median
  BUY LOW             gap > 2 pts (opportunity there, production hasn't caught up)
  REGRESSION RISK     gap < -2 pts and share down 1+ pt (outproducing a shrinking role)
  STEADY              everything else

HEURISTIC. NOT BACKTESTED. With two weeks played, share_trend is a single
week-over-week move -- treat it as noisy until 4+ weeks are in the lake.
"""
from __future__ import annotations

from functools import lru_cache
from statistics import mean, median

import data

POSITIONS = ("RB", "WR", "TE")
MIN_OPPS_PER_GAME = 3.0
GAP_POINTS = 2.0
TREND_EPS = 0.01
MIN_RATE_SAMPLE = 50


def _f(v) -> float:
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


@lru_cache(maxsize=1)
def _weekly() -> dict[str, dict[int, dict]]:
    """player_id -> week -> {team, targets, carries, rec_ppr, rush_ppr}"""
    out: dict[str, dict[int, dict]] = {}

    def slot(r):
        return out.setdefault(r["player_id"], {}).setdefault(
            int(r["week"]), {"team": r.get("team", ""), "targets": 0.0, "carries": 0.0, "rec_ppr": 0.0, "rush_ppr": 0.0})

    for r in data.load("player_receiving_week"):
        if not r.get("player_id"):
            continue
        s = slot(r)
        s["targets"] = _f(r.get("targets"))
        s["rec_ppr"] = (_f(r.get("receptions")) + 0.1 * _f(r.get("receiving_yards"))
                        + 6 * _f(r.get("receiving_tds")) - 2 * _f(r.get("receiving_fumbles_lost")))
    for r in data.load("player_rushing_week"):
        if not r.get("player_id"):
            continue
        s = slot(r)
        s["carries"] = _f(r.get("carries"))
        s["rush_ppr"] = (0.1 * _f(r.get("rushing_yards")) + 6 * _f(r.get("rushing_tds"))
                         - 2 * _f(r.get("rushing_fumbles_lost")))
    return out


@lru_cache(maxsize=1)
def _team_opps() -> dict[tuple[str, int], float]:
    totals: dict[tuple[str, int], float] = {}
    for weeks in _weekly().values():
        for wk, s in weeks.items():
            totals[(s["team"], wk)] = totals.get((s["team"], wk), 0) + s["targets"] + s["carries"]
    return totals


@lru_cache(maxsize=1)
def _league_rates() -> dict[str, tuple[float, float]]:
    """position -> (PPR per target, PPR per carry) across every week in the lake."""
    dim = data.player_dimension()
    acc: dict[str, list[float]] = {p: [0.0, 0.0, 0.0, 0.0] for p in POSITIONS}
    for pid, weeks in _weekly().items():
        pos = dim.get(pid, {}).get("position")
        if pos not in acc:
            continue
        for s in weeks.values():
            a = acc[pos]
            a[0] += s["rec_ppr"]
            a[1] += s["targets"]
            a[2] += s["rush_ppr"]
            a[3] += s["carries"]
    pooled = [sum(a[i] for a in acc.values()) for i in range(4)]
    tgt = pooled[0] / pooled[1] if pooled[1] else 0.0
    car = pooled[2] / pooled[3] if pooled[3] else 0.0
    # A handful of TE carries (one of them a TD) would otherwise set the TE per-carry rate.
    return {
        p: (a[0] / a[1] if a[1] >= MIN_RATE_SAMPLE else tgt,
            a[2] / a[3] if a[3] >= MIN_RATE_SAMPLE else car)
        for p, a in acc.items()
    }


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    ranked = sorted(values, key=values.get)
    n = len(ranked)
    return {pid: (i + 1) / n for i, pid in enumerate(ranked)} if n else {}


@lru_cache(maxsize=1)
def breakout_table() -> list[dict]:
    dim = data.player_dimension()
    rates = _league_rates()
    team_opps = _team_opps()
    rows: list[dict] = []

    for pid, weeks in _weekly().items():
        info = dim.get(pid, {})
        pos = info.get("position")
        if pos not in POSITIONS:
            continue
        played = {wk: s for wk, s in weeks.items() if s["targets"] + s["carries"] > 0}
        if not played:
            continue
        games = len(played)
        opps = sum(s["targets"] + s["carries"] for s in played.values())
        if opps / games < MIN_OPPS_PER_GAME:
            continue

        per_tgt, per_car = rates[pos]
        ppr_pg = sum(s["rec_ppr"] + s["rush_ppr"] for s in played.values()) / games
        xppr_pg = sum(s["targets"] * per_tgt + s["carries"] * per_car for s in played.values()) / games

        shares = {wk: (s["targets"] + s["carries"]) / team_opps[(s["team"], wk)]
                  for wk, s in played.items() if team_opps.get((s["team"], wk))}
        ordered = [shares[wk] for wk in sorted(shares)]
        latest = ordered[-1] if ordered else 0.0
        trend = latest - mean(ordered[:-1]) if len(ordered) > 1 else 0.0

        rows.append({
            "playerId": pid,
            "name": info.get("name", pid),
            "team": info.get("team", ""),
            "position": pos,
            "games": games,
            "pprPerGame": round(ppr_pg, 1),
            "xpprPerGame": round(xppr_pg, 1),
            "gap": round(xppr_pg - ppr_pg, 1),
            "oppShare": round(latest, 3),
            "shareTrend": round(trend, 3),
        })

    for pos in POSITIONS:
        group = [r for r in rows if r["position"] == pos]
        if not group:
            continue
        p_gap = _percentiles({r["playerId"]: r["gap"] for r in group})
        p_trend = _percentiles({r["playerId"]: r["shareTrend"] for r in group})
        p_share = _percentiles({r["playerId"]: r["oppShare"] for r in group})
        share_median = median(r["oppShare"] for r in group)
        for r in group:
            pid = r["playerId"]
            r["breakoutScore"] = round(100 * (0.4 * p_gap[pid] + 0.4 * p_trend[pid] + 0.2 * p_share[pid]), 1)
            if r["gap"] > GAP_POINTS and r["shareTrend"] > TREND_EPS and r["oppShare"] >= share_median:
                r["flag"] = "BREAKOUT CANDIDATE"
            elif r["gap"] > GAP_POINTS:
                r["flag"] = "BUY LOW"
            elif r["gap"] < -GAP_POINTS and r["shareTrend"] < -TREND_EPS:
                r["flag"] = "REGRESSION RISK"
            else:
                r["flag"] = "STEADY"

    rows.sort(key=lambda r: r["breakoutScore"], reverse=True)
    return rows


@lru_cache(maxsize=1)
def breakout_by_player() -> dict[str, dict]:
    return {r["playerId"]: r for r in breakout_table()}

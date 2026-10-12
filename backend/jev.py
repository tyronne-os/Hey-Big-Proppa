"""
JEV -- TypeSafe's System One model, giving Jimmy the Greek a second,
independent read per leg (https://github.com/typesafe-ai/typesafe-sdk-python).

Optional and additive. When JEV_API_KEY is missing, the SDK isn't installed,
or a call fails for any reason, every function here returns None and Jimmy
scores exactly as it always has -- the lake-only path stays fully
self-contained, per the original framing: "without an AI agent like Jev...
Jimmy checks the ponds to form a probability." Jev augments that score, it
never replaces or gates it.

One HTTP call per leg: a single Noul (yes/no) question asking whether the
prop clears its line, given the same numbers Jimmy already computed (recent
hit rate, usage/coach-trust score, matchup unit edge). Jev's value here is
synthesizing that evidence holistically rather than averaging it -- it can
notice, for example, that a thin 2-game sample shouldn't be weighted the
same as a matchup edge backed by a full season.

Results are cached for the process lifetime, keyed on the exact inputs --
consistent with every other pond lookup in this app (data.py, matchup.py,
jimmy.py all cache their season snapshot the same way). A transient failure
is cached as "no opinion" too; that's an accepted trade-off, not a bug.

HEURISTIC. NOT BACKTESTED -- an LLM judgment, not a fitted statistical
model like matchup.py. One signal among several in jimmy_score(), never
the sole basis for a probability.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache

try:
    from typesafe_sdk import Noul, Score, TypeSafeClient
except ImportError:  # optional dependency -- local dev without it installed still works
    Noul = None
    Score = None
    TypeSafeClient = None


@lru_cache(maxsize=1)
def _client():
    key = os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
    if not key or TypeSafeClient is None:
        return None
    return TypeSafeClient(api_key=key, model="jev-latest", timeout=8.0)


def _new_client():
    """A fresh client per call: the SDK client cannot be reused after its `with` block closes it."""
    key = os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY")
    if not key or TypeSafeClient is None:
        return None
    return TypeSafeClient(api_key=key, model="jev-latest", timeout=15.0)


def available() -> bool:
    return _client() is not None


def diagnose() -> dict:
    """
    Real diagnostic, never the value: which env var(s) are set, whether the
    SDK is installed, and -- if a key is available -- an actual trivial API
    call so a wrong or revoked key shows up as an auth error.
    """
    jev_key = os.environ.get("JEV_API_KEY")
    typesafe_key = os.environ.get("TYPESAFE_API_KEY")
    active_key = jev_key or typesafe_key
    out = {
        "jevApiKeyPresent": bool(jev_key),
        "typesafeApiKeyPresent": bool(typesafe_key),
        "activeKeyVar": "JEV_API_KEY" if jev_key else ("TYPESAFE_API_KEY" if typesafe_key else None),
        "sdkInstalled": TypeSafeClient is not None,
        "callTest": None,
    }
    if not active_key or TypeSafeClient is None:
        return out
    try:
        client = TypeSafeClient(api_key=active_key, model="jev-latest", timeout=8.0)
        with client:
            response = client.system_one(
                state="ping",
                questions={"ok": Noul(instructions="Is this a connectivity test?")},
            )
        out["callTest"] = {"ok": True, "noul": response.nouls["ok"].noul}
    except Exception as exc:
        out["callTest"] = {"ok": False, "errorType": type(exc).__name__, "error": str(exc)[:300]}
    return out


_CACHE: dict[tuple, tuple[float, float | None]] = {}
_FAIL_RETRY_SECONDS = 90
_STATS: dict = {"calls": 0, "ok": 0, "errors": {}, "lastError": None}


def stats() -> dict:
    """Call counts and the most recent failure, so a muted JEV is visible instead of silent."""
    return {"calls": _STATS["calls"], "ok": _STATS["ok"], "errors": dict(_STATS["errors"]), "lastError": _STATS["lastError"]}


def _thin_leg_probability(
    player_id: str, name: str, team: str, market_slug: str, direction: str,
    line: float | None, hit_rate: float | None, usage_score: float | None,
    matchup_edge: float | None, opponent: str | None,
) -> float | None:
    """
    Jev's independent yes/no read on one leg: will it clear its line?
    Returns the noul probability (0-1), or None if Jev has no opinion --
    callers must treat None as "no signal", never as 0.
    """
    client = _client()
    if client is None or Noul is None:
        return None

    key = (player_id, name, team, market_slug, direction, line, hit_rate, usage_score, matchup_edge, opponent)
    hit = _CACHE.get(key)
    if hit and (hit[1] is not None or hit[0] > time.time()):
        return hit[1]

    state = {
        "player": name, "team": team, "opponent": opponent,
        "prop": {"market": market_slug, "direction": direction, "line": line},
        "recent_hit_rate_vs_this_line": hit_rate,
        "coach_trust_usage_score_0_100": usage_score,
        "matchup_unit_edge_zscore_positive_favors_offense": matchup_edge,
    }
    instructions = (
        f"Given {name}'s recent hit rate against this exact line, how much his own "
        f"coaching staff trusts him (usage score, 0-100), and how his unit's matchup "
        f"z-score edge reads (positive favors his offense, negative favors the "
        f"opposing defense), how likely is it that his {market_slug} goes "
        f"{direction} {line} in his next game against {opponent}?"
    )

    _STATS["calls"] += 1
    try:
        with _new_client() as call_client:
            response = call_client.system_one(
                state=state,
                questions={
                    "hits": Noul(
                        instructions=instructions,
                        criteria={
                            "true": "The stat clears the line in the stated direction.",
                            "false": "The stat does not clear the line in the stated direction.",
                        },
                    ),
                },
            )
        val = round(response.nouls["hits"].noul, 3)
        _STATS["ok"] += 1
        _CACHE[key] = (float("inf"), val)
        return val
    except Exception as exc:
        kind = type(exc).__name__
        _STATS["errors"][kind] = _STATS["errors"].get(kind, 0) + 1
        _STATS["lastError"] = {"type": kind, "message": str(exc)[:200]}
        _CACHE[key] = (time.time() + _FAIL_RETRY_SECONDS, None)
        return None


# ---------------------------------------------------------------------------
# Scouting reads -- JEV reads the full jev_brain file and answers two questions per call:
#   a yes/no on the posted line, and a ranged Score ("by how much") that prices any other line.
# ---------------------------------------------------------------------------

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor

PROP_CUTS = (0.6, 0.8, 0.95, 1.05, 1.2, 1.4)          # band edges as multiples of the posted line
PROP_SPAN = (0.0, 2.0)
TOTAL_CUTS = (-14, -7, -3, 3, 7, 14)                    # band edges as points from the posted total
TOTAL_SPAN = (-28, 28)
MARGIN_CUTS = (-14.5, -7.5, -3.5, 3.5, 7.5, 14.5)       # home margin bands
MARGIN_SPAN = (-35, 35)
_READS: dict[str, tuple[float, dict | None]] = {}
_POOL = ThreadPoolExecutor(max_workers=8)

GUIDE = ("You are JEV, a sharp NFL handicapper. Read the whole scouting file: recent form, the Big Proppa "
         "projection, dependability ranking and share when the game is tight, target share, the opposing defense's "
         "rank and how it gets scored on (touchdown transcripts), key injuries on both sides (a missing QB1, RB1 or WR1 "
         "changes everything), game script from the spread and implied team total, weather and roof, division-game "
         "familiarity, rest, and the head-coach matchup history. Weigh thin samples (2-3 games) lightly. "
         "Be calibrated: 50% means a coin flip.")


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _edges(cuts, span, base, mult: bool) -> list[float]:
    pts = [span[0], *cuts, span[1]]
    return [round(base * c, 2) if mult else round(base + c, 2) for c in pts]


def _band_labels(edges: list[float], unit: str) -> list[str]:
    labels = [f"under {edges[1]:g} {unit}"]
    labels += [f"{edges[i]:g} to {edges[i + 1]:g} {unit}" for i in range(1, len(edges) - 2)]
    labels.append(f"over {edges[-2]:g} {unit}")
    return labels


def _dist_over(probs: list[float], edges: list[float], x: float) -> float:
    """P(value > x) with each band's mass spread evenly across it."""
    tot = 0.0
    for k, p in enumerate(probs):
        lo, hi = edges[k], edges[k + 1]
        if x <= lo:
            tot += p
        elif x < hi:
            tot += p * (hi - x) / (hi - lo)
    return min(max(tot, 0.0), 1.0)


def _expected(probs: list[float], edges: list[float]) -> float:
    return sum(p * (edges[k] + edges[k + 1]) / 2 for k, p in enumerate(probs))


def _call(state: dict, questions: dict) -> dict | None:
    _STATS["calls"] += 1
    try:
        with _new_client() as c:
            resp = c.system_one(state=state, questions=questions)
        _STATS["ok"] += 1
        return {"nouls": {k: round(v.noul, 4) for k, v in resp.nouls.items()},
                "scores": {k: [round(v.probabilities.get(i, 0.0), 4) for i in range(len(v.probabilities))] for k, v in resp.scores.items()}}
    except Exception as exc:
        kind = type(exc).__name__
        _STATS["errors"][kind] = _STATS["errors"].get(kind, 0) + 1
        _STATS["lastError"] = {"type": kind, "message": str(exc)[:200]}
        return None


def _memo(key: str, fn) -> dict | None:
    hit = _READS.get(key)
    if hit and (hit[1] is not None or hit[0] > time.time()):
        return hit[1]
    val = fn()
    _READS[key] = (float("inf") if val is not None else time.time() + _FAIL_RETRY_SECONDS, val)
    return val


def _hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def prop_read(player_id: str, name: str, team: str, market: str, line: float) -> dict | None:
    """JEV's read on one player prop at its posted line: P(over), a 7-band outcome distribution, expected value."""
    if not available() or Noul is None or Score is None:
        return None
    import jev_brain
    state = jev_brain.prop_state(player_id, name, team, market, float(line))
    if not state:
        return None
    stat = state["question"]["stat"]
    edges = _edges(PROP_CUTS, PROP_SPAN, float(line), True)

    def run():
        raw = _call({"guide": GUIDE, **state}, {
            "clears": Noul(instructions=f"Will {name} finish with MORE than {line:g} {stat} in this game?",
                           criteria={"true": f"More than {line:g} {stat}.", "false": f"{line:g} {stat} or fewer."}),
            "range": Score(instructions=f"Where will {name}'s {stat} land in this game?", criteria=_band_labels(edges, stat)),
        })
        if not raw or "clears" not in raw["nouls"] or not raw["scores"].get("range"):
            return None
        probs = raw["scores"]["range"]
        s = sum(probs) or 1
        probs = [p / s for p in probs]
        return {"kind": "prop", "line": float(line), "p": raw["nouls"]["clears"], "edges": edges, "bands": probs,
                "expected": round(_expected(probs, edges), 1), "labels": _band_labels(edges, stat), "factors": jev_brain.factors(state)}
    return _memo(f"prop:{_hash(state)}", run)


def prop_p_over(read: dict, x: float) -> float:
    """P(over x) for any line: the ranged read, shifted so it agrees with JEV's direct answer at the posted line."""
    if abs(x - read["line"]) < 1e-9:
        return read["p"]
    shift = _logit(read["p"]) - _logit(_dist_over(read["bands"], read["edges"], read["line"]))
    return round(_sig(_logit(_dist_over(read["bands"], read["edges"], x)) + shift), 4)


def game_read(away: str, home: str, total: float | None, spread_home: float | None) -> dict | None:
    """JEV's read on a game: P(over total), P(home covers), P(home wins), plus total and margin distributions."""
    if not available() or Noul is None or Score is None or total is None:
        return None
    import jev_brain
    state = jev_brain.game_state(away, home)
    sp = spread_home if spread_home is not None else 0.0
    t_edges = _edges(TOTAL_CUTS, TOTAL_SPAN, float(total), False)
    m_edges = list(MARGIN_SPAN[:1]) + list(MARGIN_CUTS) + list(MARGIN_SPAN[1:])

    def run():
        raw = _call({"guide": GUIDE, **state}, {
            "over": Noul(instructions=f"Will {away} at {home} finish with MORE than {total:g} combined points?",
                         criteria={"true": f"Combined points above {total:g}.", "false": f"Combined points {total:g} or fewer."}),
            "homeCovers": Noul(instructions=f"Will {home} cover the spread of {sp:+g} (home final margin plus {sp:+g} is above zero)?",
                               criteria={"true": f"{home} covers {sp:+g}.", "false": f"{home} does not cover {sp:+g}."}),
            "homeWins": Noul(instructions=f"Will {home} win this game outright?", criteria={"true": f"{home} wins.", "false": f"{away} wins or it ties."}),
            "totalRange": Score(instructions="Where will the combined final score land?", criteria=_band_labels(t_edges, "total points")),
            "marginRange": Score(instructions=f"What will {home}'s final margin be (home points minus away points)?",
                                 criteria=_band_labels(m_edges, f"points ({home} margin)")),
        })
        if not raw or not raw["scores"].get("totalRange") or not raw["scores"].get("marginRange"):
            return None
        norm = lambda v: [p / (sum(v) or 1) for p in v]
        return {"kind": "game", "total": float(total), "spreadHome": sp, "pOver": raw["nouls"].get("over"), "pHomeCovers": raw["nouls"].get("homeCovers"),
                "pHomeWins": raw["nouls"].get("homeWins"), "totalEdges": t_edges, "totalBands": norm(raw["scores"]["totalRange"]),
                "marginEdges": m_edges, "marginBands": norm(raw["scores"]["marginRange"]),
                "expectedTotal": round(_expected(norm(raw["scores"]["totalRange"]), t_edges), 1),
                "expectedHomeMargin": round(_expected(norm(raw["scores"]["marginRange"]), m_edges), 1)}
    return _memo(f"game:{_hash([state, total, sp])}", run)


def game_p_over(read: dict, x: float) -> float:
    base = read["pOver"] if read.get("pOver") is not None else _dist_over(read["totalBands"], read["totalEdges"], read["total"])
    if abs(x - read["total"]) < 1e-9:
        return base
    shift = _logit(base) - _logit(_dist_over(read["totalBands"], read["totalEdges"], read["total"]))
    return round(_sig(_logit(_dist_over(read["totalBands"], read["totalEdges"], x)) + shift), 4)


def game_p_home_covers(read: dict, spread_home: float) -> float:
    base = read["pHomeCovers"] if read.get("pHomeCovers") is not None else _dist_over(read["marginBands"], read["marginEdges"], -read["spreadHome"])
    if abs(spread_home - read["spreadHome"]) < 1e-9:
        return base
    shift = _logit(base) - _logit(_dist_over(read["marginBands"], read["marginEdges"], -read["spreadHome"]))
    return round(_sig(_logit(_dist_over(read["marginBands"], read["marginEdges"], -spread_home)) + shift), 4)


def prefetch(jobs: list) -> None:
    """Run many reads in parallel (each job is a zero-arg callable) so the cache is warm before scoring."""
    if available() and jobs:
        list(_POOL.map(lambda j: j(), jobs))


def leg_probability(
    player_id: str, name: str, team: str, market_slug: str, direction: str,
    line: float | None, hit_rate: float | None, usage_score: float | None,
    matchup_edge: float | None, opponent: str | None,
) -> float | None:
    """Every caller's JEV entry point: the full scouting read for yardage/reception props, the thin read otherwise."""
    import bpl
    if line is not None and market_slug in bpl.NFL_MARKETS and team:
        try:
            r = prop_read(player_id, name, team, market_slug, float(line))
        except Exception:
            r = None
        if r:
            p = r["p"]
            return round(p if direction == "over" else 1 - p, 3)
    return _thin_leg_probability(player_id, name, team, market_slug, direction, line, hit_rate, usage_score, matchup_edge, opponent)

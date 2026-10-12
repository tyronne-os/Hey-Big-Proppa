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
    from typesafe_sdk import Noul, TypeSafeClient
except ImportError:  # optional dependency -- local dev without it installed still works
    Noul = None
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
    return TypeSafeClient(api_key=key, model="jev-latest", timeout=8.0)


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


def leg_probability(
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

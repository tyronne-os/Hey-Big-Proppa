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
from functools import lru_cache

try:
    from typesafe_sdk import Noul, TypeSafeClient
except ImportError:  # optional dependency -- local dev without it installed still works
    Noul = None
    TypeSafeClient = None


@lru_cache(maxsize=1)
def _client():
    key = os.environ.get("JEV_API_KEY")
    if not key or TypeSafeClient is None:
        return None
    return TypeSafeClient(api_key=key, model="jev-latest", timeout=8.0)


def available() -> bool:
    return _client() is not None


def diagnose() -> dict:
    """
    Real diagnostic, never the value: which env var name is set (catches a
    JEV_API_KEY / TYPESAFE_API_KEY mix-up), whether the SDK is installed,
    and -- if a key is present -- an actual trivial API call so a wrong or
    revoked key shows up as an auth error instead of a silent "present".
    """
    jev_key = os.environ.get("JEV_API_KEY")
    typesafe_key = os.environ.get("TYPESAFE_API_KEY")
    out = {
        "jevApiKeyPresent": bool(jev_key), "jevApiKeyLength": len(jev_key) if jev_key else 0,
        "typesafeApiKeyPresent": bool(typesafe_key),
        "note_typesafe_key": ("TYPESAFE_API_KEY is set but this app reads JEV_API_KEY -- "
                              "that's likely the mismatch." if typesafe_key and not jev_key else None),
        "sdkInstalled": TypeSafeClient is not None,
        "callTest": None,
    }
    if not jev_key or TypeSafeClient is None:
        return out
    try:
        client = TypeSafeClient(api_key=jev_key, model="jev-latest", timeout=8.0)
        with client:
            response = client.system_one(
                state="ping",
                questions={"ok": Noul(instructions="Is this a connectivity test?")},
            )
        out["callTest"] = {"ok": True, "noul": response.nouls["ok"].noul}
    except Exception as exc:
        out["callTest"] = {"ok": False, "errorType": type(exc).__name__, "error": str(exc)[:300]}
    return out


@lru_cache(maxsize=4096)
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

    try:
        with client:
            response = client.system_one(
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
        return round(response.nouls["hits"].noul, 3)
    except Exception:
        return None

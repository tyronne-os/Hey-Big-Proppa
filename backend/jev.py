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

import json
import os
import threading
import time
from pathlib import Path
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


def ready() -> bool:
    """JEV can answer: live, or from its stored reads (see _durable). Use this to gate reads; available() means live."""
    return available() or bool(_store())


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
_POOL = ThreadPoolExecutor(max_workers=16)

PROFIT_ZONE = 0.85


def grade(p: float | None, sides: tuple[str, str] = ("over", "under")) -> dict | None:
    """Every prediction on one scale: the side it favors, confidence 50-100, profit zone at 85+."""
    if p is None:
        return None
    conf = max(p, 1 - p)
    return {"pick": sides[0] if p >= 0.5 else sides[1], "confidence": round(conf * 100, 1), "profitZone": conf >= PROFIT_ZONE}


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


# ── JEV, always available: every good read is kept on disk (and backed up with MY BOO's records), so when the API is
#    down, rate-limited, or the key is missing in a dev box, the last read for that exact game or prop still answers.
_STORE_FILE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "jev_reads.json"
_STORE: dict | None = None
_STORE_LOCK = threading.Lock()


def _store() -> dict:
    global _STORE
    if _STORE is None:
        try:
            _STORE = json.loads(_STORE_FILE.read_text())
        except (OSError, ValueError):
            _STORE = {}
    return _STORE


def _store_put(key: str, val: dict) -> None:
    with _STORE_LOCK:
        st = _store()
        st[key] = {**val, "readAt": time.time()}
        if len(st) > 4000:                                   # keep the newest reads
            for k in sorted(st, key=lambda k: st[k].get("readAt", 0))[: len(st) - 4000]:
                st.pop(k, None)
        try:
            _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = _STORE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(st))
            tmp.replace(_STORE_FILE)
        except OSError:
            pass


def _durable(stable: str, live) -> dict | None:
    """Live read when JEV is reachable (and remember it); otherwise the last read for the same game or prop, marked stale."""
    if available() and Noul is not None and Score is not None:
        val = live()
        if val is not None:
            _store_put(stable, val)
            return val
    old = _store().get(stable)
    if old:
        _STATS["fromStore"] = _STATS.get("fromStore", 0) + 1
        return {**old, "stale": True}
    return None


def _hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def prop_read(player_id: str, name: str, team: str, market: str, line: float) -> dict | None:
    """JEV's read on one player prop at its posted line: P(over), a 7-band outcome distribution, expected value."""
    return _durable(f"prop:{player_id}:{market}:{float(line):g}", lambda: _prop_read_live(player_id, name, team, market, line))


def _prop_read_live(player_id: str, name: str, team: str, market: str, line: float) -> dict | None:
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
        import h2h
        return {"kind": "prop", "line": float(line), "p": raw["nouls"]["clears"], "edges": edges, "bands": probs,
                "sigma": max(h2h.SD_FLOOR.get(market, 10.0), 0.30 * float(line)),
                "expected": round(_expected(probs, edges), 1), "labels": _band_labels(edges, stat), "factors": jev_brain.factors(state),
                "grade": grade(raw["nouls"]["clears"])}
    return _memo(f"prop:{_hash(state)}", run)


def _normal_over(mean: float, sigma: float, x: float) -> float:
    return 1 - 0.5 * (1 + math.erf((x - mean) / (sigma * math.sqrt(2))))


def _anchored(direct_p: float, mean: float, sigma: float, posted: float, x: float) -> float:
    """P(over x): JEV's expected value as the center, real-world spread (JEV's own bands run far too tight),
    shifted so it agrees exactly with JEV's direct yes/no answer at the posted line."""
    if abs(x - posted) < 1e-9:
        return direct_p
    shift = _logit(direct_p) - _logit(_normal_over(mean, sigma, posted))
    return round(_sig(_logit(_normal_over(mean, sigma, x)) + shift), 4)


def prop_p_over(read: dict, x: float) -> float:
    return _anchored(read["p"], read["expected"], read.get("sigma") or 0.3 * read["line"], read["line"], x)


def game_read(away: str, home: str, total: float | None, spread_home: float | None) -> dict | None:
    """JEV's read on a game: P(over total), P(home covers), P(home wins), plus total and margin distributions."""
    if total is None:
        return None
    stable = f"game:{away}@{home}:{float(total):g}:{spread_home if spread_home is not None else 0:g}"
    return _durable(stable, lambda: _game_read_live(away, home, total, spread_home))


def _game_read_live(away: str, home: str, total: float, spread_home: float | None) -> dict | None:
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
                "expectedHomeMargin": round(_expected(norm(raw["scores"]["marginRange"]), m_edges), 1),
                "grades": {"total": grade(raw["nouls"].get("over")), "spread": grade(raw["nouls"].get("homeCovers"), (f"{home} {sp:+g}", f"{away} {-sp:+g}")),
                           "moneyline": grade(raw["nouls"].get("homeWins"), (home, away))}}
    return _memo(f"game:{_hash([state, total, sp])}", run)


GAME_SIGMA = 13.5   # NFL totals and margins miss by about this much on a typical night


def game_p_over(read: dict, x: float) -> float:
    base = read["pOver"] if read.get("pOver") is not None else _normal_over(read["expectedTotal"], GAME_SIGMA, read["total"])
    return _anchored(base, read["expectedTotal"], GAME_SIGMA, read["total"], x)


def game_p_home_covers(read: dict, spread_home: float) -> float:
    """P(home margin > -spread_home)."""
    base = read["pHomeCovers"] if read.get("pHomeCovers") is not None else _normal_over(read["expectedHomeMargin"], GAME_SIGMA, -read["spreadHome"])
    return _anchored(base, read["expectedHomeMargin"], GAME_SIGMA, -read["spreadHome"], -spread_home)


def prefetch(jobs: list) -> None:
    """Run many reads in parallel (each job is a zero-arg callable) so the cache is warm before scoring."""
    if ready() and jobs:
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
    if hit_rate is None:                       # no recent-form read: fall back to the multiverse prior for this market side
        try:
            import jimmy
            mv = jimmy.multiverse_prior(market_slug, direction)
            hit_rate = mv["implied"] + mv["prior_edge"] if mv else None
        except Exception:
            pass
    return _thin_leg_probability(player_id, name, team, market_slug, direction, line, hit_rate, usage_score, matchup_edge, opponent)


# ---------------------------------------------------------------------------
# Leaders overlay -- JEV's projection for the BIG PROPPA column and the SAFE BET (line cut 15%)
# ---------------------------------------------------------------------------

SAFE_CUT = 0.15


def safe_line_for(line: float) -> float | None:
    """The line reduced by 15%, floored to a half point (a lower line is easier to clear). None if it cannot go lower."""
    safe = max(0.5, math.floor(line * (1 - SAFE_CUT) * 2) / 2)
    return safe if safe < line else None


def _overlay(read: dict, line: float) -> dict:
    out = {"value": read["expected"], "p": round(read["p"], 3), "grade": read.get("grade"), "safeLine": None, "safeP": None, "safeProfitZone": False}
    sl = safe_line_for(line)
    if sl is not None:
        sp = prop_p_over(read, sl)
        out.update(safeLine=sl, safeP=round(sp, 3), safeProfitZone=sp >= PROFIT_ZONE)
    return out


def leader_overlay(items: list[tuple], wait: float = 8.0) -> tuple[dict, int]:
    """items: (key, player_id, name, team, market, line). Returns ({key: overlay}, reads still running).
    Reads that miss the wait budget keep running and fill the cache, so the next load has them."""
    if not ready() or not items:
        return {}, 0
    from concurrent.futures import wait as _wait
    futs = {it[0]: _POOL.submit(prop_read, it[1], it[2], it[3], it[4], float(it[5])) for it in items}
    _, pending = _wait(list(futs.values()), timeout=wait)
    out = {}
    for it in items:
        f = futs[it[0]]
        if f.done():
            try:
                r = f.result()
            except Exception:
                r = None
            if r:
                out[it[0]] = _overlay(r, float(it[5]))
    return out, len(pending)

"""
Intelligence layer: Claude + JEV + NVIDIA NIM working as a team.

Architecture:
  Claude (Anthropic)  — strategist: reads the lake snapshot, identifies
                        overhyped lines, hidden correlations, best spots.
                        Returns natural language analysis + specific testable
                        hypotheses.

  JEV (TypeSafe)      — probability engine: given each Claude hypothesis,
                        scores it as a structured Noul probability (0-1).

  NVIDIA NIM          — validator: independent second LLM pass on the top
                        consensus findings for cross-verification.

All three degrade gracefully when their key is absent. The result always
reports which providers contributed so the UI can show connection state.

Daily cached (same as jimmy_hunt). Force refresh with invalidate_cache().
"""
from __future__ import annotations

import json
import os
import textwrap
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import data
import jimmy
import jimmy_hunt
import jev

# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _anthropic_client():
    try:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return None
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None


def claude_available() -> bool:
    return _anthropic_client() is not None


def nvidia_available() -> bool:
    return bool(os.environ.get("NVIDIA_API_KEY"))


_GEMMA_LOCAL_URL = "http://127.0.0.1:8765"


def gemma_available() -> bool:
    """Gemma runs locally via Ollama on port 8765."""
    try:
        import httpx
        r = httpx.get(f"{_GEMMA_LOCAL_URL}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def ai_status() -> dict:
    jev_diag = jev.diagnose()
    return {
        "claude": {
            "connected": claude_available(),
            "model": "claude-opus-5-5",
            "keyVar": "ANTHROPIC_API_KEY",
        },
        "jev": {
            "connected": jev.available(),
            "model": "jev-latest",
            "keyVar": jev_diag.get("activeKeyVar"),
            "callTest": jev_diag.get("callTest"),
        },
        "nvidia": {
            "connected": nvidia_available(),
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "keyVar": "NVIDIA_API_KEY",
        },
        "gemma": {
            "connected": gemma_available(),
            "model": "gemma3:4b Q4 (local)",
            "keyVar": "Ollama :8765",
        },
    }


# ---------------------------------------------------------------------------
# Lake snapshot — compact context for the LLMs
# ---------------------------------------------------------------------------
def _lake_snapshot() -> str:
    """
    A compact but complete picture of this week's lake: matchup edges,
    top-usage players, hunt picks, and recent hit-rate vs lines.
    Kept under ~6K tokens so Claude can reason over it efficiently.
    """
    lines: list[str] = []

    # Matchup edges for this week
    try:
        from matchup import slate
        games = slate()
        lines.append("=== WEEK 3 MATCHUP EDGES (z-score, + favors offense) ===")
        for g in games[:8]:
            h, a = g["home"], g["away"]
            edge_str = " | ".join(f"{u}:{h['edges'].get(u,0):+.2f}" for u in ["SCORING","AIR","GROUND"])
            lines.append(f"{h['team']} vs {a['team']} — HOME: {edge_str}")
    except Exception as e:
        lines.append(f"[matchup snapshot error: {e}]")

    # Top-usage players by position
    try:
        usage_rows = sorted(
            [r for r in data.load("player_usage") if r.get("usage_index_score")],
            key=lambda r: float(r.get("usage_index_score", 0)), reverse=True
        )
        lines.append("\n=== TOP USAGE PLAYERS (coach trust score) ===")
        pos_seen: dict[str, int] = {}
        for r in usage_rows:
            pos = (r.get("position") or "").upper()
            if pos not in ("QB","RB","WR","TE"):
                continue
            if pos_seen.get(pos, 0) >= 3:
                continue
            pos_seen[pos] = pos_seen.get(pos, 0) + 1
            lines.append(f"{pos} {r['player_name']} ({r['team']}) usage={r['usage_index_score']}")
    except Exception as e:
        lines.append(f"[usage snapshot error: {e}]")

    # Hunt picks — Jimmy's best per question
    try:
        hunt = jimmy_hunt.hunt()
        lines.append("\n=== JIMMY'S TOP PICKS THIS WEEK ===")
        for q in hunt["questions"][:12]:
            if q["players"]:
                best = q["players"][0]
                lines.append(
                    f"{q['question']}: {best['name']} ({best['team']}) "
                    f"jimmy={best['jimmyScore']} jev={best.get('jevScore','?')} "
                    f"defWeakness={best.get('defWeakness','?')}"
                )
    except Exception as e:
        lines.append(f"[hunt snapshot error: {e}]")

    # Recent performance vs lines (L2, since we only have 2 weeks)
    try:
        lines.append("\n=== L2 PERFORMANCE VS FANDUEL LINE (sample players) ===")
        from jimmy_hunt import _hit_rate
        sample = [("00-0036963","A.St. Brown","WR","recyds",80.5),
                  ("00-0033280","C.McCaffrey","RB","rushyds",75.5),
                  ("00-0035228","J.Jefferson","WR","recyds",80.5)]
        for pid, name, pos, mkt, line_ in sample:
            hr = _hit_rate(pid, mkt, line_, "over")
            lines.append(f"{pos} {name}: L2 hit rate {mkt}>{line_} = {hr}")
    except Exception as e:
        lines.append(f"[L2 snapshot error: {e}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------
_CLAUDE_SYSTEM = textwrap.dedent("""
You are Jimmy the Greek's analytical brain — a sharp, concise NFL prop analyst
with deep knowledge of how betting markets misprice player props in early-season
games when sample sizes are small and books rely on reputation rather than data.

You receive a lake snapshot: matchup unit edges, usage/coach-trust scores, and
prop-pick recommendations. Your job:

1. IDENTIFY OVERHYPED PROPS — lines the market has set inflated vs actual lake
   signals (e.g., a WR the offense clearly trusts less than their line implies).

2. FIND CORRELATIONS — pairs of props that tend to move together (e.g., if a
   team is weak AIR unit, the QB's yards AND the WR's yards both get a boost).

3. SPOT VALUE — props where the lake says yes but the market is undervaluing
   (defWeakness high, usage score high, matchup edge positive).

Output exactly 5–8 "nuggets" as a JSON array (nothing else — no prose wrapper):
[
  {
    "rank": 1,
    "claim": "one specific, actionable claim about a player/prop",
    "category": "overhyped" | "correlation" | "value",
    "action": "BET OVER / BET UNDER / PARLAY WITH [X]",
    "reasoning": "2-3 sentences max",
    "testable": "a yes/no question JEV can score"
  }
]
""").strip()


def _ask_claude(lake_ctx: str, query: str | None = None) -> list[dict]:
    client = _anthropic_client()
    if not client:
        return []
    try:
        import anthropic
        prompt = lake_ctx
        if query:
            prompt += f"\n\n=== USER QUERY ===\n{query}\n\nAnswer the query using the lake data above. Still output 5-8 nuggets as JSON."
        msg = client.messages.create(
            model="claude-opus-5-5",
            max_tokens=1500,
            system=_CLAUDE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except Exception as e:
        return [{"error": str(e), "rank": 0}]


# ---------------------------------------------------------------------------
# NVIDIA NIM validation
# ---------------------------------------------------------------------------
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"


def _ask_nvidia(nuggets: list[dict], lake_ctx: str) -> dict[int, str]:
    """Returns {rank: validation_comment} for the top nuggets."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key or not nuggets:
        return {}
    try:
        import httpx
        top = [n for n in nuggets if "rank" in n and "testable" in n][:4]
        if not top:
            return {}
        questions = "\n".join(f"{n['rank']}. {n['testable']}" for n in top)
        prompt = (
            f"You are an independent NFL analytics validator. Given this week's data "
            f"context and a set of betting prop claims, assess each claim's validity.\n\n"
            f"DATA CONTEXT:\n{lake_ctx[:2000]}\n\n"
            f"CLAIMS TO VALIDATE (answer each in 1 sentence — agree/disagree + why):\n{questions}"
        )
        resp = httpx.post(
            f"{_NVIDIA_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": _NVIDIA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 600,
                "temperature": 0.3,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        # Parse line-by-line, map back to rank
        out = {}
        for line in text.strip().split("\n"):
            for n in top:
                if str(n["rank"]) in line[:5]:
                    out[n["rank"]] = line.strip().lstrip("0123456789. ")
                    break
        return out
    except Exception as e:
        return {0: f"NVIDIA error: {str(e)[:120]}"}


# ---------------------------------------------------------------------------
# Gemma 3 ZeroGPU analysis (HF Space)
# ---------------------------------------------------------------------------
def _ask_gemma(lake_ctx: str) -> list[dict]:
    """Call local Gemma 3 server (Ollama Q4, port 8765)."""
    try:
        import httpx
        resp = httpx.post(
            f"{_GEMMA_LOCAL_URL}/predict",
            json={"data": [lake_ctx[:4000]]},
            headers={"Content-Type": "application/json"},
            timeout=120.0,  # CPU inference on 4B Q4 can take 60-90s
        )
        resp.raise_for_status()
        raw = resp.json().get("data", ["[]"])[0]
        if isinstance(raw, str):
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        return raw if isinstance(raw, list) else []
    except Exception as e:
        return [{"error": f"Gemma: {str(e)[:120]}", "rank": 0}]


# ---------------------------------------------------------------------------
# JEV scoring of Claude's hypotheses
# ---------------------------------------------------------------------------
def _score_nuggets_with_jev(nuggets: list[dict]) -> list[dict]:
    """Ask JEV to score each nugget's 'testable' question as a Noul probability."""
    if not jev.available() or not nuggets:
        return nuggets
    enriched = []
    for n in nuggets:
        if "error" in n or not n.get("testable"):
            enriched.append(n)
            continue
        try:
            prob = jev.leg_probability(
                player_id=n.get("claim", "unknown")[:20],
                name=n.get("claim", "")[:40],
                team="",
                market_slug="nugget",
                direction="over",
                line=0.5,
                hit_rate=None,
                usage_score=None,
                matchup_edge=None,
                opponent=None,
            )
            enriched.append({**n, "jevProbability": prob})
        except Exception:
            enriched.append(n)
    return enriched


# ---------------------------------------------------------------------------
# Daily cache
# ---------------------------------------------------------------------------
_cache:      dict | None = None
_cache_date: str         = ""


def invalidate_cache() -> None:
    global _cache, _cache_date
    _cache = None
    _cache_date = ""


def nuggets(force: bool = False) -> dict:
    global _cache, _cache_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not force and _cache and _cache_date == today:
        return _cache
    result      = _build_nuggets(today)
    _cache      = result
    _cache_date = today
    return result


def _build_nuggets(today: str) -> dict:
    lake_ctx = _lake_snapshot()

    # Claude: strategic analysis
    claude_nuggets = _ask_claude(lake_ctx)

    # Gemma: independent open-weight perspective (concurrent would be ideal but
    # ZeroGPU cold starts are slow — run after Claude so we don't block the main path)
    gemma_nuggets = _ask_gemma(lake_ctx)
    gemma_ok = gemma_nuggets and not any("error" in n for n in gemma_nuggets)

    # Merge Claude + Gemma before JEV scoring — tag source
    combined: list[dict] = []
    for n in claude_nuggets:
        combined.append({**n, "source": "claude"})
    for n in (gemma_nuggets if gemma_ok else []):
        # Offset rank so Gemma doesn't collide with Claude rank numbers
        combined.append({**n, "rank": n.get("rank", 0) + 100, "source": "gemma"})

    # JEV: probability scores on each claim
    if combined and not any("error" in n for n in combined):
        scored = _score_nuggets_with_jev(combined)
    else:
        scored = combined

    # NVIDIA: independent validation
    nvidia_comments = _ask_nvidia(scored, lake_ctx)

    # Merge and rank by consensus
    final = []
    for n in scored:
        rank = n.get("rank", 99)
        jev_p = n.get("jevProbability")
        nvidia_note = nvidia_comments.get(rank)

        # Consensus score: average of what we have
        signals = []
        if jev_p is not None:
            signals.append(jev_p)
        if nvidia_note and any(word in nvidia_note.lower() for word in ("agree", "correct", "strong", "confirm", "yes")):
            signals.append(0.75)
        elif nvidia_note and any(word in nvidia_note.lower() for word in ("disagree", "weak", "unlikely", "no")):
            signals.append(0.35)
        consensus = round(sum(signals) / len(signals), 3) if signals else None

        final.append({
            **n,
            "jevProbability": jev_p,
            "nvidiaNote":     nvidia_note,
            "consensusScore": consensus,
        })

    # Sort by consensus desc, then by rank
    final.sort(key=lambda x: (-(x.get("consensusScore") or 0), x.get("rank", 99)))

    return {
        "date":         today,
        "generatedAt":  datetime.now(timezone.utc).isoformat(),
        "providers":    {
            "claude": claude_available(),
            "jev":    jev.available(),
            "nvidia": nvidia_available(),
            "gemma":  gemma_ok,
        },
        "nuggets":      final,
        "lakeSnapshot": lake_ctx[:500] + "…",
    }


# ---------------------------------------------------------------------------
# Deep dive: ad-hoc query through all three AIs
# ---------------------------------------------------------------------------
def deep_dive(query: str) -> dict:
    lake_ctx = _lake_snapshot()

    # Claude answers the question
    claude_response = None
    if claude_available():
        raw = _ask_claude(lake_ctx, query=query)
        claude_response = raw

    # NVIDIA independent take
    nvidia_response = None
    key = os.environ.get("NVIDIA_API_KEY")
    if key:
        try:
            import httpx
            resp = httpx.post(
                f"{_NVIDIA_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": _NVIDIA_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a sharp NFL prop analyst. Be concise and specific. Use data provided."},
                        {"role": "user", "content": f"DATA:\n{lake_ctx[:3000]}\n\nQUESTION: {query}\n\nAnswer in 3-5 sentences focused on actionable prop insights."},
                    ],
                    "max_tokens": 400,
                    "temperature": 0.4,
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            nvidia_response = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            nvidia_response = f"[NVIDIA error: {str(e)[:100]}]"

    # Gemma quick take
    gemma_response = None
    try:
        lake_short = lake_ctx[:2000] + f"\n\nQUESTION: {query}\nAnswer with 5 focused nuggets on this question."
        raw_g = _ask_gemma(lake_short)
        if raw_g and not any("error" in n for n in raw_g):
            gemma_response = raw_g
    except Exception:
        pass

    return {
        "query":           query,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "providers":       {
            "claude": claude_available(),
            "jev":    jev.available(),
            "nvidia": nvidia_available(),
            "gemma":  gemma_response is not None,
        },
        "claudeNuggets":   claude_response,
        "nvidiaResponse":  nvidia_response,
        "gemmaResponse":   gemma_response,
    }

"""JIMMY THE GREEK'S TAKE — backend port of frontend/src/components/jimmyTake.ts.

The scoring here is a faithful 1:1 port of the TypeScript module: same factor
scores, same weights, same thresholds, same confidence tiers and red-flag scan.
Only the sentence voice differs, and it does so by design: the deliverable is
Jimmy's spoken-style read, which is what gets injected into the served HTML of
every /p/<slug> page so search engines index the commentary itself.
"""

from __future__ import annotations

import re
import math

WEIGHTS = {"defense": 0.35, "l5": 0.25, "fantasy": 0.2, "usage": 0.1, "rz": 0.1}

RED_FLAG_PATTERNS = {
    "injury": re.compile(r"\b(injury|injured|questionable|doubtful|out|ir|concussion|hamstring|ankle|knee)\b"),
    "suspension": re.compile(r"\b(suspended|suspension)\b"),
    "role reduction": re.compile(r"\b(benched|demoted|snap count drop|inactive|healthy scratch)\b"),
    "QB instability": re.compile(r"\b(qb change|quarterback change|backup qb)\b"),
}

# Defense rank → voice. Same buckets as the frontend,Jimmy-the-Greek phrasing.
_DEF_VOICE = [
    (27, "a defense you can run a truck through"),
    (21, "a soft run-fit defense"),
    (12, "an average defense"),
    (6,  "a defense that brings real resistance"),
    (0,  "an elite, legit defense"),
]


def _num(x: object) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _score_defense(rank, pool=32) -> float:
    """1 = toughest, 32 = softest → -1..+1."""
    r = _num(rank)
    if r is None or r == 0:
        return 0.0
    return (pool - r) / (pool - 1) * 2 - 1


def _score_last_five(room) -> float:
    """Fraction of L5 games that cleared the number → -1..+1."""
    games = ((room or {}).get("viewer") or {}).get("l5") or []
    with_line = [g for g in games if g.get("over") is not None]
    if not with_line:
        return 0.0
    cleared = sum(1 for g in with_line if g.get("over") is True)
    return (cleared / len(with_line)) * 2 - 1


def _score_fantasy(f) -> float:
    if not f:
        return 0.0
    proj = _num(f.get("projection"))
    season = _num(f.get("season")) or 0.0
    if not season or proj is None:
        return 0.0
    diff = (proj - season) / season
    return max(-1.0, min(1.0, diff * 3))


def _score_usage(t) -> float:
    if not t:
        return 0.0
    d = _num(t.get("confidenceDelta")) or 0.0
    return max(-1.0, min(1.0, d * 10))


def _score_red_zone(t) -> float:
    if not t:
        return 0.0
    rz = _num(((t.get("td") or {}).get("perRedZoneOpp")))
    if rz is None:
        return 0.0
    return max(-1.0, min(1.0, (rz - 0.35) / 0.35 * 2))


def _red_flags(news) -> list[str]:
    text = " ".join((n.get("headline") or "") + " " + (n.get("summary") or "") for n in (news or []))
    text = (text or "").lower()
    return [flag for flag, pat in RED_FLAG_PATTERNS.items() if pat.search(text)]


def make_take(chart: dict, news: list | None = None) -> dict:
    """Deterministic 200-char Jimmy take from the player chart payload."""
    f = chart.get("fantasy") or {}
    t = chart.get("trust") or {}
    room = chart.get("teamRank") or {}
    bpl = chart.get("bpl") or{}
    line = _num(chart.get("line"))
    if line is None:
        line = _num(bpl.get("sportsbookLine"))
    name = chart.get("name") or "He"
    team = chart.get("team") or ""
    prop = (chart.get("prop") or "the play").lower()
    opp = bpl.get("nextOpp") or f.get("opponent") or None
    opp_rank = _num(bpl.get("nextOppRank")) if _num(bpl.get("nextOppRank")) else _num(f.get("defenseRank"))
    pool = _num(f.get("defensePool")) or 32

    # ---- Factor scores -1..1 (identical to the frontend port) ----
    defense = _score_defense(opp_rank, pool)
    l5 = _score_last_five(room)
    fantasy = _score_fantasy(f)
    usage = _score_usage(t)
    rz = _score_red_zone(t)

    composite = (defense * WEIGHTS["defense"] + l5 * WEIGHTS["l5"] + fantasy * WEIGHTS["fantasy"]
                 + usage * WEIGHTS["usage"] + rz * WEIGHTS["rz"])

    confidence = "high" if abs(composite) > 0.4 else ("low" if abs(composite) < 0.15 else "medium")
    flags = _red_flags(news)
    if flags:
        confidence = "low"

    # ---- Voice ----
    opp_txt = f"at {opp}" if opp else "on Sunday"
    def_voice = next((v for t_, v in _DEF_VOICE if (opp_rank or 0) >= t_), "an average defense") if opp_rank else None
    book_txt = f"the book says {line:g}" if line is not None else "no number has dropped yet"

    call = None
    if composite > 0.15 and confidence != "low":
        call = "I'm telling you right now — take the over."
    elif composite < -0.15:
        call = "Stay away from the over — this feels like an under."

    matchup = f"{name}, {team}, " + (f"goes {opp_txt} against {def_voice}." if def_voice else "draws the Sunday slate.")

    # L5 form, in Jimmy's ride-or-die cadence
    form = None
    games = ((room.get("viewer")) or {}).get("l5") or []
    wl = [g for g in games if g.get("over") is not None]
    if wl:
        hits = sum(1 for g in wl if g.get("over") is True)
        pct = hits / len(wl)
        if pct >= 0.8:
            form = f"He's cashed {hits} of {len(wl)} straight — the well is loaded."
        elif pct >= 0.6:
            form = f"Course he's {hits} for {len(wl)}. Trend's on his side."
        elif pct >= 0.4:
            form = f"Split {hits} for {len(wl)} against the close. No edge there."
        else:
            form = f"Missed his number {len(wl) - hits} of {len(wl)} — the books know it too."

    edge = None
    bp = _num(bpl.get("bpl"))
    edge_pct = _num(bpl.get("diffPct")) or 0.0
    if bp is not None and line is not None and abs(edge_pct) > 5:
        direction = "over" if edge_pct > 0 else "under"
        edge = f"Lake's read is {bp:g} against {line:g} — {abs(edge_pct):g}% of daylight to the {direction}."

    flag_voice = None
    if flags:
        flag_voice = "Watch the wires — " + " and ".join(flags[:2]) + " could gut this bet."

    clauses = [call, matchup, form, edge, flag_voice]
    take = " ".join(c for c in clauses if c).strip()
    if len(take) > 200:
        take = take[:197].rstrip() + "…"

    drivers = []
    if abs(defense) > 0.3: drivers.append("matchup")
    if abs(l5) > 0.3: drivers.append("last five")
    if abs(fantasy) > 0.2: drivers.append("projection")
    if abs(usage) > 0.2: drivers.append("usage")
    if abs(rz) > 0.2: drivers.append("red zone")

    return {
        "prediction": take,
        "confidence": confidence,
        "composite": round(composite, 3),
        "drivers": drivers,
        "redFlags": flags,
    }


# Aliases: main.py prefers a generate() entry point based on the shared name.
def generate(chart: dict, news: list | None = None) -> dict:
    return make_take(chart, news)

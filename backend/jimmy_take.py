"""JIMMY THE GREEK'S TAKE — backend port of frontend/src/components/jimmyTake.ts.

Scoring is a faithful 1:1 port of the TypeScript module: same factor scores,
same weights, same thresholds, same confidence tiers and red-flag scan. Only
the voice differs — and it does so by design. The deliverable is Jimmy's
spoken-style read, which is what gets injected into the served HTML of every
/p/<slug> page so search engines index the commentary itself.

Voice rules the user set:
  * bold — point at the number, never hedge
  * brutal honesty — burn him when the player burned the bettor
  * neck on the line — when the data is loud, say it
  * never prose an absurd edge (placeholder books never make sentences)
"""

from __future__ import annotations

import re

WEIGHTS = {"defense": 0.35, "l5": 0.25, "fantasy": 0.2, "usage": 0.1, "rz": 0.1}

RED_FLAG_PATTERNS = {
    "an injury": re.compile(r"\b(injury|injured|questionable|doubtful|out|ir|concussion|hamstring|ankle|knee)\b"),
    "a suspension": re.compile(r"\b(suspended|suspension)\b"),
    "a role cut": re.compile(r"\b(benched|demoted|snap count drop|inactive|healthy scratch)\b"),
    "a QB shuffle": re.compile(r"\b(qb change|quarterback change|backup qb)\b"),
}

# Defense rank → voice. Same buckets as before, sharper words.
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
    r = _num(rank)
    if r is None or r == 0:
        return 0.0
    # rank 1 = stingiest (worst matchup) → -1; rank 32 = softest → +1
    return (r - 1) / (pool - 1) * 2 - 1


def _score_last_five(room) -> float:
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


def _def_vice(rank) -> str | None:
    r = _num(rank)
    if r is None or r == 0:
        return None
    for step, voice in _DEF_VOICE:
        if r >= step:
            return voice
    return None


def make_take(chart: dict, news: list | None = None) -> dict:
    """Deterministic 200-char Jimmy take from the player chart payload."""
    f = chart.get("fantasy") or {}
    t = chart.get("trust") or {}
    room = chart.get("teamRank") or {}
    bpl = chart.get("bpl") or {}
    pos = (chart.get("position") or "").upper()
    prop = chart.get("prop") or "the play"
    line = _num(chart.get("line"))
    if line is None:
        line = _num(bpl.get("sportsbookLine"))
    name = chart.get("name") or "He"
    team = chart.get("team") or ""
    opp = bpl.get("nextOpp") or f.get("opponent") or None
    opp_rank = _num(bpl.get("nextOppRank")) or _num(f.get("defenseRank"))
    pool = _num(f.get("defensePool")) or 32

    # ---- Wrong-market guard ----
    ball_skills = {"WR", "TE", "RB", "FB", ""}
    prop_low = prop.lower()
    skill_prop = any(param in prop_low for param in ("rush", "rec", "reception", "scrimmage"))
    pass_prop = "pass" in prop_low or "passing" in prop_low
    if (skill_prop and pos not in ball_skills) or (pass_prop and pos != "QB"):
        who = "throw passes" if pass_prop else f"run or catch in a {prop_low} market"
        return {
            "prediction": (f"No play. {name} is a {pos or 'specialist'} — he doesn't {who}. "
                           "That's a book filler line, not a market. Pass."),
            "confidence": "low",
            "composite": 0.0,
            "drivers": ["wrong market"],
            "redFlags": [],
        }

    # ---- Name integrity guard: no take for a player the lake can't even name ----
    if re.match(r"^00-\d{6,7}$|^N/A|^\d{2}-\d+$", str(name)):
        return {
            "prediction": "No read — this player isn't named in the lake yet. He's a number, not a name. Pass.",
            "confidence": "low",
            "composite": 0.0,
            "drivers": ["unknown name"],
            "redFlags": [],
        }

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

    # ---- The call. Jimmy never squints at a number; he points at it. ----
    if flags:
        call = f"Hard pass on {name} until the wires clear."
    elif composite > 0.25 and confidence == "high":
        call = f"Put your neck out — {name}'s going over."
    elif composite > 0.15:
        call = f"I'm on {name} over. That's my number."
    elif composite < -0.25 and confidence == "high":
        call = "Bash the under. The books haven't moved it enough."
    elif composite < -0.15:
        call = "Lean under. Not a lock. A lean."
    else:
        call = None  # neutral — the edge clause decides (see below)
    call_is_neutral = call is None

    # ---- Matchup clause ----
    match = f"{name} ({team or 'FA'}), {prop_low}" + (f", at {opp}" if opp else "")
    dv = _def_vice(opp_rank)
    if dv:
        match += f", {dv}"
    match += "."

    # ---- L5 form — with anger only when the player burned the bettor ----
    form = None
    games = list(((room.get("viewer")) or {}).get("l5") or [])
    wl = [g for g in games if g.get("over") is not None]
    if wl:
        hits = sum(1 for g in wl if g.get("over") is True)
        miss = len(wl) - hits
        pct = hits / len(wl)
        if pct >= 0.8:
            form = f"Slaughtered the number {hits} of {len(wl)} — he's the ride."
        elif pct >= 0.6:
            form = f"{hits}-for-{len(wl)} lately. He owes nobody."
        elif pct >= 0.4:
            form = f"{hits}-for-{len(wl)} — you're coin-flipping. Not a bet."
        elif miss >= 4:
            form = f"Putrid — {hits}-for-{len(wl)}. He's cost you dinner twice."
        else:
            form = f"{hits}-for-{len(wl)} — the number hugs him worse than the stat sheet."

    # Last-game stinker → Jimmy's glare, deterministically produced from data
    if wl and wl[-1].get("over") is False and line and _num(wl[-1].get("value")) is not None:
        val = _num(wl[-1]["value"])
        if val is not None and val < 0.7 * line:
            dud = f"Last week was a {val:g} stinker."
            form = (form + " " + dud) if form else dud

    # ---- Edge clause — never prose an impossible number ----
    edge = None
    bp = _num(bpl.get("bpl"))
    if bp is not None and line is not None:
        edge_pct = _num(bpl.get("diffPct"))
        if edge_pct is not None and 5 <= abs(edge_pct) < 100:
            size = abs(edge_pct)
            edge_direction = "over" if edge_pct > 0 else "under"
            edge = f"Lake {bp:g} vs book {line:g} — {size:g}% daylight, {edge_direction}."

    # A neutral composite with a loud edge is still a call — Jimmy respects daylight.
    if call is None:
        if edge and _num(bpl.get("diffPct")) and abs(_num(bpl.get("diffPct")) or 0) >= 15:
            call = f"The only angle here is the {edge_direction}."
        else:
            call = "No payday in this line — watch it, don't bet it."

    flag_voice = None
    if flags:
        flag_voice = "Wire says " + " or ".join(flags[:2]) + " — that changes everything."

    clauses = [call, match, form, edge, flag_voice]
    take = " ".join(str(c) for c in clauses if c).strip()

    # Smart trim: drop lowest-priority clauses before ever slicing text.
    if len(take) > 200:
        if flag_voice and flags:
            clauses = [c for c in clauses if c is not flag_voice]
        elif form:
            clauses = [c for c in clauses if c is not form]
        elif edge:
            clauses = [c for c in clauses if c is not edge]
        take = " ".join(str(c) for c in clauses if c).strip()
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


def generate(chart: dict, news: list | None = None) -> dict:
    return make_take(chart, news)

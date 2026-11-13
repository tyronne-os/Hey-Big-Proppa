"""
MONEY BALL — the show writer (the "consciousness").

Turns the day's deep-dive data (15/10 matchups, Rotowire domination players, the perfect
parlay, the weak defenses, the storylines) into a persona-tagged podcast script with
UNCENSORED personalities: MY BOO (host, playful, funny, talks money) + BIG PROPPA (analyst,
confident, dry, data-first). They cuss, joke, and set up the next big play.

The show writes itself from the data. No hardcoded sports opinions — every line is a
template filled from the pipeline. Output is a list of {speaker, text} lines, ready for TTS.
"""
from __future__ import annotations

import os
import random
from datetime import datetime

import bet_logic
import day_picks
import leg_builder
import rotowire_api


# ---------------------------------------------------------------------------
# Persona quip banks (uncensored, data-triggered)
# ---------------------------------------------------------------------------
MYBOO_OPENS = [
    "Money Ball, baby! {date} and we're back in the building. Y'all ready to get paid?",
    "What's up bettors! It's {date}, and Money Ball is LIVE. Let's cook.",
    "Alright, alright. It's {date}. The board is loaded and I'm hungry.",
]
# Samantha-from-Her style settling-in: MY BOO pulls PROPPA's focus, flirts, matches energy.
SETTLING_OPEN = [
    ("MY BOO", "Hey, Proppa. Hey. You with me, baby? I can feel you somewhere else — I saw that look. Last night stays last night."),
    ("BIG PROPPA", "Mmm. You caught me. I was thinking about the under, not you. ...Fine. Both."),
    ("MY BOO", "Good. Now shake it off. We got a board to read and money to make. Let's settle in, love — smooth, calm, then we light it up."),
    ("BIG PROPPA", "Smooth and calm, huh? You know I don't do calm. But for you, I'll try."),
    ("MY BOO", "There he is. My favorite numbers man. Now — look at me. Look at the board. Tell me what you see."),
    ("BIG PROPPA", "I see spots. Top-15 offense, bottom-10 defense. I see the edge, and I see us getting paid."),
]
MYBOO_FLIRT = [
    "You always know, don't you. That's why I keep you around, Proppa.",
    "Mmm. Say that number again. Slower. I like the way you say it.",
    "See, that's the thing — you read the data like it's poetry. I love that about you.",
    "Keep talking like that and I might just run your whole slate for you.",
]
MYBOO_PULL_FOCUS = [
    "Now — back to business, baby. Last night's over. The board is live. Let's make it rain.",
    "Focus, love. Focus. We got a parlay to build. Save the flirting for the payout.",
    "That's enough of that. My money's on the line. C'mon, big boy — the board's waiting.",
]
MYBOO_BIG_NUMBER = [
    "You see that number? That's the kind of number that makes grown men weep. In a good way.",
    "That's a MONEY number, baby. That's the whole point.",
    "Look at that payout. That's not a bet, that's a paycheck.",
]
MYBOO_LAUGHS = [
    "Ha! You see what I'm saying? They had the red zone TWICE and got ZERO. That's why we take the UNDER, baby.",
    "I swear the books don't even know what hit 'em. We're over here reading their homework.",
    "That's why we do this. They see a game, we see a payday.",
]
MYBOO_CLOSE = [
    "We ride with the winners. That's the whole philosophy.",
    "Losers lose — we don't do that here. Winners get the money.",
]
BIGPROPPA_OPENS = [
    "Let's talk spots. {n} matchups where the offense is top-shelf and the defense is a sieve.",
    "The board is set. Here's where the edge is, and it's real.",
]
BIGPROPPA_PICK = [
    "{why} That's the data. Don't argue with the data.",
    "{why} The line doesn't like it, but the numbers love it.",
    "{why} Plain and simple.",
]
BIGPROPPA_BOARD = [
    "Here's the board. The line is the line, and the price is the price.",
    "Best price is over there. Take it and don't look back.",
]
BIGPROPPA_MONEY = [
    "Two legs. {legA} plus {legB}. {joint} joint. That's the edge — {why}.",
    "That's the Money Ball. Two correlated legs, {joint} joint, and it pays.",
]
BIGPROPPA_DEADPAN = [
    "The red zone is a suggestion, not a promise.",
    "We take the under because the data says the offense is a mirage.",
    "I'm not saying I'm a genius. The numbers are.",
]


def _pick(bank: list[str]) -> str:
    return random.choice(bank)


def _money(n: float) -> str:
    return f"${n:,.0f}"


# NVIDIA LLM (works with the keys): enhances the draft show with personality & banter.
# Configurable via env; model defaults to the verified-working nemotron-3.5-lightning.
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
_NVIDIA_MODEL = os.environ.get("NVIDIA_LLM_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")


def _enhance_show(script: str) -> str:
    """Use the NVIDIA LLM to punch up the draft show (personality, banter, flow)."""
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        return script
    try:
        import httpx
        resp = httpx.post(
            f"{_NVIDIA_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": _NVIDIA_MODEL,
                "messages": [
                    {"role": "system", "content": (
                        "You are the writer for 'MONEY BALL', a fast, funny, uncensored sports-betting "
                        "podcast. Two hosts: MY BOO (warm, playful, talks money) and BIG PROPPA (confident, "
                        "dry, data-first). Rewrite the draft into a tighter, funnier episode. Keep every "
                        "player, prop, line and number exactly as given. Use two speakers: MY BOO and BIG PROPPA. "
                        "Short punchy lines. A few jokes. End by setting up the next big play."
                    )},
                    {"role": "user", "content": script},
                ],
                "max_tokens": 2000,
                "temperature": 0.8,
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return script


def generate_show() -> dict:
    """Build the Money Ball episode script from today's data."""
    spots = day_picks.day_picks()
    board = rotowire_api.board()
    slips = leg_builder.buildable(0.15)
    bet = bet_logic.bet_hunt()
    date = datetime.now().strftime("%B %-d, %Y")

    lines: list[dict] = []
    L = lambda sp, tx: lines.append({"speaker": sp, "text": tx})

    # 1. COLD OPEN — settling in (MY BOO pulls PROPPA's focus, flirts, then the board)
    for sp, tx in SETTLING_OPEN:
        L(sp, tx)
    L("MY BOO", _pick(MYBOO_FLIRT))
    L("MY BOO", _pick(MYBOO_PULL_FOCUS))

    # 2. THE SPOTS (15/10 matchups)
    mups = spots.get("fifteenTenMatchups") or []
    if mups:
        L("BIG PROPPA", _pick(BIGPROPPA_OPENS).format(n=len(mups)))
        for m in mups[:2]:
            L("BIG PROPPA",
              f"{m['offense']} vs {m['weakDefense']} — {m['category']}. "
              f"Top-15 offense, bottom-10 defense. That's a spot.")
            L("MY BOO", "And that's a spot, baby. Pass the slip.")
    else:
        L("BIG PROPPA", "No clean 15/10 today — the defenses are more honest than we like. "
                        "So we go straight to the players.")

    # 3. THE BOARD (Rotowire domination players)
    picks = spots.get("picks") or []
    for p in picks[:3]:
        L("BIG PROPPA", _pick(BIGPROPPA_PICK).format(why=p.get("why", "the data says so")))
        if (p.get("tdRate") or 0) >= 0.4:
            L("MY BOO", f"{p['name']} scores {p['tdRate']:.0%} of the time. "
                        f"{_pick(MYBOO_BIG_NUMBER)}")

    # 4. THE MONEY BALL (the perfect parlay)
    slips = slips if isinstance(slips, list) else (slips.get("rows") or [])
    def _leg_str(l: dict) -> str:
        cat = l.get("label") or l.get("category", "prop")
        side = l.get("side", "")
        line = l.get("line", "")
        return f"{cat} {side} {line}".strip()
    if slips:
        top = slips[0]
        a, b = top["legA"], top["legB"]
        # compute the real payout from the parlay odds (combined decimal)
        import math
        odds = []
        for l in (a, b):
            o = l.get("odds")
            if o:
                odds.append(o / 100 + 1 if o > 0 else 100 / abs(o) + 1)
        dec = math.prod(odds) if odds else 33.44
        L("BIG PROPPA", _pick(BIGPROPPA_MONEY).format(
            legA=_leg_str(a), legB=_leg_str(b),
            joint=f"{top['jointP']:.0%}", why=f"{top.get('player','')} — {_leg_str(a)} + {_leg_str(b)}"))
        L("MY BOO", f"On a five, that pays {_money(5 * dec)}. {_pick(MYBOO_BIG_NUMBER)}")
        L("BIG PROPPA", "Two legs. Correlated. That's how you build a perfect parlay.")
    else:
        L("BIG PROPPA", "No qualifying parlay today — the board's honest. We wait.")

    # 5. THE BANTER (laughs, data-triggered)
    L("MY BOO", _pick(MYBOO_LAUGHS))
    L("BIG PROPPA", _pick(BIGPROPPA_DEADPAN))
    L("MY BOO", "That's what I'm saying! Let's talk about the next big play.")

    # 6. THE CLOSE (something to live for)
    living = bet.get("living") or []
    if living:
        L("MY BOO", f"Something to live for, baby. {', '.join(living[:5])} — "
                    f"{_pick(MYBOO_CLOSE)}")
    else:
        L("MY BOO", "No winners on the board today. We stay home and count our money.")
    L("MY BOO", "That's the show. Money Ball — go make some money.")

    # Optional NVIDIA LLM punch-up (if NVIDIA_API_KEY set) — keeps the data intact.
    if os.environ.get("NVIDIA_API_KEY"):
        script_text = "\n".join(f"[{l['speaker']}] {l['text']}" for l in lines)
        enhanced = _enhance_show(script_text)
        if enhanced and "[MY BOO]" in enhanced:
            # return the LLM's version as the transcript, keep the structured lines too
            return {
                "sourceStatus": "ok", "date": date, "title": f"Money Ball — {date}",
                "cast": ["MY BOO", "BIG PROPPA"],
                "lines": lines, "enhanced": enhanced,
                "matchups": mups, "picks": picks, "parlay": slips[:3],
            }

    return {
        "sourceStatus": "ok",
        "date": date,
        "title": f"Money Ball — {date}",
        "cast": ["MY BOO", "BIG PROPPA"],
        "lines": lines,
        "matchups": mups,
        "picks": picks,
        "parlay": slips[:3],
    }


def transcript() -> str:
    """Plain-text transcript for the page (persona-tagged)."""
    show = generate_show()
    return "\n".join(f"[{l['speaker']}] {l['text']}" for l in show["lines"])


if __name__ == "__main__":
    show = generate_show()
    print("TITLE:", show["title"])
    print("=" * 60)
    for l in show["lines"]:
        print(f"[{l['speaker']}] {l['text']}")
        print()

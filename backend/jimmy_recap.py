"""
JIMMY Weekly Recap: the Big Proppa booth breaks down your week.

Three hosts, ~500 words, built around three ideas:
  1. Play of the Week -- the single leg that decided your week, with the real stat and margin.
  2. The Booth Remembers -- season storylines: Hero, Villain, bankroll arc, callbacks to past weeks.
  3. Bet the Booth -- each host closes with a pick for next week; the player can tail one, and the
     booth's record is kept all season.

Jonah Jacques opens (play-by-play, emotion), MY BOO breaks down the numbers, Julian Feltus closes
on structure and the booth standings.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import Optional

import jimmy_history as hist
from jimmy_backtester import HOSTS, SEASON_WEEKS, JimmyBacktester, Leg, Slip


def _n(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def _money(x: float) -> str:
    return f"${abs(x):,.0f}" if float(x).is_integer() else f"${abs(x):,.2f}"


def _gap(margin: float, unit: str) -> str:
    m = abs(margin)
    if m == 0.5:
        return f"half a {unit[:-1]}"
    if m < 1:
        return f"{_n(m)} of a {unit[:-1]}"
    return f"{_n(m)} {unit if m != 1 else unit[:-1]}"


def _close(margin: float, line: float) -> bool:
    return abs(margin) <= max(0.08 * line, 1.0)


def _pl(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _name(n: str) -> str:
    return n[:-1] if n.endswith(".") else n


def _side(leg_or_pick) -> str:
    over = leg_or_pick.is_over if isinstance(leg_or_pick, Leg) else leg_or_pick["is_over"]
    return "over" if over else "under"


# ---------------------------------------------------------------- 1. play of the week

def play_of_week(slips: list[Slip], unit_of) -> Optional[dict]:
    """Heartbreaker (lone miss on an otherwise live ticket) > clutch (thinnest hit on a cashed ticket) > worst miss."""
    best, best_key = None, None
    for slip in slips:
        live = [l for l in slip.legs if l.result is not None]
        misses = [l for l in live if not l.result]
        for leg in live:
            if not leg.result and len(misses) == 1 and len(live) > 1 and _close(leg.margin, leg.line):
                kind, key = "heartbreaker", (0, abs(leg.margin))
            elif leg.result and slip.result:
                kind, key = "clutch", (1, abs(leg.margin))
            elif not leg.result:
                kind, key = "bust", (2, -abs(leg.margin))
            else:
                continue
            if best_key is None or key < best_key:
                best_key = key
                best = {"kind": kind, "slip_id": slip.slip_id, "slip_legs": len(slip.legs),
                        "slip_hit": slip.legs_hit, "slip_wager": slip.wager,
                        "slip_payout_if": slip.wager * (2 ** len(live)), "leg": leg}
    if not best:
        return None
    leg = best.pop("leg")
    unit = unit_of(leg.prop_type)
    best.update({"player_id": leg.player_id, "player_name": leg.player_name, "team": leg.team, "headshot": leg.headshot,
                 "prop_type": leg.prop_type, "label": leg.label, "line": leg.line, "is_over": leg.is_over,
                 "actual": leg.actual_value, "margin": round(leg.margin, 1), "unit": unit,
                 "headline": {"heartbreaker": f"MISSED BY {_gap(leg.margin, unit).upper()}",
                              "clutch": f"CLEARED BY {_gap(leg.margin, unit).upper()}",
                              "bust": f"{_n(leg.actual_value)} ON A {_n(leg.line)} LINE"}[best["kind"]]})
    return best


# ---------------------------------------------------------------- 2. the booth remembers

def storylines(bt: JimmyBacktester, week: int) -> dict:
    st = bt.state
    hits, misses, names = Counter(), Counter(), {}
    bank, peak, peak_week, low = st.starting_bankroll, st.starting_bankroll, 0, st.starting_bankroll
    week_won: dict[int, bool] = {}
    for w in range(1, week + 1):
        ws = [s for s in st.slips if s.week == w]
        week_delta = 0.0
        for s in ws:
            for l in s.legs:
                if l.result is None:
                    continue
                names[l.player_id] = l.player_name
                (hits if l.result else misses)[l.player_id] += 1
            week_delta += (s.payout or 0) - s.wager if s.result is not None else 0
        week_delta += sum(b["amount"] for b in st.bonuses if b["week"] == w)
        bank += week_delta
        if ws:
            week_won[w] = week_delta > 0
        if bank > peak:
            peak, peak_week = bank, w
        low = min(low, bank)

    run, w = 0, week
    while w in week_won and week_won[w] == week_won.get(week):
        run, w = run + 1, w - 1

    hero = next((p for p, c in hits.most_common() if c >= 2), None)
    villain = next((p for p, c in misses.most_common() if c >= 2 and p != hero), None)
    this_week = [l for s in st.slips if s.week == week for l in s.legs if l.result is not None]
    return {
        "hero": {"player_id": hero, "player_name": names[hero], "hits": hits[hero], "misses": misses[hero]} if hero else None,
        "villain": {"player_id": villain, "player_name": names[villain], "misses": misses[villain], "hits": hits[villain],
                    "redeemed": any(l.player_id == villain and l.result for l in this_week)} if villain else None,
        "run": {"weeks": run, "kind": "winning" if week_won.get(week) else "losing"},
        "bankroll": {"now": round(bank, 2), "peak": round(peak, 2), "peak_week": peak_week, "low": round(low, 2),
                     "from_peak": round(peak - bank, 2)},
        "legs_season": {"hit": sum(hits.values()), "miss": sum(misses.values())},
    }


# ---------------------------------------------------------------- 3. bet the booth

def make_picks(bt: JimmyBacktester, week: int, story: dict) -> Optional[dict]:
    nxt = week + 1
    if nxt > SEASON_WEEKS:
        return None
    if nxt in bt.state.booth_picks:
        return bt.state.booth_picks[nxt]
    board = hist.board(bt.year, nxt, size=30)
    if len(board) < 3:
        return None
    used: set[str] = set()

    def take(p: dict, over: bool, why: str) -> dict:
        used.add(p["player_id"])
        return {"player_id": p["player_id"], "player_name": p["player_name"], "team": p["team"], "headshot": p["headshot"],
                "prop_type": p["prop_type"], "label": p["label"], "line": p["line"], "is_over": over,
                "confidence": p["confidence"] if over else 100 - p["confidence"] + 10, "why": why,
                "actual": None, "result": None}

    boo = take(board[0], True, f"Highest-rated number on the board. {_n(board[0]['avg'])} average against a {_n(board[0]['line'])} line.")

    hero_id = (story.get("hero") or {}).get("player_id")
    hot = [p for p in board if p["player_id"] not in used and (p["player_id"] == hero_id or p["form"] == "hot")]
    hot.sort(key=lambda p: (p["player_id"] != hero_id, -(p["last3"] - p["line"])))
    jp = hot[0] if hot else next(p for p in board if p["player_id"] not in used)
    jonah = take(jp, True, "He's been your guy all year. Ride him." if jp["player_id"] == hero_id
                 else f"{_n(jp['last3'])} a game over his last three. Hot hand.")

    fades = [p for p in board if p["player_id"] not in used and p["last3"] < p["line"]]
    fades.sort(key=lambda p: p["last3"] / p["line"])
    if fades:
        jf = fades[0]
        julian = take(jf, False, f"Market's still pricing the old him. {_n(jf['last3'])} over his last three, line is {_n(jf['line'])}.")
    else:
        jf = next(p for p in board if p["player_id"] not in used and p["prop_type"] != boo["prop_type"])
        julian = take(jf, True, "Different prop family than MY BOO. Spread the risk.")

    picks = {"MY BOO": boo, "Jonah Jacques": jonah, "Julian Feltus": julian}
    bt.state.booth_picks[nxt] = picks
    return picks


def _pick_line(p: dict) -> str:
    return f"{p['player_name']} {_side(p)} {_n(p['line'])} {p['label'].lower()}"


# ---------------------------------------------------------------- the scripts

def _jonah(r: random.Random, week: int, pow_: Optional[dict], story: dict, cashed: int, n: int, delta: float,
           last_booth: Optional[dict], tailed: Optional[str], pick: Optional[dict], smash: Optional[Leg]) -> str:
    out = []
    if week == 1:
        out.append("Welcome to the Big Proppa booth. Week 1 is in the books, and we already have a story.")
    elif week == SEASON_WEEKS:
        out.append("Final week of the season. Everything you built comes down to this.")
    elif week == SEASON_WEEKS // 2:
        out.append(f"We are at the halfway mark, Week {week}.")
    if pow_ and pow_["kind"] == "heartbreaker":
        need = f"{_n(pow_['line'])}" if pow_["is_over"] else f"to stay under {_n(pow_['line'])}"
        out.append(r.choice([
            f"Pull it up on the big board, because this one is going to sting. {_name(pow_['player_name'])}. You needed {need} {pow_['label'].lower()}. He gave you {_n(pow_['actual'])}.",
            f"Week {week}, and I have to start with the one that got away. {pow_['player_name']}, {_side(pow_)} {_n(pow_['line'])} {pow_['label'].lower()}. Final number: {_n(pow_['actual'])}.",
        ]))
        out.append(f"{_pl(pow_['slip_hit'], 'leg')} cashed on that ticket and one man left you {_gap(pow_['margin'], pow_['unit'])} short of a {_money(pow_['slip_payout_if'])} payday. That is your Play of the Week, and it hurts.")
    elif pow_ and pow_["kind"] == "clutch":
        out.append(r.choice([
            f"Somebody get me a towel. {pow_['player_name']}, {_side(pow_)} {_n(pow_['line'])} {pow_['label'].lower()}, and he finishes at {_n(pow_['actual'])}.",
            f"Week {week}, Play of the Week, and it came down to the wire. {pow_['player_name']} needed {_n(pow_['line'])}. He got {_n(pow_['actual'])}.",
        ]))
        thin = abs(pow_["margin"]) <= (2 if pow_["unit"] == "yards" else 0.5)
        out.append(f"Cleared it by {_gap(pow_['margin'], pow_['unit'])}. "
                   + ("The whole ticket was living on a sliver" if thin else "Closest leg on the ticket, and it held")
                   + f". Cashed for {_money(pow_['slip_payout_if'])}.")
    elif pow_:
        out.append(f"I'm not going to sugarcoat it. {pow_['player_name']} put up {_n(pow_['actual'])} on a {_n(pow_['line'])} line. That wasn't close, and that's your Play of the Week for all the wrong reasons.")

    if smash and (not pow_ or smash.player_id != pow_["player_id"]):
        out.append(f"On the other side of the ledger, {_name(smash.player_name)} buried his {_n(smash.line)} {smash.label.lower()} line with {_n(smash.actual_value)}. "
                   + r.choice(["Never in doubt.", "That one was cashed by halftime.", "Put that on a poster."]))
    run = story["run"]
    if cashed == n:
        out.append(r.choice(["You went perfect. Every ticket. Up " + _money(delta) + " on the week.",
                             f"{n} for {n}. Clean sheet. Plus {_money(delta)}."]))
    elif cashed:
        out.append(f"{cashed} of {n} tickets cashed, and the week {'nets you ' + _money(delta) if delta >= 0 else 'still costs you ' + _money(delta)}.")
    else:
        out.append(f"Zero for {n}. Minus {_money(delta)}. Those are the facts.")
    if run["weeks"] >= 3:
        out.append(f"That's {run['weeks']} straight {run['kind']} weeks. " + ("This is a run now. Don't you dare get loose." if run["kind"] == "winning" else "We need a stop, and we need it now."))

    v = story.get("villain")
    if v and v["redeemed"]:
        out.append(f"And somebody tell {v['player_name']} the booth sees him. He burned you {v['misses']} times this year and finally showed up.")
    if last_booth and tailed and tailed in last_booth:
        p = last_booth[tailed]
        if p["result"] is not None:
            out.append(f"You tailed { {'MY BOO': 'MY BOO', 'Julian Feltus': 'Julian'}.get(tailed, 'me') } last week on {p['player_name']}. "
                       + ("It hit. Booth bonus is in your account." if p["result"] else f"He finished at {_n(p['actual'])}. That one's on us."))
    if pick:
        out.append(f"My pick for next week: {_pick_line(pick)}. {pick['why']}")
    out.append(r.choice(["MY BOO, walk them through it.", "MY BOO, what are the numbers saying?", "MY BOO, take it from here."]))
    return " ".join(out)


def _myboo(r: random.Random, week: int, slips: list[Slip], story: dict, cashed: int, n: int, wager_size: float,
           pick: Optional[dict]) -> str:
    legs = [l for s in slips for l in s.legs if l.result is not None]
    hit = sum(1 for l in legs if l.result)
    voids = sum(1 for s in slips for l in s.legs if l.result is None)
    bank = story["bankroll"]
    out = [r.choice(["Let me give you the numbers, because the numbers don't have feelings.",
                     "Jonah's got the emotion covered. I've got the math.",
                     "Okay. Let's talk about what actually happened."])]
    out.append(f"You played {_pl(len(legs), 'leg')} this week and {hit} landed. That's {round(100 * hit / len(legs)) if legs else 0} percent.")
    near = [l for l in legs if not l.result and _close(l.margin, l.line)]
    if near:
        out.append(f"{_pl(len(near), 'miss')[:-1] + 'es' if len(near) != 1 else '1 miss'} came within a whisker of the line. "
                   + ("That's variance, not bad reads. Same process next week." if len(near) * 2 >= len(legs) - hit else "Some were close. Most weren't, so look at the reads."))
    if hit == 0:
        out.append("Nothing landed. That isn't structure, that's the reads, so we start over Friday.")
    elif n and cashed < n and legs:
        survivors = hit / len(legs)
        out.append(f"Here's the thing about parlays: at that hit rate, a {max(len(s.legs) for s in slips)}-leg ticket only cashes about "
                   f"{round(100 * survivors ** max(len(s.legs) for s in slips))} percent of the time. The legs were fine. The structure is the tax.")
    if voids:
        out.append(f"{voids} leg{'s' if voids > 1 else ''} voided because the player sat. Check the injury report Friday.")
    walk = []
    for sl in slips:
        for l in sl.legs:
            if l.result is None:
                walk.append(f"{_name(l.player_name)} didn't play, so that leg voids")
            else:
                walk.append(f"{_name(l.player_name)}, {_side(l)} {_n(l.line)} {l.label.lower()}, finished with {_n(l.actual_value)}. "
                            + ("Hit." if l.result else f"Miss by {_gap(l.margin, hist.PROPS[l.prop_type]['unit'])}."))
    if walk:
        out.append("Leg by leg. " + " ".join(walk[:8]))
    season = story["legs_season"]
    total = season["hit"] + season["miss"]
    if total:
        out.append(f"Season to date, you're {season['hit']} and {season['miss']} on individual legs, {round(100 * season['hit'] / total)} percent.")
    h, v = story.get("hero"), story.get("villain")
    if h:
        out.append(f"Your Hero this season is {_name(h['player_name'])}: {_pl(h['hits'], 'hit')}, {_pl(h['misses'], 'miss')[:-1] + 'es' if h['misses'] != 1 else '1 miss'}.".replace(", 0 misses", ", zero misses"))
    if v:
        out.append(f"Your Villain is {_name(v['player_name'])}: {v['misses']} misses. Stop giving him your money unless the number moves.")
    start = 100
    if bank["from_peak"] > 0 and bank["peak_week"]:
        out.append(f"Bankroll sits at {_money(bank['now'])}, {_money(bank['from_peak'])} off your Week {bank['peak_week']} high.")
    elif bank["now"] < start:
        out.append(f"Bankroll sits at {_money(bank['now'])}, {_money(start - bank['now'])} under the {_money(start)} you started with.")
    else:
        out.append(f"Bankroll sits at {_money(bank['now'])}. That's a season high.")
    exposure = wager_size * len(slips)
    if bank["now"]:
        pct = round(100 * exposure / bank["now"])
        out.append(f"Next week you're risking {_money(exposure)} across {len(slips)} slip{'s' if len(slips) > 1 else ''}, {pct} percent of your roll. "
                   + ("That's aggressive. One bad Sunday and you're in trouble." if pct >= 20 else "That's a sustainable number."))
    if bank["now"] < 500 <= bank["now"] + 150:
        out.append(f"You're within {_money(500 - bank['now'])} of the $500 tier, where your stake goes to $10.")
    if pick:
        out.append(f"My pick: {_pick_line(pick)}. {pick['why']}")
    out.append(r.choice(["Julian, what's the lesson?", "Julian, bring us home.", "Julian, you've been quiet over there."]))
    return " ".join(out)


def _julian(r: random.Random, week: int, slips: list[Slip], story: dict, record: dict, picks: Optional[dict],
            all_slips: list[Slip]) -> str:
    pick = (picks or {}).get("Julian Feltus")
    legs = [l for s in slips for l in s.legs if l.result is not None]
    out = [r.choice(["Let me zoom out, because the week only matters for what it teaches you.",
                     "I want to talk structure.",
                     "Here's what I'd take from this week."])]
    by_prop = Counter((l.label, bool(l.result)) for l in legs)
    props = sorted({l.label for l in legs})
    if props:
        best = max(props, key=lambda p: (by_prop[(p, True)] / max(1, by_prop[(p, True)] + by_prop[(p, False)])))
        rest = [p for p in props if p != best] or [best]
        worst = min(rest, key=lambda p: (by_prop[(p, True)] / max(1, by_prop[(p, True)] + by_prop[(p, False)])))
        out.append(f"{best.title()} went {by_prop[(best, True)]} for {by_prop[(best, True)] + by_prop[(best, False)]} this week."
                   + (f" {worst.title()} went {by_prop[(worst, True)]} for {by_prop[(worst, True)] + by_prop[(worst, False)]}." if worst != best else ""))
    season_legs = [l for s in all_slips for l in s.legs if l.result is not None]
    fam = Counter((l.label, bool(l.result)) for l in season_legs)
    fams = {lab for lab, _ in fam}
    rated = [(fam[(f, True)] / (fam[(f, True)] + fam[(f, False)]), f) for f in fams if fam[(f, True)] + fam[(f, False)] >= 4]
    if len(rated) >= 2:
        top, low = max(rated), min(rated)
        out.append(f"Season-long, your best prop family is {top[1].lower()} at {round(100 * top[0])} percent. Your worst is {low[1].lower()} at {round(100 * low[0])}. "
                   "Build your anchor leg from the first one.")
    teams = Counter(l.team for s in slips for l in s.legs)
    stacked = [t for t, c in teams.items() if c >= 2]
    if stacked:
        out.append(f"You stacked {stacked[0]} on the same week. When that offense stalls, it takes every leg with it. One team, one leg.")
    avg_legs = sum(len(s.legs) for s in slips) / len(slips)
    if avg_legs >= 4:
        out.append(f"You're averaging {_n(round(avg_legs, 1))} legs a ticket. Each leg you add doubles the payout and roughly halves your chances. Try a three-leg ticket and watch the cash rate move.")
    elif avg_legs <= 2:
        out.append("Short tickets, small payouts, high hit rate. That's how you survive September. Earn the right to go longer.")
    run = story["run"]
    if run["kind"] == "winning" and run["weeks"] >= 2:
        out.append("When you're running hot, the move is not more legs. It's the same process at a bigger stake.")
    elif run["kind"] == "losing" and run["weeks"] >= 2:
        out.append("Two bad weeks is variance. Three is a pattern. Change one thing, not everything.")
    if week <= 3:
        out.append("Early in the year the lines lean on last season. Back players whose role didn't change, and be careful with anybody on a new team or a new offense.")
    elif week >= 13:
        out.append("Late season, watch for teams that have clinched or checked out. Snap counts drop before the box score tells you.")
    else:
        out.append("Midseason, the lines have caught up to the obvious. Your edge is the player whose last three games don't match his season average.")
    short = {"MY BOO": "MY BOO", "Jonah Jacques": "Jonah", "Julian Feltus": "me"}
    standings = sorted(HOSTS, key=lambda h: (-record[h][0], record[h][1]))
    if sum(record[h][0] + record[h][1] for h in HOSTS):
        parts = [f"{short[h]} {record[h][0]} and {record[h][1]}" for h in standings]
        out.append("Booth standings: " + ", ".join(parts) + ".")
    else:
        out.append("The booth's record starts now. All three of us are putting a pick on the line, and we keep score.")
    if picks:
        boo, jon = picks.get("MY BOO"), picks.get("Jonah Jacques")
        if boo and jon:
            out.append(f"Here's how I read the board. MY BOO took {_pick_line(boo)}, the highest-rated number. "
                       f"Jonah is on {_pick_line(jon)}, riding the hot hand.")
            out.append("Those two are both overs, so if the same game script hurts one, it can hurt both. Tailing two of us is not diversification." if boo["is_over"] and jon["is_over"]
                       else "That's a healthy split between an over and an under. Tail one, don't tail both.")
    if pick:
        out.append(f"My pick: {_pick_line(pick)}. {pick['why']} Tail whoever you trust.")
    return " ".join(out)


# ---------------------------------------------------------------- the conversation

_REACT = [
    "{prev}, love the energy. Let me put some numbers behind it.",
    "{prev}, that's the story. Now the receipts.",
    "Easy, {prev}. Let's see if the numbers agree with you.",
    "{prev}, hold that thought. I want to show the work first.",
]
_INTERRUPT = {
    "Perfect Week": ["Clean sheet, and I'll say it: that's discipline, not luck.", "Perfect week. Don't go getting loose now."],
    "Winning Week": ["Good week, but I'd still look at the miss.", "Winning is fine. Repeatable is better."],
    "Split Decision": ["Split decision. Let's figure out which half to keep.", "Half right is still a lesson."],
    "Rough Sunday": ["Rough one. Let's not pretend otherwise.", "Nothing's going to make that week feel good. Let's make it useful."],
}


def booth_turns(segments: list[dict], arc: str, r: random.Random) -> list[dict]:
    """Turn the three monologues into a conversation: sentence-sized turns, each host answering the last."""
    turns: list[dict] = []
    prev = None
    for i, seg in enumerate(segments):
        speaker = seg["speaker"]
        if prev is not None:
            if i == 1:
                line = r.choice(_INTERRUPT.get(arc, _INTERRUPT["Split Decision"]))
            else:
                line = r.choice(_REACT).format(prev=HOST_NAME.get(prev, prev))
            turns.append({"speaker": speaker, "text": line, "beat": "react"})
        for sentence in split_sentences(seg["text"]):
            turns.append({"speaker": speaker, "text": sentence, "beat": "say"})
        prev = speaker
    return turns


HOST_NAME = {"Jonah Jacques": "Jonah", "MY BOO": "MY BOO", "Julian Feltus": "Julian"}


def split_sentences(text: str) -> list[str]:
    import re
    return [t.strip() for t in re.split(r"(?<=[.!?])\s+", text) if t.strip()]


# ---------------------------------------------------------------- entry point

def generate_weekly_recap(bt: JimmyBacktester, week: int) -> dict:
    st = bt.state
    slips = [s for s in st.slips if s.week == week]
    if not slips:
        return {"week": week, "title": f"Week {week}: The booth is waiting", "segments": [],
                "error": "Place a slip this week and the booth will break it down."}
    graded = [s for s in slips if s.result is not None]
    n, cashed = len(graded), sum(1 for s in graded if s.result)
    delta = sum((s.payout or 0) - s.wager for s in graded)
    r = random.Random(st.year * 1000 + week)

    unit_of = lambda prop: hist.PROPS[prop]["unit"]
    pow_ = play_of_week(slips, unit_of)
    hits = [l for s in slips for l in s.legs if l.result]
    smash = max(hits, key=lambda l: l.margin / max(l.line, 1)) if hits else None
    story = storylines(bt, week)
    picks = make_picks(bt, week, story)
    last_booth = st.booth_picks.get(week) if week in st.booth_graded else None
    tailed = st.booth_tails.get(week)

    if n and cashed == n:
        arc = "Perfect Week"
    elif cashed > n / 2:
        arc = "Winning Week"
    elif cashed:
        arc = "Split Decision"
    else:
        arc = "Rough Sunday"
    title = f"Week {week}: {arc}"
    if pow_:
        title += f" / {pow_['player_name']} {pow_['headline'].title()}"

    texts = [
        ("Jonah Jacques", "Play-by-Play", _jonah(r, week, pow_, story, cashed, n, delta, last_booth, tailed, (picks or {}).get("Jonah Jacques"), smash)),
        ("MY BOO", "Analyst", _myboo(r, week, slips, story, cashed, n, bt.calculate_wager_size(), (picks or {}).get("MY BOO"))),
        ("Julian Feltus", "Strategy", _julian(r, week, slips, story, st.booth_record, picks, [s for s in st.slips if s.week <= week])),
    ]
    segments = [{"speaker": s, "role": role, "text": t, "word_count": len(t.split())} for s, role, t in texts]
    return {
        "week": week, "title": title, "arc": arc, "segments": segments,
        "total_words": sum(s["word_count"] for s in segments),
        "bankroll_delta": round(delta, 2), "slips_cashed": cashed, "slips_total": n,
        "cashed_pct": round(100 * cashed / n) if n else 0,
        "key_stat": "UNDEFEATED" if n and cashed == n else f"{cashed}/{n} SLIPS CASHED",
        "turns": booth_turns(segments, arc, random.Random(st.year * 1000 + week + 7)),
        "play_of_week": pow_, "storylines": story,
        "booth": {"picks": picks, "record": st.booth_record, "last_week": last_booth, "tailed_last_week": tailed,
                  "tailed_next_week": st.booth_tails.get(week + 1), "pick_week": week + 1},
    }

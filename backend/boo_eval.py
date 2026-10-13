"""
MY BOO's WRITTEN EVALUATION -- the 300 to 500 word opening of every report.

Plain code, no LLM. Every sentence is a template filled from the measured report (grades, tickets, killers, exposure,
structure lab, tally), so the same ledger always reads the same and every number can be traced to the page below it.
Sentences carry a priority; if the piece runs past the ceiling the lowest-priority ones drop, and if it runs short
the standing-principle sentences are added, so it always lands between MIN_WORDS and MAX_WORDS.
"""
from __future__ import annotations

MIN_WORDS, MAX_WORDS = 300, 500


def _pct(a: float, b: float) -> int:
    return round(100 * a / b) if b else 0


def _n(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "?"
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def _words(paras: list[list[tuple[int, str]]]) -> int:
    return sum(len(s.split()) for p in paras for _, s in p)


def evaluate(r: dict, of_label: str | None = None) -> dict | None:
    n = r.get("night")
    if not n:
        return None
    T, L = n["tickets"], n["legs"]
    ks = n.get("killers") or []
    lab = r.get("lab") or {}
    tally = r.get("tally") or {}
    bp = (r.get("blueprint") or {}).get("rules") or []
    td = r.get("tdPolicy") or {}
    jev = r.get("jev")
    label = of_label or (r.get("entry") or {}).get("label") or n.get("game", "the game")
    decided = T["won"] + T["lost"]
    tick_pct, leg_pct = _pct(T["won"], decided), _pct(L["passed"], L["graded"])
    profit = T["returned"] - T["staked"]
    small = [s for s in T["bySize"] if s["legs"] <= 3]
    big = [s for s in T["bySize"] if s["legs"] > 3]
    sw, st = sum(s["won"] for s in small), sum(s["tickets"] for s in small)
    bw, bt = sum(s["won"] for s in big), sum(s["tickets"] for s in big)
    shapes = sorted((s for s in lab.get("shapes", []) if s["combos"] >= 200), key=lambda s: -s["winRate"])
    best = shapes[0] if shapes else None
    z = ks[0] if ks else None
    top = (n.get("exposure") or {}).get("topLegs") or []
    facts = n.get("facts") or []

    P: list[list[tuple[int, str]]] = []

    # 1. the verdict
    p = [(9, f"Here is my honest read of how we attacked {label}. {facts[0] + '. ' if facts else ''}"
             f"We graded {L['graded']} unique predictions, {L['passed']} passed ({leg_pct}%), and {T['won']} of {decided} tickets cashed ({tick_pct}%)"
             f"{', for ' + ('+' if profit >= 0 else '-') + '$' + format(abs(profit), '.0f') + ' on $' + format(T['staked'], '.0f') + ' staked' if T['staked'] else ''}.")]
    if leg_pct >= 50 and tick_pct < leg_pct:
        p.append((8, f"Read that gap carefully: we were right on more than half of the individual calls and still lost most of the tickets. That is not a prediction problem, it is a construction problem, and construction is something we control."))
    elif leg_pct < 50:
        p.append((8, f"We were right on fewer than half of the individual calls, so this one is partly a prediction problem, and no ticket structure fixes a read that is wrong. The fixes below start with which legs we trust."))
    if T.get("lostByOne"):
        p.append((7, f"{T['lostByOne']} of the {T['lost']} losing tickets died by exactly one leg, which is the cost of asking every ticket to be perfect."))
    P.append(p)

    # 2. contagion
    p = []
    if z:
        who = z["label"].split(" over ")[0].split(" under ")[0]
        p.append((9, f"The damage came from contagion. {z['label']} finished at {_n(z['actual'])} against a {_n(z['line'])} line and sat on {z['tickets']} tickets"
                     f"{', the only miss on ' + str(z['killedAlone']) + ' of them' if z['killedAlone'] else ''}. One bad number, many dead tickets."))
        names: dict[str, int] = {}
        for k in ks:
            nm = k["label"].split(" over ")[0].split(" under ")[0]
            names[nm] = names.get(nm, 0) + k["tickets"]
        dup = [(nm, c) for nm, c in names.items() if sum(1 for k in ks if k["label"].startswith(nm)) > 1]
        if dup:
            nm, c = max(dup, key=lambda x: x[1])
            p.append((6, f"{nm} failed in more than one prop line, {c} ticket slots in total, which is the same mistake in a different font."))
    if top:
        t = top[0]
        p.append((5, f"The most-copied leg was {t['label']}, on {t['tickets']} tickets ({round(t['share'] * 100)}% of the card), and it {'passed' if t['result'] == 'HIT' else 'failed'}. "
                     f"Heavy reuse is a coin flip on the whole card, and this time it landed {'in our favour' if t['result'] == 'HIT' else 'against us'}."))
    P.append(p)

    # 3. length
    p = []
    if st and bt:
        p.append((9, f"Length is the clearest signal. Tickets of three legs or fewer cashed {sw} of {st}; tickets of four or more cashed {bw} of {bt}. "
                     f"Every extra leg multiplies the chance of one dead leg, and we keep paying for payout we rarely collect."))
    if n.get("whatIf"):
        trim = next((w for w in n["whatIf"] if w.get("kind") == "trim"), None)
        if trim:
            p.append((6, f"Trimming every ticket to its three most likely legs would have saved {trim['ticketsSaved']} losing tickets on the same predictions."))
    P.append(p)

    # 4. targets and role
    p = []
    by_type = (L.get("byType") or {})
    rec = by_type.get("RECEIVING YDS")
    if rec and rec["n"] >= 4:
        p.append((7, f"Receiving yardage went {rec['passed']} for {rec['n']} ({_pct(rec['passed'], rec['n'])}%). Yardage props are the noisiest thing on the board, so they belong with the receivers who dominate targets, "
                     f"not with whoever is third in the pecking order. A WR3 at four targets a game cannot carry a ticket, and I do not want him as the load-bearing leg again."))
    P.append(p)

    # 5. the plan
    p = [(9, "Here is what has to change for the numbers to turn around."),
         (9, "One: a player and a prop appear once. If he is already on a card, use a different market (receptions, rushing, or rushing plus receiving yards) and never the same prop on every ticket. Crazy Horse is the only exception."),
         (9, "Two: three legs and go home, with at most one long ticket a night."),
         (8, "Three: legs go to players who are essential to their offense and see the targets or the carries.")]
    if best:
        p.append((8, f"Four: build around the shape that wins most often. Replayed on {lab.get('games', 'our')} games of graded predictions, {best['shape']} cashed {round(best['winRate'] * 100)}% of {best['combos']} tickets."))
    p.append((6, "Five: props the model rates under 60% go to their safe line, the posted line cut 15%, because a smaller payout beats a dead ticket."))
    if td.get("essential"):
        p.append((6, f"Touchdown legs are back, but only for essential players. They scored in {round(td['essential']['rate'] * 100)}% of games this season versus {round(td['others']['rate'] * 100)}% for everyone else, so they get a seat, not the whole card."))
    if jev:
        p.append((4, f"JEV went {jev['jevRight']} and the Big Proppa Line {jev['bplRight']} on the graded reads, so JEV is a tiebreaker until it earns more."))
    P.append(p)

    # 6. the season and what follows
    p = []
    s = tally.get("season")
    if s and (s["tw"] + s["tl"]):
        p.append((7, f"For the season we are {s['tw']} and {s['tl']} on tickets ({s['ticketPct']}%) and {s['lw']} and {s['ll']} on legs ({s['legPct']}%). "
                     f"The legs are fine. The tickets are where we are bleeding, which is why every rule above is about how the legs are combined."))
    p.append((9, "Everything below is the evidence: who infected the tickets, how we would have won, which ticket shapes pay, and the blueprint for the next game."))
    P.append(p)

    # trim to the ceiling, dropping lowest-priority sentences first
    while _words(P) > MAX_WORDS:
        cand = [(pr, i, j) for i, pp in enumerate(P) for j, (pr, _) in enumerate(pp)]
        pr, i, j = min(cand, key=lambda x: (x[0], -x[1]))
        P[i].pop(j)
    # pad to the floor with standing principles
    pad = ["A parlay is a bet that every leg lands, so the discipline is to make each leg as close to a coin flip we are already winning as we can, then stop adding legs.",
           "Hindsight in the NFL is weekly: the same teams, the same quarterbacks and the same target hogs come around again, which is why this report gets built the same way every game.",
           "None of this needs a hot take. It needs the same checklist applied every time, which is what this page is for."]
    k = 0
    while _words(P) < MIN_WORDS and k < len(pad):
        P[-1].insert(-1 if len(P[-1]) > 1 else 0, (1, pad[k]))
        k += 1
    paras = [" ".join(s for _, s in p).strip() for p in P if p]
    words = sum(len(x.split()) for x in paras)
    return {"title": f"MY BOO'S EVALUATION · {label}", "paragraphs": paras, "words": words}

"""
JIMMY Weekly Recap: Broadcast-style analysis with MY BOO + Big Proppa Sports Cast team.

Generates 500-word recaps split between three voices:
- MY BOO: analytical breakdown (stats, strategy)
- Jonah Jacques: emotional/narrative perspective
- Julian Feltus: strategic insights and patterns

Each voice gets ~170 words. Ready for TTS (HuggingFace integration in next phase).
"""
from __future__ import annotations
from typing import Optional
from jimmy_backtester import SeasonState


def generate_weekly_recap(state: SeasonState, week: int) -> dict:
    """
    Generate a 500-word weekly recap split across three voices.

    Returns:
    {
        "week": 5,
        "title": "Week 5 Recap: The Streak Begins",
        "segments": [
            {
                "speaker": "MY BOO",
                "role": "Analyst",
                "text": "...",
                "word_count": 167
            },
            {
                "speaker": "Jonah Jacques",
                "role": "Narrative",
                "text": "...",
                "word_count": 167
            },
            {
                "speaker": "Julian Feltus",
                "role": "Strategy",
                "text": "...",
                "word_count": 166
            }
        ],
        "total_words": 500,
        "bankroll_delta": 45.00,
        "slips_cashed": 2,
        "cashed_pct": 100,
        "key_stat": "🔥 UNDEFEATED THIS WEEK"
    }
    """
    week_slips = [s for s in state.slips if s.week == week]

    if not week_slips:
        return {
            "week": week,
            "title": f"Week {week} Recap: Waiting for Kickoff",
            "segments": [],
            "error": "No slips submitted this week",
        }

    # Calculate week stats
    total_legs = sum(len(s.legs) for s in week_slips)
    cashed = sum(1 for s in week_slips if s.result)
    cash_rate = (cashed / len(week_slips) * 100) if week_slips else 0
    total_wagered = sum(s.wager for s in week_slips)
    total_won = sum(s.payout or 0 for s in week_slips)
    bankroll_delta = total_won - total_wagered

    # Determine narrative arc
    if cashed == len(week_slips):
        arc = "PERFECT WEEK"
        emotion = "celebration"
    elif cashed > len(week_slips) / 2:
        arc = f"WINNING WEEK ({cash_rate:.0f}%)"
        emotion = "momentum"
    elif cashed > 0:
        arc = f"MIXED RESULTS ({cash_rate:.0f}%)"
        emotion = "learning"
    else:
        arc = "TOUGH WEEK"
        emotion = "reset"

    # MY BOO: Analytical breakdown
    myboo_text = _myboo_segment(week, week_slips, state, total_legs, cashed, cash_rate)

    # Jonah Jacques: Narrative/emotional
    jonah_text = _jonah_segment(week, emotion, state.bankroll, bankroll_delta, arc)

    # Julian Feltus: Strategic insights
    julian_text = _julian_segment(week, week_slips, state, cashed)

    segments = [
        {
            "speaker": "MY BOO",
            "role": "Analyst",
            "text": myboo_text,
            "word_count": len(myboo_text.split()),
        },
        {
            "speaker": "Jonah Jacques",
            "role": "Narrative",
            "text": jonah_text,
            "word_count": len(jonah_text.split()),
        },
        {
            "speaker": "Julian Feltus",
            "role": "Strategy",
            "text": julian_text,
            "word_count": len(julian_text.split()),
        },
    ]

    total_words = sum(s["word_count"] for s in segments)

    return {
        "week": week,
        "title": f"Week {week} Recap: {arc}",
        "segments": segments,
        "total_words": total_words,
        "bankroll_delta": round(bankroll_delta, 2),
        "slips_cashed": cashed,
        "cashed_pct": round(cash_rate, 0),
        "key_stat": f"{'🔥 UNDEFEATED' if cashed == len(week_slips) else f'{cashed}/{len(week_slips)} SLIPS CASHED'}",
    }


def _myboo_segment(week: int, slips: list, state: SeasonState, total_legs: int, cashed: int, cash_rate: float) -> str:
    """MY BOO: Statistical and strategic analysis."""

    prop_breakdown = {}
    for slip in slips:
        for leg in slip.legs:
            prop_breakdown[leg.prop_type] = prop_breakdown.get(leg.prop_type, 0) + 1

    dominant_prop = max(prop_breakdown, key=prop_breakdown.get) if prop_breakdown else "mixed"

    if cashed == len(slips):
        return (
            f"Perfect execution this week. We submitted {len(slips)} slip{'s' if len(slips) > 1 else ''} "
            f"with {total_legs} legs total and cashed every single one. The {dominant_prop} props were our foundation—"
            f"we trusted the process and the process paid off. Your bankroll grew by $({state.bankroll}). "
            f"This is what consistency looks like. You didn't chase, you didn't get greedy, you built each slip "
            f"with discipline. The leg correlation was minimal, the confidence scores held up, and execution was clean. "
            f"This is the week to study: come back to it when doubt creeps in. Every element aligned because we did the work."
        )
    elif cashed > len(slips) / 2:
        return (
            f"We cashed {cashed} of {len(slips)} slips—{cash_rate:.0f}% hit rate. That's above expectation. "
            f"You built {total_legs} legs across the week and {cashed * len(slips) // len(slips) if len(slips) else total_legs} landed. "
            f"The {dominant_prop} props carried this week. You're making smarter picks, and the data shows it. "
            f"But here's the lesson: one losing slip means we're not yet at the consistency we need. "
            f"Review the miss. Was it correlation? Confidence threshold? Line movement? "
            f"Your bankroll is now ${state.bankroll}. Growth is real, but don't celebrate yet."
        )
    else:
        return (
            f"This week was a reset. Only {cashed} slip{'s' if cashed != 1 else ''} cashed out of {len(slips)}. "
            f"That stings. But here's the filter: your instincts on prop type were strong ({dominant_prop} was solid), "
            f"but something broke in execution or variance. We'll look at the carnage below. "
            f"You've still got ${state.bankroll} to work with. The season isn't defined by one week. "
            f"What matters now is whether you learn from the breakdown or repeat the mistake. "
            f"Let's find what went wrong and not make that bet again."
        )


def _jonah_segment(week: int, emotion: str, bankroll: float, delta: float, arc: str) -> str:
    """Jonah Jacques: Narrative and emotional perspective."""

    if emotion == "celebration":
        return (
            f"This is the week you'll remember. Perfect. Every single slip. Every leg landed. "
            f"Bankroll up ${delta}. You came into this week with a plan and you executed it flawlessly. "
            f"This is what it feels like when the betting gods align with your preparation. "
            f"Don't let this go to your head—variance is still your opponent—but savor this. "
            f"You earned it through discipline. When the losing weeks come—and they will—come back to this one. "
            f"This is proof that your method works. You've got {bankroll} now, and more importantly, "
            f"you've got evidence that you can pick it perfectly when it counts."
        )
    elif emotion == "momentum":
        return (
            f"Momentum. That's what this week was. You're finding your rhythm. "
            f"Bankroll up ${delta}. You came in hot and you stayed hot. "
            f"The slips that hit, hit hard. The ones that missed—there were only a few—taught you something. "
            f"You're building confidence in your reads and that's dangerous in the best way. "
            f"But danger also means hubris is creeping in. Stay sharp. Keep the discipline tight. "
            f"You're at ${bankroll} now and the cliff is always closer than you think in betting. "
            f"One bad week can undo five good weeks. We know that. So let's keep doing what works."
        )
    elif emotion == "learning":
        return (
            f"Mixed. That's the story. You had your moments but also your misses. "
            f"Bankroll fluctuation: ${delta}. That's the nature of this game. "
            f"You're learning what sticks and what doesn't. The slips that cashed showed promise. "
            f"The ones that didn't? They're your curriculum. Pay attention to them. "
            f"Right now you're at ${bankroll}. You're still in the game, still learning. "
            f"The difference between pros and amateurs is how they react to weeks like this. "
            f"The pro asks: 'What did I miss?' The amateur asks: 'Why did I lose?' "
            f"Be the pro. Dig into the data. Find the signal in the noise."
        )
    else:  # reset
        return (
            f"Tough week. No way around it. You came in confident and the market humbled you. "
            f"That's okay. Bankroll: ${bankroll}. You've got runway. But this hurt. "
            f"It should hurt a little—that's how you learn. The slips were built with conviction but "
            f"conviction doesn't win if the execution is off. Something in your methodology broke this week. "
            f"Was it the picks? The correlation? The wager sizing? Find it. "
            f"Don't just move to next week and hope. You still have {len(state.slips)} weeks left. "
            f"Use this one as data. The teams that win championships don't win every game. "
            f"They lose, they adjust, they come back harder."
        )


def _julian_segment(week: int, slips: list, state: SeasonState, cashed: int) -> str:
    """Julian Feltus: Strategic insights and pattern discovery."""

    # Analyze slip patterns
    avg_legs_per_slip = sum(len(s.legs) for s in slips) / len(slips) if slips else 0
    prop_types = {}
    for slip in slips:
        for leg in slip.legs:
            prop_types[leg.prop_type] = prop_types.get(leg.prop_type, 0) + 1

    if state.win_streak >= 3:
        return (
            f"You're now at a {state.win_streak}-win streak. That unlocks special tickets. "
            f"We've identified that your slips with {avg_legs_per_slip:.1f} legs on average are your sweet spot. "
            f"The {max(prop_types, key=prop_types.get)} prop type is your strongest category. "
            f"Here's the strategic move: lean harder into what works. Next week, build slips around that foundation. "
            f"We've also seen that when you diversify across different prop types, you reduce catastrophic loss. "
            f"The meta-strategies unlocked by your streak—underdog domination, sharp ticks—they're worth testing. "
            f"You're earning the right to experiment. Use it wisely. The best bettors don't just pick better; they structure smarter."
        )
    else:
        return (
            f"Let's look at what's working structurally. Your slips with {avg_legs_per_slip:.1f} legs average "
            f"are performing better than longer tickets. That's valuable data. The {max(prop_types, key=prop_types.get)} props "
            f"are your bread and butter—trust that category. Correlation is still your enemy; we saw it this week. "
            f"When multiple legs depend on the same player or matchup, the entire slip becomes fragile. "
            f"Going forward: diversify within the slip. Don't build every ticket around one team's passing game. "
            f"The season is long. We're finding patterns that'll compound. Right now it's about laying the foundation. "
            f"Week {week} was data. Use it."
        )

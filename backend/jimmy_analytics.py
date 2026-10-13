"""
JIMMY Analytics: Risk scoring, correlation detection, and strategy analysis.

Provides tools for:
- Calculating risk scores for slips (1-10)
- Detecting correlated legs
- Analyzing player hot/cold indicators
- Generating MY BOO strategy reports
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math
from jimmy_backtester import Leg, Slip, SeasonState

ACHIEVEMENT_NAMES = {
    "first_win": "First Win",
    "perfect_week_1": "Perfect Week",
    "win_streak_3": "On Fire",
    "bankroll_doubles": "Bankroll Doubles",
    "hot_hand": "Hot Hand",
    "contrarian_king": "Contrarian King",
    "iron_discipline": "Iron Discipline",
}


@dataclass
class RiskScore:
    """Risk assessment for a slip."""
    overall_score: float  # 1-10
    correlation_risk: float  # 0-1
    player_concentration: float  # 0-1 (how many legs depend on same player)
    variance_expected: float  # Std dev of leg hit rates
    projected_payout_all_hit: float  # If all legs hit
    projected_payout_one_miss: float  # If one leg misses
    warnings: list[str]


def calculate_risk_score(slip: Slip, player_form: dict[str, float] | None = None) -> RiskScore:
    """
    Calculate risk score 1-10 for a slip.

    Factors:
    - Correlation between legs (shared players, props)
    - Player form (hot/cold)
    - Variance in leg difficulty
    """
    legs = slip.legs
    n_legs = len(legs)
    warnings = []

    # 1. Correlation: detect shared players
    player_counts = {}
    for leg in legs:
        player_counts[leg.player_id] = player_counts.get(leg.player_id, 0) + 1

    player_concentration = len([p for p in player_counts.values() if p > 1]) / max(n_legs, 1)
    if player_concentration > 0.4:
        warnings.append("High player concentration")

    # 2. Correlation: detect prop type overlap on same team
    team_prop_combos = {}
    for leg in legs:
        key = f"{leg.team}_{leg.prop_type}"
        team_prop_combos[key] = team_prop_combos.get(key, 0) + 1

    correlation_risk = len([v for v in team_prop_combos.values() if v > 1]) / max(n_legs, 1)
    if correlation_risk > 0.3:
        warnings.append("Correlated prop types")

    # 3. Confidence variance (how spread are the leg confidences?)
    confidences = [leg.confidence for leg in legs]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
    variance_expected = math.sqrt(sum((c - avg_conf) ** 2 for c in confidences) / len(confidences))

    # 4. Combine into 1-10 score
    # Low correlation + high avg confidence = lower risk (better)
    # High correlation + mixed confidence = higher risk (worse)
    base_risk = (correlation_risk + player_concentration) / 2
    confidence_discount = max(0, avg_conf - 0.55) * 0.5  # Reward high confidence

    overall_score = 5 + (base_risk * 4) - (confidence_discount * 3)
    overall_score = max(1, min(10, overall_score))

    # 5. Projected payouts
    wager = slip.wager
    payout_all_hit = wager * (2 ** n_legs)
    payout_one_miss = 0  # Parlay loses if any leg misses

    if correlation_risk > 0.5:
        warnings.append("High correlation risk—avoid if possible")

    return RiskScore(
        overall_score=round(overall_score, 1),
        correlation_risk=round(correlation_risk, 2),
        player_concentration=round(player_concentration, 2),
        variance_expected=round(variance_expected, 3),
        projected_payout_all_hit=round(payout_all_hit, 2),
        projected_payout_one_miss=round(payout_one_miss, 2),
        warnings=warnings,
    )


def detect_correlated_legs(legs: list[Leg], threshold: float = 0.6) -> list[tuple[int, int, float]]:
    """
    Detect pairs of legs that are highly correlated (both depend on same player/prop).
    Returns list of (leg_idx_1, leg_idx_2, correlation_score).
    """
    correlations = []
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            leg1, leg2 = legs[i], legs[j]

            # Perfect correlation: same player, same prop
            if leg1.player_id == leg2.player_id and leg1.prop_type == leg2.prop_type:
                correlations.append((i, j, 1.0))
            # High correlation: same player, different prop
            elif leg1.player_id == leg2.player_id:
                correlations.append((i, j, 0.8))
            # Medium correlation: same team, same prop type
            elif leg1.team == leg2.team and leg1.prop_type == leg2.prop_type:
                correlations.append((i, j, 0.6))

    return [c for c in correlations if c[2] >= threshold]


def calculate_player_form(slips: list[Slip], player_id: str) -> dict:
    """
    Calculate hot/cold indicator for a player based on recent slip performance.

    Looks at last 5 slips containing the player:
    - Hot: >60% hit rate
    - Cold: <40% hit rate
    - Neutral: 40-60%
    """
    recent_slips = [s for s in slips[-5:] if any(leg.player_id == player_id for leg in s.legs)]

    if not recent_slips:
        return {"form": "neutral", "hit_rate": 0.5, "appearances": 0}

    hits = sum(1 for s in recent_slips if s.result)
    hit_rate = hits / len(recent_slips)

    if hit_rate > 0.6:
        form = "hot"
    elif hit_rate < 0.4:
        form = "cold"
    else:
        form = "neutral"

    return {
        "form": form,
        "hit_rate": round(hit_rate, 2),
        "appearances": len(recent_slips),
    }


def generate_strategy_analysis(state: SeasonState) -> str:
    """
    Generate MY BOO-style strategy analysis for a week's slips.
    Analyzes slip composition, correlation, prop type performance.
    """
    if not state.slips:
        return "No slips yet. Build your first slip to see analysis."

    week_slips = [s for s in state.slips if s.week == state.current_week]
    if not week_slips:
        return "No slips for this week."

    # Analyze slip composition
    total_legs = sum(len(s.legs) for s in week_slips)
    avg_legs = total_legs / len(week_slips)

    # Analyze prop type distribution
    prop_types = {}
    for slip in week_slips:
        for leg in slip.legs:
            prop_types[leg.prop_type] = prop_types.get(leg.prop_type, 0) + 1

    dominant_prop = max(prop_types, key=prop_types.get) if prop_types else "unknown"

    # Analyze player concentration
    player_counts = {}
    for slip in week_slips:
        for leg in slip.legs:
            player_counts[leg.player_name] = player_counts.get(leg.player_name, 0) + 1

    duplicated_players = len([c for c in player_counts.values() if c > 1])

    # Build narrative
    lines = [
        f"Here's how your Week {state.current_week} slips performed:",
        f"You submitted {len(week_slips)} slip(s) with {total_legs} total legs ({avg_legs:.1f} avg per slip).",
    ]

    if duplicated_players > 0:
        lines.append(
            f"You recycled {duplicated_players} player(s) across multiple slips. "
            f"This concentrates your risk—if that player has a bad day, multiple slips suffer."
        )
    else:
        lines.append("Good diversification across different players. That's smart risk management.")

    lines.append(
        f"This week, {prop_types.get('rec_yds', 0)} receiving yards, "
        f"{prop_types.get('rush_yds', 0)} rushing yards, and {prop_types.get('pass_yds', 0)} passing yards props. "
        f"Your primary focus: {dominant_prop}."
    )

    # Weekly results
    wins = sum(1 for s in week_slips if s.result)
    lines.append(f"\nResults: {wins}/{len(week_slips)} slips cashed. Bankroll now ${state.bankroll:.0f}.")

    return " ".join(lines)


def generate_season_summary(state: SeasonState) -> dict:
    """Generate end-of-season summary and stats."""
    total_slips = len(state.slips)
    cashed_slips = sum(1 for s in state.slips if s.result)
    cash_rate = (cashed_slips / total_slips * 100) if total_slips else 0

    roi = ((state.bankroll - state.starting_bankroll) / state.starting_bankroll * 100) if state.starting_bankroll else 0

    # Best/worst slip
    if state.slips:
        best_slip = max(state.slips, key=lambda s: s.roi or -100)
        worst_slip = min(state.slips, key=lambda s: s.roi or -100)
    else:
        best_slip = worst_slip = None

    # Achievements
    achievements = [ACHIEVEMENT_NAMES.get(a, a) for a in state.achievements_unlocked]

    return {
        "total_slips": total_slips,
        "cashed": cashed_slips,
        "cash_rate": round(cash_rate, 1),
        "starting_bankroll": state.starting_bankroll,
        "final_bankroll": round(state.bankroll, 2),
        "total_wagered": round(state.total_wagered, 2),
        "total_winnings": round(state.total_won, 2),
        "roi_percent": round(roi, 1),
        "best_slip": best_slip.slip_id if best_slip else None,
        "worst_slip": worst_slip.slip_id if worst_slip else None,
        "achievements": achievements,
        "longest_win_streak": state.win_streak,  # This tracks current; we'd need history for true longest
    }

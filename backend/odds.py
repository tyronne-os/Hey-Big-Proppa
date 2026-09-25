"""
American <-> decimal odds conversion + parlay payout math.

Exactly the formulas specified in HANDOFF_CLAUDE_CODE.md section "Odds math
(implement exactly)":

    dec(american) = american > 0 ? 1 + american/100 : 1 + 100/|american|
    D             = product of dec(leg.odds)                (combined decimal odds)
    payout        = wager * D
    boostedPayout = wager + wager * (D - 1) * (1 + boost)   (boost = 0.50)
    boostedOdds   = toAmerican(1 + (D - 1) * (1 + boost))
    wager default = $5

The boost is a fictitious display promotion, per the handoff doc -- it must
stay labeled as such anywhere it reaches a user.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def decimal_from_american(american: float) -> float:
    if american > 0:
        return 1 + american / 100
    return 1 + 100 / abs(american)


def american_from_decimal(decimal_odds: float) -> int:
    if decimal_odds >= 2:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


@dataclass
class ParlayMath:
    combined_decimal: float
    payout: float
    boosted_payout: float
    boosted_american: int


def compute_parlay(leg_american_odds: list[float], wager: float = 5.0, boost: float = 0.50) -> ParlayMath:
    if not leg_american_odds:
        return ParlayMath(combined_decimal=1.0, payout=wager, boosted_payout=wager, boosted_american=0)
    combined = math.prod(decimal_from_american(o) for o in leg_american_odds)
    payout = wager * combined
    boosted_payout = wager + wager * (combined - 1) * (1 + boost)
    boosted_decimal = 1 + (combined - 1) * (1 + boost)
    boosted_american = american_from_decimal(boosted_decimal)
    return ParlayMath(
        combined_decimal=round(combined, 4),
        payout=round(payout, 2),
        boosted_payout=round(boosted_payout, 2),
        boosted_american=boosted_american,
    )

"""
The 500 bettors of THE BOOKIE MULTIVERSE.

Each bettor is a seeded persona drawn from an archetype: the kind of slip they love, how many legs, how
many slips a week, how much of the roll they stake, how much they chase after a loss, and how much they
lean toward popular (chalk) picks. Inside those habits they pick freely from the full legal menu, so the
data covers the whole space of real slips, not one strategy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# weight = share of the betting public (spread parlays are the most common ticket)
ARCHETYPES: dict[str, dict] = {
    "spread_parlay":    dict(w=0.18, label="Spread Parlay Guy",   markets={"spread"},                         sides=None,          legs=(2, 5),  slips=(1, 3), sgp="never",  desc="Covers spreads, no player props"),
    "ml_favorites":     dict(w=0.08, label="Chalk Moneyline",     markets={"ml"},                             sides={"fav"},       legs=(2, 4),  slips=(1, 2), sgp="never",  desc="Stacks favorites to win outright"),
    "ml_dogs":          dict(w=0.04, label="Dog Hunter",          markets={"ml"},                             sides={"dog"},       legs=(1, 3),  slips=(1, 2), sgp="never",  desc="Underdogs to win outright"),
    "game_overs":       dict(w=0.08, label="Overs Only",          markets={"total"},                          sides={"over"},      legs=(2, 4),  slips=(1, 2), sgp="never",  desc="Game totals going over"),
    "game_unders":      dict(w=0.03, label="Unders Sharp",        markets={"total"},                          sides={"under"},     legs=(2, 4),  slips=(1, 2), sgp="never",  desc="Game totals going under"),
    "anytime_td":       dict(w=0.14, label="TD Scorer Stacker",   markets={"anytime_td"},                     sides={"yes"},       legs=(3, 5),  slips=(1, 3), sgp="spread", desc="3-5 anytime TD scorers across matchups"),
    "qb_passing":       dict(w=0.07, label="QB Air Raid",         markets={"pass_yds", "pass_tds", "completions", "pass_att"}, sides={"over"}, legs=(2, 4), slips=(1, 2), sgp="spread", desc="Passing yards, TDs, completions"),
    "wr_yards":         dict(w=0.07, label="WR Yardage",          markets={"rec_yds", "receptions"},          sides=None,          legs=(2, 5),  slips=(1, 2), sgp="spread", desc="Receiving yards and catches"),
    "rb_ground":        dict(w=0.04, label="Ground & Pound",      markets={"rush_yds", "rush_rec_yds"},       sides=None,          legs=(2, 4),  slips=(1, 2), sgp="spread", desc="Rushing and scrimmage yards"),
    "sgp_stacker":      dict(w=0.10, label="SGP Stacker",         markets=None,                               sides=None,          legs=(3, 6),  slips=(1, 3), sgp="single", desc="One game, stacked legs that tell a story"),
    "mixed_degenerate": dict(w=0.09, label="Lottery Ticket",      markets=None,                               sides=None,          legs=(5, 10), slips=(1, 3), sgp="spread", desc="Anything goes, long parlays"),
    "chalk_grinder":    dict(w=0.08, label="Chalk Grinder",       markets={"spread", "ml", "total", "rec_yds", "rush_yds", "pass_yds"}, sides=None, legs=(2, 2), slips=(1, 2), sgp="never", desc="Two-leg favorites, small stakes"),
}


@dataclass
class Bettor:
    bettor_id: int
    archetype: str
    legs_lo: int
    legs_hi: int
    slips_lo: int
    slips_hi: int
    stake_pct: float       # share of bankroll per slip
    chase: float           # stake multiplier after a losing week (1.0 = disciplined)
    pop_bias: float        # >0 leans to chalk/popular, <0 contrarian
    over_lean: float       # P(choose over/yes) when the archetype allows both sides
    seed: int

    def dict(self) -> dict:
        return asdict(self)


def roster(n: int, seed: int, mix: dict[str, float] | None = None) -> list[Bettor]:
    rng = np.random.default_rng(seed)
    names = list(ARCHETYPES)
    w = np.array([(mix or {}).get(k, ARCHETYPES[k]["w"]) for k in names], dtype=float)
    w = w / w.sum()
    counts = np.floor(w * n).astype(int)
    for i in np.argsort(-(w * n - counts))[: n - counts.sum()]:
        counts[i] += 1
    out: list[Bettor] = []
    bid = 0
    for name, c in zip(names, counts):
        a = ARCHETYPES[name]
        for _ in range(c):
            lo, hi = a["legs"]
            out.append(Bettor(
                bettor_id=bid, archetype=name, legs_lo=lo, legs_hi=hi,
                slips_lo=a["slips"][0], slips_hi=a["slips"][1],
                stake_pct=float(np.clip(rng.lognormal(np.log(0.05), 0.45), 0.01, 0.25)),
                chase=float(rng.choice([1.0, 1.0, 1.0, 1.25, 1.5, 2.0])),
                pop_bias=float(np.clip(rng.normal(0.8 if name == "chalk_grinder" else 0.3, 0.5), -1.0, 2.0)),
                over_lean=float(np.clip(rng.normal(0.72, 0.12), 0.3, 0.95)),
                seed=int(rng.integers(0, 2**31 - 1)),
            ))
            bid += 1
    return out

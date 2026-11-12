"""
The BETTERS of BETTER-VERSE.

Every better has a username, a skill tier, a one-line ideology and a short list of rules that the simulator
actually enforces, so the leaderboard can be read as "whose logic worked", not just "who got lucky".

  SHARP    researches: re-reads which market/side beat the book using only games already played (plus last
           season), bets only where the measured edge is positive, 2-3 cross-game legs, small flat stakes,
           never chases, sits out when nothing qualifies.
  Table limits (all tiers): each better picks a $5 or $10 base bet; max bet $10 until the bankroll reaches $500,
  $20 until $1,000, and above $1,000 they bet freely.
  GRINDER  has a favorite bet type but bets like a pro: flat small stake, at most 3 legs, never chases.
  CASUAL   a favorite bet type, medium stakes, chases a bad week a little.
  DEGEN    knee-jerk: long parlays, big stakes, doubles up after losses, chases the chalk crowd.

Nothing in the tiers is rigged: the sim prices every slip the same way for everyone. Discipline only
shows up on the board if it genuinely returns more.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

# weight = share of the betting public (spread parlays are the most common ticket)
ARCHETYPES: dict[str, dict] = {
    "edge_hunter":      dict(w=0.12, label="Edge Hunter",         markets=None,                               sides=None,          legs=(2, 3),  slips=(1, 2), sgp="never",  tiers={"sharp": 1.0},
                             desc="Researches which markets beat the book, then bets only those"),
    "spread_parlay":    dict(w=0.16, label="Spread Parlay Guy",   markets={"spread"},                         sides=None,          legs=(2, 5),  slips=(1, 3), sgp="never",  tiers={"grinder": .25, "casual": .6, "degen": .15},
                             desc="Covers spreads, no player props"),
    "ml_favorites":     dict(w=0.07, label="Chalk Moneyline",     markets={"ml"},                             sides={"fav"},       legs=(2, 4),  slips=(1, 2), sgp="never",  tiers={"grinder": .25, "casual": .6, "degen": .15},
                             desc="Stacks favorites to win outright"),
    "ml_dogs":          dict(w=0.04, label="Dog Hunter",          markets={"ml"},                             sides={"dog"},       legs=(1, 3),  slips=(1, 2), sgp="never",  tiers={"grinder": .15, "casual": .6, "degen": .25},
                             desc="Underdogs to win outright"),
    "game_overs":       dict(w=0.07, label="Overs Only",          markets={"total"},                          sides={"over"},      legs=(2, 4),  slips=(1, 2), sgp="never",  tiers={"grinder": .2, "casual": .65, "degen": .15},
                             desc="Game totals going over"),
    "game_unders":      dict(w=0.03, label="Unders Sharp",        markets={"total"},                          sides={"under"},     legs=(2, 4),  slips=(1, 2), sgp="never",  tiers={"grinder": .35, "casual": .55, "degen": .1},
                             desc="Game totals going under"),
    "anytime_td":       dict(w=0.12, label="TD Scorer Stacker",   markets={"anytime_td"},                     sides={"yes"},       legs=(3, 5),  slips=(1, 3), sgp="spread", tiers={"grinder": .1, "casual": .55, "degen": .35},
                             desc="3-5 anytime TD scorers across matchups"),
    "qb_passing":       dict(w=0.07, label="QB Air Raid",         markets={"pass_yds", "pass_tds", "completions", "pass_att"}, sides={"over"}, legs=(2, 4), slips=(1, 2), sgp="spread", tiers={"grinder": .3, "casual": .6, "degen": .1},
                             desc="Passing yards, TDs, completions"),
    "wr_yards":         dict(w=0.07, label="WR Yardage",          markets={"rec_yds", "receptions"},          sides=None,          legs=(2, 5),  slips=(1, 2), sgp="spread", tiers={"grinder": .2, "casual": .65, "degen": .15},
                             desc="Receiving yards and catches"),
    "rb_ground":        dict(w=0.04, label="Ground & Pound",      markets={"rush_yds", "rush_rec_yds"},       sides=None,          legs=(2, 4),  slips=(1, 2), sgp="spread", tiers={"grinder": .3, "casual": .6, "degen": .1},
                             desc="Rushing and scrimmage yards"),
    "sgp_stacker":      dict(w=0.08, label="SGP Stacker",         markets=None,                               sides=None,          legs=(3, 6),  slips=(1, 3), sgp="single", tiers={"grinder": .1, "casual": .6, "degen": .3},
                             desc="One game, stacked legs that tell a story"),
    "mixed_degenerate": dict(w=0.08, label="Lottery Ticket",      markets=None,                               sides=None,          legs=(5, 10), slips=(1, 3), sgp="spread", tiers={"degen": 1.0},
                             desc="Anything goes, long parlays"),
    "chalk_grinder":    dict(w=0.05, label="Chalk Grinder",       markets={"spread", "ml", "total", "rec_yds", "rush_yds", "pass_yds"}, sides=None, legs=(2, 2), slips=(1, 2), sgp="never", tiers={"grinder": .6, "casual": .4},
                             desc="Two-leg favorites, small stakes"),
}

TIERS = {
    "sharp":   dict(label="Sharp",   order=0, note="researches, flat stakes, never chases"),
    "grinder": dict(label="Grinder", order=1, note="favorite bet type, pro discipline"),
    "casual":  dict(label="Casual",  order=2, note="favorite bet type, medium stakes"),
    "degen":   dict(label="Degen",   order=3, note="knee-jerk, long parlays, chases losses"),
}

_STEMS = {
    "edge_hunter": ["EdgeLedger", "QuietKelly", "FadeTheNoise", "ClosingLine", "PriorsFirst", "VigAware", "UnitSizer", "BayesBeth"],
    "spread_parlay": ["CoverKing", "ATSAndy", "PointSpreadPete", "TeaserTim", "LayTheWood", "SpreadSzn", "DogsCover"],
    "ml_favorites": ["ChalkBoss", "LockItLarry", "FavsOnly", "SafeMoneyMo", "NoUpsets"],
    "ml_dogs": ["DogDaddy", "UnderdogUri", "BiteBack", "PlusMoneyPat", "UpsetAlert"],
    "game_overs": ["OverLord", "ShootoutSam", "PointsPlz", "GoOverGary", "ScoreFest"],
    "game_unders": ["UnderTaker", "DefenseWins", "LowScoreLou", "GrindItOut", "RainGameRay"],
    "anytime_td": ["TDTony", "EndzoneEd", "ScorerSally", "RedZoneRick", "SixPointSid", "AnytimeAnnie"],
    "qb_passing": ["AirRaidAl", "ThrowItDeep", "QBWhisperer", "PassYardsPaul", "SlingItSue"],
    "wr_yards": ["WRWizard", "TargetShare", "CatchEmAll", "RouteRunnerRon", "SlotSally"],
    "rb_ground": ["GroundGame", "RushRudy", "CarryTheLoad", "BellCowBen", "Dirt4Days"],
    "sgp_stacker": ["StackSteve", "SameGameSam", "StoryParlay", "CorrelationCal", "BuildABetBo"],
    "mixed_degenerate": ["LottoLou", "MoonShotMax", "YOLOYolanda", "ParlayPapi", "LongShotLeo", "SendItSeth"],
    "chalk_grinder": ["SlowAndSteady", "TwoLegTom", "GrindMode", "SmallBallSara", "ChalkWalker"],
}

_BIO = {
    "sharp": "Treats every slip like an experiment: logs what hit, shrinks small samples, and only bets markets that have beaten the book so far.",
    "grinder": "Knows the vig is the enemy: keeps slips short, stakes flat and small, and never bets to win back a loss.",
    "casual": "Bets what feels right for the weekend. Some research, some gut, a slightly bigger bet after a bad week.",
    "degen": "Here for the payout, not the math. Stacks long parlays, bets big, and doubles up to chase a bad week.",
}


@dataclass
class Bettor:
    bettor_id: int
    username: str
    archetype: str
    tier: str
    legs_lo: int
    legs_hi: int
    slips_lo: int
    slips_hi: int
    unit: int              # the base bet this better picked: $5 or $10
    stake_pct: float       # share of bankroll per slip once the table limits are gone ($1,000+)
    chase: float           # stake multiplier after a losing week (1.0 = disciplined)
    pop_bias: float        # >0 leans to chalk/popular, <0 contrarian
    over_lean: float       # P(choose over/yes) when the archetype allows both sides
    learns: bool = False   # re-reads market edges from games already played
    edge_min: float = 0.0  # minimum measured edge a sharp needs before betting a market
    seed: int = 0
    bio: str = ""
    rules: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


BAND_1, BAND_2 = 500.0, 1000.0     # bankroll where the max bet rises from $10 to $20, then comes off entirely


def _rules(b: Bettor, a: dict) -> list[str]:
    r = [f"{b.legs_lo}–{b.legs_hi} legs per slip" if b.legs_lo != b.legs_hi else f"{b.legs_lo} legs per slip"]
    r.append(f"Bets ${b.unit} slips (max $10 until $500, $20 until $1,000, then free)")
    if b.chase == 1.0:
        r.append("Never chases a losing week")
    else:
        r.append(f"Bets ×{b.chase:g} after a losing week (up to the limit)")
    if b.learns:
        r.append(f"Bets only markets with ≥{b.edge_min:.1%} measured edge")
        r.append("Sits out when nothing qualifies")
    else:
        r.append({"never": "Cross-game legs only", "spread": "Mostly cross-game, some same-game legs",
                  "single": "Stacks one game"}[a["sgp"]])
    if b.pop_bias >= 1.0:
        r.append("Follows the crowd's favorite legs")
    elif b.pop_bias < 0:
        r.append("Fades the crowd")
    return r


def max_stake(bank: float) -> float:
    """Table limits: $10 until the bankroll reaches $500, $20 until $1,000, then bet freely."""
    return 10.0 if bank < BAND_1 else 20.0 if bank < BAND_2 else float("inf")


def stake_for(b: "Bettor", bank: float, mult: float = 1.0) -> float:
    """What this better puts on a slip: their $5/$10 pick, scaled up in the $500-$1,000 band, free above $1,000."""
    if bank >= BAND_2:
        s = max(20.0, bank * b.stake_pct) * mult
    elif bank >= BAND_1:
        s = min(20.0, b.unit * 2 * mult)
    else:
        s = min(10.0, b.unit * mult)
    return round(min(bank, max(1.0, s)), 2)


def _pick(rng: np.random.Generator, pool: list[str], used: set[str]) -> str:
    for _ in range(40):
        s = f"{pool[int(rng.integers(len(pool)))]}{int(rng.integers(2, 99))}"
        if s not in used:
            return s
    return f"better{len(used)}"


def roster(n: int, seed: int, mix: dict[str, float] | None = None) -> list[Bettor]:
    """Same (n, seed, mix) -> same people, in any season, so a career can be followed across seasons."""
    rng = np.random.default_rng(seed)
    names = list(ARCHETYPES)
    w = np.array([(mix or {}).get(k, ARCHETYPES[k]["w"]) for k in names], dtype=float)
    w = w / w.sum()
    counts = np.floor(w * n).astype(int)
    for i in np.argsort(-(w * n - counts))[: n - counts.sum()]:
        counts[i] += 1
    out: list[Bettor] = []
    used: set[str] = set()
    bid = 0
    for name, c in zip(names, counts):
        a = ARCHETYPES[name]
        tiers, tw = zip(*a["tiers"].items())
        for _ in range(c):
            tier = str(rng.choice(tiers, p=np.array(tw) / sum(tw)))
            lo, hi = a["legs"]
            slips_lo, slips_hi = a["slips"]
            if tier == "sharp":
                lo, hi = 2, int(rng.choice([2, 3]))
                stake, chase, pop = rng.uniform(0.01, 0.03), 1.0, 0.0
                over, learns, edge_min = 0.5, True, float(rng.choice([0.005, 0.01, 0.015]))
                slips_hi = 2
            elif tier == "grinder":
                hi = min(hi, 3); lo = min(lo, hi)
                stake, chase, pop = rng.uniform(0.015, 0.03), 1.0, float(np.clip(rng.normal(0.2, 0.3), -0.5, 0.8))
                over, learns, edge_min = float(np.clip(rng.normal(0.65, 0.1), 0.3, 0.9)), False, 0.0
                slips_hi = min(slips_hi, 2)
            elif tier == "degen":
                lo = max(lo, 4); hi = max(hi, lo)
                stake = float(np.clip(rng.lognormal(np.log(0.09), 0.35), 0.04, 0.25))
                chase, pop = float(rng.choice([1.5, 2.0, 2.5])), float(np.clip(rng.normal(0.9, 0.4), 0.0, 2.0))
                over, learns, edge_min = float(np.clip(rng.normal(0.82, 0.08), 0.5, 0.97)), False, 0.0
            else:
                stake = float(np.clip(rng.lognormal(np.log(0.05), 0.35), 0.02, 0.12))
                chase, pop = float(rng.choice([1.0, 1.0, 1.25, 1.5])), float(np.clip(rng.normal(0.4, 0.5), -0.5, 1.5))
                over, learns, edge_min = float(np.clip(rng.normal(0.72, 0.1), 0.3, 0.92)), False, 0.0
            unit = int(rng.choice([5, 10], p={"sharp": [.5, .5], "grinder": [.6, .4], "casual": [.5, .5], "degen": [.3, .7]}[tier]))
            b = Bettor(
                bettor_id=bid, username=_pick(rng, _STEMS[name], used), archetype=name, tier=tier,
                legs_lo=lo, legs_hi=hi, slips_lo=slips_lo, slips_hi=slips_hi, unit=unit,
                stake_pct=round(float(stake), 4), chase=chase, pop_bias=round(pop, 3), over_lean=round(over, 3),
                learns=learns, edge_min=edge_min, seed=int(rng.integers(0, 2**31 - 1)), bio=_BIO[tier])
            b.rules = _rules(b, a)
            used.add(b.username)
            out.append(b)
            bid += 1
    return out

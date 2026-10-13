"""
JIMMY Backtester: NFL prop betting strategy simulator.

Simulates playing prop slips across a full NFL season (2024 or 2025) starting from Friday of Week 1
with zero knowledge of season outcomes. Each week, the user builds 1-5 slips from FanDuel props.
The backtester simulates forward, calculating wins/losses and bankroll progression.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import csv
from pathlib import Path
from datetime import datetime, timedelta
import json
import math

SEASON_WEEKS = 17
INITIAL_BANKROLL = 100


@dataclass
class Leg:
    """A single prop bet within a slip."""
    player_id: str
    player_name: str
    team: str
    prop_type: str  # 'rec_yds', 'rec_td', 'rush_yds', 'rush_td', 'pass_yds', 'pass_td'
    line: float
    is_over: bool
    confidence: float  # 0.0-1.0 from Jimmy agent
    actual_value: Optional[float] = None
    result: Optional[bool] = None  # True if hit, False if miss, None if pending


@dataclass
class Slip:
    """A weekly bet slip with 1-5 legs."""
    week: int
    slip_id: str
    legs: list[Leg]
    wager: float
    submitted_at: str  # ISO timestamp
    legs_hit: Optional[int] = None
    payout: Optional[float] = None
    roi: Optional[float] = None
    result: Optional[bool] = None  # True if all legs hit, False if any miss
    challenge_accepted: Optional[str] = None  # Challenge type if accepted
    challenge_bonus: float = 0.0


@dataclass
class SeasonState:
    """Full state of a season simulation."""
    year: int
    slips_per_week: int  # 1-5, locked for season
    starting_bankroll: float
    current_week: int
    bankroll: float
    slips: list[Slip]  # All slips submitted this season
    total_wagered: float
    total_won: float
    win_streak: int
    loss_streak: int
    achievements_unlocked: list[str]
    double_downs_used: int
    double_downs_remaining: int = 3
    insurance_used: bool = False
    wager_size: float = 5.0  # Base, scales at bankroll milestones


class JimmyBacktester:
    """Simulates NFL prop betting strategies across full season."""

    def __init__(self, year: int, slips_per_week: int, lake_dir: Path = Path("/home/user/Hey-Big-Proppa/lake")):
        self.year = year
        self.slips_per_week = slips_per_week
        self.lake_dir = lake_dir
        self.state = SeasonState(
            year=year,
            slips_per_week=slips_per_week,
            starting_bankroll=INITIAL_BANKROLL,
            current_week=1,
            bankroll=INITIAL_BANKROLL,
            slips=[],
            total_wagered=0.0,
            total_won=0.0,
            win_streak=0,
            loss_streak=0,
            achievements_unlocked=[],
            double_downs_used=0,
        )
        self._load_season_data()

    def _load_season_data(self):
        """Load schedule and player stats from lake."""
        schedule_path = self.lake_dir / "gold" / "nfl" / "schedule.csv"
        self.schedule = {}
        if schedule_path.exists():
            with open(schedule_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    week = int(row.get("week", 0))
                    if week > 0:
                        if week not in self.schedule:
                            self.schedule[week] = []
                        self.schedule[week].append(row)

    def calculate_wager_size(self) -> float:
        """Calculate wager based on current bankroll (dynamic scaling)."""
        if self.state.bankroll >= 1000:
            return 15.0
        elif self.state.bankroll >= 500:
            return 10.0
        return 5.0

    def evaluate_leg(self, leg: Leg, week: int) -> bool:
        """
        Evaluate if a leg hit based on actual player stats for the week.
        Returns True if leg hits, False if miss.
        """
        stats_path = self.lake_dir / "gold" / "nfl" / f"player_{leg.prop_type}_week.csv"
        if not stats_path.exists():
            return False

        with open(stats_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("player_id") == leg.player_id and int(row.get("week", 0)) == week:
                    val = float(row.get("value", 0))
                    leg.actual_value = val
                    hit = (val > leg.line) if leg.is_over else (val < leg.line)
                    leg.result = hit
                    return hit
        return False

    def submit_slip(self, legs: list[Leg], challenge: Optional[str] = None) -> Slip:
        """
        Submit a slip for the current week. Evaluates all legs, calculates payout.
        """
        if len(legs) < 1 or len(legs) > 5:
            raise ValueError("Slip must have 1-5 legs")

        wager = self.calculate_wager_size()
        slip_id = f"W{self.state.current_week}_S{len(self.state.slips) + 1}_{self.year}"
        slip = Slip(
            week=self.state.current_week,
            slip_id=slip_id,
            legs=legs,
            wager=wager,
            submitted_at=datetime.utcnow().isoformat(),
            challenge_accepted=challenge,
        )

        # Evaluate all legs for this week
        legs_hit = 0
        for leg in slip.legs:
            if self.evaluate_leg(leg, self.state.current_week):
                legs_hit += 1

        slip.legs_hit = legs_hit
        slip.result = (legs_hit == len(slip.legs))

        # Calculate payout: each leg is 2x multiplier (parlay)
        if slip.result:
            payout = wager * (2 ** len(slip.legs))
            slip.payout = payout
            slip.roi = (payout - wager) / wager * 100
            self.state.total_won += payout
            self.state.bankroll += payout - wager
            self.state.win_streak += 1
            self.state.loss_streak = 0
        else:
            slip.payout = 0.0
            slip.roi = -100.0
            self.state.bankroll -= wager
            self.state.loss_streak += 1
            self.state.win_streak = 0

        self.state.total_wagered += wager
        self.state.slips.append(slip)
        self._check_achievements()
        return slip

    def apply_double_down(self):
        """Apply 2x wager multiplier for next week."""
        if self.state.double_downs_remaining <= 0:
            raise ValueError("No double-downs remaining")
        self.state.double_downs_used += 1
        self.state.double_downs_remaining -= 1
        # Wager size is doubled next week; resets after submission

    def apply_insurance(self):
        """Activate one-time insurance for this week."""
        if self.state.insurance_used:
            raise ValueError("Insurance already used")
        self.state.insurance_used = True

    def advance_week(self):
        """Move to next week if season not over."""
        if self.state.current_week < SEASON_WEEKS:
            self.state.current_week += 1
        if self.state.bankroll <= 0:
            self.state.bankroll = 0

    def _check_achievements(self):
        """Check for newly unlocked achievements after slip submission."""
        slip = self.state.slips[-1]

        # First Win
        if len([s for s in self.state.slips if s.result]) == 1:
            self._unlock("first_win")

        # Perfect Week (all slips hit)
        if self.state.current_week == 1 and all(s.result for s in self.state.slips if s.week == 1):
            self._unlock("perfect_week_1")

        # 3-Win Streak
        if self.state.win_streak >= 3:
            self._unlock("win_streak_3")

        # Bankroll Doubles
        if self.state.bankroll >= self.state.starting_bankroll * 2:
            self._unlock("bankroll_doubles")

    def _unlock(self, achievement_key: str):
        """Unlock achievement if not already unlocked."""
        if achievement_key not in self.state.achievements_unlocked:
            self.state.achievements_unlocked.append(achievement_key)

    def get_state_dict(self) -> dict:
        """Return serializable state dict."""
        return {
            "year": self.state.year,
            "slips_per_week": self.state.slips_per_week,
            "current_week": self.state.current_week,
            "bankroll": round(self.state.bankroll, 2),
            "total_wagered": round(self.state.total_wagered, 2),
            "total_won": round(self.state.total_won, 2),
            "win_streak": self.state.win_streak,
            "loss_streak": self.state.loss_streak,
            "achievements": self.state.achievements_unlocked,
            "slips": [self._serialize_slip(s) for s in self.state.slips],
        }

    def _serialize_slip(self, slip: Slip) -> dict:
        return {
            "slip_id": slip.slip_id,
            "week": slip.week,
            "wager": round(slip.wager, 2),
            "legs": len(slip.legs),
            "legs_hit": slip.legs_hit,
            "result": slip.result,
            "payout": round(slip.payout or 0, 2),
            "roi": slip.roi,
            "challenge": slip.challenge_accepted,
        }

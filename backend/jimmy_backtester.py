"""
JIMMY Backtester: NFL prop betting strategy simulator.

Travels back to Friday of Week 1 of 2024 or 2025. Each week the player builds 1-5 slips from a board
whose lines were set only from games already played; slips grade against what really happened
(nflverse weekly stats via jimmy_history). The booth's picks and tails ride along in the same save.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import jimmy_history as hist

SEASON_WEEKS = 17
INITIAL_BANKROLL = 100
HOSTS = ("MY BOO", "Jonah Jacques", "Julian Feltus")


@dataclass
class Leg:
    player_id: str
    player_name: str
    team: str
    prop_type: str  # key of jimmy_history.PROPS
    line: float
    is_over: bool
    confidence: float  # 0.0-1.0
    actual_value: Optional[float] = None
    result: Optional[bool] = None  # None = void (did not play)
    headshot: str = ""

    @property
    def label(self) -> str:
        return hist.PROPS[self.prop_type]["label"]

    @property
    def margin(self) -> Optional[float]:
        if self.actual_value is None:
            return None
        return (self.actual_value - self.line) if self.is_over else (self.line - self.actual_value)


@dataclass
class Slip:
    week: int
    slip_id: str
    legs: list[Leg]
    wager: float
    submitted_at: str
    legs_hit: Optional[int] = None
    payout: Optional[float] = None
    roi: Optional[float] = None
    result: Optional[bool] = None
    challenge_accepted: Optional[str] = None
    challenge_bonus: float = 0.0


@dataclass
class SeasonState:
    year: int
    slips_per_week: int
    starting_bankroll: float
    current_week: int
    bankroll: float
    slips: list[Slip]
    total_wagered: float
    total_won: float
    win_streak: int
    loss_streak: int
    achievements_unlocked: list[str]
    double_downs_used: int
    double_downs_remaining: int = 3
    insurance_used: bool = False
    wager_size: float = 5.0
    game_over: bool = False
    # booth: {week: {host: pick}} picks FOR that week; tails {week: host}; record {host: [w, l]}
    booth_picks: dict = field(default_factory=dict)
    booth_tails: dict = field(default_factory=dict)
    booth_record: dict = field(default_factory=lambda: {h: [0, 0] for h in HOSTS})
    booth_graded: list = field(default_factory=list)
    bonuses: list = field(default_factory=list)


class JimmyBacktester:
    def __init__(self, year: int, slips_per_week: int):
        self.year = year
        self.slips_per_week = slips_per_week
        self.log: list[dict] = []   # every player action, so a lost season can be replayed exactly
        self.state = SeasonState(
            year=year, slips_per_week=slips_per_week, starting_bankroll=INITIAL_BANKROLL, current_week=1,
            bankroll=INITIAL_BANKROLL, slips=[], total_wagered=0.0, total_won=0.0, win_streak=0,
            loss_streak=0, achievements_unlocked=[], double_downs_used=0,
        )

    def calculate_wager_size(self) -> float:
        if self.state.bankroll >= 1000:
            return 15.0
        if self.state.bankroll >= 500:
            return 10.0
        return 5.0

    def week_slips(self, week: Optional[int] = None) -> list[Slip]:
        wk = self.state.current_week if week is None else week
        return [s for s in self.state.slips if s.week == wk]

    def evaluate_leg(self, leg: Leg, week: int) -> Optional[bool]:
        leg.actual_value = hist.actual(self.year, leg.player_id, week, leg.prop_type)
        leg.result = None if leg.margin is None else leg.margin > 0
        return leg.result

    def submit_slip(self, legs: list[Leg], challenge: Optional[str] = None) -> Slip:
        slip = self._submit_slip(legs, challenge)
        self.log.append({"op": "submit", "legs": [
            {"player_id": l.player_id, "team": l.team, "prop_type": l.prop_type, "line": l.line,
             "is_over": l.is_over, "confidence": round(l.confidence * 100, 2)} for l in legs]})
        return slip

    def _submit_slip(self, legs: list[Leg], challenge: Optional[str] = None) -> Slip:
        if self.state.game_over:
            raise ValueError("Season is over")
        if not 1 <= len(legs) <= 5:
            raise ValueError("Slip must have 1-5 legs")
        if len({(l.player_id, l.prop_type) for l in legs}) != len(legs):
            raise ValueError("Duplicate leg on slip")
        if len(self.week_slips()) >= self.slips_per_week:
            raise ValueError(f"Already placed {self.slips_per_week} slip(s) this week")

        wager = min(self.calculate_wager_size(), self.state.bankroll)
        slip = Slip(week=self.state.current_week, slip_id=f"W{self.state.current_week}_S{len(self.state.slips) + 1}_{self.year}",
                    legs=legs, wager=wager, submitted_at=datetime.now(timezone.utc).isoformat(), challenge_accepted=challenge)

        for leg in legs:
            self.evaluate_leg(leg, slip.week)
        live = [l for l in legs if l.result is not None]
        slip.legs_hit = sum(1 for l in live if l.result)
        slip.result = bool(live) and slip.legs_hit == len(live)
        if not live:  # every leg voided: stake back
            slip.payout, slip.roi, slip.result = wager, 0.0, None
            self.state.slips.append(slip)
            return slip

        self.state.total_wagered += wager
        if slip.result:
            slip.payout = wager * (2 ** len(live))
            slip.roi = (slip.payout - wager) / wager * 100
            self.state.total_won += slip.payout
            self.state.bankroll += slip.payout - wager
            self.state.win_streak += 1
            self.state.loss_streak = 0
        else:
            slip.payout, slip.roi = 0.0, -100.0
            self.state.bankroll -= wager
            self.state.loss_streak += 1
            self.state.win_streak = 0
        self.state.slips.append(slip)
        self._check_achievements()
        if self.state.bankroll <= 0:
            self.state.bankroll, self.state.game_over = 0.0, True
        return slip

    def grade_booth(self, week: int) -> None:
        """Grade the booth's picks for `week` once; a winning tailed host pays one wager unit."""
        if week in self.state.booth_graded or week not in self.state.booth_picks:
            return
        for host, pick in self.state.booth_picks[week].items():
            leg = Leg(pick["player_id"], pick["player_name"], pick["team"], pick["prop_type"], pick["line"],
                      pick["is_over"], pick["confidence"] / 100)
            self.evaluate_leg(leg, week)
            pick["actual"], pick["result"] = leg.actual_value, leg.result
            if leg.result is not None:
                self.state.booth_record[host][0 if leg.result else 1] += 1
            if self.state.booth_tails.get(week) == host and leg.result:
                bonus = self.calculate_wager_size()
                self.state.bankroll += bonus
                self.state.bonuses.append({"week": week, "host": host, "amount": bonus})
                self._unlock("booth_tail_cashed")
        self.state.booth_graded.append(week)

    def tail(self, host: str) -> None:
        wk = self.state.current_week + 1
        if host not in HOSTS:
            raise ValueError("Unknown host")
        if wk not in self.state.booth_picks:
            raise ValueError("Watch this week's recap first, the booth hasn't made picks yet")
        self.state.booth_tails[wk] = host
        self.log.append({"op": "tail", "host": host})

    def advance_week(self) -> None:
        if not self.week_slips():
            raise ValueError("Place at least one slip before advancing")
        self.log.append({"op": "advance"})
        if self.state.current_week >= SEASON_WEEKS:
            self.state.game_over = True
            return
        self.state.current_week += 1
        self.grade_booth(self.state.current_week)

    def _check_achievements(self) -> None:
        wk = self.state.current_week
        if sum(1 for s in self.state.slips if s.result) == 1:
            self._unlock("first_win")
        week_slips = self.week_slips()
        if len(week_slips) == self.slips_per_week and all(s.result for s in week_slips):
            self._unlock(f"perfect_week_{wk}")
        if self.state.win_streak >= 3:
            self._unlock("win_streak_3")
        if self.state.bankroll >= self.state.starting_bankroll * 2:
            self._unlock("bankroll_doubles")

    def _unlock(self, key: str) -> None:
        if key not in self.state.achievements_unlocked:
            self.state.achievements_unlocked.append(key)

    def get_state_dict(self) -> dict:
        s = self.state
        return {
            "year": s.year, "slips_per_week": s.slips_per_week, "current_week": s.current_week,
            "bankroll": round(s.bankroll, 2), "total_wagered": round(s.total_wagered, 2), "total_won": round(s.total_won, 2),
            "win_streak": s.win_streak, "loss_streak": s.loss_streak, "achievements": s.achievements_unlocked,
            "game_over": s.game_over, "wager_size": self.calculate_wager_size(),
            "slips_this_week": len(self.week_slips()),
            "log": self.log,
            "slips": [self._serialize_slip(x) for x in s.slips],
            "booth": {"record": s.booth_record, "tails": s.booth_tails, "bonuses": s.bonuses,
                      "next_picks": s.booth_picks.get(s.current_week + 1)},
        }

    @staticmethod
    def _serialize_slip(slip: Slip) -> dict:
        return {
            "slip_id": slip.slip_id, "week": slip.week, "wager": round(slip.wager, 2), "legs": len(slip.legs),
            "legs_hit": slip.legs_hit, "result": slip.result, "payout": round(slip.payout or 0, 2), "roi": slip.roi,
            "challenge": slip.challenge_accepted,
            "leg_details": [{"player_id": l.player_id, "player_name": l.player_name, "team": l.team, "prop_type": l.prop_type,
                             "label": l.label, "line": l.line, "is_over": l.is_over, "actual": l.actual_value,
                             "result": l.result, "headshot": l.headshot} for l in slip.legs],
        }


_SESSIONS: dict[str, tuple[float, JimmyBacktester]] = {}
_SLOCK = threading.Lock()
_TTL = 60 * 60 * 24 * 7


def new_session(year: int, slips_per_week: int) -> tuple[str, JimmyBacktester]:
    sid = uuid.uuid4().hex
    bt = JimmyBacktester(year, slips_per_week)
    with _SLOCK:
        now = time.time()
        for k in [k for k, (t, _) in _SESSIONS.items() if now - t > _TTL]:
            del _SESSIONS[k]
        _SESSIONS[sid] = (now, bt)
    return sid, bt


def get_session(sid: str) -> Optional[JimmyBacktester]:
    with _SLOCK:
        hit = _SESSIONS.get(sid)
        if hit:
            _SESSIONS[sid] = (time.time(), hit[1])
        return hit[1] if hit else None


def restore(year: int, slips_per_week: int, log: list[dict]) -> tuple[str, JimmyBacktester]:
    """Rebuild a season by replaying its action log. Boards and results are deterministic, so the
    replay lands on exactly the state the player left."""
    from jimmy_recap import generate_weekly_recap   # booth picks are made when a recap is generated

    sid, bt = new_session(year, slips_per_week)
    for step in log[:500]:
        op = step.get("op")
        if op == "submit":
            legs = []
            for l in step["legs"]:
                if l.get("prop_type") not in hist.PROPS:
                    raise ValueError("Unknown prop type in log")
                meta = hist.player(year, str(l["player_id"]))
                legs.append(Leg(str(l["player_id"]), meta["name"], str(l.get("team") or meta["team"]), l["prop_type"],
                                float(l["line"]), bool(l.get("is_over", True)), float(l.get("confidence", 50)) / 100,
                                headshot=meta["headshot"]))
            bt.submit_slip(legs)
        elif op == "tail":
            generate_weekly_recap(bt, bt.state.current_week)
            bt.tail(str(step["host"]))
        elif op == "advance":
            bt.advance_week()
        else:
            raise ValueError(f"Unknown action in log: {op}")
    return sid, bt

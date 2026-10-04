"""
MATCHUP TAG -- stamp every ticket leg with who the player's team is playing, e.g. "DAL @ HOU" (road team first)
or "HOU vs DAL" (home team first), so a leg reads without a headshot. Uses the leg's own gameId when it has one
(early slate), else the team's next unplayed game from the schedule.
"""
from __future__ import annotations

from functools import lru_cache

import bpl
import data


@lru_cache(maxsize=2)
def _games(_today: str) -> dict[str, tuple[str, str]]:
    return {r["game_id"]: (r["away_team"], r["home_team"]) for r in data.load("schedule")}


def _text(team: str, away: str, home: str) -> str:
    return f"{team} @ {home}" if team == away else f"{team} vs {away}"


@lru_cache(maxsize=1)
def _team_names() -> dict[str, str]:
    return {r["abbr_lake"]: r["full_name"] for r in data.load("team_abbr_map") if r.get("abbr_lake")}


def tag_leg(leg: dict) -> dict:
    if leg.get("sport") or leg.get("matchup"):          # game-line legs already name both teams
        return leg
    if leg.get("teamName"):
        return leg
    team = leg.get("team") or data.player_dimension().get(leg.get("playerId", ""), {}).get("team")
    if not team:
        return leg
    gid = leg.get("gameId")
    pair = _games(bpl.today_central()).get(gid) if gid else None
    if not pair:
        nxt = bpl.next_games().get(team)
        pair = _games(bpl.today_central()).get(nxt["gameId"]) if nxt else None
    if pair and team in pair:
        leg["matchup"] = _text(team, *pair)
    leg["teamName"] = _team_names().get(team, team)
    return leg


def tag(slips):
    """Accepts a slip, a list of slips, or a {id: slip} dict; tags in place and returns the same object."""
    items = [slips] if isinstance(slips, dict) and "legs" in slips else list(slips.values()) if isinstance(slips, dict) else slips
    for s in items:
        for leg in (s or {}).get("legs", []):
            tag_leg(leg)
    return slips

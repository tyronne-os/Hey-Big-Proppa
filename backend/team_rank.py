"""
TEAM RANK -- the teammate ranking that lives on every player page.

THE POINT
=========
A single number on a player page means nothing on its own. "5.5 projected
receptions" is only useful next to his own quarterback's other options: is he
the guy, or is he the third guy? Jimmy weighs the competition for the ball;
so does a subscriber reading the board. So every player page carries his
team's ranking IN THE SAME CATEGORY HE IS BEING VIEWED UNDER -- rushing
yards vs his team's rushing backs, receiving yards vs his team's receivers,
targets vs his team's pass catchers.

Every row is a real lake fact: the player's own weekly stat from the gold
CSVs, plus the posted line where one exists, plus a hit rate against it.
Nothing here is a projection and nothing is a model output -- it is the
season as it actually happened, ranked.

MARKETS
=======
    rushyds  -> player_rushing_week.rushing_yards     (the whole RB room)
    recyds   -> player_receiving_week.receiving_yards  (the whole WR/TE room)
    recs     -> player_receiving_week.receptions        (the whole WR/TE room)
    passyds  -> player_passing_week.passing_yards      (QBs only -- his own position room)
    anytd    -> player_scoring_week.total_tds          (his own position room)

A player with no games in the category is simply not in the room: the room
is built from players who actually logged the stat this season.

WHY "HIS OWN POSITION ROOM" FOR PASSING
=======================================
There is only ever one starting quarterback, so a QB's room is the QBs on
his own roster (the backup -- who would take over if he sat) rather than the
entire roster, which would be meaningless. For a running back the room IS
the whole backfield, because that is the actual competition for carries.
"""
from __future__ import annotations

import re

import data

# market -> (gold csv, stat column, positions included in the room, label)
MARKET_SOURCES: dict[str, tuple[str, str, tuple[str, ...], str]] = {
    "rushyds": ("player_rushing_week", "rushing_yards", ("RB", "FB", "QB"), "RUSHING YARDS"),
    "recyds":  ("player_receiving_week", "receiving_yards", ("WR", "TE", "RB"), "RECEIVING YARDS"),
    "recs":    ("player_receiving_week", "receptions", ("WR", "TE", "RB"), "RECEPTIONS"),
    "passyds": ("player_passing_week", "passing_yards", ("QB",), "PASSING YARDS"),
    "anytd":   ("player_scoring_week", "total_tds", ("QB", "RB", "WR", "TE", "FB"), "TOUCHDOWNS"),
}

ROOM_SIZE = 8


def _f(v: object, d: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return d


def _player_pos(pid: str) -> str:
    return (data.player_dimension().get(pid) or {}).get("position", "").upper()


def _display_name(pid: str) -> str:
    """The player's real name, or a readable fallback when the lake has no name for him.

    A raw gsis_id rendered as a name ("00-0040172") in a leaderboard looks broken, so
    it falls back to the ID with the leading zeros stripped -- still honest, still
    clickable, just not pretending to be a name.
    """
    nm = data.player_name(pid)
    if nm and not re.fullmatch(r"\d{2}-\d{7}", nm or ""):
        return nm
    return pid.replace("00-", "#")


def _player_team(pid: str) -> str:
    return (data.player_dimension().get(pid) or {}).get("team", "") or data.player_team(pid)


def _lines_by_market(market: str) -> dict[tuple[str, str], dict]:
    """
    (market_slug, normalized player name) -> the posted line.

    The gold prop table carries RotoWire's own numeric player_id, not the nflverse
    gsis_id the rest of the lake uses (docs/HANDOFF.md sec 5.8 -- the id bridge
    table exists but has never been populated). So the join is by normalized player
    NAME, the same workaround scripts/matchup_report.py uses. The table also has
    no team column, so the name alone is the key; a name collision across teams
    would take the first row, which is the same limitation the rest of the lake
    already lives with.
    """
    out: dict[tuple[str, str], dict] = {}
    for r in data.load("prop_best_price"):
        m = (r.get("market_slug") or "").lower()
        if m != market:
            continue
        nm = data.normalize_name(r.get("player_name") or "")
        if not nm:
            continue
        key = (m, nm)
        # keep the first row that actually carries a line
        if key not in out or (not out[key].get("line") and r.get("line")):
            out[key] = r
    return out


def _room(market: str, player_id: str, player_team: str) -> list[dict]:
    """Every teammate in the same category, ranked, with his game log and his line."""
    src, stat_col, positions, label = MARKET_SOURCES[market]
    rows = [r for r in data.load(src) if r.get("player_id") == player_id]
    if not rows:
        return []

    # the stat column may not exist (anytd uses a derived total_tds)
    has_col = stat_col in rows[0]
    if not has_col and market == "anytd":
        stat_col = "total_tds"

    lines = _lines_by_market(market)

    # every player on the team who logged this stat
    per_player: dict[str, dict] = {}
    for r in data.load(src):
        pid = r.get("player_id") or ""
        if not pid:
            continue
        if _player_team(pid) != player_team:
            continue
        if _player_pos(pid) not in positions:
            continue
        try:
            val = _f(r.get(stat_col))
        except Exception:
            val = 0.0
        if val <= 0:
            continue
        wk = int(_f(r.get("week")))
        log = per_player.setdefault(pid, {"playerId": pid, "games": [], "season": 0.0})
        log["games"].append({
            "week": wk,
            "opponent": r.get("opponent_team") or "",
            "value": val,
        })
        log["season"] += val

    if player_id not in per_player:
        # the viewer himself is missing from the stat file: still show the room
        per_player[player_id] = {"playerId": player_id, "games": [], "season": 0.0}

    out: list[dict] = []
    for pid, rec in per_player.items():
        games = sorted(rec["games"], key=lambda g: g["week"])
        n = len(games)
        avg = rec["season"] / n if n else 0.0
        l5 = games[-5:]
        l5avg = sum(g["value"] for g in l5) / len(l5) if l5 else None

        # the posted line for this player in this market (name key)
        nm = data.normalize_name(data.player_name(pid))
        line_row = lines.get((market, nm))
        line = None
        if line_row:
            try:
                line = float(line_row.get("line")) if line_row.get("line") else None
            except (TypeError, ValueError):
                line = None

        hits = sum(1 for g in games if line is not None and g["value"] >= line)
        l5hits = sum(1 for g in l5 if line is not None and g["value"] >= line)

        out.append({
            "playerId": pid,
            "name": _display_name(pid),
            "position": _player_pos(pid),
            "games": n,
            "season": round(rec["season"], 1),
            "seasonAvg": round(avg, 1),
            "l5Avg": round(l5avg, 1) if l5avg is not None else None,
            "line": line,
            "hitRate": round(hits / n, 3) if n and line is not None else None,
            "l5HitRate": round(l5hits / len(l5), 3) if l5 and line is not None else None,
            "l5": [{"week": g["week"], "opponent": g["opponent"], "value": g["value"], "over": (g["value"] >= line) if line is not None else None}
                   for g in l5],
            "log": [{"week": g["week"], "opponent": g["opponent"], "value": g["value"]} for g in games],
            "isViewer": pid == player_id,
        })

    out.sort(key=lambda r: (-r["seasonAvg"], -r["season"], r["name"]))
    for i, r in enumerate(out):
        r["rank"] = i + 1
    return out[:ROOM_SIZE]


def team_rank(player_id: str, market: str) -> dict:
    """
    The teammate ranking for one player in one category.

    Returns {market, label, sourceStatus, team, rows, viewerRank, viewer}.
    sourceStatus is "ok" only when the lake actually has this player's rows.
    """
    market = (market or "").lower()
    if market not in MARKET_SOURCES:
        return {"market": market, "label": "", "sourceStatus": "empty", "team": "", "rows": [],
                "viewerRank": None, "viewer": None}

    team = _player_team(player_id)
    rows = _room(market, player_id, team)
    if not rows:
        return {"market": market, "label": MARKET_SOURCES[market][3], "sourceStatus": "empty",
                "team": team, "rows": [], "viewerRank": None, "viewer": None}

    viewer = next((r for r in rows if r["isViewer"]), None)
    if viewer is None:
        # He logged no games in this category but his teammates did -- keep him visible
        # at the bottom of his own room rather than pretending the room is empty.
        viewer = {
            "playerId": player_id,
            "name": _display_name(player_id),
            "position": _player_pos(player_id),
            "rank": len(rows) + 1,
            "games": 0,
            "season": 0.0,
            "seasonAvg": 0.0,
            "l5Avg": None,
            "line": None,
            "hitRate": None,
            "l5HitRate": None,
            "l5": [],
            "log": [],
            "isViewer": True,
        }
        rows.append(viewer)
    return {
        "market": market,
        "label": MARKET_SOURCES[market][3],
        "sourceStatus": "ok",
        "team": team,
        "rows": rows,
        "viewerRank": viewer["rank"],
        "viewer": viewer,
    }

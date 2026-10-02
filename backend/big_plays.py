"""
High-production tracking from the Tank01 play-by-play.

For every game it reads every play, keeps a running stat line per player, and records:
  * BIG PLAYS: every catch or run of 20+ yards (40+ is "explosive"), with quarter and clock.
  * EARLY CLEARS: every player whose FanDuel line (receptions, receiving / rushing / passing yards) was
    already beaten by the middle of the second quarter (Q2 7:30, 37.5% of regulation), and exactly when.
  * PER-PLAYER TOTALS: targets, catches, yards, and catches/runs of 10+, 16+/12+, 20+ and 40+ yards. This is
    how a game the lake has not ingested yet (a Thursday game) still feeds the Targets board.

MY BOO stores one JSON file per game in lake/gold/nfl/high_production/ and quotes it in her reports;
the Tuesday batch adds each leg's "cleared at" moment to the training package.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import data

_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
OUT_DIR = _GOLD / "high_production"
MID_Q2 = 0.375                       # Q2 7:30 left = 37.5% of regulation
BIG, EXPLOSIVE = 20, 40
LINE_MARKETS = {"recs": "rec", "recyds": "recyds", "rushyds": "rushyds", "passyds": "passyds"}
LABEL = {"rec": "receptions", "recyds": "receiving yards", "rushyds": "rushing yards", "passyds": "passing yards"}


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _elapsed(period: str, clock: str) -> float:
    import fantasy
    return fantasy._elapsed(period or "", clock or "15:00", False)


def tank_game_id(game: dict) -> str:
    return f"{game['game_date'].replace('-', '')}_{game['away_team']}@{game['home_team']}"


def _pbp(game: dict, ttl: int = 60) -> dict | None:
    import tank01
    if ttl <= 60:                                  # live: share the watcher's cached call
        body = tank01.get_live_boxscore(tank_game_id(game))
    else:
        raw = tank01._get("getNFLBoxScore", {"gameID": tank_game_id(game), "playByPlay": "true", "fantasyPoints": "false"}, ttl=ttl)
        body = (raw or {}).get("body")
    return body if isinstance(body, dict) and body.get("allPlayByPlay") else None


@lru_cache(maxsize=1)
def _ids() -> dict[tuple[str, str], str]:
    out = {}
    for pid, d in data.player_dimension().items():
        out[(data.normalize_name(d.get("name", "")), d.get("team", ""))] = pid
        out.setdefault((data.normalize_name(d.get("name", "")), ""), pid)
    return out


def _lines(game: dict) -> dict[tuple[str, str], float]:
    """(player_id, stat) -> FanDuel pregame line for this game (latest pull)."""
    teams = {game["home_team"], game["away_team"]}
    best: dict[tuple[str, str], tuple[str, float]] = {}
    for r in data.load("prop_line_rotowire"):
        if r.get("book_slug") != "fanduel" or r.get("market_slug") not in LINE_MARKETS or r.get("team") not in teams or not r.get("line"):
            continue
        opp = (r.get("opponent") or "").lstrip("@")
        if opp not in teams:
            continue
        pid = _ids().get((data.normalize_name(r["player_name"]), r["team"]))
        if not pid:
            continue
        key = (pid, LINE_MARKETS[r["market_slug"]])
        if key not in best or r.get("fetched_at_utc", "") > best[key][0]:
            best[key] = (r.get("fetched_at_utc", ""), _f(r["line"]))
    return {k: v for k, (_, v) in best.items()}


def analyze(game: dict, ttl: int = 60) -> dict | None:
    """Walk the play-by-play once. Returns totals per player, big plays and early line clears."""
    body = _pbp(game, ttl)
    if not body:
        return None
    who: dict[str, dict] = {}
    for tid, p in (body.get("playerStats") or {}).items():
        if isinstance(p, dict):
            pid = _ids().get((data.normalize_name(p.get("longName", "")), p.get("team", ""))) \
                or _ids().get((data.normalize_name(p.get("longName", "")), ""))
            who[str(tid)] = {"name": p.get("longName", ""), "team": p.get("team", ""), "pid": pid}
    lines = _lines(game)
    run: dict[str, dict] = {}
    big, cleared = [], {}
    for play in body["allPlayByPlay"]:
        t = _elapsed(play.get("playPeriod", ""), play.get("playClock", ""))
        for tid, s in (play.get("playerStats") or {}).items():
            w = who.get(str(tid))
            if not w:
                continue
            tot = run.setdefault(str(tid), {"name": w["name"], "team": w["team"], "pid": w["pid"],
                                            "tgt": 0, "rec": 0, "recyds": 0.0, "car": 0, "rushyds": 0.0, "passyds": 0.0,
                                            "rec10": 0, "rec16": 0, "rec20": 0, "rec40": 0, "rush10": 0, "rush12": 0, "rush20": 0, "rush40": 0})
            rec, rush, pas = s.get("Receiving") or {}, s.get("Rushing") or {}, s.get("Passing") or {}
            ry = _f(rec.get("recYds"))
            tot["tgt"] += int(_f(rec.get("targets")))
            if _f(rec.get("receptions")):
                tot["rec"] += 1
                for n in (10, 16, 20, 40):
                    tot[f"rec{n}"] += ry >= n
            tot["recyds"] += ry
            hy = _f(rush.get("rushYds"))
            if _f(rush.get("carries")):
                tot["car"] += 1
                for n in (10, 12, 20, 40):
                    tot[f"rush{n}"] += hy >= n
            tot["rushyds"] += hy
            tot["passyds"] += _f(pas.get("passYds"))
            gain = max(ry if _f(rec.get("receptions")) else 0, hy if _f(rush.get("carries")) else 0)
            if gain >= BIG:
                big.append({"player": w["name"], "pid": w["pid"], "team": w["team"], "yards": int(gain),
                            "kind": "catch" if ry >= hy else "run", "explosive": gain >= EXPLOSIVE,
                            "period": play.get("playPeriod"), "clock": play.get("playClock"), "elapsed": round(t, 3),
                            "play": play.get("play", "")[:160]})
            if w["pid"]:
                for stat in ("rec", "recyds", "rushyds", "passyds"):
                    line = lines.get((w["pid"], stat))
                    if line is not None and (w["pid"], stat) not in cleared and tot[stat] > line:
                        cleared[(w["pid"], stat)] = {"player": w["name"], "pid": w["pid"], "team": w["team"], "stat": stat,
                                                     "label": LABEL[stat], "line": line, "at": f"{play.get('playPeriod')} {play.get('playClock')}",
                                                     "elapsed": round(t, 3), "early": t <= MID_Q2}
    final_line = {}
    for (pid, stat), c in cleared.items():
        tot = next((v for v in run.values() if v["pid"] == pid), None)
        if tot:
            c["final"] = round(tot[stat], 1)
            c["beat_by"] = round(tot[stat] - c["line"], 1)
    box = {}
    for tid, p in (body.get("playerStats") or {}).items():          # official box totals (the play-by-play misses penalised snaps)
        w = who.get(str(tid))
        rec = (p or {}).get("Receiving") or {}
        if w and w["pid"] and rec:
            box[w["pid"]] = {"team": w["team"], "tgt": _f(rec.get("targets")), "rec": _f(rec.get("receptions")),
                             "yds": _f(rec.get("recYds")), "td": _f(rec.get("recTD"))}
    status = str(body.get("gameStatus", ""))
    return {"game_id": game["game_id"], "label": f"{game['away_team']} @ {game['home_team']}", "status": status,
            "final": "complete" in status.lower() or "final" in status.lower(),
            "players": {v["pid"] or k: v for k, v in run.items()}, "box": box,
            "big_plays": sorted(big, key=lambda b: b["elapsed"]),
            "early_clears": sorted((c for c in cleared.values() if c["early"]), key=lambda c: c["elapsed"]),
            "all_clears": sorted(cleared.values(), key=lambda c: c["elapsed"]),
            "lines_checked": len(lines)}


def record(game: dict, ttl: int = 60) -> dict | None:
    """Analyze and store one game. Final games are stored once and then read from disk."""
    path = OUT_DIR / f"{game['game_id']}.json"
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            if saved.get("final") and "box" in saved:
                return saved
        except (OSError, ValueError):
            pass
    res = analyze(game, ttl)
    if res:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(res, indent=1))
    return res


def stored(game_id: str) -> dict | None:
    try:
        return json.loads((OUT_DIR / f"{game_id}.json").read_text())
    except (OSError, ValueError):
        return None


def summary_text(hp: dict, teams: set[str] | None = None, limit: int = 6) -> str:
    """One paragraph for MY BOO's report: who blew past the line early, and the big plays."""
    ec = [c for c in hp["early_clears"] if not teams or c["team"] in teams]
    bp = [b for b in hp["big_plays"] if not teams or b["team"] in teams]
    parts = []
    if ec:
        parts.append("Beat the line by mid-second quarter: " + "; ".join(
            f"{c['player']} cleared {c['line']:g} {c['label']} at {c['at']}" + (f" and finished at {c['final']:g}" if c.get("final") is not None else "")
            for c in ec[:limit]) + ".")
    if bp:
        n40 = sum(b["explosive"] for b in bp)
        by: dict[str, int] = {}
        for b in bp:
            by[b["team"]] = by.get(b["team"], 0) + 1
        parts.append(f"Big plays (20+ yards): {len(bp)}" + (f", {n40} of them 40+" if n40 else "") + " (" +
                     ", ".join(f"{t} {n}" for t, n in by.items()) + "). Longest: " +
                     "; ".join(f"{b['player']} {b['yards']}-yard {b['kind']} ({b['period']} {b['clock']})" for b in sorted(bp, key=lambda b: -b["yards"])[:3]) + ".")
    return ("High production: " + " ".join(parts)) if parts else ""


def leg_cleared_at(hp: dict | None, pid: str | None, market: str) -> dict | None:
    if not hp or not pid:
        return None
    stat = {"recs": "rec", "recyds": "recyds", "rushyds": "rushyds", "passyds": "passyds"}.get(market)
    return next((c for c in hp["all_clears"] if c["pid"] == pid and c["stat"] == stat), None)

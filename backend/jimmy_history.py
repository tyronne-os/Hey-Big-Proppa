"""
Historical weekly player stats for the JIMMY time machine (2024 + 2025 seasons).

Pulls nflverse stats_player_week_{year}.csv once, trims it to skill players and the stat columns
JIMMY grades, and caches it under lake/gold/nfl/jimmy_history/. Lines for week N are built only
from games played before week N, so the board never peeks at the result.
"""
from __future__ import annotations

import csv
import io
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "jimmy_history"
URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv"
KEEP = ("player_id", "player_display_name", "position", "headshot_url", "week", "team", "opponent_team",
        "passing_yards", "rushing_yards", "receiving_yards", "receptions", "carries", "targets", "attempts")
SKILL = {"QB", "RB", "WR", "TE"}
_LOCK = threading.Lock()

PROPS = {
    "pass_yds":   {"col": "passing_yards",   "label": "PASS YDS",   "pos": {"QB"},             "floor": 190, "unit": "yards"},
    "rush_yds":   {"col": "rushing_yards",   "label": "RUSH YDS",   "pos": {"RB"},             "floor": 50,  "unit": "yards"},
    "rec_yds":    {"col": "receiving_yards", "label": "REC YDS",    "pos": {"WR", "TE", "RB"}, "floor": 50,  "unit": "yards"},
    "receptions": {"col": "receptions",      "label": "RECEPTIONS", "pos": {"WR", "TE", "RB"}, "floor": 4.5, "unit": "catches"},
}


def _path(year: int) -> Path:
    return CACHE / f"stats_{year}.csv"


def _download(year: int) -> None:
    req = urllib.request.Request(URL.format(year=year), headers={"User-Agent": "big-proppa-jimmy/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=KEEP)
    w.writeheader()
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("season_type") == "REG" and row.get("position") in SKILL:
            w.writerow({k: row.get(k, "") for k in KEEP})
    tmp = _path(year).with_suffix(".tmp")
    tmp.write_text(out.getvalue())
    tmp.replace(_path(year))


@lru_cache(maxsize=4)
def season(year: int) -> dict:
    """{"games": {(pid, week): row}, "players": {pid: meta}, "weeks": {pid: [weeks played]}}"""
    with _LOCK:
        if not _path(year).exists():
            try:
                _download(year)
            except Exception:
                return {"games": {}, "players": {}, "weeks": {}}
    games, players, weeks = {}, {}, {}
    with _path(year).open(newline="") as fh:
        for row in csv.DictReader(fh):
            pid, wk = row["player_id"], int(row["week"])
            games[(pid, wk)] = row
            players[pid] = {"name": row["player_display_name"], "pos": row["position"],
                            "team": row["team"], "headshot": row["headshot_url"]}
            weeks.setdefault(pid, []).append(wk)
    for w in weeks.values():
        w.sort()
    return {"games": games, "players": players, "weeks": weeks}


def _num(v) -> float:
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def actual(year: int, player_id: str, week: int, prop: str) -> float | None:
    """The stat the player actually put up that week; None when he did not play (leg voids)."""
    row = season(year)["games"].get((player_id, week))
    return None if row is None else _num(row[PROPS[prop]["col"]])


def history(year: int, player_id: str, before_week: int, prop: str, n: int = 6) -> list[float]:
    """Last n values strictly before `before_week`, reaching into last season early in the year."""
    col = PROPS[prop]["col"]
    cur = season(year)
    vals = [_num(cur["games"][(player_id, w)][col]) for w in cur["weeks"].get(player_id, []) if w < before_week]
    if len(vals) < n:
        prev = season(year - 1)
        prior = [_num(prev["games"][(player_id, w)][col]) for w in prev["weeks"].get(player_id, [])]
        vals = prior + vals
    return vals[-n:]


def _half(x: float) -> float:
    return int(x) + 0.5


def _has_role(row: dict) -> bool:
    pos = row.get("position")
    if pos == "QB":
        return _num(row.get("attempts")) >= 15
    if pos == "RB":
        return _num(row.get("carries")) >= 8 or _num(row.get("targets")) >= 4
    return _num(row.get("targets")) >= 3


def board(year: int, week: int, size: int = 16) -> list[dict]:
    """Friday-morning prop board for `week`, built from what was known before kickoff."""
    cur = season(year)
    playing = {row["team"] for (_, wk), row in cur["games"].items() if wk == week}   # the schedule, known in advance
    out = []
    for pid, meta in cur["players"].items():
        prior = [w for w in cur["weeks"].get(pid, []) if w < week]
        team = cur["games"][(pid, prior[-1])]["team"] if prior else meta["team"]
        if team not in playing:
            continue
        if week > 1 and (not prior or prior[-1] < week - 2):
            continue  # hasn't suited up lately
        last = cur["games"].get((pid, prior[-1])) if prior else None
        if last is None:
            prev = season(year - 1)
            pw = prev["weeks"].get(pid, [])
            last = prev["games"].get((pid, pw[-1])) if pw else None
        if last is None or not _has_role(last):
            continue
        if len(prior) < 2:  # early season: must have been a regular last year, not a fill-in
            prev = season(year - 1)
            if sum(_has_role(prev["games"][(pid, w)]) for w in prev["weeks"].get(pid, [])) < 8:
                continue
        for prop, spec in PROPS.items():
            if meta["pos"] not in spec["pos"]:
                continue
            vals = history(year, pid, week, prop)
            if len(vals) < 3:
                continue
            mean = sum(vals) / len(vals)
            if mean < spec["floor"]:
                continue
            line = _half(mean * 0.95)
            over_rate = sum(v > line for v in vals) / len(vals)
            last3 = sum(vals[-3:]) / 3
            trend = (last3 - mean) / mean if mean else 0
            conf = max(35, min(85, round(45 + over_rate * 30 + trend * 25)))
            out.append({
                "player_id": pid, "player_name": meta["name"], "team": team, "pos": meta["pos"],
                "headshot": meta["headshot"], "prop_type": prop, "label": spec["label"], "unit": spec["unit"],
                "line": line, "avg": round(mean, 1), "last3": round(last3, 1), "confidence": conf,
                "form": "hot" if trend > 0.12 else "cold" if trend < -0.12 else "steady",
            })
    out.sort(key=lambda p: (-p["confidence"], -p["avg"]))
    picked, per_prop, seen = [], {}, set()
    for p in out:
        if p["player_id"] in seen or per_prop.get(p["prop_type"], 0) >= size // 3:
            continue
        picked.append(p)
        seen.add(p["player_id"])
        per_prop[p["prop_type"]] = per_prop.get(p["prop_type"], 0) + 1
        if len(picked) >= size:
            break
    return picked


def player(year: int, player_id: str) -> dict:
    return season(year)["players"].get(player_id, {"name": player_id, "pos": "", "team": "", "headshot": ""})

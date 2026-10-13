"""
LAKE SYNC -- keeps the nflverse half of the data lake in step with the league, so the site runs itself.

ESPN is handled by boo_staff's agents (scoreboard, injuries, lines, standings ...). This module is the other half:
it pulls the nflverse releases that feed every page (schedule, weekly player stats, depth charts, official injuries,
headshots), validates them, swaps them in atomically, drops the in-memory caches, and works out the CURRENT week so
last week's picture clears out and this week's takes over.

Plain code, no LLM. Runs as the "lake_clerk" agent in boo_staff (on boot, then on its cadence) and by hand:
    python3 scripts/sync_all.py
Every step is independent: a failing source is logged and skipped, the others still land. Downloads are skipped
when the source has not changed (ETag / Last-Modified), so a tick that finds nothing new costs a few HEAD requests.
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
GOLD = _ROOT / "lake" / "gold" / "nfl"
ESPN_DIR = _ROOT / "lake" / "gold" / "espn"
STATE = ESPN_DIR / "lake_sync.json"
BASE = "https://github.com/nflverse/nflverse-data/releases/download"
UA = {"User-Agent": "big-proppa-lake-sync/1.0"}
_LOCK = threading.Lock()
SKILL = ("QB", "RB", "WR", "TE", "FB")


def _season() -> int:
    n = datetime.now(timezone.utc)
    return n.year if n.month >= 3 else n.year - 1      # the NFL season that is live (Jan/Feb still belong to last year)


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save_state(s: dict) -> None:
    ESPN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s))
    tmp.replace(STATE)


def _sig(url: str) -> str:
    req = urllib.request.Request(url, method="HEAD", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return f"{r.headers.get('ETag', '')}|{r.headers.get('Last-Modified', '')}|{r.headers.get('Content-Length', '')}"


def _get(url: str) -> bytes:
    last: Exception | None = None
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as e:          # noqa: BLE001 -- retry then surface
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"download failed {url}: {last}")


def _rows(path: Path) -> tuple[list[str], list[dict]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def _changed(key: str, url: str, st: dict, force: bool) -> tuple[bool, str]:
    try:
        sig = _sig(url)
    except Exception:                    # HEAD unsupported or flaky: treat as changed
        return True, ""
    return (force or st.get("sig", {}).get(key) != sig), sig


def _sf(r: dict, k: str) -> float:
    try:
        return float(r.get(k) or 0)
    except ValueError:
        return 0.0


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(round(x, 4))


# ---------------------------------------------------------------------------
# steps (each returns a one-line note)
# ---------------------------------------------------------------------------

def sync_schedule(st: dict, force: bool) -> str:
    url = f"{BASE}/schedules/games.csv"
    ch, sig = _changed("schedule", url, st, force)
    if not ch:
        return "schedule unchanged"
    new = list(csv.DictReader(io.StringIO(_get(url).decode("utf-8"))))
    cols_old, old = _rows(GOLD / "schedule.csv")
    if len(new) < 0.95 * len(old):
        raise RuntimeError(f"schedule shrank ({len(new)} < {len(old)}); kept the old file")
    _write(GOLD / "schedule.csv", list(new[0].keys()), new)
    st.setdefault("sig", {})["schedule"] = sig
    played = sum(1 for r in new if r["season"] == str(_season()) and r.get("home_score") not in ("", None))
    return f"schedule {len(new)} games ({played} played in {_season()})"


_WEEK_FILES = ("player_passing_week", "player_rushing_week", "player_receiving_week", "player_kicking_week",
               "player_defense_week", "player_scoring_week", "player_scrimmage_week", "player_returns_week")


def _derived(name: str, r: dict) -> dict:
    if name == "player_scoring_week":
        tds = sum(_sf(r, k) for k in ("rushing_tds", "receiving_tds", "def_tds", "special_teams_tds", "fumble_recovery_tds", "pt_return_tds"))
        two = sum(_sf(r, k) for k in ("passing_2pt_conversions", "rushing_2pt_conversions", "receiving_2pt_conversions", "def_2pt_made"))
        return {"total_tds": _num(tds), "total_points": _num(6 * tds + 2 * two + _sf(r, "pat_made") + 3 * _sf(r, "fg_made") + 2 * _sf(r, "def_safeties"))}
    if name == "player_scrimmage_week":
        t = _sf(r, "carries") + _sf(r, "receptions")
        y = _sf(r, "rushing_yards") + _sf(r, "receiving_yards")
        return {"touches": _num(t), "scrimmage_yards": _num(y), "scrimmage_tds": _num(_sf(r, "rushing_tds") + _sf(r, "receiving_tds")),
                "yards_per_touch": _num(y / t) if t else "0",
                "scrimmage_first_downs": _num(_sf(r, "rushing_first_downs") + _sf(r, "receiving_first_downs")),
                "scrimmage_fumbles": _num(_sf(r, "rushing_fumbles") + _sf(r, "receiving_fumbles"))}
    return {}


def sync_player_weeks(st: dict, force: bool) -> str:
    """Upsert this season's weekly player stats. New (player, week) rows are added; the last two weeks are rewritten,
    because nflverse corrects stat lines for a few days after a game."""
    season = _season()
    url = f"{BASE}/stats_player/stats_player_week_{season}.csv"
    ch, sig = _changed("player_weeks", url, st, force)
    if not ch:
        return "player stats unchanged"
    src = [r for r in csv.DictReader(io.StringIO(_get(url).decode("utf-8"))) if r.get("player_id")]
    if not src:
        return "player stats empty (kept)"
    maxw = max(int(r["week"]) for r in src)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    added = fixed = 0
    for name in _WEEK_FILES:
        path = GOLD / f"{name}.csv"
        cols, rows = _rows(path)
        if not cols:
            continue
        keep = [r for r in rows if not (r["season"] == str(season) and int(r["week"] or 0) >= maxw - 1)]
        before = len(rows) - len(keep)
        have = {(r["player_id"], r["season"], r["week"]) for r in keep}
        out = list(keep)
        n_new = 0
        for r in src:
            wk = int(r["week"])
            if wk < maxw - 1 and (r["player_id"], r["season"], str(wk)) in have:
                continue
            o = {c: r.get(c, "") for c in cols}
            o.update(_derived(name, r))
            o["ingest_run_id"] = run
            out.append(o)
            n_new += 1
        out.sort(key=lambda x: (x["season"], int(x["week"] or 0)))
        if len(out) < len(rows) - 200:
            raise RuntimeError(f"{name} would lose rows; kept the old file")
        _write(path, cols, out)
        added += max(0, n_new - before)
        fixed += min(before, n_new)
    st.setdefault("sig", {})["player_weeks"] = sig
    return f"player stats through week {maxw}: +{added} new rows, {fixed} refreshed"


def sync_depth_charts(st: dict, force: bool) -> str:
    """Games not yet played get the latest depth chart; games already played keep the chart frozen at kickoff."""
    season = _season()
    url = f"{BASE}/depth_charts/depth_charts_{season}.csv"
    ch, sig = _changed("depth", url, st, force)
    if not ch:
        return "depth charts unchanged"
    latest: dict[str, list[dict]] = {}
    newest: dict[str, str] = {}
    for r in csv.DictReader(io.StringIO(_get(url).decode("utf-8"))):
        if r["pos_abb"] not in SKILL or not r.get("gsis_id"):
            continue
        t = r["team"]
        if r["dt"] > newest.get(t, ""):
            newest[t], latest[t] = r["dt"], []
        if r["dt"] == newest[t]:
            latest[t].append(r)
    if len(latest) < 28:
        raise RuntimeError(f"depth chart only covers {len(latest)} teams; kept the old file")
    sc_cols, sched = _rows(GOLD / "schedule.csv")
    cols, old = _rows(GOLD / "depth_chart_pregame.csv")
    cols = cols or ["game_id", "season", "week", "team", "kickoff_utc", "snapshot_at", "pos_abb", "pos_name", "pos_rank", "player_id", "player_name"]
    now = datetime.now(timezone.utc)
    frozen_games, new_rows = set(), []
    unplayed = []
    for g in sched:
        if g["season"] != str(season) or g["game_type"] not in ("REG", "WC", "DIV", "CON", "SB"):
            continue
        ko = _kickoff(g)
        if ko and ko <= now:
            frozen_games.add(g["game_id"])
        else:
            unplayed.append((g, ko))
    keep = [r for r in old if r["game_id"] in frozen_games or r["season"] != str(season)]
    have_frozen = {r["game_id"] for r in keep}
    for g, ko in unplayed:
        for tm in (g["away_team"], g["home_team"]):
            for r in latest.get(tm, []):
                new_rows.append({"game_id": g["game_id"], "season": season, "week": g["week"], "team": tm,
                                 "kickoff_utc": ko.strftime("%Y-%m-%d %H:%M:%S+00:00") if ko else "",
                                 "snapshot_at": r["dt"].replace("T", " ").replace("Z", "+00:00"),
                                 "pos_abb": r["pos_abb"], "pos_name": r["pos_name"], "pos_rank": r["pos_rank"],
                                 "player_id": r["gsis_id"], "player_name": r["player_name"]})
    # a game that kicked off without a frozen snapshot (never captured) gets the latest chart rather than none
    for g in sched:
        if g["game_id"] in frozen_games and g["game_id"] not in have_frozen and g["season"] == str(season):
            ko = _kickoff(g)
            for tm in (g["away_team"], g["home_team"]):
                for r in latest.get(tm, []):
                    new_rows.append({"game_id": g["game_id"], "season": season, "week": g["week"], "team": tm,
                                     "kickoff_utc": ko.strftime("%Y-%m-%d %H:%M:%S+00:00") if ko else "",
                                     "snapshot_at": r["dt"].replace("T", " ").replace("Z", "+00:00"),
                                     "pos_abb": r["pos_abb"], "pos_name": r["pos_name"], "pos_rank": r["pos_rank"],
                                     "player_id": r["gsis_id"], "player_name": r["player_name"]})
    _write(GOLD / "depth_chart_pregame.csv", cols, keep + new_rows)
    st.setdefault("sig", {})["depth"] = sig
    return f"depth charts for {len(latest)} teams (snapshot {max(newest.values())[:16]}), {len(unplayed)} upcoming games refreshed"


def _kickoff(g: dict) -> datetime | None:
    d, t = g.get("gameday"), g.get("gametime") or "13:00"
    try:
        # nflverse gametime is US Eastern; ET is UTC-4 until early Nov, UTC-5 after. Close enough for freeze/unfreeze.
        local = datetime.fromisoformat(f"{d} {t}")
        off = 4 if (local.month, local.day) < (11, 1) and local.month >= 3 else 5
        return (local + timedelta(hours=off)).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def sync_injuries(st: dict, force: bool) -> str:
    season = _season()
    url = f"{BASE}/injuries/injuries_{season}.csv"
    ch, sig = _changed("injuries", url, st, force)
    if not ch:
        return "injury report unchanged"
    new = list(csv.DictReader(io.StringIO(_get(url).decode("utf-8"))))
    if not new:
        return "injury report empty (kept)"
    cols, old = _rows(GOLD / "injury_report_official.csv")
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    keep = [r for r in old if r.get("season") != str(season)]
    for r in new:
        r["ingest_run_id"] = run
    _write(GOLD / "injury_report_official.csv", cols or list(new[0].keys()) + ["ingest_run_id"], keep + new)
    st.setdefault("sig", {})["injuries"] = sig
    return f"injury report {len(new)} rows (latest week {max(int(r['week']) for r in new)})"


def sync_headshots(st: dict, force: bool) -> str:
    url = f"{BASE}/players/players.csv"
    ch, sig = _changed("players", url, st, force)
    if not ch:
        return "headshots unchanged"
    rows = [(r["gsis_id"], r["headshot"]) for r in csv.DictReader(io.StringIO(_get(url).decode("utf-8")))
            if r.get("gsis_id") and r.get("headshot") and (r.get("last_season") or "0") >= str(_season() - 2)]
    if len(rows) < 1500:
        raise RuntimeError("headshot table too small; kept the old file")
    with (GOLD / "player_headshots.csv.tmp").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player_id", "headshot_url"])
        w.writerows(sorted(rows))
    (GOLD / "player_headshots.csv.tmp").replace(GOLD / "player_headshots.csv")
    st.setdefault("sig", {})["players"] = sig
    return f"{len(rows)} headshots"


# ---------------------------------------------------------------------------
# week rollover + integrity
# ---------------------------------------------------------------------------

def current_week() -> dict:
    """The week the site should be showing: the earliest week of this season that still has an unfinished game.
    Last week clears the moment its final game is graded."""
    season = _season()
    _, sched = _rows(GOLD / "schedule.csv")
    games = [g for g in sched if g["season"] == season.__str__() and g["game_type"] == "REG"] or \
            [g for g in sched if g["season"] == str(season)]
    pending = [g for g in games if g.get("home_score") in ("", None)]
    wk = min((int(g["week"]) for g in pending), default=max((int(g["week"]) for g in games), default=1))
    wg = sorted((g for g in games if int(g["week"]) == wk), key=lambda g: (g["gameday"], g.get("gametime") or ""))
    nxt = next((g for g in pending), None)
    return {"season": season, "week": wk, "games": len(wg), "firstGameday": wg[0]["gameday"] if wg else None,
            "nextGameday": (nxt or {}).get("gameday"), "lastWeek": max(wk - 1, 1),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def clear_caches() -> None:
    """Drop every in-memory copy so pages re-read the files we just wrote."""
    import data
    data._cached_csv.cache_clear()
    for mod_name, fns in (("data", ("player_dimension", "_headshots", "chart_index", "_name_to_best_price", "_name_to_rotowire_fanduel")),):
        mod = __import__(mod_name)
        for fn in fns:
            f = getattr(mod, fn, None)
            if f is not None and hasattr(f, "cache_clear"):
                f.cache_clear()


def integrity() -> dict:
    """Every player on an open MY BOO slip must have a photo and a depth-chart row, or the slip cannot click through
    to a real player page. Reported, never fatal."""
    import data
    out = {"openLegs": 0, "noPhoto": [], "noPlayerPage": []}
    try:
        _, legs = _rows(GOLD / "myboo_legs.csv")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dim = data.player_dimension()
        by_name = {data.normalize_name(v["name"]): k for k, v in dim.items()}
        _, dc = _rows(GOLD / "depth_chart_pregame.csv")
        in_dc = {r["player_id"] for r in dc}
        for r in legs:
            if r.get("status") in ("SETTLED_WIN", "SETTLED_LOSS", "PUSH_VOID", "WON", "LOST"):
                continue
            nm = r["player_name"]
            if " @ " in nm or nm.upper() == "TOTAL" or "win" in nm.lower() or (r.get("game_date") or "9") < today:
                continue                                  # game-level legs and past games have no player page
            out["openLegs"] += 1
            pid = by_name.get(data.normalize_name(r["player_name"]))
            if not pid:
                out["noPlayerPage"].append(r["player_name"])
            else:
                if not data.photo_url(pid):
                    out["noPhoto"].append(r["player_name"])
                if pid not in in_dc and dim[pid].get("position", "QB") in SKILL:
                    out["noPlayerPage"].append(r["player_name"] + " (no depth chart)")
    except Exception as e:      # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


STEPS = (("schedule", sync_schedule), ("player_weeks", sync_player_weeks), ("depth_charts", sync_depth_charts),
         ("injuries", sync_injuries), ("headshots", sync_headshots))


def run(force: bool = False) -> dict:
    """Run every step, roll the week, clear caches. Safe to call repeatedly and from several threads."""
    with _LOCK:
        st = _state()
        notes, errors = {}, {}
        for key, fn in STEPS:
            try:
                notes[key] = fn(st, force)
            except Exception as e:      # noqa: BLE001
                errors[key] = f"{type(e).__name__}: {e}"
        wk = current_week()
        prev = st.get("week") or {}
        rolled = (prev.get("season"), prev.get("week")) != (wk["season"], wk["week"])
        try:
            clear_caches()
        except Exception as e:          # noqa: BLE001
            errors["caches"] = str(e)
        st.update(week=wk, notes=notes, errors=errors, at=time.time(), rolled=rolled, integrity=integrity())
        _save_state(st)
        return {"ok": not errors, "week": wk, "rolled": rolled, "notes": notes, "errors": errors, "integrity": st["integrity"]}


def status() -> dict:
    return _state()


def agent() -> str:
    r = run()
    changed = [v for v in r["notes"].values() if "unchanged" not in v and "(kept)" not in v]
    bad = f"; ERRORS: {', '.join(r['errors'])}" if r["errors"] else ""
    wk = r["week"]
    return f"week {wk['week']} ({wk['season']}){' · NEW WEEK' if r['rolled'] else ''}; " + (" | ".join(changed) if changed else "all sources current") + bad

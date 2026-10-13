"""
MY BOO's REPORT DESK -- the repeat job that makes every report happen, every week, for every game we bet.

No LLM anywhere in here. Each cycle (run by the staff scheduler, boo_staff "report_desk") this is plain code:

  1. void any automatic ticket that crossed games on a non-Sunday slate (myboo.void_cross_game_open)
  2. re-check every ticket grade against the ESPN final (slip_alerts.audit_recent)
  3. catalog the games: every game with MY BOO tickets, plus the next primetime game
  4. for each FINAL game with tickets: build the full post-game report (boo_postgame.report: leg grades, contagion hero,
     killers, what-ifs, structure lab, JEV vs BPL, grail slip, win/loss tally, blueprint) and file it
  5. for each upcoming game: file the pre-game plan (blueprint, template watch, TD policy, tickets placed so far)
  6. back the archive up through boo_store so a Space restart loses nothing

The archive is lake/gold/nfl/myboo_reports.json. The page reads the catalog (right panel) and one report (middle).
The newest FINAL report is the "current" one in the middle; the next game takes over when it goes final, and the
older ones stay in the right panel.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import threading
import time
from collections import defaultdict
from pathlib import Path

import data
import myboo

_FILE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "myboo_reports.json"
_LOCK = threading.Lock()
_ALIAS = {"LAR": "LA", "LA": "LAR"}
DAY = {"Thursday": "THUR NIGHT", "Monday": "MONDAY NIGHT", "Friday": "FRIDAY NIGHT", "Saturday": "SATURDAY"}


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text())
    except (OSError, ValueError):
        return {"reports": {}, "updated": None}


def _save(obj: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, default=str))
    tmp.replace(_FILE)


def _label(g: dict) -> str:
    wd = g.get("weekday", "")
    base = DAY.get(wd)
    if not base:
        late = (g.get("gametime") or "00:00") >= "19:00"
        base = "SUNDAY NIGHT" if wd == "Sunday" and late else f"SUNDAY · {g['away_team']} @ {g['home_team']}" if wd == "Sunday" else wd.upper()
    return f"{base} [WEEK {g['week']}]"


def _is_primetime(g: dict) -> bool:
    return g.get("weekday") in ("Thursday", "Monday", "Friday") or (g.get("weekday") == "Sunday" and (g.get("gametime") or "00:00") >= "19:00")


def _status(g: dict, scores: list[dict]) -> str:
    a, h = g["away_team"], g["home_team"]
    for s in scores:
        if {s.get("away"), _ALIAS.get(s.get("away"))} & {a} and {s.get("home"), _ALIAS.get(s.get("home"))} & {h}:
            st = s.get("status")
            return "FINAL" if st == "FINAL" else "LIVE" if st in ("LIVE", "OT", "HALFTIME") else "UPCOMING"
    d = g.get("gameday") or ""
    return "FINAL" if d and d < dt.date.today().isoformat() else "UPCOMING"


def catalog() -> list[dict]:
    """Every game with MY BOO tickets, plus the next primetime game. Oldest first (the right panel reads top to bottom)."""
    with open(myboo._TICKETS_FILE, newline="") as f:
        tickets = {t["ticket_id"]: t for t in csv.DictReader(f)}
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = list(csv.DictReader(f))
    by_game: dict[str, set] = defaultdict(set)
    for l in legs:
        if l.get("game_id") and tickets.get(l["ticket_id"], {}).get("status") != "PUSH_VOID":
            by_game[l["game_id"]].add(l["ticket_id"])
    sched = [g for g in data.load("schedule") if g.get("season") == "2026" and g.get("game_type") == "REG"]
    by_id = {g["game_id"]: g for g in sched}
    try:
        import espn
        scores = espn.get_scoreboard()
    except Exception:
        scores = []
    ids = {gid for gid, t in by_game.items() if len(t) >= 3 and gid in by_id}
    # the next primetime game (a plan, before any bet is placed)
    upcoming = [g for g in sched if _is_primetime(g) and _status(g, scores) != "FINAL"]
    if upcoming:
        nxt = min(upcoming, key=lambda g: (int(g["week"]), g.get("gameday") or "", g.get("gametime") or ""))
        ids.add(nxt["game_id"])
    out = []
    for gid in ids:
        g = by_id[gid]
        out.append({"gameId": gid, "label": _label(g), "week": int(g["week"]), "weekday": g.get("weekday"), "date": g.get("gameday"),
                    "away": g["away_team"], "home": g["home_team"], "status": _status(g, scores), "tickets": len(by_game.get(gid, ())),
                    "kickoff": g.get("gametime")})
    out.sort(key=lambda x: (x["date"] or "", x["kickoff"] or ""))
    finals = [x for x in out if x["status"] == "FINAL" and x["tickets"] >= 3]
    current = finals[-1]["gameId"] if finals else None
    for x in out:
        x["current"] = x["gameId"] == current
    return out


def _pregame(entry: dict) -> dict:
    import boo_grail
    import boo_postgame
    prev = next((c for c in reversed(catalog()) if c["status"] == "FINAL" and c["tickets"] >= 3), None)
    blueprint = None
    if prev:
        try:
            night = boo_postgame.night(prev["gameId"])
            blueprint = boo_postgame.blueprint(night, boo_postgame.structure_lab())
        except Exception:
            blueprint = None
    return {"ok": True, "mode": "PREGAME", "entry": entry, "blueprint": blueprint, "template": boo_grail.template(entry["week"]),
            "tally": boo_grail.tally(), "tdPolicy": boo_grail.td_policy(), "placed": entry["tickets"]}


def report(game_id: str | None = None) -> dict:
    """One report for the middle panel. FINAL games get the full post-game report; others get the pre-game plan."""
    cat = catalog()
    if not game_id:
        cur = next((c for c in cat if c["current"]), None) or (cat[-1] if cat else None)
        game_id = cur["gameId"] if cur else None
    entry = next((c for c in cat if c["gameId"] == game_id), None)
    if not entry:
        return {"ok": False, "error": "No report for that game."}
    if entry["status"] == "FINAL" and entry["tickets"] >= 3:
        import boo_postgame
        try:
            r = boo_postgame.report(game_id)
        except Exception:
            r = (_load()["reports"].get(game_id) or {}).get("report")      # fall back to the filed copy
        if r:
            return {**r, "mode": "FINAL", "entry": entry}
        return {"ok": False, "error": "The report could not be built yet."}
    return _pregame(entry)


def run() -> str:
    """The repeat job. Deterministic: same ledger in, same reports out."""
    notes = []
    try:
        voided = myboo.void_cross_game_open()
        if voided:
            notes.append(f"voided {len(voided)} cross-game tickets")
    except Exception as exc:
        notes.append(f"void failed: {type(exc).__name__}")
    try:
        import slip_alerts
        a = slip_alerts.audit_recent()
        if a["changed"]:
            notes.append(f"corrected {len(a['changed'])} leg grades")
    except Exception as exc:
        notes.append(f"audit failed: {type(exc).__name__}")
    cat = catalog()
    filed = changed = 0
    with _LOCK:
        db = _load()
    for entry in cat:
        gid = entry["gameId"]
        try:
            r = report(gid)
        except Exception:
            continue
        if not r.get("ok"):
            continue
        sig = json.dumps(r.get("night", {}).get("tickets", {}).get("distinct")) + json.dumps(r.get("night", {}).get("tickets", {}).get("won")) if r.get("mode") == "FINAL" else entry["status"]
        old = db["reports"].get(gid)
        if not old or old.get("sig") != sig or r.get("mode") != old.get("mode"):
            db["reports"][gid] = {"mode": r.get("mode"), "label": entry["label"], "sig": sig, "filedAt": time.time(), "report": r}
            changed += 1
        filed += 1
    db["catalog"] = cat
    db["updated"] = dt.datetime.now().strftime("%a %-I:%M %p")
    with _LOCK:
        _save(db)
    if changed:
        try:
            import boo_store
            boo_store.push(force=True)
        except Exception:
            pass
    return f"{filed} reports checked, {changed} filed or refreshed" + (f"; {'; '.join(notes)}" if notes else "")

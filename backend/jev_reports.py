"""
MY BOO's STATS REPORTER -- the staff agent that grades JEV and writes the post-game stats report.

Every run (fast while games are live, slow otherwise) it:
  1. settles the JEV ledger against ESPN finals (jev_ledger.settle)
  2. writes one stats report per game that just went final: how JEV and the Big Proppa Line did on every
     read for that game, the profit-zone (85%+) calls, the best calls and the worst misses
  3. refreshes the running scorecard (Brier scores, calibration, live blend weight)
  4. backs everything up through her store (boo_store), so a Space restart never loses a report

Reports live in lake/gold/nfl/myboo_jev_reports.json beside her other records. Served at /api/boo/stats-report
and summarized in the director's briefing.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import jev_ledger

_FILE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl" / "myboo_jev_reports.json"
_CT = ZoneInfo("America/Chicago")
_LOCK = threading.Lock()
MAX_REPORTS = 60
MARKET_WORD = {"rushyds": "rushing yds", "recyds": "receiving yds", "recs": "receptions", "passyds": "passing yds"}


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text())
    except (OSError, ValueError):
        return {"reports": []}


def _save(obj: dict) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(_FILE)


def _label(r: dict) -> str:
    k = r["kind"]
    if k == "prop":
        return f"{r['name']} {MARKET_WORD.get(r.get('market'), r.get('market', ''))} over {r['line']:g}"
    if k == "total":
        return f"{r['name']} total over {r['line']:g}"
    if k == "spread":
        return f"{r['name']} {r['line']:+g}"
    return f"{r['name']} moneyline"


def _actual(r: dict) -> str:
    a = r.get("actual")
    if a is None:
        return ""
    if r["kind"] == "prop":
        return f"finished {a:g}"
    if r["kind"] == "total":
        return f"went {a:g}"
    return f"margin {a:+g}"


def _right(p: float, hit: int) -> bool:
    return (p >= 0.5) == bool(hit)


def build_game_report(espn_id: str) -> dict | None:
    import h2h
    rows = [r for r in jev_ledger.rows_for_game(espn_id) if not r.get("void") and r.get("jevP") is not None and r.get("bplP") is not None]
    if not rows:
        return None
    lg = h2h.live_game(espn_id)
    away, home = lg.get("away", ""), lg.get("home", "")
    jev_ok = sum(_right(r["jevP"], r["hit"]) for r in rows)
    bpl_ok = sum(_right(r["bplP"], r["hit"]) for r in rows)
    blend = [r for r in rows if r.get("blendP") is not None]
    blend_ok = sum(_right(r["blendP"], r["hit"]) for r in blend)
    zone = [r for r in rows if max(r["jevP"], 1 - r["jevP"]) >= 0.85]
    zone_ok = sum(_right(r["jevP"], r["hit"]) for r in zone)

    def item(r: dict) -> dict:
        return {"read": _label(r), "jevP": r["jevP"], "bplP": r["bplP"], "result": _actual(r), "hit": bool(r["hit"])}

    right = sorted((r for r in rows if _right(r["jevP"], r["hit"])), key=lambda r: -abs(r["jevP"] - 0.5))[:3]
    wrong = sorted((r for r in rows if not _right(r["jevP"], r["hit"])), key=lambda r: -abs(r["jevP"] - 0.5))[:3]
    by_kind = {}
    for kind, name in (("prop", "props"), ("total", "totals"), ("spread", "spreads"), ("ml", "moneylines")):
        k = [r for r in rows if r["kind"] == kind]
        if k:
            by_kind[name] = {"reads": len(k), "jevRight": sum(_right(r["jevP"], r["hit"]) for r in k), "bplRight": sum(_right(r["bplP"], r["hit"]) for r in k)}
    edge = jev_ok - bpl_ok
    verdict = ("JEV beat the Big Proppa Line" if edge > 0 else "Big Proppa Line beat JEV" if edge < 0 else "JEV and the Big Proppa Line tied") + (f" by {abs(edge)} read{'s' if abs(edge) != 1 else ''}." if edge else ".")
    final = f"{away} {lg.get('awayScore', 0)} - {lg.get('homeScore', 0)} {home}" if away else espn_id
    zone_txt = f" Profit zone (85%+): {zone_ok} of {len(zone)} hit." if zone else " No read reached the 85% profit zone."
    headline = f"{final} final: JEV {jev_ok}-{len(rows) - jev_ok}, Big Proppa Line {bpl_ok}-{len(rows) - bpl_ok} on {len(rows)} graded reads. {verdict}{zone_txt}"
    return {"espnId": espn_id, "game": f"{away} @ {home}", "final": final, "at": datetime.now(_CT).strftime("%a %b %-d, %-I:%M %p CT"),
            "ts": datetime.now(_CT).timestamp(), "graded": len(rows), "jevRight": jev_ok, "bplRight": bpl_ok,
            "blendRight": blend_ok if blend else None, "profitZone": {"calls": len(zone), "hit": zone_ok}, "byKind": by_kind,
            "bestCalls": [item(r) for r in right], "worstMisses": [item(r) for r in wrong], "headline": headline}


def run() -> str:
    """The staff agent: grade, report on any game that just went final, refresh the scorecard, back it up."""
    graded = jev_ledger.settle()
    changed = False
    with _LOCK:
        db = _load()
        have = {r["espnId"] for r in db["reports"]}
        for gid in jev_ledger.pop_newly_settled():
            if gid in have:
                continue
            rep = build_game_report(gid)
            if rep:
                db["reports"].append(rep)
                changed = True
        db["reports"] = db["reports"][-MAX_REPORTS:]
        rep = jev_ledger.report()
        db["scorecard"] = rep
        db["updated"] = datetime.now(_CT).strftime("%a %-I:%M %p CT")
        _save(db)
    if changed:
        try:
            import boo_store
            boo_store.push(force=True)
        except Exception:
            pass
    if changed:
        return f"graded {graded} reads, new stats report: {db['reports'][-1]['game']}"
    return f"{rep['open']} reads waiting on finals, {rep['settled']} graded, {len(db['reports'])} reports filed"


def latest(limit: int = 10) -> dict:
    with _LOCK:
        db = _load()
    reps = list(reversed(db.get("reports", [])))[:limit]
    return {"owner": "MY BOO", "agent": "Stats Reporter", "updated": db.get("updated"), "latest": reps[0] if reps else None, "reports": reps,
            "scorecard": db.get("scorecard") or jev_ledger.report(),
            "note": "Grades every JEV read against the ESPN final. The first report posts after tonight's final." if not reps else None}


def headline() -> str | None:
    reps = _load().get("reports", [])
    return reps[-1]["headline"] if reps else None

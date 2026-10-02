"""
MY BOO slip alerts -- tells her the moment a slip is READY TO BE RECORDED.

A slip does not always wait for the final whistle:

  * an OVER leg is locked as a HIT the instant the stat passes the line (counting
    stats never go backwards), so a slip made of overs can cash in the first half
  * an UNDER leg is locked as a MISS the instant the stat reaches the line, but it
    can only cash at game final
  * one locked MISS kills the whole slip on the spot -- no reason to wait for Q4
  * moneylines, kicking points and anything the live feed cannot see wait for the final

Events (each fires once, deduped on disk):
  READY_WON / READY_LOST  the slip is decided -- EARLY (game still on) or FINAL
  HALFTIME                one summary per game: who is cashed, dead or alive
  OVERTIME                regulation ended level; names the slips riding on it
  GAME_FINAL              end of the 4th (or OT): final score and slips recorded

When a slip is ready, the grades are written to the MY BOO ledger (unless
MYBOO_AUTO_RECORD=0) and the 3-part recap is generated from the live box score, so
the report is done by the time she looks at it. Delivery is an in-app feed
(/api/myboo/alerts) that the UI polls, plus a background worker that polls the live
source every minute on game days.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import data
import myboo
import slip_recap
import tank01

_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
_ALERTS_FILE = _GOLD / "myboo_alerts.json"
_CT = ZoneInfo("America/Chicago")          # New Orleans
_LOCK = threading.RLock()
POLL_SECONDS = 60

COUNT_STATS = {"rushyds": "rushyds", "recyds": "recyds", "recs": "recs", "passyds": "passyds",
               "passtd": "passtd", "carries": "carries", "kickpts": "kickpts"}


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _now_ct() -> str:
    return datetime.now(_CT).strftime("%a %-I:%M %p CT")


# ---------------------------------------------------------------------------
# live game normalization
# ---------------------------------------------------------------------------

def _period(raw) -> int:
    s = str(raw or "").upper()
    if "OT" in s:
        return 5
    digits = "".join(c for c in s if c.isdigit())
    return int(digits) if digits else 0


def from_tank01(body: dict, lake_game: dict) -> dict:
    """Normalize a Tank01 box score into the shape the engine reads."""
    status_raw = str(body.get("gameStatus", "")).lower()
    period_raw = str(body.get("currentPeriod", ""))
    period = _period(period_raw)
    if "complete" in status_raw or "final" in status_raw:
        status = "FINAL"
    elif "sched" in status_raw or "not" in status_raw or (not period_raw and not status_raw):
        status = "PRE"
    elif "half" in period_raw.lower() or "half" in status_raw:
        status, period = "HALFTIME", 2
    else:
        status = "LIVE"
    players: dict[tuple[str, str], dict] = {}
    by_tank_id: dict[str, tuple[str, str]] = {}
    for tid, p in (body.get("playerStats") or {}).items():
        if not isinstance(p, dict):
            continue
        key = (data.normalize_name(p.get("longName", "")), p.get("team", ""))
        by_tank_id[str(tid)] = key
        rush, rec, pas, kick = p.get("Rushing") or {}, p.get("Receiving") or {}, p.get("Passing") or {}, p.get("Kicking") or {}
        players[key] = {
            "rushyds": _f(rush.get("rushYds")), "carries": _f(rush.get("carries")), "rushtd": _f(rush.get("rushTD")),
            "recyds": _f(rec.get("recYds")), "recs": _f(rec.get("receptions")), "tgt": _f(rec.get("targets")),
            "rectd": _f(rec.get("recTD")), "passyds": _f(pas.get("passYds")), "passtd": _f(pas.get("passTD")),
            "att": _f(pas.get("passAttempts")), "kickpts": _f(kick.get("kickingPts")),
        }
    first_td = None
    for sp in body.get("scoringPlays") or []:          # first touchdown of the game, if the feed names the scorer
        if "TD" in str(sp.get("scoreType", "")).upper():
            ids = sp.get("playerIDs") or []
            first_td = by_tank_id.get(str(ids[0])) if ids else None
            break
    return {"game_id": lake_game["game_id"], "status": status, "period": period, "clock": str(body.get("gameClock", "")),
            "home": lake_game["home_team"], "away": lake_game["away_team"],
            "home_pts": _f(body.get("homePts")), "away_pts": _f(body.get("awayPts")),
            "players": players, "first_td": first_td}


def tank01_source(lake_game: dict) -> dict | None:
    gid = f"{lake_game['game_date'].replace('-', '')}_{lake_game['away_team']}@{lake_game['home_team']}"
    body = tank01.get_live_boxscore(gid)
    return from_tank01(body, lake_game) if body else None


# ---------------------------------------------------------------------------
# leg + slip evaluation
# ---------------------------------------------------------------------------

def _moment(live: dict) -> str:
    if live["status"] == "FINAL":
        return "FINAL"
    if live["status"] == "HALFTIME":
        return "HALFTIME"
    q = f"OT" if live["period"] >= 5 else f"Q{live['period']}"
    return f"{q} {live['clock']}".strip()


def eval_leg(leg: dict, live: dict) -> dict:
    """-> {state: HIT|MISS|ALIVE, actual, note}. HIT/MISS are locked -- they cannot change again."""
    mk, d = leg["market"], leg.get("direction") or "over"
    line = _f(leg.get("line"), 0.5)
    final = live["status"] == "FINAL"
    me = (data.normalize_name(leg["player_name"]), leg["team"])
    p = live["players"].get(me, {})

    def counting(actual: float) -> dict:
        if d == "over":
            if actual > line:
                return {"state": "HIT", "actual": actual, "note": "over line locked"}
            return {"state": "MISS" if final else "ALIVE", "actual": actual, "note": "finished short" if final else "still needs more"}
        if actual >= line:
            return {"state": "MISS", "actual": actual, "note": "went over the under -- locked miss"}
        return {"state": "HIT" if final else "ALIVE", "actual": actual, "note": "under holds at the final" if final else "under still holding"}

    if mk in COUNT_STATS:
        return counting(p.get(COUNT_STATS[mk], 0.0))
    if mk == "anytd":
        return counting(p.get("rushtd", 0.0) + p.get("rectd", 0.0))
    if mk == "firsttd":
        if live.get("first_td"):
            return {"state": "HIT" if live["first_td"] == me else "MISS", "actual": 1.0 if live["first_td"] == me else 0.0, "note": "first TD is in the books"}
        return {"state": "ALIVE", "actual": 0.0, "note": "waiting on the first touchdown"}
    if mk == "nfl_total":
        return counting(live["home_pts"] + live["away_pts"])
    if mk == "nfl_spread":
        if not final:
            return {"state": "ALIVE", "actual": None, "note": "the spread is decided at the final"}
        mine, theirs = (live["home_pts"], live["away_pts"]) if leg["team"] == live["home"] else (live["away_pts"], live["home_pts"])
        cover = mine - theirs + line
        if cover == 0:
            return {"state": "HIT", "actual": mine - theirs, "note": "push -- FanDuel voids the leg, so it cannot lose the slip"}
        return {"state": "HIT" if cover > 0 else "MISS", "actual": mine - theirs, "note": "final margin against the spread"}
    if mk == "nfl_ml":
        if not final:
            return {"state": "ALIVE", "actual": None, "note": "moneyline is decided at the final"}
        mine, theirs = (live["home_pts"], live["away_pts"]) if leg["team"] == live["home"] else (live["away_pts"], live["home_pts"])
        return {"state": "HIT" if mine > theirs else "MISS", "actual": mine - theirs, "note": "final margin"}
    return {"state": "ALIVE", "actual": None, "note": "not visible in the live feed -- the lake grader will settle it"}


def eval_slip(legs: list[dict], lives: dict[str, dict]) -> dict:
    """Roll the legs up. ready = the slip is decided; when = EARLY (a game is still on) or FINAL."""
    results = []
    for l in legs:
        if l["status"] in ("HIT", "MISS"):
            results.append({"state": l["status"], "actual": _f(l.get("actual_value"), None), "note": "already recorded", "leg": l})
            continue
        live = lives.get(l["game_id"])
        r = eval_leg(l, live) if live else {"state": "ALIVE", "actual": None, "note": "game not live yet"}
        results.append({**r, "leg": l})
    miss = [r for r in results if r["state"] == "MISS"]
    alive = [r for r in results if r["state"] == "ALIVE"]
    decided_games = {r["leg"]["game_id"] for r in results if r["state"] in ("HIT", "MISS")}
    still_on = any(lives.get(g) and lives[g]["status"] != "FINAL" for g in {r["leg"]["game_id"] for r in results})
    if miss:
        out = "LOST"
    elif not alive:
        out = "WON"
    else:
        out = "ALIVE"
    return {"outcome": out, "ready": out != "ALIVE", "when": "EARLY" if still_on else "FINAL", "legs": results,
            "locked_hits": sum(r["state"] == "HIT" for r in results), "alive": len(alive), "dead": len(miss),
            "games": decided_games}


# ---------------------------------------------------------------------------
# alert store
# ---------------------------------------------------------------------------

def _load() -> dict:
    try:
        return json.loads(_ALERTS_FILE.read_text())
    except (OSError, ValueError):
        return {"seq": 0, "alerts": [], "fired": {}}


def _save(store: dict) -> None:
    store["alerts"] = store["alerts"][-300:]
    tmp = _ALERTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=1))
    tmp.replace(_ALERTS_FILE)


def _fire(store: dict, key: str, kind: str, title: str, body: str, **extra) -> dict | None:
    if key in store["fired"]:
        return None
    store["seq"] += 1
    a = {"id": store["seq"], "kind": kind, "title": title, "body": body, "at": _now_ct(),
         "ts": time.time(), **extra}
    store["alerts"].append(a)
    store["fired"][key] = a["id"]
    return a


def alerts_since(seq: int = 0) -> dict:
    with _LOCK:
        s = _load()
        return {"latest": s["seq"], "alerts": [a for a in s["alerts"] if a["id"] > seq][::-1]}


# ---------------------------------------------------------------------------
# recording + report
# ---------------------------------------------------------------------------

def _overlay(lives: dict[str, dict], week: int) -> dict:
    """Live box score -> the same team/player tables the recap reads from the lake."""
    ids = slip_recap._pid_lookup()
    tg: dict = {}
    pw: dict = {}
    final = None
    for live in lives.values():
        for team, opp in ((live["home"], live["away"]), (live["away"], live["home"])):
            tg[(week, team)] = {"opp": opp, "game_id": live["game_id"], "att": 0.0, "car": 0.0, "tgt": 0.0, "pyds": 0.0, "ryds": 0.0}
        for (name, team), s in live["players"].items():
            row = tg.get((week, team))
            if row:
                row["att"] += s["att"]; row["car"] += s["carries"]; row["tgt"] += s["tgt"]
                row["pyds"] += s["passyds"]; row["ryds"] += s["rushyds"]
            pid = ids.get((name, team)) or ids.get((name, ""))
            if pid:
                pw[(pid, week)] = {"att": s["att"], "car": s["carries"], "tgt": s["tgt"], "rec": s["recs"],
                                   "pyds": s["passyds"], "ryds": s["rushyds"], "recyds": s["recyds"],
                                   "td": s["rushtd"] + s["rectd"], "team": team}
        if live["status"] == "FINAL":
            final = {"away_team": live["away"], "home_team": live["home"],
                     "away_score": int(live["away_pts"]), "home_score": int(live["home_pts"]), "home_score_": 1}
    on = next((l for l in lives.values() if l["status"] != "FINAL"), None)
    return {"tg": tg, "pw": pw, "final": final, "partial": _moment(on) if on else None}


def record_ticket(ticket_id: str, ev: dict, lives: dict[str, dict]) -> dict:
    """Write the locked grades to the ledger, settle the ticket, then build + store the recap."""
    now = datetime.now().astimezone().isoformat()
    with myboo._LOCK:
        myboo._ensure_files()
        with open(myboo._LEGS_FILE, newline="") as f:
            legs = list(csv.DictReader(f))
        with open(myboo._TICKETS_FILE, newline="") as f:
            tickets = list(csv.DictReader(f))
        by_id = {r["leg"]["leg_id"]: r for r in ev["legs"]}
        for l in legs:
            r = by_id.get(l["leg_id"])
            if r and l["status"] == "PENDING" and r["state"] in ("HIT", "MISS"):
                l["status"], l["graded_at"] = r["state"], now
                l["actual_value"] = "" if r["actual"] is None else r["actual"]
        mine = [l for l in legs if l["ticket_id"] == ticket_id]
        t = next(x for x in tickets if x["ticket_id"] == ticket_id)
        if t["status"] not in ("SETTLED_WIN", "SETTLED_LOSS"):
            if any(x["status"] == "MISS" for x in mine):
                t["status"], t["result_units"], t["settled_at"] = "SETTLED_LOSS", "0", now
            elif all(x["status"] == "HIT" for x in mine):
                t["status"], t["settled_at"] = "SETTLED_WIN", now
                t["result_units"] = str(myboo._gross(_f(t["stake_units"], myboo.STAKE), _f(t["payout_odds"])))
        with open(myboo._LEGS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=myboo._LEG_COLS, extrasaction="ignore", restval="")
            w.writeheader(); w.writerows(legs)
        with open(myboo._TICKETS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=myboo._TICKET_COLS)
            w.writeheader(); w.writerows(tickets)
    # the report: built from the live box score, stored as the training record
    snap_store = slip_recap._load_json(slip_recap._THESIS_FILE)
    week = int(t["week"])
    rc = slip_recap.build_recap(t, mine, snap_store.get(ticket_id), overlay=_overlay(lives, week))
    if rc["stage"] == "FINAL":
        saved = slip_recap._load_json(slip_recap._RECAPS_FILE)
        saved[ticket_id] = rc
        slip_recap._save_json(slip_recap._RECAPS_FILE, saved)
    return {"status": t["status"], "recap_words": rc["word_count"], "verdict": (rc.get("hindsight") or {}).get("label")}


def rebuild_recaps(game_id: str, source: Callable[[dict], dict | None] = tank01_source) -> int:
    """Rewrite every settled recap on one game from its frozen thesis (used after the recap logic changes)."""
    g = next((r for r in slip_recap._rows("schedule") if r["game_id"] == game_id), None)
    live = source(g) if g else None
    if not live:
        return 0
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = [l for l in csv.DictReader(f) if l["game_id"] == game_id]
    by_t: dict[str, list[dict]] = {}
    for l in legs:
        by_t.setdefault(l["ticket_id"], []).append(l)
    snaps = slip_recap._load_json(slip_recap._THESIS_FILE)
    saved = slip_recap._load_json(slip_recap._RECAPS_FILE)
    n = 0
    for t in myboo.load_tickets_raw():
        if t["ticket_id"] in by_t and t["status"] in ("SETTLED_WIN", "SETTLED_LOSS"):
            rc = slip_recap.build_recap(t, by_t[t["ticket_id"]], snaps.get(t["ticket_id"]),
                                        overlay=_overlay({game_id: live}, int(t["week"])))
            if rc["stage"] == "FINAL":
                saved[t["ticket_id"]] = rc
                n += 1
    slip_recap._save_json(slip_recap._RECAPS_FILE, saved)
    return n


def _refresh_partials(lives: dict[str, dict]) -> int:
    """Rewrite early-record recaps from the full stat line once every game on the slip is final."""
    saved = slip_recap._load_json(slip_recap._RECAPS_FILE)
    todo = [tid for tid, r in saved.items() if r.get("partial")]
    if not todo:
        return 0
    tickets = {t["ticket_id"]: t for t in myboo.load_tickets_raw()}
    with open(myboo._LEGS_FILE, newline="") as f:
        legs = list(csv.DictReader(f))
    snaps = slip_recap._load_json(slip_recap._THESIS_FILE)
    n = 0
    for tid in todo:
        mine = [l for l in legs if l["ticket_id"] == tid]
        games = {l["game_id"] for l in mine}
        if not mine or not all(lives.get(g) and lives[g]["status"] == "FINAL" for g in games):
            continue
        rc = slip_recap.build_recap(tickets[tid], mine, snaps.get(tid), overlay=_overlay(lives, int(tickets[tid]["week"])))
        if rc["stage"] == "FINAL" and not rc.get("partial"):
            saved[tid] = rc
            n += 1
    if n:
        slip_recap._save_json(slip_recap._RECAPS_FILE, saved)
    return n


# ---------------------------------------------------------------------------
# the poll
# ---------------------------------------------------------------------------

def _slip_title(name: str) -> str:
    return name.split(" · ")[0]


def poll(source: Callable[[dict], dict | None] = tank01_source, auto_record: bool | None = None) -> list[dict]:
    """One pass: read every live game with open slips, fire whatever just became true. Returns new alerts."""
    if auto_record is None:
        auto_record = os.environ.get("MYBOO_AUTO_RECORD", "1") != "0"
    new: list[dict] = []
    with _LOCK:
        store = _load()
        tickets = [t for t in myboo.load_tickets_raw() if t["status"] in ("OPEN", "IN_PROGRESS")]
        if not tickets and not any(r.get("partial") for r in slip_recap._load_json(slip_recap._RECAPS_FILE).values()):
            return []
        with open(myboo._LEGS_FILE, newline="") as f:
            all_legs = list(csv.DictReader(f))
        by_t: dict[str, list[dict]] = {}
        for l in all_legs:
            by_t.setdefault(l["ticket_id"], []).append(l)
        sched = {g["game_id"]: g for g in slip_recap._rows("schedule")}
        game_ids = {l["game_id"] for t in tickets for l in by_t.get(t["ticket_id"], []) if l["game_id"]}
        game_ids |= {l["game_id"] for l in all_legs if l["game_id"] and l["ticket_id"] in
                     {tid for tid, r in slip_recap._load_json(slip_recap._RECAPS_FILE).items() if r.get("partial")}}
        lives: dict[str, dict] = {}
        for gid in game_ids:
            g = sched.get(gid)
            live = source(g) if g else None
            if live and live["status"] != "PRE":
                lives[gid] = live

        for gid, live in lives.items():
            score = f"{live['away']} {int(live['away_pts'])}, {live['home']} {int(live['home_pts'])}"
            riding = [t for t in tickets if any(l["game_id"] == gid for l in by_t.get(t["ticket_id"], []))]
            if live["status"] == "HALFTIME":
                lines = []
                for t in riding:
                    ev = eval_slip(by_t[t["ticket_id"]], lives)
                    tag = "CASHED" if ev["outcome"] == "WON" else "DEAD" if ev["outcome"] == "LOST" else f"{ev['locked_hits']} locked, {ev['alive']} alive"
                    lines.append(f"{_slip_title(t['name'])}: {tag}")
                a = _fire(store, f"HALFTIME:{gid}", "HALFTIME", f"Halftime — {score}",
                          f"{len(riding)} slips riding. " + "; ".join(lines[:12]) + ("…" if len(lines) > 12 else ""), game=gid)
                if a: new.append(a)
            if live["period"] >= 5 and live["status"] == "LIVE":
                names = [_slip_title(t["name"]) for t in riding if eval_slip(by_t[t["ticket_id"]], lives)["outcome"] == "ALIVE"]
                a = _fire(store, f"OT:{gid}", "OVERTIME", f"Overtime — {score}",
                          f"Regulation ended level. {len(names)} slips need the extra period: " + ", ".join(names[:10]), game=gid)
                if a: new.append(a)

        for t in tickets:
            legs = by_t.get(t["ticket_id"], [])
            if not legs:
                continue
            ev = eval_slip(legs, lives)
            if not ev["ready"]:
                continue
            gid = legs[0]["game_id"]
            live = lives.get(gid) or next(iter(lives.values()), None)
            moment = _moment(live) if live else ""
            early = ev["when"] == "EARLY"
            if ev["outcome"] == "WON":
                title = f"CASHED — {_slip_title(t['name'])}"
                body = (f"All {len(legs)} legs are locked at {moment}" + (" — the game is still on, this one is done early." if early else ".")
                        + f" Stake ${_f(t['stake_units'], myboo.STAKE):g} at +{t['payout_odds']}: ready to record.")
                severity = "win"
            else:
                dead = next(r for r in ev["legs"] if r["state"] == "MISS")
                title = f"DEAD — {_slip_title(t['name'])}"
                body = (f"{dead['leg']['player_name']} ({dead['note']}) at {moment}"
                        + (" — no reason to wait, the slip cannot recover." if early else ".") + " Ready to record.")
                severity = "loss"
            info = {}
            if auto_record:
                try:
                    info = record_ticket(t["ticket_id"], ev, lives)
                    body += f" Recorded; MY BOO's recap is written ({info['recap_words']} words" + (f", verdict {info['verdict']}" if info.get("verdict") else "") + ")."
                except Exception as e:                       # never let a bad box score kill the worker
                    body += f" (Auto-record failed: {type(e).__name__}.)"
            a = _fire(store, f"READY:{t['ticket_id']}", "READY_WON" if ev["outcome"] == "WON" else "READY_LOST", title, body,
                      ticket_id=t["ticket_id"], game=gid, when=ev["when"], moment=moment, severity=severity, recorded=bool(info))
            if a: new.append(a)

        for gid, live in lives.items():
            if live["status"] == "FINAL":
                score = f"{live['away']} {int(live['away_pts'])}, {live['home']} {int(live['home_pts'])}"
                done = sum(1 for t in tickets if any(l["game_id"] == gid for l in by_t.get(t["ticket_id"], [])) and f"READY:{t['ticket_id']}" in store["fired"])
                a = _fire(store, f"FINAL:{gid}", "GAME_FINAL", f"Final — {score}",
                          f"End of the game. {done} slips on this game are ready/recorded; anything the live feed cannot see will settle from the lake once week stats land.", game=gid)
                if a: new.append(a)
        refreshed = _refresh_partials(lives)
        if refreshed:
            a = _fire(store, f"REFRESH:{int(time.time() // 60)}", "RECAP_FINAL", "Recaps rewritten at the final",
                      f"{refreshed} early-lock recap{'s' if refreshed != 1 else ''} rebuilt from the full stat line — science or shit is now decided.")
            if a: new.append(a)
        if new:
            _save(store)
    if new:
        try:
            import boo_store
            threading.Thread(target=boo_store.push, daemon=True).start()   # keep her records off the ephemeral disk
        except Exception:
            pass
    return new


# ---------------------------------------------------------------------------
# background worker
# ---------------------------------------------------------------------------
_worker: threading.Thread | None = None


def start_worker() -> None:
    """Poll once a minute while a Tank01 key is configured. Safe to call more than once."""
    global _worker
    if _worker and _worker.is_alive():
        return

    def run() -> None:
        while True:
            try:
                if tank01.available():
                    poll()
            except Exception:
                pass
            try:
                import boo_training
                boo_training.maybe_run_tuesday()      # Tuesday 6 AM Central: MY BOO trains Jimmy from the week's slips
            except Exception:
                pass
            time.sleep(POLL_SECONDS)

    _worker = threading.Thread(target=run, daemon=True, name="boo-alerts")
    _worker.start()

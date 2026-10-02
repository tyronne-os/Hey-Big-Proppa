"""
MY BOO's staff -- the agents that run the ESPN data stream, with MY BOO as director.

Every agent is a small, single-job function with its own cadence. Cadence adapts: fast while a game is live,
slow on idle days. Each run is timed and its outcome stored (lake/gold/espn/staff_status.json) so the Data Auditor,
the STAFF tab in MY BOO and Hermes can all see who is healthy. A failing agent never stops the others.

Agents:  scoreboard_scout  play_clerk  line_watcher  poll_analyst  portal_scout  sec_reporter
         injury_desk  standings_actuary  data_auditor  director (MY BOO's briefing)  hermes_liaison (manifest export)
The schedule lives in AGENTS below and is documented in docs/UTILITY_ROOM.md.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import espn
import espn_cfb

_DIR = Path(__file__).parent.parent / "lake/gold/espn"
_STATUS = _DIR / "staff_status.json"
_LOCK = threading.RLock()
_CT = ZoneInfo("America/Chicago")
_LIVE = {"nfl": [], "cfb": []}                    # game ids live right now (set by the scoreboard scout)


def _read(name: str, default):
    try:
        return json.loads((_DIR / name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    tmp = (_DIR / name).with_suffix(".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(_DIR / name)


def _spread_num(details: str) -> float | None:
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*$", details or "")
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# agents (each returns a one-line note)
# ---------------------------------------------------------------------------

def scoreboard_scout() -> str:
    nfl = espn.get_scoreboard()
    cfb = espn_cfb.latest(max_age=0)["games"]
    _write("nfl_scoreboard.json", {"at": time.time(), "games": nfl})
    live = lambda gs: [g["game_id"] for g in gs if g["status"] in ("LIVE", "OT", "HALFTIME")]
    _LIVE["nfl"], _LIVE["cfb"] = live(nfl), live(cfb)
    return f"NFL {len(nfl)} games ({len(_LIVE['nfl'])} live, {sum(g['final'] for g in nfl)} final); CFB top25/SEC {len(cfb)} ({len(_LIVE['cfb'])} live)"


def play_clerk() -> str:
    import slip_alerts
    seen = _read("play_seen.json", {})
    events = _read("play_events.json", [])
    fired = 0
    for lg, ids in (("nfl", _LIVE["nfl"]), ("cfb", _LIVE["cfb"])):
        for gid in ids:
            d = espn.game_detail(gid, lg, limit=200)
            if not d:
                continue
            first_pass = gid not in seen                     # first look at a game: mark existing plays seen, do not flood alerts
            known = set(seen.get(gid, []))
            title_game = f"{d['away']['abbr']} @ {d['home']['abbr']}"
            for p in reversed(d["plays"]):                   # oldest first
                if p["id"] in known:
                    continue
                known.add(p["id"])
                if first_pass:
                    continue
                t = p["type"].lower()
                kind = "SCORE" if p["scoring"] else "TURNOVER" if ("interception" in t or "fumble" in t) else "BIG_PLAY" if (p["yards"] or 0) >= 20 and not any(k in t for k in ("penalty", "field goal", "punt", "kickoff")) and "no good" not in p["text"].lower() else None
                if not kind:
                    continue
                ev = {"at": time.time(), "game": gid, "lg": lg, "kind": kind, "text": p["text"][:200], "period": p["period"], "clock": p["clock"], "matchup": title_game}
                events.append(ev)
                with slip_alerts._LOCK:
                    store = slip_alerts._load()
                    a = slip_alerts._fire(store, f"PLAY:{gid}:{p['id']}", kind, f"{kind.replace('_', ' ')} — {title_game}", f"Q{p['period']} {p['clock']}: {p['text'][:180]}", game=gid)
                    if a:
                        slip_alerts._save(store); fired += 1
            seen[gid] = list(known)[-400:]
    _write("play_seen.json", seen)
    _write("play_events.json", events[-300:])
    return f"{sum(len(v) for v in _LIVE.values())} live games watched, {fired} new play alerts"


def line_watcher() -> str:
    hist = _read("line_history.json", {})
    nfl = espn.get_scoreboard()
    cfb = espn_cfb.latest()["games"]
    now, moved, flags = time.time(), [], []
    tr = {}
    try:
        import trusteddataTR
        tr = {(m["away"], m["home"]): m["spread"] for m in trusteddataTR.week_matchups()}
    except Exception:
        pass
    for g in nfl + cfb:
        sp, ou = _spread_num(g["odds_spread"]), g["odds_ou"]
        if sp is None and ou is None:
            continue
        rows = hist.setdefault(g["game_id"], {"matchup": f"{g['away']} @ {g['home']}", "lg": g["lg"], "snaps": []})
        snaps = rows["snaps"]
        if not snaps or snaps[-1]["spread"] != sp or snaps[-1]["ou"] != ou:
            snaps.append({"t": now, "spread": sp, "ou": ou, "details": g["odds_spread"]})
            rows["snaps"] = snaps[-120:]
        first, last = rows["snaps"][0], rows["snaps"][-1]
        if first["spread"] is not None and last["spread"] is not None and abs(last["spread"] - first["spread"]) >= 1.0:
            moved.append({"game": rows["matchup"], "from": first["details"], "to": last["details"], "by": round(last["spread"] - first["spread"], 1)})
        if g["lg"] == "nfl" and (g["away"], g["home"]) in tr and sp is not None:
            fav = re.match(r"\s*([A-Z]+)", g["odds_spread"] or "")
            home_sp = (-abs(sp) if fav and fav.group(1) == g["home"] else abs(sp))
            if abs(home_sp - tr[(g["away"], g["home"])]) >= 1.5:
                flags.append({"game": rows["matchup"], "espn": home_sp, "teamrankings": tr[(g["away"], g["home"])]})
    hist["_summary"] = {"moved": moved, "disagree": flags, "at": now}
    _write("line_history.json", hist)
    return f"{len(hist) - 1} games tracked, {len(moved)} moved 1+ pt, {len(flags)} ESPN-vs-TeamRankings disagreements"


def poll_analyst() -> str:
    polls = espn_cfb.polls()
    prev = _read("polls_prev.json", {})
    changes = []
    for p in polls:
        now_order = [r["team"] for r in p["ranks"]]
        if prev.get(p["name"]) and prev[p["name"]] != now_order:
            changes.append(p["name"])
    _write("polls_prev.json", {p["name"]: [r["team"] for r in p["ranks"]] for p in polls})
    movers = [(r["name"], r["move"]) for p in polls[:1] for r in p["ranks"] if r["move"]]
    movers.sort(key=lambda x: -abs(x[1]))
    _write("poll_movers.json", movers[:6])
    return f"{len(polls)} polls, changed: {', '.join(changes) or 'none'}; biggest AP mover: {movers[0][0] + ' ' + format(movers[0][1], '+d') if movers else 'none'}"


def portal_scout() -> str:
    feeds = espn_cfb.latest()["feeds"]["portal"]
    known = set(_read("portal_seen.json", []))
    new = [a for a in feeds if a["link"] not in known]
    _write("portal_seen.json", list(known | {a["link"] for a in feeds})[-500:])
    _write("cfb_portal.json", feeds)
    return f"{len(feeds)} portal stories, {len(new)} new"


def sec_reporter() -> str:
    snap = espn_cfb.latest()
    sec_games = [g for g in snap["games"] if g["sec"]]
    _write("cfb_sec.json", {"news": snap["feeds"]["sec"], "games": [g["game_id"] for g in sec_games], "matchup_news": snap["feeds"]["matchup"]})
    return f"{len(sec_games)} SEC games, {len(snap['feeds']['sec'])} SEC stories, matchup news on {len(snap['feeds']['matchup'])} games"


def injury_desk() -> str:
    inj = espn.injuries()
    prev = _read("injuries_prev.json", {})
    flat = {f"{t}:{i['player']}": i["status"] for t, rows in inj.items() for i in rows}
    changed = [k for k, v in flat.items() if prev and prev.get(k) != v]
    _write("injuries_prev.json", flat)
    _write("injuries.json", inj)
    return f"{len(flat)} players on reports, {len(changed)} new/changed since last look"


def standings_actuary() -> str:
    st, pw = espn.get_standings(), espn.derive_power_ratings()
    _write("standings.json", {"standings": st, "power": pw, "at": time.time()})
    return f"{len(st)} teams, power ratings for {len(pw)}"


def data_auditor() -> str:
    status = _read("staff_status.json", {})
    bad = []
    for a in AGENTS:
        s = status.get(a["id"])
        limit = a["idle"] * 3 + 120
        if not s:
            continue
        if a["id"] != "data_auditor" and time.time() - s.get("last_ok", 0) > limit and not a.get("live_only"):
            bad.append(f"{a['name']} stale {int((time.time() - s.get('last_ok', 0)) / 60)}m")
        if s.get("errors", 0) >= 3 and s.get("last_error"):
            bad.append(f"{a['name']} erroring: {s['last_error'][:60]}")
    _write("audit.json", {"at": time.time(), "problems": bad})
    return "all agents healthy" if not bad else "; ".join(bad)


def director() -> str:
    """MY BOO's briefing: one paragraph of what the staff found, written from the snapshots."""
    nfl = _read("nfl_scoreboard.json", {}).get("games", [])
    cfb = espn_cfb.latest()
    lines = _read("line_history.json", {}).get("_summary", {})
    bullets = []
    live = [g for g in nfl + cfb["games"] if g["status"] in ("LIVE", "OT", "HALFTIME")]
    if live:
        bullets.append(f"{len(live)} games live right now: " + ", ".join(f"{g['away']} {g['away_score']}-{g['home_score']} {g['home']}" for g in live[:4]))
    fin = [g for g in nfl if g["final"]]
    if fin:
        bullets.append("Final: " + ", ".join(f"{g['away']} {g['away_score']}-{g['home_score']} {g['home']}" for g in fin[:3]))
    ups = [g for g in cfb["games"] if g["upset_alert"]]
    if ups:
        bullets.append("UPSET WATCH: " + ", ".join(f"{g['away']} @ {g['home']}" for g in ups[:3]))
    mv = lines.get("moved", [])
    if mv:
        bullets.append("Biggest line move: " + max(mv, key=lambda m: abs(m["by"]))["game"] + f" ({max(mv, key=lambda m: abs(m['by']))['from']} -> {max(mv, key=lambda m: abs(m['by']))['to']})")
    dis = lines.get("disagree", [])
    if dis:
        bullets.append(f"{len(dis)} games where ESPN and TeamRankings disagree by 1.5+ points: " + ", ".join(d["game"] for d in dis[:3]))
    movers = _read("poll_movers.json", [])
    if movers:
        bullets.append("AP poll mover: " + f"{movers[0][0]} {movers[0][1]:+d}")
    portal = _read("cfb_portal.json", [])
    if portal:
        bullets.append("Portal: " + portal[0]["headline"])
    sec = cfb["feeds"]["sec"]
    if sec:
        bullets.append("SEC: " + sec[0]["headline"])
    prob = _read("audit.json", {}).get("problems", [])
    bullets.append("Staff: " + ("all agents reporting." if not prob else "problems — " + "; ".join(prob)))
    out = {"at": datetime.now(_CT).strftime("%a %-I:%M %p CT"), "ts": time.time(), "bullets": bullets,
           "text": "Director's briefing. " + " ".join(b if b.endswith((".", "!")) else b + "." for b in bullets)}
    _write("boo_briefing.json", out)
    return f"briefing written ({len(bullets)} items)"


def hermes_liaison() -> str:
    """Export the staff as a manifest Hermes agents can read: who does what, how often, and which endpoint serves it."""
    man = {"director": "MY BOO", "updated": time.time(), "api_base": "/api",
           "agents": [{"id": a["id"], "name": a["name"], "duty": a["duty"], "live_every_s": a["live"], "idle_every_s": a["idle"],
                       "reads": a.get("reads", ""), "endpoint": a.get("endpoint", "")} for a in AGENTS],
           "endpoints": {"staff_status": "/api/boo/staff", "briefing": "/api/boo/staff", "manifest": "/api/boo/staff/manifest",
                         "game_detail": "/api/espn/game?id={espn_id}&lg={nfl|cfb}", "college": "/api/cfb/espn", "ticker": "/api/espn/ticker"}}
    _write("hermes_staff.json", man)
    return f"manifest for {len(man['agents'])} agents exported"


# live = seconds between runs while any game is live; idle = otherwise
AGENTS = [
    {"id": "scoreboard_scout", "name": "Scoreboard Scout", "fn": scoreboard_scout, "live": 20, "idle": 600, "duty": "NFL scoreboard + college Top-25/SEC slate; spots live games and finals", "endpoint": "/api/espn/ticker", "reads": "ESPN scoreboard"},
    {"id": "play_clerk", "name": "Play-by-Play Clerk", "fn": play_clerk, "live": 15, "idle": 900, "live_only": True, "duty": "Reads every live game's plays; alerts on scores, turnovers and 20+ yard plays", "endpoint": "/api/espn/game", "reads": "ESPN game summary (drives/plays)"},
    {"id": "line_watcher", "name": "Line Watcher", "fn": line_watcher, "live": 600, "idle": 1800, "duty": "Snapshots spreads/totals, tracks movement, flags ESPN-vs-TeamRankings disagreement", "endpoint": "/api/espn/lines", "reads": "ESPN odds + TeamRankings"},
    {"id": "poll_analyst", "name": "Poll Analyst", "fn": poll_analyst, "live": 1800, "idle": 3600, "duty": "AP + Coaches polls, week-over-week movement, SEC marked", "endpoint": "/api/cfb/espn", "reads": "ESPN rankings"},
    {"id": "portal_scout", "name": "Portal Scout", "fn": portal_scout, "live": 1800, "idle": 3600, "duty": "College transfer-portal news, flags new stories", "endpoint": "/api/cfb/espn", "reads": "ESPN article search"},
    {"id": "sec_reporter", "name": "SEC Beat Reporter", "fn": sec_reporter, "live": 900, "idle": 1800, "duty": "SEC news and matchup news attached to each SEC game", "endpoint": "/api/cfb/espn", "reads": "ESPN news + search"},
    {"id": "injury_desk", "name": "Injury Desk", "fn": injury_desk, "live": 1800, "idle": 3600, "duty": "NFL injury report snapshot and changes", "endpoint": "/api/espn/injuries", "reads": "ESPN game summaries"},
    {"id": "standings_actuary", "name": "Standings Actuary", "fn": standings_actuary, "live": 1800, "idle": 3600, "duty": "Standings and the live ESPN-derived power rating Jimmy falls back on", "endpoint": "/api/espn/standings", "reads": "ESPN standings"},
    {"id": "data_auditor", "name": "Data Auditor", "fn": data_auditor, "live": 300, "idle": 600, "duty": "Checks every agent for staleness and repeated errors", "endpoint": "/api/boo/staff", "reads": "staff_status.json"},
    {"id": "director", "name": "MY BOO — Director", "fn": director, "live": 300, "idle": 3600, "duty": "Writes the briefing from what the staff found", "endpoint": "/api/boo/staff", "reads": "all snapshots"},
    {"id": "hermes_liaison", "name": "Hermes Liaison", "fn": hermes_liaison, "live": 21600, "idle": 21600, "duty": "Exports the staff manifest for Hermes agents", "endpoint": "/api/boo/staff/manifest", "reads": "AGENTS"},
]


def run_agent(a: dict) -> None:
    t0 = time.time()
    with _LOCK:
        status = _read("staff_status.json", {})
    s = status.get(a["id"], {"runs": 0, "errors": 0})
    try:
        note = a["fn"]()
        s.update(last_ok=time.time(), note=note, errors=0, last_error="")
    except Exception as e:
        s.update(errors=s.get("errors", 0) + 1, last_error=f"{type(e).__name__}: {e}", note="failed")
    s.update(last_run=time.time(), ms=int((time.time() - t0) * 1000), runs=s.get("runs", 0) + 1)
    with _LOCK:
        status = _read("staff_status.json", {})
        status[a["id"]] = s
        _write("staff_status.json", status)


def tick() -> None:
    """Run every agent that is due. Cadence is the live interval while any game is live, else the idle interval."""
    live_now = bool(_LIVE["nfl"] or _LIVE["cfb"])
    status = _read("staff_status.json", {})
    for a in AGENTS:
        every = a["live"] if live_now else a["idle"]
        if a.get("live_only") and not live_now:
            continue
        if time.time() - status.get(a["id"], {}).get("last_run", 0) >= every:
            run_agent(a)


def status() -> dict:
    st = _read("staff_status.json", {})
    live_now = bool(_LIVE["nfl"] or _LIVE["cfb"])
    return {"director": "MY BOO", "live_now": live_now, "briefing": _read("boo_briefing.json", {}),
            "agents": [{"id": a["id"], "name": a["name"], "duty": a["duty"], "reads": a.get("reads", ""), "live_every": a["live"], "idle_every": a["idle"],
                        **{k: st.get(a["id"], {}).get(k) for k in ("last_run", "last_ok", "note", "errors", "last_error", "runs", "ms")}} for a in AGENTS],
            "audit": _read("audit.json", {})}


_thread: threading.Thread | None = None


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return

    def loop() -> None:
        while True:
            try:
                tick()
            except Exception:
                pass
            time.sleep(10)

    _thread = threading.Thread(target=loop, daemon=True, name="boo-staff")
    _thread.start()

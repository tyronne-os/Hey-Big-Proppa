"""
TeamRankings / BetIQ lake intake -- replaces the paid Tank01 feed with the public pages.

Public, server-rendered pages only. Nothing here touches a subscription wall. robots.txt asks for a
10 second crawl delay and bars /ajax/, so we wait 10s between requests and never call /ajax/.

Schedule (driven by slip_alerts.start_worker via maybe_run, which catches up after downtime):
  FULL   every Tuesday 1:00 AM CT          entrance + odds + trends, plus the tr_entrance.md snapshot
  DAILY  Mon, Thu, Fri, Sat, Sun 9:00 AM CT  odds only
"""
from __future__ import annotations

import csv
import html
import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

CT = ZoneInfo("America/Chicago")
GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
BRONZE = Path(__file__).parent.parent / "lake/bronze/teamrankings"
RUNS = GOLD / "tr_runs.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
DELAY = 10
_LOCK = threading.RLock()
_last_fetch = 0.0

PAGES = {
    "entrance": "https://www.teamrankings.com/nfl/",
    "odds": "https://betiq.teamrankings.com/nfl/odds-lines/",
    "trends": "https://betiq.teamrankings.com/nfl/betting-trends/win-loss-records/",
}


def fetch(slug: str) -> str:
    """Polite GET (10s spacing) that keeps the raw page in lake/bronze so parsers can re-run for free."""
    global _last_fetch
    wait = DELAY - (time.time() - _last_fetch)
    if wait > 0:
        time.sleep(wait)
    r = requests.get(PAGES[slug], headers={"User-Agent": UA}, timeout=30)
    _last_fetch = time.time()
    r.raise_for_status()
    day = BRONZE / datetime.now(CT).date().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    (day / f"{slug}.html").write_text(r.text)
    return r.text


# ── parsing (stdlib only) ─────────────────────────────────────────────────────
def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _tables(page: str) -> list[tuple[list[str], list[list[str]]]]:
    out = []
    for t in re.findall(r"<table.*?</table>", page, re.S):
        head = [_txt(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
        rows = []
        for tr in re.findall(r"<tr.*?</tr>", t, re.S):
            cells = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if cells:
                rows.append(cells)
        out.append((head, rows))
    return out


def parse_power_ratings(page: str) -> list[dict]:
    for head, rows in _tables(page):
        if head[:3] == ["Rank", "Rating", "Team"]:
            res = []
            for r in rows:
                m = re.match(r"(.+?) \((\d+)-(\d+)(?:-(\d+))?\)", r[2])
                if m:
                    res.append({"rank": r[0], "rating": r[1], "team": m.group(1), "wins": m.group(2), "losses": m.group(3),
                                "proj_w": r[3], "proj_l": r[4], "playoffs_pct": r[5].rstrip("%"), "win_sb_pct": r[6].rstrip("%")})
            return res
    return []


def parse_week_matchups(page: str) -> list[dict]:
    res = []
    for head, rows in _tables(page):
        if not head:
            for r in rows:
                if len(r) == 2 and re.search(r"\b(vs\.|at)\b", r[0]) and re.search(r"(Sun|Mon|Thu|Fri|Sat)", r[1]):
                    res.append({"matchup": r[0], "kickoff": r[1]})
    return res


def parse_odds(page: str) -> list[dict]:
    res = []
    for head, rows in _tables(page):
        if head[:2] == ["Start Time", "Teams"]:
            for r in rows:
                if len(r) < 5:
                    continue
                m = re.match(r"(\d+) (.+?) (\d+) (.+)$", r[1])
                res.append({"start_time_et": r[0], "away": m.group(2) if m else r[1], "home": m.group(4) if m else "",
                            "point_spread": r[2], "money_line": r[3], "over_under": r[4]})
    return res


def parse_trends(page: str) -> list[dict]:
    for head, rows in _tables(page):
        if head[:2] == ["Team", "Win-Loss Record"]:
            return [{"team": r[0], "record": r[1], "win_pct": r[2].rstrip("%"), "mov": r[3], "ats_plus_minus": r[4]} for r in rows if len(r) >= 5]
    return []


def _write(name: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    stamp = datetime.now(CT).isoformat(timespec="seconds")
    GOLD.mkdir(parents=True, exist_ok=True)
    with open(GOLD / f"{name}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) + ["fetched_at_ct"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "fetched_at_ct": stamp})
    return len(rows)


def _snapshot(ratings: list[dict], matchups: list[dict]) -> None:
    """tr_entrance.md: the plain-text front door Jimmy and MY BOO read first."""
    lines = [f"# NFL power ratings and week matchups (TeamRankings)", f"Pulled {datetime.now(CT).strftime('%a %b %-d %Y %-I:%M %p CT')}", "",
             "## Power ratings", "rank | team | rating | proj W-L | playoffs % | win SB %"]
    lines += [f"{r['rank']} | {r['team']} ({r['wins']}-{r['losses']}) | {r['rating']} | {r['proj_w']}-{r['proj_l']} | {r['playoffs_pct']} | {r['win_sb_pct']}" for r in ratings]
    lines += ["", "## This week's matchups (line, kickoff)"] + [f"{m['matchup']} | {m['kickoff']}" for m in matchups]
    (GOLD / "tr_entrance.md").write_text("\n".join(lines) + "\n")


# ── runs ──────────────────────────────────────────────────────────────────────
def _runs() -> dict:
    try:
        return json.loads(RUNS.read_text())
    except (OSError, ValueError):
        return {}


def run(kind: str) -> dict:
    """kind = 'full' (entrance + odds + trends) or 'daily' (odds only). A failed page never blocks the others."""
    with _LOCK:
        res: dict = {"kind": kind, "at": datetime.now(CT).isoformat(timespec="seconds"), "pages": {}, "errors": {}}
        jobs = [("odds", lambda p: _write("tr_odds", parse_odds(p)))]
        if kind == "full":
            def entrance(p: str) -> int:
                ratings, matchups = parse_power_ratings(p), parse_week_matchups(p)
                _snapshot(ratings, matchups)
                _write("tr_week_matchups", matchups)
                return _write("tr_power_ratings", ratings)
            jobs = [("entrance", entrance)] + jobs + [("trends", lambda p: _write("tr_ats_records", parse_trends(p)))]
        for slug, handler in jobs:
            try:
                res["pages"][slug] = handler(fetch(slug))
            except Exception as e:
                res["errors"][slug] = f"{type(e).__name__}: {e}"[:200]
        runs = _runs()
        runs[kind] = res
        if kind == "full":
            runs["daily"] = res                                     # a full run already pulled today's odds
        runs.setdefault("history", []).append(res)
        runs["history"] = runs["history"][-40:]
        RUNS.write_text(json.dumps(runs, indent=1))
        try:
            import boo_store
            threading.Thread(target=boo_store.push, daemon=True).start()   # keep the new ponds off the ephemeral disk
        except Exception:
            pass
        return res


def _last(weekday: int, hour: int) -> datetime:
    now = datetime.now(CT)
    t = now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=(now.weekday() - weekday) % 7)
    return t - timedelta(days=7) if t > now else t


def _due(kind: str) -> bool:
    last = _runs().get(kind, {}).get("at")
    done = datetime.fromisoformat(last) if last else None
    now = datetime.now(CT)
    if kind == "full":
        return not done or done < _last(1, 1)                      # Tuesday 1 AM CT
    today_9 = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now.weekday() in (1, 2) or now < today_9:                    # Tue/Wed have no daily pull
        return False
    return not done or done < today_9


def maybe_run() -> dict | None:
    """Called by the worker every minute. Catches up if the Space was down at the scheduled hour."""
    for kind in ("full", "daily"):
        if _due(kind):
            return run(kind)
    return None


def status() -> dict:
    r = _runs()
    return {"full": r.get("full"), "daily": r.get("daily"), "recent": r.get("history", [])[-6:]}


# ── readers: what Jimmy, RAMP and MY BOO consume (lake only, never the network) ─
_SPECIAL = {"LA Rams": "LAR", "LA Chargers": "LAC", "NY Giants": "NYG", "NY Jets": "NYJ"}
_mem: dict[str, tuple[float, object]] = {}


def _read(name: str) -> list[dict]:
    """tr_*.csv rows, re-read only when the file changed, so a fresh intake is live on the next call."""
    p = GOLD / f"{name}.csv"
    try:
        m = p.stat().st_mtime
    except OSError:
        return []
    hit = _mem.get(name)
    if hit and hit[0] == m:
        return hit[1]  # type: ignore[return-value]
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    _mem[name] = (m, rows)
    return rows


def abbr(name: str) -> str | None:
    """'Seattle' / 'LA Rams' / 'NY Jets' -> lake abbreviation."""
    name = (name or "").strip()
    if name in _SPECIAL:
        return _SPECIAL[name]
    hit = _mem.get("_abbr")
    if not hit:
        try:
            with open(GOLD / "team_abbr_map.csv", newline="") as f:
                hit = (0.0, list(csv.DictReader(f)))
        except OSError:
            return None
        _mem["_abbr"] = hit
    for r in hit[1]:  # type: ignore[index]
        if r["city"] == name or r["full_name"] == name or r["full_name"].startswith(name + " "):
            return r["abbr_lake"]
    return None


def ratings() -> dict[str, dict]:
    """{abbr: {rank, rating, proj_w, proj_l, playoffs_pct, win_sb_pct, ats_plus_minus, mov}}"""
    ats = {abbr(r["team"]): r for r in _read("tr_ats_records")}
    out = {}
    for r in _read("tr_power_ratings"):
        a = abbr(r["team"])
        if a:
            t = ats.get(a, {})
            out[a] = {"rank": int(r["rank"]), "rating": float(r["rating"]), "proj_w": float(r["proj_w"]), "proj_l": float(r["proj_l"]),
                      "playoffs_pct": float(r["playoffs_pct"]), "win_sb_pct": float(r["win_sb_pct"]),
                      "ats_plus_minus": t.get("ats_plus_minus"), "mov": t.get("mov")}
    return out


def power_edge(team: str | None, opp: str | None) -> float | None:
    """Team rating minus opponent rating (TeamRankings points scale). None when either is unknown."""
    R = ratings()
    if team in R and opp in R:
        return round(R[team]["rating"] - R[opp]["rating"], 2)
    return None


def week_matchups() -> list[dict]:
    """[{away, home, spread (home perspective), neutral, kickoff}] parsed from 'A (-3) at B' / 'A (-4.5) vs. B' (neutral site)."""
    out = []
    for r in _read("tr_week_matchups"):
        m = re.match(r"(.+?)(?: \(([+-]?\d+(?:\.\d+)?)\))? (at|vs\.) (.+?)(?: \(([+-]?\d+(?:\.\d+)?)\))?$", r["matchup"])
        if not m:
            continue
        a_name, a_sp, how, h_name, h_sp = m.groups()          # first team is the visitor ('at') or nominal home ('vs.')
        first, second = abbr(a_name), abbr(h_name)
        away, home = (first, second) if how == "at" else (second, first)
        if how == "at":
            home_spread = float(h_sp) if h_sp else -float(a_sp or 0)
        else:
            home_spread = float(a_sp) if a_sp else -float(h_sp or 0)
        out.append({"away": away, "home": home, "spread": home_spread, "neutral": how == "vs.", "kickoff": r["kickoff"], "label": r["matchup"]})
    return out


def game_context(home: str | None, away: str | None) -> dict | None:
    R = ratings()
    if home not in R or away not in R:
        return None
    return {"home": R[home], "away": R[away], "edge_home": round(R[home]["rating"] - R[away]["rating"], 2)}

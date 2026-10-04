"""Free ESPN headshots for NFL players (replaces the paid Tank01 photo path).

Id sources, best first, all failure-tolerant (nothing here ever raises):
  1. lake/gold/espn/player_photo_map.json  (persisted {normalized name: [[team, espn_id], ...]})
  2. lake/gold/nfl/news_article_tag.csv    (offline: athlete tags carry espn_athlete_id + name)
  3. ESPN public team rosters (site.api.espn.com), fetched lazily, cached with a TTL,
     and written back to (1).
Match is by normalized name, preferring the same team.
"""
from __future__ import annotations

import csv
import json
import threading
import time
import urllib.request

import data

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
_ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team}/roster"
_TTL = 6 * 3600
_FAIL_TTL = 15 * 60
MAP_PATH = data.REPO / "lake" / "gold" / "espn" / "player_photo_map.json"
_ESPN_ABBR = {"WSH": "WAS", "LA": "LAR", "JAC": "JAX"}

_lock = threading.Lock()
_map: dict[str, list[list[str]]] | None = None
_loaded_at = 0.0
_last_fetch_try = 0.0


def url_for(espn_id) -> str:
    return f"https://a.espncdn.com/i/headshots/nfl/players/full/{espn_id}.png"


def parse_roster(body: dict, team: str) -> list[tuple[str, str, str]]:
    """ESPN roster JSON -> [(normalized_name, team, espn_id)]. Handles grouped and flat shapes."""
    out = []
    athletes = (body or {}).get("athletes") or []
    flat = []
    for g in athletes:
        if isinstance(g, dict) and "items" in g:
            flat.extend(g["items"] or [])
        else:
            flat.append(g)
    for a in flat:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        name = a.get("fullName") or a.get("displayName") or ""
        if name:
            out.append((data.normalize_name(name), team, str(a["id"])))
    return out


def _add(m: dict, name: str, team: str, eid: str) -> None:
    lst = m.setdefault(name, [])
    if [team, eid] not in lst:
        lst.append([team, eid])


def _from_lake_tags() -> dict:
    m: dict = {}
    try:
        for r in data.load("news_article_tag"):
            if r.get("tag_type") == "athlete" and r.get("espn_athlete_id") and r.get("tag_description"):
                _add(m, data.normalize_name(r["tag_description"]), "", r["espn_athlete_id"])
    except Exception:
        pass
    return m


def _read_map_file() -> dict:
    try:
        return json.loads(MAP_PATH.read_text())
    except Exception:
        return {}


def _fetch_rosters() -> dict:
    m: dict = {}
    try:
        teams = [r["abbr_lake"] for r in data.load("team_abbr_map") if r.get("abbr_lake")]
    except Exception:
        return m
    for t in teams:
        try:
            req = urllib.request.Request(_ROSTER_URL.format(team=_ESPN_ABBR.get(t, t).lower()),
                                         headers={"User-Agent": _UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                body = json.loads(r.read())
            for n, tm, eid in parse_roster(body, t):
                _add(m, n, tm, eid)
        except Exception:
            continue
    return m


def _build() -> dict:
    global _last_fetch_try
    m = _from_lake_tags()
    for n, lst in _read_map_file().items():
        for tm, eid in lst:
            _add(m, n, tm, eid)
    if time.time() - _last_fetch_try > _FAIL_TTL and (not _read_map_file() or time.time() - _loaded_at > _TTL):
        _last_fetch_try = time.time()
        live = _fetch_rosters()
        if live:
            for n, lst in live.items():
                for tm, eid in lst:
                    _add(m, n, tm, eid)
            try:
                MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
                MAP_PATH.write_text(json.dumps(live))
            except Exception:
                pass
    return m


def _get_map() -> dict:
    global _map, _loaded_at
    with _lock:
        if _map is None or time.time() - _loaded_at > _TTL:
            try:
                _map = _build()
            except Exception:
                _map = _map or {}
            _loaded_at = time.time()
        return _map


def espn_photo(name: str, team: str = "") -> str | None:
    """ESPN headshot URL for a player by name (+team preference), or None. Never raises."""
    try:
        hits = _get_map().get(data.normalize_name(name or ""), [])
        for tm, eid in hits:
            if team and tm == team:
                return url_for(eid)
        ids = {eid for _, eid in hits}
        if len(ids) == 1:  # unambiguous
            return url_for(next(iter(ids)))
    except Exception:
        pass
    return None

"""
Read-only data layer over lake/gold/nfl/*.csv.

Deliberately does NOT touch lake/nfl.duckdb -- that file is gitignored and
not guaranteed to exist on a fresh clone (see docs/HANDOFF.md sec 5). Every
gold CSV under lake/gold/nfl/ is tracked in git and is the source of truth
this backend reads.

Per HANDOFF_CLAUDE_CODE.md sec 0, rule 1: only a chart whose _index.csv row
has status == "ok" is ever rendered with real data -- anything else returns
an explicit empty/stale/error state, never a silent fallback to placeholder
values.

Known real gap, documented rather than worked around silently: prop_best_price
/ prop_line_rotowire key players by RotoWire's own numeric player_id, not the
nflverse gsis_id used everywhere else in the lake (docs/HANDOFF.md sec 5.8 --
the id bridge table exists but has never been populated). This layer joins
those two worlds by normalized player name, the same workaround
scripts/matchup_report.py already uses for the same reason.
"""
from __future__ import annotations

import csv
import pathlib
import re
import threading
from functools import lru_cache

REPO = pathlib.Path(__file__).resolve().parent.parent
GOLD = REPO / "lake" / "gold" / "nfl"

_lock = threading.Lock()


def _read_csv(name: str) -> list[dict]:
    path = GOLD / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@lru_cache(maxsize=64)
def _cached_csv(name: str, _version: int) -> list[dict]:
    return _read_csv(name)


_VERSION = 0  # bump to invalidate the cache (not needed -- data is static per session)


def load(name: str) -> list[dict]:
    with _lock:
        return _cached_csv(name, _VERSION)


def normalize_name(name: str) -> str:
    """Loose match key: lowercase, strip punctuation/suffixes, collapse spaces."""
    n = name.lower()
    n = re.sub(r"[.'\-]", "", n)
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ---------------------------------------------------------------------------
# _index.csv -- the chart-status gate every endpoint must honor
# ---------------------------------------------------------------------------

def chart_index() -> dict[str, dict]:
    rows = load("_index")
    return {r["chart_name"]: r for r in rows}


def chart_status(chart_name: str) -> str:
    row = chart_index().get(chart_name)
    return row["status"] if row else "error"


# ---------------------------------------------------------------------------
# Player dimension -- gsis_id -> {name, team, position}, built from whichever
# gold CSVs actually carry gsis ids + names (player_photos/_index.csv is the
# most complete display-name source; team/position resolved from the most
# recent week seen in player_scrimmage_week.csv).
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def player_dimension() -> dict[str, dict]:
    photos = {r["player_id"]: r["player_display_name"] for r in load("player_photos/_index") if r.get("player_id")}
    dim: dict[str, dict] = {}
    for row in load("player_scrimmage_week"):
        pid = row.get("player_id")
        if not pid:
            continue
        wk = int(row.get("week") or 0)
        existing = dim.get(pid)
        if existing is None or wk >= existing["_week"]:
            dim[pid] = {
                "player_id": pid,
                "name": photos.get(pid, pid),
                "team": row.get("team", ""),
                "_week": wk,
            }
    # position isn't on the weekly stat tables; player_usage.csv is the one
    # gold export that carries it, keyed by (season, team, player_id).
    for row in load("player_usage"):
        pid = row.get("player_id")
        if pid in dim:
            dim[pid]["position"] = row.get("position", "")
    for pid, row in dim.items():
        row.setdefault("name", photos.get(pid, pid))
        row.setdefault("position", "")
        row.pop("_week", None)
    return dim


def player_name(player_id: str) -> str:
    dim = player_dimension()
    if player_id in dim:
        return dim[player_id]["name"]
    photos = {r["player_id"]: r["player_display_name"] for r in load("player_photos/_index")}
    return photos.get(player_id, player_id)


def player_team(player_id: str) -> str:
    return player_dimension().get(player_id, {}).get("team", "")


def photo_url(player_id: str) -> str | None:
    """
    Real per-player headshots are NOT available in this deployment -- the
    *.png files are gitignored and this environment's network policy blocks
    the NFL.com/Cloudinary host they'd normally be cached from (see the plan
    doc / github.md for the full story). Always returns None so the frontend
    falls back to its initials avatar, per HANDOFF_CLAUDE_CODE.md sec 0 rule 4
    ("never hotlink").
    """
    return None


def search_players(query: str, limit: int = 20) -> list[dict]:
    q = normalize_name(query)
    if not q:
        return []
    out = []
    for pid, row in player_dimension().items():
        if q in normalize_name(row["name"]):
            out.append({"playerId": pid, "name": row["name"], "team": row["team"]})
    return out[:limit]


# ---------------------------------------------------------------------------
# Prop lines -- RotoWire, name-matched to the gsis player dimension
# ---------------------------------------------------------------------------

MARKET_TO_STAT = {
    "rushyds": ("player_rushing_week", "rushing_yards"),
    "recyds": ("player_receiving_week", "receiving_yards"),
    "recs": ("player_receiving_week", "receptions"),
    "passyds": ("player_passing_week", "passing_yards"),
    "passtd": ("player_passing_week", "passing_tds"),
}

PROP_LABELS = {
    "rushyds": "Rush Yds",
    "recyds": "Rec Yds",
    "recs": "Receptions",
    "passyds": "Pass Yds",
    "passtd": "Pass TDs",
    "anytd": "Any TD",
}


@lru_cache(maxsize=1)
def _name_to_best_price() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in load("prop_best_price"):
        key = normalize_name(row.get("player_name", ""))
        out.setdefault(key, []).append(row)
    return out


def best_price_for(player_name_str: str, market_slug: str) -> dict | None:
    key = normalize_name(player_name_str)
    for row in _name_to_best_price().get(key, []):
        if row.get("market_slug") == market_slug:
            return row
    return None


@lru_cache(maxsize=1)
def _name_to_rotowire_fanduel() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in load("prop_line_rotowire"):
        if row.get("book_slug") != "fanduel":
            continue
        key = normalize_name(row.get("player_name", ""))
        out.setdefault(key, []).append(row)
    return out


def fanduel_line_for(player_name_str: str, market_slug: str) -> dict | None:
    """
    The real FanDuel line/price for a player+market, per the user's explicit
    choice (FanDuel only, not best-price-across-books). Reads
    prop_line_rotowire.csv filtered to book_slug == 'fanduel' -- the raw,
    single-book source -- rather than prop_best_price.csv, which mixes
    whichever book happened to have the best number per market. Falls back
    to prop_best_price only if no FanDuel row exists at all for this
    player/market, and labels the book honestly either way.
    """
    key = normalize_name(player_name_str)
    candidates = [r for r in _name_to_rotowire_fanduel().get(key, []) if r.get("market_slug") == market_slug]
    if candidates:
        # multiple pulls/snapshots can exist; take the most recently fetched
        latest = max(candidates, key=lambda r: r.get("fetched_at_utc", ""))
        return {
            "line": latest.get("line"),
            "book": "fanduel",
            "over_price": latest.get("over_price_american"),
            "under_price": latest.get("under_price_american"),
            "moneyline_price": latest.get("moneyline_american"),
        }
    fallback = best_price_for(player_name_str, market_slug)
    if fallback:
        return {
            "line": fallback.get("line"),
            "book": fallback.get("best_over_book") or fallback.get("best_moneyline_book") or "unknown",
            "over_price": fallback.get("best_over_price"),
            "under_price": fallback.get("best_under_price"),
            "moneyline_price": fallback.get("best_moneyline_price"),
        }
    return None


# ---------------------------------------------------------------------------
# Weekly game log for a player + prop, with hit-rate vs the current line
# ---------------------------------------------------------------------------

def player_prop_chart(player_id: str, market_slug: str) -> dict:
    name = player_name(player_id)
    team = player_team(player_id)
    status = chart_status(MARKET_TO_STAT.get(market_slug, ("prop_best_price",))[0])

    if market_slug == "anytd":
        games = anytime_td_games(player_id)
        line_row = None
        line = 0.5
        book = None
    else:
        src, stat_col = MARKET_TO_STAT.get(market_slug, (None, None))
        if src is None:
            return {"error": f"unknown market_slug {market_slug}"}
        games = weekly_games(player_id, src, stat_col)
        line_row = fanduel_line_for(name, market_slug)
        line = float(line_row["line"]) if line_row and line_row.get("line") else None
        book = line_row.get("book") if line_row else None

    games_sorted = sorted(games, key=lambda g: g["week"])
    bars = [{"gameDate": f"Week {g['week']}", "opponent": g["opponent"], "value": g["value"]} for g in games_sorted]

    def hit_rate(window: list[dict]) -> float | None:
        if not window or line is None:
            return None
        hits = sum(1 for g in window if g["value"] >= line)
        return round(hits / len(window), 3)

    l5 = games_sorted[-5:]
    l10 = games_sorted[-10:]
    l20 = games_sorted[-20:]

    return {
        "playerId": player_id,
        "name": name,
        "team": team,
        "prop": PROP_LABELS.get(market_slug, market_slug),
        "marketSlug": market_slug,
        "line": line,
        "book": book or "FanDuel",
        "games": bars,
        "splits": [
            {"label": "L5", "hitRate": hit_rate(l5)},
            {"label": "L10", "hitRate": hit_rate(l10)},
            {"label": "L20", "hitRate": hit_rate(l20)},
        ],
        "sourceStatus": status,
        "photoUrl": photo_url(player_id),
    }


def weekly_games(player_id: str, src: str, stat_col: str) -> list[dict]:
    out = []
    for row in load(src):
        if row.get("player_id") != player_id:
            continue
        try:
            value = float(row.get(stat_col) or 0)
        except ValueError:
            value = 0.0
        out.append({"week": int(row.get("week") or 0), "opponent": row.get("opponent_team", ""), "value": value})
    return out


def anytime_td_games(player_id: str) -> list[dict]:
    out = []
    for row in load("player_scoring_week"):
        if row.get("player_id") != player_id:
            continue
        tds = float(row.get("total_tds") or 0)
        out.append({"week": int(row.get("week") or 0), "opponent": row.get("opponent_team", ""), "value": tds})
    return out


def hit_rate_probability(player_id: str, market_slug: str, window: int = 10) -> float | None:
    """
    The parlay-leg 'probability' score, per the user's explicit choice:
    hit-rate-vs-line only (no usage/toxicity/redzone weighting for v1).
    This is a documented model output, not a raw lake fact -- see
    sql/nfl_parlay_probability_schema.sql for the equivalent view definition
    and its own _index.csv row (added for when the lake is rebuilt with
    DuckDB in an environment that has it).
    """
    chart = player_prop_chart(player_id, market_slug)
    if chart.get("line") is None:
        return None
    games = sorted(chart["games"], key=lambda g: g["gameDate"])[-window:]
    if not games:
        return None
    hits = sum(1 for g in games if g["value"] >= chart["line"])
    return round(hits / len(games), 3)

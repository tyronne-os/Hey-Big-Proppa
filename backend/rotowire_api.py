"""
RotoWire prop API — exposes the RotoWire player-prop board as a clean, queryable API.

Sources (all under lake/gold/nfl/):
  prop_line_rotowire.csv    one row per player/game/book/market/pull (append-only)
  prop_best_price.csv       one row per player/game/market, best price across books
  prop_line_movement.csv    one row per player/market/book with 2+ snapshots

The page is served like the RotoWire player-props page: a board of every game, every
player, every prop market, with the line and over/under prices per book.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "nfl"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load(name: str) -> list[dict]:
    with open(BASE / name) as f:
        return list(csv.DictReader(f))


def board(market: str | None = None, team: str | None = None) -> dict:
    """The full RotoWire prop board, grouped by game, then player, then market.

    Returns the latest pull per (player, market, book) so the board shows the most
    current line/prices. Optionally filter by market slug or team.
    """
    rows = _load("prop_line_rotowire.csv")
    # keep the latest pull per (game, player, market, book)
    latest: dict[tuple, dict] = {}
    for r in rows:
        if market and r.get("market_slug") != market:
            continue
        if team and r.get("team") != team:
            continue
        key = (r.get("game_id"), r.get("player_id"), r.get("market_slug"), r.get("book_slug"))
        if key not in latest or r.get("fetched_at_utc", "") >= latest[key].get("fetched_at_utc", ""):
            latest[key] = r

    # group by game -> player -> market
    games: dict[str, dict] = defaultdict(lambda: {"players": defaultdict(lambda: defaultdict(list))})
    for (gid, pid, mkt, book), r in latest.items():
        entry = {
            "book": r.get("book_slug"), "line": _num(r.get("line")),
            "over": _num(r.get("over_price_american")), "under": _num(r.get("under_price_american")),
            "moneyline": _num(r.get("moneyline_american")),
        }
        games[gid]["players"][pid][mkt].append(entry)

    # build a clean response
    out_games = []
    for gid, g in games.items():
        players = []
        for pid, mkts in g["players"].items():
            # get player name/team from first entry's row
            name = next((r.get("player_name") for r in latest.values()
                         if r.get("game_id") == gid and r.get("player_id") == pid), pid)
            team = next((r.get("team") for r in latest.values()
                         if r.get("game_id") == gid and r.get("player_id") == pid), "")
            market_list = []
            for mkt, books in mkts.items():
                # collapse per-book lines into one player-market row
                market_list.append({"market": mkt, "books": books})
            players.append({"playerId": pid, "name": name, "team": team, "markets": market_list})
        out_games.append({"gameId": gid, "players": players})

    # a flat table view is often easier for the page
    flat = []
    for (gid, pid, mkt, book), r in latest.items():
        flat.append({
            "gameId": gid, "playerId": pid, "playerName": r.get("player_name"),
            "team": r.get("team"), "opponent": r.get("opponent"), "market": mkt,
            "book": book, "line": _num(r.get("line")),
            "over": _num(r.get("over_price_american")), "under": _num(r.get("under_price_american")),
            "moneyline": _num(r.get("moneyline_american")),
        })
    return {
        "sourceStatus": "ok",
        "games": out_games,
        "rows": flat,
        "markets": sorted({r.get("market_slug") for r in rows}),
        "books": sorted({r.get("book_slug") for r in rows}),
        "count": len(flat),
    }


def market_leaderboard(market: str = "rushyds", n: int = 25) -> dict:
    """Best-price board for one market: player, line, best over/under across books."""
    rows = _load("prop_best_price.csv")
    out = []
    for r in rows:
        if r.get("market_slug") != market:
            continue
        out.append({
            "playerId": r.get("player_id"), "playerName": r.get("player_name"),
            "line": _num(r.get("line")),
            "bestOver": _num(r.get("best_over_price")), "bestOverBook": r.get("best_over_book"),
            "bestUnder": _num(r.get("best_under_price")), "bestUnderBook": r.get("best_under_book"),
            "numBooks": _num(r.get("num_books")),
        })
    out.sort(key=lambda x: (x["bestOver"] or 999999), reverse=True)
    return {"market": market, "rows": out[:n], "count": len(out)}


if __name__ == "__main__":
    b = board()
    print("count:", b["count"])
    print("markets:", b["markets"])
    print("books:", b["books"])
    print("games:", len(b["games"]))
    # print a sample player board
    g = b["games"][0]
    p = g["players"][0]
    print(f"\nGame {g['gameId']} | {p['name']} ({p['team']}):")
    for m in p["markets"]:
        print(f"  {m['market']}: {m['books']}")

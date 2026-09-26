"""
MY BOO — Data Engineering & Sportsbook Analytics Engine

Ticket tracking system for:
  POW-ORD  Pick of the Week — high-conviction real capital bets
  SIM-ORD  Simulated sandbox orders — test logic before committing

Ticket lifecycle:
  OPEN → IN_PROGRESS → SETTLED_WIN | SETTLED_LOSS | PUSH_VOID

Weekly settlement window: Tuesday 06:00 CST → Tuesday 06:00 CST.

Outputs (lake/gold/nfl/):
  myboo_tickets.csv  — one row per parlay ticket
  myboo_legs.csv     — one row per leg within a ticket
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
_TICKETS_FILE = _GOLD / "myboo_tickets.csv"
_LEGS_FILE    = _GOLD / "myboo_legs.csv"

_TICKET_COLS = [
    "ticket_id", "order_type", "name", "created_at",
    "season", "week", "status",
    "payout_odds", "stake_units", "result_units",
    "settled_at", "note",
]

_LEG_COLS = [
    "leg_id", "ticket_id", "player_name", "team",
    "market", "direction", "line", "odds", "probability",
    "game_date", "actual_value", "pct_complete", "status",
    "graded_at",
]

_TICKET_COUNTER_FILE = _GOLD / "myboo_counter.txt"


def _ensure_files():
    _GOLD.mkdir(parents=True, exist_ok=True)
    for path, cols in [(_TICKETS_FILE, _TICKET_COLS), (_LEGS_FILE, _LEG_COLS)]:
        if not path.exists():
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(cols)


def _next_ticket_id(order_type: str, week: int, season: int) -> str:
    n = 1
    if _TICKET_COUNTER_FILE.exists():
        try:
            n = int(_TICKET_COUNTER_FILE.read_text().strip()) + 1
        except ValueError:
            pass
    _TICKET_COUNTER_FILE.write_text(str(n))
    tag = "POW" if order_type == "POW" else "SIM"
    return f"MB-{season}-WK{week:02d}-{tag}{n:04d}"


def create_ticket(
    order_type: str,          # "POW" or "SIM"
    name: str,
    legs: list[dict],
    season: int,
    week: int,
    payout_odds: float = 0.0,
    stake_units: float = 1.0,
    note: str = "",
) -> str:
    """
    Create a new parlay ticket and its legs. Returns the ticket_id.

    Each leg dict must have:
      player_name, team, market, direction, line, odds, probability, game_date
    """
    _ensure_files()
    ticket_id = _next_ticket_id(order_type, week, season)
    now = datetime.now(timezone.utc).isoformat()

    ticket_row = {
        "ticket_id":    ticket_id,
        "order_type":   order_type,
        "name":         name,
        "created_at":   now,
        "season":       season,
        "week":         week,
        "status":       "OPEN",
        "payout_odds":  payout_odds,
        "stake_units":  stake_units,
        "result_units": "",
        "settled_at":   "",
        "note":         note,
    }
    with open(_TICKETS_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=_TICKET_COLS).writerow(ticket_row)

    with open(_LEGS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_LEG_COLS)
        for i, leg in enumerate(legs, 1):
            leg_row = {
                "leg_id":       f"{ticket_id}-L{i:02d}",
                "ticket_id":    ticket_id,
                "player_name":  leg.get("player_name", ""),
                "team":         leg.get("team", ""),
                "market":       leg.get("market", ""),
                "direction":    leg.get("direction", "over"),
                "line":         leg.get("line", ""),
                "odds":         leg.get("odds", -110),
                "probability":  leg.get("probability", ""),
                "game_date":    leg.get("game_date", ""),
                "actual_value": "",
                "pct_complete": "",
                "status":       "PENDING",
                "graded_at":    "",
            }
            w.writerow(leg_row)

    return ticket_id


def load_tickets(order_type: str | None = None) -> list[dict]:
    """
    Return all tickets with their legs embedded.
    Filter by order_type ("POW" or "SIM") if provided.
    """
    _ensure_files()

    legs_by_ticket: dict[str, list[dict]] = {}
    if _LEGS_FILE.exists():
        with open(_LEGS_FILE, newline="") as f:
            for row in csv.DictReader(f):
                tid = row["ticket_id"]
                legs_by_ticket.setdefault(tid, []).append(dict(row))

    tickets = []
    if _TICKETS_FILE.exists():
        with open(_TICKETS_FILE, newline="") as f:
            for row in csv.DictReader(f):
                if order_type and row.get("order_type") != order_type:
                    continue
                t = dict(row)
                t["legs"] = legs_by_ticket.get(row["ticket_id"], [])
                # derive live progress for each leg if we have actual data
                for leg in t["legs"]:
                    try:
                        line = float(leg.get("line") or 0)
                        actual = float(leg.get("actual_value") or 0)
                        if line > 0 and actual > 0:
                            leg["pct_complete"] = min(100, round(actual / line * 100))
                        else:
                            leg["pct_complete"] = 0
                    except (ValueError, TypeError):
                        leg["pct_complete"] = 0
                tickets.append(t)

    tickets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return tickets


def weekly_ledger() -> list[dict]:
    """
    Tuesday-to-Tuesday ROI summary per week across all POW tickets.
    """
    _ensure_files()
    by_week: dict[tuple[int, int], dict] = {}

    if _TICKETS_FILE.exists():
        with open(_TICKETS_FILE, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("order_type") != "POW":
                    continue
                key = (int(row.get("season") or 0), int(row.get("week") or 0))
                b = by_week.setdefault(key, {
                    "season": key[0], "week": key[1],
                    "pow_tickets": 0, "wins": 0, "losses": 0, "pending": 0,
                    "units_staked": 0.0, "units_won": 0.0,
                })
                b["pow_tickets"] += 1
                try:
                    b["units_staked"] += float(row.get("stake_units") or 0)
                    b["units_won"]    += float(row.get("result_units") or 0)
                except (ValueError, TypeError):
                    pass
                status = row.get("status", "")
                if status == "SETTLED_WIN":
                    b["wins"] += 1
                elif status == "SETTLED_LOSS":
                    b["losses"] += 1
                else:
                    b["pending"] += 1

    rows = sorted(by_week.values(), key=lambda x: (x["season"], x["week"]), reverse=True)
    for r in rows:
        graded = r["wins"] + r["losses"]
        r["hit_rate"] = round(r["wins"] / graded, 3) if graded else None
        r["roi"] = round((r["units_won"] - r["units_staked"]) / r["units_staked"], 3) if r["units_staked"] else None
    return rows


def _load_picks_history() -> list[dict]:
    """
    Load crazy_horse_picks.csv — the main graded pick history.
    """
    fpath = _GOLD / "crazy_horse_picks.csv"
    if not fpath.exists():
        return []
    rows = []
    with open(fpath, newline="") as f:
        for row in csv.DictReader(f):
            rows.append(dict(row))
    return rows


def training_log() -> dict:
    """
    Jimmy the Greek training log:
      - hit_patterns: markets + conditions that win above 55%
      - failure_modes: markets that miss and why (structural vs variance)
      - scale_recommendations: where conservative edge has evidence to go aggressive
    """
    picks = _load_picks_history()
    graded = [p for p in picks if p.get("result") in ("HIT", "MISS")]

    if not graded:
        return {
            "summary": "No graded picks yet — tracking starts after Week 1 games settle.",
            "hit_patterns": [],
            "failure_modes": [],
            "scale_recommendations": [],
            "training_payload": {},
        }

    # Aggregate by (market, direction)
    agg: dict[tuple[str, str], dict] = {}
    for p in graded:
        key = (p.get("market", "?"), p.get("direction", "over"))
        b = agg.setdefault(key, {"hits": 0, "misses": 0, "margins": []})
        b["hits" if p["result"] == "HIT" else "misses"] += 1
        try:
            actual = float(p.get("actual_value") or 0)
            line   = float(p.get("line") or 0)
            b["margins"].append(actual - line)
        except (ValueError, TypeError):
            pass

    hit_patterns = []
    failure_modes = []
    scale_recs = []

    for (market, direction), b in sorted(agg.items(), key=lambda x: -(x[1]["hits"] + x[1]["misses"])):
        total = b["hits"] + b["misses"]
        if total < 3:
            continue
        rate = b["hits"] / total
        avg_margin = sum(b["margins"]) / len(b["margins"]) if b["margins"] else 0

        entry = {
            "market": market,
            "direction": direction,
            "total": total,
            "hits": b["hits"],
            "misses": b["misses"],
            "hit_rate": round(rate, 3),
            "avg_margin": round(avg_margin, 2),
        }

        if rate >= 0.55:
            hit_patterns.append(entry)
        elif rate < 0.45:
            # structural failure if avg margin consistently wrong side
            entry["failure_type"] = "STRUCTURAL" if avg_margin < -5 else "VARIANCE"
            failure_modes.append(entry)

        # Scale recommendation: hit rate >= 0.72 over >= 5 samples
        if rate >= 0.72 and total >= 5 and avg_margin > 0:
            scale_recs.append({
                **entry,
                "recommendation": f"Evidence supports moving {direction} line from historical to +{round(avg_margin, 1)} units ({round(rate*100)}% hit rate over {total} games)",
                "confidence": "HIGH" if total >= 10 else "MEDIUM",
            })

    # Weekly training payload for Jimmy
    training_payload: dict[str, Any] = {}
    for (market, direction), b in agg.items():
        total = b["hits"] + b["misses"]
        if total < 2:
            continue
        training_payload[f"{market}_{direction}"] = {
            "weight_adjustment": round((b["hits"] / total - 0.5) * 0.2, 4),
            "sample_size": total,
        }

    return {
        "summary": f"{len(graded)} graded picks — {sum(1 for p in graded if p['result']=='HIT')} hits ({round(sum(1 for p in graded if p['result']=='HIT')/len(graded)*100, 1)}%)",
        "hit_patterns": hit_patterns,
        "failure_modes": failure_modes,
        "scale_recommendations": scale_recs,
        "training_payload": training_payload,
    }


def post_mortem() -> dict:
    """
    Near-miss audit and 'money left on the table' analysis.
    Compares predicted thresholds against actual player performance
    for missed picks and near-miss wins.
    """
    picks = _load_picks_history()
    graded = [p for p in picks if p.get("result") in ("HIT", "MISS")]

    near_misses = []
    left_on_table = []
    conservative_flags: dict[str, dict] = {}

    for p in graded:
        try:
            actual = float(p.get("actual_value") or 0)
            line   = float(p.get("line") or 0)
            if line <= 0:
                continue
        except (ValueError, TypeError):
            continue

        margin = actual - line
        pct_over = margin / line * 100 if line > 0 else 0
        result = p.get("result")
        direction = p.get("direction", "over")

        # Near miss: MISS but came within 10% of the line
        if result == "MISS" and direction == "over" and -0.10 <= margin / line <= 0:
            near_misses.append({
                "player": p.get("player_name", ""),
                "market": p.get("market", ""),
                "direction": direction,
                "line": line,
                "actual": actual,
                "margin": round(margin, 1),
                "pct_off": round(margin / line * 100, 1),
                "horse_type": p.get("horse_type", ""),
                "week": p.get("week", ""),
                "season": p.get("season", ""),
                "note": "Variance — player missed by <10% of line",
            })

        # Money left on table: HIT but actual was 20%+ over the line
        if result == "HIT" and direction == "over" and pct_over >= 20:
            left_on_table.append({
                "player": p.get("player_name", ""),
                "market": p.get("market", ""),
                "direction": direction,
                "line": line,
                "actual": actual,
                "over_by": round(margin, 1),
                "pct_over": round(pct_over, 1),
                "week": p.get("week", ""),
                "season": p.get("season", ""),
                "note": f"Conservative — player hit {round(pct_over)}% over line. Consider raising threshold.",
            })

            # Track repeated over-performance for scale recommendation
            key = f"{p.get('player_name', '')}_{p.get('market', '')}"
            b = conservative_flags.setdefault(key, {"count": 0, "total_pct_over": 0.0, "player": p.get("player_name", ""), "market": p.get("market", "")})
            b["count"] += 1
            b["total_pct_over"] += pct_over

    # Aggressive-scale candidates: consistent over-performance in 3+ games
    aggressive_recs = []
    for key, b in conservative_flags.items():
        if b["count"] >= 3:
            avg_over = b["total_pct_over"] / b["count"]
            aggressive_recs.append({
                "player": b["player"],
                "market": b["market"],
                "games_analyzed": b["count"],
                "avg_pct_over_line": round(avg_over, 1),
                "recommendation": f"RAISE LINE by ~{round(avg_over * 0.5, 1)}% — data evidence over {b['count']} games",
                "confidence": "HIGH" if b["count"] >= 5 else "MEDIUM (need 72% hit rate over 5+ games to confirm)",
            })

    return {
        "summary": {
            "total_graded": len(graded),
            "near_misses": len(near_misses),
            "left_on_table": len(left_on_table),
            "aggressive_recs_ready": len(aggressive_recs),
        },
        "near_misses": near_misses[:20],
        "left_on_table": left_on_table[:20],
        "aggressive_scale_recs": aggressive_recs,
        "conservatism_note": (
            "MY BOO holds the 72% threshold before recommending aggressive scaling. "
            "Evidence below that threshold is logged but not acted upon."
        ),
    }

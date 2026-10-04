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
    "graded_at", "game_id",
]

_TICKET_COUNTER_FILE = _GOLD / "myboo_counter.txt"


def _ensure_files():
    _GOLD.mkdir(parents=True, exist_ok=True)
    for path, cols in [(_TICKETS_FILE, _TICKET_COLS), (_LEGS_FILE, _LEG_COLS)]:
        if not path.exists():
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(cols)
        else:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                have = set(reader.fieldnames or [])
                rows = list(reader)
            if not set(cols) <= have:
                with open(path, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval="")
                    w.writeheader()
                    w.writerows(rows)


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


def _resolve_game(leg: dict, week: int) -> dict:
    """Attach game_id / game_date from the schedule when a hand-logged leg only names a team.
    Without a game_id the live grader cannot find the leg, so every leg gets one if the schedule knows it."""
    if leg.get("game_id"):
        return {}
    team = (leg.get("team") or "").upper().strip()
    date = leg.get("game_date") or ""
    sched = _GOLD / "schedule.csv"
    if not team or not sched.exists():
        return {}
    with open(sched, newline="") as f:
        rows = [r for r in csv.DictReader(f) if team in (r.get("home_team"), r.get("away_team"))]
    hit = next((r for r in rows if date and r.get("game_date") == date), None) \
        or next((r for r in rows if str(r.get("week")) == str(week) and r.get("game_type", "REG") == "REG"), None)
    return {"game_id": hit["game_id"], "game_date": hit["game_date"], "team": team} if hit else {}


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
    import red_zone
    if red_zone.td_blocked(week) and any(red_zone._has_td(l) for l in legs):   # HARD RULE
        raise ValueError("TD-scorer legs are banned from week 4 on; use red_zone.effort_leg")
    _ensure_files()
    with open(_TICKETS_FILE, newline="") as f:
        for t in csv.DictReader(f):
            if (t["name"], str(t["season"]), str(t["week"])) == (name, str(season), str(week)):
                return t["ticket_id"]
    legs = [{**l, **_resolve_game(l, week)} for l in legs]
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
                "game_id":      leg.get("game_id", ""),
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


# ── daily report engine ───────────────────────────────────────────────────────

def _load_player_stats_by_week() -> dict[tuple[str, str, str], dict]:
    """
    Build (player_id, market, week) → {actual, avg_last4} from all player week CSVs.
    avg_last4 is the rolling 4-game average BEFORE that week (for gap analysis).
    """
    sources = [
        ("player_receiving_week.csv",  {"recyds": "receiving_yards", "recs": "receptions"}),
        ("player_rushing_week.csv",    {"rushyds": "rushing_yards",  "carries": "carries"}),
        ("player_passing_week.csv",    {"passyds": "passing_yards",  "passtd": "passing_tds",
                                        "intsthrown": "passing_interceptions"}),
        ("player_scrimmage_week.csv",  {"rushrec": "scrimmage_yards"}),
    ]
    # raw: player_id → market → [(week_int, value)]
    raw: dict[str, dict[str, list[tuple[int, float]]]] = {}

    for fname, market_cols in sources:
        fpath = _GOLD / fname
        if not fpath.exists():
            continue
        with open(fpath, newline="") as f:
            for row in csv.DictReader(f):
                pid  = row.get("player_id", "")
                wk   = row.get("week", "")
                for market, col in market_cols.items():
                    val = row.get(col)
                    if val:
                        try:
                            v = float(val)
                            raw.setdefault(pid, {}).setdefault(market, []).append((int(wk), v))
                        except (ValueError, TypeError):
                            pass

    result: dict[tuple[str, str, str], dict] = {}
    for pid, markets in raw.items():
        for market, entries in markets.items():
            entries.sort(key=lambda x: x[0])
            for i, (wk, val) in enumerate(entries):
                prev = [v for _, v in entries[:i]][-4:]
                result[(pid, market, str(wk))] = {
                    "actual": val,
                    "avg_last4": round(sum(prev) / len(prev), 1) if prev else None,
                }
    return result


def _load_ib2_for_week(week: str) -> dict[str, dict]:
    """Return (defteam, posteam) → {ib2_score, pre_pressure_rate, ...} for this week."""
    fpath = _GOLD / "ib2_matchups_current.csv"
    out: dict[str, dict] = {}
    if not fpath.exists():
        return out
    with open(fpath, newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("week")) == str(week):
                key = f"{row.get('defteam','?')}v{row.get('posteam','?')}"
                out[key] = {
                    "ib2_score":         row.get("ib2_score"),
                    "pressure_rate":     row.get("pre_pressure_rate"),
                    "int_rate":          row.get("qb_int_1plus_rate"),
                    "sacks_3plus_rate":  row.get("sacks_3plus_rate"),
                    "pass_under_rate":   row.get("pass_under_lines_rate"),
                }
    return out


def _load_injuries_by_player() -> dict[str, str]:
    """player_id → injuryStatus from injury_report_official.csv (latest entry per player)."""
    fpath = _GOLD / "injury_report_official.csv"
    out: dict[str, str] = {}
    if not fpath.exists():
        return out
    with open(fpath, newline="") as f:
        for row in csv.DictReader(f):
            pid    = row.get("player_id", row.get("playerID", ""))
            status = row.get("injuryStatus", row.get("injury_status", ""))
            if pid and status:
                out[pid] = status
    return out


def _load_schedule_by_team() -> dict[tuple[str, str], dict]:
    """(team, week) → {game_date, weekday, roof, temp, wind, spread_line, total_line}"""
    fpath = _GOLD / "schedule.csv"
    out: dict[tuple[str, str], dict] = {}
    if not fpath.exists():
        return out
    with open(fpath, newline="") as f:
        for row in csv.DictReader(f):
            wk = str(row.get("week", ""))
            for team_key in ["home_team", "away_team"]:
                t = row.get(team_key, "")
                if t:
                    out[(t, wk)] = {
                        "game_date":   row.get("game_date", ""),
                        "weekday":     row.get("weekday", ""),
                        "roof":        row.get("roof", ""),
                        "temp":        row.get("temp_actual", row.get("temp", "")),
                        "wind":        row.get("wind_actual", row.get("wind", "")),
                        "spread_line": row.get("spread_line", ""),
                        "total_line":  row.get("total_line", ""),
                    }
    return out


def _affecting_factors(pick: dict, stats: dict, injuries: dict, schedule: dict[tuple[str, str], dict]) -> list[dict]:
    """
    Return a list of factor dicts describing what affected this pick.
    """
    factors: list[dict] = []
    pid    = pick.get("player_id", "")
    market = pick.get("market", "")
    wk     = pick.get("week", "")
    team   = pick.get("team", "")
    result = pick.get("result", "PENDING")

    stat = stats.get((pid, market, str(wk)))
    if stat:
        actual  = stat["actual"]
        avg_l4  = stat["avg_last4"]
        try:
            line_f = float(pick.get("line") or 0)
        except (ValueError, TypeError):
            line_f = 0

        if avg_l4 is not None and line_f > 0:
            delta = avg_l4 - line_f
            if delta > 10:
                factors.append({
                    "type": "LINE_VALUE",
                    "severity": "positive",
                    "label": "Line was conservative",
                    "detail": f"L4 avg {avg_l4} vs line {line_f} (+{round(delta,1)}) — line undervalued player",
                })
            elif delta < -10:
                factors.append({
                    "type": "LINE_VALUE",
                    "severity": "negative",
                    "label": "Line was aggressive",
                    "detail": f"L4 avg {avg_l4} vs line {line_f} ({round(delta,1)}) — line overvalued player",
                })

        if actual is not None and line_f > 0:
            margin = actual - line_f
            pct    = round(margin / line_f * 100, 1) if line_f else 0
            direction = pick.get("direction", "over")
            hit = (actual >= line_f) if direction == "over" else (actual < line_f)
            if not hit and abs(margin) / line_f < 0.08:
                factors.append({
                    "type": "NEAR_MISS",
                    "severity": "warning",
                    "label": "Near miss — variance, not model failure",
                    "detail": f"Missed by {abs(round(margin,1))} ({abs(pct)}% off line) — within noise range",
                })
            if hit and pct > 20:
                factors.append({
                    "type": "LEFT_ON_TABLE",
                    "severity": "info",
                    "label": "Money left on table",
                    "detail": f"Player beat line by {round(margin,1)} ({pct}%) — consider raising threshold",
                })

    inj = injuries.get(pid)
    if inj and inj.upper() not in ("", "ACTIVE", "ACTIVE/FULL"):
        sev = "negative" if result == "MISS" else "warning"
        factors.append({
            "type": "INJURY",
            "severity": sev,
            "label": f"Injury flag: {inj}",
            "detail": f"{pick.get('player_name','')} was listed {inj} — limited snap/target share risk",
        })

    sched = schedule.get((team, str(wk)))
    if sched:
        try:
            wind = float(sched.get("wind") or 0)
            temp = float(sched.get("temp") or 72)
        except (ValueError, TypeError):
            wind, temp = 0, 72
        roof = (sched.get("roof") or "").lower()
        if wind >= 15 and roof in ("outdoors", "open", ""):
            factors.append({
                "type": "WEATHER",
                "severity": "negative" if market in ("passyds", "recyds", "recs") else "neutral",
                "label": f"High wind ({int(wind)} mph)",
                "detail": "Wind suppresses passing volume; passing prop lines may not fully account for it",
            })
        if temp <= 32 and roof in ("outdoors", "open", ""):
            factors.append({
                "type": "WEATHER",
                "severity": "negative",
                "label": f"Freezing conditions ({int(temp)}°F)",
                "detail": "Cold weather reduces passing accuracy and volume historically",
            })

    return factors


def _gap_analysis(all_picks_for_day: list[dict], stats: dict) -> list[dict]:
    """
    Identify signals that were available but not bet on.
    E.g. a player who vastly outperformed with no ticket on them.
    """
    gaps = []
    acted_on = {(p["player_id"], p["market"]) for p in all_picks_for_day}

    for (pid, market, wk), stat in stats.items():
        if (pid, market) in acted_on:
            continue
        actual  = stat["actual"]
        avg_l4  = stat["avg_last4"]
        if avg_l4 is None or actual is None:
            continue
        if actual > avg_l4 * 1.35 and actual > 40:
            gaps.append({
                "player_id": pid,
                "market":    market,
                "week":      wk,
                "actual":    actual,
                "avg_last4": avg_l4,
                "gap_pct":   round((actual - avg_l4) / avg_l4 * 100, 1),
                "note":      f"Outperformed L4 avg by {round((actual-avg_l4)/avg_l4*100,1)}% — no ticket on file",
            })
    gaps.sort(key=lambda x: x["gap_pct"], reverse=True)
    return gaps[:10]


def daily_reports(limit: int = 10) -> list[dict]:
    """
    One verbose report per day that had picks logged, newest first.
    Includes:
      - per-pick result breakdown with affecting factors
      - visual bar data (actual vs line vs L4 avg)
      - gap analysis (strong players with no ticket)
      - daily hit rate, units P&L
      - Jimmy adjustment note
    """
    _ensure_files()
    picks = _load_picks_history()

    stats    = _load_player_stats_by_week()
    injuries = _load_injuries_by_player()
    schedule = _load_schedule_by_team()

    # Group picks by the date portion of generated_at
    by_day: dict[str, list[dict]] = {}
    for p in picks:
        raw_ts = p.get("generated_at", "") or p.get("graded_at", "")
        day    = raw_ts[:10] if raw_ts else "unknown"
        by_day.setdefault(day, []).append(p)

    # Also pull myboo tickets grouped by day
    tickets_by_day: dict[str, list[dict]] = {}
    if _TICKETS_FILE.exists():
        with open(_TICKETS_FILE, newline="") as f:
            for row in csv.DictReader(f):
                day = row.get("created_at", "")[:10]
                tickets_by_day.setdefault(day, []).append(dict(row))

    all_days = sorted(set(list(by_day.keys()) + list(tickets_by_day.keys())), reverse=True)
    reports  = []

    for day in all_days[:limit]:
        day_picks   = by_day.get(day, [])
        day_tickets = tickets_by_day.get(day, [])

        graded_picks  = [p for p in day_picks if p.get("result") in ("HIT", "MISS")]
        pending_picks = [p for p in day_picks if p.get("result") == "PENDING"]
        hits   = sum(1 for p in graded_picks if p["result"] == "HIT")
        misses = sum(1 for p in graded_picks if p["result"] == "MISS")
        hit_rate = round(hits / len(graded_picks), 3) if graded_picks else None

        # Build per-pick detail
        pick_details = []
        for p in day_picks:
            pid    = p.get("player_id", "")
            market = p.get("market", "")
            wk     = p.get("week", "")
            stat   = stats.get((pid, market, str(wk)))
            try:
                line_f   = float(p.get("line") or 0)
                actual_f = float(p.get("actual_value") or 0) if p.get("actual_value") else None
                prob_f   = float(p.get("probability") or 0)
                avg_l4   = stat["avg_last4"] if stat else None
            except (ValueError, TypeError):
                line_f = actual_f = prob_f = avg_l4 = None

            pick_details.append({
                "pick_id":     p.get("pick_id", ""),
                "player":      p.get("player_name", ""),
                "team":        p.get("team", ""),
                "market":      market,
                "direction":   p.get("direction", "over"),
                "line":        line_f,
                "odds":        p.get("odds", ""),
                "probability": prob_f,
                "actual":      actual_f,
                "avg_last4":   avg_l4,
                "result":      p.get("result", "PENDING"),
                "horse_type":  p.get("horse_type", ""),
                "week":        wk,
                "game_date":   p.get("game_date", ""),
                # visual bar: 0–100 relative to max(line, actual, avg)
                "bar": _pick_bar(line_f, actual_f, avg_l4),
                "factors": _affecting_factors(p, stats, injuries, schedule),
            })

        # Gap analysis from stats for this week
        wk_sample = day_picks[0].get("week", "") if day_picks else ""
        week_stats = {k: v for k, v in stats.items() if k[2] == str(wk_sample)} if wk_sample else {}
        gaps = _gap_analysis(day_picks, week_stats)

        # Jimmy adjustment note
        adjustment_note = _jimmy_note(graded_picks, hits, misses)

        # Ticket summary for the day
        pow_tickets = [t for t in day_tickets if t.get("order_type") == "POW"]
        sim_tickets = [t for t in day_tickets if t.get("order_type") == "SIM"]

        reports.append({
            "date":          day,
            "week":          day_picks[0].get("week") if day_picks else day_tickets[0].get("week") if day_tickets else "",
            "total_picks":   len(day_picks),
            "graded":        len(graded_picks),
            "hits":          hits,
            "misses":        misses,
            "pending":       len(pending_picks),
            "hit_rate":      hit_rate,
            "pow_tickets":   len(pow_tickets),
            "sim_tickets":   len(sim_tickets),
            "pick_details":  pick_details,
            "gaps":          gaps,
            "adjustment_note": adjustment_note,
            "headline":      _report_headline(day, hits, misses, hit_rate, day_picks),
        })

    return reports


def _pick_bar(line: float | None, actual: float | None, avg_l4: float | None) -> dict:
    """Return normalized 0–100 values for a 3-bar chart: line, actual, avg_l4."""
    vals = [v for v in [line, actual, avg_l4] if v is not None and v > 0]
    if not vals:
        return {"line": 0, "actual": 0, "avg_l4": 0, "max": 0}
    mx = max(vals) * 1.15
    def norm(v):
        return round(v / mx * 100) if v else 0
    return {
        "line":   norm(line),
        "actual": norm(actual),
        "avg_l4": norm(avg_l4),
        "max":    round(mx, 1),
        "line_raw":   round(line, 1)   if line   else None,
        "actual_raw": round(actual, 1) if actual else None,
        "avg_l4_raw": round(avg_l4, 1) if avg_l4 else None,
    }


def _jimmy_note(graded: list[dict], hits: int, misses: int) -> str:
    if not graded:
        return "No graded picks today — training data pending."
    rate = hits / len(graded) * 100

    # Find which markets missed
    miss_markets = [p.get("market", "?") for p in graded if p.get("result") == "MISS"]
    hit_markets  = [p.get("market", "?") for p in graded if p.get("result") == "HIT"]

    note_parts = [f"{hits}/{len(graded)} picks hit today ({round(rate,1)}%)."]
    if miss_markets:
        from collections import Counter
        top_miss = Counter(miss_markets).most_common(1)
        note_parts.append(f"Recurring miss: {top_miss[0][0]} ({top_miss[0][1]}x) — Jimmy should reduce weight on this market.")
    if hit_markets:
        from collections import Counter
        top_hit = Counter(hit_markets).most_common(1)
        note_parts.append(f"Consistent hit: {top_hit[0][0]} ({top_hit[0][1]}x) — reinforce weight in training payload.")
    if rate < 50:
        note_parts.append("Below 50% today — review structural vs variance failures before next ticket.")
    elif rate >= 72:
        note_parts.append("Above 72% — eligible to unlock scale recommendations for these markets.")
    return " ".join(note_parts)


def _report_headline(day: str, hits: int, misses: int, hit_rate: float | None, picks: list[dict]) -> str:
    if not picks:
        return f"Ticket logged — no picks graded yet"
    rate_str = f"{round(hit_rate*100)}%" if hit_rate is not None else "pending"
    horse_types = list({p.get("horse_type","") for p in picks if p.get("horse_type")})
    horse_str   = " · ".join(horse_types[:2]) if horse_types else "mixed"
    if hit_rate is None or hit_rate == 0:
        return f"{horse_str} — {len(picks)} picks logged, awaiting results"
    return f"{horse_str} — {hits}W/{misses}L ({rate_str} hit rate)"



# ── automatic tracking, take/fake, settlement ────────────────────────────────

import hashlib as _hashlib
import threading as _threading

_LOCK = _threading.RLock()
STAKE = 5.0
WIN_GOAL = 500.0


def _fingerprint(legs: list[dict]) -> str:
    key = "|".join(f"{l.get('name')}:{l.get('prop', l.get('market'))}" for l in legs)
    return _hashlib.sha1(key.encode()).hexdigest()[:6]


def _expand(leg: dict) -> list[dict]:
    """A composite leg (e.g. RB 3+ catches, 75+ rush yds and a TD) is tracked as its gradable parts."""
    base = {"player_name": leg.get("name", ""), "team": leg.get("team", ""), "odds": leg.get("odds", -110),
            "probability": leg.get("probability", ""), "game_id": leg.get("gameId", ""), "game_date": ""}
    comps = leg.get("components")
    if comps:
        return [{**base, "market": c["market"], "direction": c.get("direction", "over"), "line": c.get("line", 0.5)} for c in comps]
    return [{**base, "market": leg.get("market", ""), "direction": leg.get("direction", "over"), "line": leg.get("line") or 0.5}]


def track_slips(slips: list[dict], season: int, week: int, source: str = "BOARD") -> dict[str, dict]:
    """Everything that hits the board is logged once as a FAKE IT (SIM) ticket. Returns slip id -> {ticketId, taken}."""
    out: dict[str, dict] = {}
    with _LOCK:
        for sl in slips:
            if not sl.get("legs"):
                continue
            legs = [p for l in sl["legs"] for p in _expand(l)]
            name = f"{sl.get('title', 'SLIP')} · {sl.get('id', '')} · {_fingerprint(sl['legs'])}"
            tid = create_ticket("SIM", name, legs, season, week, sl.get("boostedAmericanOdds", 0), STAKE, f"{source}")
            order = next((t["order_type"] for t in load_tickets_raw() if t["ticket_id"] == tid), "SIM")
            out[str(sl.get("id"))] = {"ticketId": tid, "taken": order == "POW"}
    try:
        import slip_recap
        slip_recap.snapshot_open()   # freeze the pre-game thesis the moment a slip hits the board
    except Exception:
        pass
    return out


def load_tickets_raw() -> list[dict]:
    _ensure_files()
    with open(_TICKETS_FILE, newline="") as f:
        return list(csv.DictReader(f))


def set_taken(ticket_id: str, taken: bool) -> dict:
    """TAKE IT = real money placed (POW). FAKE IT = paper (SIM). Same ticket either way."""
    with _LOCK:
        rows = load_tickets_raw()
        hit = None
        for r in rows:
            if r["ticket_id"] == ticket_id:
                r["order_type"] = "POW" if taken else "SIM"
                hit = r
        if not hit:
            raise KeyError(ticket_id)
        with open(_TICKETS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_TICKET_COLS)
            w.writeheader()
            w.writerows(rows)
    return {"ticket_id": ticket_id, "order_type": hit["order_type"], "taken": taken}


def _norm(name: str) -> str:
    import data
    return data.normalize_name(name or "")


def _stat_tables():
    """(player_id, week) -> {market: value} from the gold lake, plus first-TD and game results."""
    lake = _GOLD
    st: dict[tuple[str, str], dict[str, float]] = {}

    def put(fname, mapping):
        p = lake / fname
        if not p.exists():
            return
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("season_type", "REG") != "REG":
                    continue
                d = st.setdefault((r["player_id"], r["week"]), {})
                for mk, fn in mapping.items():
                    try:
                        d[mk] = fn(r)
                    except (ValueError, TypeError):
                        pass

    fl = lambda c: (lambda r: float(r[c]))
    put("player_receiving_week.csv", {"recyds": fl("receiving_yards"), "recs": fl("receptions")})
    put("player_rushing_week.csv", {"rushyds": fl("rushing_yards"), "carries": fl("carries")})
    put("player_passing_week.csv", {"passyds": fl("passing_yards"), "passtd": fl("passing_tds")})
    put("player_scoring_week.csv", {
        "anytd": lambda r: float(r["rushing_tds"] or 0) + float(r["receiving_tds"] or 0) + float(r["special_teams_tds"] or 0),
        "kickpts": lambda r: 3 * float(r["fg_made"] or 0) + float(r["pat_made"] or 0),
    })

    first_td: dict[str, str] = {}
    p = lake / "td_log.csv"
    if p.exists():
        best: dict[str, int] = {}
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    pid = int(r["play_id"])
                except ValueError:
                    continue
                if r["game_id"] not in best or pid < best[r["game_id"]]:
                    best[r["game_id"]] = pid
                    first_td[r["game_id"]] = r["scorer_player_id"]

    games = {}
    with open(lake / "schedule.csv", newline="") as f:
        for r in csv.DictReader(f):
            games[r["game_id"]] = r
    return st, first_td, games


def _grade_leg(leg, week, ids, st, first_td, games):
    """Returns (actual, 'HIT'|'MISS') or None when the result is not in the lake yet."""
    mk, direction = leg["market"], leg.get("direction") or "over"
    try:
        line = float(leg.get("line") or 0.5)
    except ValueError:
        line = 0.5
    pid = ids.get((_norm(leg["player_name"]), leg["team"])) or ids.get((_norm(leg["player_name"]), ""))

    if mk in ("recyds", "recs", "rushyds", "passyds", "passtd", "anytd", "kickpts", "carries"):
        d = st.get((pid, str(week))) if pid else None
        if not d or mk not in d:
            return None
        a = d[mk]
        return a, ("HIT" if (a > line if direction == "over" else a < line) else "MISS")

    if mk == "firsttd":
        g = leg.get("game_id")
        if not g or g not in first_td or not pid:
            return None
        return 1.0, ("HIT" if first_td[g] == pid else "MISS")

    if mk in ("nfl_total", "nfl_ml"):
        g = games.get(leg.get("game_id") or "")
        if not g:
            g = next((x for x in games.values() if str(x["week"]) == str(week) and leg["team"] in (x["home_team"], x["away_team"])), None)
        if not g or g.get("home_score") in ("", None):
            return None
        hs, as_ = float(g["home_score"]), float(g["away_score"])
        if mk == "nfl_total":
            a = hs + as_
            return a, ("HIT" if (a > line if direction == "over" else a < line) else "MISS")
        mine, theirs = (hs, as_) if leg["team"] == g["home_team"] else (as_, hs)
        return mine - theirs, ("HIT" if mine > theirs else "MISS")
    return None


def _gross(stake: float, american: float) -> float:
    if not american:
        return 0.0
    return round(stake * (1 + (american / 100 if american > 0 else 100 / abs(american))), 2)


def settle() -> dict:
    """Grade every pending leg the lake has results for, then settle tickets. Idempotent."""
    import data
    with _LOCK:
        _ensure_files()
        with open(_LEGS_FILE, newline="") as f:
            legs = list(csv.DictReader(f))
        with open(_TICKETS_FILE, newline="") as f:
            tickets = list(csv.DictReader(f))
        week_of = {t["ticket_id"]: t["week"] for t in tickets}
        pending = [l for l in legs if l["status"] == "PENDING"]
        if not pending:
            return {"graded": 0}
        ids: dict[tuple[str, str], str] = {}
        for pid, r in data.player_dimension().items():
            ids[(data.normalize_name(r.get("name", "")), r.get("team", ""))] = pid
            ids.setdefault((data.normalize_name(r.get("name", "")), ""), pid)
        st, first_td, games = _stat_tables()
        n = 0
        for l in pending:
            res = _grade_leg(l, week_of.get(l["ticket_id"], 0), ids, st, first_td, games)
            if res:
                l["actual_value"], l["status"] = res[0], res[1]
                l["graded_at"] = datetime.now(timezone.utc).isoformat()
                n += 1
        if not n:
            return {"graded": 0}
        by_t: dict[str, list[dict]] = {}
        for l in legs:
            by_t.setdefault(l["ticket_id"], []).append(l)
        for t in tickets:
            ls = by_t.get(t["ticket_id"], [])
            if not ls or t["status"] in ("SETTLED_WIN", "SETTLED_LOSS"):
                continue
            if any(x["status"] == "MISS" for x in ls):
                t["status"], t["result_units"] = "SETTLED_LOSS", "0"
                t["settled_at"] = datetime.now(timezone.utc).isoformat()
            elif all(x["status"] == "HIT" for x in ls):
                t["status"] = "SETTLED_WIN"
                t["result_units"] = str(_gross(float(t["stake_units"] or STAKE), float(t["payout_odds"] or 0)))
                t["settled_at"] = datetime.now(timezone.utc).isoformat()
            elif any(x["status"] == "HIT" for x in ls):
                t["status"] = "IN_PROGRESS"
        with open(_LEGS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_LEG_COLS, extrasaction="ignore", restval="")
            w.writeheader(); w.writerows(legs)
        with open(_TICKETS_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_TICKET_COLS)
            w.writeheader(); w.writerows(tickets)
        return {"graded": n}


def tracking_summary() -> dict:
    """Everything on the board, FAKE IT vs TAKE IT, by slip type and market, plus the $500 stake-rule progress."""
    _ensure_files()
    tickets = load_tickets_raw()
    with open(_LEGS_FILE, newline="") as f:
        legs = list(csv.DictReader(f))

    def block(rows):
        win = sum(1 for t in rows if t["status"] == "SETTLED_WIN")
        loss = sum(1 for t in rows if t["status"] == "SETTLED_LOSS")
        return {"tickets": len(rows), "wins": win, "losses": loss, "pending": len(rows) - win - loss,
                "hit_rate": round(win / (win + loss), 3) if win + loss else None}

    pow_t = [t for t in tickets if t["order_type"] == "POW"]
    sim_t = [t for t in tickets if t["order_type"] != "POW"]
    staked = sum(float(t["stake_units"] or 0) for t in pow_t if t["status"] in ("SETTLED_WIN", "SETTLED_LOSS"))
    returned = sum(float(t["result_units"] or 0) for t in pow_t if t["status"] == "SETTLED_WIN")
    net = round(returned - staked, 2)

    by_slip: dict[str, list[dict]] = {}
    for t in tickets:
        by_slip.setdefault(t["name"].split(" · ")[0], []).append(t)
    by_market: dict[str, dict] = {}
    for l in legs:
        if l["status"] in ("HIT", "MISS"):
            m = by_market.setdefault(l["market"], {"hit": 0, "miss": 0})
            m["hit" if l["status"] == "HIT" else "miss"] += 1
    return {
        "all": block(tickets), "take_it": block(pow_t), "fake_it": block(sim_t),
        "by_slip": {k: block(v) for k, v in sorted(by_slip.items())},
        "by_market": {k: {**v, "hit_rate": round(v["hit"] / (v["hit"] + v["miss"]), 3)} for k, v in sorted(by_market.items())},
        "legs": {"graded": sum(1 for l in legs if l["status"] in ("HIT", "MISS")), "pending": sum(1 for l in legs if l["status"] == "PENDING")},
        "bankroll": {"stake": STAKE, "goal": WIN_GOAL, "net_wins": net, "staked": round(staked, 2),
                     "progress": round(min(1.0, max(0.0, net / WIN_GOAL)), 3)},
    }

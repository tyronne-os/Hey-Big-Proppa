"""
HEY BIG PROPPA! backend -- thin read-only API over lake/gold/nfl/*.csv.

No compute-routing (Hugging Face / CPU / Google Cloud), no Jimmy the
Greek / Jev integration lives here yet -- both stay NOT WIRED per
HANDOFF_CLAUDE_CODE.md sec 3.9 / sec 7 until they're actually built.

Run:
    cd backend
    .venv/bin/uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import data
import jimmy
import cfb_jimmy
import leaders as leaders_mod
import bpl as bpl_mod
import jimmy_bpl
import parlays as parlays_mod
import parlay_engine as engine_mod
import breakout as breakout_mod
import hot_dog
import jev
import jimmy_hunt
import intelligence
import matchup as matchup_mod
import pow_report
import buddy_cosell as buddy_mod
import tank01
import sportsbook
import grader as grader_mod
import myboo as myboo_mod

app = FastAPI(title="HEY BIG PROPPA! API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only -- local Vite dev server + this API
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/index")
def api_index():
    return list(data.chart_index().values())


@app.get("/api/players/search")
def api_players_search(q: str = ""):
    return data.search_players(q)


@app.get("/api/chart/player_props")
def api_player_props(player_id: str, market: str = "rushyds"):
    if market not in data.PROP_LABELS:
        raise HTTPException(400, f"unknown market '{market}', expected one of {list(data.PROP_LABELS)}")
    return data.player_prop_chart(player_id, market)


@app.get("/api/jimmy_score")
def api_jimmy_score(player_id: str, market: str = "rushyds"):
    """
    JIMMY THE GREEK v2 — composite probability with full signal breakdown.
    Signals: hit-rate, usage, matchup edge, Tank01 projection, DFS salary.
    Modifiers: injury gate, starter gate, regression cut, line movement.
    HEURISTIC, NOT BACKTESTED.
    """
    hit_rate    = data.hit_rate_probability(player_id, market)
    score       = jimmy.jimmy_score(player_id, hit_rate, market_slug=market)
    usage_score = jimmy._usage_index().get(player_id)
    edge        = jimmy.leg_edge(player_id, market)
    opponent    = jimmy.next_opponent(player_id)
    breakdown   = jimmy.confidence_breakdown(player_id, hit_rate, market)
    name = data.player_dimension().get(player_id, {}).get("name", player_id)
    team = data.player_dimension().get(player_id, {}).get("team", "")
    jev_prob = (jev.leg_probability(player_id, name, team, market, "over", None, hit_rate,
                                     usage_score, edge, opponent) if jev.available() else None)
    return {
        "playerId":        player_id,
        "market":          market,
        "hitRate":         hit_rate,
        "usageIndexScore": usage_score,
        "opponent":        opponent,
        "matchupEdge":     edge,
        "eligible":        jimmy.eligible(player_id),
        "matchupGate":     jimmy.matchup_gate(player_id, market),
        "regressionFactor": jimmy.regression_factor(player_id),
        "jevAvailable":    jev.available(),
        "jevProbability":  jev_prob,
        "jimmyScore":      score,
        "breakdown":       breakdown,
        "method":          "v2: hit-rate + usage + matchup + Tank01-projection + DFS-salary "
                           "(equal weight); x injury/starter/regression multipliers; "
                           "+/- line-movement nudge. HEURISTIC, NOT BACKTESTED.",
    }


@app.get("/api/chart/leaders")
def api_leaders(category: str = "RUSHING"):
    return leaders_mod.leaders(category)


@app.get("/api/bpl/nfl-games")
def api_bpl_nfl_games():
    """BIG PROPPA LINE combined-score totals for the next unplayed NFL games."""
    return {"version": bpl_mod.BPL_VERSION, "games": bpl_mod.nfl_game_totals()}


@app.get("/api/bpl/nfl-player")
def api_bpl_nfl_player(player_id: str, market: str = "rushyds"):
    if market not in bpl_mod.NFL_MARKETS:
        return {"error": f"market must be one of {sorted(bpl_mod.NFL_MARKETS)}"}
    return bpl_mod.nfl_player_line(player_id, market, data.player_name(player_id))


@app.get("/api/bpl/cfb-game")
def api_bpl_cfb_game(home: str, away: str, neutral: bool = False):
    return bpl_mod.cfb_game_total(home, away, neutral) or {"error": "no lake data for this matchup"}


@app.get("/api/chart/parlays")
def api_parlays(slip: str = "hot_dogs"):
    fn = parlays_mod.SLIPS.get(slip)
    if fn is None:
        raise HTTPException(400, f"unknown slip '{slip}', expected one of {list(parlays_mod.SLIPS)}")
    return fn()


@app.get("/api/chart/parlays/all")
def api_parlays_all():
    return {slip_id: fn() for slip_id, fn in parlays_mod.SLIPS.items()}


@app.get("/api/parlays/engine")
def api_parlays_engine():
    """
    Jimmy BPL mode: 2-5 leg FanDuel tickets built from Big Proppa Line edges.
    Every ticket is noted by MY BOO as a SIM order (deduplicated).
    """
    slips = jimmy_bpl.build_parlays()
    jimmy_bpl.log_to_myboo(slips)
    return {"slips": slips, "mode": "BPL", "version": bpl_mod.BPL_VERSION}


@app.get("/api/parlays/engine-legacy")
def api_parlays_engine_legacy():
    """
    PAUSED previous engine (COACHES SON, IB CASCADE, VOLUME STACK, SINGLE HERO).
    Kept intact for comparison; not shown on the Big Proppa page.
    """
    return {"slips": engine_mod.run_engine(), "paused": True}


@app.get("/api/jimmy/bpl-legs")
def api_jimmy_bpl_legs():
    """Every FanDuel prop that beats the Big Proppa Line by the value threshold."""
    return {"legs": jimmy_bpl.candidate_legs(), "book": jimmy_bpl.BOOK, "minLegEv": jimmy_bpl.MIN_LEG_EV}


_PAUSED = {"paused": True, "message": "Jimmy's LLM mode is paused. Jimmy now runs on the Big Proppa Line (see /api/parlays/engine).",
           "questions": [], "parlays": [], "exploitParlays": [], "nuggets": []}


@app.get("/api/chart/team_ats_heatmap")
def api_team_ats_heatmap():
    """
    HANDOFF_CLAUDE_CODE.md sec 3.6 "Heat map (missed cover)". Per-game
    cover/miss cells, computed the same way the lake's own ATS view is
    documented to work (docs/HANDOFF.md sec 5.2) but recomputed here
    directly from schedule.csv (spread_line + final scores), since the
    lake only exports the aggregate cover_pct, not a per-game cell grid.
    """
    status = data.chart_status("schedule")
    cells = []
    for g in data.load("schedule"):
        try:
            spread = float(g.get("spread_line") or 0)
            home_score = int(g["home_score"])
            away_score = int(g["away_score"])
        except (ValueError, KeyError):
            continue
        # home team covers if (home_score - away_score) + spread_line > 0
        margin = (home_score - away_score) + spread
        if margin == 0:
            continue  # push
        covered_team = g["home_team"] if margin > 0 else g["away_team"]
        missed_team = g["away_team"] if margin > 0 else g["home_team"]
        cells.append({"team": covered_team, "week": g.get("week"), "covered": True})
        cells.append({"team": missed_team, "week": g.get("week"), "covered": False})
    return {"sourceStatus": status, "cells": cells}


@app.get("/api/chart/dvp")
def api_dvp():
    """Defense-vs-position rank bars, per sec 3.6 'DvP bars' -- from defense_ib_score.csv."""
    status = data.chart_status("defense_ib_score")
    rows = sorted(data.load("defense_ib_score"), key=lambda r: float(r.get("toxicity_index_0_100") or 0), reverse=True)
    return {
        "sourceStatus": status,
        "rows": [
            {"team": r["team"], "toxicity": float(r.get("toxicity_index_0_100") or 0), "category": r.get("ib_category", "")}
            for r in rows[:10]
        ],
    }


@app.get("/api/canvas/nodes")
def api_canvas_nodes():
    """Data-driven node list for the Lake Canvas — statuses reflect live state."""
    index = data.chart_index()
    ok_count = sum(1 for r in index.values() if r.get("status") == "ok")
    total_count = len(index)
    ramp_sub = (
        f"{ok_count}/{total_count} ponds live"
        if total_count > 0
        else "lake/gold/nfl — no index"
    )

    jev_connected = jev.available()
    jimmy_sub = (
        f"composite score · Jev {'connected' if jev_connected else 'disconnected'}"
    )

    return {
        "nodes": [
            {
                "id": "ramp-nfl",
                "type": "lake",
                "name": "RAMP NFL",
                "sub": ramp_sub,
                "chips": [],
                "store": "lake/gold/nfl",
            },
            {
                "id": "ramp-cfb",
                "type": "lake",
                "name": "RAMP CFB",
                "sub": "great-lake-of-data · CFBD + TR",
                "chips": [],
                "store": "great-lake-of-data",
            },
            {
                "id": "jimmy-the-greek",
                "type": "expert",
                "name": "JIMMY THE GREEK",
                "sub": jimmy_sub,
                "chips": ["Jev"],
            },
        ]
    }


@app.get("/api/matchups")
def api_matchups():
    """This week's slate: 5 unit edges per side, records, predicted winner and win %."""
    return {"sourceStatus": data.chart_status("team_game_stats"), "games": matchup_mod.slate()}


@app.get("/api/matchups/backtest")
def api_matchups_backtest():
    """How the predictor did on seasons it never saw, next to always-home and the Vegas favorite."""
    return {"sourceStatus": data.chart_status("matchup_backtest"), "rows": data.load("matchup_backtest")}


@app.get("/api/cfb/status")
def cfb_status():
    """CFB Jimmy connection status: CFBD key, rankings, slate size, hot dogs."""
    return cfb_jimmy.cfb_status()


@app.get("/api/cfb/slate")
def cfb_slate():
    """
    This week's top-25 games with game-level picks.
    Markets: moneyline, ATS, total. NO player props.
    HEURISTIC, NOT BACKTESTED.
    """
    return {"games": cfb_jimmy.cfb_game_slate()}


@app.get("/api/cfb/hot-dogs")
def cfb_hot_dogs():
    """
    2-leg upset alert parlays: unranked or ranked underdog vs ranked favorite
    where the dog has outperformed the favorite on 2+ of 3 metrics
    over the last 3 weeks. Both legs on the same game: Dog ML + Total.
    HEURISTIC, NOT BACKTESTED.
    """
    return {"parlays": cfb_jimmy.cfb_hot_dogs()}


@app.get("/api/cfb/overs")
def cfb_overs(date: str | None = None):
    """
    Games with highest probability of going OVER the total.
    Uses blended offense + defensive leakiness projection vs the line.
    Optional ?date=YYYY-MM-DD to filter to one day. HEURISTIC, NOT BACKTESTED.
    """
    cfb_jimmy.cfb_big_money_overs.cache_clear()
    return {"overs": cfb_jimmy.cfb_big_money_overs(date)}


@app.get("/api/cfb/locks")
def cfb_locks(date: str | None = None):
    """
    Lock cover dogs: strong hot dogs within a realistic win spread,
    with favorable ML odds. These can cover AND win outright.
    Optional ?date=YYYY-MM-DD. HEURISTIC, NOT BACKTESTED.
    """
    cfb_jimmy.cfb_lock_cover_dogs.cache_clear()
    return {"locks": cfb_jimmy.cfb_lock_cover_dogs(date)}


@app.get("/api/cfb/big-money")
def cfb_big_money(date: str | None = None):
    """
    BIG PROPPA BIG MONEY PARLAYS: DOUBLE OVER, UPSET SPECIAL, HOT DOG TRIPLE, DOG FIGHT.
    Optional ?date=YYYY-MM-DD. HEURISTIC, NOT BACKTESTED.
    """
    cfb_jimmy.cfb_big_money_overs.cache_clear()
    cfb_jimmy.cfb_lock_cover_dogs.cache_clear()
    cfb_jimmy.cfb_big_money_parlays.cache_clear()
    return {"parlays": cfb_jimmy.cfb_big_money_parlays(date)}


def _build_nfl_slates() -> dict[str, list[dict]]:
    """
    Run the parlay engine ONCE and bucket qualifying legs by game weekday.
    Returns {weekday_lower: [legs]} — reused by Thu/Sun/Mon horse builders.
    """
    from datetime import datetime, timedelta, timezone

    try:
        slips = engine_mod.run_engine()
    except Exception:
        return {}

    # Team → weekday for upcoming games
    team_weekday: dict[str, str] = {}
    for g in data.load("schedule"):
        if g.get("away_score") or g.get("home_score"):
            continue
        wd = (g.get("weekday") or "").lower()
        for key in ("home_team", "away_team"):
            t = g.get(key)
            if t:
                team_weekday[t] = wd

    # Game times from Tank01 — fetch Sunday and Thursday dates
    game_times: dict[str, str] = {}
    try:
        now = datetime.now(timezone.utc)
        weekday_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                       "friday": 4, "saturday": 5, "sunday": 6}
        for wd_name, wd_num in weekday_map.items():
            days_ahead = (wd_num - now.weekday()) % 7
            target_date = now + timedelta(days=days_ahead)
            date_str = target_date.strftime("%Y%m%d")
            for g in tank01.get_games_for_date(date_str):
                t = g.get("gameTime") or f"NFL {wd_name.upper()}"
                game_times[g.get("home", "")] = t
                game_times[g.get("away", "")] = t
    except Exception:
        pass

    injury_map: dict[str, str] = {}
    try:
        for p in tank01.get_injury_list():
            if p.get("playerID"):
                injury_map[p["playerID"]] = p.get("injuryStatus", "")
    except Exception:
        pass

    buckets: dict[str, list[dict]] = {}
    seen: set = set()
    for slip in slips:
        for leg in slip.get("legs", []):
            prob = leg.get("probability", 0)
            if prob < 0.85:
                continue
            team = leg.get("team", "")
            wd = team_weekday.get(team)
            if not wd:
                continue
            pid = leg.get("playerId")
            key = (pid, leg.get("market"), wd)
            if key in seen:
                continue
            seen.add(key)

            inj_status = injury_map.get(pid or "", "")
            if inj_status.upper() in ("OUT", "IR"):
                continue
            inj_flag = f" ⚠{inj_status}" if inj_status else ""

            name      = leg.get("name", "")
            direction = (leg.get("direction") or "OVER").upper()
            prop      = leg.get("prop", "")
            line      = leg.get("line")
            odds      = leg.get("odds", -110)
            line_str  = f" {line}" if line is not None else ""
            game_time = game_times.get(team) or f"NFL {wd.upper()}"
            day_num   = {"thursday": 3, "monday": 0, "sunday": 6}.get(wd, 6)
            buckets.setdefault(wd, []).append({
                "label":    f"TAKE {name} {direction}{line_str} {prop} · {team}{inj_flag} ({game_time})",
                "odds":     int(odds) if odds is not None else -110,
                "bet":      "player_prop",
                "gameDate": "",
                "gameTime": game_time,
                "day":      day_num,
                "prob":     prob,
            })

    for wd in buckets:
        buckets[wd].sort(key=lambda x: -x["prob"])
    return buckets


def _nfl_sunday_legs() -> list[dict]:
    return _build_nfl_slates().get("sunday", [])


@app.get("/api/cfb/crazy-horse")
def cfb_crazy_horse_endpoint(date: str | None = None):
    """
    CRAZY HORSE mega-parlays: all ≥85% confidence picks grouped by day.
      CRAZY HORSE SATURDAY — CFB Saturday picks
      CRAZY HORSE SUNDAY   — NFL Sunday picks (parlay engine ≥85%)
      SUPER CRAZY HORSE    — Saturday + Sunday combined
    $5 wager. Optional ?date=YYYY-MM-DD. HEURISTIC, NOT BACKTESTED.
    """
    cfb_jimmy.cfb_big_money_overs.cache_clear()
    cfb_jimmy.cfb_lock_cover_dogs.cache_clear()
    cfb_jimmy.cfb_crazy_horse.cache_clear()

    horses: list[dict] = list(cfb_jimmy.cfb_crazy_horse(date))  # CFB Saturday

    def _combine(mls: list) -> int | None:
        return cfb_jimmy._combine_ml(mls)

    def _build_horse(horse_type: str, tag: str, legs: list[dict], reasoning: str = "") -> dict:
        conf = 1.0
        for l in legs:
            conf *= l.get("prob", 0.5)
        return {
            "type":       horse_type,
            "tag":        tag,
            "legs":       legs,
            "parlayOdds": _combine([l["odds"] for l in legs]),
            "confidence": round(conf, 3),
            "wager":      5,
            "reasoning":  reasoning or f"{len(legs)}-leg sweep of ≥85% confidence picks — $5 for a big payout.",
        }

    # ── Run engine ONCE, bucket by weekday ───────────────────────────────────
    nfl_slates = _build_nfl_slates()
    thu_legs = nfl_slates.get("thursday", [])
    nfl_legs = nfl_slates.get("sunday", [])
    mon_legs = nfl_slates.get("monday", [])

    if len(thu_legs) >= 2:
        horses.append(_build_horse(
            "CRAZY HORSE THURSDAY", "THURSDAY NIGHT SWEEP", thu_legs,
            f"{len(thu_legs)} Thursday Night picks ≥85% confidence. Short-week fatigue already priced in.",
        ))

    if len(nfl_legs) >= 2:
        horses.append(_build_horse("CRAZY HORSE SUNDAY", "SUNDAY SWEEP", nfl_legs))

        sat_horse = next((h for h in horses if h["type"] == "CRAZY HORSE SATURDAY"), None)
        if sat_horse:
            super_legs = list(sat_horse["legs"]) + nfl_legs
            horses = [h for h in horses if h["type"] != "SUPER CRAZY HORSE"]
            h = _build_horse(
                "SUPER CRAZY HORSE", "FULL WEEKEND SWEEP", super_legs,
                f"All weekend: {len(sat_horse['legs'])} Saturday CFB + {len(nfl_legs)} Sunday NFL picks.",
            )
            horses.append(h)

    if len(mon_legs) >= 2:
        horses.append(_build_horse(
            "CRAZY HORSE MONDAY", "MONDAY NIGHT SWEEP", mon_legs,
            f"{len(mon_legs)} Monday Night Football picks ≥85% confidence.",
        ))

    return {"horses": horses}


@app.get("/api/team-logos")
def api_team_logos():
    """Team logos (ESPN CDN), colors, and wordmarks from nflverse."""
    rows = data.load("team_logos")
    return {r["team_abbr"]: r for r in rows}


# ── #15 Post-game grader + #25 Season hit-rate dashboard ─────────────────────

@app.get("/api/grader/picks")
def api_grader_picks():
    """All CRAZY HORSE picks stored this season with their grade (HIT/MISS/PENDING)."""
    return grader_mod.season_stats()


@app.get("/api/grader/season-stats")
def api_grader_season_stats():
    """Season hit-rate summary by horse type + HOT DOG backtest 2023-2026."""
    return {
        "crazyHorse": grader_mod.season_stats(),
        "hotDog":     grader_mod.hot_dog_season_stats(),
    }


@app.post("/api/grader/grade")
def api_grader_grade(week: int):
    """Grade all PENDING picks for weeks <= week-1 against actual stat results."""
    return grader_mod.grade_pending(week)


@app.get("/api/ib2")
def api_ib2():
    """
    IB 2.0 (IRRITABLE BOWEL) pass-rush matchup scores for this week, with the
    2023-2025 calibration behind each score. Built by scripts/build_ib2.py.
    """
    status = data.chart_status("ib2_matchups_current")
    return {
        "sourceStatus": status,
        "matchups": data.load("ib2_matchups_current"),
        "calibration": data.load("ib2_bucket_rates"),
        "findings": [
            "Pressure crushes efficiency (EPA/dropback +0.24 clean vs -0.45 pressured) far more than it creates "
            "interceptions (2.2% vs 1.9% per dropback).",
            "Interceptions come from holding the ball: 3.0s+ to throw carries 1.5x the INT rate of under 2.0s; "
            "throws 15+ air yards carry 3.8x the odds of an INT-worthy ball.",
            "Most dangerous state: pressured while trailing by 1-8 in the 4th quarter -- 1.9x the normal INT rate.",
            "Rattle is real but small: on a clean pocket right after being hit, the same QB in the same game throws "
            "an INT-worthy ball ~22% more often (t=2.5).",
            "Pressure with four rushers matters; blitzing does not: pressure-with-four defenses held offenses "
            "19 yds under their passing average in 2025, blitz-heavy defenses held them to even.",
            "A QB's reaction to pressure barely repeats year to year (r=0.12); how long he holds the ball does (r=0.59).",
            "First-half hits lower second-half efficiency but NOT second-half passing yards -- the trailing team "
            "throws more. Don't live-bet a 2H passing under off first-half sacks.",
        ],
        "method": "Weights set on 2023-24, checked on 2025 untouched. Current season uses a play-by-play pressure "
                  "proxy (r=0.72 with true pressure). Lines comparison uses spread/total, not historical prop lines.",
    }


@app.get("/api/target-share")
def api_target_share(team: str | None = None):
    """
    #14 Target share concentration for receiving corps, grouped by team.
    Returns players sorted by share_overall descending. Source: player_usage.csv.
    """
    rows = data.load("player_usage")
    result: dict[str, list[dict]] = {}
    for row in rows:
        pos = row.get("position", "")
        if pos not in ("WR", "TE", "RB"):
            continue
        t = row.get("team", "")
        if team and t != team:
            continue
        try:
            result.setdefault(t, []).append({
                "playerId":    row.get("player_id", ""),
                "name":        row.get("player_name", ""),
                "position":    pos,
                "shareOverall": float(row.get("share_overall") or 0),
                "usageIndex":  float(row.get("usage_index_score") or 0),
                "usageRole":   row.get("usage_role", ""),
                "games":       int(row.get("games") or 0),
                "pctI20":      float(row.get("pct_i20_shrunk") or 0),
                "spineMetric": row.get("spine_metric", "targets"),
            })
        except (ValueError, TypeError):
            continue
    for t in result:
        result[t].sort(key=lambda r: r["shareOverall"], reverse=True)
    return {"teams": result, "season": 2026}


@app.get("/api/myboo/tickets")
def api_myboo_tickets(order_type: str | None = None):
    """All MY BOO tickets (POW + SIM) with embedded legs and live progress."""
    return {"tickets": myboo_mod.load_tickets(order_type)}


@app.post("/api/myboo/tickets")
def api_myboo_create_ticket(payload: dict):
    """
    Create a new POW or SIM parlay ticket.
    Body: {order_type, name, legs, season, week, payout_odds, stake_units, note}
    """
    try:
        ticket_id = myboo_mod.create_ticket(
            order_type=payload.get("order_type", "SIM"),
            name=payload.get("name", "Untitled"),
            legs=payload.get("legs", []),
            season=int(payload.get("season", 2026)),
            week=int(payload.get("week", 1)),
            payout_odds=float(payload.get("payout_odds", 0)),
            stake_units=float(payload.get("stake_units", 1)),
            note=payload.get("note", ""),
        )
        return {"ticket_id": ticket_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/myboo/ledger")
def api_myboo_ledger():
    """Tuesday-to-Tuesday weekly ROI ledger for all POW orders."""
    return {"ledger": myboo_mod.weekly_ledger()}


@app.get("/api/myboo/training-log")
def api_myboo_training_log():
    """
    Jimmy the Greek training payload — hit patterns, failure modes,
    and conservative-to-aggressive scale recommendations derived from graded picks.
    """
    return myboo_mod.training_log()


@app.get("/api/myboo/post-mortem")
def api_myboo_post_mortem():
    """
    Near-miss audit and money-left-on-the-table analysis.
    Identifies structural failures vs variance and recommends aggressive scaling
    only when data lake shows ≥72% hit rate under matching conditions.
    """
    return myboo_mod.post_mortem()


@app.get("/api/myboo/reports")
def api_myboo_reports(limit: int = 10):
    """
    Daily verbose reports — one per day picks were logged.
    Each includes per-pick breakdown, affecting factors (injury/weather/IB/line value),
    visual bar data (actual vs line vs L4 avg), gap analysis, and Jimmy adjustment note.
    """
    return {"reports": myboo_mod.daily_reports(limit)}


@app.get("/api/hotdogs")
def api_hotdogs():
    """This week's underdogs through the Hot Dog indicator, plus the 2023-2025 backtest."""
    return {"sourceStatus": data.chart_status("hot_dog_history"), "games": hot_dog.slate(),
            "backtest": hot_dog.backtest()}


@app.get("/api/pow")
def api_pow():
    """Parlay Orders Won per week and season; a graded week under 75% is flagged as a failure."""
    return pow_report.summary()


@app.get("/api/breakout")
def api_breakout():
    """Opportunity-vs-production breakout signal for RB/WR/TE. HEURISTIC, NOT BACKTESTED."""
    return {"sourceStatus": data.chart_status("player_receiving_week"), "rows": breakout_mod.breakout_table()}


@app.get("/api/news/articles")
def api_news_articles():
    """Buddy Cosell sports reporter articles -- one per Engine slip, backed by
    Jimmy the Greek pond data. HEURISTIC, NOT BACKTESTED."""
    return {"articles": buddy_mod.articles_today()}


@app.get("/api/health")
def health():
    return {"status": "ok", "charts_indexed": len(data.chart_index())}


@app.get("/api/jev_status")
def jev_status():
    """
    Real diagnostic, never the value: which env var name is actually set
    (JEV_API_KEY vs the SDK's default TYPESAFE_API_KEY -- catches a naming
    mix-up), and if a key is present, an actual trivial Jev call so an
    invalid or revoked key shows up as a real auth error, not a false
    "present". Jev IS wired now (parlay_engine.py's _leg()) -- this endpoint
    exists to debug the secret, not to gate whether it's built.
    """
    return jev.diagnose()


@app.get("/api/jimmy/hunt")
def jimmy_hunt_endpoint():
    """
    Jimmy the Greek's daily prop hunt. Cycles 35 standard questions (2 lists)
    through Jimmy's composite score + JEV, returns:
      - questions:       best picks per question with jimmyScore, jevScore, defWeakness
      - parlays:         top 30 2-5 leg combos ranked by geometric mean of combined scores
      - exploitParlays:  same, but all legs must face a notably weak defense (defWeakness >= 0.55)
    Refreshes once per UTC calendar day; subsequent calls within the day are cached.
    """
    if jimmy_bpl.JIMMY_LLM_PAUSED:
        return _PAUSED
    return jimmy_hunt.hunt()


@app.post("/api/jimmy/hunt/refresh")
def jimmy_hunt_refresh():
    """Force a fresh hunt run (ignores the daily cache)."""
    if jimmy_bpl.JIMMY_LLM_PAUSED:
        return _PAUSED
    jimmy_hunt.invalidate_cache()
    return jimmy_hunt.hunt()


@app.get("/api/jimmy/ai-status")
def jimmy_ai_status():
    """Live connection state for all three AI providers: Claude, JEV, NVIDIA."""
    return intelligence.ai_status()


@app.get("/api/jimmy/nuggets")
def jimmy_nuggets():
    """
    Daily AI-collaboration insights: Claude finds overhyped lines + correlations,
    JEV scores each claim as a Noul probability, NVIDIA independently validates.
    Ranked by consensus score. Cached until midnight UTC.
    """
    if jimmy_bpl.JIMMY_LLM_PAUSED:
        return _PAUSED
    return intelligence.nuggets()


@app.post("/api/jimmy/nuggets/refresh")
def jimmy_nuggets_refresh():
    """Force a fresh nuggets run (ignores daily cache)."""
    if jimmy_bpl.JIMMY_LLM_PAUSED:
        return _PAUSED
    intelligence.invalidate_cache()
    return intelligence.nuggets(force=True)


@app.post("/api/jimmy/deep-dive")
async def jimmy_deep_dive(body: dict):
    """
    Ad-hoc RAG query over the lake. Claude analyzes with lake context,
    NVIDIA cross-validates, JEV scores any specific claims found.
    Body: {"query": "Which RBs have the best spot this week?"}
    """
    if jimmy_bpl.JIMMY_LLM_PAUSED:
        return {"error": _PAUSED["message"], "paused": True}
    query = (body.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    return intelligence.deep_dive(query)


# ── Tank01 endpoints ─────────────────────────────────────────────────────────

@app.get("/api/nfl/standings")
def api_nfl_standings():
    """NFL standings by division from Tank01. Falls back to {} if API unavailable."""
    return {"standings": tank01.get_nfl_standings(), "tank01Available": tank01.available()}


@app.get("/api/nfl/games")
def api_nfl_games(date: str | None = None):
    """
    NFL games for a given date (YYYYMMDD, default today) with real kickoff times in CST.
    Used to wire actual game times into CRAZY HORSE SUNDAY legs.
    """
    games = tank01.get_games_for_date(date)
    return {"games": games, "date": date or "today", "tank01Available": tank01.available()}


@app.get("/api/nfl/schedule")
def api_nfl_schedule():
    """Full weekly schedule with kickoff times in CST."""
    return {"games": tank01.get_weekly_schedule(), "tank01Available": tank01.available()}


@app.get("/api/nfl/injuries")
def api_nfl_injuries():
    """
    Current injury list: OUT / IR / Q / D / O / LP designations.
    Refreshed every 5 minutes. Essential for pre-game parlay validation.
    """
    injuries = tank01.get_injury_list()
    return {"injuries": injuries, "count": len(injuries), "tank01Available": tank01.available()}


@app.get("/api/nfl/inactives")
def api_nfl_inactives(week: int | None = None):
    """Official inactives (posted ~90 min before kickoff). Triggers SCRATCHED badge on legs."""
    inactives = tank01.get_inactive_players(week)
    return {"inactives": inactives, "count": len(inactives), "tank01Available": tank01.available()}


@app.get("/api/nfl/depth-charts")
def api_nfl_depth_charts(team: str | None = None):
    """
    NFL depth charts by team and position. Starters are rank=1.
    Optional ?team=BUF to filter to one team.
    """
    charts = tank01.get_depth_charts(team)
    return {"charts": charts, "tank01Available": tank01.available()}


@app.get("/api/nfl/scoreboard")
def api_nfl_scoreboard(date: str | None = None):
    """Live in-game scores (refreshed every 2 min on game days)."""
    scores = tank01.get_daily_scoreboard(date)
    return {"games": scores, "tank01Available": tank01.available()}


@app.get("/api/nfl/projections")
def api_nfl_projections(week: int | None = None):
    """Tank01 fantasy point projections — projected stats by player for the current week."""
    projs = tank01.get_fantasy_projections(week)
    return {"projections": projs, "count": len(projs), "tank01Available": tank01.available()}


@app.get("/api/player/{player_id}/info")
def api_player_info(player_id: str):
    """
    Player info from Tank01 including espnID for headshot URL.
    photoUrl is the ESPN CDN headshot (96x70 px).
    """
    info = tank01.get_player_info(player_id)
    return {"info": info, "tank01Available": tank01.available()}


# ── Sportsbook / Odds API endpoints ──────────────────────────────────────────

@app.get("/api/odds/nfl")
def api_odds_nfl():
    """
    Live NFL lines (spread, total, ML) across major US books.
    Consensus median price. Cached 10 min. Deducts Odds API quota per call.
    """
    lines = sportsbook.get_nfl_lines()
    return {"lines": lines, "count": len(lines), "sbAvailable": sportsbook.available()}


@app.get("/api/odds/cfb")
def api_odds_cfb():
    """Live CFB lines (spread, total, ML). Same structure as /api/odds/nfl."""
    lines = sportsbook.get_cfb_lines()
    return {"lines": lines, "count": len(lines), "sbAvailable": sportsbook.available()}


@app.get("/api/odds/nfl/props")
def api_odds_nfl_props(event_id: str):
    """
    Player prop lines for one NFL event from The Odds API.
    event_id: the game ID returned by /api/odds/nfl.
    """
    props = sportsbook.get_nfl_props(event_id)
    return {"props": props, "count": len(props), "sbAvailable": sportsbook.available()}


@app.get("/api/odds/nfl/movement")
def api_odds_nfl_movement():
    """
    Line movement for all current NFL games vs opening line.
    Returns {gameID: {total_drift, spread_drift, has_movement}} per game.
    """
    lines = sportsbook.get_nfl_lines()
    movement = {g["gameID"]: sportsbook.line_movement(g["gameID"], lines) for g in lines}
    return {"movement": movement, "sbAvailable": sportsbook.available()}


@app.get("/api/odds/best-line")
def api_odds_best_line(team: str, market: str = "h2h"):
    """
    Best available price across all books for one team.
    Returns: {bookmaker, price, eventID}
    """
    result = sportsbook.best_line(team, market)
    return {"result": result, "sbAvailable": sportsbook.available()}


# ── Combined pre-game intelligence for RAMP INDEX ────────────────────────────

@app.get("/api/ramp/gameday")
def api_ramp_gameday(date: str | None = None):
    """
    All-in-one game-day intelligence for the RAMP index page.
    Combines: schedule, live lines, scoreboard, standings, injuries.
    One call powers the full RAMP index view.
    """
    games_t01    = tank01.get_games_for_date(date)
    scoreboard   = tank01.get_daily_scoreboard(date)
    standings    = tank01.get_nfl_standings()
    injuries     = tank01.get_injury_list()
    nfl_lines    = sportsbook.get_nfl_lines()

    # Merge live lines into game entries by home team name
    lines_by_home = {g["home"]: g for g in nfl_lines}

    # Build injury count per team for quick display
    injury_count: dict[str, int] = {}
    for p in injuries:
        t = p.get("team", "")
        if t:
            injury_count[t] = injury_count.get(t, 0) + 1

    # Merge scoreboard into games
    score_by_id = {g["gameID"]: g for g in scoreboard}

    enriched = []
    for g in games_t01:
        live    = score_by_id.get(g["gameID"], {})
        line    = lines_by_home.get(g["home"]) or lines_by_home.get(g["away"])
        home_inj = injury_count.get(g["home"], 0)
        away_inj  = injury_count.get(g["away"], 0)
        enriched.append({
            **g,
            "homeScore":    live.get("homeScore") or g.get("homeScore"),
            "awayScore":    live.get("awayScore") or g.get("awayScore"),
            "quarter":      live.get("quarter"),
            "clock":        live.get("clock"),
            "liveStatus":   live.get("status") or g.get("gameStatus"),
            "totalLine":    line.get("total_line") if line else None,
            "spread":       line.get("spread_home") if line else None,
            "mlHome":       line.get("ml_home") if line else None,
            "mlAway":       line.get("ml_away") if line else None,
            "overOdds":     line.get("over_odds") if line else None,
            "underOdds":    line.get("under_odds") if line else None,
            "homeInjuries": home_inj,
            "awayInjuries": away_inj,
        })

    return {
        "games":     enriched,
        "standings": standings,
        "injuryCount": injury_count,
        "tank01Available": tank01.available(),
        "sbAvailable":     sportsbook.available(),
    }


# Serves the built React app (frontend/dist, produced by the Dockerfile's node stage) for the
# single-container Hugging Face Space deployment -- same-origin, so the frontend's VITE_API_BASE
# is built empty and every /api/* call above already works with no CORS involved. Local dev keeps
# using the Vite dev server directly, so this mount is a no-op unless dist/ actually exists.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")

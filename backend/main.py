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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import data
import jimmy
import leaders as leaders_mod
import parlays as parlays_mod
import parlay_engine as engine_mod
import breakout as breakout_mod
import buddy_cosell as buddy_mod

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
    JIMMY THE GREEK's composite probability for one player+market, with its
    component breakdown -- the same lake-only scoring parlays.py uses, but
    exposed directly for transparency (see backend/jimmy.py for the method).
    """
    hit_rate = data.hit_rate_probability(player_id, market)
    score = jimmy.jimmy_score(player_id, hit_rate, market_slug=market)
    return {
        "playerId": player_id,
        "market": market,
        "hitRate": hit_rate,
        "usageIndexScore": jimmy._usage_index().get(player_id),
        "opponent": jimmy.next_opponent(player_id),
        "opponentToxicity": jimmy._defense_toxicity().get(jimmy.next_opponent(player_id) or ""),
        "regressionFactor": jimmy.regression_factor(player_id),
        "jimmyScore": score,
        "method": "average of {hit-rate-vs-line, usage_index/100, 1 - opponent_toxicity/100}, "
                  "+ redzone boost for TD props, x regression cut on REGRESSION RISK players "
                  "-- HEURISTIC, not backtested",
    }


@app.get("/api/chart/leaders")
def api_leaders(category: str = "RUSHING"):
    return leaders_mod.leaders(category)


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
    Correlation-based parlay engine: finds COACHES SON, IB CASCADE,
    VOLUME STACK, and SINGLE HERO slips from the lake's ponds.
    All legs carry FanDuel prices and >= 85% Jimmy probability.
    Min 30% profit boost on combined odds (HEURISTIC, NOT BACKTESTED).
    """
    return {"slips": engine_mod.run_engine()}


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
    """
    Data-driven node list for the Lake Canvas, per HANDOFF_CLAUDE_CODE.md
    sec 3.3. Two nodes exist today; the shape supports more without a
    frontend code change. JIMMY THE GREEK stays 'harness . not wired' until
    Jev is actually connected (needs JEV_API_KEY as an environment variable
    on this session -- see github.md).
    """
    return {
        "nodes": [
            {
                "id": "ramp-nfl",
                "type": "lake",
                "name": "RAMP NFL",
                "sub": "lake/nfl.duckdb -- schema . ponds . not wired",
                "chips": [],
            },
            {
                "id": "jimmy-the-greek",
                "type": "expert",
                "name": "JIMMY THE GREEK",
                "sub": "harness . not wired",
                "chips": ["Jev"],
            },
        ]
    }


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

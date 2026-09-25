---
title: Big Proppa
emoji: 🏈
colorFrom: yellow
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---
# HEY BIG PROPPA!

An NFL analytics and parlay app built on a real, self-built data lake -- no consensus lines, no
outside picks. Everything the app says is either raw box-score data or a documented, backtested
derivation of it.

- **Lake Canvas** -- player props, leaders, a correlation-based parlay engine (COACHES SON / IB
  CASCADE / VOLUME STACK / SINGLE HERO), and Buddy Cosell's FB NEWS column
- **BIG PROPPA MATCHUP HEAT MAP** -- a fitted, backtested team-vs-team predictor (2023+ modern
  era) scored on five unit matchups (scoring, red zone, ground, air, ball security), plus NFL
  offense/defense power rankings
- **HOT DOG INDICATOR** -- certifies dangerous underdogs by comparing their last 5 games against
  the favorite's on win %, points allowed, 3rd-down %, turnovers, and defense rank; backtested
  2023-2025
- **POW ledger** -- Parlay Orders Won, tracked and graded every week; a board under 75% is a
  failure, cash won is not the measure

Every heuristic is labeled as such and backtested where the lake has the history to do it --
see `docs/HANDOFF.md` and each pond's own module docstring for method and numbers.

## Deployment

This Space builds from the root `Dockerfile`: a Node stage builds the React/Vite frontend, then a
Python stage serves it and the FastAPI backend from one process on port 7860 (`backend/main.py`
mounts `frontend/dist/` as static files, same-origin, no Gradio involved anywhere). The data lake
(`lake/gold/nfl/*.csv`) ships inside the image; `lake/bronze/` (raw nflverse play-by-play) does
not -- it's fully re-derivable via `scripts/build_team_game_stats.py`.

`JEV_API_KEY` is a Space secret (Settings -> Variables and secrets) -- never committed, never
pasted in chat.

The data lake is separately backed up to the private dataset
[AIBRUH/big-proppa-lake](https://huggingface.co/datasets/AIBRUH/big-proppa-lake) via
`scripts/backup_lake_to_hf.py`. Canonical source of truth is
[github.com/tyronne-os/Hey-Big-Proppa](https://github.com/tyronne-os/Hey-Big-Proppa); both this
Space and the dataset are redundancy, not a second source.

## Local dev

```
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

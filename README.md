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

[![Last updated](https://img.shields.io/github/last-commit/tyronne-os/Hey-Big-Proppa?label=last%20updated&color=d9b45a)](https://github.com/tyronne-os/Hey-Big-Proppa/commits)
[![Live app](https://img.shields.io/badge/live-aibruh--big--proppa--live.hf.space-7c3aed)](https://aibruh-big-proppa-live.hf.space)
[![BETTER-VERSE](https://img.shields.io/badge/BETTER--VERSE-docs-ffb81c)](docs/BETTER-VERSE.md)

**Jump to:** [BETTER-VERSE](docs/BETTER-VERSE.md) · [Latest updates](#latest-updates) · [Deployment](#deployment) · [Repo index](INDEX.md)

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

- **[BETTER-VERSE](docs/BETTER-VERSE.md)** -- a town of simulated betters (Sharp, Grinder, Casual, Degen), each with a
  username and a stated ideology, betting FanDuel/DraftKings-legal slips through a real 2024/2025 season at real prices.
  The leaderboard ranks real winnings (no filtering), the Strategy Lab pools many universes to show which parlay
  strategies actually make money, and the results become MY BOO training data for JIMMY and JEV. Live at [/betterverse](https://aibruh-big-proppa-live.hf.space/betterverse); full write-up in
  [docs/BETTER-VERSE.md](docs/BETTER-VERSE.md).

Every heuristic is labeled as such and backtested where the lake has the history to do it --
see `docs/HANDOFF.md` and each pond's own module docstring for method and numbers.

## Latest updates

| Date | Update |
|---|---|
| 2026-10-14 | **BETTER-VERSE Strategy Lab**: pools many universes across both real seasons to show which parlay strategies make money (95% intervals), $5/$10 table limits, and a leaderboard of real winnings. |
| 2026-10-14 | **[BETTER-VERSE](docs/BETTER-VERSE.md)**: named betters in four skill tiers, career view and per-better deep dive; replaces JIMMY in the nav. |
| 2026-10-14 | **Contact Us** page and a working **Join the Waitlist** form on the home page; every submission is stored and emailed to the owner. |
| 2026-10-14 | Gradio-SDK Space hardened in raw mode: no Gradio UI, and a startup failure serves a readable 503 instead of restart-looping. |

The badge at the top always shows the date of the latest commit; the table above is the human-readable changelog.

## Deployment

This Space builds from the root `Dockerfile`: a Node stage builds the React/Vite frontend, then a
Python stage serves it and the FastAPI backend from one process on port 7860 (`backend/main.py`
mounts `frontend/dist/` as static files, same-origin). The live Space can also run as a **Gradio-SDK Space in raw mode**
(`space_gradio/app.py`): it serves that same FastAPI app with no Gradio UI at all, and if the backend ever fails to import it
serves a readable 503 plus `/healthz` instead of crash-looping. The data lake
(`lake/gold/nfl/*.csv`) ships inside the image; `lake/bronze/` (raw nflverse play-by-play) does
not -- it's fully re-derivable via `scripts/build_team_game_stats.py`.

**Contact Us and waitlist email.** `POST /api/contact` and `POST /api/waitlist` store every submission in
`lake/gold/nfl/inbox.jsonl` (gitignored, mirrored to the private dataset) and email it to `INBOX_TO`
(default `tjengineer@berylize.com`). For guaranteed delivery set the Space secrets `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`
(optional `SMTP_PORT`, `SMTP_FROM`). Without them it falls back to the FormSubmit.co relay, which sends a one-time
activation email to the destination address on the first message. Undelivered messages are kept and retried.

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

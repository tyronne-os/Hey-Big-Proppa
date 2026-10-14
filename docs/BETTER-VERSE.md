# BETTER-VERSE

[![Last updated](https://img.shields.io/github/last-commit/tyronne-os/Hey-Big-Proppa?label=last%20updated&color=d9b45a)](https://github.com/tyronne-os/Hey-Big-Proppa/commits)

**A town of simulated sports betters that learns what wins and what loses, and feeds it to MY BOO, JIMMY and JEV.**

- Live page: <https://aibruh-big-proppa-live.hf.space/betterverse>
- Source: [`backend/betterverse_*.py`](../backend), [`frontend/src/pages/BetterversePage.tsx`](../frontend/src/pages/BetterversePage.tsx)
- Back to the [project README](../README.md)

## Why it exists

JIMMY's single season playthrough is one sample. BETTER-VERSE runs a whole town of betters through a real NFL season (2024 or 2025),
each with their own habits, so the data answers the question that matters: **which kinds of slips actually beat the book, which never
cash, and which win consistently**, across every player and every matchup.

## The betters

Every better has a username, a **tier**, a one-line ideology, and rules the simulator enforces.

| Tier | Behaviour |
|---|---|
| **Sharp** | Re-measures which market sides beat the book using only games already played (plus last season). Bets only markets with positive measured edge, 2-3 cross-game legs, small flat stakes, never chases, sits out when nothing qualifies. |
| **Grinder** | Has a favorite bet type but bets like a pro: flat small stakes, at most 3 legs, never chases. |
| **Casual** | Favorite bet type, medium stakes, chases a bad week a little. |
| **Degen** | Long parlays, big stakes, doubles up after losses, follows the crowd. |

13 betting styles (spread parlays, moneyline chalk or dogs, game overs or unders, anytime-TD stackers, QB passing stacks, WR yardage,
rushing, SGP stackers, lottery tickets, ...) are crossed with the tiers. The default roster is **150 betters**; set it up to 2000 for more
training rows. Same `(betters, seed, mix)` always gives the same people, so careers can be followed across seasons.

## Realistic, legal slips

- **Real results** from nflverse player stats and `lake/gold/nfl/schedule.csv` (final scores).
- **Real prices** for games: the actual 2024-25 closing spread, moneyline and total odds. Props are priced at -115; anytime TD from the player's prior scoring rate plus book margin. Prop lines use only games played before that week (no look-ahead).
- **FanDuel/DraftKings combination rules** in [`betterverse_rules.py`](../backend/betterverse_rules.py): no duplicate player+market, no over and under of one market, no spread+moneyline in one game, same-game parlays priced with a correlation haircut.

## The leaderboard ranks proof, not luck

**Proof** is the ROI a better would still have had on a *bad-luck replay of their own season*: their slips are resampled 300 times and the
10th-percentile ROI is kept. One lucky 30x ticket barely moves it; steady, disciplined returns do. Betters with fewer than 15 settled slips
are marked provisional. A **Career** view pools 2024 + 2025 slips for the same betters. Click any better for a deep dive: ideology, rules,
bankroll curve, what they actually bet, best and worst slips, every slip.

## What it has found so far (150 betters, seed 7)

- Discipline shows up as **losing less**, not as beating the house: average proof across both seasons was -43% (Sharp), -44% (Grinder), -63% (Casual), -94% (Degen). No Degen reached the career top 10.
- At realistic prices **no tier is profitable on average**; the book's hold (about 11-25%) is larger than any edge found so far.
- Sharps' measured edges did not persist (rush-yards unders measured +2.6% in 2024, then lost to the price in 2025). A proven edge needs many more universes, keeping only what wins in **both** seasons.

## Data it writes (ready to ingest)

Per run, under `lake/gold/nfl/betterverse/<run_id>/` (not committed; mirrored to the private HF dataset):

| File | Schema | Rows |
|---|---|---|
| `legs.parquet` | `boo.bv_leg.v1` | one per leg: market, side, line, price, actual, hit, void, tier, ... |
| `slips.parquet` | `boo.bv_slip.v1` | one per slip: legs, signature, odds, stake, payout, won, bankroll |
| `bettors.parquet` | `boo.bv_bettor.v1` | one per better: username, tier, ideology, rules, ROI, proof, rank |
| `insights.json` | `boo.bv_insights.v1` | tier comparison, leaderboard, never-cashed and consistent slip shapes, market edges |

**Send to MY BOO** pools runs into `lake/gold/nfl/betterverse_priors.json` (shrunk, capped at +/-5%). JIMMY adds it as a `betterverse` score
signal and JEV falls back on it when a leg has no recent-form read. Live lessons always outrank simulated ones.

## API

`POST /api/betterverse/run` · `GET /api/betterverse/status/{run_id}` · `GET /api/betterverse/runs` · `GET /api/betterverse/insights/{run_id}` ·
`GET /api/betterverse/career?runs=a,b` · `GET /api/betterverse/bettor/{run_id}/{id}` · `POST /api/betterverse/ingest/{run_id}` ·
`GET /api/betterverse/priors` · `GET /api/betterverse/archetypes`

## Run it

```
cd backend && python -m pytest tests/test_betterverse.py     # rules, no look-ahead, determinism, leaderboard
cd backend && uvicorn main:app --port 8000                    # then open /betterverse
```

## Changelog

| Date | Change |
|---|---|
| 2026-10-14 | Renamed from "The Bookie Multiverse" to **BETTER-VERSE**. Named betters, skill tiers, proof leaderboard, career view, deep dive. Nav: BETTER-VERSE replaces JIMMY. |
| 2026-10-14 | First version: 500-bettor season simulator, FD/DK legality rules, realistic pricing, MY BOO ingest, node cluster on the Lake Canvas. |

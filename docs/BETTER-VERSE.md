# BETTER-VERSE

[![Last updated](https://img.shields.io/github/last-commit/tyronne-os/Hey-Big-Proppa?label=last%20updated&color=d9b45a)](https://github.com/tyronne-os/Hey-Big-Proppa/commits)

**A town of simulated sports betters that learns what wins and what loses, and feeds it to MY BOO, JIMMY and JEV.**

- Live page: <https://aibruh-big-proppa-live.hf.space/betterverse>
- Source: [`backend/betterverse_*.py`](../backend), [`frontend/src/pages/BetterversePage.tsx`](../frontend/src/pages/BetterversePage.tsx)
- Back to the [project README](../README.md) · How to play and read the data: [PLAYBOOK.md](PLAYBOOK.md)

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

## Table limits

Everyone starts with **$100** and each better picks a **$5 or $10** base bet. The maximum bet is **$10 until the bankroll reaches $500**,
**$20 until $1,000**, and above $1,000 betters **bet freely** (their own percentage of bankroll). Chasing a losing week can scale a bet up,
but never past the limit.

## The leaderboard ranks real winnings

Nothing is filtered or re-weighted: a rookie who gets hot ranks exactly where the money puts them, and the deep dive shows how they won. That is
data too. A second **Luck-adjusted** view ranks the ROI a better would still have had on a bad-luck replay of their own season (10th percentile
of 300 resamples of their slips), which helps spot repeatable skill. A **Career** view pools 2024 + 2025 for the same betters. Click any better for
a deep dive: ideology, rules, base bet, bankroll curve, what they actually bet, best and worst slips, every slip.

## Strategy Lab: which parlay strategy makes the most money?

One roster is one lucky or unlucky sample, so the Strategy Lab pools **many universes** (different rosters, different random picks) across **every tested real
season**: 20 universes × 150 betters × 3 seasons = 9,000 bettor-seasons and about 196,000 slips in about a minute. For every strategy (style × tier,
tier, style, legs per slip, same-game vs cross-game, exact slip shape) it reports pooled ROI with a **95% confidence interval** (bootstrap over
bettor-seasons), profit per slip, slip hit rate, share of bettor-seasons in profit, ROI in each season, and a **probability ranking** (chance of profit in each season and in every season, chance of beating the field, slip hit probability vs the price-implied probability), and flags for **proven $** (the whole interval
is above zero), **$ every season**, and **beat field**. It also lists the biggest winners and the biggest rookie (Casual/Degen) winners with the slip
that won it.

Limit to keep in mind: every universe replays the same real NFL seasons, so more universes average out the betters' randomness, not what really
happened. Trust strategies that win in **every** season, and use the Strategy Lab's *compare* view to check whether a ranking survives a new season.

## What it has found so far (20 universes × 150 betters, three real seasons: 2023, 2024, 2025)

- **No parlay type is proven to beat the book in every season.** The house kept about **17.4%** of every dollar staked (20.1% in 2023, 11.5% in 2024, 20.9% in 2025). No strategy was profitable with 95% confidence.
- **The earlier two-season "winners" did not survive 2023.** See the comparison below.
- **Closest to break-even: the Sharps** (Edge Hunter · Sharp): **+1.8% ROI (95% range -0.5% to +4.1%)** over 21,766 slips: +8.9% in 2024, +4.1% in 2025, -14.4% in 2023 (the one season with no earlier season to learn from). Grinders -9.5%, Casuals -17.2%, Degens -33.6%.
- **Only one shape was in profit in all three seasons**: a 3-leg slip with one completions-over and two rush-yards-unders (+2.1%, +23.4%, +26.3%; 23% hit vs 15% implied), but its chance of profit in every season is only **39%**. It is on MY BOO's watch list, not taught.
- **Same-game parlays** returned -45.9% vs -13.9% for cross-game slips; **6+ leg slips** lost 43% to 81%; **Lottery Ticket · Degen** lost 62.9%.
- The biggest single winners were rookies hitting **4-5 leg anytime-TD tickets at roughly 150x to over 700x**, yet TD Scorer Stackers lose money overall (-41.5% for Casuals). Rookie wins are real, they just don't repeat.

### Adding a third season changed the answer

Run with identical universes and seed, once on 2024-25 and once on 2023-25 (prop lines re-fitted on 2022 so every test season is out-of-sample):

| Parlay type | Chance of profit on 2024-25 | 2023 ROI | 2024 | 2025 | Chance of profit on all three |
|---|---|---|---|---|---|
| 2-leg rush-yards unders | 100% | -18.1% | +11.0% | +7.1% | 0% |
| 3-leg game-total overs | 72% | -23.3% | +15.6% | +3.2% | 0% |
| 2-leg game-total overs | 70% | -21.3% | +7.6% | +2.6% | 0% |

Of the 5 shapes that looked promising on two seasons, **0 held up and 5 dropped**. (The first published ranking, 80% / 70% / 66%, used lines fitted on 2023 itself; fitting them on 2022 raised the 2024-25 figures to the 100% / 72% / 70% above, and 2023 then erased all three.) One mechanism worth knowing: on the whole 2023 board rush-yards unders hit 55%, but the legs the betters actually picked (they favor high-volume players) hit only 49%. Who you pick matters as much as the market.

## Obsidian vault export

The Strategy Lab can export its report as an **Obsidian vault**: linked notes for every tier, style, strategy, slip shape and big winner, with
Mermaid charts and a pre-colored graph (gold = proven money-maker, red = confident loser, white = a winning better). Download it from the Strategy Lab
(or `GET /api/betterverse/study/{study_id}/obsidian`), unzip, open the folder as a vault in Obsidian, then open Graph view. Code:
[`backend/betterverse_obsidian.py`](../backend/betterverse_obsidian.py). Step by step: [PLAYBOOK.md](PLAYBOOK.md#3-see-the-connections-the-obsidian-vault).

## Data it writes (ready to ingest)

Per run, under `lake/gold/nfl/betterverse/<run_id>/` (not committed; mirrored to the private HF dataset):

| File | Schema | Rows |
|---|---|---|
| `legs.parquet` | `boo.bv_leg.v1` | one per leg: market, side, line, price, actual, hit, void, tier, ... |
| `slips.parquet` | `boo.bv_slip.v1` | one per slip: legs, signature, odds, bankroll before, stake, payout, won, bankroll after |
| `bettors.parquet` | `boo.bv_bettor.v1` | one per better: username, tier, ideology, rules, base bet, ROI, proof, ranks |
| `insights.json` | `boo.bv_insights.v1` | tier comparison, leaderboard, never-cashed and consistent slip shapes, market edges |

Strategy Lab studies live in `lake/gold/nfl/betterverse_studies/<study_id>/study.json` (`boo.bv_study.v1`).

**Send to MY BOO** pools runs into `lake/gold/nfl/betterverse_priors.json` (shrunk, capped at +/-5%) and files study results under `strategies`
(proven money-makers, proven money-losers, ROI by shape and legs per slip). JIMMY adds the priors as a `betterverse` score signal and JEV falls back on
them when a leg has no recent-form read. Live lessons always outrank simulated ones.

## API

`POST /api/betterverse/run` · `GET /api/betterverse/status/{run_id}` · `GET /api/betterverse/runs` · `GET /api/betterverse/insights/{run_id}` ·
`GET /api/betterverse/career?runs=a,b` · `GET /api/betterverse/bettor/{run_id}/{id}` · `POST /api/betterverse/ingest/{run_id}` ·
`GET /api/betterverse/priors` · `GET /api/betterverse/archetypes`

Strategy Lab: `POST /api/betterverse/study` · `GET /api/betterverse/study/status/{study_id}` · `GET /api/betterverse/study/{study_id}` ·
`GET /api/betterverse/studies` · `POST /api/betterverse/study/{study_id}/ingest` · `GET /api/betterverse/study/{study_id}/obsidian`

## Run it

```
cd backend && python -m pytest tests/test_betterverse.py     # rules, limits, no look-ahead, leaderboard, career, study
cd backend && uvicorn main:app --port 8000                    # then open /betterverse
```

## Changelog

| Date | Change |
|---|---|
| 2026-10-14 | **Third season (2023) added** and every study re-run: the two-season winners failed in 2023. Prop-line shading re-fitted on 2022. Strategy Lab gets a season picker and a compare view. |
| 2026-10-14 | **MY BOO harvester**: every run and study is collected automatically (event hooks, startup backfill, scheduled cycles, GitHub Action trigger), packaged into numbered curriculum releases, and used to train JEV in house. See [BOO-CURRICULUM.md](BOO-CURRICULUM.md). |
| 2026-10-14 | **Obsidian vault export** of the Strategy Lab report, and [PLAYBOOK.md](PLAYBOOK.md) (how to play, how to read the data). |
| 2026-10-14 | **Strategy Lab** (pooled universes, 95% intervals, proven/consistency flags), **$5/$10 table limits** ($10 until $500, $20 until $1,000, then free), leaderboard now ranks **real winnings** (luck-adjusted view kept as an option). |
| 2026-10-14 | Renamed from "The Bookie Multiverse" to **BETTER-VERSE**. Named betters, skill tiers, proof score, career view, deep dive. Nav: BETTER-VERSE replaces JIMMY. |
| 2026-10-14 | First version: 500-bettor season simulator, FD/DK legality rules, realistic pricing, MY BOO ingest, node cluster on the Lake Canvas. |

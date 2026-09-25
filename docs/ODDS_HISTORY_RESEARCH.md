# Research: odds history, line movement, and betting-news generation

Research brief, 2026-09-25. The user's five target questions, and what it would
actually take to answer each from the lake. **Research only — no fix built yet**,
pending the user's own proposal to combine with this.

## The five questions, scored

| # | Question | Status today | What it needs |
|---|---|---|---|
| 1 | Who went way over the line | **Cannot answer** | Prop line captured *pre-game* + actual result. Actuals: have. Lines: not captured before games happened. |
| 2 | Predicted to cover and flopped | **Works for TEAMS today.** Players: cannot | Team: closing spread + result — already in `silver.nfl_schedule`. Player: same gap as #1. |
| 3 | Most moneyline/line movement | **Cannot answer** | Two or more *pre-game* snapshots of the same market. Infrastructure exists; had only run once. |
| 4 | Top 10 most-wagered players and why | **Cannot answer honestly** | True money handle. Only available from paid enterprise feeds. Free proxies exist but are NOT handle (see below). |
| 5 | Who sucks at covering | **Works for TEAMS today.** Players: cannot | Same as #2. |

Proof that #2/#5 already work at team level — worst ATS teams, computed from
real closing lines and final scores in the lake:

```
team  games  ats_wins  ats_losses  avg_margin_vs_spread
MIA       2         0           2                 -25.8
ATL       2         0           2                 -23.5
CLE       2         0           2                 -18.5
```

## Sources investigated

### 1. The Odds API — key already available (`THE_ODDS_API_KEY`)
Tested live, all results confirmed by actual HTTP calls:

- Current/upcoming **game lines and player props: available on the free tier.**
  Verified: Josh Allen pass yards 239.5, Justin Herbert 225.5 (DraftKings) for
  LAC@BUF.
- **Historical odds: paid plans only.** Confirmed with an explicit
  `HTTP 401 / HISTORICAL_UNAVAILABLE_ON_FREE_USAGE_PLAN`. Per their docs,
  featured markets go back to mid-2020 and other markets (props) to May 2023 —
  but not on this plan.
- **Cost model, measured:** 1 credit per market, per region, per event call.
  A 4-market call returned `x-requests-last: 4`.
- **Free tier budget reality:** 500 credits/month. A full 16-game slate at 4
  markets = 64 credits per snapshot round → roughly **7 rounds per month**.
  Too thin to be the primary movement tracker on its own.
- Real value: `last_update` timestamps per market, wide book coverage, clean
  JSON, and event IDs that match the lake's schedule.

### 2. RotoWire — already built into this lake
- 22 markets, no key, no documented request cap, `robots.txt` permits
  `/betting/`. Already has an append-only snapshot table and a movement view.
- **This is the natural workhorse for movement tracking** — the cost profile of
  The Odds API free tier makes it unsuitable for frequent polling, while this is
  already integrated and free.

### 3. Covers.com consensus — new find, free, server-rendered
- `https://contests.covers.com/consensus/topconsensus/nfl/overall`
- `robots.txt` allows it (only forum/admin internals are disallowed).
- Data is in the static HTML, no JS execution needed. Confirmed schema:
  `Matchup | Date | Consensus % | Sides (spread) | Picks (counts)`.
  Real row parsed: `NE @ BUF, Sun Oct 04 1:00pm ET, 19% / 81%, +5.5 / -5.5,
  35 / 148 picks`.
- **Critical caveat:** this is the percentage of picks in the *Covers community*,
  plus that community's pick counts. It is **not sportsbook money handle.** It's
  a public-sentiment proxy. Presenting it as "where the money is" would be wrong.

### 4. Sportradar Betting Splits — the real answer to #4, but paid
- Aggregates real wagering data from 150+ bookmakers: share of tickets **and**
  share of money, which is exactly what question #4 asks for.
- Enterprise product; the Insights API key is issued by their support team, not
  self-serve. Not free.

### 5. Others noted
- Action Network splits (tickets vs money) — accessible mainly via third-party
  scrapers; same "is this really handle" question applies.
- BetQL, SportsBettingDime — public-betting percentages, web-facing.
- ESPN's `sports.core.api.espn.com/.../ats` endpoint — tested, returned
  `count: 0` (empty). No loss; ATS is already computed locally from closing lines.

## Two real bugs found while testing the movement mechanism

Taking a second RotoWire snapshot to prove the movement view works surfaced two
defects that would have silently corrupted any line-movement analysis:

### Bug A — `fetched_at_utc` is not UTC
The column is declared `TIMESTAMP` (naive). The loader passes a timezone-aware
UTC datetime, and DuckDB converts it to *local* time and drops the zone on
insert. Run logs showed `01:37 UTC` and `03:04 UTC`; the stored values are
`20:37` and `22:04` — CDT, five hours off, in a column literally named
`fetched_at_utc`. Any time-window or "opening vs closing" logic built on this
would be wrong. Fix direction: declare the column `TIMESTAMPTZ`, or store an
explicit epoch/normalized UTC value.

### Bug B — live in-game lines contaminate "movement"
The movement view reported Drake London's receiving-yards line moving from 60.5
to 174.5 and Bijan Robinson's rushing line +111 — in under three hours. Those
are not pre-game line moves. ATL@GB kicked off at 20:15 ET, and **both**
snapshots were taken after kickoff, so both captured **live in-game** lines,
which re-price continuously as the game unfolds.

The lesson is bigger than the bug: **a snapshot is meaningless without knowing
where it sits relative to kickoff.** Any usable design has to tag each snapshot
as pre-game / in-game / post-game and only compare like with like. Otherwise
"biggest line movement" just surfaces whoever was playing while the scraper ran.

## What this means for the fix

Most of the gap is **operational, not architectural**. The append-only snapshot
table and movement view were already correct — they returned 0 rows purely
because the loader had only ever run once. Taking one more snapshot produced
1,441 movement rows immediately.

So the shape of a fix is roughly:
1. Snapshot on a schedule, and crucially **before kickoff**, not after.
2. Tag every snapshot relative to each game's kickoff, so pre-game movement can
   be isolated from live re-pricing (Bug B).
3. Fix the timestamp storage so windows are trustworthy (Bug A).
4. Accept that question #4 needs either a paid handle feed or an explicitly
   labeled free proxy — not a silent substitution.

Questions 1, 2, 3, and 5 are all reachable **for free** once snapshot discipline
exists. Only #4 genuinely requires paid data to answer honestly.

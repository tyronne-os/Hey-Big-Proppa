---
inclusion: always
---
# frontal-lobe2 — project brief

**Mission:** recreate the *chart design* (columns, dropdown/split controls, catalog of available
charts) for NFL, College Football, NBA, and MLB as SQL schemas, laid out as a spreadsheet
catalog. This is prep work only — no predictions, no live data yet. Phase 2 wires each schema to
a free live-data wrapper; Phase 3 folds everything into a searchable data lake. NHL is deferred
(`docs/NHL_GAP.md` — TeamRankings has no NHL section).

Mirrored to a private Hugging Face Space (`AIBRUH/frontal-lobe2`) as backup and eventual app
host, since the user's models live on Hugging Face. Push to both remotes when committing.

## What's already done (2026-09-24)
1. Pulled a reference HTML snapshot from TeamRankings (logged-in session) into
   `lake/bronze/reference/teamrankings/20260924T222408Z/` (gitignored, local only — do not
   commit raw HTML). Manifest with sha256 per file confirms integrity.
2. Read the HTML structurally (not the data values) via a sub-agent audit — findings are in
   `docs/CHART_AUDIT.md`. Confirmed: a universal 8-column per-stat template
   (`Rank|Team|season|Last 3|Last 1|Home|Away|prior season` + season-year dropdown), consistent
   standings/schedules/projections shapes per league, and ~600 total chart slugs across the 4
   leagues' catalog pages.
3. Two confirmed gaps: the odds board renders client-side via AJAX (no static HTML capture
   possible without a headless browser); per-team ranking tables are only meta-indexed (24
   rating types per league), not sampled.
4. `sql/schema.sql` — canonical schema derived from the audit. `silver.odds_snapshot` is
   explicitly marked PROVISIONAL until the AJAX gap is resolved.

## NFL PFR-style lake (2026 season) — DONE and verified 2026-09-24
Scope per the user: NFL only for now, current season only, going head-to-head with
sportsbook lines (their line vs. our actual per-game data). CFB comes next, same pattern.

- `sql/nfl_pfr_schema.sql` — 7 PFR chart families for players (passing, rushing,
  receiving, scrimmage, defense, scoring, kicking) + returns + PFR advanced
  pass/rush/rec/def, plus `silver.nfl_team_week` with a view per chart family.
  **Week grain** everywhere; season totals are views. Validated against DuckDB v1.5.5.
- `sql/nfl_td_logs.sql` — `silver.nfl_td_log` (one row per TD play) with
  `v_nfl_team_td_log` / `v_nfl_opp_td_log` reproducing PFR's `#all_team_td_log` and
  `#all_opp_td_log` for **all 32 teams from one play-by-play pull** (no per-team fetch).
  Adds down / goal-to-go / yardline context PFR's own chart omits.
- `scripts/ingest_nfl_2026.py`, `scripts/ingest_nfl_td_logs.py` — set-based DuckDB
  loaders (INSERT..SELECT over `read_csv_auto`, ~4s). Idempotent per season.
- **PFR is never fetched.** It returns HTTP 403 behind a Cloudflare bot challenge on
  every path incl. robots.txt, and its ToS bars harvesting. Data comes from nflverse,
  which also mirrors PFR's advanced tables. Full reasoning: `docs/PFR_SOURCE_NOTE.md`.
- Verified load: 2,223 player-week rows/category, 64 team-week, 162 TDs, 32/32 teams
  both scored and allowed, 1,306 players, 501 linked to `pfr_player_id`.
- Local only (gitignored): `lake/nfl.duckdb`, `lake/bronze/nflverse/`, `.pylibs/`.
  duckdb is installed via `pip install --target=.pylibs duckdb` because this box has an
  externally-managed Python (PEP 668) and sudo is blocked by user permissions.

## The "ramp" pattern -- NFL is the first one, done end to end (2026-09-25)
A ramp = one league's full pipeline: sources -> schema -> itemized per-chart CSV
exports -> manifest. Full design in `docs/RAMP_ARCHITECTURE.md`. Applies to
every future league (cfb/nba/mlb/nhl) with the same layout, different adapters.

- `lake/gold/nfl/*.csv` -- 19 itemized chart exports (one CSV per chart, matches
  nflverse's own one-file-per-topic convention) + `_index.csv` manifest (row
  counts, source, status per chart). Regenerate with
  `PYTHONPATH=.pylibs python3 scripts/export_ramp.py`. One chart failing to
  export does not block the others (each wrapped in its own try/except).
- `lake/gold/nfl/player_photos/*.png` -- 1,301/1,301 nflverse-sourced headshots,
  downloaded once (200px, ~51MB total), reused all season. `_index.csv` there
  tracks sha256/status per player. Rebuild: `scripts/cache_player_photos.py`.
- `sql/nfl_props_schema.sql` + `scripts/ingest_rotowire_props.py` -- RotoWire
  player props, 22 markets, scoped to draftkings/fanduel/caesars per user
  request (bet365 requested but not available on this source). Append-only
  snapshots (`gold.nfl_prop_line_rotowire`) for line-movement/CLV tracking.
  Verified load: 18,262 rows across test pulls, real DK/FD/Caesars lines
  confirmed (e.g. Aaron Rodgers pass yards 219.5-220.5 depending on book).
- Full source verification in `docs/DATA_SOURCES.md` -- both nflverse and
  RotoWire's legitimacy/scope were checked directly (HTTP status, robots.txt,
  actual page content), not assumed.

## Sports report room -- DONE and verified for any team (2026-09-25)
Bar set by the user: a beat writer could file a matchup preview from the lake
alone. Full design/verification in `docs/REPORT_ROOM.md`.

- `sql/nfl_report_room_schema.sql` -- official injury report (nflverse),
  ESPN narrative injuries, news (tagged to players/teams via structured IDs,
  not fuzzy text match), transactions.
- `scripts/ingest_nflverse_injuries.py`, `scripts/ingest_espn_news.py` --
  loaders. ESPN via `site.web.api.espn.com` (the commonly-cited
  `site.api.espn.com` 403'd in this environment -- same unofficial-API risk
  already flagged for ESPN elsewhere, different host).
- `scripts/matchup_report.py TEAM_A TEAM_B` -- the actual deliverable. Verified
  end to end on two different real matchups (BUF/LAC and KC/PHI), not just one
  team, confirming the design generalizes.
- Honest gap: final inactives (~90 min pre-kickoff) aren't covered by any
  source used here; this pipeline goes up to the last posted practice-report
  status. Documented, not glossed over.
- Two real bugs found + fixed during verification: a missing SELECT column
  hid real moneyline prices behind "None (None)"; the injury query used
  latest-week-number instead of latest-week-with-data, silently blanking
  status when the current week's Friday report hadn't posted yet.

## Utility room -- every source tweakable/serviceable/replaceable (2026-09-25)
`sources.yaml` + `scripts/sources.py` (list/show/check/enable/disable/run).
One file to see what feeds what, how often, and its confirmed risk profile --
no more discovering a table is silently empty by accident (confirmed
`gold.nfl_prop_line` was dead/superseded and `gold.nfl_player_id_bridge` was
never populated during this session's verification; both now documented
rather than silently sitting there). `check --all` does real HTTP checks --
verified 6/9 sources healthy, the 2 failures match their documented
broken/disabled status exactly. Full detail: `docs/UTILITY_ROOM.md`.

## The Match Page -- lead page for this lake and every future ramp (2026-09-25)
Hardcoded chain, exactly as specified: today -> games today (y/n) -> matchups
-> per-matchup inactives/weather/odds. No model logic; impact scoring is
explicitly deferred to a later "logic engine" phase. Full detail:
`docs/MATCH_PAGE.md`.

- `sql/nfl_schedule_schema.sql` + `scripts/ingest_nfl_schedule.py` -- fixes a
  confirmed real gap: `silver.nfl_game` had NULL home_team/away_team/
  kickoff_utc for every row. `silver.nfl_schedule` (272 games, 2026 season,
  nflverse `schedules` release) is the real, populated replacement for this
  need. Also carries team-level spread/total/moneyline for upcoming games
  (confirmed populated, not historical-only) -- a second odds source
  alongside RotoWire's player props, kept separate (different grain).
- `sql/nfl_match_page_schema.sql` -- the chain as views:
  v_today -> v_games_today_flag -> v_matchups_today -> v_matchup_inactives /
  v_matchup_weather_signal / v_matchup_game_odds / v_matchup_prop_odds ->
  v_match_page_today (rollup).
- `scripts/match_page.py [--date YYYY-MM-DD] [--json]` -- the actual
  deliverable. Verified BOTH branches with real data: today (2026-09-24 ET)
  has a real game (ATL@GB, real spread/moneyline/8 injury entries/10 prop
  lines); 2026-09-25 correctly returns "NO games" and stops cleanly.
- Two real bugs found+fixed while building: (1) host container is CDT not
  UTC -- naive CURRENT_DATE would silently vary by machine, fixed by
  anchoring explicitly to America/New_York; (2) RotoWire's game_id and
  nflverse's game_id are unrelated ID schemes -- joining on game_id directly
  silently returned 0 prop rows even with real data present; fixed by
  joining on team membership instead.
- Added `nflverse_schedule` to the utility room (`sources.yaml`).
- Known gap, documented not hidden: the true final inactives list (~90 min
  pre-kickoff) still isn't covered by any source in this ramp.

## RotoWire promoted to ongoing line-movement source (2026-09-25)
User decision: RotoWire props (already free, already integrated, no request
cap) becomes our own ongoing source for line movement -- snapshot repeatedly
through the week, not once. A SessionStart hook (.kiro/hooks/
rotowire-props-snapshot.json) reminds the agent to keep this fresh.

Two real bugs fixed as part of promoting this to "trusted ongoing source":
- fetched_at_utc was naive TIMESTAMP storing LOCAL time under a column named
  _utc. Fixed to TIMESTAMPTZ; verified real UTC now stored correctly.
- Movement view mixed pre-game and live in-game snapshots (confirmed real
  contamination earlier this session). Fixed with an is_pregame flag,
  computed at load time against our own silver.nfl_schedule kickoff times.
  gold.v_nfl_prop_line_movement now only compares pregame-to-pregame.
- Known gap: RotoWire uses 'LAR' for the Rams, our schedule uses 'LA' --
  is_pregame correctly comes back NULL for that team (no wrong guess) rather
  than silently mismatching. Not fixed yet; noted in sql/nfl_props_schema.sql.

Also: ATS (against-the-spread) last-5/last-10 cover %% is COMPUTED, not
sourced -- confirmed nflverse doesn't publish this stat anywhere in their
catalog. silver.nfl_schedule already has real closing spreads + final scores,
which is 100%% of what's needed. See sql/nfl_schedule_schema.sql
(v_nfl_team_ats_current). Fills naturally as more weeks complete (2 games/
team currently; real last-5 window arrives at week 5).

## Roadmap note: BIG PROPPA alerts (user's term, 2026-09-25)
Phase 3 (tracking/notification alerts) will include "BIG PROPPA alerts" --
high-probability, data-driven parlay alerts. This depends on Lake Logic phase
2's checkdowns being built first. Not started; recorded here so it isn't lost.

## Next concrete tasks (not yet done)
- Extract the full stat/player-stat slug lists from the archived `*_stats.html` /
  `*_player-stats.html` files into `catalog/*.csv` (see `catalog/README.md`).
- Build the spreadsheet deliverable from `catalog/*.csv` + `sql/schema.sql`.
- Resolve the odds-board gap: either a Playwright headless capture of one live odds page per
  league, or inspect the `/ajax/league/v3/odds_controller.php` response shape directly.
- Sample one per-team ranking page per league to confirm/replace the inferred shape.
- Phase 2: wire schemas to live sources per `docs/DATA_SOURCES.md`.

## Working rules for this repo
1. `lake/bronze/` is reference-only and gitignored — raw scraped HTML never gets committed or
   pushed to GitHub or Hugging Face. Only derived docs/schemas/catalogs are versioned.
2. Never commit `.teamrankings_cookies.txt` or any cookie/session file.
3. Keys come from environment variables by name only (see global `03-keys-and-secrets` rule).
4. This repo stays scoped to chart-design/schema work. Prediction logic, edge detection, and
   bet execution belong to a later phase/repo — do not merge that scope in here.
## Player usage / situational-confidence pond -- DONE and verified (2026-09-25)
The user's own indicator, built the way HE builds it: identify two stats first
(the spine), then layer everything else on top. Full detail: `docs/PLAYER_USAGE_INDEX.md`.
- **Layer 1, the spine -- position-gated opportunity:** WR/TE -> targets,
  RB/FB -> rush attempts. Nothing else. QBs excluded entirely.
- **Layer 2, stress -- the actual signal.** User's thesis: "the higher the
  stress level the more they go to who they know." A 4-step stress ladder
  (goal-to-go/inside-5/4th down/one-score-late = MAX; red zone/3rd down/<=2 to
  go = HIGH) and the metric is `confidence_delta` = his intra-team share when
  stress is high MINUS his share when it is not. Volume is what a book already
  prices; the delta is the part a box score does not say.
- Layers 3-5: point-in-time depth chart (surplus vs. listed slot), field-zone
  tiers + location/gap maps, and Yards From Scrimmage / Y-per-touch (reused from
  silver.nfl_player_scrimmage_week, not recomputed).
- **EVERY share is intra-team** per the user -- confidence is measured within a
  coach's own roster, never league-wide. All denominators are that player's own
  team, that same game.
- `sql/nfl_player_usage_schema.sql` + `scripts/ingest_nfl_player_usage.py`.
  New tables: `silver.nfl_opportunity_event` (one row per target or carry, with
  stress level), `silver.nfl_depth_chart_snapshot`. Key views:
  `v_nfl_opportunity_spine`, `v_nfl_stress_split`, `v_nfl_redzone_tiers`,
  `v_nfl_depth_chart_pregame`, `gold.v_nfl_player_usage_components` (facts),
  `gold.v_nfl_player_usage_index` (+ `_by_team`).
- Sources: nflverse `pbp` (same file as the TD logs -- one download feeds both)
  and nflverse `depth_charts` (new source, added to sources.yaml). No new vendor
  was needed. Verified: 3,641 opportunities, 32 teams, 328/329 players matched a
  point-in-time depth rank.
- **ffverse/ffopportunity evaluated and deliberately NOT used in Phase 1** --
  real and current (ep_weekly_2026, ep_pbp_pass/rush_2026 with expected TDs) but
  GPL-3.0, weekly not nightly, and a MODEL output not a fact. (game_id, play_id)
  is preserved so it can join 1:1 as a Phase 2 enrichment.
- **Three real confounds found and fixed, all caught by implausible output:**
  (1) QB sneaks inverted the indicator -- Hurts +36.9% / Barkley -28.2% on the
  same team, and the whole negative tail was RBs on every team. QB carries are
  now excluded from the rush pool; a back competes with backs, not with his
  QB's sneaks. A related bug had the spine GUESSING the gate for unlabeled
  positions, which pulled 4 QBs onto the leaderboard.
  (2) depth_surplus compared a within-position depth rank against a whole-team
  usage rank -- every TE1/RB1 looked negative. Now within position group.
  (3) Small samples faked everything: teams had 0-18 inside-20 opportunities all
  season, so 14 players pinned at a perfect trust score. Added shrinkage (k=4 on
  red-zone denominators, delta scaled by opps/(opps+6)); raw and shrunk both
  exposed.
- `gold.v_nfl_player_usage_index` is a HEURISTIC, clearly labeled as such. Weights live
  in one CTE (stress .34, red zone .22, share .20, depth .12, return .12). NOT
  backtested -- validating it (does a rising score precede a line moving?) is
  Phase 2 and needs a walk-forward test, not a same-season correlation.
- `player_usage_role` ships alongside the score because one number collapses
  cases a bettor must treat differently: THE GUY / CLOSER -- SMALL ROLE, BIG
  MOMENTS / VOLUME ONLY -- BENCHED WHEN IT TIGHTENS / RISING -- OUT-EARNING
  DEPTH CHART / RED ZONE SPECIALIST / INSUFFICIENT SAMPLE.
- Best real find, 2026 wks 1-2: Denver's committee. Dobbins has 68% of the calm
  carries but -45.1% delta; Coleman 9.1% calm and +65.9% delta (9 of 12
  high-stress carries). Two backs, opposite roles, and a market pricing "the
  starter" gets exactly one of them wrong.
- 38 charts now export (was 29), 0 failures. `silver.nfl_depth_chart_snapshot`
  is deliberately NOT exported -- 560k rows / 63MB would trip GitHub's file-size
  warning every commit.
- Also fixed in passing: a corrupted `/usr/bin/bash` string that had been
  interpolated into the rapidapi_player_props_pond risk note in sources.yaml.
### Usage pond corrections from the user (2026-09-25, same day)
- **QB carries belong IN the rush pool -- I was wrong to exclude them.** User:
  "in that situation the team is inside of the 5 yardline therefore qb if he runs
  is counted as a running back in my system because the actual rb is competing
  with the qb in an area where he should get the ball and that too is a
  measurment of the coaches confidence." Inside the 5 is the one place a starter
  should get the ball; a keeper called instead IS the confidence statement.
  Excluding it deleted signal rather than measuring it. Reverted. QBs now appear
  in the spine as `rush_attempts_qb`. Only SCRAMBLES are held out (collapsed
  pocket, not a called play) -- flagged via is_qb_scramble/is_designed_run, never
  dropped. His cross-check against burying starters is v_nfl_redzone_tiers
  (inside-20 + success), which is why the tiers sit beside the stress split.
  What PHI actually shows with the QB restored: Barkley -28.3%, Shipley +19.5%,
  Hurts +31.2% with ZERO inside-5 carries -- so Barkley's drop was never the
  sneak, it is a Shipley committee split the exclusion had hidden.
- **The TD log is a direct correlation to the usage index** -- this is why the TD
  logs were built first. `gold.v_nfl_player_usage_td_correlation` joins the
  confidence read to who actually finished. User's framing: "correlation of
  datas - the relating stats meaning if this than that also - it is how i confirm
  i got the predictive element correct." Flags: AGREEMENT / OPPORTUNITY (trusted,
  has not cashed -- markets price the result not the usage, so the line lags) /
  HOLLOW (scored without trust -- the "bait" profile a book advertises) / QUIET /
  MIXED. Verified: J.Palmer BUF has 2 TDs on ZERO red-zone opportunities.
## Phase 1 remaining, per the user (2026-09-25)
Two sections left, then Phase 1 is DONE:
1. **2026 NFL Leaders and Leaderboards**
2. **Defense rankings by team** -- and this is where QB COMFORT enters. User:
   "in the def we consider the comfortibility of the qb - comfortable qb are calm
   and collective because of their confidence in the offensive line - but what if
   that same line is facing four defensive tackles from hell and two of them lead
   the nfl in sacks - that will cause a qb to go from high comfort to irritable
   from one week to the next. Data lake will know those defensive lines from hell
   because they also allow the defensive backs to eliminate the #1 TARGET REC,
   creating opportunities for the second most targeted rec or even the 3rd - when
   the qb is uncomfortable his trusted people is who he will count on."
   This closes the loop with the usage index: pressure -> discomfort -> he goes to
   who he knows. Inputs ALREADY in the lake: silver.nfl_pfr_adv_passing_week
   (times_pressured/pressured_pct, times_blitzed, times_hurried, times_hit,
   times_sacked) and silver.nfl_pfr_adv_defense_week (def_pressures, def_sacks,
   def_completion_pct, def_yards_allowed_per_tgt, def_adot, def_passer_rating_
   allowed). No new source needed -- verify before assuming.
   The betting thesis this enables: a top-offense WR1 with a big target share is
   what a book uses as BAIT; the lake should know that WR1 is about to face a
   line-wrecking front and will not cover.

## NAMING RULE -- internal labels never reach the backend (2026-09-25, user)
Internal shorthand for sections of this lake is the family's business. It does
NOT appear in table names, view names, column names, file names, chart names, or
any query path -- and it is not to be discussed or explained in artifacts that
leave this machine. Queries are addressed by PLAYER NAME + requested data, or
TEAM + requested stat. Nothing else.
Object naming is plain and descriptive of the mechanics: `player_usage`,
`usage_index_score`, `usage_role`, `opportunity_event`, `stress_split`,
`redzone_tiers`, `depth_chart_pregame`. Apply this to every future section
without being asked again.
NOTE: commits before dd79a7f contain the old naming in git history on both
remotes (both private). Scrubbing history would require a rewrite + force-push
to origin and hf -- NOT done, needs explicit approval.

## Defense pond -- DONE and verified (2026-09-25)
User: skip the leaderboards for now (RotoWire already covers that surface);
go straight to defense, framed explicitly as "a toxic pond" that has major
impact on the predictive performance of the usage-index players. Full detail:
`docs/DEFENSE_TOXICITY.md`.
Kept to exactly the 8 stat columns specified, no more: NFL rank in defense,
rank in sacks, rank in interceptions, points allowed in the 2nd half, team win
%, who gets the sacks (individual), who intercepts the ball (individual), def
rank in turnovers created. 7 of 8 were ALREADY in the lake (nfl_team_week,
nfl_pfr_adv_defense_week, nfl_player_defense_week, nfl_schedule) -- verify
before assuming a gap. Only points-by-half needed a new build: nflverse does
not publish it as a team-week aggregate anywhere, so it's derived from the
same play_by_play file already pulled for the TD log/usage pond (one more
pass over a file on disk, not a new download). Cross-checked against real
schedule final scores for all 32 teams -- max disagreement 0 points.
`sql/nfl_defense_schema.sql` + `scripts/ingest_nfl_defense.py`. New table:
`silver.nfl_points_by_half`. Key views: `v_nfl_team_defense_season` (the 8
columns + rankings, computed here since nflverse publishes no rankings table),
`v_nfl_individual_sacks`, `v_nfl_individual_interceptions`,
`gold.v_nfl_defense_ib_score`, `gold.v_nfl_matchup_toxicity`.
**The IB Score (irritable-bowel score)** is the user's own QB-comfort scale,
CAT 1 (no pressure, RB 100+, multiple WR 60+, 4 pass TD) to CAT 5 (irritated
all game). Per the user: "the evidence is in the stats -- how they are being
scored on and how often." Built as 5 components (pressure, coverage inverted,
takeaways, run-stop inverted, scoring incl. 2nd half), each scaled 0-100
against the REAL league min/max THIS SEASON (recomputed every run -- bounds
move as the season plays out, per the user: "as the season goes it will all
fall in line"), averaged, then mapped onto CAT 1-5. Verified wks 1-2: MIN/LV
top the toxicity list (fewest PA/G, top-5 sack rank); IND bottom at 37 PA/G;
0 teams at CAT 1 yet, which is correct this early -- 5/19/6/2 across CAT 2-5.
`gold.v_nfl_matchup_toxicity` is the join this pond exists for: every
scheduled game's two defenses side by side, meant to pair with a usage-index
player on the opposing offense -- a heavily-featured player on a top offense
(a book's bait) about to face a CAT 4/5 defense is the mismatch this lake was
built to catch.
IB Score is a HEURISTIC, same caveat as the usage index -- not backtested.
45 charts now export (was 39), 0 failures.
## NAMING RULE reminder
Applied to this pond too: no internal shorthand anywhere in object/column/file
names. "defense_ib_score", "ib_category", "toxicity_index_0_100" are plain
descriptive names, not a family label -- confirmed fine to use since IB/toxicity
are the user's own stated terminology for the mechanic, not a euphemism for a
project label. If in doubt on a future pond, ask rather than assume a term is safe.

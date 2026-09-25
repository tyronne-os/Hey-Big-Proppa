# HANDOFF — frontal-lobe2, NFL ramp, Phase 1

Written 2026-09-25. This document exists because a prior session lost context
mid-task and had to re-derive everything from the repo. If you are reading this
after a memory reset: **trust this document's structure, but verify every
number against the live database before acting on it** (queries to run are at
the bottom). This is a snapshot of what was true when written, not a live feed.

If any statement here conflicts with the actual code, config, or database,
**the code is the truth.** Re-derive from source rather than propagate a stale
claim from this file.

---

## 1. What this project is

`frontal-lobe2` is a sports data lake, built one league ("ramp") at a time.
NFL is the first ramp, in progress. The mission, verbatim from
`.kiro/steering/project.md`: recreate chart designs (columns, splits, catalog
of available charts) for NFL, College Football, NBA, and MLB as SQL schemas,
then wire each to a free/legal live-data source, then fold everything into a
searchable lake. NHL is deferred — TeamRankings has no NHL section
(`docs/NHL_GAP.md`).

**Three phases, defined by the user, for every ramp:**

1. **Phase 1 (current)** — schema + real data + derived "ponds" (indicators
   built on top of the base schema). No predictions yet in the strict sense,
   though Phase 1 already includes situational/comparative indicators — see
   §5. "Just the facts" was the original framing but the user explicitly
   authorized exceptions (RotoWire line-movement tracking, the usage/defense
   ponds) as they came up.
2. **Phase 2** — wire in live sources beyond what's built, validate the
   heuristic ponds against real outcomes (backtesting), enrichment joins
   (e.g. ffopportunity expected-points).
3. **Phase 3** — alerts/notifications layer. The user's term for this,
   recorded so it is not lost: **"BIG PROPPA alerts"** — high-probability,
   data-driven parlay alerts. Not started. Depends on Phase 2 validation.

## 2. Two repos, one project, kept in sync

- **Local path:** `/home/him/frontal-lobe2`
- **GitHub (private):** `https://github.com/tyronne-os/frontal-lobe2.git`
  — git remote name `origin`
- **Hugging Face Space (private):** `https://huggingface.co/spaces/AIBRUH/frontal-lobe2`
  — git remote name `hf`

**Convention: every commit gets pushed to both `origin main` and `hf main`.**
The user calls this "save to GitHub and Hugging Face" or "quick save to both
places." Do it every time, not just when asked, unless told otherwise.
`README.md` carries HF Space frontmatter (`sdk: gradio`, etc.) — do not strip
that when editing the README.

As of this writing, `HEAD`, `origin/main`, and `hf/main` are all at commit
`d0c5eaf`. Verify this hasn't drifted (see §9 for the command).

## 3. Environment / tooling facts that will trip you up if forgotten

- **This box has an externally-managed Python (PEP 668).** `pip install` at
  the system level fails. The fix already in place: a local pip target dir,
  `.pylibs/` (gitignored), populated via:
  ```bash
  pip install --target=.pylibs duckdb pyyaml
  ```
  Every script is then run with `PYTHONPATH=.pylibs` prefixed:
  ```bash
  PYTHONPATH=.pylibs python3 scripts/whatever.py
  ```
  If a script errors with `ModuleNotFoundError: duckdb`, this is why —
  install into `.pylibs`, don't try a venv or sudo.
- **Engine is DuckDB.** Database file: `lake/nfl.duckdb` (gitignored,
  rebuildable — never commit it, never assume it exists on a fresh clone; it
  is built by running the ingest scripts).
- **The user is in New Orleans (US Central / America/Chicago).** All
  display-facing times are anchored explicitly to `America/Chicago`, not host
  machine time. The host container itself runs in a different timezone (CDT
  observed during a live check) — a naive `CURRENT_DATE`/`CURRENT_TIMESTAMP`
  silently gives a wrong "today" depending on which machine runs the query.
  This bug was found and fixed once already (`gold.v_today` in
  `sql/nfl_match_page_schema.sql`) — do not reintroduce a naive date/time
  comparison anywhere new.
- **Keys**: per global steering, keys are environment variables by name only,
  loaded from `~/.dev_credentials` / `~/.huggingface_env` / `~/.api_keys_env`
  (last wins). Never print, log, or commit a key value. Relevant ones seen in
  this project: `GITHUB_TOKEN`, `HF_TOKEN`, `THE_ODDS_API_KEY`, a temporary
  RapidAPI key (user said explicitly it will be rotated before going live —
  do not treat it as permanent).

## 4. Naming rule — READ THIS BEFORE NAMING ANYTHING

**Standing rule, given explicitly by the user on 2026-09-25, applies to every
future pond without being asked again:**

> all of these terms like [the internal indicator name] are all our internal
> labels for sections of data but once queried those terms never lead the
> backend — only thing goes for are players name and requested or team stat
> and requested data. keep the trade secret as the families business not to
> be discussed

**What this means concretely:**
- Internal/family shorthand for a section of the lake (the user will tell you
  the term in conversation) **never** appears in: table names, view names,
  column names, file names, chart/export names, or anything in
  `sources.yaml` or the manifest.
- It also does not appear in **anything written to a file that leaves this
  machine** — docs, commit messages, code comments in files that get pushed.
  It is fine to discuss internally in chat with the user, but do not encode it
  into an artifact.
- The query surface is: **player name + requested stat**, or **team + requested
  stat**. Nothing else identifies a query.
- Object naming should be plain and descriptive of the *mechanics*: e.g.
  `player_usage`, `usage_index_score`, `usage_role`, `opportunity_event`,
  `stress_split`, `redzone_tiers`, `defense_ib_score`, `toxicity_index_0_100`.
  Terms like "IB score" / "toxicity" were confirmed OK because the user coined
  them himself as the stated mechanic name, not as the trade-secret label —
  **if you are unsure whether a term is the private label or a legitimate
  mechanic name, ask before using it in a committed file.**
- **A prior mistake, corrected once already:** the indicator described in §5
  was originally built and committed under its internal family name, in table
  names, file names, and doc prose. It was caught and renamed in commit
  `2befee2` (all objects, files, and columns renamed to plain descriptive
  names; doc rewritten neutral). **The old name still exists in git history**
  in commits before `2befee2`, on both remotes (both private repos). Scrubbing
  history requires a rewrite + force-push and was explicitly NOT done —
  it needs the user's explicit approval first, since it's a destructive/hard-
  to-reverse operation on shared remotes.

## 5. The ramp, pond by pond — what exists and why

A **"ramp"** = one league's full pipeline: sources → schema → itemized
per-chart CSV exports → manifest (`docs/RAMP_ARCHITECTURE.md`). A **"pond"** =
a derived indicator or grouped-stat section built on top of the base schema —
the user's term, and it will recur for every future ramp ("every ramp will
have a [X]" was said explicitly about the sports-reporter pond, item 5.3
below — treat that as a standing requirement per ramp, not an NFL-only thing).

### 5.1 Base schema — PFR-style player/team stats (first built)

`sql/nfl_pfr_schema.sql`. Recreates 7 Pro-Football-Reference chart families —
passing, rushing, receiving, scrimmage, defense, scoring, kicking — for both
players and teams, **week grain** (season totals are views, never stored
directly, so a stat correction upstream can't leave totals stale).

**PFR itself is never fetched.** Confirmed HTTP 403 on every path including
`robots.txt` — a Cloudflare bot challenge on the whole domain, and PFR's own
ToS separately prohibits harvesting. Data instead comes from **nflverse**
(`github.com/nflverse/nflverse-data`), an open-data project (CC-BY-4.0) that
republishes the same stats, including a direct mirror of PFR's own advanced
tables (`pfr_advstats` release). Full reasoning: `docs/PFR_SOURCE_NOTE.md`.
**Never attempt to scrape PFR directly, in this or any future ramp** — this
was investigated thoroughly and is a dead end by design (bot wall + ToS), not
a temporary blocker.

Loader: `scripts/ingest_nfl_2026.py`. TD logs (one row per TD play, all 32
teams from one play-by-play pull, two views for "scored" vs "allowed"):
`sql/nfl_td_logs.sql` + `scripts/ingest_nfl_td_logs.py`.

### 5.2 Schedule + Match Page

`sql/nfl_schedule_schema.sql` fixed a real gap: the original `silver.nfl_game`
table had `home_team`/`away_team`/`kickoff_utc` defined but never populated.
`silver.nfl_schedule` (from nflverse's `schedules` release) is the real,
populated replacement — 272 games for the 2026 season, and it also carries
team-level spread/total/moneyline odds for upcoming games (a second odds
source alongside RotoWire's player props, kept in separate tables since the
grain differs).

The **Match Page** (`sql/nfl_match_page_schema.sql` +
`scripts/match_page.py`) is the lead page for the whole lake: a strict,
hardcoded, deterministic query chain per the user's explicit request ("these
are static queries the loop or jobs," "there are things I want hard coded"):
today → games today (yes/no) → matchups → per-matchup inactives/weather/odds.
**No model logic in this chain.** Impact scoring of any signal here is
explicitly deferred to a later "logic engine" phase — this layer only
surfaces raw signal, never judges it. Do not add scoring/weighting logic
directly into the Match Page views; build it as a separate layer that reads
from them.

Also computed here (not sourced — nflverse has no such stat): ATS
(against-the-spread) rolling cover % — `v_nfl_team_ats_current` /
`_rolling` / `_game`, built from real closing spreads + real final scores
already in `silver.nfl_schedule`.

### 5.3 Sports report room — "every ramp will have one of these"

`sql/nfl_report_room_schema.sql` + `scripts/ingest_nflverse_injuries.py` +
`scripts/ingest_espn_news.py` + `scripts/matchup_report.py`. **This is the
first appearance of the sports-reporter pond, and the user has stated every
future ramp gets one of these.** The bar the user set: a beat writer should
be able to file a matchup preview from the lake alone, no browser tab open.

Covers: official weekly injury report (nflverse — practice status, game
status, injury type), ESPN narrative injury context (why it matters, who
benefits), news (headlines tagged to players/teams via structured IDs, not
fuzzy text matching), and transactions (signings/releases/trades).

ESPN access note: `site.web.api.espn.com` is used because the more commonly
documented `site.api.espn.com` returns HTTP 403 in this environment. Both are
**unofficial, undocumented APIs** — no ToS grant, can change or vanish without
notice. This is the single highest-risk source in the whole ramp. Check
`sources.yaml`'s `last_verified` date for `espn_news` before trusting it
blindly if meaningful time has passed.

**Known, documented, unfixed gap:** the NFL's true final inactives list is
released ~90 minutes before kickoff. No source in this ramp covers that
specific timing — the official injury report is the closest proxy and is
explicitly labeled as such (`'practice_report_proxy -- NOT the final
inactives list'` appears literally in the view output). Do not present this
proxy as the real inactives list.

The deliverable: `scripts/matchup_report.py TEAM_A TEAM_B` — verified end to
end on two different real matchups, not just one, confirming the pattern
generalizes.

**When building this pond for a future ramp (CFB/NBA/MLB), reuse this exact
shape**: official injury feed + a narrative/news feed + a matchup-bundler
script that returns one team's full bundle, called twice and stitched
together — do not redesign the pattern from scratch.

### 5.4 The Utility Room — source management

`sources.yaml` (the manifest, one entry per data source) + `scripts/sources.py`
(CLI: `list` / `show` / `check --all` / `enable` / `disable` / `run`). This is
where every source's status, cadence, risk profile, and replacement candidates
live. **Before adding any new data source in any future ramp, add it here
first** — this is the single place to check "is this source healthy" without
hunting through ingest scripts.

Current sources (`sources.yaml`, check `status` field for current truth):
`nflverse_stats`, `nflverse_pbp`, `nflverse_pbp_defense` (same pbp file,
different aggregate), `nflverse_depth_charts`, `nflverse_injuries`,
`nflverse_schedule`, `rotowire_props`, `espn_news`, `player_headshots` — all
`active`. `rapidapi_player_props_pond` — `tested_mostly_redacted` (free tier
redacts movement/history/trends; usable only as a current-odds snapshot).
`draftkings4_rapidapi` — `active` but budget-constrained (300 total requests
on the plan, not daily — see `scripts/ingest_draftkings4.py`, which is
incomplete/rationed by design). `teamrankings_reference` — `deprecated`
(design-reference only, never loaded into silver/gold). `pfr_direct` —
`broken` (kept on record to document why PFR is ruled out, not to retry it).
`tank01_rapidapi` — `disabled` (documented option, needs the user's own live
key test before building).

### 5.5 RotoWire player props — the line-movement source

`sql/nfl_props_schema.sql` + `scripts/ingest_rotowire_props.py`. Pulls
RotoWire's own first-party embedded JSON (confirmed: `robots.txt` allows
`/betting/`; the paywall flag only gates their CSV *export* button, not the
underlying data visible to any visitor). 22 markets, scoped to
draftkings/fanduel/caesars per user request (bet365 requested but does not
exist on this source at all — would need a different source entirely).

**Promoted to an ongoing tracked source** (user decision, 2026-09-25): this is
the lake's own free line-movement tracker, since it's free and has no request
cap. `.kiro/hooks/rotowire-props-snapshot.json` is a SessionStart hook that
reminds the agent to keep re-snapshotting through the week — **check whether
this hook still exists and still fires** if picking this back up after a gap;
if it's missing, re-create it (see the hook's own JSON for the exact prompt
text, or `createHook` with trigger `SessionStart`).

Two real bugs found and fixed here, both worth knowing so they aren't
reintroduced elsewhere: (1) `fetched_at_utc` was declared as a naive
`TIMESTAMP` and silently stored **local** time under a column literally named
`_utc` — fixed by declaring it `TIMESTAMPTZ`. **Any new timestamp column
that claims to be UTC must be `TIMESTAMPTZ`, not `TIMESTAMP`** — this
exact bug recurred in a second table later (see the depth-chart snapshot
table, §5.6) and was caught before shipping because of this precedent. (2)
The line-movement view was mixing pre-game and live in-game snapshots,
producing a fake "60.5 → 174.5" move that was actually two in-game
re-pricings of a game already underway — fixed with an `is_pregame` flag
computed against the lake's own schedule kickoff times. **Any snapshot-style
table needs a point-in-time discipline like this — never compare two
snapshots without knowing where each sits relative to the event they
describe.**

Known unfixed gap: RotoWire uses team code `LAR` for the Rams; this lake's
schedule uses `LA`. `is_pregame` correctly comes back `NULL` for that team
(no wrong guess) rather than silently mismatching — not fixed, noted in the
SQL file's comments.

### 5.6 Player usage & situational-confidence pond (built 2026-09-25)

**File names, deliberately plain per §4:** `sql/nfl_player_usage_schema.sql`
+ `scripts/ingest_nfl_player_usage.py` + `docs/PLAYER_USAGE_INDEX.md`.

**What it measures**, per the user's own definition, built in the exact order
he specified — two stats first (the "spine"), then every other stat layered
on top:

- **Layer 1, the spine — position-gated opportunity.** WR/TE → targets.
  RB/FB → rush attempts. **QB → rush attempts too** (this was corrected once
  — see below). The gate is strictly positional with **no inference** — an
  earlier version guessed the gate for unlabeled positions and that silently
  pulled quarterbacks in mislabeled; don't reintroduce inference-based gating.
- **Layer 2, stress — the actual signal.** The user's thesis, verbatim: "the
  higher the stress level the more they go to who they know." A 4-step
  stress ladder built only from real play-by-play fields (down, distance,
  quarter, score, clock) — see the SQL file's `STRESS` CASE expression for
  the exact thresholds. The core metric, `confidence_delta`, is: (his share
  of his team's opportunities when stress is high) MINUS (his share when it
  is not). **Positive delta = the offense leans on him more as it tightens.**
  This delta, not raw volume, is the actual indicator — volume alone is
  already priced by a sportsbook.
- **Layers 3–5**: point-in-time depth chart (surplus vs. published rank,
  compared **only within the same position group** — comparing across
  groups was a real bug, fixed), field-zone tiers (Inside 20/10/5, PFR-chart
  shaped), and Yards From Scrimmage / yards-per-touch (reused from the
  already-existing `silver.nfl_player_scrimmage_week`, not recomputed).

**Every share is intra-team** — computed against that player's own team's
total in that same game, never league-wide. This was explicit and repeated by
the user: the measurement is confidence *within a coach's own roster*.

**A real correction happened mid-build, and it matters for how you should
treat "confounds" going forward:** an early version excluded QB carries from
the rush pool, reasoning that goal-line sneaks were a structural artifact
crushing every back's stress share (Hurts +36.9% / Barkley −28.2% on the same
team looked implausible). **The user corrected this, and he was right**:
inside the 5-yard line is the one place a starting back should get the ball,
so a coach calling a QB keeper there instead *is* the confidence measurement,
not noise obscuring one. The exclusion was reverted. **Lesson for future
work: when a result looks like an artifact, describe it to the user before
"fixing" it by removing data — the apparent artifact may be the actual
finding.** The one distinction that *was* kept: a **designed** QB run
(sneak/keeper/draw) is a coaching decision and counts; a **scramble** is a
collapsed pocket and does not — both are flagged in the data
(`is_qb_scramble` / `is_designed_run`), never silently dropped.

Base new tables: `silver.nfl_opportunity_event` (one row per target or carry,
with the stress level attached) and `silver.nfl_depth_chart_snapshot` (a
point-in-time series from nflverse's `depth_charts` release — 197 snapshot
timestamps, all 32 teams, ~560K rows; **deliberately NOT exported to CSV** —
it's 63MB raw and would trip GitHub's file-size warning on every commit; it
lives only in the database).

Key views: `silver.v_nfl_opportunity_spine`, `silver.v_nfl_stress_split`,
`silver.v_nfl_redzone_tiers`, `silver.v_nfl_depth_chart_pregame`,
`gold.v_nfl_player_usage_components` (facts only, no weighting — read this
if you distrust the score below), `gold.v_nfl_player_usage_index` (the
weighted score + `usage_role` classification), `gold.v_nfl_player_usage_by_team`
(ranked within one team), `gold.v_nfl_player_usage_td_correlation` (see next
paragraph).

**The TD-log correlation is a deliberate design requirement from the user, not
an afterthought** — he stated the TD logs were built *specifically* to make
this join possible later: "that TD log is a direct correlation to [the usage
pond] ... if this then that also ... it is how i confirm i got the predictive
element correct." `gold.v_nfl_player_usage_td_correlation` joins the usage
read to `silver.nfl_td_log` and flags: `AGREEMENT` (trusted and finishing),
`OPPORTUNITY` (trusted, hasn't cashed a TD yet — where a market's TD line
likely lags), `HOLLOW` (scored without usage backing it — fragile, the
"bait" profile a sportsbook would advertise), `QUIET`, `MIXED`.

**The score is a heuristic, explicitly labeled as such in its own SQL
comments — it has NOT been backtested.** Weights live in one CTE
(`stress .34, redzone .22, share .20, depth .12, return .12`) so they change
in one place. Validating this (does a rising score precede real line
movement or actual production?) is Phase 2 work requiring a walk-forward test
on point-in-time data — a same-season correlation is not sufficient evidence
and should not be presented as validation.

Deliberately evaluated and **not used** as a source for this pond:
`ffverse/ffopportunity` (expected fantasy points, play-grain, real and
current — verified live) — excluded because it's GPL-3.0 (vs. CC-BY-4.0
everywhere else in this lake), updates weekly not nightly, and is a **model
output**, not an observed fact, which conflicts with the Phase 1 "facts only"
default. `(game_id, play_id)` is preserved on the event table specifically so
this can be joined 1:1 later if Phase 2 wants it.

### 5.7 Defense pond — "the toxic pond" (built 2026-09-25)

`sql/nfl_defense_schema.sql` + `scripts/ingest_nfl_defense.py` +
`docs/DEFENSE_TOXICITY.md`.

**Why this pond exists, per the user**: every other pond measures an
offensive player against his own team. This one measures the **opposing
defense** he's about to face, because that defense determines whether a
usage-pond read actually converts into real production against a sportsbook
line. The user's framing: measure defenses "by toxicity" to a quarterback's
comfort.

**Kept to exactly 8 stat columns, per explicit user instruction — do not
expand this list without being asked:**
1. NFL ranking in defense (scoring defense)
2. Ranking in sacks
3. Ranking in interceptions
4. Points allowed in the 2nd half
5. Team win percentage
6. Who gets the sacks (individual player)
7. Who intercepts the ball (individual player)
8. Defensive rank in turnovers created

**7 of these 8 were already sitting in the lake** from tables built earlier
(`nfl_team_week`, `nfl_pfr_adv_defense_week`, `nfl_player_defense_week`,
`nfl_schedule`) — **verified this before assuming any gap existed.** Only
#4 (points allowed in the 2nd half) required new work, since nflverse
publishes no such team-week aggregate anywhere in its catalog. It's derived
from the same `play_by_play` file already pulled for the TD log and usage
pond — one more pass over a file already on disk. **Cross-checked against
real final scores in `silver.nfl_schedule` for all 32 teams — verified exact
agreement (max disagreement: 0 points)** before trusting it.

Rankings (`rank_scoring_defense`, `rank_sacks`, `rank_interceptions`,
`rank_turnovers_created`) are computed in `silver.v_nfl_team_defense_season`
— nflverse publishes no pre-ranked table, same reason ATS is computed rather
than sourced (see §5.2). Turnovers created = interceptions + fumbles forced
(nflverse has no combined column; it's summed from the two it does have).

**The IB Score** (the user's own coined term, confirmed safe to use per §4 —
it stands for "irritable bowel," his own metaphor for quarterback comfort,
not the private family label): a 1–5 category, CAT 1 = totally comfortable
(no pressure, a back over 100 rushing, multiple receivers over 60, four
passing TDs — the user's own literal description of what CAT 1 looks like)
to CAT 5 = irritated and aggravated all game. Built from 5 components, each
scaled 0–100 against the **real league min/max for the current season**
(recomputed on every ingest run — the scaling bounds move as the season
progresses, which the user explicitly wants: "as the season goes it will all
fall in line," i.e. do not hardcode a fixed scale that ignores where the
league actually is right now): pressure (sacks + hits + tracked pressures per
game), coverage (passer rating allowed, inverted), takeaways (INT + forced
fumbles per game), run-stop (rushing yards allowed per game, inverted), and
scoring (points allowed per game, including specifically the 2nd half).

`gold.v_nfl_defense_ib_score` carries both the 0–100 continuous
`toxicity_index_0_100` and the 1–5 `ib_score` / `ib_category` mapping.
`gold.v_nfl_matchup_toxicity` is **the join this whole pond exists for** —
every scheduled game's two defenses side by side, meant to be joined against
a usage-pond player on the opposing offense. The bait-detection logic the
user described: a heavily-featured player on a strong offense (the name a
sportsbook uses to draw a bet) about to face a CAT 4/5 defense is the exact
mismatch this lake was built to surface. **This specific join
(`gold.v_nfl_player_usage_index` × `gold.v_nfl_matchup_toxicity` on the
opposing team) has been smoke-tested but not built as its own persisted
view yet — that is a natural next step if not already done by the time you
read this.**

Same heuristic caveat as the usage pond: **not backtested.** Verified only
for internal consistency and plausibility on weeks 1–2 real data (Minnesota
and Las Vegas correctly top the toxicity list with the league's stingiest
scoring defense; Indianapolis correctly sits at the bottom giving up the
most points per game; zero teams have earned CAT 1 yet, which is the
statistically correct read this early in a season, not a bug).

### 5.8 Explicitly skipped / deferred by the user

- **2026 NFL Leaders and Leaderboards** — the user explicitly said to skip
  this "for now," reasoning that RotoWire's own page already covers that
  surface adequately. **This is deferred, not cancelled** — if the user asks
  to pick Phase 1 back up and this hasn't been mentioned, ask whether it's
  still in scope before assuming it was dropped for good.
- **`scripts/ingest_draftkings4.py`** is intentionally incomplete/rationed —
  a hard 300-request budget on that RapidAPI plan (confirmed via the
  `x-ratelimit-requests-limit` header, not a daily reset). Do not increase its
  call frequency without re-checking the remaining budget
  (`lake/bronze/draftkings4/_budget_log.jsonl` tracks usage).
- **Third RapidAPI odds source** (possibly hosted under a name like
  `nikitaiakovleve33` or similar, seen only in a screenshot) — base
  path/host was never confirmed. Investigation was abandoned in favor of the
  usage/defense ponds. Not resolved either way.
- **A cross-source ESPN-athlete-ID ↔ nflverse-gsis_id bridge**
  (`gold.nfl_player_id_bridge`) exists as a table but is **0 rows, never
  populated.** `matchup_report.py` works around this by matching on team +
  player name instead. Do not assume this bridge is usable until it's
  actually built.

## 6. What Phase 1 still needs before it's "done" (per the user's own framing)

As of this writing, the user has not yet declared Phase 1 complete. Sections
built: base schema, TD logs, schedule, Match Page, report room, Utility Room,
RotoWire props, usage pond, defense pond. Leaders/leaderboards were
explicitly skipped (see §5.8). **Ask the user directly what remains** rather
than assuming the list above is exhaustive — this document may itself be
written before Phase 1's actual end, and a future session should confirm
current status rather than trust this section blindly.

## 7. Hard-won lessons — do not relearn these the expensive way

1. **PFR cannot be scraped.** Confirmed 403 + Cloudflare + ToS bar. Don't
   retry it in any future ramp either — the same publisher (Sports Reference)
   runs the equivalent site for other leagues, and the same access wall
   almost certainly applies. Go straight to the open-data mirror.
2. **Any timestamp claiming to be UTC must be `TIMESTAMPTZ`, never a naive
   `TIMESTAMP`.** This exact bug happened twice (RotoWire props, and it was
   specifically checked-for and avoided when building the depth-chart
   snapshot table). Grep for `TIMESTAMP NOT NULL` (without `TZ`) in any new
   schema file before considering it done if the column name implies UTC.
3. **A snapshot-style (point-in-time) table needs explicit point-in-time
   resolution logic wherever it's joined to an event.** Never compare two
   snapshots, or join a snapshot to a game, without pinning "as of when."
   Pattern to reuse: `v_nfl_depth_chart_pregame` and the RotoWire
   `is_pregame` flag are both instances of the same fix — take the latest
   snapshot at or before the reference instant, never just "the latest."
4. **Host machine time zone is not the user's time zone, and may not even be
   UTC.** Anchor every "today"/date comparison to an explicit zone
   (`America/Chicago` for this user) rather than trusting `CURRENT_DATE`.
5. **When a computed number looks implausible, investigate before deleting
   data to fix it.** The QB-carries correction (§5.6) is the concrete example
   — the "fix" that excluded data was wrong; the right move was surfacing the
   implausible result to the user, who correctly identified it as a real
   finding, not an artifact.
6. **Check whether a stat is already in the lake before treating it as a new
   requirement.** Both new ponds in this session (usage, defense) needed far
   less new data than initially assumed — most of what looked like "new
   asks" were already-loaded columns being read through a new lens. Query
   the existing schema first (`information_schema.tables`, or just read the
   relevant `.sql` file) before writing a new loader.
7. **Any raw source table with 100K+ rows should NOT be added to the CSV
   export list without checking file size first.** The depth-chart snapshot
   table is 560K rows / ~63MB uncompressed — deliberately excluded from
   `scripts/export_ramp.py`'s `CHARTS` list to avoid tripping GitHub's
   file-size warnings on every commit. If a future pond needs a similarly
   large raw mirror, keep it database-only and export only a resolved/
   filtered view of it, following this precedent.
8. **Every new pond needs a `sources.yaml` entry, even if it reuses an
   existing file/source.** `nflverse_pbp_defense` is a real example: the
   *file* (`play_by_play_<season>.csv.gz`) is already tracked under
   `nflverse_pbp`, but it feeds a genuinely new table
   (`silver.nfl_points_by_half`) for a new purpose, so it got its own
   manifest entry documenting that specific use and its own verification
   note. Don't skip the manifest entry just because the underlying file
   isn't new.
9. **Heuristic/weighted indicators must be clearly and repeatedly labeled as
   unvalidated**, both in SQL comments at the point of definition and in the
   accompanying doc. Never let a weighted score be presented or discussed as
   if it were a validated predictor before an actual walk-forward backtest
   has been run against it (Phase 2 work, not done).

## 8. File map — where things actually live

```
frontal-lobe2/
├── .kiro/
│   ├── hooks/rotowire-props-snapshot.json   # SessionStart reminder hook
│   └── steering/project.md                  # running log, ALWAYS INCLUDED --
│                                             # read this first, it has more
│                                             # granular dated entries than
│                                             # this handoff document
├── sources.yaml                             # the Utility Room manifest
├── sql/
│   ├── schema.sql                           # original 4-league TeamRankings-
│                                             # audit schema (pre-NFL-ramp;
│                                             # mostly superseded by the files
│                                             # below for NFL specifically)
│   ├── nfl_pfr_schema.sql                   # base player/team stats + dims
│   ├── nfl_td_logs.sql                      # TD log (one row per TD play)
│   ├── nfl_schedule_schema.sql              # real schedule + ATS views
│   ├── nfl_match_page_schema.sql            # the hardcoded lead-page chain
│   ├── nfl_report_room_schema.sql           # injuries/news/transactions
│   ├── nfl_props_schema.sql                 # RotoWire prop lines
│   ├── nfl_player_usage_schema.sql          # usage/stress/depth-chart pond
│   └── nfl_defense_schema.sql               # defense/IB-score pond
├── scripts/
│   ├── sources.py                           # Utility Room CLI
│   ├── ingest_nfl_2026.py                   # base stats loader
│   ├── ingest_nfl_td_logs.py
│   ├── ingest_nfl_schedule.py
│   ├── ingest_nflverse_injuries.py
│   ├── ingest_espn_news.py
│   ├── ingest_rotowire_props.py
│   ├── ingest_draftkings4.py                # incomplete/rationed, see §5.8
│   ├── ingest_nfl_player_usage.py
│   ├── ingest_nfl_defense.py
│   ├── match_page.py                        # the lead-page CLI
│   ├── matchup_report.py                    # report-room deliverable CLI
│   ├── cache_player_photos.py
│   ├── export_ramp.py                       # writes lake/gold/nfl/*.csv + manifest
│   └── pull_teamrankings.sh                 # one-time reference pull (legacy)
├── docs/
│   ├── HANDOFF.md                           # THIS FILE
│   ├── PFR_SOURCE_NOTE.md                   # why PFR is never scraped
│   ├── RAMP_ARCHITECTURE.md                 # the ramp/pond/manifest pattern
│   ├── UTILITY_ROOM.md
│   ├── MATCH_PAGE.md
│   ├── REPORT_ROOM.md                       # (referenced in steering; verify exists)
│   ├── DATA_SOURCES.md
│   ├── ODDS_HISTORY_RESEARCH.md
│   ├── PLAYER_USAGE_INDEX.md                # usage pond, neutral naming
│   ├── DEFENSE_TOXICITY.md                  # defense pond
│   ├── CHART_AUDIT.md                       # original TeamRankings audit
│   └── NHL_GAP.md
├── lake/
│   ├── nfl.duckdb                           # GITIGNORED, rebuildable, the
│   │                                         # actual working database
│   ├── bronze/                              # GITIGNORED raw pulls, timestamped
│   └── gold/nfl/*.csv + _index.csv          # itemized exports, TRACKED in git
│       gold/nfl/player_photos/*.png         # TRACKED, 1300+ headshot files
└── catalog/README.md                        # legacy, pre-NFL-ramp
```

## 9. Commands to re-orient yourself, right now, if memory was lost

Run these before trusting anything above as current:

```bash
# where is git, really
cd /home/him/frontal-lobe2
git log --oneline -10
git status --short --branch
git rev-parse HEAD origin/main hf/main    # should all match if nothing pending

# what tables/views actually exist and how big are they
PYTHONPATH=.pylibs python3 -c "
import duckdb
c = duckdb.connect('lake/nfl.duckdb', read_only=True)
for s,t,k in c.execute(\"select table_schema,table_name,table_type from information_schema.tables order by 1,3,2\").fetchall():
    if k == 'BASE TABLE':
        n = c.execute(f'select count(*) from {s}.{t}').fetchone()[0]
        print(f'{s}.{t:42s} TABLE {n}')
    else:
        print(f'{s}.{t:42s} VIEW')
"

# what sources are configured and their current health
PYTHONPATH=.pylibs python3 scripts/sources.py list
PYTHONPATH=.pylibs python3 scripts/sources.py check --all

# re-read the running log -- this has more granular dated entries than
# this handoff document and is ALWAYS loaded into context automatically
cat .kiro/steering/project.md
```

If `lake/nfl.duckdb` doesn't exist (fresh clone), rebuild it by running each
`ingest_*.py` script in this rough order (later ones depend on tables earlier
ones create, though each script applies its own dependency schema files
automatically via `SCHEMA_FILES`):

```bash
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_td_logs.py --skip-download
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_schedule.py
PYTHONPATH=.pylibs python3 scripts/ingest_nflverse_injuries.py
PYTHONPATH=.pylibs python3 scripts/ingest_espn_news.py
PYTHONPATH=.pylibs python3 scripts/ingest_rotowire_props.py
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py --skip-download
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py --skip-download
PYTHONPATH=.pylibs python3 scripts/export_ramp.py
```

(Drop `--skip-download` on the first run of each script that supports it —
it means "reuse the raw file already sitting in `lake/bronze/`," which won't
exist yet on a truly fresh clone.)

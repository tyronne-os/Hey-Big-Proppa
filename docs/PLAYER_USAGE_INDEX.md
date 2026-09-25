# Player usage & situational-confidence pond

A per-player index of how much of an offense runs through him, and whether his
share **grows or shrinks as the situation tightens**.

Naming note: internal shorthand for sections of this lake is not used in object
names, column names, or any query path. The backend answers to player names and
team/stat requests only. Everything below is the mechanics.

## Built as a spine plus layers

### Layer 1 — the spine: position-gated opportunity

| position | the stat |
|---|---|
| WR, TE | **targets** |
| RB, FB | **rush attempts** |
| QB | **rush attempts** (labeled `rush_attempts_qb`) |

A receiver's opportunity is measured in targets, a back's in carries. Collapsing
both into one "touches" number lets a checkdown back outrank a primary receiver
and says nothing about either.

Quarterback designed runs count and sit in the same rush pool as the backs. At
the goal line the keeper is the back's direct competition, so a back's share
falling there is the measurement, not an artifact. Only **scrambles** are held
out — a collapsed pocket is not a called play. Both are flagged
(`is_qb_scramble`, `is_designed_run`), never dropped.

### Layer 2 — situational stress: the signal

Every opportunity is graded on a four-step ladder, built only from pbp fields:

| level | condition |
|---|---|
| 3 MAX | goal to go, inside the 5, 4th down, or a one-score game inside 5 minutes |
| 2 HIGH | red zone, 3rd down, or 2 yards or fewer to go |
| 1 MODERATE | 2nd and 7+, or trailing by 9–16 |
| 0 NEUTRAL | everything else |

`is_high_stress` = level 2 or 3. Real distribution, 2026 weeks 1–2: L3 = 468,
L2 = 960, L1 = 776, L0 = 1,437.

```
confidence_delta = (share of team opportunities when stress is high)
                 - (share when it is not)
```

Positive = the offense concentrates on him as the situation tightens. Raw share
is volume, and volume is already priced. The delta is the part a box score does
not carry.

### Layers 3–5

- **Depth chart** (`nflverse depth_charts`) — the published hierarchy, resolved
  point-in-time to the latest snapshot before each kickoff. `depth_surplus` =
  listed rank minus actual usage rank *within his own position group*.
- **Field position** — Inside 20/10/5 tiers, plus pass location × air-yard depth
  for targets and run location × gap for carries.
- **Return** — yards from scrimmage and yards per touch, reused from
  `silver.nfl_player_scrimmage_week` so a touch means one thing in this lake.

## Every share is intra-team

Shares are computed against the player's **own team's** total in that same game,
never league-wide. A receiver on a pass-heavy offense out-targets a heavily
featured receiver on a run-first team without either fact describing how the two
offenses distribute trust.

## Sources — no new vendor

| need | source | license |
|---|---|---|
| every target and carry, with down/distance/clock/score/field position | nflverse `pbp` | CC-BY-4.0 |
| published hierarchy, point-in-time | nflverse `depth_charts` | CC-BY-4.0 |

`pbp` is the same file `ingest_nfl_td_logs.py` pulls, so running both loaders
costs one download.

Verified 2026-09-25: 559,864 depth-chart rows across 197 snapshot timestamps
(Mar→Sep), all 32 teams, team codes matching our schedule exactly (uses `LA`,
not the `LAR` mismatch affecting RotoWire). 362 of 363 qualified players matched
a point-in-time depth rank.

### Evaluated, not used in Phase 1

`ffverse/ffopportunity` — expected fantasy points, play-grain, with expected
TDs. Real and current, but GPL-3.0 (versus CC-BY-4.0 everywhere else here),
weekly rather than nightly, and a **model output** rather than an observation.
`silver.nfl_opportunity_event` keeps `(game_id, play_id)` so it joins 1:1 as a
Phase 2 enrichment.

Also available, unwired: nflverse `snap_counts` and `ftn_charting` (motion, play
action, personnel).

## Three defects found and fixed

All three surfaced from implausible output, not from anything erroring.

**1. Removing QB carries broke it.** An early version excluded them as an
artifact. That deleted signal. Restored — and the restoration surfaced a finding
the exclusion had hidden: in Philadelphia the primary back sits at −28.3% while
Will Shipley is **+19.5%** and the quarterback has **zero** inside-5 carries. The
drop was never the sneak; it is a short-yardage committee split.

A related bug did need fixing: the spine originally inferred the gate from
"whichever stat he accumulated more of" for unlabeled positions, which pulled
quarterbacks in under a label that looked real. The gate is now explicit per
position with no inference.

**2. Depth rank compared across position groups.** `depth_surplus` was measuring
a within-position depth rank against a whole-team usage rank, so every TE1 and
RB1 looked negative purely because receivers out-target them. Now within
position group only.

**3. Small samples faked everything.** Teams had 0–18 inside-20 opportunities
for the *entire* season through week 2. A raw share on a denominator of 5 is
noise: 2-of-5 reads as 40% and outranks 6-of-18. Fourteen players pinned at a
perfect score.

Fix: shrinkage. Red-zone shares add k=4 to the denominator; the stress delta is
scaled by `opps_stress / (opps_stress + 6)`. Raw and shrunk columns are both
exposed so the adjustment is visible and reversible.

## Roles

`usage_role` ships with the score, because one number collapses cases that need
different handling:

| role | meaning |
|---|---|
| `PRIMARY -- TRUSTED UNDER PRESSURE` | high share, and share grows under stress |
| `CLOSER -- SMALL ROLE, BIG MOMENTS` | modest volume, large stress share |
| `VOLUME ONLY -- BENCHED WHEN IT TIGHTENS` | gets the touches, loses them late |
| `RISING -- OUT-EARNING DEPTH CHART` | used ahead of his listed slot |
| `RED ZONE SPECIALIST` | outsized share of scoring chances only |
| `INSUFFICIENT SAMPLE` | under 5 spine opportunities — do not read |

## Correlation with the TD log

`gold.v_nfl_player_usage_td_correlation` joins the usage read to who actually
finished. Related stats should agree: if the usage index is right, the scoring
log ought to echo it.

| flag | meaning |
|---|---|
| `AGREEMENT` | high index, TDs on the board |
| `OPPORTUNITY` | high index, no TDs yet — usage is ahead of the box score |
| `HOLLOW` | TDs without usage — scored on volume or a broken play |
| `QUIET` / `MIXED` | neither, or in between |

Distribution, 2026 weeks 1–2: 21 AGREEMENT, 14 agreement-finishing-lightly,
10 OPPORTUNITY, 3 HOLLOW, 49 QUIET, 111 MIXED. `td_per_redzone_opp` carries the
raw conversion rate so a flag never has to be taken on faith.

## Run it

```bash
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_player_usage.py --skip-download
PYTHONPATH=.pylibs python3 scripts/export_ramp.py
```

Idempotent per season. The depth-chart file is 53MB — the largest single pull in
this ramp — so `--skip-download` matters when iterating.

## Limitations

- **Two weeks of data.** Everything rests on 3,641 opportunities. Shrinkage is
  doing heavy lifting; revisit the weights around week 6. The index is a
  weighted heuristic (weights in one CTE: stress .34, red zone .22, share .20,
  depth .12, return .12) and has **not** been backtested. Validation is Phase 2
  and needs a walk-forward test, not a same-season correlation.
- **Depth chart tail is noisy.** The source lists WRs up to 16 deep; ranks past
  WR4 are not a real hierarchy.
- **ESPN one layer down.** nflverse depth charts are ESPN-sourced, so that
  caveat applies indirectly.
- **Snapshot cadence is the data.** A missed week leaves no pre-kickoff snapshot
  for that slate, which silently drops those games from
  `v_nfl_depth_chart_pregame`. Re-pull before each slate.
- **`silver.nfl_depth_chart_snapshot` is not exported** — 560k rows / 63MB would
  trip GitHub's file-size warning every commit. It stays in the database;
  `depth_chart_pregame` is the resolved slice.

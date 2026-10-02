# MY BOO: Reporting Procedure (zero deviation)

Run every step, in order, for every slip. Each step names the code that performs it. If the code and this
document ever disagree, the report is non-compliant: `slip_recap.audit()` flags it, and it must be fixed
before the record counts as training data.

All clocks are **Central (America/Chicago)**.

---

## Step 1: Log the slip

1. A slip enters the book one of three ways:
   - TAKE IT or FAKE IT on a board slip (`myboo.track_slips`, `myboo.set_taken`).
   - **+ NEW TICKET** on the MY BOO page for a FanDuel slip (`POST /api/myboo/tickets`).
   - A Throwdown, Monday Night or Sunday build (`throwdown.build`, which tracks automatically).
2. Every leg must carry a `game_id`. If a hand-logged leg names only a team, `myboo._resolve_game` attaches
   that team's game for the week from the schedule. A leg with no game cannot be watched live.
3. Real money is `POW`; board paper is `SIM`. Log the stake in dollars and the payout in American odds.

## Step 2: Freeze the thesis (the moment the slip is logged)

1. `slip_recap.snapshot_open()` writes the pre-game thesis to `myboo_thesis.json`. It covers:
   - each leg's opponent defense rank and yards allowed;
   - the player's usage average, from games before this week only;
   - each team's identity;
   - prices, the implied probability, the edge and the nugget.
2. It is called on ticket creation, on every board track and by the live watcher. It is idempotent and
   **never overwrites** a frozen thesis.
3. Game-total and moneyline legs belong to the game. Their teams come from the schedule; "TOTAL" is never treated as a team.

## Step 3: Watch the games

1. `slip_alerts.start_worker()` polls once a minute (`POLL_SECONDS = 60`) while a Tank01 key is configured.
2. For every game with an open slip, read the Tank01 box score (`tank01.get_live_boxscore`, 45-second cache).
3. The desk (`boo_desk.clock()`) shows the mode: **PREP DAY**, **GAME DAY**, **LIVE** or **RECORDING**. It
   also shows the NFL and college games today and next, and the slips riding on each game.

## Step 4: Lock legs (`slip_alerts.eval_leg`)

| Market | Locks as HIT | Locks as MISS |
|---|---|---|
| Counting overs (rush, rec, pass yds, receptions, carries, kicker points) | the moment the stat passes the line | at the final, if short |
| Counting unders | at the final, if still under | the moment the stat reaches the line |
| Anytime TD | the moment he scores | at the final, if he did not |
| First TD | when the first TD is scored by him | when the first TD is scored by anyone else |
| Game total over | the moment the combined score passes the line | at the final |
| Moneyline / spread | at the final only | at the final only |

A spread push is graded as a non-loss, because FanDuel voids the leg.

## Step 5: Record (`slip_alerts.record_ticket`)

1. **Any leg locked MISS:** the slip is dead. Record it at once as `READY_LOST`, even mid-game.
2. **Every leg locked HIT:** record it at once as `READY_WON`, even in the first half.
3. When a slip is recorded:
   - write the grades and actual values to `myboo_legs.csv`;
   - settle the ticket in `myboo_tickets.csv`;
   - build the report from the frozen thesis plus the live box score;
   - save it to `myboo_recaps.json`.
4. A slip decided with its game still on gets `EARLY CASH` or `EARLY KILL`.

## Step 6: Write the report (`slip_recap.build_recap`)

**THE SETUP**

1. Open with "I always read the defense first." Give each opposing defense's pass rank and run rank, yards
   allowed and the league average. Split defenses are described as split.
2. Give the offensive identity per team: attempts, rushes, targets, pass rate and label.
3. Give the leg-by-leg thesis: line, usage average, price edge.
4. Add the coach's-call paragraph if any touchdown leg is on the slip.
5. Name the nugget of gold.
6. Run the price check.

**THE FACTS**

1. The final score.
2. Per team: pass attempts, rushes, targets, passing and rushing yards, and whether the identity held or flipped.
3. Where we got it right: every hit leg with its actual number and its usage against the average.
4. Where we got it wrong: every missed leg with the reason:
   - **Workload fell short:** the role broke.
   - **Workload and matchup were there:** efficiency, or someone else ate the production.
   - **Defense played above its numbers:** the ranking gets corrected.
   - **Touchdown leg:** his scrimmage yards, and who actually scored for his team.

**HINDSIGHT**

1. Exactly one verdict from the closed set in [SKILL.md](SKILL.md).
2. Then the process score: the share of graded effort legs where the matchup and usage both held. Touchdown legs are excluded.

**Length:** at least 200 words, padded only with data-backed lines (`slip_recap._pad`).

## Step 7: The final whistle

1. `GAME_FINAL` fires.
2. `slip_alerts._refresh_partials` rewrites every early record from the full stat line, which turns
   EARLY CASH or EARLY KILL into a SCIENCE or SHIT verdict. `RECAP_FINAL` then fires.
3. If the recap logic changes, `slip_alerts.rebuild_recaps(game_id)` rewrites every settled report on that
   game from its frozen thesis. The setup data is never changed.

## Step 8: Score the logic (`boo_desk.scorecard`)

1. After every game, tally hits by market, kept separately for POW and SIM. Effort legs and touchdown legs
   are always reported apart.
2. Count the losing slips that died only on a touchdown leg.
3. Publish the scorecard to the MY BOO desk (`GET /api/myboo/desk`).

## Step 9: Keep the record

1. The ledger files live in `lake/gold/nfl/`:
   - `myboo_tickets.csv`
   - `myboo_legs.csv`
   - `myboo_thesis.json`
   - `myboo_recaps.json`
   - `myboo_alerts.json`
   - `myboo_counter.txt`
2. On the Space they are mirrored to the private dataset `AIBRUH/big-proppa-lake` under `myboo/`
   (`boo_store.py`) whenever an `HF_TOKEN` secret is set, so a restart or redeploy never erases her records.

## Step 10: Audit (`slip_recap.audit`)

Every report is checked against this procedure. A violation keeps the report out of the training set until it is fixed. The checks:

- [ ] Three sections present and in order. A pregame report has THE SETUP only.
- [ ] THE SETUP begins "I always read the defense first."
- [ ] At least 200 words.
- [ ] The verdict is in the closed set.
- [ ] A touchdown leg on the slip has the coach's-call paragraph.
- [ ] A missed touchdown leg means the verdict is `SHIT (TD GAMBLE)`.
- [ ] A final report's facts open with "Final:".
- [ ] A lost slip with a touchdown leg ends its HINDSIGHT with the "What-if:" counterfactual.

## Step 11: The Tuesday batch (`boo_training.run_batch`)

Runs automatically once after each **Tuesday 6:00 AM Central** (`boo_training.maybe_run_tuesday`, checked every
minute by the worker; if the worker was down at 6:00 it runs on restart). It can also be run by hand as a preview.

1. **Collect.** Every FINAL report becomes one `boo.slip.v1` record and one `boo.leg.v1` record per graded leg
   (full schema in [TRAINING_SCHEMA.md](TRAINING_SCHEMA.md)). Written to `lake/gold/nfl/boo_training/week_NN_legs.jsonl`
   and `week_NN_slips.jsonl`.
2. **Calibrate.** Hit rate against Jimmy's number by market and by bucket, with Brier score.
3. **Weigh the signals.** For each signal Jimmy averages, the correlation between its value and the hit, shrunk
   by sample size, becomes a weight between 0.7x and 1.3x. Under 30 legs the weight stays 1.0.
4. **Bias the markets.** A market whose hit rate sits away from Jimmy's number (25 or more legs) gets a nudge of
   at most 5 points.
5. **Correct the defenses.** Actual yards allowed over expected, per defense and phase, averaged over games and
   shrunk toward 1.0 (range 0.7 to 1.3).
6. **Log usage drift and the miss taxonomy.** How each player's real workload compared with the baseline, and
   why legs missed.
7. **Retire what the evidence retires.** Touchdown-scorer legs are recorded with their record as the retired-markets lesson.
8. **Write.** `jimmy_lessons.json` (the previous file is kept as `jimmy_lessons.vN.json`), `batches.json` (the log)
   and `latest_report.md` (what Jimmy learned, in plain words, including the touchdown tax for real money and for the board).
9. **Mirror.** The package, lessons and log are mirrored to the ledger dataset (Step 9).

## When something fails

- **No live data.** If Tank01 is unreachable or the game is not in the feed, the slip stays open. Never guess
  a result. The lake grader settles it when the week's stats land.
- **Leg the feed cannot see.** The leg stays ALIVE with that note. The slip is not recorded until it can be.
- **No usage sample** (rookie or first game). The leg is graded on the matchup alone. If no leg can be graded,
  the verdict is `UNSCORED`.

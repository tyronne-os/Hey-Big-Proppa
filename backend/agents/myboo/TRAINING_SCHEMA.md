# MY BOO training package: schema for Jimmy and Big Proppa

Written every Tuesday 6 AM Central to `lake/gold/nfl/boo_training/`. One pair of JSON-lines files per NFL week.

## `week_NN_legs.jsonl`: `boo.leg.v1`, one line per graded leg

| Field | Meaning |
|---|---|
| `ticket_id`, `order_type` | The slip. `POW` is real money, `SIM` is the board's paper slip. |
| `week`, `season`, `game_id` | Which game. |
| `player`, `player_id`, `team`, `opp` | The player and his opponent. |
| `market`, `direction`, `line`, `odds` | The bet. |
| `model_prob`, `implied`, `edge` | The Big Proppa Line probability, the price-implied probability, the gap. |
| `jimmy_score` | Jimmy's composite score when the slip was frozen. |
| `components` | Every signal Jimmy averaged, by name, frozen pre-game (`hit_rate`, `usage`, `matchup`, `recency_defense`, `qb_pressure`, `projection`, `dfs_salary`, `fantasy`). |
| `hit` | 1 or 0. |
| `actual`, `margin`, `margin_pct` | What happened, and by how much against the line. |
| `usage` | `key` (carries, targets, attempts, touches), the `avg` baseline, what he `used`, and the `ratio`. |
| `volume_held`, `env_held`, `thesis_held` | Whether the workload and the defensive matchup played out as written. |
| `miss_type` | `COACH_CALL`, `VOLUME_COLLAPSE`, `DEFENSE_OVERPERFORMED`, `DEFENSE_UNDERPERFORMED`, `NEAR_MISS`, `EFFICIENCY`, or null on a hit. |
| `coach_call` | True for touchdown-scorer legs. These never teach a signal. |
| `attack` | The defense the leg attacked: `cat` (pass or rush), `rank`, `expected` yards allowed, `actual`, `ratio`. |
| `game` | Game script: shape, margin, total points against the posted total, plays, pass rate. |
| `slip_verdict` | The slip's verdict, for context. |

## `week_NN_slips.jsonl`: `boo.slip.v1`, one line per recorded slip

`ticket_id`, `order_type`, `week`, `name`, `status`, `stake`, `payout_odds`, `result_units`, `verdict`,
`process_score`, `tags`, `words`, `whatif` (the strip-the-gamble counterfactual, or null), `game`, and `report`
(`setup`, `facts`, `hindsight`: the full text, for any model that learns from prose).

## `jimmy_lessons.json`: what Jimmy reads

| Key | Effect |
|---|---|
| `weights` | Per-signal multiplier used by `jimmy_score()` when it averages the signals. Absent means 1.0. |
| `market_bias` | Added to the score for that market, capped at plus or minus 0.05. |
| `defense_residual` | Per defense, per phase: actual over expected yards allowed. Nudges the recency-defense signal by at most 0.08. |
| `usage_drift` | Per player and usage key: real workload over baseline. For reference. |
| `retired_markets` | What the evidence says to stop betting. |
| `calibration`, `signal_detail`, `miss_taxonomy`, `whatif`, `notes` | The evidence behind the numbers. |
| `version`, `preview`, `through_week`, `partial_weeks` | Which batch, and whether it included a week still in progress. |

Rolling back: delete `jimmy_lessons.json` and rename `jimmy_lessons.v(N-1).json` to take its place.

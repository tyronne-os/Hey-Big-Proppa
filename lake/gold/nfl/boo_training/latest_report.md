# WHAT JIMMY LEARNED: batch v4

Built Mon Oct 12, 12:07 PM CT by MY BOO (Tuesday batch, complete weeks only).
Training package: 167 graded legs from 51 slips through week 4.

## Lessons
- Touchdown-scorer legs are 6/29 (real money 0/4, board 6/25). Retired from week 4; effort legs replace them.
- CLE's pass defense runs 13% softer than its rank.
- DAL's pass defense runs 10% softer than its rank.
- LV's rush defense runs 18% softer than its rank.

## The touchdown tax: Real money
3 slips carried a touchdown leg; 2 would have cashed without it, paying about $81.95 profit on $3.75 staked ($176.23 had the touchdown also landed). Stripped-leg prices are estimates from FanDuel's board.

## The touchdown tax: The board (paper)
13 slips carried a touchdown leg; 7 would have cashed without it, paying about $792.64 profit on $35 staked ($4531.25 had the touchdown also landed). Stripped-leg prices are estimates from FanDuel's board.

## Miss taxonomy
- anytd: COACH_CALL 21
- firsttd: COACH_CALL 2
- passtd: EFFICIENCY 1
- rushyds: NEAR_MISS 8, EFFICIENCY 3, VOLUME_COLLAPSE 2
- recs: EFFICIENCY 6, VOLUME_COLLAPSE 2, DEFENSE_UNDERPERFORMED 1
- recyds: EFFICIENCY 5, DEFENSE_UNDERPERFORMED 2, VOLUME_COLLAPSE 2
- passyds: DEFENSE_UNDERPERFORMED 1
- kickpts: EFFICIENCY 1
- nfl_total: NEAR_MISS 1
- nfl_ml: EFFICIENCY 2
- nfl_spread: EFFICIENCY 3

## Calibration (Jimmy's number vs reality)
- kickpts over: predicted 55%, observed 0%, n=1, Brier 0.302
- nfl_ml over: predicted 45%, observed 100%, n=1, Brier 0.306
- nfl_ml win: predicted 44%, observed 75%, n=8, Brier 0.248
- nfl_spread cover: predicted 63%, observed 0%, n=3, Brier 0.393
- nfl_total over: predicted 49%, observed 88%, n=8, Brier 0.287
- passtd over: predicted 29%, observed 50%, n=2, Brier 0.193
- passyds over: predicted 57%, observed 100%, n=16, Brier 0.198
- passyds under: predicted 26%, observed 0%, n=1, Brier 0.07
- recs over: predicted 51%, observed 65%, n=23, Brier 0.298
- recs under: predicted 66%, observed 92%, n=13, Brier 0.14
- recyds over: predicted 58%, observed 79%, n=24, Brier 0.213
- recyds under: predicted 58%, observed 0%, n=3, Brier 0.338
- rushyds over: predicted 30%, observed 40%, n=10, Brier 0.371
- rushyds under: predicted 67%, observed 25%, n=8, Brier 0.356

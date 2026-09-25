# Defense pond -- the toxic pond

Every other pond in this lake reads an offensive player against his own team.
This one reads the opposing **defense** he is about to face, because that
defense decides whether a usage-index read actually cashes on a sportsbook
line. A player can be exactly as trusted as the lake says and still not
deliver, because the defense he draws that week is toxic.

## The 8 stat columns, exactly as specified

| # | stat | where it lives |
|---|---|---|
| 1 | NFL ranking in defense (scoring) | `rank_scoring_defense` in `v_nfl_team_defense_season` |
| 2 | Ranking in sacks | `rank_sacks` |
| 3 | Ranking in interceptions | `rank_interceptions` |
| 4 | Points allowed in the 2nd half | `points_allowed_2nd_half_per_game` |
| 5 | Team win percentage | `win_pct` |
| 6 | Who gets the sacks | `silver.v_nfl_individual_sacks` |
| 7 | Who intercepts the ball | `silver.v_nfl_individual_interceptions` |
| 8 | Defensive rank in turnovers created | `rank_turnovers_created` |

Nothing else is in the base rollup. No new source was needed for seven of the
eight — `silver.nfl_team_week`, `silver.nfl_pfr_adv_defense_week`,
`silver.nfl_player_defense_week`, and `silver.nfl_schedule` already carried
them. **Points allowed by half** is the one gap: nflverse does not publish it
as a team-week aggregate anywhere in its catalog. It's rebuilt from the same
`play_by_play` file already pulled for the TD log and usage pond — one more
pass over a file already on disk, not a new download.

Rankings are computed here, not sourced pre-ranked — nflverse does not publish
a rankings table, the same reason ATS is computed rather than sourced
elsewhere in this lake.

Turnovers created = interceptions + fumbles forced. nflverse does not publish
a combined column, so it's summed from the two components it does track.

## Points-by-half: verified against real final scores

Built from scoring plays (TD, FG, XP, 2-point, safety), attributed to whichever
team was on defense at the moment of the score — including the flip on a
defensive/return touchdown or a safety, where the team on offense is the one
who allowed it, not the one who scored.

Not just internally consistent — cross-checked against
`silver.nfl_schedule`'s real final scores for all 32 teams. Verified 2026-09-25:
max disagreement 0 points.

## The IB Score

The user's own framing, quoted directly because it defines the scale:

> IB (irritable bowel) score. Very irritated and aggravated all game is CAT 5.
> Not at all is CAT 1, meaning no pressure up the middle all day to pass the
> ball — RB could get over 100 rushing, perhaps multiple WR over 60 yards and
> 4 passing touchdowns. That is what CAT 1 looks like, and the evidence is in
> the stats — how they are being scored on and how often.

So the score is not a vibe. It's five components, each a real season-to-date
stat, scaled 0 (least toxic) to 100 (most toxic) against this season's actual
league range, then averaged and mapped onto CAT 1–5:

| component | built from |
|---|---|
| **pressure** | sacks + QB hits + tracked pressures, per game |
| **coverage** | passer rating allowed, inverted (low rating allowed = high toxicity) |
| **takeaways** | interceptions + fumbles forced, per game |
| **run stop** | rushing yards allowed per game, inverted — a live run game means the QB never faces a one-dimensional defense |
| **scoring** | points allowed per game, and specifically the 2nd half — does this defense fold as the game wears on |

The scaling bounds are `min()`/`max()` across the real league **this season**,
recomputed on every run. As the user put it: "as the season goes it will all
fall in line" — the bounds move with the season instead of being fixed to an
assumption made in week 2.

`gold.v_nfl_defense_ib_score` carries both the 0–100 `toxicity_index_0_100` and
the 1–5 `ib_score` / `ib_category` mapping.

## Verified on real 2026 weeks 1–2 data

```
TEAM  IB  TOX   WIN%  PA/G  PA2H  SACKS(rk)  INT(rk)  TO(rk)
MIN    5  81.1  100.0  12.5   3.0    8 (1)      2 (5)    5 (4)
LV     5  80.5  100.0  13.5   7.0    8 (1)      3 (2)    9 (1)
...
IND    2  23.5    0.0  37.0            4(16)    0(24)    1(28)
```

Minnesota and Las Vegas top the toxicity list with the fewest points allowed
per game and a share of the league's sack lead — exactly the profile CAT 5
should produce. Indianapolis sits at the bottom giving up 37 points per game.
No team has reached CAT 1 yet at two weeks, which is correct this early — the
sample has not accumulated enough to justify the top tier, and it shouldn't.

Category distribution at week 2: 0 CAT 1, 5 CAT 2, 19 CAT 3, 6 CAT 4, 2 CAT 5.

## The join this pond exists for

`gold.v_nfl_matchup_toxicity` pairs every scheduled game's two defenses. The
actual use is joining a usage-index player to the defense he is about to
face — when a heavily-featured player on a top offense (the name a book uses
to draw a bet) is about to face a CAT 4/5 defense, that is the mismatch this
lake was built to catch.

## Run it

```bash
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_defense.py --skip-download
PYTHONPATH=.pylibs python3 scripts/export_ramp.py
```

## Limitations

- **Two weeks of data.** The league-range scaling bounds are noisy this early;
  they tighten as more of the season is played, by design.
- **IB Score is a heuristic**, same caveat as the usage index: components and
  their equal weighting are a judgement call, not backtested. It is a reading
  of the evidence, not a validated predictor, until tested against actual
  QB/skill-player output in the following weeks.
- **Points-by-half folds overtime into the 2nd half.** Correct for a 2nd-half
  prop (OT points are still second-half-or-later defensive failure), but noted
  since it is a deliberate choice, not an oversight.

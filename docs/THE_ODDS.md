# THE ODDS — pond + page (built 2026-09-26)

Vegas lines for every game on the board, kept in the lake as a pond so predictions and
reference views can read them, and shown on the **THE ODDS** tab.

## The pond (`lake/gold/nfl/`)

| table | grain | notes |
|---|---|---|
| `odds_board.csv` | one row per game (`league` = `nfl` or `cfb`) | consensus + FanDuel spread/total/moneyline, the open, moves since open, last change time |
| `odds_line_history.csv` | append-only, one row per game/book each time a number changes | books stored: `consensus` (median across books) and `fanduel` |

Registered in `_index.csv` (counts toward the RAMP "ponds live" total).
Columns: see `BOARD_COLS` / `HISTORY_COLS` in `backend/odds_pond.py`.

**"Open" caveat.** Tank01 does not return opening lines. A game's open is the first snapshot
this lake saw, so "Biggest Line Moves From Open" fills in as pulls accumulate (moves are 0 on
the first pull). It is exact from the day tracking starts, not from when Vegas posted the number.

## Sources and refresh
- **NFL:** Tank01 `getNFLBettingOdds` (about 7-8 books per game) and `getNFLGamesForDate`
  (kickoff epoch). Dates come from the lake schedule (the next unplayed week). Tank01's odds
  endpoint spells LAR/WSH where its games endpoint says LA/WAS (`_ALIAS`).
- **College Top 25:** CFBD lines via `cfb_jimmy.cfb_game_slate()` (ranked games this week,
  one provider). Tank01's key does not include the college API.
- Refresh is lazy: `GET /api/odds?league=nfl|cfb` refreshes when the pond is older than 10
  minutes (`&refresh=true` forces it). The page polls once a minute.
- Needs `TANK01_API_KEY` (and `CFBD_API_KEY` for college) in the environment. Without a key the
  page serves whatever is already in the pond files.

## The page (`frontend/src/components/OddsTab.tsx`)
- Center nav: NFL / COLLEGE TOP 25. Add a league by adding it to `LEAGUES` and to `odds_pond.refresh`.
- 75% games grouped by day (spread, total, moneyline, ET kickoff, move arrows), 25% right column:
  Smoke Proppa Watch, Biggest Line Moves From Open, Most Recent Line Changes, Biggest / Smallest
  Spreads, Highest / Lowest Totals (upcoming games only).
- Theme: white by default; the round icon bottom-left switches White / Dark / Tan (remembered in
  the browser).

## Smoke Proppa watch (`odds_pond._watch_one`)
Reads the pond and compares Vegas to the Big Proppa Line (team-points model, `bpl.py`); no LLM.
- Probability that a side wins comes from a normal curve around the BPL margin / total with
  sd 16.6 (college, measured) or 13.5 (NFL, derived from the 7.57 team-points error, not
  measured on totals). Only half of the gap from 50% is trusted, because Vegas is sharper than a
  model fed two games of this season.
- **MONEY PLAY** = 60%+ after that (about 70% raw). **WATCHING** = 54%+, or a total/spread that
  moved 2+ points since open. Spreads over 21 points get no pick. Started games get no flag.
- These are unproven, like every Big Proppa Line edge; MY BOO's graded record is the test.

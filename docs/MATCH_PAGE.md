# The Match Page

The lead page for this lake and every ramp to come. A strict, hardcoded query
chain -- deterministic SQL, no model logic -- that the user specified exactly:

1. What is today
2. Are there any NFL games today (yes/no)
3. If yes: the matchups
4. Per matchup: inactive players, weather signal, odds

Impact *scoring* of weather/inactives is explicitly deferred to a later
"logic engine" phase per the user. This layer only surfaces the raw signal.

## Run it

```bash
PYTHONPATH=.pylibs python3 scripts/match_page.py                    # today
PYTHONPATH=.pylibs python3 scripts/match_page.py --date 2026-09-27   # any date
PYTHONPATH=.pylibs python3 scripts/match_page.py --json
```

## Verified both branches with real data, 2026-09-25

- **YES branch**: today (2026-09-24 in America/New_York -- see timezone note
  below) has a real game, ATL @ GB, Thursday Night Football. Full bundle
  returned: real spread (4.5) and moneyline (away +190 / home -230), 8 real
  injury-report entries (5 Out, 3 Questionable, with injury type), and 10 real
  player prop lines shown (Bijan Robinson rush+rec yards 134.5, Tucker Kraft
  receptions 5.5, etc.)
- **NO branch**: 2026-09-25 has zero games. The chain correctly returns "NO --
  0 games" and stops -- confirmed this is not an error path, it's the correct
  answer on most calendar days.
- **Future date**: 2026-09-27 (14-game Sunday slate) returns real spread/
  total/moneyline for every game, confirming the schedule feed's odds aren't
  historical-only.

## The chain, as SQL (`sql/nfl_match_page_schema.sql`)

| Step | View | Notes |
|---|---|---|
| 1 | `gold.v_today` | Anchored to `America/New_York`, not host machine time -- see bug below |
| 2 | `gold.v_games_today_flag` | Single row, `has_games_today` boolean + count |
| 3 | `gold.v_matchups_today` | Empty result set on a non-game day is correct, not an error |
| 3b | `gold.v_matchups_upcoming` | Companion view -- what's coming up, since most days are empty |
| 4a | `gold.v_matchup_inactives` | Practice-report proxy -- see gap below |
| 4b | `gold.v_matchup_weather_signal` | Raw signal + one hardcoded threshold flag |
| 4c | `gold.v_matchup_game_odds` | Team-level spread/total/moneyline (nflverse schedule) |
| 4c | `gold.v_matchup_prop_odds` | Player-level prop lines (RotoWire), kept separate from game odds -- different grain |
| all | `gold.v_match_page_today` | The rollup: one row per today's matchup with counts from each section |

## New source: `silver.nfl_schedule` (`sql/nfl_schedule_schema.sql`)

Fixes a confirmed real gap found while building this: `silver.nfl_game` (from
the original PFR-style schema) has `home_team`/`away_team`/`kickoff_utc` all
NULL for every row -- those columns were defined but nothing ever populated
them. `silver.nfl_schedule` is the real, correctly-populated table, sourced
from nflverse's `schedules` release (272 games, 2026 season).

Confirmed field behavior, not assumed:
- `gameday`/`gametime`/`roof`/`surface`: populated for every game, past and
  future (roof/surface are fixed stadium properties, known ahead of time).
- `spread_line`/`total_line`/moneylines: populated for **upcoming** games too
  -- a second, independent odds source alongside RotoWire's player props.
  Different grain (team line vs. player prop) -- kept in separate views, not
  merged, per the user's request to "pull in the odds" for the handoff to
  Lake Logic.
- `temp`/`wind`: **only** populated for games already played (recorded actual
  conditions). For an upcoming game these are NULL -- correct behavior, not a
  bug. A real pre-game weather **forecast** needs a different, forward-looking
  source; not built in this ramp.

## Two real bugs found and fixed while building this

1. **Timezone bug.** The host container runs in CDT, not UTC. A naive
   `CURRENT_DATE` would silently give a different "today" depending on which
   machine runs the query -- exactly the kind of non-hardcoded behavior the
   user was trying to avoid. Fixed: `v_today` explicitly converts
   `CURRENT_TIMESTAMP` to `America/New_York` (the NFL's own scheduling
   timezone) before taking the date. Confirmed the fix by checking
   `timedatectl` on the host and comparing both versions' output.

2. **Cross-source game_id mismatch.** RotoWire's `game_id` (an internal
   numeric id, e.g. `2978668`) and nflverse's `game_id` (e.g.
   `2026_03_ATL_GB`) are two unrelated ID schemes. The first version of
   `v_matchup_prop_odds` joined directly on `game_id` and silently returned
   zero rows even though 199 real prop-line rows existed for the two teams in
   today's game. Fixed by joining on team membership (a prop's player's team
   is one of the two teams in the matchup) instead. Verified: 85 real prop
   rows now correctly link to today's ATL@GB matchup.

## Known gap: the true final inactives list

Repeated from `docs/REPORT_ROOM.md` because it's directly relevant here: the
NFL's actual final inactives list is released ~90 minutes before kickoff, and
no source in this ramp publishes that specific list on that timeline.
`v_matchup_inactives` is explicitly labeled `practice_report_proxy -- NOT the
final inactives list` in its own output -- the best available signal before
kickoff, not the real thing. A same-day source would be needed later for the
actual list.

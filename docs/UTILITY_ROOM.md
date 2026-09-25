# The Utility Room

One file, `sources.yaml`, describes every data source feeding the lake. One
CLI, `scripts/sources.py`, reads and manages it. This is where a source gets
tweaked, serviced, or swapped -- without touching any other source, and
without hunting through ingest scripts to remember what depends on what.

## Why this exists

Confirmed during this session's verification pass: two tables were quietly
empty (`gold.nfl_prop_line`, superseded; `gold.nfl_player_id_bridge`, not yet
built) and nobody would have known without directly querying row counts. The
utility room makes that kind of gap visible by design, in one place, instead
of requiring a manual audit every time.

## Commands

```bash
PYTHONPATH=.pylibs python3 scripts/sources.py list
PYTHONPATH=.pylibs python3 scripts/sources.py list --status active
PYTHONPATH=.pylibs python3 scripts/sources.py show rotowire_props
PYTHONPATH=.pylibs python3 scripts/sources.py check --all      # live reachability
PYTHONPATH=.pylibs python3 scripts/sources.py check espn_news  # one source
PYTHONPATH=.pylibs python3 scripts/sources.py disable espn_news
PYTHONPATH=.pylibs python3 scripts/sources.py enable espn_news
PYTHONPATH=.pylibs python3 scripts/sources.py run rotowire_props -- --skip-download
```

`check --all` does a real HTTP GET against each source's `base_url` and
reports the status code. Verified 2026-09-25: 6 of 9 sources return a healthy
response; the 2 failures (`pfr_direct` HTTP 403, `tank01_rapidapi` HTTP 401)
match their documented `broken`/`disabled` status exactly -- the tool isn't
just printing green for everything.

## What's in `sources.yaml` right now

| id | status | what it feeds |
|---|---|---|
| `nflverse_stats` | active | 8 player-week chart tables, team_week, player/game dims |
| `nflverse_pbp` | active | TD log (all 32 teams) |
| `nflverse_injuries` | active | official weekly injury report |
| `rotowire_props` | active | 22 prop markets, scoped to DK/FD/Caesars |
| `espn_news` | active | injury narrative, news, transactions |
| `player_headshots` | active | cached photo files (derived from nflverse_stats, no independent pull) |
| `teamrankings_reference` | deprecated | chart-design reference only, never loaded into silver/gold |
| `pfr_direct` | broken | documents why PFR itself was ruled out (403, Cloudflare + ToS) |
| `tank01_rapidapi` | disabled | documented option, not built; needs the user's own live key test |

Each entry records: what it feeds, how often it should be re-pulled, its
confirmed risk profile (ToS/stability/access caveats -- not guessed), and
replacement candidates already identified if it needs to be swapped.

## Servicing a source

1. `show <id>` to see its current config and risk notes.
2. Edit the relevant fields in `sources.yaml` directly (rate limits, cadence,
   replacement candidate). No code change needed for config-only tweaks.
3. If the ingest logic itself needs to change, only that source's script
   (`ingest_script` field) is touched -- no other source's script imports or
   depends on it.
4. `check <id>` to confirm it's still reachable before trusting a scheduled
   re-run.
5. To retire a source: set `status: deprecated` or `broken` and fill in why
   under `risk` -- don't delete the entry, since the "why we stopped using
   this" record is as valuable as the "what we use now" record (see
   `pfr_direct` and `teamrankings_reference` for the pattern).

## Known gaps, tracked here rather than hidden

- `gold.nfl_prop_line` (in `sql/nfl_pfr_schema.sql`) is superseded and empty
  by design -- marked in a comment at its definition, not removed, in case
  anything already references the name.
- `gold.nfl_player_id_bridge` is a real, unfinished piece: the schema exists
  to link ESPN athlete IDs to nflverse `gsis_id`, but the matching logic was
  never built. Currently 0 rows. Don't join through it yet -- match on team +
  player name in the meantime, as `matchup_report.py` already does.

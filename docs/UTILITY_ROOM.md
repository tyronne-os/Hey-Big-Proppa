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

## The ESPN stream: schedule and staff (added 2026-10-02)

MY BOO is the director of the ESPN data stream. `backend/boo_staff.py` runs her staff in one background thread
(started from `slip_alerts.start_worker()`, so it comes up with the Space). Every agent has two cadences: **LIVE**
(any NFL or Top-25/SEC game in progress) and **IDLE**. Each run is timed and stored in
`lake/gold/espn/staff_status.json`; the Data Auditor flags any agent that goes stale or errors 3 times running, and
the MY BOO → STAFF tab shows it all. A failing agent never stops the others, and the college page serves the last good
snapshot if ESPN is down.

| Agent | Duty | LIVE | IDLE | Writes (lake/gold/espn/) |
|---|---|---|---|---|
| Scoreboard Scout | NFL scoreboard + college Top-25/SEC slate, spots live games and finals | 20 s | 10 min | `nfl_scoreboard.json`, `cfb_snapshot.json` |
| Play-by-Play Clerk | Reads plays of every live game; alerts on scores, turnovers, 20+ yd plays | 15 s | (off) | `play_events.json`, `play_seen.json` + MY BOO alert feed |
| Line Watcher | Spread/total history, 1+ pt movement, ESPN-vs-TeamRankings disagreement (1.5+ pts) | 10 min | 30 min | `line_history.json` |
| Poll Analyst | AP + Coaches polls, week-over-week movement | 30 min | 1 h | `polls_prev.json`, `poll_movers.json` |
| Portal Scout | College transfer-portal stories, flags new ones | 30 min | 1 h | `cfb_portal.json` |
| SEC Beat Reporter | SEC news + matchup news per SEC game | 15 min | 30 min | `cfb_sec.json` |
| Injury Desk | NFL injury report snapshot and changes | 30 min | 1 h | `injuries.json` |
| Standings Actuary | Standings + ESPN-derived power rating (Jimmy's fallback for `tr_power`) | 30 min | 1 h | `standings.json` |
| Data Auditor | Staleness and error check on every agent | 5 min | 10 min | `audit.json` |
| MY BOO — Director | Writes the briefing from the snapshots | 5 min | 1 h | `boo_briefing.json` |
| Hermes Liaison | Exports the roster as a manifest for Hermes agents | 6 h | 6 h | `hermes_staff.json` |

Other schedules that feed the lake (unchanged): TeamRankings Tue 1 AM CT full / Mon, Thu–Sun 9 AM CT daily
(`trusteddataTR.maybe_run`); MY BOO Jimmy training Tue 6 AM CT (`boo_training.maybe_run_tuesday`).

**Scope:** college football is Top 25 + SEC only (`espn_cfb.SEC` holds the 16 SEC team ids). To change a cadence, edit the
`live`/`idle` numbers in `boo_staff.AGENTS`; to pause one agent, remove it from that list. Endpoints: `/api/boo/staff`,
`/api/boo/staff/manifest` (Hermes), `/api/espn/ticker`, `/api/espn/game?id=&lg=nfl|cfb`, `/api/cfb/espn`, `/api/espn/lines`.

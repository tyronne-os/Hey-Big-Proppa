# Why PFR chart designs, but nflverse data

## The charts we're recreating

Pro-Football-Reference pages targeted for this project (2026 season):

| PFR page | Anchor | Our table / view |
|---|---|---|
| `/years/2026/passing.htm` | `#all_passing` | `silver.nfl_player_passing_week` |
| `/years/2026/rushing.htm` | `#all_rushing` | `silver.nfl_player_rushing_week` |
| `/years/2026/receiving.htm` | `#all_receiving` | `silver.nfl_player_receiving_week` |
| `/years/2026/scrimmage.htm` | `#all_scrimmage` | `silver.nfl_player_scrimmage_week` |
| `/years/2026/defense.htm` | `#all_defense` | `silver.nfl_player_defense_week` |
| `/years/2026/scoring.htm` | `#all_scoring` | `silver.nfl_player_scoring_week` |
| `/years/2026/kicking.htm` | `#all_kicking` | `silver.nfl_player_kicking_week` |
| `/teams/<abbr>/2026.htm` | `#all_team_td_log` | `silver.v_nfl_team_td_log` |
| `/teams/<abbr>/2026.htm` | `#all_opp_td_log` | `silver.v_nfl_opp_td_log` |

Team-level counterparts are views over `silver.nfl_team_week`
(`v_nfl_team_passing_week`, `v_nfl_team_rushing_week`, ... one per chart family).

## PFR cannot be fetched programmatically

Verified 2026-09-24:

- `https://www.pro-football-reference.com/years/2026/` -> **HTTP 403**
- `https://www.pro-football-reference.com/years/2026/passing.htm` -> **HTTP 403**
- `https://www.pro-football-reference.com/robots.txt` -> **HTTP 403**

The 403 body is a Cloudflare interstitial (`<title>Just a moment...</title>`), i.e. a
bot challenge on the whole domain, not a per-path rule. Sports Reference's Terms of
Use separately prohibit harvesting/scraping without permission. Defeating that
challenge would be circumventing an access control, so we don't.

## nflverse supplies the same numbers, openly

[nflverse-data](https://github.com/nflverse/nflverse-data) publishes per-season
releases built for programmatic use. Relevant feeds, all confirmed present for 2026:

| Feed | File | Use |
|---|---|---|
| `stats_player` | `stats_player_week_2026.csv` | 150 columns covering all 7 chart families, week grain |
| `stats_team` | `stats_team_week_2026.csv` | 138 columns, team grain |
| `pbp` | `play_by_play_2026.csv.gz` | every play -> touchdown logs for all 32 teams |
| `pfr_advstats` | `advstats_week_{pass,rush,rec,def}_2026.csv` | **a direct mirror of PFR's own advanced tables** |

That last row matters: nflverse republishes PFR advanced stats (pressure counts,
yards before/after contact, broken tackles, coverage numbers) keyed on
`pfr_player_id`. So the PFR-specific columns are still available without touching
PFR itself.

## Deliberate design choices

**Week grain, not season totals.** Every base table is one row per player (or team)
per game. Season totals are views (`v_nfl_player_*_season`). Props are priced per
game, so per-game history is what a line can be argued against; storing only totals
would throw that away. A late stat correction also can't leave totals out of sync
with the weeks that feed them.

**One TD-log table, two views.** PFR's `#all_team_td_log` and `#all_opp_td_log` are
two perspectives on the same touchdown event. `silver.nfl_td_log` holds one row per
TD play; `v_nfl_team_td_log` reads it as "scored" and `v_nfl_opp_td_log` as
"allowed". This is why all 32 teams come from a single play-by-play pull instead of
32 page fetches.

**Extra situational context.** Because the logs are derived from play-by-play, each
TD carries `down`, `goal_to_go`, `yardline_100`, quarter and clock. PFR's own TD log
does not show down or goal-to-go. Red-zone and goal-to-go conversion rates on both
sides of the ball are where an anytime-TD or team-total price tends to drift.

**`total_tds` excludes passing TDs.** A thrown touchdown is credited to the receiver,
not the passer. `passing_tds` is still reported in
`silver.nfl_player_scoring_week`, but excluded from `total_tds` and `total_points`
so a QB isn't double-counted against an anytime-scorer market.

## Reproducing

```bash
pip install --target=.pylibs duckdb            # PEP 668 box: no venv needed
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_2026.py      # players + teams
PYTHONPATH=.pylibs python3 scripts/ingest_nfl_td_logs.py   # TD logs, all 32 teams
```

Raw CSVs land append-only under `lake/bronze/nflverse/<UTC-timestamp>/` with sha256
logged; `bronze.ingestion_runs` records each run. Both loaders are idempotent
(delete + reinsert the season), so re-running weekly through the season is safe.

Verified load, 2026 weeks 1-2: 2,223 player-week rows per category, 64 team-week
rows, 162 TD plays across all 32 teams, 1,306 players, 501 linked to a `pfr_player_id`.

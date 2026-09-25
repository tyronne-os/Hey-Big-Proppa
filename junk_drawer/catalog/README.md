# Chart/stat catalog

This directory holds the master list of every chart TeamRankings exposes per league — the raw
material for the spreadsheet deliverable and the seed data for `silver.stat_catalog`.

## Status

The structural audit (`docs/CHART_AUDIT.md`) confirmed catalog page counts per league:

| League | Team-stat slugs | Player-stat slugs | Rating-type slugs |
|---|---|---|---|
| NFL | 150+ | 100+ | 24 |
| NBA | 150+ | 30+ | 24 |
| MLB | 141 | 100 | 22 |
| NCF | 146 | 67 | 24 |

The full slug lists (href + visible link text) were extracted during the audit but not yet
saved as structured files in this repo. Next step: re-run the extraction against the archived
HTML in `lake/bronze/reference/teamrankings/<timestamp>/*_stats.html` and
`*_player-stats.html`, and write one CSV per league here:

- `nfl_team_stats.csv`, `nfl_player_stats.csv`
- `nba_team_stats.csv`, `nba_player_stats.csv`
- `mlb_team_stats.csv`, `mlb_player_stats.csv`
- `ncf_team_stats.csv`, `ncf_player_stats.csv` (use `/college-football/stat/` and
  `/college-football/player-stat/` prefixes, not `/ncf/...`)

Each CSV: `slug,display_name,category`. Load into `silver.stat_catalog` via `sql/schema.sql`.

This is the next concrete task, not yet done.

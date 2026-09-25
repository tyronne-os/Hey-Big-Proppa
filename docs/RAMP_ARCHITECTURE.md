# The "ramp" pattern

A **ramp** is one league's complete pipeline: sources -> schema -> itemized chart
exports -> index. `nfl` is the first ramp. `cfb`, `nba`, `mlb`, `nhl` follow the same
shape later — same folder layout, same manifest convention, different source
adapters underneath.

## Why itemized, not one big file

Modeled on how nflverse itself ships data: one release *tag* per topic
(`stats_player`, `stats_team`, `pfr_advstats`, `pbp`, ...), each producing its own
small file. If one topic's data is stale or malformed, the others are unaffected --
nothing downstream has to parse a monolith to get at one chart.

We mirror that inside the lake. Every chart (in the PFR/TeamRankings sense -- one
table or one page's worth of data) gets:

- its own CSV under `lake/gold/nfl/<chart_name>.csv`
- its own row in `lake/gold/nfl/_index.csv` (the manifest)

A chart being broken, empty, or mid-refresh never blocks reading any other chart.
You can open exactly one CSV in a spreadsheet and see exactly one chart -- no
filtering a giant combined file.

## Layout

```
lake/
  bronze/                          # raw pulls, append-only, gitignored
    nflverse/<UTC-timestamp>/      # raw CSVs from nflverse, as fetched
    rotowire/<UTC-timestamp>/      # raw HTML snapshots from rotowire props page
  nfl.duckdb                       # working database (gitignored, rebuildable)
  gold/
    nfl/
      _index.csv                   # the manifest -- one row per chart
      player_passing_week.csv
      player_rushing_week.csv
      player_receiving_week.csv
      player_scrimmage_week.csv
      player_defense_week.csv
      player_scoring_week.csv
      player_kicking_week.csv
      player_returns_week.csv
      pfr_adv_passing_week.csv
      pfr_adv_rushing_week.csv
      pfr_adv_receiving_week.csv
      pfr_adv_defense_week.csv
      team_week.csv
      td_log.csv
      prop_line_rotowire.csv
      player_photos/
        _index.csv                # player_id -> local file, sha256, source url
        <player_id>.jpg
```

## The manifest (`_index.csv`)

One row per exported chart:

| column | meaning |
|---|---|
| `chart_name` | matches the CSV filename (no extension) |
| `source_table_or_view` | the DuckDB object it was exported from |
| `grain` | e.g. "one row per player per week" |
| `row_count` | as of last export |
| `last_exported_at_utc` | |
| `source_name` | nflverse \| rotowire \| tank01 |
| `status` | ok \| stale \| empty \| error |

A downstream consumer (spreadsheet, app, another script) reads `_index.csv` first to
see what's fresh before touching any individual chart file.

## Export is a separate step from loading

`scripts/ingest_*.py` load raw source data into `lake/nfl.duckdb` (silver/gold
schemas). A new `scripts/export_ramp.py` reads that database and writes the itemized
CSVs + manifest. Loading and exporting are decoupled on purpose: if the export step
breaks, the database (source of truth) is untouched and can be re-exported once fixed.

## Applying this to future ramps

When CFB/NBA/MLB/NHL are built, each gets its own `lake/gold/<league>/` folder with
the same `_index.csv` convention. The chart *names* differ per league (following
that league's own PFR-equivalent chart taxonomy), but the manifest columns and the
one-file-per-chart rule stay identical, so tooling written against `_index.csv`
works across every ramp without change.

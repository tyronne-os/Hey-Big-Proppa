---
title: frontal-lobe2
emoji: 🏈
colorFrom: blue
colorTo: gray
sdk: gradio
pinned: false
---
# frontal-lobe2

Chart-schema catalog and data-lake prep for a multi-sport (NFL, College Football, NBA, MLB —
NHL deferred, see `docs/NHL_GAP.md`) stats/odds pipeline. This repo captures **chart design**
(columns, splits/dropdowns, catalog of available charts), not TeamRankings' actual data values.
The goal: recreate every chart as a SQL schema, then wire each one to a free/legal live source
(ESPN, CFBD, nflverse, nba_api, MLB StatsAPI, The Odds API) in a later phase, and finally load
into a searchable data lake.

Mirrored to a private Hugging Face Space for backup + eventual app hosting:
`https://huggingface.co/spaces/AIBRUH/frontal-lobe2`

## Phases
1. **This repo, current state** — reverse-engineer chart structure from a TeamRankings reference
   pull, produce SQL `CREATE TABLE` schemas + a spreadsheet catalog. No live data yet.
2. **Next** — connect each schema to a live free-data wrapper (see `docs/DATA_SOURCES.md`).
3. **Later** — fold into a queryable, streaming-friendly data lake (DuckDB/Parquet, medallion
   bronze/silver/gold), per the `data-lake-foundation` pattern.

## Layout
- `docs/CHART_AUDIT.md` — structural findings from reading the raw HTML (what's real, what's
  missing, per league/page type)
- `docs/DATA_SOURCES.md` — recommended live-source mapping per league for phase 2
- `docs/NHL_GAP.md` — why NHL is deferred
- `sql/schema.sql` — the canonical schema derived from the chart audit
- `catalog/` — the stat/chart catalog (every individual chart slug found per league), the raw
  material for the spreadsheet deliverable
- `lake/bronze/reference/` — raw reference HTML pulls (gitignored; local only, not pushed)
- `scripts/pull_teamrankings.sh` — the reference-pull script (safe to keep; no secrets inside)

## Keys
Uses the same environment-variable convention as `great-lakes-cfb`: `CFBD_API_KEY`,
`THE_ODDS_API_KEY`, `GITHUB_TOKEN`, `HF_TOKEN`, etc. Never printed, logged, or committed.

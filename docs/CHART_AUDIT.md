# Chart structure audit (source: TeamRankings reference pull, 2026-09-24)

Pulled anonymously (no auth) into
`~/great-lakes-cfb/lake/bronze/reference/teamrankings/20260924T222408Z/` — 36 usable files across
NFL, NBA, MLB, NCF (NHL excluded, see `NHL_GAP.md`; one NCF stat sample 404'd on a wrong URL
prefix and was not re-pulled). This documents structure only — column headers, dropdown/split
controls, catalog links — never TeamRankings' actual stat values.

## The universal per-stat chart template

Every individual stat chart page (confirmed directly on one sample per league: NFL
`points-per-game`, NBA `points-per-game`, MLB `runs-per-game`) has the identical shape:

```
Rank | Team | <current_season> | Last 3 | Last 1 | Home | Away | <prior_season>
```

plus a `<select id="date">` season-year picker spanning ~15-20+ years back. This single template
covers every stat slug in the catalogs below — one normalized fact table, not one physical table
per stat (there are 600+ slugs across 4 leagues; a table-per-stat design does not scale).

## Per-league findings

### NFL
| Page | Header / structure | Splits found | Verdict |
|---|---|---|---|
| home | Rank, Rating, Team, Proj W, Proj L, Playoffs, Win SB | team chooser (33) | usable |
| stats (index) | no table — pure catalog | — | 150+ `/nfl/stat/<slug>` links extracted |
| standings | Rank, Overall W-L, Pct, GB, Div W-L, Home, Road, Streak, ×8 divisions | team chooser | usable |
| schedules | dynamic day headers, Time, Location | `week` (23), `group`/division (11) | usable (day = data, not a column) |
| odds | **grid empty** — AJAX-rendered client-side | `div` (11), `team` (33); AJAX endpoint `/ajax/league/v3/odds_controller.php` (`period_id`, `season_id`) | gap — needs headless capture |
| projections | 2-tier: Current/Projection/Playoffs → W,L,T / W,L,T / Playoffs%,WinDiv%,TopSeed%,WinSB% | team chooser | usable |
| player-stats (index) | no table — catalog | — | 100+ `/nfl/player-stat/<slug>` links |
| rankings (index) | Rating name, Best, Worst (meta-index only) | — | 24 rating-type slugs; per-team ranking table shape NOT captured |
| stat/points-per-game | canonical 8-col template | `date` (24 seasons), team chooser | usable — reference template |

### NBA
Same shape as NFL:
- home: Rank, Rating, Team, Proj W, Proj L, Playoffs, Champ — usable
- stats / player-stats: 0 tables, catalogs (150+ team-stat, 30+ player-stat slugs)
- standings: Rank, Overall W-L, Pct, GB, Div W-L, Home, Road, Streak per division — usable
- schedules: Rank, Hotness Score, Matchup, Time, Location; `group` division filter (7, incl. legacy "Midwest") — usable
- odds: all 6 tables showed "No matching games for this cat" (dead slate at capture time) — filter dims confirmed (`div` 7, `team` 30, Latest/History tabs) but **no real column values captured** — gap
- projections: 2-tier (Current/Projection/Playoffs → W,L / W,L / Playoffs%,WinDiv%,1Seed%,Champs%) — usable
- rankings: meta-index, 24 slugs — partial, same as NFL
- stat/points-per-game: canonical 8-col template confirmed, `date` spans 2003-04 through 2025-26 — usable

### MLB
- home: Rank, Rating, Team, Proj W, Proj L, Playoffs, WS Champs — usable
- stats / player-stats: 0 tables, catalogs (141 team-stat, 100 player-stat slugs — batting + pitching)
- standings: Rank, Overall W-L, Pct, GB, Div W-L, Home, Road, Streak, grouped AL/NL × East/Central/West — usable
- schedules: Rank, Hotness Score, Matchup, Time, Location; `group` division filter (6) — usable
- odds: 0 tables at all, AJAX form only (`div` 6, `team` 30) — gap
- projections: division-grouped, Current W/L, Projected W/L, Playoffs%, WinDiv%, TopSeed%, WSChamps% — usable
- rankings: 22 rating-type slugs — partial
- stat/runs-per-game: canonical 8-col template confirmed — usable, reference template

### NCF (college football)
Note: catalog/stat pages require the `/college-football/...` URL prefix, NOT `/ncf/...` — the
short `ncf` alias only works for the section root and a few top-level pages.
- home: Rank, Rating, Team, Proj W, Proj L, **SOS Rank, Luck Rank** (two extra columns vs pro leagues) — usable
- stats / player-stats: 0 tables, catalogs — 146 team-stat slugs, 67 player-stat slugs (via `/college-football/stat/` and `/college-football/player-stat/`)
- standings: 11 separate conference tables (not 2 like pro leagues); Team, Rank, Conf W-L, Pct, GB, Overall W-L, Home, Road, Streak; MAC table has an East/West sub-split doubling columns — usable
- schedules: date-pivoted headers; `week` (17, incl. Bowl Week), `group` (16: All, AP Top 25, Coaches' Poll, +13 conferences) — usable
- odds: 6 headerless tables (no `<th>`), Latest/History tabs, AJAX form (`div` 16, `team` 139 FBS/FCS) — gap
- projections: 3-tier (Current/Projection/Playoffs), W/L/**T** (CFB has ties) + Bowl Eligible%/WinConf%/Undefeated% — usable
- rankings: meta-index, 24 slugs incl. CFB-specific `neutral-by-other` — partial

## Confirmed gaps (apply to all 4 leagues)

1. **Odds board.** The real spread/total/moneyline grid is rendered client-side via a POST to
   `/ajax/league/v3/odds_controller.php` (params include `period_id`, `season_id`, `view`,
   `div`, `team`). A static HTML pull never sees it — only the filter form. Needs a headless
   browser (Playwright) capture, or calling that AJAX endpoint directly, to get real columns.
2. **Per-team ranking tables.** The `rankings` page for each league is a meta-index of ~22-24
   rating *types* (e.g. different power-rating systems), not a sample of what one actual
   per-team ranking grid looks like. Likely mirrors the home page's `Rank/Rating/Team` shape,
   but that's inferred, not confirmed. Needs one sample ranking-type page per league.

## What this is enough to build now

1. `stat_catalog(league, slug, display_name, category)` — from the 4 `stats`/`player-stats`
   index pages, ~600+ slugs total.
2. `team_stat_value(league, stat_slug, team, season, split, value)` — one normalized fact table
   for every per-game/per-stat chart, confirmed via 3 direct reference-page extractions.
3. `standings`, `projections`, `schedules` per league — division/conference-grouped, consistent
   column sets confirmed per league above.
4. `ranking_catalog(league, rating_name, best, worst)` — the rating-type list, but not the
   per-team ranking value table (needs a follow-up sample).

Not yet buildable: the real odds-board schema (needs the AJAX-capture follow-up).

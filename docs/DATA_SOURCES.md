# Recommended live-data sources per league (Phase 2)

Chart *design* comes from the TeamRankings audit (`CHART_AUDIT.md`). Actual live values should
come from these free/legal wrappers instead of scraping, once schemas are finalized.

| League | Primary source | Notes |
|---|---|---|
| NFL | ESPN unofficial endpoints (`site.api.espn.com`) for live scores/standings; `nflverse`/`nfl_data_py` for deep historical team & player stats | No key needed for ESPN's unofficial endpoints; nflverse is open data |
| College Football | CFBD (`collegefootballdata.com`), key already wired as `CFBD_API_KEY` | Confirm endpoint names against live OpenAPI docs before coding |
| NBA | `nba_api` (wraps stats.nba.com) for stats; ESPN or balldontlie for scores/standings | No key for `nba_api`; check balldontlie rate limits |
| MLB | MLB StatsAPI (`statsapi.mlb.com`, official, free, no key); `pybaseball` for historical | Official API, most reliable of the group |
| NHL | deferred — see `NHL_GAP.md`; likely candidate is the official NHL API (`api-web.nhle.com`, free, no key) | Not started |
| Odds (all leagues) | The Odds API, key already available as `THE_ODDS_API_KEY` (header `x-api-key` or query `apiKey`) | Covers DraftKings and other books; snapshot every fetch, never overwrite (append-only) |

## NFL ramp, finalized (2026-09-25)

Two reliable sources cover the entire NFL ramp end to end:

| Need | Source | Notes |
|---|---|---|
| Player/team stats (7 PFR chart families + returns), TD logs, headshots | **nflverse** | Open data, nightly updates in-season. See `docs/PFR_SOURCE_NOTE.md`. |
| Player prop lines (22 markets, DraftKings/FanDuel/Caesars) | **RotoWire** (`/betting/nfl/player-props.php`) | First-party embedded JSON, confirmed allowed by `robots.txt`. See below. |

Tank01 (RapidAPI) remains a documented option for injuries/depth charts/DFS
salaries if needed later -- not built yet, pending the user's own live test call
against their key (an API key should never be entered into this repo or this
chat). See the v1 repo's `TANK01_INTEGRATION_SETUP.md` for the original plan.

### RotoWire player props -- what was actually confirmed

- `robots.txt` allows `/betting/` (only `/users/login.php?` and `/account/` are
  disallowed).
- The real prop lines are RotoWire's own first-party betting tables, embedded as
  JSON directly in the page's static HTML -- a plain HTTP GET returns the data
  already in the response body. No JS execution or headless browser needed.
- `isPaywalled = true` in the page's own JS only gates RotoWire's **CSV export**
  button ("must be a paid subscriber" to click *Export*). It does not hide or
  restrict the underlying data, which is visible to any visitor.
- The page also embeds an unrelated third-party "Props.Cash" demo widget with
  its own weather-context feed (a personal Val Town endpoint). That widget is
  explicitly NOT used as a source -- only RotoWire's own tables are.
- 22 markets confirmed populated: 5 TD-scorer types (first/anytime/last/2+/3+),
  5 passing, 2 rushing, 3 receiving, 4 defense, 3 kicking.
- 10 books appear in the source overall; **scoped down to draftkings, fanduel,
  caesars by request**. bet365 was requested too but does not appear on this
  source at all -- would need a different source if required.
- Lines move during the week, so every pull is an append-only snapshot
  (`gold.nfl_prop_line_rotowire`), never an overwrite -- needed for closing-line
  value (CLV) analysis later.

## Why not scrape TeamRankings for live data

TeamRankings was used only as a **design reference** (chart layout, column names, splits) during
an authorized, logged-in personal pull. Live production data should come from the sources above:
faster, no ToS risk, no session/cookie maintenance, and typically better raw granularity
(box scores, play-by-play) than a stats-aggregator site exposes.

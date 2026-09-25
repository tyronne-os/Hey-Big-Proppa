# NHL: deferred

TeamRankings does not have an NHL section. Confirmed two ways during the reference pull
(2026-09-24):

- Every `/nhl/...` URL (root, `stats/`, `standings/`, `schedules/`, `odds/`, `projections/`,
  `player-stats/`, `rankings/`, `stat/goals-per-game`) returned an HTTP 200 but with an
  **identical sha256 hash** across all 8 pages, and the `<title>` tag was the generic
  TeamRankings homepage title, not anything NHL-specific. `curl -L` was following a redirect
  to the homepage/catch-all for a section that doesn't exist.
- A web search for `site:teamrankings.com nhl stats` returned no NHL-specific pages; every
  result was NFL/NBA/MLB/CFB.

## Options for a future pass
1. Model NHL chart schemas from the official NHL API (`api-web.nhle.com`, free, no key) directly
   instead of scraping a chart site.
2. Find an alternate NHL stats/odds reference site with a similar chart layout to mirror.
3. Skip NHL charts entirely and build NHL's schema straight from whatever the live API returns,
   skipping the "recreate a chart design" step used for the other 4 leagues.

Not resolved yet — revisit when NHL is prioritized.

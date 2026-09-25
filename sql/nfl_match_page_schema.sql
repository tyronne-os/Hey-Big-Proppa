-- =============================================================================
-- frontal-lobe2 : THE MATCH PAGE -- the lead page for this lake and every ramp
-- to come. A strict, hardcoded query chain, deterministic, no model logic:
--
--   1. what is today                         -> v_today
--   2. are there NFL games today (yes/no)    -> v_games_today_flag
--   3. if yes, list the matchups             -> v_matchups_today
--   4. for each matchup: inactives, weather  -> v_matchup_inactives,
--      signal, and odds                         v_matchup_weather_signal,
--                                                v_matchup_odds
--
-- This chain is deliberately simple SQL, not application code, per the user's
-- explicit request: "these are static queries the loop or jobs" and "there
-- are things i want hard coded." Impact SCORING of weather/inactives is
-- explicitly deferred to a later "logic engine" phase -- this layer only
-- surfaces the raw signal, it does not judge it.
--
-- Engine: DuckDB. "Today" is CURRENT_DATE, i.e. the database engine's own
-- clock at query time -- never a value baked into a table, so this chain is
-- correct on any day it's run, not just the day it was built.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- -----------------------------------------------------------------------------
-- STEP 1: what is today. The single anchor everything else depends on.
--
-- Anchored explicitly to America/Chicago (US Central) -- the user's own
-- timezone (New Orleans) -- NOT the host machine's local timezone. Confirmed
-- during this build: the host container is CDT, and naive CURRENT_DATE gave
-- a different answer than an explicit-timezone version depending on time of
-- day. This bug would silently vary by which machine runs the query.
--
-- NOTE: NFL scheduling itself (gametime strings in silver.nfl_schedule) is
-- published in US/Eastern by the league; game_time_local_cst below converts
-- that to the user's Central time for DISPLAY. The "is there a game today"
-- date comparison still correctly uses the calendar date, which does not
-- shift between Eastern and Central on the same day for any NFL kickoff time
-- (earliest kickoffs are ~11am CT / 12pm ET, never near a date boundary).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_today AS
SELECT CAST(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago' AS DATE) AS today_date,
       CURRENT_TIMESTAMP AS as_of_utc,
       dayname(CAST(CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago' AS DATE)) AS weekday;

-- -----------------------------------------------------------------------------
-- STEP 2: are there any NFL games today. A single-row yes/no flag with a count.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_games_today_flag AS
SELECT t.today_date,
       count(s.game_id) > 0 AS has_games_today,
       count(s.game_id) AS game_count
FROM gold.v_today t
LEFT JOIN silver.nfl_schedule s ON s.game_date = t.today_date
GROUP BY t.today_date;

-- -----------------------------------------------------------------------------
-- STEP 3: the matchup list for today (empty result set is a valid, correct
-- answer on a non-game day -- the chain must not error or fake a matchup).
-- -----------------------------------------------------------------------------
-- game_time_local in silver.nfl_schedule is published by the league in
-- US/Eastern (confirmed: a game at Melbourne Cricket Ground shows 20:35,
-- the same convention as a normal US Eastern-time evening kickoff -- this is
-- NOT literal stadium-local time). game_time_cst below converts to the
-- user's own timezone (New Orleans, US/Central) for display. ET is always
-- exactly 1 hour ahead of CT (both observe DST on the same schedule), so this
-- is a flat, safe offset -- no timezone-library edge cases.
CREATE OR REPLACE VIEW gold.v_matchups_today AS
SELECT s.game_id, s.season, s.week, s.game_date, s.weekday,
       s.game_time_local AS game_time_et,
       strftime(s.game_date + CAST(s.game_time_local AS TIME)
                - INTERVAL 1 HOUR, '%H:%M') AS game_time_cst,
       s.away_team, s.home_team, s.location, s.roof, s.surface, s.div_game
FROM silver.nfl_schedule s
WHERE s.game_date = CURRENT_DATE
ORDER BY s.game_time_local;

-- A "next games" view is the practical companion to v_matchups_today --
-- most days have zero games today, so this answers "what's coming up" without
-- changing the hardcoded yes/no chain above.
CREATE OR REPLACE VIEW gold.v_matchups_upcoming AS
SELECT s.game_id, s.season, s.week, s.game_date, s.weekday,
       s.game_time_local AS game_time_et,
       strftime(s.game_date + CAST(s.game_time_local AS TIME)
                - INTERVAL 1 HOUR, '%H:%M') AS game_time_cst,
       s.away_team, s.home_team, s.location, s.roof, s.surface, s.div_game,
       s.game_date - CURRENT_DATE AS days_until
FROM silver.nfl_schedule s
WHERE s.game_date > CURRENT_DATE
ORDER BY s.game_date, s.game_time_local;

-- -----------------------------------------------------------------------------
-- STEP 4a: inactives/injury status per matchup. Two distinct signals kept
-- separate on purpose -- do not blur them:
--   - official Wed/Thu/Fri practice-report status (the closest proxy we have)
--   - the TRUE final inactives list is NOT available from any source in this
--     ramp (released ~90 min pre-kickoff; see docs/MATCH_PAGE.md). This view
--     is the proxy, clearly labeled as such, not the real thing.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_matchup_inactives AS
SELECT s.game_id, s.game_date, s.away_team, s.home_team,
       r.team, r.full_name, r.position, r.report_status, r.report_primary_injury,
       r.practice_status,
       'practice_report_proxy -- NOT the final inactives list' AS signal_type
FROM silver.nfl_schedule s
JOIN silver.nfl_injury_report r
  ON r.team IN (s.away_team, s.home_team)
 AND r.season = s.season
 AND r.week = s.week
WHERE r.report_status IS NOT NULL
ORDER BY s.game_id,
         CASE r.report_status WHEN 'Out' THEN 0 WHEN 'Doubtful' THEN 1
                               WHEN 'Questionable' THEN 2 ELSE 3 END;

-- -----------------------------------------------------------------------------
-- STEP 4b: weather signal per matchup. Raw signal only -- no impact score
-- (that's explicitly the logic engine's job later). Two honest distinctions:
--   - roof/surface: KNOWN ahead of time (fixed stadium property) for every
--     game, past or future.
--   - temp_actual/wind_actual: ONLY populated for games already played
--     (recorded conditions). For an upcoming game these will be NULL --
--     that's correct, not a bug; a real pre-game FORECAST needs a different,
--     forward-looking source not built in this ramp yet.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_matchup_weather_signal AS
SELECT game_id, game_date, away_team, home_team,
       roof, surface,
       temp_actual, wind_actual,
       CASE WHEN roof = 'outdoors' THEN true ELSE false END AS is_outdoor_venue,
       CASE WHEN temp_actual IS NULL THEN 'no_recorded_conditions_yet_or_forecast_not_sourced'
            WHEN roof != 'outdoors' THEN 'indoor_venue_weather_not_a_factor'
            WHEN temp_actual <= 32 THEN 'freezing'
            WHEN temp_actual >= 90 THEN 'extreme_heat'
            WHEN wind_actual >= 20 THEN 'high_wind'
            ELSE 'no_extreme_flag' END AS weather_flag_hardcoded_threshold
FROM silver.nfl_schedule;

-- -----------------------------------------------------------------------------
-- STEP 4c: odds per matchup -- BOTH sources, clearly separated by grain.
--   - game-level (spread/total/moneyline): from the schedule feed itself.
--   - player-prop lines: from RotoWire, already snapshotted for line
--     movement (gold.nfl_prop_line_rotowire / gold.v_nfl_prop_best_price).
-- Kept as two views, not merged, since they are different grains (team vs.
-- player) and merging them would hide that distinction from whatever reads
-- this next (the Lake Logic phase the user referenced).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_matchup_game_odds AS
SELECT game_id, game_date, away_team, home_team,
       spread_line, away_spread_odds, home_spread_odds,
       total_line, over_odds, under_odds,
       away_moneyline, home_moneyline,
       'nflverse_schedule -- reference line, not a live-updating snapshot' AS source_note
FROM silver.nfl_schedule
WHERE spread_line IS NOT NULL OR total_line IS NOT NULL;

-- NOTE on the join: RotoWire's game_id (a RotoWire-internal numeric id, e.g.
-- "2978668") and the nflverse schedule's game_id (e.g. "2026_03_ATL_GB") are
-- two entirely different ID schemes -- confirmed while building this view;
-- joining on game_id directly returns zero rows even when real prop data
-- exists for both teams. Joining on team membership instead (a prop's player
-- team is one of the two teams in the matchup) is the correct link until a
-- real cross-source game_id bridge is built.
CREATE OR REPLACE VIEW gold.v_matchup_prop_odds AS
SELECT s.game_id, s.game_date, s.away_team, s.home_team,
       pl.player_name, pl.market_slug, pl.line,
       pl.best_over_book, pl.best_over_price, pl.best_under_book, pl.best_under_price,
       pl.best_moneyline_book, pl.best_moneyline_price
FROM silver.nfl_schedule s
JOIN gold.nfl_prop_line_rotowire raw
  ON raw.team IN (s.away_team, s.home_team)
JOIN gold.v_nfl_prop_best_price pl
  ON pl.player_id = raw.player_id AND pl.market_slug = raw.market_slug
GROUP BY s.game_id, s.game_date, s.away_team, s.home_team, pl.player_name,
         pl.market_slug, pl.line, pl.best_over_book, pl.best_over_price,
         pl.best_under_book, pl.best_under_price, pl.best_moneyline_book,
         pl.best_moneyline_price;

-- -----------------------------------------------------------------------------
-- The full bundle, one row set per matchup for TODAY only. If v_games_today_flag
-- says false, this returns zero rows -- correct behavior, not an error.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gold.v_match_page_today AS
SELECT m.game_id, m.season, m.week, m.game_date, m.weekday, m.game_time_et, m.game_time_cst,
       m.away_team, m.home_team, m.roof, m.surface, m.div_game,
       (SELECT count(*) FROM gold.v_matchup_inactives i WHERE i.game_id = m.game_id) AS inactive_signal_count,
       (SELECT weather_flag_hardcoded_threshold FROM gold.v_matchup_weather_signal w
        WHERE w.game_id = m.game_id) AS weather_flag,
       (SELECT count(*) FROM gold.v_matchup_game_odds o WHERE o.game_id = m.game_id) AS has_game_odds,
       (SELECT count(*) FROM gold.v_matchup_prop_odds p WHERE p.game_id = m.game_id) AS prop_line_count
FROM gold.v_matchups_today m;

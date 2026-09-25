-- =============================================================================
-- frontal-lobe2 : NFL schedule -- the backbone the Match Page is built on
-- =============================================================================
-- Fixes a confirmed real gap: silver.nfl_game (sql/nfl_pfr_schema.sql) has
-- home_team/away_team/kickoff_utc as NULL for every row -- those columns were
-- defined but the loader never had a source that actually populated them.
-- This is that source.
--
-- Source: nflverse-data 'schedules' release (games.csv), confirmed live with
-- real 2026 data 2026-09-25. 272 games for the 2026 season.
--
-- Confirmed field behavior (not assumed):
--   - gameday/gametime: populated for ALL games, past and future.
--   - spread_line/total_line/home_moneyline/away_moneyline: populated for
--     BOTH past AND upcoming games (e.g. 2026_03_LAC_BUF, played 2026-09-27,
--     already carries spread=7, total=50.5 as of 2026-09-25). This is a
--     second, independent game-level odds source alongside RotoWire's
--     player-prop lines -- different grain (team spread/total vs. player
--     prop), kept in separate tables, not merged.
--   - temp/wind/roof/surface: temp and wind are ONLY populated for games
--     that have already been played (recorded actual conditions), NOT a
--     forward-looking forecast. Confirmed: only 20/272 2026 games have a
--     temp value, and all upcoming games show blank. roof/surface (dome vs
--     outdoors, turf vs grass) ARE known ahead of time and populated for
--     upcoming games too -- that's a fixed stadium property, not a forecast.
--   - A real weather FORECAST for upcoming games would need a different,
--     forward-looking source -- not built here. See docs/MATCH_PAGE.md.
--
-- Engine: DuckDB.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

CREATE TABLE IF NOT EXISTS silver.nfl_schedule (
    game_id             VARCHAR PRIMARY KEY,     -- matches game_id used elsewhere (nfl_td_log, player-week tables)
    season              INTEGER NOT NULL,
    game_type           VARCHAR,                 -- REG | WC | DIV | CON | SB etc.
    week                INTEGER NOT NULL,
    game_date           DATE NOT NULL,            -- gameday
    weekday             VARCHAR,
    game_time_local     VARCHAR,                  -- gametime, as published (stadium-local, not normalized to UTC -- see docs)
    away_team           VARCHAR NOT NULL,
    home_team           VARCHAR NOT NULL,
    away_score          INTEGER,                  -- NULL until played
    home_score          INTEGER,
    location             VARCHAR,                 -- 'Home' | 'Neutral'
    result_margin        INTEGER,                  -- home - away, once played
    total_points          INTEGER,
    overtime              BOOLEAN,
    -- fixed stadium properties, known ahead of time (not a forecast)
    roof                  VARCHAR,                 -- outdoors | dome | closed | open
    surface               VARCHAR,                 -- grass | turf variants
    stadium_id            VARCHAR,
    stadium               VARCHAR,
    -- recorded actual conditions -- ONLY populated after the game is played
    temp_actual            INTEGER,
    wind_actual            INTEGER,
    -- game-level odds (spread/total/moneyline). Populated for upcoming games
    -- too, unlike temp/wind. Historical rows show the CLOSING line, not
    -- necessarily what a book showed pre-game -- treat as a reference line,
    -- not a live-updating snapshot (RotoWire's prop lines ARE snapshotted
    -- for movement; this schedule feed is not).
    spread_line            DOUBLE,                  -- home team spread (negative = home favored)
    away_spread_odds       INTEGER,
    home_spread_odds       INTEGER,
    total_line             DOUBLE,
    over_odds              INTEGER,
    under_odds             INTEGER,
    away_moneyline         INTEGER,
    home_moneyline         INTEGER,
    div_game               BOOLEAN,
    away_qb_name           VARCHAR,
    home_qb_name           VARCHAR,
    away_coach             VARCHAR,
    home_coach             VARCHAR,
    referee                VARCHAR,
    ingest_run_id          VARCHAR NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_schedule_date ON silver.nfl_schedule (game_date);
CREATE INDEX IF NOT EXISTS ix_schedule_season_week ON silver.nfl_schedule (season, week);
CREATE INDEX IF NOT EXISTS ix_schedule_teams ON silver.nfl_schedule (home_team, away_team);

-- =============================================================================
-- ATS (against the spread) -- computed here, not sourced elsewhere.
-- Checked nflverse's own release catalog (stats_player, stats_team, pbp,
-- injuries, schedules, pfr_advstats, snap_counts, depth_charts): none of them
-- publish a rolling covers-percentage stat. That's not a gap in what we
-- pulled -- nflverse simply doesn't track that as a derived metric. But we
-- don't need a new source for it: this table already has real closing
-- spreads + real final scores for every played game, which is 100% of what
-- ATS math needs. "Last 5 covers %" is a rolling window over data we already
-- have, not a missing-source problem.
-- =============================================================================

-- One row per team per game they played, spread-adjusted result. Both home
-- and away perspectives are unioned so every team has one row per game.
CREATE OR REPLACE VIEW silver.v_nfl_team_ats_game AS
SELECT game_id, season, week, game_date, home_team AS team, away_team AS opponent,
       true AS was_home, -spread_line AS spread_needed, result_margin AS actual_margin,
       CASE WHEN result_margin > -spread_line THEN 'cover'
            WHEN result_margin < -spread_line THEN 'no_cover' ELSE 'push' END AS ats_result
FROM silver.nfl_schedule
WHERE home_score IS NOT NULL AND spread_line IS NOT NULL
UNION ALL
SELECT game_id, season, week, game_date, away_team, home_team,
       false, spread_line, -result_margin,
       CASE WHEN -result_margin > spread_line THEN 'cover'
            WHEN -result_margin < spread_line THEN 'no_cover' ELSE 'push' END
FROM silver.nfl_schedule
WHERE home_score IS NOT NULL AND spread_line IS NOT NULL;

-- Season-to-date ATS record + rolling last-5 and last-10 windows per team.
-- Uses DuckDB window functions ordered by game_date so "last 5" always means
-- the 5 most recent played games for that team, regardless of week gaps
-- (byes) -- not a fixed week range.
CREATE OR REPLACE VIEW silver.v_nfl_team_ats_rolling AS
SELECT game_id, season, week, game_date, team, opponent, was_home,
       spread_needed, actual_margin, ats_result,
       row_number() OVER (PARTITION BY team, season ORDER BY game_date) AS game_num,
       sum(CASE WHEN ats_result = 'cover' THEN 1 ELSE 0 END)
           OVER (PARTITION BY team, season ORDER BY game_date
                 ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS covers_last_5,
       count(*) FILTER (WHERE ats_result != 'push')
           OVER (PARTITION BY team, season ORDER BY game_date
                 ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS graded_games_last_5,
       sum(CASE WHEN ats_result = 'cover' THEN 1 ELSE 0 END)
           OVER (PARTITION BY team, season ORDER BY game_date
                 ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS covers_last_10,
       count(*) FILTER (WHERE ats_result != 'push')
           OVER (PARTITION BY team, season ORDER BY game_date
                 ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS graded_games_last_10
FROM silver.v_nfl_team_ats_game;

-- The actual "who covers, who doesn't" leaderboard, as of the most recent
-- game each team has played. Percentage, not just raw counts.
CREATE OR REPLACE VIEW silver.v_nfl_team_ats_current AS
SELECT team,
       max(game_num) AS games_played_this_season,
       max_by(covers_last_5, game_num) AS covers_last_5,
       max_by(graded_games_last_5, game_num) AS games_last_5,
       round(100.0 * max_by(covers_last_5, game_num)
             / NULLIF(max_by(graded_games_last_5, game_num), 0), 1) AS cover_pct_last_5,
       max_by(covers_last_10, game_num) AS covers_last_10,
       max_by(graded_games_last_10, game_num) AS games_last_10,
       round(100.0 * max_by(covers_last_10, game_num)
             / NULLIF(max_by(graded_games_last_10, game_num), 0), 1) AS cover_pct_last_10
FROM silver.v_nfl_team_ats_rolling
GROUP BY team
ORDER BY cover_pct_last_5 DESC NULLS LAST;

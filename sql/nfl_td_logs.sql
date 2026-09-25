-- =============================================================================
-- frontal-lobe2 : NFL touchdown scoring logs  (all 32 teams, no manual paste)
-- =============================================================================
-- Recreates the two PFR team-page charts:
--   /teams/<abbr>/2026.htm#all_team_td_log   -> team touchdowns scored
--   /teams/<abbr>/2026.htm#all_opp_td_log    -> touchdowns allowed to opponents
--
-- KEY INSIGHT: those two PFR charts are two views of the SAME touchdown event --
-- one from the scoring team's side, one from the conceding defense's side. So we
-- store one row per touchdown play and expose two views. No duplicated storage,
-- and no scraping 32 separate team pages.
--
-- SOURCE: nflverse play_by_play_<season> (open data). Every touchdown play carries
-- td_team, td_player_id/name, quarter, clock, yardline_100, down, goal_to_go and
-- pass/rush/return flags -- so the log is reconstructed exactly, with MORE detail
-- than PFR's own chart (PFR omits down and goal-to-go context).
-- Verified against real 2026 data 2026-09-24: 162 TD plays, all 32 teams, wks 1-2.
--
-- Reuses the table design from the earlier great-lakes-v1 work
-- (sql-data-lake-builder/schema/nfl_touchdown_logs.sql) rather than reinventing it.
--
-- Engine: DuckDB. Depends on sql/nfl_pfr_schema.sql for the bronze/silver schemas.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;

-- One row per touchdown play. This is the grain PFR's TD logs are built from.
CREATE TABLE IF NOT EXISTS silver.nfl_td_log (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR,
    game_id                 VARCHAR NOT NULL,
    play_id                 INTEGER NOT NULL,
    game_date               DATE,
    -- who scored / who conceded
    scoring_team            VARCHAR NOT NULL,      -- td_team
    defense_team            VARCHAR,               -- team that allowed it
    is_offensive_td         BOOLEAN,               -- scoring team had possession
    -- scorer
    scorer_player_id        VARCHAR,
    scorer_player_name      VARCHAR,
    td_type                 VARCHAR,               -- pass | rush | return | other
    -- game context
    qtr                     INTEGER,
    clock                   VARCHAR,               -- game clock at the play
    drive                   INTEGER,
    -- situational context (this is the part PFR's chart does NOT give you)
    yardline_100            INTEGER,               -- yards from opponent goal line
    is_red_zone             BOOLEAN,               -- yardline_100 <= 20
    is_goal_to_go           BOOLEAN,
    down                    INTEGER,
    is_third_down           BOOLEAN,
    -- passing detail when applicable
    passer_player_id        VARCHAR,
    passer_player_name      VARCHAR,
    -- score state after the play
    posteam_score_post      INTEGER,
    defteam_score_post      INTEGER,
    play_description        VARCHAR,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, game_id, play_id)
);

CREATE INDEX IF NOT EXISTS ix_td_log_scoring ON silver.nfl_td_log (season, scoring_team, week);
CREATE INDEX IF NOT EXISTS ix_td_log_defense ON silver.nfl_td_log (season, defense_team, week);
CREATE INDEX IF NOT EXISTS ix_td_log_scorer  ON silver.nfl_td_log (season, scorer_player_id);

-- =============================================================================
-- PFR #all_team_td_log  -- touchdowns a team SCORED
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_team_td_log AS
SELECT season, week, game_id, game_date,
       scoring_team              AS team,
       defense_team              AS opponent,
       qtr, clock, drive,
       scorer_player_name, scorer_player_id, td_type,
       passer_player_name,
       yardline_100, is_red_zone, is_goal_to_go, down, is_third_down,
       play_description
FROM silver.nfl_td_log
ORDER BY season, week, game_id, qtr;

-- =============================================================================
-- PFR #all_opp_td_log  -- touchdowns a team ALLOWED
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_opp_td_log AS
SELECT season, week, game_id, game_date,
       defense_team             AS team,          -- the team that gave it up
       scoring_team             AS opponent,
       qtr, clock, drive,
       scorer_player_name, scorer_player_id, td_type,
       passer_player_name,
       yardline_100, is_red_zone, is_goal_to_go, down, is_third_down,
       play_description
FROM silver.nfl_td_log
WHERE defense_team IS NOT NULL
ORDER BY season, week, game_id, qtr;

-- =============================================================================
-- Rollups: scored vs. allowed per team, with situational splits.
-- This is the shape that actually feeds a matchup edge -- a team that concedes
-- red-zone TDs at a high rate against a team that reaches the red zone often is
-- where a total or anytime-TD prop gets mispriced.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_td_scored_rollup AS
SELECT season, scoring_team AS team,
       count(*)                                              AS tds_scored,
       sum(CASE WHEN td_type='pass'   THEN 1 ELSE 0 END)      AS passing_tds,
       sum(CASE WHEN td_type='rush'   THEN 1 ELSE 0 END)      AS rushing_tds,
       sum(CASE WHEN td_type='return' THEN 1 ELSE 0 END)      AS return_tds,
       sum(CASE WHEN is_red_zone     THEN 1 ELSE 0 END)       AS red_zone_tds,
       sum(CASE WHEN is_goal_to_go   THEN 1 ELSE 0 END)       AS goal_to_go_tds,
       sum(CASE WHEN is_third_down   THEN 1 ELSE 0 END)       AS third_down_tds,
       count(DISTINCT week)                                   AS weeks_played,
       1.0 * count(*) / NULLIF(count(DISTINCT game_id), 0)    AS tds_per_game
FROM silver.nfl_td_log
GROUP BY season, scoring_team;

CREATE OR REPLACE VIEW silver.v_nfl_td_allowed_rollup AS
SELECT season, defense_team AS team,
       count(*)                                              AS tds_allowed,
       sum(CASE WHEN td_type='pass'   THEN 1 ELSE 0 END)      AS passing_tds_allowed,
       sum(CASE WHEN td_type='rush'   THEN 1 ELSE 0 END)      AS rushing_tds_allowed,
       sum(CASE WHEN td_type='return' THEN 1 ELSE 0 END)      AS return_tds_allowed,
       sum(CASE WHEN is_red_zone     THEN 1 ELSE 0 END)       AS red_zone_tds_allowed,
       sum(CASE WHEN is_goal_to_go   THEN 1 ELSE 0 END)       AS goal_to_go_tds_allowed,
       sum(CASE WHEN is_third_down   THEN 1 ELSE 0 END)       AS third_down_tds_allowed,
       count(DISTINCT week)                                   AS weeks_played,
       1.0 * count(*) / NULLIF(count(DISTINCT game_id), 0)    AS tds_allowed_per_game
FROM silver.nfl_td_log
WHERE defense_team IS NOT NULL
GROUP BY season, defense_team;

-- Both sides of the ball in one row per team -- the matchup view.
CREATE OR REPLACE VIEW silver.v_nfl_td_team_summary AS
SELECT COALESCE(s.season, a.season)  AS season,
       COALESCE(s.team, a.team)      AS team,
       s.tds_scored, s.red_zone_tds, s.goal_to_go_tds, s.third_down_tds,
       s.tds_per_game,
       a.tds_allowed, a.red_zone_tds_allowed, a.goal_to_go_tds_allowed,
       a.third_down_tds_allowed, a.tds_allowed_per_game,
       COALESCE(s.tds_scored, 0) - COALESCE(a.tds_allowed, 0) AS td_differential
FROM silver.v_nfl_td_scored_rollup s
FULL OUTER JOIN silver.v_nfl_td_allowed_rollup a
  ON s.season = a.season AND s.team = a.team;

-- Anytime-TD scorer leaderboard -- directly comparable to an anytime-TD prop.
CREATE OR REPLACE VIEW silver.v_nfl_anytime_td_scorers AS
SELECT season, scorer_player_id, scorer_player_name,
       ANY_VALUE(scoring_team)                           AS team,
       count(*)                                          AS total_tds,
       count(DISTINCT game_id)                           AS games_with_td,
       sum(CASE WHEN td_type='rush' THEN 1 ELSE 0 END)   AS rushing_tds,
       sum(CASE WHEN td_type='pass' THEN 1 ELSE 0 END)   AS receiving_tds,
       sum(CASE WHEN is_red_zone    THEN 1 ELSE 0 END)   AS red_zone_tds
FROM silver.nfl_td_log
WHERE scorer_player_id IS NOT NULL
GROUP BY season, scorer_player_id, scorer_player_name
ORDER BY total_tds DESC;

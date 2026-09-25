-- =============================================================================
-- frontal-lobe2 : NFL "Pro-Football-Reference style" schema section
-- =============================================================================
-- Recreates the chart/table design of the PFR 2026 season pages:
--   passing.htm | rushing.htm | receiving.htm | scrimmage.htm
--   defense.htm | scoring.htm | kicking.htm
-- for BOTH players and teams.
--
-- SCOPE: 2026 season only (current season). Season is still a column everywhere so
-- scaling to more seasons later is a data change, not a schema change.
--
-- GRAIN: one row per player (or team) PER WEEK PER GAME. This is deliberate --
-- season totals are a derived view (see bottom), not the base table. Prop markets
-- are priced per game, so week grain is required to go head-to-head with a book's
-- line on a specific matchup.
--
-- SOURCE OF COLUMNS: verified against real nflverse 2026 files on 2026-09-24
-- (weeks 1-2 present, REG season). NOT scraped from PFR -- PFR sits behind a
-- Cloudflare bot challenge (HTTP 403 on every path incl. robots.txt) and its ToS
-- prohibits harvesting. nflverse republishes the same underlying stats as open
-- data, including a direct mirror of PFR advanced stats. See docs/PFR_SOURCE_NOTE.md.
--
-- Engine: DuckDB.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- =============================================================================
-- BRONZE: ingestion audit. One row per loader run so any silver row can be traced
-- back to the exact pull that produced it (ingest_run_id on every fact table).
-- =============================================================================
CREATE TABLE IF NOT EXISTS bronze.ingestion_runs (
    run_id          VARCHAR PRIMARY KEY,
    source_name     VARCHAR NOT NULL,          -- 'nflverse' | 'nflverse_pbp'
    source_kind     VARCHAR NOT NULL,          -- 'api' | 'html_snapshot'
    league          VARCHAR,
    started_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    row_count       INTEGER,
    status          VARCHAR NOT NULL,          -- success | failed
    error_message   VARCHAR
);

-- =============================================================================
-- SHARED DIMENSIONS
-- =============================================================================

-- Player identity. nflverse gpsis/player_id is the join key; pfr_player_id lets us
-- reconcile against anything PFR-derived (advanced stats arrive keyed that way).
CREATE TABLE IF NOT EXISTS silver.nfl_player (
    player_id           VARCHAR PRIMARY KEY,      -- nflverse player_id
    pfr_player_id       VARCHAR,                  -- PFR id, from advstats feeds
    player_name         VARCHAR,                  -- short/abbrev form
    player_display_name VARCHAR NOT NULL,
    position            VARCHAR,
    position_group      VARCHAR,
    headshot_url        VARCHAR
);
CREATE INDEX IF NOT EXISTS ix_nfl_player_pfr ON silver.nfl_player (pfr_player_id);

-- Game spine. Every stat row hangs off (season, week, game_id).
CREATE TABLE IF NOT EXISTS silver.nfl_game (
    game_id         VARCHAR PRIMARY KEY,          -- nflverse game_id
    pfr_game_id     VARCHAR,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    season_type     VARCHAR NOT NULL,             -- REG | POST
    home_team       VARCHAR,
    away_team       VARCHAR,
    kickoff_utc     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_nfl_game_sw ON silver.nfl_game (season, week);

-- =============================================================================
-- PLAYER TABLES -- one per PFR page, matching that page's chart
-- =============================================================================

-- PFR passing.htm  (#all_passing)
CREATE TABLE IF NOT EXISTS silver.nfl_player_passing_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    completions             INTEGER,
    attempts                INTEGER,
    passing_yards           INTEGER,
    passing_tds             INTEGER,
    passing_interceptions   INTEGER,
    sacks_suffered          DOUBLE,
    sack_yards_lost         INTEGER,
    sack_fumbles            INTEGER,
    sack_fumbles_lost       INTEGER,
    passing_air_yards       INTEGER,
    passing_yards_after_catch DOUBLE,
    passing_first_downs     INTEGER,
    passing_epa             DOUBLE,
    passing_cpoe            DOUBLE,
    passing_2pt_conversions INTEGER,
    pacr                    DOUBLE,               -- passing air conversion ratio
    passing_10              INTEGER,              -- completions of 10+ air yds
    passing_16              INTEGER,
    passing_20              INTEGER,
    passing_40              INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR rushing.htm  (#all_rushing)
CREATE TABLE IF NOT EXISTS silver.nfl_player_rushing_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    carries                 INTEGER,
    rushing_yards           INTEGER,
    rushing_tds             INTEGER,
    rushing_fumbles         INTEGER,
    rushing_fumbles_lost    INTEGER,
    rushing_first_downs     INTEGER,
    rushing_epa             DOUBLE,
    rushing_2pt_conversions INTEGER,
    rushing_10              INTEGER,              -- rushes of 10+ yds
    rushing_12              INTEGER,
    rushing_20              INTEGER,
    rushing_40              INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR receiving.htm  (#all_receiving)
CREATE TABLE IF NOT EXISTS silver.nfl_player_receiving_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    receptions              INTEGER,
    targets                 INTEGER,
    receiving_yards         INTEGER,
    receiving_tds           INTEGER,
    receiving_fumbles       INTEGER,
    receiving_fumbles_lost  INTEGER,
    receiving_air_yards     INTEGER,
    receiving_yards_after_catch DOUBLE,
    receiving_first_downs   INTEGER,
    receiving_epa           DOUBLE,
    receiving_2pt_conversions INTEGER,
    receiving_10            INTEGER,
    receiving_16            INTEGER,
    receiving_20            INTEGER,
    receiving_40            INTEGER,
    racr                    DOUBLE,               -- receiver air conversion ratio
    target_share            DOUBLE,
    air_yards_share         DOUBLE,
    wopr                    DOUBLE,               -- weighted opportunity rating
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR scrimmage.htm  (#all_scrimmage) -- rushing + receiving combined ("all-purpose").
-- Kept as its own table because PFR presents it as its own chart with derived totals.
CREATE TABLE IF NOT EXISTS silver.nfl_player_scrimmage_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    touches                 INTEGER,              -- carries + receptions
    scrimmage_yards         INTEGER,              -- rushing_yards + receiving_yards
    scrimmage_tds           INTEGER,              -- rushing_tds + receiving_tds
    yards_per_touch         DOUBLE,
    scrimmage_first_downs   INTEGER,
    scrimmage_fumbles       INTEGER,
    carries                 INTEGER,
    rushing_yards           INTEGER,
    rushing_tds             INTEGER,
    receptions              INTEGER,
    targets                 INTEGER,
    receiving_yards         INTEGER,
    receiving_tds           INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR defense.htm  (#all_defense)
CREATE TABLE IF NOT EXISTS silver.nfl_player_defense_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    def_tackles_solo        INTEGER,
    def_tackles_with_assist INTEGER,
    def_tackle_assists      INTEGER,
    def_tackles_for_loss    INTEGER,
    def_tackles_for_loss_yards DOUBLE,
    def_fumbles_forced      INTEGER,
    def_sacks               DOUBLE,
    def_sack_yards          DOUBLE,
    def_qb_hits             INTEGER,
    def_interceptions       INTEGER,
    def_interception_yards  INTEGER,
    def_pass_defended       INTEGER,
    def_tds                 INTEGER,
    def_fumbles             INTEGER,
    def_safeties            INTEGER,
    def_punt_blocks         INTEGER,
    def_pat_blocks          INTEGER,
    def_fg_blocks           INTEGER,
    def_2pt_atts            INTEGER,
    def_2pt_made            INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR scoring.htm  (#all_scoring) -- every way a player put points on the board.
CREATE TABLE IF NOT EXISTS silver.nfl_player_scoring_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    passing_tds             INTEGER,
    rushing_tds             INTEGER,
    receiving_tds           INTEGER,
    def_tds                 INTEGER,
    special_teams_tds       INTEGER,
    fumble_recovery_tds     INTEGER,
    pt_return_tds           INTEGER,              -- punt-team return TDs
    total_tds               INTEGER,
    passing_2pt_conversions INTEGER,
    rushing_2pt_conversions INTEGER,
    receiving_2pt_conversions INTEGER,
    def_2pt_made            INTEGER,
    pat_made                INTEGER,
    fg_made                 INTEGER,
    def_safeties            INTEGER,
    total_points            INTEGER,              -- 6*TD + 2*2pt + 1*PAT + 3*FG + 2*safety
    fantasy_points          DOUBLE,
    fantasy_points_ppr      DOUBLE,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR kicking.htm  (#all_kicking) -- FG + PAT + punting, incl. PFR's distance buckets.
CREATE TABLE IF NOT EXISTS silver.nfl_player_kicking_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    -- field goals
    fg_made                 INTEGER,
    fg_att                  INTEGER,
    fg_missed               INTEGER,
    fg_blocked              INTEGER,
    fg_long                 INTEGER,
    fg_pct                  DOUBLE,
    fg_made_0_19            INTEGER,
    fg_made_20_29           INTEGER,
    fg_made_30_39           INTEGER,
    fg_made_40_49           INTEGER,
    fg_made_50_59           INTEGER,
    fg_made_60_             INTEGER,
    fg_missed_0_19          INTEGER,
    fg_missed_20_29         INTEGER,
    fg_missed_30_39         INTEGER,
    fg_missed_40_49         INTEGER,
    fg_missed_50_59         INTEGER,
    fg_missed_60_           INTEGER,
    fg_made_distance        DOUBLE,
    fg_missed_distance      DOUBLE,
    fg_blocked_distance     DOUBLE,
    -- game-winning FG
    gwfg_made               INTEGER,
    gwfg_att                INTEGER,
    gwfg_missed             INTEGER,
    gwfg_blocked            INTEGER,
    gwfg_distance           DOUBLE,
    -- extra points
    pat_made                INTEGER,
    pat_att                 INTEGER,
    pat_missed              INTEGER,
    pat_blocked             INTEGER,
    pat_pct                 DOUBLE,
    -- punting
    pt_att                  INTEGER,
    pt_yards                INTEGER,
    pt_net_yards            INTEGER,
    pt_long                 INTEGER,
    pt_blocked              INTEGER,
    pt_inside_20            INTEGER,
    pt_out_of_bounds        INTEGER,
    pt_downed               INTEGER,
    pt_touchback            INTEGER,
    pt_fair_caught          INTEGER,
    pt_returned             INTEGER,
    pt_return_yards         INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- PFR returns (punt/kick return) -- shares the kicking/special-teams family.
CREATE TABLE IF NOT EXISTS silver.nfl_player_returns_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    player_id               VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    punt_returns            INTEGER,
    punt_return_yards       INTEGER,
    kickoff_returns         INTEGER,
    kickoff_return_yards    INTEGER,
    special_teams_tds       INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, player_id)
);

-- =============================================================================
-- PFR ADVANCED STATS -- nflverse mirrors PFR's own advanced tables directly.
-- Keyed on pfr_player_id (that's how the source arrives); join via silver.nfl_player.
-- These are the columns a book's model may not be pricing well -- pressure rates,
-- yards after contact, broken tackles, coverage stats.
-- =============================================================================

CREATE TABLE IF NOT EXISTS silver.nfl_pfr_adv_passing_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    game_type               VARCHAR,
    game_id                 VARCHAR,
    pfr_game_id             VARCHAR,
    pfr_player_id           VARCHAR NOT NULL,
    pfr_player_name         VARCHAR,
    team                    VARCHAR NOT NULL,
    opponent                VARCHAR,
    passing_drops           INTEGER,
    passing_drop_pct        DOUBLE,
    passing_bad_throws      INTEGER,
    passing_bad_throw_pct   DOUBLE,
    times_sacked            INTEGER,
    times_blitzed           INTEGER,
    times_hurried           INTEGER,
    times_hit               INTEGER,
    times_pressured         INTEGER,
    times_pressured_pct     DOUBLE,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, pfr_player_id, team)
);

CREATE TABLE IF NOT EXISTS silver.nfl_pfr_adv_rushing_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    game_type               VARCHAR,
    game_id                 VARCHAR,
    pfr_game_id             VARCHAR,
    pfr_player_id           VARCHAR NOT NULL,
    pfr_player_name         VARCHAR,
    team                    VARCHAR NOT NULL,
    opponent                VARCHAR,
    carries                 INTEGER,
    rushing_yards_before_contact     DOUBLE,
    rushing_yards_before_contact_avg DOUBLE,
    rushing_yards_after_contact      DOUBLE,
    rushing_yards_after_contact_avg  DOUBLE,
    rushing_broken_tackles           INTEGER,
    receiving_broken_tackles         INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, pfr_player_id, team)
);

CREATE TABLE IF NOT EXISTS silver.nfl_pfr_adv_receiving_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    game_type               VARCHAR,
    game_id                 VARCHAR,
    pfr_game_id             VARCHAR,
    pfr_player_id           VARCHAR NOT NULL,
    pfr_player_name         VARCHAR,
    team                    VARCHAR NOT NULL,
    opponent                VARCHAR,
    rushing_broken_tackles  INTEGER,
    receiving_broken_tackles INTEGER,
    receiving_drop          INTEGER,
    receiving_drop_pct      DOUBLE,
    receiving_int           INTEGER,
    receiving_rat           DOUBLE,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, pfr_player_id, team)
);

CREATE TABLE IF NOT EXISTS silver.nfl_pfr_adv_defense_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    game_type               VARCHAR,
    game_id                 VARCHAR,
    pfr_game_id             VARCHAR,
    pfr_player_id           VARCHAR NOT NULL,
    pfr_player_name         VARCHAR,
    team                    VARCHAR NOT NULL,
    opponent                VARCHAR,
    def_ints                INTEGER,
    def_targets             INTEGER,
    def_completions_allowed INTEGER,
    def_completion_pct      DOUBLE,
    def_yards_allowed       INTEGER,
    def_yards_allowed_per_cmp DOUBLE,
    def_yards_allowed_per_tgt DOUBLE,
    def_receiving_td_allowed  INTEGER,
    def_passer_rating_allowed DOUBLE,
    def_adot                DOUBLE,               -- avg depth of target
    def_air_yards_completed INTEGER,
    def_yards_after_catch   DOUBLE,
    def_times_blitzed       INTEGER,
    def_times_hurried       INTEGER,
    def_times_hitqb         INTEGER,
    def_sacks               DOUBLE,
    def_pressures           INTEGER,
    def_tackles_combined    INTEGER,
    def_missed_tackles      INTEGER,
    def_missed_tackle_pct   DOUBLE,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, pfr_player_id, team)
);

-- =============================================================================
-- TEAM TABLES -- same 7 chart families, team grain.
-- One wide weekly table mirrors the source exactly; per-chart views slice it so
-- each PFR page still has a 1:1 counterpart without duplicating storage.
-- =============================================================================

CREATE TABLE IF NOT EXISTS silver.nfl_team_week (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR NOT NULL,
    game_id                 VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,
    opponent_team           VARCHAR,
    -- passing
    completions             INTEGER,
    attempts                INTEGER,
    passing_yards           INTEGER,
    passing_tds             INTEGER,
    passing_interceptions   INTEGER,
    sacks_suffered          DOUBLE,
    sack_yards_lost         INTEGER,
    passing_air_yards       INTEGER,
    passing_yards_after_catch DOUBLE,
    passing_first_downs     INTEGER,
    passing_epa             DOUBLE,
    passing_cpoe            DOUBLE,
    -- rushing
    carries                 INTEGER,
    rushing_yards           INTEGER,
    rushing_tds             INTEGER,
    rushing_first_downs     INTEGER,
    rushing_epa             DOUBLE,
    -- receiving
    receptions              INTEGER,
    targets                 INTEGER,
    receiving_yards         INTEGER,
    receiving_tds           INTEGER,
    receiving_air_yards     INTEGER,
    receiving_yards_after_catch DOUBLE,
    receiving_first_downs   INTEGER,
    receiving_epa           DOUBLE,
    -- defense
    def_tackles_solo        INTEGER,
    def_sacks               DOUBLE,
    def_sack_yards          DOUBLE,
    def_qb_hits             INTEGER,
    def_interceptions       INTEGER,
    def_pass_defended       INTEGER,
    def_tds                 INTEGER,
    def_safeties            INTEGER,
    def_fumbles_forced      INTEGER,
    def_tackles_for_loss    INTEGER,
    -- scoring / special
    special_teams_tds       INTEGER,
    fumble_recovery_tds     INTEGER,
    fg_made                 INTEGER,
    fg_att                  INTEGER,
    fg_long                 INTEGER,
    fg_pct                  DOUBLE,
    pat_made                INTEGER,
    pat_att                 INTEGER,
    pat_pct                 DOUBLE,
    -- punting / returns
    pt_att                  INTEGER,
    pt_yards                INTEGER,
    pt_net_yards            INTEGER,
    pt_inside_20            INTEGER,
    punt_returns            INTEGER,
    punt_return_yards       INTEGER,
    kickoff_returns         INTEGER,
    kickoff_return_yards    INTEGER,
    -- discipline / ball security
    penalties               INTEGER,
    penalty_yards           INTEGER,
    fumbles_total           INTEGER,
    fumbles_lost_total      INTEGER,
    timeouts                INTEGER,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, week, game_id, team)
);

-- Per-PFR-page team views (1:1 with the site's charts, no extra storage)
CREATE OR REPLACE VIEW silver.v_nfl_team_passing_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       completions, attempts, passing_yards, passing_tds, passing_interceptions,
       sacks_suffered, sack_yards_lost, passing_air_yards, passing_yards_after_catch,
       passing_first_downs, passing_epa, passing_cpoe
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_rushing_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       carries, rushing_yards, rushing_tds, rushing_first_downs, rushing_epa
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_receiving_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       receptions, targets, receiving_yards, receiving_tds, receiving_air_yards,
       receiving_yards_after_catch, receiving_first_downs, receiving_epa
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_scrimmage_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       carries + receptions                  AS touches,
       rushing_yards + receiving_yards        AS scrimmage_yards,
       rushing_tds + receiving_tds            AS scrimmage_tds,
       rushing_first_downs + receiving_first_downs AS scrimmage_first_downs
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_defense_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       def_tackles_solo, def_tackles_for_loss, def_sacks, def_sack_yards,
       def_qb_hits, def_interceptions, def_pass_defended, def_tds,
       def_safeties, def_fumbles_forced
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_scoring_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       passing_tds, rushing_tds, receiving_tds, def_tds, special_teams_tds,
       fumble_recovery_tds,
       COALESCE(rushing_tds,0) + COALESCE(receiving_tds,0) + COALESCE(def_tds,0)
         + COALESCE(special_teams_tds,0)      AS total_tds,
       fg_made, pat_made, def_safeties,
       6 * (COALESCE(rushing_tds,0) + COALESCE(receiving_tds,0) + COALESCE(def_tds,0)
            + COALESCE(special_teams_tds,0))
         + 3 * COALESCE(fg_made,0) + COALESCE(pat_made,0)
         + 2 * COALESCE(def_safeties,0)        AS points_scored
FROM silver.nfl_team_week;

CREATE OR REPLACE VIEW silver.v_nfl_team_kicking_week AS
SELECT season, week, season_type, game_id, team, opponent_team,
       fg_made, fg_att, fg_long, fg_pct, pat_made, pat_att, pat_pct,
       pt_att, pt_yards, pt_net_yards, pt_inside_20
FROM silver.nfl_team_week;

-- =============================================================================
-- SEASON AGGREGATE VIEWS -- what PFR's season page shows. Derived, never stored,
-- so a late stat correction upstream can't leave totals out of sync with weeks.
-- =============================================================================

CREATE OR REPLACE VIEW silver.v_nfl_player_passing_season AS
SELECT season, season_type, player_id, ANY_VALUE(team) AS team,
       COUNT(*)                     AS games,
       SUM(completions)             AS completions,
       SUM(attempts)                AS attempts,
       SUM(passing_yards)           AS passing_yards,
       SUM(passing_tds)             AS passing_tds,
       SUM(passing_interceptions)   AS passing_interceptions,
       SUM(passing_first_downs)     AS passing_first_downs,
       SUM(sacks_suffered)          AS sacks_suffered,
       CASE WHEN SUM(attempts) > 0
            THEN 1.0 * SUM(completions) / SUM(attempts) END AS completion_pct,
       CASE WHEN SUM(attempts) > 0
            THEN 1.0 * SUM(passing_yards) / SUM(attempts) END AS yards_per_attempt,
       SUM(passing_epa)             AS passing_epa
FROM silver.nfl_player_passing_week
GROUP BY season, season_type, player_id;

CREATE OR REPLACE VIEW silver.v_nfl_player_rushing_season AS
SELECT season, season_type, player_id, ANY_VALUE(team) AS team,
       COUNT(*)                 AS games,
       SUM(carries)             AS carries,
       SUM(rushing_yards)       AS rushing_yards,
       SUM(rushing_tds)         AS rushing_tds,
       SUM(rushing_first_downs) AS rushing_first_downs,
       CASE WHEN SUM(carries) > 0
            THEN 1.0 * SUM(rushing_yards) / SUM(carries) END AS yards_per_carry,
       SUM(rushing_epa)         AS rushing_epa
FROM silver.nfl_player_rushing_week
GROUP BY season, season_type, player_id;

CREATE OR REPLACE VIEW silver.v_nfl_player_receiving_season AS
SELECT season, season_type, player_id, ANY_VALUE(team) AS team,
       COUNT(*)                   AS games,
       SUM(receptions)            AS receptions,
       SUM(targets)               AS targets,
       SUM(receiving_yards)       AS receiving_yards,
       SUM(receiving_tds)         AS receiving_tds,
       SUM(receiving_first_downs) AS receiving_first_downs,
       CASE WHEN SUM(targets) > 0
            THEN 1.0 * SUM(receptions) / SUM(targets) END AS catch_rate,
       CASE WHEN SUM(receptions) > 0
            THEN 1.0 * SUM(receiving_yards) / SUM(receptions) END AS yards_per_reception,
       AVG(target_share)          AS avg_target_share,
       SUM(receiving_epa)         AS receiving_epa
FROM silver.nfl_player_receiving_week
GROUP BY season, season_type, player_id;

-- =============================================================================
-- GOLD: the head-to-head layer. Player form vs. a book's posted prop line.
--
-- SUPERSEDED (confirmed empty, 0 rows, 2026-09-25): this was the original
-- placeholder before a real props source was scoped. gold.nfl_prop_line_rotowire
-- (sql/nfl_props_schema.sql) is the real, populated table -- 4,956+ rows,
-- verified real DK/FD/Caesars lines. Kept here (not dropped) so nothing that
-- may already reference this name breaks; do not write new code against it.
-- =============================================================================

CREATE TABLE IF NOT EXISTS gold.nfl_prop_line (
    league              VARCHAR NOT NULL DEFAULT 'nfl',
    season              INTEGER NOT NULL,
    week                INTEGER NOT NULL,
    game_id             VARCHAR,
    player_id           VARCHAR,
    book                VARCHAR NOT NULL,
    market              VARCHAR NOT NULL,        -- e.g. player_pass_yds, player_rush_yds
    line                DOUBLE,
    over_price_decimal  DOUBLE,
    under_price_decimal DOUBLE,
    fetched_at_utc      TIMESTAMP NOT NULL,
    source_name         VARCHAR NOT NULL,        -- 'the_odds_api'
    PRIMARY KEY (season, week, book, market, player_id, fetched_at_utc)
);

-- Rolling player form, point-in-time safe: only weeks strictly BEFORE the target
-- week feed the average, so a backtest can't peek at the result it's predicting.
CREATE OR REPLACE VIEW gold.v_nfl_player_form_passing AS
SELECT p.season, p.week AS as_of_week, p.player_id,
       AVG(h.passing_yards) OVER w  AS avg_passing_yards_prior,
       AVG(h.attempts)      OVER w  AS avg_attempts_prior,
       COUNT(*)             OVER w  AS games_in_window
FROM silver.nfl_player_passing_week p
JOIN silver.nfl_player_passing_week h
  ON h.player_id = p.player_id AND h.season = p.season AND h.week < p.week
WINDOW w AS (PARTITION BY p.player_id, p.season, p.week);

CREATE INDEX IF NOT EXISTS ix_pass_wk   ON silver.nfl_player_passing_week (season, week, player_id);
CREATE INDEX IF NOT EXISTS ix_rush_wk   ON silver.nfl_player_rushing_week (season, week, player_id);
CREATE INDEX IF NOT EXISTS ix_rec_wk    ON silver.nfl_player_receiving_week (season, week, player_id);
CREATE INDEX IF NOT EXISTS ix_def_wk    ON silver.nfl_player_defense_week (season, week, player_id);
CREATE INDEX IF NOT EXISTS ix_kick_wk   ON silver.nfl_player_kicking_week (season, week, player_id);
CREATE INDEX IF NOT EXISTS ix_team_wk   ON silver.nfl_team_week (season, week, team);
CREATE INDEX IF NOT EXISTS ix_propline  ON gold.nfl_prop_line (season, week, market, player_id);

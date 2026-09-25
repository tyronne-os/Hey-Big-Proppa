-- frontal-lobe2 canonical schema.
-- Derived from docs/CHART_AUDIT.md (TeamRankings structural audit, 2026-09-24).
-- Design-only: recreates chart shape (columns + splits/dropdowns), not TeamRankings' data.
-- Target engine: DuckDB (schemas as namespaces; PRAGMA lines are SQLite-compatible fallback).
-- Leagues in scope: nfl, ncf (college football), nba, mlb. NHL deferred (docs/NHL_GAP.md).

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================================
-- BRONZE: ingestion tracking (shared across all reference pulls and live pulls)
-- ============================================================================
CREATE TABLE IF NOT EXISTS bronze.ingestion_runs (
    run_id          VARCHAR PRIMARY KEY,
    source_name     VARCHAR NOT NULL,          -- e.g. 'teamrankings_reference', 'espn_api', 'cfbd'
    source_kind     VARCHAR NOT NULL,          -- 'html_snapshot' | 'api'
    league          VARCHAR,                   -- nfl | ncf | nba | mlb
    started_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP,
    row_count       INTEGER,
    status          VARCHAR NOT NULL,
    error_message   VARCHAR
);

-- ============================================================================
-- SILVER: chart catalog -- the master list of every chart/stat available per league.
-- Populated from the *_stats.html / *_player-stats.html index pages (~600+ slugs total).
-- This IS the spreadsheet deliverable's source of truth; export this table to build it.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.stat_catalog (
    league          VARCHAR NOT NULL,          -- nfl | ncf | nba | mlb
    stat_slug       VARCHAR NOT NULL,          -- e.g. 'points-per-game'
    display_name    VARCHAR NOT NULL,          -- e.g. 'Points per Game'
    stat_scope      VARCHAR NOT NULL,          -- 'team' | 'player'
    category        VARCHAR,                   -- offense | defense | special_teams | batting | pitching | etc.
    source_page     VARCHAR,                   -- which catalog page this was found on
    PRIMARY KEY (league, stat_scope, stat_slug)
);

CREATE TABLE IF NOT EXISTS silver.ranking_catalog (
    league          VARCHAR NOT NULL,
    rating_name     VARCHAR NOT NULL,          -- e.g. 'Predictive by other', 'Home Advantage'
    best_label      VARCHAR,                   -- label used for #1 in that rating system
    worst_label     VARCHAR,
    PRIMARY KEY (league, rating_name)
);

-- ============================================================================
-- SILVER: the universal per-stat chart template.
-- Confirmed identical shape across every sampled stat page (NFL/NBA points-per-game,
-- MLB runs-per-game): Rank | Team | current season | Last 3 | Last 1 | Home | Away | prior season.
-- One normalized fact table covers all ~600 stat_catalog entries -- do not create one
-- physical table per stat.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.team_stat_value (
    league          VARCHAR NOT NULL,
    stat_slug       VARCHAR NOT NULL,          -- FK -> stat_catalog.stat_slug (stat_scope='team')
    team            VARCHAR NOT NULL,
    season          INTEGER NOT NULL,          -- the 'date' dropdown selection
    split           VARCHAR NOT NULL,          -- 'overall' | 'last_3' | 'last_1' | 'home' | 'away'
    rank            INTEGER,
    value           DOUBLE,
    source_name     VARCHAR NOT NULL,          -- live source once wired, e.g. 'espn', 'nflverse'
    captured_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (league, stat_slug, team, season, split, captured_at)
);

CREATE TABLE IF NOT EXISTS silver.player_stat_value (
    league          VARCHAR NOT NULL,
    stat_slug       VARCHAR NOT NULL,          -- FK -> stat_catalog.stat_slug (stat_scope='player')
    player_name     VARCHAR NOT NULL,
    team            VARCHAR,
    position        VARCHAR,
    season          INTEGER NOT NULL,
    split           VARCHAR NOT NULL,
    rank            INTEGER,
    value           DOUBLE,
    source_name     VARCHAR NOT NULL,
    captured_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (league, stat_slug, player_name, team, season, split, captured_at)
);

-- ============================================================================
-- SILVER: standings. Confirmed division/conference-grouped per league; NCF has
-- 11 conference tables (vs. 2 for pro leagues) and a MAC East/West sub-split.
-- group_name carries the division/conference label so all leagues share one table.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.standings (
    league              VARCHAR NOT NULL,
    season              INTEGER NOT NULL,
    group_name          VARCHAR NOT NULL,      -- division/conference label, e.g. 'AFC East', 'MAC East'
    rank_in_group       INTEGER,
    team                VARCHAR NOT NULL,
    overall_wins        INTEGER,
    overall_losses      INTEGER,
    overall_ties        INTEGER,               -- NCF/NFL can have ties; NULL where not applicable
    win_pct             DOUBLE,
    games_back          DOUBLE,
    group_wins          INTEGER,                -- division/conference record
    group_losses        INTEGER,
    home_wins           INTEGER,
    home_losses         INTEGER,
    road_wins           INTEGER,
    road_losses         INTEGER,
    streak              VARCHAR,
    source_name         VARCHAR NOT NULL,
    captured_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (league, season, group_name, team, captured_at)
);

-- ============================================================================
-- SILVER: schedules. Confirmed: date-pivoted headers with Time/Location per league,
-- plus week and group(division/conference/poll) filters as splits.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.schedule (
    league          VARCHAR NOT NULL,
    season          INTEGER NOT NULL,
    week            VARCHAR,                    -- NFL/NCF use week labels incl. 'Bowl Week'; NBA/MLB use game date grouping
    game_date       DATE,
    home_team       VARCHAR,
    away_team       VARCHAR,
    game_time_utc   TIME,
    location        VARCHAR,
    group_filter    VARCHAR,                    -- the 'group' dropdown value this row was captured under (division/conference/poll), if applicable
    home_score      INTEGER,
    away_score      INTEGER,
    status          VARCHAR,
    source_name     VARCHAR NOT NULL,
    captured_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (league, season, game_date, home_team, away_team, captured_at)
);

-- ============================================================================
-- SILVER: projections. Confirmed 2-tier (NFL/NBA/MLB) or 3-tier (NCF, adds ties)
-- structure: Current record / Projected record / Playoff-odds percentages.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.season_projection (
    league              VARCHAR NOT NULL,
    season              INTEGER NOT NULL,
    team                VARCHAR NOT NULL,
    current_wins        INTEGER,
    current_losses      INTEGER,
    current_ties        INTEGER,                -- NCF only; NULL elsewhere
    projected_wins       DOUBLE,
    projected_losses     DOUBLE,
    projected_ties        DOUBLE,               -- NCF only
    playoff_pct          DOUBLE,
    win_division_pct      DOUBLE,
    top_seed_pct          DOUBLE,
    win_championship_pct  DOUBLE,               -- Win SB / Champs / WS Champs / Bowl Eligible% depending on league
    undefeated_pct         DOUBLE,              -- NCF only; NULL elsewhere
    source_name           VARCHAR NOT NULL,
    captured_at            TIMESTAMP NOT NULL,
    PRIMARY KEY (league, season, team, captured_at)
);

-- ============================================================================
-- SILVER: odds board. SCHEMA IS PROVISIONAL -- the real column structure was NOT
-- captured (client-side AJAX render, see CHART_AUDIT.md "Confirmed gaps"). This
-- shape is inferred from The Odds API's standard market fields, not from a
-- confirmed TeamRankings sample. Revise once a headless-browser capture or the
-- AJAX endpoint response is inspected directly.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.odds_snapshot (       -- PROVISIONAL
    league              VARCHAR NOT NULL,
    game_id             VARCHAR NOT NULL,
    book                VARCHAR NOT NULL,
    market              VARCHAR NOT NULL,       -- spread | total | moneyline
    home_line           DOUBLE,
    away_line           DOUBLE,
    home_price          DOUBLE,
    away_price          DOUBLE,
    is_closing_line      BOOLEAN,
    fetched_at_utc        TIMESTAMP NOT NULL,
    source_name           VARCHAR NOT NULL,
    PRIMARY KEY (league, game_id, book, market, fetched_at_utc)
);

CREATE INDEX IF NOT EXISTS idx_team_stat_lookup
    ON silver.team_stat_value (league, stat_slug, season, split);
CREATE INDEX IF NOT EXISTS idx_player_stat_lookup
    ON silver.player_stat_value (league, stat_slug, season, split);
CREATE INDEX IF NOT EXISTS idx_standings_lookup
    ON silver.standings (league, season, group_name);
CREATE INDEX IF NOT EXISTS idx_schedule_lookup
    ON silver.schedule (league, season, week);

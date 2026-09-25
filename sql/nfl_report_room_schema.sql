-- =============================================================================
-- frontal-lobe2 : NFL sports report room
-- =============================================================================
-- Purpose: give a beat writer everything needed to write a matchup preview from
-- the lake alone -- injuries, inactives-track, current news, transactions -- no
-- browser tab open. This is the data layer only; narrative generation (an agent
-- reading this and writing the article) is a later phase, per the user.
--
-- Sources, both confirmed live with real 2026 data on 2026-09-25:
--   1. nflverse injuries_2026.csv -- OFFICIAL weekly injury report (practice
--      status, game status, injury type). This is the closest thing to a
--      league-mandated inactives signal available pre-gameday. See caveat in
--      docs/REPORT_ROOM.md: the FINAL inactives list is only released ~90 min
--      before kickoff and is not covered here -- this is the last official
--      report before that point (usually Fri "Questionable/Doubtful/Out").
--   2. ESPN (site.web.api.espn.com -- confirmed reachable; the more commonly
--      documented site.api.espn.com returned HTTP 403 in this environment).
--      Same "unofficial/undocumented, can change without notice" risk profile
--      already flagged for ESPN elsewhere in this project -- just a different,
--      currently-reachable host. Three endpoints used:
--        /injuries         -- narrative injury context per player (why it
--                              matters, who benefits if they sit)
--        /news, /news?team=<abbr> -- headlines + summary, tagged with
--                              structured athleteId/teamId categories (no fuzzy
--                              text matching needed to link a story to a player)
--        /transactions     -- roster moves (signings, releases, IR moves)
--
-- Engine: DuckDB.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ============================================================================
-- Official weekly injury report (nflverse). One row per player per week.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_injury_report (
    season                   INTEGER NOT NULL,
    week                     INTEGER NOT NULL,
    season_type              VARCHAR,
    game_type                VARCHAR,
    team                     VARCHAR NOT NULL,
    gsis_id                  VARCHAR,             -- nflverse player id, joins to nfl_player
    position                 VARCHAR,
    full_name                VARCHAR,
    report_primary_injury    VARCHAR,
    report_secondary_injury  VARCHAR,
    report_status            VARCHAR,             -- Questionable | Doubtful | Out
    practice_primary_injury  VARCHAR,
    practice_secondary_injury VARCHAR,
    practice_status          VARCHAR,             -- Did Not Participate | Limited | Full
    ingest_run_id            VARCHAR NOT NULL,
    PRIMARY KEY (season, week, team, gsis_id, full_name)
);
CREATE INDEX IF NOT EXISTS ix_injury_team_week
    ON silver.nfl_injury_report (season, week, team);

-- ============================================================================
-- ESPN narrative injury context. One row per player, current snapshot
-- (ESPN's injuries endpoint is "current state", not a per-week history --
-- snapshot it repeatedly if a history is wanted later).
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_injury_narrative (
    espn_athlete_id     VARCHAR NOT NULL,
    player_name         VARCHAR,
    team                VARCHAR,
    status              VARCHAR,             -- Questionable | Doubtful | Out | IR
    injury_type         VARCHAR,              -- e.g. 'Toe', 'Achilles'
    injury_location      VARCHAR,             -- e.g. 'Leg'
    injury_side          VARCHAR,             -- Left | Right
    return_date          DATE,
    short_comment        VARCHAR,             -- one-line practice-report style note
    long_comment         VARCHAR,             -- full narrative paragraph, matchup context
    reported_at          TIMESTAMP,
    fetched_at_utc       TIMESTAMP NOT NULL,
    source_name          VARCHAR NOT NULL DEFAULT 'espn',
    PRIMARY KEY (espn_athlete_id, fetched_at_utc)
);
CREATE INDEX IF NOT EXISTS ix_injury_narr_team
    ON silver.nfl_injury_narrative (team, fetched_at_utc);

-- ============================================================================
-- News articles. League-wide + team-scoped pulls land here; category tags
-- (below) are what actually link a story to a specific player/team.
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_news_article (
    espn_article_id   VARCHAR PRIMARY KEY,
    headline          VARCHAR,
    description       VARCHAR,              -- ESPN's own summary, not just a title
    article_type      VARCHAR,              -- e.g. 'Media', 'HeadlineNews', 'Story'
    published_at      TIMESTAMP,
    last_modified_at  TIMESTAMP,
    is_premium        BOOLEAN,              -- ESPN+ gated; still has headline/description
    fetched_at_utc    TIMESTAMP NOT NULL,
    source_name       VARCHAR NOT NULL DEFAULT 'espn'
);
CREATE INDEX IF NOT EXISTS ix_news_published
    ON silver.nfl_news_article (published_at);

-- Many-to-many: one article can tag multiple players/teams (a trade story tags
-- two teams and the player involved, for instance).
-- No composite PK here on purpose: espn_athlete_id/team are legitimately NULL
-- for non-athlete/non-team tags (e.g. a 'league' tag has neither), and DuckDB
-- (like most SQL engines) rejects NULL in a PRIMARY KEY column. A tag_id
-- surrogate key keeps this table de-duplicable without that constraint.
CREATE TABLE IF NOT EXISTS silver.nfl_news_article_tag (
    tag_id            VARCHAR PRIMARY KEY,   -- article_id + tag_type + subject, hashed
    espn_article_id   VARCHAR NOT NULL,
    tag_type          VARCHAR NOT NULL,     -- 'athlete' | 'team' | 'league'
    espn_athlete_id   VARCHAR,
    team              VARCHAR,              -- abbreviation, when tag_type='team'
    tag_description   VARCHAR               -- display name as ESPN tagged it
);
CREATE INDEX IF NOT EXISTS ix_newstag_athlete
    ON silver.nfl_news_article_tag (espn_athlete_id);
CREATE INDEX IF NOT EXISTS ix_newstag_team
    ON silver.nfl_news_article_tag (team);

-- ============================================================================
-- Transactions (signings, releases, IR moves, trades).
-- ============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_transaction (
    transaction_id    VARCHAR NOT NULL,
    team              VARCHAR,
    description       VARCHAR NOT NULL,      -- ESPN's own transaction text
    transaction_date  DATE,
    fetched_at_utc    TIMESTAMP NOT NULL,
    source_name       VARCHAR NOT NULL DEFAULT 'espn',
    PRIMARY KEY (transaction_id, fetched_at_utc)
);
CREATE INDEX IF NOT EXISTS ix_txn_team_date
    ON silver.nfl_transaction (team, transaction_date);

-- ============================================================================
-- GOLD: espn_athlete_id <-> nflverse gsis_id bridge. ESPN and nflverse use
-- different player id schemes; name-matched as a best effort (case-insensitive,
-- suffix-stripped). Anything unresolved stays NULL rather than a wrong guess --
-- check gold.v_nfl_player_id_bridge_unmatched before trusting a join silently.
-- ============================================================================
CREATE TABLE IF NOT EXISTS gold.nfl_player_id_bridge (
    gsis_id          VARCHAR,
    espn_athlete_id  VARCHAR,
    match_method     VARCHAR NOT NULL,      -- 'exact_name' | 'normalized_name' | 'manual'
    PRIMARY KEY (gsis_id, espn_athlete_id)
);

-- ============================================================================
-- GOLD: the matchup bundle. Parameterized by two team abbreviations -- run as
-- a query template (see scripts/matchup_report.py), not a static materialized
-- view, since "which two teams" changes every call.
--
-- This view returns injuries + news + transactions for ONE team; the report
-- script calls it twice (once per side) and stitches the bundle together, so
-- the underlying SQL stays simple and reusable rather than a single giant
-- cross-joined query.
-- ============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_team_report_card AS
SELECT 'injury_official' AS section, r.team, r.full_name AS subject, r.report_status AS headline,
       r.report_primary_injury AS detail, NULL AS narrative,
       NULL::TIMESTAMP AS occurred_at
FROM silver.nfl_injury_report r
JOIN (SELECT max(season) AS season, max(week) AS week FROM silver.nfl_injury_report) latest
  ON r.season = latest.season AND r.week = latest.week
UNION ALL
SELECT 'injury_narrative', team, player_name, status,
       injury_type || COALESCE(' (' || injury_location || ')', ''), long_comment,
       reported_at
FROM silver.nfl_injury_narrative
WHERE fetched_at_utc = (SELECT max(fetched_at_utc) FROM silver.nfl_injury_narrative)
UNION ALL
SELECT 'news', t.team, a.headline, a.description, NULL, a.description, a.published_at
FROM silver.nfl_news_article a
JOIN silver.nfl_news_article_tag t ON t.espn_article_id = a.espn_article_id
WHERE t.tag_type = 'team'
UNION ALL
SELECT 'transaction', team, description, NULL, NULL, NULL, transaction_date::TIMESTAMP
FROM silver.nfl_transaction;

CREATE INDEX IF NOT EXISTS ix_bridge_gsis ON gold.nfl_player_id_bridge (gsis_id);

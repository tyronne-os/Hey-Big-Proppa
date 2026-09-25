-- =============================================================================
-- frontal-lobe2 : player usage & situational-confidence pond (Phase 1)
-- =============================================================================
-- Built the way the user built it: identify TWO stats first -- the spine -- then
-- layer every other stat on top of that spine. The layers are only meaningful
-- because the spine decides who we are even asking about.
--
--   LAYER 1  THE SPINE -- position-gated opportunity. "Who does he go to?"
--              if WR or TE  -> TARGETS
--              if RB or FB  -> RUSH ATTEMPTS
--            Nothing else. A WR's confidence is measured in targets and a
--            back's in carries, because those are the touches the coach
--            actually assigns. Mixing them into one "touches" number lets a
--            checkdown back outrank a WR1 and tells you nothing.
--
--   LAYER 2  STRESS -- the user's core insight, quoted:
--              "the higher the stress level the more they go to who they know"
--            So the signal is not how big a share he gets. It is whether his
--            share GROWS as the situation tightens. A coach spreading the ball
--            around on 1st-and-10 in the 2nd quarter is calling an offense. A
--            coach going to the same man on 3rd-and-4 at the 8 with a
--            three-point lead in the 4th is telling you who he trusts.
--            Measured as: share under high stress MINUS share under low
--            stress. That delta is the indicator.
--
--   LAYER 3  THE DEPTH CHART -- the coach's own published hierarchy, compared
--            to what the ball actually says. Out-earning your listed slot is
--            the most perishable signal here, because the chart is public and
--            slow while usage is real and fast.
--
--   LAYER 4  WHERE -- field zone (Inside 20/10/5), pass location, air yards.
--            "in the red zone, where were the passes thrown."
--
--   LAYER 5  RETURN -- Yards From Scrimmage / yards per touch. PFR's
--            /years/2026/scrimmage.htm. "productive players once they touch
--            the ball." Reused from silver.nfl_player_scrimmage_week so a
--            touch means one thing in this lake.
--
-- EVERY SHARE IS INTRA-TEAM. Per the user: the measurement is confidence
-- "within his own team", not across the NFL. A WR on a pass-heavy offense
-- out-targets a trusted WR1 on a run-first team without either fact saying
-- anything about the two coaches. So every denominator below is that player's
-- OWN TEAM's total in that same game.
--
-- SOURCES -- nflverse only (CC-BY-4.0, nightly). No new vendor needed:
--   pbp           play_by_play_2026.csv.gz  -> every target and every carry,
--                 with down, distance, clock, score, field position. Same file
--                 ingest_nfl_td_logs.py already pulls.
--   depth_charts  depth_charts_2026.csv     -> the stated hierarchy,
--                 point-in-time (197 snapshots Mar->Sep 2026, verified).
--
-- PFR is never fetched (403 Cloudflare + ToS). docs/PFR_SOURCE_NOTE.md.
-- ffverse/ffopportunity expected-points is verified and real but deliberately
-- NOT used in Phase 1: it is GPL-3.0, weekly rather than nightly, and a model
-- output rather than an observed fact. (game_id, play_id) is preserved below
-- so it can be joined 1:1 as a Phase 2 enrichment.
--
-- Engine: DuckDB. Depends on sql/nfl_pfr_schema.sql and
-- sql/nfl_schedule_schema.sql.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- =============================================================================
-- BASE TABLE: one row per OPPORTUNITY -- a target or a carry.
--
-- GRAIN: (game_id, play_id, opportunity_type). Same event-grain philosophy as
-- silver.nfl_td_log: store the decision once, express every chart as a view.
-- A single play can be only one of the two, so in practice this is one row per
-- play, but the composite key keeps it honest.
--
-- An "opportunity" is a coaching decision to put the ball in a named player's
-- hands. Sacks, scrambles, throwaways and spikes have no intended recipient in
-- the data and are excluded -- they are not decisions to trust anyone.
-- =============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_opportunity_event (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    season_type             VARCHAR,
    game_id                 VARCHAR NOT NULL,
    play_id                 INTEGER NOT NULL,
    opportunity_type        VARCHAR NOT NULL,      -- 'target' | 'rush'
    -- who
    posteam                 VARCHAR NOT NULL,      -- the offense; whose coach we are reading
    defteam                 VARCHAR,
    player_id               VARCHAR,               -- receiver on a target, rusher on a carry
    player_name             VARCHAR,
    passer_player_id        VARCHAR,               -- NULL on a rush
    passer_player_name      VARCHAR,

    -- ---- LAYER 4: WHERE ------------------------------------------------
    yardline_100            INTEGER,               -- yards from the opponent goal line
    is_inside_20            BOOLEAN,               -- PFR "Inside 20"
    is_inside_10            BOOLEAN,               -- PFR "Inside 10"
    is_inside_5             BOOLEAN,               -- PFR "Inside 5"
    is_goal_to_go           BOOLEAN,
    air_yards               INTEGER,               -- targets only
    pass_location           VARCHAR,               -- left | middle | right (targets)
    run_location            VARCHAR,               -- left | middle | right (rushes)
    run_gap                 VARCHAR,               -- guard | tackle | end (rushes)

    -- ---- LAYER 2: STRESS ----------------------------------------------
    -- The situation as the play was called. All four inputs come straight
    -- from pbp; none are inferred.
    down                    INTEGER,
    ydstogo                 INTEGER,
    qtr                     INTEGER,
    game_seconds_remaining  INTEGER,
    score_differential      INTEGER,               -- offense minus defense, pre-play
    -- The stress ladder. Documented explicitly so it can be argued with
    -- rather than reverse-engineered:
    --   3 MAX      -- goal to go, inside the 5, 4th down, or a one-score
    --                 game in the last 5 minutes. No margin for error.
    --   2 HIGH     -- red zone, 3rd down, or 2 yards or fewer to go.
    --                 Conversion or scoring pressure.
    --   1 MODERATE -- 2nd and long, or trailing by 9-16 (two-score chase).
    --   0 NEUTRAL  -- everything else. Open field, script territory.
    stress_level            INTEGER NOT NULL,
    is_high_stress          BOOLEAN NOT NULL,      -- stress_level >= 2
    is_two_minute           BOOLEAN,               -- last 2 min of either half
    -- QB run type. A designed keeper or sneak is a CALLED PLAY -- the coach
    -- chose the quarterback over his back, which is a confidence statement and
    -- belongs in the pool. A scramble is a collapsed pocket: nobody decided to
    -- give him the ball. Flagged, not deleted, so either reading is available.
    is_qb_scramble          BOOLEAN,
    is_designed_run         BOOLEAN,               -- rush that was not a scramble

    -- ---- outcome (Layer 5 inputs) --------------------------------------
    completed               BOOLEAN,               -- complete_pass; NULL-ish on rush (true)
    yards_gained            INTEGER,
    yards_after_catch       INTEGER,
    touchdown               BOOLEAN,
    first_down              BOOLEAN,
    turnover                BOOLEAN,               -- interception on a target
    play_description        VARCHAR,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, game_id, play_id, opportunity_type)
);

CREATE INDEX IF NOT EXISTS ix_opp_player  ON silver.nfl_opportunity_event (season, player_id, week);
CREATE INDEX IF NOT EXISTS ix_opp_team    ON silver.nfl_opportunity_event (season, posteam, week);
CREATE INDEX IF NOT EXISTS ix_opp_stress  ON silver.nfl_opportunity_event (season, posteam, is_high_stress);
CREATE INDEX IF NOT EXISTS ix_opp_type    ON silver.nfl_opportunity_event (season, posteam, opportunity_type);

-- =============================================================================
-- BASE TABLE: depth chart snapshots (Layer 3) -- the coach's stated hierarchy.
--
-- This source is a POINT-IN-TIME snapshot series, not a weekly table. A depth
-- chart read today says nothing about who the WR2 was in week 1, so every
-- join below goes through v_nfl_depth_chart_pregame, which takes the latest
-- snapshot at or before that game's kickoff. Same point-in-time discipline the
-- props table enforces with is_pregame -- and for the same reason: otherwise a
-- mid-week promotion leaks backwards into a metric describing a past decision.
--
-- snapshot_at is TIMESTAMPTZ deliberately. The source publishes ISO-8601 with
-- a literal Z; storing that naive is exactly the bug already found and fixed
-- on gold.nfl_prop_line_rotowire, where local time sat in a column named _utc.
-- =============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_depth_chart_snapshot (
    snapshot_at             TIMESTAMPTZ NOT NULL,
    team                    VARCHAR NOT NULL,
    pos_grp                 VARCHAR,               -- '3WR 1TE' = offense
    pos_abb                 VARCHAR NOT NULL,      -- QB | RB | WR | TE | FB | OL...
    pos_name                VARCHAR,
    pos_slot                INTEGER,
    pos_rank                INTEGER NOT NULL,      -- 1 = starter at that spot
    gsis_id                 VARCHAR,               -- joins silver.nfl_player.player_id
    espn_id                 VARCHAR,
    player_name             VARCHAR NOT NULL,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_at, team, pos_abb, pos_rank, player_name)
);
CREATE INDEX IF NOT EXISTS ix_depth_team_at ON silver.nfl_depth_chart_snapshot (team, snapshot_at);
CREATE INDEX IF NOT EXISTS ix_depth_gsis    ON silver.nfl_depth_chart_snapshot (gsis_id, snapshot_at);

-- =============================================================================
-- LAYER 1 -- THE SPINE
-- =============================================================================
-- Team opportunity totals: the denominator for every share in this pond. Split
-- by type, because the spine is position-gated -- a WR's share is of the
-- team's TARGETS, a back's is of the team's CARRIES. One definition, one place.
-- QB DESIGNED RUNS ARE IN THE RUSH POOL. Per the user, and he is right:
--
--   "in that situation the team is inside of the 5 yardline therefore qb if he
--    runs is counted as a running back in my system, because the actual rb is
--    competing with the qb in an area where he should get the ball and that too
--    is a measurement of the coaches confidence"
--
-- An earlier version of this view excluded QB carries, on the theory that the
-- goal-line sneak was a structural artifact crushing every back's stress share.
-- That was wrong, and it deleted the signal instead of measuring it. If a coach
-- is inside the 5 -- the one place a starting back should get the ball -- and
-- calls a keeper instead, that IS the confidence statement. A back's share
-- falling under stress because his quarterback takes the sneak is the finding,
-- not a bug obscuring one.
--
-- The one distinction kept: a DESIGNED run (sneak, keeper, draw) is a called
-- play, so it counts. A SCRAMBLE is a collapsed pocket -- nobody chose to give
-- him the ball -- so it does not. Both stay in the event table, flagged, so
-- this choice is auditable rather than baked in.
--
-- The user's own cross-check on whether this unfairly buries starters:
--   "it will not effect the starting RB overall because if you look at the
--    rushing inside the 20 and success rate then more than likely it is going
--    to the starting rb"
-- That check is v_nfl_redzone_tiers (inside-20 opportunities and TDs), which is
-- exactly why the tiers live alongside the stress split rather than inside it.
CREATE OR REPLACE VIEW silver.v_nfl_team_opportunity_volume AS
WITH e AS (
    SELECT o.*, COALESCE(p.position, 'UNK') AS position
    FROM silver.nfl_opportunity_event o
    LEFT JOIN silver.nfl_player p ON p.player_id = o.player_id
    -- scrambles are not a coaching decision; everything else counts
    WHERE o.opportunity_type = 'target' OR COALESCE(o.is_designed_run, true)
)
SELECT season, week, game_id, posteam AS team,
       count(*) FILTER (WHERE opportunity_type = 'target')        AS team_targets,
       count(*) FILTER (WHERE opportunity_type = 'rush')          AS team_rushes,
       count(*) FILTER (WHERE opportunity_type = 'target' AND is_high_stress)
                                                                   AS team_targets_stress,
       count(*) FILTER (WHERE opportunity_type = 'rush' AND is_high_stress)
                                                                   AS team_rushes_stress,
       count(*) FILTER (WHERE opportunity_type = 'target' AND NOT is_high_stress)
                                                                   AS team_targets_calm,
       count(*) FILTER (WHERE opportunity_type = 'rush' AND NOT is_high_stress)
                                                                   AS team_rushes_calm,
       count(*) FILTER (WHERE is_inside_20)                        AS team_opps_inside_20,
       count(*) FILTER (WHERE is_inside_10)                        AS team_opps_inside_10,
       count(*) FILTER (WHERE is_inside_5)                         AS team_opps_inside_5,
       count(*) FILTER (WHERE is_goal_to_go)                       AS team_opps_g2g,
       count(*) FILTER (WHERE stress_level = 3)                    AS team_opps_max_stress,
       -- the QB's slice of the pool, surfaced rather than hidden: this is the
       -- number that explains a back's stress share, so it should be readable
       -- next to it instead of buried in a denominator
       count(*) FILTER (WHERE opportunity_type = 'rush' AND position = 'QB')
                                                                   AS team_qb_designed_runs,
       count(*) FILTER (WHERE opportunity_type = 'rush' AND position = 'QB'
                          AND is_inside_5)                         AS team_qb_runs_inside_5,
       count(*) FILTER (WHERE opportunity_type = 'rush' AND position = 'QB'
                          AND is_high_stress)                      AS team_qb_runs_stress
FROM e
GROUP BY season, week, game_id, posteam;

-- THE SPINE ITSELF. One row per player per game, carrying only the
-- position-appropriate opportunity metric and its intra-team share.
--
-- spine_metric names which stat is being counted so nothing downstream has to
-- guess, and so a mis-gated position is visible rather than silent.
CREATE OR REPLACE VIEW silver.v_nfl_opportunity_spine AS
WITH counted AS (
    SELECT e.season, e.week, e.game_id, e.posteam AS team, e.player_id,
           ANY_VALUE(e.player_name)                                  AS player_name,
           count(*) FILTER (WHERE e.opportunity_type = 'target')      AS targets,
           count(*) FILTER (WHERE e.opportunity_type = 'rush')        AS rushes,
           count(*) FILTER (WHERE e.opportunity_type = 'target' AND e.is_high_stress)
                                                                       AS targets_stress,
           count(*) FILTER (WHERE e.opportunity_type = 'rush'   AND e.is_high_stress)
                                                                       AS rushes_stress,
           count(*) FILTER (WHERE e.opportunity_type = 'target' AND NOT e.is_high_stress)
                                                                       AS targets_calm,
           count(*) FILTER (WHERE e.opportunity_type = 'rush'   AND NOT e.is_high_stress)
                                                                       AS rushes_calm
    FROM silver.nfl_opportunity_event e
    WHERE e.player_id IS NOT NULL
      -- scrambles excluded from a player's own count too, matching the
      -- denominator in v_nfl_team_opportunity_volume
      AND (e.opportunity_type = 'target' OR COALESCE(e.is_designed_run, true))
    GROUP BY e.season, e.week, e.game_id, e.posteam, e.player_id
)
-- THE GATE
--   WR, TE  -> targets
--   RB, FB  -> rush attempts
--   QB      -> rush attempts, per the user: "qb if he runs is counted as a
--              running back in my system". Labeled rush_attempts_qb so a
--              quarterback appearing high on a rushing leaderboard is obviously
--              a quarterback and not a mislabel -- when Hurts tops Philadelphia
--              inside the 5, that is the actual finding, not an error.
--
-- No inference. An earlier version fell back to "whichever stat he accumulated
-- more of" for unlabeled positions, which silently pulled QBs in under a name
-- that looked like a real gate. Guessing the gate defeats having one.
SELECT c.season, c.week, c.game_id, c.team, c.player_id, c.player_name,
       p.position,
       CASE WHEN p.position = 'QB'          THEN 'rush_attempts_qb'
            WHEN p.position IN ('RB', 'FB') THEN 'rush_attempts'
            ELSE 'targets' END                                  AS spine_metric,
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN c.rushes
            ELSE c.targets END                                  AS spine_opportunities,
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN c.rushes_stress
            ELSE c.targets_stress END                           AS spine_opps_stress,
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN c.rushes_calm
            ELSE c.targets_calm END                             AS spine_opps_calm,
       -- the matching team denominator for that same metric
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN v.team_rushes
            ELSE v.team_targets END                             AS team_spine_opportunities,
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN v.team_rushes_stress
            ELSE v.team_targets_stress END                       AS team_spine_opps_stress,
       CASE WHEN p.position IN ('RB', 'FB', 'QB') THEN v.team_rushes_calm
            ELSE v.team_targets_calm END                         AS team_spine_opps_calm,
       -- both raw counts kept: a receiving back's targets still matter, they
       -- are just not his spine
       c.targets, c.rushes,
       -- the QB's share of this team's rush pool, carried on every row. This is
       -- the number that EXPLAINS a back's stress share, so it should be
       -- readable beside it rather than buried in a denominator.
       v.team_qb_designed_runs, v.team_qb_runs_inside_5, v.team_qb_runs_stress
FROM counted c
LEFT JOIN silver.nfl_player p ON p.player_id = c.player_id
JOIN silver.v_nfl_team_opportunity_volume v
  ON v.game_id = c.game_id AND v.team = c.team
WHERE p.position IN ('WR', 'TE', 'RB', 'FB', 'QB');

-- =============================================================================
-- LAYER 2 -- STRESS. The heart of the indicator.
--
-- "the higher the stress level the more they go to who they know"
--
-- confidence_delta = his share of the team's spine opportunities when the
-- situation is tight, MINUS his share when it is not. Positive means the coach
-- concentrates on him under pressure. That is the measurement.
--
-- Read alongside spine_opps_stress: a delta computed off 2 high-stress
-- opportunities is noise, which is why the raw counts travel with it and why
-- the indicator applies shrinkage rather than trusting the ratio directly.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_stress_split AS
SELECT season, team, player_id,
       ANY_VALUE(player_name)                                    AS player_name,
       ANY_VALUE(spine_metric)                                   AS spine_metric,
       count(DISTINCT game_id)                                    AS games,
       sum(spine_opportunities)                                   AS spine_opps,
       sum(team_spine_opportunities)                              AS team_spine_opps,
       sum(spine_opps_stress)                                     AS spine_opps_stress,
       sum(team_spine_opps_stress)                                AS team_spine_opps_stress,
       sum(spine_opps_calm)                                       AS spine_opps_calm,
       sum(team_spine_opps_calm)                                  AS team_spine_opps_calm,
       -- overall intra-team share of his own position's opportunity pool
       round(1.0 * sum(spine_opportunities)
             / NULLIF(sum(team_spine_opportunities), 0), 4)        AS share_overall,
       -- share when it is tight, and when it is not
       round(1.0 * sum(spine_opps_stress)
             / NULLIF(sum(team_spine_opps_stress), 0), 4)          AS share_stress,
       round(1.0 * sum(spine_opps_calm)
             / NULLIF(sum(team_spine_opps_calm), 0), 4)            AS share_calm,
       -- THE SIGNAL
       round(1.0 * sum(spine_opps_stress) / NULLIF(sum(team_spine_opps_stress), 0)
           - 1.0 * sum(spine_opps_calm)   / NULLIF(sum(team_spine_opps_calm), 0), 4)
                                                                   AS confidence_delta
FROM silver.v_nfl_opportunity_spine
GROUP BY season, team, player_id;

-- =============================================================================
-- LAYER 4 -- WHERE. Field-zone tiers, shaped like PFR's red-zone pages
-- (/years/2026/redzone-passing.htm, redzone-rushing.htm): three nested tiers,
-- each with opportunities, yards and TDs.
--
-- The "%" column on those PFR pages is a TEAM share, which is also the only
-- version that answers this pond's question -- a league-wide red-zone
-- percentage just ranks offenses. Named _intra so that is unambiguous.
--
-- _shrunk columns exist because red-zone samples are genuinely tiny. Confirmed
-- on real weeks 1-2 data: teams had between 0 and 18 inside-20 opportunities
-- for the entire season so far. A raw share on a denominator of 5 is mostly
-- noise -- 2-of-5 reads as 40% and would outrank a far more clearly trusted
-- player at 6-of-18. Adding k=4 to the denominator pulls small samples toward
-- zero until volume earns the number, and fades to irrelevance as real
-- denominators grow. Raw and shrunk are both exposed so the adjustment is
-- always visible and reversible.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_redzone_tiers AS
WITH pl AS (
    SELECT season, posteam AS team, player_id,
           ANY_VALUE(player_name) AS player_name,
           ANY_VALUE(opportunity_type) AS opportunity_type,
           count(*) FILTER (WHERE is_inside_20)                     AS opp_i20,
           sum(CASE WHEN is_inside_20 THEN yards_gained ELSE 0 END)  AS yds_i20,
           count(*) FILTER (WHERE is_inside_20 AND touchdown)        AS td_i20,
           count(*) FILTER (WHERE is_inside_10)                     AS opp_i10,
           sum(CASE WHEN is_inside_10 THEN yards_gained ELSE 0 END)  AS yds_i10,
           count(*) FILTER (WHERE is_inside_10 AND touchdown)        AS td_i10,
           count(*) FILTER (WHERE is_inside_5)                      AS opp_i5,
           sum(CASE WHEN is_inside_5 THEN yards_gained ELSE 0 END)   AS yds_i5,
           count(*) FILTER (WHERE is_inside_5 AND touchdown)         AS td_i5,
           count(*) FILTER (WHERE is_goal_to_go)                    AS opp_g2g,
           count(*) FILTER (WHERE is_goal_to_go AND touchdown)       AS td_g2g
    FROM silver.nfl_opportunity_event
    WHERE player_id IS NOT NULL
    GROUP BY season, posteam, player_id
), tm AS (
    SELECT season, posteam AS team,
           count(*) FILTER (WHERE is_inside_20)  AS t_i20,
           count(*) FILTER (WHERE is_inside_10)  AS t_i10,
           count(*) FILTER (WHERE is_inside_5)   AS t_i5,
           count(*) FILTER (WHERE is_goal_to_go) AS t_g2g
    FROM silver.nfl_opportunity_event
    GROUP BY season, posteam
)
SELECT pl.season, pl.team, pl.player_id, pl.player_name, pl.opportunity_type,
       tm.t_i20 AS team_opp_i20, tm.t_i10 AS team_opp_i10, tm.t_i5 AS team_opp_i5,
       pl.opp_i20, pl.yds_i20, pl.td_i20,
       round(1.0 * pl.opp_i20 / NULLIF(tm.t_i20, 0), 4)     AS pct_i20_intra,
       round(1.0 * pl.opp_i20 / NULLIF(tm.t_i20 + 4, 0), 4) AS pct_i20_shrunk,
       pl.opp_i10, pl.yds_i10, pl.td_i10,
       round(1.0 * pl.opp_i10 / NULLIF(tm.t_i10, 0), 4)     AS pct_i10_intra,
       round(1.0 * pl.opp_i10 / NULLIF(tm.t_i10 + 4, 0), 4) AS pct_i10_shrunk,
       pl.opp_i5, pl.yds_i5, pl.td_i5,
       round(1.0 * pl.opp_i5 / NULLIF(tm.t_i5, 0), 4)       AS pct_i5_intra,
       round(1.0 * pl.opp_i5 / NULLIF(tm.t_i5 + 4, 0), 4)   AS pct_i5_shrunk,
       pl.opp_g2g, pl.td_g2g,
       round(1.0 * pl.opp_g2g / NULLIF(tm.t_g2g + 4, 0), 4) AS pct_g2g_shrunk
FROM pl JOIN tm ON tm.season = pl.season AND tm.team = pl.team
WHERE pl.opp_i20 > 0;

-- Where on the field the ball went: pass location x air-yard depth for
-- targets, run location x gap for carries. One view, one row per bucket.
CREATE OR REPLACE VIEW silver.v_nfl_opportunity_location_map AS
SELECT season, posteam AS team, player_id,
       ANY_VALUE(player_name) AS player_name,
       opportunity_type,
       COALESCE(pass_location, run_location, 'unknown') AS field_side,
       CASE WHEN opportunity_type = 'rush' THEN COALESCE(run_gap, 'no_gap_recorded')
            WHEN air_yards IS NULL   THEN 'unknown'
            WHEN air_yards < 0       THEN 'behind_los'
            WHEN air_yards <= 5      THEN 'short_0_5'
            WHEN air_yards <= 10     THEN 'short_6_10'
            WHEN air_yards <= 20     THEN 'intermediate_11_20'
            ELSE 'deep_21_plus' END                    AS depth_or_gap,
       count(*)                                        AS opportunities,
       count(*) FILTER (WHERE is_high_stress)           AS opportunities_stress,
       sum(yards_gained)                               AS yards,
       count(*) FILTER (WHERE touchdown)                AS tds
FROM silver.nfl_opportunity_event
WHERE player_id IS NOT NULL
GROUP BY season, posteam, player_id, opportunity_type, field_side, depth_or_gap;

-- =============================================================================
-- LAYER 3 -- the depth chart, resolved point-in-time per game.
-- Kickoff derived the way ingest_rotowire_props.py does it: schedule gametime
-- is published in US/Eastern, converted to a real instant.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_depth_chart_pregame AS
WITH kick AS (
    SELECT game_id, season, week, home_team AS team,
           timezone('America/New_York', game_date + CAST(game_time_local AS TIME)) AS kickoff_utc
    FROM silver.nfl_schedule
    UNION ALL
    SELECT game_id, season, week, away_team,
           timezone('America/New_York', game_date + CAST(game_time_local AS TIME))
    FROM silver.nfl_schedule
), best AS (
    SELECT k.game_id, k.season, k.week, k.team, k.kickoff_utc,
           max(d.snapshot_at) AS snapshot_at
    FROM kick k
    JOIN silver.nfl_depth_chart_snapshot d
      ON d.team = k.team AND d.snapshot_at <= k.kickoff_utc
    GROUP BY k.game_id, k.season, k.week, k.team, k.kickoff_utc
)
SELECT b.game_id, b.season, b.week, b.team, b.kickoff_utc, b.snapshot_at,
       d.pos_abb, d.pos_name, d.pos_rank, d.gsis_id AS player_id, d.player_name
FROM best b
JOIN silver.nfl_depth_chart_snapshot d
  ON d.team = b.team AND d.snapshot_at = b.snapshot_at
WHERE d.pos_grp = '3WR 1TE'
  AND d.pos_abb IN ('QB', 'RB', 'WR', 'TE', 'FB');

-- =============================================================================
-- COMPONENTS -- all five layers, facts only, no weighting.
--
-- Kept separate from the indicator on purpose: these are observations. If the
-- weights below are ever retuned or discarded, nothing in this view moves.
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_player_usage_components AS
WITH scrim AS (
    -- LAYER 5: Yards From Scrimmage. Reused, not recomputed.
    SELECT s.season, s.team, s.player_id,
           sum(s.touches)                                       AS touches,
           sum(s.scrimmage_yards)                               AS scrimmage_yards,
           sum(s.scrimmage_tds)                                 AS scrimmage_tds,
           round(1.0 * sum(s.scrimmage_yards)
                 / NULLIF(sum(s.touches), 0), 2)                AS yards_per_touch,
           round(1.0 * sum(s.scrimmage_yards)
                 / NULLIF(sum(t.team_scrimmage_yards), 0), 4)   AS scrimmage_yards_share_intra
    FROM silver.nfl_player_scrimmage_week s
    JOIN (SELECT season, game_id, team, sum(scrimmage_yards) AS team_scrimmage_yards
          FROM silver.nfl_player_scrimmage_week GROUP BY 1,2,3) t
      ON t.game_id = s.game_id AND t.team = s.team
    WHERE s.touches > 0
    GROUP BY s.season, s.team, s.player_id
), depth AS (
    SELECT season, team, player_id,
           arg_max(pos_abb,  week) AS depth_pos,
           arg_max(pos_rank, week) AS depth_rank,
           max(week)               AS depth_as_of_week
    FROM silver.v_nfl_depth_chart_pregame
    WHERE player_id IS NOT NULL
    GROUP BY season, team, player_id
)
SELECT ss.season, ss.team, ss.player_id,
       COALESCE(ss.player_name, p.player_display_name)  AS player_name,
       p.position, ss.games,
       -- LAYER 1: the spine
       ss.spine_metric, ss.spine_opps, ss.team_spine_opps, ss.share_overall,
       -- LAYER 2: stress
       ss.spine_opps_stress, ss.team_spine_opps_stress, ss.share_stress,
       ss.spine_opps_calm, ss.team_spine_opps_calm, ss.share_calm,
       ss.confidence_delta,
       -- LAYER 3: depth chart
       d.depth_pos, d.depth_rank, d.depth_as_of_week,
       -- LAYER 4: where
       rz.opp_i20, rz.opp_i10, rz.opp_i5, rz.opp_g2g,
       rz.td_i20, rz.td_i5,
       rz.team_opp_i20,
       rz.pct_i20_intra, rz.pct_i20_shrunk, rz.pct_i10_shrunk, rz.pct_i5_shrunk,
       rz.pct_g2g_shrunk,
       -- LAYER 5: return
       sc.touches, sc.scrimmage_yards, sc.yards_per_touch,
       sc.scrimmage_yards_share_intra, sc.scrimmage_tds,
       -- intra-team usage ranks. The pos-group rank is the ONLY one comparable
       -- to depth_rank, since depth_rank is itself within-position (WR1/WR2).
       -- Ranking a TE against the team's WRs and calling the gap a surplus was
       -- a real bug caught on first run: every TE1 and RB1 showed a large
       -- negative surplus purely because receivers out-target them.
       row_number() OVER (PARTITION BY ss.season, ss.team ORDER BY ss.spine_opps DESC)
                                                        AS usage_rank_on_team,
       row_number() OVER (PARTITION BY ss.season, ss.team, d.depth_pos
                          ORDER BY ss.spine_opps DESC)  AS usage_rank_in_pos_group
FROM silver.v_nfl_stress_split ss
LEFT JOIN silver.v_nfl_redzone_tiers rz
       ON rz.season = ss.season AND rz.team = ss.team AND rz.player_id = ss.player_id
LEFT JOIN scrim sc
       ON sc.season = ss.season AND sc.team = ss.team AND sc.player_id = ss.player_id
LEFT JOIN depth d
       ON d.season = ss.season AND d.team = ss.team AND d.player_id = ss.player_id
LEFT JOIN silver.nfl_player p ON p.player_id = ss.player_id;

-- =============================================================================
-- THE INDICATOR
--
-- READ THIS BEFORE TRUSTING THE NUMBER.
--
-- Everything above this line is an observed fact. This view is not. It is a
-- weighted heuristic. It has NOT been backtested, and no claim is made that a
-- high score predicts anything. Validating it -- does a rising score precede a
-- prop line moving -- is Phase 2 and needs a walk-forward test on
-- point-in-time data, not a correlation against this season's own totals.
--
-- The weights sit in one CTE so they change in one place, and every input is
-- exposed raw above so the score can always be taken apart.
--
-- STRESS CARRIES THE MOST WEIGHT because it is the user's actual thesis: the
-- tighter the situation, the more a coach goes to who he knows. Raw share is
-- volume, which a book already prices. The stress delta is the part that says
-- something a box score does not.
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_player_usage_index AS
WITH weights AS (
    -- Change here and nowhere else. Sums to 1.0.
    SELECT 0.34::DOUBLE AS w_stress,   -- does his share GROW under pressure
           0.22::DOUBLE AS w_redzone,  -- share of the scarcest chances
           0.20::DOUBLE AS w_share,    -- baseline intra-team opportunity share
           0.12::DOUBLE AS w_depth,    -- out-earning his listed depth slot
           0.12::DOUBLE AS w_return    -- what happens once he has it
), base AS (
    SELECT c.*,
           CASE WHEN c.depth_rank IS NULL THEN NULL
                ELSE c.depth_rank - c.usage_rank_in_pos_group END AS depth_surplus,
           -- Y/Tch scaled within his own team: "efficient" must mean efficient
           -- against the teammates competing for the same touches, not against
           -- the league, which would reintroduce the cross-team comparison
           -- this pond exists to avoid.
           CASE WHEN max(c.yards_per_touch) OVER w = min(c.yards_per_touch) OVER w THEN 0.5
                ELSE (c.yards_per_touch - min(c.yards_per_touch) OVER w)
                     / NULLIF(max(c.yards_per_touch) OVER w
                              - min(c.yards_per_touch) OVER w, 0) END AS ypt_scaled_in_team,
           -- Shrink the stress delta by how many high-stress chances it rests
           -- on. A +40% delta off 2 opportunities is not a finding. At 8+
           -- high-stress opportunities this is essentially unshrunk.
           COALESCE(c.confidence_delta, 0)
             * (COALESCE(c.spine_opps_stress, 0)::DOUBLE
                / (COALESCE(c.spine_opps_stress, 0) + 6))          AS confidence_delta_shrunk
    FROM gold.v_nfl_player_usage_components c
    WINDOW w AS (PARTITION BY c.season, c.team)
), scored AS (
    SELECT b.*,
           -- stress axis: 0 delta -> 50. +0.20 (twenty points more share when
           -- tight) -> 100. Symmetric downward, so a coach visibly taking the
           -- ball OUT of someone's hands under pressure scores below 50.
           round(LEAST(GREATEST(50 + 250 * b.confidence_delta_shrunk, 0), 100), 1)
                                                                   AS stress_score,
           round(LEAST(100 * (0.5 * COALESCE(b.pct_i20_shrunk, 0)
                              + 0.3 * COALESCE(b.pct_i10_shrunk, 0)
                              + 0.2 * COALESCE(b.pct_i5_shrunk, 0)) / 0.32, 100), 1)
                                                                   AS redzone_score,
           round(LEAST(100 * COALESCE(b.share_overall, 0) / 0.35, 100), 1)
                                                                   AS share_score,
           round(50 + 50 * LEAST(GREATEST(COALESCE(b.depth_surplus, 0), -3), 3) / 3.0, 1)
                                                                   AS depth_score,
           round(LEAST(100 * (0.5 * COALESCE(b.ypt_scaled_in_team, 0)
                              + 0.5 * COALESCE(b.scrimmage_yards_share_intra, 0) / 0.40),
                       100), 1)                                    AS return_score
    FROM base b
)
SELECT s.season, s.team, s.player_id, s.player_name, s.position, s.games,
       s.spine_metric,
       round(w.w_stress  * s.stress_score
           + w.w_redzone * s.redzone_score
           + w.w_share   * s.share_score
           + w.w_depth   * s.depth_score
           + w.w_return  * s.return_score, 1)                      AS usage_index_score,
       -- the axes, readable on their own
       s.stress_score, s.redzone_score, s.share_score, s.depth_score, s.return_score,
       -- LAYER 2 raw: the actual thesis, in plain numbers
       s.share_calm, s.share_stress, s.confidence_delta,
       s.spine_opps_stress, s.team_spine_opps_stress,
       -- the classification. A single score collapses cases a bettor must
       -- treat completely differently, so the role travels with it.
       CASE
         WHEN s.spine_opps < 5                                THEN 'INSUFFICIENT SAMPLE'
         WHEN COALESCE(s.depth_surplus, 0) >= 1
              AND s.share_score >= 20                          THEN 'RISING -- OUT-EARNING DEPTH CHART'
         WHEN s.stress_score >= 60 AND s.share_score >= 40     THEN 'PRIMARY -- TRUSTED UNDER PRESSURE'
         WHEN s.stress_score >= 60 AND s.share_score <  40     THEN 'CLOSER -- SMALL ROLE, BIG MOMENTS'
         WHEN s.stress_score <  40 AND s.share_score >= 40     THEN 'VOLUME ONLY -- BENCHED WHEN IT TIGHTENS'
         WHEN s.redzone_score >= 45 AND s.share_score < 40      THEN 'RED ZONE SPECIALIST'
         WHEN s.share_score >= 20                              THEN 'ROTATIONAL CONTRIBUTOR'
         ELSE 'FRINGE'
       END                                                        AS usage_role,
       -- facts carried through so the score is never taken on faith
       s.spine_opps, s.team_spine_opps, s.share_overall,
       s.usage_rank_on_team, s.usage_rank_in_pos_group,
       s.depth_pos, s.depth_rank, s.depth_surplus, s.depth_as_of_week,
       s.opp_i20, s.opp_i10, s.opp_i5, s.opp_g2g, s.team_opp_i20,
       s.pct_i20_intra, s.pct_i20_shrunk, s.td_i20, s.td_i5,
       s.touches, s.yards_per_touch, s.scrimmage_yards,
       s.scrimmage_yards_share_intra, s.scrimmage_tds
FROM scored s CROSS JOIN weights w
ORDER BY usage_index_score DESC;

-- =============================================================================
-- "Who is THIS coach's son" -- one team at a time, ranked within itself.
-- The pond's whole purpose.
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_player_usage_by_team AS
SELECT team, season,
       row_number() OVER (PARTITION BY team, season ORDER BY usage_index_score DESC)
                                                        AS rank_on_team,
       player_name, position, spine_metric,
       depth_pos, depth_rank, depth_surplus,
       usage_index_score, usage_role,
       stress_score, redzone_score, share_score, depth_score, return_score,
       spine_opps, team_spine_opps, share_overall,
       share_calm, share_stress, confidence_delta,
       opp_i20, team_opp_i20, yards_per_touch, scrimmage_yards
FROM gold.v_nfl_player_usage_index
ORDER BY team, rank_on_team;

-- =============================================================================
-- CORRELATION: usage index x the TD log
--
-- The user's framing, and the reason the TD logs were built before this pond:
--
-- The TD log exists upstream of this pond for exactly this join: it is the
-- confirmation step for the usage read. Related stats must agree -- if the
-- usage index is right, the scoring log should echo it.
--
-- The usage index says who the coach LEANS ON.
-- silver.nfl_td_log says who actually FINISHED. Putting them side by side turns
-- an opinion into a testable claim:
--
--   agreement   -- high confidence AND scoring. The read holds.
--   opportunity -- high confidence, no TDs yet. The coach keeps going back to
--                  him and it has not cashed. Anytime-TD markets price the
--                  result, not the usage, so this is where a line lags.
--   hollow      -- TDs without confidence. Scored on volume or a broken play,
--                  not on trust. The most dangerous profile to bet on repeating,
--                  which is exactly the profile a book will advertise.
--
-- Both sides are already in this lake and both are facts. The only judgement
-- here is the label, and the counts that produce it travel with it.
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_player_usage_td_correlation AS
WITH td AS (
    SELECT season, scorer_player_id AS player_id,
           ANY_VALUE(scoring_team)                          AS team,
           count(*)                                          AS tds,
           count(*) FILTER (WHERE is_red_zone)               AS tds_red_zone,
           count(*) FILTER (WHERE is_goal_to_go)             AS tds_goal_to_go,
           count(*) FILTER (WHERE is_third_down)             AS tds_third_down,
           count(*) FILTER (WHERE td_type = 'rush')          AS tds_rush,
           count(*) FILTER (WHERE td_type = 'pass')          AS tds_rec,
           count(DISTINCT game_id)                           AS games_with_td
    FROM silver.nfl_td_log
    WHERE scorer_player_id IS NOT NULL
    GROUP BY season, scorer_player_id
)
SELECT cs.season, cs.team, cs.player_id, cs.player_name, cs.position,
       cs.spine_metric, cs.usage_index_score, cs.usage_role,
       -- the confidence side
       cs.share_overall, cs.share_calm, cs.share_stress, cs.confidence_delta,
       cs.opp_i20, cs.opp_i10, cs.opp_i5, cs.opp_g2g,
       cs.pct_i20_shrunk,
       -- the finishing side (TD log)
       COALESCE(td.tds, 0)             AS tds,
       COALESCE(td.tds_red_zone, 0)    AS tds_red_zone,
       COALESCE(td.tds_goal_to_go, 0)  AS tds_goal_to_go,
       COALESCE(td.tds_rush, 0)        AS tds_rush,
       COALESCE(td.tds_rec, 0)         AS tds_rec,
       COALESCE(td.games_with_td, 0)   AS games_with_td,
       -- conversion: TDs per red-zone opportunity. The bridge between the two.
       round(1.0 * COALESCE(td.tds_red_zone, 0) / NULLIF(cs.opp_i20, 0), 3)
                                       AS td_per_redzone_opp,
       -- IF THIS THEN THAT: does the confidence read agree with the scoring?
       CASE
         WHEN cs.usage_index_score >= 55 AND COALESCE(td.tds, 0) >= 2
              THEN 'AGREEMENT -- trusted and finishing'
         WHEN cs.usage_index_score >= 55 AND COALESCE(td.tds, 0) = 0
              THEN 'OPPORTUNITY -- trusted, has not cashed yet'
         WHEN cs.usage_index_score >= 55
              THEN 'AGREEMENT -- trusted, finishing lightly'
         WHEN cs.usage_index_score < 40 AND COALESCE(td.tds, 0) >= 2
              THEN 'HOLLOW -- scoring without trust, fragile'
         WHEN COALESCE(td.tds, 0) = 0 AND cs.usage_index_score < 40
              THEN 'QUIET -- neither trusted nor scoring'
         ELSE 'MIXED'
       END                             AS correlation_flag
FROM gold.v_nfl_player_usage_index cs
LEFT JOIN td ON td.season = cs.season AND td.player_id = cs.player_id
WHERE cs.usage_role <> 'INSUFFICIENT SAMPLE'
ORDER BY cs.usage_index_score DESC;

-- =============================================================================
-- frontal-lobe2 : DEFENSE POND -- the toxic pond
-- =============================================================================
-- Every other pond in this ramp measures an offensive player's own team. This
-- one measures the OPPOSING defense he is about to face, because that defense
-- is the thing that decides whether a usage-index read cashes on a RotoWire
-- line or not. A player can be exactly as trusted as the lake says and still
-- not deliver the yards, because the defense he drew that week is toxic.
--
-- Kept to exactly the 8 stat columns specified, no more:
--   1. NFL ranking in defense (scoring defense, points allowed per game)
--   2. Ranking in sacks
--   3. Ranking in interceptions
--   4. Points allowed in the 2nd half
--   5. Team win percentage
--   6. Who gets the sacks (individual)
--   7. Who intercepts the ball (individual)
--   8. Defensive rank in turnovers created
--
-- Plus THE IB SCORE on top -- see below. This is the "quarterback comfort"
-- read the user asked for: pressure up the middle collapses a QB's comfort,
-- and a QB who is comfortable produces the exact stat signature the user
-- described -- a back over 100 rushing, multiple receivers over 60, four
-- passing TDs. The evidence for the score is IN those stats: how a defense is
-- being scored on, and how often.
--
-- SOURCE: everything here already exists in this lake. No new vendor needed.
--   silver.nfl_team_week            -- def_sacks, def_interceptions,
--                                       def_fumbles_forced, def_tds
--   silver.nfl_pfr_adv_defense_week -- def_pressures, def_times_blitzed,
--                                       def_completion_pct, def_yards_allowed_
--                                       per_tgt, def_adot, def_passer_rating_
--                                       allowed (the PFR-mirrored coverage
--                                       stats -- see docs/PFR_SOURCE_NOTE.md)
--   silver.nfl_player_defense_week  -- individual sacks/INTs (#6, #7)
--   silver.nfl_schedule             -- final scores, win/loss, home/away
--   nflverse pbp (already pulled for the TD log/usage pond) -- quarter-level
--     scoring, needed ONLY for #4 (2nd-half points allowed), which is not
--     published as a team-week aggregate anywhere in nflverse.
--
-- Engine: DuckDB. Depends on sql/nfl_pfr_schema.sql, sql/nfl_schedule_schema.sql.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- =============================================================================
-- BASE TABLE: points allowed by half. The one stat in this pond not already
-- sitting in a team-week table anywhere in nflverse -- has to be built from
-- pbp scoring plays, same source as silver.nfl_td_log.
--
-- GRAIN: one row per team per game per half. A defense's 2nd-half number is
-- what should worry a bettor holding a 2nd-half prop or a team total -- a unit
-- that tightens up after halftime adjustments is a different bet than one
-- that caved for four quarters.
-- =============================================================================
CREATE TABLE IF NOT EXISTS silver.nfl_points_by_half (
    season                  INTEGER NOT NULL,
    week                    INTEGER NOT NULL,
    game_id                 VARCHAR NOT NULL,
    team                    VARCHAR NOT NULL,      -- the DEFENSE (points allowed BY this team)
    opponent                VARCHAR NOT NULL,
    half                    INTEGER NOT NULL,      -- 1 or 2 (OT folded into 2nd half)
    points_allowed          INTEGER NOT NULL,
    ingest_run_id           VARCHAR NOT NULL,
    PRIMARY KEY (season, game_id, team, half)
);
CREATE INDEX IF NOT EXISTS ix_pbh_team ON silver.nfl_points_by_half (season, team, week);

-- =============================================================================
-- #4: points allowed in the 2nd half, rolled to season-to-date per team.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_points_allowed_2nd_half AS
SELECT season, team,
       count(DISTINCT game_id)                                  AS games,
       sum(points_allowed)                                      AS points_allowed_2nd_half,
       round(1.0 * sum(points_allowed) / NULLIF(count(DISTINCT game_id), 0), 2)
                                                                 AS points_allowed_2nd_half_per_game
FROM silver.nfl_points_by_half
WHERE half = 2
GROUP BY season, team;

-- =============================================================================
-- #6 / #7: individual production -- who gets the sacks, who gets the picks.
-- One row per player per season, on defense.
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_individual_sacks AS
SELECT d.season, d.team, d.player_id, ANY_VALUE(p.player_display_name) AS player_name,
       ANY_VALUE(p.position)                                     AS position,
       sum(d.def_sacks)                                          AS sacks,
       sum(d.def_qb_hits)                                        AS qb_hits,
       sum(d.def_tackles_for_loss)                                AS tackles_for_loss,
       count(DISTINCT d.game_id)                                  AS games,
       row_number() OVER (PARTITION BY d.season, d.team ORDER BY sum(d.def_sacks) DESC)
                                                                 AS sack_rank_on_team
FROM silver.nfl_player_defense_week d
LEFT JOIN silver.nfl_player p ON p.player_id = d.player_id
WHERE d.def_sacks > 0
GROUP BY d.season, d.team, d.player_id
ORDER BY sacks DESC;

CREATE OR REPLACE VIEW silver.v_nfl_individual_interceptions AS
SELECT d.season, d.team, d.player_id, ANY_VALUE(p.player_display_name) AS player_name,
       ANY_VALUE(p.position)                                     AS position,
       sum(d.def_interceptions)                                  AS interceptions,
       sum(d.def_interception_yards)                             AS interception_yards,
       sum(d.def_pass_defended)                                  AS passes_defended,
       count(DISTINCT d.game_id)                                  AS games,
       row_number() OVER (PARTITION BY d.season, d.team ORDER BY sum(d.def_interceptions) DESC)
                                                                 AS int_rank_on_team
FROM silver.nfl_player_defense_week d
LEFT JOIN silver.nfl_player p ON p.player_id = d.player_id
WHERE d.def_interceptions > 0
GROUP BY d.season, d.team, d.player_id
ORDER BY interceptions DESC;

-- =============================================================================
-- TEAM-LEVEL ROLLUP -- items #1, #2, #3, #5, #8, one row per team per season.
-- Every "ranking" the user asked for is a rank() computed here, in this table,
-- from real season-to-date totals -- not sourced pre-ranked from anywhere,
-- since nflverse does not publish a rankings table (checked; same reason ATS
-- was computed rather than sourced in sql/nfl_schedule_schema.sql).
-- =============================================================================
CREATE OR REPLACE VIEW silver.v_nfl_team_defense_season AS
WITH tw AS (
    SELECT season, team,
           count(DISTINCT game_id)                              AS games,
           -- #1 scoring defense input: points allowed. Uses the schedule table
           -- (real final scores), not team_week, since points allowed is a
           -- game-level fact, not a per-play defensive stat category.
           sum(def_sacks)                                        AS sacks,
           sum(def_interceptions)                                AS interceptions,
           sum(def_fumbles_forced)                                AS fumbles_forced,
           sum(def_tds)                                           AS def_tds,
           sum(def_tackles_for_loss)                              AS tackles_for_loss,
           sum(def_qb_hits)                                       AS qb_hits,
           sum(def_pass_defended)                                 AS passes_defended
    FROM silver.nfl_team_week
    GROUP BY season, team
), sched AS (
    -- final scores + win/loss, one row per team per game (both perspectives)
    SELECT season, home_team AS team, away_team AS opponent, home_score AS points_scored,
           away_score AS points_allowed,
           CASE WHEN home_score > away_score THEN 1
                WHEN home_score < away_score THEN 0 ELSE NULL END AS win
    FROM silver.nfl_schedule WHERE home_score IS NOT NULL
    UNION ALL
    SELECT season, away_team, home_team, away_score, home_score,
           CASE WHEN away_score > home_score THEN 1
                WHEN away_score < home_score THEN 0 ELSE NULL END
    FROM silver.nfl_schedule WHERE home_score IS NOT NULL
), sched_agg AS (
    SELECT season, team,
           count(*)                                              AS games_played,
           sum(win)                                              AS wins,
           count(*) FILTER (WHERE win = 0)                        AS losses,
           sum(points_allowed)                                    AS points_allowed_total,
           round(1.0 * sum(points_allowed) / NULLIF(count(*), 0), 2)
                                                                  AS points_allowed_per_game,
           -- #5: team win percentage
           round(100.0 * sum(win) / NULLIF(count(*), 0), 1)       AS win_pct
    FROM sched
    GROUP BY season, team
), adv AS (
    -- pass-defense context that feeds the IB Score: how a defense is being
    -- scored on and how often, per the user's own framing
    SELECT season, team,
           sum(def_pressures)                                     AS pressures,
           sum(def_times_blitzed)                                 AS times_blitzed,
           sum(def_times_hurried)                                 AS times_hurried,
           sum(def_times_hitqb)                                   AS times_hit_qb,
           round(AVG(def_completion_pct), 4)                       AS completion_pct_allowed,
           round(AVG(def_yards_allowed_per_tgt), 3)                AS yards_allowed_per_tgt,
           round(AVG(def_passer_rating_allowed), 2)                AS passer_rating_allowed,
           round(AVG(def_adot), 2)                                 AS adot_allowed
    FROM silver.nfl_pfr_adv_defense_week
    GROUP BY season, team
)
SELECT tw.season, tw.team, sa.games_played,
       -- #5
       sa.wins, sa.losses, sa.win_pct,
       -- #1 (scoring defense)
       sa.points_allowed_total, sa.points_allowed_per_game,
       rank() OVER (PARTITION BY tw.season ORDER BY sa.points_allowed_per_game ASC)
                                                                  AS rank_scoring_defense,
       -- #2
       tw.sacks,
       rank() OVER (PARTITION BY tw.season ORDER BY tw.sacks DESC) AS rank_sacks,
       -- #3
       tw.interceptions,
       rank() OVER (PARTITION BY tw.season ORDER BY tw.interceptions DESC) AS rank_interceptions,
       -- #8: turnovers created = interceptions + fumbles forced (the standard
       -- definition; nflverse does not publish a combined column, so it is
       -- summed here from the two components it does publish)
       tw.interceptions + tw.fumbles_forced                        AS turnovers_created,
       rank() OVER (PARTITION BY tw.season
                    ORDER BY tw.interceptions + tw.fumbles_forced DESC)
                                                                  AS rank_turnovers_created,
       -- context that feeds the IB Score
       tw.qb_hits, tw.tackles_for_loss, tw.passes_defended, tw.def_tds,
       adv.pressures, adv.times_blitzed, adv.times_hurried, adv.times_hit_qb,
       adv.completion_pct_allowed, adv.yards_allowed_per_tgt,
       adv.passer_rating_allowed, adv.adot_allowed,
       ph.points_allowed_2nd_half, ph.points_allowed_2nd_half_per_game
FROM tw
JOIN sched_agg sa ON sa.season = tw.season AND sa.team = tw.team
LEFT JOIN adv ON adv.season = tw.season AND adv.team = tw.team
LEFT JOIN silver.v_nfl_points_allowed_2nd_half ph
       ON ph.season = tw.season AND ph.team = tw.team;

-- =============================================================================
-- THE IB SCORE (Irritable Bowel Score) -- quarterback comfort against a given
-- defense, on the 1-5 scale the user defined:
--
--   CAT 1  no pressure up the middle all day. RB over 100 rushing, multiple
--          WRs over 60 yards, 4 passing TDs -- the QB is comfortable and it
--          shows up in every stat line at once.
--   CAT 5  irritated and aggravated all game -- constant pressure, nothing
--          comes easy.
--
-- Per the user: "the evidence is in the stats -- how they are being scored on
-- and how often." So the score is not a vibe, it's five components, each
-- normalized against the rest of the league this season and averaged:
--
--   PRESSURE    def_pressures + def_times_hitqb + sacks, per game
--   COVERAGE    completion_pct_allowed, yards_allowed_per_tgt, passer_rating_
--               allowed -- can this defense actually stop the throw once
--               pressure gets there
--   TAKEAWAYS   interceptions + fumbles forced, per game -- a defense that
--               creates turnovers is a defense a QB has to play scared of
--   RUN STOP    inverse of rushing yards allowed per game (from nfl_team_week)
--               -- if the run is live, the QB never faces a one-dimensional
--               defense and stays comfortable longer
--   SCORING     points allowed per game, and specifically 2nd half -- does
--               this defense fold as the game goes on
--
-- Each component is scaled 0 (least toxic) to 100 (most toxic) against this
-- season's real league range, THEN AVERAGED, THEN mapped onto 1-5. Nothing is
-- guessed -- every input is a season-to-date real stat, and the scaling
-- bounds move automatically as more of the season is played, per the user's
-- point that "as the season goes it will all fall in line."
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_defense_ib_score AS
WITH d AS (
    SELECT t.*,
           tw.rushing_yards AS rushing_yards_allowed_raw
    FROM silver.v_nfl_team_defense_season t
    LEFT JOIN (SELECT season, opponent_team AS team, sum(rushing_yards) AS rushing_yards
               FROM silver.nfl_team_week GROUP BY season, opponent_team) tw
           ON tw.season = t.season AND tw.team = t.team
), scaled AS (
    SELECT d.*,
           round(1.0 * d.rushing_yards_allowed_raw / NULLIF(d.games_played, 0), 2)
                                                                  AS rushing_yards_allowed_per_game,
           -- pressure per game: sacks + hits + tracked pressures, blended so a
           -- defense that hits the QB without a sack still reads as toxic
           round(1.0 * (d.sacks + d.qb_hits + COALESCE(d.pressures, 0))
                 / NULLIF(d.games_played, 0), 2)                  AS pressure_events_per_game,
           round(1.0 * d.turnovers_created / NULLIF(d.games_played, 0), 2)
                                                                  AS turnovers_per_game
    FROM d
), rng AS (
    -- league min/max THIS SEASON, recomputed every run -- the scaling bounds
    -- move as more games are played, which is the point.
    SELECT season,
           min(pressure_events_per_game) AS p_min, max(pressure_events_per_game) AS p_max,
           min(COALESCE(passer_rating_allowed, 0)) AS pr_min,
           max(COALESCE(passer_rating_allowed, 200)) AS pr_max,
           min(turnovers_per_game) AS to_min, max(turnovers_per_game) AS to_max,
           min(rushing_yards_allowed_per_game) AS ry_min, max(rushing_yards_allowed_per_game) AS ry_max,
           min(points_allowed_per_game) AS pa_min, max(points_allowed_per_game) AS pa_max,
           min(COALESCE(points_allowed_2nd_half_per_game, points_allowed_per_game/2))
                                                     AS pa2_min,
           max(COALESCE(points_allowed_2nd_half_per_game, points_allowed_per_game/2))
                                                     AS pa2_max
    FROM scaled GROUP BY season
), norm AS (
    SELECT s.*,
           -- 0..100, HIGHER = MORE TOXIC on every component
           round(100 * (s.pressure_events_per_game - r.p_min)
                 / NULLIF(r.p_max - r.p_min, 0), 1)                AS pressure_component,
           round(100 * (1 - (COALESCE(s.passer_rating_allowed, r.pr_max) - r.pr_min)
                 / NULLIF(r.pr_max - r.pr_min, 0)), 1)             AS coverage_component,
           round(100 * (s.turnovers_per_game - r.to_min)
                 / NULLIF(r.to_max - r.to_min, 0), 1)              AS takeaway_component,
           round(100 * (1 - (s.rushing_yards_allowed_per_game - r.ry_min)
                 / NULLIF(r.ry_max - r.ry_min, 0)), 1)             AS run_stop_component,
           round(100 * (1 - (s.points_allowed_per_game - r.pa_min)
                 / NULLIF(r.pa_max - r.pa_min, 0)), 1)             AS scoring_component,
           round(100 * (1 - (COALESCE(s.points_allowed_2nd_half_per_game,
                                       s.points_allowed_per_game/2) - r.pa2_min)
                 / NULLIF(r.pa2_max - r.pa2_min, 0)), 1)           AS second_half_component
    FROM scaled s JOIN rng r ON r.season = s.season
)
SELECT season, team, games_played, wins, losses, win_pct,
       rank_scoring_defense, rank_sacks, rank_interceptions, rank_turnovers_created,
       points_allowed_per_game, points_allowed_2nd_half_per_game,
       sacks, interceptions, turnovers_created,
       pressure_component, coverage_component, takeaway_component,
       run_stop_component, scoring_component, second_half_component,
       round((pressure_component + coverage_component + takeaway_component
              + run_stop_component + scoring_component + second_half_component) / 6.0, 1)
                                                                  AS toxicity_index_0_100,
       -- map the 0-100 toxicity index onto the user's 1-5 category scale
       CASE
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 20
              THEN 1
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 40
              THEN 2
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 60
              THEN 3
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 80
              THEN 4
         ELSE 5
       END                                                        AS ib_score,
       CASE
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 20
              THEN 'CAT 1 -- comfortable: clean pocket, run is live, big game likely'
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 40
              THEN 'CAT 2 -- mostly comfortable'
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 60
              THEN 'CAT 3 -- mixed, game-plan dependent'
         WHEN (pressure_component + coverage_component + takeaway_component
               + run_stop_component + scoring_component + second_half_component) / 6.0 < 80
              THEN 'CAT 4 -- uncomfortable, expect pressure'
         ELSE 'CAT 5 -- irritated all game: heavy pressure, takeaways likely'
       END                                                        AS ib_category
FROM norm
ORDER BY toxicity_index_0_100 DESC;

-- =============================================================================
-- THE JOIN THIS POND EXISTS FOR: pair a defense's toxicity against the offense
-- it is about to face, using the usage-pond players on that offense. When the
-- #1 target on a top offense (a name a book uses as bait, per the user) is
-- about to face a high-IB-score defense, that is the mismatch this lake was
-- built to catch.
-- =============================================================================
CREATE OR REPLACE VIEW gold.v_nfl_matchup_toxicity AS
SELECT s.game_id, s.season, s.week, s.game_date,
       s.away_team, s.home_team,
       ha.ib_score AS home_defense_ib_score, ha.ib_category AS home_defense_ib_category,
       aa.ib_score AS away_defense_ib_score, aa.ib_category AS away_defense_ib_category,
       -- the away offense faces the HOME defense, and vice versa
       ha.toxicity_index_0_100 AS home_defense_toxicity,
       aa.toxicity_index_0_100 AS away_defense_toxicity
FROM silver.nfl_schedule s
LEFT JOIN gold.v_nfl_defense_ib_score ha ON ha.season = s.season AND ha.team = s.home_team
LEFT JOIN gold.v_nfl_defense_ib_score aa ON aa.season = s.season AND aa.team = s.away_team;

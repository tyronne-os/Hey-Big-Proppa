-- Parlay leg probability -- HEURISTIC, hit-rate-vs-line only, NOT backtested.
--
-- Added alongside the "HEY BIG PROPPA!" frontend build (see
-- frontend/design/HANDOFF_CLAUDE_CODE.md sec 4 / sec 0 rule 3: "Do not
-- invent derived metrics silently. If a chart needs a metric that no gold
-- object provides, build it as a named, documented view in the lake,
-- export it through scripts/export_ramp.py with its own _index.csv row,
-- and label it in the UI as a model output.")
--
-- Method, per the user's explicit choice (not usage/toxicity/redzone
-- weighted): a player's probability for a prop leg is simply his hit rate
-- against the current FanDuel line over his last 10 games (or fewer if
-- fewer have been played this season). This mirrors exactly what
-- backend/data.py's hit_rate_probability() computes at request time from
-- the exported CSVs directly.
--
-- WHY THIS FILE EXISTS BUT ISN'T WIRED INTO export_ramp.py YET: this
-- session's container has no lake/nfl.duckdb (gitignored, not rebuildable
-- here -- see docs/HANDOFF.md sec 5 and github.md for why) and this
-- environment's network policy blocks the hosts the ingest chain needs.
-- backend/data.py computes the identical hit-rate-vs-line logic directly
-- against lake/gold/nfl/*.csv so the frontend has real numbers regardless.
-- When the lake is next rebuilt on a machine with DuckDB + network access,
-- run this file and add a CHARTS row for it in scripts/export_ramp.py
-- (chart_name = 'parlay_leg_probability') so it becomes a real gold export
-- like every other pond, instead of being backend-computed only.

CREATE OR REPLACE VIEW gold.v_nfl_parlay_leg_probability AS
WITH lines AS (
    SELECT
        player_name,
        market_slug,
        line,
        book_slug,
        fetched_at_utc,
        ROW_NUMBER() OVER (
            PARTITION BY player_name, market_slug
            ORDER BY fetched_at_utc DESC
        ) AS rn
    FROM gold.nfl_prop_line_rotowire
    WHERE book_slug = 'fanduel'
),
current_fanduel_line AS (
    SELECT player_name, market_slug, line
    FROM lines
    WHERE rn = 1
),
-- weekly stat unpivoted per market_slug this project already supports
weekly AS (
    SELECT player_id, team, week, 'rushyds' AS market_slug, rushing_yards AS value
    FROM silver.nfl_player_rushing_week
    UNION ALL
    SELECT player_id, team, week, 'recyds', receiving_yards
    FROM silver.nfl_player_receiving_week
    UNION ALL
    SELECT player_id, team, week, 'recs', receptions
    FROM silver.nfl_player_receiving_week
    UNION ALL
    SELECT player_id, team, week, 'passyds', passing_yards
    FROM silver.nfl_player_passing_week
),
player_names AS (
    SELECT player_id, player_display_name AS player_name
    FROM gold.nfl_player_photos_index  -- or silver.nfl_player, whichever carries display name at rebuild time
),
joined AS (
    SELECT
        w.player_id,
        pn.player_name,
        w.market_slug,
        w.week,
        w.value,
        fl.line
    FROM weekly w
    JOIN player_names pn USING (player_id)
    JOIN current_fanduel_line fl
      ON fl.player_name = pn.player_name AND fl.market_slug = w.market_slug
),
last10 AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY player_id, market_slug ORDER BY week DESC) AS rn
    FROM joined
)
SELECT
    player_id,
    player_name,
    market_slug,
    line,
    COUNT(*) AS games_considered,
    SUM(CASE WHEN value >= line THEN 1 ELSE 0 END) AS games_hit,
    ROUND(SUM(CASE WHEN value >= line THEN 1 ELSE 0 END)::DOUBLE / COUNT(*), 3) AS probability,
    'hit_rate_vs_line -- HEURISTIC, not backtested, v1 has no usage/toxicity/redzone weighting' AS method_label
FROM last10
WHERE rn <= 10
GROUP BY player_id, player_name, market_slug, line;

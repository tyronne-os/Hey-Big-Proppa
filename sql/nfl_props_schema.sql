-- =============================================================================
-- frontal-lobe2 : NFL player props -- RotoWire (all 22 markets, 8 books)
-- =============================================================================
-- Source: https://www.rotowire.com/betting/nfl/player-props.php
-- Confirmed 2026-09-25:
--   - robots.txt allows /betting/ (only /users/login.php and /account/ disallowed)
--   - the real prop lines are RotoWire's OWN first-party betting tables, embedded
--     directly as JSON inside the page's static HTML (no JS execution needed to
--     read them -- a plain HTTP GET returns the data already in the response body)
--   - `isPaywalled = true` in the page's JS only gates RotoWire's own CSV *export*
--     button ("must be a paid subscriber" to click Export). It does NOT hide or
--     restrict the underlying data, which is visible to any visitor and is what
--     this schema loads.
--   - The page ALSO embeds a separate third-party "Props.Cash" demo widget with
--     its own weather-context feed (an unrelated Val Town endpoint). That widget
--     is NOT used as a source here -- only RotoWire's first-party tables are.
--
-- 22 markets confirmed populated (field counts from the raw page, 2026-09-25):
--   TD scorer:  firsttd, anytd, lasttd, twotd, threetd
--   Passing:    comp, passatt, passyds, passtd, intsthrown
--   Rushing:    rushyds, longrush
--   Receiving:  recs, recyds, rushrec (combined rush+rec yards)
--   Defense:    tackle, solo, assist, sack
--   Kicking:    kickpts, fgm, xpm
--
-- 8 sportsbooks tracked (not every book posts every market -- columns are
-- nullable and a book's absence on a given market/game is normal, not a bug):
--   betr, betrivers, caesars, draftkings, fanduel, fanatics, mgm, hardrock,
--   thescore, circasports
-- (note: some prop blocks show "fanduel", others show "fanatics" in the same
--  book-name slot -- RotoWire appears to have transitioned sportsbook partners
--  mid-market-rollout; both are stored as distinct book codes, not merged.)
--
-- GRAIN: one row per (player, game, book, market, pull). Lines move during the
-- week, so this is append-only like odds_snapshots in the CFB schema -- never
-- update or delete a row, always insert a new snapshot. Closing-line value (CLV)
-- analysis depends on keeping every snapshot, not just the latest.
--
-- Engine: DuckDB.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.nfl_prop_market_catalog (
    market_slug    VARCHAR PRIMARY KEY,      -- e.g. 'passyds'
    market_name    VARCHAR NOT NULL,         -- e.g. 'Pass Yards'
    category       VARCHAR NOT NULL,         -- td_scorer | passing | rushing | receiving | defense | kicking
    line_type      VARCHAR NOT NULL          -- 'over_under' (has a numeric line) | 'moneyline_only' (TD scorer props)
);

INSERT OR REPLACE INTO gold.nfl_prop_market_catalog VALUES
    ('firsttd',    'First TD',            'td_scorer', 'moneyline_only'),
    ('anytd',      'Anytime TD',          'td_scorer', 'moneyline_only'),
    ('lasttd',     'Last TD',             'td_scorer', 'moneyline_only'),
    ('twotd',      'Score 2+ TDs',        'td_scorer', 'moneyline_only'),
    ('threetd',    'Score 3+ TDs',        'td_scorer', 'moneyline_only'),
    ('comp',       'Completions',        'passing',   'over_under'),
    ('passatt',    'Pass Attempts',      'passing',   'over_under'),
    ('passyds',    'Pass Yards',         'passing',   'over_under'),
    ('passtd',     'Pass TDs',           'passing',   'over_under'),
    ('intsthrown', 'Ints Thrown',        'passing',   'over_under'),
    ('rushyds',    'Rush Yards',         'rushing',   'over_under'),
    ('longrush',   'Longest Rush',       'rushing',   'over_under'),
    ('recs',       'Receptions',         'receiving', 'over_under'),
    ('recyds',     'Rec Yards',          'receiving', 'over_under'),
    ('rushrec',    'Rush + Rec Yards',   'receiving', 'over_under'),
    ('tackle',     'Total Tackles',      'defense',   'over_under'),
    ('solo',       'Solo Tackles',       'defense',   'over_under'),
    ('assist',     'Assisted Tackles',   'defense',   'over_under'),
    ('sack',       'Sacks',              'defense',   'over_under'),
    ('kickpts',    'Kicking Points',     'kicking',   'over_under'),
    ('fgm',        'Field Goals Made',   'kicking',   'over_under'),
    ('xpm',        'Extra Points Made',  'kicking',   'over_under');

-- Scoped to the books the user actually wants tracked (draftkings, fanduel,
-- caesars). RotoWire's source page also carries betr, betrivers, fanatics, mgm,
-- hardrock, thescore, circasports -- omitted here by request, not by limitation.
-- bet365 was requested too but is NOT present on this source at all (confirmed
-- 2026-09-25); it would need a different data source if required later.
--
-- KNOWN TEAM-CODE VARIANCE: RotoWire uses 'LAR' for the LA Rams; our schedule
-- table (nflverse-sourced) uses 'LA'. Confirmed this causes is_pregame to be
-- NULL for that one team (no match found, not a wrong guess) rather than
-- silently mapping it incorrectly. Fix properly (a small team-code alias
-- table) if this team's line movement is needed; not blocking otherwise.
CREATE TABLE IF NOT EXISTS gold.nfl_prop_book_catalog (
    book_slug   VARCHAR PRIMARY KEY,        -- e.g. 'draftkings'
    book_name   VARCHAR NOT NULL            -- e.g. 'DraftKings'
);
INSERT OR REPLACE INTO gold.nfl_prop_book_catalog VALUES
    ('draftkings',   'DraftKings'),
    ('fanduel',      'FanDuel'),
    ('caesars',      'Caesars');

-- One row per player/game/book/market/pull. Append-only.
CREATE TABLE IF NOT EXISTS gold.nfl_prop_line_rotowire (
    pull_id            VARCHAR NOT NULL,     -- one id per script run (this snapshot)
    fetched_at_utc     TIMESTAMPTZ NOT NULL, -- TIMESTAMPTZ, not TIMESTAMP: a naive TIMESTAMP
                                              -- silently stored LOCAL time under a column
                                              -- literally named _utc (confirmed real bug,
                                              -- fixed here -- old rows before this fix are
                                              -- off by the host's UTC offset)
    game_id            VARCHAR,              -- rotowire gameID
    player_id          VARCHAR,              -- rotowire playerID
    player_name        VARCHAR,
    team               VARCHAR,
    opponent           VARCHAR,              -- as shown, e.g. '@MIA' or 'SEA' (home/away encoded)
    market_slug        VARCHAR NOT NULL,     -- FK -> nfl_prop_market_catalog
    book_slug          VARCHAR NOT NULL,     -- FK -> nfl_prop_book_catalog
    line               DOUBLE,               -- numeric line (NULL for moneyline-only TD props)
    over_price_american INTEGER,             -- NULL for TD scorer props (no over/under side)
    under_price_american INTEGER,
    moneyline_american  INTEGER,             -- for TD scorer props: the single moneyline (e.g. firsttd odds)
    is_pregame          BOOLEAN,             -- true if fetched before that game's kickoff;
                                              -- NULL if kickoff time unknown at load time.
                                              -- Required so movement analysis never mixes
                                              -- pre-game and live in-game lines (confirmed
                                              -- real contamination: a fake "recyds 60.5 ->
                                              -- 174.5" move was actually two in-game snapshots
                                              -- of a game already underway)
    source_name        VARCHAR NOT NULL DEFAULT 'rotowire',
    PRIMARY KEY (pull_id, player_id, game_id, market_slug, book_slug)
);

CREATE INDEX IF NOT EXISTS ix_propline_rw_lookup
    ON gold.nfl_prop_line_rotowire (player_id, market_slug, fetched_at_utc);
CREATE INDEX IF NOT EXISTS ix_propline_rw_game
    ON gold.nfl_prop_line_rotowire (game_id, market_slug);

-- Latest snapshot per player/market/book -- what you'd actually compare against
-- your own model right now, without re-deriving "most recent" every query.
CREATE OR REPLACE VIEW gold.v_nfl_prop_line_latest AS
SELECT p.*
FROM gold.nfl_prop_line_rotowire p
WHERE p.fetched_at_utc = (
    SELECT max(p2.fetched_at_utc)
    FROM gold.nfl_prop_line_rotowire p2
    WHERE p2.player_id = p.player_id
      AND p2.market_slug = p.market_slug
      AND p2.book_slug = p.book_slug
      AND p2.game_id = p.game_id
);

-- Best (highest) over price and best (highest) under price across books, per
-- player/market/game -- the actual best-price shopping view for placing a bet.
CREATE OR REPLACE VIEW gold.v_nfl_prop_best_price AS
SELECT game_id, player_id, ANY_VALUE(player_name) AS player_name, market_slug,
       max(line)                                        AS line,             -- lines mostly agree across books; max as a representative value
       max(over_price_american)                         AS best_over_price,
       arg_max(book_slug, over_price_american)           AS best_over_book,
       max(under_price_american)                        AS best_under_price,
       arg_max(book_slug, under_price_american)          AS best_under_book,
       max(moneyline_american)                          AS best_moneyline_price,
       arg_max(book_slug, moneyline_american)            AS best_moneyline_book,
       count(DISTINCT book_slug)                         AS num_books
FROM gold.v_nfl_prop_line_latest
GROUP BY game_id, player_id, market_slug;

-- Line movement: first-seen vs latest, per player/market/book. This is the CLV
-- input -- compare where your model fired to the closing number, not just today's.
--
-- PRE-GAME ONLY (is_pregame = true), on purpose. Confirmed real contamination
-- otherwise: comparing two in-game snapshots of a game already underway
-- produced a fake "Drake London recyds 60.5 -> 174.5" move -- that's live
-- re-pricing during the game, not pre-game market movement. Never compare
-- across that boundary.
CREATE OR REPLACE VIEW gold.v_nfl_prop_line_movement AS
SELECT player_id, ANY_VALUE(player_name) AS player_name, market_slug, book_slug,
       min(fetched_at_utc)                                  AS first_seen_at,
       max(fetched_at_utc)                                  AS last_seen_at,
       arg_min(line, fetched_at_utc)                         AS opening_line,
       arg_max(line, fetched_at_utc)                         AS current_line,
       arg_max(line, fetched_at_utc) - arg_min(line, fetched_at_utc) AS line_delta,
       count(DISTINCT fetched_at_utc)                       AS num_snapshots
FROM gold.nfl_prop_line_rotowire
WHERE line IS NOT NULL AND is_pregame = true
GROUP BY player_id, market_slug, book_slug
HAVING count(DISTINCT fetched_at_utc) > 1;

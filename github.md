repo: tyronne-os/frontal-lobe2
branch: claude/clever-cori-swkzal
path: frontend, backend

## Last sync
date: 2026-09-25 (this session, second pass)

### Second pass this session
- **JIMMY THE GREEK now has a real, lake-only scoring method** (`backend/jimmy.py`):
  a composite of hit-rate-vs-line, `usage_index_score` (the usage pond), and
  the opposing defense's `toxicity_index_0_100` (inverted -- tougher defense
  lowers the score), evenly weighted per the user's explicit choice, plus a
  redzone-share boost for TD props. This **replaces** the earlier
  hit-rate-only probability everywhere it's shown (parlay PROB badges) --
  per the user: "without an AI agent like Jev or cloud the lake is designed
  to return best possible outcomes -- it is the JIMMY THE GREEK node that
  checks the ponds and the lake to form a probability." Jev integration
  itself is still future work; this is the standalone-lake half of that.
  Exposed directly at `GET /api/jimmy_score?player_id=&market=` for
  transparency/debugging. HOT DOGS! is the one exception -- it's a
  team-vs-spread bet with no player usage/toxicity pond to run through
  Jimmy, so it stays on `team_ats_current`'s real cover rate.
- **Leaders tab gets a USAGE INDEX category** (`backend/leaders.py`,
  `frontend/src/components/LeadersTab.tsx`): ranks by `usage_index_score`
  from `player_usage.csv`, showing the lake's own `usage_role` label
  (e.g. "PRIMARY -- TRUSTED UNDER PRESSURE") per row instead of hiding this
  pond behind plain yardage totals.
- **Fixed the bar-chart scaling bug**: `PlayerTab.tsx` and `ChartsTab.tsx`
  computed their axis max purely from whatever games existed, so an early
  two-game sample stretched modest values to fill the whole chart height.
  Now uses a fixed per-market axis ceiling (rushyds 200, recyds 150,
  passyds 400, recs 12, anytd 3) that a real outlier can still exceed, plus
  10 reserved bar slots (matching "L10") so the chart doesn't re-stretch
  as the season fills in -- exactly the Props.Cash-style behavior the user
  asked for.

### First pass this session

### Updated in this session
- Brought the "Node design and canvas layout" handoff package into the repo
  at `frontend/design/` (was previously only in a separate Claude design
  project, unreachable from Code): `HANDOFF_CLAUDE_CODE.md`, the three
  `.dc.html` visual specs, and `assets/big-proppa.png`.
- New `backend/` (FastAPI): reads `lake/gold/nfl/*.csv` directly (does not
  depend on `lake/nfl.duckdb`, which is gitignored and not present in a
  fresh clone). Endpoints for player prop charts, leaders, the 4 parlay
  slips, team ATS heat map, and defense-vs-position rank bars.
- Rebuilt `frontend/src/App.tsx` (now split into `frontend/src/components/`)
  as the real HEY BIG PROPPA! Lake Canvas: data-driven React Flow nodes,
  resizable 40/60 split, 5 display tabs, admin panel, composer.
- New `/parlays` route (`frontend/src/pages/ParlaysPage.tsx`): the full
  ticket dashboard, wired to real legs/odds from the backend.
- `sql/nfl_parlay_probability_schema.sql`: documents the parlay-leg
  probability view (hit-rate-vs-line, HEURISTIC, not backtested) for when
  the lake is next rebuilt with DuckDB + network access. The backend
  currently computes the identical logic directly against the CSVs
  (`backend/data.py: hit_rate_probability`), since this container has
  neither `lake/nfl.duckdb` nor network access to rebuild it.

## Screen map
| Screen | Repo files |
|---|---|
| Lake Canvas.dc.html | frontend/src/App.tsx, frontend/src/components/*, frontend/src/AnimatedPulseEdge.tsx |
| Big Proppa Parlays.dc.html | frontend/src/pages/ParlaysPage.tsx |
| Big Proppa Logo.dc.html | frontend/src/components/SmokeBadge.tsx, frontend/src/theme.css (not a full logo-sheet page — no such route was in the handoff's chart map) |
| HANDOFF_CLAUDE_CODE.md chart source map | backend/data.py, backend/leaders.py, backend/parlays.py |

## Known gaps / decisions made this session (flagging honestly rather than silently working around)

1. **Player photos are not real in this deployment.** `lake/gold/nfl/player_photos/_index.csv`
   is real and tracked (1,301 rows, all `status: ok`, pointing at NFL.com/
   Cloudinary URLs), but the actual `*.png` files are gitignored and none
   exist in this container. `scripts/cache_player_photos.py` (the normal
   repopulation path) needs `lake/nfl.duckdb`, which also doesn't exist
   here. Direct network access to `static.www.nfl.com` was tested and is
   **blocked by this environment's network policy** (`CONNECT tunnel
   failed, 403`). Every player renders the initials-avatar fallback the
   design already specifies — never hotlinked, never fabricated.
2. **`assets/big-proppa.png` licensing blocker** (documented in
   `HANDOFF_CLAUDE_CODE.md` sec 1): derived from a Shutterstock preview.
   Fine for this private repo; do not ship publicly until the user
   licenses the full-resolution image or supplies his own.
3. **Probability model (parlay legs)**: superseded by the second pass above
   -- now JIMMY THE GREEK's composite (hit-rate + usage index + defense
   toxicity + redzone boost for TDs), not hit-rate alone. A leg still needs
   a real FanDuel price AND >=85% composite probability or it is dropped,
   never fabricated — TOP GUN and HOT BOYS commonly render empty this early
   in the season (2 games played) because the tougher, multi-signal bar is
   harder to clear on a thin sample than hit-rate alone was.
4. **Odds/pricing scope**: FanDuel only, per the user's explicit choice
   this session — not "best price across all books."
5. **Data quality note, not something this session altered**: player
   `00-0038134` (`Kenneth Walker III` per `player_photos/_index.csv`) is
   tagged team `KC` in `player_rushing_week.csv` for both played weeks,
   which doesn't match the real player (a Seahawks RB). This is upstream
   lake data (nflverse ID/team mismatch), passed through as-is per this
   project's own convention of never silently altering lake data —
   flagging here for whoever next touches the ingest scripts.
6. **Compute-source pill / mic / actual Jev API calls** are still
   `NOT WIRED`, exactly as `HANDOFF_CLAUDE_CODE.md` sec 3.9 / sec 7
   requires — no fake routing was added. `JEV_API_KEY` env var name is
   reserved for when that gets built. Jimmy's *lake-only* scoring (see
   second pass above) is real and live; only the "hand it to Jev for a
   refined read" half of Jimmy is still future work.
7. **Charts tab**: all 6 chart types from the handoff render from real
   data (heat map and DvP bars needed two new backend endpoints,
   `/api/chart/team_ats_heatmap` and `/api/chart/dvp`, since the lake
   doesn't export a per-game ATS cell grid — recomputed here from
   `schedule.csv` using the same methodology the lake's own ATS view
   uses, per `docs/HANDOFF.md` sec 5.2).

## How to run

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
echo "VITE_API_BASE=http://localhost:8000" > .env.local
npm run dev
```

## Sync history
- 2026-09-25T15:10:53Z — initial recreation of Lake Canvas from frontend/src/App.tsx (design project)
- 2026-09-25T16:51:21Z — HEY BIG PROPPA! branding + Lake Canvas + Parlays dashboard designs finalized (design project)
- 2026-09-25 (this session) — design package brought into repo, backend API built, frontend rebuilt against it, verified end-to-end in a browser

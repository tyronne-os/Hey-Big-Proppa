# HEY BIG PROPPA! — Design handoff to Claude Code

Written 2026-09-25 by Claude Design. This is the design source for `frontend/` in
`tyronne-os/frontal-lobe2`. Read `frontend/REACT_FLOW_CANVAS_HANDOFF.md` first; everything
in it still applies (§0a compute routing, §0b inline viewing, §5 do-not-change rules).
Where this doc and the user disagree, the user wins.

---

## 0. THE ONE NON-NEGOTIABLE: build every chart from the RAMP

**Every number, bar, line, row, and slip in these designs is placeholder.** The designs
fix *layout and behavior*. You must wire each chart to real data from the NFL ramp —
`lake/nfl.duckdb` (source of truth) and its itemized exports in `lake/gold/nfl/*.csv`.

Rules:
1. Read `lake/gold/nfl/_index.csv` first. Only render a chart whose source row has
   `status = ok`. For `stale | empty | error`, render the chart's empty state with the
   status label — never fall back to the placeholder values in the design files.
2. Query DuckDB (or the gold CSVs) through a backend endpoint — the browser does not open
   `nfl.duckdb` directly. Suggested: a thin API (`/api/chart/:chart_name?player_id=…`)
   that returns the shapes in §6.
3. Do not invent derived metrics silently. If a chart needs a metric that no gold object
   provides (see "probability score" in §4), build it as a named, documented view in the
   lake, export it through `scripts/export_ramp.py` with its own `_index.csv` row, and
   label it in the UI as a model output.
4. Player photos come from `lake/gold/nfl/player_photos/_index.csv` (player_id → local
   file). Fallback is the initials avatar already in the design; never hotlink.
5. Verify every column name below against the actual CSV header / DuckDB schema before
   using it — the mapping names the *source object*; column names are yours to confirm.

### Chart → RAMP source map

| UI element (file · tab) | Gold source(s) | Notes |
|---|---|---|
| Player bar chart, L5/L10 (Canvas · Player) | `player_rushing_week`, `player_receiving_week`, `player_passing_week`, `player_scrimmage_week` (by active prop chip) | One bar per game, newest right. Bar green if ≥ line, red if < line. |
| Betting line on that chart | `prop_best_price` (FanDuel price/line), fallback `prop_line_rotowire` | The gold animated line (§3.4). Show book name. |
| L10 AVG / HIT RATE / POS RANK tiles; H2H / L5 / L10 / L20 splits | same weekly tables + `schedule` (for H2H opponent) | Hit rate = games ≥ line ÷ games. Green ≥ 50%, red < 50%. |
| Player header (name, team, pos, opp) | `schedule`, weekly tables, `player_photos/_index` | Name renders in gold gradient. |
| Leaders · RUSHING / RECEIVING / PASSING | season aggregate of the matching `player_*_week` | #1 gets the hero card; ranks 2…N in the table; bar = value ÷ leader. |
| Leaders · SCORING | `player_scoring_week` | |
| Leaders · SACKS | `individual_sacks` | |
| Leaders · FIELD GOALS | `player_kicking_week` | |
| Leaders · DIVISIONS | `schedule` (derive W-L) , `team_week` | 1st seed green, last red. |
| Charts · Heat map (missed cover) | `team_ats_current`, `matchup_game_odds` | Red = missed cover, green = covered. |
| Charts · Radial hit rate | computed from weekly vs line | |
| Charts · Stacked comparison | over vs under counts per market | |
| Charts · Trend line | weekly stat series | |
| Charts · DvP bars | `defense_ib_score`, `pfr_adv_defense_week`, `matchup_toxicity` | Rank vs position. |
| Charts · Spark rows / Watchlist | weekly series for watch-listed players | |
| Parlays · HOT DOGS! (3 underdogs to cover) | `matchup_game_odds`, `team_ats_current` | Underdog spread; L5 = cover rate last 5. |
| Parlays · BEAST MODE (2 RBs, 2+ TD) | `anytime_td_scorers`, `td_log`, `redzone_tiers`, `player_usage` | |
| Parlays · HOT BOYS (receivers by targets) | `player_receiving_week`, `opportunity_spine`, `player_usage` | Targets are the WR/TE spine stat (docs/PLAYER_USAGE_INDEX.md). |
| Parlays · TOP GUN (QBs 250+ pass yds) | `player_passing_week` | |
| Parlay odds (all slips) | `prop_best_price` filtered to FanDuel | Default wager $5. |

---

## 1. Files in the design project

| File | What it is |
|---|---|
| `Lake Canvas.dc.html` | The main app: node canvas (left) + data display (right). |
| `Big Proppa Parlays.dc.html` | Full-page parlay poster dashboard. No nodes. |
| `Big Proppa Logo.dc.html` | Logo sheet: main badge, header lockup, app icons, palette. |
| `assets/big-proppa.png` | Mascot photo: watermark cropped, grayscale baked in, red cigar ember painted at (21.5%, 61%). |
| `github.md` | Repo association + screen map. |

Treat the `.dc.html` files as the visual spec; rebuild them as React components in
`frontend/src/` (they are not meant to be copied in).

**Licensing blocker:** `assets/big-proppa.png` is derived from a Shutterstock preview
(`uploads/hey-big-proppa.webp`). Do not ship it publicly until the user licenses the
full-resolution image or supplies his own.

---

## 2. Brand

- Name: **HEY BIG PROPPA!** — exactly one exclamation mark, everywhere. App-icon monogram: `HBP!`.
- Wordmark: Geist 900, one uniform old-gold gradient
  `linear-gradient(180deg,#f7e7a6 0%,#d9b45a 38–40%,#8a6224 52–55%,#c9a54e 70%,#f1dc92 100%)`
  clipped to text, with `drop-shadow(0 2px 0 #2a1a08)` on large sizes.
- Badge ring: gold + chrome conic gradient
  `conic-gradient(from 210deg,#6b4a1c,#c9a54e,#f4e4a8,#a07a2c,#e8e8ec,#8c8c94,#f6f6f8,#b48a3a,#6b4a1c)`.
- Type: Geist (UI) + Geist Mono (numbers, tags, odds) — Klarden UI design system.

### Palette (make these CSS variables; the design currently inlines them)

| Role | Value |
|---|---|
| Page / panel bg (dark) | `#0b0512` |
| Card (dark) | `#140a20` · border `#2a1e36` · muted text `#8a8290` |
| Canvas bg | `#120818` + orange glow `rgba(125,52,18,.38)` + purple glow `rgba(112,40,150,.38)` |
| Old gold | `#f1dc92` / `#d9b45a` / `#c9a54e` / `#8a6224` / `#6b4a1c` |
| Node orange (tags, pulse dot, dividers) | `#e0782f` / `#f08a3a` |
| **Green — hit / cover / positive** | `#2ee6a6` (text on green: `#06140e`) |
| **Red — miss / missed cover / heat** | `#ef4444` |
| Light theme | bg `#f6f3f8`, card `#ffffff`, border `#e2dce8` |

Dark is the default theme (unchanged from the original spec).

---

## 3. Lake Canvas (`frontend/src/App.tsx`)

### 3.1 Header (52px)
Badge (34px, smoke animation) · wordmark · spacer · compute-source pill · theme icon
(moon/sun, single toggle) · gear (admin panel). The pill and theme toggle moved **out of
the display panel into the header** at the user's request.

### 3.2 Split + resizable divider
Default 40/60. A 6px divider between panes drags left/right, clamped **22%–65%**; the
canvas re-fits on every change. Leaders (§3.7) hides the canvas entirely by default.

### 3.3 Node canvas (React Flow)
- **Data-driven nodes** — no hardcoded two-node layout. `nodes[]` of
  `{ id, type: 'lake' | 'expert', name, sub, chips?, x, y }`. Implement as one custom
  node type (`nodeTypes`) with a `type`-driven variant:
  - `lake` (RAMP): steel brushed-metal frame, orange `LAKE` tag, DATA mode, database
    icon, Store rows (`lake/nfl.duckdb`, "schema · ponds · not wired").
  - `expert` (harness, e.g. JIMMY THE GREEK): **gold** brushed-metal frame, violet
    `HARNESS` tag, EXEC mode, users icon, Experts chips (e.g. `Jev`), "harness · not wired".
  - Shared: 210px wide, gold 1.5px border, dark inner "screen" `#07050d`, orange rule,
    IDLE status, 4 footer icons, × remove button, handles top/bottom.
- **Edges** chain consecutive nodes (node[i] → node[i+1]), keep `AnimatedPulseEdge`:
  dashed `#cdaaba` stroke, orange dot `#f08a3a` + halo travelling 0→1→0 over 3s, and a
  `query` pill at the midpoint. Replace `PULSE_COLOR` with `#f08a3a`.
- Controls (zoom in/out/fit) + minimap at **bottom-right**. Fit view accounts for the
  controls cluster so nodes are never covered. No "NODE CANVAS" label.

### 3.4 The gold betting line (charts)
On player performance charts (L5/L10), the sportsbook line is a **solid** gold line
(`linear-gradient(90deg,#8a6224,#d9b45a 30%,#f1dc92 50%,#d9b45a 70%,#8a6224)`, 2px, soft
gold glow) with a gold ball (radial `#fff6d0→#f1dc92→#c9a54e→#8a6224`, 10px + 20px halo)
travelling end-to-end and back, 3s linear infinite — same motion as the node edge. Build
it as one reusable `<BettingLine value={line} max={axisMax} />` overlay.

### 3.5 Admin panel (gear)
Modal over the display panel with four strips:
1. **Nodes** — `Add RAMP`, `Add expert` (appends a node, chains an edge, re-fits).
2. **Charts** — catalog (Team Efficiency, Player Props, Matchup Report, Injury Report)
   with `+ Add`; added charts appear as chips on the Charts tab. Wire the catalog to
   `_index.csv` so it lists real exported charts.
3. **GPU / Compute priority** — same list as the header pill (§3.9).
4. **Logs** — session log (moved here; no longer on the canvas).

### 3.6 Display panel tabs
`Player · Leaders · Parlays · Charts · Queries` (pill tabs, top of the panel).

- **Player** — prop chips (Rush Yds, TD, Carries, Rush Lng, Rec Yds) · header card
  (photo, **gold name**, team · pos, opponent, `Add to slip`) · 4 tiles · bar chart with
  gold line (§3.4) · split pills. `Add to slip` pushes the current player+prop into
  **My Slip**; label flips to `In slip` (click opens Parlays).
- **Leaders** — §3.7.
- **Parlays** — banner linking to the dashboard (§4), **My Slip** card (user-built legs,
  removable, rough combined odds), example slips with HIT/MISS legs.
- **Charts** — six chart types: heat map (missed cover), radial hit rate, stacked
  comparison, trend line, DvP rank bars, spark rows. All need RAMP data (§0).
- **Queries** — the original echo cards from the composer.

### 3.7 Leaders page
Selecting Leaders **hides the node canvas** (full-width page); `Show nodes` / `Full view`
toggles it; other tabs restore the split. Category nav across the top (underline style,
wraps): RUSHING · RECEIVING · PASSING · SCORING · SACKS · FIELD GOALS · DIVISIONS.
Player categories: #1 hero card (gold border, gold name, big green stat) + ranked table
(RK, player, GP, stat, proportional green bar). **Clicking any row opens that player in
the Player tab.** DIVISIONS: grid of division cards with W-L.

### 3.8 Composer (bottom-center of the display panel, max 680px)
Textarea · mic (still inert, "not wired") · **target picker** (All nodes + every node on
the canvas; replaces the old Model button; Mode was removed as redundant with the tabs) ·
Clear (trash icon) · Send (Klarden `RichButton`, orange).
- Enter sends, Shift+Enter newline.
- **Clear**: the button, or sending the word `clear` (case-insensitive), wipes query
  results and added charts and shows `DISPLAY CLEAR`; the next real query restores views.
- The query counter shows only after the first query.
- Per §0a, **submitting a query is the trigger for the Hugging Face GPU availability
  check**.

### 3.9 Compute-source indicator (§0a of the original handoff — still NOT wired)
Pill: status dot · source name · state text · `NOT WIRED` tag. Four visual states:
`not wired` (grey), `connected` (teal), `retrying` (amber pulse, "retrying 2/3 · 4s"),
`awaiting confirmation` (orange pulse). Priority list: 1 Hugging Face GPU (default, no
confirm) → 2 My CPU (confirm) → 3 Google Cloud GPU (last resort, confirm). Picking a
fallback opens a confirm dialog; declining holds the query. Retry defaults 3 tries,
2/4/8s — adjustable. **Keep the `NOT WIRED` label until real routing exists.**

---

## 4. Big Proppa Parlays dashboard (new route, full page, no nodes)

- Left 20%: mascot with animated smoke (swap for a full-body image when supplied; the
  smoke anchor must be re-measured to the new cigar tip).
- Right 80%: header badge (smoking) + `TONIGHT'S SLIPS` / wordmark, WAGER chip,
  `FANDUEL ODDS` chip, back link to the canvas. 2×2 ticket grid:
  **HOT DOGS!** (3 underdogs to cover) · **BEAST MODE** (2 RBs, 2+ TD) · **HOT BOYS**
  (receivers by targets) · **TOP GUN** (QBs 250+ pass yds).
- Each leg: player photo (team badge for Hot Dogs) · name/team · prop · **L5 %**
  (green ≥80, white ≥60, red <60) · **PROB** badge (green) · FanDuel odds.
- **Only legs with probability ≥ 85% are shown** (filter server-side; the design filters
  client-side to demonstrate — one Top Gun leg at 81% is hidden).
- Tickets: perforated divider with side notches, `+50% PROFIT BOOST` badge, ticket id
  (`HBP-W04-001`), `$5 WAGER`, original payout struck through, boosted payout in gold.

### Odds math (implement exactly)
```
dec(american) = american > 0 ? 1 + american/100 : 1 + 100/|american|
D             = Π dec(leg.odds)                  // combined decimal odds
payout        = wager × D
boostedPayout = wager + wager × (D − 1) × (1 + boost)   // boost = 0.50
boostedOdds   = toAmerican(1 + (D − 1) × (1 + boost))
wager default = $5
```
The boost is a fictitious display promotion for now — label it as such if it ever
reaches real users.

### Probability score — does not exist yet
No gold object produces a leg "probability". Build it as a documented model view
(inputs e.g. hit rate vs line, `player_usage` confidence delta, `matchup_toxicity`,
`redzone_tiers`), export it with its own `_index.csv` row, and label it as a model output.
Do not display a probability that isn't computed.

---

## 5. Logo & smoke animation

- Photo: `assets/big-proppa.png`; cigar tip anchor **left 21.5%, top 61%** of the
  image box (image aspect 260:256). Badges wrap image + smoke in one element scaled
  `1.18–1.25` from origin `50% 38%` so the anchor stays aligned.
- Smoke layer is sized in `em`; set `font-size` per badge size (≈ badge px ÷ 40).
- One **3.6s "drag" cycle**: `bpEmber` (red glow flares to 1.8× at 6%, settles by 40%)
  + `bpCore` (hot yellow core flash), then five puffs (`bpPuffA/B/C`, delays
  0.25/0.4/0.55/0.75/0.95s) rise ~16em, drift, scale to ~3×, fade. Three slow wisps
  (`bpWisp`, 6s, delays 0/2/4s) keep drifting between drags. All keyframes are in the
  `<style>` of each `.dc.html` — port them as-is. Respect `prefers-reduced-motion`
  (freeze on the glowing ember, hide puffs).
- Smoke appears on: logo badge, header lockups (logo sheet, canvas header, parlay
  header), both app icons, the parlay mascot.

---

## 6. Suggested data shapes

```ts
type NodeType = 'lake' | 'expert';
interface CanvasNode { id: string; type: NodeType; name: string; sub: string; chips?: string[]; }

interface GameBar { gameDate: string; opponent: string; value: number; }          // one per game
interface PlayerPropChart {
  playerId: string; name: string; team: string; pos: string; photoUrl?: string;
  prop: string; line: number; book: 'FanDuel' | string;
  games: GameBar[];                                    // L5 / L10 / L20 windows sliced client-side
  splits: { label: 'H2H' | 'L5' | 'L10' | 'L20'; hitRate: number | null }[];
  sourceStatus: 'ok' | 'stale' | 'empty' | 'error';    // from _index.csv
}
interface LeaderRow { rank: number; playerId: string; name: string; team: string; gp: number; value: number; }
interface ParlayLeg { playerId?: string; teamId?: string; name: string; prop: string;
  l5: number; probability: number; odds: number; photoUrl?: string; }
interface ParlaySlip { id: string; title: 'HOT DOGS!' | 'BEAST MODE' | 'HOT BOYS' | 'TOP GUN';
  legs: ParlayLeg[]; wager: number; boost: number; }
```

---

## 7. Do not change without asking the user
- Left = nodes, right = data. Dark is the default. Composer is bottom-center of the right panel.
- The node names and what they mean (RAMP NFL = Phase 1 lake; JIMMY THE GREEK = the expert harness).
- `NOT WIRED` labels stay until the thing is actually wired (compute routing, mic).
- Green = hit/cover, red = miss/missed cover. Gold = brand, lines and headings.
- One exclamation mark in the name.

## 8. Open questions for the user
1. What should the mic do (voice-to-text into the composer?)?
2. Full-body mascot image and photo licensing.
3. How the probability score should be weighted (§4).
4. Whether FanDuel is the only book, or best price across books with FanDuel as default.
5. Inline viewing (§0b of the original handoff) — still unresolved for the React build.

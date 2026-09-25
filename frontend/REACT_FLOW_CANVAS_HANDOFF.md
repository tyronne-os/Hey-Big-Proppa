# React Flow Canvas — handoff to Claude Design

Written 2026-09-25 by the agent that built the structural scaffold. **Read
this before touching `src/App.tsx`.** The user could not upload a reference
image for this screen (repeated upload failures), so everything below was
built from his written description alone, in one message. Treat the current
code as **structure and wiring proof, not final visual design** — that's
explicitly your job next.

If anything here conflicts with what the user tells you directly, the user's
live instructions win. This document is a snapshot of intent as of the date
above, not a spec that overrides him.

---

## 0a. COMPUTE SOURCE — the lake must be GPU-powered via Hugging Face Pro,
##     with a defined fallback chain and a visible source indicator

The user's own words, verbatim, because the exact wording matters for a
requirement like this:

> i do want you to make sure this lake is powered by my free gpu provided
> through my hugging face pro and if there is a time it is not available
> then the upper right is a gpu source display which can be hugging face -
> my cpu (i have unused slot with gb of storage waiting) or a gpu from my
> google cloud last resort. each option there is a confirmation question if
> i want to choose my cpu or gpu but hugging face free is the default unless
> it is not available and my system retries when it is not. what trigger the
> default is when i enter a query

**This is a real infrastructure requirement, not a UI cosmetic.** It affects
where and how any actual compute (Jimmy's scoring, Jev calls, any future
model inference) gets executed, not just what a badge says. Do not treat this
as "just add a dropdown" — the dropdown is the visible tip of a real backend
routing decision that has to exist and actually check availability.

### The priority chain, exactly as specified — do not reorder
1. **Hugging Face Pro's free GPU** (his own account/Space allocation) — the
   default, tried first, every time.
2. **The user's own CPU** — explicitly described as "unused slot with GB of
   storage waiting." His own machine, not a cloud CPU tier.
3. **Google Cloud GPU** — explicitly "last resort." Only reached if both of
   the above are unavailable/declined.

### The trigger
The availability check happens **when the user submits a query in the
composer** — not on page load, not on a timer, not speculatively in the
background. Every query submission is the moment the system asks "is Hugging
Face's free GPU available right now?" This is explicit ("what trigger the
default is when i enter a query") — don't move this check to a different
lifecycle point for engineering convenience.

### Retry behavior
The user said his system "retries when it is not [available]" — confirming a
retry exists, but not specifying its exact shape. **The following retry
parameters are this agent's judgment call, not a user-specified requirement
— revisit with the user if he pushes back, but proceed with these as a
sensible default rather than leaving the behavior unspecified:**
- 3 attempts against Hugging Face before falling back, exponential backoff
  (roughly 2s / 4s / 8s), ~15s total budget. Chosen to survive a typical
  Hugging Face Space cold-start without making the user wait indefinitely on
  every single query.
- Treat ANY of the following as "not available" for the purpose of
  triggering a retry: an explicit error/failure response, a timeout past the
  attempt's backoff window, or an explicit queue-full/rate-limit response.
  All three collapse into one `unavailable` signal — the UI does not need to
  distinguish *why* HF wasn't available, only whether it's still trying or
  has given up.
- After the retry budget is exhausted, fall back to asking the user (see
  confirmation requirement below) rather than silently switching to CPU.

**These specific numbers (3 attempts, 2/4/8s, ~15s) are a placeholder for a
real decision the user should confirm or override** — implement them, but
flag in the UI or in a code comment that they're adjustable, not hardcoded
gospel.

### The UI requirement
- **Upper right of the display panel** (not the node canvas side) shows the
  current/active compute source at all times — this is a persistent status
  indicator, not something that only appears during a switch.
- Three states the indicator needs to visually distinguish: **connected**
  (showing which of the 3 sources is active), **retrying** (Hugging Face
  specifically, mid-backoff — the user should be able to tell the system is
  still trying HF, not stuck or already failed over), and **awaiting
  confirmation** (a fallback is available and the user needs to approve it).
- **Every fallback option requires an explicit confirmation question before
  switching** — CPU and Google Cloud both require the user to affirmatively
  say yes before a query actually runs on them. Hugging Face, as the default,
  does NOT require confirmation when it's the one being used (asking to
  confirm the default every single query would defeat the point of having a
  default).
- If the user declines a fallback option's confirmation, the system needs a
  defined behavior (this agent's judgment: hold the query, let the user
  retry Hugging Face manually or pick a different fallback — do not silently
  drop the query or silently pick a fallback the user just declined).

### What does NOT exist yet — be clear about this with the user
No backend compute-routing logic exists in this repo as of this handoff.
There is no code anywhere that actually calls Hugging Face's inference API,
checks GPU availability, or executes anything on a CPU/Google Cloud target.
This section describes a requirement for something that needs to be
designed and built, not something already working that just needs a UI
wrapped around it. Do not present a compute-source indicator in the UI that
implies real routing is happening underneath it until that routing actually
exists — a fake/static indicator would misrepresent the system's real state
to the user, which this project's other conventions (see `docs/HANDOFF.md`
§7, lesson 9 on labeling heuristics honestly) explicitly guard against.

---

## 0b. VIEWING CONSTRAINT — read this too, it changes how you ship this

The user does not want to leave the chat surface and open a separate browser
tab to see this canvas. He wants to view it **inline, in the same space he is
chatting in** ("built within the artifact... meaning I don't have [to] leave
the chat space to open a browser tab").

This is a real architectural constraint, not a preference to defer. The
current `frontend/` app is a Vite dev server serving a real React + React
Flow bundle — that requires a running process and a browser tab/iframe
pointed at a port, which is exactly what the user said he does not want.

**This was explicitly left for you to solve** (the agent who built the
scaffold raised building a parallel static-HTML artifact version, and the
user said "we will allow claude to sort that out" instead). Do not assume the
answer is "just embed an iframe pointing at the dev server" without checking
whether that satisfies the actual constraint (it still requires a server
running somewhere) — figure out what rendering surface the user's environment
actually supports for inline viewing, and build to that. Ask him directly if
it's unclear what counts as "inline" in his environment before guessing.

Whatever you land on, the `frontend/` React + React Flow app described below
should remain the source of truth for the design/logic — don't fork into two
permanently-diverging implementations (one real app, one inline-viewable
toy) unless that turns out to be the only way to satisfy the constraint, and
if so, document clearly which one is authoritative going forward.

---

## 1. What the user actually asked for (his words, condensed)

> a react flow canvas that is a dual playground or dual sandbox style —
> left side is the node, right side is the data display visualize... within
> right side appear the results of queried data... the queried data appear
> in all forms with player photos (see those images I presented earlier of
> the Props.Cash design)... bottom center of the right side is where I can
> enter queries between these nodes is a chat composer exactly like the one
> I am typing in now and with the same icon for tools like mic and model and
> mode etc... the results of the query in the composer allow me to instantly
> examine the visualize displays on the right... the display area on the
> right come in two modes — 1. Dark 2. white with the dark being default

And, on the two nodes already built (from the prior turn, unchanged in
substance):

> NODE 1 = RAMP NFL
> NODE 2 = JIMMY THE GREEK (JEV & HARNESS TO ADD ADDITION EXPERTS)

## 2. The layout, as built

```
┌───────────────────────┬──────────────────────────────────────────┐
│                       │  [theme: Dark/White]   [GPU: Hugging Face▾]│  ← upper-right,
│   ┌──────────┐        │  ┌────────┐ ┌────────┐ ┌────────┐          │    see §0a
│   │  NODE 1  │        │  │ result │ │ result │ │ result │  ← grid  │
│   │  NODE 1  │        │  │ result │ │ result │ │ result │  ← grid  │
│   │ RAMP NFL │        │  │  card  │ │  card  │ │  card  │    of    │
│   └────┬─────┘        │  └────────┘ └────────┘ └────────┘  result  │
│        │              │                                     cards  │
│        ▼              │                                            │
│   ┌──────────┐        │                                            │
│   │  NODE 2  │        │                                            │
│   │  JIMMY   │        │                                            │
│   │THE GREEK │        │                                            │
│   └──────────┘        │                                            │
│                       │  ┌──────────────────────────────────────┐  │
│   [React Flow         │  │ 🎤 ⚙︎ ⋮   [ chat composer input ] [Send]│  │
│    canvas: pan/zoom/  │  └──────────────────────────────────────┘  │
│    minimap controls]  │            ↑ bottom-center of RIGHT side   │
└───────────────────────┴──────────────────────────────────────────┘
     LEFT ~40% width               RIGHT ~60% width
```

- **Left panel** — a real `<ReactFlow>` canvas (pan/zoom/minimap controls
  already wired via the `Controls` component). Two nodes, one directed edge
  (`ramp-nfl -> jimmy-the-greek`), default ReactFlow node rendering with
  inline `style` for size only — no custom node component yet.
- **Right panel** — vertically split into: a theme-toggle row (top), a
  scrollable CSS-grid of result cards (middle, this is the bulk of the
  space), and the chat composer (bottom, horizontally centered, not full
  width — the user said "bottom center," not "bottom full-width").
- **Theme** — a `theme` state (`"dark" | "light"`), default `"dark"`, toggled
  by a single button. Currently implemented as inline hex colors on a few
  container divs. **This is the single biggest thing to properly systematize**
  — see §4.

## 3. What's real vs. what's a placeholder

**Real / functionally wired:**
- The React Flow canvas renders both nodes and the edge between them.
- The composer captures text, and pressing Enter (without Shift) or clicking
  Send appends a new result card to the top of the right-side grid and clears
  the input. This proves the round-trip (composer → display panel) works.
- Theme toggle actually swaps the color scheme live, dark is the default on
  load.
- A running `history` array counts how many queries were submitted this
  session (shown as a small counter under the composer).

**NOT real — do not treat any of this as connected to actual data:**
- There is **no backend call**. Submitting a query does not touch
  `lake/nfl.duckdb`, does not call Jev, does not call anything. It echoes the
  typed text back into a card. Search `App.tsx` for `handleSubmitQuery` —
  the comment right above it says this explicitly.
- Player photos, real stat values, and the "Props.Cash"-style visual density
  the user referenced do not exist yet. `QueryResultCard.photoUrl` is a real
  field in the type and the img tag is wired to render it *if present* — but
  no query currently produces one.
- The mic/model/mode icons in the composer are inert emoji buttons with a
  `title` tooltip saying "(not wired)". They do nothing on click. The user
  wants them to look and behave like this chat interface's own composer
  icons — that requires knowing what those icons actually do in this
  environment (voice input? model switcher? conversation mode?), which was
  not specified in enough detail to implement correctly rather than guessed.
  **Ask the user what each icon should actually trigger before wiring
  behavior — do not guess and ship a wrong affordance.**

## 4. Concrete design tasks for Claude Design

Roughly in the order they'll matter most:

1. **Node visuals.** Currently default ReactFlow rectangles with plain text
   labels (`\n`-joined multi-line strings, which is a crude stand-in for
   real multi-line node content). The user has referenced wanting these to
   look deliberate/branded eventually ("we will make it pretty later," said
   twice across two sessions) — this is "later." A custom node type
   (`nodeTypes` prop on `<ReactFlow>`) is the right mechanism; don't keep
   forcing multi-line labels through the default node.
2. **Result card design**, modeled on the "Props.Cash" reference the user
   described but could not upload. Ask him to describe it verbally in detail
   (layout, information density, what a single player card shows, color
   coding for over/under, etc.) since the image itself never made it into
   this session. The current `QueryResultCard` shape (`title`, `subtitle`,
   `photoUrl`, `stats[]`, `raw`) is a first guess at what fields a real
   query result needs — validate it against an actual query result once
   Phase 2's Jimmy-the-Greek scoring exists, and change the shape if the
   real data doesn't fit it. Don't force real data into a wrong shape just
   because this shape shipped first.
3. **Theme system.** Replace the inline hex-color approach with a real
   design-token/CSS-variable system (or whatever this project's existing
   convention is, if one exists elsewhere — check before introducing a new
   one). Dark must remain the default per explicit instruction.
4. **Composer parity with the current chat UI.** The user was explicit that
   this composer should look and function like the one he's typing into in
   this very conversation, "with the same icon for tools like mic and model
   and mode etc." That means: figure out what icon set and behavior this
   environment's own composer actually has, and replicate the *affordances*
   (not just the icons) — mic likely means voice-to-text, model likely means
   a model picker, mode likely means something like autopilot/supervised or
   similar. Confirm with the user rather than assume.
5. **Additional "expert" nodes.** Node 2 is explicitly named to leave room
   for growth: `"JIMMY THE GREEK (Jev & harness to add addition experts)"`.
   When more nodes are added (Jev as its own node? BIG PROPPA in Phase 3?),
   the canvas layout, edge routing, and result-card system all need to keep
   working with an arbitrary, growing node count — don't hardcode assumptions
   that only work for exactly two nodes.
6. **Responsiveness.** The current 40/60 split is a fixed percentage with no
   responsive behavior below a certain viewport width. Not addressed at all
   yet.

## 5. Things NOT to change without asking

- **The 40/60 (canvas/display) split direction** — left is nodes, right is
  data. This was explicit and specific in the user's own words; don't flip it
  even if a different layout seems cleaner.
- **Dark as the default theme.** Explicit, stated as item "1. Dark 2. White
  with the dark being default."
- **Composer position** — bottom **center** of the right panel, not full
  width, not attached to the left panel, not floating over the canvas.
- **The node names and their meaning** — `RAMP NFL` is Phase 1 (the whole
  lake: schema, ponds, everything in `docs/HANDOFF.md`). `JIMMY THE GREEK` is
  explicitly described as "Jev & harness to add additional experts" — it is
  not just "Jimmy," it's the harness node that Jev runs inside of, with room
  designed in from day one for more expert nodes to join it later. Don't
  rename or re-scope either node without the user's sign-off — see
  `docs/HANDOFF.md` §5.6–5.7 and the chat history around "Hermes" for the
  full reasoning behind why Jimmy is a harness, not a single model call.

## 6. Where to find everything else

- `docs/HANDOFF.md` at the repo root — the full Phase 1 recovery document.
  Read this to understand what RAMP NFL (Node 1) actually contains before
  designing what a query result from it should look like.
- `.kiro/steering/project.md` — the running, dated log of every decision made
  in this project. More granular than `HANDOFF.md`, always loaded into
  context automatically for whichever agent is working in this repo.
- The naming rule in `docs/HANDOFF.md` §4 applies here too: no internal
  family shorthand in anything committed to this repo. "RAMP NFL" and "JIMMY
  THE GREEK" are the user's own chosen public names for these nodes, already
  cleared for use.

## 7. How to run this

```bash
cd frontend
npm install      # only needed once, or after a dependency change
npm run dev       # starts a local dev server; use control_bash_process /
                   # start it as a background process, don't block on it
npm run build     # production build check -- must pass with zero
                   # TypeScript errors before considering a change done
```

Verified as of this handoff: `npm install` clean, `npm run build` succeeds
with zero TypeScript errors, and the dev server was manually started once and
confirmed to render both nodes and the split-panel layout before being
stopped again (nothing was left running).

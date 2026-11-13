# MONEY BALL — Automated Podcast Master Plan

> **Vision.** A page called **MONEY BALL** that is pure information, but plays like a
> **podcast with real voice** (NotebookLM-style). The show **writes itself** from the
> data — the players, the props, and the defenses they face drive everything. The cast
> is **MY BOO** and **BIG PROPPA** (with JIMMY + JEV as guest voices). Lots of laughs,
> big talk about parlay payouts, and building the perfect parlay from the players on
> the board.
>
> **Goal:** an automated, genuinely good sports-betting show that bettors want to hear,
> generated fresh every day from the same Rotowire + bet-logic + thesis pipeline.

---

## 0. Why this works (and is automated)

The podcast has **no scriptwriter** — the data *is* the script. Everything the cast says
comes from the API pipeline already built:

| Data | Source | Feeds the show's… |
|------|--------|-------------------|
| Today's 15/10 matchups | `bet_logic.bet_hunt()` | "Tonight's spots" segment |
| The domination players | `day_picks.day_picks()` | "Who's about to get paid" |
| Prop lines + best price | `rotowire_api.board()` / `board()` | "The board" segment |
| The perfect parlay | `leg_builder.buildable()` / `correlated_parlay` | "The Money Ball" segment |
| Big payouts | `leg_builder` joint-prob → decimal odds | "What it pays" segment |
| The storylines | `bet_logic._living()` (winning records) | "Something to live for" |
| The player's full read | `h2h.analyze()` / `jimmy_take` | "The deep dive" |

**Because the data drives it, the show literally writes itself.** The cast's *personas*
provide the spice; the data provides the substance.

---

## 1. The Cast (personas)

### MY BOO — the host / ringleader
- Warm, funny, high-energy. Keeps the show moving.
- Voice: playful, a little chaotic, loves the big number. The "friend at the bar who's
  got the inside info."
- Leans on **JEV** (the projection read) for the "trust me" moment.

### BIG PROPPA — the analyst / the money brain
- The parlay engine personified. Cold, sharp, data-first.
- Voice: confident, dry humor, never hedges. "The line is the line."
- Leans on **JIMMY** (bold voice) for the brutal truth and **the thesis** for the edge.

### Guest voices (optional, spice)
- **JIMMY THE GREEK** — the bombastic, bold, "neck on the line" hot-take machine.
- **JEV** — the quiet projection model that always says "here's the real number."

---

## 2. The Show Structure (auto-generated, ~4-6 min)

Each episode has fixed beats, each fed by a data call:

**1. COLD OPEN (MY BOO)** — "What are we playing tonight?" 
   → `bet_logic.bet_hunt()` (15/10 matchups + weak defenses)

**2. THE SPOTS (BIG PROPPA)** — "Here's the edge."
   → `day_picks.day_picks()` (the domination players + WHY)

**3. THE BOARD (BIG PROPPA)** — "Here's the board, here's the price."
   → `rotowire_api.board()` (players, lines, best price per book)

**4. THE MONEY BALL (MY BOO + BIG PROPPA)** — "Let's build the perfect parlay."
   → `leg_builder.buildable()` + `correlated_parlay.top()` (the 2-leg tickets + joint prob)
   → Compute the payout from the odds ("$5 → $167"). **This is the pay-talk beat.**

**5. THE LAUGHS / BANTER** — MY BOO ribs BIG PROPPA about the brutal beats, BIG PROPPA
   deadpans back. Template one-liners keyed to the data (e.g., "the Giants were in the
   red zone twice and got ZERO — that's why we take the UNDER, baby").

**6. THE CLOSE (MY BOO)** — "Something to live for." 
   → `bet_logic._living()` (the winning-record teams / storylines) → "We ride with winners."

---

## 3. The Voice / TTS Engine (NotebookLM-style)

Two viable paths. **Both are "real voice" — the difference is cost vs. control.**

### Path A — ElevenLabs (best quality, pay-per-use) ✅ recommended
- **Endpoint:** `/v1/text-to-speech/{voice_id}` with `model_id=eleven_multilingual_v2`.
- **Two cloned voices:** MY BOO (host) + BIG PROPPA (analyst). Clone from 30s samples
  (or use stock voices that match the personas).
- **Input:** the generated script per segment. Split by speaker, call TTS per line,
  then **concatenate** the audio (with tiny gaps).
- **Output:** an MP3/stream that the MONEY BALL page `<audio>` plays.

### Path B — Edge-TTS / Coqui (free, on-prem)
- **Microsoft Edge TTS** (`edge-tts`) gives natural neural voices free, no API key.
  `edge-tts --voice en-US-ChristopherNeural --text "..." --write-media out.mp3`.
- Pick two distinct voices for the two personas. Good enough, zero cost, runs in the
  Space (CPU basic).
- **Note:** Coqui needs a model download (~2GB) — too heavy for CPU-basic; Edge-TTS
  is the right free choice.

### The pipeline (write → speak → stitch)
```
script = generate_show()               # pure text, persona-tagged
audio = []
for line in script:
    if line.speaker == "MY BOO": voice = BOO_VOICE
    elif line.speaker == "BIG PROPPA": voice = BP_VOICE
    audio.append(tts(line.text, voice))
stream = concat(audio)                 # add 200-400ms gaps between turns
save/stream → GET /api/moneyball/audio
```

---

## 4. The "Show Writes Itself" generator

`backend/moneyball.py` — a pure-text script generator. It has **no hardcoded sports
opinions**; every line is a template filled from the data.

```python
def generate_show() -> list[Line]:
    spots  = day_picks.day_picks()          # 15/10 matchups + domination players
    board  = rotowire_api.board()           # props, lines, prices
    slips  = leg_builder.buildable(0.15)    # the perfect parlays
    living = bet_logic._living_teams()      # storylines

    lines = []
    lines.append(Line("MY BOO", f"Money Ball, baby. We got {n} spots tonight and the
                       {weak} defense can't stop a soul — {offense} is about to feast."))
    for pick in spots["picks"][:3]:
        lines.append(Line("BIG PROPPA", f"{pick['name']} is {pick['why']}."))
        lines.append(Line("MY BOO", f"And that's a {pick['seasonAvg']}-a-game kind of night.
                           Pass the parlay slip."))
    # the Money Ball segment
    top = slips["rows"][0]
    lines.append(Line("BIG PROPPA", f"Two legs. {top['legA']['label']} + {top['legB']['label']}.
                       {top['jointP']:.0%} joint. That's the edge."))
    lines.append(Line("MY BOO", f"On a five, that pays {money(payout)}. THAT is the Money Ball."))
    ...
    return lines
```

**The "laughs" come from personality templates** — a bank of MY BOO's quips and BIG
PROPPA's deadpans, chosen by data conditions (e.g., a team that was red-zone-0 picks the
"that's why we take the UNDER" quip). Never hardcoded results, always data-triggered.

---

## 5. The MONEY BALL Page (frontend)

- **Route:** `/moneyball`
- **Layout:** a big player/audio card. Title = the episode (auto: "Money Ball — Week X,
  {date}"). A **play button** streams `GET /api/moneyball/audio`.
- **Below the player:** the **show transcript** (the generated script, persona-tagged,
  MY BOO gold / BIG PROPPA violet). Scrolling transcript that highlights as audio plays.
- **Side panels:** the board (from `/api/rotowire`), the day-picks, the Money Ball slip.
- **Controls:** regenerate, pick a market, "Tonight's spots" filter.

---

## 6. API Surface

| Endpoint | Purpose |
|----------|---------|
| `POST /api/moneyball/generate` | Run `moneyball.generate_show()` → return the script (text) |
| `GET /api/moneyball/script` | The latest script (JSON, persona-tagged) |
| `GET /api/moneyball/audio` | The synthesized podcast (MP3 stream) — generates on demand, caches |
| `GET /api/moneyball/transcript` | The same script, text form for the page |

---

## 7. Build Order (phased, each testable)

1. **Phase 1 — The writer (pure text).** `moneyball.generate_show()` returns a persona-
   tagged script from the data. Testable instantly, no TTS needed. *This is the core.*
2. **Phase 2 — The TTS.** Wire Edge-TTS (free) for two voices → `GET /api/moneyball/audio`.
   Verifiable: it speaks.
3. **Phase 3 — The page.** `/moneyball` with the audio player + live transcript + board.
4. **Phase 4 — Personality tuning.** Expand the quip bank, tighten pacing, add the JIMMY/JEV
   guest beats. Make it genuinely funny and sharp.
5. **Phase 5 — The Money Ball bump.** Bake the **15/10 +6 bump** into the payout talk so the
   show says exactly what the model is pricing.

---

## 8. Cost / Feasibility

- **Edge-TTS:** free, runs on CPU-basic, no API key. **Recommended first build.**
- **ElevenLabs:** ~$5-22/mo (Creator tier) for real cloned voices, higher quality.
  Worth it once Phase 1-3 prove the show is good.
- **Compute:** a 4-6 min episode = ~30-60 TTS calls. Edge-TTS is fast; cache the audio
  per day so it's generated once, not every play.
- **Storage:** one MP3/day is tiny. Store in `lake/gold/nfl/moneyball/`.

---

## 9. Why this is "really fucking good" (the pitch)

- **It's honest.** The show only ever talks about real players, real lines, real defense
  tiers, real payouts — from the same pipeline that prices the bets.
- **It writes itself.** New slate = new episode, zero manual work.
- **It has personality.** MY BOO and BIG PROPPA are *personas*, not just TTS voices — the
  humor and banter are template-driven but data-triggered, so it never feels canned.
- **It builds the perfect parlay on air.** The Money Ball segment literally assembles the
  2-leg ticket from `leg_builder`, states the joint probability, and announces the payout.
- **Bettors will actually listen.** It's the edge, explained by characters, in your ear.

# MONEY BALL — Open-Source NotebookLLM Deep-Dive & Build-Your-Own Plan

> **Question answered (11-12-2026):** Is there a truly open-source NotebookLM that engineers
> love, with **no API subscription**, so we get the podcast's "consciousness" for free?
>
> **Answer: YES — `lfnovo/open-notebook`.** 41.9k stars, MIT, 100% self-hostable, **1-4 speakers
> with custom profiles**, full REST API, and it plugs into **any OpenAI-compatible TTS** —
> including your **NVIDIA Kokoro free endpoint**. That's the whole thing, zero subscriptions.

---

## 1. The winner: `lfnovo/open-notebook`

| Attribute | Value |
|-----------|-------|
| **Stars / Forks** | 41.9k / 4.8k — the engineers' favorite |
| **License** | MIT (free, commercial use OK) |
| **Stack** | Python + FastAPI + Next.js/React + SurrealDB + LangChain |
| **Deploy** | Docker (2 services: `surrealdb` + `open_notebook`), or from source |
| **Podcast** | **1-4 speakers**, custom speaker profiles, Episode Profiles, per-speaker TTS override |
| **API** | Full REST API (port 5055) — automate everything |
| **Local** | 100% local with Ollama (LLM) + a local TTS server — nothing leaves the machine |

### Why it's the one
- **It's the NotebookLM clone, but better.** More speakers (1-4 vs Google's 2), custom
  speaker profiles (name + Voice ID + backstory + personality), custom episode briefings,
  and a real API (Google's has none).
- **No vendor lock-in.** 20+ providers, and crucially an **OpenAI-Compatible** provider slot —
  that's exactly where your **NVIDIA Kokoro endpoint** goes.
- **Podcast "consciousness" with zero cost.** Use **Ollama** (local LLM for outline + transcript)
  + **Kokoro** (local TTS) = fully free, fully local. Or use your free NVIDIA Kokoro endpoint
  for the voice and a free LLM for the script.

### How it generates the show (the "consciousness")
```
Selected content (your Money Ball sources)
   │
1. OUTLINE      outline model + briefing → a plan with N segments
   │
2. TRANSCRIPT   transcript model writes the dialogue, segment by segment,
   │            using the speakers' names, backstories, personalities
   ▼
3. AUDIO        each line voiced with its speaker's voice model + Voice ID,
                then joined into one audio file
```

**This is exactly our Money Ball show.** MY BOO + BIG PROPPA are **speaker profiles**
(name + Voice ID + backstory + personality). The **content** = your live data pipeline
(`day_picks` + `rotowire_api` + `leg_builder` + `bet_logic`). The **briefing** = the show
structure (spots → board → money ball → banter). The show writes itself.

---

## 2. The TTS: your NVIDIA Kokoro free endpoint

**No ElevenLabs, no subscription.** Open Notebook's **OpenAI-Compatible provider** accepts any
TTS server that speaks the OpenAI `/audio/speech` API. Your **NVIDIA Kokoro free endpoint**
is exactly that.

```
POST https://integrate.api.nvidia.com/v1/audio/speech
  Authorization: Bearer <NVIDIA_API_KEY>
  json: { model: <kokoro>, input: text, voice: <voice>, response_format: "mp3" }
```

### Two-voice set for the cast
- **MY BOO** — warm, playful host
- **BIG PROPPA** — confident, dry analyst

Pick two distinct Kokoro voices; set them as each speaker's **Voice ID**. (Open Notebook even
supports a **per-speaker TTS override** so each host can come from a different TTS provider.)

---

## 3. The fully-free stack (no API subs at all)

| Layer | Tool | Cost |
|-------|------|------|
| **Script (LLM)** | Ollama (local, e.g. Llama/Qwen) or your free NVIDIA LLM endpoint | $0 |
| **Voice (TTS)** | **Kokoro** via NVIDIA free endpoint, or local Kokoro/speaches | $0 |
| **Orchestrator** | `lfnovo/open-notebook` (MIT, self-hosted) | $0 |
| **Data** | our `day_picks` / `rotowire_api` / `leg_builder` pipeline | $0 |
| **Storage** | SurrealDB in the Docker container | $0 |

**Total: $0.** The "consciousness" (the outline/transcript model) and the voice both come from
free open-source / free-tier endpoints. No monthly fee.

---

## 4. How to make it OUR Money Ball (the build plan)

1. **Stand up Open Notebook** (`docker compose up -d`), connect your NVIDIA/Kokoro TTS as an
   OpenAI-Compatible provider + a free LLM (Ollama or NVIDIA) for outline/transcript.
2. **Create the speaker profiles:** MY BOO (host) and BIG PROPPA (analyst), each with a
   backstory + personality + Kokoro Voice ID. Optionally add JIMMY + JEV as guests.
3. **Create an Episode Profile:** "Money Ball — Week X." Set the briefing to the show structure
   (spots → board → money ball → banter → close), segments 4-6.
4. **Feed it the data as sources.** Either:
   - (a) point it at a **generated text source** from `moneyball.py` (our script generator), or
   - (b) use Open Notebook's **REST API** to add sources + trigger episodes programmatically.
5. **Automate:** a cron/worker that each day runs `day_picks` + `leg_builder`, writes the
   Money Ball source, adds it as a source, and triggers a podcast episode → audio file.
6. **Embed on our site:** pull the generated episode audio + transcript into the `/moneyball`
   page (audio player + live transcript + board).

### Where our existing work plugs in
- `moneyball.generate_show()` → the **briefing / source content** (or replace Open Notebook's
  transcript step entirely with our own script, and use Open Notebook only for the **voice**).
- `day_picks`, `rotowire_api`, `leg_builder`, `bet_logic` → the **content** the show discusses.
- The **15/10 +6 bump** and **payout talk** → text the transcript model is told to include.

---

## 5. Two paths (pick based on how much we want Open Notebook's UI)

**Path A — Use Open Notebook end-to-end (recommended).**
Its podcast engine (outline → transcript → multi-speaker TTS) is the "consciousness." We give
it our data as sources + speaker profiles. Fastest to a great show, all free.

**Path B — Use only its voice, keep our own writer.**
Our `moneyball.generate_show()` already writes the script (persona-tagged, data-driven). We
just call the **Kokoro TTS** (via Open Notebook's OpenAI-Compatible layer, or directly) per
line and stitch. Full control over the writing; Open Notebook supplies the voices.

---

## 6. Bottom line

- **The engineers' favorite open-source NotebookLM is `lfnovo/open-notebook`** (MIT, 41.9k stars).
- **It does 1-4 speaker podcasts with custom personas** — perfect for MY BOO + BIG PROPPA.
- **It accepts any OpenAI-compatible TTS**, so your **free NVIDIA Kokoro endpoint** is the voice.
- **No API subscriptions.** Combine with a free local LLM (Ollama/NVIDIA) → **fully free, fully
  self-hosted** podcast "consciousness."

**Next step:** stand up `lfnovo/open-notebook` locally (Docker), wire the NVIDIA Kokoro TTS as
an OpenAI-Compatible provider, and create the MY BOO + BIG PROPPA speaker profiles. Then feed
it the Money Ball data from `day_picks` / `rotowire_api` / `leg_builder`. Want me to set up the
Docker compose + provider config for Open Notebook, or build our own `moneyball.py` writer that
drives Kokoro directly?

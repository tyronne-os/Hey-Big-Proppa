# HANDOFF — deployment + Jev integration state

Written 2026-09-25, end of session. `docs/HANDOFF.md` covers the lake/pond
side (predates this repo's rename from `frontal-lobe2`, some of it stale —
see its own header). This doc covers what's live, where, and the one open
item: Jev's API key not reaching the deployed Space.

If anything here conflicts with the actual code or the live Space, **the
code and the Space are the truth.** Re-verify before acting on a stale claim.

---

## 1. Where everything lives

| What | URL | Notes |
|---|---|---|
| **Source of truth** | https://github.com/tyronne-os/Hey-Big-Proppa | branch `main`, public repo |
| **Live app (Space)** | https://huggingface.co/spaces/AIBRUH/big-proppa | private, Docker SDK, `RUNNING` as of this write |
| **Space settings (secrets go here)** | https://huggingface.co/spaces/AIBRUH/big-proppa/settings | Settings → Variables and secrets |
| **Data lake backup (Dataset)** | https://huggingface.co/datasets/AIBRUH/big-proppa-lake | private, 52 CSVs from `lake/gold/nfl/`, mirror not source of truth |

Deploy mechanism: `Dockerfile` at repo root builds the React frontend (node
stage) and the FastAPI backend (python stage) into one container, `uvicorn
main:app` on port 7860. `backend/main.py` mounts `frontend/dist/` as static
files, same-origin — no Gradio anywhere, no CORS needed. Redeploying =
`huggingface_hub`'s `upload_folder(repo_id='AIBRUH/big-proppa',
repo_type='space', folder_path='.', ignore_patterns=[...bronze/venv/
node_modules/dist/junk_drawer...])` from a fresh clone of `main`, run from a
Hugging Face Sandbox (`mcp__Hugging_Face__hf_sandbox*` tools) — this coding
environment's own network policy blocks huggingface.co and typesafe.ai
directly, the HF Sandbox does not.

Two other Spaces/datasets exist in the AIBRUH account from earlier,
unrelated or superseded — not touched by this deploy:
- `AIBRUH/frontal-lobe2` (Space, private, `sdk: gradio`) — stale mirror of
  the pre-migration repo, almost certainly the source of the original
  "Gradio compile error" complaint. Left alone.
- `AIBRUH/tyronne-lake` (Space, private, `sdk: docker`) — a **different,
  unrelated project** (its own files: `app_react.py`, `dual_engine.py`,
  `tyronne_os_v1.py`, etc.). Not this app. Not touched.

---

## 2. Jev integration — built, wired, verified working when the key is present

`backend/jev.py`: thin wrapper over the official SDK
(`typesafe-sdk==0.7.1`, https://github.com/typesafe-ai/typesafe-sdk-python).
One Noul (yes/no) question per leg, state built from what Jimmy already
computed (recent hit rate, usage/coach-trust score, matchup unit edge).
Cached per (player, market, direction) for the process lifetime.

**Where it's called:** only inside `parlay_engine.py`'s `_leg()` — once per
leg that already cleared the pond-only gate, never during the broad scan
each finder runs first. This was a deliberate cost control (a full-engine
run touches ~50-100 scan candidates; only the handful that qualify get a
Jev call).

**Graceful degrade, verified:** with `typesafe_sdk` not installed locally
and `JEV_API_KEY` unset, `python3 -c "import parlay_engine as pe;
pe.run_engine()"` produces identical output to before Jev existed — no
crash, no behavior change. This is the expected state for local dev.

**Env var name:** this app reads `JEV_API_KEY`, not the SDK's own default
(`TYPESAFE_API_KEY`, confirmed from `typesafe_sdk/_core/config.py`'s
`API_KEY_ENV` constant). `jev.py`'s `_client()` reads `JEV_API_KEY` itself
and passes it to `TypeSafeClient(api_key=...)` explicitly, so the SDK's own
env var fallback is never exercised. Deliberate choice, for consistency
with everything already named `JEV_API_KEY` (the diagnostic endpoint below,
this doc, prior session history).

---

## 3. Open item: the Space secret isn't reaching the container

**Status as of the last check tonight:** `GET /api/jev_status` on the live
Space returns:
```json
{"jevApiKeyPresent": false, "jevApiKeyLength": 0, "typesafeApiKeyPresent": false,
 "sdkInstalled": true, "callTest": null}
```
Neither `JEV_API_KEY` nor `TYPESAFE_API_KEY` is present in the container,
checked immediately after a **factory reboot** (not just a restart — a
factory reboot fully recreates the container, which rules out "the secret
was added but the old container hadn't picked it up yet"). This has been
tried three times tonight with the same result each time.

**What's been ruled out:**
- Only one `AIBRUH/big-proppa` Space exists (confirmed via `hf_fs search`)
  — no chance of the secret landing on a similarly-named Space instead.
- Not a naming mismatch between `JEV_API_KEY` and the SDK's default
  `TYPESAFE_API_KEY` — the diagnostic checks both, neither is present.
- Not a code bug — confirmed from the SDK's actual source
  (`_core/config.py`) that passing `api_key=` explicitly (as `jev.py` does)
  bypasses the env var lookup entirely; this was independently verified
  correct regardless of what's in the environment.
- Not a stale build — the diagnostic code itself was redeployed and
  confirmed live before each check.

**What hasn't been checked:** the actual content of the Variables and
secrets section at
https://huggingface.co/spaces/AIBRUH/big-proppa/settings — this requires
visual confirmation (a screenshot showing the secret's *name*, which HF
does not mask) since neither the Hub API nor this session can list a
Space's secret names or values. Likely culprits, in rough order of
likelihood: a typo in the exact name (`JEV_API_KEY`, case-sensitive — env
vars on Linux are case-sensitive), the save not actually completing before
navigating away, or a browser/session issue on that specific page.

**To verify once fixed** (from a Hugging Face Sandbox, or ask Claude in a
future session — this coding environment's own network can't reach
huggingface.co or typesafe.ai directly):
```python
from huggingface_hub import HfApi
api = HfApi()
api.restart_space('AIBRUH/big-proppa', factory_reboot=True)
# poll api.get_space_runtime('AIBRUH/big-proppa').stage until 'RUNNING'
```
```bash
curl -s -H "Authorization: Bearer $HF_TOKEN" https://aibruh-big-proppa.hf.space/api/jev_status
```
Success looks like `"jevApiKeyPresent": true` and `"callTest": {"ok": true, "noul": <0-1 value>}`.
A present-but-invalid key shows up as `"callTest": {"ok": false, "errorType": "...", "error": "..."}`
— a real, specific error, not a guess.

Once confirmed working, no further code changes are needed — Jev is already
wired into the live parlay engine and will start contributing to leg
probabilities on the very next `/api/parlays/engine` or `/api/chart/parlays/all`
call.

---

## 4. Quick reference — rebuilding the lake / redeploying

```bash
# Rebuild the lake ponds (run in order, from repo root, backend/.venv active)
python scripts/build_team_game_stats.py         # 2023-2026 team game stats from nflverse pbp
python scripts/fit_matchup_model.py             # fits + backtests the matchup predictor
python scripts/backtest_hot_dogs.py             # Hot Dog indicator history + backtest
python scripts/pow_ledger.py snapshot           # record this week's board before kickoff
python scripts/pow_ledger.py grade --week N     # after games finish

# Back up the lake to the private HF dataset
python scripts/backup_lake_to_hf.py

# Redeploy the Space (from an HF Sandbox — see mcp__Hugging_Face__hf_sandbox* tools)
# 1. git clone --depth 1 https://github.com/tyronne-os/hey-big-proppa /root/repo
# 2. HfApi().upload_folder(repo_id='AIBRUH/big-proppa', repo_type='space',
#    folder_path='/root/repo', ignore_patterns=[git/bronze/venv/node_modules/dist/junk_drawer])
```

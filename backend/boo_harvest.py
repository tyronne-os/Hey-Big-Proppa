"""
MY BOO's BETTER-VERSE harvester: automatic, obsessive collection of everything BETTER-VERSE produces.

Nothing here waits for a person to click. Triggers:

  EVENT      every BETTER-VERSE run written           -> harvest_run    (hook in betterverse_sim._write)
             every Strategy Lab study written         -> harvest_study  (hook in betterverse_study._write)
  STARTUP    the worker backfills anything on disk that is not in the ledger and retries unsent mirrors
  SCHEDULE   the worker runs a harvest CYCLE every HARVEST_EVERY_MIN minutes (default 360): fresh universes across every
             real season -> harvest -> a Strategy Lab study every HARVEST_STUDY_EVERY cycles (new evidence for the curriculum)
             -> in-house JEV training when enough new data has arrived
  EXTERNAL   POST /api/myboo/harvest/cycle (token) lets a scheduled GitHub Action wake a sleeping Space and run a cycle

What is collected, per run: every leg, every slip, every better (username, tier, ideology, rules, base bet, results) and the
insights, checksummed and mirrored to the private dataset AIBRUH/big-proppa-lake under myboo/betterverse/<run_id>/. A crowd
counter records how often each board leg was picked, by tier, across every run. Per study: the full study plus curriculum
evidence and a curriculum release if anything changed. If the mirror is unreachable the item stays queued and is retried.

Files (lake/gold/nfl/boo_harvest/): ledger.jsonl · crowd.json · state.json
Switches: BOO_HARVEST=0 turns every trigger off (tests), AUTOHARVEST=0 turns off only the scheduled cycles.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import pandas as pd

DIR = Path(__file__).parent.parent / "lake/gold/nfl/boo_harvest"
ENABLED = os.environ.get("BOO_HARVEST", "1") != "0"
EVERY_MIN = int(os.environ.get("HARVEST_EVERY_MIN", "360"))
UNIVERSES = int(os.environ.get("HARVEST_UNIVERSES", "3"))
BETTERS = int(os.environ.get("HARVEST_BETTERS", "150"))
STUDY_EVERY = int(os.environ.get("HARVEST_STUDY_EVERY", "4"))
STUDY_UNIVERSES = int(os.environ.get("HARVEST_STUDY_UNIVERSES", "20"))
FIRST_SEED = 1000                       # automatic universes use seeds from here up, so they never repeat a hand-run seed
_LOCK = threading.RLock()
_CYCLE_LOCK = threading.Lock()
_worker: threading.Thread | None = None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _p(name: str) -> Path:
    return DIR / name


def _read(name: str, default):
    try:
        return json.loads(_p(name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, obj) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = _p(name + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(_p(name))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- ledger
def ledger() -> list[dict]:
    try:
        return [json.loads(l) for l in _p("ledger.jsonl").read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _append(rec: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    with _p("ledger.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _collected() -> dict[tuple[str, str], dict]:
    """{(kind, id): latest collection record}"""
    out: dict = {}
    for r in ledger():
        if r.get("event") == "collected":
            out[(r["kind"], r["id"])] = r
    return out


def _mirrored() -> set[tuple[str, str]]:
    return {(r["kind"], r["id"]) for r in ledger() if r.get("event") == "mirrored" and r.get("ok")}


def pending() -> list[tuple[str, str]]:
    done = _mirrored()
    return [k for k in _collected() if k not in done]


# --------------------------------------------------------------------------- mirror (durable copy in the private dataset)
def _mirror(kind: str, ident: str, path: Path, remote: str) -> bool:
    ok = False
    try:
        import boo_store
        ok = bool(boo_store.enabled() and boo_store.push_dir(path, remote))
    except Exception:
        ok = False
    with _LOCK:
        _append({"event": "mirrored", "kind": kind, "id": ident, "ok": ok, "at": _now()})
    return ok


def _mirror_state() -> None:
    try:
        import boo_store
        if boo_store.enabled():
            boo_store.push_dir(DIR, "myboo/boo_harvest")
    except Exception:
        pass


def retry_pending(limit: int = 25) -> int:
    """Re-send anything that has not reached the dataset yet."""
    import betterverse_sim as sim
    import betterverse_study as study
    n = 0
    for kind, ident in pending()[:limit]:
        base = sim.OUT if kind == "run" else study.OUT
        remote = f"myboo/betterverse/{ident}" if kind == "run" else f"myboo/betterverse_studies/{ident}"
        if (base / ident).exists() and _mirror(kind, ident, base / ident, remote):
            n += 1
    if n:
        _mirror_state()
    return n


# --------------------------------------------------------------------------- crowd counters
def _update_crowd(legs: pd.DataFrame) -> int:
    """How often each board leg was picked, in total and by tier, across every run harvested."""
    crowd = _read("crowd.json", {})
    cols = ["season", "week", "game_id", "player_id", "market", "side", "line", "tier"]
    g = legs[cols].astype({"season": int, "week": int}).groupby(cols[:-1] + ["tier"]).size().reset_index(name="n")
    tiers = ["sharp", "grinder", "casual", "degen"]
    for r in g.itertuples(index=False):
        key = f"{r.season}|{r.week}|{r.game_id}|{r.player_id}|{r.market}|{r.side}|{r.line}"
        c = crowd.setdefault(key, [0, 0, 0, 0, 0])
        c[0] += int(r.n)
        c[1 + tiers.index(r.tier)] += int(r.n)
    _write("crowd.json", crowd)
    return len(crowd)


# --------------------------------------------------------------------------- collection
def harvest_run(run_id: str) -> dict:
    """Collect one BETTER-VERSE run. Idempotent: a run already in the ledger with the same checksum is skipped."""
    import betterverse_sim as sim
    d = sim.OUT / run_id
    if not (d / "slips.parquet").exists():
        return {"ok": False, "reason": "run not found"}
    with _LOCK:
        sha = _sha(d / "slips.parquet") + _sha(d / "legs.parquet")[:8]
        have = _collected().get(("run", run_id))
        if have and have.get("sha") == sha:
            return {"ok": True, "skipped": True, "run_id": run_id}
        man = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        legs = pd.read_parquet(d / "legs.parquet", columns=["season", "week", "game_id", "player_id", "market", "side", "line", "tier"])
        crowd_keys = _update_crowd(legs)
        bett = pd.read_parquet(d / "bettors.parquet", columns=["bettor_id"])
        rec = {"event": "collected", "kind": "run", "id": run_id, "at": _now(), "sha": sha, "season": man.get("season"),
               "bettors": int(len(bett)), "slips": int(man.get("rows", {}).get("slips", 0)), "legs": int(len(legs)),
               "bytes": int(sum(f.stat().st_size for f in d.iterdir() if f.is_file()))}
        _append(rec)
    _mirror("run", run_id, d, f"myboo/betterverse/{run_id}")
    _mirror_state()
    return {"ok": True, "run_id": run_id, "legs": rec["legs"], "slips": rec["slips"], "bettors": rec["bettors"], "crowd_keys": crowd_keys}


def harvest_study(study_id: str) -> dict:
    """Collect one Strategy Lab study: file it, send its evidence to the curriculum, cut a release if anything changed."""
    import betterverse_study as study
    import boo_curriculum
    d = study.OUT / study_id
    if not (d / "study.json").exists():
        return {"ok": False, "reason": "study not found"}
    with _LOCK:
        sha = _sha(d / "study.json")
        have = _collected().get(("study", study_id))
        if have and have.get("sha") == sha:
            return {"ok": True, "skipped": True, "study_id": study_id}
        boo_curriculum.ingest_study(study_id)
        try:
            import boo_training
            boo_training.ingest_betterverse_study(study_id)
        except Exception:
            pass
        release = boo_curriculum.cut_release(trigger="harvest")
        s = json.loads((d / "study.json").read_text())
        _append({"event": "collected", "kind": "study", "id": study_id, "at": _now(), "sha": sha, "seasons": s.get("seasons"),
                 "bettors": s.get("bettor_seasons"), "slips": s.get("slips"), "legs": 0, "bytes": (d / "study.json").stat().st_size})
    _mirror("study", study_id, d, f"myboo/betterverse_studies/{study_id}")
    _mirror_state()
    return {"ok": True, "study_id": study_id, "release": release}


def backfill() -> dict:
    """Harvest everything on disk that the ledger has not seen, and retry unsent mirrors."""
    import betterverse_sim as sim
    import betterverse_study as study
    got = {"runs": 0, "studies": 0}
    if sim.OUT.exists():
        for d in sorted(sim.OUT.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and ("run", d.name) not in _collected():
                if harvest_run(d.name).get("ok"):
                    got["runs"] += 1
    if study.OUT.exists():
        for d in sorted(study.OUT.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and ("study", d.name) not in _collected():
                if harvest_study(d.name).get("ok"):
                    got["studies"] += 1
    got["retried"] = retry_pending()
    return got


# --------------------------------------------------------------------------- event hooks
def _bg(fn, *a) -> None:
    threading.Thread(target=lambda: _safe(fn, *a), daemon=True, name=f"harvest-{fn.__name__}").start()


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        st = _read("state.json", {})
        st["last_error"] = f"{fn.__name__}: {type(e).__name__}: {str(e)[:160]}"
        _write("state.json", st)


def on_run(run_id: str) -> None:
    if ENABLED:
        _bg(harvest_run, run_id)


def on_study(study_id: str) -> None:
    if ENABLED:
        _bg(harvest_study, study_id)


# --------------------------------------------------------------------------- cycles
def state() -> dict:
    return _read("state.json", {"cycles": 0, "next_seed": FIRST_SEED, "studies_run": 0})


def cycle(reason: str = "schedule", universes: int | None = None, bettors: int | None = None, study_universes: int | None = None) -> dict:
    """One full harvest: new universes over every real season, collected; a study now and then; training when due."""
    import betterverse_sim as sim
    import betterverse_study as study
    if not _CYCLE_LOCK.acquire(blocking=False):
        return {"ok": False, "reason": "a cycle is already running"}
    t0 = time.time()
    try:
        st = state()
        u, n = universes or UNIVERSES, bettors or BETTERS
        seed = int(st.get("next_seed", FIRST_SEED))
        collected = {"runs": 0, "legs": 0, "slips": 0}
        for k in range(u):
            for season in sim.md.SEASONS:
                sim.simulate(season, n, seed + k)
                h = harvest_run(sim.run_id(season, n, seed + k, None))
                if h.get("ok") and not h.get("skipped"):
                    collected["runs"] += 1
                    collected["legs"] += h["legs"]
                    collected["slips"] += h["slips"]
        st.update(next_seed=seed + u, cycles=int(st.get("cycles", 0)) + 1)
        study_id = None
        if STUDY_EVERY and st["cycles"] % STUDY_EVERY == 1 or st["cycles"] == 1:
            sseed = FIRST_SEED * (2 + int(st.get("studies_run", 0)))            # a new study seed each time = replication evidence
            res = study.run_study(study_universes or STUDY_UNIVERSES, n, sseed)
            study._write(res["study_id"], res)
            harvest_study(res["study_id"])
            study_id = res["study_id"]
            st["studies_run"] = int(st.get("studies_run", 0)) + 1
        trained = None
        try:
            import boo_jev_trainer
            trained = boo_jev_trainer.maybe_train(st["cycles"])
        except Exception as e:
            st["last_error"] = f"train: {type(e).__name__}: {str(e)[:160]}"
        st.update(last_cycle=_now(), last_cycle_secs=round(time.time() - t0, 1), last_reason=reason)
        _write("state.json", st)
        _mirror_state()
        return {"ok": True, "reason": reason, "seed": seed, "universes": u, "collected": collected, "study": study_id,
                "trained": trained, "seconds": st["last_cycle_secs"]}
    except Exception as e:
        st = state()
        st["last_error"] = f"cycle: {type(e).__name__}: {str(e)[:160]}"
        _write("state.json", st)
        return {"ok": False, "error": st["last_error"]}
    finally:
        _CYCLE_LOCK.release()


def due() -> bool:
    st = state()
    last = st.get("last_cycle")
    if not last:
        return True
    return time.time() - calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ")) >= EVERY_MIN * 60


def start_worker() -> None:
    """Start the background collector once. Safe to call repeatedly."""
    global _worker
    if not ENABLED or (_worker and _worker.is_alive()):
        return

    def run() -> None:
        time.sleep(45)                                         # let the app finish booting before doing real work
        _safe(backfill)
        while True:
            if os.environ.get("AUTOHARVEST", "1") != "0":
                _safe(lambda: cycle("schedule") if due() else None)
            time.sleep(300)

    _worker = threading.Thread(target=run, daemon=True, name="boo-harvest")
    _worker.start()


# --------------------------------------------------------------------------- status
def status() -> dict:
    led = ledger()
    col = _collected()
    runs = [r for (k, _), r in col.items() if k == "run"]
    studies = [r for (k, _), r in col.items() if k == "study"]
    st = state()
    nxt = None
    if st.get("last_cycle"):
        nxt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(calendar.timegm(time.strptime(st["last_cycle"], "%Y-%m-%dT%H:%M:%SZ")) + EVERY_MIN * 60))
    try:
        import boo_jev_trainer
        model = boo_jev_trainer.status()
    except Exception:
        model = None
    return {"enabled": ENABLED, "auto_cycles": os.environ.get("AUTOHARVEST", "1") != "0", "every_minutes": EVERY_MIN,
            "universes_per_cycle": UNIVERSES, "betters_per_universe": BETTERS,
            "collected": {"runs": len(runs), "studies": len(studies), "legs": sum(r.get("legs", 0) for r in runs),
                          "slips": sum(r.get("slips", 0) for r in runs), "betters": sum(r.get("bettors", 0) for r in runs),
                          "bytes": sum(r.get("bytes", 0) for r in runs + studies)},
            "pending_mirror": len(pending()), "crowd_keys": len(_read("crowd.json", {})), "cycles": st.get("cycles", 0),
            "studies_run": st.get("studies_run", 0), "last_cycle": st.get("last_cycle"), "last_cycle_secs": st.get("last_cycle_secs"),
            "next_cycle_after": nxt, "last_error": st.get("last_error"), "model": model,
            "recent": [{k: r.get(k) for k in ("kind", "id", "at", "season", "legs", "slips")} for r in list(col.values())[-8:]][::-1]}

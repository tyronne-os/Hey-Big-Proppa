"""
JEV LEDGER -- every JEV read is written down before kickoff and graded against the ESPN final.

That is how "JEV is smarter" stays a measured claim instead of a hope:
  record()  one row per prop / total / spread / moneyline read: BPL probability, JEV probability, blend, line
  settle()  once ESPN marks the game FINAL, fill in the real stat or score and whether the over/cover/win hit
  report()  Brier score and hit rate for BPL alone, JEV alone and the blend, plus JEV's calibration buckets
  weight()  the JEV blend weight, tuned from settled rows (0.25 until 40 rows exist, then whatever weight in
            0-0.60 minimizes the blend's Brier score on the graded history)

Rows live in lake/gold/espn/jev_ledger.jsonl. Hugging Face Spaces wipe their disk on restart, so when
HF_TOKEN is set the ledger also syncs to a private dataset repo (JEV_LEDGER_REPO) and reloads from it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from pathlib import Path

import data

_FILE = Path(__file__).resolve().parent.parent / "lake" / "gold" / "espn" / "jev_ledger.jsonl"
_REPO = os.environ.get("JEV_LEDGER_REPO", "AIBRUH/big-proppa-jev-ledger")
_LOCK = threading.Lock()
_ROWS: dict[str, dict] | None = None
_STATE = {"dirty": False, "lastSync": 0.0, "lastSettle": 0.0, "worker": False, "syncError": None}
DEFAULT_WEIGHT = 0.25
MIN_ROWS_TO_TUNE = 40
GAME_KINDS = ("total", "spread", "ml")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _load() -> dict[str, dict]:
    global _ROWS
    if _ROWS is not None:
        return _ROWS
    rows: dict[str, dict] = {}
    if not _FILE.exists() and os.environ.get("HF_TOKEN"):
        try:
            from huggingface_hub import hf_hub_download
            p = hf_hub_download(_REPO, "jev_ledger.jsonl", repo_type="dataset", token=os.environ["HF_TOKEN"])
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            _FILE.write_text(Path(p).read_text())
        except Exception as exc:
            _STATE["syncError"] = f"load: {type(exc).__name__}"
    if _FILE.exists():
        for ln in _FILE.read_text().splitlines():
            try:
                r = json.loads(ln)
                rows[r["key"]] = r
            except (ValueError, KeyError):
                continue
    _ROWS = rows
    return rows


def _save() -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r) for r in _load().values()))
    tmp.replace(_FILE)


def _sync(force: bool = False) -> None:
    tok = os.environ.get("HF_TOKEN")
    if not tok or not _FILE.exists() or (not force and time.time() - _STATE["lastSync"] < 900):
        return
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=tok)
        api.create_repo(_REPO, repo_type="dataset", private=True, exist_ok=True)
        api.upload_file(path_or_fileobj=str(_FILE), path_in_repo="jev_ledger.jsonl", repo_id=_REPO, repo_type="dataset",
                        commit_message="JEV ledger sync")
        _STATE["lastSync"], _STATE["syncError"] = time.time(), None
    except Exception as exc:
        _STATE["syncError"] = f"upload: {type(exc).__name__}"


_ESPN_IDS: dict[str, str] = {}


def espn_id_for(lake_game_id: str) -> str | None:
    if not _ESPN_IDS:
        _ESPN_IDS.update({r["game_id"]: r["espn"] for r in data.load("schedule") if r.get("espn") and r.get("season", "") >= "2025"})
    return _ESPN_IDS.get(lake_game_id)


def record(kind: str, key: str, **fields) -> None:
    """kind: prop | total | spread | ml. `key` must be unique per read (game, side and line)."""
    if fields.get("jevP") is None:
        return
    with _LOCK:
        rows = _load()
        if key in rows:
            return
        rows[key] = {"key": key, "kind": kind, "created": _now(), "settled": False, **fields}
        _save()
        _STATE["dirty"] = True
    _ensure_worker()


def _outcome(row: dict, lg: dict) -> tuple[float | None, int | None]:
    k = row["kind"]
    if k == "prop":
        import h2h
        st = lg["players"].get(f"{data.normalize_name(row['name'])}|{row['team']}")
        if not st:
            return None, None                          # did not record a stat: void
        v = float(st.get(h2h.STAT_KEY[row["market"]], 0.0))
        return v, int(v > row["line"]) if row.get("direction", "over") == "over" else int(v < row["line"])
    hs, as_ = lg["homeScore"], lg["awayScore"]
    if k == "total":
        t = hs + as_
        return t, None if t == row["line"] else int((t > row["line"]) == (row.get("direction", "over") == "over"))
    if k == "spread":
        m = hs - as_ + row["line"]
        return hs - as_, None if m == 0 else int(m > 0)
    if k == "ml":
        return hs - as_, None if hs == as_ else int(hs > as_)
    return None, None


def settle() -> int:
    import h2h
    with _LOCK:
        open_rows = [r for r in _load().values() if not r["settled"] and r.get("espnId")]
    done = 0
    for gid in {r["espnId"] for r in open_rows}:
        lg = h2h.live_game(gid)
        if not lg.get("ok") or lg.get("state") != "FINAL":
            continue
        with _LOCK:
            for r in _load().values():
                if r.get("espnId") != gid or r["settled"]:
                    continue
                actual, hit = _outcome(r, lg)
                r.update(settled=True, settledAt=_now(), actual=actual, hit=hit, void=hit is None)
                done += 1
            _save()
            _STATE["dirty"] = True
    _STATE["lastSettle"] = time.time()
    return done


def _worker() -> None:
    while True:
        try:
            settle()
            if _STATE["dirty"]:
                _sync()
                _STATE["dirty"] = bool(_STATE["syncError"])
        except Exception:
            pass
        time.sleep(1200)


def _ensure_worker() -> None:
    if not _STATE["worker"]:
        _STATE["worker"] = True
        threading.Thread(target=_worker, daemon=True, name="jev-ledger").start()


def _graded(kinds) -> list[dict]:
    return [r for r in _load().values() if r["kind"] in kinds and r.get("settled") and not r.get("void") and r.get("bplP") is not None]


def _brier(rows, field: str) -> float | None:
    return round(sum((r[field] - r["hit"]) ** 2 for r in rows) / len(rows), 4) if rows else None


_W: dict[str, tuple[float, float]] = {}


def weight(group: str = "prop") -> float:
    """JEV's share of the blended probability for 'prop' or 'game' legs, tuned from graded history."""
    hit = _W.get(group)
    if hit and hit[0] > time.time():
        return hit[1]
    rows = _graded(("prop",) if group == "prop" else GAME_KINDS)
    w = DEFAULT_WEIGHT
    if len(rows) >= MIN_ROWS_TO_TUNE:
        best = min((sum(((1 - c) * r["bplP"] + c * r["jevP"] - r["hit"]) ** 2 for r in rows), c) for c in [i / 20 for i in range(13)])
        w = best[1]
    _W[group] = (time.time() + 600, w)
    return w


def report() -> dict:
    with _LOCK:
        rows = list(_load().values())
    out = {"rows": len(rows), "settled": sum(1 for r in rows if r.get("settled")), "open": sum(1 for r in rows if not r.get("settled")),
           "lastSettle": dt.datetime.fromtimestamp(_STATE["lastSettle"], dt.timezone.utc).isoformat(timespec="seconds") if _STATE["lastSettle"] else None,
           "durableSync": bool(os.environ.get("HF_TOKEN")), "syncError": _STATE["syncError"], "groups": {}}
    for group, kinds in (("prop", ("prop",)), ("game", GAME_KINDS)):
        g = _graded(kinds)
        buckets = []
        for lo in (0.0, 0.4, 0.5, 0.6, 0.7):
            hi = {0.0: 0.4, 0.4: 0.5, 0.5: 0.6, 0.6: 0.7, 0.7: 1.01}[lo]
            b = [r for r in g if lo <= r["jevP"] < hi]
            if b:
                buckets.append({"jevSays": f"{int(lo * 100)}-{min(int(hi * 100), 100)}%", "n": len(b), "actuallyHit": round(sum(r["hit"] for r in b) / len(b), 3)})
        out["groups"][group] = {
            "graded": len(g), "weightNow": weight(group), "tuned": len(g) >= MIN_ROWS_TO_TUNE,
            "brier": {"bplOnly": _brier(g, "bplP"), "jevOnly": _brier(g, "jevP"), "blend": _brier([r for r in g if r.get("blendP") is not None], "blendP")},
            "hitRateWhenFavored": {"bpl": round(sum(r["hit"] for r in g if r["bplP"] >= 0.5) / max(1, sum(1 for r in g if r["bplP"] >= 0.5)), 3) if g else None,
                                   "jev": round(sum(r["hit"] for r in g if r["jevP"] >= 0.5) / max(1, sum(1 for r in g if r["jevP"] >= 0.5)), 3) if g else None},
            "jevCalibration": buckets,
        }
    out["note"] = "Lower Brier is better. The blend weight retunes itself once 40 rows in a group are graded."
    return out

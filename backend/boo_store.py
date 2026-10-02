"""
Keeps MY BOO's records alive across restarts and redeploys.

The Space's disk is wiped every time the container rebuilds, which is how a night of slips can vanish.
When an HF_TOKEN secret is set on the Space, her ledger files are mirrored to the private dataset
AIBRUH/big-proppa-lake under myboo/ after every change, and pulled back down at startup.
The token is read from the environment and never printed, logged or committed.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

_GOLD = Path(__file__).parent.parent / "lake/gold/nfl"
REPO = "AIBRUH/big-proppa-lake"
FILES = ["myboo_tickets.csv", "myboo_legs.csv", "myboo_thesis.json", "myboo_recaps.json", "myboo_alerts.json", "myboo_counter.txt"]
_state = {"last_push": 0.0, "pushes": 0, "last_error": None}
_lock = threading.Lock()


def _token() -> str | None:
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")


def enabled() -> bool:
    return bool(_token())


def status() -> dict:
    return {"enabled": enabled(), "repo": REPO, **_state}


def pull() -> int:
    """At startup: fetch her files if the local copy is missing or older. Never overwrites newer local data."""
    if not enabled():
        return 0
    n = 0
    try:
        from huggingface_hub import hf_hub_download
        for f in FILES:
            try:
                got = hf_hub_download(REPO, f"myboo/{f}", repo_type="dataset", token=_token())
            except Exception:
                continue
            dst = _GOLD / f
            if not dst.exists() or Path(got).stat().st_size > dst.stat().st_size:
                dst.write_bytes(Path(got).read_bytes())
                n += 1
    except Exception as e:                         # a mirror problem must never stop the app
        _state["last_error"] = type(e).__name__
    return n


def push(force: bool = False) -> bool:
    """After a change: upload her files (at most once every 30 s unless forced)."""
    if not enabled():
        return False
    with _lock:
        if not force and time.time() - _state["last_push"] < 30:
            return False
        try:
            from huggingface_hub import CommitOperationAdd, HfApi
            ops = [CommitOperationAdd(f"myboo/{f}", str(_GOLD / f)) for f in FILES if (_GOLD / f).exists()]
            HfApi(token=_token()).create_commit(REPO, ops, repo_type="dataset", commit_message="MY BOO ledger sync")
            _state.update(last_push=time.time(), pushes=_state["pushes"] + 1, last_error=None)
            return True
        except Exception as e:
            _state["last_error"] = type(e).__name__
            return False

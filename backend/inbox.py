"""
Contact Us and waitlist submissions.

Every submission is written to lake/gold/nfl/inbox.jsonl first (mirrored to the private HF dataset by boo_store, never
committed to GitHub), then emailed to the owner in a background thread. A failed email is not lost: it stays "undelivered" in
the log and is retried on the next submission and by flush().

Delivery, in order:
  1. SMTP, when SMTP_HOST / SMTP_USER / SMTP_PASSWORD are set as Space secrets (optional SMTP_PORT, SMTP_FROM).
  2. FormSubmit.co relay (no secrets needed). The first message it ever receives for an address triggers a one-time
     activation email to that address; click it once and later messages arrive normally.
The destination is INBOX_TO (default tjengineer@berylize.com).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import smtplib
import threading
import time
import urllib.request
import uuid
from collections import defaultdict, deque
from email.message import EmailMessage
from pathlib import Path

TO = os.environ.get("INBOX_TO", "tjengineer@berylize.com")
FILE = Path(__file__).parent.parent / "lake/gold/nfl/inbox.jsonl"
KINDS = {"waitlist": "Waitlist signup", "contact": "Contact form"}
LIMITS = {"name": 100, "email": 200, "topic": 60, "message": 4000}
RATE_MAX, RATE_WINDOW = 5, 600          # submissions per client per 10 minutes
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
_LOCK = threading.RLock()
_HITS: dict[str, deque] = defaultdict(deque)


class InboxError(ValueError):
    """A problem the visitor can fix (bad email, too fast); the message is safe to show."""


def _clean(v, limit: int) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v or "")).strip()[:limit]


def _one_line(v: str) -> str:
    return re.sub(r"[\r\n]+", " ", v)


def _rate_check(client: str) -> None:
    now = time.time()
    hits = _HITS[client]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_MAX:
        raise InboxError("Too many messages from this connection. Please try again in a few minutes.")
    hits.append(now)


def _append(row: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def _rows() -> list[dict]:
    try:
        return [json.loads(l) for l in FILE.read_text().splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _smtp_ready() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def _body(sub: dict) -> str:
    lines = [f"{KINDS.get(sub['kind'], sub['kind'])} · {sub['ts']}", ""]
    for k in ("name", "email", "topic"):
        if sub.get(k):
            lines.append(f"{k.title()}: {sub[k]}")
    if sub.get("message"):
        lines += ["", sub["message"]]
    return "\n".join(lines)


def _subject(sub: dict) -> str:
    base = KINDS.get(sub["kind"], "Big Proppa")
    who = sub.get("name") or sub.get("email", "")
    topic = f" — {sub['topic']}" if sub.get("topic") else ""
    return _one_line(f"[Big Proppa] {base}{topic}: {who}")[:200]


def _send_smtp(sub: dict) -> None:
    msg = EmailMessage()
    msg["Subject"] = _subject(sub)
    msg["From"] = os.environ.get("SMTP_FROM") or os.environ["SMTP_USER"]
    msg["To"] = TO
    msg["Reply-To"] = sub["email"]
    msg.set_content(_body(sub))
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=20) as s:
        if port != 465:
            s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


def _send_relay(sub: dict) -> None:
    payload = {"name": sub.get("name") or "(not given)", "email": sub["email"], "_subject": _subject(sub),
               "_template": "table", "_captcha": "false", "type": KINDS.get(sub["kind"], sub["kind"]),
               "message": sub.get("message") or "(waitlist signup)", "topic": sub.get("topic") or "-"}
    req = urllib.request.Request(
        f"https://formsubmit.co/ajax/{TO}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "big-proppa-inbox/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode() or "{}")
    if str(out.get("success")).lower() != "true":
        raise RuntimeError(str(out.get("message") or "relay refused the message")[:200])


def _deliver(sub: dict) -> dict:
    try:
        if _smtp_ready():
            _send_smtp(sub)
            return {"delivered": True, "via": "smtp"}
        _send_relay(sub)
        return {"delivered": True, "via": "formsubmit"}
    except Exception as e:   # recorded, retried later, never shown to the visitor
        return {"delivered": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def _mirror() -> None:
    try:
        import boo_store
        boo_store.push()
    except Exception:
        pass


def _process(subs: list[dict]) -> None:
    for sub in subs:
        res = _deliver(sub)
        with _LOCK:
            _append({"id": sub["id"], "event": "delivery", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **res})
    _mirror()


def undelivered(limit: int = 20) -> list[dict]:
    rows = _rows()
    done = {r["id"] for r in rows if r.get("event") == "delivery" and r.get("delivered")}
    return [r for r in rows if r.get("event") == "submission" and r["id"] not in done][:limit]


def flush(background: bool = True) -> int:
    """Retry anything that never reached the owner's inbox."""
    pending = undelivered()
    if pending:
        if background:
            threading.Thread(target=_process, args=(pending,), daemon=True, name="inbox-flush").start()
        else:
            _process(pending)
    return len(pending)


def submit(kind: str, data: dict, client: str = "unknown") -> dict:
    if kind not in KINDS:
        raise InboxError("Unknown form.")
    if str(data.get("website") or "").strip():                       # honeypot: real visitors never see this field
        return {"ok": True, "id": "ignored"}
    email = _clean(data.get("email"), LIMITS["email"]).lower()
    if not _EMAIL.match(email):
        raise InboxError("Please enter a valid email address.")
    sub = {"event": "submission", "id": uuid.uuid4().hex[:12], "kind": kind,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "email": email,
           "name": _clean(data.get("name"), LIMITS["name"]), "topic": _clean(data.get("topic"), LIMITS["topic"]),
           "message": _clean(data.get("message"), LIMITS["message"]),
           "client": hashlib.sha256(client.encode()).hexdigest()[:12]}
    if kind == "contact" and len(sub["message"]) < 5:
        raise InboxError("Please write a short message.")
    with _LOCK:
        _rate_check(client)
        _append(sub)
    retry = [r for r in undelivered(5) if r["id"] != sub["id"]]
    threading.Thread(target=_process, args=([sub] + retry,), daemon=True, name="inbox-send").start()
    return {"ok": True, "id": sub["id"]}


def health() -> dict:
    rows = _rows()
    subs = [r for r in rows if r.get("event") == "submission"]
    return {"to": TO, "smtp": _smtp_ready(), "relay": "formsubmit" if not _smtp_ready() else None,
            "stored": len(subs), "undelivered": len(undelivered(1000)),
            "waitlist": sum(1 for r in subs if r["kind"] == "waitlist"), "contact": sum(1 for r in subs if r["kind"] == "contact")}

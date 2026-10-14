import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inbox


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "FILE", tmp_path / "inbox.jsonl")
    monkeypatch.setattr(inbox, "_HITS", __import__("collections").defaultdict(__import__("collections").deque))
    sent = []
    monkeypatch.setattr(inbox, "_deliver", lambda sub: sent.append(sub) or {"delivered": True, "via": "test"})
    monkeypatch.setattr(inbox, "_mirror", lambda: None)
    return sent


def _wait(sent, n=1):
    import time
    for _ in range(200):
        rows = [json.loads(l) for l in inbox.FILE.read_text().splitlines()] if inbox.FILE.exists() else []
        if len(sent) >= n and any(r.get("event") == "delivery" for r in rows):
            return
        time.sleep(0.02)


def test_waitlist_is_stored_and_emailed(isolated):
    r = inbox.submit("waitlist", {"email": "Fan@Example.com"}, "1.2.3.4")
    assert r["ok"]
    _wait(isolated)
    assert isolated[0]["email"] == "fan@example.com"
    rows = [json.loads(l) for l in inbox.FILE.read_text().splitlines()]
    assert rows[0]["kind"] == "waitlist" and any(x.get("event") == "delivery" for x in rows)
    assert inbox.undelivered() == []


def test_bad_email_and_short_message_rejected():
    with pytest.raises(inbox.InboxError):
        inbox.submit("waitlist", {"email": "nope"}, "a")
    with pytest.raises(inbox.InboxError):
        inbox.submit("contact", {"email": "a@b.co", "message": "hi"}, "a")


def test_honeypot_is_dropped_silently(isolated):
    assert inbox.submit("contact", {"email": "a@b.co", "message": "hello there", "website": "http://spam"}, "a")["id"] == "ignored"
    assert not inbox.FILE.exists()


def test_rate_limit():
    for i in range(inbox.RATE_MAX):
        inbox.submit("waitlist", {"email": f"u{i}@b.co"}, "same")
    with pytest.raises(inbox.InboxError, match="Too many"):
        inbox.submit("waitlist", {"email": "x@b.co"}, "same")


def test_header_injection_is_flattened():
    sub = {"kind": "contact", "name": "Eve\r\nBcc: evil@x.com", "email": "a@b.co", "topic": "", "ts": "t"}
    assert "\n" not in inbox._subject(sub) and "\r" not in inbox._subject(sub)


def test_failed_delivery_is_kept_and_retried(monkeypatch):
    monkeypatch.setattr(inbox, "_deliver", lambda sub: {"delivered": False, "error": "down"})
    inbox.submit("waitlist", {"email": "a@b.co"}, "x")
    import time; time.sleep(0.3)
    assert len(inbox.undelivered()) == 1
    monkeypatch.setattr(inbox, "_deliver", lambda sub: {"delivered": True, "via": "test"})
    assert inbox.flush(background=False) == 1
    assert inbox.undelivered() == []

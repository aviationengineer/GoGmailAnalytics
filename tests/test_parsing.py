"""Parsing tests with mock Gmail payloads (no real account needed)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gmail_intel.parsing import parse_message, parse_addrs, thread_summary


def _msg(**kw):
    base = {
        "id": "m1", "threadId": "t1", "internalDate": "1700000000000",
        "snippet": "hello",
        "payload": {"headers": [
            {"name": "From", "value": "John Smith <john.smith@company.com>"},
            {"name": "To", "value": "me@gmail.com"},
            {"name": "Subject", "value": "Q3 data platform"},
            {"name": "Date", "value": "Tue, 14 Nov 2023 10:00:00 +0000"},
        ]},
        "labelIds": ["INBOX"],
    }
    base.update(kw)
    return base


def test_parse_addrs():
    addrs = parse_addrs("John Smith <john@x.com>, jane@y.com")
    assert addrs[0] == {"name": "John Smith", "email": "john@x.com"}
    assert addrs[1]["email"] == "jane@y.com"


def test_parse_message_fields():
    r = parse_message(_msg())
    assert r["from_email"] == "john.smith@company.com"
    assert r["from_name"] == "John Smith"
    assert r["subject"] == "Q3 data platform"
    assert r["date"].startswith("2023-11-14")
    assert r["body_text"] == ""  # bodies off by default


def test_parse_message_sent_flag():
    r = parse_message(_msg(labelIds=["SENT"]))
    assert r["is_sent"] is True


def test_thread_summary():
    a = parse_message(_msg(id="m1", threadId="t1"))
    b = parse_message(_msg(id="m2", threadId="t1"))
    s = thread_summary([a, b])
    assert s["message_count"] == 2
    assert s["participant_count"] == 2

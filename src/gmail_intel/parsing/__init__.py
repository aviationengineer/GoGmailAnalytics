"""Email parsing: Gmail message payload -> normalized email record.

Bodies are only retained when store_body=True (default False, per the
privacy principle: metadata is enough for relationship analytics).
"""
from __future__ import annotations

import base64
import email.utils
from datetime import timezone


def parse_addrs(value: str) -> list[dict]:
    out = []
    for name, addr in email.utils.getaddresses([value or ""]):
        addr = (addr or "").strip().lower()
        if not addr or "@" not in addr:
            continue
        out.append({"name": name.strip(), "email": addr})
    return out


def parse_date(value: str) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt is not None:
            return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    return ""


def _decode_body(payload: dict) -> tuple[str, str]:
    """Return (text, html); empty unless a part carries them."""
    text, html = "", ""
    stack = [payload]
    while stack:
        part = stack.pop()
        for child in part.get("parts", []) or []:
            stack.append(child)
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if not data:
            continue
        try:
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            continue
        if mime == "text/plain" and not text:
            text = decoded
        elif mime == "text/html" and not html:
            html = decoded
    return text, html


def parse_message(msg: dict, store_body: bool = False) -> dict:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    from_list = parse_addrs(headers.get("From", ""))
    frm = from_list[0] if from_list else {"name": "", "email": ""}
    label_ids = msg.get("labelIds", [])
    body_text, body_html = ("", "")
    if store_body:
        body_text, body_html = _decode_body(msg.get("payload", {}))
    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "internal_date": msg.get("internalDate", ""),
        "date": parse_date(headers.get("Date", "")),
        "from_name": frm["name"],
        "from_email": frm["email"],
        "to": parse_addrs(headers.get("To", "")),
        "cc": parse_addrs(headers.get("Cc", "")),
        "reply_to": parse_addrs(headers.get("Reply-To", "")),
        "subject": headers.get("Subject", ""),
        "snippet": msg.get("snippet", "") if not store_body else "",
        "labels": label_ids,
        "is_sent": "SENT" in label_ids,
        "is_draft": "DRAFT" in label_ids,
        "is_spam": "SPAM" in label_ids,
        "is_trash": "TRASH" in label_ids,
        "body_text": body_text,
        "body_html": body_html,
    }


def thread_summary(messages: list[dict]) -> dict:
    """Aggregate one thread's messages into the email_threads model."""
    msgs = sorted([m for m in messages if m.get("date")], key=lambda m: m["date"])
    participants = set()
    for m in messages:
        if m.get("from_email"):
            participants.add(m["from_email"])
        for p in m.get("to", []) + m.get("cc", []):
            participants.add(p["email"])
    return {
        "thread_id": messages[0]["thread_id"] if messages else "",
        "first_message_date": msgs[0]["date"] if msgs else "",
        "last_message_date": msgs[-1]["date"] if msgs else "",
        "message_count": len(messages),
        "participants": sorted(participants),
        "participant_count": len(participants),
        "subject": messages[0].get("subject", "") if messages else "",
        "duration_days": _days(msgs[0]["date"], msgs[-1]["date"]) if len(msgs) > 1 else 0,
    }


def _days(a: str, b: str) -> float:
    from datetime import datetime
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 86400
    except ValueError:
        return 0.0

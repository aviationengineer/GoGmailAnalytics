"""Analyze pipeline: raw metadata -> DuckDB -> contacts -> categories ->
analytics. Idempotent: reruns upsert by stable IDs, never duplicate."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from ..analytics import follow_up_for, health_score, importance_for
from ..career import extract as career_extract
from ..categorization import RuleBasedCategorizer, make_categorizer
from ..contacts import CONSUMER_DOMAINS, resolve
from ..database import Database
from ..nlp import contact_topics
from ..organizations import extract as org_extract
from ..parsing import parse_date, thread_summary
from ..relationships import build_graph

log = logging.getLogger("gmail-intel.pipeline")


def _normalize(r: dict) -> dict:
    """Accept both pipeline-native and legacy extractor record shapes."""
    if "thread_id" not in r and "threadId" in r:
        r["thread_id"] = r["threadId"]
    if "labels" not in r and "labelIds" in r:
        r["labels"] = r["labelIds"]
    if "is_sent" not in r:
        r["is_sent"] = "SENT" in r.get("labels", [])
    r.setdefault("to", [])
    r.setdefault("cc", [])
    r.setdefault("subject", "")
    # legacy extractor left RFC-2822 dates unparsed; normalize to ISO
    import re as _re
    if r.get("date") and not _re.match(r"^\d{4}-\d{2}-\d{2}", r["date"]):
        r["date"] = parse_date(r["date"])
    return r


def load_raw_meta(raw_dir: str, account: str) -> list[dict]:
    path = os.path.join(raw_dir, f"meta_{account}.jsonl")
    recs = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    recs.append(_normalize(json.loads(line)))
                except json.JSONDecodeError:
                    pass
    # Back-compat: earlier extractor wrote data/raw/meta.jsonl
    legacy = os.path.join(os.path.dirname(raw_dir), "meta.jsonl")
    if not recs and os.path.exists(legacy):
        with open(legacy, encoding="utf-8") as f:
            for line in f:
                try:
                    recs.append(_normalize(json.loads(line)))
                except json.JSONDecodeError:
                    pass
    return recs


def _label_names(raw_dir: str) -> dict:
    for name in ("labels.json", "labels_personal.json"):
        path = os.path.join(raw_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    legacy = os.path.join(os.path.dirname(raw_dir), "labels.json")
    if os.path.exists(legacy):
        with open(legacy, encoding="utf-8") as f:
            return json.load(f)
    return {}


def analyze(account: str, account_email: str, raw_dir: str, db: Database,
            config) -> dict:
    """Full analyze pass for one account. Returns summary counts."""
    recs = load_raw_meta(raw_dir, account)
    log.info("analyze: %d raw messages for %s", len(recs), account)
    if not recs:
        return {"emails": 0}

    for r in recs:
        r.setdefault("account", account)
    db.upsert_emails(recs)

    # Threads
    by_thread: dict[str, list] = {}
    for r in recs:
        by_thread.setdefault(r["thread_id"], []).append(r)
    thread_rows = []
    for tid, msgs in by_thread.items():
        s = thread_summary(msgs)
        thread_rows.append({
            "thread_id": tid, "account": account,
            "first_message_date": s["first_message_date"] or None,
            "last_message_date": s["last_message_date"] or None,
            "message_count": s["message_count"],
            "participants": json.dumps(s["participants"]),
            "participant_count": s["participant_count"],
            "subject": s["subject"], "duration_days": s["duration_days"],
        })
    db.replace_table("email_threads", thread_rows,
                     ["thread_id", "account", "first_message_date",
                      "last_message_date", "message_count", "participants",
                      "participant_count", "subject", "duration_days"])

    # Contacts
    own = {account_email.lower()}
    own |= {r["from_email"] for r in recs if r.get("is_sent") and r["from_email"]}
    contacts = resolve(recs, own)

    # Categorize (rule-based; AI only when privacy.enable_ai)
    label_names = _label_names(raw_dir)
    provider = "rule"
    if config.get("privacy", "enable_ai"):
        provider = config.get("ai", "provider", default="openai")
    categorizer = make_categorizer(
        provider if provider in ("rule", "openai") else "rule",
        label_names=label_names, consumer_domains=CONSUMER_DOMAINS)
    for c in contacts:
        cat = categorizer.categorize_contact(c)
        c["relationship_category"] = cat["category"]
        c["relationship_subcategory"] = cat["subcategory"]
        c["categorize_confidence"] = cat["confidence"]
        c["primary_topics"] = contact_topics(c.get("subjects", []))
    # Importance proxy from rank (user curates later)
    for i, c in enumerate(contacts):
        c["importance"] = importance_for(c, i / max(1, len(contacts)))

    # Analytics
    at = datetime.now(timezone.utc)
    follow_rows = []
    for c in contacts:
        scored = health_score(c, at)
        c.update({k: v for k, v in scored.items()
                  if k in ("health_score", "health_band")})
        c["communication_frequency"] = scored["frequency_band"]
        c["current_status"] = scored["lifecycle"]
        c["follow_up_required"] = False
        fu = follow_up_for(c, scored)
        if fu:
            c["follow_up_required"] = True
            follow_rows.append(fu)

    contact_rows = [{
        "contact_id": c["contact_id"], "full_name": c["full_name"],
        "primary_email": c["primary_email"],
        "alternate_emails": json.dumps(c["alternate_emails"]),
        "company": c.get("company", ""), "industry": "",
        "relationship_category": c.get("relationship_category", "Unknown"),
        "relationship_subcategory": c.get("relationship_subcategory", ""),
        "relationship_strength": health_score(c, at)["strength"],
        "importance": c["importance"],
        "first_communication": c["first_communication"] or None,
        "last_communication": c["last_communication"] or None,
        "communication_count": c["communication_count"],
        "incoming_count": c["incoming_count"], "outgoing_count": c["outgoing_count"],
        "thread_count": c["thread_count"],
        "communication_frequency": c["communication_frequency"],
        "current_status": c["current_status"],
        "primary_topics": json.dumps(c["primary_topics"]),
        "health_score": c["health_score"], "health_band": c["health_band"],
        "follow_up_required": c["follow_up_required"],
        "merge_confidence": c["merge_confidence"], "merge_reason": c["merge_reason"],
        "source": f"Gmail ({account_email})",
    } for c in contacts]
    db.replace_table("contacts", contact_rows, list(contact_rows[0].keys()))

    # Communications (one row per message, linked to best contact)
    email_to_cid = {}
    for c in contacts:
        for em in [c["primary_email"]] + c["alternate_emails"]:
            email_to_cid[em] = c["contact_id"]
    comm_rows = []
    for n, r in enumerate(recs):
        other = r["from_email"] if not r.get("is_sent") else ""
        if not other and r.get("to"):
            other = r["to"][0]["email"]
        cid = email_to_cid.get(other, "")
        parts = [r["from_email"]] + [p["email"] for p in r.get("to", [])]
        comm_rows.append({
            "communication_id": f"M{n:07d}", "contact_id": cid,
            "thread_id": r["thread_id"], "email_id": r["id"],
            "date": r["date"] or None, "communication_type": "Email",
            "direction": "outgoing" if r.get("is_sent") else "incoming",
            "subject": r.get("subject", ""),
            "participants": json.dumps(parts),
            "topic": (contact_topics([r.get("subject", "")], top_n=1) or [""])[0],
            "account": account,
        })
    db.replace_table("communications", comm_rows, list(comm_rows[0].keys()))

    orgs = org_extract(contacts)
    db.replace_table("organizations", orgs, list(orgs[0].keys()) if orgs else
                     ["organization_id", "organization_name", "domain",
                      "first_contact", "last_contact", "contact_count",
                      "communication_count"])

    career = career_extract(contacts)
    db.replace_table("career_history", career, ["contact_id", "company", "role",
                     "relationship", "first_seen", "last_seen",
                     "evidence_count", "confidence"])

    db.replace_table("follow_up", follow_rows,
                     ["contact_id", "last_contact_date", "days_since_contact",
                      "importance", "relationship_strength",
                      "historical_frequency", "follow_up_priority",
                      "recommended_action", "reason"])

    # Topics rollup
    topic_counts: dict[str, dict] = {}
    for c in contacts:
        for t in c["primary_topics"]:
            e = topic_counts.setdefault(t, {"mentions": 0, "contacts": set()})
            e["mentions"] += c["communication_count"]
            e["contacts"].add(c["contact_id"])
    db.replace_table("topics",
                     [{"topic": t, "mentions": e["mentions"],
                       "contact_count": len(e["contacts"])}
                      for t, e in topic_counts.items()],
                     ["topic", "mentions", "contact_count"])

    graph = build_graph(contacts, orgs)
    _write_data_quality(db, recs, contacts)

    summary = {"emails": len(recs), "threads": len(thread_rows),
               "contacts": len(contacts), "organizations": len(orgs),
               "follow_ups": len(follow_rows), "graph": graph}
    log.info("analyze summary: %s", {k: v for k, v in summary.items() if k != "graph"})
    return summary


def _write_data_quality(db: Database, recs: list[dict], contacts: list[dict]) -> None:
    no_subject = sum(1 for r in recs if not r.get("subject"))
    unknown_cat = sum(1 for c in contacts if c.get("relationship_category") == "Unknown")
    no_name = sum(1 for c in contacts if not c.get("full_name"))
    rows = [
        {"metric": "messages_missing_subject", "value": str(no_subject),
         "threshold": "<5%", "status": "ok" if not recs or no_subject / len(recs) < 0.05 else "warn"},
        {"metric": "contacts_unknown_category", "value": str(unknown_cat),
         "threshold": "<40%", "status": "ok" if not contacts or unknown_cat / len(contacts) < 0.4 else "warn"},
        {"metric": "contacts_missing_name", "value": str(no_name),
         "threshold": "<10%", "status": "ok" if not contacts or no_name / len(contacts) < 0.1 else "warn"},
        {"metric": "total_contacts", "value": str(len(contacts)),
         "threshold": "n/a", "status": "ok"},
    ]
    db.replace_table("data_quality", rows, ["metric", "value", "threshold", "status"])

"""Career intelligence: employers, recruiters, opportunities from signals."""
from __future__ import annotations

import logging
import re

log = logging.getLogger("gmail-intel.career")

JOB_SIGNAL = re.compile(
    r"interview|job application|offer letter|resume|\bcv\b|promotion|onboarding|"
    r"reference check|background check|hiring manager|job id|requisition",
    re.IGNORECASE)
RECRUITER_SIGNAL = re.compile(r"recruit|talent acquisition|headhunt|staffing", re.IGNORECASE)


def extract(contacts: list[dict]) -> list[dict]:
    """Evidence rows linking contacts to career signals."""
    rows = []
    for c in contacts:
        subjects = " ".join(c.get("subjects", []))
        signals = set()
        if JOB_SIGNAL.search(subjects):
            signals.add("job_opportunity")
        if RECRUITER_SIGNAL.search(subjects + " " + c.get("primary_email", "")):
            signals.add("recruiter")
        if c.get("relationship_category") == "Recruiter":
            signals.add("recruiter")
        for sig in signals:
            rows.append({
                "contact_id": c["contact_id"],
                "company": c.get("company", ""),
                "role": "",
                "relationship": sig,
                "first_seen": c.get("first_communication", ""),
                "last_seen": c.get("last_communication", ""),
                "evidence_count": c.get("communication_count", 0),
                "confidence": 0.7 if sig == "recruiter" else 0.55,
            })
    log.info("career evidence rows: %d", len(rows))
    return rows

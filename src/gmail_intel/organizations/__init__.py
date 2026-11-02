"""Organization intelligence: aggregate contacts by email domain."""
from __future__ import annotations

import logging
from collections import defaultdict

from ..contacts import CONSUMER_DOMAINS

log = logging.getLogger("gmail-intel.organizations")


def extract(contacts: list[dict]) -> list[dict]:
    orgs: dict[str, dict] = defaultdict(
        lambda: {"domains": set(), "contacts": [], "first": "", "last": "",
                 "communications": 0})
    for c in contacts:
        for em in [c["primary_email"]] + c.get("alternate_emails", []):
            domain = em.split("@", 1)[1] if "@" in em else ""
            if not domain or domain in CONSUMER_DOMAINS:
                continue
            o = orgs[domain]
            o["domains"].add(domain)
            o["contacts"].append(c["contact_id"])
            o["communications"] += c["communication_count"]
            if c.get("first_communication") and (not o["first"] or c["first_communication"] < o["first"]):
                o["first"] = c["first_communication"]
            if c.get("last_communication") and (not o["last"] or c["last_communication"] > o["last"]):
                o["last"] = c["last_communication"]
    out = []
    for i, (domain, o) in enumerate(
            sorted(orgs.items(), key=lambda kv: kv[1]["communications"], reverse=True), 1):
        name = domain.split(".")[0].replace("-", " ").title()
        out.append({
            "organization_id": f"ORG{i:05d}",
            "organization_name": name,
            "domain": domain,
            "first_contact": o["first"],
            "last_contact": o["last"],
            "contact_count": len(set(o["contacts"])),
            "communication_count": o["communications"],
        })
    log.info("extracted %d organizations", len(out))
    return out

"""Contact resolution engine.

Core rule: one email address is NOT one person. Addresses are clustered
into person records with union-find over:
  1. exact normalized email match (gmail dots/plus-tags folded),
  2. same display name + same local-part stem (john.smith@gmail.com and
     john.smith@company.com as "John Smith").

Every merge records merge_confidence and merge_reason. Low-confidence
candidates are never merged automatically: same-name/different-stem
pairs are left separate.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

log = logging.getLogger("gmail-intel.contacts")

CONSUMER_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.ca", "hotmail.com",
    "hotmail.ca", "outlook.com", "live.com", "live.ca", "msn.com", "aol.com",
    "icloud.com", "me.com", "mac.com", "protonmail.com", "proton.me",
    "zoho.com", "gmx.com", "ymail.com",
}


def norm_email(addr: str) -> str:
    addr = (addr or "").strip().lower()
    if "@" not in addr:
        return addr
    local, domain = addr.split("@", 1)
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    else:
        local = local.split("+", 1)[0]
    return f"{local}@{domain}"


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", (name or "").lower())).strip()


def local_stem(addr: str) -> str:
    local = addr.split("@", 1)[0] if "@" in addr else addr
    return re.sub(r"[^a-z]", "", local.lower())


class UnionFind:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        p = self.p.setdefault(x, x)
        if p != x:
            self.p[x] = self.find(p)
        return self.p[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def company_from_email(email: str) -> str:
    domain = email.split("@", 1)[1] if "@" in email else ""
    if not domain or domain in CONSUMER_DOMAINS:
        return ""
    parts = domain.split(".")
    core = parts[-2] if len(parts) >= 2 else domain
    return core.replace("-", " ").title()


def resolve(emails: list[dict], own_addresses: set[str]) -> list[dict]:
    """Cluster parsed email records into person dicts."""
    uf = UnionFind()
    email_to_name: dict[str, Counter] = {}

    def consider(addr: str, name: str):
        em = norm_email(addr)
        if not em or "@" not in em or em in own_addresses:
            return
        uf.find(("e", em))
        if name and len(name) >= 2:
            email_to_name.setdefault(em, Counter())[name] += 1

    for r in emails:
        consider(r["from_email"], r["from_name"])
        for p in r.get("to", []) + r.get("cc", []):
            consider(p["email"], p["name"])

    # Merge same display name + same local-part stem across different emails.
    name_groups: dict[tuple, list] = defaultdict(list)
    for em, names in email_to_name.items():
        best = names.most_common(1)[0][0]
        nk = name_key(best)
        if len(nk) >= 4:
            name_groups[(nk, local_stem(em))].append(em)
    merges = 0
    for group in name_groups.values():
        for em in group[1:]:
            uf.union(("e", group[0]), ("e", em))
            merges += 1
    log.info("name-stem merges: %d", merges)

    people: dict = {}
    for r in emails:
        dt = r.get("date") or ""
        outgoing = r["from_email"] in own_addresses
        parts = ([("from", {"name": r["from_name"], "email": r["from_email"]})]
                 + [("to", p) for p in r.get("to", [])]
                 + [("cc", p) for p in r.get("cc", [])])
        for role, p in parts:
            em = norm_email(p["email"])
            if not em or "@" not in em or em in own_addresses:
                continue
            pid = uf.find(("e", em))
            person = people.setdefault(pid, {
                "emails": Counter(), "names": Counter(), "first": "",
                "last": "", "count": 0, "in": 0, "out": 0,
                "threads": set(), "subjects": [], "labels": Counter(),
                "merged": False,
            })
            person["emails"][em] += 1
            if p["name"]:
                person["names"][p["name"]] += 1
            person["count"] += 1
            if outgoing:
                if role != "from":
                    person["out"] += 1
            else:
                person["in"] += 1
            if dt:
                if not person["first"] or dt < person["first"]:
                    person["first"] = dt
                if not person["last"] or dt > person["last"]:
                    person["last"] = dt
            person["threads"].add(r["thread_id"])
            if r.get("subject"):
                person["subjects"].append(r["subject"])
            for lb in r.get("labels", []):
                person["labels"][lb] += 1

    contacts = []
    for pid, p in people.items():
        emails_sorted = [e for e, _ in p["emails"].most_common()]
        name = p["names"].most_common(1)[0][0] if p["names"] else ""
        if not name:
            name = emails_sorted[0].split("@")[0].replace(".", " ").replace("_", " ").title()
        merged = len(emails_sorted) > 1
        contacts.append({
            "person_key": pid[1],
            "full_name": name,
            "primary_email": emails_sorted[0],
            "alternate_emails": emails_sorted[1:],
            "company": company_from_email(emails_sorted[0]),
            "first_communication": p["first"],
            "last_communication": p["last"],
            "communication_count": p["count"],
            "incoming_count": p["in"],
            "outgoing_count": p["out"],
            "thread_count": len(p["threads"]),
            "subjects": p["subjects"],
            "label_counts": dict(p["labels"]),
            "merge_confidence": 0.95 if merged else 1.0,
            "merge_reason": ("same display name + email local-part stem"
                             if merged else "single address"),
        })
    contacts.sort(key=lambda c: c["communication_count"], reverse=True)
    for i, c in enumerate(contacts, 1):
        c["contact_id"] = f"C{i:06d}"
    log.info("resolved %d contacts", len(contacts))
    return contacts

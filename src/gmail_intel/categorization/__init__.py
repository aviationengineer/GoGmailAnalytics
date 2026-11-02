"""Categorization: controlled taxonomies + rule-based categorizer +
AI provider abstraction (the system works fully without any LLM).

RuleBasedCategorizer uses Gmail user labels, sender patterns and domains.
OpenAICategorizer calls the registered custom.openai connector (only when
privacy.enable_ai is true and only on allowed fields).
"""
from __future__ import annotations

import abc
import json
import logging
import os
import re
import subprocess

log = logging.getLogger("gmail-intel.categorization")

RELATIONSHIP_CATEGORIES = [
    "Family", "Friend", "Professional", "Current Colleague", "Former Colleague",
    "Manager", "Executive", "Customer", "Vendor", "Partner", "Recruiter",
    "University", "Government", "Professional Association", "Community",
    "Automated", "Newsletter", "Unknown",
]
RELATIONSHIP_SUBCATEGORIES = [
    "Former Manager", "Former Direct Report", "Peer", "Industry Contact",
    "Recruiter", "Hiring Manager", "Professor", "Classmate", "Client",
    "Consultant", "Supplier", "",
]
STRENGTH_LABELS = {1: "Very Weak", 2: "Weak", 3: "Acquaintance", 4: "Good",
                   5: "Strong", 6: "Very Strong"}
COMMUNICATION_TYPES = [
    "Email", "Meeting", "Introduction", "Recruiting", "Career", "Project",
    "Administrative", "Personal", "Networking", "Newsletter", "Automated",
    "Notification", "Transaction", "Travel", "Finance", "Education", "Other",
]
LIFECYCLE = ["New", "Active", "Maintained", "Dormant", "Reactivated", "Archived"]

AUTO_SENDERS = ("noreply", "no-reply", "donotreply", "do-not-reply", "newsletter",
                "notifications", "notify", "alerts", "support", "billing",
                "accounts", "service", "team", "info", "hello", "mailer-daemon",
                "postmaster")
RECRUIT_HINTS = ("recruit", "talent acquisition", "hiring", "job opportunity",
                 "career opportunity", "headhunt")


class CategorizationProvider(abc.ABC):
    @abc.abstractmethod
    def categorize_contact(self, contact: dict) -> dict:
        """Return {category, subcategory, confidence, reason}."""

    @abc.abstractmethod
    def extract_topics(self, text: str) -> list[str]:
        """Return topic labels for a subject/snippet."""


class RuleBasedCategorizer(CategorizationProvider):
    """Deterministic categorizer from labels, sender patterns and domains."""

    def __init__(self, label_names: dict | None = None,
                 consumer_domains: set | None = None):
        self.label_names = label_names or {}
        self.consumer_domains = consumer_domains or set()

    def categorize_contact(self, contact: dict) -> dict:
        email = contact["primary_email"]
        local = email.split("@", 1)[0] if "@" in email else ""
        name = contact["full_name"]
        label_text = " ".join(
            self.label_names.get(lb, "") for lb in contact.get("label_counts", {}))
        lt = label_text.lower()

        if any(s in local for s in AUTO_SENDERS):
            return {"category": "Automated", "subcategory": "",
                    "confidence": 0.9, "reason": "automated sender address"}
        if "newsletter" in lt or "news" in local:
            return {"category": "Newsletter", "subcategory": "",
                    "confidence": 0.8, "reason": "newsletter pattern"}
        if any(h in (name + " " + email).lower() for h in RECRUIT_HINTS):
            return {"category": "Recruiter", "subcategory": "Recruiter",
                    "confidence": 0.7, "reason": "recruiting keywords"}
        if re.search(r"friend", lt):
            return {"category": "Friend", "subcategory": "",
                    "confidence": 0.85, "reason": "user 'Friends' label"}
        if re.search(r"famil|mom|dad|mother|father|brother|sister|wife|husband|son\b|daughter", lt):
            return {"category": "Family", "subcategory": "",
                    "confidence": 0.8, "reason": "family label/name pattern"}
        domain = email.split("@", 1)[1] if "@" in email else ""
        if domain.endswith(".edu"):
            return {"category": "University", "subcategory": "",
                    "confidence": 0.8, "reason": "education domain"}
        if domain.endswith(".gov") or domain.endswith(".gc.ca"):
            return {"category": "Government", "subcategory": "",
                    "confidence": 0.8, "reason": "government domain"}
        if domain and domain not in self.consumer_domains:
            return {"category": "Professional", "subcategory": "",
                    "confidence": 0.6, "reason": "corporate domain"}
        if contact.get("thread_count", 0) >= 3:
            return {"category": "Friend", "subcategory": "",
                    "confidence": 0.5, "reason": "sustained personal-domain exchange"}
        return {"category": "Unknown", "subcategory": "",
                "confidence": 0.3, "reason": "no signal"}

    def extract_topics(self, text: str) -> list[str]:
        topics = []
        low = (text or "").lower()
        for topic, hints in TOPIC_HINTS.items():
            if any(h in low for h in hints):
                topics.append(topic)
        return topics


TOPIC_HINTS = {
    "Aviation": ["aviation", "airline", "aircraft", "airport", "flight", "aerospace", "iata"],
    "MRO": ["mro", "maintenance", "repair", "overhaul"],
    "Data Engineering": ["data engineer", "data platform", "etl", "pipeline", "spark", "airflow"],
    "AI": ["artificial intelligence", "machine learning", " ml ", "ai ", "llm", "gpt"],
    "Career": ["interview", "job application", "offer letter", "resume", "cv ", "promotion"],
    "Recruitment": ["recruiter", "hiring", "job opportunity", "talent"],
    "Finance": ["invoice", "payment", "bank", "insurance", "tax"],
    "Travel": ["booking", "itinerary", "hotel", "boarding pass", "visa"],
    "Education": ["university", "course", "school", "professor", "degree", "student"],
    "Government": ["immigration", "permit", "c CRA ", "service canada"],
    "Family": ["family"],
    "Technology": ["software", "cloud", "api", "database", "devops"],
}


class OpenAICategorizer(CategorizationProvider):
    """LLM categorizer through the registered custom.openai connector.

    Only used when privacy.enable_ai is true. Never receives bodies, only
    the allowed fields (subject/snippet/topics).
    """

    def __init__(self, model: str = "gpt-4o-mini", helper: str | None = None):
        self.model = model
        self.helper = helper or os.environ.get(
            "GMAIL_INTEL_OPENAI_HELPER",
            os.path.expanduser(
                "~/workspace/custom-connectors/custom.openai/bin/openai_api.py"))

    def _chat(self, messages: list[dict]) -> str:
        import os as _os
        if not _os.path.isfile(self.helper):
            raise RuntimeError(
                "OpenAI connector helper not found; set GMAIL_INTEL_OPENAI_HELPER "
                "or use the rule-based categorizer")
        proc = subprocess.run(
            ["python3", self.helper, "chat", "--model", self.model,
             "--temperature", "0"],
            input=json.dumps(messages).encode(), capture_output=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode()[:300])
        return proc.stdout.decode().strip()

    def categorize_contact(self, contact: dict) -> dict:
        cats = ", ".join(RELATIONSHIP_CATEGORIES)
        prompt = (
            "Categorize this email contact. Reply with JSON only: "
            '{"category": "<one of: ' + cats + '>", '
            '"confidence": 0.0-1.0, "reason": "short reason"}. '
            f"Name: {contact['full_name']}, email: {contact['primary_email']}, "
            f"company: {contact.get('company', '')}, "
            f"messages: {contact.get('communication_count', 0)}."
        )
        try:
            data = json.loads(self._chat([{"role": "user", "content": prompt}]))
            return {"category": data.get("category", "Unknown"), "subcategory": "",
                    "confidence": float(data.get("confidence", 0.5)),
                    "reason": f"llm:{data.get('reason','')}"}
        except (ValueError, RuntimeError) as exc:
            log.warning("LLM categorization failed, falling back: %s", exc)
            return RuleBasedCategorizer().categorize_contact(contact)

    def extract_topics(self, text: str) -> list[str]:
        return RuleBasedCategorizer().extract_topics(text)


class LocalLLMCategorizer(CategorizationProvider):
    def __init__(self, *a, **k):
        raise NotImplementedError("local LLM backend not configured")

    def categorize_contact(self, contact: dict) -> dict:  # pragma: no cover
        raise NotImplementedError

    def extract_topics(self, text: str) -> list[str]:  # pragma: no cover
        raise NotImplementedError


class GeminiCategorizer(CategorizationProvider):
    def __init__(self, *a, **k):
        raise NotImplementedError("gemini backend not configured")

    def categorize_contact(self, contact: dict) -> dict:  # pragma: no cover
        raise NotImplementedError

    def extract_topics(self, text: str) -> list[str]:  # pragma: no cover
        raise NotImplementedError


def make_categorizer(provider: str, **kwargs) -> CategorizationProvider:
    if provider == "rule":
        return RuleBasedCategorizer(**kwargs)
    if provider == "openai":
        return OpenAICategorizer(**kwargs)
    if provider == "local":
        return LocalLLMCategorizer(**kwargs)
    if provider == "gemini":
        return GeminiCategorizer(**kwargs)
    raise ValueError(f"unknown categorizer provider: {provider}")

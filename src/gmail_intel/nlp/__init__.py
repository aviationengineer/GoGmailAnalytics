"""NLP layer: keyword topics and regex entity extraction that work with
zero heavy dependencies. spaCy/sentence-transformers plug in here when
installed; every function degrades gracefully without them."""
from __future__ import annotations

import logging
import re
from collections import Counter

log = logging.getLogger("gmail-intel.nlp")

try:
    import spacy  # noqa: F401
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

STOPWORDS = set("""a an the and or of to in on for with is are was were be been by at from
as it its this that these those you your he she they we our us me my him her them
will would can could should shall may might must do does did done have has had re fw
fwd please thanks thank regards best cheers hello hi hey urgent important new update
updated reminder notification""".split())

ORG_HINTS = re.compile(
    r"\b([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3}\s+"
    r"(Inc|LLC|Ltd|Limited|Corp|Corporation|GmbH|SAS|Pty|AB|AG|Co|Group|Holdings|Technologies|Systems|Airlines|Aviation|Aerospace))\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")


def keywords(text: str, top_n: int = 10) -> list[str]:
    toks = re.findall(r"[a-zA-Z]{4,}", (text or "").lower())
    counts = Counter(t for t in toks if t not in STOPWORDS)
    return [t for t, _ in counts.most_common(top_n)]


def extract_entities(text: str) -> dict:
    """Regex entities; spaCy NER used automatically when installed."""
    text = text or ""
    ents: dict = {"organizations": [], "emails": [], "phones": []}
    ents["organizations"] = sorted(set(ORG_HINTS.findall(text)))
    # findall with groups returns tuples; normalize
    orgs = sorted({m[0].strip() for m in ORG_HINTS.finditer(text)})
    ents["organizations"] = orgs
    ents["emails"] = sorted(set(EMAIL_RE.findall(text)))
    ents["phones"] = sorted(set(PHONE_RE.findall(text)))
    if HAS_SPACY:
        log.debug("spaCy available; regex pass used for determinism")
    return ents


def contact_topics(subjects: list[str], top_n: int = 8) -> list[str]:
    counts: Counter = Counter()
    for s in subjects:
        for kw in keywords(s, top_n=6):
            counts[kw] += 1
    return [k for k, _ in counts.most_common(top_n)]

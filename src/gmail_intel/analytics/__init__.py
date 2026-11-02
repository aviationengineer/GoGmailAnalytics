"""Communication analytics: frequency, recency, relationship health,
follow-up intelligence. All scores are explainable: component values are
stored alongside the final score."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("gmail-intel.analytics")


def _parse(iso: str):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def frequency_band(count: int, days_span: float) -> tuple[str, float]:
    """Band + messages-per-year from historical intervals."""
    if days_span <= 0 or count <= 1:
        return ("Rare", 0.0)
    per_year = count / (days_span / 365.25)
    if per_year >= 300:
        return ("Daily", per_year)
    if per_year >= 40:
        return ("Weekly", per_year)
    if per_year >= 18:
        return ("Biweekly", per_year)
    if per_year >= 9:
        return ("Monthly", per_year)
    if per_year >= 3.5:
        return ("Quarterly", per_year)
    if per_year >= 1.5:
        return ("Semiannual", per_year)
    if per_year >= 0.7:
        return ("Annual", per_year)
    return ("Rare", per_year)


def strength_score(count: int, two_way: bool, threads: int) -> int:
    """1-6 relationship strength from volume and reciprocity."""
    if count >= 100 and two_way:
        return 6
    if count >= 40 and two_way:
        return 5
    if count >= 12:
        return 4
    if count >= 4:
        return 3
    if count >= 2:
        return 2
    return 1


def health_score(contact: dict, at: datetime | None = None) -> dict:
    """Weighted, explainable 0-100 score.

    30% recency + 25% frequency + 20% strength + 15% importance + 10% responsiveness.
    """
    at = at or now_utc()
    last = _parse(contact.get("last_communication", ""))
    first = _parse(contact.get("first_communication", ""))
    days_since = (at - last).days if last else 9999
    span_days = (last - first).days if (last and first) else 0
    count = contact.get("communication_count", 0)
    two_way = contact.get("incoming_count", 0) > 0 and contact.get("outgoing_count", 0) > 0

    if days_since < 30:
        recency = 30
    elif days_since < 90:
        recency = 24
    elif days_since < 180:
        recency = 17
    elif days_since < 365:
        recency = 10
    elif days_since < 730:
        recency = 5
    else:
        recency = 0

    band, per_year = frequency_band(count, span_days)
    frequency = min(25, per_year / 4) if per_year else (3 if count else 0)

    strength = strength_score(count, two_way, contact.get("thread_count", 0))
    strength_pts = {1: 4, 2: 8, 3: 12, 4: 15, 5: 18, 6: 20}[strength]

    importance = contact.get("importance", "Unknown")
    importance_pts = {"High": 15, "Medium": 9, "Low": 4}.get(importance, 6)

    responsiveness = 10 if two_way else (5 if count >= 3 else 0)

    total = round(recency + frequency + strength_pts + importance_pts + responsiveness, 1)
    band_label = ("Strong" if total >= 90 else "Healthy" if total >= 75
                  else "Maintain" if total >= 50 else "At risk" if total >= 25
                  else "Dormant")
    return {
        "health_score": total,
        "health_band": band_label,
        "recency_pts": recency,
        "frequency_pts": round(frequency, 1),
        "strength_pts": strength_pts,
        "importance_pts": importance_pts,
        "responsiveness_pts": responsiveness,
        "days_since_contact": days_since,
        "frequency_band": band,
        "strength": strength,
        "lifecycle": ("Dormant" if days_since > 365 else
                      "Active" if days_since < 90 else "Maintained"),
    }


def follow_up_for(contact: dict, scored: dict) -> dict | None:
    """Return a follow-up record, or None when no action is warranted."""
    importance = contact.get("importance", "Unknown")
    days = scored["days_since_contact"]
    strength = scored["strength"]
    band = scored["frequency_band"]

    # High-value + long silence = candidate.
    if importance == "High" and days >= 180:
        priority, action = "P1", "Reconnect"
    elif strength >= 4 and days >= 365 and band in ("Weekly", "Biweekly", "Monthly"):
        priority, action = "P2", "Rekindle"
    elif days >= 730 and strength >= 3:
        priority, action = "P3", "Check in"
    else:
        return None
    return {
        "contact_id": contact["contact_id"],
        "last_contact_date": contact.get("last_communication", ""),
        "days_since_contact": days,
        "importance": importance,
        "relationship_strength": strength,
        "historical_frequency": band,
        "follow_up_priority": priority,
        "recommended_action": action,
        "reason": (f"Historically {band.lower()} contact (strength {strength}/6); "
                   f"no communication for {days} days."),
    }


def importance_for(contact: dict, rank_pct: float) -> str:
    """Proxy importance from network rank until the user curates it."""
    if contact.get("relationship_category") in ("Family",):
        return "High"
    if rank_pct <= 0.05:
        return "High"
    if rank_pct <= 0.30:
        return "Medium"
    return "Low"

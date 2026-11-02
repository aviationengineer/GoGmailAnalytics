"""Analytics tests: frequency bands and health scoring."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone, timedelta
from gmail_intel.analytics import frequency_band, health_score


def _contact(days_ago=10, count=50, two_way=True, importance="High"):
    now = datetime.now(timezone.utc)
    last = (now - timedelta(days=days_ago)).isoformat()
    first = (now - timedelta(days=400)).isoformat()
    return {"contact_id": "C000001", "first_communication": first,
            "last_communication": last, "communication_count": count,
            "incoming_count": count // 2 if two_way else count,
            "outgoing_count": count // 2 if two_way else 0,
            "thread_count": 10, "importance": importance}


def test_frequency_band_monthly():
    band, per_year = frequency_band(24, 730)
    assert band == "Monthly"


def test_health_score_recent_strong():
    s = health_score(_contact(days_ago=5, count=120))
    assert s["health_score"] >= 75
    assert s["health_band"] in ("Strong", "Healthy")


def test_health_score_dormant():
    s = health_score(_contact(days_ago=900, count=3, two_way=False, importance="Low"))
    assert s["health_band"] == "Dormant"
    assert s["lifecycle"] == "Dormant"


def test_health_score_explainable():
    s = health_score(_contact())
    parts = (s["recency_pts"] + s["frequency_pts"] + s["strength_pts"] +
             s["importance_pts"] + s["responsiveness_pts"])
    assert abs(parts - s["health_score"]) < 0.2

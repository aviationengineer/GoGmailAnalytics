"""Dashboard data preparation (real) + Streamlit app stub.

data_for_dashboard(db) returns every dataset the Streamlit pages need, so
the dashboard is a thin presentation layer. Streamlit itself is optional:
install it to run `gmail-intel dashboard`.
"""
from __future__ import annotations

import logging

log = logging.getLogger("gmail-intel.dashboard")


def data_for_dashboard(db) -> dict:
    df = db.df
    return {
        "overview": dict(db.query(
            "SELECT 'total_contacts', COUNT(*) FROM contacts UNION ALL "
            "SELECT 'active', COUNT(*) FROM contacts WHERE current_status='Active' UNION ALL "
            "SELECT 'dormant', COUNT(*) FROM contacts WHERE current_status='Dormant' UNION ALL "
            "SELECT 'high_priority', COUNT(*) FROM contacts WHERE importance='High' UNION ALL "
            "SELECT 'emails', COUNT(*) FROM emails UNION ALL "
            "SELECT 'organizations', COUNT(*) FROM organizations UNION ALL "
            "SELECT 'follow_ups', COUNT(*) FROM follow_up")),
        "health_bands": df(
            "SELECT health_band, COUNT(*) n FROM contacts GROUP BY 1").to_dict("records"),
        "emails_by_year": df(
            "SELECT YEAR(date) y, COUNT(*) n FROM emails WHERE date IS NOT NULL "
            "GROUP BY 1 ORDER BY 1").to_dict("records"),
        "direction": df(
            "SELECT direction, COUNT(*) n FROM emails GROUP BY 1").to_dict("records"),
        "top_contacts": df(
            "SELECT full_name, primary_email, communication_count, health_band, "
            "last_communication FROM contacts ORDER BY communication_count DESC "
            "LIMIT 25").to_dict("records"),
        "top_orgs": df(
            "SELECT organization_name, contact_count, communication_count "
            "FROM organizations ORDER BY communication_count DESC LIMIT 25").to_dict("records"),
        "topics": df(
            "SELECT topic, mentions FROM topics ORDER BY mentions DESC LIMIT 25").to_dict("records"),
        "follow_ups": df(
            "SELECT * FROM follow_up ORDER BY follow_up_priority LIMIT 100").to_dict("records"),
    }


def run_app(db_path: str, port: int = 8501):  # pragma: no cover
    try:
        import streamlit  # noqa: F401
    except ImportError:
        raise RuntimeError("streamlit is not installed; pip install streamlit to run the dashboard")
    raise NotImplementedError("Streamlit pages stub: use data_for_dashboard() to build them")

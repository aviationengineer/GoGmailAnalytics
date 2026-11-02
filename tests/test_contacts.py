"""Contact resolution tests: one person, many addresses."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gmail_intel.contacts import resolve, norm_email


def _rec(frm, frm_name, mid):
    return {"id": mid, "thread_id": "t" + mid, "date": "2024-01-01T00:00:00+00:00",
            "from_email": frm, "from_name": frm_name, "to": [], "cc": [],
            "subject": "hi", "labels": [], "is_sent": False}


def test_gmail_dots_fold():
    assert norm_email("John.Smith@gmail.com") == norm_email("johnsmith@gmail.com")


def test_same_person_two_emails_merge():
    recs = [
        _rec("john.smith@gmail.com", "John Smith", "m1"),
        _rec("john.smith@company.com", "John Smith", "m2"),
    ]
    contacts = resolve(recs, set())
    assert len(contacts) == 1
    got = set(contacts[0]["alternate_emails"] + [contacts[0]["primary_email"]])
    # gmail dots are folded by normalization (by design)
    assert got == {"johnsmith@gmail.com", "john.smith@company.com"}
    assert contacts[0]["merge_reason"].startswith("same display name")


def test_same_name_different_stem_stays_split():
    recs = [
        _rec("john.smith@gmail.com", "John Smith", "m1"),
        _rec("jsmith99@other.com", "John Smith", "m2"),
    ]
    contacts = resolve(recs, set())
    assert len(contacts) == 2  # low confidence: never auto-merge


def test_own_addresses_excluded():
    recs = [_rec("me@gmail.com", "Me", "m1"), _rec("a@x.com", "A", "m2")]
    contacts = resolve(recs, {"me@gmail.com"})
    assert all(c["primary_email"] != "me@gmail.com" for c in contacts)

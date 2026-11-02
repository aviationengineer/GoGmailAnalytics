"""Excel export: formatted workbook with filters, frozen headers,
conditional formatting, summary sheet and data dictionary."""
from __future__ import annotations

import json
import logging
import os

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

log = logging.getLogger("gmail-intel.exports")

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
BAND_FILL = PatternFill("solid", fgColor="D6E4F0")


def _style_sheet(ws, widths: dict[int, int] | None = None):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    if widths:
        for idx, w in widths.items():
            ws.column_dimensions[get_column_letter(idx)].width = w


def _add_table(ws, columns: list[str], rows: list[list], widths=None):
    ws.append(columns)
    for r in rows:
        ws.append([("" if v is None else v) for v in r])
    _style_sheet(ws, widths)


def export_excel(db, path: str, max_history_rows: int = 20000) -> str:
    """Build gmail_relationship_intelligence.xlsx from the database."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = Workbook()

    # SUMMARY
    ws = wb.active
    ws.title = "SUMMARY"
    stats = dict(db.query(
        "SELECT 'contacts', COUNT(*) FROM contacts UNION ALL "
        "SELECT 'emails', COUNT(*) FROM emails UNION ALL "
        "SELECT 'threads', COUNT(*) FROM email_threads UNION ALL "
        "SELECT 'organizations', COUNT(*) FROM organizations UNION ALL "
        "SELECT 'follow_ups', COUNT(*) FROM follow_up"))
    ws.append(["Metric", "Value"])
    for k, v in stats.items():
        ws.append([k.replace("_", " ").title(), v])
    ws.append([])
    ws.append(["Health band", "Contacts"])
    for band, n in db.query(
            "SELECT health_band, COUNT(*) FROM contacts GROUP BY 1 ORDER BY 2 DESC"):
        ws.append([band, n])
    _style_sheet(ws, {1: 28, 2: 16})

    # CONTACT_MASTER
    cols = ["contact_id", "full_name", "primary_email", "alternate_emails",
            "company", "relationship_category", "relationship_subcategory",
            "relationship_strength", "importance", "first_communication",
            "last_communication", "communication_count", "incoming_count",
            "outgoing_count", "thread_count", "communication_frequency",
            "current_status", "primary_topics", "health_score", "health_band",
            "follow_up_required", "merge_confidence", "merge_reason", "source"]
    rows = db.df(f"SELECT {','.join(cols)} FROM contacts ORDER BY communication_count DESC")
    ws = wb.create_sheet("CONTACT_MASTER")
    _add_table(ws, cols, rows.values.tolist(), {2: 26, 3: 34, 4: 30, 6: 20})
    ws.conditional_formatting.add(
        f"S2:S{ws.max_row}",
        CellIsRule(operator="greaterThan", formula=["75"], fill=BAND_FILL))

    # COMMUNICATION_HISTORY (capped for Excel sanity)
    cols = ["communication_id", "contact_id", "date", "direction", "subject",
            "topic", "thread_id"]
    rows = db.df(f"SELECT {','.join(cols)} FROM communications ORDER BY date DESC "
                 f"LIMIT {max_history_rows}")
    ws = wb.create_sheet("COMMUNICATION_HISTORY")
    _add_table(ws, cols, rows.values.tolist(), {5: 60})

    # FOLLOW_UP
    cols = ["contact_id", "last_contact_date", "days_since_contact", "importance",
            "relationship_strength", "historical_frequency", "follow_up_priority",
            "recommended_action", "reason"]
    rows = db.df(f"SELECT {','.join(cols)} FROM follow_up "
                 "ORDER BY follow_up_priority, days_since_contact DESC")
    ws = wb.create_sheet("FOLLOW_UP")
    _add_table(ws, cols, rows.values.tolist(), {9: 70})

    # ORGANIZATIONS
    cols = ["organization_id", "organization_name", "domain", "first_contact",
            "last_contact", "contact_count", "communication_count"]
    rows = db.df(f"SELECT {','.join(cols)} FROM organizations "
                 "ORDER BY communication_count DESC")
    ws = wb.create_sheet("ORGANIZATIONS")
    _add_table(ws, cols, rows.values.tolist(), {2: 28})

    # CATEGORIZATION (controlled vocabularies)
    from ..categorization import (COMMUNICATION_TYPES, LIFECYCLE,
                                  RELATIONSHIP_CATEGORIES,
                                  RELATIONSHIP_SUBCATEGORIES, STRENGTH_LABELS)
    ws = wb.create_sheet("CATEGORIZATION")
    ws.append(["Relationship categories"])
    for c in RELATIONSHIP_CATEGORIES:
        ws.append([c])
    ws.append([])
    ws.append(["Relationship subcategories"])
    for c in RELATIONSHIP_SUBCATEGORIES:
        ws.append([c])
    ws.append([])
    ws.append(["Strength scale"])
    for k, v in STRENGTH_LABELS.items():
        ws.append([f"{k} - {v}"])
    ws.append([])
    ws.append(["Communication types"])
    for c in COMMUNICATION_TYPES:
        ws.append([c])
    ws.append([])
    ws.append(["Lifecycle"])
    for c in LIFECYCLE:
        ws.append([c])
    ws.append([])
    ws.append(["Health score = 30% recency + 25% frequency + 20% strength + "
               "15% importance + 10% responsiveness (0-100). Bands: 90-100 Strong, "
               "75-89 Healthy, 50-74 Maintain, 25-49 At risk, 0-24 Dormant."])
    _style_sheet(ws, {1: 60})

    # DATA_DICTIONARY
    from ..sheets import data_dictionary
    dd = data_dictionary()
    ws = wb.create_sheet("DATA_DICTIONARY")
    _add_table(ws, list(dd[0].keys()), [[d[k] for k in dd[0]] for d in dd],
               {3: 50, 7: 50})

    wb.save(path)
    log.info("excel written: %s", path)
    return path

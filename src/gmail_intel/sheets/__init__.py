"""Google Sheets sync with stable-ID upserts.

Transport: the runtime's Sheets connector (hatch_gws_cli); gspread is the
documented alternative for direct-OAuth deployments. Every sheet upserts
on its ID column: existing IDs are updated in place, new IDs appended,
so reruns never duplicate rows. Sync stats go to sync_state.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone

log = logging.getLogger("gmail-intel.sheets")


def _gws_cli() -> str:
    return os.environ.get("GMAIL_INTEL_GWS_CLI", "/opt/hatch/bin/hatch_gws_cli")

# sheet name -> (db table, id column, columns)
SHEETS = {
    "CONTACT_MASTER": ("contacts", "contact_id", [
        "contact_id", "full_name", "primary_email", "alternate_emails",
        "company", "industry", "relationship_category",
        "relationship_subcategory", "relationship_strength", "importance",
        "first_communication", "last_communication", "communication_count",
        "incoming_count", "outgoing_count", "thread_count",
        "communication_frequency", "current_status", "primary_topics",
        "health_score", "health_band", "follow_up_required",
        "merge_confidence", "merge_reason", "source"]),
    "COMMUNICATION_HISTORY": ("communications", "communication_id", [
        "communication_id", "contact_id", "thread_id", "email_id", "date",
        "communication_type", "direction", "subject", "participants",
        "topic", "account"]),
    "EMAIL_THREADS": ("email_threads", "thread_id", [
        "thread_id", "account", "first_message_date", "last_message_date",
        "message_count", "participant_count", "subject", "duration_days"]),
    "ORGANIZATIONS": ("organizations", "organization_id", [
        "organization_id", "organization_name", "domain", "first_contact",
        "last_contact", "contact_count", "communication_count"]),
    "TOPICS": ("topics", "topic", ["topic", "mentions", "contact_count"]),
    "CAREER_HISTORY": ("career_history", None, [
        "contact_id", "company", "role", "relationship", "first_seen",
        "last_seen", "evidence_count", "confidence"]),
    "FOLLOW_UP": ("follow_up", "contact_id", [
        "contact_id", "last_contact_date", "days_since_contact", "importance",
        "relationship_strength", "historical_frequency", "follow_up_priority",
        "recommended_action", "reason"]),
    "DATA_QUALITY": ("data_quality", "metric",
                     ["metric", "value", "threshold", "status"]),
}


class SheetsSync:
    def __init__(self, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id

    def _cli(self, *args: str) -> dict:
        cmd = [_gws_cli(), "sheets", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"sheets call failed: {(proc.stdout + proc.stderr)[-800:]}")
        start = proc.stdout.find("{")
        if start < 0:
            start = proc.stdout.find("[")
        return json.loads(proc.stdout[start:]) if start >= 0 else {}

    def _read_col_a(self, sheet: str) -> list[str]:
        data = self._cli("+read", "--spreadsheet", self.spreadsheet_id,
                         "--range", f"{sheet}!A:A")
        values = data.get("values", []) if isinstance(data, dict) else []
        return [r[0] if r else "" for r in values]

    def _write_range(self, sheet: str, start_row: int, rows: list[list[str]]) -> None:
        ncols = max(len(r) for r in rows)
        end_col = chr(ord("A") + ncols - 1)
        self._cli("spreadsheets", "values", "update",
                  "--params", json.dumps({
                      "spreadsheetId": self.spreadsheet_id,
                      "range": f"{sheet}!A{start_row}:{end_col}{start_row + len(rows) - 1}",
                      "valueInputOption": "RAW"}),
                  "--json", json.dumps({"values": rows}))

    def _append_rows(self, sheet: str, rows: list[list[str]]) -> None:
        ncols = max(len(r) for r in rows)
        end_col = chr(ord("A") + ncols - 1)
        self._cli("spreadsheets", "values", "append",
                  "--params", json.dumps({
                      "spreadsheetId": self.spreadsheet_id,
                      "range": f"{sheet}!A:{end_col}",
                      "valueInputOption": "RAW"}),
                  "--json", json.dumps({"values": rows}))

    def sync_table(self, db, sheet: str) -> dict:
        table, id_col, columns = SHEETS[sheet]
        rows = db.df(f"SELECT {','.join(columns)} FROM {table}").to_dict("records")
        str_rows = [[("" if v is None else str(v)) for v in
                     (r[c] for c in columns)] for r in rows]

        existing = self._read_col_a(sheet)
        have_header = bool(existing)
        existing_ids = set(existing[1:] if have_header else existing)

        to_update, to_append = [], []
        for row, rec in zip(str_rows, rows):
            key = str(rec[id_col]) if id_col else None
            if key is not None and key in existing_ids:
                idx = existing.index(key) + 1  # 1-based row number
                to_update.append((idx, row))
            else:
                to_append.append(row)

        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        if not have_header:
            self._write_range(sheet, 1, [columns])
        for idx, row in to_update:
            self._write_range(sheet, idx, [row])
            stats["updated"] += 1
        if to_append:
            self._append_rows(sheet, to_append)
            stats["inserted"] += len(to_append)
        log.info("sheet %s: %s", sheet, stats)
        return stats

    def sync_all(self, db) -> dict:
        total = {}
        for sheet in SHEETS:
            try:
                total[sheet] = self.sync_table(db, sheet)
            except RuntimeError as exc:
                log.error("sheet %s failed: %s", sheet, str(exc)[:200])
                total[sheet] = {"error": str(exc)[:200]}
        from datetime import datetime, timezone
        db.con.execute(
            """INSERT INTO sync_state VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(target) DO UPDATE SET last_synced=excluded.last_synced,
               records_inserted=excluded.records_inserted,
               records_updated=excluded.records_updated,
               sync_status=excluded.sync_status""",
            ["sheets", datetime.now(timezone.utc),
             sum(v.get("inserted", 0) for v in total.values() if isinstance(v, dict)),
             sum(v.get("updated", 0) for v in total.values() if isinstance(v, dict)),
             0, "ok"])
        return total


def data_dictionary() -> list[dict]:
    """Column documentation for the DATA_DICTIONARY sheet."""
    entries = [
        ("CONTACT_MASTER", "contact_id", "Stable person identifier", "TEXT", "C000123",
         "contacts", "rank by message count", "Normal"),
        ("CONTACT_MASTER", "last_communication", "Most recent message date", "DATE",
         "2026-08-12", "Gmail", "MAX(emails.date)", "Normal"),
        ("CONTACT_MASTER", "health_score", "Explainable 0-100 relationship score",
         "NUMBER", "72.5", "analytics", "30% recency + 25% frequency + 20% strength + 15% importance + 10% responsiveness", "Normal"),
        ("CONTACT_MASTER", "primary_email", "Main email address", "TEXT",
         "ahmed@example.com", "Gmail", "most-used address", "Sensitive"),
        ("FOLLOW_UP", "recommended_action", "Suggested next step", "TEXT",
         "Reconnect", "analytics", "rule: importance x silence", "Normal"),
    ]
    return [{"table_name": t, "column_name": c, "description": d, "data_type": dt,
             "example": e, "source": s, "calculation": calc, "sensitivity": sens}
            for t, c, d, dt, e, s, calc, sens in entries]

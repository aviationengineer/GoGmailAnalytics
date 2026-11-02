"""Local analytical database (DuckDB): schema, loads, upserts.

One database per project at data/processed/gmail_intel.duckdb, so Gmail
never needs rescanning to re-run analytics. Stable IDs make every load
an upsert: reruns never duplicate records.
"""
from __future__ import annotations

import json
import os

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    email_id VARCHAR PRIMARY KEY,
    thread_id VARCHAR,
    account VARCHAR,
    internal_date VARCHAR,
    date TIMESTAMP,
    from_email VARCHAR,
    from_name VARCHAR,
    to_emails VARCHAR,          -- JSON array
    cc_emails VARCHAR,          -- JSON array
    subject VARCHAR,
    snippet VARCHAR,
    labels VARCHAR,             -- JSON array
    direction VARCHAR,          -- incoming | outgoing
    is_sent BOOLEAN,
    body_text VARCHAR
);
CREATE TABLE IF NOT EXISTS email_threads (
    thread_id VARCHAR PRIMARY KEY,
    account VARCHAR,
    first_message_date TIMESTAMP,
    last_message_date TIMESTAMP,
    message_count INTEGER,
    participants VARCHAR,       -- JSON array
    participant_count INTEGER,
    subject VARCHAR,
    duration_days DOUBLE
);
CREATE TABLE IF NOT EXISTS contacts (
    contact_id VARCHAR PRIMARY KEY,
    full_name VARCHAR,
    primary_email VARCHAR,
    alternate_emails VARCHAR,   -- JSON array
    company VARCHAR,
    industry VARCHAR,
    relationship_category VARCHAR,
    relationship_subcategory VARCHAR,
    relationship_strength INTEGER,
    importance VARCHAR,
    first_communication TIMESTAMP,
    last_communication TIMESTAMP,
    communication_count INTEGER,
    incoming_count INTEGER,
    outgoing_count INTEGER,
    thread_count INTEGER,
    communication_frequency VARCHAR,
    current_status VARCHAR,
    primary_topics VARCHAR,     -- JSON array
    health_score DOUBLE,
    health_band VARCHAR,
    follow_up_required BOOLEAN,
    merge_confidence DOUBLE,
    merge_reason VARCHAR,
    source VARCHAR
);
CREATE TABLE IF NOT EXISTS communications (
    communication_id VARCHAR PRIMARY KEY,
    contact_id VARCHAR,
    thread_id VARCHAR,
    email_id VARCHAR,
    date TIMESTAMP,
    communication_type VARCHAR,
    direction VARCHAR,
    subject VARCHAR,
    participants VARCHAR,       -- JSON array
    topic VARCHAR,
    account VARCHAR
);
CREATE TABLE IF NOT EXISTS organizations (
    organization_id VARCHAR PRIMARY KEY,
    organization_name VARCHAR,
    domain VARCHAR,
    first_contact TIMESTAMP,
    last_contact TIMESTAMP,
    contact_count INTEGER,
    communication_count INTEGER
);
CREATE TABLE IF NOT EXISTS topics (
    topic VARCHAR PRIMARY KEY,
    mentions INTEGER,
    contact_count INTEGER
);
CREATE TABLE IF NOT EXISTS career_history (
    contact_id VARCHAR,
    company VARCHAR,
    role VARCHAR,
    relationship VARCHAR,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    evidence_count INTEGER,
    confidence DOUBLE
);
CREATE TABLE IF NOT EXISTS follow_up (
    contact_id VARCHAR PRIMARY KEY,
    last_contact_date TIMESTAMP,
    days_since_contact INTEGER,
    importance VARCHAR,
    relationship_strength INTEGER,
    historical_frequency VARCHAR,
    follow_up_priority VARCHAR,
    recommended_action VARCHAR,
    reason VARCHAR
);
CREATE TABLE IF NOT EXISTS data_quality (
    metric VARCHAR PRIMARY KEY,
    value VARCHAR,
    threshold VARCHAR,
    status VARCHAR,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sync_state (
    target VARCHAR PRIMARY KEY,   -- e.g. sheets:CONTACT_MASTER
    last_synced TIMESTAMP,
    records_inserted INTEGER,
    records_updated INTEGER,
    records_skipped INTEGER,
    sync_status VARCHAR
);
"""


class Database:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.con = duckdb.connect(path)
        self.con.execute(SCHEMA)

    def close(self):
        self.con.close()

    # -- emails -------------------------------------------------------
    def upsert_emails(self, rows: list[dict]) -> int:
        sql = """INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(email_id) DO UPDATE SET
                   subject=excluded.subject, snippet=excluded.snippet,
                   labels=excluded.labels"""
        data = [(
            r["id"], r["thread_id"], r.get("account", ""),
            r.get("internal_date", ""),
            r["date"] or None, r["from_email"], r["from_name"],
            json.dumps([p["email"] for p in r.get("to", [])]),
            json.dumps([p["email"] for p in r.get("cc", [])]),
            r.get("subject", ""), r.get("snippet", ""),
            json.dumps(r.get("labels", [])),
            "outgoing" if r.get("is_sent") else "incoming",
            bool(r.get("is_sent")), r.get("body_text", ""),
        ) for r in rows]
        self.con.executemany(sql, data)
        return len(data)

    def email_count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM emails").fetchone()[0]

    # -- generic helpers ----------------------------------------------
    def replace_table(self, table: str, rows: list[dict], columns: list[str]) -> int:
        """Full refresh of a derived table (contacts, analytics...)."""
        self.con.execute(f"DELETE FROM {table}")
        if rows:
            placeholders = ",".join(["?"] * len(columns))
            self.con.executemany(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                [[r.get(c) for c in columns] for r in rows],
            )
        return len(rows)

    def query(self, sql: str, params: list | None = None):
        return self.con.execute(sql, params or []).fetchall()

    def df(self, sql: str, params: list | None = None):
        return self.con.execute(sql, params or []).df()

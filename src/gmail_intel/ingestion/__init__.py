"""Gmail ingestion engine: resumable, incremental, rate-limit aware.

State per account lives in data/processed/scan_state.json:
  account, last_scan, messages_processed, threads_processed,
  contacts_discovered, status, query

Incremental scans page newest-first and stop at the first message id
already seen, so only new mail is fetched.
"""
from __future__ import annotations

import json
import logging
import os
import time

from ..auth import RateLimitedError, TransportError
from ..gmail import GmailClient
from ..parsing import parse_message

log = logging.getLogger("gmail-intel.ingestion")


class ScanState:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def get(self, account: str) -> dict:
        return self.data.get(account, {})

    def set(self, account: str, **fields) -> None:
        cur = self.data.setdefault(account, {})
        cur.update(fields)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)


class ScanEngine:
    def __init__(self, client: GmailClient, account_name: str, state: ScanState,
                 raw_dir: str, query: str = "", sleep: float = 0.05,
                 max_retries: int = 5, store_body: bool = False):
        self.client = client
        self.account_name = account_name
        self.state = state
        self.raw_dir = raw_dir
        self.query = query
        self.sleep = sleep
        self.max_retries = max_retries
        self.store_body = store_body
        os.makedirs(raw_dir, exist_ok=True)

    def _meta_path(self) -> str:
        return os.path.join(self.raw_dir, f"meta_{self.account_name}.jsonl")

    def _seen_ids(self) -> set[str]:
        seen = set()
        path = self._meta_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        seen.add(json.loads(line)["id"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        return seen

    def scan(self, date_from: str = "", date_to: str = "",
             incremental: bool = False, max_messages: int = 0) -> dict:
        """Run a scan. Returns a summary dict."""
        q = self.query
        if date_from:
            q += f" after:{date_from}"
        if date_to:
            q += f" before:{date_to}"
        seen = self._seen_ids()
        log.info("account=%s query=%r already_have=%d incremental=%s",
                 self.account_name, q, len(seen), incremental)

        stats = {"discovered": 0, "fetched": 0, "skipped": 0, "errors": 0,
                 "stopped_early": False}
        path = self._meta_path()
        with open(path, "a", encoding="utf-8") as out:
            for ref in self.client.list_message_ids(query=q.strip()):
                stats["discovered"] += 1
                mid = ref["id"]
                if mid in seen:
                    stats["skipped"] += 1
                    if incremental:
                        stats["stopped_early"] = True
                        break  # newest-first: everything older is known
                    continue
                if max_messages and stats["fetched"] >= max_messages:
                    break
                rec = self._fetch_with_retry(mid)
                if rec is None:
                    stats["errors"] += 1
                    continue
                out.write(json.dumps(rec) + "\n")
                seen.add(mid)
                stats["fetched"] += 1
                if stats["fetched"] % 500 == 0:
                    out.flush()
                    log.info("account=%s fetched=%d", self.account_name, stats["fetched"])
                time.sleep(self.sleep)

        self.state.set(
            self.account_name, last_scan=time.strftime("%Y-%m-%dT%H:%M:%S"),
            messages_processed=len(seen), query=q.strip(), status="ok",
        )
        log.info("scan summary account=%s %s", self.account_name, stats)
        return stats

    def _fetch_with_retry(self, mid: str) -> dict | None:
        delay = 1.0
        for attempt in range(self.max_retries):
            try:
                msg = self.client.get_message(mid)
                return parse_message(msg, store_body=self.store_body)
            except RateLimitedError:
                log.warning("rate limited, backing off %.0fs (attempt %d)", delay, attempt + 1)
                time.sleep(delay)
                delay *= 2
            except TransportError as exc:
                log.warning("fetch %s failed: %s", mid, str(exc)[:200])
                return None
        log.error("fetch %s gave up after %d retries", mid, self.max_retries)
        return None

"""Thin Gmail client over a GmailTransport: list/get/search/profile/labels."""
from __future__ import annotations

from typing import Iterator

from ..auth import GmailTransport


class GmailClient:
    def __init__(self, transport: GmailTransport):
        self.t = transport

    def profile_email(self) -> str:
        return self.t.profile_email()

    def list_message_ids(self, query: str = "", max_results: int = 500,
                         page_limit: int = 100000) -> Iterator[dict]:
        """Yield {'id','threadId'} pages. Gmail returns newest first."""
        page_token = None
        pages = 0
        while True:
            params = {"userId": "me", "maxResults": max_results, "q": query}
            if page_token:
                params["pageToken"] = page_token
            data = self.t.raw("users", "messages", "list", params=params)
            for m in data.get("messages", []):
                yield {"id": m["id"], "threadId": m.get("threadId", "")}
            page_token = data.get("nextPageToken")
            pages += 1
            if not page_token or pages >= page_limit:
                return

    def get_message(self, message_id: str, metadata_headers: list[str] | None = None,
                    full: bool = False) -> dict:
        params: dict = {"userId": "me", "id": message_id}
        if full:
            params["format"] = "full"
        else:
            params["format"] = "metadata"
            params["metadataHeaders"] = metadata_headers or ["From", "To", "Cc", "Subject", "Date"]
        return self.t.raw("users", "messages", "get", params=params)

    def get_thread(self, thread_id: str) -> dict:
        return self.t.raw("users", "threads", "get",
                          params={"userId": "me", "id": thread_id, "format": "metadata",
                                  "metadataHeaders": ["From", "To", "Cc", "Subject", "Date"]})

    def list_labels(self) -> dict:
        return self.t.raw("users", "labels", "list", params={"userId": "me"})

    def label_totals(self, label_id: str) -> dict:
        return self.t.raw("users", "labels", "get",
                          params={"userId": "me", "id": label_id})

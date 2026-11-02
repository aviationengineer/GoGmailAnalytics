"""Semantic search layer (optional).

Designed for sentence-transformers + ChromaDB with local storage, but
both are heavy optional dependencies. Importing this module never fails;
call build_index() only when the stack is installed.
"""
from __future__ import annotations

import logging

log = logging.getLogger("gmail-intel.embeddings")

try:
    import sentence_transformers  # noqa: F401
    import chromadb  # noqa: F401
    HAS_STACK = True
except ImportError:
    HAS_STACK = False


def build_index(texts: list[str], ids: list[str], persist_dir: str):
    if not HAS_STACK:
        raise RuntimeError(
            "semantic search needs sentence-transformers and chromadb; "
            "install them to enable embeddings")
    raise NotImplementedError("index builder stub")


def search(query: str, persist_dir: str, top_k: int = 10) -> list[dict]:
    if not HAS_STACK:
        raise RuntimeError("semantic search is not installed")
    raise NotImplementedError("search stub")

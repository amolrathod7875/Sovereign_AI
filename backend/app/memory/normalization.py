"""Deterministic memory content normalization for deduplication.

The normalized form is used ONLY for deduplication lookups. The original
human-readable ``content`` is preserved unchanged in the canonical record.
"""
from __future__ import annotations

import re


def normalize_memory_content(text: str) -> str:
    """Return a deterministic normalized form of memory content for dedup.

    Steps:
      1. Strip leading/trailing whitespace
      2. Collapse runs of whitespace to a single space
      3. Lowercase
      4. Strip trailing punctuation ('.', '!', '?')
    """
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    text = text.rstrip(".!?")
    return text

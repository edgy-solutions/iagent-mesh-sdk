"""Generic text normalization for identity comparison — one function, no domain knowledge.

This module knows nothing about what it normalizes: no corporate-suffix stripping, no
revision-dot handling, no field named for a specific kind of identifier. That logic belongs to
the caller, one layer up, the same split every other normalization-adjacent module in this SDK
draws between declaring a shape and interpreting it.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = [
    "normalize_mpn",
]

_NOISE_PUNCTUATION_RE = re.compile(r"[.,']")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_mpn(value: Any) -> str:
    """Generic text normalization for identity comparison: case-fold, drop typesetting-variant
    punctuation ('.', ',', apostrophes), collapse internal whitespace to a single space, strip
    ends. `None` normalizes to "". Keeps '-': a printed dash can be structural, not noise.

    Deliberately does nothing domain- or kind-specific (no corporate-suffix stripping, no
    revision-dot handling) — that logic belongs to the caller, one layer up."""
    if value is None:
        return ""
    text = str(value).casefold()
    text = _NOISE_PUNCTUATION_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text

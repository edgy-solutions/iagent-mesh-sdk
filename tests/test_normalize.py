"""`normalize_mpn` is pure text normalization for identity comparison — no domain knowledge, no
corporate-suffix or revision-dot handling. These seals cover exactly what the docstring claims
and nothing the caller is meant to layer on top.
"""
from __future__ import annotations

from iagent_mesh.normalize import normalize_mpn


def test_none_normalizes_to_empty_string():
    assert normalize_mpn(None) == ""


def test_mixed_case_folds():
    assert normalize_mpn("AbC") == "abc"


def test_noise_punctuation_is_dropped():
    assert normalize_mpn("a.b,c'd") == "abcd"


def test_internal_whitespace_runs_collapse_to_one_space():
    assert normalize_mpn("a   b\tc") == "a b c"


def test_leading_and_trailing_whitespace_is_stripped():
    assert normalize_mpn("  abc  ") == "abc"


def test_hyphen_is_preserved():
    assert normalize_mpn("a-b") == "a-b"


def test_non_string_input_is_stringified_first():
    assert normalize_mpn(123) == "123"

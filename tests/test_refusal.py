"""`Refusal` is an envelope, not a resolver — it carries a denied authorization decision, it does
not decide anything. This file's spine: the four fields are what a caller needs to route the
refusal somewhere (which policy, what was missing, who could grant it, what else to try), and
nothing here infers or interprets those values — they are opaque tokens, checked only for shape.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.refusal import Refusal

VALID = dict(
    policy_id="topaz:can_invoke_mesh_startReview",
    missing_binding="persona:finance-approver",
    grantable_by="role:finance-lead",
    candidates=("role:finance-lead", "role:finance-admin"),
)


def test_refusal_builds_from_the_valid_fixture():
    r = Refusal(**VALID)
    assert r.policy_id == "topaz:can_invoke_mesh_startReview"
    assert r.missing_binding == "persona:finance-approver"
    assert r.grantable_by == "role:finance-lead"
    assert r.candidates == ("role:finance-lead", "role:finance-admin")


def test_refusal_candidates_defaults_to_empty():
    r = Refusal(**{k: v for k, v in VALID.items() if k != "candidates"})
    assert r.candidates == ()


def test_refusal_required_strings_cannot_be_blank():
    for field in ("policy_id", "missing_binding", "grantable_by"):
        with pytest.raises(ValidationError, match=field):
            Refusal(**{**VALID, field: ""})
        with pytest.raises(ValidationError, match=field):
            Refusal(**{**VALID, field: "   "})


def test_refusal_candidates_cannot_contain_a_blank_entry():
    with pytest.raises(ValidationError, match="candidates"):
        Refusal(**{**VALID, "candidates": ("role:finance-lead", "")})


def test_refusal_is_frozen_and_forbids_extra_fields():
    r = Refusal(**VALID)
    with pytest.raises(ValidationError):
        r.policy_id = "something-else"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Refusal(**VALID, decided_by="bob")  # type: ignore[call-arg]


# ── to_terminal / from_terminal ─────────────────────────────────────────────────────────────

def test_to_terminal_and_from_terminal_round_trip():
    r = Refusal(**VALID)
    rebuilt = Refusal.from_terminal(r.to_terminal())
    assert rebuilt == r


def test_to_terminal_is_deterministic():
    r = Refusal(**VALID)
    assert r.to_terminal() == r.to_terminal()


def test_to_terminal_serializes_empty_candidates_as_an_empty_list_not_omitted():
    r = Refusal(**{**VALID, "candidates": ()})
    assert '"candidates":[]' in r.to_terminal()


def test_from_terminal_returns_none_for_a_non_string():
    assert Refusal.from_terminal(12345) is None
    assert Refusal.from_terminal(None) is None
    assert Refusal.from_terminal(["refusal:", "x"]) is None


def test_from_terminal_returns_none_for_a_string_with_no_prefix():
    assert Refusal.from_terminal("not a refusal at all") is None


def test_from_terminal_returns_none_for_invalid_json():
    assert Refusal.from_terminal("refusal:not json") is None


def test_from_terminal_returns_none_for_a_json_array_not_an_object():
    import json
    assert Refusal.from_terminal("refusal:" + json.dumps([1, 2, 3])) is None


def test_from_terminal_returns_none_for_a_blank_required_field():
    import json
    assert Refusal.from_terminal("refusal:" + json.dumps({"policy_id": ""})) is None


def test_from_terminal_returns_none_for_a_dict_missing_a_required_key():
    import json
    body = {k: v for k, v in VALID.items() if k != "grantable_by"}
    assert Refusal.from_terminal("refusal:" + json.dumps(body)) is None

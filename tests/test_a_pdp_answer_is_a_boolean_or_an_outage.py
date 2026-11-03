"""A PDP answer is a JSON boolean, or it is an outage: never a truthy guess.

Carries over leg 1 of `invincible-agent/tests/security/
test_a_pdp_answer_is_a_boolean_or_an_outage.py` (PR #190) — the reader, over a matrix of bodies —
which is the part of that seal that is about this module's own behavior. Legs 2 (the by-form
source census over `agent_fleet`/`src`/`policy`/`scripts`) and 3 (invincible-agent's own PDP-backed
consumers: `finance_agent`, the gateway, the rail checks) are properties of THAT repo's call
sites, not of this one, and stay there; this SDK has none of those call sites to census.

Run:  python -m pytest tests/test_a_pdp_answer_is_a_boolean_or_an_outage.py -q
"""
from __future__ import annotations

import json as _json

import httpx
import pytest

from iagent_mesh.pdp_answer import MalformedPdpAnswer, check_answer, decision_answer

URL = "http://topaz.test"
ENDPOINT = "/api/v3/directory/check"


def _resp(status: int = 200, *, json=None, content: bytes | None = None) -> httpx.Response:
    # The body is serialised here, so `json=None` is the JSON `null`, not an empty body.
    req = httpx.Request("POST", URL + ENDPOINT)
    if content is None:
        content = _json.dumps(json).encode()
    return httpx.Response(status, content=content, request=req, headers={"content-type": "application/json"})


MALFORMED_CHECK = [{"check": None}, {"check": "false"}, {"check": "no"}, {"check": "0"}, {"check": "true"},
                   {"check": 0}, {"check": 1}, {"check": []}, {"check": {}}]
MALFORMED_BODY = [[], None, "true", 1]


@pytest.mark.parametrize("body,want", [({"check": True}, True), ({"check": False}, False),
                                       ({}, False), ({"allowed": True}, False)])
def test_a_boolean_or_an_absent_check_is_an_answer(body, want):
    assert check_answer(_resp(json=body)) is want


@pytest.mark.parametrize("body", MALFORMED_CHECK + MALFORMED_BODY, ids=repr)
def test_anything_else_is_malformed(body):
    with pytest.raises(MalformedPdpAnswer):
        check_answer(_resp(json=body))


@pytest.mark.parametrize("content", [b"", b"<html>bad gateway</html>", b"{\"check\": tru"])
def test_a_body_that_is_not_json_is_malformed(content):
    with pytest.raises(MalformedPdpAnswer):
        check_answer(_resp(content=content))


def test_malformed_is_the_transport_failure_class():
    # The property every site relies on: its outage handler catches an httpx.HTTPError. And a
    # body that is not JSON raised a ValueError before, so a caller that caught that still does.
    assert issubclass(MalformedPdpAnswer, httpx.HTTPError)
    assert issubclass(MalformedPdpAnswer, ValueError)


def _decisions(*ds):
    return _resp(json={"decisions": list(ds)})


@pytest.mark.parametrize("response,want", [
    (_decisions({"decision": "allowed", "is": True}), True),
    (_decisions({"decision": "allowed", "is": False}), False),
    (_decisions({"decision": "allowed"}), False),
    (_decisions({"decision": "other", "is": True}), False),
    (_decisions(), False),
    (_resp(json={}), False),
], ids=["is-true", "is-false", "is-absent", "other-decision", "no-decisions", "no-decisions-key"])
def test_a_decision_is_its_boolean_is(response, want):
    assert decision_answer(response, "allowed") is want


@pytest.mark.parametrize("response", [
    _decisions({"decision": "allowed", "is": "false"}),
    _decisions({"decision": "allowed", "is": None}),
    _decisions({"decision": "allowed", "is": 1}),
    _decisions("allowed"),
    _resp(json={"decisions": {"allowed": True}}),
    _resp(json=[]),
    _resp(content=b"<html/>"),
], ids=["is-string", "is-null", "is-int", "decision-not-object", "decisions-not-list", "body-list", "not-json"])
def test_a_malformed_decision_is_malformed(response):
    with pytest.raises(MalformedPdpAnswer):
        decision_answer(response, "allowed")

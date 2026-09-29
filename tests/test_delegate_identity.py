"""`delegate_initiator_from_token` — sealed per the overnight order, item 2, 2026-09-28.

THE DEFECT THIS MODULE EXISTS TO CATCH: a delegate minted from a client-credentials token whose
`on_behalf_of` claim never arrived (a Keycloak protocol-mapper gap) used to reach
`Initiator(kind="delegate", on_behalf_of=None)` and fail there as an unattributed
`ValidationError` — a construction-time accident, not a named refusal. This module names the
refusal at the token, before `Initiator` is ever built, and this file proves it actually does —
every refusal branch is exercised by a token built to trip it, not merely read from the source.

Every fixture here is a real (unsigned-verification) JWT via `jwt.encode` — the same technique
`test_transport_auth.py` uses to build its own fixtures, since `delegate_initiator_from_token`
decodes without verifying a signature by design (see the module docstring for why).
"""
from __future__ import annotations

import jwt
import pytest

from iagent_mesh.delegate_identity import (
    DelegateCredentialRefused,
    delegate_initiator_from_token,
)
from iagent_mesh.interfaces import Initiator


def _token(**claims) -> str:
    return jwt.encode(claims, "irrelevant-key", algorithm="HS256")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("DELEGATE_SUBJECT_CLAIM", "DELEGATE_ON_BEHALF_OF_CLAIM"):
        monkeypatch.delenv(k, raising=False)


# ── positive control ─────────────────────────────────────────────────────────────────────

def test_A_CONFORMING_TOKEN_YIELDS_A_DELEGATE_INITIATOR():
    """POSITIVE CONTROL. Without this, every refusal below could be a function that refuses
    everything."""
    tok = _token(sub="svc:doc-tools-worker", on_behalf_of="user:cnogradi")
    initiator = delegate_initiator_from_token(tok)

    assert isinstance(initiator, Initiator)
    assert initiator.kind == "delegate"
    assert initiator.subject == "svc:doc-tools-worker"
    assert initiator.on_behalf_of == "user:cnogradi"
    # THE PRODUCED INITIATOR MUST ACTUALLY WORK AT THE WRITE BOUNDARY — an integration check,
    # not just a shape check.
    initiator.require_person_or_delegate("conformance-op")


def test_A_CONFORMING_TOKEN_CARRIES_ITS_CLAIMS_OPAQUE_AND_VERBATIM():
    """`Initiator.subject` and `.on_behalf_of` must be exactly the claim values — carried, never
    parsed. A numeric claim (some Keycloak configs emit these) must still round-trip as a str."""
    tok = _token(sub=42, on_behalf_of="user:with a space and CAPS")
    initiator = delegate_initiator_from_token(tok)
    assert initiator.subject == "42"
    assert initiator.on_behalf_of == "user:with a space and CAPS"


# ── THE DEFECT ITSELF: on_behalf_of absent or blank ─────────────────────────────────────────

def test_A_TOKEN_WITH_NO_on_behalf_of_CLAIM_IS_REFUSED():
    tok = _token(sub="svc:doc-tools-worker")  # no on_behalf_of at all
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'on_behalf_of'"):
        delegate_initiator_from_token(tok)


def test_A_TOKEN_WITH_A_BLANK_on_behalf_of_CLAIM_IS_REFUSED():
    tok = _token(sub="svc:doc-tools-worker", on_behalf_of="   ")
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'on_behalf_of'"):
        delegate_initiator_from_token(tok)


def test_A_TOKEN_WITH_A_NULL_on_behalf_of_CLAIM_IS_REFUSED():
    tok = _token(sub="svc:doc-tools-worker", on_behalf_of=None)
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'on_behalf_of'"):
        delegate_initiator_from_token(tok)


# ── the delegate's own subject, same discipline ─────────────────────────────────────────────

def test_A_TOKEN_WITH_NO_SUBJECT_CLAIM_IS_REFUSED():
    tok = _token(on_behalf_of="user:cnogradi")  # no sub at all
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'sub'"):
        delegate_initiator_from_token(tok)


def test_A_TOKEN_WITH_A_BLANK_SUBJECT_CLAIM_IS_REFUSED():
    tok = _token(sub="  ", on_behalf_of="user:cnogradi")
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'sub'"):
        delegate_initiator_from_token(tok)


# ── an undecodable token ────────────────────────────────────────────────────────────────────

def test_AN_UNDECODABLE_TOKEN_IS_REFUSED_NOT_RAISED_AS_A_RAW_JWT_EXCEPTION():
    with pytest.raises(DelegateCredentialRefused, match=r"undecodable"):
        delegate_initiator_from_token("not-a-jwt-at-all")


# ── configurable claim names: parameter and env, and that they actually change behaviour ────

def test_A_CUSTOM_CLAIM_NAME_PASSED_AS_A_PARAMETER_IS_HONOURED():
    tok = _token(client_id="svc:doc-tools-worker", acting_for="user:cnogradi")
    initiator = delegate_initiator_from_token(
        tok, subject_claim="client_id", on_behalf_of_claim="acting_for"
    )
    assert initiator.subject == "svc:doc-tools-worker"
    assert initiator.on_behalf_of == "user:cnogradi"


def test_THE_DEFAULT_CLAIM_NAMES_DO_NOT_ACCIDENTALLY_MATCH_A_CUSTOM_TOKEN():
    """FIXTURE DISCRIMINATION, the same discipline the conformance arms apply: proves the
    parameter above is actually being READ, not merely accepted and ignored while the default
    claim names happen to work anyway."""
    tok = _token(client_id="svc:doc-tools-worker", acting_for="user:cnogradi")
    with pytest.raises(DelegateCredentialRefused, match=r"no usable 'sub'"):
        delegate_initiator_from_token(tok)  # no subject_claim override — must fail on default 'sub'


def test_A_CUSTOM_CLAIM_NAME_SET_VIA_ENV_IS_HONOURED(monkeypatch):
    monkeypatch.setenv("DELEGATE_SUBJECT_CLAIM", "azp")
    monkeypatch.setenv("DELEGATE_ON_BEHALF_OF_CLAIM", "obo")
    tok = _token(azp="svc:doc-tools-worker", obo="user:cnogradi")
    initiator = delegate_initiator_from_token(tok)
    assert initiator.subject == "svc:doc-tools-worker"
    assert initiator.on_behalf_of == "user:cnogradi"


def test_AN_EXPLICIT_PARAMETER_OVERRIDES_THE_ENV(monkeypatch):
    monkeypatch.setenv("DELEGATE_SUBJECT_CLAIM", "azp")
    tok = _token(sub="svc:doc-tools-worker", on_behalf_of="user:cnogradi")
    initiator = delegate_initiator_from_token(tok, subject_claim="sub")
    assert initiator.subject == "svc:doc-tools-worker"


# ── on_behalf_of stays provenance, never a gate input, even minted this way ─────────────────

def test_on_behalf_of_NEVER_GATES_A_REFUSAL_AT_THE_WRITE_BOUNDARY():
    """The write boundary admits ANY delegate carrying SOME on_behalf_of — its value must never
    change whether `require_person_or_delegate` admits it. Two different values, same admission,
    proves the value is not consulted."""
    a = delegate_initiator_from_token(_token(sub="svc:x", on_behalf_of="user:alice"))
    b = delegate_initiator_from_token(_token(sub="svc:x", on_behalf_of="a completely different name"))
    a.require_person_or_delegate("op")
    b.require_person_or_delegate("op")

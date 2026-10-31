"""Tests for mcp_server/bff_tools.py — the MCP-over-BFF generator.

Fakes in THIS file only (never shipped): a counting wrapper around the real
`UnwiredTokenExchanger`, and two exchangers that stand in for "Lane 1's Keycloak
implementation" so the sub-equality check and the happy path can be exercised without a real
RFC 8693 round trip. The inbound-token *verification* is real pyjwt (HS256, with a fixed test
key injected through `JWKSKeySource` instead of a live JWKS fetch) — only the key lookup is
faked, not the cryptographic check.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
import pytest
from mcp.server.fastmcp import FastMCP

from iagent_mesh.refusal import Refusal
from mcp_server.bff_tools import (
    BffRefusalError,
    BffToolConfig,
    Operation,
    TokenVerifier,
    UnwiredTokenExchanger,
    call_bff_operation,
    generate_tools,
)

ISSUER = "https://keycloak.example/realms/mesh"
MCP_AUDIENCE = "iagent-mesh"
_HS256_SECRET = "unit-test-shared-secret-not-a-real-key-32-bytes-plus"
_BFF_AUDIENCE_SECRET = "bff-audience-secret-not-a-real-key-32-bytes-plus"


def _make_inbound_jwt(sub: str, *, aud: str = MCP_AUDIENCE, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {"sub": sub, "iss": ISSUER, "aud": aud, "iat": now, "exp": now + exp_delta}
    return jwt.encode(payload, _HS256_SECRET, algorithm="HS256")


class _FixedKeySource:
    """Stands in for a real JWKS fetch: hands back the one HS256 secret every test token is
    signed with. `jwt.decode` underneath still performs a real signature check against it."""

    def get_signing_key(self, token: str) -> Any:
        return _HS256_SECRET


def _verifier() -> TokenVerifier:
    return TokenVerifier(
        _FixedKeySource(), issuer=ISSUER, audience=MCP_AUDIENCE, algorithms=("HS256",)
    )


class _FixedTokenSource:
    def __init__(self, token):
        self._token = token

    def get(self):
        return self._token


class _NoTokenSource:
    def get(self):
        return None


class _CountingExchanger:
    """Wraps another exchanger and counts attempts, so a test can tell "never attempted" (case
    1) apart from "attempted, then the wrapped exchanger raised" (case 2)."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    async def exchange(self, inbound_token: str, *, audience: str) -> str:
        self.calls += 1
        return await self._inner.exchange(inbound_token, audience=audience)


class _MatchingSubExchanger:
    """Test-local fake of Lane 1's Keycloak exchange: returns a BFF-audience token for the SAME
    subject as the inbound token — the only case where a call should proceed."""

    def __init__(self, sub: str):
        self._sub = sub
        self.calls = 0
        self.last_token: str | None = None

    async def exchange(self, inbound_token: str, *, audience: str) -> str:
        self.calls += 1
        token = jwt.encode(
            {"sub": self._sub, "aud": audience, "exp": int(time.time()) + 3600},
            _BFF_AUDIENCE_SECRET,
            algorithm="HS256",
        )
        self.last_token = token
        return token


class _MismatchedSubExchanger:
    """Test-local fake that returns a token for a DIFFERENT subject than the inbound token —
    the case the sub-equality check exists to catch."""

    async def exchange(self, inbound_token: str, *, audience: str) -> str:
        return jwt.encode(
            {"sub": "someone-else", "aud": audience, "exp": int(time.time()) + 3600},
            _BFF_AUDIENCE_SECRET,
            algorithm="HS256",
        )


def _case_read_operation() -> Operation:
    return Operation(
        operation_id="case_read",
        summary="Read a case",
        method="GET",
        path="/cases/{case_id}",
        input_schema={
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
        is_multipart=False,
    )


def _config(*, token_source, exchanger, http_client) -> BffToolConfig:
    return BffToolConfig(
        bff_base_url="https://bff.example",
        token_source=token_source,
        verifier=_verifier(),
        exchanger=exchanger,
        http_client=http_client,
    )


def _recording_client(status_code: int = 200, json_body: Any = None):
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code, json=json_body if json_body is not None else {})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client, calls


# ── 1. No inbound token -> refused before any outbound call ────────────────────────────────


async def test_no_inbound_token_refuses_before_any_outbound_call():
    exchanger = _CountingExchanger(UnwiredTokenExchanger())
    client, calls = _recording_client()
    config = _config(token_source=_NoTokenSource(), exchanger=exchanger, http_client=client)

    with pytest.raises(BffRefusalError) as excinfo:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config)

    assert excinfo.value.refusal.policy_id == "mcp:inbound_token"
    assert exchanger.calls == 0
    assert calls == []


# ── 2. Valid inbound token, stub exchanger raises -> refused, zero BFF calls ────────────────


async def test_unwired_exchanger_raises_and_refuses_with_zero_bff_calls():
    inbound = _make_inbound_jwt(sub="alice")
    exchanger = _CountingExchanger(UnwiredTokenExchanger())
    client, calls = _recording_client()
    config = _config(
        token_source=_FixedTokenSource(inbound), exchanger=exchanger, http_client=client
    )

    with pytest.raises(BffRefusalError) as excinfo:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config)

    assert excinfo.value.refusal.policy_id == "mcp:token_exchange"
    assert exchanger.calls == 1  # attempted (unlike case 1), then raised
    assert calls == []


# ── distinguishing 1 and 2 explicitly ───────────────────────────────────────────────────────


async def test_missing_token_and_failed_exchange_are_distinguishable():
    no_token_exchanger = _CountingExchanger(UnwiredTokenExchanger())
    client_a, calls_a = _recording_client()
    config_a = _config(
        token_source=_NoTokenSource(), exchanger=no_token_exchanger, http_client=client_a
    )
    with pytest.raises(BffRefusalError) as excinfo_a:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config_a)

    failed_exchange = _CountingExchanger(UnwiredTokenExchanger())
    client_b, calls_b = _recording_client()
    config_b = _config(
        token_source=_FixedTokenSource(_make_inbound_jwt(sub="alice")),
        exchanger=failed_exchange,
        http_client=client_b,
    )
    with pytest.raises(BffRefusalError) as excinfo_b:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config_b)

    assert excinfo_a.value.refusal.policy_id != excinfo_b.value.refusal.policy_id
    assert no_token_exchanger.calls == 0
    assert failed_exchange.calls == 1


# ── 3. sub mismatch after exchange -> refused ───────────────────────────────────────────────


async def test_sub_mismatch_after_exchange_refuses_with_zero_bff_calls():
    inbound = _make_inbound_jwt(sub="alice")
    exchanger = _MismatchedSubExchanger()
    client, calls = _recording_client()
    config = _config(
        token_source=_FixedTokenSource(inbound), exchanger=exchanger, http_client=client
    )

    with pytest.raises(BffRefusalError) as excinfo:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config)

    assert excinfo.value.refusal.policy_id == "mcp:token_exchange"
    assert excinfo.value.refusal.missing_binding == "sub_preserved_through_exchange"
    assert calls == []


# ── 4. matching sub -> proceeds, calls BFF once with the EXCHANGED token ───────────────────


async def test_matching_sub_proceeds_and_forwards_exchanged_token_not_inbound():
    inbound = _make_inbound_jwt(sub="alice")
    exchanger = _MatchingSubExchanger(sub="alice")
    client, calls = _recording_client(status_code=200, json_body={"case_id": "abc123"})
    config = _config(
        token_source=_FixedTokenSource(inbound), exchanger=exchanger, http_client=client
    )

    result = await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config)

    assert result == {"case_id": "abc123"}
    assert len(calls) == 1
    assert exchanger.calls == 1
    sent_auth = calls[0].headers["authorization"]
    assert sent_auth == f"Bearer {exchanger.last_token}"
    assert sent_auth != f"Bearer {inbound}"
    assert str(calls[0].url) == "https://bff.example/cases/abc123"


# ── 5. generation produces the expected tool set ────────────────────────────────────────────


def _synthetic_openapi() -> dict:
    return {
        "paths": {
            "/cases/{case_id}": {
                "get": {
                    "operationId": "case_read",
                    "summary": "Read a case",
                    "parameters": [
                        {
                            "name": "case_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                }
            },
            "/me/human_tasks": {
                "get": {
                    "operationId": "task_list",
                    "summary": "List my human tasks",
                }
            },
            "/ingest": {
                "post": {
                    "operationId": "document_drop",
                    "summary": "Drop a document for ingest",
                    "requestBody": {
                        "required": True,
                        "content": {"multipart/form-data": {"schema": {"type": "object"}}},
                    },
                }
            },
        }
    }


def test_generate_tools_produces_expected_tool_names_and_count():
    mcp = FastMCP("test-bff-tools")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    config = _config(
        token_source=_NoTokenSource(), exchanger=UnwiredTokenExchanger(), http_client=client
    )

    registered = generate_tools(_synthetic_openapi(), mcp, config)

    assert set(registered.keys()) == {"case_read", "task_list", "document_drop"}
    assert len(registered) == 3
    assert set(mcp._tool_manager._tools.keys()) == {"case_read", "task_list", "document_drop"}
    assert registered["document_drop"].is_multipart is True
    assert registered["case_read"].input_schema["properties"]["case_id"] == {"type": "string"}
    assert mcp._tool_manager._tools["task_list"].description == "List my human tasks"


# ── 6. BFF 403 with {error, refusal, message} comes back with those fields preserved ───────


async def test_bff_403_envelope_fields_preserved_in_refusal():
    inbound = _make_inbound_jwt(sub="alice")
    exchanger = _MatchingSubExchanger(sub="alice")
    envelope = {
        "error": "forbidden",
        "refusal": {
            "policy_id": "topaz:case_read",
            "missing_binding": "persona:case_reviewer",
            "grantable_by": "svc:access-admin",
            "candidates": ["persona:case_viewer"],
        },
        "message": "alice lacks case_reviewer on this case",
    }
    client, calls = _recording_client(status_code=403, json_body=envelope)
    config = _config(
        token_source=_FixedTokenSource(inbound), exchanger=exchanger, http_client=client
    )

    with pytest.raises(BffRefusalError) as excinfo:
        await call_bff_operation(_case_read_operation(), {"case_id": "abc123"}, config)

    refusal = excinfo.value.refusal
    assert isinstance(refusal, Refusal)
    assert refusal.policy_id == "topaz:case_read"
    assert refusal.missing_binding == "persona:case_reviewer"
    assert refusal.grantable_by == "svc:access-admin"
    assert refusal.candidates == ("persona:case_viewer",)
    assert excinfo.value.bff_error == "forbidden"
    assert excinfo.value.bff_message == "alice lacks case_reviewer on this case"
    assert len(calls) == 1

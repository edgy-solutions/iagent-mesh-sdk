"""THE MCP-OVER-BFF GENERATOR — one MCP tool per tagged BFF operation, identity translated,
never decided.

Built against the two filed specs for "the MCP server over the BFF" (2026-10-30):
- `invincible-agent/sessions/2026-10-30-packet-to-lane-01-cc-architect-saf-from-ca-mcp-generator-spec-and-three-unresolved-routes.md`
  (ca's own spec, rev 2 — this generator's piece)
- `sessions/2026-10-30-packet-to-architect-cc-ca-saf-from-lane-01-mcp-server-over-the-bff-one-page-spec.md`
  (Lane 1's v2 — authoritative where the two conflict; its Section 3 identity model is what
  the exchange/verify flow below implements)

THIS MODULE DECIDES NOTHING. No Topaz call, no permission logic, no `Initiator`. The BFF's own
`get_current_user` + Topaz decide exactly as they would for a direct call — this layer's only
job is identity TRANSLATION (RFC 8693 token exchange) and mechanical forwarding.

THE EXCHANGE IS STUBBED, ON PURPOSE, TONIGHT. `UnwiredTokenExchanger` is the only shipped
`TokenExchanger` and it raises. Lane 1 supplies the real Keycloak implementation later. What
IS real here: the inbound-token verification (signature/iss/aud/exp via pyjwt against a real
JWKS, modulo an injectable key source so tests don't need a live Keycloak), the post-exchange
`sub`-equality check, the BFF forward over `httpx` (including the SSE and multipart special
cases), and the refusal wrapping. NEVER pass the inbound token through unexchanged — that is
exactly the passthrough Lane 1's spec Section 5 seal 2 rules out ("no inbound token reaches the
BFF"); there is no code path in `call_bff_operation` that forwards `inbound_token` itself.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional, Protocol

import httpx
import jwt
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.tools.base import Tool
from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase, FuncMetadata
from pydantic import create_model

from iagent_mesh.refusal import Refusal

__all__ = [
    "TokenExchanger",
    "UnwiredTokenExchanger",
    "KeycloakTokenExchanger",
    "InboundTokenSource",
    "HeaderTokenSource",
    "StdioFileTokenSource",
    "TokenVerificationError",
    "JWKSKeySource",
    "PyJWKClientKeySource",
    "TokenVerifier",
    "BffRefusalError",
    "BffToolConfig",
    "Operation",
    "parse_operations",
    "call_bff_operation",
    "generate_tools",
]


# ── THE EXCHANGER — one interface, one stub ─────────────────────────────────────────────────


class TokenExchanger(Protocol):
    """RFC 8693 token exchange: trades the inbound (MCP-audience) token for a BFF-audience token
    carrying the same subject. Lane 1's concern (Keycloak), not this generator's — this is the
    seam it plugs into."""

    async def exchange(self, inbound_token: str, *, audience: str) -> str: ...


class UnwiredTokenExchanger:
    """The only shipped implementation. Always raises — there is no default that succeeds,
    because a default that succeeded would have to either call a real Keycloak (not this
    module's job tonight) or fabricate a token (which would be a silent passthrough or forgery).
    Lane 1 supplies the real implementation; until then every tool call refuses here."""

    async def exchange(self, inbound_token: str, *, audience: str) -> str:
        raise NotImplementedError(
            "token exchange not wired — Lane 1 supplies the Keycloak implementation"
        )


class KeycloakTokenExchanger:
    """Exchanges an inbound bearer (RFC 8693 `subject_token`) for a token scoped to a
    different audience, via a Keycloak realm's token endpoint. The realm's `iagent-mesh`
    client performs the exchange using its own client-credential; the original token's
    `sub` is preserved through the exchange (RFC 8693 guarantees this), which is what lets
    a downstream audit trail show the real caller rather than this server's own identity.
    """

    def __init__(
        self,
        *,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_client = http_client

    async def exchange(self, inbound_token: str, *, audience: str) -> str:
        response = await self._http_client.post(
            self._token_endpoint,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "subject_token": inbound_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "audience": audience,
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Keycloak token exchange failed with status {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            body = response.json()
            access_token = body["access_token"]
        except Exception as exc:
            raise RuntimeError(
                f"Keycloak token exchange response had no usable access_token: {exc}"
            ) from exc
        return access_token


# ── INBOUND TOKEN EXTRACTION — real for both transports ────────────────────────────────────


class InboundTokenSource(Protocol):
    """Where the inbound bearer comes from, per transport. Read fresh on every call — neither
    implementation below caches."""

    def get(self) -> Optional[str]: ...


class HeaderTokenSource:
    """SSE transport: the token rides the `Authorization` header of the HTTP request carrying
    the tool call. `headers_provider` is supplied by whatever wires this generator to the real
    SSE/ASGI transport (the entrypoint's job, built separately) — this class does the real,
    transport-independent part: read `Authorization`, strip a `Bearer ` prefix if present."""

    def __init__(self, headers_provider: Callable[[], Mapping[str, str]]):
        self._headers_provider = headers_provider

    def get(self) -> Optional[str]:
        headers = self._headers_provider()
        for key, value in headers.items():
            if key.lower() != "authorization":
                continue
            if value.lower().startswith("bearer "):
                token = value[len("bearer "):].strip()
            else:
                token = value.strip()
            return token or None
        return None


class StdioFileTokenSource:
    """stdio transport: the token lives in the file named by `IAGENT_USER_TOKEN_FILE`. Re-read
    on every call — NEVER cached across calls — so a caller can rotate or revoke the token
    without restarting the server."""

    def __init__(self, env_var: str = "IAGENT_USER_TOKEN_FILE"):
        self._env_var = env_var

    def get(self) -> Optional[str]:
        path = os.environ.get(self._env_var)
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                token = fh.read().strip()
        except OSError:
            return None
        return token or None


# ── INBOUND TOKEN VERIFICATION — real, via pyjwt, against an injectable JWKS key source ────


class TokenVerificationError(Exception):
    """The inbound bearer failed verification: bad signature, wrong `iss`/`aud`, or expired.
    Callers refuse on the exception TYPE; the message is for logs only."""


class JWKSKeySource(Protocol):
    """Resolves the signing key for a token, duck-typed to `jwt.PyJWKClient`'s own return value
    (an object with a `.key` attribute) so `PyJWKClientKeySource` below is a one-line wrapper."""

    def get_signing_key(self, token: str) -> Any: ...


class PyJWKClientKeySource:
    """Production key source: a real JWKS lookup via `jwt.PyJWKClient` against the issuer's
    actual JWKS endpoint. Not used by the tests in this module — they inject a key source that
    hands back a known key, so the pyjwt verification underneath still runs for real without
    reaching a live Keycloak."""

    def __init__(self, jwks_url: str):
        self._client = jwt.PyJWKClient(jwks_url)

    def get_signing_key(self, token: str) -> Any:
        return self._client.get_signing_key_from_jwt(token)


class TokenVerifier:
    """Verifies signature + `iss` + `aud` + `exp`, all via pyjwt — nothing hand-rolled. `aud` is
    checked by pyjwt's own membership semantics (`audience=...` matches if the token's `aud`
    claim is either that string or a list containing it), which is exactly "aud contains
    iagent-mesh", not an equality check."""

    def __init__(
        self,
        key_source: JWKSKeySource,
        *,
        issuer: str,
        audience: str = "iagent-mesh",
        algorithms: tuple[str, ...] = ("RS256",),
    ):
        self._key_source = key_source
        self._issuer = issuer
        self._audience = audience
        self._algorithms = algorithms

    def verify(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._key_source.get_signing_key(token)
            key = getattr(signing_key, "key", signing_key)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(self._algorithms),
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iss", "aud"]},
            )
        except Exception as exc:  # jwt.PyJWTError and anything the key source raises
            raise TokenVerificationError(str(exc)) from exc
        return claims


# ── THE REFUSAL ENVELOPE ────────────────────────────────────────────────────────────────────


class BffRefusalError(ToolError):
    """A denied call, shaped as `iagent_mesh.refusal.Refusal`, raised as the tool's error.

    `str(self)` is exactly `refusal.to_terminal()` — the "Refusal.to_terminal()-shaped tool
    error" the spec asks for. The structured `Refusal`, and (when the BFF supplied its own
    `{error, refusal, message}` envelope) those raw fields, are kept as attributes so a caller —
    including this module's own tests — can inspect the decision without re-parsing the
    terminal string.
    """

    def __init__(
        self,
        refusal: Refusal,
        *,
        bff_error: Optional[str] = None,
        bff_message: Optional[str] = None,
    ):
        self.refusal = refusal
        self.bff_error = bff_error
        self.bff_message = bff_message
        super().__init__(refusal.to_terminal())


# CA'S DEFAULT for `grantable_by` on the four refusal sites below (missing/invalid inbound
# token, failed exchange, sub mismatch). `Refusal` treats the field as opaque and the SDK does
# not prescribe a value — and these four sites are TERMINAL in this flow: nothing downstream
# ever completes them, so `iagent_mesh.refusal.PartialRefusal` does not apply here (per the
# architect's 2026-10-30 ruling on that type, relayed 2026-10-30). The caller cannot grant
# itself a valid token or a working RFC 8693 exchange grant; the one party who can is whoever
# administers the `iagent-mesh` Keycloak client — its token issuance for "no/invalid token", its
# token-exchange permission onto the BFF's audience for "exchange failed"/"sub mismatch". A real
# deployment may want a sharper role name; this is ca's placeholder until one is specified.
_KEYCLOAK_REALM_ADMIN = "keycloak:iagent-mesh-realm-admin"


def _missing_token_refusal() -> Refusal:
    return Refusal(
        policy_id="mcp:inbound_token",
        missing_binding="bearer_token_present",
        grantable_by=_KEYCLOAK_REALM_ADMIN,
        candidates=(),
    )


def _invalid_token_refusal(reason: str) -> Refusal:
    return Refusal(
        policy_id="mcp:inbound_token",
        missing_binding=("valid_bearer_token:" + reason)[:200],
        grantable_by=_KEYCLOAK_REALM_ADMIN,
        candidates=(),
    )


def _exchange_failed_refusal(reason: str) -> Refusal:
    return Refusal(
        policy_id="mcp:token_exchange",
        missing_binding=("exchanged_bff_token:" + reason)[:200],
        grantable_by=_KEYCLOAK_REALM_ADMIN,
        candidates=(),
    )


def _sub_mismatch_refusal() -> Refusal:
    return Refusal(
        policy_id="mcp:token_exchange",
        missing_binding="sub_preserved_through_exchange",
        grantable_by=_KEYCLOAK_REALM_ADMIN,
        candidates=(),
    )


def _bff_unclassified_refusal() -> Refusal:
    # BEST-EFFORT MINIMAL REFUSAL (documented choice): the BFF gave no {error, refusal, message}
    # envelope — either a plain-string body, or JSON without a `refusal` key (e.g. FastAPI's own
    # {"detail": "..."}). We refuse rather than raise an unhandled 401/403, but there is no real
    # policy decision to report here, so policy_id/missing_binding/grantable_by are placeholder
    # opaque tokens this layer invented, not a classification the BFF made. The raw body is kept
    # on `BffRefusalError.bff_message` so nothing is actually lost.
    return Refusal(
        policy_id="bff:unclassified",
        missing_binding="unknown",
        grantable_by="unknown",
        candidates=(),
    )


def _wrap_bff_error(status_code: int, body: bytes) -> BffRefusalError:
    text = body.decode("utf-8", errors="replace")
    try:
        parsed: Any = json.loads(text)
    except ValueError:
        parsed = None

    if isinstance(parsed, dict) and isinstance(parsed.get("refusal"), dict):
        try:
            refusal = Refusal.model_validate(parsed["refusal"])
        except Exception:
            refusal = _bff_unclassified_refusal()
        error_field = parsed.get("error")
        message_field = parsed.get("message")
        return BffRefusalError(
            refusal,
            bff_error=error_field if isinstance(error_field, str) else None,
            bff_message=message_field if isinstance(message_field, str) else None,
        )

    return BffRefusalError(_bff_unclassified_refusal(), bff_message=text or None)


# ── OPERATIONS — parsed from an already-filtered OpenAPI dict ──────────────────────────────

_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass(frozen=True)
class Operation:
    operation_id: str
    summary: str
    method: str
    path: str
    input_schema: dict[str, Any]
    is_multipart: bool


def _merge_input_schema(
    params: list[dict[str, Any]], request_body: Optional[dict[str, Any]]
) -> tuple[dict[str, Any], bool]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in params:
        name = param.get("name")
        if not name:
            continue
        properties[name] = dict(param.get("schema") or {"type": "string"})
        if param.get("required"):
            required.append(name)

    is_multipart = False
    if request_body:
        content = request_body.get("content", {})
        if "multipart/form-data" in content:
            # Per spec: base64 content + a filename field, not the real multipart schema.
            is_multipart = True
            properties["content_base64"] = {
                "type": "string",
                "description": "base64-encoded file content",
            }
            properties["filename"] = {"type": "string"}
            required.extend(["content_base64", "filename"])
        elif "application/json" in content:
            body_schema = content["application/json"].get("schema", {}) or {}
            if body_schema.get("type") == "object":
                properties.update(body_schema.get("properties", {}))
                required.extend(body_schema.get("required", []))
            elif body_schema:
                properties["body"] = body_schema
                if request_body.get("required"):
                    required.append("body")

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = sorted(set(required))
    return schema, is_multipart


def parse_operations(openapi: dict[str, Any]) -> list[Operation]:
    """Turns an already-filtered OpenAPI document into one `Operation` per tagged route. Never
    fetches anything — `openapi` is a plain dict the caller already has (the committed, filtered
    `docs/api/mcp.openapi.json` Lane 1's generator writes, once it exists)."""
    operations: list[Operation] = []
    for path, path_item in (openapi.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        shared_params = path_item.get("parameters", [])
        for method, op in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            operation_id = op.get("operationId")
            if not operation_id:
                raise ValueError(f"operation {method.upper()} {path} has no operationId")
            params = list(shared_params) + list(op.get("parameters", []))
            schema, is_multipart = _merge_input_schema(params, op.get("requestBody"))
            operations.append(
                Operation(
                    operation_id=operation_id,
                    summary=op.get("summary", ""),
                    method=method.upper(),
                    path=path,
                    input_schema=schema,
                    is_multipart=is_multipart,
                )
            )
    return operations


# ── RUNTIME — verify, exchange, forward ─────────────────────────────────────────────────────


@dataclass
class BffToolConfig:
    bff_base_url: str
    token_source: InboundTokenSource
    verifier: TokenVerifier
    exchanger: TokenExchanger
    http_client: httpx.AsyncClient
    bff_audience: str = "iagent-mesh"


def _build_url(base_url: str, path: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    remaining = dict(arguments)
    resolved_path = path
    start = 0
    while True:
        open_brace = resolved_path.find("{", start)
        if open_brace == -1:
            break
        close_brace = resolved_path.find("}", open_brace)
        if close_brace == -1:
            break
        name = resolved_path[open_brace + 1 : close_brace]
        if name not in remaining:
            raise ToolError(f"missing required path parameter {name!r}")
        value = str(remaining.pop(name))
        resolved_path = resolved_path[:open_brace] + value + resolved_path[close_brace + 1 :]
        start = open_brace + len(value)
    return base_url.rstrip("/") + resolved_path, remaining


def _build_request_kwargs(operation: Operation, remaining_args: dict[str, Any]) -> dict[str, Any]:
    if operation.is_multipart:
        content_b64 = remaining_args.pop("content_base64", "")
        filename = remaining_args.pop("filename", "upload")
        try:
            file_bytes = base64.b64decode(content_b64) if content_b64 else b""
        except (binascii.Error, ValueError) as exc:
            raise ToolError(f"content_base64 is not valid base64: {exc}") from exc
        kwargs: dict[str, Any] = {"files": {"file": (filename, file_bytes)}}
        if remaining_args:
            kwargs["data"] = remaining_args
        return kwargs
    if operation.method in ("GET", "DELETE"):
        return {"params": remaining_args} if remaining_args else {}
    return {"json": remaining_args} if remaining_args else {}


async def _drain_sse(
    response: httpx.Response,
    progress_callback: Optional[Callable[[Any], Awaitable[None]]],
) -> Any:
    """Reads an SSE stream to its final event and returns that event's data. Intermediate
    events: best-effort progress callback if one was supplied, otherwise drained and ignored."""
    final_event: Any = None
    data_lines: list[str] = []

    async def _flush() -> None:
        nonlocal final_event, data_lines
        if not data_lines:
            return
        raw = "\n".join(data_lines)
        data_lines = []
        try:
            parsed: Any = json.loads(raw)
        except ValueError:
            parsed = raw
        final_event = parsed
        if progress_callback is not None:
            try:
                await progress_callback(parsed)
            except Exception:
                pass  # best-effort only — a broken progress sink must not break the drain

    async for line in response.aiter_lines():
        if line == "":
            await _flush()
            continue
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip())
    await _flush()
    return final_event


def _parse_body(body: bytes, content_type: str) -> Any:
    if "application/json" in content_type:
        try:
            return json.loads(body)
        except ValueError:
            pass
    return body.decode("utf-8", errors="replace")


async def call_bff_operation(
    operation: Operation,
    arguments: dict[str, Any],
    config: BffToolConfig,
    *,
    progress_callback: Optional[Callable[[Any], Awaitable[None]]] = None,
) -> Any:
    """The runtime body of every generated tool: verify, exchange, assert `sub`, forward.

    Refuses BEFORE any outbound call (no exchange attempt, no BFF call) when the inbound token
    is missing or fails verification. The inbound token is read ONCE here and never sent to the
    BFF — only `exchanged_token` rides the outbound `Authorization` header.
    """
    inbound_token = config.token_source.get()
    if not inbound_token:
        raise BffRefusalError(_missing_token_refusal())

    try:
        inbound_claims = config.verifier.verify(inbound_token)
    except TokenVerificationError as exc:
        raise BffRefusalError(_invalid_token_refusal(str(exc))) from exc

    try:
        exchanged_token = await config.exchanger.exchange(
            inbound_token, audience=config.bff_audience
        )
    except Exception as exc:
        raise BffRefusalError(_exchange_failed_refusal(str(exc))) from exc

    try:
        # Keycloak already signed this; we only need to read `sub`, not re-verify a token this
        # server didn't mint and isn't the audience of.
        exchanged_claims = jwt.decode(exchanged_token, options={"verify_signature": False})
    except Exception as exc:
        raise BffRefusalError(
            _exchange_failed_refusal(f"exchanged token unreadable: {exc}")
        ) from exc

    if exchanged_claims.get("sub") != inbound_claims.get("sub"):
        raise BffRefusalError(_sub_mismatch_refusal())

    url, remaining_args = _build_url(config.bff_base_url, operation.path, dict(arguments))
    request_kwargs = _build_request_kwargs(operation, remaining_args)
    headers = {"Authorization": f"Bearer {exchanged_token}"}

    async with config.http_client.stream(
        operation.method, url, headers=headers, **request_kwargs
    ) as response:
        if response.status_code in (401, 403):
            body = await response.aread()
            raise _wrap_bff_error(response.status_code, body)

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return await _drain_sse(response, progress_callback)

        body = await response.aread()
        return _parse_body(body, content_type)


# ── REGISTRATION — one FastMCP tool per operation ───────────────────────────────────────────


def _register_tool(mcp: FastMCP, operation: Operation, config: BffToolConfig) -> None:
    async def _tool_fn(**kwargs: Any) -> Any:
        return await call_bff_operation(operation, kwargs, config)

    _tool_fn.__name__ = operation.operation_id
    _tool_fn.__doc__ = operation.summary

    # No public FastMCP API registers a tool with an input schema distinct from one derived
    # from the handler's own Python signature — `FastMCP.add_tool`/`.tool()` always re-derive it
    # via `Tool.from_function`. The handler's real signature is `**kwargs` precisely because its
    # schema comes from the OpenAPI operation, not from Python type hints, so we build the `Tool`
    # ourselves. `Tool` / `FuncMetadata` / `ArgModelBase` are mcp's own classes
    # (mcp.server.fastmcp.tools.base / .utilities.func_metadata); only `_tool_manager._tools` is
    # a private attribute, and inserting into it is exactly what `add_tool` itself does with the
    # `Tool` it builds.
    properties = operation.input_schema.get("properties", {})
    required = set(operation.input_schema.get("required", []))
    fields: dict[str, Any] = {
        name: (Any, ... if name in required else None) for name in properties
    }
    arg_model = create_model(
        f"{operation.operation_id}_Args", __base__=ArgModelBase, **fields
    )
    fn_metadata = FuncMetadata(arg_model=arg_model)

    tool = Tool(
        fn=_tool_fn,
        name=operation.operation_id,
        description=operation.summary,
        parameters=operation.input_schema,
        fn_metadata=fn_metadata,
        is_async=True,
    )
    mcp._tool_manager._tools[operation.operation_id] = tool


def generate_tools(
    openapi: dict[str, Any],
    mcp: FastMCP,
    config: BffToolConfig,
) -> dict[str, Operation]:
    """Registers one MCP tool per operation in the already-filtered `openapi` dict onto `mcp`.
    Tool name = `operationId`, description = `summary`, input schema = merged parameters +
    request body schema. Returns the name -> `Operation` map it registered, so a caller (or a
    test) can inspect what was built without round-tripping the full MCP JSON-RPC machinery.

    Decides nothing about authorization — every registered tool's runtime body is
    `call_bff_operation`, which only verifies identity, exchanges it, and forwards.
    """
    operations = parse_operations(openapi)
    registered: dict[str, Operation] = {}
    for operation in operations:
        _register_tool(mcp, operation, config)
        registered[operation.operation_id] = operation
    return registered

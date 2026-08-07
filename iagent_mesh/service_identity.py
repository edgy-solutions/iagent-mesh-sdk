"""Service-identity minting — ONE general implementation, many thin bindings.

WHY IT LIVES HERE. The SDK is the mesh's membership package: what an engine needs to join.
Authenticating — inbound and outbound — is a membership obligation, not a use case, so the
package that already owns registration, telemetry wiring and the app factory owns identity
too. The SDK is a genuine leaf (pydantic / fastapi / httpx and nothing platform-side), so
platform -> SDK is the ordinary shared-kernel direction; the "circular dependency" fear was a
naming illusion resting on ONE guarded import, now inverted.

WHAT THIS REPLACES — a divergence, not a duplication. Two mints existed: the platform's
`mint_service_token()` reading REVIEW_STARTER_CLIENT_ID/SECRET, and this package's inline
fallback reading MESH_CLIENT_ID/SECRET. They were mistaken for transcriptions of each other;
reading both showed DIFFERENT ENV CONTRACTS — the one-implementation rule's predicted drift,
already realised. Worse, the platform's carried a GENERAL NAME over SPECIFIC BEHAVIOUR, which
is how the supervisor came to mint the review starter's identity and would have carried that
role's capability grant on every dispatch (fixed 2026-08-07, invincible-agent 3ac573d).

The repair that makes consolidation possible: IDENTITY IS AN ARGUMENT, never an ambient env
read. One general function; each caller binds its own credentials in a named wrapper. The
platform's `service_identity` now imports THIS and binds the review starter's env; the SDK
binds MESH_CLIENT_ID for externally packaged engines. Same function, two bindings, zero drift
surface.

MINT AT USE — never a stored token. There is no JWT to go stale and no lifetime knob to tune;
a static credential replayed later is the time-machine defect this exists to remove.

THE MINT'S WITNESS IS THE DECODED SUBJECT, NOT THE 200. A mint returning a token proves a mint
happened, not WHOSE. Every new call site decodes its first token and asserts the identity —
the procedure whose absence let the confused-deputy bug above ship at all.
"""
from __future__ import annotations

import os
from typing import Optional


class ServiceTokenError(RuntimeError):
    """The mint failed, with the cause NAMED.

    A plain exception, not a framework error: each caller maps it to its own runtime's loud
    failure. A Restate handler lets it propagate (retryable — a Keycloak blip is transient
    infra, NOT an authorization denial, so it must not fail-and-release the way a 401 on the
    action does); a Dagster sensor raises `Failure`; the supervisor's OBSERVE-phase dispatch
    logs and proceeds token-less, because refusing before anything requires a token would be
    an outage of its own.
    """


def mint_token(*, client_id: str, client_secret: str, realm_url: Optional[str] = None,
               timeout: float = 15.0) -> str:
    """Mint a fresh access token for an EXPLICITLY NAMED client identity.

    `realm_url` defaults to ``KEYCLOAK_REALM_URL``. Raises `ServiceTokenError` naming the
    cause — "Keycloak was down so nothing happened and nothing said so" is precisely the
    invisible death this refuses.
    """
    import httpx

    realm = (realm_url or os.environ["KEYCLOAK_REALM_URL"]).rstrip("/")
    token_url = f"{realm}/protocol/openid-connect/token"
    try:
        resp = httpx.post(
            token_url,
            data={"grant_type": "client_credentials",
                  "client_id": client_id, "client_secret": client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        raise ServiceTokenError(
            f"mint_token: Keycloak token endpoint unreachable at {token_url}: {exc}"
        ) from exc
    if resp.status_code != 200:
        raise ServiceTokenError(
            f"mint_token: client-credentials mint failed HTTP {resp.status_code} for "
            f"client {client_id!r} at {token_url}: {resp.text[:300]}"
        )
    token = (resp.json() or {}).get("access_token")
    if not token:
        raise ServiceTokenError("mint_token: token response carried no access_token")
    return token


def mint_mesh_token(*, timeout: float = 15.0) -> str:
    """The EXTERNAL ENGINE binding — `MESH_CLIENT_ID` / `MESH_CLIENT_SECRET`.

    An engine packaged outside the platform gets the identical implementation platform
    engines use. That is the point: auth must not be conditional on running inside the
    platform, which would be the perimeter assumption reborn as an import graph.
    """
    return mint_token(
        client_id=os.environ["MESH_CLIENT_ID"],
        client_secret=os.environ["MESH_CLIENT_SECRET"],
        timeout=timeout,
    )

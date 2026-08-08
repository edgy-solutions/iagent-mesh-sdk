"""Transport auth for mesh tools — verify-if-present now, require later.

WHAT THIS REPLACES, and why it is not "adding auth to a fleet that had none".
`MeshTool`'s /execute handler already carried a check:

    if not auth_header and not os.getenv("LOCAL_DEV"):
        raise HTTPException(403, "Missing Topaz Ticket")

That is PRESENCE-ONLY. It refuses an absent header and accepts ANY value present —
`Authorization: Bearer anything` passes. A presence check is not authentication; it is a
gate that a manifest counts as present while it verifies nothing. (Third instance of that
class in this arc, after `core/authz.py` being importable-but-never-applied and the DA read
path deferring to a gateway keyed on a payload field.)

THE POSTURE IS DECLARED AND ANNOUNCED, NEVER IMPLIED
    OBSERVE  (default) — validate any token that arrives, record the outcome, REFUSE NOTHING.
    REQUIRE            — a valid token is mandatory; missing or invalid is 401/403.

Default is OBSERVE **because this ships to every engine at once**. The retroactive-inheritance
property that makes an SDK the right place for a cross-cutting obligation is exactly what makes
a refusing default dangerous: it would deny every token-less caller fleet-wide on the next
rebuild — the empty-caller incident shipped as a library bump. Callers migrate first; the flag
flips after.

WHY ITS OWN FLAG, not `ENABLE_AGENTIC_AUTH`. That flag gates two Topaz ASKS (catalog can_view,
per-chunk can_read). It was found on 2026-08-07 to gate no JWT verification at all — the
verification function existed and was applied nowhere. Overloading it to also mean "require
JWTs" would recreate the three-jobs hazard on a flag whose blast radius was just corrected
downward. These are different enforcement layers with different caller-readiness gates, so they
stay independently flippable.

READING THE MIGRATION RATHER THAN ASSERTING IT. In OBSERVE mode every request logs its caller
posture, so "all callers migrated" stops being an enumeration someone vouches for and becomes a
gauge: the flip is ready when the unverified-caller count reads zero. `transport auth: OBSERVE
(default)` is also a pre-positioned assertion — after the contract phase it is a string the
system must never emit.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

# MODULE-LEVEL on purpose. This file uses `from __future__ import annotations`, so every
# annotation is a STRING that FastAPI resolves via typing.get_type_hints() against MODULE
# GLOBALS. Importing Request inside the factory made it a local, the string "Request" did
# not resolve, and FastAPI fell back to treating the parameter as a QUERY param — every
# request 422'd with {'loc': ['query','request']}. A dependency that 422s on every call is
# a fleet-wide outage shipped as a library bump; the OBSERVE-serves tests caught it.
from fastapi import HTTPException, Request

logger = logging.getLogger("iagent_mesh.transport_auth")

POSTURE_OBSERVE = "OBSERVE"
POSTURE_REQUIRE = "REQUIRE"


def _raw_posture() -> Optional[str]:
    return os.getenv("REQUIRE_TRANSPORT_AUTH")


def resolve_posture() -> str:
    raw = _raw_posture()
    return POSTURE_REQUIRE if (raw or "").lower() in ("true", "1", "yes") else POSTURE_OBSERVE


def posture_line(component: str = "mesh-tool") -> str:
    """The startup announcement. Names the SOURCE as well as the state, per the
    admitted_by pattern: after the contract phase `OBSERVE (default)` must be impossible,
    and a line that cannot tell "nobody configured this" from "someone chose this" cannot
    demonstrate that."""
    src = "explicit config" if _raw_posture() is not None else "default"
    return f"transport auth: {resolve_posture()} ({src}) [{component}]"


_PKG_LOGGER = logging.getLogger("iagent_mesh")
_AUTOCONFIG_MARK = "_iagent_mesh_gauge_handler"


def _emits_info(lg: logging.Logger) -> bool:
    """Would an INFO record on `lg` actually reach a handler?

    Two independent ways to emit nothing, and both must be checked: the record can be
    filtered by EFFECTIVE LEVEL before dispatch, or it can pass the level and find NO
    HANDLER anywhere on the propagation chain (falling to `logging.lastResort`, which is
    itself WARNING). Checking one and not the other is how this bug survived review.
    """
    if lg.getEffectiveLevel() > logging.INFO:
        return False
    cur: Optional[logging.Logger] = lg
    while cur:
        if cur.handlers:
            return True
        cur = cur.parent if cur.propagate else None
    return False


def ensure_gauge_visible() -> bool:
    """Make this package's INFO records visible IF AND ONLY IF they would otherwise vanish.

    WHY THIS EXISTS. `make_transport_auth_dependency` logs one line per request, and its own
    docstring calls that "what turns the migration into a gauge instead of a claim". It was
    still a claim: no mesh engine configures logging, so the record fell through to
    `logging.lastResort` (WARNING) and was DISCARDED. Twelve services announced `OBSERVE` at
    startup and then observed nothing — and the contract flip's precondition is "the
    unverified-caller count reads zero", which a silent gauge satisfies perfectly and falsely.
    ZERO-BECAUSE-SILENT AND ZERO-BECAUSE-CLEAN ARE THE TWO STATES THE INSTRUMENT EXISTS TO
    SEPARATE. Python's logging defaults are the `uv sync --frozen` shape: a system instructed
    by default to be silent about a disagreement it should be loud about.

    ADDITIVE AND DEFERENTIAL, which is the whole contract of this function:

    * If the records already emit, do NOTHING. An app that configured logging owns its
      configuration, and a second handler here would DOUBLE-EMIT into every properly
      configured deployment — trading a silent gauge for a duplicated one.
    * If they are filtered only by LEVEL while handlers exist upstream, lower the level on
      THIS PACKAGE'S logger and stop. No handler is added, so nothing duplicates.
    * Only when no handler exists anywhere on the chain is one attached — and it attaches to
      the `iagent_mesh` namespace, NEVER to root. The SDK earns the right to make ITS OWN
      records visible; it does not get to reconfigure the host's logging. Same boundary as
      everywhere else: the shim owns its obligation, never the app's.

    Idempotent. Set ``IAGENT_MESH_LOG_AUTOCONFIG=0`` to disable — which exists so the gauge's
    own witness can be BROKEN ON PURPOSE and shown to go dark, because a leg of a litany that
    has never gone red is not yet a check.

    Returns True if this call changed anything.
    """
    if os.getenv("IAGENT_MESH_LOG_AUTOCONFIG", "1").lower() in ("0", "false", "no"):
        return False
    if _emits_info(logger):
        return False

    changed = False
    if _PKG_LOGGER.getEffectiveLevel() > logging.INFO:
        _PKG_LOGGER.setLevel(logging.INFO)
        changed = True

    # Re-check: lowering the level may be sufficient when the host has handlers upstream.
    if _emits_info(logger):
        return changed

    if not any(getattr(h, _AUTOCONFIG_MARK, False) for h in _PKG_LOGGER.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setLevel(logging.INFO)
        h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        setattr(h, _AUTOCONFIG_MARK, True)
        _PKG_LOGGER.addHandler(h)
        changed = True
    return changed


def announce(component: str = "mesh-tool") -> str:
    # Before the announcement, so a service that announces OBSERVE is a service whose gauge
    # can actually be read. Announcing a posture whose evidence channel is dark is the exact
    # gate-with-paperwork shape this package exists to refuse.
    ensure_gauge_visible()
    line = posture_line(component)
    print(line, flush=True)
    return line


class CallerIdentity:
    """The verified (or unverified) caller of a mesh request.

    `authz_id` is the mint-contract subject — `svc:<name>` for a service, the
    USER_ENTITLEMENT_CLAIM value for a human. It is the ONLY field an authorization
    decision may key on; `raw` exists for logging and nothing else.
    """

    __slots__ = ("authz_id", "verified", "reason", "raw")

    def __init__(self, authz_id: Optional[str], verified: bool, reason: str, raw: Any = None):
        self.authz_id = authz_id
        self.verified = verified
        self.reason = reason
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover — logging aid
        who = self.authz_id or "none"
        return f"<caller {who} verified={self.verified} ({self.reason})>"


def _entitlement_claim() -> str:
    return os.getenv("USER_ENTITLEMENT_CLAIM", "email")


def verify_bearer(token: Optional[str]) -> CallerIdentity:
    """Validate a bearer token and extract the mint-contract subject.

    SIGNATURE VERIFICATION IS THE POINT and it is NOT optional in REQUIRE mode: a decode
    without signature checking is the presence-check defect wearing a JWT's clothes. When no
    verification key is configured the token is reported UNVERIFIED with the reason named —
    never silently trusted.
    """
    if not token:
        return CallerIdentity(None, False, "absent")

    try:
        import jwt  # PyJWT
    except ImportError:  # pragma: no cover — environment without PyJWT
        return CallerIdentity(None, False, "pyjwt-missing")

    key = os.getenv("MESH_JWT_PUBLIC_KEY") or os.getenv("KEYCLOAK_PUBLIC_KEY")
    if not key:
        # Honest-unverified: we can read who it CLAIMS to be, and we say so. This value is
        # legal to LOG and illegal to authorize on — REQUIRE mode refuses it below.
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except Exception as exc:  # noqa: BLE001
            return CallerIdentity(None, False, f"undecodable: {type(exc).__name__}")
        return CallerIdentity(claims.get(_entitlement_claim()), False, "no-verification-key")

    try:
        claims = jwt.decode(token, key, algorithms=["RS256", "HS256"],
                            options={"verify_aud": False})
    except Exception as exc:  # noqa: BLE001
        return CallerIdentity(None, False, f"invalid: {type(exc).__name__}")

    subject = claims.get(_entitlement_claim())
    if not subject:
        return CallerIdentity(None, False, f"no {_entitlement_claim()!r} claim")
    return CallerIdentity(subject, True, "verified", raw=claims)


def _bearer_from(header: Optional[str]) -> Optional[str]:
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return header.strip() or None


def make_transport_auth_dependency(component: str = "mesh-tool"):
    """FastAPI dependency implementing the posture. Returns a `CallerIdentity`.

    OBSERVE: never raises. Every request logs its posture, which is what turns the migration
    into a gauge instead of a claim.
    REQUIRE: 401 when absent, 403 when present-but-invalid — a deliberate distinction, because
    "you sent nothing" and "you sent something I could not trust" are different operator
    problems and collapsing them costs an incident's first hour.
    """
    async def transport_auth(request: Request) -> CallerIdentity:
        caller = verify_bearer(_bearer_from(request.headers.get("Authorization")))
        posture = resolve_posture()

        # GAUGE DISCRIMINANT. `caller: none` has two causes — a caller that never minted, and
        # one whose mint FAILED — and they mean opposite things for migration readiness. The
        # caller may state which via X-Auth-Status. That header is DIAGNOSTIC ONLY: it is
        # caller-asserted, unverifiable, and never reaches an authorization decision. Logged
        # as `claimed:` so no reader mistakes it for a verified fact.
        detail = caller.reason
        if caller.reason == "absent":
            claimed = request.headers.get("X-Auth-Status")
            detail = f"absent, claimed:{claimed}" if claimed else "absent, no mint attempted"

        logger.info("caller: %s (%s) posture=%s path=%s",
                    caller.authz_id or "none", detail, posture, request.url.path)

        if posture == POSTURE_REQUIRE:
            if caller.reason == "absent":
                raise HTTPException(status_code=401, detail="transport auth required")
            if not caller.verified:
                raise HTTPException(status_code=403,
                                    detail=f"transport auth failed: {caller.reason}")
        return caller

    return transport_auth

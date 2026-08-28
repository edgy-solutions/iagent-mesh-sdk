"""Transport auth for mesh tools — verify-if-present now, require later.

WHAT THIS REPLACES, and why it is not "adding auth to a fleet that had none".
`MeshTool`'s /execute handler already carried a check:

    if not auth_header and not os.getenv("LOCAL_DEV"):
        raise HTTPException(403, "Missing Topaz Ticket")

That is PRESENCE-ONLY. It refuses an absent header and accepts ANY value present —
`Authorization: Bearer anything` passes. A presence check is not authentication; it is a
gate that a manifest counts as present while it verifies nothing. CLOSED IN 0.2.0 (68e28c0)
by this module.

It was the third instance of that class in this arc, and the other two are recorded here with
their real status so this paragraph cannot read as a list of live holes:

  * `core/authz.py` importable-but-never-applied — CLOSED. Retired rather than repaired
    (invincible-agent 4500f2a, 2026-08-07): the module a manifest told everyone to adopt was
    deleted, because a gate nobody applies is worse than an absent one.
  * the DA read path deferring to a gateway keyed on a payload field — STILL OPEN, tracked as
    ``[[da-sends-no-user-token]]``. Engine DA takes its read subject from an unauthenticated
    request field rather than from a verified token, so the read is per-user in shape only.
    Named here because this SDK now offers the alternative — `CallerIdentity` on the handler,
    `require_authz_id()` at the read — which is what that item converges on.

THE POSTURE IS DECLARED AND ANNOUNCED, NEVER IMPLIED
    OBSERVE  (default) — validate any token that arrives, record the outcome, REFUSE NOTHING.
    REQUIRE            — a valid token is mandatory; missing or invalid is 401/403.

**The default is OBSERVE TODAY and the flip to REQUIRE is planned, tracked as
``[[transport-flip]]``.** Its stated precondition is not a date but a reading: every caller
enumerated and minting, corroborated by the gauge below. So the "refuses nothing" above is a
declared, instrumented, time-boxed posture with a named owner — not an oversight.

Default is OBSERVE **because this ships to every engine at once**. The retroactive-inheritance
property that makes an SDK the right place for a cross-cutting obligation is exactly what makes
a refusing default dangerous: it would deny every token-less caller fleet-wide on the next
rebuild — the empty-caller incident shipped as a library bump. Callers migrate first; the flag
flips after.

WHY ITS OWN FLAG, not `ENABLE_AGENTIC_AUTH`. That flag gates two Topaz ASKS (catalog can_view,
per-chunk can_read). It was found on 2026-08-07 to gate no JWT verification at all — the
verification function existed and was applied nowhere. THAT GAP IS CLOSED: verification lives
in this module (`verify_bearer`) and is applied at every engine as an app-level dependency
(SDK 0.2.0 / invincible-agent fb82af6). What remains is the flag's own flip, tracked as
``[[agentic-auth-flip]]`` and blocked on ``[[transport-flip]]``.

Overloading `ENABLE_AGENTIC_AUTH` to also mean "require JWTs" would recreate the three-jobs
hazard on a flag whose blast radius was just corrected downward. These are different
enforcement layers with different caller-readiness gates, so they stay independently flippable.

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
from contextvars import ContextVar
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


def docs_enabled() -> bool:
    """API documentation routes are OFF unless explicitly opted in (`IAGENT_MESH_DOCS=1`)."""
    return os.getenv("IAGENT_MESH_DOCS", "0").lower() in ("1", "true", "yes")


def app_docs_kwargs() -> dict:
    """FastAPI kwargs that disable `/docs`, `/redoc` and `/openapi.json` in deployment.

    WHY DISABLE RATHER THAN GATE — three arguments, and the middle one is decisive.

    * Deployed pods have no human readers. A route that serves nobody in production is
      deny-by-default's easiest case.
    * A gate here would admit NO LEGITIMATE TRAFFIC EVER: an authenticated *service* has no use
      for `/redoc`. A gate whose correct steady state is 100% denial is a disable wearing a
      dependency's cost.
    * The disclosure is reconnaissance-grade. `/openapi.json` enumerates the full verb surface
      of every engine, unauthenticated — knowing WHAT CAN BE DONE to a system is the map an
      attacker draws first, and it is the operation-dimension disclosure the SPO authz work
      already identified as its own risk axis.

    WHY THIS IS A KWARGS HELPER AND NOT A FACTORY. The SDK owns ONE app factory, but the ten
    platform engines construct `FastAPI(...)` themselves. A factory-only fix would protect the
    scaffolded engines and leave the fleet exposed — coverage decided by which construction path
    a service happened to use, which is the same shape as "fleet-wide meant ten because of a
    glob". So the POLICY lives here (one place decides) and every construction site applies it;
    a route-census assertion in the consumer's suite enforces that they all do.

    MEASURED, not theorised — **FIXED IN 0.4.0; the exposure below is HISTORY, not current
    behaviour.** Under REQUIRE on a live pod, `/openapi.json`, `/docs` and `/redoc` all returned
    200 UNAUTHENTICATED, because FastAPI registers them via Starlette's `add_route` — so
    app-level `dependencies=` never applies to them. Closed by this function (SDK 0.2.3,
    f24fdfd): the routes are not registered at all unless `IAGENT_MESH_DOCS=1` is set
    deliberately, and a route-census assertion in the consumer's suite holds every construction
    site to it.

    Docs were the KNOWN member of that class. Any FUTURE mount or `add_route` bypasses app-level
    dependencies the same way, so the class is open even though this instance is closed — which
    is why the census, not this function, is the durable control.
    """
    if docs_enabled():
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


def docs_line() -> str:
    src = "explicit config" if os.getenv("IAGENT_MESH_DOCS") is not None else "default"
    return f"api docs: {'ENABLED' if docs_enabled() else 'DISABLED'} ({src})"


def announce(component: str = "mesh-tool") -> str:
    # Before the announcement, so a service that announces OBSERVE is a service whose gauge
    # can actually be read. Announcing a posture whose evidence channel is dark is the exact
    # gate-with-paperwork shape this package exists to refuse.
    ensure_gauge_visible()
    line = posture_line(component)
    print(line, flush=True)
    # Announced next to the posture, so a production pod with docs ON declares its own anomaly
    # in the same breath as its enforcement stance — the pre-positioned-string pattern.
    print(docs_line(), flush=True)
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

    def require_authz_id(self) -> str:
        """The subject to authorize a DOWNSTREAM READ as — or a loud refusal.

        THIS IS THE FAIL-CLOSED ACCESSOR, and the distinction from `.authz_id` is the whole
        point. `.authz_id` is `Optional[str]` and legal to LOG; passing it straight into a data
        read is how an unresolved caller becomes a SILENT SERVICE READ:

            CortexDataClient(originator_email=caller.authz_id)   # None -> reads as the service

        `None` there does not fail. It falls back to the process's own identity, rows come back,
        nothing errors, and every user of the agent reads with the service's entitlements — the
        confused deputy, arriving with no symptom. Under OBSERVE (the default posture) an
        unauthenticated caller yields exactly that `None`, so this is the ORDINARY case, not an
        exotic one.

        So the read path gets an accessor that CANNOT return `None`:

            CortexDataClient(originator_email=caller.require_authz_id())

        Raises `PermissionError` naming the reason — "absent", "invalid: ...", "no 'email' claim"
        — because which of those it was decides whether the fix is a caller that never minted, a
        broken key, or a claim misconfigured for this deployment.
        """
        if not self.authz_id:
            raise PermissionError(
                f"caller identity unresolved ({self.reason}) — refusing to authorize a read. "
                "Reading as the service identity here would grant this caller the SERVICE's "
                "entitlements; if that is genuinely intended, say so explicitly rather than "
                "letting an unresolved caller decide it."
            )
        return self.authz_id


#: The request's caller, readable without threading a parameter through every frame.
#:
#: WHY A CONTEXTVAR AND NOT `request.state`. A helper three frames below the handler — the exact
#: place a `CortexDataClient` actually gets built — has no `Request`. Passing one down purely to
#: carry identity is the plumbing that does not get done, and the fallback when it is not done is
#: the silent service read. `default=None` means "no request in scope" (notebook, pipeline, test),
#: which is a DIFFERENT state from "in a request whose caller did not resolve" — the first may
#: legitimately fall back to a process identity, the second must never.
_CURRENT_CALLER: "ContextVar[Optional[CallerIdentity]]" = ContextVar(
    "iagent_mesh_current_caller", default=None
)


def current_caller() -> Optional[CallerIdentity]:
    """The caller of the request in scope, or `None` when not inside one.

    `None` means NO REQUEST — never "a request by nobody". A request whose caller did not
    resolve returns a `CallerIdentity` with `authz_id=None`, so a reader can tell the two apart
    and fail closed on the second. Collapsing them is what lets an agent-pod read fall through
    to a notebook-shaped env fallback.
    """
    return _CURRENT_CALLER.get()


def _entitlement_claim() -> str:
    return os.getenv("USER_ENTITLEMENT_CLAIM", "email")


def verify_bearer(token: Optional[str]) -> CallerIdentity:
    """Validate a bearer token and extract the mint-contract subject.

    SIGNATURE VERIFICATION IS THE POINT and it is NOT optional in REQUIRE mode: a decode
    without signature checking is the presence-check defect wearing a JWT's clothes. When no
    verification key is configured the token is reported UNVERIFIED with the reason named —
    never silently trusted — and under REQUIRE it is refused. Admitting it is the OBSERVE
    posture, tracked as ``[[transport-flip]]``, not a gap in this function.

    WHAT AN UNVERIFIED CALLER MEANS TODAY, stated plainly rather than left to inference. Under
    the default OBSERVE posture an unverified caller is ADMITTED — that is what OBSERVE means,
    and it is the migration state tracked as ``[[transport-flip]]``. Under REQUIRE the same
    caller is refused (401 absent / 403 unverifiable). The subject it reports is legal to LOG
    and illegal to AUTHORIZE on, which is why the read path goes through
    `CallerIdentity.require_authz_id()` rather than `.authz_id`.

    WHICH GATEWAY IS WHICH — the distinction matters and is easy to get backwards. The USER-PLANE
    gateway (cortex-bff, `src/iagent/gateway.py`) DOES verify: live JWKS, `algorithms=["RS256"]`
    pinned, signature checking on, probed with a forged/legitimate pair. The still-open instance
    is the dag-tools CENTRAL GATEWAY on the data plane, which decodes with signature checking
    off, so the read subject it authorizes on is asserted rather than proven — tracked as
    ``[[dag-tools-gateway-unverified-subject]]``, blocked on the OBSERVE reading and on
    ``[[da-sends-no-user-token]]``. This module's verification does not fix that hop; it is what
    makes fixing it possible.
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
        # legal to LOG and illegal to authorize on — REQUIRE mode refuses it below, and
        # admitting it meanwhile is the OBSERVE posture tracked as [[transport-flip]].
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


# Paths the KUBELET reaches, never the mesh. Exempt from enforcement AND from the gauge.
#
# WHY THIS IS A SAFETY FEATURE, NOT A HOLE. `transport_auth` is applied as an app-level
# dependency, so it covers `/health`. The kubelet sends no bearer token and never will. Under
# REQUIRE every liveness probe would 401, every pod would be marked unhealthy, and the fleet
# would restart itself into a cluster-wide outage — CAUSED BY THE SECURITY CONTROL, not by an
# attacker. Measured at day zero: 549 gauge lines across ten services, essentially all probes.
#
# The second reason is the gauge's arithmetic. Probe traffic dominates by ~10:1, so an
# unverified count that includes it CAN NEVER REACH ZERO — making the contract flip's own
# precondition unsatisfiable, and an unsatisfiable precondition is one that eventually gets
# waived by someone who decides the number "doesn't really count". Exempting probes is what
# turns "reads zero" into a reachable target rather than a formality.
#
# Health endpoints are the KUBELET'S CONTRACT, not the mesh's: they expose liveness, not
# gated content. Everything else stays gated.
#
# EXACT MATCH, never prefix. A prefix rule would exempt `/health-records` — the shape where an
# operational convenience quietly becomes a data leak.
#
# `/ping` is deliberately NOT here. It is not a kubelet convention, and including it broke a
# rule this set exists to uphold: the SDK's own suite serves `/ping` as its ordinary gated
# route, so exempting it would have made
# `test_OBSERVE_serves_a_request_with_no_token_at_all` pass TRIVIALLY — a false green in the
# tests that prove the dependency enforces at all. An exemption list must be short enough that
# every entry is a kubelet path and nothing else.
DEFAULT_EXEMPT_PATHS = ("/health", "/healthz", "/livez", "/readyz")


def _configured_exempt_paths() -> tuple:
    """`TRANSPORT_AUTH_EXEMPT_PATHS` (comma-separated) REPLACES the default set.

    Services differ (`mesh-registrar` probes `/v1/healthz`), and an operator must be able to
    correct a probe path without a code change and a rebuild — the alternative is an outage
    waiting on a release. Replaces rather than extends, so the effective set is always exactly
    what is configured and never a union nobody can read off one value.
    """
    raw = os.getenv("TRANSPORT_AUTH_EXEMPT_PATHS")
    if raw is None:
        return DEFAULT_EXEMPT_PATHS
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def make_transport_auth_dependency(component: str = "mesh-tool", exempt_paths=None):
    """FastAPI dependency implementing the posture. Returns a `CallerIdentity`.

    OBSERVE: never raises. Every non-exempt request logs its posture, which is what turns the
    migration into a gauge instead of a claim.
    REQUIRE: 401 when absent, 403 when present-but-invalid — a deliberate distinction, because
    "you sent nothing" and "you sent something I could not trust" are different operator
    problems and collapsing them costs an incident's first hour.

    `exempt_paths` overrides both the default set and the env var, for a service whose probe
    path is a fixed fact of its own code rather than a deployment choice.

    ALSO PUBLISHES the caller to `_CURRENT_CALLER` so code below the handler can read it without
    a `Request`. FastAPI DISCARDS an app-level dependency's return value — it is not injectable
    into a route and never reaches `request.state` — so for the ten engines that mount this at
    app level the contextvar is the ONLY way the computed identity survives at all. It was being
    resolved, logged, and thrown away one frame before anyone could use it.
    """
    async def transport_auth(request: Request) -> CallerIdentity:
        path = request.url.path
        exempt = tuple(exempt_paths) if exempt_paths is not None else _configured_exempt_paths()
        if path in exempt:
            # DEBUG, not INFO: exempt traffic must not enter the gauge, or the count it feeds
            # can never reach zero. Still logged, because a probe path silently swallowing
            # requests is its own debugging problem — and because `exempt=` in the line is what
            # lets an operator confirm the exemption is doing what they think.
            logger.debug("caller: exempt (probe path) posture=%s path=%s exempt=true",
                         resolve_posture(), path)
            probe_caller = CallerIdentity(None, False, "exempt-probe-path")
            _CURRENT_CALLER.set(probe_caller)
            return probe_caller

        caller = verify_bearer(_bearer_from(request.headers.get("Authorization")))
        posture = resolve_posture()

        # Published BEFORE the REQUIRE branch below can raise, so a handler that never runs is
        # not the reason the var is unset — and so the value is in scope for anything the
        # framework runs after the dependency (including the exception path's logging).
        #
        # No token is taken to reset. Starlette runs each request in its own copied context, so
        # this write is request-scoped ALREADY and cannot leak into the next request; a manual
        # reset here would only be theatre. The property is pinned by a test that runs two
        # requests with different callers through one app.
        _CURRENT_CALLER.set(caller)

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

"""The ONE authenticated registration transport — mint, retry, and a named failure.

WHY THIS MODULE EXISTS. Two implementations of `_emit_to_registrar` existed, one here and one
in the platform (`agent_fleet/utils/mesh_registration.py`), both POSTing `/v1/register`. That
is the same two-transcription shape that produced the confused deputy, where one mint read
`REVIEW_STARTER_CLIENT_ID` and the other read `MESH_CLIENT_ID` — a divergence nobody saw until
a token was decoded.

BUT THE OBVIOUS CONSOLIDATION WAS BACKWARDS, and the read is what caught it. The platform's
version already implemented the retry semantics ruled in ADR-0006's addendum — 422 is a
permanent Contract D rejection (the ontology must be fixed; retrying cannot help), 5xx is
retry-safe because the saga compensated, bounded with exponential backoff. The SDK's version
had NONE of that: one POST, `raise RuntimeError` on any non-200. "Platform binds the SDK"
would therefore have DELETED the ruled behaviour in the name of one implementation.

So the transport moves here carrying the platform's semantics, and both callers bind it.

ONE SEAM FOR AUTH, N BODIES FOR CONTENT. The manifest bodies differ for real — the platform
constructs verb/URI content and a presentation variant the SDK's lifespan registration does not
— and forcing those to merge would satisfy the one-implementation rule's LETTER against its
INTENT. The rule's target is the place where credentials attach and divergence is invisible:
the HTTP POST. That is here, exactly once.

THE FAILURE IS NAMED, NOT JUST LOGGED. `mint failed` and `registrar refused` are two causes
with ONE symptom — the engine's verbs are absent from routing — and an operator who cannot tell
them apart spends the first hour of an incident learning which side of the call broke. The
result object carries which, so the caller's announcement can say
`unregistered (mint failed: ...)` or `unregistered (registrar 5xx after N attempts)`.

WHY RUNNING UNREGISTERED IS SAFE, and it is a routing-layer fact rather than optimism: routing
is conjunctive, so a verb that never registered simply never routes. The engine is degraded and
visible, never corrupt. That is what makes retry-then-proceed the correct posture instead of
failing the process — and it is why the loud surface matters more than the retry count.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("iagent_mesh.registration")


class RegistrationResult:
    """Outcome of a registration attempt, with the CAUSE named."""

    __slots__ = ("registered", "reason", "attempts", "status_code")

    def __init__(self, registered: bool, reason: str = "", attempts: int = 0,
                 status_code: Optional[int] = None):
        self.registered = registered
        self.reason = reason
        self.attempts = attempts
        self.status_code = status_code

    def announcement(self, component: str) -> str:
        """The line a service prints so 'up but unregistered' is an ALARM, not a mystery."""
        if self.registered:
            return f"mesh registration: OK [{component}]"
        return f"mesh registration: UNREGISTERED ({self.reason}) [{component}]"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RegistrationResult registered={self.registered} reason={self.reason!r}>"


def register_with_mesh(
    registrar_url: str,
    manifest: Dict[str, Any],
    *,
    component: str = "mesh-tool",
    mint: Optional[Callable[[], str]] = None,
    timeout: float = 30.0,
) -> RegistrationResult:
    """POST a registration manifest under an authenticated identity. Never raises.

    `mint` returns a bearer token for THIS engine's identity. Passed as an argument, never read
    from ambient env here: identity is an argument, which is the rule that stopped the
    supervisor from dispatching as the review starter.

    Retry semantics (ADR-0006 addendum, preserved from the platform implementation):
      * 200  -> registered.
      * 422  -> PERMANENT Contract D rejection. Return immediately; the ontology must be fixed
                and retrying cannot help, so retrying would only delay the alarm.
      * 5xx  -> retry-safe (the saga compensated, so the substrate is clean). Bounded
                exponential backoff.
      * mint failure -> retried on the same schedule, because Keycloak being briefly
                unreachable at boot is transient infrastructure, NOT an authorization denial.
    """
    import httpx

    max_attempts = int(os.getenv("MESH_REGISTRAR_SDK_MAX_ATTEMPTS", "5"))
    backoff = float(os.getenv("MESH_REGISTRAR_SDK_INITIAL_BACKOFF_S", "0.5"))
    max_backoff = float(os.getenv("MESH_REGISTRAR_SDK_MAX_BACKOFF_S", "4.0"))

    last = RegistrationResult(False, "no attempt made")
    for attempt in range(1, max_attempts + 1):
        headers = {}
        if mint is not None:
            try:
                headers["Authorization"] = f"Bearer {mint()}"
            except Exception as exc:  # noqa: BLE001 — named, then retried
                last = RegistrationResult(
                    False, f"mint failed: {type(exc).__name__}: {str(exc)[:120]}", attempt)
                logger.warning("registration mint failed (attempt %d/%d): %s",
                               attempt, max_attempts, exc)
                if attempt < max_attempts:
                    time.sleep(backoff); backoff = min(backoff * 2, max_backoff)
                    continue
                return last

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{registrar_url}/v1/register", json=manifest,
                                   headers=headers)
        except Exception as exc:  # noqa: BLE001
            last = RegistrationResult(
                False, f"registrar unreachable: {type(exc).__name__}", attempt)
            logger.warning("registrar unreachable (attempt %d/%d): %s",
                           attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(backoff); backoff = min(backoff * 2, max_backoff)
                continue
            return last

        if resp.status_code == 200:
            return RegistrationResult(True, "", attempt, 200)

        if resp.status_code == 422:
            # PERMANENT. Retrying a Contract D rejection only delays the alarm.
            return RegistrationResult(
                False, f"registrar rejected 422 (Contract D): {resp.text[:200]}",
                attempt, 422)

        last = RegistrationResult(
            False, f"registrar {resp.status_code} after {attempt} attempt(s)",
            attempt, resp.status_code)
        if resp.status_code >= 500 and attempt < max_attempts:
            logger.warning("registrar %s (attempt %d/%d); retrying in %.2fs",
                           resp.status_code, attempt, max_attempts, backoff)
            time.sleep(backoff); backoff = min(backoff * 2, max_backoff)
            continue
        return last

    return last

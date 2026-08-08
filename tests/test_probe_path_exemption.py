"""Probe paths are exempt — the change that makes REQUIRE survivable and its gauge reachable.

MEASURED, NOT ASSUMED. Day zero across ten deployed services: 549 gauge lines, 0 verified, 549
unverified — essentially all of it `path=/health` from the kubelet. `transport_auth` is an
app-level dependency, so it covers health endpoints, and the kubelet sends no bearer token and
never will. Two consequences, both fatal to the contract phase:

  1. Under REQUIRE every liveness probe 401s -> every pod is marked unhealthy -> the fleet
     restarts itself into a CLUSTER-WIDE OUTAGE CAUSED BY THE SECURITY CONTROL.
  2. Probe traffic dominates ~10:1, so an unverified count including it CAN NEVER REACH ZERO.
     The flip's own precondition becomes unsatisfiable — and an unsatisfiable precondition is
     one that eventually gets waived by someone deciding the number "doesn't really count".

So exemption is not a hole; it is what makes the gate deployable and its gauge honest. Health
endpoints are the KUBELET'S contract, not the mesh's: liveness, never gated content.
"""
from __future__ import annotations

import logging

import pytest

from iagent_mesh import transport_auth as ta

fastapi = pytest.importorskip("fastapi")
starlette_test = pytest.importorskip("fastapi.testclient")


def _client(exempt_paths=None):
    app = fastapi.FastAPI(dependencies=[
        fastapi.Depends(ta.make_transport_auth_dependency("engine-x", exempt_paths=exempt_paths))
    ])

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/health-records")      # the prefix trap, as a real route
    async def health_records():
        return {"secret": "gated content"}

    @app.get("/v1/healthz")          # a service-specific probe path (mesh-registrar's)
    async def healthz():
        return {"ok": True}

    @app.get("/query")               # an ordinary gated route
    async def query():
        return {"ok": True}

    return starlette_test.TestClient(app, raise_server_exceptions=False)


# --- the outage this prevents -------------------------------------------------
def test_REQUIRE_does_not_401_the_kubelet(monkeypatch):
    """THE test. Without it, flipping REQUIRE takes the fleet down with no attacker involved."""
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    assert ta.resolve_posture() == ta.POSTURE_REQUIRE, "premise: posture must be REQUIRE"
    assert _client().get("/health").status_code == 200, (
        "a token-less probe was refused under REQUIRE — this is the self-inflicted fleet "
        "outage the exemption exists to prevent"
    )


def test_REQUIRE_still_401s_an_ordinary_route(monkeypatch):
    """POSITIVE CONTROL. Without it, an exemption that swallowed EVERY path would pass above."""
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    assert _client().get("/query").status_code == 401, (
        "REQUIRE stopped enforcing on a normal route — the exemption is over-broad and the "
        "gate is now decorative"
    )


# --- the security case --------------------------------------------------------
def test_exemption_is_exact_match_never_prefix(monkeypatch):
    """`/health-records` must NOT be exempt.

    A prefix rule would exempt it, which is the shape where an operational convenience
    quietly becomes a data leak — a gated route released because its name starts like a
    probe's.
    """
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    assert _client().get("/health-records").status_code == 401, (
        "/health-records was exempted — the match is behaving as a PREFIX, and a route "
        "serving gated content is now unauthenticated"
    )


# --- the gauge ----------------------------------------------------------------
def test_probe_traffic_does_not_enter_the_gauge(caplog):
    """Exempt requests must not log at INFO, or the count they feed can never reach zero."""
    with caplog.at_level(logging.INFO, logger="iagent_mesh.transport_auth"):
        _client().get("/health")
    gauge = [r for r in caplog.records if r.levelno >= logging.INFO and "caller:" in r.getMessage()]
    assert not gauge, f"probe traffic entered the gauge at INFO: {[r.getMessage() for r in gauge]}"


def test_ordinary_traffic_still_enters_the_gauge(caplog):
    """POSITIVE CONTROL for the above: the gauge must still see real callers."""
    with caplog.at_level(logging.INFO, logger="iagent_mesh.transport_auth"):
        _client().get("/query")
    msgs = [r.getMessage() for r in caplog.records if "caller:" in r.getMessage()]
    assert any("path=/query" in m for m in msgs), f"the gauge lost a real caller; saw {msgs}"


def test_exempt_requests_are_still_visible_at_debug(caplog):
    """Not silent — a probe path swallowing requests is its own debugging problem, and
    `exempt=true` is how an operator confirms the exemption does what they believe."""
    with caplog.at_level(logging.DEBUG, logger="iagent_mesh.transport_auth"):
        _client().get("/health")
    assert any("exempt=true" in r.getMessage() for r in caplog.records), (
        "exempt requests vanish entirely — an operator cannot confirm the exemption applied"
    )


# --- configuration ------------------------------------------------------------
def test_env_var_replaces_the_default_set(monkeypatch):
    """Services differ (mesh-registrar probes /v1/healthz); an operator must be able to fix a
    probe path without a rebuild, or the alternative is an outage waiting on a release."""
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    monkeypatch.setenv("TRANSPORT_AUTH_EXEMPT_PATHS", "/v1/healthz")
    c = _client()
    assert c.get("/v1/healthz").status_code == 200, "configured exempt path was still enforced"
    assert c.get("/health").status_code == 401, (
        "the env var EXTENDED the defaults instead of REPLACING them — the effective set must "
        "be readable off one value, not a union nobody can see"
    )


def test_explicit_argument_beats_the_env(monkeypatch):
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    monkeypatch.setenv("TRANSPORT_AUTH_EXEMPT_PATHS", "/v1/healthz")
    c = _client(exempt_paths=["/health"])
    assert c.get("/health").status_code == 200
    assert c.get("/v1/healthz").status_code == 401, "the env overrode an explicit argument"


def test_ping_is_not_exempt_by_default():
    """Regression guard on the exemption LIST itself.

    `/ping` was briefly in the default set. The SDK's own suite serves `/ping` as its ordinary
    gated route, so that would have made `test_OBSERVE_serves_a_request_with_no_token_at_all`
    pass TRIVIALLY — a false green inside the tests that prove the dependency enforces at all.
    Every entry in this list must be a kubelet path and nothing else.
    """
    assert "/ping" not in ta.DEFAULT_EXEMPT_PATHS
    assert set(ta.DEFAULT_EXEMPT_PATHS) == {"/health", "/healthz", "/livez", "/readyz"}

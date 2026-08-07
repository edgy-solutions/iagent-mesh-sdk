"""Transport auth — OBSERVE by default, REQUIRE reachable, both PROVEN.

The break-on-purpose here is DOUBLE-SIDED on purpose, because this ships to every engine at
once via an SDK bump:

  * OBSERVE proven permissive — an invalid token is recorded and the request is STILL SERVED.
    If this ever went red, a library bump would deny every token-less caller fleet-wide: the
    empty-caller incident shipped as a dependency upgrade.
  * REQUIRE proven reachable — the contract phase actually refuses. A flag that cannot be
    shown to change behaviour is a flag nobody can trust to close the migration.

A guard that has never failed has not been shown to guard anything — and here BOTH the
failing and the not-failing behaviours are the guarantee, so both get a test.
"""
from __future__ import annotations

import importlib

import pytest

ta = importlib.import_module("iagent_mesh.transport_auth")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("REQUIRE_TRANSPORT_AUTH", "MESH_JWT_PUBLIC_KEY", "KEYCLOAK_PUBLIC_KEY",
              "USER_ENTITLEMENT_CLAIM"):
        monkeypatch.delenv(k, raising=False)


# --- posture resolution + the announcement ----------------------------------
def test_default_posture_is_observe():
    assert ta.resolve_posture() == ta.POSTURE_OBSERVE


def test_announcement_names_its_source(monkeypatch):
    """`OBSERVE (default)` is a pre-positioned assertion: after the contract phase it is a
    string the system must never emit. That only works if source is distinguishable."""
    assert "OBSERVE (default)" in ta.posture_line("engine-x")
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "false")
    assert "OBSERVE (explicit config)" in ta.posture_line("engine-x")
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    assert "REQUIRE (explicit config)" in ta.posture_line("engine-x")


# --- verification honesty ----------------------------------------------------
def test_absent_token_is_absent_not_invalid():
    c = ta.verify_bearer(None)
    assert c.verified is False and c.reason == "absent" and c.authz_id is None


def test_unsigned_read_is_reported_unverified_never_trusted():
    """Without a verification key we may READ the claim and must NOT trust it. A decode
    without signature checking is the presence-check defect wearing a JWT's clothes."""
    jwt = pytest.importorskip("jwt")
    tok = jwt.encode({"email": "svc:impostor"}, "k", algorithm="HS256")
    c = ta.verify_bearer(tok)
    assert c.authz_id == "svc:impostor"      # readable
    assert c.verified is False               # never trusted
    assert c.reason == "no-verification-key"


def test_valid_signature_yields_a_verified_subject(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "topsecret")
    tok = jwt.encode({"email": "svc:supervisor"}, "topsecret", algorithm="HS256")
    c = ta.verify_bearer(tok)
    assert c.verified is True and c.authz_id == "svc:supervisor"


def test_tampered_token_is_invalid(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "topsecret")
    tok = jwt.encode({"email": "svc:supervisor"}, "WRONG-KEY", algorithm="HS256")
    c = ta.verify_bearer(tok)
    assert c.verified is False and c.reason.startswith("invalid")


def test_subject_comes_from_the_entitlement_claim(monkeypatch):
    """Keyed on the authz identity, not on 'email' the concept — work names an
    employee-id claim, and hardcoding `email` is the email-as-identity defect."""
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("USER_ENTITLEMENT_CLAIM", "employee_id")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "k")
    tok = jwt.encode({"employee_id": "E01234567", "email": "ignored@example.com"},
                     "k", algorithm="HS256")
    assert ta.verify_bearer(tok).authz_id == "E01234567"


# --- the double-sided behaviour proof ----------------------------------------
def _client_with_dependency():
    fastapi = pytest.importorskip("fastapi")
    starlette_test = pytest.importorskip("fastapi.testclient")
    app = fastapi.FastAPI(
        dependencies=[fastapi.Depends(ta.make_transport_auth_dependency("engine-x"))]
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return starlette_test.TestClient(app, raise_server_exceptions=False)


def test_OBSERVE_serves_a_request_with_no_token_at_all():
    """THE side that must never regress: a refusing default would deny eight token-less
    caller modules fleet-wide on the next rebuild."""
    assert _client_with_dependency().get("/ping").status_code == 200


def test_OBSERVE_serves_a_request_with_an_INVALID_token(monkeypatch):
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "right-key")
    jwt = pytest.importorskip("jwt")
    bad = jwt.encode({"email": "svc:x"}, "wrong-key", algorithm="HS256")
    r = _client_with_dependency().get("/ping", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 200, "OBSERVE must record, never refuse"


def test_REQUIRE_refuses_absent_with_401(monkeypatch):
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    assert _client_with_dependency().get("/ping").status_code == 401


def test_REQUIRE_refuses_invalid_with_403(monkeypatch):
    """401 vs 403 deliberately distinguished: 'you sent nothing' and 'you sent something I
    could not trust' are different operator problems, and collapsing them costs an
    incident's first hour."""
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "right-key")
    jwt = pytest.importorskip("jwt")
    bad = jwt.encode({"email": "svc:x"}, "wrong-key", algorithm="HS256")
    r = _client_with_dependency().get("/ping", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 403


def test_REQUIRE_admits_a_verified_caller(monkeypatch):
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", "k")
    jwt = pytest.importorskip("jwt")
    good = jwt.encode({"email": "svc:supervisor"}, "k", algorithm="HS256")
    r = _client_with_dependency().get("/ping", headers={"Authorization": f"Bearer {good}"})
    assert r.status_code == 200


# --- the gauge discriminant --------------------------------------------------
def test_absent_caller_records_whether_a_mint_was_attempted(caplog):
    """TWO CAUSES, ONE SYMPTOM. A caller that never minted and one whose mint FAILED both
    arrive as `caller: none`, and they mean opposite things for migration readiness — the
    first is an unmigrated caller, the second is a Keycloak blip. Without the discriminant a
    blip reads as readiness REGRESSING and the contract flip's gauge inherits noise it
    cannot explain."""
    import logging
    client = _client_with_dependency()

    with caplog.at_level(logging.INFO, logger="iagent_mesh.transport_auth"):
        client.get("/ping")
    assert "no mint attempted" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="iagent_mesh.transport_auth"):
        client.get("/ping", headers={"X-Auth-Status": "mint-failed:ServiceTokenError"})
    assert "claimed:mint-failed:ServiceTokenError" in caplog.text


def test_the_diagnostic_header_can_never_authorize(monkeypatch):
    """X-Auth-Status is CALLER-ASSERTED and therefore unverifiable — the exact property that
    made the payload-written subject a spoofing surface. Legal to log, illegal to trust: a
    caller claiming a successful mint must still be refused under REQUIRE."""
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    r = _client_with_dependency().get("/ping", headers={"X-Auth-Status": "verified:svc:admin"})
    assert r.status_code == 401, "a claimed status must never substitute for a token"

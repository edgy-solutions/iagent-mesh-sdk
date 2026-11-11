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

v0.9.20 added a second double-sided property to prove: RS256-only + issuer/audience allow-lists
+ JWKS key resolution. Each refusal arm below is paired with a positive control using the SAME
shapes, correctly configured — a harness must prove it can fail, never just that it can pass.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ta = importlib.import_module("iagent_mesh.transport_auth")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _craft_hs256_token(payload: dict, secret: str) -> str:
    """Build an HS256 JWT by hand, bypassing PyJWT's own `encode()` — which, as of the
    installed version, refuses to use a PEM-shaped string as an HMAC secret
    (`InvalidKeyError: ... should not be used as an HMAC secret`). That guard is exactly the
    mitigation this change's own defense is about, but it means `jwt.encode(..., algorithm=
    "HS256")` can no longer be used to PRODUCE the audit's attack token: an attacker crafting a
    forged JWT by hand is not bound by pyjwt's client-side encode-time guard, and the server-side
    `verify_bearer` must refuse such a token on its own — which is what this test actually
    proves."""
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "." + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def _rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


# One keypair per module is enough — generation is ~tens of ms, no need to repeat it per test.
_PRIVATE_PEM, _PUBLIC_PEM = _rsa_keypair()
# A SECOND, unrelated keypair for the tampered-signature case.
_OTHER_PRIVATE_PEM, _OTHER_PUBLIC_PEM = _rsa_keypair()

ISSUER = "https://issuer.example.com/realm"
AUDIENCE = "iagent-mesh"


def _claims(**overrides):
    base = {"email": "svc:supervisor", "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 3600}
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("REQUIRE_TRANSPORT_AUTH", "MESH_JWT_PUBLIC_KEY", "KEYCLOAK_PUBLIC_KEY",
              "USER_ENTITLEMENT_CLAIM", "MESH_JWT_ACCEPTED_ISSUERS",
              "MESH_JWT_ACCEPTED_AUDIENCES", "MESH_JWT_JWKS_URL"):
        monkeypatch.delenv(k, raising=False)
    # One `jwt.PyJWKClient` is now cached per URL across calls (see `_jwks_client_for`), so a
    # test that monkeypatches `jwt.PyJWKClient` must not leak its stub into a later test that
    # reuses the same URL string — cleared before every test, never in production.
    ta._clear_jwks_client_cache()


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
    without signature checking is the presence-check defect wearing a JWT's clothes. This is the
    one test allowed to keep an HS256-"signed" token: this branch never checks a signature at
    all (no key, no JWKS URL configured), so the algorithm used to produce it is irrelevant."""
    jwt = pytest.importorskip("jwt")
    tok = jwt.encode({"email": "svc:impostor"}, "k", algorithm="HS256")
    c = ta.verify_bearer(tok)
    assert c.authz_id == "svc:impostor"      # readable
    assert c.verified is False               # never trusted
    assert c.reason == "no-verification-key"


def test_valid_signature_yields_a_verified_subject(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    tok = jwt.encode(_claims(email="svc:supervisor"), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is True and c.authz_id == "svc:supervisor"


def test_tampered_token_is_invalid(monkeypatch):
    """Signed with a DIFFERENT RSA private key than the one configured — same claimed
    issuer/audience, wrong signature."""
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    tok = jwt.encode(_claims(), _OTHER_PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is False and c.reason.startswith("invalid")


def test_subject_comes_from_the_entitlement_claim(monkeypatch):
    """Keyed on the authz identity, not on 'email' the concept — work names an
    employee-id claim, and hardcoding `email` is the email-as-identity defect."""
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("USER_ENTITLEMENT_CLAIM", "employee_id")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    tok = jwt.encode(
        _claims(employee_id="E01234567", email="ignored@example.com"),
        _PRIVATE_PEM, algorithm="RS256",
    )
    assert ta.verify_bearer(tok).authz_id == "E01234567"


# --- v0.9.20 seals: RS256-only, issuer/audience allow-lists, JWKS ------------
def test_HS256_token_is_refused_RS256_control_is_admitted(monkeypatch):
    """The audit's own phrasing: "including one signed with a key that would pass as an HMAC
    secret" — the RSA PUBLIC PEM string itself, used as an HMAC secret, used to verify clean.
    Crafted by hand (`_craft_hs256_token`) because PyJWT's own `encode()` now refuses to use a
    PEM-shaped string as an HMAC secret — an attacker forging a token is not bound by that
    client-side guard, so `verify_bearer` must refuse it on its own."""
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    hs_tok = _craft_hs256_token(_claims(), _PUBLIC_PEM)
    c_hs = ta.verify_bearer(hs_tok)
    assert c_hs.verified is False and c_hs.reason.startswith("invalid")

    rs_tok = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256")
    c_rs = ta.verify_bearer(rs_tok)
    assert c_rs.verified is True


def test_wrong_issuer_is_refused_correct_issuer_is_the_control(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    wrong_tok = jwt.encode(_claims(iss="https://not-accepted.example.com"), _PRIVATE_PEM,
                           algorithm="RS256")
    c_wrong = ta.verify_bearer(wrong_tok)
    assert c_wrong.verified is False and c_wrong.reason.startswith("invalid")

    right_tok = jwt.encode(_claims(iss=ISSUER), _PRIVATE_PEM, algorithm="RS256")
    c_right = ta.verify_bearer(right_tok)
    assert c_right.verified is True


def test_wrong_audience_is_refused_correct_audience_is_the_control(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    wrong_tok = jwt.encode(_claims(aud="not-accepted"), _PRIVATE_PEM, algorithm="RS256")
    c_wrong = ta.verify_bearer(wrong_tok)
    assert c_wrong.verified is False and c_wrong.reason.startswith("invalid")

    right_tok = jwt.encode(_claims(aud=AUDIENCE), _PRIVATE_PEM, algorithm="RS256")
    c_right = ta.verify_bearer(right_tok)
    assert c_right.verified is True


def test_empty_accepted_issuers_refuses_an_otherwise_correct_token(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    # MESH_JWT_ACCEPTED_ISSUERS left unset — _clean_env already delenv'd it.
    tok = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is False and c.reason == "no accepted issuers configured"


def test_empty_accepted_audiences_refuses_an_otherwise_correct_token(monkeypatch):
    jwt = pytest.importorskip("jwt")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    # MESH_JWT_ACCEPTED_AUDIENCES left unset.
    tok = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is False and c.reason == "no accepted audiences configured"


def test_jwks_url_resolves_the_signing_key(monkeypatch):
    """Proves the JWKS path is actually exercised, not silently falling through to
    "no-verification-key" because MESH_JWT_PUBLIC_KEY was never set."""
    jwt = pytest.importorskip("jwt")

    class _FakeSigningKey:
        def __init__(self, key):
            self.key = key

    class FakeClient:
        def __init__(self, url):
            self.url = url

        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey(_PUBLIC_PEM)

    monkeypatch.setattr(jwt, "PyJWKClient", FakeClient)
    monkeypatch.setenv("MESH_JWT_JWKS_URL", "https://issuer.example.com/jwks")
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    tok = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is True and c.authz_id == "svc:supervisor"


def test_jwks_url_takes_precedence_over_static_key_when_both_set(monkeypatch):
    jwt = pytest.importorskip("jwt")

    class _FakeSigningKey:
        def __init__(self, key):
            self.key = key

    class FakeClient:
        def __init__(self, url):
            self.url = url

        def get_signing_key_from_jwt(self, token):
            return _FakeSigningKey(_PUBLIC_PEM)  # the CORRECT key

    monkeypatch.setattr(jwt, "PyJWKClient", FakeClient)
    monkeypatch.setenv("MESH_JWT_JWKS_URL", "https://issuer.example.com/jwks")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _OTHER_PUBLIC_PEM)  # the WRONG key
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    tok = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is True, "JWKS must win; the wrong static key must never be used"


def test_jwks_client_is_reused_across_verifications_one_fetch_per_kid(monkeypatch):
    """Lane 1's review of d5ab283e: a fresh `jwt.PyJWKClient` per call has an empty cache every
    time, so every verification was an HTTP round-trip to the realm's certs endpoint — on the
    event loop. `_jwks_client_for` now keeps one client per URL so ITS OWN cache (and its
    refetch-once-on-an-unknown-`kid`, which PyJWKClient already implements) has something to
    work with. Seal: two verifications with the same `kid` cause one fetch. Control: a third
    verification with an unknown `kid` is the one case that cache is supposed to miss — a second
    fetch, not a rebuilt client."""
    jwt = pytest.importorskip("jwt")

    class _FakeSigningKey:
        def __init__(self, key):
            self.key = key

    class FakeClient:
        """Mirrors the one thing about the real `PyJWKClient` this test needs: it fetches the
        whole JWK set over the network and caches it by `kid`, so resolving an already-seen `kid`
        costs nothing further — only an unseen `kid` triggers another fetch. `fetch_count` stands
        in for the network call; `get_signing_key_from_jwt` stands in for the cache-aware resolve
        that PyJWT itself provides and that `_jwks_client_for` exists to let actually run."""

        instances = 0

        def __init__(self, url):
            self.url = url
            self.fetch_count = 0
            self._known_kids: set = set()
            FakeClient.instances += 1

        def get_signing_key_from_jwt(self, token):
            kid = jwt.get_unverified_header(token).get("kid")
            if kid not in self._known_kids:
                self.fetch_count += 1
                self._known_kids.add(kid)
            return _FakeSigningKey(_PUBLIC_PEM)

    monkeypatch.setattr(jwt, "PyJWKClient", FakeClient)
    url = "https://issuer.example.com/jwks"
    monkeypatch.setenv("MESH_JWT_JWKS_URL", url)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    tok_a1 = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256", headers={"kid": "kid-a"})
    tok_a2 = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256", headers={"kid": "kid-a"})
    tok_b = jwt.encode(_claims(), _PRIVATE_PEM, algorithm="RS256", headers={"kid": "kid-b"})

    assert ta.verify_bearer(tok_a1).verified is True
    assert ta.verify_bearer(tok_a2).verified is True
    assert FakeClient.instances == 1, "one PyJWKClient per URL, not rebuilt per call"
    client = ta._jwks_client_for(url)
    assert client.fetch_count == 1, "two verifications, same kid: one fetch"

    assert ta.verify_bearer(tok_b).verified is True
    assert FakeClient.instances == 1, "still the same client — an unknown kid is refetched, not rebuilt"
    assert client.fetch_count == 2, "control: a different kid, a second fetch"


def test_two_accepted_issuers_admits_a_token_whose_iss_is_the_second_entry(monkeypatch):
    """Sandbox serves TWO accepted issuers — the in-cluster realm URL and the public one, since
    Keycloak has no fixed hostname — per Lane 1's packet
    (sessions/2026-11-11-packet-to-ca-from-lane-01-v0-9-20-review-two-changes-then-ask-chris-to-
    merge-now.md). Every other test in this module configures a single issuer; this is the
    two-element shape that will actually run, and the reason the `pyjwt` floor had to move at
    all — below 2.9.0, `issuer=["a", "b"]` is compared to the whole list as one value, so every
    token is refused regardless of which of the two issuers minted it."""
    jwt = pytest.importorskip("jwt")
    second_issuer = "https://issuer-internal.example.svc.cluster.local/realm"
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", f"{ISSUER},{second_issuer}")
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)

    tok = jwt.encode(_claims(iss=second_issuer), _PRIVATE_PEM, algorithm="RS256")
    c = ta.verify_bearer(tok)
    assert c.verified is True and c.authz_id == "svc:supervisor"


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
    """Invalid because RS256 is configured+accepted but the token is HS256-signed."""
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
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
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    jwt = pytest.importorskip("jwt")
    bad = jwt.encode({"email": "svc:x"}, "wrong-key", algorithm="HS256")
    r = _client_with_dependency().get("/ping", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 403


def test_REQUIRE_admits_a_verified_caller(monkeypatch):
    monkeypatch.setenv("REQUIRE_TRANSPORT_AUTH", "true")
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _PUBLIC_PEM)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_ISSUERS", ISSUER)
    monkeypatch.setenv("MESH_JWT_ACCEPTED_AUDIENCES", AUDIENCE)
    jwt = pytest.importorskip("jwt")
    good = jwt.encode(_claims(email="svc:supervisor"), _PRIVATE_PEM, algorithm="RS256")
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

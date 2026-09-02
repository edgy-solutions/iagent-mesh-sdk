"""The caller reaches the handler, and reaching it is what a per-user read needs.

Finding A of `docs/HANDOFF-meshtool-execute.md`: `make_transport_auth_dependency` computed a
`CallerIdentity` and FastAPI discarded it (app-level dependency return values are not injectable
and never reach `request.state`), so a handler had nothing to pass to
`CortexDataClient(originator_email=...)` and its only working option read as the SERVICE.

The failure being prevented is SILENT — an agent reading as the service returns rows and raises
nothing — so these tests assert on the SUBJECT a read would authorize as, never merely on a 200.

Every test here fails against the pre-fix SDK. That is the point: they were written by breaking
the fixed code and confirming each goes red for its own reason, not as a set.
"""
import os

import pytest
from fastapi.testclient import TestClient

from iagent_mesh import CallerIdentity, current_caller
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

# HS256 with a known secret: a REAL signature check, so `verified=True` means the token was
# actually verified rather than decoded. A test that only ever exercises the unverified path
# cannot tell a working verifier from an absent one.
_SECRET = "test-signing-secret"


def _token(claims: dict) -> str:
    import jwt
    return jwt.encode(claims, _SECRET, algorithm="HS256")


class Q(ToolInput):
    asset: str


class A(ToolOutput):
    read_as: str


@pytest.fixture
def verifying_env(monkeypatch):
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _SECRET)
    monkeypatch.delenv("REQUIRE_TRANSPORT_AUTH", raising=False)
    monkeypatch.delenv("USER_ENTITLEMENT_CLAIM", raising=False)


def _tool(handler, name="identity-probe"):
    tool = MeshTool(
        name=name,
        description="probe",
        verb="mesh:probeIdentity",
        input_uri="mesh:Query",
        output_uri="mesh:Answer",
    )
    tool.execute()(handler)
    return TestClient(tool.app)


def test_handler_annotated_CallerIdentity_receives_the_verified_caller(verifying_env):
    """The target shape from the handoff: a parameter annotated `CallerIdentity` gets the user."""
    def handler(data: Q, caller: CallerIdentity) -> A:
        return A(read_as=caller.require_authz_id())

    client = _tool(handler)
    r = client.post("/execute", json={"asset": "x"},
                    headers={"Authorization": f"Bearer {_token({'email': 'analyst@corp.com'})}"})
    assert r.status_code == 200, r.text
    assert r.json()["read_as"] == "analyst@corp.com"


def test_two_users_are_two_subjects(verifying_env):
    """Acceptance: *two different users invoking the same agent get different rows.*

    Rows are downstream, so this asserts the thing that DECIDES them — the authz subject the
    handler would hand the data client. Pinned across two requests to ONE app instance, which is
    also what proves the contextvar is request-scoped and not leaking between callers.
    """
    seen = []

    def handler(data: Q, caller: CallerIdentity) -> A:
        seen.append(caller.require_authz_id())
        return A(read_as=caller.require_authz_id())

    client = _tool(handler)
    for who in ("alice@corp.com", "bob@corp.com"):
        r = client.post("/execute", json={"asset": "x"},
                        headers={"Authorization": f"Bearer {_token({'email': who})}"})
        assert r.status_code == 200, r.text
        assert r.json()["read_as"] == who
    assert seen == ["alice@corp.com", "bob@corp.com"]


def test_employee_id_deployment_keys_on_the_configured_claim(verifying_env, monkeypatch):
    """authz_id follows USER_ENTITLEMENT_CLAIM — the work-deploy shape.

    The sandbox keys on `email`; work-deploy keys on an employee id in another claim. Both the
    SDK here and the dag-tools gateway's token path resolve through this same env var, so a
    handler's `require_authz_id()` yields the employee id and
    `CortexDataClient(originator_email=<employee id>)` matches the employee-id-keyed Topaz
    relations. Nothing in this path parses the value's FORMAT — identity stays opaque.
    """
    monkeypatch.setenv("USER_ENTITLEMENT_CLAIM", "preferred_username")

    def handler(data: Q, caller: CallerIdentity) -> A:
        return A(read_as=caller.require_authz_id())

    client = _tool(handler, name="empid-probe")
    token = _token({"preferred_username": "E123456", "email": "ignored@corp.com"})
    r = client.post("/execute", json={"asset": "x"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    # The EMPLOYEE ID, not the email that also rides in the token.
    assert r.json()["read_as"] == "E123456"


def test_unresolved_caller_refuses_instead_of_reading_as_the_service(verifying_env):
    """The confused deputy, refused.

    Under OBSERVE an unauthenticated caller is admitted at the transport layer (by design), so
    `authz_id` is None and `CortexDataClient(originator_email=None)` would fall back to the
    service identity and succeed — every user reading with the service's entitlements. The read
    accessor raises instead; the handler's failure surfaces as a 500 rather than wrong rows.
    """
    def handler(data: Q, caller: CallerIdentity) -> A:
        return A(read_as=caller.require_authz_id())

    client = _tool(handler, name="refuse-probe")
    r = client.post("/execute", json={"asset": "x"})  # no Authorization header at all
    assert r.status_code == 500
    # And the reason is retrievable rather than guessed:
    ident = CallerIdentity(None, False, "absent")
    with pytest.raises(PermissionError, match="absent"):
        ident.require_authz_id()


def test_authz_id_stays_optional_for_logging():
    """`.authz_id` must remain readable-and-None; only the READ accessor is fail-closed.

    Collapsing the two would make the gauge line (`caller: none (absent)`) raise, which would
    turn OBSERVE's own instrument into an outage.
    """
    ident = CallerIdentity(None, False, "absent")
    assert ident.authz_id is None
    assert "none" in repr(ident)


def test_single_parameter_handlers_are_untouched(verifying_env):
    """The pre-existing form keeps working, unchanged and un-injected.

    The SDK's own `app.py` uses it, and so does every scaffolded template. A fix that obliged
    every existing handler to grow a parameter would be a migration, not a fix.
    """
    def handler(data: Q) -> A:
        return A(read_as="no-caller-requested")

    client = _tool(handler, name="legacy-probe")
    r = client.post("/execute", json={"asset": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["read_as"] == "no-caller-requested"


def test_caller_parameter_is_matched_by_annotation_not_by_name(verifying_env):
    """Any parameter name works, so long as the annotation is `CallerIdentity`."""
    def handler(data: Q, whoever_is_asking: CallerIdentity) -> A:
        return A(read_as=whoever_is_asking.require_authz_id())

    client = _tool(handler, name="named-probe")
    r = client.post("/execute", json={"asset": "x"},
                    headers={"Authorization": f"Bearer {_token({'email': 'z@corp.com'})}"})
    assert r.status_code == 200, r.text
    assert r.json()["read_as"] == "z@corp.com"


def test_contextvar_is_readable_without_threading_a_parameter(verifying_env):
    """`current_caller()` works from a helper the handler calls — the no-Request case.

    This is the path that exists because a `CortexDataClient` is usually built three frames below
    the handler, where passing a parameter down is the plumbing that does not get done.
    """
    def build_client_deep_below():
        return current_caller().require_authz_id()

    def handler(data: Q) -> A:
        return A(read_as=build_client_deep_below())

    client = _tool(handler, name="ctxvar-probe")
    r = client.post("/execute", json={"asset": "x"},
                    headers={"Authorization": f"Bearer {_token({'email': 'deep@corp.com'})}"})
    assert r.status_code == 200, r.text
    assert r.json()["read_as"] == "deep@corp.com"


def test_current_caller_is_None_outside_a_request():
    """No request in scope is DIFFERENT from a request by nobody.

    A notebook may legitimately fall back to a process identity; an agent request whose caller
    did not resolve must not. Collapsing the two is what lets an agent-pod read silently take the
    notebook path.
    """
    assert current_caller() is None


def test_ROOT_CAUSE_fastapi_discards_app_level_dependency_return_values():
    """SEAL 3, as an executable fact rather than a remembered one.

    The defect's root cause was not a missed line — it was a FastAPI property: an app-level
    `dependencies=[...]` entry is run for its SIDE EFFECTS and its return value is DROPPED. It is
    not injectable into a route, and it does not land on `request.state`. That is why
    `make_transport_auth_dependency` could compute a correct `CallerIdentity`, log it, and still
    leave every handler with nothing.

    Pinned here because the whole design rests on it. A future author "simplifying" the
    contextvar away — reasonably assuming the app-level dependency's return is reachable — would
    reintroduce the exact silent unscoping, and would do it in a diff that reads like cleanup.
    This test fails the moment that assumption is acted on.
    """
    from fastapi import Depends, FastAPI, Request
    from fastapi.testclient import TestClient

    def app_level_dep() -> str:
        return "computed-and-then-discarded"

    app = FastAPI(dependencies=[Depends(app_level_dep)])
    seen = {}

    @app.get("/probe")
    async def probe(request: Request):
        seen["on_state"] = getattr(request.state, "app_level_dep", "ABSENT")
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/probe").status_code == 200

    assert seen["on_state"] == "ABSENT", (
        "FastAPI now surfaces app-level dependency return values on request.state. If that is "
        "genuinely true of this version, the SDK could read the caller from there — but the "
        "change must be deliberate, and this seal is where it gets noticed."
    )

"""A tool module using `from __future__ import annotations` must still work.

FOUND WHILE WRITING THE PER-USER READ TEST, not by inspection. `execute()` read
`inspect.signature(func).parameters[0].annotation` RAW. Under PEP 563 — `from __future__ import
annotations`, this SDK's own house style in every module, and the long-planned Python default —
that attribute is the *string* `"MyInput"`, so `InputModel(**body)` evaluated to
`"MyInput"(**body)`:

    HTTP 422  {"detail": "'str' object is not callable"}

on EVERY request, with a message naming nothing the author wrote. The defect is invisible to a
tool's own unit tests (which call the function directly, never through `/execute`) and is
triggered by a single import line at the top of the file — one that linters and modern templates
actively encourage adding.

This module is compiled WITH the future import, so it reproduces the deployed condition rather
than describing it. `test_core.py` covers the non-future case; both must pass, because the two
forms take genuinely different code paths through `typing.get_type_hints`.
"""
from __future__ import annotations           # <- THE WHOLE POINT OF THIS FILE

import pytest
from fastapi.testclient import TestClient

from iagent_mesh import CallerIdentity
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

_SECRET = "test-signing-secret"


class Reading(ToolInput):
    sensor: str
    threshold: float = 0.9


class Verdict(ToolOutput):
    sensor: str
    caller: str


def _tool(handler, name="pep563-tool"):
    tool = MeshTool(name=name, description="probe", verb="mesh:probePep563",
                    input_uri="mesh:Query", output_uri="mesh:Answer")
    tool.execute()(handler)
    return TestClient(tool.app)


def test_string_annotations_resolve_to_the_request_body_model():
    """The plain case: a handler in a PEP-563 module parses its body correctly."""
    def handler(data: Reading) -> Verdict:
        return Verdict(sensor=data.sensor, caller="n/a")

    r = _tool(handler).post("/execute", json={"sensor": "pump-7", "threshold": 0.5})
    assert r.status_code == 200, r.text
    assert r.json()["sensor"] == "pump-7"


def test_validation_still_rejects_a_bad_body_for_the_RIGHT_reason():
    """422 must mean "your body is wrong", not "the SDK could not resolve a type".

    Before the fix every request produced a 422 whose detail was `'str' object is not callable` —
    the same status code for an unrelated cause, which is what made the defect read as a
    client-side schema problem and sent authors hunting through their own models.
    """
    def handler(data: Reading) -> Verdict:
        return Verdict(sensor=data.sensor, caller="n/a")

    r = _tool(handler, name="pep563-invalid").post("/execute", json={"threshold": "not-a-float"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "not callable" not in detail, f"the annotation bug is back: {detail}"
    assert "sensor" in detail, f"422 should name the offending field, got: {detail}"


def test_caller_injection_also_works_under_postponed_annotations(monkeypatch):
    """`CallerIdentity` is a string annotation here too, and must still be recognised."""
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _SECRET)
    monkeypatch.delenv("REQUIRE_TRANSPORT_AUTH", raising=False)
    monkeypatch.delenv("USER_ENTITLEMENT_CLAIM", raising=False)
    import jwt

    def handler(data: Reading, caller: CallerIdentity) -> Verdict:
        return Verdict(sensor=data.sensor, caller=caller.require_authz_id())

    token = jwt.encode({"email": "pep563@corp.com"}, _SECRET, algorithm="HS256")
    r = _tool(handler, name="pep563-caller").post(
        "/execute", json={"sensor": "pump-7"},
        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["caller"] == "pep563@corp.com"


def test_an_unresolvable_annotation_fails_at_DECORATION_not_per_request():
    """A model defined where it cannot be resolved must fail loudly, once, at import.

    The alternative — the old behaviour — is a tool that starts cleanly, registers itself into
    the mesh, and then 422s every request it is ever routed. Failing at decoration means the
    author sees it on the first run instead of the router seeing it in production.
    """
    class LocallyDefined(ToolInput):     # not importable from module scope
        x: int

    tool = MeshTool(name="unresolvable", description="probe", verb="mesh:probeBad",
                    input_uri="mesh:Query", output_uri="mesh:Answer")

    with pytest.raises(TypeError, match="could not resolve the type annotation"):
        @tool.execute()
        def handler(data: LocallyDefined) -> Verdict:
            return Verdict(sensor="x", caller="y")

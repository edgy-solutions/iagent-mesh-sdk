"""The SDK's OWN registration consumer is bound to the one transport — pinned, because it wasn't.

THE DEFECT THIS EXISTS FOR (0.3.0 -> 0.3.1). `registration_transport.register_with_mesh` was added
in 0.3.0 expressly to be THE one authenticated registration path — mint, ADR-0006 retry semantics,
named failure. Its commit message argued, correctly, that a second registration implementation is
exactly what the one-implementation rule forbids. The platform bound the new transport. **The
SDK's own consumer — `MeshTool._emit_to_registrar`, reached from the lifespan — was never
converted**, and stayed a bare `httpx.post` with no credential and no retry.

So every externally-scaffolded engine, the exact audience this package exists for, registered
UNMINTED and would stop the moment the mesh flips REQUIRE_TRANSPORT_AUTH. The package built to
prevent the defect shipped it.

THE MISS IS THE INSTRUCTIVE PART, and it is a general law, not a slip: *a consolidation is
complete when every consumer is bound, not when the shared implementation exists.* Building the
seam and wiring the callers to it are two pieces of work; the first is visible and argued for in a
commit message, the second is tedious and invisible, and it is the one that makes the first true.

These pins encode the law's test: **who were the consumers of the old path, and which line now
binds each of them to the new one?**
"""
from __future__ import annotations

import inspect
import re

import pytest

from iagent_mesh import core as core_mod
from iagent_mesh.core import MeshTool


def _emit_src() -> str:
    return inspect.getsource(MeshTool._emit_to_registrar)


def test_the_sdks_own_consumer_calls_the_one_transport():
    """THE REGRESSION PIN. A second registration implementation living beside the shared one is
    the whole defect; this asserts the consumer REACHES the seam rather than reimplementing it."""
    src = _emit_src()
    assert "register_with_mesh" in src, (
        "MeshTool._emit_to_registrar must register through registration_transport, not its own POST"
    )


def test_no_second_registration_implementation_survives_in_core():
    """ONE IMPLEMENTATION, PROVEN BY ABSENCE. The old body posted `/v1/register` directly; a stray
    one here would be the drift re-seeded, and it would be invisible for exactly as long as the
    first one was."""
    src = _emit_src()
    assert not re.search(r"\.post\(\s*f?\"[^\"]*/v1/register", src), (
        "a direct POST to /v1/register survives in core — that is the second implementation"
    )


def test_identity_is_an_argument_not_ambient_env():
    """`mint` is threaded from the CALLER. A helper that resolved an engine's credentials from
    ambient env on its behalf would be a general name over specific behaviour — the shape that
    made a supervisor dispatch as the review starter."""
    sig = inspect.signature(MeshTool.__init__)
    assert "mint" in sig.parameters, "MeshTool must accept the engine's mint as an argument"
    assert sig.parameters["mint"].default is None, (
        "mint must default to None — the SDK never invents an identity for the engine"
    )


def _tool(**overrides):
    defaults = dict(
        name="dummy",
        description="Dummy test tool",
        verb="mesh:dummyOp",
        input_uri="mesh:DummyInput",
        output_uri="mesh:DummyOutput",
    )
    defaults.update(overrides)
    return MeshTool(**defaults)


def test_the_mint_actually_REACHES_the_transport(monkeypatch):
    """THE WITNESS, NOT THE PRESENCE CHECK. The 2026-08-07 miss was a wiring commit that verified a
    mint HAPPENED and a token ATTACHED but never decoded WHOSE — so this asserts the caller's own
    mint object arrives at the transport, which is the thing that was silently absent."""
    seen = {}

    def _fake_register(registrar_url, manifest, *, component=None, mint=None, timeout=30.0):
        seen["url"] = registrar_url
        seen["mint"] = mint
        seen["component"] = component
        return type("R", (), {"registered": True, "reason": ""})()

    monkeypatch.setattr(
        "iagent_mesh.registration_transport.register_with_mesh", _fake_register
    )

    sentinel = lambda: "tok-from-the-engine"  # noqa: E731
    tool = _tool(mint=sentinel)
    tool._emit_to_registrar("http://registrar:8090", {"openapi": "spec"})

    assert seen["mint"] is sentinel, "the engine's own mint must reach the transport unchanged"
    assert seen["mint"]() == "tok-from-the-engine"
    assert seen["url"] == "http://registrar:8090"


def test_a_failed_registration_still_raises_for_the_lifespan(monkeypatch):
    """UNTOUCHED-BEHAVIOUR SEAL. `register_with_mesh` never raises — it returns a named reason. The
    lifespan's ADR-0006 contract ("a failed registration must NOT take the tool down") depends on
    _emit_to_registrar raising so the existing handler logs it. Losing that in the rebind would
    convert a logged warning into a silent success, which is worse than the defect being fixed."""
    def _fake_register(registrar_url, manifest, *, component=None, mint=None, timeout=30.0):
        return type("R", (), {"registered": False, "reason": "registrar rejected 422"})()

    monkeypatch.setattr(
        "iagent_mesh.registration_transport.register_with_mesh", _fake_register
    )

    with pytest.raises(RuntimeError, match="422"):
        _tool()._emit_to_registrar("http://registrar:8090", {"openapi": "spec"})

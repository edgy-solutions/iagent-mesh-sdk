"""Omitting the caller must be VISIBLE, never silent — the residue of the original defect.

`[[sdk-discards-caller-identity]]` was that `MeshTool` computed a `CallerIdentity` and threw it
away, so a handler COULD NOT scope work to its invoker. Making the identity reachable fixed that
half. The other half is that a handler which simply omits the parameter is back in the original
condition — unable to scope to the verified caller, with nothing saying so. Silence is what let
the discarded identity sit unnoticed in the first place, so silence is what this file removes.

THE CONTRACT
  * takes a `CallerIdentity` parameter      -> CALLER-SCOPED, announced at INFO
  * `@app.execute(caller_scoped=True)`      -> CALLER-SCOPED via `current_caller()`, INFO
  * `@app.execute(caller_scoped=False)`     -> NOT caller-scoped, DECLARED, INFO
  * neither                                 -> NOT caller-scoped, UNDECLARED, **WARNING**

The escape hatch is deliberate. A warning that cannot be switched off by stating intent becomes
noise, and noise is re-silencing by another route — so `caller_scoped=False` records that the
author considered it, and the fleet can still COUNT undeclared tools from the log.
"""
from __future__ import annotations

import logging

import pytest

from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.transport_auth import CallerIdentity


class In(ToolInput):
    value: int


class Out(ToolOutput):
    result: int


def _tool(name="posture-probe"):
    return MeshTool(name=name, description="d", verb="mesh:probe",
                    input_uri="mesh:In", output_uri="mesh:Out")


def _register(caplog, *, scoped_param: bool, declared=None):
    """Register a handler and return the records emitted while doing so."""
    tool = _tool()
    kwargs = {} if declared is None else {"caller_scoped": declared}
    with caplog.at_level(logging.INFO, logger="MeshTool"):
        caplog.clear()
        if scoped_param:
            @tool.execute(**kwargs)
            def handler(data: In, caller: CallerIdentity) -> Out:
                return Out(result=data.value)
        else:
            @tool.execute(**kwargs)
            def handler(data: In) -> Out:  # noqa: F811
                return Out(result=data.value)
    return caplog.records


def _texts(records):
    # `getMessage()` already applies the %-args; interpolating again raises TypeError.
    return "\n".join(r.getMessage() for r in records)


# ---------------------------------------------------------------------------
# The warning — the whole point of this file
# ---------------------------------------------------------------------------
def test_an_undeclared_unscoped_handler_WARNS_at_registration(caplog):
    records = _register(caplog, scoped_param=False, declared=None)
    warnings = [r for r in records if r.levelno >= logging.WARNING]
    assert warnings, (
        "a handler that cannot scope to the verified caller registered SILENTLY — this is the "
        "exact condition that let the discarded-identity defect sit unnoticed"
    )
    msg = _texts(warnings)
    assert "UNDECLARED" in msg
    # The warning must be ACTIONABLE: it names both remedies.
    assert "CallerIdentity" in msg and "caller_scoped=False" in msg


def test_declaring_the_intent_silences_the_warning(caplog):
    records = _register(caplog, scoped_param=False, declared=False)
    assert not [r for r in records if r.levelno >= logging.WARNING], (
        "declaring `caller_scoped=False` did not silence the warning — an unsilenceable "
        "warning becomes noise, and noise re-silences by another route"
    )
    assert "NOT caller-scoped, DECLARED" in _texts(records)


def test_a_caller_scoped_handler_does_not_warn_and_says_how(caplog):
    records = _register(caplog, scoped_param=True, declared=None)
    assert not [r for r in records if r.levelno >= logging.WARNING]
    msg = _texts(records)
    assert "CALLER-SCOPED" in msg
    # Naming the parameter is what makes the line auditable against the source.
    assert "caller" in msg


def test_contextvar_users_can_declare_scoped_without_a_parameter(caplog):
    """`current_caller()` is a legitimate way to scope, and must not be forced to warn."""
    records = _register(caplog, scoped_param=False, declared=True)
    assert not [r for r in records if r.levelno >= logging.WARNING]
    assert "CALLER-SCOPED" in _texts(records)


# ---------------------------------------------------------------------------
# The declaration must not change behaviour
# ---------------------------------------------------------------------------
def test_declaring_the_posture_does_not_alter_execution():
    """`caller_scoped` is a DECLARATION, not an enforcement switch.

    If it silently changed what the handler received, the log line would stop describing the
    code — the failure mode this whole change exists to prevent.
    """
    from fastapi.testclient import TestClient

    tool = _tool("decl-noop")

    @tool.execute(caller_scoped=False)
    def handler(data: In) -> Out:
        return Out(result=data.value * 3)

    with TestClient(tool.app) as c:
        assert c.post("/execute", json={"value": 5}).json()["result"] == 15


def test_a_declared_false_handler_that_still_asks_for_the_caller_gets_it():
    """Contradictory input must resolve toward MORE identity, never less.

    `caller_scoped=False` alongside a `CallerIdentity` parameter is an author mistake. The
    parameter is the operative fact — silently withholding the identity because a flag said
    "not scoped" would be the original defect re-created by a typo.
    """
    from fastapi.testclient import TestClient

    tool = _tool("decl-contradiction")
    seen = {}

    @tool.execute(caller_scoped=False)
    def handler(data: In, caller: CallerIdentity) -> Out:
        seen["caller"] = caller
        return Out(result=data.value)

    with TestClient(tool.app) as c:
        c.post("/execute", json={"value": 1})
    assert isinstance(seen.get("caller"), CallerIdentity)


# ---------------------------------------------------------------------------
# Positive control
# ---------------------------------------------------------------------------
def test_the_warning_check_can_actually_fail(caplog):
    """A caplog assertion that never sees a WARNING would pass for the wrong reason.

    Proves the harness observes this logger at this level, so
    `test_declaring_the_intent_silences_the_warning` is measuring silence rather than deafness.
    """
    with caplog.at_level(logging.INFO, logger="MeshTool"):
        caplog.clear()
        logging.getLogger("MeshTool").warning("probe: the gauge is live")
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


@pytest.mark.parametrize("template", [
    "01_pure_math", "02_instructor_polars", "03_baml_pandas",
    "legacy_adapter", "smolagents_subswarm",
])
def test_every_shipped_template_declares_its_posture(template):
    """The authoring examples must not model the silent state.

    A template that registers undeclared teaches the omission by example and emits the warning
    on every scaffolded tool's startup — training authors to ignore it.
    """
    from iagent_mesh.scaffold_core import template_root

    src = (template_root() / template / "app.py").read_text(encoding="utf-8")
    declares = "@app.execute(caller_scoped=" in src
    takes_caller = "CallerIdentity" in src and "@app.execute()" in src
    assert declares or takes_caller, (
        f"template {template} registers a handler without declaring a scoping posture"
    )

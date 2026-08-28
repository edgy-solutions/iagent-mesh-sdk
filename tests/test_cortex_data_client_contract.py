"""CROSS-REPO CONTRACT: what a MeshTool handler hands `dag_tools`' `CortexDataClient`.

The per-user read is a THREE-REPO path and every hop keys on the same opaque subject:

    iagent-mesh-sdk   caller.require_authz_id()          <- USER_ENTITLEMENT_CLAIM off the JWT
    dag-tools         CortexDataClient(originator_email=) -> header X-Originator-Email
    dag-tools gateway subject_gauge.entitlement_claim()   -> Topaz can_read subject

If the SDK hands the wrong thing, or `CortexDataClient` renames the parameter, the failure is
NOT an exception — the gateway falls back to the token's own subject and the read succeeds as
the SERVICE. So this is pinned by INSPECTING THE REAL dag-tools SOURCE rather than by mocking a
client whose signature this repo would then be free to imagine.

Parsed with `ast`, not imported: `dag_tools.cortex_data.client` pulls in polars (and, per
source_type, pyiceberg / clickhouse-connect), which this SDK neither depends on nor should. A
syntax-level read gets the true signature without the dependency.

If dag-tools is not checked out beside this repo the module SKIPS — and a skip is not a pass, so
it says which path it could not verify.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Sibling checkout: ../dag-tools/dag_tools/cortex_data/client.py
_CLIENT = (Path(__file__).resolve().parents[2]
           / "dag-tools" / "dag_tools" / "cortex_data" / "client.py")

pytestmark = pytest.mark.skipif(
    not _CLIENT.exists(),
    reason=f"dag-tools not checked out at {_CLIENT} — the per-user read contract is UNVERIFIED",
)


def _init_kwargs() -> list:
    tree = ast.parse(_CLIENT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CortexDataClient":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    a = item.args
                    return [p.arg for p in (a.posonlyargs + a.args + a.kwonlyargs)
                            if p.arg != "self"]
    raise AssertionError("CortexDataClient.__init__ not found in dag-tools source")


def test_the_parameter_the_sdk_targets_still_EXISTS():
    """`originator_email` is the seam. A rename here silently re-aims the read at the service."""
    assert "originator_email" in _init_kwargs(), (
        "CortexDataClient no longer accepts `originator_email` — the SDK's documented bridge "
        "(originator_email=caller.require_authz_id()) is broken, and the failure mode is a "
        "SILENT service-identity read, not an error"
    )


def test_the_client_still_takes_no_caller_object():
    """Records that the SDK must pass a STRING subject, not a `CallerIdentity`.

    The handoff sketched `CortexDataClient(caller=caller)` as a nicer target. It does not exist
    yet, so the SDK bridges with the string the current client accepts. When dag-tools grows a
    `caller=`/`authz_id=` parameter this test goes red — which is the signal to simplify the
    documented bridge, not a defect.
    """
    kwargs = _init_kwargs()
    assert "caller" not in kwargs and "authz_id" not in kwargs, (
        f"CortexDataClient grew a caller-shaped parameter ({kwargs}) — revisit the bridge "
        "documented in docs/jupyter_guide.md and MeshTool.execute's docstring"
    )


def test_the_value_is_carried_OPAQUE_so_employee_id_works():
    """The subject is never parsed as an email — work-deploy keys on an employee id.

    `originator_email` is a NAME, not a format constraint: the client puts it verbatim in
    `X-Originator-Email` and the gateway uses it verbatim as the Topaz subject. Anything in this
    chain that validated it as an email would break every non-sandbox deployment, so the absence
    of such validation is the property worth pinning.
    """
    src = _CLIENT.read_text(encoding="utf-8")
    header_line = [ln for ln in src.splitlines() if "X-Originator-Email" in ln]
    assert header_line, "X-Originator-Email header no longer sent"
    # Assigned straight from the attribute — no parsing, splitting, or validation in between.
    assert any("self.originator_email" in ln for ln in header_line), (
        "the originator value is no longer passed through verbatim — if it is being parsed or "
        "reformatted, employee-id deployments (which carry no '@') will break"
    )


def test_sdk_side_subject_follows_the_same_configurable_claim():
    """Both ends resolve the subject through USER_ENTITLEMENT_CLAIM.

    The SDK reads it off the JWT; the dag-tools gateway reads it off the token on its own
    fallback path (dag-tools 73bbc6a, which fixed a hardcoded `email` lookup that would have
    fail-closed denied every read on a `preferred_username` deployment). A divergence here is
    the same defect in mirror image, so the SDK's use of the env var is pinned.
    """
    from iagent_mesh import transport_auth as ta

    import os
    old = os.environ.get("USER_ENTITLEMENT_CLAIM")
    try:
        os.environ["USER_ENTITLEMENT_CLAIM"] = "preferred_username"
        assert ta._entitlement_claim() == "preferred_username"
        del os.environ["USER_ENTITLEMENT_CLAIM"]
        assert ta._entitlement_claim() == "email", "default must remain email (sandbox)"
    finally:
        if old is not None:
            os.environ["USER_ENTITLEMENT_CLAIM"] = old
        else:
            os.environ.pop("USER_ENTITLEMENT_CLAIM", None)

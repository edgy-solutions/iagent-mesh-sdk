"""Tests for ``iagent_mesh.core.MeshTool``.

Covers:
- Required-field validation at construction time
- Namespace-authority derivation from the verb prefix (per ADR-0005)
- URN scheme
- Topaz auth, sync + async execute paths, internal error handling
- Lifespan: opt-in DataHub registration via ``MESH_REGISTER_ON_STARTUP``
- Lifespan: registration payload contents (the predicate-graph custom
  properties doc-tools will consume)
- Lifespan: registration failure does not crash the tool (ADR-0006)
"""

import json
import sys

import pytest
from fastapi.testclient import TestClient

from iagent_mesh.core import MeshTool, VALID_COST_CLASSES
from iagent_mesh.models import ToolInput, ToolOutput


class DummyInput(ToolInput):
    value: int


class DummyOutput(ToolOutput):
    result: int


# ---------------------------------------------------------------------------
# Helper: a fully-specified MeshTool used by most tests
# ---------------------------------------------------------------------------
def _make_tool(**overrides):
    """Build a MeshTool with sensible defaults, allowing per-test overrides."""
    defaults = dict(
        name="dummy",
        description="Dummy test tool",
        verb="mesh:dummyOp",
        input_uri="mesh:DummyInput",
        output_uri="mesh:DummyOutput",
    )
    defaults.update(overrides)
    return MeshTool(**defaults)


@pytest.fixture
def mesh_tool():
    tool = _make_tool()

    @tool.execute()
    def dummy_func(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value * 2)

    return tool


@pytest.fixture
def client(mesh_tool):
    return TestClient(mesh_tool.app)


# ---------------------------------------------------------------------------
# Construction + validation
# ---------------------------------------------------------------------------
def test_minimum_required_fields():
    """name, description, verb, input_uri, output_uri are all required."""
    tool = _make_tool()
    assert tool.name == "dummy"
    assert tool.verb == "mesh:dummyOp"
    assert tool.input_uri == "mesh:DummyInput"
    assert tool.output_uri == "mesh:DummyOutput"


def test_missing_verb_raises():
    with pytest.raises(TypeError):
        MeshTool(name="x", description="x", input_uri="mesh:A", output_uri="mesh:B")


def test_missing_input_uri_raises():
    with pytest.raises(TypeError):
        MeshTool(name="x", description="x", verb="mesh:doIt", output_uri="mesh:B")


def test_missing_output_uri_raises():
    with pytest.raises(TypeError):
        MeshTool(name="x", description="x", verb="mesh:doIt", input_uri="mesh:A")


def test_unnamespaced_verb_rejected():
    with pytest.raises(ValueError, match="namespaced URI"):
        _make_tool(verb="dummyOp")


def test_unnamespaced_input_uri_rejected():
    with pytest.raises(ValueError, match="namespaced URI"):
        _make_tool(input_uri="DummyInput")


def test_unnamespaced_output_uri_rejected():
    with pytest.raises(ValueError, match="namespaced URI"):
        _make_tool(output_uri="DummyOutput")


def test_invalid_cost_class_rejected():
    with pytest.raises(ValueError, match="cost_class must be one of"):
        _make_tool(cost_class="lightning")


@pytest.mark.parametrize("good", sorted(VALID_COST_CLASSES))
def test_valid_cost_classes_accepted(good):
    tool = _make_tool(cost_class=good)
    assert tool.cost_class == good


def test_empty_name_rejected():
    with pytest.raises(ValueError, match="name must be a non-empty string"):
        _make_tool(name="")


# ---------------------------------------------------------------------------
# Namespace authority (ADR-0005)
# ---------------------------------------------------------------------------
def test_namespace_authority_platform_for_mesh_prefix():
    tool = _make_tool(verb="mesh:foo")
    assert tool.namespace_authority == "platform"


def test_namespace_authority_domain_for_non_mesh_prefix():
    tool = _make_tool(verb="mro:applyDiagnostics", input_uri="mro:Symptom", output_uri="mro:FaultReport")
    assert tool.namespace_authority == "domain"


def test_namespace_authority_domain_for_unknown_prefix():
    """Unknown prefixes default to domain — ADR-0005's reasoning is that
    only ``mesh:`` is platform-reserved; everything else is a domain
    namespace whose ontology owner governs additions."""
    tool = _make_tool(verb="future-domain:doStuff")
    assert tool.namespace_authority == "domain"


# ---------------------------------------------------------------------------
# URN scheme (uses standard DataHub mlModel primitive)
# ---------------------------------------------------------------------------
def test_urn_scheme():
    tool = _make_tool(name="rotor_wear")
    assert tool.urn == "urn:li:mlModel:(urn:li:dataPlatform:mesh,rotor_wear,PROD)"
    assert tool.app.title == tool.urn


# ---------------------------------------------------------------------------
# Optional metadata defaults
# ---------------------------------------------------------------------------
def test_optional_metadata_defaults():
    tool = _make_tool()
    assert tool.verb_synonyms == []
    assert tool.owner_persona is None
    assert tool.cost_class == "fast"
    assert tool.requires_human_approval is False
    assert tool.version == "0.1.0"


def test_optional_metadata_set():
    tool = _make_tool(
        verb_synonyms=["foo", "bar"],
        owner_persona="MECHANIC",
        cost_class="slow",
        requires_human_approval=True,
        version="1.2.3",
    )
    assert tool.verb_synonyms == ["foo", "bar"]
    assert tool.owner_persona == "MECHANIC"
    assert tool.cost_class == "slow"
    assert tool.requires_human_approval is True
    assert tool.version == "1.2.3"


# ---------------------------------------------------------------------------
# Execute decorator: auth + validation + sync/async + error paths
# ---------------------------------------------------------------------------
def test_topaz_zero_trust_failure(client, monkeypatch):
    monkeypatch.delenv("LOCAL_DEV", raising=False)
    response = client.post("/execute", json={"value": 5})
    assert response.status_code == 403
    assert response.json()["detail"] == "Missing Topaz Ticket"


def test_local_dev_bypasses_auth(client, monkeypatch):
    monkeypatch.setenv("LOCAL_DEV", "true")
    response = client.post("/execute", json={"value": 7})
    assert response.status_code == 200
    assert response.json()["result"] == 14


def test_topaz_zero_trust_success(client):
    response = client.post(
        "/execute", json={"value": 5}, headers={"Authorization": "Bearer dummy_token"}
    )
    assert response.status_code == 200
    assert response.json()["result"] == 10


def test_input_validation(client):
    response = client.post(
        "/execute",
        json={"wrong_field": 5},
        headers={"Authorization": "Bearer dummy_token"},
    )
    assert response.status_code == 422


def test_async_execute_path():
    tool = _make_tool(name="async_tool")

    @tool.execute()
    async def doubler(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value * 3)

    c = TestClient(tool.app)
    response = c.post(
        "/execute", json={"value": 4}, headers={"Authorization": "Bearer x"}
    )
    assert response.status_code == 200
    assert response.json()["result"] == 12


def test_tool_internal_error_returns_500():
    tool = _make_tool(name="boom")

    @tool.execute()
    def explode(data: DummyInput) -> DummyOutput:
        raise RuntimeError("kaboom")

    c = TestClient(tool.app)
    response = c.post(
        "/execute", json={"value": 1}, headers={"Authorization": "Bearer x"}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Tool Error"


# ---------------------------------------------------------------------------
# Lifespan: opt-in DataHub registration
# ---------------------------------------------------------------------------
def test_lifespan_skips_registration_by_default(monkeypatch, caplog):
    """Without ``MESH_REGISTER_ON_STARTUP=true``, the lifespan logs that it's
    skipping and never touches acryl-datahub. We assert via the log message
    and verify the tool boots + serves requests."""
    monkeypatch.delenv("MESH_REGISTER_ON_STARTUP", raising=False)

    tool = _make_tool()

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    with caplog.at_level("INFO", logger="MeshTool"):
        with TestClient(tool.app) as c:
            r = c.post(
                "/execute", json={"value": 1}, headers={"Authorization": "Bearer x"}
            )
            assert r.status_code == 200

    assert any(
        "Skipping DataHub registration" in r.getMessage() for r in caplog.records
    ), f"expected 'Skipping DataHub registration' log; got: {[r.getMessage() for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Lifespan: fake acryl-datahub modules so we can verify the emission shape
# without depending on the real package being installed.
# ---------------------------------------------------------------------------
class _FakeEmittedMcp:
    """Capture-only stand-in for acryl-datahub's MetadataChangeProposalWrapper."""
    def __init__(self, entityUrn=None, aspect=None, **kwargs):
        self.entityUrn = entityUrn
        self.aspect = aspect


class _FakeMlModelProps:
    """Capture-only stand-in for MLModelPropertiesClass."""
    def __init__(self, description=None, customProperties=None, **kwargs):
        self.description = description
        self.customProperties = customProperties or {}


class _FakeEmitter:
    instances = []

    def __init__(self, gms_server=None, token=None, **kwargs):
        self.gms_server = gms_server
        self.token = token
        self.emitted = []
        _FakeEmitter.instances.append(self)

    def emit(self, mcp):
        self.emitted.append(mcp)


@pytest.fixture
def fake_datahub(monkeypatch):
    """Inject fake ``datahub.*`` modules so the lifespan can import them."""
    _FakeEmitter.instances = []

    import types

    mcp_mod = types.ModuleType("datahub.emitter.mcp")
    mcp_mod.MetadataChangeProposalWrapper = _FakeEmittedMcp

    rest_mod = types.ModuleType("datahub.emitter.rest_emitter")
    rest_mod.DatahubRestEmitter = _FakeEmitter

    schema_mod = types.ModuleType("datahub.metadata.schema_classes")
    schema_mod.MLModelPropertiesClass = _FakeMlModelProps

    parent = types.ModuleType("datahub")
    parent_emitter = types.ModuleType("datahub.emitter")
    parent_metadata = types.ModuleType("datahub.metadata")

    monkeypatch.setitem(sys.modules, "datahub", parent)
    monkeypatch.setitem(sys.modules, "datahub.emitter", parent_emitter)
    monkeypatch.setitem(sys.modules, "datahub.metadata", parent_metadata)
    monkeypatch.setitem(sys.modules, "datahub.emitter.mcp", mcp_mod)
    monkeypatch.setitem(sys.modules, "datahub.emitter.rest_emitter", rest_mod)
    monkeypatch.setitem(sys.modules, "datahub.metadata.schema_classes", schema_mod)

    yield


def test_lifespan_emits_to_datahub_when_enabled(fake_datahub, monkeypatch):
    """When ``MESH_REGISTER_ON_STARTUP=true``, the lifespan emits a single
    MCP containing the predicate-graph custom properties."""
    monkeypatch.setenv("MESH_REGISTER_ON_STARTUP", "true")
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://fake-gms:8080")
    monkeypatch.setenv("DATAHUB_TOKEN", "fake-token")
    monkeypatch.setenv("MESH_TOOL_ENDPOINT", "http://my-tool.svc:8000/execute")

    # Settings is read at module import; rebuild it AND rebind in core's
    # namespace so the lifespan sees the new values.
    from iagent_mesh import config as _config
    from iagent_mesh import core as _core
    new_settings = _config.Settings()
    monkeypatch.setattr(_config, "settings", new_settings)
    monkeypatch.setattr(_core, "settings", new_settings)

    tool = _make_tool(
        name="reg_tool",
        verb="mro:applyDiagnostics",
        input_uri="mro:Symptom",
        output_uri="mro:FaultReport",
        verb_synonyms=["diagnose", "troubleshoot"],
        owner_persona="MECHANIC",
        cost_class="medium",
        requires_human_approval=True,
    )

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    with TestClient(tool.app):
        pass

    assert _FakeEmitter.instances, "expected an emitter to be constructed"
    emitter = _FakeEmitter.instances[0]
    assert emitter.gms_server == "http://fake-gms:8080"
    assert emitter.token == "fake-token"
    assert len(emitter.emitted) == 1

    mcp = emitter.emitted[0]
    assert mcp.entityUrn == "urn:li:mlModel:(urn:li:dataPlatform:mesh,reg_tool,PROD)"

    props = mcp.aspect.customProperties
    assert props["mesh_is_registration"] == "true"
    assert props["mesh_tool_kind"] == "AITool"
    assert props["mesh_verb_iri"] == "mro:applyDiagnostics"
    assert props["mesh_input_uri"] == "mro:Symptom"
    assert props["mesh_output_uri"] == "mro:FaultReport"
    assert json.loads(props["mesh_verb_synonyms"]) == ["diagnose", "troubleshoot"]
    assert props["mesh_owner_persona"] == "MECHANIC"
    assert props["mesh_cost_class"] == "medium"
    assert props["mesh_requires_human_approval"] == "true"
    assert props["mesh_namespace_authority"] == "domain"  # mro: is a domain
    assert props["mesh_endpoint_url"] == "http://my-tool.svc:8000/execute"
    assert json.loads(props["mesh_openapi_schema"])["info"]["title"].startswith("urn:li:mlModel")
    assert props["mesh_sdk_version"] == "0.1.0"
    assert props["mesh_tool_version"] == "0.1.0"


def test_lifespan_swallows_registration_errors(fake_datahub, monkeypatch):
    """If the emitter raises, the tool still starts and serves requests
    (ADR-0006: DataHub is the inbox; runtime serving is independent)."""
    monkeypatch.setenv("MESH_REGISTER_ON_STARTUP", "true")
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://fake-gms:8080")

    from iagent_mesh import config as _config
    monkeypatch.setattr(_config, "settings", _config.Settings())

    class _ExplodingEmitter(_FakeEmitter):
        def emit(self, mcp):
            raise RuntimeError("DataHub unreachable")

    monkeypatch.setattr(
        sys.modules["datahub.emitter.rest_emitter"],
        "DatahubRestEmitter",
        _ExplodingEmitter,
    )

    tool = _make_tool(name="degraded")

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    # If the lifespan propagated the error, TestClient startup would raise.
    with TestClient(tool.app) as c:
        r = c.post("/execute", json={"value": 1}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 200


def test_lifespan_missing_gms_url_logs_and_continues(fake_datahub, monkeypatch, caplog):
    """``MESH_REGISTER_ON_STARTUP=true`` without ``DATAHUB_GMS_URL`` set
    must not crash; it logs a warning and keeps the tool serving."""
    monkeypatch.setenv("MESH_REGISTER_ON_STARTUP", "true")
    monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)

    from iagent_mesh import config as _config
    from iagent_mesh import core as _core
    new_settings = _config.Settings(DATAHUB_GMS_URL=None)
    monkeypatch.setattr(_config, "settings", new_settings)
    monkeypatch.setattr(_core, "settings", new_settings)

    tool = _make_tool(name="no_gms")

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    with TestClient(tool.app):
        pass

    # The warning message must mention the env var to make the failure
    # actionable from a single grep.
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("DATAHUB_GMS_URL" in r.getMessage() for r in warnings), (
        f"expected a WARNING mentioning DATAHUB_GMS_URL; got: "
        f"{[r.getMessage() for r in warnings]}"
    )

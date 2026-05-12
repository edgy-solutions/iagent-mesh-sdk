import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

class DummyInput(ToolInput):
    value: int

class DummyOutput(ToolOutput):
    result: int

@pytest.fixture
def mesh_tool():
    tool = MeshTool(name="dummy", description="Dummy test tool")

    @tool.execute()
    def dummy_func(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value * 2)

    return tool

@pytest.fixture
def client(mesh_tool):
    return TestClient(mesh_tool.app)

def test_tool_initialization(mesh_tool):
    assert mesh_tool.urn == "urn:li:aitool:dummy"
    assert mesh_tool.description == "Dummy test tool"
    assert mesh_tool.app.title == "urn:li:aitool:dummy"
    assert mesh_tool.ontology_uris == ["provisional:dummy"]
    assert mesh_tool.is_mcp is False

def test_mcp_tool_urn():
    tool = MeshTool(name="mcp_thing", description="An MCP server", is_mcp=True)
    assert tool.urn == "urn:li:mcpServer:mcp_thing"
    assert tool.is_mcp is True

def test_explicit_ontology_uris():
    tool = MeshTool(
        name="anomaly",
        description="x",
        ontology_uris=["mro:RotorAssembly", "mro:MaintenanceMetric"],
    )
    assert tool.ontology_uris == ["mro:RotorAssembly", "mro:MaintenanceMetric"]

def test_topaz_zero_trust_failure(client, monkeypatch):
    # Ensure LOCAL_DEV is not set
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
    response = client.post("/execute", json={"value": 5}, headers={"Authorization": "Bearer dummy_token"})
    assert response.status_code == 200
    assert response.json()["result"] == 10

def test_input_validation(client):
    # Missing required 'value' field
    response = client.post("/execute", json={"wrong_field": 5}, headers={"Authorization": "Bearer dummy_token"})
    assert response.status_code == 422


def test_async_execute_path():
    tool = MeshTool(name="async_tool", description="Async test tool")

    @tool.execute()
    async def doubler(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value * 3)

    c = TestClient(tool.app)
    response = c.post("/execute", json={"value": 4}, headers={"Authorization": "Bearer x"})
    assert response.status_code == 200
    assert response.json()["result"] == 12


def test_tool_internal_error_returns_500():
    tool = MeshTool(name="boom", description="Tool that explodes")

    @tool.execute()
    def explode(data: DummyInput) -> DummyOutput:
        raise RuntimeError("kaboom")

    c = TestClient(tool.app)
    response = c.post("/execute", json={"value": 1}, headers={"Authorization": "Bearer x"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Tool Error"


class _AsyncResp:
    """Minimal stand-in for an httpx.Response used in async lifespan path."""
    def __init__(self, status_code=200):
        self.status_code = status_code
    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    posts = []

    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def post(self, url, json=None, **kwargs):
        _FakeAsyncClient.posts.append({"url": url, "payload": json})
        return _AsyncResp(200)


def test_lifespan_registers_to_datahub(monkeypatch):
    _FakeAsyncClient.posts = []
    monkeypatch.setattr("iagent_mesh.core.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("MESH_TOOL_ENDPOINT", "http://my-tool.svc:8000/execute")

    tool = MeshTool(name="reg_tool", description="Reg test")

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    # Triggering the lifespan startup hook by entering the TestClient context
    with TestClient(tool.app) as c:
        # Sanity check the route still works after startup
        r = c.post("/execute", json={"value": 11}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 200

    # Lifespan should have made a registration POST
    assert _FakeAsyncClient.posts, "Expected at least one registration POST"
    call = _FakeAsyncClient.posts[0]
    assert call["url"].endswith("/entities")
    payload = call["payload"]
    assert payload["urn"] == "urn:li:aitool:reg_tool"
    assert payload["type"] == "AITool"
    assert payload["endpoint_url"] == "http://my-tool.svc:8000/execute"
    assert payload["ontology_uris"] == ["provisional:reg_tool"]
    assert "openapi_schema" in payload


def test_lifespan_mcp_entity_type(monkeypatch):
    _FakeAsyncClient.posts = []
    monkeypatch.setattr("iagent_mesh.core.httpx.AsyncClient", _FakeAsyncClient)

    tool = MeshTool(name="mcp_reg", description="MCP reg test", is_mcp=True)

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    with TestClient(tool.app):
        pass

    assert _FakeAsyncClient.posts
    payload = _FakeAsyncClient.posts[0]["payload"]
    assert payload["urn"] == "urn:li:mcpServer:mcp_reg"
    assert payload["type"] == "MCPServer"


def test_lifespan_swallows_registration_errors(monkeypatch):
    """If DataHub is unreachable, startup should NOT crash the tool."""
    import httpx

    class _ErrorClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def post(self, *args, **kwargs):
            raise httpx.RequestError("DataHub unreachable")

    monkeypatch.setattr("iagent_mesh.core.httpx.AsyncClient", _ErrorClient)

    tool = MeshTool(name="degraded", description="Resilience test")

    @tool.execute()
    def f(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value)

    # If registration error were not swallowed, TestClient startup would propagate it
    with TestClient(tool.app) as c:
        r = c.post("/execute", json={"value": 1}, headers={"Authorization": "Bearer x"})
        assert r.status_code == 200

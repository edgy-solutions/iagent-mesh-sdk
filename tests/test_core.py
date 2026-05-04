import os
import pytest
from fastapi.testclient import TestClient
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

class DummyInput(ToolInput):
    value: int

class DummyOutput(ToolOutput):
    result: int

@pytest.fixture
def mesh_tool():
    tool = MeshTool(urn="urn:test:dummy", description="Dummy test tool")
    
    @tool.execute()
    def dummy_func(data: DummyInput) -> DummyOutput:
        return DummyOutput(result=data.value * 2)
        
    return tool

@pytest.fixture
def client(mesh_tool):
    return TestClient(mesh_tool.app)

def test_tool_initialization(mesh_tool):
    assert mesh_tool.urn == "urn:test:dummy"
    assert mesh_tool.description == "Dummy test tool"
    assert mesh_tool.app.title == "urn:test:dummy"

def test_topaz_zero_trust_failure(client, monkeypatch):
    # Ensure LOCAL_DEV is not set
    monkeypatch.delenv("LOCAL_DEV", raising=False)
    
    response = client.post("/execute", json={"value": 5})
    assert response.status_code == 403
    assert response.json()["detail"] == "Missing Topaz Ticket"

def test_topaz_zero_trust_success(client):
    response = client.post("/execute", json={"value": 5}, headers={"Authorization": "Bearer dummy_token"})
    assert response.status_code == 200
    assert response.json()["result"] == 10

def test_input_validation(client):
    # Missing required 'value' field
    response = client.post("/execute", json={"wrong_field": 5}, headers={"Authorization": "Bearer dummy_token"})
    assert response.status_code == 422

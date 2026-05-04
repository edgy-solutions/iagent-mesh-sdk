import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app import app

client = TestClient(app)

def test_scaffold_generator():
    payload = {
        "template_id": "01_pure_math",
        "tool_name": "test-tool",
        "tool_urn": "urn:test:tool"
    }
    
    response = client.post("/scaffold/execute", json=payload, headers={"Authorization": "mock_token"})
    
    assert response.status_code == 200
    data = response.json()
    assert "workspace_uuid" in data
    assert "target_path" in data
    
    # Verify files were created
    target_path = data["target_path"]
    assert os.path.exists(target_path)
    assert os.path.exists(os.path.join(target_path, "app.py"))

@patch("subprocess.run")
@patch("os.getenv")
def test_mesh_publisher(mock_getenv, mock_subprocess_run, tmp_path):
    # Setup mock env and files
    mock_getenv.return_value = "dummy_token"
    mock_subprocess_run.return_value.returncode = 0
    
    workspace_uuid = "test-uuid"
    target_path = f"/tmp/{workspace_uuid}"
    
    # Mocking the creation of the target directory that scaffold_generator would make
    os.makedirs(target_path, exist_ok=True)
    
    payload = {
        "workspace_uuid": workspace_uuid,
        "tool_name": "test-tool",
        "tool_urn": "urn:test:tool",
        "target_git_group": "test-group"
    }
    
    response = client.post("/publish/execute", json=payload, headers={"Authorization": "mock_token"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Success"
    assert data["git_url"] == "https://oauth2:dummy_token@git.sustainment.internal/test-group/test-tool.git"
    
    # Verify subprocess.run was called multiple times (init, add, commit, remote add)
    assert mock_subprocess_run.call_count >= 4
    
    calls = mock_subprocess_run.call_args_list
    init_call = calls[0]
    assert "init" in init_call[0][0]
    
    add_call = calls[1]
    assert "add" in add_call[0][0]
    
    commit_call = calls[2]
    assert "commit" in commit_call[0][0]
    
    remote_call = calls[3]
    assert "remote" in remote_call[0][0]

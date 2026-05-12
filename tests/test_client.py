import os
import httpx
import pytest
from unittest.mock import patch, MagicMock

from iagent_mesh.client import MeshClient


def test_meshclient_requires_token(monkeypatch):
    monkeypatch.delenv("MESH_DEV_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="MESH_DEV_TOKEN not found"):
        MeshClient()


def test_meshclient_uses_default_gateway_url():
    client = MeshClient()
    assert client.gateway_url == "http://cortex-bff.local.svc:8000/orchestrate"
    assert client.token == "mock_token"


def test_meshclient_accepts_custom_gateway_url():
    client = MeshClient(gateway_url="http://custom-host:9000/orchestrate")
    assert client.gateway_url == "http://custom-host:9000/orchestrate"


def test_ask_returns_json(monkeypatch):
    client = MeshClient()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"answer": "Hello from the Mesh"}

    class FakeHTTPXClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, headers, json, timeout):
            # Capture call inputs for assertion
            FakeHTTPXClient.last_call = {"url": url, "headers": headers, "json": json, "timeout": timeout}
            return mock_response

    monkeypatch.setattr("iagent_mesh.client.httpx.Client", FakeHTTPXClient)

    result = client.ask("hello")
    assert result == {"answer": "Hello from the Mesh"}
    assert FakeHTTPXClient.last_call["url"] == client.gateway_url
    assert FakeHTTPXClient.last_call["headers"]["Authorization"] == "Bearer mock_token"
    assert FakeHTTPXClient.last_call["headers"]["Content-Type"] == "application/json"
    assert FakeHTTPXClient.last_call["json"] == {"prompt": "hello"}
    assert FakeHTTPXClient.last_call["timeout"] == 30.0


def test_ask_returns_text_when_not_json(monkeypatch):
    client = MeshClient()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.side_effect = ValueError("not json")
    mock_response.text = "raw plain text"

    class FakeHTTPXClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, *args, **kwargs): return mock_response

    monkeypatch.setattr("iagent_mesh.client.httpx.Client", FakeHTTPXClient)

    result = client.ask("hello")
    assert result == "raw plain text"


def test_ask_raises_on_http_error(monkeypatch):
    client = MeshClient()

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock(status_code=500)
    )

    class FakeHTTPXClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, *args, **kwargs): return mock_response

    monkeypatch.setattr("iagent_mesh.client.httpx.Client", FakeHTTPXClient)

    with pytest.raises(httpx.HTTPStatusError):
        client.ask("hello")

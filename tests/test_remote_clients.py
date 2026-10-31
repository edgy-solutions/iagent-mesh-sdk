"""Tests for the v0.9.13 concrete ``MeshGraph`` remote client.

No live gateway is called anywhere here — every ``httpx.Client`` is a stub built from
``httpx.MockTransport``, which is the injection seam ``MeshGraphRemoteClient`` is built to take
(see ``iagent_mesh/remote_clients.py``'s constructor).
"""

import httpx
import pytest

from iagent_mesh.interfaces import Initiator, MeshGraph
from iagent_mesh.remote_clients import MeshGraphRemoteClient

BASE_URL = "http://mesh-gateway.test"


def _initiator() -> Initiator:
    return Initiator(subject="person:chris", kind="person")


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_is_structurally_a_meshgraph():
    client = MeshGraphRemoteClient(BASE_URL, _client_for(lambda r: httpx.Response(200)))
    assert isinstance(client, MeshGraph)


# ── success mapping ─────────────────────────────────────────────────────────────────────────


def test_registry_maps_a_successful_response_into_mesh_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mesh/graph/registry"
        return httpx.Response(200, json={"outcome": "answered", "rows": [{"persona": "ops"}]})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.registry(_initiator())

    assert result.outcome == "answered"
    assert result.rows == ({"persona": "ops"},)


def test_providers_for_maps_an_empty_response_into_mesh_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mesh/graph/providers_for"
        return httpx.Response(200, json={"outcome": "empty"})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.providers_for(_initiator(), "mesh:resolveInstance")

    assert result.outcome == "empty"
    assert result.rows == ()


def test_ancestors_maps_a_successful_response_into_mesh_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mesh/graph/ancestors"
        return httpx.Response(200, json={"outcome": "answered", "rows": ["urn:a", "urn:b"]})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.ancestors(_initiator(), "urn:thing", max_hops=5)

    assert result.outcome == "answered"
    assert result.rows == ("urn:a", "urn:b")


def test_is_safety_critical_maps_a_successful_response_into_mesh_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mesh/graph/is_safety_critical"
        return httpx.Response(200, json={"outcome": "answered", "rows": [True]})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.is_safety_critical(_initiator(), mpn="MPN-1", domain="aero")

    assert result.outcome == "answered"
    assert result.rows == (True,)


# ── failure mapping: non-2xx and transport error both land on `unreachable` ───────────────────


def test_non_2xx_status_maps_to_unreachable_not_an_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="gateway down for maintenance")

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.registry(_initiator())

    assert result.outcome == "unreachable"
    assert "503" in result.detail


def test_transport_failure_maps_to_unreachable_not_an_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.providers_for(_initiator(), "mesh:resolveInstance")

    assert result.outcome == "unreachable"
    assert "ConnectError" in result.detail


def test_is_safety_critical_transport_failure_maps_to_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.is_safety_critical(_initiator(), mpn="MPN-1", domain="aero")

    assert result.outcome == "unreachable"
    assert "ConnectTimeout" in result.detail


def test_malformed_response_body_maps_to_unreachable_not_an_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"outcome": "not-a-real-outcome"})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    result = client.registry(_initiator())

    assert result.outcome == "unreachable"


# ── initiator on the wire ───────────────────────────────────────────────────────────────────


def test_initiator_is_serialized_into_the_request_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"outcome": "empty"})

    client = MeshGraphRemoteClient(BASE_URL, _client_for(handler))
    client.edge(_initiator(), "urn:subject", "mesh:verb")

    assert captured["body"]["initiator"] == {
        "subject": "person:chris",
        "kind": "person",
        "on_behalf_of": None,
        "authz_id": None,
    }
    assert captured["body"]["subject"] == "urn:subject"
    assert captured["body"]["verb"] == "mesh:verb"

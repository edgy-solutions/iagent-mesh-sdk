"""`JenaOntologyWriter` against a real `httpx.MockTransport`, mirroring `test_client.py`'s own
"a mock is only evidence when it is shaped like the server" discipline: the fixture below asserts
on the ACTUAL SPARQL body sent, not merely on the outcome the writer returns, so a writer that
returned `written` without ever GRAPH-wrapping the insert half would still be caught.
"""
from __future__ import annotations

import urllib.parse

import httpx
import pytest

from iagent_mesh.interfaces import Initiator
from iagent_mesh.write_results import MeshWriteResult
from iagent_mesh.writers.jena import JenaOntologyWriter

PERSON = Initiator(subject="alice", kind="person")
DELEGATE = Initiator(subject="lane:ca", kind="delegate", on_behalf_of="chris")
SERVICE = Initiator(subject="svc:anything", kind="service")


@pytest.fixture
def wire(monkeypatch):
    """Route JenaOntologyWriter's httpx.post through a MockTransport, capturing the request."""
    seen = {}

    def install(response_for):
        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            # form-urlencoded (`data={"update": sparql}`) — decode back to the actual SPARQL text
            # sent, not the wire-encoded body, so an assertion on it is a POSITIVE CONTENT check.
            seen["body"] = urllib.parse.parse_qs(request.read().decode())["update"][0]
            return response_for(request)

        transport = httpx.MockTransport(handler)

        def fake_post(url, *, data=None, timeout=None):
            with httpx.Client(transport=transport) as client:
                return client.post(url, data=data, timeout=timeout)

        monkeypatch.setattr("iagent_mesh.writers.jena.httpx.post", fake_post)
        return seen

    return install


def _writer() -> JenaOntologyWriter:
    return JenaOntologyWriter(base_url="http://fuseki.local", dataset="ds")


# ── the route ────────────────────────────────────────────────────────────────────────────

def test_upsert_posts_update_to_the_declared_dataset_route(wire):
    seen = wire(lambda r: httpx.Response(200, text="Update succeeded"))
    result = _writer().upsert(
        PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<http://mesh/thing> a <http://mesh/Class> ."]
    )
    assert result == MeshWriteResult.written()
    assert seen["url"] == "http://fuseki.local/ds/update"


# ── every triple this writer emits is GRAPH-wrapped, on BOTH halves, in ONE request ─────────

def test_the_body_GRAPH_WRAPS_both_the_delete_and_the_insert_half(wire):
    """THE POSITIVE-CONTENT ASSERTION. An outcome-only check would pass a writer that silently
    dropped the GRAPH clause and landed the triple in Jena's default graph — exactly the defect
    this class exists to make unrepresentable."""
    seen = wire(lambda r: httpx.Response(200, text="Update succeeded"))
    _writer().upsert(
        PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<http://mesh/thing> a <http://mesh/Class> ."]
    )
    body = seen["body"]
    assert "DELETE WHERE { GRAPH <http://mesh/g> {" in body
    assert "INSERT DATA { GRAPH <http://mesh/g> {" in body
    assert "<http://mesh/thing> a <http://mesh/Class> ." in body


@pytest.fixture
def count_requests(monkeypatch):
    """No two-round-trip window where the graph holds neither the old state nor the new one —
    asserted below by counting requests, not by reading the source."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="Update succeeded")

    transport = httpx.MockTransport(handler)

    def fake_post(url, *, data=None, timeout=None):
        with httpx.Client(transport=transport) as client:
            return client.post(url, data=data, timeout=timeout)

    monkeypatch.setattr("iagent_mesh.writers.jena.httpx.post", fake_post)
    return calls


def test_upsert_makes_exactly_one_request(count_requests):
    _writer().upsert(PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<http://mesh/thing> a <http://mesh/Class> ."])
    assert len(count_requests) == 1


# ── identity gate, refused BEFORE any I/O ───────────────────────────────────────────────────

def test_a_service_identity_is_refused_and_performs_NO_request(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "iagent_mesh.writers.jena.httpx.post",
        lambda *a, **k: calls.append(1) or httpx.Response(200, text="Update succeeded"),
    )
    result = _writer().upsert(SERVICE, graph="http://mesh/g", iri="http://mesh/thing", triples=["<x> a <y> ."])
    assert result.outcome == "refused"
    assert calls == [], "a refused write must perform no I/O — this class's own docstring claims it"


def test_a_delegate_is_admitted(wire):
    wire(lambda r: httpx.Response(200, text="Update succeeded"))
    result = _writer().upsert(DELEGATE, graph="http://mesh/g", iri="http://mesh/thing", triples=["<x> a <y> ."])
    assert result == MeshWriteResult.written()


# ── refusals that never reach the network ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "graph,iri,triples,why",
    [
        ("", "http://mesh/thing", ["<x> a <y> ."], "empty"),
        ("http://mesh/g", "", ["<x> a <y> ."], "empty"),
        ("http://mesh/g", "http://mesh/thing", [], "no triples"),
        ("http://mesh/g>evil", "http://mesh/thing", ["<x> a <y> ."], "not a legal character"),
        ("http://mesh/g", "http://mesh/thing<evil", ["<x> a <y> ."], "not a legal character"),
    ],
)
def test_malformed_or_empty_input_is_refused_with_no_request(monkeypatch, graph, iri, triples, why):
    calls = []
    monkeypatch.setattr(
        "iagent_mesh.writers.jena.httpx.post",
        lambda *a, **k: calls.append(1) or httpx.Response(200, text="Update succeeded"),
    )
    result = _writer().upsert(PERSON, graph=graph, iri=iri, triples=triples)
    assert result.outcome == "refused"
    assert why in (result.detail or "")
    assert calls == []


# ── the substrate half ───────────────────────────────────────────────────────────────────

def test_a_request_error_is_UNREACHABLE_not_failed(monkeypatch):
    def raise_it(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("iagent_mesh.writers.jena.httpx.post", raise_it)
    result = _writer().upsert(PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<x> a <y> ."])
    assert result.outcome == "unreachable"


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_5xx_PROXY_status_is_UNREACHABLE_not_failed(wire, status):
    """The read side's failed/unreachable split, carried over: a proxy 5xx is a deployment
    problem, not the update itself being rejected."""
    wire(lambda r: httpx.Response(status, text="Bad Gateway"))
    result = _writer().upsert(PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<x> a <y> ."])
    assert result.outcome == "unreachable"


def test_a_non_200_non_5xx_status_is_FAILED(wire):
    wire(lambda r: httpx.Response(400, text="parse error at line 3"))
    result = _writer().upsert(PERSON, graph="http://mesh/g", iri="http://mesh/thing", triples=["<x> a <y> ."])
    assert result.outcome == "failed"
    assert "400" in (result.detail or "")


# ── the shape of what upsert returns ────────────────────────────────────────────────────────

def test_it_structurally_satisfies_MeshOntologyWriter():
    from iagent_mesh.interfaces import MeshOntologyWriter

    assert isinstance(_writer(), MeshOntologyWriter)

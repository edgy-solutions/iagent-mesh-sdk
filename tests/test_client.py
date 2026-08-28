"""`MeshClient` against the gateway's ACTUAL `/orchestrate` contract.

WHAT THESE REPLACE. The previous suite asserted the client sent `{"prompt": "hello"}` and parsed
`response.json()`. Both were wrong against the live gateway — `InterviewRequest` requires
`message` AND `session_id`, and the handler returns `text/event-stream` — so the tests PINNED THE
DEFECT: green for months against a `MagicMock` that returned whatever it was told, over a call
that would have 422'd on its first real request. A mock is only evidence when it is shaped like
the server, so the fixtures below are literal SSE frames in the gateway's documented format and
the transport is a real `httpx.MockTransport` rather than a stand-in object.

Gateway contract (invincible-agent `src/iagent/gateway.py`):
    POST /orchestrate  body {"message": str, "session_id": str}  ->  text/event-stream
    event: status         data: {...}
    event: final_payload  data: {"components": [{"markdown_content": "..."}]}
"""
import json as _json

import httpx
import pytest

from iagent_mesh.client import MeshClient


def _sse(*frames) -> bytes:
    return "".join(f"event: {e}\ndata: {d}\n\n" for e, d in frames).encode()


ANSWER = _sse(
    ("status", '{"label": "Engaging Supervisor Agent..."}'),
    ("final_payload", '{"components": [{"markdown_content": "42 anomalies found."}]}'),
)


@pytest.fixture
def wire(monkeypatch):
    """Route MeshClient's httpx.Client through a MockTransport, capturing the request."""
    seen = {}

    def install(response_for):
        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["body"] = _json.loads(request.content)
            return response_for(request)

        real_client = httpx.Client
        transport = httpx.MockTransport(handler)

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr("iagent_mesh.client.httpx.Client", factory)
        return seen

    return install


def test_meshclient_no_longer_requires_a_static_token(monkeypatch):
    """CONTRACT CHANGED, deliberately. This asserted that MeshClient RAISES without
    MESH_DEV_TOKEN — "Ensure you are running within the secured JupyterHub environment."
    That was the perimeter assumption written down as a runtime requirement: a long-lived
    credential whose safety rested on WHERE THE PROCESS RUNS, which is security assumed at
    a boundary the component does not control.

    Constructing a client is now always legal; identity is resolved AT USE (mint-at-use),
    so the absence of a static token is not an error — it is the normal path."""
    monkeypatch.delenv("MESH_DEV_TOKEN", raising=False)
    MeshClient()  # must not raise


def test_default_gateway_url_points_at_the_port_the_service_LISTENS_on():
    """cortex-bff serves 8090. The old default said 8000 — nothing serves that."""
    client = MeshClient()
    assert ":8090" in client.gateway_url
    assert client.gateway_url.endswith("/orchestrate")


def test_meshclient_accepts_custom_gateway_url():
    client = MeshClient(gateway_url="http://custom-host:9000/orchestrate")
    assert client.gateway_url == "http://custom-host:9000/orchestrate"


def test_ask_sends_the_fields_the_gateway_REQUIRES(wire):
    """`message` + `session_id` — not `prompt`.

    `session_id` is required by the gateway precisely because a missing one used to be filled
    with a fresh UUID per request, defeating the run-tracker's dedup and firing duplicate
    Dagster runs. Omitting it is not a cosmetic difference; it is a 422.
    """
    seen = wire(lambda r: httpx.Response(200, content=ANSWER))
    result = MeshClient(gateway_url="http://bff.test/orchestrate").ask("find anomalies")

    assert seen["body"]["message"] == "find anomalies"
    assert seen["body"]["session_id"], "session_id must be sent — the gateway requires it"
    assert "prompt" not in seen["body"]
    assert seen["headers"]["authorization"] == "Bearer mock_token"
    assert seen["headers"]["accept"] == "text/event-stream"
    assert result.text == "42 anomalies found."


def test_ask_parses_the_answer_out_of_the_SSE_STREAM(wire):
    """The response is an event stream; the answer is inside `final_payload`.

    `response.json()` on this body raises — which is what the old client did, and why it would
    have returned the raw SSE text as though it were the answer.
    """
    wire(lambda r: httpx.Response(200, content=ANSWER))
    result = MeshClient(gateway_url="http://bff.test/orchestrate").ask("q")

    assert result.text == "42 anomalies found."
    assert str(result) == "42 anomalies found."
    # The trace is retained — a caller debugging a bad answer needs to see which engine answered.
    assert [e["event"] for e in result.events] == ["status", "final_payload"]


def test_session_id_is_stable_across_calls_and_overridable(wire):
    """One client, one conversation — a follow-up must land on the same thread."""
    seen = wire(lambda r: httpx.Response(200, content=ANSWER))
    client = MeshClient(gateway_url="http://bff.test/orchestrate", session_id="fixed")

    client.ask("first")
    assert seen["body"]["session_id"] == "fixed"
    client.ask("second")
    assert seen["body"]["session_id"] == "fixed"
    client.ask("third", session_id="other")
    assert seen["body"]["session_id"] == "other"


def test_non_200_surfaces_the_gateway_REASON(wire):
    """422's field errors / 403 `cell_not_entitled` must reach the caller.

    Letting `raise_for_status` fire on an unread streaming response discards exactly the body
    that says what to fix — the operator gets a status code and no cause.
    """
    body = b'{"detail":[{"loc":["body","session_id"],"msg":"Field required"}]}'
    wire(lambda r: httpx.Response(422, content=body))

    with pytest.raises(httpx.HTTPStatusError, match="session_id"):
        MeshClient(gateway_url="http://bff.test/orchestrate").ask("q")


def test_pipeline_error_event_is_a_FAILURE_not_an_empty_answer(wire):
    """A mid-stream failure arrives on a 200 — the status line precedes the failure.

    A client that only checks HTTP status reports success for a run that produced no answer.
    """
    wire(lambda r: httpx.Response(200, content=_sse(
        ("status", '{"label": "working"}'),
        ("pipeline_error", '{"error": "engine unreachable"}'))))

    with pytest.raises(RuntimeError, match="engine unreachable"):
        MeshClient(gateway_url="http://bff.test/orchestrate").ask("q")


def test_a_200_with_no_answer_event_RAISES(wire):
    """An empty run is a failed run, not a terse reply."""
    wire(lambda r: httpx.Response(200, content=_sse(("status", '{"l": 1}'))))

    with pytest.raises(RuntimeError, match="no answer event"):
        MeshClient(gateway_url="http://bff.test/orchestrate").ask("q")


def test_static_dev_token_announces_itself(caplog):
    """A static token in a real deployment must read as the anomaly it is."""
    import logging
    with caplog.at_level(logging.WARNING, logger="iagent_mesh.client"):
        MeshClient()._authorization()  # noqa: SLF001
    assert "MESH_DEV_TOKEN" in caplog.text

"""Sync handlers run off the event loop, and carry the request context with them.

Finding B of `docs/HANDOFF-meshtool-execute.md`: `jupyter_guide.md` told authors a standard `def`
handler "will execute safely in a background thread" and recommended it for `df.collect()` — the
heaviest workload — while `execute()` called it inline on the event loop. Authors who FOLLOWED
the recommendation were the ones whose tools stalled.

The last test here is the one the handoff names as proof the two findings were fixed together
rather than in sequence: `asyncio.to_thread`/anyio copy the context, `loop.run_in_executor` does
not, so threading via the wrong mechanism leaves `current_caller()` reading None inside exactly
the handler style the quickstart recommends.
"""
import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from iagent_mesh import CallerIdentity, current_caller
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

_SECRET = "test-signing-secret"


def _token(claims: dict) -> str:
    import jwt
    return jwt.encode(claims, _SECRET, algorithm="HS256")


class Q(ToolInput):
    value: int = 0


class A(ToolOutput):
    result: str


def _tool(handler, name="thread-probe"):
    tool = MeshTool(name=name, description="probe", verb="mesh:probeThread",
                    input_uri="mesh:Query", output_uri="mesh:Answer")
    tool.execute()(handler)
    return tool


def _on_event_loop() -> bool:
    """Is the CURRENT frame executing on a thread with a running event loop?

    The discriminator these tests turn on, and it is measured INSIDE one request rather than by
    comparing thread ids ACROSS two. `TestClient` may serve different requests from different
    portal threads, so "handler thread != some other request's loop thread" can be true even when
    the handler ran inline — a comparison that passes for the wrong reason and would have
    reported this fix working had it never been made.

    Called from a sync handler invoked inline by the async route handler, this returns True (the
    loop is running on this very thread). Called from a worker thread, it raises internally and
    returns False.
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_sync_handler_does_not_run_on_the_event_loop_thread():
    """The direct statement of the defect: the handler must not execute on the loop's thread."""
    observed = {}

    def handler(data: Q) -> A:
        observed["on_loop"] = _on_event_loop()
        return A(result="ok")

    tool = _tool(handler)
    client = TestClient(tool.app)
    r = client.post("/execute", json={"value": 1})

    assert r.status_code == 200, r.text
    assert observed["on_loop"] is False, (
        "sync handler ran on the event-loop thread — a blocking handler stalls every other "
        "request to this tool, health probes included"
    )


def test_a_blocking_sync_handler_does_not_delay_a_concurrent_request():
    """Acceptance: *a sync handler doing a multi-second collect() does not delay a concurrent
    request.*

    Driven through the real ASGI stack with two genuinely concurrent requests. If the handler
    held the loop, the health probe could not complete until the sleep finished.
    """
    import httpx

    def handler(data: Q) -> A:
        time.sleep(1.0)          # stands in for df.collect()
        return A(result="slow")

    tool = _tool(handler, name="blocking-probe")

    @tool.app.get("/health")
    async def health():
        return {"status": "ok"}

    async def drive():
        # BOTH requests are scheduled BEFORE either runs, and each records its own completion
        # time. An earlier version of this test awaited a "handler started" event and only then
        # started the clock — which meant that under the inline (blocking) implementation the
        # loop was already unblocked by the time it measured, and the test PASSED WITH THE DEFECT
        # PRESENT. Verified by re-running it against the pre-fix code: it stayed green. The clock
        # must start before the blocking can begin, or it measures the recovery, not the stall.
        transport = httpx.ASGITransport(app=tool.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            t0 = time.monotonic()

            async def timed(coro):
                resp = await coro
                return resp, time.monotonic() - t0

            slow_task = asyncio.create_task(timed(c.post("/execute", json={"value": 1},
                                                         timeout=30.0)))
            probe_task = asyncio.create_task(timed(c.get("/health", timeout=30.0)))
            (slow_resp, _), (probe, probe_elapsed) = await asyncio.gather(slow_task, probe_task)
            return probe, probe_elapsed, slow_resp

    probe, probe_elapsed, slow_resp = asyncio.run(drive())

    assert probe.status_code == 200
    assert slow_resp.status_code == 200, slow_resp.text
    assert probe_elapsed < 0.5, (
        f"health probe completed only after {probe_elapsed:.2f}s, behind a 1s sync handler — "
        "the handler is holding the event loop"
    )


def test_async_handlers_still_run_on_the_loop():
    """`async def` handlers are awaited, not shunted to a thread.

    The POSITIVE CONTROL for the test above: it proves `_on_event_loop()` can return True in this
    harness at all. Without it, a discriminator that always answered False would make the
    sync-handler assertion pass no matter what `execute()` did.
    """
    observed = {}

    async def handler(data: Q) -> A:
        observed["on_loop"] = _on_event_loop()
        return A(result="async")

    tool = _tool(handler, name="async-probe")
    client = TestClient(tool.app)
    r = client.post("/execute", json={"value": 1})
    assert r.status_code == 200, r.text
    assert observed["on_loop"] is True


def test_THE_COORDINATION_TEST_contextvar_survives_into_the_threaded_sync_handler(monkeypatch):
    """*If threaded: a ContextVar set by the auth dependency is readable inside a sync handler.*

    THIS IS THE TEST THAT PROVES THE TWO FIXES WERE COORDINATED. Fix B done with
    `loop.run_in_executor` — which takes a bare callable and does NOT copy the context — passes
    every other test in this file while making `current_caller()` return None inside the
    recommended handler style. A helper that then fell back to a process identity would read as
    the SERVICE, for every user, with no error: two individually-correct-looking fixes composing
    into a cross-tenant read.

    So the assertion is not "threading works" but "threading preserved the identity".
    """
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _SECRET)
    monkeypatch.delenv("REQUIRE_TRANSPORT_AUTH", raising=False)
    monkeypatch.delenv("USER_ENTITLEMENT_CLAIM", raising=False)

    observed = {}

    def deep_helper():
        # No Request, no parameter — the contextvar is the only channel.
        caller = current_caller()
        observed["on_loop"] = _on_event_loop()
        return caller.require_authz_id() if caller else "LOST"

    def handler(data: Q) -> A:
        return A(result=deep_helper())

    tool = _tool(handler, name="coordination-probe")
    client = TestClient(tool.app)
    r = client.post("/execute", json={"value": 1},
                    headers={"Authorization": f"Bearer {_token({'email': 'threaded@corp.com'})}"})

    assert r.status_code == 200, r.text
    assert r.json()["result"] == "threaded@corp.com", (
        "the caller did not survive into the worker thread — the threading mechanism did not "
        "copy the request context"
    )
    # ...and it genuinely ran OFF the loop, so the assertion above was not satisfied trivially
    # by the handler having run inline (where the contextvar would be in scope anyway).
    assert observed["on_loop"] is False

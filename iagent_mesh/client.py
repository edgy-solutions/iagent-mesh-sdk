"""Client for the mesh's control plane (`POST /orchestrate` on cortex-bff)."""
import json
import logging
import os
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .service_identity import ServiceTokenError, mint_mesh_token  # noqa: F401

logger = logging.getLogger("iagent_mesh.client")

#: cortex-bff's in-cluster address. The service listens on 8090; this default said 8000 for
#: four months, so the zero-config constructor pointed at a port nothing serves.
DEFAULT_GATEWAY_URL = "http://iagent-cortex-bff:8090/orchestrate"

#: The answer event. `generate_dagster_stream` emits `final_payload` carrying the
#: Server-Driven-UI component JSON; the other three are older names kept for back-compat with
#: deployments that have not rolled forward.
_ANSWER_EVENTS = ("final_payload", "final_response", "complete", "result")

#: Emitted when the pipeline fails mid-stream. It arrives on a 200 response — the status line is
#: sent before the failure exists — so a client that only checks HTTP status reports success for
#: a run that produced no answer.
_ERROR_EVENTS = ("pipeline_error", "access_denied")


class MeshResponse:
    """The result of one `ask`, with the raw event stream retained.

    `text` is the answer. `events` is every SSE frame in order — the status/routing trace the UI
    renders — kept because a caller debugging a bad answer needs to see WHICH engine answered,
    and that is only in the trace.
    """

    __slots__ = ("text", "payload", "events")

    def __init__(self, text: str, payload: Optional[Dict[str, Any]], events: List[Dict[str, Any]]):
        self.text = text
        self.payload = payload
        self.events = events

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"<MeshResponse {len(self.text)} chars, {len(self.events)} events>"


class MeshClient:
    """Client for calling the mesh gateway under a SERVICE IDENTITY.

    WHAT CHANGED AND WHY (2026-08-07). This class used to read a single static
    `MESH_DEV_TOKEN` from the environment and raise without it, with the message *"Ensure
    you are running within the secured JupyterHub environment."* That sentence is the
    architecture's old trust model preserved in prose: a long-lived credential whose safety
    rests on WHERE THE PROCESS HAPPENS TO RUN — security assumed at a boundary the component
    does not control. Same shape as the DA read path deferring to a gateway it could not
    verify.

    Minting does not modernise the token; it REMOVES THE PERIMETER DEPENDENCY. Afterwards
    the SDK's outbound trust rests on an identity the platform declares and reconciles, and
    the caller is authenticated wherever it runs.

    `MESH_DEV_TOKEN` survives as a DEV fallback and ANNOUNCES ITSELF, so a static token in a
    real deployment reads as the anomaly it is instead of passing silently.

    THE WIRE CONTRACT WAS THREE-WAYS WRONG (fixed 2026-08-27). `ask` posted `{"prompt": ...}`
    and called `response.json()` against a default URL on port 8000. The gateway's
    `InterviewRequest` requires `message` AND `session_id` (a missing `session_id` used to be
    filled with a fresh UUID per request, which defeated the run-tracker's dedup and fired
    duplicate Dagster runs — so it was made required); the handler returns
    `StreamingResponse(media_type="text/event-stream")`; and the service listens on 8090. Every
    call therefore 422'd, and had it not, `.json()` would have failed on an SSE body. This was
    never caught because the test suite asserted the SDK sent `{"prompt": ...}` — pinning the
    defect rather than the contract, against a mock that could not disagree.
    """

    def __init__(self, gateway_url: str = DEFAULT_GATEWAY_URL, *, session_id: Optional[str] = None):
        self.gateway_url = gateway_url
        self._static_token = os.getenv("MESH_DEV_TOKEN")
        # One client, one conversation by default. The gateway keys its run-tracker on
        # session_id, so reusing it across calls is what makes a follow-up question a follow-up
        # rather than a new thread; callers wanting isolation pass their own per call.
        self._session_id = session_id or f"sdk-{os.getpid()}"

    def _authorization(self) -> str:
        if self._static_token:
            logger.warning("outbound identity: MESH_DEV_TOKEN (static, dev fallback) — "
                           "no service identity in use")
            return f"Bearer {self._static_token}"
        token = mint_mesh_token()
        logger.info("outbound identity: %s (minted)",
                    os.getenv("MESH_CLIENT_ID", "service-identity"))
        return f"Bearer {token}"

    @staticmethod
    def _iter_events(lines: Iterator[str]) -> Iterator[Dict[str, Any]]:
        """Parse an SSE byte-stream into `{"event": name, "data": parsed}` frames.

        Non-JSON `data:` is surfaced as `{"raw": ...}` rather than dropped — a frame the server
        emits and the client silently discards is how a stream "returns nothing" with no error.
        """
        current: Optional[str] = None
        for line in lines:
            if line.startswith("event:"):
                current = line[len("event:"):].strip()
            elif line.startswith("data:"):
                raw = line[len("data:"):].strip()
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = {"raw": raw}
                yield {"event": current, "data": data}

    @staticmethod
    def _text_from(payload: Any) -> str:
        """Pull the human-readable answer out of a Server-Driven-UI payload."""
        if isinstance(payload, str):
            return payload
        if not isinstance(payload, dict):
            return ""
        parts: List[str] = []
        for comp in (payload.get("components") or []):
            if isinstance(comp, dict):
                md = comp.get("markdown_content") or comp.get("content")
                if md:
                    parts.append(str(md))
        if parts:
            return "\n".join(parts)
        for key in ("answer", "text", "message", "content"):
            if payload.get(key):
                return str(payload[key])
        return ""

    def ask(self, prompt: str, *, session_id: Optional[str] = None,
            timeout: float = 300.0) -> MeshResponse:
        """Ask the orchestrator a question and return its answer.

        Blocks until the stream completes. The default timeout is 300s, not 30s: a multi-hop
        supervisor query routinely runs minutes, and the old 30s ceiling would have reported a
        timeout for a query that was progressing normally.
        """
        headers = {
            "Authorization": self._authorization(),
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        body = {"message": prompt, "session_id": session_id or self._session_id}

        events: List[Dict[str, Any]] = []
        answer: Optional[Dict[str, Any]] = None
        streamed = ""

        with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            with client.stream("POST", self.gateway_url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    # Read the body before raising: the gateway puts the REASON here (422's
                    # field errors, 403 `cell_not_entitled` with the entitled cells). Letting
                    # `raise_for_status` fire on an unread streaming response discards exactly
                    # the text that says what to fix.
                    detail = response.read().decode("utf-8", "replace")[:500]
                    raise httpx.HTTPStatusError(
                        f"orchestrate failed: HTTP {response.status_code}: {detail}",
                        request=response.request, response=response,
                    )

                for frame in self._iter_events(response.iter_lines()):
                    events.append(frame)
                    name, data = frame["event"], frame["data"]
                    if name in _ERROR_EVENTS:
                        raise RuntimeError(f"mesh pipeline failed ({name}): {data}")
                    if name in _ANSWER_EVENTS:
                        answer = data
                    elif name in ("text", "delta"):
                        streamed += (data.get("content", "") if isinstance(data, dict)
                                     else str(data))

        text = self._text_from(answer) if answer is not None else streamed
        if not text and answer is None:
            # A 200 that carried no answer event is a FAILED run, not an empty one. Returning ""
            # here would let a broken pipeline read as a terse reply.
            raise RuntimeError(
                "mesh returned no answer event "
                f"(received {len(events)} events: {sorted({e['event'] for e in events if e['event']})}). "
                "The run ended without emitting final_payload."
            )
        return MeshResponse(text, answer, events)

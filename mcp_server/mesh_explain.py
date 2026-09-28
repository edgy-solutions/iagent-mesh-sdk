"""``mesh_explain`` — the first outside consumer of engine-docs ``/explain``.

WHY THIS LIVES HERE AND NOT IN ``iagent_mesh``. ``/explain`` is an HTTP route on one fleet
engine, not a ``MeshOntology``/``MeshGraph``/``MeshVectors`` operation — the SDK's Protocols stay
free of one deployment's endpoint shape. ``mcp_server`` is already the SDK's own DevEx-Hub
consumer package (``scaffold_local_workspace``, ``publish_local_to_mesh``); this is a second
consumer of the same kind, not a new layer.

THE IDENTITY IS A DELEGATE, AND HONESTLY SO. This tool acts under its own entitlements, on behalf
of whoever configured it — that is what ``Initiator.kind == "delegate"`` and ``on_behalf_of``
exist to say (per the architect's ruling, ``iagent_mesh/interfaces.py``). It never claims to be a
person: passing this same ``Initiator`` into ``Initiator.require_person`` raises
``DelegateIdentityRefused``, proven in ``tests/test_mesh_explain.py``, exactly as it would for any
other delegate reaching a person-only guard.

**NO MINT PATH EXISTS YET for ``kind="delegate"``** (see
``invincible-agent/sessions/2026-09-27-packet-from-ca-require-person-is-now-a-shared-allowlist-import-it.md``,
§4). There is no Keycloak client, no claim mapper, nothing that turns this ``Initiator`` into a
verified bearer token engine-docs could check. Sending one anyway would be inventing a credential
this SDK does not have the authority to mint. So the identity travels as **informational headers,
not an Authorization header** — engine-docs' own logs can show who asked and on whose behalf,
under the OBSERVE posture that admits every caller today (``iagent_mesh/transport_auth.py``).
**This is a provenance record, not an authentication control, and must not be read as one.** When
a delegate mint path lands, the one change this module needs is replacing these headers with a
real ``Authorization: Bearer <token>`` from that mint.

THE FIRST REAL CALL FROM A LANE WORKTREE WILL 401, AND THAT IS EXPECTED, NOT A DEFECT HERE (Chris,
2026-09-27). ``iagent_mesh/transport_auth.py``'s OBSERVE posture describes this SDK's own app-level
check; it says nothing about the infrastructure this tool's HTTP call actually crosses in a live
cluster. engine-docs sits behind the BFF's bearer check, and this module sends no ``Authorization``
header at all (the paragraph above) — so a non-mocked call gets refused one layer earlier than
``/explain`` itself, by the gateway, not by engine-docs' own logic. The fix is not in this module:
it is a Keycloak client-credentials client **per delegate** (this lane, a future edge agent), with
``on_behalf_of`` becoming a claim the gateway *records* and never gates on — the next SDK/fleet
item, once the write-half proposal is read.

FOUR OUTCOMES, NEVER A BARE STRING. ``mesh_explain()`` returns a ``MeshResult`` — the same
discipline every mesh read in this SDK follows — so a caller cannot collapse "the corpus has
nothing to say" (``empty``, engine-docs' normal state) into "the corpus could not be asked"
(``unreachable``/``failed``). The two other MCP tools in this package return ``str`` and swallow
their own failures into ``"Failed to ...: {e}"``; this tool is deliberately not built that way.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from iagent_mesh.config import settings
from iagent_mesh.interfaces import Initiator
from iagent_mesh.results import MeshResult

#: Overridable per call; the module default matches the other outbound calls this SDK makes
#: (``service_identity.mint_token``'s own default), so a caller that never thinks about timeouts
#: still gets one — an HTTP call with no timeout is an outage waiting for something else to
#: notice it.
DEFAULT_TIMEOUT_SECONDS = 15.0


class MeshExplainMisconfigured(RuntimeError):
    """The delegate identity or the target URL cannot be established. Refuses before any network
    call, naming the missing variable — never a call made as an invented or anonymous identity."""


def delegate_initiator() -> Initiator:
    """The identity this tool connects as — a delegate, never a person or a silent service.

    ``MESH_EXPLAIN_SUBJECT`` defaults to a fixed, honest label (this tool has no per-user
    credential to read a real one from). ``MESH_EXPLAIN_ON_BEHALF_OF`` has NO default: a delegate
    with nobody accountable is a service under another name (``Initiator``'s own validator refuses
    it), and this function refuses it one step earlier, naming the environment variable rather
    than surfacing a ``ValidationError`` about a field the caller never set directly.
    """
    subject = os.environ.get("MESH_EXPLAIN_SUBJECT", "mcp:mesh_explain")
    on_behalf_of = os.environ.get("MESH_EXPLAIN_ON_BEHALF_OF")
    if not on_behalf_of or not on_behalf_of.strip():
        raise MeshExplainMisconfigured(
            "MESH_EXPLAIN_ON_BEHALF_OF is not set. mesh_explain connects as a delegate "
            "Initiator, and a delegate must name who it acts for — see Initiator.on_behalf_of. "
            "Set it to the person or process this lane's docs reads are attributed to."
        )
    return Initiator(subject=subject, kind="delegate", on_behalf_of=on_behalf_of)


def _provenance_headers(initiator: Initiator) -> dict[str, str]:
    """Informational only — see the module docstring's mint-path caveat before treating this as
    authentication. A header engine-docs does not read yet is still a header its operator can
    grep for once it does."""
    return {
        "X-Mesh-Initiator-Subject": initiator.subject,
        "X-Mesh-Initiator-Kind": initiator.kind,
        "X-Mesh-Initiator-On-Behalf-Of": initiator.on_behalf_of or "",
    }


def mesh_explain(
    subject: str,
    *,
    initiator: Optional[Initiator] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> MeshResult[dict[str, Any]]:
    """Call engine-docs ``POST /explain`` for ``subject``; always return a ``MeshResult``.

    Outcome mapping, read against ``agent_fleet/docs_agent/main.py::explain_endpoint`` (the
    engine's actual contract, not a guess at one):

    * 200, ``abstained: true``  -> ``empty``      — asked; nothing explains this subject yet.
      Engine-docs' documented normal state, not a defect.
    * 200, ``pages: [...]``     -> ``answered``, rows = the pages, whole.
    * 503                       -> ``unreachable`` — the reader/body-store is not wired, or the
      reader raised ``ReaderUnavailable``. A deployment state, not a query defect.
    * 422 / 502 / 409           -> ``failed`` — a bad request, a missing body, or a sha mismatch
      (409 refuses the WHOLE answer on purpose; a partial page list would look complete when it
      is not). Each keeps engine-docs' own detail text.
    * connection error / timeout -> ``unreachable`` — could not even ask.
    * anything else              -> ``failed``, refusing to guess a meaning for an unmapped status
      rather than defaulting it to ``empty`` (the exact collapse ``MeshResult`` exists to end).

    ``initiator`` is accepted as a parameter (rather than only read from the environment) so a
    caller — and the test suite — can supply one explicitly without monkeypatching os.environ.
    """
    initiator = initiator if initiator is not None else delegate_initiator()
    base_url = settings.require("ENGINE_DOCS_URL")
    url = f"{base_url.rstrip('/')}/explain"
    headers = _provenance_headers(initiator)
    body = {"fn": "explain", "params": {"subject": subject}}

    try:
        response = httpx.post(url, json=body, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        return MeshResult.unreachable(
            f"engine-docs /explain timed out after {timeout}s calling {url}: {exc}"
        )
    except httpx.HTTPError as exc:
        return MeshResult.unreachable(f"engine-docs /explain unreachable at {url}: {exc}")

    if response.status_code == 200:
        payload = response.json()
        if payload.get("abstained"):
            return MeshResult.empty()
        pages = payload.get("pages") or []
        if not pages:
            # A 200 that is neither an abstain nor carries pages is a shape this contract does
            # not define. Refusing to guess it means "empty" is the point: `answered` demands
            # rows, and treating an unrecognised 200 as `empty` is the same silent-fallback this
            # type exists to end, one status code later.
            return MeshResult.failed(
                f"engine-docs /explain returned 200 with neither pages nor abstained: {payload!r}"
            )
        return MeshResult.answered(pages)

    if response.status_code == 503:
        return MeshResult.unreachable(f"engine-docs /explain 503: {response.text[:500]}")

    if response.status_code in (422, 502, 409):
        return MeshResult.failed(
            f"engine-docs /explain {response.status_code}: {response.text[:500]}"
        )

    return MeshResult.failed(
        f"engine-docs /explain returned unmapped status {response.status_code}: "
        f"{response.text[:500]}"
    )

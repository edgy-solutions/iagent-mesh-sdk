"""``mcp_server.mesh_explain`` — the identity is honestly a delegate, and the four outcomes hold.

Two things this suite exists to prove, not merely exercise:

1. The identity this tool builds for itself is REFUSED by ``Initiator.require_person`` exactly
   like any other delegate — proof that it never quietly claims to be a person.
2. Every engine-docs response this contract defines maps to a DISTINCT ``MeshResult`` outcome,
   and an unmapped one is refused rather than guessed into ``empty``.
"""
import httpx
import pytest
from unittest.mock import MagicMock, patch

from iagent_mesh.interfaces import DelegateIdentityRefused, Initiator
from mcp_server.mesh_explain import (
    MeshExplainMisconfigured,
    delegate_initiator,
    mesh_explain,
)

SUBJECT = "urn:li:aitool:cost_agent"


def _response(status_code: int, payload: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    resp.text = text or str(payload or {})
    return resp


# ── the identity itself ──────────────────────────────────────────────────────────────────────


def test_delegate_initiator_refuses_to_build_with_nobody_accountable(monkeypatch):
    monkeypatch.delenv("MESH_EXPLAIN_ON_BEHALF_OF", raising=False)
    with pytest.raises(MeshExplainMisconfigured, match="MESH_EXPLAIN_ON_BEHALF_OF"):
        delegate_initiator()


def test_delegate_initiator_is_a_real_delegate(monkeypatch):
    monkeypatch.setenv("MESH_EXPLAIN_ON_BEHALF_OF", "cnogradi@gmail.com")
    initiator = delegate_initiator()
    assert initiator.kind == "delegate"
    assert initiator.on_behalf_of == "cnogradi@gmail.com"


def test_the_delegate_initiator_is_REFUSED_by_require_person(monkeypatch):
    """The load-bearing assertion: this tool's own identity, run through the SAME allowlist
    every other caller in the fleet is held to, is refused — never silently admitted as a
    person, and never swallowed by the SERVICE exception either."""
    monkeypatch.setenv("MESH_EXPLAIN_ON_BEHALF_OF", "cnogradi@gmail.com")
    initiator = delegate_initiator()
    with pytest.raises(DelegateIdentityRefused):
        initiator.require_person("some person-only operation")


def test_on_behalf_of_travels_as_a_header_not_an_authorization_credential():
    """Provenance, not authentication — see the module docstring's mint-path caveat. There is
    no bearer token to send, so there must be no Authorization header pretending there is."""
    initiator = Initiator(subject="mcp:mesh_explain", kind="delegate", on_behalf_of="chris")
    with patch("mcp_server.mesh_explain.httpx.post") as mock_post:
        mock_post.return_value = _response(200, {"abstained": True, "subject": SUBJECT})
        mesh_explain(SUBJECT, initiator=initiator)
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["X-Mesh-Initiator-Subject"] == "mcp:mesh_explain"
    assert headers["X-Mesh-Initiator-Kind"] == "delegate"
    assert headers["X-Mesh-Initiator-On-Behalf-Of"] == "chris"
    assert "Authorization" not in headers


# ── the four outcomes, one per branch of the real contract ──────────────────────────────────


def _explain(payload=None, status=200, text="", initiator=None, side_effect=None):
    initiator = initiator or Initiator(subject="mcp:mesh_explain", kind="delegate", on_behalf_of="chris")
    with patch("mcp_server.mesh_explain.httpx.post") as mock_post:
        if side_effect is not None:
            mock_post.side_effect = side_effect
        else:
            mock_post.return_value = _response(status, payload, text)
        return mesh_explain(SUBJECT, initiator=initiator), mock_post


def test_200_with_pages_is_ANSWERED():
    pages = [{"page_iri": "urn:1", "title": "cost measures"}]
    result, mock_post = _explain(payload={"pages": pages, "page_count": 1, "subject": SUBJECT})
    assert result.outcome == "answered"
    assert result.rows == tuple(pages)
    # the whole page carried, not a summary
    assert result.rows[0]["title"] == "cost measures"


def test_200_abstained_is_EMPTY_not_a_failure():
    result, _ = _explain(payload={"abstained": True, "subject": SUBJECT, "reason": "no_page_explains_this_subject"})
    assert result.outcome == "empty"


def test_503_is_UNREACHABLE_a_deployment_state():
    result, _ = _explain(status=503, text="reader not wired")
    assert result.outcome == "unreachable"
    assert "reader not wired" in result.detail


@pytest.mark.parametrize("status", [422, 502, 409])
def test_client_and_corpus_defects_are_FAILED(status):
    result, _ = _explain(status=status, text=f"engine-docs said {status}")
    assert result.outcome == "failed"
    assert str(status) in result.detail


def test_an_UNMAPPED_status_is_FAILED_never_guessed_as_empty():
    result, _ = _explain(status=500, text="unexpected")
    assert result.outcome == "failed"
    assert "500" in result.detail


def test_a_200_with_neither_pages_nor_abstained_is_FAILED_not_a_silent_empty():
    result, _ = _explain(payload={"subject": SUBJECT})
    assert result.outcome == "failed"
    assert "neither pages nor abstained" in result.detail


def test_a_timeout_is_UNREACHABLE():
    result, _ = _explain(side_effect=httpx.TimeoutException("took too long"))
    assert result.outcome == "unreachable"
    assert "timed out" in result.detail


def test_a_connection_error_is_UNREACHABLE():
    result, _ = _explain(side_effect=httpx.ConnectError("refused"))
    assert result.outcome == "unreachable"


def test_the_configured_timeout_reaches_httpx():
    initiator = Initiator(subject="mcp:mesh_explain", kind="delegate", on_behalf_of="chris")
    with patch("mcp_server.mesh_explain.httpx.post") as mock_post:
        mock_post.return_value = _response(200, {"abstained": True, "subject": SUBJECT})
        mesh_explain(SUBJECT, initiator=initiator, timeout=3.0)
    assert mock_post.call_args.kwargs["timeout"] == 3.0


def test_ENGINE_DOCS_URL_missing_raises_naming_it(monkeypatch):
    from iagent_mesh.config import settings

    monkeypatch.setattr(settings, "ENGINE_DOCS_URL", None)
    initiator = Initiator(subject="mcp:mesh_explain", kind="delegate", on_behalf_of="chris")
    with pytest.raises(RuntimeError, match="ENGINE_DOCS_URL"):
        mesh_explain(SUBJECT, initiator=initiator)

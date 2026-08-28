"""The surface invincible-agent imports — pinned HERE, where a break originates.

invincible-agent depends on this package by GIT TAG (`iagent-mesh @ git+...@v0.3.1`), so a
change here reaches it only on a deliberate tag bump. That is a safety margin, not a guarantee:
the bump is the moment ten engines and the projector inherit whatever this repo did, and by then
the break is discovered downstream in someone else's suite.

So the consumed surface is asserted in the SDK's own tests. Every entry below was established by
enumerating the real import sites in invincible-agent (2026-08-27), not by guessing what "seems
public":

  agent_fleet/{data_analyst,langgraph_support,mesh_registrar,datahub_wrapper,weaviate_expert,
               planning_agent,neo4j_expert,swarms_scraper,ontology_service,presentation_agent,
               restate_analyst}/main.py, src/iagent/projector/app.py,
               helm/invincible-agent/files/domain-broker.py
      -> announce(component=...), app_docs_kwargs(), make_transport_auth_dependency(<name>)
  agent_fleet/restate_analyst/main.py:3414
      -> CallerIdentity as a route annotation; reads .verified / .authz_id / .reason
  agent_fleet/utils/mesh_registration.py:233,549
      -> register_with_mesh(url, manifest, component=, mint=, timeout=)
         result: .registered / .announcement(name) / .status_code / .reason
  agent_fleet/utils/service_identity.py:51
      -> mint_token(client_id=, client_secret=), ServiceTokenError
  tests/test_cross_repo_contracts.py:214
      -> identity_stanzas(tool_name)

NOTE ON WHAT THIS DOES NOT DO. `MeshTool` and `MeshClient` are absent deliberately: no engine in
invincible-agent constructs either (verified by census — zero `MeshTool(` call sites and zero
`.execute()` handlers), which is why 0.4.0 could change `execute()`'s handler semantics at all.
If that ever changes, this file is where the new dependency gets recorded.
"""
from __future__ import annotations

import inspect


def test_transport_auth_app_wiring_signature():
    """The three-line block every engine's `main.py` runs at import."""
    from iagent_mesh.transport_auth import announce, app_docs_kwargs, make_transport_auth_dependency

    # Called POSITIONALLY by restate_analyst (`_transport_auth("engine-a")`) and by keyword
    # elsewhere — both must keep working.
    dep_positional = make_transport_auth_dependency("engine-x")
    dep_keyword = make_transport_auth_dependency(component="engine-x")
    assert callable(dep_positional) and callable(dep_keyword)

    line = announce(component="engine-x")
    assert "transport auth:" in line

    kwargs = app_docs_kwargs()
    assert set(kwargs) <= {"docs_url", "redoc_url", "openapi_url"}


def test_the_dependency_still_returns_a_CallerIdentity_with_the_three_read_fields():
    """restate_analyst's `approve_task` reads `.verified`, `.authz_id`, `.reason`.

    Adding `require_authz_id()` in 0.4.0 must not have disturbed the attributes that route
    already depends on — a `__slots__` class is exactly where an additive change can go wrong.
    """
    from iagent_mesh.transport_auth import CallerIdentity

    ident = CallerIdentity("svc:thing", True, "verified", raw={"sub": "x"})
    assert ident.authz_id == "svc:thing"
    assert ident.verified is True
    assert ident.reason == "verified"
    # And the accessor added for the read path is additive, not a replacement.
    assert ident.require_authz_id() == "svc:thing"


def test_register_with_mesh_signature_and_result_shape():
    """`mesh_registration.py` calls this with exactly these keywords and reads four attributes."""
    from iagent_mesh.registration_transport import register_with_mesh

    params = inspect.signature(register_with_mesh).parameters
    for kw in ("component", "mint", "timeout"):
        assert kw in params, f"register_with_mesh lost the `{kw}` keyword"
    # First two are positional: (registrar_url, manifest)
    positional = [n for n, p in params.items()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    assert positional[:2] == ["registrar_url", "manifest"], positional


def test_registration_result_exposes_what_the_consumer_reads():
    from iagent_mesh.registration_transport import register_with_mesh  # noqa: F401
    import iagent_mesh.registration_transport as rt

    result_cls = None
    for obj in vars(rt).values():
        if inspect.isclass(obj) and hasattr(obj, "announcement"):
            result_cls = obj
            break
    assert result_cls is not None, "no result class exposing .announcement() — consumer breaks"
    for attr in ("registered", "status_code", "reason", "announcement"):
        assert hasattr(result_cls, attr) or attr in getattr(result_cls, "__slots__", ()) \
            or attr in getattr(result_cls, "__annotations__", {}), \
            f"registration result lost `{attr}`"


def test_mint_token_keyword_contract():
    """`service_identity.py` binds the review-starter's env onto this general function."""
    from iagent_mesh.service_identity import ServiceTokenError, mint_token

    params = inspect.signature(mint_token).parameters
    assert "client_id" in params and "client_secret" in params
    # Keyword-only by design: identity is an ARGUMENT, never positional-by-accident.
    assert params["client_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert issubclass(ServiceTokenError, RuntimeError)


def test_identity_stanzas_shape():
    """Pinned from both sides; invincible-agent's cross-repo test consumes this dict."""
    from iagent_mesh.identity_stanzas import SERVICE_CLIENT_KEYS, USER_KEYS, identity_stanzas

    st = identity_stanzas("my_tool")
    assert set(st) == {"serviceClient", "user"}
    assert set(st["serviceClient"]) == set(SERVICE_CLIENT_KEYS)
    assert set(st["user"]) == set(USER_KEYS)
    assert st["serviceClient"]["authzId"] == "svc:my-tool"

"""API docs are OFF in deployment — and the routes prove it, not the kwargs.

MEASURED ON A LIVE POD under REQUIRE: `/openapi.json`, `/docs` and `/redoc` all returned 200
UNAUTHENTICATED. FastAPI registers them through Starlette's `add_route`, not `add_api_route`,
so app-level `dependencies=` NEVER applies to them. The endpoint-gating manifest's claim that
the app-level dependency "covers every route" was therefore false for three routes on every
service — a coverage claim the artifact did not honour.

WHY DISABLED RATHER THAN GATED. A gate here would admit no legitimate traffic ever: an
authenticated *service* has no use for `/redoc`, so its correct steady state is 100% denial —
a disable wearing a dependency's cost. And the disclosure is reconnaissance-grade: an
unauthenticated `/openapi.json` enumerates the full verb surface of every engine, which is the
map an attacker draws first.

DOCS ARE ONLY THE KNOWN MEMBER of the Starlette-bypass class; any future mount or `add_route`
has the same hole. The consumer-side route census is what covers the class. This file covers
the member.
"""
from __future__ import annotations

import pytest

from iagent_mesh import transport_auth as ta

fastapi = pytest.importorskip("fastapi")
starlette_test = pytest.importorskip("fastapi.testclient")


def _app():
    app = fastapi.FastAPI(**ta.app_docs_kwargs())

    @app.get("/real")
    async def real():
        return {"ok": True}

    return starlette_test.TestClient(app, raise_server_exceptions=False)


def test_docs_routes_are_absent_by_default(monkeypatch):
    """Asserted on the ROUTES, not on the kwargs dict — the kwargs are the mechanism, the
    404 is the property. A test of the mechanism passes while the property fails."""
    monkeypatch.delenv("IAGENT_MESH_DOCS", raising=False)
    c = _app()
    for p in ("/openapi.json", "/docs", "/redoc"):
        assert c.get(p).status_code == 404, f"{p} is still served — the disclosure remains"


def test_the_ordinary_route_still_works(monkeypatch):
    """POSITIVE CONTROL: an app that 404'd EVERYTHING would pass the test above."""
    monkeypatch.delenv("IAGENT_MESH_DOCS", raising=False)
    assert _app().get("/real").status_code == 200


def test_explicit_opt_in_restores_them(monkeypatch):
    """Dev keeps its docs — the opt-in must actually work, or people will disable the disable."""
    monkeypatch.setenv("IAGENT_MESH_DOCS", "1")
    c = _app()
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/docs").status_code == 200


def test_the_announcement_states_which(monkeypatch, capsys):
    """A production pod with docs ON must declare its own anomaly, in the same breath as its
    enforcement posture — the pre-positioned-string pattern."""
    monkeypatch.delenv("IAGENT_MESH_DOCS", raising=False)
    ta.announce(component="engine-test")
    assert "api docs: DISABLED (default)" in capsys.readouterr().out

    monkeypatch.setenv("IAGENT_MESH_DOCS", "1")
    ta.announce(component="engine-test")
    out = capsys.readouterr().out
    assert "api docs: ENABLED (explicit config)" in out, (
        "docs were enabled and the startup line did not say so — a deployed pod serving its "
        "full API surface would announce nothing unusual"
    )

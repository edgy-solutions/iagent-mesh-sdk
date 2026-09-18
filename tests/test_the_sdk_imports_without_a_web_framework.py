"""The SDK's CLIENT surface must import AND RUN without a web framework.

Before 2026-09-15 it could not: `__init__.py` eagerly imported `transport_auth`, which imports
`fastapi` unguarded, so every consumer paid for the server stack — including the ones that never
serve anything, which are exactly the consumers a lightweight install exists for.

── THE FIRST FIX WAS WRONG, AND THIS FILE IS SHAPED BY WHY ─────────────────────────────────
It made `__init__` lazy (PEP 562) so the eager import went away. But `current_caller` is
EXPORTED FROM the fastapi-importing module. Deferring the import does not remove the dependency,
it moves the failure from `import iagent_mesh` to the FIRST CALL of the function a non-web
consumer installed the SDK for. Same outcome, later, harder to diagnose.

So the arm that decides this file is not `test_importing...` — an import-only seal passes under
BOTH the broken lazy shape and the correct one. It is `test_current_caller_is_CALLABLE...`
below, which the lazy shape fails. An import seal over a lazy module measures deferral, not
independence.

The real split is inside `transport_auth`: `CallerIdentity` and `current_caller` touch no
fastapi symbol; only the server dependency factory does. Guarding the import THERE is the fix.

── WHY AN `extra` ALONE WOULD HAVE BEEN WORSE THAN NOTHING ─────────────────────────────────
Moving fastapi behind an optional extra with the import unguarded does not make anyone lighter;
it makes the SDK fail for precisely the non-web consumers the extra was written to serve. Every
engine in the fleet already depends on fastapi and would not have noticed. And the failure is
not always loud: dag-tools soft-imports `current_caller` inside a bare `except`, where a missing
transitive is indistinguishable from an absent SDK — see the commit message. The obvious half is
a footgun without the half underneath it.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(snippet: str) -> subprocess.CompletedProcess:
    """A SUBPROCESS, NOT `sys.modules` surgery in-process. Poisoning `sys.modules` in the test
    process leaks into every later test in the session and the failure surfaces somewhere else
    entirely — a fixture whose blast radius is the rest of the suite."""
    return subprocess.run([sys.executable, "-c", textwrap.dedent(snippet)],
                          capture_output=True, text=True)


# `find_spec`, NOT `find_module`. The first version used the legacy finder API, which Python
# removed in 3.12 — so the blocker silently blocked nothing and the main arm passed because
# fastapi was importable all along, not because the SDK had stopped needing it. Caught by the
# control below, which is the only reason it is not still green and meaningless.
_BLOCK_FASTAPI = """
    import sys

    class _Blocker:
        def find_spec(self, name, path=None, target=None):
            if name == "fastapi" or name.startswith("fastapi."):
                raise ImportError(f"{name} is blocked for this test")
            return None
    sys.meta_path.insert(0, _Blocker())
"""


def test_THE_CONTROL_the_blocker_actually_blocks():
    """A blocker that silently failed to block would make every arm below pass for the wrong
    reason — green because fastapi was importable all along. The fixture must be shown to bite
    before anything it fixtures is trusted, so it is stated FIRST."""
    r = _run(_BLOCK_FASTAPI + """
    import fastapi
    """)
    assert r.returncode != 0, "the blocker did not block — every arm below proves nothing"


def test_importing_the_sdk_does_not_require_fastapi():
    r = _run(_BLOCK_FASTAPI + """
    import iagent_mesh
    print("OK", iagent_mesh.MeshClient.__name__)
    """)
    assert r.returncode == 0, (
        f"`import iagent_mesh` still requires a web framework:\n{r.stderr[-800:]}"
    )
    assert "OK MeshClient" in r.stdout


def test_current_caller_is_CALLABLE_without_fastapi_not_merely_IMPORTABLE():
    """THE ARM THIS FILE EXISTS FOR.

    A lazy `__init__` over an unguarded `transport_auth` passes the import arm above and FAILS
    here — the dependency was deferred, not removed, and the failure lands on the first call
    rather than at import. Nothing else in this file discriminates those two shapes.
    """
    r = _run(_BLOCK_FASTAPI + """
    from iagent_mesh import CallerIdentity, current_caller
    assert current_caller() is None, "no request in scope reads as None, it does not raise"
    ident = CallerIdentity("u@example.test", True, "ok")
    assert ident.authz_id == "u@example.test"
    print("CLIENT SURFACE RUNS")
    """)
    assert "CLIENT SURFACE RUNS" in r.stdout, (
        f"the client surface imports but does not RUN without fastapi:\n{r.stderr[-800:]}"
    )


def test_the_SERVER_factory_refuses_with_a_reason_when_the_stack_is_absent():
    """A bare NameError on `Request` names nothing an operator can act on. The refusal must say
    which half needs the framework, and that the other half deliberately does not."""
    r = _run(_BLOCK_FASTAPI + """
    from iagent_mesh.transport_auth import make_transport_auth_dependency
    try:
        make_transport_auth_dependency("some-engine")
    except ModuleNotFoundError as exc:
        msg = str(exc)
        assert "SERVER half" in msg, msg
        assert "CLIENT half" in msg, "the refusal must say the other half still works"
        print("REFUSED WELL")
    """)
    assert "REFUSED WELL" in r.stdout, r.stderr[-800:]


def test_the_REFUSAL_IS_AT_SETUP_not_per_request():
    """An app that assembles successfully and then 500s on every request has moved a packaging
    error into the traffic path. The factory must refuse while the app is being built."""
    import inspect

    from iagent_mesh import transport_auth as ta

    src = inspect.getsource(ta.make_transport_auth_dependency)
    guard = src.index("_FASTAPI_MISSING is not None")
    inner = src.index("async def transport_auth")
    assert guard < inner, "the guard must fire before the per-request closure is even defined"


# ── the regression this fix must not reintroduce ─────────────────────────────────────────

def test_Request_STAYS_A_MODULE_GLOBAL():
    """THE 422 OUTAGE GUARD, and the reason the fix REBINDS rather than RELOCATES.

    `transport_auth` uses `from __future__ import annotations`, so `request: Request` is a STRING
    that FastAPI resolves with typing.get_type_hints() against MODULE GLOBALS. A previous attempt
    moved this import inside the factory; the name became a local, the string did not resolve,
    FastAPI treated the parameter as a QUERY param, and every request 422'd — a fleet-wide outage
    shipped as a library bump.

    Guarding the import is safe precisely because it keeps the name a module global on BOTH
    branches. If someone "simplifies" it back into the factory, this reds.
    """
    from iagent_mesh import transport_auth as ta

    assert hasattr(ta, "Request"), (
        "`Request` is no longer a module global — if it was moved into the factory, every "
        "request will 422 with loc=['query','request']"
    )
    assert hasattr(ta, "HTTPException")


def test_the_client_surface_names_no_fastapi_symbol():
    """The claim underneath the whole split, asserted rather than assumed: if `current_caller`
    ever grows a fastapi reference, the guarded import will hand it None at runtime."""
    import inspect

    from iagent_mesh import transport_auth as ta

    src = inspect.getsource(ta.current_caller)
    for symbol in ("HTTPException", "Request"):
        assert symbol not in src, (
            f"current_caller references {symbol} — it is no longer framework-free"
        )


# ── the [server] extra: the second half of the two-commit change ─────────────────────────

def _pyproject() -> str:
    import pathlib

    return (pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
        encoding="utf-8"
    )


def test_THE_SERVER_STACK_IS_NOT_A_HARD_DEPENDENCY():
    """THE ARM THE EXTRA EXISTS FOR. While fastapi sat in `dependencies`, every consumer paid for
    a web framework including the ones that never serve — and the extra is the only thing that
    stops that."""
    import re

    deps = re.search(r"^dependencies = \[(.*?)^\]", _pyproject(), re.S | re.M)
    assert deps, "the dependencies block could not be parsed"
    block = deps.group(1)
    for pkg in ("fastapi", "uvicorn"):
        assert f'"{pkg}' not in block, (
            f"{pkg} is back in the HARD dependencies, so the [server] extra buys nothing and "
            f"non-web consumers are paying for a web framework again"
        )


def test_THE_SERVER_EXTRA_EXISTS_AND_CARRIES_BOTH():
    """Removing them from `dependencies` without an extra to install them from would strand
    every engine — the fleet needs a name to ask for the stack by."""
    import re

    extras = re.search(r"^server = \[(.*?)\]", _pyproject(), re.S | re.M)
    assert extras, "there is no [server] extra, so nothing can ask for the stack by name"
    for pkg in ("fastapi", "uvicorn"):
        assert pkg in extras.group(1), f"the server extra does not carry {pkg}"


def test_THE_ENGINE_HOST_REFUSES_WITH_A_REASON_RATHER_THAN_A_BARE_IMPORT_ERROR():
    """`core.py` IS the host, so it genuinely cannot work without fastapi — what changed is the
    READING of the failure. While fastapi was a hard dependency, a missing one meant a broken
    install; now it usually means the extra was not installed. A bare traceback cannot tell
    those apart, and they have different fixes."""
    r = _run(_BLOCK_FASTAPI + """
    try:
        import iagent_mesh.core
    except ModuleNotFoundError as exc:
        msg = str(exc)
        assert "ENGINE HOST" in msg, msg
        assert "iagent-mesh[server]" in msg, "the refusal must name what to install"
        assert "CLIENT surface" in msg, "it must say which half still works without the stack"
        print("HOST REFUSED WELL")
    """)
    assert "HOST REFUSED WELL" in r.stdout, r.stderr[-800:]


def test_THE_PACKAGE_STILL_IMPORTS_WITHOUT_THE_EXTRA():
    """THE WHOLE POINT, RESTATED AGAINST THE NEW PACKAGING: making the stack optional is only
    safe because the guard landed first. If `import iagent_mesh` needed fastapi, this extra
    would break exactly the consumers it was written to serve."""
    r = _run(_BLOCK_FASTAPI + """
    import iagent_mesh
    assert iagent_mesh.current_caller() is None
    assert iagent_mesh.MeshVectors is not None
    assert "currency" in iagent_mesh.MARKER_DOES_NOT_ASSERT
    print("CLIENT SURFACE INTACT WITHOUT THE EXTRA")
    """)
    assert "CLIENT SURFACE INTACT WITHOUT THE EXTRA" in r.stdout, r.stderr[-800:]


def test_THE_DEV_EXTRA_PULLS_THE_SERVER_STACK():
    """THE SUITE TESTS THE SERVER SURFACE, so a dev environment without it cannot COLLECT.

    Eight modules import `fastapi.testclient` or `iagent_mesh.core` directly. When fastapi moved
    from `dependencies` to the `[server]` extra, `uv run --extra dev` stopped resolving it and CI
    died at collection with eight import errors.

    IT COULD NOT HAVE BEEN CAUGHT LOCALLY, and that is why this arm exists rather than a note: the
    move left fastapi ALREADY INSTALLED in every venv that predated it, so the declared set and
    the actual environment disagreed and only a clean resolution could tell. The same shape as a
    system-wide editable install — the environment answering a question about the declaration.

    Asserted as a SELF-REFERENCE rather than by listing fastapi twice: `server` owns the version
    bounds and `dev` asks for it by name. Two lists are free to drift, and a dev environment
    resolving a different fastapi than the extra declares is the divergence this change is about.
    """
    import re

    # THE WHOLE LINE, not a bracket-to-bracket match. A non-greedy `\[(.*?)\]` stops at the FIRST
    # `]` — which is the one inside `iagent-mesh[server]`, the very token being looked for. The
    # instrument could not see its target because the target contains the instrument's terminator.
    dev = re.search(r"^dev = (.+)$", _pyproject(), re.M)
    assert dev, "the dev extra could not be parsed"
    assert "iagent-mesh[server]" in dev.group(1), (
        "the dev extra no longer pulls the server stack, so `uv run --extra dev` cannot collect "
        "the eight modules that import fastapi — CI dies before a single test runs, and no "
        "existing venv will reproduce it"
    )
    for pkg in ("fastapi", "uvicorn"):
        assert f'"{pkg}' not in dev.group(1), (
            f"{pkg} is listed in `dev` directly — that is a second copy of the version bounds, "
            f"free to drift from the [server] extra it duplicates"
        )

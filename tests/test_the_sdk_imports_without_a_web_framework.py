"""`import iagent_mesh` must not require a web framework.

Before 2026-09-15 it did: `__init__.py` eagerly imported `transport_auth`, which imports
`fastapi` unguarded. Every consumer paid for the server stack — including the ones that never
serve anything, which are exactly the consumers a lightweight install exists for.

AND IT IS WHY AN `extra` ALONE WOULD HAVE BEEN WORSE THAN NOTHING. Moving the server stack behind
an optional extra with the eager import still in place does not make anyone lighter; it makes
`import iagent_mesh` FAIL for precisely the non-web consumers the extra was written to serve.
Every engine in the fleet already depends on fastapi and would not have noticed. The obvious half
is a footgun without the half underneath it.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


def _run(snippet: str) -> subprocess.CompletedProcess:
    """A SUBPROCESS, NOT `sys.modules` SURGERY IN-PROCESS. Poisoning `sys.modules` in the test
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


def test_importing_the_sdk_does_not_require_fastapi():
    r = _run(_BLOCK_FASTAPI + """
    import iagent_mesh
    print("OK", iagent_mesh.MeshClient.__name__)
    """)
    assert r.returncode == 0, (
        f"`import iagent_mesh` still requires a web framework:\n{r.stderr[-600:]}"
    )
    assert "OK MeshClient" in r.stdout, "the client surface must survive the lazy split"


def test_THE_CONTROL_the_blocker_actually_blocks():
    """A blocker that silently failed to block would make the arm above pass for the wrong
    reason — green because fastapi was importable all along, not because the SDK stopped
    needing it. The fixture must be shown to bite before it is trusted."""
    r = _run(_BLOCK_FASTAPI + """
    import fastapi
    """)
    assert r.returncode != 0, "the blocker did not block — the arm above proves nothing"


def test_the_server_surface_still_resolves_when_the_stack_is_present():
    """POSITIVE CONTROL for the lazy split: the names stay importable for anyone who has the
    server stack, and stay in `__all__`. Only the COST moved."""
    import iagent_mesh

    assert iagent_mesh.CallerIdentity is not None
    assert iagent_mesh.current_caller is not None
    assert "CallerIdentity" in iagent_mesh.__all__


def test_the_server_surface_REFUSES_WITH_A_REASON_when_the_stack_is_absent():
    """A bare ModuleNotFoundError names `fastapi` and leaves the reader to guess whether that is
    a bug or a choice. The refusal says it is a choice and what to do about it."""
    r = _run(_BLOCK_FASTAPI + """
    import iagent_mesh
    try:
        iagent_mesh.CallerIdentity
    except ModuleNotFoundError as exc:
        assert "server surface" in str(exc), str(exc)
        assert "on purpose" in str(exc), "the refusal must say the omission was deliberate"
        print("REFUSED WELL")
    """)
    assert "REFUSED WELL" in r.stdout, r.stderr[-600:]


def test_an_unknown_attribute_is_still_an_AttributeError():
    """PEP 562 `__getattr__` catches EVERY missed lookup, so a typo could have become a
    confusing import error about a web framework."""
    import iagent_mesh

    with pytest.raises(AttributeError):
        iagent_mesh.no_such_name

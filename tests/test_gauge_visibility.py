"""The gauge can actually be READ — asserted, not claimed by a docstring.

WHAT THIS CAUGHT, in production, on the first service rolled. `make_transport_auth_dependency`
logs one line per request and its docstring says that is "what turns the migration into a gauge
instead of a claim". It was still a claim. No mesh engine configures logging, so the record's
logger had no handlers, root had none and sat at WARNING, and the line fell through to
`logging.lastResort` — which is WARNING. Twelve services would have announced `OBSERVE` at
startup and observed NOTHING.

Why that is worse than an ordinary missing log: the contract flip's precondition is "the
unverified-caller count reads zero", and **a silent gauge satisfies that perfectly and falsely**.
ZERO-BECAUSE-SILENT AND ZERO-BECAUSE-CLEAN are precisely the two states the instrument exists to
separate — the guard-gone-quiet species, about to become load-bearing for a security posture flip.

So the instrument gets the same treatment every claim has earned: a witness, and a demonstrated
ability to go dark.
"""
from __future__ import annotations

import logging

import pytest

from iagent_mesh import transport_auth as ta


@pytest.fixture(autouse=True)
def _clean_logging(monkeypatch):
    """Each case starts from a KNOWN logging state and restores it.

    Without this the cases contaminate each other through global logger state — and a test
    that passes because a previous test configured logging is the same false green this file
    exists to catch.

    NOTE ON `propagate = False`: pytest's own logging plugin installs a capture handler on the
    ROOT logger for every test, and `ensure_gauge_visible` correctly DEFERS to any handler it
    finds upstream. Clearing root is not reliable — the plugin owns it. So the package logger
    is detached from the chain, which reproduces the deployed condition faithfully (a mesh
    engine has no handler anywhere) and deterministically. Cases that model an
    app-with-logging re-attach it explicitly.
    """
    pkg = logging.getLogger("iagent_mesh")
    root = logging.getLogger()
    saved = (list(pkg.handlers), pkg.level, pkg.propagate, root.level)
    pkg.handlers.clear()
    pkg.setLevel(logging.NOTSET)
    pkg.propagate = False
    root.setLevel(logging.WARNING)
    monkeypatch.delenv("IAGENT_MESH_LOG_AUTOCONFIG", raising=False)
    yield
    pkg.handlers[:], pkg.level, pkg.propagate, root.level = saved


def test_the_bug_reproduces_without_the_fix():
    """POSITIVE CONTROL for the defect itself: bare defaults emit NOTHING at INFO.

    If this ever stops failing, the environment has changed and every other case here is
    testing something other than what it claims.
    """
    assert not ta._emits_info(ta.logger), (
        "an INFO record already emits under bare logging defaults — the premise of this "
        "module is gone and the fix below is untestable"
    )


def test_ensure_gauge_visible_makes_records_emit(capsys):
    changed = ta.ensure_gauge_visible()
    assert changed, "ensure_gauge_visible() reported no change on a silent configuration"
    assert ta._emits_info(ta.logger)

    ta.logger.info("caller: none (absent, no mint attempted) posture=OBSERVE path=/health")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "posture=OBSERVE" in out, f"the gauge line did not reach stdout; got: {out!r}"


def test_it_attaches_to_the_package_logger_never_root():
    """The SDK makes ITS OWN records visible; it does not reconfigure the host.

    Asserted as "root is UNCHANGED", not "root is empty" — pytest's logging plugin owns root
    handlers here, so an emptiness assertion would be testing the test runner rather than the
    SDK. The claim is about what this function ADDS.
    """
    root = logging.getLogger()
    before = list(root.handlers)
    root_level_before = root.level

    ta.ensure_gauge_visible()

    assert logging.getLogger("iagent_mesh").handlers, "no handler on the package logger"
    assert list(root.handlers) == before, (
        "the SDK attached a handler to the ROOT logger — that reconfigures the host "
        "application's logging, which is not this package's to own"
    )
    assert root.level == root_level_before, "the SDK changed the ROOT logger's level"


def test_it_defers_when_the_app_already_configured_logging():
    """DOUBLE-EMIT TRAP. An app with its own handler must be left completely alone."""
    pkg = logging.getLogger("iagent_mesh")
    pkg.propagate = True                      # rejoin the chain: this app HAS logging
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    root.setLevel(logging.INFO)

    changed = ta.ensure_gauge_visible()
    assert not changed, "the SDK modified logging even though records already emitted"
    assert not logging.getLogger("iagent_mesh").handlers, (
        "the SDK added a handler on top of a configured app — every gauge line would appear "
        "TWICE, trading a silent gauge for a duplicated one"
    )


def test_level_only_repair_when_handlers_exist_upstream():
    """Handlers upstream but level too high: lower the level, add NO handler.

    This is the case a naive "if not handlers: add one" fix gets wrong in the other
    direction — it would see handlers, do nothing, and leave the gauge dark.
    """
    pkg = logging.getLogger("iagent_mesh")
    pkg.propagate = True                      # rejoin the chain: handlers exist upstream
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    root.setLevel(logging.WARNING)

    assert not ta._emits_info(ta.logger), "premise: records must be level-filtered here"
    changed = ta.ensure_gauge_visible()
    assert changed and ta._emits_info(ta.logger), "the level-only repair did not take"
    assert not logging.getLogger("iagent_mesh").handlers, (
        "a handler was added when lowering the level alone was sufficient — this duplicates "
        "every record into the app's existing handler"
    )


def test_it_is_idempotent():
    ta.ensure_gauge_visible()
    n = len(logging.getLogger("iagent_mesh").handlers)
    ta.ensure_gauge_visible()
    ta.ensure_gauge_visible()
    assert len(logging.getLogger("iagent_mesh").handlers) == n, "handlers accumulated"


def test_the_escape_hatch_makes_the_gauge_GO_DARK(monkeypatch):
    """BREAK-ON-PURPOSE, shipped as a test.

    A litany leg that has never gone red is not yet a check. This proves the gauge's
    visibility is a real, defeatable property rather than an ambient accident of the
    environment — and gives the roll litany a way to demonstrate leg 5 can fail.
    """
    monkeypatch.setenv("IAGENT_MESH_LOG_AUTOCONFIG", "0")
    assert ta.ensure_gauge_visible() is False
    assert not ta._emits_info(ta.logger), (
        "records emit even with autoconfig disabled — leg 5 cannot be shown to fail, so it "
        "is not yet a check"
    )


def test_announce_makes_the_gauge_readable_before_it_announces(capsys):
    """A service announcing OBSERVE must be a service whose gauge can be read.

    Announcing a posture whose evidence channel is dark is the gate-with-paperwork shape
    this package exists to refuse — the announcement would be the paperwork.
    """
    line = ta.announce(component="engine-test")
    assert "transport auth:" in line
    assert ta._emits_info(ta.logger), "announce() left the gauge unreadable"

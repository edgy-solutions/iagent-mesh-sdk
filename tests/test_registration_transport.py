"""The one registration transport: retry semantics preserved, failure cause NAMED.

The retry shape here is not new — it is ADR-0006's addendum, which the PLATFORM already
implemented and this package did not. Consolidating "platform binds SDK" would have deleted it,
which is why the consolidation was read before it was written.
"""
from __future__ import annotations

import pytest

from iagent_mesh import registration_transport as rt

httpx = pytest.importorskip("httpx")


class _Resp:
    def __init__(self, code, text=""):
        self.status_code, self.text = code, text


def _patch(monkeypatch, codes, record=None):
    """Feed a scripted sequence of status codes; optionally record the headers sent.

    `register_with_mesh` does `import httpx` INSIDE the function, so replacing the module in
    sys.modules is what the call actually resolves. `time` is replaced on the MODULE object
    rather than globally — patching the real time.sleep would slow every other test's
    unrelated sleeps to zero and hide a hang.
    """
    import sys, types
    seq = list(codes)

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None):
            if record is not None:
                record.append(headers or {})
            return _Resp(seq.pop(0))

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(Client=_Client))
    monkeypatch.setattr(rt, "time", types.SimpleNamespace(sleep=lambda *_a, **_k: None))


def test_success_registers(monkeypatch):
    _patch(monkeypatch, [200])
    r = rt.register_with_mesh("http://reg", {"a": 1})
    assert r.registered and r.attempts == 1


def test_422_is_permanent_and_NOT_retried(monkeypatch):
    """A Contract D rejection needs the ontology fixed; retrying only DELAYS THE ALARM."""
    _patch(monkeypatch, [422, 200])          # a retry would find the 200 and hide the bug
    r = rt.register_with_mesh("http://reg", {})
    assert not r.registered and r.attempts == 1, "422 was retried — it is permanent"
    assert "422" in r.reason and "Contract D" in r.reason


def test_5xx_is_retried_then_reported(monkeypatch):
    monkeypatch.setenv("MESH_REGISTRAR_SDK_MAX_ATTEMPTS", "3")
    _patch(monkeypatch, [503, 503, 503])
    r = rt.register_with_mesh("http://reg", {})
    assert not r.registered and r.attempts == 3
    assert "503" in r.reason


def test_5xx_then_success(monkeypatch):
    """POSITIVE CONTROL: retry must actually RECOVER, not merely count."""
    monkeypatch.setenv("MESH_REGISTRAR_SDK_MAX_ATTEMPTS", "3")
    _patch(monkeypatch, [503, 200])
    r = rt.register_with_mesh("http://reg", {})
    assert r.registered and r.attempts == 2


def test_the_token_is_actually_sent(monkeypatch):
    seen = []
    _patch(monkeypatch, [200], record=seen)
    rt.register_with_mesh("http://reg", {}, mint=lambda: "TOK")
    assert seen and seen[0].get("Authorization") == "Bearer TOK", (
        "the mint was called but its token never reached the request — an authenticated "
        "transport that sends no credential is the presence-check defect one layer up"
    )


def test_mint_failure_and_registrar_refusal_are_distinguishable(monkeypatch):
    """THE DISCRIMINANT. Both produce one symptom — the engine's verbs absent from routing —
    and an operator who cannot tell them apart spends an incident's first hour learning which
    side of the call broke. Two causes must not share one message."""
    monkeypatch.setenv("MESH_REGISTRAR_SDK_MAX_ATTEMPTS", "2")

    _patch(monkeypatch, [200])
    def _boom():
        raise RuntimeError("keycloak unreachable")
    mint_fail = rt.register_with_mesh("http://reg", {}, mint=_boom)

    _patch(monkeypatch, [503, 503])
    registrar_fail = rt.register_with_mesh("http://reg", {})

    assert not mint_fail.registered and not registrar_fail.registered
    assert "mint failed" in mint_fail.reason, mint_fail.reason
    assert "503" in registrar_fail.reason, registrar_fail.reason
    assert mint_fail.reason != registrar_fail.reason, (
        "two different causes produced the same message — the symptom is identical, so the "
        "MESSAGE is the only thing that can separate them"
    )


def test_the_announcement_makes_unregistered_an_alarm():
    """'Up but unregistered' must be a NAMED state, not a mystery. Routing is conjunctive, so
    an unregistered verb never routes — degraded and visible, never corrupt. That safety is
    what makes run-unregistered correct, and the announcement is what makes it visible."""
    ok = rt.RegistrationResult(True)
    bad = rt.RegistrationResult(False, "mint failed: ServiceTokenError")
    assert "OK" in ok.announcement("engine-w")
    line = bad.announcement("engine-w")
    assert "UNREGISTERED" in line and "mint failed" in line, line

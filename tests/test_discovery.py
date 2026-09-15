"""Discovery refuses ambiguity. The arm that matters is the one asserting it does NOT pick.

Zero and one are the easy cases. TWO is where a resolver quietly becomes a chooser — first
match, alphabetical, most recently installed — and every one of those reads as reasonable while
making a deployment's store selection invisible.
"""
from __future__ import annotations

import pytest

from iagent_mesh.discovery import (
    GROUPS,
    AmbiguousImplementation,
    NoImplementation,
    available,
    resolve,
)


class _EP:
    """A stand-in for an installed entry point. Not a mock of the resolver — the resolver is the
    thing under test; this is the package metadata it reads."""

    def __init__(self, name: str, value: str, dist: str | None = None, loads=None):
        self.name, self.value = name, value
        self.dist = type("D", (), {"name": dist})() if dist else None
        self._loads = loads

    def load(self):
        return self._loads


def _install(monkeypatch, *eps):
    monkeypatch.setattr("iagent_mesh.discovery._entry_points", lambda group: list(eps))


# ── the three cardinalities ──────────────────────────────────────────────────────────────

def test_ONE_implementation_resolves(monkeypatch):
    """POSITIVE CONTROL. A resolver that raised on everything would pass both refusals below."""
    sentinel = object()
    _install(monkeypatch, _EP("neo4j", "pkg.graph:Impl", "my-pkg", loads=sentinel))
    assert resolve("MeshGraph") is sentinel


def test_ZERO_is_an_ABSENCE_and_says_what_to_declare(monkeypatch):
    _install(monkeypatch)
    with pytest.raises(NoImplementation) as exc:
        resolve("MeshGraph")
    msg = str(exc.value)
    assert "iagent_mesh.graph" in msg, "the refusal must name the group nothing declared"
    assert "entry-points" in msg, "…and what a package writes to fill it"
    assert "ABSENCE" in msg, (
        "nothing installed is a different problem from something installed and broken, and an "
        "operator who cannot tell which will debug the wrong one"
    )


def test_TWO_IS_A_REFUSAL_AND_NOT_A_PICK(monkeypatch):
    """THE ARM THIS MODULE EXISTS FOR. A resolver that returned the first, the alphabetically
    first, or the most recently installed would pass every other test in this file."""
    a = _EP("alpha", "a.graph:A", "pkg-a", loads="A")
    b = _EP("beta", "b.graph:B", "pkg-b", loads="B")
    _install(monkeypatch, a, b)
    with pytest.raises(AmbiguousImplementation):
        resolve("MeshGraph")


def test_the_ambiguity_refusal_NAMES_BOTH_and_their_distributions(monkeypatch):
    """"Ambiguous implementation" with no candidates sends an operator to read the whole
    dependency tree. The distribution is the actionable fact — it says what to uninstall."""
    _install(monkeypatch,
             _EP("alpha", "a.graph:A", "pkg-a", loads="A"),
             _EP("beta", "b.graph:B", "pkg-b", loads="B"))
    with pytest.raises(AmbiguousImplementation) as exc:
        resolve("MeshGraph")
    msg = str(exc.value)
    for expected in ("alpha", "beta", "pkg-a", "pkg-b"):
        assert expected in msg, f"the refusal must name {expected!r}"


def test_there_is_NO_ARGUMENT_THAT_MAKES_IT_PICK():
    """An override would BE a pick, and a pick is the thing being refused — it moves the
    ambiguity from the package set into a values file, where it is harder to see, not easier."""
    import inspect

    params = set(inspect.signature(resolve).parameters) - {"interface"}
    assert not params, (
        f"resolve() grew {sorted(params)} — a selection argument turns a refusal into a choice"
    )


# ── diagnostics must not have side effects ───────────────────────────────────────────────

def test_available_does_NOT_load_anything(monkeypatch):
    """An operator asking "what is installed" must not trigger the import side effects of the
    thing they are investigating."""
    loaded = []

    class _Exploding(_EP):
        def load(self):
            loaded.append(self.name)
            raise AssertionError("available() must not load")

    _install(monkeypatch, _Exploding("alpha", "a:A", "pkg-a"), _Exploding("beta", "b:B", "pkg-b"))
    assert available("MeshGraph") == [("alpha", "a:A"), ("beta", "b:B")]
    assert loaded == [], "available() loaded an implementation"


def test_available_reports_AMBIGUITY_rather_than_refusing_it(monkeypatch):
    """The diagnostic must survive the state the resolver refuses — otherwise the only tool for
    investigating "two installed" is the thing that will not run while two are installed."""
    _install(monkeypatch, _EP("alpha", "a:A", "pkg-a"), _EP("beta", "b:B", "pkg-b"))
    assert len(available("MeshGraph")) == 2


# ── the group names ──────────────────────────────────────────────────────────────────────

def test_groups_are_named_for_the_INTERFACE_never_an_implementation():
    """`iagent_mesh.graph`, not `iagent_mesh.neo4j` — R-038 applied to a group name. A group
    named for its first implementation makes swapping the store a rename every consumer sees."""
    for interface, group in GROUPS.items():
        assert group.startswith("iagent_mesh."), group
        leaf = group.split(".", 1)[1]
        for implementation_name in ("neo4j", "weaviate", "jena", "fuseki", "rdflib", "langfuse"):
            assert implementation_name not in leaf, (
                f"group {group!r} names an implementation; name the interface it fills"
            )


def test_an_unknown_interface_is_refused_by_name():
    with pytest.raises(NoImplementation, match="not a mesh interface"):
        resolve("MeshWhatever")

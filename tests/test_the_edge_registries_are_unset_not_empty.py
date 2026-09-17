"""The edge registries: derived membership, and UNSET distinguished from EMPTY.

The declaration lives here and the writes live in `invincible-agent`, so this file cannot check
conformance — that seal is over there, asserting both directions. What it CAN check is that the
registry does not lie about what it knows.
"""
from __future__ import annotations

import pytest

from iagent_mesh.edge_types import (
    REGISTRAR_EDGE_TYPES,
    TRACE_WRITER_EDGE_TYPES,
    UndeclaredWriteInterface,
    declared_edge_types,
)


def test_THE_REGISTRAR_DECLARES_WHAT_IT_WRITES():
    """Derived, not guessed: the registrar emits PARAMETERISED_BY and nothing else structural."""
    assert declared_edge_types("registrar") == frozenset({"PARAMETERISED_BY"})


def test_AN_UNDERIVED_SET_IS_NONE_AND_NOT_AN_EMPTY_SET():
    """R-012 ON A REGISTRY. `frozenset()` is a positive claim — "this interface writes no
    structural edges" — and it is false: answer_artifact_writer writes PRODUCED_BY, PRODUCED_FOR,
    DERIVED_FROM and CITES. `None` says nobody has derived it, which is the true state."""
    assert TRACE_WRITER_EDGE_TYPES is None, (
        "the trace writer's set became a concrete value — if it was DERIVED from the write "
        "census, good; if it was assembled by reading names, that is the guess the ruling forbids"
    )
    assert TRACE_WRITER_EDGE_TYPES != frozenset(), "None and empty must not compare equal here"


def test_ASKING_FOR_AN_UNDERIVED_SET_RAISES_RATHER_THAN_RETURNING_EMPTY():
    """THE ARM THAT MATTERS. A caller handed `frozenset()` cannot tell "writes nothing" from
    "nobody measured", and will report an unverified write path as clean — which is the exact
    failure the registry exists to prevent, reproduced inside the mechanism."""
    with pytest.raises(UndeclaredWriteInterface) as exc:
        declared_edge_types("trace_writer")
    msg = str(exc.value)
    assert "UNSET, not" in msg, "the refusal must distinguish unset from empty"
    assert "SKIP" in msg, "it must tell a checker what to do — skip, and report unverified"


def test_A_THIRD_WRITE_INTERFACE_IS_A_FINDING_NOT_A_REGISTRY_ENTRY():
    """ADR-0054 names exactly two doors. doc-tools' domain-plugin ingest is a third writer today,
    and the right response is a finding — adding it here would legitimise the write path the ADR
    says should not exist."""
    with pytest.raises(UndeclaredWriteInterface, match="not a declared write interface"):
        declared_edge_types("doc_tools_ingest")


def test_THE_REGISTRY_HOLDS_STRUCTURAL_TYPES_ONLY():
    """The registrar also writes one relationship per registered verb, typed by the verb's local
    name. Those cannot be declared as literals — the set is whatever the fleet registers — so a
    lower-case entry here means the dynamic write leaked into the structural registry, and a
    conformance seal would then red on every newly registered verb."""
    for t in REGISTRAR_EDGE_TYPES:
        assert t.isupper() or "_" in t, f"{t!r} is not a SCREAMING_CASE structural type"
        assert t == t.upper(), (
            f"{t!r} looks like a verb local name, not a structural edge type — the dynamic "
            f"per-verb write must stay out of this registry"
        )


def test_THE_REGISTRY_IS_REACHABLE_FROM_THE_PACKAGE_ROOT():
    """A conformance seal in another repo has to import this. A registry it cannot find is the
    cross-repo drift with an extra step."""
    import iagent_mesh

    for n in ("REGISTRAR_EDGE_TYPES", "declared_edge_types", "UndeclaredWriteInterface"):
        assert hasattr(iagent_mesh, n), f"{n} is not reachable from `import iagent_mesh`"

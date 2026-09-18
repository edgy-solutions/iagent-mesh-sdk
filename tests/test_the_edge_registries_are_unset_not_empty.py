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


def test_THE_TRACE_WRITER_IS_DECLARED_FROM_THE_CENSUS_NOT_SHIPPED_AS_UNSET():
    """It was `None` while the write census was outstanding. The census has landed and partitions
    all thirteen types 13/13 with no residue, so `None` here would now use an honest "we have not
    measured" to stand in for an answer that EXISTS — which is the opposite of what the
    unset/empty distinction is for, and a skip that hides a fact rather than a gap."""
    assert TRACE_WRITER_EDGE_TYPES is not None, (
        "the trace writer's set is unset while the census that derives it has landed"
    )
    assert declared_edge_types("trace_writer") == frozenset(
        {"CITES", "DERIVED_FROM", "PRODUCED_BY", "PRODUCED_FOR"}
    )


def test_THE_TWO_DOORS_DO_NOT_CLAIM_THE_EIGHT_THAT_BELONG_TO_A_THIRD():
    """THE FINDING, HELD OPEN BY AN ASSERTION. The census assigns eight types to doc-tools'
    domain-plugin ingest — a door ADR-0054 does not have. Declaring them under either real
    interface would make the partition add up while hiding the write path that should not exist,
    which is the catch-all the ruling forbade."""
    ingest = {"GOVERNED_BY", "HAS_CHILD", "REPLACED_BY", "REQUIRES_TOOL",
              "SUBJECT_TO", "HAS_PART", "REFERENCES", "INSTANCE_OF"}
    claimed = declared_edge_types("registrar") | declared_edge_types("trace_writer")
    assert not (claimed & ingest), (
        f"a declared door has absorbed {sorted(claimed & ingest)} — those belong to the ingest "
        f"writer in a sibling repo, and absorbing them retires the finding by bookkeeping"
    )
    assert len(claimed) + len(ingest) == 13, (
        "the partition no longer totals thirteen; the census and this registry disagree"
    )


def test_THE_UNSET_MECHANISM_STILL_WORKS_FOR_AN_INTERFACE_NOBODY_HAS_COUNTED(monkeypatch):
    """BOTH DOORS ARE MEASURED, so nothing real is unset — and the mechanism must still be sealed,
    because the state it represents will recur the next time a write interface appears before its
    census does. Exercised against a HYPOTHETICAL interface rather than by leaving a real one
    unset: a registry entry exists to be believed, and adding a fake door to keep a test honest
    would be the same bookkeeping this file refuses elsewhere.
    """
    import iagent_mesh.edge_types as et

    monkeypatch.setitem(et._INTERFACES, "some_future_door", None)
    with pytest.raises(UndeclaredWriteInterface) as exc:
        declared_edge_types("some_future_door")
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

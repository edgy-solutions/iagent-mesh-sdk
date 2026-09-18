"""WHICH STRUCTURAL EDGE TYPES EACH WRITE INTERFACE PROMISES TO EMIT.

Under ADR-0054 there are exactly two doors for graph edges — the registrar and the trace writer —
and each declares its own set here, beside the Protocol that promises the writes. The
implementations live in `invincible-agent`; the CONTRACT lives with the interface, which is the
same split `MeshVectors` uses: declaration where the contract is, conformance where the writes
happen.

── WHY THE DECLARATION IS HERE AND THE WRITES ARE NOT ──────────────────────────────────────
This SDK has no graph driver: nothing under `iagent_mesh/` touches neo4j or apoc. So a registry
here declares edges this package cannot emit, and that asymmetry is a real risk rather than a
tidy abstraction — **rename the type in the registrar and the SDK keeps declaring a type nobody
writes, while the census reports an undeclared one nobody declared.** Silent, cross-repo, and
invisible from either side alone.

That is why the declaration ships WITH a conformance seal in the repo that performs the writes,
asserting BOTH directions:

    written and NOT declared   -> a new edge type nobody registered
    declared and NEVER written -> the rename above, or a type that was removed

**Duplicate only where a wrong copy FAILS LOUDLY.** One copy in each repo is safe exactly because
the second arm makes disagreement red; without it this file is a second source of truth with no
referee.

── "NEVER WRITTEN" MEANS NO WRITER IN THE DECLARING INTERFACE ──────────────────────────────
NOT "no edges in the graph", and the difference is measured rather than hypothetical. Every type
this SDK does not declare still has live edges — INSTANCE_OF 21, HAS_CHILD 54, SUBJECT_TO 20,
GOVERNED_BY 7, REQUIRES_TOOL 2, HAS_PART 1, REPLACED_BY 1, REFERENCES 1 — written by doc-tools'
domain-plugin ingest, a THIRD writer outside ADR-0054's two doors. A live edge proves a writer
existed; it says nothing about which interface authored it. A conformance seal that read the graph
would red because another repo is the author, which is not the drift it exists to catch.

── DYNAMIC TYPES ARE OUT OF SCOPE BY CONSTRUCTION ──────────────────────────────────────────
The registrar also writes ONE relationship per registered verb, typed by the verb's own local
name (`costSupplierConcentration`, …). Those cannot be declared as literals — the set is whatever
the fleet registers — so this registry covers STRUCTURAL types only, the SCREAMING_CASE ones the
census walks. A seal must exclude the dynamic write or it reds on every new verb.
"""
from __future__ import annotations

from typing import Optional

__all__ = [
    "REGISTRAR_EDGE_TYPES",
    "TRACE_WRITER_EDGE_TYPES",
    "declared_edge_types",
    "UndeclaredWriteInterface",
]


class UndeclaredWriteInterface(LookupError):
    """A write interface whose edge-type set has not been derived yet. NOT the same as empty."""


#: The REGISTRAR's structural edge types. Derived from the writes, not guessed: the registrar
#: emits `PARAMETERISED_BY` in `sync_parameterised_by_edges` (the verb-subject-to-referent edge
#: carrying `verb_iri`, `_tool_urn`, `slot`, `required`) and nothing else structural.
REGISTRAR_EDGE_TYPES: frozenset = frozenset({"PARAMETERISED_BY"})

#: THE TRACE WRITER'S SET, DERIVED FROM THE FLEET-WIDE WRITE CENSUS — not read off the names.
#: Source: invincible-agent `docs/plans/fleet-write-census-store-classes.md`, which partitions all
#: THIRTEEN structural edge types 13/13 with no residue and nothing undecided:
#:
#:     4  artifact writer  CITES DERIVED_FROM PRODUCED_BY PRODUCED_FOR
#:                         src/iagent/answer_artifact_writer.py
#:     1  registrar        PARAMETERISED_BY
#:                         agent_fleet/mesh_registrar/v2_substrate.py
#:     8  doc-tools ingest GOVERNED_BY HAS_CHILD REPLACED_BY REQUIRES_TOOL SUBJECT_TO
#:                         HAS_PART REFERENCES INSTANCE_OF  —  A SIBLING REPO
#:
#: THE EIGHT ARE NOT DECLARED HERE AND THAT IS THE FINDING, NOT AN OMISSION. ADR-0054 names two
#: doors; doc-tools' domain-plugin ingest is a third, and giving it a registry entry would
#: legitimise the write path the ADR says should not exist. `declared_edge_types` refuses an
#: unknown interface by name for exactly that reason.
#:
#: `trace writer` is ADR-0054's term; the census calls the same component `the artifact writer`
#: after the module that implements it. One thing, two names — recorded so a reader comparing the
#: two documents does not go looking for a third writer.
TRACE_WRITER_EDGE_TYPES: Optional[frozenset] = frozenset(
    {"CITES", "DERIVED_FROM", "PRODUCED_BY", "PRODUCED_FOR"}
)

_INTERFACES = {
    "registrar": REGISTRAR_EDGE_TYPES,
    "trace_writer": TRACE_WRITER_EDGE_TYPES,
}


def declared_edge_types(interface: str) -> frozenset:
    """The structural edge types ``interface`` promises to write.

    Raises :class:`UndeclaredWriteInterface` when the set has not been derived, rather than
    returning an empty one — a caller that cannot tell "writes nothing" from "nobody has
    measured yet" will report an unverified path as clean.

    BOTH DOORS ARE MEASURED NOW, so nothing in this module is currently unset. The mechanism
    stays because the state it represents is real and will recur: **it is for the NEXT interface
    nobody has counted, not for one whose census has landed.** Shipping a measured set as `None`
    would use an honest "we do not know" to stand in for an answer that exists — the opposite of
    what the distinction is for, and a skip that hides a fact rather than a gap.
    """
    if interface not in _INTERFACES:
        raise UndeclaredWriteInterface(
            f"{interface!r} is not a declared write interface. ADR-0054 names exactly two: "
            f"{sorted(_INTERFACES)}. A third writer is a finding, not a registry entry — "
            f"doc-tools' domain-plugin ingest is one today."
        )
    declared = _INTERFACES[interface]
    if declared is None:
        raise UndeclaredWriteInterface(
            f"the edge-type set for {interface!r} has NOT been derived yet — this is UNSET, not "
            f"empty, and the difference is the whole point: empty would claim it writes nothing. "
            f"Membership comes from the fleet-wide write census. Until then a conformance check "
            f"must SKIP this interface and report it as unverified, never as conforming."
        )
    return declared

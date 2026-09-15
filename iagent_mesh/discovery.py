"""Discovery by DECLARATION, not by import: an engine asks for an interface and gets one.

An engine that writes ``from some_neo4j_thing import GraphReader`` has chosen an implementation
at authoring time and pinned a driver into its own dependency tree. So it does not import one —
it asks the SDK, and the SDK resolves whatever the deployment installed through an entry point
the implementing package declares:

    [project.entry-points."iagent_mesh.graph"]
    neo4j = "my_pkg.graph:Neo4jMeshGraph"

── TWO FOUND IS A REFUSAL, NOT A PICK ──────────────────────────────────────────────────────
**One implementation per interface per deployment.** Two installed is ambiguity, and resolving
ambiguity silently is how a deployment ends up reading from one store and believing it read from
another. This is the same rule as two in-domain providers claiming a noun: the mesh refuses and
names both rather than choosing.

**There is deliberately no override to break the tie.** An override would BE a pick, and a pick
is the thing being refused — a config key selecting between two installed implementations moves
the ambiguity from the package set into a values file where it is harder to see, not easier. **A
deployment chooses by installing one.**

── WHY THE REFUSAL NAMES BOTH, AND SAYS WHERE THEY CAME FROM ───────────────────────────────
An "ambiguous implementation" error that does not name the candidates sends an operator to read
the whole dependency tree. The distribution that declared each entry point is the actionable
fact — it says which package to remove.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "GROUPS",
    "NoImplementation",
    "AmbiguousImplementation",
    "resolve",
    "available",
]

#: The entry-point group per interface. Named for the INTERFACE, never for an implementation —
#: ``iagent_mesh.graph``, not ``iagent_mesh.neo4j`` — so swapping the store behind it is a
#: packaging change rather than a rename every consumer sees. R-038 applied to a group name.
GROUPS = {
    "MeshGraph": "iagent_mesh.graph",
    "MeshOntology": "iagent_mesh.ontology",
    "MeshVectors": "iagent_mesh.vectors",
}


class NoImplementation(LookupError):
    """Nothing declared the group. Names the group and what a package must declare to fill it."""


class AmbiguousImplementation(LookupError):
    """Two or more implementations declared one group. NEVER resolved by picking."""


def _entry_points(group: str) -> list:
    from importlib.metadata import entry_points  # stdlib; no driver, no third party

    return list(entry_points(group=group))


def available(interface: str) -> list[tuple[str, str]]:
    """``(name, value)`` for everything declaring this interface's group — for diagnostics.

    Deliberately does NOT resolve or load anything: an operator asking "what is installed" must
    not trigger the import side effects of the thing they are investigating.
    """
    group = GROUPS.get(interface)
    if group is None:
        raise NoImplementation(
            f"{interface!r} is not a mesh interface. Known: {sorted(GROUPS)}"
        )
    return sorted((ep.name, ep.value) for ep in _entry_points(group))


def resolve(interface: str) -> Any:
    """Load the ONE implementation of ``interface`` this deployment installed.

    Raises :class:`NoImplementation` for zero and :class:`AmbiguousImplementation` for two or
    more. It never picks, and there is no argument that would make it pick.
    """
    group = GROUPS.get(interface)
    if group is None:
        raise NoImplementation(
            f"{interface!r} is not a mesh interface. Known: {sorted(GROUPS)}"
        )

    eps = _entry_points(group)

    if not eps:
        raise NoImplementation(
            f"no implementation of {interface} is installed — nothing declares the entry-point "
            f"group {group!r}. An implementing package declares it as:\n"
            f'    [project.entry-points."{group}"]\n'
            f'    <name> = "<module>:<class>"\n'
            f"This is an ABSENCE, not a failure: the deployment installed no implementation, "
            f"which is a different problem from one that is installed and broken."
        )

    if len(eps) > 1:
        found = "\n".join(
            f"    {ep.name} = {ep.value}   (from {getattr(getattr(ep, 'dist', None), 'name', 'unknown distribution')})"
            for ep in sorted(eps, key=lambda e: e.name)
        )
        raise AmbiguousImplementation(
            f"{len(eps)} implementations of {interface} are installed and the mesh does not "
            f"choose between them:\n{found}\n"
            f"One implementation per interface per deployment. Resolving this by picking would "
            f"move the ambiguity into a config file where it is harder to see, not easier — "
            f"uninstall the one this deployment does not want."
        )

    return eps[0].load()

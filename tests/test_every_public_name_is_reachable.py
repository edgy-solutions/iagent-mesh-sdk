"""A module's `__all__` is a promise; the package root is where it is kept — or declined, in the open.

THE DEFECT THIS IS DERIVED FROM, and it has happened twice in this SDK's history:
`v0.7.0` was a release whose ENTIRE POINT was sharing `enforce_refusal`, and the package did not
re-export it. `v0.7.1` fixed that, and a derived coverage check then found `SLOT_KINDS` unexported
since `v0.5.0`. Both are the same shape: a name public in its module, invisible from
`import iagent_mesh`, with nothing asking.

A hand-written list of expected exports cannot catch it — the name missing from the package is
missing from the list for the same reason. So this is DERIVED: every module's `__all__` is read,
and every module is classified as exported or declined WITH A REASON. A new module with an
`__all__` and no classification fails, which is the only way this survives contact with growth.

── WHY NOT SIMPLY RE-EXPORT EVERYTHING ─────────────────────────────────────────────────────
Because four names are exported by two modules each, and a blanket re-export would let one
silently shadow the other:

    compose         graph_manifest.py  task_kinds.py
    json_schema     graph_manifest.py  task_kinds.py
    validate_dir    graph_manifest.py  task_kinds.py
    resolve         discovery.py       task_kinds.py

`compose` IS THE ONE WITH BOTH CONSUMERS ALREADY SHIPPED, which makes it the better example:

    graph_manifest.compose   composes a ratified GRAPH ROW with its overlays
                             consumed by agent_fleet/graph_host/main.py:43-46
    task_kinds.compose       composes a TASK KIND
                             consumed by src/iagent/human_tasks.py:536

Two live callers, one name, unrelated jobs. `resolve` is the same shape — `discovery.resolve`
loads an interface implementation, `task_kinds.resolve` resolves a task kind. A root exporting
either pair would answer one caller's question with the other's function, and nothing would
report it. So the surface is chosen per module, and the modules left out say why here rather than
by omission.

── WHO ACTUALLY CONSUMES THE SURFACE THIS FILE GUARDS: NOBODY IN THE FLEET ─────────────────
Measured across invincible-agent: `from iagent_mesh import ...` has ZERO occurrences. Every
consumer there imports by submodule path — `from iagent_mesh.graph_manifest import compose`, and
so on. The SDK's own tests use the root; the fleet never does.

**A READER WHO GREPS FOR ROOT IMPORTS, FINDS NONE, AND CONCLUDES THIS SEAL PROTECTS NOTHING HAS
THE FACT RIGHT AND THE LESSON BACKWARDS.** A surface with no local consumer is exactly where a
seal earns most: breakage there trips nobody in this repo, so nothing reports it, and the only
party who feels it is a team following the documented import from outside. A surface with local
consumers defends itself — someone's build breaks. This one has no such defence, which is the
argument FOR the arms rather than against them.

THE ORIGINATING STORY, NARROWED BY THE LANE THAT TOLD IT, because it travelled oversized:
`enforce_refusal` missing from the root in v0.7.0 BROKE NO IN-REPO CONSUMER — engine-lg imported
it from `graph_manifest` then and still does. What it broke was the DOCUMENTED SURFACE and route
C. Still a defect, still the reason to derive this seal; just not "the function the release
existed to share was unavailable", which is what the shorter telling implies. Recorded at its
true size so nobody inflates it back.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import iagent_mesh

_PKG = pathlib.Path(iagent_mesh.__file__).parent

#: Modules whose public surface IS the package's surface. Every `__all__` name must be reachable
#: from `import iagent_mesh`.
_EXPORTED = {
    "conformance", "edge_types", "enumeration", "graph_manifest",
    "interfaces", "results", "rows", "shapes",
}

#: Modules deliberately NOT re-exported, each with the reason. An omission with a reason is a
#: decision; an omission without one is the v0.7.0 defect waiting to recur.
_DECLINED = {
    "core": "the ENGINE HOST — needs the [server] extra, so importing it at the root would put "
            "fastapi back in the path of `import iagent_mesh` and undo the 0.9.1 guard",
    "transport_auth": "its CLIENT half (CallerIdentity, current_caller) IS exported by name; the "
                      "rest is the server dependency factory",
    "declarations": "not yet part of the promised surface — exported by name when a second "
                    "consumer needs it, which is this repo's extract-at-the-second-consumer rule",
    "discovery": "exports `resolve`, which collides with task_kinds.resolve; the root cannot "
                 "carry both and choosing silently is the shadowing this file exists to prevent",
    "task_kinds": "exports `resolve`, `compose`, `json_schema` and `validate_dir`, all of which "
                  "collide with another module. Needs a naming decision before a root export",
    "client": "no __all__ — MeshClient and MeshResponse are exported by name",
    "models": "tool input/output base classes, consumed by subclassing from the module",
}

#: Names public in an EXPORTED module and deliberately absent from the root, with the reason.
_EXEMPT = {
    ("interfaces", "marker_is_stale"):
        "the deprecated alias for marker_predates_collection. Promoting a deprecated name into a "
        "NEW namespace extends its life rather than ending it — it stays importable from "
        "iagent_mesh.interfaces for the consumers the interval owes, and no wider",
}


def _module_all(name: str) -> set:
    tree = ast.parse((_PKG / f"{name}.py").read_text(encoding="utf-8"))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in n.targets):
            try:
                return set(ast.literal_eval(n.value))
            except Exception:
                return set()
    return set()


def _modules_with_all() -> set:
    found = set()
    for f in sorted(_PKG.glob("*.py")):
        if f.name == "__init__.py":
            continue
        if _module_all(f.stem):
            found.add(f.stem)
    return found


# ── the derived coverage check ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("module", sorted(_EXPORTED))
def test_EVERY_PUBLIC_NAME_OF_AN_EXPORTED_MODULE_IS_REACHABLE(module):
    """THE ARM v0.7.0 NEEDED. A release whose point is sharing a name, that does not re-export
    it, ships its own purpose broken — and the pin moves before anyone notices."""
    declared = _module_all(module)
    assert declared, f"{module} is listed as exported but declares no __all__"
    missing = sorted(
        n for n in declared
        if not hasattr(iagent_mesh, n) and (module, n) not in _EXEMPT
    )
    assert not missing, (
        f"{module} declares {missing} public and `import iagent_mesh` cannot reach them. Either "
        f"re-export them, or add each to _EXEMPT with the reason it is withheld."
    )


def test_EVERY_MODULE_WITH_AN_ALL_IS_CLASSIFIED():
    """THE ARM THAT SURVIVES GROWTH. A new module added with an `__all__` and no classification
    is exactly how the first two escapes happened — nobody was asked. This forces the question at
    the moment the module appears rather than at the release that needed it."""
    classified = _EXPORTED | set(_DECLINED)
    unclassified = sorted(_modules_with_all() - classified)
    assert not unclassified, (
        f"{unclassified} declare an __all__ and are neither exported nor declined. Add each to "
        f"_EXPORTED (and re-export its names) or to _DECLINED with the reason."
    )


def test_EVERY_DECLINED_MODULE_AND_EXEMPT_NAME_CARRIES_A_REASON():
    """An omission with a reason is a decision; an omission without one is the defect waiting to
    recur. A blank reason reads as considered while recording nothing."""
    for mod, why in _DECLINED.items():
        assert why and why.strip(), f"{mod} is declined with no reason"
    for (mod, name), why in _EXEMPT.items():
        assert why and why.strip(), f"{mod}.{name} is exempt with no reason"


def test_A_DECLINED_MODULE_IS_NOT_ALSO_EXPORTED():
    """Both at once means one of the two is a lie, and the permissive reading wins silently —
    the partition rule, applied to a package surface."""
    both = _EXPORTED & set(_DECLINED)
    assert not both, f"{sorted(both)} are both exported and declined"


# ── the collision that makes a blanket re-export impossible ──────────────────────────────

def test_THE_ROOT_DOES_NOT_CARRY_A_COLLIDING_NAME_FROM_BOTH_SIDES():
    """TWO INSTANCES IN THE WILD, not one hypothetical.

    `compose` is the one with both consumers already shipped — `graph_manifest.compose` composes a
    ratified graph row (graph_host/main.py:43-46), `task_kinds.compose` composes a task kind
    (human_tasks.py:536). `resolve` is the same shape: `discovery.resolve` loads an interface
    implementation, `task_kinds.resolve` resolves a task kind.

    A root exporting either pair answers one caller's question with the other's function, and
    nothing reports it. A rule with two instances found in the wild reads differently from one
    with a single example — the next person to propose a blanket sweep will check this comment
    before they check the code."""
    import collections

    seen = collections.defaultdict(list)
    for module in _modules_with_all():
        for n in _module_all(module):
            seen[n].append(module)
    colliding = {n: mods for n, mods in seen.items() if len(mods) > 1}
    assert colliding, (
        "no collisions found — if they were resolved by renaming, this arm and the _DECLINED "
        "reasons that cite them are stale and should be re-derived"
    )
    for name, mods in colliding.items():
        exported_sides = [m for m in mods if m in _EXPORTED]
        assert len(exported_sides) <= 1, (
            f"{name!r} is exported by {exported_sides}; the root can only mean one of them and "
            f"the other is shadowed silently"
        )


# ── the move this file shipped with ──────────────────────────────────────────────────────

def test_THE_LEDGER_ROW_VOCABULARY_ARRIVED_WHOLE():
    """ADR-0046's contract, moved from agent_fleet/graph_host so route C inherits it. Asserted
    against the module's own __all__ rather than a transcribed list — a hand-copied expectation
    would be missing the same name the export is."""
    from iagent_mesh import rows

    assert len(rows.__all__) == 11
    for n in rows.__all__:
        assert hasattr(iagent_mesh, n), f"rows.{n} did not survive the move to the root"


def test_THE_PRODUCER_AND_CONSUMER_OF_holes_NOW_LIVE_TOGETHER():
    """The reason the move is more than relocation. `holes_from` is the ONLY place `holes` is
    built and `enforce_refusal` refuses on it — they were in different repos, which is the
    cross-repo split the edge-type registry needed a conformance seal to survive. Here it is
    removed rather than refereed."""
    assert hasattr(iagent_mesh, "holes_from")
    assert hasattr(iagent_mesh, "enforce_refusal")
    import inspect

    assert "holes" in inspect.getsource(iagent_mesh.enforce_refusal), (
        "enforce_refusal no longer reads `holes` — if the contract moved, holes_from's claim to "
        "be its only producer needs re-deriving"
    )

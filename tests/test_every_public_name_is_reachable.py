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
report it.

── 0.9.4: THE CHOICE MOVED FROM THE MODULE TO THE NAME ─────────────────────────────────────
Until 0.9.4 the answer was to decline the whole module, which kept the four names off the root
and SIXTEEN OTHERS with them — names that collided with nothing and were absent for no reason
anyone had stated. `declarations`, `discovery` and `task_kinds` are exported now; the four
colliding names are withheld ONE AT A TIME in `_EXEMPT`, each with its own reason, because the
two cases are not the same failure. `resolve` is absent on both sides, so a caller gets an
AttributeError. `compose`, `json_schema` and `validate_dir` are PRESENT at the root as
graph_manifest's, so on the task_kinds side the caller gets a working function that does
another job — which is why the coverage arm below now compares IDENTITY and not `hasattr`.

MEASURED, because "the old arms were weaker" is the kind of claim this file exists to refuse:
with the three modules promoted and `task_kinds.compose` re-exported over graph_manifest's, the
old `hasattr` arm passed all eleven modules, and the old collision arm — which read _EXPORTED
membership rather than the root — failed IDENTICALLY on the shadowed tree and on the correct
one. One arm blind to the defect, one arm red either way. Neither carried information.

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
import importlib
import pathlib

import pytest

import iagent_mesh

_PKG = pathlib.Path(iagent_mesh.__file__).parent

#: Modules whose public surface IS the package's surface. Every `__all__` name must be reachable
#: from `import iagent_mesh`.
_EXPORTED = {
    "conformance", "declarations", "discovery", "edge_types", "enumeration",
    "graph_manifest", "interfaces", "results", "rows", "shapes", "task_kinds",
}

#: Modules deliberately NOT re-exported, each with the reason. An omission with a reason is a
#: decision; an omission without one is the v0.7.0 defect waiting to recur.
_DECLINED = {
    "core": "the ENGINE HOST — needs the [server] extra, so importing it at the root would put "
            "fastapi back in the path of `import iagent_mesh` and undo the 0.9.1 guard",
    "transport_auth": "its CLIENT half (CallerIdentity, current_caller) IS exported by name; the "
                      "rest is the server dependency factory",
    "client": "no __all__ — MeshClient and MeshResponse are exported by name",
    "models": "tool input/output base classes, consumed by subclassing from the module",
}

#: Names public in an EXPORTED module and deliberately absent from the root, with the reason.
#: RULED 2026-09-19 (the architect): the four names exported by two modules each are NEVER
#: exported bare at the root. They stay module-qualified, and the decision is recorded here —
#: per NAME and per SIDE — rather than by declining a whole module, because declining the module
#: also withheld sixteen names that never collided with anything and had no reason to be absent.
#:
#: WHY THE TWO REASONS ARE NOT INTERCHANGEABLE, and this is the part a reader needs:
#: `resolve` is absent from the root on BOTH sides, so a caller writing `iagent_mesh.resolve`
#: gets an AttributeError and goes looking. `compose`, `json_schema` and `validate_dir` ARE at
#: the root and mean GRAPH_MANIFEST'S — shipped since 0.7.x, consumed by
#: agent_fleet/graph_host/main.py:43-46. So on the task_kinds side the failure mode is worse
#: than absence: the caller gets a function, of the right name, that does another job. That is
#: the shadowing this file exists to prevent, and it is why the coverage arm below compares
#: IDENTITY rather than asking `hasattr` — under `hasattr` these three read as reachable.
_EXEMPT = {
    ("discovery", "resolve"):
        "collides with task_kinds.resolve — `discovery.resolve` loads an interface "
        "implementation, `task_kinds.resolve` resolves a task kind. RULED: neither comes to the "
        "root, so the name is absent on both sides and a caller is told so by AttributeError",
    ("task_kinds", "resolve"):
        "collides with discovery.resolve. RULED: neither side comes to the root",
    ("task_kinds", "compose"):
        "collides with graph_manifest.compose, which IS at the root and has shipped since "
        "0.7.x (agent_fleet/graph_host/main.py:43-46). RULED: the task_kinds one stays "
        "module-qualified. Withdrawing graph_manifest's so the root carries neither would be a "
        "SUBTRACTION from a published surface, which the same ruling forbids in its last line",
    ("task_kinds", "json_schema"):
        "collides with graph_manifest.json_schema, which is at the root. Same ruling, same "
        "reason as `compose`",
    ("task_kinds", "validate_dir"):
        "collides with graph_manifest.validate_dir, which is at the root and is what the policy "
        "repo's PR gate imports. Same ruling, same reason as `compose`",
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
    it, ships its own purpose broken — and the pin moves before anyone notices.

    IT ASKS FOR IDENTITY, NOT `hasattr`, AND THAT IS THE 0.9.4 CHANGE. Three modules joined
    _EXPORTED in 0.9.4, and one of them — `task_kinds` — declares `compose`, `json_schema` and
    `validate_dir`, all three of which ALREADY resolve at the root as graph_manifest's
    functions. `hasattr(iagent_mesh, "compose")` is True, so under the old form this arm would
    have reported task_kinds' public surface as fully reachable while the root handed every
    caller another module's function.

    A GREEN OVER THE WRONG OBJECT IS INDISTINGUISHABLE FROM A GREEN OVER THE RIGHT ONE, so the
    two failures are separated and named: a name the root cannot reach is MISSING, and a name
    the root reaches as somebody else's object is SHADOWED. The second is the one that was
    invisible, and it is the whole reason the four colliding names needed a ruling rather than
    a re-export."""
    declared = _module_all(module)
    assert declared, f"{module} is listed as exported but declares no __all__"
    mod = importlib.import_module(f"iagent_mesh.{module}")
    missing, shadowed = [], []
    for n in sorted(declared):
        if (module, n) in _EXEMPT:
            continue
        if not hasattr(iagent_mesh, n):
            missing.append(n)
        elif getattr(iagent_mesh, n) is not getattr(mod, n):
            shadowed.append(n)
    assert not missing, (
        f"{module} declares {missing} public and `import iagent_mesh` cannot reach them. Either "
        f"re-export them, or add each to _EXEMPT with the reason it is withheld."
    )
    assert not shadowed, (
        f"the root carries {shadowed} but NOT {module}'s — a caller who reads {module}'s "
        f"__all__ and imports that name from the root gets another module's object. Either the "
        f"root should carry this module's, or add each to _EXEMPT saying which side the root "
        f"means and why."
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


def test_AN_EXEMPT_NAME_IS_ACTUALLY_ABSENT_FROM_THE_ROOT():
    """AN EXEMPTION IS A CLAIM, SO CHECK IT. `_EXEMPT` says "this module's name is deliberately
    not at the root"; the coverage arm then SKIPS that pair. So the table is the one place in
    this file where writing a sentence makes an arm stop looking — and if the name later
    arrives at the root anyway, every reason recorded here becomes false with nothing red.

    THE CONCRETE ONE: `("discovery", "resolve")` says "neither side comes to the root". Add
    `from .discovery import resolve` to the package root and, without this arm, the suite stays
    GREEN — the coverage arm skips the exempt pair and the collision arm is satisfied because
    the OTHER side is exempt too. The ruling would be broken, the reason in the table would be
    a lie, and the only evidence would be the sentence itself."""
    for (module, name), why in _EXEMPT.items():
        mod = importlib.import_module(f"iagent_mesh.{module}")
        if not hasattr(iagent_mesh, name):
            continue
        assert getattr(iagent_mesh, name) is not getattr(mod, name), (
            f"({module!r}, {name!r}) is in _EXEMPT — recorded as withheld from the root, "
            f"because: {why} — but `iagent_mesh.{name}` IS {module}.{name}. The exemption is "
            f"now false. Either drop the entry and let the coverage arm cover the name, or "
            f"take the export back out."
        )


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
        "no collisions found — if they were resolved by renaming, this arm and the _EXEMPT "
        "reasons that cite them are stale and should be re-derived"
    )

    # ── MEASURED AT THE ROOT, NOT FROM _EXPORTED MEMBERSHIP ─────────────────────────────────
    # Until 0.9.4 this arm asked which colliding modules were in _EXPORTED. That was a PROXY,
    # and it held only because a declined module put nothing at the root — so the proxy and the
    # fact moved together and nothing distinguished them. 0.9.4 promoted `task_kinds` WITH its
    # four colliding names withheld, and the proxy stopped tracking the fact in both directions
    # at once: it would now call a correct root a shadowing (the module is exported), and it
    # would still have nothing to say about WHICH object the root actually hands back.
    # The fact is about what `iagent_mesh.<name>` IS. Ask that.
    for name, mods in sorted(colliding.items()):
        owners = []
        for m in mods:
            mod = importlib.import_module(f"iagent_mesh.{m}")
            if hasattr(iagent_mesh, name) and getattr(iagent_mesh, name) is getattr(mod, name):
                owners.append(m)
        assert len(owners) <= 1, (
            f"{name!r} at the root is the same object as {owners}'s on more than one side — "
            f"the collision is not what this arm believes it is"
        )
        if hasattr(iagent_mesh, name):
            assert owners, (
                f"the root carries {name!r} and it is NOT the object of any of {sorted(mods)}, "
                f"which all export that name. Something else bound it, and the collision this "
                f"arm reasons about is no longer the one in the code"
            )
        for m in sorted(set(mods) - set(owners)):
            assert (m, name) in _EXEMPT, (
                f"{m}.{name} is not what the root means by {name!r} — the root means "
                f"{owners[0] if owners else 'nothing'} — and ({m!r}, {name!r}) is not in "
                f"_EXEMPT. An omission with a reason is a decision; this one records nothing."
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

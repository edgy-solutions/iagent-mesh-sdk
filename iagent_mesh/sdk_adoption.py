# SDK-adoption drift check — "does ANOTHER repo hand-copy a type this SDK already exports,
# instead of importing it?" This is a different question from `iagent_mesh/conformance.py`'s
# (does a given MeshGraph/MeshVectors/... IMPLEMENTATION behave per its interface contract?).
# Same English word "conformance" would fit either, which is exactly why this lives in its own
# module — see the 2026-10-17 census (docs/measurements/2026-10-17-sdk-adoption-census.md):
# `ResolveInstanceRequest` was hand-copied in 7 of 17 fleet engines instead of imported from
# here. That census was a one-off, manual read of each engine's source tree. This module is the
# reusable, importable version of the same check, meant to be called from ANOTHER repo's own
# test suite / CI — `from iagent_mesh.sdk_adoption import assert_no_hand_copied_types`.
#
# This module makes ZERO assumptions about the caller's package layout: `package_root` names a
# directory that, at call time, belongs to some OTHER repo's source tree (an engine in the
# fleet), not this one. It is parsed with `ast`, never imported/exec'd — the target files may
# belong to a package that isn't installed in this process, may not even be valid to import here
# (missing deps, different Python version constructs), and executing arbitrary third-party source
# as a side effect of running a CI check would itself be the kind of silent, assumption-laden
# behavior this SDK's conventions reject.
from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path

import iagent_mesh


def _sdk_exported_names() -> frozenset[str]:
    """The set of names `iagent_mesh` exports at its root.

    Prefers `iagent_mesh.__all__` (authoritative — this is the module's own declared public
    surface) over `dir(iagent_mesh)`, which would also pick up dunders and anything merely
    reachable (e.g. submodules bound as attributes) rather than deliberately exported.
    """
    all_names = getattr(iagent_mesh, "__all__", None)
    if all_names is not None:
        return frozenset(all_names)
    return frozenset(
        name for name in dir(iagent_mesh) if not name.startswith("_")
    )


def _canonical_definition_files() -> dict[str, Path]:
    """Where each EXPORTED CLASS is actually defined, inside this SDK's own source.

    A hand-copy is a class redefined somewhere OTHER than the file that genuinely defines it.
    Without this, running the check against the SDK's own `iagent_mesh/` tree would flag every
    export's real definition as a "hand-copy of itself" — the SDK obviously defines
    `ResolveInstanceRequest` etc. SOMEWHERE; that is not an adoption-drift finding. Only a
    *second* definition, at a file other than this canonical one, is.

    Keyed by class name; a name whose exported object isn't a class (a function, a constant) has
    no entry, since only `class` statements are ever flagged by `find_hand_copied_types`.
    """
    canonical: dict[str, Path] = {}
    for name in _sdk_exported_names():
        obj = getattr(iagent_mesh, name, None)
        if not inspect.isclass(obj):
            continue
        try:
            source_file = inspect.getsourcefile(obj)
        except TypeError:
            source_file = None
        if source_file is not None:
            canonical[name] = Path(source_file).resolve()
    return canonical


# Directory names never worth descending into when walking a THIRD-PARTY package root — build
# output, caches and VCS metadata cannot contain source a conformance check should flag.
_SKIP_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
    }
)


@dataclass(frozen=True)
class HandCopyFinding:
    """One local class definition whose name collides with an `iagent_mesh` export."""

    path: Path
    line: int
    class_name: str


def _iter_py_files(package_root: Path):
    for path in sorted(package_root.rglob("*.py")):
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(package_root).parts[:-1]):
            continue
        yield path


def find_hand_copied_types(package_root: "Path | str") -> list[HandCopyFinding]:
    """Scan `package_root` (some OTHER repo's source tree) for local classes that hand-copy a
    type this SDK already exports, instead of importing it.

    Only a top-level `class Foo:` statement whose name matches an `iagent_mesh` export is a
    finding. A file that imports the name (`from iagent_mesh import ResolveInstanceRequest`)
    and never locally redefines it is not flagged — importing it is exactly the fix this check
    exists to encourage.

    Files are parsed with `ast`, never imported or executed: `package_root` may belong to a
    package not installed in this process.
    """
    root = Path(package_root)
    exported = _sdk_exported_names()
    canonical = _canonical_definition_files()
    findings: list[HandCopyFinding] = []

    for py_file in _iter_py_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        resolved_file = py_file.resolve()
        for node in tree.body:
            if not (isinstance(node, ast.ClassDef) and node.name in exported):
                continue
            # The SDK's own genuine definition of one of its exports is not a hand-copy of
            # itself — only a definition somewhere ELSE, with the same name, is.
            if canonical.get(node.name) == resolved_file:
                continue
            findings.append(
                HandCopyFinding(path=py_file, line=node.lineno, class_name=node.name)
            )

    return findings


def assert_no_hand_copied_types(package_root: "Path | str") -> None:
    """Raise `AssertionError`, listing every finding, if `package_root` hand-copies any
    `iagent_mesh`-exported type instead of importing it. Returns `None` (no finding) otherwise.

    The one-liner an external repo's own `test_sdk_conformance.py` (or equivalent) calls.
    """
    findings = find_hand_copied_types(package_root)
    if findings:
        lines = [
            f"{finding.path}:{finding.line}: class {finding.class_name!r} hand-copies an "
            f"iagent_mesh export — import it from iagent_mesh instead of redefining it locally"
            for finding in findings
        ]
        raise AssertionError(
            f"{len(findings)} hand-copied iagent_mesh type(s) found:\n" + "\n".join(lines)
        )

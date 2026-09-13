"""The shared composer, exercised by a family that is NOT task kinds.

The ADR-0039 amendment refuses a fourth composer by name. A shared composer only earns that
refusal if a second family can actually use it, so every arm below drives it with a different
key field, a different builder and a different error subclass — and NONE of them import
``task_kinds``. If this file needed that import, the mechanism would not be shared, it would be
borrowed.

The task-kind suite is the other half of the proof: all nineteen of its arms pass unchanged
against the delegating implementation, so the extraction moved no behaviour.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict

from iagent_mesh.declarations import (
    DeclarationError,
    compose_rows,
    load_rows,
    read_rows,
)


class DecisionError(DeclarationError):
    """A family subclass, so a caller can catch this family and not every family."""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision_id: str
    outcome: str


def _build(raw: dict) -> Decision:
    return Decision(**raw)


_OPTS = dict(key_field="decision_id", builder=_build, label="decision", error=DecisionError)


def _write(d: Path, name: str, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(row), encoding="utf-8")


SEED_ROW = {"decision_id": "d_seed", "outcome": "ratified"}

_REPO = Path(__file__).resolve().parents[1]


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an import in a file, read from the SYNTAX TREE.

    Not a substring scan: `task_kinds` appears in this file's own prose, and a grep-shaped
    check would fail on a docstring that merely mentions it — a seal that cannot be written
    about is one people route around.

    MUST INCLUDE THE IMPORTED NAMES, NOT JUST THE MODULE. ``from iagent_mesh import task_kinds``
    puts ``iagent_mesh`` in ``node.module`` and ``task_kinds`` in ``node.names`` — so a check
    reading only the module misses the most natural way to write the very import it forbids.
    Found by running that exact mutation against the first version of this helper, which PASSED.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
            # `from <pkg> import <name>` — the NAME is the module for a submodule import, and
            # is the only place it appears.
            out.update(a.name for a in node.names)
    return out


# ── the extraction is real, not renamed ──────────────────────────────────────────────────

def test_the_shared_composer_does_not_import_its_FIRST_CALLER():
    """THE BOUNDARY, ASSERTED. A mechanism that imports the family it was extracted from was
    renamed, not extracted — and the dependency would be real however the module is named.

    HOW IT ACTUALLY FAILS, measured: a MODULE-LEVEL import here is circular (task_kinds already
    imports this module), so pytest reports a COLLECTION ERROR before this arm runs. Still red,
    still loud, but the diagnostic is "circular import" rather than this assertion's message —
    worth knowing so nobody chases the wrong thing. The arm earns its keep on the case that is
    NOT circular: a lazy import inside a function body, which `ast.walk` reaches and which would
    otherwise import cleanly and silently reinstate the dependency.
    """
    imported = _imported_modules(_REPO / "iagent_mesh" / "declarations.py")
    offenders = {m for m in imported if "task_kind" in m}
    assert not offenders, (
        f"iagent_mesh/declarations.py imports {sorted(offenders)} — the shared composer must "
        f"not depend on the first family that needed it"
    )


def test_THIS_SUITE_IMPORTS_TASK_KINDS_NOWHERE():
    """The cheapest seal standing between a real extraction and a convincing one.

    If exercising the composer ever requires `task_kinds`, the mechanism is BORROWED rather
    than shared, and every arm in this file is really another task-kind test wearing a
    different name. Asserted rather than merely true, because the day someone reaches for a
    TaskKind here as a convenient builder is the day it stops being true silently.
    """
    imported = _imported_modules(Path(__file__))
    offenders = {m for m in imported if "task_kind" in m}
    assert not offenders, (
        f"this suite imports {sorted(offenders)} — exercise the composer with a family of its "
        f"own, or the extraction was a rename"
    )


# ── the positive control ─────────────────────────────────────────────────────────────────

def test_a_second_family_composes_at_all(tmp_path):
    """THE CONTROL, and the whole justification for the module. Every refusal below would pass
    against a composer that raised on everything."""
    _write(tmp_path, "a.yaml", SEED_ROW)
    rows = load_rows(tmp_path, **_OPTS)
    assert [r.decision_id for r in rows] == ["d_seed"]
    assert isinstance(rows[0], Decision)


# ── composition proper ───────────────────────────────────────────────────────────────────

def test_the_overlay_branch_actually_RAN(tmp_path):
    """Composing the SEED ALONE must not yield the overlay row — otherwise a green forward is
    consistent with the composer never having read the overlay at all."""
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", SEED_ROW)
    _write(overlay, "b.yaml", {"decision_id": "d_local", "outcome": "deferred"})

    seed_only = {r.decision_id for r in compose_rows(seed, **_OPTS)}
    assert seed_only == {"d_seed"}, "the overlay row appeared without an overlay"

    composed = {r.decision_id for r in compose_rows(seed, [overlay], **_OPTS)}
    assert composed == {"d_seed", "d_local"}


def test_an_overlay_row_fully_replaces_by_key(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", SEED_ROW)
    _write(overlay, "a.yaml", {"decision_id": "d_seed", "outcome": "superseded"})
    rows = compose_rows(seed, [overlay], **_OPTS)
    assert [(r.decision_id, r.outcome) for r in rows] == [("d_seed", "superseded")]


def test_a_row_the_overlay_never_mentions_comes_through_untouched(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", SEED_ROW)
    _write(seed, "b.yaml", {"decision_id": "d_other", "outcome": "ratified"})
    _write(overlay, "a.yaml", {"decision_id": "d_seed", "outcome": "superseded"})
    rows = {r.decision_id: r.outcome for r in compose_rows(seed, [overlay], **_OPTS)}
    assert rows["d_other"] == "ratified"


# ── the refusals, each with the family's own error type ──────────────────────────────────

def test_a_tombstone_for_an_unseeded_key_raises(tmp_path):
    """THE CHEAPEST PROOF THE COMPOSITION BRANCH RAN, rather than the seed being read twice."""
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", SEED_ROW)
    _write(overlay, "gone.yaml", {"decision_id": "never_shipped", "deleted": True})
    with pytest.raises(DecisionError, match="does not ship"):
        compose_rows(seed, [overlay], **_OPTS)


def test_a_tombstone_composes_away_a_row_the_seed_DOES_ship(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "a.yaml", SEED_ROW)
    _write(overlay, "gone.yaml", {"decision_id": "d_seed", "deleted": True})
    assert compose_rows(seed, [overlay], **_OPTS) == []


def test_a_tombstone_outside_an_overlay_raises(tmp_path):
    _write(tmp_path, "x.yaml", {"decision_id": "d_seed", "deleted": True})
    with pytest.raises(DecisionError, match="tombstone"):
        load_rows(tmp_path, **_OPTS)


def test_two_files_declaring_one_key_raises(tmp_path):
    _write(tmp_path, "a.yaml", SEED_ROW)
    _write(tmp_path, "b.yaml", dict(SEED_ROW))
    with pytest.raises(DecisionError, match="both declare"):
        load_rows(tmp_path, **_OPTS)


def test_a_missing_key_field_raises_naming_THAT_field(tmp_path):
    """The message must name the family's own key, not a hardcoded one — that is the whole
    difference between a shared composer and a copied one."""
    _write(tmp_path, "a.yaml", {"outcome": "ratified"})
    with pytest.raises(DecisionError, match="decision_id"):
        load_rows(tmp_path, **_OPTS)


def test_an_empty_file_raises(tmp_path):
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "a.yaml").write_text("", encoding="utf-8")
    with pytest.raises(DecisionError, match="empty"):
        load_rows(tmp_path, **_OPTS)


def test_an_invalid_row_raises_NAMING_THE_FILE(tmp_path):
    """"A declaration is invalid" is not actionable at merge time."""
    _write(tmp_path, "bad_row.yaml", {"decision_id": "d", "outcome": "x", "extra": 1})
    with pytest.raises(DecisionError, match="bad_row.yaml"):
        load_rows(tmp_path, **_OPTS)


def test_several_documents_in_one_file_are_REFUSED(tmp_path):
    """Deliberately not parameterised, and the refusal is the good outcome: silently taking the
    first document would give a family four missing rows and a green seal. Measured — a lane
    wrote five rows into one file separated by `---` and this surfaced in seconds."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "many.yaml").write_text(
        "decision_id: a\noutcome: x\n---\ndecision_id: b\noutcome: y\n", encoding="utf-8"
    )
    with pytest.raises(Exception):
        load_rows(tmp_path, **_OPTS)


def test_the_family_error_is_raised_not_the_base(tmp_path):
    """A rail composing several families catches the base; one composing decisions catches
    DecisionError. That only works if the family type actually comes out."""
    _write(tmp_path, "a.yaml", {"outcome": "no key here"})
    with pytest.raises(DecisionError):
        read_rows(tmp_path, key_field="decision_id", error=DecisionError)
    # …and the base still catches it, since the family subclasses it.
    _write(tmp_path, "a.yaml", {"outcome": "no key here"})
    with pytest.raises(DeclarationError):
        read_rows(tmp_path, key_field="decision_id", error=DecisionError)

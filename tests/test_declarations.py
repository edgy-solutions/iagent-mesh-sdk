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

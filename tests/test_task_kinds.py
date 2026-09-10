"""The task kind declaration replaces two code tables, so its job is to make three
CONVENTIONS into PROPERTIES. This file is where each one stops being a comment.

The tables being retired stayed contained for one reason: three rules people followed — a new
kind is a row, everything keys on the archetype, an undeclared kind gets an honest default.
Rules in a comment do not survive a cutover. If they are not asserted here, the cutover trades
CONTAINED scaffolding for UNCONTAINED data, which is a worse position than the one it left.

A refusal suite with no positive control is the failure it is testing for: a model that raised
on everything would pass every rejection below. VALID is that control, and it is exercised
first.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from iagent_mesh.task_kinds import (
    ARCHETYPES,
    UNDECLARED,
    RendersAs,
    Resolution,
    TaskKind,
    TaskKindError,
    compose,
    json_schema,
    load_task_kinds,
    resolve,
    validate_dir,
)

VALID = {
    "kind": "grouped_review",
    "renders_as": {"badge": "REVIEW", "title": "Disposition review", "archetype": "GROUPED_REVIEW"},
    "accepts": ["approved", "rejected"],
}

_SCHEMA_ARTIFACT = Path(__file__).resolve().parents[1] / "schemas" / "task_kind.schema.json"


def _write(d: Path, name: str, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(row), encoding="utf-8")


# ── the positive control ─────────────────────────────────────────────────────────────────

def test_a_valid_row_builds():
    """THE CONTROL. Everything below asserts a refusal; without this they prove nothing."""
    tk = TaskKind(**VALID)
    assert tk.kind == "grouped_review"
    assert tk.renders_as.archetype == "GROUPED_REVIEW"
    assert tk.accepts == frozenset({"approved", "rejected"})


# ── discipline 1: a new kind is a ROW, never a branch ────────────────────────────────────

def test_resolve_is_total_so_no_caller_ever_meets_a_failed_lookup():
    """A lookup that CAN fail is what invites the `if kind == "..."` rescue branch. Totality
    is what makes 'a new kind is a row' structural instead of aspirational."""
    decls = [TaskKind(**VALID)]
    assert resolve("grouped_review", decls).declared is True
    # Every string answers — including the ones that broke a dict lookup before.
    for hostile in ("", "nope", "constructor", "toString", "__proto__", "hasOwnProperty"):
        r = resolve(hostile, decls)
        assert isinstance(r, Resolution)
        assert r.declared is False
        assert r.task_kind is UNDECLARED


def test_accepts_is_required_so_an_overlay_row_cannot_inherit_silently():
    """The one inheritance this module refuses. An overlay species that needed one extra verb
    and could not state it would get that verb as a branch in code — the thing being deleted."""
    without = {k: v for k, v in VALID.items() if k != "accepts"}
    with pytest.raises(Exception):
        TaskKind(**without)


# ── discipline 2: everything keys on the ARCHETYPE ───────────────────────────────────────

def test_archetype_vocabulary_is_closed():
    """An open archetype lets a species name a rendering nobody implements, which is a blank
    card rather than an honest fallback."""
    bad = copy.deepcopy(VALID)
    bad["renders_as"]["archetype"] = "SOMETHING_NEW"
    with pytest.raises(Exception):
        TaskKind(**bad)
    for a in ARCHETYPES:
        ok = copy.deepcopy(VALID)
        ok["renders_as"]["archetype"] = a
        assert TaskKind(**ok).renders_as.archetype == a


def test_a_kind_may_not_contain_a_colon():
    """THE COLON IS LOAD-BEARING. It separates an authz audience key from a render contract,
    and the two have been spelled the same. A kind that could carry one would let a render
    contract be mistaken for a grant key."""
    bad = {**VALID, "kind": "disposition_review:SUSTAINMENT"}
    with pytest.raises(Exception, match="colon|bare snake token"):
        TaskKind(**bad)


# ── discipline 3: an undeclared kind gets the HONEST default ─────────────────────────────

def test_the_undeclared_default_offers_no_verbs():
    """THIS CLOSES A LIVE HOLE — verified by tracing the render, not by reading a comment.

    Both tables being replaced hand an undeclared kind approve/reject today. The render side
    defaults to an approval archetype whose card renders both buttons unconditionally, and the
    "is this declared" predicate that would have stopped it has no caller outside its own
    tests. A note above that default claims a no-verb read-only mode; the mode does not exist.

    Empty accepts makes read-only a CONSEQUENCE of the row rather than a mode a card has to
    remember. The species this protects is the NEXT one added, which inherits approve/reject
    on "this document could not be prepared for review" — a decision the data cannot represent,
    archived immutably as promotion evidence."""
    assert UNDECLARED.accepts == frozenset()
    assert UNDECLARED.renders_as.badge == "TASK"
    # The archetype still renders a card — the default is honest, not absent.
    assert UNDECLARED.renders_as.archetype in ARCHETYPES


def test_declared_is_reported_separately_from_the_row():
    """A consumer must be able to say "unknown species here" rather than present the default
    as though it were a real declaration."""
    r = resolve("nope", [TaskKind(**VALID)])
    assert r.declared is False and r.task_kind is UNDECLARED
    r2 = resolve("grouped_review", [TaskKind(**VALID)])
    assert r2.declared is True and r2.task_kind.kind == "grouped_review"


# ── the row's own coherence ──────────────────────────────────────────────────────────────

def test_reason_required_must_be_reachable():
    """Requiring a reason for a verb nobody can choose is a rule that READS as enforced and
    is not — the failure mode with no symptom."""
    bad = {**VALID, "reason_required": ["acknowledged"]}
    with pytest.raises(Exception, match="does not accept|reason"):
        TaskKind(**bad)
    ok = {**VALID, "accepts": ["acknowledged", "redriven"], "reason_required": ["acknowledged"]}
    assert TaskKind(**ok).reason_required == frozenset({"acknowledged"})


def test_a_read_only_species_is_expressible():
    """Empty accepts is legal and MEANS something: rendered, not actionable. If it were
    illegal, the only way to express a read-only species would be to omit its row — which
    resolves to UNDECLARED and loses the badge and title the species actually has."""
    ro = TaskKind(**{**VALID, "accepts": []})
    assert ro.accepts == frozenset()
    assert ro.renders_as.badge == "REVIEW"


def test_extra_fields_are_refused():
    with pytest.raises(Exception):
        TaskKind(**{**VALID, "colour": "red"})


# ── loading and ADR-0036 composition ─────────────────────────────────────────────────────

def test_load_raises_on_an_invalid_row_rather_than_skipping(tmp_path):
    """A consumer that skipped one would come up healthy and render exactly one species as
    UNDECLARED — a task that silently loses its verbs and looks like a design decision."""
    _write(tmp_path, "a.yaml", VALID)
    _write(tmp_path, "b.yaml", {**VALID, "kind": "bad:kind"})
    with pytest.raises(TaskKindError):
        load_task_kinds(tmp_path)


def test_two_files_declaring_one_kind_is_an_error(tmp_path):
    _write(tmp_path, "a.yaml", VALID)
    _write(tmp_path, "b.yaml", dict(VALID))
    with pytest.raises(TaskKindError, match="both declare"):
        load_task_kinds(tmp_path)


def test_overlay_replaces_by_kind_and_carries_its_own_verbs(tmp_path):
    """WHERE DOMAIN SPECIES LIVE. The seed ships structural kinds; a deployment adds its own
    here — and because the overlay row is a FULL replacement carrying its own accepts, a
    domain species needing a domain verb declares it rather than growing a branch in code."""
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "grouped_review.yaml", VALID)
    _write(overlay, "local_species.yaml", {
        "kind": "local_species",
        "renders_as": {"badge": "LOCAL", "title": "A deployment's own species",
                       "archetype": "APPROVAL_TASK"},
        "accepts": ["approved", "rejected", "deferred"],
    })
    out = compose(seed, [overlay])
    kinds = {t.kind: t for t in out}
    assert set(kinds) == {"grouped_review", "local_species"}
    assert "deferred" in kinds["local_species"].accepts, (
        "an overlay row must be able to declare a verb the seed never heard of"
    )


def test_a_tombstone_for_a_kind_the_seed_does_not_ship_is_an_error(tmp_path):
    """A stale tombstone is how an overlay rots: it keeps deleting a key nobody ships while
    the species it meant to remove returns under a new name with nothing to say so."""
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "grouped_review.yaml", VALID)
    _write(overlay, "gone.yaml", {"kind": "never_shipped", "deleted": True})
    with pytest.raises(TaskKindError, match="does not ship"):
        compose(seed, [overlay])


def test_a_tombstone_outside_an_overlay_is_an_error(tmp_path):
    _write(tmp_path, "x.yaml", {"kind": "grouped_review", "deleted": True})
    with pytest.raises(TaskKindError, match="tombstone"):
        validate_dir(tmp_path)


# ── the schema artifact ──────────────────────────────────────────────────────────────────

def test_committed_schema_matches_the_models():
    """DRIFT SEAL. The schema is GENERATED from the models, so the two cannot disagree — but
    only if something checks the committed artifact against a fresh generation. Without this,
    the committed file is a snapshot that rots the first time a field moves, and a consumer
    validating against it would accept rows the models reject."""
    assert _SCHEMA_ARTIFACT.exists(), (
        f"{_SCHEMA_ARTIFACT.name} is missing — regenerate with "
        f"`python -c \"import json,iagent_mesh.task_kinds as t; "
        f"print(json.dumps(t.json_schema(), indent=2))\"`"
    )
    committed = json.loads(_SCHEMA_ARTIFACT.read_text(encoding="utf-8"))
    assert committed == json_schema(), (
        "the committed schema no longer matches the models — regenerate it"
    )


def test_the_schema_seal_can_fail():
    """THE POSITIVE CONTROL FOR THE SEAL ITSELF. A comparison against a value derived from the
    same call would pass no matter what; this proves the assertion above discriminates."""
    mutated = dict(json_schema())
    mutated["title"] = "NotTheRealTitle"
    assert mutated != json_schema()

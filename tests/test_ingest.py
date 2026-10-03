"""The ingest wire shapes have one property that matters more than any field-level check:
ADR-0021 rules an unregistered content kind a HALT, never a default and never a guess. That is
a DIFFERENT shape from every other "resolve a declared row" function this SDK ships —
`task_kinds.resolve` is deliberately TOTAL — so the spine of this file is proving the two
resolvers actually disagree, not merely documenting that they should.

A refusal suite with no positive control is the failure it is testing for. VALID_* is that
control for each model, exercised first.
"""
from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from iagent_mesh.declarations import DeclarationError
from iagent_mesh.interfaces import Initiator
from iagent_mesh.provenance import DIRECT, ProvenanceBlock
from iagent_mesh.task_kinds import UNDECLARED, resolve as resolve_task_kind
from iagent_mesh.ingest import (
    CONTENT_KIND_BRANCHES,
    INGEST_STAGES,
    ContentKindRegistration,
    ContentKindUnregistered,
    IngestRequest,
    IngestStatus,
    compose,
    load_content_kind_registrations,
    registered_kinds,
    resolve_content_kind,
    validate_dir,
)

VALID_PROVENANCE = dict(
    authoritative_source="vendor-pcn-feed",
    obtained_via=DIRECT,
    as_of="2026-09-30",
    ingested_at="2026-09-30T12:00:00Z",
    ingest_run="run-001",
    standing="trusted",
)

VALID_INITIATOR = dict(subject="user:cnogradi", kind="person")

VALID_REGISTRATION = dict(
    kind="work-instruction",
    passes=("manufacturing.baml::ExtractWorkInstructions",),
    outputs=("mfg:WorkInstruction",),
    domain="SUSTAINMENT",
)

VALID_EVENT_REGISTRATION = dict(
    kind="maintenance-fault-event",
    branch="event",
    seeds_workflow="maintenance-fault-workflow",
    identity_field="event_id",
)


def _write(d, name: str, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(yaml.safe_dump(row), encoding="utf-8")


# ── the stage vocabulary ─────────────────────────────────────────────────────────────────

def test_ingest_stages_is_the_six_stage_tuple():
    """`review` as of 0.9.7 — a rename of `awaiting_disposition`, same state, not a seventh
    value beside it (see the INGEST_STAGES comment in ingest.py)."""
    assert INGEST_STAGES == (
        "received", "extracting", "review", "promoted", "rejected", "failed"
    )


def test_ingest_status_builds_for_a_clean_stage_with_no_detail():
    status = IngestStatus(stage="received")
    assert status.detail is None
    assert status.is_terminal() is False


def test_ingest_status_requires_detail_on_rejected_and_failed():
    """Same discipline as MeshWriteResult: a terminal state with no reason reaches an operator
    as 'something happened'."""
    for stage in ("rejected", "failed"):
        with pytest.raises(ValidationError, match="detail"):
            IngestStatus(stage=stage)
        IngestStatus(stage=stage, detail="explained")  # does not raise


def test_ingest_status_does_not_require_detail_on_promoted():
    """`promoted` is terminal but its reason lives on the promotion fact (ADR-0041 §5), not a
    field this model re-carries — distinct from `rejected`/`failed`, which have nowhere else to
    say why."""
    status = IngestStatus(stage="promoted")
    assert status.detail is None
    assert status.is_terminal() is True


def test_is_terminal_matches_the_named_terminal_stages():
    terminal = {"promoted", "rejected", "failed"}
    for stage in INGEST_STAGES:
        detail = "x" if stage in ("rejected", "failed") else None
        status = IngestStatus(stage=stage, detail=detail)
        assert status.is_terminal() == (stage in terminal), stage


def test_ingest_status_stage_vocabulary_is_closed():
    with pytest.raises(ValidationError):
        IngestStatus(stage="archived")


# ── IngestRequest ────────────────────────────────────────────────────────────────────────

def _request(**overrides) -> IngestRequest:
    fields = dict(
        object_ref="ingress-user/2026-09-30/pcn-1234.pdf",
        content_kind=None,
        domain_type="manufacturing",
        provenance=ProvenanceBlock(**VALID_PROVENANCE),
        initiator=Initiator(**VALID_INITIATOR),
    )
    fields.update(overrides)
    return IngestRequest(**fields)


def test_a_valid_ingest_request_builds():
    req = _request()
    assert req.object_ref.endswith("pcn-1234.pdf")
    assert req.content_kind is None
    assert req.provenance.authoritative_source == "vendor-pcn-feed"


def test_ingest_request_requires_provenance():
    with pytest.raises(ValidationError):
        IngestRequest(
            object_ref="x", initiator=Initiator(**VALID_INITIATOR)
        )  # type: ignore[call-arg]


def test_ingest_request_requires_initiator():
    with pytest.raises(ValidationError):
        IngestRequest(
            object_ref="x", provenance=ProvenanceBlock(**VALID_PROVENANCE)
        )  # type: ignore[call-arg]


def test_ingest_request_object_ref_cannot_be_blank():
    with pytest.raises(ValidationError, match="object_ref"):
        _request(object_ref="")


def test_ingest_request_content_kind_none_means_undeclared_blank_string_is_refused():
    """`None` is the legitimate 'defer to path-derived fallback' state (ADR-0021 rule 2); a
    blank string is not the same thing and is refused rather than silently treated as None."""
    _request(content_kind=None)  # does not raise
    with pytest.raises(ValidationError, match="content_kind"):
        _request(content_kind="")


def test_ingest_request_is_frozen_and_forbids_extra_fields():
    req = _request()
    with pytest.raises(ValidationError):
        req.object_ref = "something-else"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _request(unexpected_field="x")


# ── ContentKindRegistration, the mapping-table row ─────────────────────────────────────────

def test_a_valid_registration_builds():
    row = ContentKindRegistration(**VALID_REGISTRATION)
    assert row.kind == "work-instruction"
    assert row.passes == ("manufacturing.baml::ExtractWorkInstructions",)
    assert row.outputs == ("mfg:WorkInstruction",)


def test_registration_kind_cannot_be_blank():
    with pytest.raises(ValidationError, match="kind"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "kind": ""})


def test_registration_passes_and_outputs_cannot_be_empty():
    """A kind with no pass runs nothing; a kind with no output produces instances the routing
    graph can never reach — ADR-0021's whole point. Neither is a legal row."""
    with pytest.raises(ValidationError, match="passes"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "passes": ()})
    with pytest.raises(ValidationError, match="outputs"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "outputs": ()})


def test_registration_rejects_a_repeated_pass_or_output():
    with pytest.raises(ValidationError, match="repeats"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "passes": ("a", "a")})
    with pytest.raises(ValidationError, match="repeats"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "outputs": ("a", "a")})


def test_passes_order_is_preserved_not_a_set():
    """Passes run in sequence — a set would let composition silently reorder the pipeline."""
    ordered = ("pass-b", "pass-a", "pass-c")
    row = ContentKindRegistration(**{**VALID_REGISTRATION, "passes": ordered})
    assert row.passes == ordered


def test_domain_is_optional_a_generic_kind_declares_none():
    """Corrected by the architect: a required domain forces every kind to declare one, which is
    the hazard the drop-domains prompt identified. A generic kind (pdf, engineering-document,
    doors-export) has no home domain; its artifacts' origin resolves per-artifact from evidence."""
    row = ContentKindRegistration(**{**VALID_REGISTRATION, "domain": None})
    assert row.domain is None


def test_domain_blank_string_is_refused_but_none_is_not():
    with pytest.raises(ValidationError, match="domain"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "domain": ""})


# ── ContentKindRegistration, the Event branch (0.9.7) ──────────────────────────────────────

def test_content_kind_branches_is_the_two_branch_tuple():
    assert CONTENT_KIND_BRANCHES == ("document", "event")


def test_a_valid_event_registration_builds():
    row = ContentKindRegistration(**VALID_EVENT_REGISTRATION)
    assert row.branch == "event"
    assert row.seeds_workflow == "maintenance-fault-workflow"
    assert row.identity_field == "event_id"
    assert row.passes == ()
    assert row.outputs == ()


def test_document_branch_is_the_default():
    row = ContentKindRegistration(**VALID_REGISTRATION)
    assert row.branch == "document"
    assert row.seeds_workflow is None
    assert row.identity_field is None


def test_event_branch_requires_seeds_workflow():
    with pytest.raises(ValidationError, match="seeds_workflow"):
        ContentKindRegistration(**{**VALID_EVENT_REGISTRATION, "seeds_workflow": None})


def test_event_branch_requires_identity_field():
    with pytest.raises(ValidationError, match="identity_field"):
        ContentKindRegistration(**{**VALID_EVENT_REGISTRATION, "identity_field": None})


def test_event_branch_forbids_passes_and_outputs():
    """An event kind is not extracted — it seeds a workflow. passes/outputs belong to
    branch='document' rows only."""
    with pytest.raises(ValidationError, match="passes/outputs"):
        ContentKindRegistration(**{**VALID_EVENT_REGISTRATION, "passes": ("p",)})
    with pytest.raises(ValidationError, match="passes/outputs"):
        ContentKindRegistration(**{**VALID_EVENT_REGISTRATION, "outputs": ("o",)})


def test_document_branch_forbids_seeds_workflow_and_identity_field():
    """The inverse of the event-branch check — these two fields are event-only, so a document
    row declaring either is the same shape of error as an event row declaring passes."""
    with pytest.raises(ValidationError, match="seeds_workflow"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "seeds_workflow": "x"})
    with pytest.raises(ValidationError, match="identity_field"):
        ContentKindRegistration(**{**VALID_REGISTRATION, "identity_field": "x"})


# ── resolve_content_kind: THE HALT, not the default ─────────────────────────────────────

def test_resolve_content_kind_returns_the_matching_row():
    row = ContentKindRegistration(**VALID_REGISTRATION)
    resolved = resolve_content_kind("work-instruction", [row])
    assert resolved is row


def test_resolve_content_kind_HALTS_by_name_on_an_unregistered_kind():
    """ADR-0021 rule 3. Raised, never returned as a sentinel row — proven by contrast against
    task_kinds.resolve below, which is deliberately the opposite shape for a different reason."""
    row = ContentKindRegistration(**VALID_REGISTRATION)
    with pytest.raises(ContentKindUnregistered, match="not a registered content kind"):
        resolve_content_kind("mystery-kind", [row])


def test_resolve_content_kind_is_NOT_total_unlike_task_kinds_resolve():
    """THE ARM THAT WOULD CATCH THE WRONG PATTERN BEING COPIED. `task_kinds.resolve` degrades
    to UNDECLARED for a UI card that must draw something; `resolve_content_kind` must not offer
    the same comfort, because a silently-defaulted content kind is exactly how the single flat
    `mfg:ManufacturingStep` kind ADR-0021 replaces happened. Both resolvers exercised side by
    side on the identical unknown string, asserting they disagree."""
    task_kind_result = resolve_task_kind("mystery-kind", [])
    assert task_kind_result.task_kind is UNDECLARED and task_kind_result.declared is False

    row = ContentKindRegistration(**VALID_REGISTRATION)
    with pytest.raises(ContentKindUnregistered):
        resolve_content_kind("mystery-kind", [row])


def test_resolve_content_kind_message_names_the_registered_set():
    """The halt must be actionable — naming what IS registered, not only that the kind wasn't."""
    row = ContentKindRegistration(**VALID_REGISTRATION)
    with pytest.raises(ContentKindUnregistered, match="work-instruction"):
        resolve_content_kind("mystery-kind", [row])


# ── registered_kinds: select-from-authorized-set ───────────────────────────────────────────

def test_registered_kinds_is_the_pickers_legal_set():
    rows = [
        ContentKindRegistration(**VALID_REGISTRATION),
        ContentKindRegistration(kind="compliance-audit", passes=("p",), outputs=("o",),
                                domain="SUSTAINMENT"),
    ]
    assert registered_kinds(rows) == ("compliance-audit", "work-instruction")


def test_a_kind_absent_from_registered_kinds_is_the_kind_resolve_halts_on():
    """The picker's legal set and the resolver's admitted set must be the SAME set — a kind
    outside one and inside the other would mean the picker offers something resolve refuses,
    or refuses something resolve would have accepted."""
    rows = [ContentKindRegistration(**VALID_REGISTRATION)]
    legal = registered_kinds(rows)
    assert "mystery-kind" not in legal
    with pytest.raises(ContentKindUnregistered):
        resolve_content_kind("mystery-kind", rows)
    resolve_content_kind(legal[0], rows)  # does not raise


# ── loading and ADR-0036 composition — proving the wiring, not re-proving the composer ────

def test_load_raises_on_an_invalid_row_rather_than_skipping(tmp_path):
    _write(tmp_path, "a.yaml", VALID_REGISTRATION)
    _write(tmp_path, "b.yaml", {**VALID_REGISTRATION, "kind": "bad", "passes": []})
    with pytest.raises(DeclarationError):
        load_content_kind_registrations(tmp_path)


def test_two_files_declaring_one_kind_is_an_error(tmp_path):
    _write(tmp_path, "a.yaml", VALID_REGISTRATION)
    _write(tmp_path, "b.yaml", dict(VALID_REGISTRATION))
    with pytest.raises(DeclarationError, match="both declare"):
        load_content_kind_registrations(tmp_path)


def test_overlay_replaces_by_kind_and_carries_its_own_passes_and_outputs(tmp_path):
    """WHERE A DEPLOYMENT'S OWN KINDS LIVE — the seed ships nothing domain-specific (ADR-0021:
    the table is colocated with the plugin registry, which lives in doc-tools, not here)."""
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "work_instruction.yaml", VALID_REGISTRATION)
    _write(overlay, "compliance_audit.yaml", {
        "kind": "compliance-audit",
        "passes": ["compliance.baml::ExtractAudit"],
        "outputs": ["mfg:ComplianceAudit"],
        "domain": "SUSTAINMENT",
    })
    out = compose(seed, [overlay])
    kinds = {r.kind: r for r in out}
    assert set(kinds) == {"work-instruction", "compliance-audit"}
    assert kinds["compliance-audit"].outputs == ("mfg:ComplianceAudit",)


def test_a_tombstone_for_a_kind_the_seed_does_not_ship_is_an_error(tmp_path):
    seed, overlay = tmp_path / "seed", tmp_path / "overlay"
    _write(seed, "work_instruction.yaml", VALID_REGISTRATION)
    _write(overlay, "gone.yaml", {"kind": "never-shipped", "deleted": True})
    with pytest.raises(DeclarationError, match="does not ship"):
        compose(seed, [overlay])


def test_a_tombstone_outside_an_overlay_is_an_error(tmp_path):
    _write(tmp_path, "x.yaml", {"kind": "work-instruction", "deleted": True})
    with pytest.raises(DeclarationError, match="tombstone"):
        validate_dir(tmp_path)


def test_validate_dir_resolves_and_picks_from_the_loaded_rows(tmp_path):
    """End to end: a directory of rows composes into exactly what resolve_content_kind and
    registered_kinds then operate on — the path a deployment's own registry directory travels."""
    _write(tmp_path, "work_instruction.yaml", VALID_REGISTRATION)
    rows = validate_dir(tmp_path)
    assert registered_kinds(rows) == ("work-instruction",)
    resolve_content_kind("work-instruction", rows)  # does not raise
    with pytest.raises(ContentKindUnregistered):
        resolve_content_kind("mystery-kind", rows)

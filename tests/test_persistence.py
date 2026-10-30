"""ADR-0060 types, unwired — see the module docstring: these are shapes only, no behavior, no
Protocol change, pending an architect ruling. These seals cover field validation only: required
strings, `extra="forbid"`, frozen, the parent-both-or-neither pair, and the `blob:` pattern.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.persistence import (
    ArtifactRef,
    BlobRef,
    DocumentManifest,
    PersistedClass,
    PersistenceDescriptor,
)

VALID_PERSISTED_CLASS = dict(
    output_class="mfg:WorkInstruction",
    store="neo4j",
    identity_field="instance_id",
)


# ── PersistedClass ──────────────────────────────────────────────────────────────────────────

def test_persisted_class_builds_from_required_fields():
    pc = PersistedClass(**VALID_PERSISTED_CLASS)
    assert pc.output_class == "mfg:WorkInstruction"
    assert pc.readable_fields == ()
    assert pc.parent_class is None
    assert pc.parent_link_field is None


def test_persisted_class_forbids_an_unknown_field():
    with pytest.raises(ValidationError):
        PersistedClass(**VALID_PERSISTED_CLASS, extra_field="surprise")


def test_persisted_class_is_frozen():
    pc = PersistedClass(**VALID_PERSISTED_CLASS)
    with pytest.raises(ValidationError):
        pc.store = "weaviate"  # type: ignore[misc]


def test_persisted_class_parent_must_be_both_or_neither():
    PersistedClass(**VALID_PERSISTED_CLASS, parent_class="mfg:Pcn", parent_link_field="pcn_id")
    with pytest.raises(ValidationError, match="both set or both None"):
        PersistedClass(**VALID_PERSISTED_CLASS, parent_class="mfg:Pcn")
    with pytest.raises(ValidationError, match="both set or both None"):
        PersistedClass(**VALID_PERSISTED_CLASS, parent_link_field="pcn_id")


def test_persisted_class_required_strings_cannot_be_blank():
    for field in ("output_class", "store", "identity_field"):
        with pytest.raises(ValidationError, match=field):
            PersistedClass(**{**VALID_PERSISTED_CLASS, field: ""})


# ── PersistenceDescriptor ────────────────────────────────────────────────────────────────────

def test_persistence_descriptor_defaults_to_no_classes():
    pd = PersistenceDescriptor()
    assert pd.classes == ()


def test_persistence_descriptor_holds_one_persisted_class_per_output_class():
    pd = PersistenceDescriptor(classes=(PersistedClass(**VALID_PERSISTED_CLASS),))
    assert len(pd.classes) == 1
    assert pd.classes[0].output_class == "mfg:WorkInstruction"


def test_persistence_descriptor_forbids_an_unknown_field():
    with pytest.raises(ValidationError):
        PersistenceDescriptor(extra_field="surprise")


def test_persistence_descriptor_is_frozen():
    pd = PersistenceDescriptor()
    with pytest.raises(ValidationError):
        pd.classes = (PersistedClass(**VALID_PERSISTED_CLASS),)  # type: ignore[misc]


# ── ArtifactRef ──────────────────────────────────────────────────────────────────────────────

def test_artifact_ref_builds_from_id():
    ref = ArtifactRef(id="artifact:1")
    assert ref.id == "artifact:1"


def test_artifact_ref_id_cannot_be_blank():
    with pytest.raises(ValidationError, match="id"):
        ArtifactRef(id="")


def test_artifact_ref_forbids_an_unknown_field_and_is_frozen():
    with pytest.raises(ValidationError):
        ArtifactRef(id="artifact:1", extra_field="surprise")
    ref = ArtifactRef(id="artifact:1")
    with pytest.raises(ValidationError):
        ref.id = "artifact:2"  # type: ignore[misc]


# ── BlobRef ──────────────────────────────────────────────────────────────────────────────────

def test_blob_ref_accepts_the_blob_prefix():
    ref = BlobRef(reference="blob:ingest-1/path/to/file")
    assert ref.reference == "blob:ingest-1/path/to/file"


def test_blob_ref_rejects_a_reference_without_the_blob_prefix():
    with pytest.raises(ValidationError):
        BlobRef(reference="https://example.com/file")


def test_blob_ref_forbids_an_unknown_field_and_is_frozen():
    with pytest.raises(ValidationError):
        BlobRef(reference="blob:ingest-1/x", extra_field="surprise")
    ref = BlobRef(reference="blob:ingest-1/x")
    with pytest.raises(ValidationError):
        ref.reference = "blob:ingest-2/y"  # type: ignore[misc]


# ── DocumentManifest ─────────────────────────────────────────────────────────────────────────

def test_document_manifest_builds_from_required_fields():
    m = DocumentManifest(ingest_id="ingest-1", kind="work-instruction")
    assert m.ingest_id == "ingest-1"
    assert m.kind == "work-instruction"
    assert m.artifacts is None
    assert m.entities == ()
    assert m.blobs == ()


def test_document_manifest_required_strings_cannot_be_blank():
    with pytest.raises(ValidationError, match="ingest_id"):
        DocumentManifest(ingest_id="", kind="work-instruction")
    with pytest.raises(ValidationError, match="kind"):
        DocumentManifest(ingest_id="ingest-1", kind="")


def test_document_manifest_artifacts_none_vs_empty_tuple_are_distinguishable():
    unknown = DocumentManifest(ingest_id="ingest-1", kind="work-instruction", artifacts=None)
    none_visible = DocumentManifest(ingest_id="ingest-1", kind="work-instruction", artifacts=())
    assert unknown.artifacts is None
    assert none_visible.artifacts == ()
    assert unknown.artifacts != none_visible.artifacts


def test_document_manifest_forbids_an_unknown_field_and_is_frozen():
    with pytest.raises(ValidationError):
        DocumentManifest(ingest_id="ingest-1", kind="work-instruction", extra_field="surprise")
    m = DocumentManifest(ingest_id="ingest-1", kind="work-instruction")
    with pytest.raises(ValidationError):
        m.kind = "pcn"  # type: ignore[misc]

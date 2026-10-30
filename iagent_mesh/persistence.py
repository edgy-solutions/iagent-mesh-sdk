"""ADR-0060 TYPES, UNWIRED. Four proposed data shapes from ADR-0060's §5 — a persistence
descriptor for a content kind's output classes, and the artifact/blob/document-manifest shapes
a proposed `GET /documents/{id}` route would answer with. None of this is load-bearing and none
of it is used anywhere in this codebase yet: no existing Protocol method is changed, no route is
built, and the origin-rule/verb-generation behavior ADR-0060 describes is not implemented here.
This module ships the shapes only, pending an architect ruling on the behavior around them — the
same split :mod:`iagent_mesh.refusal` draws between validating a shape and deciding anything
about it.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "PersistedClass",
    "PersistenceDescriptor",
    "ArtifactRef",
    "BlobRef",
    "DocumentManifest",
]


def _required_str(model: str, field: str, v: str) -> str:
    if not v.strip():
        raise ValueError(f"{model}.{field}='' — required, cannot be blank")
    return v


class PersistedClass(BaseModel):
    """One output class of a content kind's persistence descriptor: where it lives and what a
    generated read verb may expose about it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_class: str
    store: str
    identity_field: str
    readable_fields: tuple[str, ...] = ()
    parent_class: Optional[str] = None
    parent_link_field: Optional[str] = None
    facets: tuple[str, ...] = ()
    search_fields: tuple[str, ...] = ()

    @field_validator("output_class", "store", "identity_field")
    @classmethod
    def _required_fields_are_present(cls, v: str, info) -> str:
        return _required_str("PersistedClass", info.field_name, v)

    @model_validator(mode="after")
    def _parent_is_both_or_neither(self) -> "PersistedClass":
        # parent_class and parent_link_field must be both set or both None — a half-declared
        # parent link is not a valid (class, link_field) pair.
        if (self.parent_class is None) != (self.parent_link_field is None):
            raise ValueError(
                f"PersistedClass(output_class={self.output_class!r}): parent_class and "
                f"parent_link_field must be both set or both None — a half-declared parent "
                f"link is not a valid (class, link_field) pair"
            )
        return self


class PersistenceDescriptor(BaseModel):
    """One `PersistedClass` per output class a content kind produces. Deliberately distinct from
    the kind row's own `identity_field`/`parent_link_field` (arrival dedupe / extracted-output
    parent) — this descriptor's fields answer a different question (how a generated verb addresses
    a *persisted* row) and need not agree with those."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classes: tuple[PersistedClass, ...] = ()


class ArtifactRef(BaseModel):
    """An opaque reference to one stored artifact. Field shape is intentionally minimal: the
    source ADR leaves whether this becomes `MeshArtifacts.get`'s documented payload, or stays
    scoped to `DocumentManifest` only, to an open architect ruling — only `id` is textually
    grounded today."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str

    @field_validator("id")
    @classmethod
    def _id_is_present(cls, v: str) -> str:
        return _required_str("ArtifactRef", "id", v)


class BlobRef(BaseModel):
    """A stable byte-reference, never a store URL: `blob:<ingest_id>/<path>`. Resolved to a
    short-lived URL by a route this ADR proposes and does not build; the reference itself never
    expires even though the URL it resolves to does."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: str = Field(..., pattern=r"^blob:")


class DocumentManifest(BaseModel):
    """One ingested document's manifest: the proposed response shape of a `GET /documents/{id}`
    route this ADR describes and does not build. `artifacts`: `None`=unknown, `()`=none or none
    visible to this caller (folded together on purpose, per the ADR's existence-oracle framing)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ingest_id: str
    kind: str
    leaf: Optional[str] = None
    domain: Optional[str] = None
    title: Optional[str] = None
    stage: Optional[str] = None
    arrived_at: Optional[str] = None
    owner_domain: Optional[str] = None
    program: Optional[str] = None
    artifacts: Optional[tuple[ArtifactRef, ...]] = None
    entities: tuple[dict, ...] = ()
    blobs: tuple[BlobRef, ...] = ()

    @field_validator("ingest_id", "kind")
    @classmethod
    def _required_fields_are_present(cls, v: str, info) -> str:
        return _required_str("DocumentManifest", info.field_name, v)

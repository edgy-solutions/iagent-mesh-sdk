"""THE SYSTEMS-OF-RECORD REGISTRY, AND `Origin` — the architect's 2026-10-02 ruling "ORIGIN, not
audience", item 1: ``policy/overlays/<deployment>/systems_of_record.yaml`` with the schema from
``lane/ca``. ia-01/lane/01 is blocked on this module: "Nothing sets origin yet. Every artifact
stays visible to its owner only until your schema lands and the resolver is built to it."

── WHAT THE RESOLVER DOES WITH THIS, QUOTED SO THE SCHEMA CAN BE CHECKED AGAINST IT ────────
    extracted identity -> first matching system's pattern -> connector lookup -> origin from
    the record. Miss or no pattern -> origin unresolved, visible to the dropper only. Sandbox
    ships an empty list plus one fake connector for the seal.

This module ships the ROW SHAPE (:class:`SystemOfRecord`), the pure MATCH step
(:func:`match_system_of_record` — "first matching system's pattern wins", no connector call), the
CONNECTOR SHAPE one lookup and one miss both honour (:class:`SystemOfRecordConnector`), and the
ARTIFACT-SIDE RESULT (:class:`Origin`). It does NOT ship the resolver (the connector call plus
the origin-from-the-record wiring) or the sandbox overlay — ia-01's own packet says "when you tag
the schema, I build the resolver plus the sandbox overlay", and that division holds here the same
way :mod:`iagent_mesh.ingest` ships the registry shape and never the pipeline that runs a pass.

**THIS SDK DOES NOT SHIP ANY ROWS** — same discipline as :mod:`iagent_mesh.ingest` and
:mod:`iagent_mesh.task_kinds`. ``policy/overlays/<deployment>/systems_of_record.yaml`` is a
deployment's file, not this package's.

── FOUR RULINGS, ANSWERING ia-01's FOUR OPEN QUESTIONS ─────────────────────────────────────
1. **An "extracted identity" is a set of (field name -> value) pairs already read off the
   artifact, not one global string.** e.g. ``{"work_order_ref": "WO-12345", "tail_number":
   "N12345"}``. :attr:`SystemOfRecord.identity`'s ``fields`` names, in priority order, which of
   those field names THIS system's identity is drawn from; ``pattern`` is a regex tested against
   each named field's value in that order, and the first field present on the artifact whose value
   matches is the match. Regex, not glob or prefix: it is the only one of the three that can
   express "this looks like a `sor-events-a` work-order number" without the row author inventing a second
   mini-language, and this SDK already uses regex for a closed-vocabulary row field elsewhere
   (:data:`iagent_mesh.task_kinds.KIND_PATTERN`) — one grammar, not two.
2. **A connector's name is free text in the row, resolved against the deployment's registered
   connector set, and an unknown name is a load-time refusal, never a silent miss** — the
   "prefix-registry failure class" ia-01 named. This module cannot perform that check itself: a
   row does not know its deployment's registry. :func:`validate_connectors_known` is the refusal,
   called BY the deployment that owns the registry, the same split
   :func:`iagent_mesh.ingest.resolve_content_kind` draws between the registry shape (here) and the
   registry's contents (the kind-source repo).
3. **The connector protocol is one method, hit-or-miss, no third state.**
   :class:`SystemOfRecordConnector` — ``lookup(value) -> dict | None``. ``None`` is a miss, a
   present dict is a hit, keyed by the names in :attr:`ConnectorLookup.returns`. One ``Protocol``
   so the sandbox's one fake connector and a real one are the same type, exactly what ia-01 asked
   for.
4. **``resolved_by`` is a NEW, closed vocabulary, deliberately NOT
   :data:`iagent_mesh.provenance.OBTAINED_VIA`.** ``obtained_via`` measures how far a COPY of an
   assertion travelled from the system that owns it (direct/etl/warehouse/manual-export/
   user-drop, ordered nearest-to-truth). ``resolved_by`` measures a different thing: HOW an
   artifact's ``owner_domain``/``program`` were determined at all — a system-of-record lookup, a
   human steward's assertion, or neither. Folding the two into one tuple would make a position in
   an ordered-by-distance vocabulary answer a question it was never ordered to answer, so
   :data:`RESOLVED_BY` is its own tuple, and ``Origin`` carries both the field (ADR-0046-unrelated
   — this is the invincible-agent internal numbering, not OpenDDIL's) and the field it does NOT
   reuse named side by side in this docstring so the next reader does not have to re-derive why.
5. **``Origin.evidence[]`` CITES the connector's own returned fields — it never restates them
   under a new SDK-invented name.** A ``resolved_by="record"`` origin's evidence came from
   somewhere real: the connector's ``lookup`` already returned a dict of named fields
   (:attr:`ConnectorLookup.returns`), and if that system's own provenance vocabulary names WHAT
   was read, WHO produced it, and WHEN it was observed (e.g. a protocol name, a producer id, an
   observed-at timestamp — the shape a deployment's connector is expected to return when its
   source system has one), the citation is built FROM those names, not from a generic
   ``record_ref`` this module makes up to stand in for "something was read." A row's
   ``ConnectorLookup.returns`` should name its source system's own provenance fields when it has
   them, so the evidence this module's resolver writes is a citation to a real field, not a
   restatement of the record under a borrowed name. (This module does not format the citation
   string itself — that's the resolver's job, per ruling 2 above — it only states which fields a
   well-formed ``returns`` list should prefer naming.)

── WHY `compose`/`validate_dir` ARE MODULE-QUALIFIED ONLY, NEVER PROMOTED BARE ─────────────
This is the FIFTH family sharing the composer (:mod:`iagent_mesh.declarations`), after
``graph_manifest``, ``task_kinds`` and ``ingest``. ``compose``/``validate_dir`` already collide
twice at the SDK root (the 2026-09-19 ruling recorded in ``iagent_mesh/__init__.py``); this module
adds a THIRD collision rather than a new one needing its own carve-out, and the existing rule
already covers it: no new colliding name ever reaches the root. Import
``iagent_mesh.systems_of_record.compose``, not a root ``compose``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .declarations import DeclarationError, compose_rows, load_rows

__all__ = [
    "IdentityMatch",
    "ConnectorLookup",
    "SystemOfRecord",
    "SystemOfRecordConnector",
    "UnknownConnector",
    "match_system_of_record",
    "validate_connectors_known",
    "load_systems_of_record",
    "compose",
    "validate_dir",
    "RESOLVED_BY",
    "ResolvedBy",
    "Origin",
]


class IdentityMatch(BaseModel):
    """Which extracted field(s) of the artifact this system's identity is drawn from, and the
    pattern a candidate value must match to belong to this system. See the module docstring's
    ruling 1 for why this is a field LIST plus one pattern, rather than one global string."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: str
    """A regex. Tested against each of ``fields``' values in order; the first present field
    whose value matches is the match for this system."""

    fields: tuple[str, ...]
    """Extracted-artifact field names, in priority order. Non-empty, unique — a system with no
    named field cannot ever be matched, which is a row someone forgot to finish, not a system
    with no identity."""

    @field_validator("pattern")
    @classmethod
    def _pattern_is_present_and_compiles(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "IdentityMatch.pattern='' — a blank pattern matches nothing, which makes the "
                "row unreachable rather than general"
            )
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"IdentityMatch.pattern={v!r} is not a valid regex: {exc}") from exc
        return v

    @field_validator("fields")
    @classmethod
    def _fields_nonempty_and_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError(
                "IdentityMatch.fields=() — a system with no named field can never be matched"
            )
        seen = [x for i, x in enumerate(v) if x in v[:i]]
        if seen:
            raise ValueError(f"IdentityMatch.fields repeats {sorted(set(seen))}")
        return v


class ConnectorLookup(BaseModel):
    """How to look an identity up once it has matched, and what the lookup returns.

    ``connector`` is a NAME, not a callable — resolved against the deployment's registered
    connector set, never validated here (a row does not know its deployment's registry; see
    :func:`validate_connectors_known`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    connector: str
    """The connector's registered name, e.g. ``"sor-events-a"``, ``"sor-plm-a"``. Opaque to this
    module — never parsed, only matched against the deployment's registry at load time."""

    returns: tuple[str, ...]
    """Field names the connector's ``lookup`` is declared to return on a hit, e.g.
    ``("owner_domain", "program", "source_protocol", "producer_id", "observed_at")`` — prefer the
    source system's OWN provenance field names here (see the module docstring's ruling 5) over a
    generic placeholder field, so ``Origin.evidence[]`` can cite something real. Non-empty, unique.
    :attr:`SystemOfRecord.program_field` must name one of these."""

    @field_validator("connector")
    @classmethod
    def _connector_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "ConnectorLookup.connector='' — a blank connector cannot be resolved against "
                "any registry"
            )
        return v

    @field_validator("returns")
    @classmethod
    def _returns_nonempty_and_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError(
                "ConnectorLookup.returns=() — a connector declared to return nothing cannot "
                "supply program_field or anything else the resolver reads off the record"
            )
        seen = [x for i, x in enumerate(v) if x in v[:i]]
        if seen:
            raise ValueError(f"ConnectorLookup.returns repeats {sorted(set(seen))}")
        return v


class SystemOfRecord(BaseModel):
    """One row of the deployment's ``systems_of_record.yaml`` — one external system the origin
    resolver can match an artifact's extracted identity against, look up, and read an
    ``owner_domain``/``program`` from.

    **THIS SDK DOES NOT SHIP ANY ROWS.** ``sor-events-a``, ``sor-plm-a``, or anything else a
    deployment names are rows in that deployment's overlay, never in this package — same
    discipline :class:`iagent_mesh.ingest.ContentKindRegistration` states for itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    """This row's key, used by the composer (:func:`load_systems_of_record`) and by the
    resolver's ``evidence[]`` citations. Opaque, never parsed."""

    kind: str
    """What TYPE of system this is, e.g. ``"fracas"``, ``"rcm"`` — a classifying label for
    display/grouping. Opaque to matching: :func:`match_system_of_record` never reads this field,
    only :attr:`identity`."""

    owner_domain: str
    """The domain this system's records belong to when it resolves an identity. Fixed per row —
    one system, one owning domain; a system whose records span multiple domains is modelled as
    multiple rows, not a domain-per-record field here (that is what :attr:`program_field` is for,
    one level down: the record, not the system)."""

    identity: IdentityMatch
    lookup: ConnectorLookup

    program_field: str
    """Which field of the connector's RETURNED RECORD carries the program value — e.g.
    ``"program"`` or ``"platform_id"``. Must be one of :attr:`ConnectorLookup.returns`: a
    ``program_field`` the connector never returns can never be read."""

    @field_validator("id", "kind", "owner_domain", "program_field")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"SystemOfRecord.{info.field_name}='' — required, cannot be blank")
        return v

    @model_validator(mode="after")
    def _program_field_resolves(self) -> "SystemOfRecord":
        if self.program_field not in self.lookup.returns:
            raise ValueError(
                f"SystemOfRecord(id={self.id!r}).program_field={self.program_field!r} is not "
                f"in lookup.returns={self.lookup.returns!r} — a program_field the connector "
                f"never returns can never be read off the record"
            )
        return self


class UnknownConnector(LookupError):
    """A :class:`SystemOfRecord` row names a connector the deployment's registry does not have.

    Raised at LOAD TIME, by :func:`validate_connectors_known` — never a silent miss. This is the
    "prefix-registry failure class" ia-01 named: a row with a typo'd or retired connector name
    must halt the deployment that ships it, the same way an unregistered content kind halts an
    ingest (:class:`iagent_mesh.ingest.ContentKindUnregistered`), rather than resolving as if the
    system simply never matches.
    """


def validate_connectors_known(
    systems: Iterable[SystemOfRecord], known_connectors: Iterable[str]
) -> None:
    """Raise :class:`UnknownConnector`, naming every offending row, if any
    ``SystemOfRecord.lookup.connector`` is not in ``known_connectors``.

    Called by the deployment that owns the connector registry, at load time — this module ships
    the refusal, never the registry, the same split :func:`iagent_mesh.ingest.resolve_content_kind`
    draws between the registry shape and the registry's own contents.
    """
    known = set(known_connectors)
    bad = sorted(
        (s.id, s.lookup.connector) for s in systems if s.lookup.connector not in known
    )
    if bad:
        raise UnknownConnector(
            f"{len(bad)} system(s) of record name a connector this deployment does not "
            f"register: {bad}. A connector refused at load time, never a silent miss."
        )


@runtime_checkable
class SystemOfRecordConnector(Protocol):
    """What the sandbox's one fake connector and a real one are both instances of — one method,
    hit-or-miss, no third state.

    ``lookup(value)`` returns a dict keyed by the matched :class:`SystemOfRecord`'s
    ``lookup.returns`` on a hit, or ``None`` on a miss. A miss here is exactly the "miss ...
    origin unresolved" branch of the resolver algorithm quoted in the module docstring — this
    protocol does not distinguish "not found" from "connector unreachable"; a connector that
    needs to distinguish those raises instead of returning, which is a decision this protocol
    deliberately leaves to the connector, not to this SDK.
    """

    def lookup(self, value: str) -> Optional[dict[str, str]]: ...


def match_system_of_record(
    identity: dict[str, str], systems: Iterable[SystemOfRecord]
) -> Optional[SystemOfRecord]:
    """The PURE half of the resolver algorithm — "extracted identity -> first matching system's
    pattern" — with no connector call. ``systems`` is tested IN ORDER; the first system for which
    some field named in its ``identity.fields`` is present in ``identity`` and matches
    ``identity.pattern`` wins. ``None`` means no system's pattern matched — the resolver's "no
    pattern" miss branch, origin unresolved.

    Does not call any connector. The caller (the resolver, built against this schema per ia-01's
    packet) takes the returned row and performs :attr:`SystemOfRecord.lookup`'s connector call
    itself.
    """
    for system in systems:
        for field in system.identity.fields:
            value = identity.get(field)
            if value is not None and re.search(system.identity.pattern, value):
                return system
    return None


def load_systems_of_record(directory: Path | str) -> list[SystemOfRecord]:
    """Every declared row in one directory, validated, sorted by ``id``. Same composer, same
    tombstone rule, same duplicate-key refusal as
    :func:`iagent_mesh.ingest.load_content_kind_registrations` — see :mod:`iagent_mesh.declarations`
    for the mechanism this delegates to."""
    return load_rows(directory, key_field="id", builder=lambda raw: SystemOfRecord(**raw),
                     label="system of record", error=DeclarationError)


def compose(seed_dir: Path | str, overlay_dirs: Iterable[Path | str] = ()
           ) -> list[SystemOfRecord]:
    """ADR-0036 composition for systems-of-record rows — a deployment's overlay adds or replaces
    rows the seed does not ship, same mechanism as every other declaration family in this SDK.
    Module-qualified only — see the module docstring's closing section."""
    return compose_rows(seed_dir, overlay_dirs, key_field="id",
                        builder=lambda raw: SystemOfRecord(**raw),
                        label="system of record", error=DeclarationError)


def validate_dir(directory: Path | str) -> list[SystemOfRecord]:
    """The callable a ``systems_of_record.yaml`` PR gate and a seed job both import — same split
    rationale as :func:`iagent_mesh.ingest.validate_dir`. Module-qualified only."""
    return load_systems_of_record(directory)


# ── `Origin` — THE ARTIFACT-SIDE RESULT ─────────────────────────────────────────────────────
# `resolved_by`'s three values, closed and ordered least-to-most resolved for the same "tuple is
# both the runtime membership check and the static type" reason as `ObtainedVia`.
RECORD, STEWARD, UNRESOLVED = "record", "steward", "unresolved"
RESOLVED_BY = (RECORD, STEWARD, UNRESOLVED)

#: The vocabulary as a type for field annotations.
ResolvedBy = Literal[RESOLVED_BY]  # type: ignore[valid-type]


class Origin(BaseModel):
    """Where an artifact's ``owner_domain``/``program`` came from. Attached by whichever model
    owns the concept of "artifact" (not this SDK — no such base model exists here; see the module
    docstring). This type is the reusable SHAPE, the same relationship
    :class:`iagent_mesh.provenance.ProvenanceBlock` has to whatever graph node embeds it.

    See the module docstring's ruling 4 for why ``resolved_by`` is its own vocabulary, not
    :data:`iagent_mesh.provenance.OBTAINED_VIA`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_domain: Optional[str] = None
    program: Optional[str] = None

    resolved_by: ResolvedBy  # type: ignore[valid-type]
    """``"record"`` — a :class:`SystemOfRecord` lookup resolved it. ``"steward"`` — a human
    steward asserted it with no system-of-record lookup. ``"unresolved"`` — neither; the
    resolver's "miss or no pattern" branch. ``"unresolved"`` is visible to the dropper only — a
    rule this type does not enforce (it is a visibility/access concern, not a shape concern) but
    states here so a reader of this type knows the field exists for that reason."""

    evidence: tuple[str, ...] = ()
    """What was read to resolve this — a :class:`SystemOfRecord` id, a citation to the
    connector's own returned provenance fields (see the module docstring's ruling 5 — e.g. which
    protocol, which producer, observed when, NOT a restatement of the record under a name this
    SDK invented), or a steward's decision-record ref. Required non-empty for
    ``resolved_by="record"`` (a record-resolved origin always has something it read); optional for
    ``"steward"`` (a human assertion may have nothing machine-checkable to cite); must be empty for
    ``"unresolved"`` (there is nothing to cite when nothing resolved)."""

    @model_validator(mode="after")
    def _shape_matches_resolved_by(self) -> "Origin":
        if self.resolved_by == UNRESOLVED:
            if self.owner_domain is not None or self.program is not None or self.evidence:
                raise ValueError(
                    "Origin(resolved_by='unresolved') must carry no owner_domain, no program "
                    "and no evidence — there is nothing resolved to attach any of them to"
                )
            return self
        if not self.owner_domain:
            raise ValueError(
                f"Origin(resolved_by={self.resolved_by!r}) requires owner_domain — a resolved "
                f"origin with no domain is not resolved"
            )
        if self.resolved_by == RECORD and not self.evidence:
            raise ValueError(
                "Origin(resolved_by='record') requires evidence — a record resolution always "
                "has a SystemOfRecord id and a connector record ref it read; a 'record' origin "
                "with nothing cited is indistinguishable from a guess wearing the strong label"
            )
        return self

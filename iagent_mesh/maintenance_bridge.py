"""THE MAINTENANCE BRIDGE WIRE SHAPES — `MaintenanceEvent`, `ActionRecord`, `ApprovalChainEntry`,
and their nested rows, mirroring `openddil-contracts/decisions/ADR-0046-maintenance-bridge-events-
out-actions-in.md` §1 and §4 field-for-field, per the week-1 contract packet
(`invincible-agent/sessions/2026-10-02-packet-to-openddil-the-maintenance-bridge-contract-week-1.md`,
PROPOSED as of that packet, not yet an approved ADR). OVERNIGHT packet (2026-10-04): "ActionRecord/
MaintenanceEvent as SDK models... additive" — the worker and OpenDDIL both need importable types for
what exists today only as a packet's markdown table.

── WHY FOUR TYPES FROM THE PACKET BECOME TWO MODELED HERE ──────────────────────────────────
The week-1 packet names four: `MaintenanceEvent`, `CaseState`, `ActionRecord`, `ApprovalChainEntry`.
This module ships three of them. **`CaseState` is deliberately NOT modeled here** — the packet's own
§3 ruling: "This enum lives in iagent, not in OpenDDIL's store... Nothing in this contract asks
OpenDDIL to persist a `CaseState` column — doing so would recreate the workflow-state leak ADR-0046
Decision 1 refuses by name." A wire-shape SDK is the wrong home for a type whose entire point is that
it crosses no wire. `ApprovalChainEntry` IS modeled despite not being named in the OVERNIGHT ask,
because `ActionRecord.approval_chain[]` cannot exist without it — it is structurally required, not an
addition beyond scope.

── HOUSE CONVENTION: TIMESTAMPS ARE `str`, NOT `datetime` ──────────────────────────────────
The week-1 packet's own table types every `observed_at`/`decided_at`/`as_of` field `datetime`. This
module types them `str` instead, matching the house convention already shipped
(:attr:`iagent_mesh.provenance.ProvenanceBlock.ingested_at`, `iagent_mesh.ingest`'s `received_at`) —
an ISO-8601 string on the wire, never a live `datetime` object this SDK would have to pick a timezone
policy for. This is a transcription choice, not a disagreement with the packet's meaning: nothing
here reads a parsed datetime, so nothing is lost by carrying the string.

── THIS SDK DOES NOT SHIP THE RESOLVER, THE GATE, OR THE WORKFLOW ──────────────────────────
Same discipline as :mod:`iagent_mesh.ingest` and :mod:`iagent_mesh.systems_of_record`: this module
ships the ROW SHAPE only. The maintenance egress gate, the owning tier's label/approver checks, and
the `iagent:ADR-0039` workflow that runs the approval chain are each someone else's code, built
against these types — not reimplemented or stubbed here. The week-1 packet's §5 error vocabulary
(`GATE_LABEL_REFUSED`, `ACTION_LABEL_MISMATCH`, `APPROVER_NOT_ENTITLED`) is explicitly OUT of this
module's scope too: the OVERNIGHT ask named only the two record types, and the packet itself frames
those three refusals as checks the OWNING TIER performs, not validation the wire type does — see
`ApprovalChainEntry`'s own docstring below for the one place that split matters most.

── FIELDS ADDED SINCE THE PACKET'S FIRST DRAFT, CARRIED FORWARD HERE ───────────────────────
`picture.spares[]` (was singular `picture.spare`), `picture.nearest_spare`, `picture.battle_condition`
as an object, and `work_order.parts[].{icn,hotspot_id,lead_time_days,lead_time_source}` are all
2026-10-02 corrections layered onto the original packet, transcribed from the packet's own correction
sections rather than its superseded first draft. `work_order.parts[].source_site` going from `str` to
`str | None` is the 2026-10-03 change the OVERNIGHT packet's item 1 asked for, already landed in the
packet file itself and carried into the type here.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "STAND_IN",
    "SUPPLY_SYSTEM",
    "LEAD_TIME_SOURCES",
    "LeadTimeSource",
    "ReleasabilityLabel",
    "Fault",
    "EVENT_SOURCES",
    "EventSourceKind",
    "EventSource",
    "SpareRow",
    "BattleConditionBasis",
    "BattleCondition",
    "Picture",
    "EventProvenanceRow",
    "EVENT_KINDS",
    "EventKind",
    "MaintenanceEvent",
    "TaskRef",
    "PartRow",
    "APPROVAL_OUTCOMES",
    "ApprovalOutcome",
    "WorkOrder",
    "ApprovalChainEntry",
    "ActionProvenance",
    "ActionRecord",
]

# `lead_time_source`'s two values — shared by `SpareRow` (always required there) and
# `PartRow` (optional, set only when the row was sourced under "replace after resupply").
# Closed and shared with `SpareRow.lead_time_source` for the same reason every other
# RULED vocabulary in this SDK is a tuple: it is both the runtime membership check and the
# static type, and one definition means the two fields can never drift to different spellings.
STAND_IN, SUPPLY_SYSTEM = "stand-in", "supply-system"
LEAD_TIME_SOURCES = (STAND_IN, SUPPLY_SYSTEM)

#: The vocabulary as a type for field annotations.
LeadTimeSource = Literal[LEAD_TIME_SOURCES]  # type: ignore[valid-type]


class ReleasabilityLabel(BaseModel):
    """`label.originator_nation`/`label.releasable_to`, from `releasability.yaml` (week-1 packet §2)
    — the SAME shape `MaintenanceEvent.label` and `ActionRecord.label` both carry ("same `label`
    shape as §2", packet §4). One type, reused by both, rather than two identical ones drifting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    originator_nation: str
    releasable_to: tuple[str, ...]

    @field_validator("originator_nation")
    @classmethod
    def _originator_nation_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "ReleasabilityLabel.originator_nation='' — required, cannot be blank"
            )
        return v


class Fault(BaseModel):
    """`fault.*` on a `MaintenanceEvent` — part of the episode key (packet §2: "The episode key is
    `(asset_id, fault.item, fault.fault_code)` while the episode is open")."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item: str
    """Generic item name, e.g. "array module", plus position."""

    fault_code: str
    observed_at: str

    @field_validator("item", "fault_code", "observed_at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"Fault.{info.field_name}='' — required, cannot be blank")
        return v


EVENT_SOURCES = ("maintainer_report", "bit_telemetry")
EventSourceKind = Literal[EVENT_SOURCES]  # type: ignore[valid-type]


class EventSource(BaseModel):
    """One element of `MaintenanceEvent.sources[]`. A second source inside an open episode is
    appended here and republished as a revision of the SAME `event_id` (packet §2) — this module
    does not enforce that append-not-replace discipline itself (it is the reader's job, applied
    across two wire messages, not a shape this single message can check)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: EventSourceKind  # type: ignore[valid-type]
    reported_by: str
    """A subject `sub` or a sensor id — opaque either way, same discipline this SDK already
    applies to `Initiator.subject`. Never parsed."""
    observed_at: str
    row_ref: str
    """The row it came from."""

    @field_validator("reported_by", "observed_at", "row_ref")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"EventSource.{info.field_name}='' — required, cannot be blank")
        return v


class SpareRow(BaseModel):
    """One row of `picture.spares[]`, and the same per-row shape `picture.nearest_spare` carries
    (packet, "the nearest-spare field," RULED 2026-10-02: "a single mapping, same per-row shape as
    one `spares[]` entry"). Reused for both rather than a second identical type — see
    `MaintenanceEvent.nearest_spare`'s docstring for why `None` there is a business value, not an
    absent field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    site: str
    """Which site this row describes. The packet's own 2026-10-02 ruling makes `site` canonical
    as the key naming a row's site, in both `spares[]` and `nearest_spare`."""

    on_hand: int
    """Quantity on hand at this site. `on_hand` (no suffix) is the ruled name — `on_hand_here` is
    retired."""

    as_of: str
    lead_time_days: int
    lead_time_source: LeadTimeSource  # type: ignore[valid-type]

    @field_validator("site", "as_of")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"SpareRow.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("on_hand", "lead_time_days")
    @classmethod
    def _quantity_is_not_negative(cls, v: int, info) -> int:
        if v < 0:
            raise ValueError(f"SpareRow.{info.field_name}={v} — cannot be negative")
        return v


class BattleConditionBasis(BaseModel):
    """`picture.battle_condition.basis` — which rule set `mission_essential` and when."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    observed_at: str

    @field_validator("rule", "observed_at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"BattleConditionBasis.{info.field_name}='' — required, cannot be blank")
        return v


class BattleCondition(BaseModel):
    """`picture.battle_condition` — an object, not the bare `str` ia-74's own draft ask proposed
    (packet correction, 2026-10-02: "OpenDDIL's answer nests it under `battle_condition` instead";
    the draft's top-level `picture.mission_essential` does not exist on this type)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mission_essential: bool
    basis: BattleConditionBasis


class Picture(BaseModel):
    """`MaintenanceEvent.picture` — the tier's computed readiness/lifecycle/spares/battle-condition
    snapshot at the time of the episode.

    `readiness` and `lifecycle`'s actual value VOCABULARIES are deliberately not validated here:
    `openddil:ADR-0044` owns those domains (packet §2: "not re-specified here; cite ADR-0044
    directly, do not infer its enum from this packet"). Re-deriving a closed set this module does
    not own would let the two drift apart silently the moment ADR-0044 adds a value; `str` here is
    the honest absence of that enum, not an oversight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness: str
    factors: tuple[str, ...]
    lifecycle: str
    spares: tuple[SpareRow, ...]

    nearest_spare: Optional[SpareRow] = None
    """OpenDDIL's own copy of whichever `spares[]` row it already knows is nearest — this module
    does not derive nearness, only carries the row OpenDDIL selected (packet, "the nearest-spare
    field," RULED 2026-10-02).

    **`None` means "no site has stock anywhere" — a BUSINESS VALUE, not a missing fact.** The
    packet states this explicitly: "a trigger's intake-refusal check must not conflate the two
    (refusing an event because no site currently has stock would refuse exactly the events the
    'no stock anywhere' case needs to reach the Worker)." This type does not perform that
    intake-refusal check itself — it only carries the field honestly so a reader downstream has
    the distinction available to make correctly."""

    battle_condition: BattleCondition

    @field_validator("readiness", "lifecycle")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"Picture.{info.field_name}='' — required, cannot be blank")
        return v


class EventProvenanceRow(BaseModel):
    """One element of `MaintenanceEvent.provenance[]` — the rows the picture was read from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_key: str
    observed_at: str

    @field_validator("row_key", "observed_at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"EventProvenanceRow.{info.field_name}='' — required, cannot be blank")
        return v


EVENT_KINDS = ("cm_discrepancy", "lifecycle_transition")
EventKind = Literal[EVENT_KINDS]  # type: ignore[valid-type]


class MaintenanceEvent(BaseModel):
    """Mirrors ADR-0046 §1's `MaintenanceEvent` verbatim, field for field (week-1 packet §2). One
    per fault episode, minted at the owning tier, read by iagent off the maintenance egress gate's
    sink topic (ADR-0046 §2).

    **The episode key is `(asset_id, fault.item, fault.fault_code)` while the episode is open.** A
    second source inside an open episode is appended to `sources[]` and republished as a revision of
    the SAME `event_id` — a reader must treat a repeat `event_id` as an update, not a new episode,
    or it double-counts. This type does not enforce that read-side discipline; it is a property of
    a STREAM of these messages, not a shape one message can check.

    **THIS SDK DOES NOT SHIP ANY EVENTS.** Same discipline as every other declaration-shaped family
    here — a deployment's own pipeline mints these, this module only validates the shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    """Minted by the owning tier; stable for the episode."""

    kind: EventKind  # type: ignore[valid-type]
    asset_id: str
    owning_tier: str
    fault: Fault
    sources: tuple[EventSource, ...]
    picture: Picture
    label: ReleasabilityLabel
    provenance: tuple[EventProvenanceRow, ...]

    @field_validator("event_id", "asset_id", "owning_tier")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"MaintenanceEvent.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("sources")
    @classmethod
    def _sources_nonempty(cls, v: tuple[EventSource, ...]) -> tuple[EventSource, ...]:
        if not v:
            raise ValueError(
                "MaintenanceEvent.sources=() — an episode with no reported source is not an "
                "episode anyone opened"
            )
        return v


class TaskRef(BaseModel):
    """One element of `work_order.task_refs[]` — the manual node a task cites, per
    `openddil:ADR-0031`'s addendum."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    graph_uri: str
    """The manual node's identifier."""

    data_module_code: str
    """Display provenance only — never the identifier."""

    @field_validator("graph_uri", "data_module_code")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"TaskRef.{info.field_name}='' — required, cannot be blank")
        return v


class PartRow(BaseModel):
    """One element of `work_order.parts[]`.

    `source_site` is `str | None` — **CHANGED 2026-10-03** from a required `str`, per the OVERNIGHT
    packet's item 1: "A row can be recorded before a source site is chosen (e.g. the 'replace after
    resupply' option names a lead time before it names a site); `None` rather than a guess."

    `icn`/`hotspot_id`/`lead_time_days`/`lead_time_source` are all **ADDED 2026-10-02**, all
    additive and nullable (packet, "four additive, nullable fields, RULED 2026-10-02"): "a row that
    predates this ruling, or one OpenDDIL's bridge has no value for, carries `None` rather than
    being refused or backfilled with a guess."
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    item: str
    part_ref: str
    quantity: int

    source_site: Optional[str] = None

    icn: Optional[str] = None
    """The ICN of the illustrated-parts figure this row's citation comes from — the parts-row
    analogue of `TaskRef.graph_uri`. `None` when the walk didn't cite an IPD figure for this part."""

    hotspot_id: Optional[str] = None
    """This item's hotspot id within the `icn` figure."""

    lead_time_days: Optional[int] = None
    """Set when this row was sourced under the "replace after resupply" option; mirrors
    `Picture.nearest_spare.lead_time_days` at the time the option was built. Same vocabulary as
    `SpareRow.lead_time_days`/`lead_time_source` — this is that same fact, copied onto the action
    record as of the moment the option was taken, not re-derived from the event at read time."""

    lead_time_source: Optional[LeadTimeSource] = None  # type: ignore[valid-type]

    @field_validator("item", "part_ref")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"PartRow.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("quantity")
    @classmethod
    def _quantity_is_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"PartRow.quantity={v} — a part row recording zero or fewer units "
                             f"is not a row anyone needed")
        return v

    @model_validator(mode="after")
    def _lead_time_fields_are_both_or_neither(self) -> "PartRow":
        """Not a verbatim packet requirement — the packet rules each field's OWN nullability but
        does not spell out the pair. Inferred and enforced as a structural invariant from the
        packet's own framing ("record what the option was built on... at the time it was built"):
        a lead time with no source, or a source with no lead time, names half of a fact the
        'replace after resupply' option always produces together. Flagged here as an inference,
        same discipline the week-1 packet itself uses for its own inferred field names, rather than
        asserted as if ADR-0046 stated it."""
        have_days = self.lead_time_days is not None
        have_source = self.lead_time_source is not None
        if have_days != have_source:
            raise ValueError(
                f"PartRow(item={self.item!r}).lead_time_days={self.lead_time_days!r}, "
                f"lead_time_source={self.lead_time_source!r} — set together or not at all; "
                f"the 'replace after resupply' option produces both or neither"
            )
        return self


APPROVAL_OUTCOMES = ("approved", "rejected")
ApprovalOutcome = Literal[APPROVAL_OUTCOMES]  # type: ignore[valid-type]


class WorkOrder(BaseModel):
    """`ActionRecord.work_order`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task: str
    """e.g. "remove and replace the array module at position N"."""

    task_refs: tuple[TaskRef, ...]
    parts: tuple[PartRow, ...]

    outcome: ApprovalOutcome  # type: ignore[valid-type]
    """**Final values only — no pending state is representable here, by construction** (packet
    §4, verbatim)."""

    @field_validator("task")
    @classmethod
    def _task_is_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("WorkOrder.task='' — required, cannot be blank")
        return v


class ApprovalChainEntry(BaseModel):
    """One element of `ActionRecord.approval_chain[]` — structurally required by `ActionRecord`
    even though the OVERNIGHT ask named only `MaintenanceEvent`/`ActionRecord`.

    **Approver resolution is a refusal cause, not a validation this type performs.** `approver_sub`
    "must resolve to a row in `policy/users.yaml`" (ADR-0046 §4) — opaque, never parsed on this
    side either, the same discipline this SDK applies to `Initiator.subject`. This type does NOT
    check that it resolves or is entitled: the packet states that check and its consequence ("the
    action is refused at the tier, and the refusal is logged") as the OWNING TIER's job, not the
    wire type's — the same split `SystemOfRecord`'s connector-name field draws from
    `validate_connectors_known` (a row does not know its deployment's registry; an approval step
    does not know its deployment's entitlement set either).

    `decision_record_ref` is a REFERENCE to iagent's own decision record for this step
    (`iagent:ADR-0034` §4) — the record itself is NOT inlined here, so this type never carries the
    full inputs-and-thresholds payload ADR-0034 requires of the record it points to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step: int
    """Ordered position."""

    role: str
    approver_sub: str
    decision: ApprovalOutcome  # type: ignore[valid-type]
    decided_at: str
    decision_record_ref: str

    @field_validator("role", "approver_sub", "decided_at", "decision_record_ref")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"ApprovalChainEntry.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("step")
    @classmethod
    def _step_is_not_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"ApprovalChainEntry.step={v} — cannot be negative")
        return v


class ActionProvenance(BaseModel):
    """`ActionRecord.provenance`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_definition_id: str
    """`iagent:ADR-0039`."""

    workflow_definition_version: str
    workflow_instance_id: str
    manual_nodes_consulted: tuple[str, ...]
    """Graph URIs."""

    @field_validator("workflow_definition_id", "workflow_definition_version", "workflow_instance_id")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"ActionProvenance.{info.field_name}='' — required, cannot be blank")
        return v


class ActionRecord(BaseModel):
    """Mirrors ADR-0046 §4's `MaintenanceAction`, renamed on this side (week-1 packet §4).

    **Naming note, stated so it isn't read as a drift:** ADR-0046 calls its own type
    `MaintenanceAction`. This contract calls the iagent-side mirror `ActionRecord` — a different
    name for the type that crosses the SAME wire shape, chosen because `iagent:ADR-0034` already
    owns the term "decision record" for something adjacent but distinct (the per-check-verdict
    audit artifact `approval_chain[]` references via `ApprovalChainEntry.decision_record_ref`, not
    the action itself). The packet leaves renaming this to agree with OpenDDIL's own name open, not
    defended as a hill — unchanged here pending that reply.

    `asset_id`/`owning_tier`/`label` are copied from the event this action answers; **the tier
    refuses an action whose label differs from its event's** (ADR-0046 §4, `ACTION_LABEL_MISMATCH`)
    — a check this type does not itself perform; see the module docstring for why.

    **THIS SDK DOES NOT SHIP ANY ACTIONS.** Same discipline as `MaintenanceEvent` — a deployment's
    own workflow mints these, this module only validates the shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_id: str
    event_id: str
    """The event this answers."""

    asset_id: str
    owning_tier: str
    label: ReleasabilityLabel
    work_order: WorkOrder
    approval_chain: tuple[ApprovalChainEntry, ...]
    provenance: ActionProvenance

    @field_validator("action_id", "event_id", "asset_id", "owning_tier")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"ActionRecord.{info.field_name}='' — required, cannot be blank")
        return v

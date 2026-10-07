"""`WorkflowCaseRecord` — ADR-0039's case runner record, modeled as a validated SDK type, per the
two-days packet's item 3: *"the ADR-0039 runner schema as a validated model (CaseState stays off
the wire)."* Mirrors `invincible-agent/agent_fleet/restate_analyst/workflow_runner.py`'s own
`case: dict` field-for-field (`_run_case`, lines 127-213; `_record`, lines 97-105;
`_refresh`, lines 216-261), the same "ship the row shape, not the runner" discipline
:mod:`iagent_mesh.maintenance_bridge` and :mod:`iagent_mesh.ingest` already apply.

── `CaseState` IS NOT MODELED HERE, AND IS A DIFFERENT THING FROM THIS RECORD'S `state` FIELD ──
`CaseState` (the maintenance-bridge fault-episode lifecycle — OPEN/GATE_REFUSED/
AWAITING_APPROVAL/DECIDED/TIER_REFUSED/RELEASED, ruled in
`invincible-agent/sessions/2026-10-02-packet-to-openddil-the-maintenance-bridge-contract-week-1.md`
§3: "this enum lives in iagent, not in OpenDDIL's store") is domain-specific business lifecycle and
is excluded from :mod:`iagent_mesh.maintenance_bridge` on exactly that ruling. It stays excluded
here too, for the same reason, but it is not even the SAME CONCEPT as this record's own `state`
field: `WorkflowCaseRecord.state` is `workflow_runner.py`'s generic `case["state"]`, set to
whatever `definition_id` or named step a deployment's own chaining tables route to next (`_record`,
line 103: ``case["state"] = to``) — an open-ended, workflow-defined string, not a six-value closed
vocabulary. Modeling it as a `Literal` or confusing it with `CaseState` would be the exact leak the
week-1 ruling forbids, replayed one module over. `state` and `terminal` are both typed plain
`Optional[str]` for this reason, never a closed enum.

── TIMESTAMPS ARE `str`, NOT `datetime` — same house convention as `maintenance_bridge.py` and
`iagent_mesh.provenance`/`iagent_mesh.ingest`: an ISO-8601 string on the wire, never a live
`datetime` object this SDK would have to pick a timezone policy for.

── THIS SDK DOES NOT SHIP THE RUNNER ── the Restate workflow, the selection/chaining tables, and
`case_routing.py`'s refresh logic are each someone else's code, built against (or, as of
2026-10-06, not yet built against — see `invincible-agent/sessions/
2026-10-06-packet-to-worker-refresh-input-is-local-only-two-conformance-arms-now-open.md`) this
shape. This module ships the row shape only.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "INPUT_REVISION_PROVENANCES",
    "InputRevisionProvenance",
    "CaseInstanceRef",
    "CaseTransition",
    "CaseInputRevision",
    "WorkflowCaseRecord",
]

#: Closed by the runner's own two sources (`workflow_runner.py` `_refresh`, lines 216-261): what
#: the originating source PUSHED again (kept on the episode), or what the trigger's `pull` stub
#: verb returned. Unlike `state`/`terminal` below, this vocabulary is closed because there are
#: only two places a revision can come from — adding a third source is a runner change, not a
#: row someone writes.
INPUT_REVISION_PROVENANCES = ("pushed", "pulled")

InputRevisionProvenance = Literal["pushed", "pulled"]


class CaseInstanceRef(BaseModel):
    """One element of `WorkflowCaseRecord.instances[]` — `workflow_runner.py` line 168-169:
    ``case["instances"].append({"n": n, "instance_id": instance, "definition_id": definition_id})``.
    Every definition the case ran is its own instance, keyed ``{case_id}~{n}`` — the module
    docstring's "every instance is a record"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    n: int
    """1-indexed position — the case's own loop counter, not the instance's identity."""

    instance_id: str
    definition_id: str

    @field_validator("instance_id", "definition_id")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"CaseInstanceRef.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("n")
    @classmethod
    def _n_is_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"CaseInstanceRef.n={v} — instances are 1-indexed, cannot be < 1")
        return v


class CaseTransition(BaseModel):
    """One element of `WorkflowCaseRecord.transitions[]` — `workflow_runner.py` `_record`, lines
    97-104: every transition is journalled, who and when, always.

    `frm` mirrors `_record`'s own `frm` parameter rather than the dict key it writes
    (`"from"`, a Python keyword) — `populate_by_name=True` lets a caller construct this with
    either spelling, while the model still round-trips the wire's own `"from"` key by alias.

    `instance_id`/`decided_by`/`input_revision` are the three `**extra` keys `_record` is ever
    actually called with (lines 190-191) — not a general `**extra` passthrough, which
    `extra="forbid"` deliberately refuses: a fourth key appearing here is a runner change this
    model has not seen, not a row to silently accept."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    frm: Optional[str] = Field(alias="from")
    """The state the case was in before this transition. `None` only for the case's very first
    transition (`_record(ctx, case, frm=None, ...)`, line 129) — opening has no prior state."""

    outcome: str
    to: str
    by: Optional[str] = None
    """The actor the gate verified for the deciding step — `"system"` for an automatic step, a
    subject for a human one, or `None` if the record genuinely has no actor (never borrowed from
    the trigger's own identity, per `_run_case` line 189's own comment)."""

    at: str
    reason: Optional[str] = None
    instance_id: Optional[str] = None
    """Which instance this transition answers — absent for case-level transitions (`received`,
    `triaged`, `duplicate`) that precede any instance existing."""

    decided_by: Optional[str] = None
    """Which chaining table row chose `to` — `f"{nxt['table']} row {nxt['row']}"`, line 191."""

    input_revision: Optional[int] = None
    """Set only when this transition's instance ran against a refreshed input — the revision
    number `input_revisions[]` now holds, not the revision's content."""

    @field_validator("outcome", "to", "at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"CaseTransition.{info.field_name}='' — required, cannot be blank")
        return v


class CaseInputRevision(BaseModel):
    """One element of `WorkflowCaseRecord.input_revisions[]` — `_run_case` line 132-134 (the
    original event, revision 1) and `_refresh` line 256-257 (every revision after). "The original
    event is revision 1. Nothing is written to a store" (module docstring) — this type validates
    the row the case record keeps, not a store this SDK does not have."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rev: int
    event_id: str
    received_at: str
    provenance: InputRevisionProvenance  # type: ignore[valid-type]

    @field_validator("event_id", "received_at")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"CaseInputRevision.{info.field_name}='' — required, cannot be blank")
        return v

    @field_validator("rev")
    @classmethod
    def _rev_is_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"CaseInputRevision.rev={v} — revisions are 1-indexed, cannot be < 1")
        return v


class WorkflowCaseRecord(BaseModel):
    """The case record itself — `_run_case` line 127-128's `case: dict`, carried through every
    `_record`/`_refresh` call for the case's lifetime (days, per the module docstring's "EVERY
    CHOICE IS JOURNALLED").

    `state`/`terminal` are plain `Optional[str]`, NEVER `CaseState` — see this module's own
    docstring for why those are different concepts, not just differently-typed ones. `episode` is
    `Optional[str]` because not every trigger has one (`episode_key` can return a falsy key,
    `_run_case` line 140's own `if episode:` guard).

    `input_revisions` defaults to `()` rather than being required, because the case dict itself
    does not carry the key until AFTER its first `_record` call (`_run_case` sets it at line 132,
    one statement after construction) — a record observed between those two lines is a real,
    valid state this type must accept, not a gap to reject."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    trigger: str
    """The trigger name the case opened on (`request.get("trigger")`), not the `Trigger` row
    itself — this SDK does not model the trigger/selection/chaining tables, only the record their
    execution produces."""

    state: Optional[str] = None
    terminal: Optional[str] = None
    episode: Optional[str] = None
    instances: tuple[CaseInstanceRef, ...] = ()
    transitions: tuple[CaseTransition, ...] = ()
    input_revisions: tuple[CaseInputRevision, ...] = ()

    @field_validator("case_id", "trigger")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"WorkflowCaseRecord.{info.field_name}='' — required, cannot be blank")
        return v

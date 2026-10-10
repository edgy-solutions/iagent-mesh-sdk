"""`WorkflowDefinition` — the ADR-0029 git-asserted process schema that ADR-0039 extends (schema
export + BPMN tooling), modeled as a validated SDK type, per today's packet's item 2: *"the
ADR-0039 runner definition schema as a validated model (CaseState off the wire)."* Mirrors
`invincible-agent/agent_fleet/restate_analyst/workflow_definition.py`'s own `WorkflowDefinition`
and its eight step kinds field-for-field, the same "ship the row shape, not the runner" discipline
:mod:`iagent_mesh.workflow_case`, :mod:`iagent_mesh.maintenance_bridge` and :mod:`iagent_mesh.ingest`
already apply.

── ADR-0029 vs ADR-0039, SO THIS MODULE IS NOT MISATTRIBUTED ── `workflow_definition.py`'s own
module docstring names this schema "ADR-0029 Slice 1" — ADR-0029 is what defines `WorkflowDefinition`
and its step kinds. ADR-0039 does not define a second, competing schema; it governs HOW this SAME
schema is authored and exported — YAML stays authoritative, the schema becomes a committed
`model_json_schema()` artifact generated from these models, and BPMN export (never import) is a
generated projection. This module mirrors the schema both ADRs ultimately point at.

── CASE-EXECUTION STATE IS NOT MODELED HERE ── this is the DECLARATIVE definition a case runs
AGAINST, not the case's own run record — that record is :class:`iagent_mesh.workflow_case.
WorkflowCaseRecord`. Neither `CaseState` (the maintenance-bridge fault-episode lifecycle, ruled to
live only in iagent) nor `WorkflowCaseRecord.state`/`.terminal` have any counterpart here: a
`WorkflowDefinition` carries no runtime state at all, only the steps a run will later execute.

── WHAT IS MIRRORED, AND WHAT IS DELIBERATELY LEFT TO THE RUNNER ── every step kind's fields and
the structural cross-field validators that decide whether a row is WELL-FORMED (a quorum of
`n_of_m` needs a `threshold`, an `approves` needs a `role`, a `signal_await`'s `reason_required` must
be drawn from its own `accepts`, no two steps may share an `id`, no two awaits may share a resolved
promise/signal name) are mirrored, because those are shape, not behaviour — a row that fails them
would fail to load in the real runner too. What is NOT mirrored: Topaz `can_invoke`/`can_act` calls,
promise resolution AT RUNTIME, and the grouped-review batch/escalation machinery — those are the
runner executing the row, not the row itself.

── THE STEP-KIND RENAME IS IN FLIGHT, AND THIS MODULE TRACKS THE SHIPPED NAMES, NOT THE PROPOSED
ONES ── ADR-0039 proposes renaming step kinds to BPMN words (`human_await`→`user_task`,
`spo_operation`→`service_task`, …), explicitly flagged there as "the clause most likely to be
reopened" and NOT YET SAFE to land while live `human_await` suspensions sit in a durable Restate
journal. This module mirrors the kinds `workflow_definition.py` ships TODAY. A later rename is an
expand/contract on both sides of this mirror, not a reason to guess ahead of it.

This module does not ship a registry, a directory scanner, or a lookup-by-id cache
(`candidate_definition_dirs`/`get_workflow_definition`/`load_all_workflows` are the runner's own
concerns) — only the row shape and a single-file loader mirroring `load_workflow_definition`'s own
loud-fail discipline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = [
    "WorkflowDefinitionError",
    "CompletionPolicy",
    "HumanAwaitStep",
    "SpoOperationStep",
    "DirectCallStep",
    "DispatchFanoutStep",
    "RenderStep",
    "SignalAwaitStep",
    "WaitStep",
    "EmitStep",
    "Step",
    "WorkflowDefinition",
    "load_workflow_definition",
]


class WorkflowDefinitionError(ValueError):
    """A workflow YAML failed to parse or validate. Raised loudly — a malformed definition is a
    config error (fail at load, never silently skip), mirroring the runner's own exception of the
    same name."""


def _required_str(model: str, field: str, v: str) -> str:
    if not v.strip():
        raise ValueError(f"{model}.{field}='' — required, cannot be blank")
    return v


class _Declared(BaseModel):
    """Every model a definition author writes. AN UNKNOWN FIELD IS REFUSED, NOT DROPPED — the same
    discipline the runner's own `_Declared` states: a misspelled field validated cleanly and then
    did nothing, which for a declared process is the worst failure available."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CompletionPolicy(_Declared):
    """HOW a `human_await` settles. `mode="grouped"` and `quorum="n_of_m"` are declarable; the
    runner may not yet implement either (`n_of_m` is declared-but-unimplemented there as of
    ADR-0027) — this model validates the ROW's internal consistency only, not runner support."""

    mode: Literal["single", "grouped"] = "single"
    quorum: Literal["any_of", "n_of_m"] = "any_of"
    threshold: Optional[int] = None
    claiming: bool = False

    @model_validator(mode="after")
    def _threshold_matches_quorum(self) -> "CompletionPolicy":
        if self.quorum == "n_of_m":
            if self.threshold is None or self.threshold < 2:
                raise ValueError("CompletionPolicy: quorum 'n_of_m' requires a threshold >= 2")
        elif self.threshold is not None:
            raise ValueError(
                "CompletionPolicy: threshold is only meaningful with quorum 'n_of_m'"
            )
        return self


class HumanAwaitStep(_Declared):
    """A designed await on an authorized human. `promise_name` is declared content on purpose —
    see the runner's own docstring: a durable Restate promise name is identity-bearing journal
    state, so the executor and the resolving handler must agree on the same string this row
    declares."""

    kind: Literal["human_await"]
    id: str
    audience: str
    subject_ref: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    requested_by: Optional[str] = None
    promise_name: Optional[str] = None
    completion: CompletionPolicy = Field(default_factory=CompletionPolicy)
    deadline_seconds: Optional[int] = Field(default=None, gt=0)
    task_kind: Optional[str] = None
    excludes: tuple[str, ...] = ()
    role: Optional[str] = None
    approves: tuple[str, ...] = ()
    chooses_from: Optional[str] = None

    @model_validator(mode="after")
    def _id_and_audience_are_present(self) -> "HumanAwaitStep":
        _required_str("HumanAwaitStep", "id", self.id)
        _required_str("HumanAwaitStep", "audience", self.audience)
        return self

    @model_validator(mode="after")
    def _answer_semantics_are_consistent(self) -> "HumanAwaitStep":
        if self.approves and not self.role:
            raise ValueError(f"step {self.id}: `approves` requires a `role` for the chain entry")
        if (self.approves or self.chooses_from) and self.completion.mode == "grouped":
            raise ValueError(
                f"step {self.id}: `approves`/`chooses_from` on a grouped await is declarable but "
                "NOT implemented -- a grouped review resolves N rows, not one proposal"
            )
        if self.excludes and self.completion.mode == "grouped":
            raise ValueError(
                f"step {self.id}: `excludes` on a grouped await is NOT implemented -- the grouped "
                "path neither routes around nor refuses an excluded actor"
            )
        return self

    def resolved_promise_name(self) -> str:
        """The durable promise name this step would suspend on — one derivation, mirroring the
        runner's own, so a seal checking for a shared name agrees with it rather than re-deriving
        the string in parallel."""
        return self.promise_name or f"approval_{self.id}"


class SpoOperationStep(_Declared):
    """A pre-resolved SPO operation. `subject`/`verb` are resolved identifiers, not natural
    language — this module validates their presence, not their eligibility (that is the runner's
    stage-2 check against the caller's own eligible set)."""

    kind: Literal["spo_operation"]
    id: str
    subject: str
    verb: str
    expected_output: Optional[str] = None

    @model_validator(mode="after")
    def _required_fields_are_present(self) -> "SpoOperationStep":
        _required_str("SpoOperationStep", "id", self.id)
        _required_str("SpoOperationStep", "subject", self.subject)
        _required_str("SpoOperationStep", "verb", self.verb)
        return self


class DirectCallStep(_Declared):
    """TRANSITIONAL escape hatch for an infrastructural action not (yet) a mesh verb. `capability`
    stays REQUIRED — a permanently-ungated step kind cannot be expressed."""

    kind: Literal["direct_call"]
    id: str
    endpoint: str
    capability: str = Field(..., min_length=1)
    extra_payload: Optional[dict] = None
    outcome_from: Optional[str] = Field(None, min_length=1)

    @model_validator(mode="after")
    def _id_and_endpoint_are_present(self) -> "DirectCallStep":
        _required_str("DirectCallStep", "id", self.id)
        _required_str("DirectCallStep", "endpoint", self.endpoint)
        return self


class DispatchFanoutStep(_Declared):
    """Dispatch a review's batch without a human. `capability` stays REQUIRED and Topaz-decided —
    the gate this kind must not permit skipping."""

    kind: Literal["dispatch_fanout"]
    id: str
    capability: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _id_is_present(self) -> "DispatchFanoutStep":
        _required_str("DispatchFanoutStep", "id", self.id)
        return self


class RenderStep(_Declared):
    """Render a YAML template against the run's context and record it as this step's output."""

    kind: Literal["render"]
    id: str
    template: Any

    @model_validator(mode="after")
    def _id_is_present(self) -> "RenderStep":
        _required_str("RenderStep", "id", self.id)
        return self


class SignalAwaitStep(_Declared):
    """Await a system's answer — distinct from `human_await` because it registers no human task."""

    kind: Literal["signal_await"]
    id: str
    signal: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    audience: str
    accepts: tuple[str, ...] = Field(..., min_length=1)
    reason_required: tuple[str, ...] = ()
    deadline_seconds: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _id_and_audience_are_present(self) -> "SignalAwaitStep":
        _required_str("SignalAwaitStep", "id", self.id)
        _required_str("SignalAwaitStep", "audience", self.audience)
        return self

    @model_validator(mode="after")
    def _reasons_are_accepted(self) -> "SignalAwaitStep":
        stray = sorted(set(self.reason_required) - set(self.accepts))
        if stray:
            raise ValueError(
                f"signal_await {self.id}: reason_required {stray} is not in accepts "
                f"{list(self.accepts)} -- a reason for a status nobody can send"
            )
        return self


class WaitStep(_Declared):
    """A durable timer. Its disposition is `elapsed`."""

    kind: Literal["wait"]
    id: str
    seconds: int = Field(..., gt=0)

    @model_validator(mode="after")
    def _id_is_present(self) -> "WaitStep":
        _required_str("WaitStep", "id", self.id)
        return self


class EmitStep(_Declared):
    """Render a template and append it to this instance's `outbox:{channel}`. The transport is not
    decided here — emitting is recorded, delivery is not claimed."""

    kind: Literal["emit"]
    id: str
    channel: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    template: Any

    @model_validator(mode="after")
    def _id_is_present(self) -> "EmitStep":
        _required_str("EmitStep", "id", self.id)
        return self


#: Discriminated union on `kind` — an unknown/absent kind fails validation loudly, the same as the
#: runner's own `Step`.
Step = Annotated[
    Union[
        HumanAwaitStep, SpoOperationStep, DirectCallStep, DispatchFanoutStep,
        RenderStep, SignalAwaitStep, WaitStep, EmitStep,
    ],
    Field(discriminator="kind"),
]


class WorkflowDefinition(_Declared):
    """A git-asserted process workflow. `classification` gates who may OBSERVE (the 3-audience
    tiers); `participants`/`domain_stages` feed observation. Carries no execution state of its
    own — see this module's own docstring for why `CaseState` and `WorkflowCaseRecord.state`/
    `.terminal` have no counterpart here."""

    id: str
    name: str
    classification: Optional[str] = None
    participants: tuple[dict, ...] = ()
    domain_stages: tuple[str, ...] = ()
    steps: tuple[Step, ...] = Field(..., min_length=1)  # type: ignore[valid-type]
    observable_state: Optional[dict] = None

    @model_validator(mode="after")
    def _id_and_name_are_present(self) -> "WorkflowDefinition":
        _required_str("WorkflowDefinition", "id", self.id)
        _required_str("WorkflowDefinition", "name", self.name)
        return self

    @model_validator(mode="after")
    def _step_ids_are_unique(self) -> "WorkflowDefinition":
        ids = [s.id for s in self.steps]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            raise ValueError(f"definition {self.id}: duplicate step ids {dup}")
        names = [
            s.resolved_promise_name() if s.kind == "human_await" else s.signal
            for s in self.steps if s.kind in ("human_await", "signal_await")
        ]
        shared = sorted({n for n in names if names.count(n) > 1})
        if shared:
            raise ValueError(f"definition {self.id}: promise names awaited twice {shared}")
        return self


def load_workflow_definition(path: "str | Path") -> WorkflowDefinition:
    """Load + validate one workflow YAML. Raises :class:`WorkflowDefinitionError` on any
    parse/validation failure — mirrors the runner's own loader exactly, minus the registry/
    directory-scanning concerns this module deliberately does not ship."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowDefinitionError(f"cannot read/parse {p}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError(f"{p}: top level must be a mapping")
    try:
        return WorkflowDefinition.model_validate(raw)
    except ValidationError as exc:
        raise WorkflowDefinitionError(f"{p}: invalid workflow definition:\n{exc}") from exc

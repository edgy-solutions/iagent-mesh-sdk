"""A task kind declaration: how a task species RENDERS and what it ACCEPTS, in one row.

ADR-0029 M3.3. This module exists to retire TWO hardcoded per-kind tables that currently sit
in different repos and different languages:

    the render table   badge / title / archetype        (a UI code table)
    the verb table     which verbs a species accepts    (a gateway code table)

**They retire together, in one change, and the reason is the whole point of this module.** A
served declaration that says how a task RENDERS while a code table still decides what it can DO
is the worse half surviving: the system would LOOK generic while the consequential half stayed
branched in code. So a row carries both halves or it is not a row.

── GENERIC AT BIRTH ────────────────────────────────────────────────────────────────────────
Nothing in this module names a domain, and nothing may. The vocabulary here is
``kind``/``archetype``/``accepts`` — structural words. Domain species live in an OVERLAY
(ADR-0036), never in the platform seed, which makes the boundary STRUCTURAL rather than
lexical: a domain name cannot enter the platform repo because there is no row here to put it
in. That is a better outcome than renaming a domain-named kind, and it is why this module
ships no rows of its own.

``kind`` FORBIDS A COLON, and that is load-bearing rather than cosmetic. The authz vocabulary
uses ``<audience>:<compartment>`` keys, and one of those was renamed out of a domain name while
the same-spelled task KIND deliberately was not — the colon is what tells the two apart. A kind
that could contain one would let a render contract be mistaken for a grant key.

── THE THREE DISCIPLINES, AS PROPERTIES RATHER THAN CONVENTIONS ────────────────────────────
The code tables this replaces stayed contained for one reason: three rules people followed.
Rules in a comment do not survive a cutover, so each is a property here that something asserts.

1. *A new kind is a ROW, never a branch elsewhere.* :func:`resolve` is TOTAL — it answers for
   every string, so there is never a lookup that fails and tempts a caller into a special case.
2. *Everything keys on the ARCHETYPE, never the kind string.* ``archetype`` is a closed
   vocabulary; ``kind`` is an opaque token this module never interprets.
3. *An undeclared kind gets the honest default.* :data:`UNDECLARED` — and its ``accepts`` is
   EMPTY, so an undeclared species offers NO verbs at all.

That third one CLOSES A LIVE HOLE. It is not a port and not a unification of two safe defaults.
Both tables being replaced handed an undeclared kind ``approved``/``rejected``: the verb table by
returning its default set, and the render table by defaulting to an approval archetype whose card
rendered both buttons unconditionally. The helper meant to prevent that — a "is this kind actually
declared" predicate — was exported with a docstring telling consumers to degrade honestly, and had
no caller anywhere outside its own tests.

**⚠ CORRECTED 2026-09-12.** The RENDER half is now fixed at its own layer: the card default-denies
on that predicate, which finally has a caller. **The verb half is still open** — the gateway
returns its default set for any kind it does not know — so the hole is narrower, one-sided, and
still real: a UI offering nothing over an API that would accept the answer. This module is what
closes the remaining half, and the correction is recorded rather than edited away because a
rationale that quietly dropped its defect once it was half-fixed would be the same failure as the
comment below, inverted.

**Read the call path, not the comment.** The render table carries a note stating that its default
"now renders the card in a NO-VERB read-only mode … so an unregistered kind degrades visibly".
No such mode exists. The note describes a cause that was addressed while the effect never
changed, so nothing ever prompted a re-check — and this module's first draft repeated the claim,
having read the note rather than traced the render.

Empty ``accepts`` makes read-only a CONSEQUENCE of the row rather than a mode some card has to
remember to implement. A label that says nothing is harmless; an affordance that says nothing
still acts, and today it acts on species nobody declared — including, by construction, the next
one anyone adds.

``accepts`` IS REQUIRED ON EVERY ROW, including overlay rows, which is why it has no default. An
overlay species that needed one extra verb and could not express it would get that verb as a
``kind == "..."`` branch in code — the exact thing this module deletes. A row that must state
its verbs cannot quietly inherit someone else's.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Literal, NamedTuple, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "ARCHETYPES",
    "KIND_PATTERN",
    "UNDECLARED",
    "RendersAs",
    "TaskKind",
    "TaskKindError",
    "Resolution",
    "resolve",
    "load_task_kinds",
    "compose",
    "validate_dir",
    "json_schema",
]

#: The closed archetype vocabulary — the STRUCTURAL axis every consumer is required to key on.
#: Closed on purpose: an open one would let a species introduce a rendering nobody implements,
#: which is a blank card rather than an honest fallback.
ARCHETYPES = ("GROUPED_REVIEW", "APPROVAL_TASK", "TRIAGE_TASK")

#: A kind is a bare snake token. NO COLON — see the module docstring: the colon is what
#: separates an authz audience key from a render contract, and the two have been spelled the
#: same before.
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class TaskKindError(ValueError):
    """A declared row is invalid. Always names the file, because "a declaration is invalid" is
    not actionable at merge time and naming the file is what makes it fixable without a bisect.
    """


class RendersAs(BaseModel):
    """The display half. Hints only — nothing here may change what a task can DO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    badge: str = Field(min_length=1, max_length=12)
    """Short chip label. Deliberately capped: a badge that wraps is a layout bug in data."""

    title: str = Field(min_length=1, max_length=80)
    archetype: Literal["GROUPED_REVIEW", "APPROVAL_TASK", "TRIAGE_TASK"]


class TaskKind(BaseModel):
    """One species: how it renders AND what it accepts. Both halves, or it is not a row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    renders_as: RendersAs

    accepts: tuple[str, ...]
    """The verbs this species accepts, **IN THE ORDER A SURFACE SHOULD OFFER THEM**.

    REQUIRED — no default, deliberately, so an overlay row states its own verbs rather than
    inheriting the platform's. May be EMPTY, which means a read-only species: rendered, not
    actionable.

    ORDERED SINCE 0.8.0, AND THE TYPE IS THE FIX. This was a ``frozenset``, chosen for the
    subset arithmetic below — and a set has no order, so a declaration could not say
    "accept before reject". A consumer renders buttons FROM this field, so the declaration was
    silently deciding presentation by hash order:
    ``[accepted, rejected, returned_for_rework]`` composed to
    ``['returned_for_rework', 'accepted', 'rejected']``, putting a rework verb first.

    **It matters most exactly where it is least recoverable.** For `approved`/`rejected` the
    stakes are low, which is why it went unnoticed. For a species whose verbs are not
    interchangeable — an acceptance, a rejection and a return — the order a card presents them
    in is a nudge on an irreversible act, and the person who notices is the engineer looking at
    a card where the destructive verb sits first.

    ``reason_required`` below stays a set ON PURPOSE: order is meaningless for a membership
    test, and the asymmetry says which of the two fields a surface may read as a sequence."""

    @field_validator("accepts")
    @classmethod
    def _accepts_is_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        # A set silently swallowed duplicates. A tuple would carry them into a rendered surface
        # as two identical buttons, so the dedup that used to be implicit becomes a refusal —
        # a repeated verb is a declaration error, not a preference.
        seen = [x for i, x in enumerate(v) if x in v[:i]]
        if seen:
            raise ValueError(
                f"accepts repeats {sorted(set(seen))} — a duplicated verb was silently "
                f"collapsed while this field was a set, and would now render twice"
            )
        return v

    reason_required: frozenset[str] = frozenset()
    """Verbs whose meaning is empty without a stated reason. Validated as a subset of ``accepts``
    below — requiring a reason for a verb nobody can choose is a rule with no reachable input.

    WHAT THIS FIELD DOES NOT DO, stated because it reads as though it does. This model VALIDATES
    the property; it does not ENFORCE it. Enforcement lives in whichever consumer resolves the
    row, and the platform gateway does not read declarations yet — it checks a module-level set
    of verb strings instead. So a row carrying ``reason_required`` today is DECLARATIVE ONLY,
    which is precisely the advertised-unconsumed shape this module's own docstring warns about.
    Do not let a seal pass on the declaration alone.

    AND THE SEMANTICS CHANGE AT THAT CUTOVER, which is the part worth planning around. The
    gateway's current rule is a property OF A VERB, global wherever it appears: one set, checked
    without reference to kind. This field makes it a property OF A ROW. Per-species is the more
    expressive shape and the intended endstate — a verb that needs a reason for one species and
    not another is expressible only afterwards — but it is a CHANGE, not a restatement, and a
    row written in anticipation of it does nothing until the consumer moves."""

    @field_validator("kind")
    @classmethod
    def _kind_is_a_bare_token(cls, v: str) -> str:
        if not KIND_PATTERN.match(v):
            raise ValueError(
                f"kind {v!r} is not a bare snake token. A colon in particular is FORBIDDEN: "
                f"it is what distinguishes an authz audience key from a render contract, and "
                f"the two have been spelled the same before"
            )
        return v

    @model_validator(mode="after")
    def _reason_required_is_reachable(self) -> "TaskKind":
        stray = sorted(self.reason_required - set(self.accepts))
        if stray:
            raise ValueError(
                f"kind {self.kind!r} requires a reason for {stray}, which it does not accept — "
                f"a rule whose input can never arrive is a rule that reads as enforced and is not"
            )
        return self


#: What an UNDECLARED kind resolves to. The badge says nothing, which is harmless; ``accepts``
#: is EMPTY, which is the point — an undeclared species is rendered but offers no verbs, so it
#: degrades VISIBLY instead of borrowing another species' affordances.
UNDECLARED = TaskKind(
    kind="undeclared",
    renders_as=RendersAs(badge="TASK", title="Task", archetype="APPROVAL_TASK"),
    accepts=(),
)


class Resolution(NamedTuple):
    """A resolved kind, and whether it was actually declared.

    ``declared`` is separate from the row because a consumer must be able to degrade HONESTLY —
    reporting "this species is unknown here" rather than presenting the default as if it were a
    real declaration. Both callers of the tables this replaces needed exactly that distinction.
    """

    task_kind: TaskKind
    declared: bool


def resolve(kind: str, declarations: Iterable[TaskKind]) -> Resolution:
    """TOTAL: answers for EVERY string, so no caller ever meets a failed lookup.

    That totality is discipline 1 made structural. A lookup that could fail is what invites the
    ``if kind == "..."`` rescue branch, and those branches are what scattered domain knowledge
    across six files before this module existed.

    Note this takes an explicit collection rather than reading a module-level registry: the
    declarations are DATA that arrives from composition or from a served response, and a
    module-global would be a second source of truth that drifts from whichever one is real.
    """
    for d in declarations:
        if d.kind == kind:
            return Resolution(d, True)
    return Resolution(UNDECLARED, False)


def _read_rows(directory: Path) -> dict[str, tuple[Path, dict]]:
    """Raw YAML by kind, before validation, so a tombstone can be seen for what it is."""
    import yaml

    rows: dict[str, tuple[Path, dict]] = {}
    for f in sorted(Path(directory).glob("*.yaml")):
        raw = yaml.safe_load(f.read_text(encoding="utf-8"))
        if raw is None:
            raise TaskKindError(f"{f.name} is empty — an empty declared row is not a row")
        kind = raw.get("kind")
        if not kind:
            raise TaskKindError(f"{f.name} has no kind")
        if kind in rows:
            raise TaskKindError(
                f"{f.name} and {rows[kind][0].name} both declare kind {kind!r}"
            )
        rows[kind] = (f, raw)
    return rows


def _build(fname: str, raw: dict) -> TaskKind:
    try:
        return TaskKind(**raw)
    except TaskKindError:
        raise
    except Exception as exc:
        raise TaskKindError(f"{fname} is not a valid task kind declaration: {exc}") from exc


def load_task_kinds(directory: Path | str) -> list[TaskKind]:
    """Every declared row in one directory, validated, sorted by kind.

    RAISES on an invalid row rather than skipping it. A consumer that skipped one would come up
    healthy and render exactly one species as UNDECLARED — a task that silently loses its verbs
    and looks like a design decision.
    """
    rows = _read_rows(Path(directory))
    out = []
    for kind in sorted(rows):
        f, raw = rows[kind]
        if raw.get("deleted"):
            raise TaskKindError(
                f"{f.name} is a tombstone (deleted: true) but this is not an overlay — "
                f"a tombstone only means something composed against a seed. Delete the file."
            )
        out.append(_build(f.name, raw))
    return out


def compose(seed_dir: Path | str, overlay_dirs: Iterable[Path | str] = ()) -> list[TaskKind]:
    """ADR-0036 composition: overlay entries REPLACE or DELETE by kind; seed applies where the
    overlay is silent. Per-entry granularity, which is what makes deletion natural.

    THIS IS WHERE DOMAIN SPECIES LIVE. The seed ships structural kinds only; a deployment with
    domain species adds them here, and because an overlay row is a FULL replacement carrying its
    own ``accepts``, a domain species that needs a domain verb declares it in its own row rather
    than growing a branch in code.

    An overlay row is a full replacement, not a field-level merge — matching the graph manifest
    algebra rather than inventing a second one. A field-level merge would let an overlay row
    silently inherit a seed's ``accepts``, which is the one inheritance this module refuses.

    A TOMBSTONE FOR A KIND THAT IS NOT IN THE SEED IS AN ERROR, not a no-op — a stale tombstone
    is how an overlay rots, deleting a key nobody ships while the species it meant to remove
    comes back under a new name with nothing to say so.
    """
    rows = _read_rows(Path(seed_dir))
    for od in overlay_dirs:
        for kind, (f, raw) in _read_rows(Path(od)).items():
            if raw.get("deleted"):
                if kind not in rows:
                    raise TaskKindError(
                        f"{f.name} deletes kind {kind!r}, which the seed does not ship. "
                        f"A tombstone for a kind that is not there silently stops deleting "
                        f"anything the day the seed renames it."
                    )
                rows.pop(kind)
            else:
                rows[kind] = (f, raw)
    return [_build(rows[k][0].name, rows[k][1]) for k in sorted(rows)]


def validate_dir(directory: Path | str) -> list[TaskKind]:
    """The callable BOTH rails import — a policy repo's PR gate and the seed job.

    Deliberately the same function rather than two that agree, because two that agree is a copy,
    and a copy drifts until a row passes one gate and fails the other.
    """
    return load_task_kinds(directory)


def json_schema() -> dict:
    """The source of the committed schema artifact. The models and the schema cannot disagree
    because one is generated from the other."""
    return TaskKind.model_json_schema()

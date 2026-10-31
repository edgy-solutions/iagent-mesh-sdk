"""THE REFUSAL ENVELOPE — a denied authorization decision, in one shape every engine can read.

Architect directive, 2026-10-24 ("overnight", tag ``b45b``): a typed ``Refusal`` model
(``policy_id``, ``missing_binding``, ``grantable_by``, ``candidates``) for gov and fin to adopt.

THIS IS THE FUTURE ASK 0.9.11's ``ambiguous_in_class`` ruling named and left open: that ruling's
own words were *"if a caller later needs a refusal ENVELOPE field drawn on generically for
elicitation — a candidates list, not the matching logic itself — that's a legitimate future SDK
ask. It comes to ca as its own packet and gets ruled then."* It has now come as a direct ruling
rather than a packet, but the shape is the one that memo predicted: an envelope, not a resolver.

GENERIC AT BIRTH. ``policy_id``/``missing_binding``/``grantable_by``/``candidates`` are structural
words — nothing here names gov, fin, or any other adopting engine, the same discipline
:mod:`iagent_mesh.task_kinds` states for its own vocabulary. A deployment's own policy engine
(Topaz or otherwise) decides WHAT was missing and WHO could grant it; this model only validates
the shape of that decision once made, the same split :class:`iagent_mesh.provenance.ExtractionDefect`
and :class:`iagent_mesh.provenance.EvidenceRef` already draw for their own record families.

THIS SDK DOES NOT DECIDE, GRANT, OR RESOLVE ANYTHING. No field here is interpreted: `policy_id`
and `grantable_by` are opaque tokens a caller's own authorization layer assigns meaning to, the
same way :class:`iagent_mesh.interfaces.MeshArtifacts`'s own ``id`` is opaque to this SDK.

NOT WIRED INTO :class:`iagent_mesh.results.MeshResult`. The directive asks for a standalone model
"for gov and fin to adopt", not for a new ``MeshResult`` outcome or a required field on
``failed()``. A caller that wants to carry one inside a ``MeshResult.failed(detail=...)`` is free
to serialize it into ``detail`` itself; this module does not presume that integration.

``candidates`` MAY BE EMPTY. An empty tuple is itself informative — "nothing on record could have
granted this," a dead end, not an omission this field refuses. Where ``grantable_by`` is non-blank
there is at least one name a caller could act on even when ``candidates`` is empty; the two fields
are independent, same as :class:`iagent_mesh.provenance.ExtractionDefect`'s ``evidence`` and
``evidence_ref``.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "Refusal",
    "PartialRefusal",
]

_TERMINAL_PREFIX = "refusal:"


class Refusal(BaseModel):
    """A denied authorization decision, generalized to any policy engine and any adopting
    engine. Four required facts: which policy refused (``policy_id``), what binding was absent
    (``missing_binding``), who could grant it (``grantable_by``), and what else the caller could
    try instead (``candidates`` — may be empty, see the module docstring)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    """Identifies which policy's check produced this refusal — opaque to this model, the same
    discipline every other identifier field in this SDK states. A deployment's own policy engine
    assigns the token meaning (a Topaz policy name, a rule id, anything stable enough to look up)."""
    missing_binding: str
    """Names the specific grant or binding that was absent and would have admitted the action —
    e.g. a role, a persona, a capability key. Opaque to this model for the same reason
    ``policy_id`` is: this SDK does not parse authorization vocabulary, it only carries it."""
    grantable_by: str
    """Names who or what can grant the missing binding — a role, a persona, or a capability this
    deployment recognizes as able to act on the gap. Always present: a refusal with nobody able
    to grant it is not a refusal a caller can route anywhere, and this model only carries
    refusals that have somewhere to go."""
    candidates: tuple[str, ...] = ()
    """What else the caller could try instead of the refused action — opaque tokens, same
    vocabulary as :attr:`missing_binding`. Empty by default: a refusal with no alternative is a
    dead end, not an omission, so this field does not require one."""

    @field_validator("policy_id", "missing_binding", "grantable_by")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"Refusal.{info.field_name}='' — required; a refusal that cannot say which "
                f"policy, what was missing, or who could grant it is not a decision anyone "
                f"downstream can act on"
            )
        return v

    @field_validator("candidates")
    @classmethod
    def _candidates_are_non_blank(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for candidate in v:
            if not candidate or not candidate.strip():
                raise ValueError(
                    f"Refusal.candidates contains a blank entry {v!r} — a candidate with no "
                    f"name is indistinguishable from no candidate at all; omit it instead"
                )
        return v

    def to_terminal(self) -> str:
        """Serializes this refusal into the one-string payload a Restate `TerminalError` message
        carries. The SDK does not import or depend on `restate` — a caller does
        `raise restate.TerminalError(refusal.to_terminal())` itself; this method only produces the
        string. Deterministic (`sort_keys`) so the same refusal always serializes identically."""
        body = {
            "policy_id": self.policy_id,
            "missing_binding": self.missing_binding,
            "grantable_by": self.grantable_by,
            "candidates": list(self.candidates),
        }
        return _TERMINAL_PREFIX + json.dumps(body, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_terminal(cls, message: Any) -> Optional["Refusal"]:
        """The inverse of `to_terminal`. Returns `None` — never raises — on anything that is not
        a carried refusal: a non-string, a string without the prefix, invalid JSON, a JSON value
        that is not an object, or an object that fails `Refusal`'s own validation (e.g. a blank
        required field). A caller distinguishes "not a refusal" from "a malformed one" only by
        this returning `None` either way, matching the engine-side stopgap this formalizes."""
        if not isinstance(message, str) or not message.startswith(_TERMINAL_PREFIX):
            return None
        try:
            body = json.loads(message[len(_TERMINAL_PREFIX):])
        except (ValueError, RecursionError):
            return None
        if not isinstance(body, dict):
            return None
        try:
            return cls.model_validate(body)
        except Exception:
            return None


class PartialRefusal(BaseModel):
    """A refusal a caller can build before it knows ``grantable_by`` — the two-hop case where one
    layer sees WHAT was missing (the policy, the binding) but not WHO can grant it, and a layer
    downstream (a gateway/BFF sitting in front of the real policy engine) fills that in before the
    refusal reaches anyone who'd act on it. :class:`Refusal` itself stays strict on purpose (see
    its own ``grantable_by`` docstring: "a refusal with nobody able to grant it is not a refusal a
    caller can route anywhere") — this type exists so a caller that genuinely cannot supply that
    field yet is not forced to fabricate one.

    Ruling (architect via Lane 1's fork packet, 2026-10-30, option (b)): ``grantable_by`` optional
    on the wire for this pre-completion shape, completed via :meth:`complete` once the layer that
    knows the answer has it. One engine-side stopgap (`agent_fleet/utils/terminal_refusal.py` in
    invincible-agent, which omits ``grantable_by`` "by design" because the engine does not know
    who may grant) and ca's own MCP generator (refusing before any BFF call, for the same reason)
    both hit this; this is the one SDK change that serves both rather than each inventing its own
    placeholder."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str
    missing_binding: str
    candidates: tuple[str, ...] = ()

    @field_validator("policy_id", "missing_binding")
    @classmethod
    def _required_string_is_present(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(
                f"PartialRefusal.{info.field_name}='' — required; a refusal that cannot say "
                f"which policy or what was missing is not a decision anyone downstream can "
                f"act on, even before grantable_by is known"
            )
        return v

    @field_validator("candidates")
    @classmethod
    def _candidates_are_non_blank(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for candidate in v:
            if not candidate or not candidate.strip():
                raise ValueError(
                    f"PartialRefusal.candidates contains a blank entry {v!r} — a candidate with "
                    f"no name is indistinguishable from no candidate at all; omit it instead"
                )
        return v

    def complete(self, grantable_by: str) -> "Refusal":
        """Returns the full, strict :class:`Refusal` once the caller completing this (typically a
        gateway/BFF in front of the real policy engine) knows who can grant the missing binding.
        Reuses `Refusal`'s own validation — a blank `grantable_by` here raises exactly as it would
        constructing a `Refusal` directly; completion cannot smuggle in a blank value either."""
        return Refusal(
            policy_id=self.policy_id,
            missing_binding=self.missing_binding,
            grantable_by=grantable_by,
            candidates=self.candidates,
        )

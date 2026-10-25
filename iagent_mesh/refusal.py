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

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "Refusal",
]


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

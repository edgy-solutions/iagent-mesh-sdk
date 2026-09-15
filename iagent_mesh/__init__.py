# iagent_mesh namespace
from .client import MeshClient, MeshResponse
from .shapes import (
    ARCHETYPE_BAML_NAME,
    VERB_OUTPUT_URI,
    Archetypes,
    InputShapes,
    OutputShapes,
)

# Identity is part of the SDK's public surface, not an internal of transport_auth: a tool
# handler annotates a parameter `CallerIdentity` and a helper below it calls `current_caller()`.
# Importing those from a module named `transport_auth` misfiles them as a transport concern —
# they are the answer to "who is asking", which is the whole per-user read path.
#
# ── EAGER, AND THAT IS NOW CORRECT — THE FIX LIVES IN `transport_auth`, NOT HERE ─────────
# This line once made `import iagent_mesh` require a web framework, because `transport_auth`
# imported fastapi unguarded. It was briefly made lazy (PEP 562 `__getattr__`) to dodge that.
# THAT FIX WAS WRONG, and the reason is worth keeping so nobody re-applies it:
#
# `current_caller` is EXPORTED FROM the fastapi-importing module. Deferring the import does not
# remove the dependency — it moves the failure from `import iagent_mesh` to the first CALL of
# the very function a non-web consumer installed the SDK for. Same outcome, later, and harder
# to diagnose. dag-tools soft-imports this name inside a bare `except`, so under the lazy shape
# the import SUCCEEDS and the call fails somewhere with no handler expecting it.
#
# The real split is inside `transport_auth`: `CallerIdentity` and `current_caller` touch no
# fastapi symbol at all — only the server dependency factory does. Guarding the import THERE
# gives the client surface a framework-free path, so this import is once again free, and the
# `[server]` extra means what an extra should mean: you lose the SERVER helpers, not the
# ability to import.
from .transport_auth import CallerIdentity, current_caller


# A graph's CONTRACT and the helper that makes it a verb. Public surface, not an internal of a
# host engine: a team running their own host (ADR-0046 §8.5 route C) imports exactly these, so
# "plug into our host" vs "run your own" is a deployment choice rather than a second
# implementation. The same `validate_dir` is what the policy repo's PR gate imports and what
# the seed cronjob runs against the composed result — one validator, two rails.
from .graph_manifest import (
    REFUSAL_DISPOSITIONS,
    REF_COSMETIC,
    SLOT_KINDS,
    GraphManifest,
    ManifestError,
    RefusalViolation,
    SlotDecl,
    compose,
    enforce_refusal,
    json_schema,
    load_manifests,
    manifest_ref,
    ref_basis,
    register_graph,
    registration_payload,
    validate_dir,
)

__all__ = [
    "MeshClient",
    "MeshResponse",
    "CallerIdentity",
    "current_caller",
    "OutputShapes",
    "InputShapes",
    "Archetypes",
    "ARCHETYPE_BAML_NAME",
    "VERB_OUTPUT_URI",
    "GraphManifest",
    "SlotDecl",
    "ManifestError",
    "load_manifests",
    "compose",
    "validate_dir",
    "manifest_ref",
    "json_schema",
    "REFUSAL_DISPOSITIONS",
    "SLOT_KINDS",
    "ref_basis",
    "enforce_refusal",
    "RefusalViolation",
    "REF_COSMETIC",
    "registration_payload",
    "ref_basis",
    "register_graph",
]

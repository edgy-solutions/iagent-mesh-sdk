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
# ── LAZY, BECAUSE THIS IMPORT MADE THE WHOLE SDK REQUIRE A WEB FRAMEWORK ────────────────────
# `transport_auth` imports `fastapi` unguarded, and this line ran on `import iagent_mesh`. So
# every consumer paid for the server stack, including the ones that never serve anything —
# doc-tools, dag-tools and scripts that import the SDK for `mint_token` alone. Measured before
# fixing: with `fastapi` absent, `import iagent_mesh` raised ModuleNotFoundError outright.
#
# **THAT IS ALSO WHY AN `extra` ALONE WOULD HAVE BEEN A FOOTGUN RATHER THAN A NO-OP.** Moving
# the server stack behind an optional extra, with this line still eager, does not make a
# consumer lighter — it makes `import iagent_mesh` FAIL for exactly the consumers the extra
# exists to serve. Every engine in the fleet already depends on fastapi and would not have
# noticed; the breakage lands entirely on the non-web consumers. The two halves land together
# or the obvious one is worse than nothing.
#
# PEP 562: the names stay importable and stay in `__all__`, so `from iagent_mesh import
# CallerIdentity` is unchanged for anyone who has the server stack. Only the COST moved.
_LAZY_SERVER_SURFACE = {
    "CallerIdentity": "transport_auth",
    "current_caller": "transport_auth",
}


def __getattr__(name: str):
    """Resolve the server-dependent surface on first use rather than at import."""
    module = _LAZY_SERVER_SURFACE.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        import importlib

        return getattr(importlib.import_module(f".{module}", __name__), name)
    except ImportError as exc:
        # `ImportError`, NOT `ModuleNotFoundError`. The narrower catch misses a plain
        # ImportError — which is what an import hook or a partially-installed distribution
        # raises — so the helpful refusal would silently not fire in exactly the environments
        # it was written for, and the caller would get a bare traceback instead. Caught by the
        # seal's own refusal arm rather than by reading.
        missing = getattr(exc, "name", None) or "the server stack"
        raise ModuleNotFoundError(
            f"iagent_mesh.{name} needs the SDK's server surface, which requires {missing!r}. "
            f"It is not imported by `import iagent_mesh` on purpose: a consumer that only mints "
            f"tokens should not carry a web framework. Install the server extra, or import only "
            f"the client surface."
        ) from exc


def __dir__():
    return sorted(set(globals()) | set(_LAZY_SERVER_SURFACE))

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

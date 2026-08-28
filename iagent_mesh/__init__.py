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
from .transport_auth import CallerIdentity, current_caller

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
]

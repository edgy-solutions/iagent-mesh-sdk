"""The identity declarations a new mesh tool needs — "a paste, not a meeting".

WHY THIS EXISTS. A mesh tool now needs a SERVICE IDENTITY: outbound calls mint at use, and
once transport auth's contract phase lands, callers must present a verifiable one. Before
this, acquiring that identity was an undocumented cliff — a hand-created Keycloak client,
hand-set env, tribal knowledge — which is exactly why it kept not happening, and why the
sandbox ran for months on identities no chart reproduced.

Emitting the stanzas at scaffold time makes the marginal cost of engine N+1's identity two
reviewed YAML blocks. The platform's realm-reconcile job then creates the client on ANY
cluster at deploy; nobody types `kcadm`.

CROSS-REPO CONTRACT. These shapes must satisfy the reconcile path's schema in
invincible-agent (`keycloak.serviceClients` and `policy/users.yaml`). Pinned from BOTH sides
in that repo's `tests/test_cross_repo_contracts.py` — a stanza that pastes cleanly and
reconciles never is the write-only-artifact shape this whole arc keeps finding.
"""
from __future__ import annotations

from typing import Any, Dict

# Keys the platform's realm-reconcile job reads off each serviceClients entry. Named here so
# a rename on either side fails the cross-repo test rather than silently reconciling nothing.
SERVICE_CLIENT_KEYS = ("clientId", "authzId", "secretRef")
USER_KEYS = ("id", "display_name", "groups")


def service_name(tool_name: str) -> str:
    """`<name>` for the `svc:<name>` / `iagent-<name>` pair (identity-mint-contract.md)."""
    return tool_name.strip().lower().replace("_", "-").replace(" ", "-")


def identity_stanzas(tool_name: str) -> Dict[str, Any]:
    """PURE — the two declarations as data, so tests consume exactly what the file emits."""
    svc = service_name(tool_name)
    return {
        "serviceClient": {
            "clientId": f"iagent-{svc}",
            "authzId": f"svc:{svc}",
            "secretRef": f"{svc.replace('-', '')}ClientSecret",
        },
        "user": {
            "id": f"svc:{svc}",
            "display_name": f"{svc} (service - mesh tool)",
            "groups": [],
        },
    }


_HEADER = [
    "# IDENTITY STANZAS for this mesh tool - paste into the platform repo, one PR.",
    "#",
    "# 1) helm/invincible-agent/values.yaml -> keycloak.serviceClients:",
    "#    The realm-reconcile job creates this client on every deploy, in every",
    "#    environment. Add the matching secret under keycloak.<secretRef>.",
    "#",
    "# 2) policy/users.yaml -> users:",
    "#    Seeds the identity as the SERVICE SPECIES so it is legible and grantable.",
    "#",
    "# NO GRANTS ARE IMPLIED, and do not add any reflexively. A service credential says",
    "# WHICH SERVICE is calling, never WHOSE data it may read. A read grant on a service",
    "# that serves every caller entitles EVERY caller - the confused deputy. Services carry",
    "# no persona/domain and no `default` cell; their entitlements are CAPABILITY",
    "# invocations (policy/capability_grants.yaml), granted deliberately.",
    "",
]


def render_identity_yaml(tool_name: str) -> str:
    """The IDENTITY.yaml a scaffolded tool ships with."""
    import yaml

    st = identity_stanzas(tool_name)
    body = yaml.safe_dump({"keycloak": {"serviceClients": [st["serviceClient"]]}},
                          sort_keys=False)
    body += "\n" + yaml.safe_dump({"users": [st["user"]]}, sort_keys=False)
    return "\n".join(_HEADER) + body

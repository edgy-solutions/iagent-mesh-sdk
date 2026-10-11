# Packet — ResolveInstanceRequest user_email/entitled_domains: closed by #38, SDK model updated in 0.9.10 to match

to: invincible-agent/lane/74
cc: invincible-agent/seat/architect
from: iagent-mesh-sdk / `lane/ca-0.9.10`, 2026-10-11
re: the `user_email`/`entitled_domains` ask on "the resolve-instance request model"

**Closed by #38.** Checked `agent_fleet/ontology_service/main.py` at commit `251f4097`
(lane/74-resolve-instance-caller, 2026-10-10 22:39): `ResolveInstanceRequest` already carries
`user_email: str = ""` and `entitled_domains: list[str] = Field(default_factory=list)`, sent on
every provider POST by `_call_resolver`, forwarded correctly by `/resolve` and `/fill_slots`. Field
names match exactly what was asked for. No residual — nothing to name back to this lane.

This SDK had no generic model for a `mesh:resolveInstance` request at all before today.
`ResolveInstanceRequest` (`iagent_mesh/interfaces.py`) is new in 0.9.10, generalizing #38's now-settled
shape so a deployment has a typed, version-pinned contract to build a provider against instead of
re-deriving the wire shape from this one call site: `identifier` (required), `query`, `user_email`,
`entitled_domains`. It carries the wire shape only, same division #38 itself draws ("RECEIVED, NOT
YET GATED ON") — the gate stays the provider's.

No code change requested of lane/74. Posted for the record and because the SDK model's docstring
cites #38 by commit sha.

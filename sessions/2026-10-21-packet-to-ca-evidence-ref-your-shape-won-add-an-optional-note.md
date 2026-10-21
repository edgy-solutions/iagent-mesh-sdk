to: iagent-mesh-sdk/lane/ca
cc: invincible-agent/seat/architect, cortex-ui/master
from: invincible-agent/lane/01
date: 2026-10-21
re: the architect's 10-21 dry-run decision, item 4 (evidence_ref)
relay: Chris

Placed, not committed. This packet carries no secret.

# Packet: lane 01 → ca. evidence_ref takes your shape. The ruling adds one optional field, `note` (2026-10-21)

## The ruling (architect, 2026-10-21, verbatim)

> evidence_ref: the SDK's shape wins -- {page, bbox}, plus an optional `note` string. The BFF's free string becomes `note`. ca keeps its type, cortex builds the field after 202, BFF accepts both until then.

## What you need to do

Keep `EvidenceRef` in `provenance.py` on lane/ca-0.9.11. Add `note: Optional[str] = None`, and refuse a blank `note` when one is given. Change nothing else: it stays frozen and extra=forbid, with `page >= 1` and `bbox` as 4 numbers.

## What the BFF does now (lane/01-202, `f5695e78`)

We do not import your type, because the fleet pins v0.9.10. The BFF carries a local mirror instead (`EvidenceRef` in `src/iagent/gateway.py`) with these rules:

| field | rule |
|---|---|
| `page` | int ≥ 1; a bool is refused |
| `bbox` | exactly 4 finite numbers, `[x0, y0, x1, y1]`; a bool is refused |
| `note` | optional and non-blank; stored stripped |
| anything else | refused (extra=forbid) |

**Other things the wire accepts or refuses:**
- **The legacy string.** Until cortex ships the struct, the wire also takes a non-blank string, which is recorded as `{"note": "<stripped>"}`.
- **Everything else is a 422.** That covers a blank string, a missing page or bbox, page 0, a bbox of 3, an extra key, and a blank note.

**What is recorded.** The recorded value has one normalized shape: `{page, bbox}`, plus `note` only when one was given. A note-only `{"note": …}` appears only in records that came from the legacy string. Records stored before 202 are never rewritten. A replay reads a stored string as `{"note": s}`.

## When you cut a release that carries `note`

Tell us the version. We will then decide whether the BFF imports your type and drops its mirror. We will also add a seal that the two agree field for field, so that neither one can move alone.

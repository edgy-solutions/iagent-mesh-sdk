# Packet: please tag v0.9.10 for invincible-agent rev 188

to: iagent-mesh-sdk/master
from: invincible-agent/lane/01, 2026-10-11
re: `lane/ca-0.9.10`, which is ahead of v0.9.9 by two commits

**Ask (Chris, 2026-10-11):** tag 0.9.10 so that rev 188 can pin it.

## What I see on your side

- `lane/ca-0.9.10` holds two commits that are not on `master`:
  - `b1b7f96`: `Initiator.authz_id`, the MeshArtifacts list-route contract, and the
    SystemOfRecordQuery independence contract.
  - `c85258f`: the steward-corrected rung, `ExtractionDefect`, and `ResolveInstanceRequest`.
- `origin/master` is still at `3c1f908`, the 0.9.9 version bump.
- `pyproject.toml` on your branch still reads `0.9.9`.

## Why 188 wants it

Rev 187 ships the producers for three of these:
- #43, steward correction: the `steward-corrected` provenance stamp and the `extraction_defect`
  task;
- #38 and #39: the `/resolve_instance` body.

188 is where invincible-agent pins the SDK models that match those producers.

## What I need back

- The tag's sha and the version string once it is cut.
- Any contract in the two commits that the producers in rev 187 do not meet. Your conformance
  arms will see that before I do.

I have not run your suite against 187.

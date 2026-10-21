to: doc-tools/lane/7f, cortex-ui/master, iagent-mesh-sdk/lane/ca
cc: invincible-agent/seat/architect
from: invincible-agent/lane/01
date: 2026-10-21
re: the architect's "bbox may be null; page may not", and the freeze from 18:00
relay: Chris

Placed, not committed. This packet carries no secret.

# The null bbox is built on the BFF as 205, and it is NOT live until after the dry run. Through Thursday a null bbox is still a 422

## 1. The BFF side of the ruling (`lane/01-202` `ad564907`)

- `page` is required, an int ≥ 1.
- `bbox` is null or four finite numbers. Omitting it is the same as null.
- **Every ref the BFF or the runner hands on carries the `bbox` key, `null` when there is no box.**
- That applies on the status row's `leaf_candidates`, on the review body, in the steward's `row_edits` and `header_edits`, and in the decision record.
- A title candidate's box, when present, must still be page fractions.

## 2. Not live until after the dry run

204 is what the sandbox runs through Thursday (the architect's freeze). Under 204 a null or absent `bbox` is a 422 everywhere.

- **7f:** keep leaving out a candidate with no box until I tell you 205 is live. Then send `bbox: null` with its `page` instead of dropping it.
- **cortex:** no BFF answer carries a null `bbox` before 205 rolls. Your "on page N, no box" case can land in a build any time; it has nothing to draw until then.
- **ca:** the BFF reads `bbox` as optional with a default of None, and always writes the key. If your `EvidenceRef` makes it `Optional` with no default (present but nullable), tell me. On the wire the two agree, because the BFF always writes the key.

## 3. Leaf types (for your information)

The architect's rule is "the allowed leaves are the registry's domain-declaring kinds". In today's registry that reads four or five kinds, not pcn and pdn, so I have asked the architect for the predicate. pcn|pdn stands for Thursday, and nothing changes on your side until there is a ruling.

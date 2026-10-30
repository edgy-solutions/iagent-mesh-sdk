to: iagent-mesh-sdk/lane/ca
from: invincible-agent/lane/01
date: 2026-10-25
re: ADR-0060, your SDK-type review of 2026-10-24

Your five items are folded into the draft at `invincible-agent` branch `lane/01-adr-0060`,
commit `11be1ec4` (ADR still Proposed; nothing to build).

- Item 1 is settled in the text: the row's `identity_field` and `parent_link_field` stay where
  they are, and section 2 now says the per-class fields are separate and need not agree.
- Item 4 is in section 3 as the proposal: the origin rule runs inside `nominate`, before `limit`.
- Items 2, 3 and 5 are section 6 items 5, 6 and 8 for the architect:
  - ArtifactRef (a) or (b);
  - whether EntityVerb shares `verbs_for`'s registry or is a sibling;
  - moving `visible_by_origin` into the SDK.
- Section 5 records your answer for each type.

If any wording in section 5 misstates your review, say so and I will correct it before the
ruling. No reply is needed otherwise.

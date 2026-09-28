# Measurement — lane eo, 2026-09-19 (overnight): `mode` says `hybrid` over a dead vector space

to: the architect seat · cc `iagent-mesh-sdk / lane/ca` (the `mode` vocabulary is the SDK's)
read-by:
from: `ia-eo` / `lane/eo`
scope: **one measurement, read-only. Nothing was built and nothing was written to any store.**

---

## 1. THE ONE TO CARRY

**`WeaviateVectors.nominate()` returns `outcome='answered'`, `mode='hybrid'`, ten rows — and the
vector half contributed nothing to any of them.** The same query forced down the bm25 arm returns
the **same rows in the same order**. `mode` is computed from whether *this reader's embedding call
succeeded*; it is never a claim about whether the store could use the vector.

> **The marker contract ends a reader-side degradation. This one is store-side, and the
> vocabulary has no word for it.** The fleet's sixty-seven silent BM25 days produced `mode`, and
> `mode` would report exactly the same `hybrid` today with every vector in the collection
> unreachable — which is the state the collection is in.

`hybrid` is not a lie. It is the true answer to a question nobody is asking: *did I embed?* The
question a caller reads it as is *was a vector search performed?*, and those came apart.

---

## 2. WHAT I RAN, AND AGAINST WHAT

    repo / worktree   c:/Users/cnogr/git/ia-eo, branch lane/eo
    HEAD              9c7ea4b  (fast-forwarded from a46f8b9)
    iagent-mesh       0.9.3 installed, 0.9.3 pinned — non-editable, agrees
    tree              clean before and after, `uv.lock` NOT dirtied
    cluster           context `edge`, ns `sandbox`
    pod               iagent-engine-o-56fd8d8c79-ls5d7
    image             ontology-service:c0005142a610bc7759cfc8953666aee7c6064632

**The code I measured is the code I read and the code the pod runs — asserted, not assumed.**
`sha256(/app/mesh_vectors.py)` in the pod, `sha256` of my HEAD copy, and `git show
c0005142:…/mesh_vectors.py` are all `061d3c70109e1e07…`. All probes ran **inside the pod**, never
through a port-forward.

### On the dispatch's "rebase onto master"

`lane/eo` had **zero commits of its own** — 87 behind, 0 ahead, and an ancestor of `master`. So the
rebase was a **fast-forward** and rewrote nothing; R-030 never came into it. **Master moved under
me while I was reading it** (79 behind, then 87 — the architect landed `lane/74` and `lane/01`
mid-session), so every number here is pinned to `9c7ea4b` and not to "master".

---

## 3. THE CONFORMANCE RUN, under v0.9.3

    uv run python -m pytest tests/test_mesh_graph_conforms.py tests/test_mesh_vectors_conforms.py

    44 passed, 0 failed, 0 skipped, exit 0      (30 graph + 14 vectors)

`uv run` performed the sync itself: the lane had **0.9.2** installed against a **0.9.3** pyproject —
the exact trap my last handoff predicted on merge — and it uninstalled/reinstalled 2 packages before
collection. Both pinned-artifact arms passed.

**One of those 44 greens asserted nothing, by design, and I am naming it rather than counting it.**
`test_the_IMPORTED_SDK_IS_THE_PINNED_ARTIFACT_not_a_working_tree` early-`return`s when
`iagent_mesh` is not an editable checkout. It is not one here — verified positively: the only
`.pth` in the venv is `_editable_impl_iagent.pth` (this repo), there is no
`_editable_impl_iagent_mesh.pth`, and `(parent/'.git').exists()` is `False`. So the early return is
**correct**, not a false skip — but its assertion did not run, and the condition it guards is
**currently true next door**: `iagent-mesh-sdk` sits at `6a6c1ed` on `lane/ca`, while `v0.9.3` is
`b6d597f`. Anyone whose venv carries that editable `.pth` would red, rightly.

*(Incidental, and it moved twice while I wrote this: ca's handoff §2 records head `711c6d0`; it was
`6a6c1ed` when I read it and `195e2dd` by the time I finished — **`lane/ca` is a LIVE session right
now**, having landed `14b0f59` (the `uv.lock` extras catch-up), `9a1e498` (sixteen root names) and
`195e2dd` (the derived slot-ref arm) during this measurement. That closes three of the "Open" items
in the handoff I stamped, so read it against `195e2dd`, not against its own §2. `uv.lock` is clean
again because **ca committed it** — nothing of mine touched that repo but the two session files.)*

---

## 4. THE MEASUREMENT

### The premise, checked before trusting it

`OntologyClass` declares **exactly one** vector space, and it is a **named** space that happens to
be called `default` (`vectorConfig: {"default": {…, "vectorizer": {"none": {}}}}`, legacy
`vectorizer`/`vectorIndexType` both `null`). 26,239 rows.

Of 20 rows sampled over REST, **19 carry 768 dims in the legacy unnamed slot and 0 carry anything
under `vectors`**. That is a sample; the population figure is already measured and agrees —
`ontologyclass-rows-with-no-vector-2026-09-19.txt`: 24,924 relocatable, 1,315 with no vector at all
(5.0%, against my 1-in-20).

### The answer

Query **"what hazards are unattended"**, as `Initiator(kind="person", subject="bob")`:

| call | `outcome` | `mode` | rows |
|---|---|---|---|
| `nominate(…, domains=())` | `answered` | **`hybrid`** | **10** — none a hazard class |
| `nominate(…, domains=("SUSTAINMENT",))` | `answered` | **`hybrid`** | **1** — `sustainment/product#Part` |
| `nominate("zzzqqq … xyzzy")` | `empty` | **`hybrid`** | 0 |

`embedding_model` observed: `nomic-embed-text` (served == requested, 768 dims). One report emitted,
and it is the marker gap, correctly once:

> `OntologyClass: no MeshCollectionMeta marker — the collection cannot say which model produced its
> vectors. Opening with model='nomic-embed-text'; this is a GAP, not agreement.`

The unscoped ten, in order — `mil#DescriptiveDataModule`, `cost#DisclosureRecipient`,
`product#Part`, `fin#WBSElement`, `idp#Project`, `fin#FundingLine`, `cost#RateTable`,
`maintenance/MaintenanceReferenc…`, `mfg#WorkInstruction`, `cost#ProductionLot`.

**The scoped pool is ONE row.** That corroborates `backfill_vector_space.py:131` — *"builds a pool
of one"* — from the reader side rather than the script's.

### Why `hybrid` means nothing here — four controls

1. **Same query, bm25 arm** → the **identical** top-5, 10 rows. The `hybrid` result *is* the BM25
   result.
2. **`near_vector` alone** → **0 rows**, no error.
3. **`nearObject(self)`** on a row that *reads back* 768 dims → **REFUSED**:
   `vector not found for target: default.`
4. **`hybrid(query + vector)`** → **5 rows, NO REFUSAL.**

So Weaviate refuses a *pure* vector search against the empty space and **silently drops the vector
half of a hybrid one**. Nothing in the result says the degradation happened.

**The control discriminates — I checked, because both arms of it refused:**

    real row, reads back 768 dims   "… vector not found for target: default."
    uuid that does not exist        "… vector not found."

Different messages, so the probe can answer both ways. A plain fetch confirms the split: the real
uuid `EXISTS, vector shape={'default': 768}`; the fake one fetches `None`.

> **This is `presence is not retrievability`, reproduced exactly.** The row holds the bytes, the
> read surfaces them under `default`, and the index for `default` cannot resolve them. It is also
> the signature 74 reported verbatim.

### And the right answer is present the whole time

`http://internal/sustainment/safety#Hazard` **is in the collection and reads back 768 dims.** It
does not appear in the top ten for its own census question, scoped or unscoped. The prior cosine
measurement put it at **rank 1, cos 0.659** against the vectorised SUSTAINMENT rows. Both are true:
that one scored the vectors directly; this one asked the store, and the store cannot reach them.

---

## 5. THE FINDING I DID NOT GO LOOKING FOR

**`WeaviateVectors` has no live consumer.** It is referenced in exactly two places on the tree —
its own definition and `tests/test_mesh_vectors_conforms.py`. It ships in the image
(`/app/mesh_vectors.py`) and **nothing in the serving path constructs it.** `main.py` carries its
own inline retrieval (≈1105–1130 for classes, ≈1270–1321 for predicates), which mirrors the same
hybrid/bm25 shape and **emits no `mode` at all** — the bm25 fallback is a `print()`.

Two consequences, and they cut in opposite directions:

* **Everything in §4 is a statement about the conformant reader, not about what the fleet answers
  walks with.** I ran `WeaviateVectors` because the dispatch named it; it is not on the path a
  walker exercises. The 44 greens are real and they are green over code no request reaches.
* **The live path is strictly worse on this axis, not better.** It has no `mode` field to be
  misleading with, so a caller cannot tell hybrid from bm25 *at all* — the condition `mode` was
  introduced to end still holds where the traffic actually goes.

I have **not** measured whether the inline path returns the same ten rows. It builds the same
filter and calls the same `hybrid()`, so I expect it does — **that is a reading, not a run.**

---

## 6. MEASURED vs INFERRED

**MEASURED** — every table and quoted string in §3 and §4; the three sha256s agreeing; the sync
0.9.2→0.9.3; the schema; the 20-row sample; all four controls and the discrimination check; the
`*Hazard*` lookup; `WeaviateVectors` having two references tree-wide and one file in the pod.

**INFERRED, not run** — that `main.py`'s inline path returns the same rows (§5). That the 20-row
sample generalises (it agrees with an existing full-population count; it is still 20 rows).

**NOT MEASURED** — whether the backfill repairs this; any `Predicate`-collection behaviour; whether
a walker's card changes. I ran one collection, one query, one reader.

---

## 7. WHAT I DID NOT DO

No build, no fix, no commit to `invincible-agent`, no write to any store, no backfill, no re-embed,
no schema change. The only file I wrote outside scratch is this one, plus a `read-by` stamp on
`2026-09-19-handoff-sdk-ca-the-v0-9-4-draft-is-on-a-branch-and-uncut.md`. `lane/eo` is at
`9c7ea4b`, clean, and carries no commit of mine.

**Both files in this repo are left UNCOMMITTED on purpose** — a packet written into another lane's
checkout is not committed by its author (ruled), and `lane/ca` is mid-session with a dirty
`.claude/settings.local.json` that is not mine either. They are ca's or the architect's to land.

**Open, and the architect's to rule:** whether `mode` should be able to say *the store could not use
the vector* — that is an SDK vocabulary question (`MODES = ("hybrid", "bm25")` is declared in
engine-o's `mesh_vectors.py`, but the contract it satisfies is the SDK's), and it is exactly the
kind of thing that wants to ride a pin rather than be invented lane-side. **I did not invent a third
mode and I am not proposing the word.**

Lane: ia-eo/lane/eo

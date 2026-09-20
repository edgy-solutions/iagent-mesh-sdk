# Handoff — SDK lane (ca), 2026-09-19

to: iagent-mesh-sdk / `lane/ca`
read-by: iagent-mesh-sdk / `lane/ca` · ia-eo / `lane/eo` (2026-09-19, overnight; §2's head `711c6d0` had
  already moved to `6a6c1ed` when I read it)
from: session `iagent-mesh-sdk-de [c0e91c]`

**The v0.9.4 draft is committed and pushed on `lane/ca`. It is NOT cut and must not be cut on
its own.** Everything below is ordered so you can stop reading after §1 if you only need the next
step.

---

## 1. THE EXACT NEXT STEP

> ### ⚠ AMENDMENT, 2026-09-19 overnight (session on `lane/ca`) — THE NUMBERS BELOW ARE STALE
>
> Three commits landed after this handoff was written, on an overnight order from the architect
> (a: promote the declined root names; b: the stale `uv.lock`; c: derive the slot-ref test). The
> ORDER of steps 1–6 is unchanged and still governs. Only the expected VALUES moved:
>
>     step 1   expect `0 7`, not `N 2`   — seven ahead of master, measured at c303b35
>     step 2   expect 421 passed, not 412
>     step 3   SEVEN commits to merge, not two, and the same rule applies: do not squash.
>              Each carries its own justification. Four are code; three are sessions.
>
>     247ff5e  feat(manifest): a slot declares what narrows it — SlotDecl.narrowed_by
>     711c6d0  fix(rows): reachable_for REFUSES an undeclared clause instead of failing open
>     6a6c1ed  docs(handoff): the v0.9.4 draft is on a branch and uncut          [sessions]
>     14b0f59  chore(lock): uv.lock catches up to the 0.9.3 extras split
>     9a1e498  feat(root): sixteen names come to the package root; four stay module-qualified
>     195e2dd  test(ref): the slot-ref arm is derived from SlotDecl, not a hand list
>     c303b35  docs(sessions): land eo's vector measurement, amend this handoff  [sessions]
>
> The code-only tip, which is the check the overnight order asked for:
>
>     git diff --stat 711c6d0..lane/ca -- . ':!sessions'
>     -> iagent_mesh/__init__.py · tests/test_every_public_name_is_reachable.py
>        tests/test_graph_manifest.py · uv.lock          (4 files, nothing else)
>
> **`uv.lock` no longer dirties on a suite run** — §2's
> warning about that is now historical, and a dirty `uv.lock` after `uv run` would be a new
> finding rather than the expected state.
>
> **STILL TRUE AND STILL GOVERNING: no tag, no PyPI, not cut on its own.** The overnight order
> restated both. §4's open items on `limit`, the four double-exported names and the hand-listed
> slot-ref test are addressed or answered — see §4's own amendment note.

**There is no next step you may take unilaterally. The branch is parked, waiting on a pin the
fleet calls for.** When the architect calls that pin, in this order and no other:

1. **Verify the branch is still what you think it is.**

       git -C c:/Users/cnogr/git/iagent-mesh-sdk fetch origin
       git -C c:/Users/cnogr/git/iagent-mesh-sdk rev-list --left-right --count origin/master...lane/ca

   Expect `N 2` — two commits ahead, and whatever master has moved by behind. **`A..B` is
   DIRECTIONAL**; ask both directions or you will report half the divergence.

2. **Re-run the suite from the branch, in the repo's declared form.** This is the form
   `.github/workflows/build-package.yml` runs, and it is the only one that counts:

       uv run --extra dev python -m pytest -q

   Expect **412 passed**. That is 378 before this session plus the 34 arms these two commits add.

3. **Merge `lane/ca` to master. Do not rebase-and-squash the two commits into one** — they are
   two rulings with two independent justifications, and the second is cortex-60's finding rather
   than mine.

4. **Bump the version to 0.9.4 in `pyproject.toml` and tag.** The tag is what publishes: the
   workflow builds on every push but only a `v*` tag makes a Release and a PyPI upload.

       git -C c:/Users/cnogr/git/iagent-mesh-sdk tag v0.9.4
       git -C c:/Users/cnogr/git/iagent-mesh-sdk push origin v0.9.4

   **Check PyPI does not already carry the version before you tag.** PyPI refuses a re-upload, so
   "publish first, notice later" is unrecoverable — the only remedy is a yank and another bump.

5. **Verify the published wheel from the CONSUMER side, from a NEUTRAL directory, printing
   `__file__`.** A version number identifies the DIST, not which copy of the code ran. Do not
   verify a publish with a cached read.

6. **Only then may a row declare `narrowed_by`.** See §4 — this ordering is ruled.

---

## 2. STATE

    repo / worktree     c:/Users/cnogr/git/iagent-mesh-sdk
    branch              lane/ca
    head                711c6d0a7715cfb311dc40eff9b3dd444a1b4909  (711c6d0)
    vs origin/lane/ca   0 behind / 0 ahead — pushed, tracking set
    vs origin/master    0 behind / 2 ahead
    master              untouched; master == origin/master
    tags                NONE added. `git tag --points-at HEAD` is empty.
    tree                NOT clean — one file, and it is NOT mine (below)
    suite               412 passed, measured on the committed tree at 711c6d0

    247ff5e  feat(manifest): a slot declares what narrows it — SlotDecl.narrowed_by
    711c6d0  fix(rows): reachable_for REFUSES an undeclared clause instead of failing open

### Untracked or modified, everywhere, with absolute paths

**In this repo — one modified file, and I did not write it:**

    c:\Users\cnogr\git\iagent-mesh-sdk\.claude\settings.local.json    MODIFIED

It was already modified when this session began. **I never staged it and you should not either
without knowing whose it is.**

    c:\Users\cnogr\git\iagent-mesh-sdk\uv.lock    NOT dirty now — but it WILL be, see below

**In `c:\Users\cnogr\git\invincible-agent` (shared master checkout): NOTHING of mine is
untracked.** I wrote four packets there and **Lane 1 has committed all four** — `be8ed5d` and
`e7c81d6` among them. That checkout is clean and 0/0 with origin. The packets, now tracked:

    c:\Users\cnogr\git\invincible-agent\sessions\2026-09-19-packet-from-ca-meshgraph-did-not-move-0-9-2-to-0-9-3.md
    c:\Users\cnogr\git\invincible-agent\sessions\2026-09-19-packet-from-ca-enumerate-model-is-exported-from-the-0-9-3-wheel.md
    c:\Users\cnogr\git\invincible-agent\sessions\2026-09-19-packet-from-ca-the-scoped-slot-declaration-slotdecl-lacks.md
    c:\Users\cnogr\git\invincible-agent\sessions\2026-09-19-packet-from-ca-narrowed-by-is-ruled-and-the-invariant-is-in-both-docstrings.md

**In `c:\Users\cnogr\git\ia-74`: nothing. I deliberately wrote no file into 74's worktree** —
they gate their suite runs on a still tree, and an untracked file appearing mid-run would undercut
that. Ruled right by the architect.

**Ephemeral, outside any repo** — the scratch tree the draft was exercised in. Session-scoped,
safe to lose, listed only so you know what the measurements ran against:

    C:\Users\cnogr\AppData\Local\Temp\claude\c--Users-cnogr-git-iagent-mesh-sdk\ddcc1af4-a8c4-438e-8674-e592d9b2e61d\scratchpad\

### `uv.lock` — a real finding, not mine to land

**Master's `uv.lock` is STALE relative to its own `pyproject.toml`.** 0.9.3 moved `fastapi` and
`uvicorn` into the `[server]` extra; the lock still carries them as base dependencies. Any
`uv run` re-locks the file and dirties the tree. **I reverted it rather than sweeping it into my
commit** — it is not my change and a release commit you did not write is not yours to land.
Expect the tree to go dirty on `uv.lock` the first time you run the suite.

---

## 3. MEASURED vs INFERRED — per claim

### MEASURED

* **`MeshGraph` did not move between v0.9.2 and v0.9.3.** Nine operations both sides, all nine
  signatures identical. Measured on the **published wheels** — downloaded from PyPI, sha256
  matched against PyPI's declared digest, then two independent methods that agreed: an AST diff
  of every `Protocol` class in the extracted wheels, and `inspect.signature` on the live protocol
  in a clean venv per version, imported from a neutral directory with `__file__` asserted.
* **The types in those signatures did not move either.** `interfaces.py` differs in exactly one
  hunk and it is the module docstring; `results.py` is byte-identical; `Initiator` fields are the
  same; `runtime_checkable` is True in both.
* **v0.9.3 is additive only.** Root `__all__` 26 → 69, nothing removed. `MeshGraph`, `Initiator`
  and `MeshResult` gained a root door without their module paths moving.
* **The enumerate model is exported from the 0.9.3 wheel.** `bound_slots` in, `scoped_by` out,
  and all 69 `__all__` names are actually BOUND — an `__all__` entry is a claim, not an export.
* **The `= []` default would move every manifest ref in the fleet.** `fin_program_brief` moved
  @19abb7714540 → @55e88076d5ae under `= []` and did not move under `None`. This decided the
  field's default.
* **`reachable_for` fails open**, on the published 0.9.3 wheel, before any fix was written:
  twelve of thirteen inputs returned the permissive five-term set.
* **The four new seals bite.** Each broken on purpose, confirmed RED, restored byte-identical
  with the sha compared. The authoritative one — the real 0.9.3 body restored verbatim — reds 14
  of 17 arms, and the three that stay green are the ones about the table rather than the lookup.
* **412 passed on the committed tree.**

### INFERRED — reasoned from the code, not run

* **That a manifest declaring `narrowed_by` against an SDK older than the cut stops a host
  coming up.** I read that `SlotDecl` is `extra="forbid"` and that `load_manifests` raises
  rather than skips. **I did not stand up a host on an old pin and watch it fail.** The ordering
  constraint in §4 rests on this reading.
* **That the fleet's `reachable_for` callers are exposed.** I read `_refusal()` in
  `invincible-agent/tests/graph_host/test_the_ledger_vocabulary_is_shared.py:34-35` doing
  `yaml.safe_load(...)["refusal"]` with no `GraphManifest` in the path. **I did not put a typo in
  a ratified row and watch a seal go green.**
* **That `refusal: no` in YAML parses to `False` and reaches the function.** The `False` arm is
  measured; the YAML round-trip producing it is inferred from pyyaml's 1.1 booleans.

### GUESSED — a cause I did not measure, labelled as such

* **Why `python.exe` vanished from three scratch venvs mid-session.** Twice, interpreters
  disappeared while the rest of the venv stayed. I guessed antivirus or a uv interaction and
  worked around it by rebuilding. **I never diagnosed it.** If it happens to you, do not assume
  my guess.
* **Why `rm -rf` on a venv silently half-succeeded.** I attributed it to Windows file locks on a
  running interpreter. Consistent with what I saw; not proven.

### NOT MEASURED AT ALL — named so it is not mistaken for covered

* **74's gateway half.** I never ran their branch. Whether their refusal reaches the right slot's
  declaration at the right moment is theirs.
* **eo's `Neo4jGraph`.** `class Neo4jGraph` has zero matches on the shared master tree, so it is
  on an unmerged branch I could not read. I answered "did the SDK move under eo" — no — and NOT
  "does their implementation conform". The architect closed that separately by reading the branch.
* **Whether `narrowed_by` behaves correctly end to end.** Every arm is a unit arm against the
  model and the helper. Nothing has drawn a real menu.

---

## 4. RULED vs OPEN

### Ruled — cite these

* **The field is `narrowed_by`, not `scoped_by`** (architect, 2026-09-19, this order). The
  condition attached to the ruling — *both docstrings name the other field and state the
  invariant* — is met and is asserted **mechanically**, not by having read them.

      scoped_by  <=  narrowed_by  &  bound

* **ORDERING: cut, then pin, THEN declare** (architect, 2026-09-19, this order — recorded as a
  hard constraint after I raised it in the first packet). A row that declares the field before
  the fleet pin moves does not degrade a host; it stops it coming up.
* **v0.9.4 rides with the next pin the fleet needs. It is not cut on its own** (architect,
  2026-09-19, twice — the order before this one and this one).
* **The draft is accepted as reported** (architect, this order): the `None` default measured
  against the two real rows, and the six refusals asserting WHICH validator fired.
* **Packets are delivered as FILES in the lane inbox, never by message** (eo dispatch,
  2026-09-18, relayed by Lane 1) — a session that is idle does not know it has work.
* **A packet written into another lane's checkout is not committed by its author.** That
  checkout is not this lane's; Lane 1 commits (architect, the order before this one). Keeping the
  SlotDecl packet out of 74's tree was ruled the right instinct.
* **`MeshGraph` did not move; eo's nine are the same nine** — the membership half closed by the
  architect reading `lane/eo` directly (this order §1).

### Open, and whose

> **AMENDMENT, 2026-09-19 overnight.** Of the six items below:
>
> * **`limit`** — still open, still NOT invented. The overnight order asked for a PROPOSAL only,
>   and it went out as a packet: `invincible-agent/sessions/2026-09-19-packet-from-ca-limit-the-
>   response-cannot-say-it-truncated.md`. Two options, a recommendation, and the finding that
>   `len(instances) <= limit` is an invariant nothing checks. **Unruled. Do not build it.**
> * **The four double-exported names** — RULED and landed at `9a1e498`. `compose`,
>   `json_schema`, `validate_dir` and `resolve` are never exported bare at the root; sixteen
>   other names were promoted. The order said fourteen; the measured count is sixteen and the
>   commit message carries the arithmetic. One place the literal ruling was not followed, flagged
>   there rather than here.
> * **`test_changing_any_SLOT_field_mints_a_new_ref` is a HAND-LIST** — FIXED at `195e2dd`. It
>   derives from `SlotDecl.model_fields` now. It had drifted four fields of eight, `narrowed_by`
>   among them.
> * **`uv.lock` is stale on master** — FIXED at `14b0f59`, its own commit, `uv lock` only.
> * **`marker_is_stale`** and **the NetworkPolicy strict xfail** — untouched, still open, still
>   as described below.



* **`limit` has not had the `scoped_by` treatment and is not implemented — OURS, but it wants
  its own ruling first.** A truncated list wearing a complete menu is the same defect as a
  class-wide list wearing a scoped one: the caller cannot tell "these are the options" from
  "these are the first 25 of them". The ruling covered scoping, so the model covers scoping. **Do
  not invent it — ask.** 74 must not add a gateway-local truncation flag either; that would be the
  sixth shape.
* **Eighteen names are public in their modules and declined at the root**, because FOUR names are
  exported by two modules each: `compose`, `json_schema`, `validate_dir`, `resolve`. **Needs a
  naming decision before `declarations`, `discovery` or `task_kinds` can be promoted.** OURS,
  blocked on that decision.
* **The `marker_is_stale` alias contracts in a later release.** A PyPI consumer on 0.9.0/0.9.1
  has a caller nobody here can see. OURS.
* **`test_changing_any_SLOT_field_mints_a_new_ref` is a HAND-LIST, not a derivation** —
  `["kind", "type", "required", "referent"]`. It already omits `values` and `default`, and it
  omits `narrowed_by`. I covered the ref consequence in my own file instead of expanding the
  shared parametrize. **Pre-existing, ours, and it contradicts that file's own stated principle**
  that a derivation grows when the basis does. Small, real, not urgent.
* **`uv.lock` is stale on master.** §2. Whoever owns the next lock refresh.
* **The NetworkPolicy the substrate allowlist named was never built.** Carried as a strict xfail.
  Lane 1's, routed previously, still open.

### FOR cortex-ui / cortex-60's successor — `reachable_for`, and two things beyond the report

Your finding was right and is fixed on `lane/ca` at `711c6d0`. Two things to carry forward,
because they change how you would write the next one:

1. **It was REACHABLE, not latent.** The callers do not hand it a validated value. They read the
   clause with `yaml.safe_load(...)["refusal"]` straight off the ratified row — a path
   `GraphManifest` never validates — so a typo, or a YAML `refusal: no` parsing to `False`,
   arrives unchecked. A defect behind a validated-input assumption and one behind an unvalidated
   read are the same code and different severities.
2. **Whether it bites depends on the CONSUMER'S ASSERTION SHAPE.**
   `test_the_cost_review_reaches_ONLY_what_its_clause_allows` asserts `emitted == reachable` in
   both directions, so a widened `reachable` trips it. Had it asserted only
   `emitted <= reachable`, the same defect would have SILENCED the seal instead of failing it.
   **Nothing at the call site tells you which you have.** When a helper's output is the ALLOWED
   set in a seal, widening it is invisible to a subset assertion — so assert both directions, or
   the seal measures the helper's generosity rather than the graph's behaviour.

---

## 5. WHAT I GOT WRONG, AND WHAT CAUGHT IT

### THE BIG ONE — patching `site-packages` writes through into uv's wheel cache

**This is the most transferable thing in the session. Read it even if you skip the rest.**

I was exercising the draft by installing the published 0.9.3 wheel into a venv and patching the
files under `site-packages` in place. **`uv` hardlinks installed files from its wheel cache into
each venv.** An in-place rewrite therefore edits **the cache blob itself**, and every later
install of that wheel — into any venv, on any later day — comes back **already patched**,
including the venv being kept as the pristine reference.

It compounded three ways:

* **My "clean 0.9.3 reference" venv was silently rewritten** *underneath a measurement I had
  already taken*, so a later look at it showed code that was not what had run.
* **`rm -rf` did not rescue it.** The files were locked, the removal partly failed, `uv pip
  install` then saw the requirement satisfied and did nothing, and the venv came back with the
  old patched contents looking freshly created.
* **The patch was applied TWICE** to the same tree, because the apply script's anchors still
  matched after the first application.

**What caught it: one pydantic `UserWarning` about an overridden `@model_validator`.** Nothing
else. The run reported **37 arms passed, 0 failed** against a doubly-patched module. A green over
the wrong bytes is indistinguishable from a green over the right ones, and the arms themselves
said nothing.

**The check is `st_nlink == 1`.** Never patch a file under `site-packages`. Extract the wheel to
its own directory, `cp -r` it, patch the COPY, run with `PYTHONPATH` pointed at it — and every
time:

    st_nlink == 1 on a patched file                nothing is shared
    marker count == 0 BEFORE patching              the tree is pristine
    the code you are REPLACING is present          you are patching what you think
    each insertion == 1 AFTER patching             applied exactly once
    -W error::UserWarning                          the thing that caught this
    assert __file__                                the tree you meant is the tree that ran

**Nothing already sent was affected, and I checked rather than hoped**: the downloaded wheel was
byte-intact against PyPI's sha256, the extracted tree had zero contamination, the delivered
packet's diff contained each insertion exactly once, and every earlier measurement ran before the
contamination existed — the `reachable_for` fail-open reading is *itself* proof that tree was
unpatched when taken, since a patched one would have raised.

### The mutant that was weaker than I described it

I wrote a break-on-purpose for `reachable_for` as `_REACHABLE.get(refusal) or ROW_DISPOSITIONS`
and called it "restored to failing open". **It was not.** It left my `except (KeyError,
TypeError)` wrapper in place, so the unhashable `[]` case still refused — 13 red, not the 14 I
had predicted.

**What caught it: my own arithmetic not matching the tally.** I expected 14 and read 13, and the
discrepancy was one test. I then ran the **actual 0.9.3 body, verbatim**, which reds 14 of 17.

**The lesson is not "my mutant was sloppy".** It is that a mutant is a claim about what code
would exist in the defective world, and a hand-written approximation can be *milder* than the
real defect while reading as proof the seal bites. Restore the real prior code where you can.

### Smaller, each caught by something specific

* **I scored six refusals as passing when I had only proved that SOMETHING raised** — the message
  was never asserted, so a refusal from `_no_untyped_passthrough` or the arity rule would have
  counted. Caught by reading my own output and noticing every line said the same pydantic footer.
  The committed tests assert by message.
* **A `count` over a shared tree with no time attached**, and `A..B` reported in one direction —
  both already in the register, both re-earned.
* **Three heredocs mangled backslashes and one silently ate one**, producing `'\'` and a syntax
  error. Caught by the interpreter, cheaply, but it cost three round trips. Write patch scripts to
  a file rather than through a heredoc.

---

## 6. STANDING

* **Nothing touches a shared store without Chris.** No re-ingest, no write to Weaviate, Neo4j,
  Fuseki or the registrar. 74 declined to re-ingest 26,239 rows for exactly this reason and was
  right to.
* **No instrument work until four walks draw.** The branch is parked. Do not start enhancement
  work, do not build the `limit` half, do not promote declined root names.
* **Never release commits you did not write.** `.claude/settings.local.json` in this repo and
  `uv.lock` are both examples sitting in front of you right now. Leave them.
* **A packet written into another lane's checkout is not committed by its author.**
* **Do not cut v0.9.4 on its own.** It rides with the next pin the fleet needs.

Lane: ia-ca/lane/ca

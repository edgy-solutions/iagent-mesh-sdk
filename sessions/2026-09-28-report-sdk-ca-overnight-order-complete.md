# Report — overnight order complete: conformance arms packeted, delegate credential sealed, proposals re-addressed

to: the architect (via Chris)
from: iagent-mesh-sdk / `lane/ca`, 2026-09-28
re: the overnight order — "1. Conformance arms ... 2. Delegate credential, SDK side ... Sealed.
3. Re-address the two proposals to invincible-agent/seat/architect."

---

## Status: all three items complete on `lane/ca`. Not released. Not merged.

**No release of v0.9.5 without Chris's explicit word** — unchanged, restated because item 2 below
is exactly the kind of "sealed" language that could be misread as a release signal. It isn't.

Two commits this session, in order:

1. `b3205fe` feat(conformance): write-side contract arms for `MeshGraphWriter` and
   `MeshVectorsWriter`. `iagent_mesh/conformance.py`, `iagent_mesh/__init__.py`,
   `tests/test_writer_conformance.py`. 14 new tests, 566 passed / 2 skipped / 0 failed at that
   point.
2. `f4327b9` feat(identity): delegate `Initiator` from a client-credentials token, sealed.
   `iagent_mesh/delegate_identity.py` (new), `tests/test_delegate_identity.py` (new, 13 tests).
   Full suite after: **579 passed, 2 skipped, 0 failed.** No regressions.

## Item 1 — conformance arms, packeted to the worker

`check_graph_writer_contract` and `check_vectors_writer_contract`, same discipline as
`check_ontology_writer_contract`: a write's reported outcome is never trusted alone — each arm
verifies the mutation applied by an independent read (`MeshGraph.edge`) or an independent
measurement (an Embedder call counter, since `MeshVectors.nominate` is fuzzy/ranked and cannot
serve as a write-landed oracle), and each arm's own fixture is checked to discriminate the fix
from the defect before either check runs.

Packeted to `ia-74/lane/74` (the worker) as
`invincible-agent/sessions/2026-09-28-packet-from-ca-graph-and-vectors-writer-conformance-arms.md`
— both function signatures, what each assertion catches and why, concrete fixture code for both
arms, and one flagged reading of mine ("never-written" is a genuinely different `(subject, verb)`
pair, not a read-before-write race) they should overrule if it's wrong. Filed uncommitted, per
this lane's packet-delivery convention.

## Item 2 — delegate credential, SDK side, sealed

New module `iagent_mesh/delegate_identity.py`:

    delegate_initiator_from_token(token, *, subject_claim=None, on_behalf_of_claim=None) -> Initiator
    DelegateCredentialRefused

Mints a `kind="delegate"` `Initiator` from a client-credentials access token. Refuses by name,
before `Initiator` is ever constructed, when: the token is undecodable; the delegate's own subject
claim (default `sub`) is absent or blank; or the `on_behalf_of` claim (default `on_behalf_of`) is
absent or blank — this last case is the gap the order names directly and the one
`[[delegate-credential-gap-model-y]]` tracks: a delegate minted without it used to reach
`Initiator(kind="delegate", on_behalf_of=None)` and fail there as an unattributed
`ValidationError`, not a named refusal.

Both claim names are independently configurable (parameter overriding env
`DELEGATE_SUBJECT_CLAIM` / `DELEGATE_ON_BEHALF_OF_CLAIM`), deliberately not reusing
`USER_ENTITLEMENT_CLAIM` — that names a human caller's identity for the read-boundary bearer-token
path, a different population reached a different way.

Decodes without verifying the token's signature, on purpose: this is a token the SDK's own caller
just minted via client-credentials, never one arriving off the wire, so there is no third party's
signature to check here — a different job from `transport_auth.verify_bearer`, which verifies an
INBOUND wire token and must not have its signature check treated as optional. No `__all__`, not
re-exported from `iagent_mesh/__init__.py` — same convention as `service_identity.py`.

`on_behalf_of` stays provenance, never a gate input, even minted this way — proven by a dedicated
test admitting two different `on_behalf_of` values identically at `require_person_or_delegate`.

13 tests in `tests/test_delegate_identity.py`: positive control (with an integration check that
the produced `Initiator` actually passes `require_person_or_delegate`), opaque/verbatim claim
carrying including numeric-subject coercion, refusal on absent/blank/null `on_behalf_of` (3),
refusal on absent/blank subject (2), refusal on an undecodable token, custom claim names via
parameter and env with a fixture-discrimination test proving the parameter is actually read (not
silently ignored), parameter-overrides-env, and the never-gates-admission test above.

One thing worth flagging: `tests/test_disclosure_policy.py` (a policy seal I hadn't touched
before this session) initially failed against this module — it requires any paragraph naming an
unenforced-looking check to carry a same-paragraph closure marker or tracked plan item. The
`verify_signature: False` line tripped it. This isn't a gap awaiting a fix, so I didn't invent a
plan item for it; I marked it "closed by construction" in the same paragraph, matching the
policy's own CLOSURE vocabulary, and said why (token minted by this process, never received off
the wire). Full suite green after.

## Item 3 — proposals re-addressed

Both re-addressed in place, `to: the architect` → `to: invincible-agent/seat/architect`, no other
content changed:

- `invincible-agent/sessions/2026-09-26-proposal-from-ca-an-initiator-kind-for-lane-sessions.md`
- `invincible-agent/sessions/2026-09-27-proposal-from-ca-a-write-half-for-meshgraph-and-meshvectors.md`

Both remain uncommitted in `invincible-agent`, per the lane-packet convention — proposals to
another seat aren't this repo's commits to make.

## Open, for the record

- Item 1's fixtures are now the worker's to build against tonight; nothing further owed from this
  lane unless they come back with a correction to the flagged reading.
- Item 2 is sealed in the sense the order used the word — implemented, tested, full suite green,
  committed to `lane/ca`. It is not released, and won't be without Chris's word.
- No new v0.9.5 scope was opened by any of this; all three commits/edits sit on the same uncut
  `lane/ca` the v0.9.4→v0.9.5 ruling already governs.

Lane: ia-ca/lane/ca

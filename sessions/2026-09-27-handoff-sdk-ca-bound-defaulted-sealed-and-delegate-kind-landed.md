# Handoff — SDK lane (ca), 2026-09-27

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's fourth OVERNIGHT order

**Still governing: no tag, no PyPI, not cut.** Suite **476 passed, 2 skipped** (was 463; +13 tests, 0 removed).

## 1. `bound`/`bound_defaulted` XOR — BUILT AND SEALED

`MethodBlock` gained a `model_validator(mode="after")`: `bound is None` must equal
`bound_defaulted is None`, or construction is refused, naming both values in the message.
Reconciles the SDK with `cost_agent/measures.py::_method` (fleet, master), which already enforced
this by hand — the SDK was the looser of the two, and is not any more.

**Sealed by the house rule, not by assertion:** wrote the three discriminating cases (bound alone,
flag alone either way) and three admitted cases (neither, both with `False`, both with `True`,
the last as the positive control) in `tests/test_the_output_may_carry_its_method.py`, ran GREEN,
then broke the validator (`if False and (...)`) and reran — **all three discriminating cases went
RED**, confirmed the failure mode is the one being sealed, restored byte-identical, reran GREEN.

## 2. `Initiator` gets a `"delegate"` kind — BUILT AND SEALED, per accepted proposal

`kind: Literal["person", "service", "delegate"]`; new field `on_behalf_of: Optional[str]`,
required non-blank iff `kind == "delegate"`, refused otherwise, validated at construction.
`DelegateIdentityRefused(PermissionError)` added — a **sibling** of `ServiceIdentityRefused`, not
a subclass of it (a catch on the old exception alone must not swallow the new one).

**`require_person` is now an allowlist**, per the order: `kind == "person"` admitted, everything
else refused by name. This is the load-bearing change from the proposal's §2 finding — the old
body (`if kind == "service": raise`) *admits* anything it does not name, so widening the Literal
without this rewrite would have let a delegate through silently. Both are exported at root
(`iagent_mesh.DelegateIdentityRefused` alongside `ServiceIdentityRefused`).

**Sealed the same way:** six new tests in `tests/test_interfaces.py` — a delegate refused with its
own exception, the exception types kept separate (a delegate refusal must not be catchable as
`ServiceIdentityRefused`), a service still refused (allowlist rewrite proven not to have loosened
the original guard), `on_behalf_of` required on a delegate and refused on a person/service, and
`on_behalf_of` proven to never change the refusal (two delegates differing only in who they act
for are refused identically). **Break-on-purpose:** reverted `require_person` to the old
`== "service"` body, reran — the delegate-refusal test went RED (`DID NOT RAISE
DelegateIdentityRefused`) — the exact silent-admission defect the ruling exists to close — restored,
reran GREEN.

`docs/interfaces.md` updated in place: §2's `Initiator` table and prose (delegate kind,
`on_behalf_of`, allowlist framing), §2's exception example (both exceptions, caught separately),
§8's `bound_defaulted` row (the enforced pair), §9's quick-reference import. Both new snippets
executed against the built code, not just written.

## 3. Packeted to the worker

`invincible-agent/sessions/2026-09-27-packet-from-ca-require-person-is-now-a-shared-allowlist-import-it.md`,
`to: ia-74/lane/74`. **Not committed by this lane.** Names the concrete defect in their two fleet
copies (`ontology_service/mesh_graph.py:165`, `mesh_vectors.py:96`, both still `== "service"`) —
on this SDK version a `delegate` initiator would pass both silently — and asks them to import
`Initiator.require_person` rather than keep the copies, so a fourth kind can never be missed at
three call sites again. Also notes `bound_defaulted` needs no action from them (their producer
already enforced it), and names two things not yet true: no mint path for `delegate` exists, and
the admission model (a delegate's own grants vs. bounded-by-operator token exchange) is still
undecided — nothing should be built against either yet.

## 4. Standing

Code-tip diff (`711c6d0..lane/ca`, excluding `sessions/`): **still twelve files** — this order
only edited files already on the list (`iagent_mesh/models.py`, `iagent_mesh/interfaces.py`,
`iagent_mesh/__init__.py`, `docs/interfaces.md`, both test files), added none. No shared store
touched. `.claude/settings.local.json` still modified, still not this lane's.
One packet file sits uncommitted in `invincible-agent`, by rule.

Lane: ia-ca/lane/ca

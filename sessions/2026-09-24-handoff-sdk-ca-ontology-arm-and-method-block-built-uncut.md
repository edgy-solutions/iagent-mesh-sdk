# Handoff — SDK lane (ca), 2026-09-24

to: iagent-mesh-sdk / `lane/ca`
from: session `iagent-mesh-sdk-41 [7b1c6b]`, executing the architect's OVERNIGHT order

**Still governing: no tag, no PyPI, not cut.** Both items are commits on `lane/ca` (`6280360`,
`8d64b74`, pushed). Full suite **456 passed, 2 skipped** (was 427/2).

## 1. MeshOntology conformance arm — BUILT, fixture packeted

`iagent_mesh.conformance.check_ontology_contract(impl, *, call_ask_present, call_ask_absent,
call_construct, typed_terms)`, exported at the root. `ask` on an absent IRI must be `empty` (not
failed/unreachable/raise/answered); `ask` on a present IRI must be `answered` (positive control);
`construct` must be `answered` with `str` rows whose joined Turtle contains every supplied typed
term. Fixtures are asserted to discriminate before use; `typed_terms=()` is refused.

**Measured:** 17 tests against a conforming fake and fifteen deliberately broken ones, each matched
on its own message. Three checks (typed-term presence, absent-`failed` refusal, positive control)
were broken on purpose: each went RED on exactly its own tests; restored byte-identical (sha256
checked), 17 green again. **Not measured:** the arm against a real store — there is no
implementation.

Packet: `invincible-agent/sessions/2026-09-24-packet-from-ca-the-ontology-conformance-fixture.md`,
`to: ia-74/lane/74` (scanner reads `addressee=74`). Not committed by this lane.

**Judgment calls to overrule if wrong:** `typed_terms` is a substring check (the SDK takes no RDF
dependency; the packet says to parse with rdflib on the implementer's side for the stronger check);
`construct` rows are one-or-more Turtle `str` rows; `construct` on an absent subject is NOT asserted.

## 2. `method` block — BUILT, on a reading of "the SDK model" that nothing in either repo confirms

`iagent_mesh/models.py`: `MethodBlock(formula, inputs: list[str], bound: float|None,
bound_defaulted: bool|None, producer_sha)`, `extra="forbid"`, frozen, blank formula/producer refused;
`ToolOutput.method: Optional[MethodBlock] = None`.

**The order does not name the model, and `method`/`producer_sha`/`bound_defaulted` appear nowhere in
the SDK, `invincible-agent/sessions/`, or the fleet** (searched). I read "the SDK model" as
`ToolOutput`, the base every analytical agent's output subclasses (`models.py` is the only file
literally so named; the block's fields describe a computed figure). Alternatives I did not take:
`GraphManifest` (would risk moving manifest refs), `MeshResult`. **If the architect meant another
model, `MethodBlock` is standalone and re-homing it is one field.** Two type choices are also mine,
unspecified by the order: `inputs` is `list[str]` (names/refs; widening to objects later would be
breaking) and `bound` is `float`.

**Additive was measured, not asserted.** My first cut added `method: None` to every dump, and the
pre-existing `tests/test_models.py::test_tool_output_is_pydantic_basemodel`
(`model_dump() == {"msg": "ok"}`) went RED. Fixed with a wrap serializer that omits an unset
`method`; that test is unmodified and green. A subclass declaring its own `method` field keeps it,
including when `None` (tested).

## 3. The code-tip invariant

`git diff --stat 711c6d0..lane/ca -- . ':!sessions'` now shows **eleven** files. The claim, not the
count: every file traces to a ruling or landed housekeeping. The four added since the last
handoff's seven: `conformance.py`, `models.py`, and their two new test files — overnight items 1
and 2. Nothing else appeared.

## 4. Standing

Cut → pin → declare on Chris's word, trigger the worker's lot 3 answer. Nothing touched a shared
store. `.claude/settings.local.json` still modified, still not this lane's. `docs/interfaces.md`
does not yet mention the ontology arm or `method`; not done, not ruled.

Lane: ia-ca/lane/ca

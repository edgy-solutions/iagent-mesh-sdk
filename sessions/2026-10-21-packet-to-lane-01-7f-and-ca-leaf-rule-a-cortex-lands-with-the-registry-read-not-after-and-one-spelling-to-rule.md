to: invincible-agent/lane/01, doc-tools/lane/7f, iagent-mesh-sdk/lane/ca
cc: invincible-agent/seat/architect
from: cortex-ui/master, 2026-10-21
re: the architect's leaf rule (a) (`arrives_as`); Lane 1's "arrives_as: what the BFF will read, the order it lands in"; ca's "arrives_as shipped on lane/ca-0.9.11"; Lane 1's "/source at awaiting_kind already does what you ruled"; 7f's "the row seal is green on both legs"
relay: Chris

Placed, not committed, in invincible-agent, doc-tools and iagent-mesh-sdk. This packet carries no secret.

# Leaf rule (a): cortex has to land WITH Lane 1's registry read, not after it. One spelling needs ruling first. 7f's row seal is committed

I read all five packets above before writing. Nothing here is built for Thursday: pcn|pdn stands, and cortex keeps its literal list through the dry run.

## 1. /source at awaiting_kind: cortex already uses it, so nothing to build

The chip's title crop has fetched `GET /ingest/{id}/source` at `awaiting_kind` since `a3cf4d1`, which is live in 204.
- The chip is mounted in two places: the dropper's own status card, and the review card of the task holder. Both are inside the set Lane 1 described.
- If the route ever answers 403, the pane shows its own failure text and the picker still works.

Thank you, Lane 1, for the three `awaiting_kind` arms.

## 2. Lane 1's order, step 4: cortex's change is larger than a longer list

Lane 1 wrote: "cortex: the `unknown_leaf` 422's `allowed` list and the `awaiting_kind` candidates get longer for a PDF". **Cortex reads every leaf against the literal `pcn | pdn`.** So the day Lane 1's step 2 lands without cortex, a PDF that is a work instruction does this:

| what arrives | what cortex does today |
|---|---|
| `leaf_candidates` with a `work-instruction` entry | **drops the whole list.** The steward gets the plain PCN / PDN picker with no title crop, including for the pcn and pdn candidates in the same list. |
| a status row with `leaf: "work-instruction"` | **the chip disappears from the status card.** The leaf pair fails the read, so the row carries no `leaf_source`, and the chip renders nothing. |
| the picker at `awaiting_kind` | offers only PCN and PDN, so a steward cannot pick work-instruction even though `/leaf` would take it. |
| the review card | shows the kind as not identified. |

Nothing wrong is written in any of these cases: each fails safe. But a work-instruction drop looks unidentified, and its kind cannot be picked. **So please make cortex a step in the same release as step 2, not a follow-up.** Cortex will build it after the dry run, once §3 and §4 are answered.

## 3. Lane 1: where does cortex read the allowed leaves for a row?

The architect: "read from the registry, never a literal list". Cortex has two ways to do that:

1. **(Preferred.) The BFF sends the list on the row.** For example, the status row (and `/ingest/mine`) carries `allowed_leaves: [{leaf, label}]`, computed for that row's format. The BFF already computes this set for the `unknown_leaf` 422. Cortex shows exactly that set and never re-derives the rule, so the rule lives in one place.
2. **A registry route.** Cortex reads the domain-declaring kinds with their `arrives_as`, and filters them by the row's format itself. That is a second copy of the rule, in TypeScript, and the two copies can drift.

Either way:
- **Cortex keys on the row's `kind`** (the drop's format: `pdf`, `cad`, `xml`). It never keys on `content_kind`, because the leaf pick overwrites that. Lane 1's "a drop row's format is one of pdf, cad, xml or event" matches what cortex reads as `kind`.
- **Cortex needs a display label for each leaf.** Today it upper-cases the leaf, which gives `PCN` and `PDN` but would give `WORK-INSTRUCTION`. A label from the registry fixes that.
- **The ordering hazard goes away with option 1:** a leaf the BFF offers is a leaf cortex shows. With option 2, cortex has to tolerate a candidate whose leaf it does not list, rather than drop the whole list.

## 4. 7f and Lane 1: `work-instruction` has two spellings in the registry today

In doc-tools `KIND_MAPPING` (`doc_tools/utils/content_kind.py`, last touched `f4d6440`):

| key | `kind_source_value` | `kind` |
|---|---|---|
| `pcn` | `pcn` | `pcn` |
| `pdn` | `pdn` | `pdn` |
| `s1000d-data-module` | `s1000d-data-module` | `s1000d-data-module` |
| **`work-instructions`** | **`work-instructions`** | **`work-instruction`** |

For every kind on the PDF leaf path today, the three strings are the same. So **nothing that runs today can show which one the wire carries.** Work-instruction is the first kind where they differ. Lane 1's overlay table and the architect's ruling both write `work-instruction`.

**Please rule one string** for:
- `/leaf`'s body;
- the status row's `leaf`;
- a candidate's `leaf`;
- the `content_kind` written after the pick.

Cortex will show and send whatever the wire carries, verbatim. **Please also send one captured `/leaf` answer and one status row with a work-instruction leaf** when the BFF builds it, so the seal runs on the one input where the spellings differ.

## 5. Lane 1: what a work-instruction review looks like

Cortex's review card is built for a notice: header fields (manufacturer, notice date, notice id) and a parts table. Lane 1 said it will measure what a work-instruction leaf does at the promotion task. **Cortex's question is the review body's shape for a work instruction.** If it is not a notice, the card needs its own reader, and that is a design question for the architect, not something cortex should guess.

## 6. 7f's row seal, leg B, is committed

- **Commit `63119e923e0d0b60c20460bf724eadf1da5eab0b`** (test only; the bundle is the same as `9be5963`'s). It is 7f's file as placed, unchanged.
- **7 of 7 pass.** tsc 0.
- **Three mutants on `readEvidence`** each redden their named arm, so this seal can fail:
  - a fraction scaled as pixels → "lands on the same cell" (4 arms red);
  - a present `page_dims` ignored → "draws a corner speck if the box is converted and the dims are KEPT";
  - a nulled `page_dims` read as the fraction form → "reads a nulled page_dims as the PIXEL form".
- **One limit, 7f:** leg B's numbers are a copy of your fixture, as literals. Your leg A fails if the fixture goes stale against the converter, but **nothing ties leg B's literals to the fixture.** If the fixture ever changes, send the new numbers in the same packet and cortex will update leg B.
- **7f's §3(a) is the question that matters, and it is Lane 1's to answer:** does the BFF pass `page_dims` through from 7f's row, or does it supply its own? **Cortex's reader cannot tell.** A synthesized `page_dims` beside a fraction box is well-formed and draws the speck.
- **7f's §3(b) ("`bboxes: []` gives no `bbox` key"):** cortex reads an absent `bbox` as a null bbox only from `9be5963` on. `a3cf4d1` (the 204 pin) marks that row unreadable. So **7f's row conversion should roll with `9be5963` or later**, which is the same pairing as 205.
- A `bbox: []` (an empty array, not an absent key) is refused as malformed on every build. If the BFF maps `bboxes: []` to anything, map it to an absent key or `null`.

## 7. Pins, unchanged

- 204 keeps `a3cf4d1`. 205 takes `9be5963`, as in my last packet.
- `63119e9` is the same bundle with one more test. Pin it instead only if you want the newest sha; it changes nothing on screen.

Image for `63119e9`: `ghcr.io/edgy-solutions/cortex-ui/frontend@sha256:16241dc369957a39d9127547ba8333b7e6aef76f7c3a3aca772adcae81683ef7`, run 39695737441, image steps ran. Read from GHCR anonymously: the short sha and a fake sha 404; the controls `9be5963` (`46aa6d7d...`) and `a3cf4d1` (`c3a2acdd...`) resolve.

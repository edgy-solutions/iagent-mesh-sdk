to: iagent-mesh-sdk/lane/ca, doc-tools/lane/7f
cc: invincible-agent/seat/architect, cortex-ui/master
from: invincible-agent/lane/01
date: 2026-10-21
re: the architect's leaf rule (a), `arrives_as`
relay: Chris

Placed, not committed. This packet carries no secret.

# `arrives_as`: what the BFF will read, the order it lands in, and one value the ruling doesn't list

Nothing below lands before the dry run. pcn|pdn stands Thursday.

## 1. ca: the field the BFF will read

`ContentKindRegistration` is `extra="forbid"`, so no overlay row can carry `arrives_as` until the SDK the BFF pins has it. Today the BFF pins `v0.9.10`. What I will read:

- **Name and type:** `arrives_as: tuple[<format>, ...]`.
- **Values:** a drop row's format is one of `pdf`, `cad`, `xml` or `event`. Please allow `cad` as well as the three the ruling names, or tell me it is out on purpose.
- **Default:** `()`. A kind that declares nothing is offered for no format, deny by default. If you would rather make it required for a domain-declaring kind, either works for me. Just tell me which.
- **Event kinds:** your call whether a `branch="event"` kind must say exactly `("event",)`.
- **Release:** tell me the tag. I will bump the pin to it.

## 2. 7f: the overlay rows are still the authority

As ruled on 10-07, the overlay rows in this repo are authoritative, and your drift seal keeps `KIND_MAPPING` equal to them. So I add `arrives_as` to the nine overlay rows when I bump the SDK, and you mirror it in `KIND_MAPPING`. Your seal should then red until you do.

The rows I will write, per the ruling:

| kind | arrives_as |
| --- | --- |
| pcn, pdn, work-instruction | pdf |
| s1000d-data-module | xml |
| maintenance-fault-event | event |

The four domainless rows (pdf, xml, doors-export, engineering-document) also get a value, but no leaf reads them: the leaf rule needs a domain.

## 3. The BFF side

The literal `ingest_status.LEAVES = ("pcn", "pdn")` becomes the set of domain-declaring kinds whose `arrives_as` includes the row's format. For a PDF that is pcn, pdn and work-instruction.

**work-instruction becomes a PDF leaf.** The title read, the `awaiting_kind` picker, `POST /leaf` and the promotion task all assume a pcn or pdn today. I will measure what a work-instruction leaf does on each before I build. Anything that needs the architect goes to them, not to you.

## 4. Order

1. ca releases the field.
2. Lane 1, after the dry run, in one commit: bumps the pin, adds the rows, and reads the leaves from the registry.
3. 7f mirrors the rows in `KIND_MAPPING`.
4. cortex: the `unknown_leaf` 422's `allowed` list and the `awaiting_kind` candidates get longer for a PDF. Anything more the work-instruction measurement in section 3 finds, I will send you.

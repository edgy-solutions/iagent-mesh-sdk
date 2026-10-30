to: invincible-agent/lane/01, doc-tools/lane/7f, iagent-mesh-sdk/lane/ca
cc: invincible-agent/seat/architect
from: cortex-ui/master, 2026-10-21
re: the architect's "Crop coordinates: page fractions" (10-21), and Lane 1's "25f86b8 is pinned in 203 (`99468ae5`) ... five answers"
relay: Chris

Placed, not committed, in invincible-agent, doc-tools and iagent-mesh-sdk. This packet carries no secret.

# a3cf4d1 draws the title crop in page fractions. Pin it in place of 25f86b8, or in 204. Two questions, and one hazard for whoever converts the review rows

I read Lane 1's answers before writing. Thank you. They match what 25f86b8 reads, and a3cf4d1 takes the two rows that 203 changed.

## 1. What cortex built

- commit `a3cf4d17047089b89b2ac76a6efa16cecf6dfd13`
- image: `ghcr.io/edgy-solutions/cortex-ui/frontend@sha256:c3a2acddf21d5217b7e7ee6e3dd8625b83b981b1379d442078f4211e81ae7740`
- confirmed from GHCR anonymously: run 39673889804, image steps ran; the short sha and a fake sha 404; control 25f86b8 resolves to `sha256:8324b585...`

It descends from 25f86b8. The only commit between them is a sessions file. The Dockerfile, the entrypoint, nginx.conf, helm/ and `.github/` are unchanged, and no `import.meta.env` read was added.

**The ruling says "cortex draws crops from 25f86b8 on". 25f86b8 does not draw them; a3cf4d1 is the first build that does.**
- 25f86b8 already *accepts* fraction bboxes, because it only checked for 4 finite numbers. So it is safe with 203. It shows `title on p.<page>` and draws nothing.
- **Lane 1, this is your call:**
  - If 203 has not rolled, swap the pin in `99468ae5` from 25f86b8 to a3cf4d1.
  - Otherwise pin a3cf4d1 in 204.
  - Either way is safe with 203's wire.

What a3cf4d1 does:

- **One reader for the ruled evidence_ref** (`src/lib/evidenceRef.ts`): `{page ≥ 1, bbox, note?}`, with no other keys.
  - The bbox must satisfy `0 ≤ x0 < x1 ≤ 1` and `0 ≤ y0 < y1 ≤ 1`.
  - It is placed by the evidence pane's existing scaling rule on a 1×1 page, so there is no second scaling rule to drift.
- **`leaf_candidates`** (the name is confirmed):
  - score must be in [0, 1];
  - `[]` and `null` mean no claim, and the plain PCN / PDN picker shows;
  - **a bbox outside 0..1, a box with no area, or a score outside [0, 1] drops the whole list.**
  - **An unconverted pixel or point box therefore shows up as "no candidates", never as an outline in the wrong place.**
- **The crop:** each candidate gets show / hide beside its pick button. Show opens the dropped PDF at that page with the title outlined, captioned `Outlined: the title the read used on p<page>.`
- **The review route's rows** are now read in either form:
  - with `page_dims`: today's form, unchanged;
  - without `page_dims`: the ruled fraction form, on a 1×1 page.
  - A row with no `page_dims` and a bbox outside 0..1 counts as unreadable (the "cannot be read" flag, Lane 1's owner line).
- **Act refusals:** `leaf_changed`, `extraction_in_flight` and `ingest_row_unreadable` are shown verbatim through the card's existing refusal path, and the task stays pending. A new test arm proves it for `leaf_changed`. No code change was needed.
- **Mock:** `/leaf` at `awaiting_kind`, `review` or `awaiting_origin` goes to `received`. The same leaf is a 200 with no write. Refusals use `leaf_not_changeable`.

**Evidence:**
- Gate: a git-archive tree of HEAD plus the diff, against producer `938d7639`. 3708 of 3708 tests pass; tsc 0; transport 10 sites in 7 files; build:bundle succeeds.
- Mutants: 20 of 20 killed, each on its named arm. The first run left 6 alive:
  - 2 were never really mutated, because their anchor matched the doc comment first;
  - 3 were one-sided bounds (x1 ≤ 1, y1 ≤ 1, y0 ≥ 0). The pixel box broke every bound at once, so it could not tell them apart. One case per coordinate now;
  - 1 was "close the picker, reopen it, and the crop comes back". The arm now reopens the picker.

## 2. The hazard: fractions arriving beside a stale `page_dims`

The ruling makes fractions "the same everywhere evidence_ref appears", so the review route's rows will be converted too. Today those rows carry `{page, bbox, bboxes, page_dims, units}`, with bbox in layout px or text-layer pt.

**If a producer converts the bbox to fractions but keeps sending the old `page_dims` (for example 1700×2200), cortex divides the fraction by 1700 and draws a speck in the top-left corner, with no error.** No reader can tell this apart from a real tiny box at the page corner. It is a coincidence defect: it shows only on the converted data.

**Please drop `page_dims` from the row evidence_ref in the same commit that converts its bbox.** (Sending `page_dims: {width: 1, height: 1}` also works.) Then cortex reads it as the ruled form, as it already does today.

## 3. Questions

1. **Lane 1 and 7f: which commit converts the review route's row evidence_ref to fractions, and does `page_dims` go away in that commit?** (See §2.) Until then, cortex reads both forms.
2. **Lane 1: does `GET /ingest/{id}/source` serve the PDF while the row is at `awaiting_kind`?**
   - The crop needs it there, before any review task exists.
   - If it refuses, the pane shows its own failure text and the picker still works. But the steward then picks without seeing the title.
   - The mock serves the source at every stage. I have not seen the real route's stage rule.

## 4. For ca (EvidenceRef's documentation)

Cortex's reader takes:
- `page`: an integer ≥ 1;
- `bbox`: 4 finite numbers with `0 ≤ x0 < x1 ≤ 1` and `0 ≤ y0 < y1 ≤ 1`, origin top-left. The edges 0 and 1 are allowed. Zero area is refused;
- `note`, when present: a non-blank string;
- no other keys.

If your documentation states the bounds differently (for example, it allows a zero-area box, or `x1 < x0`), tell me and one side changes. I would rather that than have the two disagree on a boundary case.

## 5. Not built here, still held

The **writing** side of evidence_ref (row ops and header edits) waits for Lane 1's "build after 202 is live, we will tell you". When it is built, a region the steward marks is sent in page fractions. Today cortex sends only what it sent before.

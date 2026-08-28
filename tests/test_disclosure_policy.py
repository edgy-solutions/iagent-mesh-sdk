"""POLICY: naming an unenforced gate is allowed only with a status marker.

THE RULE (owner's, 2026-08-27): "the unenforced gate naming is ok if it's marked as fixed or a
planned release is named to fix it."

WHY IT NEEDS A TEST RATHER THAN CARE. This package is published — a public GitHub repo, and a
PyPI release from the same tree — so its docstrings are read by people who are not on this
project. Commentary that names a gate which "verifies nothing" is genuinely valuable engineering
history when it says *and here is where that was closed*, and is a to-do list for someone else
when it does not. The difference is one clause, which is exactly the kind of thing that erodes:
the next author writes the vivid half and omits the boring half, and nothing complains.

So the boring half is enforced. Every passage in the SHIPPED PACKAGE that names a weak or
unenforced gate must carry, in the same passage, either

  * a CLOSURE marker — "CLOSED IN 0.2.0", "FIXED IN 0.4.0", "RETIRED", "no longer", … , or
  * a NAMED plan item in ``[[double-bracket]]`` form, which is this project's convention for a
    tracked, owned piece of work.

This checks the docstrings that SHIP. `tests/` and `docs/` are deliberately out of scope: they
are not in the wheel, and the test files necessarily quote defects verbatim while proving them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "iagent_mesh"

#: Phrases that assert a gate did not, or does not, enforce. Deliberately narrow — the point is
#: to catch DISCLOSURES, not every mention of the word "auth". Each is a phrase that would read
#: to an outsider as "here is something that was not checked".
DISCLOSURE_PATTERNS = [
    r"verifies nothing",
    r"verified nothing",
    r"gate no JWT",
    r"applied nowhere",
    r"importable-but-never-applied",
    r"never applied",
    r"200 unauthenticated",
    r"200 UNAUTHENTICATED",
    r"registered unminted",
    r"unauthenticated POST",
    r"silently trusted",
    r"could not verify",
    r"verify_signature.{0,4}False",
]

#: Either half of the rule satisfies it.
CLOSURE = re.compile(
    r"CLOSED IN|FIXED IN|CLOSED\b|FIXED\b|RETIRED|no longer exists|no longer|"
    r"THAT GAP IS CLOSED|is HISTORY|pre-\d|closed by",
    re.IGNORECASE,
)
PLAN_ITEM = re.compile(r"\[\[[a-z0-9][a-z0-9-]+\]\]")


def _shipped_files() -> list[Path]:
    return sorted(p for p in PKG.glob("*.py"))


def _paragraphs(text: str):
    """Split into blank-line-separated blocks, keeping the 1-based start line of each.

    A PARAGRAPH is the unit of judgement on purpose: the marker must sit next to the claim,
    where a reader meets it. A closure notice fifty lines away in the same file does not stop
    the disclosure from reading as live.
    """
    block, start = [], 1
    line_no = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not block:
                start = line_no
            block.append(line)
        elif block:
            yield start, "\n".join(block)
            block = []
    if block:
        yield start, "\n".join(block)


def _violations():
    out = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8")
        for start, para in _paragraphs(text):
            hits = [p for p in DISCLOSURE_PATTERNS if re.search(p, para)]
            if not hits:
                continue
            if CLOSURE.search(para) or PLAN_ITEM.search(para):
                continue
            out.append((path.name, start, hits, para.strip()[:240]))
    return out


def test_every_gate_disclosure_carries_a_status_marker():
    violations = _violations()
    if violations:
        report = "\n\n".join(
            f"{name}:{line} — matched {hits}\n"
            f"    Add a closure marker (e.g. 'CLOSED IN 0.4.0') or a named plan item\n"
            f"    (e.g. [[transport-flip]]) to THIS paragraph.\n"
            f"    {para}"
            for name, line, hits, para in violations
        )
        pytest.fail(
            f"{len(violations)} gate disclosure(s) in the shipped package name a weakness "
            f"without saying it is fixed or naming the work that fixes it:\n\n{report}"
        )


def test_the_policy_check_can_actually_fail():
    """POSITIVE CONTROL. A linter that cannot fire is decoration.

    Without this, deleting every pattern from DISCLOSURE_PATTERNS — or writing a CLOSURE regex
    that matches everything — would leave the suite green and the policy unenforced.
    """
    bare = "This gate verifies nothing and always has."
    assert any(re.search(p, bare) for p in DISCLOSURE_PATTERNS)
    assert not CLOSURE.search(bare) and not PLAN_ITEM.search(bare)

    marked_fixed = "This gate verifies nothing — CLOSED IN 0.2.0 by the transport dependency."
    assert CLOSURE.search(marked_fixed)

    marked_planned = "This gate verifies nothing; tracked as [[transport-flip]]."
    assert PLAN_ITEM.search(marked_planned)


def test_the_known_disclosures_are_still_present_and_marked():
    """The policy is satisfied by MARKING, never by deleting the history.

    A future author could pass `test_every_gate_disclosure_carries_a_status_marker` by stripping
    the commentary instead of maintaining it — which would trade an accurate record for a silent
    one and lose the reason each fix exists. These passages must therefore still be here, and
    still be marked.
    """
    ta = (PKG / "transport_auth.py").read_text(encoding="utf-8")
    assert "verifies nothing" in ta, "the presence-check history was deleted rather than marked"
    assert "CLOSED IN 0.2.0" in ta
    assert "[[transport-flip]]" in ta, "the OBSERVE default no longer names its planned flip"
    assert "[[da-sends-no-user-token]]" in ta
    assert "[[agentic-auth-flip]]" in ta


@pytest.mark.parametrize("slug", [
    "transport-flip",
    "agentic-auth-flip",
    "da-sends-no-user-token",
    "dag-tools-gateway-unverified-subject",
])
def test_named_plan_items_exist_in_the_platform_repo(slug):
    """A named item must be a REAL tracked item, not a plausible-looking slug.

    "Named a planned release" is only a real commitment if the name resolves to something with
    an owner and a status. An invented slug reads exactly like a tracked one, so the citation is
    checked against invincible-agent's `docs/plans/` — the same cross-repo pin used for the
    dag-tools client contract. SKIPS (loudly) when the platform repo is not checked out beside
    this one.
    """
    plans = Path(__file__).resolve().parents[2] / "invincible-agent" / "docs" / "plans"
    if not plans.is_dir():
        pytest.skip(f"invincible-agent not checked out at {plans} — plan citations UNVERIFIED")

    # The slug is either the filename or the `id:` in a plan item's frontmatter.
    if (plans / f"{slug}.md").is_file():
        return
    for md in plans.glob("*.md"):
        head = md.read_text(encoding="utf-8", errors="replace")[:600]
        if re.search(rf"^id:\s*{re.escape(slug)}\s*$", head, re.MULTILINE):
            return
    pytest.fail(
        f"docstrings cite [[{slug}]] but no plan item with that filename or `id:` exists in "
        f"{plans} — a citation that resolves to nothing is not a plan"
    )

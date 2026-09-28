"""`reachable_for` must REFUSE an unrecognised refusal clause, not return the permissive set.

REPORTED BY cortex-60 AND MEASURED HERE BEFORE THE FIX. Through 0.9.3 the function read:

    if refusal == "fail":
        return set(NON_HOLE_DISPOSITIONS)
    return set(ROW_DISPOSITIONS)

so every input but the exact string `"fail"` returned all five dispositions — `Fail`, `FAIL`,
`" fail"`, `"failed"`, `""`, `None`, `0`, `[]`, `False` and a YAML `refusal: no`, which
`safe_load` parses to `False`. Twelve of thirteen inputs tried came back permissive.

WHY THE PERMISSIVE DIRECTION IS THE HARMFUL ONE. The function's consumers are SEALS asking "is
every disposition this graph emitted allowed by its clause?". Against the full vocabulary that
question is trivially yes, so a clause typo SILENCES the seal rather than tripping it — the
failure mode with no symptom.

AND IT IS REACHABLE, NOT LATENT. The fleet's callers do not hand it a validated value: they read
the clause with `yaml.safe_load(...)["refusal"]` straight off the ratified row, a path
`GraphManifest` never validates. An unchecked string arrives here directly.

WHETHER IT BITES DEPENDS ON THE CONSUMER'S ASSERTION SHAPE, which is worth knowing before the
next one is written. A seal asserting `emitted == reachable` trips when `reachable` widens; one
asserting only `emitted <= reachable` does not. The same defect is loud or silent depending on
which was written, and nothing in the calling code says which you have.
"""

from __future__ import annotations

import pytest

from iagent_mesh.graph_manifest import REFUSAL_DISPOSITIONS
from iagent_mesh.rows import (NON_HOLE_DISPOSITIONS, ROW_DISPOSITIONS, _REACHABLE,
                              reachable_for)


# -- 1. the positive control, first ----------------------------------------------------------

def test_the_two_DECLARED_clauses_still_answer_and_still_DISAGREE():
    """POSITIVE CONTROL, and it is not optional here: a fix that refused everything would pass
    all thirteen refusal arms below while destroying the function. The two legal clauses must
    still answer, and must still answer DIFFERENTLY — the whole point of deriving reachability
    from the clause is that `fail` and `named-hole` do not reach the same set.
    """
    assert reachable_for("fail") == set(NON_HOLE_DISPOSITIONS)
    assert reachable_for("named-hole") == set(ROW_DISPOSITIONS)
    assert reachable_for("fail") != reachable_for("named-hole")
    assert not reachable_for("fail") & {"unentitled", "unavailable"}, (
        "a `fail` graph RAISES on a refused inner call, so it never returns a hole row"
    )


# -- 2. every input that used to come back permissive ----------------------------------------

@pytest.mark.parametrize("clause", [
    "Fail", "FAIL", " fail", "fail ", "failed", "", "nonsense", "raise", "none",
    None, 0, False, [],
])
def test_an_UNDECLARED_clause_is_REFUSED_rather_than_answered(clause):
    """Each of these returned all five terms through 0.9.3.

    `False` and `None` are here because they are not hypothetical: `refusal: no` in a ratified
    row is `False` after `safe_load`, and a row with the key absent hands `None` through the
    `.get` its callers use. `[]` is unhashable, so the guard must catch `TypeError` as well as
    `KeyError` — without that it raises the wrong exception and the caller sees a lookup bug
    rather than the named refusal.
    """
    with pytest.raises(ValueError, match="not a declared refusal clause"):
        reachable_for(clause)


def test_the_refusal_NAMES_the_clauses_it_would_have_accepted():
    """A reporter must fail LOUDER than what it reports. "Invalid clause" sends the reader back
    to the source; naming the two accepted spellings is what makes a typo fixable from the
    message alone."""
    with pytest.raises(ValueError) as exc:
        reachable_for("Fail")
    assert "'fail'" in str(exc.value) and "'named-hole'" in str(exc.value)
    assert "'Fail'" in str(exc.value), "the refusal does not echo what it was given"


# -- 3. the seal the table depends on --------------------------------------------------------

def test_the_table_and_the_declared_vocabulary_AGREE():
    """THE ONE THING THE TABLE CANNOT PROVE ABOUT ITSELF.

    `rows.py` is stdlib-imports-only — the property that let this vocabulary move repos without a
    single change — so `_REACHABLE` does NOT import `REFUSAL_DISPOSITIONS`. Two spellings of one
    vocabulary agree until someone edits one, which is the failure the extraction exists to
    prevent, so the agreement is ASSERTED here rather than assumed.

    A third clause added to `REFUSAL_DISPOSITIONS` fails this test until it is given a
    reachability row — which is the loud version of what used to happen silently, when an
    unrecognised clause simply inherited the permissive set by falling off the end of an `if`.
    """
    assert set(_REACHABLE) == set(REFUSAL_DISPOSITIONS), (
        f"the reachability table covers {sorted(_REACHABLE)} but the declared refusal "
        f"vocabulary is {sorted(REFUSAL_DISPOSITIONS)} — a clause in one and not the other is "
        f"either an unreachable name or a clause with no declared reachability"
    )


def test_every_clause_in_the_table_reaches_a_SUBSET_of_the_full_vocabulary():
    """A reachability row naming a disposition that is not in `ROW_DISPOSITIONS` would be a
    sixth term invented by the table, which no reader of a ledger row could interpret."""
    for clause, reachable in _REACHABLE.items():
        assert set(reachable) <= set(ROW_DISPOSITIONS), (
            f"{clause!r} claims dispositions outside the declared vocabulary: "
            f"{sorted(set(reachable) - set(ROW_DISPOSITIONS))}"
        )

"""A computed figure may say how it was computed â€” and an output that does not say is unchanged.

THE DEFECT THE SHAPE PREVENTS: a number arrives with no formula, no inputs and no producer, so a
reader cannot re-derive it or tell which code made it. `ToolOutput.method` carries the answer.

THE OTHER HALF IS "OPTIONAL AND ADDITIVE": every output already in the fleet subclasses
`ToolOutput`, and none of them may be forced to supply a method or refused for not having one.
"""
from __future__ import annotations

from typing import Optional

import pytest
from pydantic import ValidationError

from iagent_mesh.models import MethodBlock, ToolOutput

_BLOCK = dict(formula="rate * hours", inputs=["rate", "hours"], producer_sha="abc1234")


# â”€â”€ the block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_A_METHOD_BLOCK_ROUND_TRIPS():
    m = MethodBlock(**_BLOCK, bound=40.0, bound_defaulted=False)
    assert MethodBlock(**m.model_dump()) == m


def test_BOUND_DEFAULTED_IS_UNKNOWN_UNTIL_SAID_AND_UNKNOWN_IS_NOT_FALSE():
    """`None` is "the producer did not say"; `False` is "the caller supplied it". Collapsing them
    would let every silent producer read as having asked the caller for its bound."""
    m = MethodBlock(**_BLOCK)
    assert m.bound is None
    assert m.bound_defaulted is None
    assert m.bound_defaulted is not False


@pytest.mark.parametrize("field", ["formula", "producer_sha"])
def test_A_BLANK_FORMULA_OR_PRODUCER_IS_REFUSED(field):
    with pytest.raises(ValidationError):
        MethodBlock(**{**_BLOCK, field: "  "})


@pytest.mark.parametrize("field", ["formula", "inputs", "producer_sha"])
def test_THE_REQUIRED_FIELDS_ARE_REQUIRED(field):
    without = {k: v for k, v in _BLOCK.items() if k != field}
    with pytest.raises(ValidationError):
        MethodBlock(**without)


def test_AN_UNDECLARED_KEY_IS_REFUSED_rather_than_dropped():
    with pytest.raises(ValidationError):
        MethodBlock(**_BLOCK, producer="abc1234")  # a misspelt producer_sha must not vanish


# â”€â”€ additive â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _Existing(ToolOutput):
    total: float


def test_AN_EXISTING_OUTPUT_NEEDS_NO_METHOD():
    """THE ARM THAT MATTERS: a subclass written before this field existed still validates."""
    out = _Existing(total=3.0)
    assert out.method is None
    assert out.model_dump() == {"total": 3.0}, (
        "an output that sets no method must dump as it always did — a `method: null` key in every "
        "output in the fleet is not additive"
    )
    assert "method" not in out.model_dump_json()


def test_AN_OUTPUT_CAN_CARRY_A_METHOD_AND_IT_SURVIVES_A_DUMP():
    out = _Existing(total=3.0, method=MethodBlock(**_BLOCK))
    assert _Existing(**out.model_dump()).method == MethodBlock(**_BLOCK)


def test_A_SUBCLASS_THAT_ALREADY_HAS_ITS_OWN_METHOD_FIELD_KEEPS_IT():
    """The name is a common one. The base must not take it away from an output that already used
    it for something else."""
    class Own(ToolOutput):
        method: str

    assert Own(method="ols").method == "ols"
    with pytest.raises(ValidationError):
        Own()


def test_A_SUBCLASS_METHOD_FIELD_THAT_IS_NONE_IS_STILL_DUMPED():
    """Omitting an unset block must not swallow a subclass's own `None`: that field's absence
    would read as "never declared" and its `None` as "declared and empty"."""
    class Own(ToolOutput):
        method: Optional[str] = None

    assert Own().model_dump() == {"method": None}

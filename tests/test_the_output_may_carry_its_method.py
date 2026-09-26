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

from iagent_mesh.models import MethodBlock, MethodInput, ToolOutput

_BLOCK = dict(formula="rate * hours", inputs=[{"name": "rate", "value": 12.5, "unit": "USD/h"}, {"name": "hours", "value": 8}], producer_sha="abc1234")


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


# ── inputs carry their values ────────────────────────────────────────────────────────────

def test_AN_INPUT_CARRIES_ITS_VALUE_AND_AN_OPTIONAL_UNIT():
    m = MethodBlock(**_BLOCK)
    rate, hours = m.inputs
    assert (rate.name, rate.value, rate.unit) == ("rate", 12.5, "USD/h")
    assert hours.unit is None, "no unit stated is None — not dimensionless, not an empty string"


def test_THE_BARE_NAME_FORM_IS_REFUSED_rather_than_coerced():
    """`inputs` was `list[str]`. A name with no value is exactly what this block now refuses to
    carry: a formula's inputs are only re-derivable if their values are recorded."""
    with pytest.raises(ValidationError):
        MethodBlock(**{**_BLOCK, "inputs": ["rate", "hours"]})


def test_AN_INPUT_VALUE_KEEPS_ITS_TYPE():
    """`12` must not become `12.0`, nor `True` become `1`: the value is evidence of what ran."""
    m = MethodBlock(**{**_BLOCK, "inputs": [
        {"name": "n", "value": 12}, {"name": "on", "value": True}, {"name": "x", "value": 0.5},
    ]})
    assert [type(i.value) for i in m.inputs] == [int, bool, float]


@pytest.mark.parametrize("bad", [
    {"name": " ", "value": 1},
    {"name": "x", "value": 1, "unit": " "},
    {"name": "x"},
    {"name": "x", "value": 1, "scale": 2},
])
def test_A_MALFORMED_INPUT_IS_REFUSED(bad):
    with pytest.raises(ValidationError):
        MethodInput(**bad)

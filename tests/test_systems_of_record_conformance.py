"""`check_system_of_record_query_contract` (0.9.9, lane/saf's proposal 1) must go red on the
implementations it exists to reject, the same discipline as `test_ingest_conformance.py` and
`test_writer_conformance.py`.

THE DEFECTS THIS ARM EXISTS TO CATCH: a `query()` that returns nothing for a value its own
fixture holds; a `query()` whose result cannot be iterated twice (a one-shot iterator, silently
empty on a caller's second pass — count, then cite); records whose keys drift from the row's own
`lookup.returns`; records missing the `record_id` a caller needs to build the
`f"{connector}:{record_id}"` citation; two records that collide onto the same citation; and a
`lookup()` widened into returning a list once `query()` exists beside it — the control proving
the single-record path stays untouched.

Nothing here imports a driver; both fixtures are plain Python.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_system_of_record_query_contract,
    check_system_of_record_query_independence_contract,
)

_CONNECTOR = "sor-events-a"
_RETURNS = ("owner_domain", "program")
_RECORDS = [
    {"owner_domain": "SUSTAINMENT", "program": "F-35", "record_id": "r1"},
    {"owner_domain": "SUSTAINMENT", "program": "F-16", "record_id": "r2"},
]


class _GoodConnector:
    """The reference connector: query() re-builds a fresh list every call (safely re-iterable),
    records are keyed by exactly `_RETURNS` plus `record_id`, and lookup() keeps returning at
    most one dict."""

    def query(self, value: str):
        return [dict(r) for r in _RECORDS] if value == "PN-9001" else []

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def _check(connector) -> None:
    check_system_of_record_query_contract(
        connector=_CONNECTOR,
        returns=_RETURNS,
        call_query_known=lambda: connector.query("PN-9001"),
        call_query_unknown=lambda: connector.query("PN-UNKNOWN"),
        call_lookup_known=lambda: connector.lookup("PN-9001"),
    )


def test_accepts_a_connector_whose_query_and_lookup_both_behave():
    _check(_GoodConnector())


class _EmptyQueryConnector:
    """BROKEN: query() never returns anything, even for a value the fixture holds."""

    def query(self, value: str):
        return []

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def test_rejects_a_query_that_never_returns_a_hit():
    with pytest.raises(ConformanceFailure, match="no records"):
        _check(_EmptyQueryConnector())


class _OneShotQueryConnector:
    """BROKEN: query() returns a one-shot iterator — the SAME object goes empty on a second
    pass, exactly the "count, then cite" failure the re-iterability check exists to catch."""

    def query(self, value: str):
        return iter([dict(r) for r in _RECORDS] if value == "PN-9001" else [])

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def test_rejects_a_query_whose_result_is_not_re_iterable():
    with pytest.raises(ConformanceFailure, match="RE-ITERABLE"):
        _check(_OneShotQueryConnector())


class _WrongKeysConnector:
    """BROKEN: records carry a connector-invented field instead of the row's own `returns`."""

    def query(self, value: str):
        if value != "PN-9001":
            return []
        return [{"owner_domain": "SUSTAINMENT", "payload": "F-35", "record_id": "r1"}]

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def test_rejects_records_keyed_off_the_rows_own_returns():
    with pytest.raises(ConformanceFailure, match="lookup.returns"):
        _check(_WrongKeysConnector())


class _MissingRecordIdConnector:
    """BROKEN: a record has no `record_id` at all — no citation can be built from it."""

    def query(self, value: str):
        if value != "PN-9001":
            return []
        return [{"owner_domain": "SUSTAINMENT", "program": "F-35"}]

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def test_rejects_a_record_missing_record_id():
    with pytest.raises(ConformanceFailure, match="record_id"):
        _check(_MissingRecordIdConnector())


class _CollidingCitationConnector:
    """BROKEN: two distinct records share one record_id — their citations collide."""

    def query(self, value: str):
        if value != "PN-9001":
            return []
        return [
            {"owner_domain": "SUSTAINMENT", "program": "F-35", "record_id": "r1"},
            {"owner_domain": "SUSTAINMENT", "program": "F-16", "record_id": "r1"},
        ]

    def lookup(self, value: str):
        return dict(_RECORDS[0]) if value == "PN-9001" else None


def test_rejects_records_whose_citations_collide():
    with pytest.raises(ConformanceFailure, match="collide"):
        _check(_CollidingCitationConnector())


class _LookupWidenedConnector:
    """BROKEN: lookup() was widened into returning a list once query() was added — the exact
    regression the control call exists to catch."""

    def query(self, value: str):
        return [dict(r) for r in _RECORDS] if value == "PN-9001" else []

    def lookup(self, value: str):
        return [dict(r) for r in _RECORDS] if value == "PN-9001" else []


def test_rejects_a_lookup_widened_into_returning_a_list():
    with pytest.raises(ConformanceFailure, match="dict-or-None"):
        _check(_LookupWidenedConnector())


# ── check_system_of_record_query_independence_contract, added 2026-10-10 (0.9.10 branch item 3)

_A_RECORDS = [{"owner_domain": "SUSTAINMENT", "program": "F-35", "record_id": "a1"}]
_B_RECORDS = [{"owner_domain": "SUSTAINMENT", "program": "F-16", "record_id": "b1"}]


class _IndependentConnector:
    """The reference connector: query() is a pure function of its argument, no shared state
    between calls."""

    def query(self, value: str):
        if value == "A":
            return list(_A_RECORDS)
        if value == "B":
            return list(_B_RECORDS)
        return []


def _check_independence(connector) -> None:
    check_system_of_record_query_independence_contract(
        call_query_value_a=lambda: connector.query("A"),
        call_query_value_b=lambda: connector.query("B"),
        call_query_value_a_again=lambda: connector.query("A"),
    )


def test_accepts_a_connector_whose_query_is_independent_across_values():
    _check_independence(_IndependentConnector())


class _BleedingConnector:
    """BROKEN: a shared cursor/counter is consumed by the first call to A — querying A a second
    time, after B has been queried, comes back empty. State bleeds across values."""

    def __init__(self) -> None:
        self._a_calls = 0

    def query(self, value: str):
        if value == "A":
            self._a_calls += 1
            return list(_A_RECORDS) if self._a_calls == 1 else []
        if value == "B":
            return list(_B_RECORDS)
        return []


def test_rejects_a_connector_whose_second_answer_for_a_is_perturbed_by_querying_b():
    with pytest.raises(ConformanceFailure, match="SAME value must produce the SAME records"):
        _check_independence(_BleedingConnector())


class _IgnoresValueConnector:
    """BROKEN: query() ignores its argument and always returns the same fixed set — A and B come
    back identical, so this fixture cannot tell 'independent' apart from 'constant'."""

    def query(self, value: str):
        return list(_A_RECORDS)


def test_rejects_a_fixture_where_a_and_b_are_not_actually_distinct():
    with pytest.raises(ConformanceFailure, match="record sets actually differ"):
        _check_independence(_IgnoresValueConnector())


class _OneShotOnSecondCallConnector:
    """BROKEN: A's SECOND query (the one made after B) returns a one-shot iterator — correct data
    on the first pass, silently empty on a re-iteration."""

    def __init__(self) -> None:
        self._a_calls = 0

    def query(self, value: str):
        if value == "A":
            self._a_calls += 1
            return list(_A_RECORDS) if self._a_calls == 1 else iter(_A_RECORDS)
        if value == "B":
            return list(_B_RECORDS)
        return []


def test_rejects_a_second_answer_for_a_that_is_not_re_iterable():
    with pytest.raises(ConformanceFailure, match="RE-ITERABLE"):
        _check_independence(_OneShotOnSecondCallConnector())

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

from iagent_mesh.conformance import ConformanceFailure, check_system_of_record_query_contract

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

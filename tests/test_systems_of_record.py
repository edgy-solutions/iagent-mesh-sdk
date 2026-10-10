"""Seals for the 0.9.7 systems-of-record schema and `Origin` — the architect's "ORIGIN, not
audience" ruling, item 1. One seal per ruling the module docstring states, so a later edit that
quietly reverses a ruling fails here first.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from iagent_mesh.systems_of_record import (
    ConnectorLookup,
    IdentityMatch,
    Origin,
    SystemOfRecord,
    SystemOfRecordConnector,
    SystemOfRecordQuery,
    UnknownConnector,
    compose,
    load_systems_of_record,
    match_system_of_record,
    validate_connectors_known,
    validate_dir,
)
from iagent_mesh.declarations import DeclarationError


def _row(id_="sor-events-a", pattern=r"^WO-\d+$", fields=("work_order_ref",),
         connector="sor-events-a", returns=("owner_domain", "program"),
         program_field="program") -> SystemOfRecord:
    return SystemOfRecord(
        id=id_, kind="fracas", owner_domain="SUSTAINMENT",
        identity=IdentityMatch(pattern=pattern, fields=fields),
        lookup=ConnectorLookup(connector=connector, returns=returns),
        program_field=program_field,
    )


# ── SystemOfRecord shape ─────────────────────────────────────────────────────────────────

def test_program_field_must_be_in_lookup_returns():
    with pytest.raises(ValidationError, match="not in lookup.returns"):
        _row(program_field="not_returned")


def test_identity_pattern_must_be_a_valid_regex():
    with pytest.raises(ValidationError, match="not a valid regex"):
        IdentityMatch(pattern="(unclosed", fields=("x",))


def test_identity_fields_must_be_nonempty():
    with pytest.raises(ValidationError, match="no named field"):
        IdentityMatch(pattern=".*", fields=())


def test_lookup_returns_must_be_nonempty():
    with pytest.raises(ValidationError, match="return nothing"):
        ConnectorLookup(connector="sor-events-a", returns=())


def test_blank_required_strings_refused():
    with pytest.raises(ValidationError):
        _row(id_="")
    with pytest.raises(ValidationError):
        _row(program_field="")
    with pytest.raises(ValidationError):
        SystemOfRecord(
            id="sor-events-a", kind="", owner_domain="SUSTAINMENT",
            identity=IdentityMatch(pattern=r"^WO-\d+$", fields=("work_order_ref",)),
            lookup=ConnectorLookup(connector="sor-events-a", returns=("owner_domain", "program")),
            program_field="program",
        )
    with pytest.raises(ValidationError):
        SystemOfRecord(
            id="sor-events-a", kind="fracas", owner_domain="",
            identity=IdentityMatch(pattern=r"^WO-\d+$", fields=("work_order_ref",)),
            lookup=ConnectorLookup(connector="sor-events-a", returns=("owner_domain", "program")),
            program_field="program",
        )


# ── match_system_of_record — the pure half, no connector call ───────────────────────────────

def test_first_matching_system_wins_in_row_order():
    sor_events_a = _row(id_="sor-events-a", pattern=r"^WO-\d+$", fields=("work_order_ref",))
    sor_plm_a = _row(id_="sor-plm-a", pattern=r"^SPA-\d+$", fields=("component_serial",))
    identity = {"work_order_ref": "WO-12345", "component_serial": "SPA-999"}
    assert match_system_of_record(identity, [sor_events_a, sor_plm_a]) is sor_events_a
    assert match_system_of_record(identity, [sor_plm_a, sor_events_a]) is sor_plm_a


def test_no_match_is_none_not_a_refusal():
    row = _row(pattern=r"^WO-\d+$", fields=("work_order_ref",))
    assert match_system_of_record({"work_order_ref": "nope"}, [row]) is None
    assert match_system_of_record({}, [row]) is None


def test_match_tests_fields_in_priority_order():
    row = _row(pattern=r"^A", fields=("primary", "secondary"))
    # primary present but non-matching, secondary matches — secondary field is still tried.
    assert match_system_of_record({"primary": "Z1", "secondary": "A2"}, [row]) is row
    # neither matches.
    assert match_system_of_record({"primary": "Z1", "secondary": "Z2"}, [row]) is None


# ── SystemOfRecordQuery — 0.9.9, lane/saf's proposal 1, a SIBLING to SystemOfRecordConnector ──

class _FakeConnectorWithQuery:
    """A fixture connector carrying both the existing `lookup` and the new `query` — proves the
    two are siblings on one object, same as a real connector would be, not two unrelated types."""

    def __init__(self) -> None:
        self._records = [
            {"owner_domain": "SUSTAINMENT", "program": "F-35", "record_id": "r1"},
            {"owner_domain": "SUSTAINMENT", "program": "F-16", "record_id": "r2"},
        ]

    def lookup(self, value: str):
        return dict(self._records[0]) if value == "PN-9001" else None

    def query(self, value: str):
        return [dict(r) for r in self._records] if value == "PN-9001" else []


def test_a_connector_can_satisfy_both_protocols_at_once():
    connector = _FakeConnectorWithQuery()
    assert isinstance(connector, SystemOfRecordConnector)
    assert isinstance(connector, SystemOfRecordQuery)


def test_query_returns_every_record_lookup_only_returns_one():
    connector = _FakeConnectorWithQuery()
    hits = list(connector.query("PN-9001"))
    assert len(hits) == 2
    assert connector.lookup("PN-9001") == hits[0]


def test_query_miss_is_an_empty_iterable_not_none():
    connector = _FakeConnectorWithQuery()
    miss = connector.query("PN-UNKNOWN")
    assert list(miss) == []
    assert miss is not None


def test_query_record_round_trips_to_the_lookup_dot_connector_colon_record_id_citation():
    connector = _FakeConnectorWithQuery()
    hit = list(connector.query("PN-9001"))[0]
    citation = f"sor-events-a:{hit['record_id']}"
    assert citation == "sor-events-a:r1"


# ── connector registry refusal — the "prefix-registry failure class" ────────────────────────

def test_unknown_connector_is_a_named_refusal_not_a_silent_miss():
    row = _row(connector="sor-events-a")
    with pytest.raises(UnknownConnector, match="sor-events-a"):
        validate_connectors_known([row], known_connectors=["sor-plm-a"])


def test_known_connector_passes_silently():
    row = _row(connector="sor-events-a")
    validate_connectors_known([row], known_connectors=["sor-events-a", "sor-plm-a"])


# ── Origin — resolved_by shape rulings ───────────────────────────────────────────────────────

def test_unresolved_origin_carries_nothing():
    Origin(resolved_by="unresolved")
    with pytest.raises(ValidationError, match="must carry no owner_domain"):
        Origin(resolved_by="unresolved", owner_domain="SUSTAINMENT")


def test_resolved_origin_requires_owner_domain():
    with pytest.raises(ValidationError, match="requires owner_domain"):
        Origin(resolved_by="steward", evidence=("steward-ref-1",))


def test_record_resolution_requires_evidence():
    with pytest.raises(ValidationError, match="requires evidence"):
        Origin(resolved_by="record", owner_domain="SUSTAINMENT")
    Origin(resolved_by="record", owner_domain="SUSTAINMENT", evidence=("sor-events-a:WO-12345",))


def test_steward_resolution_does_not_require_evidence():
    Origin(resolved_by="steward", owner_domain="SUSTAINMENT")


def test_resolved_by_is_not_obtained_via():
    # Origin has no obtained_via field at all — a distinct vocabulary, per the module's ruling 4.
    assert not hasattr(Origin(resolved_by="unresolved"), "obtained_via")


# ── the composer family — same mechanism, same tombstone/duplicate-key discipline ───────────

def test_load_and_compose_round_trip(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "sor-events-a.yaml").write_text(
        "id: sor-events-a\nkind: fracas\nowner_domain: SUSTAINMENT\n"
        "identity:\n  pattern: '^WO-\\\\d+$'\n  fields: [work_order_ref]\n"
        "lookup:\n  connector: sor-events-a\n  returns: [owner_domain, program]\n"
        "program_field: program\n",
        encoding="utf-8",
    )
    rows = load_systems_of_record(seed)
    assert [r.id for r in rows] == ["sor-events-a"]
    assert validate_dir(seed)[0].id == "sor-events-a"

    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "sor-plm-a.yaml").write_text(
        "id: sor-plm-a\nkind: rcm\nowner_domain: SUSTAINMENT\n"
        "identity:\n  pattern: '^SPA-\\\\d+$'\n  fields: [component_serial]\n"
        "lookup:\n  connector: sor-plm-a\n  returns: [owner_domain, program]\n"
        "program_field: program\n",
        encoding="utf-8",
    )
    composed = compose(seed, [overlay])
    assert [r.id for r in composed] == ["sor-events-a", "sor-plm-a"]


def test_duplicate_id_in_one_directory_refuses(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    row_yaml = (
        "id: sor-events-a\nkind: fracas\nowner_domain: SUSTAINMENT\n"
        "identity:\n  pattern: '^WO-\\\\d+$'\n  fields: [work_order_ref]\n"
        "lookup:\n  connector: sor-events-a\n  returns: [owner_domain, program]\n"
        "program_field: program\n"
    )
    (seed / "a.yaml").write_text(row_yaml, encoding="utf-8")
    (seed / "b.yaml").write_text(row_yaml, encoding="utf-8")
    with pytest.raises(DeclarationError, match="both declare"):
        load_systems_of_record(seed)

"""`check_provenance_floor_contract` / `check_provenance_sources_contract` (0.9.9, item 2 of
today's packet) must go red on the implementations they exist to reject, the same discipline as
`test_systems_of_record_conformance.py` and `test_writer_conformance.py`.

Neither arm admits an implementation of an SDK Protocol — `provenance_floor()` and
`whichPartsDoesThisNoticeAffect` both live in invincible-agent, not here, and neither is a
Protocol this SDK defines. What these arms state are the invariants this SDK's OWN vocabulary
(`OBTAINED_VIA`'s ordering, the `promoted` ingest stage, `ProvenanceBlock`'s required fields)
forces on any caller-side function shaped like "the weakest provenance behind an answer" or "the
per-source provenance list behind a graph read". Nothing here imports invincible-agent; every
fixture below is a plain Python function this file owns.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_provenance_floor_contract,
    check_provenance_sources_contract,
)
from iagent_mesh.provenance import DIRECT, ETL, OBTAINED_VIA, USER_DROP, make_provenance

UNSTAMPED = "unstamped"

_DIRECT_SOURCES = [
    {"obtained_via": DIRECT, "ingest_id": "d1"},
    {"obtained_via": DIRECT, "ingest_id": "d2"},
]
_USER_DROP_SOURCE = {"obtained_via": USER_DROP, "ingest_id": "u1"}
_USER_DROP_NO_ID_SOURCE = {"obtained_via": USER_DROP, "ingest_id": None}


def _check_floor(floor_fn) -> None:
    check_provenance_floor_contract(
        unstamped=UNSTAMPED,
        call_floor_of_direct_only=lambda: floor_fn(list(_DIRECT_SOURCES)),
        call_floor_of_direct_and_user_drop=lambda: floor_fn(_DIRECT_SOURCES + [_USER_DROP_SOURCE]),
        call_floor_of_user_drop_once_promoted=lambda: floor_fn(
            _DIRECT_SOURCES + [_USER_DROP_SOURCE], promoted={"u1"}
        ),
        call_floor_of_user_drop_with_no_ingest_id=lambda: floor_fn(
            [_DIRECT_SOURCES[0], _USER_DROP_NO_ID_SOURCE]
        ),
    )


def _good_floor(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    user_drops = [s for s in live if s["obtained_via"] == USER_DROP]
    if user_drops:
        obtained_via = USER_DROP
    elif live:
        obtained_via = max((s["obtained_via"] for s in live), key=OBTAINED_VIA.index)
    else:
        obtained_via = UNSTAMPED
    ingest_ids = sorted({s["ingest_id"] for s in user_drops if s.get("ingest_id")})
    unidentified = sum(1 for s in user_drops if not s.get("ingest_id"))
    return {"obtained_via": obtained_via, "ingest_ids": ingest_ids, "unidentified": unidentified}


def test_accepts_a_floor_function_that_tracks_the_weakest_unpromoted_rung():
    _check_floor(_good_floor)


def _broken_always_unstamped(sources, promoted=()):
    return {"obtained_via": UNSTAMPED, "ingest_ids": [], "unidentified": 0}


def test_rejects_a_floor_that_never_reports_a_real_rung():
    with pytest.raises(ConformanceFailure, match="direct itself"):
        _check_floor(_broken_always_unstamped)


def _broken_ignores_user_drop_entirely(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    return {"obtained_via": DIRECT if live else UNSTAMPED, "ingest_ids": [], "unidentified": 0}


def test_rejects_a_floor_that_cannot_tell_direct_only_from_direct_plus_user_drop():
    with pytest.raises(ConformanceFailure, match="does not discriminate"):
        _check_floor(_broken_ignores_user_drop_entirely)


def _broken_undercounts_user_drop(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    if not live:
        return {"obtained_via": UNSTAMPED, "ingest_ids": [], "unidentified": 0}
    has_user_drop = any(s["obtained_via"] == USER_DROP for s in live)
    return {"obtained_via": ETL if has_user_drop else DIRECT, "ingest_ids": [], "unidentified": 0}


def test_rejects_a_floor_that_does_not_move_all_the_way_to_user_drop():
    with pytest.raises(ConformanceFailure, match="WORST source drawn on"):
        _check_floor(_broken_undercounts_user_drop)


def _broken_ignores_promotion(sources, promoted=()):
    return _good_floor(sources, promoted=())  # BUG: `promoted` is never consulted


def test_rejects_a_floor_that_cannot_tell_unpromoted_from_promoted():
    with pytest.raises(ConformanceFailure, match="does not discriminate"):
        _check_floor(_broken_ignores_promotion)


def _broken_promotes_the_id_not_the_rung(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    user_drops_all = [s for s in sources if s["obtained_via"] == USER_DROP]
    if user_drops_all:
        obtained_via = USER_DROP  # BUG: computed over the UNFILTERED sources, ignoring `promoted`
    elif sources:
        obtained_via = max((s["obtained_via"] for s in sources), key=OBTAINED_VIA.index)
    else:
        obtained_via = UNSTAMPED
    user_drops_live = [s for s in live if s["obtained_via"] == USER_DROP]
    ingest_ids = sorted({s["ingest_id"] for s in user_drops_live if s.get("ingest_id")})
    unidentified = sum(1 for s in user_drops_live if not s.get("ingest_id"))
    return {"obtained_via": obtained_via, "ingest_ids": ingest_ids, "unidentified": unidentified}


def test_rejects_a_floor_where_promotion_clears_the_id_but_not_the_rung():
    with pytest.raises(ConformanceFailure, match="promoting the ONLY user-drop source"):
        _check_floor(_broken_promotes_the_id_not_the_rung)


def _broken_drops_unidentified(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    user_drops = [s for s in live if s["obtained_via"] == USER_DROP]
    if user_drops:
        obtained_via = USER_DROP
    elif live:
        obtained_via = max((s["obtained_via"] for s in live), key=OBTAINED_VIA.index)
    else:
        obtained_via = UNSTAMPED
    ingest_ids = sorted({s["ingest_id"] for s in user_drops if s.get("ingest_id")})
    return {"obtained_via": obtained_via, "ingest_ids": ingest_ids, "unidentified": 0}  # BUG


def test_rejects_a_floor_that_silently_drops_unidentified_user_drops():
    with pytest.raises(ConformanceFailure, match="unidentified=0"):
        _check_floor(_broken_drops_unidentified)


def _broken_blank_id_in_list(sources, promoted=()):
    live = [s for s in sources if s.get("ingest_id") not in promoted]
    user_drops = [s for s in live if s["obtained_via"] == USER_DROP]
    if user_drops:
        obtained_via = USER_DROP
    elif live:
        obtained_via = max((s["obtained_via"] for s in live), key=OBTAINED_VIA.index)
    else:
        obtained_via = UNSTAMPED
    ingest_ids = [s.get("ingest_id") or "" for s in user_drops]  # BUG: blank entries, not omitted
    unidentified = sum(1 for s in user_drops if not s.get("ingest_id"))
    return {"obtained_via": obtained_via, "ingest_ids": ingest_ids, "unidentified": unidentified}


def test_rejects_a_floor_that_puts_a_blank_entry_in_ingest_ids():
    with pytest.raises(ConformanceFailure, match="ingest_ids contains"):
        _check_floor(_broken_blank_id_in_list)


# ── check_provenance_sources_contract ───────────────────────────────────────────────────────

_STAMPED_BLOCK = make_provenance(
    authoritative_source="SRC", obtained_via=DIRECT, as_of="2026-01-01",
    ingested_at="2026-01-01T00:00:00Z", ingest_run="run-1", standing="supervised",
    ingest_id="ing-1",
)


def _check_sources(sources_fn) -> None:
    check_provenance_sources_contract(
        unstamped=UNSTAMPED,
        call_sources_for_a_stamped_item=lambda: sources_fn(seeded=False),
        call_sources_for_a_seeded_item=lambda: sources_fn(seeded=True),
    )


def _good_sources(seeded: bool):
    if seeded:
        return [{"provenance": UNSTAMPED}]
    return [{"provenance": dict(_STAMPED_BLOCK)}]


def test_accepts_a_sources_function_that_stamps_tracked_rows_and_sentinels_seeded_ones():
    _check_sources(_good_sources)


def _broken_stamped_empty(seeded: bool):
    return [] if not seeded else _good_sources(seeded)


def test_rejects_a_sources_function_with_no_sources_for_a_stamped_item():
    with pytest.raises(ConformanceFailure, match="empty source list"):
        _check_sources(_broken_stamped_empty)


def _broken_stamped_no_provenance(seeded: bool):
    return [{"provenance": None}] if not seeded else _good_sources(seeded)


def test_rejects_a_stamped_source_carrying_no_provenance_block():
    with pytest.raises(ConformanceFailure, match="carries no provenance block"):
        _check_sources(_broken_stamped_no_provenance)


def _broken_stamped_incomplete(seeded: bool):
    if seeded:
        return _good_sources(seeded)
    incomplete = dict(_STAMPED_BLOCK)
    del incomplete["standing"]
    return [{"provenance": incomplete}]


def test_rejects_a_stamped_source_whose_block_is_incomplete():
    with pytest.raises(ConformanceFailure, match="validate_provenance"):
        _check_sources(_broken_stamped_incomplete)


def _broken_seeded_empty(seeded: bool):
    return [] if seeded else _good_sources(seeded)


def test_rejects_a_sources_function_with_no_sources_for_a_seeded_item():
    with pytest.raises(ConformanceFailure, match="empty source list"):
        _check_sources(_broken_seeded_empty)


def _broken_seeded_not_sentinel(seeded: bool):
    return [{"provenance": dict(_STAMPED_BLOCK)}] if seeded else _good_sources(seeded)


def test_rejects_a_seeded_source_that_carries_a_full_block_instead_of_the_sentinel():
    with pytest.raises(ConformanceFailure, match="caller's own unstamped"):
        _check_sources(_broken_seeded_not_sentinel)

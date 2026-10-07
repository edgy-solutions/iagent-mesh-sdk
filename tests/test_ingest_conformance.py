"""The two conformance arms added 2026-10-06 — `check_artifact_revision_chain_contract` and
`check_refresh_spec_pull_contract` — must go red on the implementations they exist to reject, the
same discipline as `test_the_ontology_conformance_arm_bites.py` and
`test_writer_conformance.py`.

THE DEFECT `check_artifact_revision_chain_contract` EXISTS TO CATCH: a seam whose "build the next
revision" step does not read its own chain's actual head — it emits a constant, or freezes at
rev=1, rather than extending the chain it is supposed to be appending to.

THE DEFECT `check_refresh_spec_pull_contract` EXISTS TO CATCH: a seam that resolves a refresh
pull's URL without actually substituting the artifact's own identity value into the template.

Nothing here imports a driver; both fixtures are plain Python.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_artifact_revision_chain_contract,
    check_refresh_spec_pull_contract,
)
from iagent_mesh.ingest import ArtifactRevision
from iagent_mesh.provenance import DIRECT, make_provenance

_PROVENANCE = make_provenance(
    authoritative_source="vendor-feed", obtained_via=DIRECT, as_of="2026-10-06",
    ingested_at="2026-10-06T00:00:00Z", ingest_run="run-1", standing="trusted",
)


# ── check_artifact_revision_chain_contract ──────────────────────────────────────────────────

class _ChainSeam:
    """The reference builder: reads its own chain's current length before building the next
    row. `_FrozenChainSeam`/`_ConstantChainSeam` below are the broken variants."""

    def __init__(self) -> None:
        self._chain: list[ArtifactRevision] = []

    def build_next(self) -> ArtifactRevision:
        rev = len(self._chain) + 1
        row = ArtifactRevision(
            rev=rev, received_at="2026-10-06T00:00:00Z", provenance=_PROVENANCE,
            supersedes=(rev - 1) if rev > 1 else None,
        )
        self._chain.append(row)
        return row


class _FrozenChainSeam:
    """BROKEN: always returns rev=1 — never advances past the first revision."""

    def build_next(self) -> ArtifactRevision:
        return ArtifactRevision(
            rev=1, received_at="2026-10-06T00:00:00Z", provenance=_PROVENANCE, supersedes=None,
        )


def test_chain_contract_accepts_a_seam_that_reads_its_own_head():
    seam = _ChainSeam()
    check_artifact_revision_chain_contract(
        call_build_initial_revision=seam.build_next,
        call_build_next_revision=seam.build_next,
    )


def test_chain_contract_rejects_a_seam_frozen_at_rev_one():
    seam = _FrozenChainSeam()
    with pytest.raises(ConformanceFailure, match="does not discriminate"):
        check_artifact_revision_chain_contract(
            call_build_initial_revision=seam.build_next,
            call_build_next_revision=seam.build_next,
        )


def test_chain_contract_rejects_a_seam_that_skips_a_rev():
    # A seam that produces a legal single row each time, but jumps rev 1 -> rev 3 rather than
    # rev 1 -> rev 2: neither row violates ArtifactRevision's OWN validator on its own, so only
    # the chain-level arm — not the pydantic type — can catch the skip.
    with pytest.raises(ConformanceFailure, match="is rev=3"):
        check_artifact_revision_chain_contract(
            call_build_initial_revision=lambda: ArtifactRevision(
                rev=1, received_at="2026-10-06T00:00:00Z", provenance=_PROVENANCE,
                supersedes=None,
            ),
            call_build_next_revision=lambda: ArtifactRevision(
                rev=3, received_at="2026-10-06T00:00:00Z", provenance=_PROVENANCE, supersedes=2,
            ),
        )


# ── check_refresh_spec_pull_contract ────────────────────────────────────────────────────────

def _resolve(url_template: str, identity_value: str) -> str:
    """The reference resolver: substitutes the identity value into the template's placeholder."""
    start, end = url_template.index("{"), url_template.index("}")
    return url_template[:start] + identity_value + url_template[end + 1:]


def test_refresh_pull_contract_accepts_a_url_keyed_on_the_identity_value():
    check_refresh_spec_pull_contract(
        identity_value="evt-42",
        call_pull_url=lambda: _resolve("https://example/picture/{event_id}", "evt-42"),
    )


def test_refresh_pull_contract_rejects_a_url_that_ignores_the_identity_value():
    with pytest.raises(ConformanceFailure, match="does not contain the identity value"):
        check_refresh_spec_pull_contract(
            identity_value="evt-42",
            call_pull_url=lambda: "https://example/picture/latest",
        )


def test_refresh_pull_contract_rejects_a_blank_identity_value_fixture():
    with pytest.raises(ConformanceFailure, match="identity_value=''"):
        check_refresh_spec_pull_contract(
            identity_value="",
            call_pull_url=lambda: "https://example/picture/latest",
        )

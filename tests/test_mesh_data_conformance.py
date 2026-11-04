"""`check_mesh_data_entitlement_contract` and `check_mesh_data_size_gate_contract` must go red on
the implementations they exist to reject, the same discipline as
`test_mesh_artifacts_conformance.py` — `MeshData`'s own nearest precedent.

THE DEFECTS THESE ARMS EXIST TO CATCH: a `MeshData.resolve` that hands a materializing ticket to
an initiator not entitled to it — `outcome="answered"` where the Protocol requires a refusal
(`outcome="empty"`) — and a resolve over an oversized urn that answers or silently empties instead
of reporting the gate it crossed (`outcome="failed"` with a `detail`), which is the unreported-OOM
shape `MeshData`'s own docstring names as the incident this gate exists to replace.

Nothing here imports a driver; the store is a dict.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_mesh_data_entitlement_contract,
    check_mesh_data_size_gate_contract,
)
from iagent_mesh.interfaces import DataRef, Initiator
from iagent_mesh.results import MeshResult

ENTITLED = Initiator(subject="alice", kind="person")
UNENTITLED = Initiator(subject="mallory", kind="person")

URN = "urn:li:dataset:(urn:li:dataPlatform:s3,ev_fixture,PROD)"
NEVER_REGISTERED_URN = "urn:li:dataset:(urn:li:dataPlatform:s3,never_registered,PROD)"
OVERSIZED_URN = "urn:li:dataset:(urn:li:dataPlatform:s3,too_big,PROD)"


def _ref() -> DataRef:
    return DataRef(
        ticket="ticket-1",
        schema=(("program", "str"), ("BCWS", "float")),
        row_count_estimate=54,
        as_of="2026-11-03",
        provenance="seed",
    )


class _DataBroker:
    """The reference implementation: one urn, granted to `alice`. `resolve` refuses anyone else
    and refuses an unregistered urn alike — both come back `outcome="empty"`, the collapsed
    shape the Protocol's own docstring requires."""

    def __init__(self) -> None:
        self._grants = {URN: "alice"}

    def resolve(self, initiator: Initiator, urn: str, **_kw) -> MeshResult:
        owner = self._grants.get(urn)
        if owner is None:
            return MeshResult.empty()
        if initiator.subject != owner:
            return MeshResult.empty()
        return MeshResult.answered([_ref()])


def _run(store) -> None:
    check_mesh_data_entitlement_contract(
        call_resolve_as_entitled=lambda: store.resolve(ENTITLED, URN),
        call_resolve_as_unentitled=lambda: store.resolve(UNENTITLED, URN),
        call_resolve_absent_urn=lambda: store.resolve(ENTITLED, NEVER_REGISTERED_URN),
    )


def test_A_CONFORMING_MESH_DATA_BROKER_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run(_DataBroker())


def test_AN_ENTITLED_RESOLVE_THAT_COMES_BACK_EMPTY_IS_CAUGHT():
    """THE NO-OP-GATE DEFECT'S MIRROR: a broker whose `resolve` refuses EVERYONE, entitled or
    not — the one case meant to pass does not, so entitlement was never actually proven to be a
    real gate."""

    class RefusesEveryone(_DataBroker):
        def resolve(self, initiator, urn, **_kw):
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"data\.resolve.*entitled to the fixture's own"):
        _run(RefusesEveryone())


def test_A_LEAKING_BROKER_THAT_ANSWERS_FOR_THE_UNENTITLED_INITIATOR_IS_CAUGHT():
    """THE DEFECT THIS ARM EXISTS TO CATCH: the entitlement check is a no-op — `resolve` hands out
    a ticket for an initiator this fixture built specifically to be refused."""

    class LeaksToAnyone(_DataBroker):
        def resolve(self, initiator, urn, **_kw):
            if urn not in self._grants:
                return MeshResult.empty()
            return MeshResult.answered([_ref()])  # never checks initiator.subject

    with pytest.raises(ConformanceFailure, match=r"data\.resolve.*NOT entitled.*materializing"):
        _run(LeaksToAnyone())


def test_AN_ABSENT_URN_THAT_ANSWERS_INSTEAD_OF_REFUSING_IS_CAUGHT():
    """Unrelated to entitlement: a urn the fixture never registered must still come back
    `outcome='empty'`, the ordinary absent case."""

    class AnswersForAbsent(_DataBroker):
        def resolve(self, initiator, urn, **_kw):
            if urn == NEVER_REGISTERED_URN:
                return MeshResult.answered([_ref()])
            return super().resolve(initiator, urn)

    with pytest.raises(ConformanceFailure, match=r"data\.resolve.*never registered.*not 'empty'"):
        _run(AnswersForAbsent())


# ── check_mesh_data_size_gate_contract, added 2026-11-03 (0.9.14 branch item) ────────────────


def _run_gate(store) -> None:
    check_mesh_data_size_gate_contract(
        call_resolve_oversized=lambda: store.resolve(ENTITLED, OVERSIZED_URN),
    )


class _GatedBroker(_DataBroker):
    """The reference implementation: `OVERSIZED_URN` always exceeds the (fictional) row ceiling,
    and `resolve` reports it as a named failure rather than answering or emptying."""

    def resolve(self, initiator, urn, **_kw):
        if urn == OVERSIZED_URN:
            return MeshResult.failed(detail="row estimate 4_200_000 exceeds MAX_ROWS=100_000")
        return super().resolve(initiator, urn)


def test_A_GATED_MESH_DATA_BROKER_PASSES():
    """POSITIVE CONTROL. Without this, the red below could be an arm that fails everything."""
    _run_gate(_GatedBroker())


def test_AN_OVERSIZED_RESOLVE_THAT_ANSWERS_INSTEAD_OF_FAILING_IS_CAUGHT():
    """THE UNREPORTED-OOM DEFECT: a broker that silently answers (or empties) an oversized
    resolve instead of reporting the gate it crossed — the same shape as the pod `MeshData`'s own
    docstring cites, discovered from the pod's death rather than from the result."""

    class IgnoresTheGate(_GatedBroker):
        def resolve(self, initiator, urn, **_kw):
            if urn == OVERSIZED_URN:
                return MeshResult.answered([_ref()])
            return super().resolve(initiator, urn)

    with pytest.raises(ConformanceFailure, match=r"data\.resolve.*exceed its own size gate"):
        _run_gate(IgnoresTheGate())


def test_AN_OVERSIZED_RESOLVE_THAT_FAILS_WITH_NO_DETAIL_IS_CAUGHT():
    """`outcome='failed'` alone is not enough — a failure with no `detail` naming the gate is
    'something went wrong', the same unreported shape one level down."""

    class FailsSilently(_GatedBroker):
        def resolve(self, initiator, urn, **_kw):
            if urn == OVERSIZED_URN:
                return MeshResult.failed(detail="unspecified error")
            return super().resolve(initiator, urn)

    # A non-empty detail that names nothing still passes this arm — it only requires a detail be
    # present, the same "shape, not the policy decision" split entitlement draws. This case
    # instead proves the ABSENCE of a detail is caught.
    class FailsWithNoDetail(_GatedBroker):
        def resolve(self, initiator, urn, **_kw):
            if urn == OVERSIZED_URN:
                result = MeshResult.failed(detail="x")
                return result.model_copy(update={"detail": None})
            return super().resolve(initiator, urn)

    _run_gate(FailsSilently())  # has a detail, even if uninformative — passes

    with pytest.raises(ConformanceFailure, match=r"data\.resolve.*no detail naming the gate"):
        _run_gate(FailsWithNoDetail())

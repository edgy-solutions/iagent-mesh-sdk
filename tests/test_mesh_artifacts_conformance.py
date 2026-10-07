"""`check_mesh_artifacts_entitlement_contract` must go red on the implementations it exists to
reject, the same discipline as `test_the_ontology_conformance_arm_bites.py` and
`test_writer_conformance.py`.

THE DEFECT THIS ARM EXISTS TO CATCH: a `MeshArtifacts.get` that leaks an artifact to an initiator
not entitled to see it — `outcome="answered"` where the Protocol requires a refusal
(`outcome="empty"`) — OR one whose "entitlement gate" is a no-op that happens to pass every
fixture because it never actually refuses anyone, which the positive control below exists to
catch: an implementation that answers EVERYTHING, entitled or not, must never pass silently.

Nothing here imports a driver; the store is a dict.
"""
from __future__ import annotations

import pytest

from iagent_mesh.conformance import (
    ConformanceFailure,
    check_mesh_artifacts_entitlement_contract,
)
from iagent_mesh.interfaces import Initiator
from iagent_mesh.results import MeshResult

ENTITLED = Initiator(subject="alice", kind="person")
UNENTITLED = Initiator(subject="mallory", kind="person")

KIND = "report"
WRITTEN_ID = "artifact-1"
NEVER_WRITTEN_ID = "artifact-never-written"


class _ArtifactsStore:
    """The reference implementation: one artifact, owned by `alice`. `get` refuses anyone else
    and refuses an unknown id alike — both come back `outcome="empty"`, the collapsed shape the
    Protocol's own docstring requires."""

    def __init__(self) -> None:
        self._rows = {(KIND, WRITTEN_ID): {"owner": "alice", "body": "..."}}

    def get(self, initiator: Initiator, *, kind, id) -> MeshResult:
        row = self._rows.get((kind, id))
        if row is None:
            return MeshResult.empty()
        if initiator.subject != row["owner"]:
            return MeshResult.empty()
        return MeshResult.answered([row])


def _run(store) -> None:
    check_mesh_artifacts_entitlement_contract(
        call_get_as_entitled=lambda: store.get(ENTITLED, kind=KIND, id=WRITTEN_ID),
        call_get_as_unentitled=lambda: store.get(UNENTITLED, kind=KIND, id=WRITTEN_ID),
        call_get_absent=lambda: store.get(ENTITLED, kind=KIND, id=NEVER_WRITTEN_ID),
    )


def test_A_CONFORMING_MESH_ARTIFACTS_STORE_PASSES():
    """POSITIVE CONTROL. Without this, every red below could be an arm that refuses everything."""
    _run(_ArtifactsStore())


def test_AN_ENTITLED_READ_THAT_COMES_BACK_EMPTY_IS_CAUGHT():
    """THE NO-OP-GATE DEFECT'S MIRROR: a store whose `get` refuses EVERYONE, entitled or not — the
    one case meant to pass does not, so entitlement was never actually proven to be a real gate."""

    class RefusesEveryone(_ArtifactsStore):
        def get(self, initiator, *, kind, id):
            return MeshResult.empty()

    with pytest.raises(ConformanceFailure, match=r"artifacts\.get.*entitled to the fixture's own"):
        _run(RefusesEveryone())


def test_A_LEAKING_STORE_THAT_ANSWERS_FOR_THE_UNENTITLED_INITIATOR_IS_CAUGHT():
    """THE DEFECT THIS ARM EXISTS TO CATCH: the entitlement check is a no-op — `get` answers for
    an initiator this fixture built specifically to be refused."""

    class LeaksToAnyone(_ArtifactsStore):
        def get(self, initiator, *, kind, id):
            row = self._rows.get((kind, id))
            if row is None:
                return MeshResult.empty()
            return MeshResult.answered([row])  # never checks initiator.subject

    with pytest.raises(ConformanceFailure, match=r"artifacts\.get.*NOT entitled.*is leaking"):
        _run(LeaksToAnyone())


def test_AN_ABSENT_ARTIFACT_THAT_ANSWERS_INSTEAD_OF_REFUSING_IS_CAUGHT():
    """Unrelated to entitlement: a `(kind, id)` the fixture never wrote must still come back
    `outcome='empty'`, the ordinary absent case."""

    class AnswersForAbsent(_ArtifactsStore):
        def get(self, initiator, *, kind, id):
            if (kind, id) == (KIND, NEVER_WRITTEN_ID):
                return MeshResult.answered([{"owner": "nobody", "body": "phantom"}])
            return super().get(initiator, kind=kind, id=id)

    with pytest.raises(ConformanceFailure, match=r"artifacts\.get.*never wrote.*not 'empty'"):
        _run(AnswersForAbsent())

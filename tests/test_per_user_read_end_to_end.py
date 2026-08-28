"""THE ACCEPTANCE TEST: two users invoking one agent read as themselves, not as the service.

Everything else in this repo tests a piece. This drives the whole per-user read path the way a
data scientist will actually write it — a `MeshTool` handler that builds a data client and reads
an asset — and asserts on the SUBJECT THE BROKER WOULD AUTHORIZE, which is the thing that
decides which rows come back.

The stand-in `_FakeCortexDataClient` mirrors dag-tools' real constructor and its
`X-Originator-Email` behaviour; that the real one still has that shape is pinned separately in
`test_cortex_data_client_contract.py` against dag-tools' source. Splitting it this way keeps
this test free of polars/pyiceberg while leaving no room to imagine the signature.

WHY A FAKE IS HONEST HERE. The real client's next hop is an HTTP POST to a broker that mints
credentials — unavailable in unit tests, and mocking it would only re-assert my own mock. The
question this file answers is narrower and is the one that was actually broken: DOES THE RIGHT
SUBJECT ARRIVE AT THE CONSTRUCTOR? Everything downstream of that already worked.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from iagent_mesh import CallerIdentity
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput

_SECRET = "test-signing-secret"


def _token(claims: dict) -> str:
    import jwt
    return jwt.encode(claims, _SECRET, algorithm="HS256")


class _FakeCortexDataClient:
    """Mirrors `dag_tools.cortex_data.client.CortexDataClient`'s identity handling.

    Reproduced faithfully, INCLUDING THE DANGEROUS PART: `originator_email=None` is not an
    error. The client omits the header, and the gateway then keys the Topaz `can_read` decision
    on the M2M token's own subject — i.e. the read silently succeeds AS THE SERVICE. That is the
    confused deputy this whole arc exists to prevent, so the fake must be able to express it or
    the test cannot detect it.
    """

    last: "dict" = {}

    def __init__(self, broker_url="http://broker.test", jwt_token="svc-token",
                 originator_email=None, originator_sub=None):
        self.originator_email = originator_email
        self.jwt_token = jwt_token

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.jwt_token}"}
        if self.originator_email:
            h["X-Originator-Email"] = self.originator_email
        return h

    def get_dataframe(self, urn: str):
        headers = self._headers()
        # The gateway's rule, reproduced: header subject wins; otherwise the token's own.
        subject = headers.get("X-Originator-Email") or "svc:the-service"
        type(self).last = {"urn": urn, "authorized_as": subject, "headers": headers}
        return f"rows-for:{subject}"


class Ask(ToolInput):
    asset: str


class Rows(ToolOutput):
    authorized_as: str
    data: str


@pytest.fixture(autouse=True)
def _verifying(monkeypatch):
    monkeypatch.setenv("MESH_JWT_PUBLIC_KEY", _SECRET)
    monkeypatch.delenv("REQUIRE_TRANSPORT_AUTH", raising=False)
    monkeypatch.delenv("USER_ENTITLEMENT_CLAIM", raising=False)
    _FakeCortexDataClient.last = {}


def _agent(name="reliability-agent"):
    """The tool exactly as the quickstart tells a data scientist to write it."""
    tool = MeshTool(
        name=name,
        description="Reads an asset on behalf of the caller.",
        verb="mesh:readAsset",
        input_uri="mesh:CatalogAssetQuery",
        output_uri="mesh:DatasetAnalysisReport",
    )

    @tool.execute()
    def read_asset(data: Ask, caller: CallerIdentity) -> Rows:
        # THE ONE LINE THIS ARC EXISTED TO MAKE WRITABLE.
        client = _FakeCortexDataClient(originator_email=caller.require_authz_id())
        rows = client.get_dataframe(data.asset)
        return Rows(authorized_as=_FakeCortexDataClient.last["authorized_as"], data=rows)

    return TestClient(tool.app)


URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,sales_customers,PROD)"


def test_two_users_read_as_THEMSELVES_not_as_the_service():
    """Acceptance: *two different users invoking the same agent get different rows.*"""
    client = _agent()
    got = {}
    for who in ("alice@corp.com", "bob@corp.com"):
        r = client.post("/execute", json={"asset": URN},
                        headers={"Authorization": f"Bearer {_token({'email': who})}"})
        assert r.status_code == 200, r.text
        got[who] = r.json()

    assert got["alice@corp.com"]["authorized_as"] == "alice@corp.com"
    assert got["bob@corp.com"]["authorized_as"] == "bob@corp.com"
    assert got["alice@corp.com"]["data"] != got["bob@corp.com"]["data"], (
        "both users got identical rows — the read is not per-user"
    )
    # The negative that matters: neither read fell back to the service.
    assert "svc:the-service" not in str(got)


def test_employee_id_deployment_authorizes_on_the_employee_id(monkeypatch):
    """Work-deploy: the subject is an employee id in `preferred_username`, carried opaque."""
    monkeypatch.setenv("USER_ENTITLEMENT_CLAIM", "preferred_username")
    client = _agent(name="empid-agent")

    r = client.post("/execute", json={"asset": URN}, headers={
        "Authorization": f"Bearer {_token({'preferred_username': 'E123456',
                                           'email': 'ignored@corp.com'})}"})
    assert r.status_code == 200, r.text
    assert r.json()["authorized_as"] == "E123456"
    # Nothing on the path treated the subject as an email address.
    assert _FakeCortexDataClient.last["headers"]["X-Originator-Email"] == "E123456"


def test_an_unauthenticated_caller_does_NOT_read_as_the_service():
    """The confused deputy, refused loudly.

    Under OBSERVE the request is admitted at the transport layer by design, so this is the
    ordinary shape of an un-migrated caller — and the pre-fix code would have read as the
    service here and returned rows with no error at all.
    """
    client = _agent(name="anon-agent")
    r = client.post("/execute", json={"asset": URN})   # no token

    assert r.status_code == 500, "an unresolved caller must not produce a successful read"
    assert _FakeCortexDataClient.last == {}, (
        "a data read was ATTEMPTED for an unresolved caller — it would have authorized as the "
        "service identity"
    )


def test_the_fake_can_express_the_defect_it_is_asked_to_detect():
    """POSITIVE CONTROL for the harness itself.

    If `originator_email=None` did not silently authorize as the service in this fake, the test
    above would pass for the wrong reason and this file would prove nothing.
    """
    c = _FakeCortexDataClient(originator_email=None)
    assert c.get_dataframe(URN) == "rows-for:svc:the-service"
    assert "X-Originator-Email" not in _FakeCortexDataClient.last["headers"]

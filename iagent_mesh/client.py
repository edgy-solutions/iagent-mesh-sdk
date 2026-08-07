import logging
import os

import httpx

logger = logging.getLogger("iagent_mesh.client")


def _mint_service_token(timeout: float = 15.0) -> str:
    """Mint a FRESH service token via Keycloak client-credentials.

    ONE MINT IMPLEMENTATION, NOT TWO. This defers to the platform's
    `agent_fleet.utils.service_identity.mint_service_token` whenever it is importable —
    the same code path the extraction→review sensor and the supervisor use. Two minting
    implementations is two places for the claim contract to drift, and the mint contract's
    entire value is that there is ONE shape to verify. The inline fallback below exists
    only for engines packaged without the platform on the path, and is deliberately a
    transcription of the same request, not a variant of it.

    MINT AT USE, never a stored token: there is no JWT to go stale and no lifetime knob to
    tune. A static credential replayed later is the time-machine defect this replaces.
    """
    try:  # platform implementation — preferred, single source
        from agent_fleet.utils.service_identity import mint_service_token  # type: ignore
        return mint_service_token(timeout=timeout)
    except ImportError:
        pass

    realm = os.environ["KEYCLOAK_REALM_URL"].rstrip("/")
    client_id = os.environ["MESH_CLIENT_ID"]
    client_secret = os.environ["MESH_CLIENT_SECRET"]
    resp = httpx.post(
        f"{realm}/protocol/openid-connect/token",
        data={"grant_type": "client_credentials",
              "client_id": client_id, "client_secret": client_secret},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"mint failed HTTP {resp.status_code} for client {client_id!r} at {realm}: "
            f"{resp.text[:200]}"
        )
    token = (resp.json() or {}).get("access_token")
    if not token:
        raise RuntimeError("token response carried no access_token")
    return token


class MeshClient:
    """Client for calling the mesh gateway under a SERVICE IDENTITY.

    WHAT CHANGED AND WHY (2026-08-07). This class used to read a single static
    `MESH_DEV_TOKEN` from the environment and raise without it, with the message *"Ensure
    you are running within the secured JupyterHub environment."* That sentence is the
    architecture's old trust model preserved in prose: a long-lived credential whose safety
    rests on WHERE THE PROCESS HAPPENS TO RUN — security assumed at a boundary the component
    does not control. Same shape as the DA read path deferring to a gateway it could not
    verify.

    Minting does not modernise the token; it REMOVES THE PERIMETER DEPENDENCY. Afterwards
    the SDK's outbound trust rests on an identity the platform declares and reconciles, and
    the caller is authenticated wherever it runs.

    `MESH_DEV_TOKEN` survives as a DEV fallback and ANNOUNCES ITSELF, so a static token in a
    real deployment reads as the anomaly it is instead of passing silently.
    """

    def __init__(self, gateway_url: str = "http://cortex-bff.local.svc:8000/orchestrate"):
        self.gateway_url = gateway_url
        self._static_token = os.getenv("MESH_DEV_TOKEN")

    def _authorization(self) -> str:
        if self._static_token:
            logger.warning("outbound identity: MESH_DEV_TOKEN (static, dev fallback) — "
                           "no service identity in use")
            return f"Bearer {self._static_token}"
        token = _mint_service_token()
        logger.info("outbound identity: %s (minted)",
                    os.getenv("MESH_CLIENT_ID", "service-identity"))
        return f"Bearer {token}"

    def ask(self, prompt: str) -> str:
        headers = {"Authorization": self._authorization(),
                   "Content-Type": "application/json"}
        with httpx.Client() as client:
            response = client.post(self.gateway_url, headers=headers,
                                   json={"prompt": prompt}, timeout=30.0)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return response.text

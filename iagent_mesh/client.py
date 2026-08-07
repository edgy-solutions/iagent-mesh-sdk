import logging
import os

import httpx

from .service_identity import ServiceTokenError, mint_mesh_token  # noqa: F401

logger = logging.getLogger("iagent_mesh.client")


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
        token = mint_mesh_token()
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

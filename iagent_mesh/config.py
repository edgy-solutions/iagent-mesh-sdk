"""SDK environment-driven configuration.

Centralizes the URLs and tokens the SDK needs at runtime so engine
deployments can wire them via ConfigMap / Secret without code changes.
"""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DataHub (predicate-graph registration inbox per ADR-0006).
    # Optional because the SDK is usable for local-dev without registering;
    # ``MESH_REGISTER_ON_STARTUP`` gates whether registration actually fires.
    DATAHUB_GMS_URL: Optional[str] = None
    DATAHUB_TOKEN: Optional[str] = None

    # Provisioning + git platform integration (used by scaffold_core /
    # mcp_server, not by MeshTool itself).
    GIT_PROVISION_API_URL: str
    GIT_SERVER_HOST: str
    ARTIFACTORY_BASE_URL: str
    PLATFORM_GIT_TOKEN: Optional[str] = None
    MESH_DEV_TOKEN: Optional[str] = None


settings = Settings()

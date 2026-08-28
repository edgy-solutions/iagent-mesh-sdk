"""SDK environment-driven configuration.

Centralizes the URLs and tokens the SDK needs at runtime so engine
deployments can wire them via ConfigMap / Secret without code changes.

NOTHING HERE IS REQUIRED AT IMPORT TIME, and that is a correctness property rather than a
convenience. `Settings` is instantiated at module scope and `core.py` imports it, so a REQUIRED
field made `import iagent_mesh.core` — the first line of the quickstart, and of every scaffolded
tool — raise `ValidationError` on any machine that had not already exported three variables:

    pydantic_core._pydantic_core.ValidationError: 3 validation errors for Settings
    GIT_PROVISION_API_URL / GIT_SERVER_HOST / ARTIFACTORY_BASE_URL: Field required

Those three are consumed ONLY by `scaffold_core` / `mcp_server` (repository provisioning). A data
scientist importing `MeshTool` to serve a tool, or to read data, needs none of them — yet could
not import the package at all without inventing values for a git-provisioning API they will never
call. The suite could not see this: `tests/conftest.py` sets all three before any import, so the
one environment guaranteed to have them was the one asserting the package worked.

The requirement is now enforced WHERE IT IS REAL — `require()` raises at the point of use, naming
the variable and what needs it — instead of at import, where it blocked every unrelated use.
"""

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DataHub (predicate-graph registration inbox per ADR-0006).
    # Optional because the SDK is usable for local-dev without registering;
    # ``MESH_REGISTER_ON_STARTUP`` gates whether registration actually fires.
    DATAHUB_GMS_URL: Optional[str] = None
    DATAHUB_TOKEN: Optional[str] = None

    # Provisioning + git platform integration. Used by scaffold_core / mcp_server, NEVER by
    # MeshTool — hence optional here and demanded by `require()` at the call site.
    GIT_PROVISION_API_URL: Optional[str] = None
    GIT_SERVER_HOST: Optional[str] = None
    ARTIFACTORY_BASE_URL: Optional[str] = None
    PLATFORM_GIT_TOKEN: Optional[str] = None
    MESH_DEV_TOKEN: Optional[str] = None

    def require(self, name: str) -> str:
        """Return a setting that the CALLER genuinely cannot proceed without, or fail naming it.

        Deferring the check from import to use does not weaken it: an unset value still stops the
        operation that needs it, and now says which operation that was. `MeshTool` never calls
        this, which is the point — the scaffolding paths keep their hard requirement while the
        serving path stops inheriting it.
        """
        value = getattr(self, name, None)
        if not value:
            raise RuntimeError(
                f"{name} is not set. It is required for repository provisioning / scaffolding "
                f"(scaffold_core, mcp_server). Serving a MeshTool does not need it — see "
                f".env.example."
            )
        return value


settings = Settings()

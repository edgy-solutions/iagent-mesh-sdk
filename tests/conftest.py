"""Test-suite environment bootstrap.

Sets dummy values for the env vars ``iagent_mesh.config.Settings`` reads
at import time, so tests can ``from iagent_mesh.config import settings``
without needing real platform credentials.

``DATAHUB_GMS_URL`` is left unset by default — registration is opt-in via
``MESH_REGISTER_ON_STARTUP`` per the SDK's API (ADR-0006) and most tests
exercise the SDK without DataHub. Individual tests that need it set it
explicitly via ``monkeypatch``.
"""

import os

# Required settings (no defaults).
os.environ.setdefault("GIT_PROVISION_API_URL", "https://mock-api/v1/git/provision")
os.environ.setdefault("GIT_SERVER_HOST", "mock-git-server")
os.environ.setdefault("ARTIFACTORY_BASE_URL", "https://mock-artifactory")

# Optional settings — left unset by default to mirror local-dev posture.
os.environ.setdefault("PLATFORM_GIT_TOKEN", "mock_token")
os.environ.setdefault("MESH_DEV_TOKEN", "mock_token")

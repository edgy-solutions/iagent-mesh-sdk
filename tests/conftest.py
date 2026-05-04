import os

# Set dummy environment variables so pydantic-settings can instantiate at import time
os.environ["DATAHUB_URL"] = "http://mock-datahub:8080"
os.environ["GIT_PROVISION_API_URL"] = "https://mock-api/v1/git/provision"
os.environ["GIT_SERVER_HOST"] = "mock-git-server"
os.environ["ARTIFACTORY_BASE_URL"] = "https://mock-artifactory"
os.environ["PLATFORM_GIT_TOKEN"] = "mock_token"
os.environ["MESH_DEV_TOKEN"] = "mock_token"

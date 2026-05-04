from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATAHUB_URL: str
    GIT_PROVISION_API_URL: str
    GIT_SERVER_HOST: str
    ARTIFACTORY_BASE_URL: str
    PLATFORM_GIT_TOKEN: Optional[str] = None
    MESH_DEV_TOKEN: Optional[str] = None

settings = Settings()

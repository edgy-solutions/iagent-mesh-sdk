from pydantic import BaseModel, Field
from typing import Optional

class ToolInput(BaseModel):
    """Base class for all Data Scientist inputs."""
    pass

class ToolOutput(BaseModel):
    """Base class for all Data Scientist outputs."""
    pass

class DataPointer(BaseModel):
    """The secure token and URI provided by Engine DA for unstructured/structured data."""
    source: str = Field(..., description="e.g., 'minio', 'snowflake'")
    uri: str = Field(..., description="The dynamic path to the data")
    temporary_access_token: str = Field(..., description="Secure, short-lived STS token")

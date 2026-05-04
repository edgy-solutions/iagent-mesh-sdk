import os
import uuid
import subprocess
from fastapi import FastAPI
from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool
from iagent_mesh.scaffold_core import generate_template_files
from iagent_mesh.config import settings

# 1. Define Schemas
class ScaffoldInput(ToolInput):
    template_id: str = Field(...)
    tool_name: str = Field(...)
    tool_urn: str = Field(...)

class ScaffoldOutput(ToolOutput):
    workspace_uuid: str
    target_path: str

class PublishInput(ToolInput):
    workspace_uuid: str = Field(...)
    tool_name: str = Field(...)
    tool_urn: str = Field(...)
    target_git_group: str = Field(...)

class PublishOutput(ToolOutput):
    status: str
    git_url: str

# 2. Initialize MeshTools
scaffold_tool = MeshTool(urn="urn:li:tool:scaffold_generator", description="Scaffolds a DevEx template")
publish_tool = MeshTool(urn="urn:li:tool:mesh_publisher", description="Publishes a DevEx workspace to Git")

# 3. Define Tool Logic
@scaffold_tool.execute()
def run_scaffold(data: ScaffoldInput) -> ScaffoldOutput:
    workspace_uuid = str(uuid.uuid4())
    target_path = f"/tmp/{workspace_uuid}"
    
    generate_template_files(data.template_id, data.tool_name, data.tool_urn, target_path)
    
    return ScaffoldOutput(workspace_uuid=workspace_uuid, target_path=target_path)

@publish_tool.execute()
def run_publish(data: PublishInput) -> PublishOutput:
    target_path = f"/tmp/{data.workspace_uuid}"
    if not os.path.exists(target_path):
        raise ValueError(f"Workspace not found at {target_path}")
        
    assert settings.PLATFORM_GIT_TOKEN is not None, "PLATFORM_GIT_TOKEN is required"
    git_url = f"https://oauth2:{settings.PLATFORM_GIT_TOKEN}@{settings.GIT_SERVER_HOST}/{data.target_git_group}/{data.tool_name}.git"
    
    # Initialize git, commit, and push
    subprocess.run(["git", "init"], cwd=target_path, check=True)
    subprocess.run(["git", "add", "."], cwd=target_path, check=True)
    subprocess.run(["git", "commit", "-m", f"Automated DevEx Scaffold for {data.tool_name}"], cwd=target_path, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=target_path, check=True)
    subprocess.run(["git", "remote", "add", "origin", git_url], cwd=target_path, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=target_path, check=True)
    
    return PublishOutput(status="Success", git_url=git_url)

# 4. Master App
app = FastAPI(title="DevEx Hub Cloud Tools")
app.mount("/scaffold", scaffold_tool.app)
app.mount("/publish", publish_tool.app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

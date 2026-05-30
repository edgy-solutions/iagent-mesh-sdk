import os
import uuid
import subprocess
from fastapi import FastAPI
from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool
from iagent_mesh.scaffold_core import generate_template_files, publish_workspace_to_git
from iagent_mesh.config import settings

# 1. Define Schemas
class ScaffoldInput(ToolInput):
    template_id: str = Field(...)
    tool_name: str = Field(...)
    is_mcp: bool = Field(False)

class ScaffoldOutput(ToolOutput):
    workspace_uuid: str
    target_path: str

class PublishInput(ToolInput):
    workspace_uuid: str = Field(...)
    tool_name: str = Field(...)
    is_mcp: bool = Field(False)
    target_git_group: str = Field(...)

class PublishOutput(ToolOutput):
    status: str
    git_url: str

# 2. Initialize MeshTools — these are platform tools (the DevEx Hub itself
# exists only because the mesh exists), so they use the ``mesh:`` namespace
# per ADR-0005. The predicate edges they create are:
#
#     (mesh:ScaffoldRequest) --[mesh:scaffoldWorkspace]--> (mesh:ScaffoldedWorkspace)
#     (mesh:PublishRequest)  --[mesh:publishWorkspace]-->  (mesh:GitDeployment)
scaffold_tool = MeshTool(
    name="scaffold_generator",
    description="Scaffolds a DevEx template into a fresh workspace directory.",
    verb="mesh:scaffoldWorkspace",
    input_uri="mesh:ScaffoldRequest",
    output_uri="mesh:ScaffoldedWorkspace",
    verb_synonyms=["scaffold", "generate workspace", "create from template"],
    owner_persona="DATA_STEWARD",
    cost_class="fast",
)
publish_tool = MeshTool(
    name="mesh_publisher",
    description="Publishes a scaffolded workspace to a managed git remote.",
    verb="mesh:publishWorkspace",
    input_uri="mesh:PublishRequest",
    output_uri="mesh:GitDeployment",
    verb_synonyms=["publish", "push to git", "deploy workspace"],
    owner_persona="DATA_STEWARD",
    cost_class="medium",
)

# 3. Define Tool Logic
@scaffold_tool.execute()
def run_scaffold(data: ScaffoldInput) -> ScaffoldOutput:
    workspace_uuid = str(uuid.uuid4())
    target_path = f"/tmp/{workspace_uuid}"
    
    # Enforce standardized URN based on type
    if data.is_mcp:
        tool_urn = f"urn:li:mcpServer:{data.tool_name}"
    else:
        tool_urn = f"urn:li:aitool:{data.tool_name}"
    
    generate_template_files(data.template_id, data.tool_name, tool_urn, target_path)
    
    return ScaffoldOutput(workspace_uuid=workspace_uuid, target_path=target_path)

@publish_tool.execute()
def run_publish(data: PublishInput) -> PublishOutput:
    target_path = f"/tmp/{data.workspace_uuid}"
    if not os.path.exists(target_path):
        raise ValueError(f"Workspace not found at {target_path}")
        
    assert settings.PLATFORM_GIT_TOKEN is not None, "PLATFORM_GIT_TOKEN is required"
    git_url = f"https://oauth2:{settings.PLATFORM_GIT_TOKEN}@{settings.GIT_SERVER_HOST}/{data.target_git_group}/{data.tool_name}.git"
    
    # Use centralized utility
    try:
        publish_workspace_to_git(target_path, git_url)
    except RuntimeError as e:
        raise ValueError(str(e))
    
    return PublishOutput(status="Success", git_url=git_url)

# 4. Master App
app = FastAPI(title="DevEx Hub Cloud Tools")
app.mount("/scaffold", scaffold_tool.app)
app.mount("/publish", publish_tool.app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

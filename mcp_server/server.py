import os
import subprocess
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from iagent_mesh.scaffold_core import generate_template_files, publish_workspace_to_git
from iagent_mesh.config import settings

mcp = FastMCP("iagent_mesh_devex")

@mcp.tool()
def scaffold_local_workspace(template_id: str, tool_name: str, tool_urn: str, target_directory: str) -> str:
    """
    Scaffolds a new agent tool workspace locally.
    
    Instruct the LLM in the target_directory description to infer the absolute path
    from the user's active IDE workspace, or ask if unknown.
    """
    try:
        generate_template_files(template_id, tool_name, tool_urn, target_directory)
        
        # Run local git init and git commit
        subprocess.run(["git", "init"], cwd=target_directory, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target_directory, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Initial commit for {tool_name}"], cwd=target_directory, check=True, capture_output=True)
        
        return f"Successfully scaffolded {tool_name} at {target_directory} and initialized git repository."
    except Exception as e:
        return f"Failed to scaffold: {str(e)}"

@mcp.tool()
def publish_local_to_mesh(local_directory: str, tool_urn: str, target_git_group: str) -> str:
    """
    Publishes a local agent workspace to the iagent Mesh platform.
    Provisions via API and pushes code.
    """
    try:
        assert settings.MESH_DEV_TOKEN is not None, "MESH_DEV_TOKEN is required"
        
        # Call provision API
        response = httpx.post(
            settings.GIT_PROVISION_API_URL,
            headers={"Authorization": f"Bearer {settings.MESH_DEV_TOKEN}"}
        )
        response.raise_for_status()
        # Assume provision API returns {"git_url": "..."}
        git_url = response.json().get("git_url", f"https://{settings.GIT_SERVER_HOST}/{target_git_group}/{os.path.basename(local_directory)}.git")
        
        try:
            publish_workspace_to_git(local_directory, git_url)
        except RuntimeError as e:
            return str(e)
        
        return f"Successfully published {tool_urn} from {local_directory} to {git_url}."
    except Exception as e:
        return f"Failed to publish: {str(e)}"

if __name__ == "__main__":
    mcp.run()

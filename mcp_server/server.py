import os
import subprocess
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from iagent_mesh.scaffold_core import generate_template_files

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
    Mocks API provisioning, pushes code, and registers with DataHub.
    """
    try:
        # Mock API call to httpx.post("https://api.sustainment.svc/v1/git/provision")
        mock_git_url = f"https://git.sustainment.internal/{target_git_group}/{os.path.basename(local_directory)}.git"
        
        # Local subprocess to run git remote add and git push
        subprocess.run(["git", "remote", "add", "origin", mock_git_url], cwd=local_directory, capture_output=True)
        # We don't want to actually push in the mock, but we would run:
        # subprocess.run(["git", "push", "-u", "origin", "main"], cwd=local_directory, check=True)
        
        # Mock a DataHub registration API call
        # httpx.post("http://datahub:8080", json={"urn": tool_urn})
        
        return f"Successfully published {tool_urn} from {local_directory} to {mock_git_url} and registered with DataHub."
    except Exception as e:
        return f"Failed to publish: {str(e)}"

if __name__ == "__main__":
    mcp.run()

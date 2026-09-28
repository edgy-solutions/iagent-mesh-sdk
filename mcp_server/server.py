import os
import subprocess
import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from iagent_mesh.scaffold_core import generate_template_files, publish_workspace_to_git
from iagent_mesh.config import settings
from mcp_server.mesh_explain import mesh_explain as _mesh_explain

mcp = FastMCP("iagent_mesh_devex")

@mcp.tool()
def scaffold_local_workspace(template_id: str, tool_name: str, target_directory: str, is_mcp: bool = False) -> str:
    """
    Scaffolds a new agent tool workspace locally.
    
    Instruct the LLM in the target_directory description to infer the absolute path
    from the user's active IDE workspace, or ask if unknown.
    """
    try:
        # Enforce standardized URN based on type
        if is_mcp:
            tool_urn = f"urn:li:mcpServer:{tool_name}"
        else:
            tool_urn = f"urn:li:aitool:{tool_name}"

        generate_template_files(template_id, tool_name, tool_urn, target_directory)
        
        # Run local git init and git commit
        subprocess.run(["git", "init"], cwd=target_directory, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=target_directory, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Initial commit for {tool_name}"], cwd=target_directory, check=True, capture_output=True)
        
        return f"Successfully scaffolded {tool_name} at {target_directory} and initialized git repository."
    except Exception as e:
        return f"Failed to scaffold: {str(e)}"

@mcp.tool()
def publish_local_to_mesh(local_directory: str, tool_name: str, target_git_group: str) -> str:
    """
    Publishes a local agent workspace to the iagent Mesh platform.
    Provisions via API and pushes code.
    """
    try:
        assert settings.MESH_DEV_TOKEN is not None, "MESH_DEV_TOKEN is required"
        
        # Required AT USE, not at package import — publishing genuinely needs these; importing
        # the SDK to serve a tool never did. `require` names the missing variable instead of
        # POSTing to the string "None" or building a `https://None/...` remote.
        provision_api = settings.require("GIT_PROVISION_API_URL")
        git_host = settings.require("GIT_SERVER_HOST")

        # Call provision API
        response = httpx.post(
            provision_api,
            headers={"Authorization": f"Bearer {settings.MESH_DEV_TOKEN}"}
        )
        response.raise_for_status()
        # Assume provision API returns {"git_url": "..."}
        git_url = response.json().get("git_url", f"https://{git_host}/{target_git_group}/{os.path.basename(local_directory)}.git")
        
        try:
            publish_workspace_to_git(local_directory, git_url)
        except RuntimeError as e:
            return str(e)
        
        return f"Successfully published {tool_name} from {local_directory} to {git_url}."
    except Exception as e:
        return f"Failed to publish: {str(e)}"

@mcp.tool()
def mesh_explain(subject: str) -> dict:
    """
    Explains a subject via engine-docs' reviewed corpus (POST /explain).

    Connects as a delegate Initiator (Initiator.kind == "delegate"), acting on behalf of
    whoever MESH_EXPLAIN_ON_BEHALF_OF names — never a person, and never a silent service: the
    same identity is refused by Initiator.require_person with DelegateIdentityRefused, the way
    any other non-person identity is.

    Requires ENGINE_DOCS_URL and MESH_EXPLAIN_ON_BEHALF_OF to be set; raises naming whichever is
    missing rather than guessing a target or an accountable party.

    Always returns the outcome, never a bare failure string: "answered" (rows = the pages,
    whole), "empty" (nothing explains this subject yet — the corpus's normal state), "failed"
    (the request or the corpus rejected it; detail says why), or "unreachable" (engine-docs
    could not be reached at all).
    """
    result = _mesh_explain(subject)
    return result.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()

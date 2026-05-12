import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from mcp_server.server import scaffold_local_workspace, publish_local_to_mesh


@patch("mcp_server.server.subprocess.run")
def test_scaffold_local_workspace_happy_path(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0)

    dest = tmp_path / "ws"
    result = scaffold_local_workspace(
        template_id="01_pure_math",
        tool_name="local-tool",
        target_directory=str(dest),
        is_mcp=False,
    )

    assert "Successfully scaffolded local-tool" in result
    assert str(dest) in result
    # Generated files present
    assert (dest / "app.py").exists()
    # Tool URN got injected into pyproject and app.py
    assert "local-tool" in (dest / "app.py").read_text(encoding="utf-8")
    # Local git init + add + commit (3 calls)
    assert mock_run.call_count == 3
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert cmds[0] == ["git", "init"]
    assert cmds[1] == ["git", "add", "."]
    assert cmds[2][:3] == ["git", "commit", "-m"]


@patch("mcp_server.server.subprocess.run")
@patch("mcp_server.server.generate_template_files")
def test_scaffold_local_workspace_mcp_urn(mock_generate, mock_run, tmp_path):
    """is_mcp=True should pass the urn:li:mcpServer:<name> URN to the generator."""
    mock_run.return_value = MagicMock(returncode=0)
    dest = tmp_path / "ws"
    dest.mkdir()

    result = scaffold_local_workspace(
        template_id="01_pure_math",
        tool_name="my-mcp",
        target_directory=str(dest),
        is_mcp=True,
    )

    assert "Successfully scaffolded my-mcp" in result
    mock_generate.assert_called_once_with("01_pure_math", "my-mcp", "urn:li:mcpServer:my-mcp", str(dest))


@patch("mcp_server.server.subprocess.run")
@patch("mcp_server.server.generate_template_files")
def test_scaffold_local_workspace_aitool_urn(mock_generate, mock_run, tmp_path):
    """is_mcp=False should pass the urn:li:aitool:<name> URN to the generator."""
    mock_run.return_value = MagicMock(returncode=0)
    dest = tmp_path / "ws"
    dest.mkdir()

    scaffold_local_workspace(
        template_id="01_pure_math",
        tool_name="my-tool",
        target_directory=str(dest),
        is_mcp=False,
    )

    mock_generate.assert_called_once_with("01_pure_math", "my-tool", "urn:li:aitool:my-tool", str(dest))


def test_scaffold_local_workspace_error_returns_string(tmp_path):
    """Errors are caught and converted to a 'Failed to scaffold' string (MCP convention)."""
    result = scaffold_local_workspace(
        template_id="completely_made_up_template",
        tool_name="x",
        target_directory=str(tmp_path),
        is_mcp=False,
    )
    assert result.startswith("Failed to scaffold")


@patch("mcp_server.server.publish_workspace_to_git")
@patch("mcp_server.server.httpx.post")
def test_publish_local_to_mesh_happy_path(mock_post, mock_publish, tmp_path):
    mock_post.return_value = MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"git_url": "https://git.example/group/x.git"}),
    )

    result = publish_local_to_mesh(
        local_directory=str(tmp_path),
        tool_name="my-tool",
        target_git_group="my-group",
    )

    assert "Successfully published my-tool" in result
    assert "https://git.example/group/x.git" in result
    mock_publish.assert_called_once_with(str(tmp_path), "https://git.example/group/x.git")
    # Auth header on provision API call
    call_headers = mock_post.call_args.kwargs["headers"]
    assert call_headers["Authorization"] == "Bearer mock_token"


@patch("mcp_server.server.publish_workspace_to_git")
@patch("mcp_server.server.httpx.post")
def test_publish_local_to_mesh_falls_back_to_constructed_git_url(mock_post, mock_publish, tmp_path):
    """When provision API returns no git_url, server constructs one from settings."""
    mock_post.return_value = MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={}),  # no git_url in response
    )

    result = publish_local_to_mesh(
        local_directory=str(tmp_path),
        tool_name="my-tool",
        target_git_group="my-group",
    )

    # Falls back to mock-git-server (from conftest) and uses dir basename
    expected_basename = os.path.basename(str(tmp_path))
    assert f"https://mock-git-server/my-group/{expected_basename}.git" in result
    mock_publish.assert_called_once()


@patch("mcp_server.server.publish_workspace_to_git")
@patch("mcp_server.server.httpx.post")
def test_publish_local_to_mesh_propagates_git_failure(mock_post, mock_publish, tmp_path):
    mock_post.return_value = MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"git_url": "https://git.example/r.git"}),
    )
    mock_publish.side_effect = RuntimeError("Git publishing failed: forbidden")

    result = publish_local_to_mesh(
        local_directory=str(tmp_path),
        tool_name="x",
        target_git_group="g",
    )
    assert "Git publishing failed" in result


@patch("mcp_server.server.httpx.post")
def test_publish_local_to_mesh_provision_api_failure(mock_post, tmp_path):
    """Errors from the provision API are caught and returned as a Failed-to-publish string."""
    mock_post.return_value = MagicMock(
        raise_for_status=MagicMock(side_effect=RuntimeError("502 bad gateway"))
    )

    result = publish_local_to_mesh(
        local_directory=str(tmp_path),
        tool_name="x",
        target_git_group="g",
    )
    assert result.startswith("Failed to publish")
    assert "502" in result

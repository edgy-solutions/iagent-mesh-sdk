import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from iagent_mesh.scaffold_core import generate_template_files, publish_workspace_to_git


def test_scaffold_generation(tmp_path):
    dest_dir = str(tmp_path)

    generate_template_files('01_pure_math', 'test-tool', 'urn:test', dest_dir)

    # 1. Test File Existence
    app_py = tmp_path / "app.py"
    pyproject_toml = tmp_path / "pyproject.toml"
    assemble_script = tmp_path / ".s2i" / "bin" / "assemble"

    assert app_py.exists()
    assert pyproject_toml.exists()
    assert assemble_script.exists()

    # 2. Test Variable Injection
    app_content = app_py.read_text(encoding="utf-8")
    assert "test-tool" in app_content
    assert "REPLACE_ME_NAME" not in app_content
    assert "REPLACE_ME_URN" not in app_content

    toml_content = pyproject_toml.read_text(encoding="utf-8")
    assert "test-tool" in toml_content
    assert "REPLACE_ME_NAME" not in toml_content

    # 3. Test Template Exclusion
    template_yaml = tmp_path / "template.yaml"
    assert not template_yaml.exists()


def test_scaffold_creates_jenkinsfile_with_artifactory(tmp_path):
    generate_template_files('01_pure_math', 'sample-tool', 'urn:li:aitool:sample-tool', str(tmp_path))

    jenkinsfile = tmp_path / "Jenkinsfile"
    assert jenkinsfile.exists()

    content = jenkinsfile.read_text(encoding="utf-8")
    # Tool name interpolated
    assert "sample-tool" in content
    # Settings interpolated (conftest sets ARTIFACTORY_BASE_URL=https://mock-artifactory)
    assert "https://mock-artifactory" in content
    # Pipeline structure
    assert "pipeline" in content
    assert "Bootstrap Runner" in content
    assert "Security Scan" in content
    assert "Build & Push" in content


def test_scaffold_assemble_script_content(tmp_path):
    generate_template_files('01_pure_math', 't', 'urn:t', str(tmp_path))
    assemble = tmp_path / ".s2i" / "bin" / "assemble"
    body = assemble.read_text(encoding="utf-8")
    assert body.startswith("#!/bin/bash")
    assert "pip install uv" in body
    assert "uv pip install --system -r pyproject.toml" in body


def test_scaffold_unknown_template_raises(tmp_path):
    with pytest.raises(ValueError, match="Template .* not found"):
        generate_template_files("nonexistent_template_xyz", "x", "urn:x", str(tmp_path))


@pytest.mark.parametrize("template_id", [
    "01_pure_math",
    "02_instructor_polars",
    "03_baml_pandas",
    "legacy_adapter",
    "smolagents_subswarm",
])
def test_scaffold_all_templates_produce_app_py(template_id, tmp_path):
    """All five catalog templates must produce a runnable app.py after scaffolding."""
    dest = tmp_path / template_id
    generate_template_files(template_id, f"tool-{template_id}", f"urn:li:aitool:tool-{template_id}", str(dest))
    assert (dest / "app.py").exists()
    assert (dest / "pyproject.toml").exists()
    assert not (dest / "template.yaml").exists()


@patch("iagent_mesh.scaffold_core.subprocess.run")
def test_publish_workspace_to_git_happy_path(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0)

    publish_workspace_to_git(str(tmp_path), "https://example.com/group/repo.git")

    # init, add, commit, branch, remote add, push  =>  6 subprocess calls
    assert mock_run.call_count == 6
    call_cmds = [c.args[0] for c in mock_run.call_args_list]
    assert call_cmds[0] == ["git", "init"]
    assert call_cmds[1] == ["git", "add", "."]
    assert call_cmds[2] == ["git", "commit", "-m", "Automated DevEx Scaffold"]
    assert call_cmds[3] == ["git", "branch", "-M", "main"]
    assert call_cmds[4] == ["git", "remote", "add", "origin", "https://example.com/group/repo.git"]
    assert call_cmds[5] == ["git", "push", "-u", "origin", "main"]
    # All should be invoked with cwd=tmp_path
    for c in mock_run.call_args_list:
        assert c.kwargs["cwd"] == str(tmp_path)
        assert c.kwargs["check"] is True


@patch("iagent_mesh.scaffold_core.subprocess.run")
def test_publish_workspace_to_git_failure_propagates(mock_run, tmp_path):
    err = subprocess.CalledProcessError(returncode=1, cmd=["git", "push"])
    err.stderr = b"remote rejected: forbidden"
    mock_run.side_effect = [
        MagicMock(returncode=0),  # init
        MagicMock(returncode=0),  # add
        MagicMock(returncode=0),  # commit
        MagicMock(returncode=0),  # branch
        MagicMock(returncode=0),  # remote add
        err,                      # push fails
    ]

    with pytest.raises(RuntimeError, match="Git publishing failed.*forbidden"):
        publish_workspace_to_git(str(tmp_path), "https://example.com/group/repo.git")

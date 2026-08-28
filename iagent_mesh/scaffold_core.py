import os
import shutil
import subprocess
from pathlib import Path
from iagent_mesh.config import settings

def generate_template_files(template_id: str, tool_name: str, tool_urn: str, dest_dir: str) -> None:
    """Scaffold a new tool from a template."""
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    # 1. Read requested template
    # Find the template directory. It could be prefixed with a number, e.g., 01_pure_math
    base_dir = Path(__file__).parent.parent / "templates"
    template_dir = None
    for d in base_dir.iterdir():
        if d.is_dir() and d.name.endswith(template_id):
            template_dir = d
            break
            
    if not template_dir:
        raise ValueError(f"Template {template_id} not found in {base_dir}")
        
    # 2. Copy all files except template.yaml
    for item in template_dir.rglob("*"):
        if item.is_file() and item.name != "template.yaml":
            rel_path = item.relative_to(template_dir)
            target = dest_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            
    # 3. String replacements
    for target_file in ["pyproject.toml", "app.py"]:
        file_path = dest_path / target_file
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            content = content.replace("REPLACE_ME_NAME", tool_name)
            content = content.replace("REPLACE_ME_URN", tool_urn)
            file_path.write_text(content, encoding="utf-8")

    # 4. IDENTITY STANZAS - see iagent_mesh/identity_stanzas.py for the why. Makes the
    # marginal cost of a new tool's service identity two reviewed YAML blocks instead of
    # an undocumented Keycloak errand.
    from iagent_mesh.identity_stanzas import render_identity_yaml
    (dest_path / "IDENTITY.yaml").write_text(render_identity_yaml(tool_name), encoding="utf-8")
            
    # 4. Generate .s2i/bin/assemble
    s2i_bin = dest_path / ".s2i" / "bin"
    s2i_bin.mkdir(parents=True, exist_ok=True)
    assemble_script = s2i_bin / "assemble"
    assemble_content = """#!/bin/bash
set -e
echo "---> Installing dependencies using uv..."
pip install uv
uv pip install --system -r pyproject.toml
# Or standard installation: uv pip install --system .
"""
    assemble_script.write_text(assemble_content, encoding="utf-8")
    os.chmod(assemble_script, 0o755)
    
    # 5. Generate Jenkinsfile
    #
    # Demanded HERE rather than at package import: scaffolding genuinely cannot proceed without
    # the Artifactory base, but serving a MeshTool never needed it (see config.Settings). An
    # f-string over an unset Optional would emit `curl -LO None/binaries-local/...` into a
    # committed Jenkinsfile — a build that fails much later, in someone else's CI, with the
    # cause four steps upstream. Fail at the write instead, naming the variable.
    artifactory = settings.require("ARTIFACTORY_BASE_URL")

    jenkinsfile = dest_path / "Jenkinsfile"
    jenkins_content = f"""pipeline {{
    agent any
    stages {{
        stage('Bootstrap Runner') {{
            steps {{
                echo 'Downloading S2I, UV, and Bandit from Artifactory...'
                sh '''
                    curl -LO {artifactory}/binaries-local/s2i/s2i-linux-amd64.tar.gz
                    tar -xzf s2i-linux-amd64.tar.gz
                    chmod +x s2i
                    export PATH=$PATH:$(pwd)
                    
                    # Assuming uv and bandit are also available as binaries
                    curl -LO {artifactory}/binaries-local/uv/uv-linux-amd64.tar.gz
                    tar -xzf uv-linux-amd64.tar.gz
                    chmod +x uv
                    
                    curl -LO {artifactory}/binaries-local/bandit/bandit-linux.tar.gz
                    tar -xzf bandit-linux.tar.gz
                    chmod +x bandit
                '''
            }}
        }}
        stage('Security Scan') {{
            steps {{
                echo 'Running Bandit Security Scan...'
                sh './bandit -r .'
            }}
        }}
        stage('Build & Push') {{
            steps {{
                echo 'Building {tool_name} with S2I...'
                sh './s2i build . python-39-centos7 {artifactory}/docker-local/{tool_name}:latest'
                echo 'Pushing {tool_name} to Artifactory...'
                sh 'docker push {artifactory}/docker-local/{tool_name}:latest'
            }}
        }}
    }}
}}"""
    jenkinsfile.write_text(jenkins_content, encoding="utf-8")
    print(f"Scaffolded {tool_name} from {template_id} to {dest_dir}")

def publish_workspace_to_git(workspace_dir: str, git_url: str) -> None:
    """Centralized utility to initialize, commit, and push a workspace to a git remote."""
    try:
        # We use check=True and capture_output=True so we can retrieve stderr on failure
        subprocess.run(["git", "init"], cwd=workspace_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=workspace_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Automated DevEx Scaffold"], cwd=workspace_dir, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=workspace_dir, check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", git_url], cwd=workspace_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=workspace_dir, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise RuntimeError(f"Git publishing failed: {error_msg}")

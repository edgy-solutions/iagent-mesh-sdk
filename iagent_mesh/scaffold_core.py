import os
import shutil
from pathlib import Path

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
    jenkinsfile = dest_path / "Jenkinsfile"
    jenkins_content = f"""pipeline {{
    agent any
    stages {{
        stage('Build') {{
            steps {{
                echo 'Building {tool_name} with S2I...'
                // Placeholder for standard S2I build steps
                sh 's2i build . python-39-centos7 {tool_name}:latest'
            }}
        }}
    }}
}}"""
    jenkinsfile.write_text(jenkins_content, encoding="utf-8")
    
    print(f"Scaffolded {tool_name} from {template_id} to {dest_dir}")

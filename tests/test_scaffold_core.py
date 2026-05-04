import os
from pathlib import Path
from iagent_mesh.scaffold_core import generate_template_files

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
    assert "urn:test" in app_content
    assert "REPLACE_ME_URN" not in app_content
    
    toml_content = pyproject_toml.read_text(encoding="utf-8")
    assert "test-tool" in toml_content
    assert "REPLACE_ME_NAME" not in toml_content
    
    # 3. Test Template Exclusion
    template_yaml = tmp_path / "template.yaml"
    assert not template_yaml.exists()

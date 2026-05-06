import os
import shutil
import pytest
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
import sys
from iagent_mesh.scaffold_core import generate_template_files

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
TEMPLATE_IDS = [d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir()]

# We mock heavy external dependencies to allow structural validation without 
# installing the entire data science stack in the CI environment.
# For Pydantic to accept these as type hints, they need to be actual classes.
from pydantic import BaseModel
class MockType(BaseModel): pass

MOCK_MODULES = [
    "polars", "pandas", "instructor", "baml_py", 
    "llama_index", "llama_index.core", "langchain", "langchain.agents", 
    "langchain.chat_models", "smolagents", "nest_asyncio", "dag_tools",
    "dag_tools.cortex_data.client", "langchain_openai", "baml_client",
    "baml_client.types"
]

@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_template_scaffold_and_load(template_id, tmp_path):
    """
    E2E test: Scaffolds each template and verifies the resulting app.py is valid and runnable.
    """
    # Apply mocks
    for mod in MOCK_MODULES:
        mock_mod = MagicMock()
        # If the template tries to use a class from the module as a type hint
        # we give it a real class so Pydantic doesn't explode
        mock_mod.BamlExtractedOutput = MockType
        mock_mod.VectorStoreIndex = MockType
        mock_mod.Document = MockType
        mock_mod.ChatOpenAI = MockType
        
        sys.modules[mod] = mock_mod
        
    tool_name = f"test-{template_id}".replace("_", "-")
    tool_urn = f"urn:li:aitool:{tool_name}"
    dest_dir = tmp_path / template_id
    
    # 1. Scaffold the template
    generate_template_files(template_id, tool_name, tool_urn, str(dest_dir))
    
    app_path = dest_dir / "app.py"
    assert app_path.exists(), f"app.py missing for template {template_id}"
    
    # 2. Dynamically load the generated app.py
    # We use a unique module name for each template to avoid import caching issues
    spec = importlib.util.spec_from_file_location(f"module_{template_id}", str(app_path))
    module = importlib.util.module_from_spec(spec)
    
    # We mock the environment since some templates might try to call DataHub or other APIs at startup
    os.environ["DATAHUB_URL"] = "http://mock-datahub"
    os.environ["LOCAL_DEV"] = "true"
    
    try:
        spec.loader.exec_module(module)
        
        # 3. Assertions: Check if 'app' exists and is a MeshTool (or has the expected FastAPI app)
        assert hasattr(module, "app"), f"Template {template_id} failed to export 'app'"
        
        # Depending on the template, 'app' might be a MeshTool instance or a FastAPI instance
        # Most of our templates use 'app = MeshTool(...)'
        from iagent_mesh.core import MeshTool
        if isinstance(module.app, MeshTool):
            assert module.app.name == tool_name
            assert module.app.urn == tool_urn
            assert module.app.app.title == tool_urn
        else:
            # Fallback for templates that might expose the FastAPI app directly
            assert hasattr(module.app, "title")
            
    except Exception as e:
        pytest.fail(f"Template {template_id} failed to load or has syntax errors: {e}")

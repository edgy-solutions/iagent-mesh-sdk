# DevEx Hub: Jupyter Notebook Quickstart

Welcome to the iagent Mesh! As a Data Scientist, you have access to two distinct layers of the platform directly from your secured JupyterHub environment.

## 1. The Control Plane (Interacting with the AI)

The Control Plane allows you to chat with the central AI orchestrator (Engine A). You can ask it to find assets, scaffold new tools, or trigger deployments. 

Auth is handled invisibly via Keycloak because the `MESH_DEV_TOKEN` is automatically injected into your Jupyter environment. All you need to do is import the `MeshClient`:

### Scenario A: Asking the AI Orchestrator to do work
#### Python
```python
from iagent_mesh import MeshClient

# Initialize the client (automatically picks up your secure MESH_DEV_TOKEN)
client = MeshClient()

# Ask the orchestrator a question or give it a command
response = client.ask("Find the latest 'Asset Reliability' dataset and scaffold a new BAML tool for it.")

print(response)
```

## 2. The Data Plane (Working with Big Data)

Once the AI orchestrator tells you where a dataset lives (e.g., an S3 path or a DataHub URN), you can load the heavy Parquet or CSV files directly into your notebook.

You don't stream big data through the AI! Instead, `dag_tools` implements a unified, zero-trust data plane through the **Cortex Data Client**, which handles authorization, credential minting, and data fetching under the hood.

### Scenario B: Loading raw data directly from the Data Plane (Zero-Config)
#### Python
```python
import polars as pl
from dag_tools.cortex_data.client import CortexDataClient

# 1. Initialize the Universal Data Client
# Zero-Config! Automatically picks up CORTEX_BROKER_URL and MESH_DEV_TOKEN
client = CortexDataClient()

# 2. Fetch the DataHub URN directly
lf = client.get_dataframe("urn:li:dataset:(urn:li:dataPlatform:s3,reliability_metrics,PROD)")

# 3. Compute and view the data
df = lf.collect()
print(df.head())
```

## 3. The "Inception" Workflow (Turning Logic into a Mesh Tool)

Once you've finalized your logic in Jupyter, you can turn your function into a registered Mesh Tool that the central AI can call.

### Scenario C: Building and Registering a Mesh Tool
#### Python
```python
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field

# 1. Define your Input/Output schemas
class AnalysisInput(ToolInput):
    facility_id: str = Field(..., description="The ID of the target facility.")

class AnalysisOutput(ToolOutput):
    score: float

# 2. Wrap your logic in the MeshTool
app = MeshTool(name="my_custom_analysis", description="Detailed reliability analysis.")

@app.execute()
def my_analysis(data: AnalysisInput) -> AnalysisOutput:
    # Use the client we initialized above!
    from dag_tools.cortex_data.client import CortexDataClient
    client = CortexDataClient()
    lf = client.get_dataframe("urn:li:dataset:...")
    
    # ... logic ...
    return AnalysisOutput(score=42.0)
```

### Scaffolding to Production
To turn this notebook into a production repository, use the provided scaffolding scripts:

#### Bash
```bash
# In your terminal
./scripts/scaffold.sh
# Follow the interactive prompts to select your template and tool name!
```

### Summary
- Use **`iagent_mesh.MeshClient`** to tell the AI what to do.
- Use **`CortexDataClient()`** for zero-config, secure data access.
- Use **`MeshTool`** to wrap and register your logic for the AI Orchestrator.

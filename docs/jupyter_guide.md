# DevEx Hub: Jupyter Notebook Quickstart

Welcome to the iagent Mesh! As a Data Scientist, you have access to two distinct layers of the platform directly from your secured JupyterHub environment.

## 1. The Control Plane (Interacting with the AI)

The Control Plane allows you to chat with the central AI orchestrator (Engine A). You can ask it to find assets, scaffold new tools, or trigger deployments. 

Auth is handled invisibly via Keycloak because the `MESH_DEV_TOKEN` is automatically injected into your Jupyter environment. 

All you need to do is import the `MeshClient`:

```python
# Scenario A: Asking the AI Orchestrator to do work
from iagent_mesh import MeshClient

# Initialize the client (automatically picks up your secure MESH_DEV_TOKEN)
client = MeshClient()

# Ask the orchestrator a question or give it a command
response = client.ask("Find the latest 'Asset Reliability' dataset and scaffold a new BAML tool for it.")

print(response)
```

## 2. The Data Plane (Working with Big Data)

Once the AI orchestrator tells you where a dataset lives (e.g., an S3 path or a DataHub URN), you can load the heavy Parquet or CSV files directly into your notebook.

You don't stream big data through the AI! Instead, use `dag_tools` to fetch the secure credentials and load the data directly into Pandas or Polars.

```python
# Scenario B: Loading raw data directly from the Data Plane
import pandas as pd
import dag_tools

# Fetch secure STS tokens from Engine DA
credentials = dag_tools.get_sts_credentials("urn:li:dataset:(urn:li:dataPlatform:s3,reliability_metrics,PROD)")

# Load the heavy dataset directly into Pandas
df = pd.read_parquet(
    "s3://sustainment-data-lake/reliability_metrics/latest.parquet",
    storage_options={
        "key": credentials.access_key,
        "secret": credentials.secret_key,
        "token": credentials.session_token
    }
)

df.head()
```

### Summary
- Use **`iagent_mesh.MeshClient`** to tell the AI what to do.
- Use **`dag_tools`** and **`pandas/polars`** to actually crunch the numbers.

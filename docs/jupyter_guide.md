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

You don't stream big data through the AI! Instead, `dag-tools` implements a unified, zero-trust data plane through the **Cortex Data Client**, which handles authorization, credential minting, and data fetching under the hood.

```python
import polars as pl
from dag_tools.cortex_data.client import CortexDataClient

# 1. Initialize the Universal Data Client
# It automatically uses M2M credentials or an existing JWT 
client = CortexDataClient(
    broker_url="https://gateway.internal.domain",
    client_id="your-m2m-client-id",
    client_secret="your-m2m-secret"
)

# 2. Fetch the DataHub URN directly
# The client talks to the Central Gateway, gets STS credentials under the hood, 
# applies security filters, and returns a Polars LazyFrame
lf = client.get_dataframe("urn:li:dataset:(urn:li:dataPlatform:s3,reliability_metrics,PROD)")

# 3. Compute and view the data
df = lf.collect()
print(df.head())
```

### Key Differences:
1. **Polars over Pandas**: The client returns a `polars.LazyFrame` (using `pl.scan_parquet` internally for S3). This is required for our unified Jupyter-to-Production pipeline portability.
2. **Abstracted Credentials**: You do not manually handle the STS tokens. The `CortexDataClient` automatically calls the Central Gateway's `/authorize` endpoint to exchange your JWT for a routing ticket and injects the returned AWS STS credentials natively into the Polars execution context.
3. **Automatic Security Enforcement**: The client automatically applies Row Level Security (RLS) filters and Column Masking (`allowed_columns`) returned by the Topaz AuthZ engine before you ever see the DataFrame.

### Summary
- Use **`iagent_mesh.MeshClient`** to tell the AI what to do.
- Use **`CortexDataClient`** and **`polars`** to actually crunch the numbers securely.

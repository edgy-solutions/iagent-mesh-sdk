# DevEx Hub: Jupyter Notebook Quickstart

Welcome to the iagent Mesh! As a Data Scientist, you have access to three distinct layers of the platform directly from your secured JupyterHub environment.

## 1. The Control Plane (Commanding the AI)

The Control Plane allows you to chat with the central AI orchestrator (Engine A). Auth is handled invisibly via Keycloak because the `MESH_DEV_TOKEN` is automatically injected into your Jupyter environment. 

### Scenario A: Asking the AI Orchestrator to do work
```python
from iagent_mesh import MeshClient

# Defaults to the in-cluster cortex-bff (http://iagent-cortex-bff:8090/orchestrate).
# Pass gateway_url= if you are port-forwarding.
client = MeshClient()

# Command the orchestrator to act on your behalf.
# `ask` consumes the gateway's SSE stream and blocks until the run completes.
response = client.ask("Find the latest 'Asset Reliability' dataset and summarize its schema.")

print(response.text)            # the answer
print(len(response.events))     # the routing/status trace, for debugging
```

One `MeshClient` is one conversation: it reuses a `session_id` so follow-up questions land on the
same thread. Pass `session_id=` (per client or per `ask`) to control that explicitly.

## 2. The Data Plane (Working with Big Data)

Once you know where a dataset lives, load the heavy Parquet or CSV files directly into your notebook. We do not stream big data through the AI. Instead, `dag_tools` provides a unified, zero-trust data plane that handles credential minting invisibly.

> **This client ships in `dag-tools`, not in this SDK.** Install it with
> `uv pip install edgy-dag-tools` (distribution name differs from the import name:
> `import dag_tools`). Installing `iagent-mesh` alone will not give you `CortexDataClient`.

### Scenario B: Loading raw data securely (Zero-Config)
```python
import polars as pl
from dag_tools.cortex_data.client import CortexDataClient

# Zero-Config! Automatically picks up CORTEX_BROKER_URL and your MESH_DEV_TOKEN
client = CortexDataClient()

# Fetch the DataHub URN directly. Topaz handles RLS and Column Masking automatically.
lf = client.get_dataframe("urn:li:dataset:(urn:li:dataPlatform:postgres,sales_customers,PROD)")

df = lf.collect()
print(df.head())
```

**Use a URN the broker actually serves.** The gateway routes by an exact URN registered by a
domain broker; anything else is a `404 No active domain broker found`. The sandbox broker
currently serves exactly two:

| URN | Source |
| --- | --- |
| `urn:li:dataset:(urn:li:dataPlatform:postgres,sales_customers,PROD)` | postgres |
| `urn:li:dataset:(urn:li:dataPlatform:postgres,instance_state,PROD)` | postgres |

*(An earlier version of this guide used an `s3,reliability_metrics` URN that no broker has ever
registered — the example itself returned 404.)*

#### Who the read is authorized as

The broker decides which rows and columns you get from **one opaque subject**. Resolution order:

1. `X-Originator-Email` if the client was given `originator_email=` — used **verbatim**.
2. otherwise the claim named by `USER_ENTITLEMENT_CLAIM` (default `email`) on your token.

Despite the name, the value is **never parsed as an email**. At work-deploy, where the
entitlement key is an employee id, pass the employee id — every hop carries it opaque:

```python
client = CortexDataClient(originator_email="E123456")   # employee id — carried verbatim
```

Zero-config works only when your token itself carries the configured claim. A **service/M2M**
token has no user subject, so a bare `CortexDataClient()` on an agent pod authorizes as the
*service* — see §3 for how a tool gets its caller.

## 3. The Anatomy of a Domain Node (A Conceptual Look)

Before you generate a full project, here is a look at the raw engine. This is all it takes to turn your Python logic into a secure, globally discoverable AI Node on the Mesh. 

Notice how there is no API routing, no Keycloak validation, and no HTTP boilerplate. You just define your Pydantic schema (which acts as the prompt for the Central AI) and write your logic. 

```python
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field

# 1. Prompt Engineer the Central AI using strict types and descriptions
class AnomalyInput(ToolInput):
    dataset_name: str = Field(..., description="The name of the dataset to analyze.")
    sensitivity: float = Field(0.9, description="Threshold for flagging anomalies.")

class AnomalyOutput(ToolOutput):
    flagged_records: int
    summary: str

# 2. Register your Node as a typed predicate in the mesh's predicate graph.
#    The verb is the *operation* (a named relation between concept classes);
#    input_uri / output_uri are the typed endpoints. The router (Engine O)
#    discovers your tool by walking the predicate graph -- it does NOT
#    pattern-match the description.
#
#    See the SDK ADRs for the model:
#      - ADR-0004: predicate-graph routing
#      - ADR-0005: domain (mro:, logistics:, ...) vs platform (mesh:) prefixes
app = MeshTool(
    name="basic_anomaly_detector",
    description="Flags anomalies in a dataset given a sensitivity threshold.",
    verb="mro:detectVibrationAnomalies",        # what this tool DOES
    input_uri="mro:VibrationDataset",            # what it consumes
    output_uri="mro:AnomalyReport",              # what it produces
    verb_synonyms=["find anomalies", "flag outliers"],
    owner_persona="MECHANIC",
    cost_class="medium",
)

# 3. Write your clean business logic
@app.execute()
def detect_anomalies(data: AnomalyInput) -> AnomalyOutput:
    # Topaz security and Trace IDs are already handled invisibly!
    print(f"Scanning {data.dataset_name} at {data.sensitivity} sensitivity...")

    # ... your Polars/Pandas/Agentic logic goes here ...

    return AnomalyOutput(flagged_records=42, summary="Found severe outliers in Q3 data.")
```

### Reading data *as the user who asked* (required for any per-user read)

A tool invoked through the mesh is called by the **supervisor**, not by a person. If your handler
builds a data client with no subject, the read authorizes as your tool's **service identity** —
so every user of your tool sees the service's data. It returns rows and raises nothing, which is
what makes it dangerous.

Ask for the caller by annotating a parameter `CallerIdentity`:

```python
from iagent_mesh import CallerIdentity
from dag_tools.cortex_data.client import CortexDataClient

@app.execute()
def detect_anomalies(data: AnomalyInput, caller: CallerIdentity) -> AnomalyOutput:
    # require_authz_id() REFUSES an unresolved caller instead of silently
    # falling back to the service identity.
    client = CortexDataClient(originator_email=caller.require_authz_id())
    lf = client.get_dataframe(data.dataset_name)
    df = lf.collect()          # runs on a worker thread; safe to block
    ...
```

`caller.authz_id` is the subject from your deployment's `USER_ENTITLEMENT_CLAIM` — an email in
the sandbox, an employee id at work. Prefer `require_authz_id()` at a **read**; use the plain
`.authz_id` (which may be `None`) only for logging.

If the client is built several frames below your handler, `current_caller()` reads the same
identity without threading a parameter through:

```python
from iagent_mesh import current_caller

def _load(urn):                       # called from your handler, no parameter passed
    return CortexDataClient(originator_email=current_caller().require_authz_id()).get_dataframe(urn)
```

> Handlers that read no per-user data need no `caller` parameter — the single-argument form is
> unchanged.

> **Note** — DataHub registration is opt-in. Set
> `MESH_REGISTER_ON_STARTUP=true` (plus `DATAHUB_GMS_URL` and
> `DATAHUB_TOKEN`) when you want the tool to announce itself to the
> mesh; leave it unset for local-dev. The tool always serves requests
> regardless.

*This is just the appetizer. When you are ready to build for real, proceed to Section 4 to scaffold your production-ready workspace!*

## 4. Building Your Own Node (Moving to the IDE)

Your notebook is perfect for prototyping data logic (Data Plane) and asking the AI questions (Control Plane). But when you are ready to turn your logic into an enterprise capability, **you move out of the notebook and into your IDE.**

We provide a curated catalog of production-ready templates. You do not need to write boilerplate!

### Step 1: Scaffold your workspace
Generate a fresh template using any of these three methods:

1. **Ask the Central AI:** Use your `MeshClient` in this notebook:
   `client.ask("Scaffold a new smolagents template named supply_chain_investigator")`
2. **Ask your IDE:** If using an AI IDE (Cursor/Windsurf), ask the local MCP server to do it.
3. **Use the Terminal Wizard:** Run `./scripts/scaffold.sh` and follow the prompts.

### Step 2: Choose Your Architecture (The Template Catalog)

When scaffolding, you will be asked to select a template. Choose the one that fits your architecture. (Note: The generated files will always contain the most up-to-date platform standards and `nest_asyncio` patches).

#### Template 1: `01_pure_math` (The Logic Tool)
* **Best for:** Synchronous Python math, physics calculations, or deterministic logic.
* **How it works:** A lightweight, pure-Python wrapper. Perfect for moving your proven notebook algorithms into the Mesh without any LLM or database overhead.

#### Template 2: `02_instructor_polars` (The Standard Data Tool)
* **Best for:** Data crunching and high-performance analytical queries.
* **How it works:** Wires up `Polars` for fast data access via the Data Plane. It uses the `instructor` pattern to ensure the Mesh Orchestrator extracts exactly the entities your analysis needs.

#### Template 3: `03_baml_pandas` (The Hybrid Tool)
* **Best for:** Legacy Pandas workflows that require advanced LLM extraction.
* **How it works:** Combines the familiarity of Pandas with the power of the `BAML` Rust compiler. Use this if you need to extract complex structures from unstructured documents in your data pipeline.

#### Template 4: `smolagents_subswarm` (The Agentic Tool)
* **Best for:** Complex, multi-step reasoning that requires an autonomous loop.
* **How it works:** You become a Node Commander. The template wires up a local `CodeAgent` safely inside your tool. The Central AI routes the hard questions to your tool, and your local agent investigates it autonomously before returning the verdict.

#### Template 5: `legacy_adapter` (The Framework Wrapper)
* **Best for:** Existing LlamaIndex RAG pipelines or LangChain routing setups.
* **How it works:** Do not rewrite your old code! This template acts as a "Smart Ingress Controller." Engine A parses the messy human prompt, classifies the intent, and hands your legacy LangChain/LlamaIndex code the exact clean query it needs to run.

### Step 3: Publish to the Mesh
Once you have filled in your business logic in the generated `app.py`, push the repository to Git (or ask the MCP server to `publish` it). Our GitOps pipeline will build, deploy, and dynamically register your Domain Node to the global Mesh!

---

> ### 💡 Platform Pro-Tip: `def` vs `async def`
> The `MeshTool` templates support both asynchronous and synchronous Python.
> * **Use standard `def` (Recommended):** If you are crunching Polars DataFrames (`df.collect()`), stick to standard `def`. We execute it in a background thread, so a long `collect()` does not stall other requests to your tool.
> * **Use `async def`:** Only if your tool is a lightweight router making numerous downstream HTTP calls.
>
> *(This was a promise the SDK did not keep until 0.4.0 — sync handlers ran inline on the event
> loop, so the recommended shape for the heaviest workload was the one that blocked every
> concurrent request, health probes included.)*


---


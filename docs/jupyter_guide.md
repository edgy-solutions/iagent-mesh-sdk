# DevEx Hub: Jupyter Notebook Quickstart

Welcome to the iagent Mesh! As a Data Scientist, you have access to three distinct layers of the platform directly from your secured JupyterHub environment.

## 1. The Control Plane (Commanding the AI)

The Control Plane allows you to chat with the central AI orchestrator (Engine A). Auth is handled invisibly via Keycloak because the `MESH_DEV_TOKEN` is automatically injected into your Jupyter environment. 

### Scenario A: Asking the AI Orchestrator to do work
```python
from iagent_mesh import MeshClient

client = MeshClient()

# Command the orchestrator to act on your behalf
response = client.ask("Find the latest 'Asset Reliability' dataset and scaffold a new BAML tool for it.")
print(response)
```

## 2. The Data Plane (Working with Big Data)

Once you know where a dataset lives, load the heavy Parquet or CSV files directly into your notebook. We do not stream big data through the AI. Instead, `dag_tools` provides a unified, zero-trust data plane that handles credential minting invisibly.

### Scenario B: Loading raw data securely (Zero-Config)
```python
import polars as pl
from dag_tools.cortex_data.client import CortexDataClient

# Zero-Config! Automatically picks up CORTEX_BROKER_URL and your MESH_DEV_TOKEN
client = CortexDataClient()

# Fetch the DataHub URN directly. Topaz handles RLS and Column Masking automatically.
lf = client.get_dataframe("urn:li:dataset:(urn:li:dataPlatform:s3,reliability_metrics,PROD)")

df = lf.collect()
print(df.head())
```

## 3. Prompt Engineering the Mesh (Tool Registration)

When you turn your Python logic into a Mesh Tool, you are not just writing an API—**you are prompt engineering the central AI.** The Central Orchestrator reads your `description` strings to decide when and how to route traffic to you. The better your descriptions, the smarter the Central AI becomes at using your tool.

### Scenario C: Steering the Central AI with Pydantic
```python
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field
from dag_tools.cortex_data.client import CortexDataClient

# 1. PROMPT ENGINEERING YOUR INPUTS
# These descriptions tell the Central LLM exactly how to format the data before calling you.
class AnalysisInput(ToolInput):
    facility_id: str = Field(
        ..., 
        description="The exact ID of the facility (e.g., 'FAC-123'). If the user provides a city name, you must look up the facility_id first."
    )
    confidence: float = Field(
        0.95, 
        description="Statistical confidence threshold. Default to 0.95 unless the user specifies otherwise."
    )

class AnalysisOutput(ToolOutput):
    score: float
    recommendation: str

# 2. PROMPT ENGINEERING YOUR TOOL
# This acts as the System Prompt for your capability in the mesh.
app = MeshTool(
    name="reliability_analyzer", 
    description="USE THIS TOOL ONLY when asked to perform deep statistical reliability analysis. Do not use this for simple metrics."
)

@app.execute()
def my_analysis(data: AnalysisInput) -> AnalysisOutput:
    # Crunch the numbers using the Data Plane
    client = CortexDataClient()
    lf = client.get_dataframe("urn:li:dataset:...")
    
    return AnalysisOutput(score=42.0, recommendation="Inspect turbine blade pitch.")
```

## 4. The Agentic Tool (Building a Sub-Swarm)

Sometimes, pure math isn't enough. If your tool needs to perform complex reasoning *before* returning an answer to the Central Orchestrator, you can embed your own local LLM agent directly inside the Mesh Tool! 

You control the brain of your specific domain.

### Scenario D: Putting an Agent inside a Tool
```python
from iagent_mesh.core import MeshTool
from pydantic import Field
from smolagents import CodeAgent, HfApiModel # Or LangChain, Ollama, etc.
from dag_tools.cortex_data.client import CortexDataClient

app = MeshTool(
    name="supply_chain_investigator", 
    description="Pass a supplier ID to this tool, and it will autonomously investigate their recent delays."
)

@app.execute()
def investigate_supplier(data: SupplierInput) -> InvestigationOutput:
    # 1. Pull the massive datasets locally
    client = CortexDataClient()
    df_delays = client.get_dataframe("urn:li:dataset:supplier_delays").collect()
    
    # 2. Spin up your own LOCAL agent to reason over the data!
    local_agent = CodeAgent(tools=[], model=HfApiModel())
    
    prompt = f"Analyze this delay data for {data.supplier_id} and determine the root cause: {df_delays.to_pandas()}"
    verdict = local_agent.run(prompt)
    
    # 3. Return the intelligent verdict back up to the Central Orchestrator
    return InvestigationOutput(root_cause_analysis=verdict)
```

## 5. Integrating Legacy Frameworks (LangChain & LlamaIndex)

If you have already built robust RAG pipelines in LlamaIndex or complex agentic loops in LangChain, **do not rewrite them!** Instead, wrap them in a `MeshTool`. The Central AI (Engine A) will act as your "Front Desk." It will parse the messy human prompt, extract the exact entities your LangChain/LlamaIndex setup needs, and hand you a perfectly formatted Pydantic object to kick off your existing graph.

### Scenario E: The LlamaIndex / LangChain Adapter
```python
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field
from typing import Literal

# Import your legacy frameworks!
from llama_index.core import VectorStoreIndex, Document
from langchain.agents import initialize_agent, AgentType
from langchain.chat_models import ChatOpenAI

# 1. PROMPT ENGINEER YOUR INGRESS
# Engine A does the heavy NLP parsing so your LlamaIndex/LangChain code doesn't have to.
class EnterprisePolicyInput(ToolInput):
    clean_query: str = Field(
        ..., 
        description="Rewrite the user's messy prompt into a highly optimized search query for a Vector DB."
    )
    policy_domain: Literal["HR", "IT", "Finance"] = Field(
        ..., 
        description="Classify the domain of the question to route to the correct LlamaIndex store."
    )
    requires_approval: bool = Field(
        False, 
        description="Set to True if the user is asking to modify a policy or execute a financial transaction."
    )

class PolicyOutput(ToolOutput):
    final_answer: str
    sources_cited: list[str]

# 2. REGISTER THE NODE
app = MeshTool(
    name="enterprise_policy_router", 
    description="ROUTE ALL company policy, IT troubleshooting, and HR questions here."
)

@app.execute()
def legacy_framework_router(data: EnterprisePolicyInput) -> PolicyOutput:
    # --- YOUR EXISTING LLAMA-INDEX / LANGCHAIN CODE LIVES HERE ---
    
    if data.requires_approval:
        # Route to a LangChain execution agent for action-taking
        llm = ChatOpenAI(temperature=0)
        agent = initialize_agent(tools=[...], llm=llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
        result = agent.run(f"Execute approval workflow for: {data.clean_query}")
        return PolicyOutput(final_answer=result, sources_cited=["LangChain Execution Env"])
        
    else:
        # Route to LlamaIndex for heavy RAG
        # Because Engine A already classified 'policy_domain', you know exactly which index to load!
        index = load_my_llama_index(domain=data.policy_domain) 
        query_engine = index.as_query_engine()
        
        # Notice we use the 'clean_query' that Engine A optimized for us
        response = query_engine.query(data.clean_query) 
        
        sources = [node.node.metadata.get('file_name') for node in response.source_nodes]
        return PolicyOutput(final_answer=str(response), sources_cited=sources)
```

## 6. From Notebook to Production (The Template Smorgasbord)

Your notebook is the perfect place to prototype your data logic and prompts. Once your agent or tool is working, you need to package it for the Mesh. 

Instead of writing Dockerfiles, Kubernetes manifests, and FastAPI boilerplate from scratch, you pull from our curated smorgasbord of enterprise templates (e.g., `instructor_polars`, `smolagents_router`, `basic_meshtool`).

### Step 1: Scaffold your workspace
Generate a fresh template using any of these three methods:

1. **Ask the Central AI (The Control Plane):** Use your `MeshClient` to ask Engine A to do it for you:
   `client.ask("Scaffold a new smolagents template named supply_chain_investigator")`
   
2. **Ask your IDE (The MCP Server):** If you are using an AI IDE (like Cursor or Windsurf) connected to your local workspace, just ask it! Our local MCP server allows your IDE to scaffold templates autonomously.
   
3. **Use the Terminal Wizard:**
   ```bash
   # Run the interactive wizard to select your template
   ./scripts/scaffold.sh
   ```

### Step 2: Paste and Publish
Once your template is generated:
1. Copy your prototyped Pydantic models and `@app.execute()` function from your notebook into the new `app.py` file.
2. Push the repository to Git (or ask the MCP server to `publish` it for you). 
3. Our GitOps pipeline will automatically build your container, deploy it, and dynamically register your Domain Node to the global Mesh!

---

> ### 💡 Platform Pro-Tip: `def` vs `async def`
> The `MeshTool` framework supports both asynchronous and synchronous Python!
> * **Use standard `def` (Recommended):** If your tool does heavy data crunching with Polars/Pandas (`df.collect()`), use standard `def`. The platform will automatically execute your heavy math in a background thread so your API remains responsive.
> * **Use `async def`:** Only use this if your tool acts as a lightweight router making numerous downstream `httpx` or database calls.


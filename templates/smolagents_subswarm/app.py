import os
import nest_asyncio
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field
from smolagents import CodeAgent, HfApiModel
from dag_tools.cortex_data.client import CortexDataClient

# Apply global patch to allow agents to run safely inside FastAPI's event loop
nest_asyncio.apply()

class InvestigationInput(ToolInput):
    target_id: str = Field(..., description="The ID of the entity to investigate.")
    context: str = Field("", description="Additional context from the user.")

class InvestigationOutput(ToolOutput):
    findings: str

# REPLACE_ME_NAME is automatically swapped by scaffold.sh
# Predicate edge — autonomous multi-step investigation:
#     (mesh:InvestigationTarget) --[mesh:investigateEntity]--> (mesh:InvestigationFindings)
#
# Investigation loops are mesh-internal (no domain ontology has a clean
# concept for "agent ran a tool-use loop and produced findings"); the verb
# lives in the platform namespace.
app = MeshTool(
    name="REPLACE_ME_NAME",
    description="Autonomous CodeAgent investigation loop. Inputs an entity, outputs findings.",
    verb="mesh:investigateEntity",
    input_uri="mesh:InvestigationTarget",
    output_uri="mesh:InvestigationFindings",
    verb_synonyms=["investigate", "root cause", "drill down"],
    owner_persona="AUDITOR",
    cost_class="slow",  # agentic loops are not cheap
    requires_human_approval=False,
)

@app.execute()
def run_investigation(data: InvestigationInput) -> InvestigationOutput:
    # 1. Access Data Plane securely (Optional: define tools for your agent)
    # client = CortexDataClient()
    # df = client.get_dataframe("urn:li:dataset:...").collect()
    
    # 2. Spin up your local Sub-Swarm Agent
    # HfApiModel is used as a default; swap with your preferred enterprise LLM provider
    local_agent = CodeAgent(tools=[], model=HfApiModel())
    
    # 3. Prompt Engineer your agent's task
    prompt = f"Investigate {data.target_id}. Consider this context: {data.context}."
    result = local_agent.run(prompt)
    
    return InvestigationOutput(findings=str(result))

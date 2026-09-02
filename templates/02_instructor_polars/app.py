import polars as pl
import instructor
from openai import AsyncOpenAI
from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput, DataPointer
from iagent_mesh.core import MeshTool

# 1. Define the Schema (Prompting the Router)
class InventoryInput(ToolInput):
    target_facility: str = Field(..., description="The facility location code.")
    document_pointer: DataPointer = Field(..., description="Pointer from Engine DA")

class InventoryOutput(ToolOutput):
    high_priority_items: list[str]
    total_value: float

# 2. Initialize the Mesh Tool — this tool is a predicate edge in the graph:
#
#     (logistics:InventorySnapshot) --[logistics:analyzeFacilityInventory]--> (logistics:InventorySummary)
#
# See ADR-0004 for the model, ADR-0005 for namespacing.
app = MeshTool(
    name="REPLACE_ME_NAME",
    description="Analyzes facility inventory via Polars over a Parquet snapshot.",
    verb="logistics:analyzeFacilityInventory",
    input_uri="logistics:InventorySnapshot",
    output_uri="logistics:InventorySummary",
    verb_synonyms=["inventory rollup", "summarize inventory", "facility totals"],
    owner_persona="LOGISTICS",
    cost_class="medium",
)

# 3. Write the Logic
# `caller_scoped=False` DECLARES that this handler does not scope to the verified caller.
# Read this before copying the pattern: the read below is scoped by the token INSIDE
# `data.document_pointer`, which the caller supplies in the request body. That is the legacy
# Engine-DA-mints-a-pointer shape — the scope rides in an unauthenticated payload field rather
# than being derived from a verified identity.
#
# For a tool that reaches the data plane ITSELF, prefer the caller-scoped pattern instead
# (see templates/smolagents_subswarm):
#
#     @app.execute()
#     async def analyze(data: InventoryInput, caller: CallerIdentity) -> InventoryOutput:
#         client = CortexDataClient(originator_email=caller.require_authz_id())
@app.execute(caller_scoped=False)
async def analyze_inventory(data: InventoryInput) -> InventoryOutput:
    # A. Obey Data Gravity: Read Polars directly from MinIO using the Topaz token
    storage_options = {"aws_session_token": data.document_pointer.temporary_access_token}
    df = pl.read_parquet(data.document_pointer.uri, storage_options=storage_options)
    
    # B. Do the Math
    filtered_df = df.filter(pl.col("facility") == data.target_facility)
    total_val = filtered_df["price"].sum()
    items = filtered_df["item_name"].to_list()

    # C. (Optional) Pass to Instructor LLM for summarization/formatting
    # llm_client = instructor.from_openai(AsyncOpenAI(base_url="http://vllm..."))
    # result = await llm_client.chat.completions.create(...)

    return InventoryOutput(high_priority_items=items, total_value=total_val)

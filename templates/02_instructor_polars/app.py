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
@app.execute()
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

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

# 2. Initialize the Mesh Tool
app = MeshTool(urn="REPLACE_ME_URN", description="Analyzes inventory via Polars")

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

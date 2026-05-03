# iagent-mesh-sdk

This repository contains the `iagent_mesh` SDK, which provides universal contracts and an infrastructure wrapper for the iagent Mesh platform.

## Installation

Data scientists can install this SDK directly via `uv pip install`:

```bash
uv pip install git+https://[your-repo-url]
```

## Data Scientist Templates

Below are the three templates to be handed to data scientists. Notice how you never need to import FastAPI or write HTTP logic.

### Template 1: Instructor + Polars (The Standard DA Query)

Best for: Querying large Parquet files securely provided by Engine DA using local IDEs (code-server).

```python
# app.py
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
app = MeshTool(urn="urn:li:tool:polars_inventory", description="Analyzes inventory via Polars")

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
```

### Template 2: BAML + Pandas (Converting DA Data for Legacy ML)

Best for: When data scientists have existing legacy Pandas code, but still need to use BAML for prompt engineering and Engine DA for the data pointer.

```python
# app.py
import polars as pl
import pandas as pd
from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput, DataPointer
from iagent_mesh.core import MeshTool
from baml_client import b 
from baml_client.types import BamlExtractedOutput

class LegacyModelInput(ToolInput):
    threshold: float
    document_pointer: DataPointer

class LegacyModelOutput(ToolOutput):
    baml_analysis: BamlExtractedOutput

app = MeshTool(urn="urn:li:tool:pandas_baml_analyzer", description="Pandas + BAML")

@app.execute()
async def run_legacy_analysis(data: LegacyModelInput) -> LegacyModelOutput:
    # A. Fetch highly optimized Polars dataframe from the Mesh
    storage_options = {"aws_session_token": data.document_pointer.temporary_access_token}
    df_polars = pl.read_parquet(data.document_pointer.uri, storage_options=storage_options)
    
    # B. Convert to Pandas for their legacy scikit-learn/ML workloads
    df_pandas = df_polars.to_pandas()
    
    # C. Do legacy Pandas math
    anomalies = df_pandas[df_pandas['vibration'] > data.threshold]
    anomaly_text_summary = anomalies.to_string()

    # D. Pass the Pandas output into the BAML Rust compiler for LLM reasoning
    baml_result = await b.ExtractAnomalies(anomaly_text_summary)
    
    return LegacyModelOutput(baml_analysis=baml_result)
```

### Template 3: Pure Math / No Data Pointer (The Edge Device)

Best for: Simple calculators, standard LLM prompt wrappers, or YOLO vision models running on Triton where Engine DA is not involved.

```python
# app.py
from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool

# Notice: No DataPointer here. Engine DA just passes literal values.
class MathInput(ToolInput):
    flight_hours: float = Field(..., description="Total logged flight hours")
    environment_factor: float = Field(..., description="Multiplier for harsh environments")

class MathOutput(ToolOutput):
    projected_wear: float

app = MeshTool(urn="urn:li:tool:simple_math", description="Calculates rotor wear limits.")

@app.execute()
def calculate_wear(data: MathInput) -> MathOutput:
    # Pure, synchronous Python math. No network calls. No LLMs.
    wear = (data.flight_hours / 10000.0) * data.environment_factor * 100 
    
    return MathOutput(projected_wear=round(wear, 2))
```

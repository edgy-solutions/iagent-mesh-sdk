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

app = MeshTool(urn="REPLACE_ME_URN", description="Pandas + BAML")

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

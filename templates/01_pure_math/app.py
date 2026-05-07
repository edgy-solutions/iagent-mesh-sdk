from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool

# Notice: No DataPointer here. Engine DA just passes literal values.
class MathInput(ToolInput):
    flight_hours: float = Field(..., description="Total logged flight hours")
    environment_factor: float = Field(..., description="Multiplier for harsh environments")

class MathOutput(ToolOutput):
    projected_wear: float

app = MeshTool(
    name="REPLACE_ME_NAME", 
    description="Calculates rotor wear limits.",
    # Link this tool to the Enterprise Ontology so the Mesh can route to it:
    # ontology_uris=["mro:RotorAssembly", "mro:MaintenanceMetric"]
)

@app.execute()
def calculate_wear(data: MathInput) -> MathOutput:
    # Pure, synchronous Python math. No network calls. No LLMs.
    wear = (data.flight_hours / 10000.0) * data.environment_factor * 100 
    
    return MathOutput(projected_wear=round(wear, 2))

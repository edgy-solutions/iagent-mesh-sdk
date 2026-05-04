from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool

# Notice: No DataPointer here. Engine DA just passes literal values.
class MathInput(ToolInput):
    flight_hours: float = Field(..., description="Total logged flight hours")
    environment_factor: float = Field(..., description="Multiplier for harsh environments")

class MathOutput(ToolOutput):
    projected_wear: float

app = MeshTool(urn="REPLACE_ME_URN", description="Calculates rotor wear limits.")

@app.execute()
def calculate_wear(data: MathInput) -> MathOutput:
    # Pure, synchronous Python math. No network calls. No LLMs.
    wear = (data.flight_hours / 10000.0) * data.environment_factor * 100 
    
    return MathOutput(projected_wear=round(wear, 2))

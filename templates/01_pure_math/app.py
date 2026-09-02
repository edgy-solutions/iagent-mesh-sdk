from pydantic import Field
from iagent_mesh.models import ToolInput, ToolOutput
from iagent_mesh.core import MeshTool

# Notice: No DataPointer here. Engine DA just passes literal values.
class MathInput(ToolInput):
    flight_hours: float = Field(..., description="Total logged flight hours")
    environment_factor: float = Field(..., description="Multiplier for harsh environments")

class MathOutput(ToolOutput):
    projected_wear: float

# This tool is a typed predicate in the mesh's predicate graph (ADR-0004):
#
#     (mro:ComponentSnapshot) --[mro:projectComponentWear]--> (mro:WearProjection)
#
# ``verb``, ``input_uri``, ``output_uri`` are required. Pick concept URIs from
# the IOF MRO ontology (or your domain's equivalent); pick the verb from the
# same ontology if it exists, or mint a ``mesh:`` verb if it doesn't.
# See ADR-0005 for namespacing conventions and ADR-0007 for the survey rule
# before minting platform concepts.
app = MeshTool(
    name="REPLACE_ME_NAME",
    description="Projects component wear over flight-hour exposure.",
    verb="mro:projectComponentWear",          # rdf:Property in the MRO ontology
    input_uri="mro:ComponentSnapshot",         # rdfs:domain
    output_uri="mro:WearProjection",           # rdfs:range
    verb_synonyms=["project wear", "estimate wear", "compute wear limit"],
    owner_persona="MECHANIC",
    cost_class="fast",
)

# `caller_scoped=False` DECLARES that this tool does not scope work to the invoking user.
# That is correct here: it reads no data at all — Engine DA passes literal values — so there
# is nothing to entitle. Declaring it records the decision and silences the registration
# warning; omitting the declaration is what the warning is for.
@app.execute(caller_scoped=False)
def calculate_wear(data: MathInput) -> MathOutput:
    # Pure, synchronous Python math. No network calls. No LLMs.
    wear = (data.flight_hours / 10000.0) * data.environment_factor * 100 
    
    return MathOutput(projected_wear=round(wear, 2))

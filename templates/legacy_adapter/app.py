import os
import nest_asyncio
from iagent_mesh.core import MeshTool
from iagent_mesh.models import ToolInput, ToolOutput
from pydantic import Field
from typing import Literal

# Import legacy frameworks (Note: You may need to install specific providers like llama-index-llms-openai)
# from llama_index.core import VectorStoreIndex
# from langchain.agents import initialize_agent

# Apply global patch to allow nested loops
nest_asyncio.apply()

class EnterprisePolicyInput(ToolInput):
    clean_query: str = Field(
        ..., 
        description="Rewrite the user's messy prompt into a highly optimized search query for a Vector DB."
    )
    policy_domain: Literal["HR", "IT", "Finance"] = Field(
        ..., 
        description="Classify the domain of the question to route to the correct internal store."
    )
    requires_approval: bool = Field(
        False, 
        description="Set to True if the user is asking to modify a policy or execute a transaction."
    )

class PolicyOutput(ToolOutput):
    final_answer: str
    sources_cited: list[str]

# REPLACE_ME_NAME is automatically swapped by scaffold.sh
# Predicate edge — the platform's "query existing RAG over enterprise policy":
#     (mesh:PolicyQuery) --[mesh:queryEnterprisePolicy]--> (mesh:PolicyAnswer)
#
# The mesh: prefix marks this as a platform-internal verb (ADR-0005). This
# wrapper exists because the mesh exists -- legacy RAG pipelines don't have
# a natural place in a domain ontology. If a domain ontology grows a
# matching concept, you can re-register against it without breaking
# anything (the URI just changes).
app = MeshTool(
    name="REPLACE_ME_NAME",
    description="Adapter node wrapping a LlamaIndex / LangChain RAG pipeline.",
    verb="mesh:queryEnterprisePolicy",
    input_uri="mesh:PolicyQuery",
    output_uri="mesh:PolicyAnswer",
    verb_synonyms=["look up policy", "consult policy RAG", "ask the policy index"],
    owner_persona="TECH_WRITER",
    cost_class="medium",
)

@app.execute()
def legacy_framework_router(data: EnterprisePolicyInput) -> PolicyOutput:
    # --- YOUR EXISTING LLAMA-INDEX / LANGCHAIN CODE LIVES HERE ---
    
    # Example logic using the 'clean_query' and 'policy_domain' provided by the Mesh Orchestrator
    # if data.requires_approval:
    #     ... execute LangChain agent ...
    # else:
    #     ... query LlamaIndex using data.policy_domain ...
    
    return PolicyOutput(
        final_answer=f"Legacy logic executed for {data.policy_domain}. Query: {data.clean_query}",
        sources_cited=["adapter-template-v1"]
    )

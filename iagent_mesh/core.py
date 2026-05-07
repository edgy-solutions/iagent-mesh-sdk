import os
import inspect
import logging
import httpx
import nest_asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException

# Apply nest_asyncio globally to allow nested event loops (e.g. agents inside tools)
nest_asyncio.apply()
from iagent_mesh.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MeshTool")

class MeshTool:
    def __init__(self, name: str, description: str, is_mcp: bool = False, ontology_uris: list[str] = None):
        self.name = name
        self.description = description
        self.is_mcp = is_mcp
        self.ontology_uris = ontology_uris or [f"provisional:{name}"]
        self.urn = f"urn:li:mcpServer:{name}" if is_mcp else f"urn:li:aitool:{name}"
        self.app = FastAPI(title=self.urn, description=description, lifespan=self._lifespan)

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        logger.info(f"Registering {self.urn} to DataHub Mesh...")
        
        try:
            # 1. Automatically grab the exact JSON schema generated from the Pydantic models
            openapi_spec = app.openapi()
            
            # 2. Determine Entity Type from URN
            entity_type = "AITool"
            if self.urn.startswith("urn:li:mcpServer:"):
                entity_type = "MCPServer"
            elif self.urn.startswith("urn:li:aitool:"):
                entity_type = "AITool"

            # 3. Grab the live cluster URL (injected by your Kubernetes deployment)
            # Example fallback: http://tool-name.mesh-tools.svc.cluster.local:8000/execute
            live_endpoint = os.getenv("MESH_TOOL_ENDPOINT", f"http://localhost:8000/execute")

            # 4. Build the payload that actually empowers the LLM
            registration_payload = {
                "urn": self.urn,
                "type": entity_type,
                "description": self.description,
                "endpoint_url": live_endpoint,
                "openapi_schema": openapi_spec,
                "ontology_uris": self.ontology_uris
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.DATAHUB_URL}/entities",
                    json=registration_payload
                )
                response.raise_for_status()
                logger.info(f"✅ Successfully registered {self.urn} with full OpenAPI schema.")
                
        except httpx.RequestError as e:
            logger.warning(f"⚠️ Failed to register to DataHub Mesh: {e}")
            
        yield
        
        logger.info(f"Deregistering {self.urn} from Mesh...")
        # Optional: Add deregistration HTTP call here

    def execute(self):
        """Decorator that transforms pure Python math into a Mesh API."""
        def decorator(func):
            # Inspect the data scientist's function to get their Pydantic models
            sig = inspect.signature(func)
            input_param = list(sig.parameters.values())[0]
            InputModel = input_param.annotation

            @self.app.post("/execute")
            async def route_handler(request: Request):
                # 1. PLATFORM LOGIC: Enforce Topaz Zero-Trust invisibly
                auth_header = request.headers.get("Authorization")
                if not auth_header and not os.getenv("LOCAL_DEV"):
                    raise HTTPException(status_code=403, detail="Missing Topaz Ticket")

                # 2. Parse the incoming JSON into the Data Scientist's model
                body = await request.json()
                try:
                    input_data = InputModel(**body)
                except Exception as e:
                    raise HTTPException(status_code=422, detail=str(e))

                # 3. Run the Data Scientist's clean logic
                try:
                    if inspect.iscoroutinefunction(func):
                        return await func(input_data)
                    return func(input_data)
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    raise HTTPException(status_code=500, detail="Internal Tool Error")
            
            return route_handler
        return decorator

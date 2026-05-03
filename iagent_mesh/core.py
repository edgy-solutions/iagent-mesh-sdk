import os
import inspect
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MeshTool")

class MeshTool:
    def __init__(self, urn: str, description: str):
        self.urn = urn
        self.description = description
        self.app = FastAPI(title=urn, description=description, lifespan=self._lifespan)

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        # PLATFORM LOGIC: This runs when the S2I container boots.
        # Here is where you POST the OpenAPI schema to DataHub.
        logger.info(f"Registering {self.urn} to DataHub Mesh...")
        # httpx.post("http://datahub:8080", json={"urn": self.urn})
        yield
        logger.info(f"Deregistering {self.urn} from Mesh...")

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

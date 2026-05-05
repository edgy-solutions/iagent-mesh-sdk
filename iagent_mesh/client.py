import os
import httpx

class MeshClient:
    def __init__(self, gateway_url: str = "http://gateway.sustainment.svc:8080/execute"):
        self.gateway_url = gateway_url
        self.token = os.getenv("MESH_DEV_TOKEN")
        
        if not self.token:
            raise RuntimeError("MESH_DEV_TOKEN not found. Ensure you are running within the secured JupyterHub environment.")

    def ask(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "prompt": prompt
        }
        
        with httpx.Client() as client:
            response = client.post(
                self.gateway_url,
                headers=headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            
            # Try to return the JSON response or fallback to plain text
            try:
                return response.json()
            except ValueError:
                return response.text

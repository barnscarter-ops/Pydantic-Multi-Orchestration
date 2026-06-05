import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import os
import json

from schemas.gateway import GatewayRequest, GatewayResponse, FileSaveRequest
from core.router import ModelRouter

# Load environment variables
load_dotenv(".env")

app = FastAPI(title="PACC Model Gateway", description="Local-first AI Orchestration Layer")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Core Components
# The Gateway now points to the Registry (Brain) on the Proxmox Server
REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://<PROXMOX_IP>:8001")
router = ModelRouter(registry_url=REGISTRY_URL, env_vars=os.environ)

@app.get("/health")
async def health_check():
    """Health check endpoint for the Brain to monitor the Muscle."""
    return {"status": "online", "muscle": "active"}

@app.post("/generate")
async def generate(request: GatewayRequest):
    """
    Unified generation endpoint.
    Now implements the Handshake Protocol:
    Request -> Registry (Fetch Manifest) -> Execution
    Supports streaming if request.stream is True.
    """
    if request.stream:
        async def event_generator():
            async for chunk in router.route_stream(request):
                yield json.dumps(chunk) + "\n"
        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    try:
        response = await router.route(request)
        if response.error:
            # We still return the response object so the client knows WHY it failed
            return response
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/file")
async def read_file(path: str):
    """Reads a local file and returns its content."""
    if not path:
        raise HTTPException(status_code=400, detail="Path parameter is required")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

@app.post("/file")
async def write_file(request: FileSaveRequest):
    """Writes content to a local file path."""
    try:
        directory = os.path.dirname(request.path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        with open(request.path, "w", encoding="utf-8") as f:
            f.write(request.content)
        return {"status": "success", "path": request.path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

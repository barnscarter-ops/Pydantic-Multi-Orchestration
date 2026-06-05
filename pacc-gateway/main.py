import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from dotenv import load_dotenv
import os
import json
import subprocess
import sys

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
    """Reads a local file and returns its content or lists directory contents."""
    if not path:
        raise HTTPException(status_code=400, detail="Path parameter is required")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        if os.path.isdir(path):
            files = []
            for item in os.listdir(path):
                full_item = os.path.join(path, item)
                files.append({
                    "name": item,
                    "is_dir": os.path.isdir(full_item),
                    "path": os.path.abspath(full_item)
                })
            # Sort directories first, then files alphabetically
            files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return {"path": os.path.abspath(path), "is_directory": True, "files": files}

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": os.path.abspath(path), "is_directory": False, "content": content}
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

@app.get("/preview", response_class=HTMLResponse)
async def preview_file(path: str):
    """Renders a local HTML landing page file in the browser preview iframe."""
    if not path:
        raise HTTPException(status_code=400, detail="Path parameter is required")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read preview file: {str(e)}")

@app.post("/dialog/open-file")
def open_file_dialog():
    """Triggers a native Windows file open dialog in a safe separate subprocess."""
    try:
        py_cmd = (
            "import tkinter as tk; "
            "from tkinter import filedialog; "
            "root = tk.Tk(); "
            "root.withdraw(); "
            "root.attributes('-topmost', True); "
            "path = filedialog.askopenfilename(title='Select Workspace File'); "
            "print(path); "
            "root.destroy()"
        )
        output = subprocess.check_output([sys.executable, "-c", py_cmd], text=True, encoding="utf-8")
        file_path = output.strip()
        if not file_path:
            return {"status": "cancelled", "path": ""}
        return {"status": "success", "path": os.path.abspath(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file dialog: {str(e)}")

@app.post("/dialog/open-folder")
def open_folder_dialog():
    """Triggers a native Windows folder open dialog in a safe separate subprocess."""
    try:
        py_cmd = (
            "import tkinter as tk; "
            "from tkinter import filedialog; "
            "root = tk.Tk(); "
            "root.withdraw(); "
            "root.attributes('-topmost', True); "
            "path = filedialog.askdirectory(title='Select Workspace Folder'); "
            "print(path); "
            "root.destroy()"
        )
        output = subprocess.check_output([sys.executable, "-c", py_cmd], text=True, encoding="utf-8")
        folder_path = output.strip()
        if not folder_path:
            return {"status": "cancelled", "path": ""}
        return {"status": "success", "path": os.path.abspath(folder_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder dialog: {str(e)}")

@app.get("/browser-screenshot")
def get_browser_screenshot():
    """Serves the latest browser subagent screenshot from multiple possible locations."""
    paths = [
        r"C:\Users\carte\.gemini\antigravity-ide\brain\a8a85000-f802-4cda-8330-bbd4c3ffd1f7\browser_screenshot.png",
        r"C:\Users\carte\.gemini\antigravity-ide\brain\a8a85000-f802-4cda-8330-bbd4c3ffd1f7\browser_view.png",
        r"C:\Users\carte\.gemini\antigravity-ide\brain\a8a85000-f802-4cda-8330-bbd4c3ffd1f7\screenshot_ui.png",
        r"C:\Users\carte\pacc-gateway\browser_screenshot.png",
        r"C:\Users\carte\pacc-gateway\browser_view.png",
        r"C:\Users\carte\pacc-gateway\mav-console\public\browser_screenshot.png"
    ]
    for path in paths:
        if os.path.exists(path):
            return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="No screenshot available")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

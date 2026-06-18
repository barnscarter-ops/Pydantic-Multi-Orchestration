"""
FastAPI server for the multi-agent dashboard.

Endpoints:
  POST /api/run         — submit a task (multipart: text + optional image)
  GET  /api/tokens      — current token usage per agent
  WS   /ws/logs         — real-time event stream (JSON-encoded Event objects)
  GET  /                — serves the React frontend
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from orchestrator import Event, Orchestrator, RunResult


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

orchestrator = Orchestrator(max_rounds=3)

# Active WebSocket connections for log streaming
_ws_clients: set[WebSocket] = set()
# Queue for broadcasting events to all WS clients
_broadcast_queue: asyncio.Queue = asyncio.Queue()


async def _broadcaster() -> None:
    """Background task: fan-out events from the orchestrator bus to all WS clients."""
    q = orchestrator.bus.subscribe()
    try:
        while True:
            event: Event = await q.get()
            payload = json.dumps({
                "timestamp": event.timestamp,
                "agent": event.agent,
                "type": event.event_type,
                "data": event.data if isinstance(event.data, (dict, list, str, int, float, bool, type(None))) else str(event.data),
            })
            dead: set[WebSocket] = set()
            for ws in list(_ws_clients):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            _ws_clients.difference_update(dead)
    finally:
        orchestrator.bus.unsubscribe(q)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_broadcaster())
    yield
    task.cancel()


app = FastAPI(title="Multi-Agent Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/run")
async def run_task(
    task: str = Form(...),
    image: UploadFile | None = File(None),
) -> JSONResponse:
    """Submit a task to the multi-agent system. Returns a job ID immediately."""
    job_id = str(uuid.uuid4())[:8]

    image_bytes: bytes | None = None
    image_media_type = "image/png"
    if image and image.filename:
        image_bytes = await image.read()
        image_media_type = image.content_type or "image/png"

    async def _run() -> None:
        orchestrator.reset_agents()
        result: RunResult = await orchestrator.run(task, image_bytes, image_media_type)
        # Final summary broadcast
        summary = {
            "job_id": job_id,
            "rounds": result.rounds,
            "passed": result.passed,
            "duration_seconds": result.duration_seconds,
            "token_totals": result.token_totals,
        }
        payload = json.dumps({
            "timestamp": 0,
            "agent": "system",
            "type": "summary",
            "data": summary,
        })
        for ws in list(_ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                pass

    asyncio.create_task(_run())

    return JSONResponse({"job_id": job_id, "status": "running"})


@app.get("/api/tokens")
async def get_tokens() -> JSONResponse:
    return JSONResponse(orchestrator.token_counts())


# ---------------------------------------------------------------------------
# WebSocket log stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        # Keep connection alive; events are pushed from _broadcaster
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
async def index():
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return JSONResponse({"message": "Frontend not built. Run: cd frontend && npm run build"})


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)

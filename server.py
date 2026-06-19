"""
FastAPI server — multi-agent dashboard backend.

Routes:
  POST /api/run                    submit a task (multipart: task + optional image)
  GET  /api/jobs                   list recent jobs
  GET  /api/jobs/{job_id}          job status + result
  POST /api/jobs/{job_id}/cancel   cancel a running job
  GET  /api/tokens                 token usage from the most recent run
  GET  /api/health                 server health check
  WS   /ws/logs                    real-time event stream (newline-delimited JSON)
"""

from __future__ import annotations

# Logfire instrumentation — must come before pydantic-ai agent runs
try:
    import logfire
    logfire.configure(send_to_logfire="if-token-present")
    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx(capture_all=False)
except Exception:
    pass  # logfire is optional; continues without telemetry if not authenticated

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from orchestrator import Event, Orchestrator


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

orchestrator = Orchestrator()
_ws_clients: set[WebSocket] = set()


def _serialize_event(event: Event) -> str:
    data = event.data
    if not isinstance(data, (dict, list, str, int, float, bool, type(None))):
        data = str(data)
    return json.dumps({
        "timestamp": event.timestamp,
        "agent": event.agent,
        "type": event.event_type,
        "data": data,
    })


async def _broadcaster() -> None:
    """Fan-out events from the orchestrator bus to all WebSocket clients."""
    q: asyncio.Queue = asyncio.Queue()
    orchestrator.bus.subscribe(q)
    try:
        while True:
            event: Event = await q.get()
            payload = _serialize_event(event)
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
    # Give the bus a reference to the running loop so worker-thread emits are safe.
    orchestrator.bus.set_loop(asyncio.get_running_loop())
    task = asyncio.create_task(_broadcaster())
    yield
    task.cancel()


app = FastAPI(title="Multi-Agent Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "busy": orchestrator.is_busy(),
        "ws_clients": len(_ws_clients),
        "job_count": len(orchestrator.list_jobs()),
    })


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------

@app.post("/api/run", status_code=202)
async def run_task(
    task: str = Form(...),
    image: UploadFile | None = File(None),
) -> JSONResponse:
    if not task.strip():
        raise HTTPException(400, "task must not be empty")

    image_bytes: bytes | None = None
    image_media_type = "image/png"
    if image and image.filename:
        image_bytes = await image.read()
        image_media_type = image.content_type or "image/png"

    job = await orchestrator.submit(task.strip(), image_bytes, image_media_type)
    return JSONResponse({"job_id": job.id, "status": job.status.value})


# ---------------------------------------------------------------------------
# Job inspection & control
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
async def list_jobs() -> JSONResponse:
    return JSONResponse(orchestrator.list_jobs())


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return JSONResponse(job.to_dict())


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JSONResponse:
    if not orchestrator.cancel_job(job_id):
        raise HTTPException(404, f"Job '{job_id}' not found")
    return JSONResponse({"job_id": job_id, "cancelled": True})


# ---------------------------------------------------------------------------
# Token summary
# ---------------------------------------------------------------------------

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
        while True:
            # Keep-alive ping; client messages are ignored
            await asyncio.sleep(25)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# WebSocket terminal — virtual shell (command-at-a-time, no PTY needed)
# ---------------------------------------------------------------------------

@app.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket) -> None:
    await websocket.accept()

    cwd = str(Path(__file__).parent)
    history: list[str] = []
    hist_idx = -1

    async def send(text: str) -> None:
        try:
            await websocket.send_text(text)
        except Exception:
            pass

    async def show_prompt() -> None:
        await send(f"\r\n\x1b[32m{cwd}\x1b[0m\x1b[90m $\x1b[0m ")

    await send("\x1b[1;34mOrchestrator Shell\x1b[0m  \x1b[90m(Windows CMD)\x1b[0m\r\n")
    await show_prompt()

    line = ""
    try:
        while True:
            data = await websocket.receive_text()

            if data == "\r":  # Enter
                await send("\r\n")
                command = line.strip()
                line = ""
                hist_idx = -1

                if command:
                    history.append(command)

                    if command.lower() in ("exit", "quit"):
                        await send("Goodbye.\r\n")
                        break

                    elif command.lower() in ("cls", "clear"):
                        await send("\x1b[2J\x1b[H")

                    elif command.lower() == "cd" or command.lower().startswith("cd ") or command.lower().startswith("cd\t"):
                        parts = command.split(None, 1)
                        if len(parts) == 1:
                            await send(f"{cwd}\r\n")
                        else:
                            target = parts[1].strip().strip('"').strip("'")
                            candidate = Path(target) if Path(target).is_absolute() else Path(cwd) / target
                            try:
                                candidate = candidate.resolve(strict=True)
                                if candidate.is_dir():
                                    cwd = str(candidate)
                                else:
                                    await send(f"Not a directory: {target}\r\n")
                            except FileNotFoundError:
                                await send(f"The system cannot find the path specified.\r\n")

                    else:
                        try:
                            proc = await asyncio.create_subprocess_shell(
                                command,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.STDOUT,
                                cwd=cwd,
                            )
                            try:
                                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60.0)
                            except asyncio.TimeoutError:
                                try:
                                    proc.terminate()
                                except Exception:
                                    pass
                                stdout = b"[command timed out after 60 s]\n"
                            if stdout:
                                out = stdout.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\n", "\r\n")
                                await send(out)
                        except Exception as exc:
                            await send(f"Error: {exc}\r\n")

                await show_prompt()

            elif data in ("\x7f", "\x08"):  # Backspace / DEL
                if line:
                    line = line[:-1]
                    await send("\x08 \x08")

            elif data == "\x03":  # Ctrl+C
                line = ""
                hist_idx = -1
                await send("^C")
                await show_prompt()

            elif data == "\x1b[A":  # Up arrow — history back
                if history:
                    hist_idx = min(hist_idx + 1, len(history) - 1)
                    new_line = history[-(hist_idx + 1)]
                    await send("\x08 \x08" * len(line))
                    await send(new_line)
                    line = new_line

            elif data == "\x1b[B":  # Down arrow — history forward
                if hist_idx > 0:
                    hist_idx -= 1
                    new_line = history[-(hist_idx + 1)]
                    await send("\x08 \x08" * len(line))
                    await send(new_line)
                    line = new_line
                elif hist_idx == 0:
                    hist_idx = -1
                    await send("\x08 \x08" * len(line))
                    line = ""

            elif data.startswith("\x1b"):
                pass  # ignore other escape sequences

            else:
                line += data
                await send(data)  # echo back

    except (WebSocketDisconnect, Exception):
        pass


# ---------------------------------------------------------------------------
# API index
# ---------------------------------------------------------------------------

@app.get("/api")
async def api_index() -> JSONResponse:
    return JSONResponse({
        "routes": [
            "POST /api/run",
            "GET  /api/jobs",
            "GET  /api/jobs/{job_id}",
            "POST /api/jobs/{job_id}/cancel",
            "GET  /api/tokens",
            "GET  /api/health",
            "WS   /ws/logs",
        ]
    })


# ---------------------------------------------------------------------------
# Frontend (optional — only mounted if built)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
async def index() -> Any:
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return JSONResponse({
        "message": "Backend is running. Frontend not built yet.",
        "hint": "cd frontend && npm install && npm run build",
        "api": "/api",
    })


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)

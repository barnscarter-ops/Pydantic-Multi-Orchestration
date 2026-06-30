"""
Slack bot — bridges homelab agent DMs to the orchestrator's /api/chat endpoint.

Connects via Socket Mode (no public URL needed).
On each DM: opens a WebSocket to /ws/logs, posts to /api/chat, collects the
Sonnet response, replies when system/chat_response fires.

PM2: homelab-slack-bot (see ecosystem.config.cjs)
Env: SLACK_BOT_TOKEN (xoxb-...), SLACK_APP_TOKEN (xapp-...)
     HOMELAB_API (default http://localhost:8000)
"""
import asyncio
import json
import logging
import os

import httpx
import websockets
from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
API_BASE  = os.getenv("HOMELAB_API", "http://localhost:8000")
WS_URL    = API_BASE.replace("http://", "ws://").replace("https://", "wss://") + "/ws/logs"
TIMEOUT   = 60  # seconds before giving up


async def ask_orchestrator(message: str) -> str:
    """POST to /api/chat, subscribe to /ws/logs, collect Sonnet response."""
    # Connect before posting so we never miss events.
    async with websockets.connect(WS_URL) as ws:
        async with httpx.AsyncClient() as client:
            await client.post(f"{API_BASE}/api/chat", json={"message": message}, timeout=10)

        full_text = ""
        deadline = asyncio.get_event_loop().time() + TIMEOUT

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                log.warning("Timed out waiting for chat_response")
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                log.error("WS error: %s", exc)
                break

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            agent = event.get("agent", "")
            etype = event.get("type", "")
            data  = event.get("data") or {}

            if agent == "sonnet" and etype == "stream" and isinstance(data, dict):
                full_text += data.get("delta", "")
            elif agent == "sonnet" and etype == "message" and isinstance(data, dict):
                # Full message text supersedes accumulated stream deltas.
                full_text = data.get("text", full_text)
            elif agent == "system" and etype == "chat_response":
                break

    return full_text.strip() or "_(no response)_"


app = AsyncApp(token=BOT_TOKEN)


@app.event("message")
async def handle_dm(event, say):
    # Only handle direct messages; skip bot messages and subtypes (edits, deletions).
    if event.get("channel_type") != "im":
        return
    if event.get("bot_id") or event.get("subtype"):
        return

    text = (event.get("text") or "").strip()
    if not text:
        return

    log.info("DM from %s: %s", event.get("user"), text[:80])
    try:
        reply = await ask_orchestrator(text)
    except Exception as exc:
        log.exception("Orchestrator error")
        reply = f"Sorry, something went wrong: {exc}"

    await say(reply)


async def main() -> None:
    handler = AsyncSocketModeHandler(app, APP_TOKEN)
    log.info("HomeLab Slack bot starting (Socket Mode)…")
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())

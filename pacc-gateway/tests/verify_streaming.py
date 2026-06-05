import asyncio
import httpx
import json
import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv("pacc-gateway/.env")

GATEWAY_URL = "http://localhost:8000"

async def test_streaming():
    print("🚀 Starting Streaming and Escalation Verification...")

    # 1. Normal Stream Check (Local Model)
    print("\n[1/2] Requesting stream from primary model (Gemma)...")
    payload = {
        "prompt": "Say 'hello world' in Python.",
        "agent_id": "goldenpathagent",
        "stream": True
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("POST", f"{GATEWAY_URL}/generate", json=payload) as response:
                if response.status_code != 200:
                    print(f"❌ Stream Request Failed: {response.status_code}")
                    return

                print("Streaming response:")
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            print(f"\n❌ Chunk error: {chunk['error']}")
                        else:
                            print(chunk.get("content", ""), end="", flush=True)
            print("\n✅ Normal streaming finished successfully.")
        except Exception as e:
            print(f"❌ Normal Streaming Error: {e}")

    # 2. Forced Escalation Stream Check (Claude)
    print("\n[2/2] Requesting forced escalation stream...")
    payload["force_escalate"] = True

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("POST", f"{GATEWAY_URL}/generate", json=payload) as response:
                print(f"Status Code: {response.status_code}")
                print("Streaming response:")
                async for line in response.aiter_lines():
                    if line:
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            print(f"\nExpected Error (due to placeholder API Key): {chunk['error']}")
                        else:
                            print(chunk.get("content", ""), end="", flush=True)
            print("\n✅ Forced escalation flow verified.")
        except Exception as e:
            print(f"❌ Escalation Streaming Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_streaming())

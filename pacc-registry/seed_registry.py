import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://192.168.1.12:8001")

async def seed_skills():
    print("Seeding Skills...")
    skills = [
        {
            "skill_id": "web_search",
            "description": "Performs a real-time web search to retrieve current information.",
            "exec_command": "pacc-web-search",
            "args_schema": {"query": "string"}
        },
        {
            "skill_id": "desktop_commander",
            "description": "Executes system-level commands and interacts with the local OS.",
            "exec_command": "pacc-desktop-cmd",
            "args_schema": {"command": "string", "timeout": "int"}
        },
        {
            "skill_id": "file_manager",
            "description": "Reads, writes, and organizes files on the local filesystem.",
            "exec_command": "pacc-file-mgr",
            "args_schema": {"action": "string", "path": "string", "content": "string"}
        },
        {
            "skill_id": "terminal_executor",
            "description": "Runs shell commands and captures output for analysis.",
            "exec_command": "pacc-term-exec",
            "args_schema": {"cmd": "string"}
        },
        {
            "skill_id": "system_monitor",
            "description": "Monitors CPU, GPU, and RAM usage on the Muscle machine.",
            "exec_command": "pacc-sys-mon",
            "args_schema": {}
        }
    ]

    async with httpx.AsyncClient() as client:
        for skill in skills:
            resp = await client.post(f"{REGISTRY_URL}/skills", json=skill)
            if resp.status_code == 200:
                print(f"Skill {skill['skill_id']} seeded.")
            else:
                print(f"Failed to seed {skill['skill_id']}: {resp.text}")

async def seed_agents():
    print("\nSeeding Agents...")
    agents = [
        {
            "name": "Golden Path Agent",
            "system_prompt": "You are a verification agent ensuring system integrity.",
            "primary_model": "Gemma4-MaxCoder:latest",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["web_search", "desktop_commander"],
            "params": {"temperature": 0.7, "max_tokens": 1024}
        },
        {
            "name": "MAV-RESEARCH",
            "system_prompt": "You are a deep-research agent specializing in synthesis.",
            "primary_model": "Gemma4-MaxCoder:latest",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["web_search", "desktop_commander", "system_monitor"],
            "params": {"temperature": 0.4, "max_tokens": 4096}
        },
        {
            "name": "MAV-CODER",
            "system_prompt": "You are an elite software engineer specializing in Python and React.",
            "primary_model": "qwen2.5-coder:14b",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["desktop_commander", "web_search", "file_manager", "terminal_executor", "system_monitor"],
            "params": {"temperature": 0.2, "max_tokens": 2048}
        },
        {
            "name": "MAV-CODER-12B",
            "system_prompt": "You are a high-performance coding agent optimized for speed and accuracy.",
            "primary_model": "Gemma4-MaxCoder-12b:latest",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["desktop_commander", "web_search", "file_manager", "terminal_executor", "system_monitor"],
            "params": {"temperature": 0.5, "max_tokens": 128000}
        },
        {
            "name": "GEMMA4-12B",
            "system_prompt": "You are a general purpose AI assistant powered by Gemma 4.",
            "primary_model": "gemma4:12b",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["desktop_commander", "web_search", "file_manager", "terminal_executor", "system_monitor"],
            "params": {"temperature": 0.7, "max_tokens": 8192}
        }
    ]

    async with httpx.AsyncClient() as client:
        for agent in agents:
            resp = await client.post(f"{REGISTRY_URL}/agents", json=agent)
            if resp.status_code == 200:
                print(f"Agent {agent['name']} seeded.")
            else:
                print(f"Failed to seed {agent['name']}: {resp.text}")

async def main():
    print(f"Connecting to Registry at {REGISTRY_URL}...")
    await seed_skills()
    await seed_agents()
    print("\nRegistry seeding complete!")

if __name__ == "__main__":
    asyncio.run(main())

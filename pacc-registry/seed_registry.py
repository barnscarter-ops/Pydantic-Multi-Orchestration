import urllib.request
import json

REGISTRY_URL = "http://192.168.1.12:8001"

def post_json(path, data):
    url = f"{REGISTRY_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error posting to {url}: {e}")
        return None

def main():
    print("Seeding skills...")
    skills = [
        {
            "skill_id": "fs_read",
            "description": "Read and view files in the local workspace.",
            "exec_command": "cat {file_path}",
            "args_schema": {"file_path": "string"}
        },
        {
            "skill_id": "git_commit",
            "description": "Commit staged changes with a git message.",
            "exec_command": "git commit -m '{message}'",
            "args_schema": {"message": "string"}
        },
        {
            "skill_id": "npm_run",
            "description": "Execute node development scripts or tests.",
            "exec_command": "npm run {script_name}",
            "args_schema": {"script_name": "string"}
        },
        {
            "skill_id": "web_search",
            "description": "Search the web for information using a search engine.",
            "exec_command": "curl 'https://api.search.com?q={query}'",
            "args_schema": {"query": "string"}
        }
    ]

    for skill in skills:
        res = post_json("/skills", skill)
        if res:
            print(f"Registered skill: {skill['skill_id']}")

    print("\nSeeding agents...")
    agents = [
        {
            "name": "MAV-CODER",
            "system_prompt": "You are MAV-CODER, an expert programming assistant designed for Maverick Integrations. Work in a tactical, precise, and efficient manner.",
            "primary_model": "qwen2.5-coder:14b",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["fs_read", "git_commit", "npm_run"],
            "params": {
                "temperature": 0.3,
                "max_tokens": 2048,
                "context_window": 8192
            }
        },
        {
            "name": "MAV-RESEARCH",
            "system_prompt": "You are MAV-RESEARCH, an expert research assistant designed for Maverick Integrations. Search, verify, and validate all facts and resources.",
            "primary_model": "Gemma4-MaxCoder:latest",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["fs_read", "web_search"],
            "params": {
                "temperature": 0.5,
                "max_tokens": 1024,
                "context_window": 4096
            }
        },
        {
            "name": "MAV-OPS",
            "system_prompt": "You are MAV-OPS, an operations control assistant designed for Maverick Integrations. Monitor system status, orchestrate services, and execute commands.",
            "primary_model": "qwen2.5-coder:14b",
            "fallback_model": "claude-3-5-sonnet",
            "skill_ids": ["fs_read", "npm_run", "git_commit"],
            "params": {
                "temperature": 0.2,
                "max_tokens": 1024,
                "context_window": 4096
            }
        }
    ]

    for agent in agents:
        res = post_json("/agents", agent)
        if res:
            print(f"Registered agent: {agent['name']}")

if __name__ == "__main__":
    main()

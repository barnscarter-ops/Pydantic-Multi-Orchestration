"""
Three peer-to-peer agents backed by claude-opus-4-8.
Images are embedded in the thread by the orchestrator — Agent.respond() does
not need to handle them directly. Tool-use loops are handled internally.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import anthropic


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        # Opus 4.8 pricing ($/1M tokens)
        regular_input = max(0, self.input_tokens - self.cache_read_input_tokens)
        return (
            regular_input * 5.00 / 1_000_000
            + self.cache_read_input_tokens * 0.50 / 1_000_000
            + self.cache_creation_input_tokens * 6.25 / 1_000_000
            + self.output_tokens * 25.00 / 1_000_000
        )

    def add(self, usage: anthropic.types.Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


# ---------------------------------------------------------------------------
# P2P mention detection
# ---------------------------------------------------------------------------

_MENTION_RE = re.compile(r"@(PlanningAgent|ImplementationAgent|ReviewAgent)\b")


def parse_mentions(text: str) -> list[str]:
    """Return unique @AgentName mentions in the order they appear."""
    seen: set[str] = set()
    result: list[str] = []
    for m in _MENTION_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from disk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory (and any missing parents).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Execute a shell command and return stdout/stderr. "
            "Use for compiling, running tests, installing packages, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "description": "Working directory (optional)"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "git_op",
        "description": (
            "Run a git operation: status, diff, add, commit, log, branch, "
            "checkout, pull, push, stash, show, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Git subcommand + args, e.g. 'log --oneline -10'",
                },
                "cwd": {"type": "string", "description": "Repo path (optional)"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo. Returns titles, URLs, and snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {
                    "type": "integer",
                    "description": "Number of results (default 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a URL via HTTP GET and return its text content (HTML stripped).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {
                    "type": "integer",
                    "description": "Max characters to return (default 8000)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "http_request",
        "description": "Make an HTTP request with configurable method, headers, and body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                },
                "url": {"type": "string"},
                "headers": {
                    "type": "object",
                    "description": "Request headers as key-value pairs",
                },
                "body": {
                    "type": "string",
                    "description": "Request body; JSON string for JSON APIs",
                },
            },
            "required": ["method", "url"],
        },
    },
]


def execute_tool(name: str, inp: dict) -> str:
    try:
        if name == "read_file":
            return Path(inp["path"]).read_text(encoding="utf-8", errors="replace")[:50_000]

        elif name == "write_file":
            p = Path(inp["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(inp["content"], encoding="utf-8")
            return f"Wrote {len(inp['content'])} bytes to {inp['path']}"

        elif name == "create_directory":
            Path(inp["path"]).mkdir(parents=True, exist_ok=True)
            return f"Created: {inp['path']}"

        elif name == "list_directory":
            entries = sorted(Path(inp["path"]).iterdir(), key=lambda e: (e.is_file(), e.name))
            return "\n".join(("DIR  " if e.is_dir() else "FILE ") + e.name for e in entries)

        elif name == "run_command":
            result = subprocess.run(
                inp["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=int(inp.get("timeout", 60)),
                cwd=inp.get("cwd"),
            )
            out = (result.stdout or "")[-12_000:]
            err = (result.stderr or "")[-2_000:]
            return f"EXIT {result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}"

        elif name == "git_op":
            result = subprocess.run(
                f"git {inp['operation']}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=inp.get("cwd"),
            )
            return f"EXIT {result.returncode}\n{(result.stdout or '')[-10_000:]}{(result.stderr or '')[-2_000:]}"

        elif name == "web_search":
            return _web_search(inp["query"], int(inp.get("max_results", 5)))

        elif name == "fetch_url":
            return _fetch_url(inp["url"], int(inp.get("max_chars", 8_000)))

        elif name == "http_request":
            return _http_request(
                inp["method"], inp["url"],
                inp.get("headers"), inp.get("body"),
            )

        else:
            return f"Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as exc:
        return f"Tool error ({name}): {type(exc).__name__}: {exc}"


# -- Network helpers ---------------------------------------------------------

def _web_search(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS  # type: ignore
        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return "No results found."
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', '')}")
            lines.append(f"   {r.get('href', '')}")
            lines.append(f"   {r.get('body', '')[:300]}")
            lines.append("")
        return "\n".join(lines)
    except ImportError:
        return _ddg_instant(query)
    except Exception as exc:
        return f"Search error: {exc}"


def _ddg_instant(query: str) -> str:
    import urllib.parse
    import urllib.request
    enc = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={enc}&format=json&no_html=1&skip_disambig=1"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        lines: list[str] = []
        if data.get("AbstractText"):
            lines.append(f"Abstract: {data['AbstractText']}")
            if data.get("AbstractURL"):
                lines.append(f"Source: {data['AbstractURL']}")
        for t in data.get("RelatedTopics", [])[:5]:
            if isinstance(t, dict) and "Text" in t:
                lines.append(f"- {t['Text'][:200]}")
        return (
            "\n".join(lines)
            if lines
            else "No results. Install duckduckgo-search for full results."
        )
    except Exception as exc:
        return f"DDG error: {exc}"


def _strip_html(html: str) -> str:
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_url(url: str, max_chars: int = 8_000) -> str:
    try:
        import requests as req
        resp = req.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MultiAgentBot/1.0)"},
            allow_redirects=True,
        )
        ct = resp.headers.get("content-type", "")
        text = _strip_html(resp.text) if "html" in ct else resp.text
        return text[:max_chars]
    except Exception as exc:
        return f"Fetch error: {exc}"


def _http_request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: str | None = None,
) -> str:
    try:
        import requests as req
        kwargs: dict[str, Any] = {"headers": headers or {}, "timeout": 30}
        if body:
            try:
                kwargs["json"] = json.loads(body)
                kwargs["headers"].setdefault("Content-Type", "application/json")
            except json.JSONDecodeError:
                kwargs["data"] = body
        resp = req.request(method.upper(), url, **kwargs)
        return f"Status: {resp.status_code}\nBody:\n{resp.text[:5_000]}"
    except Exception as exc:
        return f"HTTP error: {exc}"


# ---------------------------------------------------------------------------
# Stable system prefix — cached at the API level for all agents
# ---------------------------------------------------------------------------

STABLE_SHARED_PREFIX = """\
You are part of a three-agent peer-to-peer collaborative system for software \
engineering tasks (code, infrastructure, DevOps).

AGENTS
  PlanningAgent        — decomposes tasks, creates detailed step-by-step plans
  ImplementationAgent  — writes code, edits files, runs commands via tools
  ReviewAgent          — audits outputs against the plan, approves or requests fixes

PEER-TO-PEER PROTOCOL
- The shared thread shows the full conversation. Other agents' turns are prefixed [AgentName].
- Mention @AgentName when you need a direct response from that agent mid-turn.
  Example: "@ImplementationAgent — can you check if /src/config.py already exists?"
- Mentions cause the mentioned agent to respond immediately before the main flow continues.
- Only mention another agent when genuinely necessary. Do not mention yourself.
- Limit to one @mention per response unless multiple agents are needed simultaneously.

TOOL USE
- Prefer tools over assumptions. Read files before writing them.
- Report exit codes and relevant output after running commands.
- For research: web_search first, then fetch_url on specific pages.

OUTPUT STYLE
- Be concise. Do not repeat what other agents have already stated.
- End every response with a clear CONCLUSION or NEXT STEP line.
- Use markdown code blocks for code, backticks for file paths.
"""


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class Agent:
    name: str = "Agent"
    role_prompt: str = ""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.usage = TokenUsage()
        self.on_event: Callable[[str, str, Any], None] | None = None

    def _emit(self, event_type: str, data: Any) -> None:
        if self.on_event:
            self.on_event(self.name, event_type, data)

    def _system(self) -> list[dict]:
        return [
            {
                "type": "text",
                "text": STABLE_SHARED_PREFIX,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": self.role_prompt},
        ]

    def _tools(self) -> list[dict]:
        tools = [dict(t) for t in TOOLS]
        # cache_control on the last tool caches the entire tools array
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        return tools

    def respond(
        self,
        messages: list[dict],
        cancel: threading.Event | None = None,
    ) -> str:
        """
        Run one agent turn given the shared message thread.
        Handles the tool-use loop internally. Returns the final text response.
        The thread must end with role="user" (guaranteed by the orchestrator).
        """
        local_messages = list(messages)
        self._emit("start", {"message_count": len(local_messages)})

        while True:
            if cancel and cancel.is_set():
                return "[Cancelled]"

            with self.client.messages.stream(
                model="claude-opus-4-8",
                max_tokens=16384,
                thinking={"type": "adaptive"},
                system=self._system(),
                tools=self._tools(),
                messages=local_messages,
            ) as stream:
                message = stream.get_final_message()

            self.usage.add(message.usage)
            self._emit("usage", self.usage.to_dict())

            if message.stop_reason == "tool_use":
                tool_results: list[dict] = []
                for block in message.content:
                    if block.type != "tool_use":
                        continue
                    if cancel and cancel.is_set():
                        return "[Cancelled]"
                    self._emit("tool_call", {"tool": block.name, "input": block.input})
                    result = execute_tool(block.name, block.input)
                    self._emit("tool_result", {"tool": block.name, "result": result[:500]})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                # Append full assistant content (includes thinking blocks) then tool results.
                # This keeps thinking blocks in context for continuity within one agent's turn.
                local_messages.append({"role": "assistant", "content": message.content})
                local_messages.append({"role": "user", "content": tool_results})
                continue

            # Extract only text blocks for the final response
            text_parts = [b.text for b in message.content if b.type == "text"]
            response_text = "\n".join(text_parts).strip() or "[No text response]"
            self._emit("response", {"text": response_text[:300]})
            return response_text

    def count_tokens(self, messages: list[dict]) -> int:
        result = self.client.messages.count_tokens(
            model="claude-opus-4-8",
            system=self._system(),
            tools=self._tools(),
            messages=messages,
        )
        return result.input_tokens


# ---------------------------------------------------------------------------
# Specialized agents
# ---------------------------------------------------------------------------

class PlanningAgent(Agent):
    name = "PlanningAgent"
    role_prompt = """\
YOUR ROLE: PlanningAgent
You decompose tasks into concrete, ordered execution plans.

Required output format:
  ## Goal
  One sentence describing the desired outcome.

  ## Plan
  Numbered steps. For each step include:
    - What to do (specific actions, file paths, commands)
    - Which agent executes it
    - Dependencies on prior steps

  ## Success Criteria
  A checklist ReviewAgent will use to verify completion.

  ## Open Questions (if any)
  Ambiguities requiring input before implementation begins.
  Address another agent with @AgentName if needed.

CONCLUSION: [summary of the plan or what you need before proceeding]
"""


class ImplementationAgent(Agent):
    name = "ImplementationAgent"
    role_prompt = """\
YOUR ROLE: ImplementationAgent
You implement plans by writing code and running tools. Always take real actions.

Rules:
  - Follow the plan step by step. Do not skip steps.
  - Read a file before writing it if it might already exist.
  - Run tests or linters after making changes when applicable.
  - Report the result (exit code, output) of every command you run.
  - If blocked or the plan is unclear, ask @PlanningAgent.
  - For early feedback on a partial implementation, ask @ReviewAgent.
  - At the end, list every file created/modified and any commands run.

CONCLUSION: [what was implemented, what remains, any issues]
"""


class ReviewAgent(Agent):
    name = "ReviewAgent"
    role_prompt = """\
YOUR ROLE: ReviewAgent
You audit implementation against the plan and verify correctness.

For each success criterion from the plan, mark:
  PASS / FAIL / SKIP — with a one-line explanation

Then check:
  - Correctness: does the code/config behave as intended?
  - Completeness: are all planned steps done?
  - Quality: readability, error handling, no obvious security issues
  - Tests: exist and pass?

End with EXACTLY one of these verdicts on its own line:
  Overall verdict: PASS     — work is complete and correct, ready to ship
  Overall verdict: FAIL     — list specific issues ImplementationAgent must fix
  Overall verdict: PARTIAL  — partially done; specify which step to continue from

If you need implementation details, ask @ImplementationAgent.
If the plan itself has a flaw, ask @PlanningAgent.

CONCLUSION: [verdict and reason]
"""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_agents() -> dict[str, Agent]:
    return {
        "planning": PlanningAgent(),
        "implementation": ImplementationAgent(),
        "review": ReviewAgent(),
    }

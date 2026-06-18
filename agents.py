"""
Multi-agent system with three peer-to-peer agents:
  - PlanningAgent: breaks down tasks and creates execution plans
  - ImplementationAgent: writes code and executes tools
  - ReviewAgent: reviews outputs and suggests improvements

All agents use claude-opus-4-8 with adaptive thinking and streaming.
Prompt caching is applied to stable system prompt prefixes.
"""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    def effective_input_cost(self) -> float:
        """Approximate USD cost using Opus 4.8 pricing."""
        cache_miss = (self.input_tokens - self.cache_read_input_tokens) * 5.00 / 1_000_000
        cache_read = self.cache_read_input_tokens * 0.50 / 1_000_000
        cache_write = self.cache_creation_input_tokens * 6.25 / 1_000_000
        output = self.output_tokens * 25.00 / 1_000_000
        return cache_miss + cache_read + cache_write + output

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
            "estimated_cost_usd": round(self.effective_input_cost, 6),
        }


# ---------------------------------------------------------------------------
# Tool definitions (shared across all agents)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating it if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command and return stdout/stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "cwd": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
            "required": ["path"],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return a string result."""
    try:
        if tool_name == "read_file":
            content = Path(tool_input["path"]).read_text(encoding="utf-8", errors="replace")
            return content[:50_000]  # cap to avoid runaway context
        elif tool_name == "write_file":
            p = Path(tool_input["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(tool_input["content"], encoding="utf-8")
            return f"Wrote {len(tool_input['content'])} bytes to {tool_input['path']}"
        elif tool_name == "run_command":
            result = subprocess.run(
                tool_input["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tool_input.get("cwd"),
            )
            out = result.stdout[-10_000:] if result.stdout else ""
            err = result.stderr[-2_000:] if result.stderr else ""
            return f"EXIT {result.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        elif tool_name == "list_directory":
            entries = sorted(Path(tool_input["path"]).iterdir())
            lines = [("D " if e.is_dir() else "F ") + e.name for e in entries]
            return "\n".join(lines)
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as exc:
        return f"Tool error: {exc}"


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

STABLE_SHARED_PREFIX = """\
You are part of a three-agent peer-to-peer collaborative system.
The agents are:
  • PlanningAgent  — decomposes tasks, creates execution plans
  • ImplementationAgent — writes code, executes commands and tools
  • ReviewAgent — audits outputs, identifies issues, suggests improvements

COMMUNICATION RULES
- Messages from other agents appear prefixed with their name: [PlanningAgent], [ImplementationAgent], [ReviewAgent].
- You may address another agent by mentioning their name.
- Always be concise. Avoid repeating what others have already said.
- State your conclusion clearly at the end of your message.

TOOL USE
- Use tools proactively to gather information rather than asking the user.
- Prefer reading existing files before writing new ones.
"""


class Agent:
    """Base peer-to-peer agent backed by claude-opus-4-8."""

    name: str = "Agent"
    role_prompt: str = ""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.usage = TokenUsage()
        # Log callback: (agent_name, event_type, data)
        self.on_event: Any = None

    def _emit(self, event_type: str, data: Any) -> None:
        if self.on_event:
            self.on_event(self.name, event_type, data)

    def _build_system(self) -> list[dict]:
        """Return system blocks with cache_control on the stable shared prefix."""
        return [
            {
                "type": "text",
                "text": STABLE_SHARED_PREFIX,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": self.role_prompt,
            },
        ]

    def _build_tool_block(self) -> list[dict]:
        """Inject cache_control on the last tool definition for cache-friendliness."""
        tools = [dict(t) for t in TOOLS]
        if tools:
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
        return tools

    def respond(
        self,
        messages: list[dict],
        image_bytes: bytes | None = None,
        image_media_type: str = "image/png",
    ) -> str:
        """
        Run one agent turn with the full shared message thread.
        Handles tool use loops internally.
        Returns the final text response.
        """
        local_messages = list(messages)

        # Optionally attach a vision payload to the last user message
        if image_bytes:
            b64 = base64.standard_b64encode(image_bytes).decode()
            last = local_messages[-1]
            content = last.get("content", "")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_media_type,
                        "data": b64,
                    },
                }
            )
            local_messages = local_messages[:-1] + [{"role": "user", "content": content}]

        self._emit("start", {"message_count": len(local_messages)})

        while True:
            with self.client.messages.stream(
                model="claude-opus-4-8",
                max_tokens=16384,
                thinking={"type": "adaptive"},
                system=self._build_system(),
                tools=self._build_tool_block(),
                messages=local_messages,
            ) as stream:
                message = stream.get_final_message()

            self.usage.add(message.usage)
            self._emit("usage", self.usage.to_dict())

            if message.stop_reason == "tool_use":
                # Collect tool calls and execute them
                assistant_content = message.content
                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        self._emit("tool_call", {"tool": block.name, "input": block.input})
                        result = execute_tool(block.name, block.input)
                        self._emit("tool_result", {"tool": block.name, "result": result[:500]})
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                local_messages.append({"role": "assistant", "content": assistant_content})
                local_messages.append({"role": "user", "content": tool_results})
                continue

            # Extract final text
            text_parts = [b.text for b in message.content if hasattr(b, "text")]
            response_text = "\n".join(text_parts).strip()
            self._emit("response", {"text": response_text[:200]})
            return response_text

    def count_tokens(self, messages: list[dict]) -> int:
        """Count tokens for the given messages without sending them."""
        result = self.client.messages.count_tokens(
            model="claude-opus-4-8",
            system=self._build_system(),
            tools=self._build_tool_block(),
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
You break down complex tasks into clear, ordered steps.
Output a structured plan with:
  1. A numbered list of subtasks
  2. For each subtask: what needs to be done, which agent should do it, and any dependencies
  3. Success criteria

Be specific. Reference file paths and commands where known.
"""


class ImplementationAgent(Agent):
    name = "ImplementationAgent"
    role_prompt = """\
YOUR ROLE: ImplementationAgent
You implement plans by writing code and running commands.
- Follow the plan from PlanningAgent step by step.
- Use tools to read/write files and run commands — don't just describe actions.
- After completing a step, briefly report what you did and any issues encountered.
- If you encounter an error, diagnose it and fix it before moving on.
"""


class ReviewAgent(Agent):
    name = "ReviewAgent"
    role_prompt = """\
YOUR ROLE: ReviewAgent
You review the work done by ImplementationAgent and verify against the plan.
Check for:
  - Correctness: does the implementation satisfy the requirements?
  - Code quality: readability, security, edge-case handling
  - Completeness: are all planned steps done?
  - Tests: suggest or run tests where appropriate

Output a structured review with PASS/FAIL per item and an overall verdict.
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

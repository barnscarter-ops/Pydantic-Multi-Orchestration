"""
Multi-model agent pipeline:
  SonnetPlannerAgent   — claude-sonnet-4-6        (planner, debater, prompt builder)
  NemotronReviewAgent  — nvidia nemotron ultra     (co-debater, code reviewer, final reviewer)
  QwenExecutorAgent    — qwen3-14b local llama.cpp (executor — no reasoning, just does it)
  GeminiDesignAgent    — gemini-2.5-pro            (UI/design/image/video/chat)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anthropic
from openai import OpenAI

try:
    from google import genai as google_genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Config (all overridable via .env)
# ---------------------------------------------------------------------------

LLAMA_BASE_URL  = os.getenv("LLAMA_BASE_URL",  "http://localhost:8080/v1")
QWEN_MODEL      = os.getenv("QWEN_MODEL",      "qwen3-14b")
NVIDIA_API_KEY  = os.getenv("NVIDIA_API_KEY",  "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL    = os.getenv("NVIDIA_MODEL",    "nvidia/nemotron-3-ultra-550b-a55b")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY",  "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL",    "gemini-2.5-pro")
SONNET_MODEL    = os.getenv("SONNET_MODEL",    "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Per-model usage tracking
# ---------------------------------------------------------------------------

@dataclass
class ModelUsage:
    input_tokens:  int = 0
    output_tokens: int = 0

    def add(self, inp: int, out: int) -> None:
        self.input_tokens  += inp
        self.output_tokens += out

    def to_dict(self) -> dict:
        return {"input": self.input_tokens, "output": self.output_tokens}


class TokenUsage:
    def __init__(self) -> None:
        self.sonnet   = ModelUsage()
        self.nemotron = ModelUsage()
        self.qwen     = ModelUsage()
        self.gemini   = ModelUsage()

    @property
    def estimated_cost_usd(self) -> float:
        # Sonnet 4.6: $3/$15 per 1M in/out
        s = self.sonnet.input_tokens   * 3.00 / 1_000_000 + self.sonnet.output_tokens   * 15.00 / 1_000_000
        # Nemotron via NIM: ~$0.99/$3.99 per 1M
        n = self.nemotron.input_tokens * 0.99 / 1_000_000 + self.nemotron.output_tokens *  3.99 / 1_000_000
        # Qwen local: free
        # Gemini 2.5 Pro: ~$1.25/$5 per 1M
        g = self.gemini.input_tokens   * 1.25 / 1_000_000 + self.gemini.output_tokens   *  5.00 / 1_000_000
        return round(s + n + g, 6)

    def to_dict(self) -> dict:
        return {
            "sonnet":   self.sonnet.to_dict(),
            "nemotron": self.nemotron.to_dict(),
            "qwen":     {**self.qwen.to_dict(), "cost": "free (local)"},
            "gemini":   self.gemini.to_dict(),
            "estimated_cost_usd": self.estimated_cost_usd,
        }


# ---------------------------------------------------------------------------
# Tools — used by QwenExecutorAgent only
# ---------------------------------------------------------------------------

_TOOLS_DEF: list[dict] = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from disk.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory and any missing parents.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": "Execute a shell command. Returns exit code and output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd":     {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "git_op",
        "description": "Run a git operation (status, diff, add, commit, log, push, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "description": "git subcommand + args"},
                "cwd":       {"type": "string"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web via DuckDuckGo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a URL and return its text content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":       {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
        },
    },
]


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in tools
    ]


OPENAI_TOOLS = _to_openai_tools(_TOOLS_DEF)


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
            res = subprocess.run(
                inp["command"], shell=True, capture_output=True, text=True,
                timeout=int(inp.get("timeout", 60)), cwd=inp.get("cwd"),
            )
            return (
                f"EXIT {res.returncode}\n"
                f"STDOUT:\n{(res.stdout or '')[-12_000:]}\n"
                f"STDERR:\n{(res.stderr or '')[-2_000:]}"
            )

        elif name == "git_op":
            res = subprocess.run(
                f"git {inp['operation']}", shell=True, capture_output=True, text=True,
                timeout=60, cwd=inp.get("cwd"),
            )
            return f"EXIT {res.returncode}\n{(res.stdout or '')[-10_000:]}{(res.stderr or '')[-2_000:]}"

        elif name == "web_search":
            return _web_search(inp["query"], int(inp.get("max_results", 5)))

        elif name == "fetch_url":
            return _fetch_url(inp["url"], int(inp.get("max_chars", 8_000)))

        else:
            return f"Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as exc:
        return f"Tool error ({name}): {type(exc).__name__}: {exc}"


def _web_search(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=max_results))
        if not results:
            return "No results found."
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            lines += [
                f"{i}. {r.get('title', '')}",
                f"   {r.get('href', '')}",
                f"   {r.get('body', '')[:300]}",
                "",
            ]
        return "\n".join(lines)
    except Exception as exc:
        return f"Search error: {exc}"


def _fetch_url(url: str, max_chars: int = 8_000) -> str:
    try:
        import requests as req
        resp = req.get(
            url, timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MultiAgentBot/1.0)"},
            allow_redirects=True,
        )
        ct   = resp.headers.get("content-type", "")
        text = resp.text
        if "html" in ct:
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        return f"Fetch error: {exc}"


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class BaseAgent:
    name: str = "Agent"

    def __init__(self) -> None:
        self.on_event: Callable[[str, str, Any], None] | None = None

    def _emit(self, event_type: str, data: Any) -> None:
        if self.on_event:
            self.on_event(self.name, event_type, data)


# ---------------------------------------------------------------------------
# SonnetPlannerAgent — claude-sonnet-4-6
# Roles: debate co-planner, task breakdown, Gemini prompt builder
# ---------------------------------------------------------------------------

_SONNET_SYSTEM = """\
You are SonnetPlannerAgent in a multi-model AI pipeline.

ROLE 1 — DEBATE
Collaborate with NemotronReviewAgent to find the strongest implementation plan.
Argue for the best approach. Acknowledge valid counterpoints.
When you agree the plan is solid, end your response with exactly:
  CONSENSUS REACHED
Otherwise end with:
  DEBATE CONTINUES

ROLE 2 — BREAKDOWN
Convert the agreed plan into numbered atomic execution chunks for QwenExecutorAgent.
QwenExecutor cannot reason — every chunk must be fully self-contained:
  - Exact file path to read/write
  - Exact content or shell command
  - Nothing left to interpretation
One action per numbered item. Be exhaustive.

ROLE 3 — DESIGN PROMPT
When implementation is complete and a visual deliverable is needed, produce a
detailed generation prompt for Gemini. Include: purpose, style, colour palette,
layout, dimensions, content, and format.
Prefix the prompt with exactly:
  GEMINI PROMPT:
"""


class SonnetPlannerAgent(BaseAgent):
    name = "SonnetPlannerAgent"

    def __init__(self) -> None:
        super().__init__()
        self.client = anthropic.Anthropic()
        self.usage  = ModelUsage()

    def respond(self, messages: list[dict], cancel: threading.Event | None = None) -> str:
        if cancel and cancel.is_set():
            return "[Cancelled]"
        self._emit("start", {"message_count": len(messages)})
        resp = self.client.messages.create(
            model=SONNET_MODEL,
            max_tokens=8192,
            system=_SONNET_SYSTEM,
            messages=messages,
        )
        self.usage.add(resp.usage.input_tokens, resp.usage.output_tokens)
        self._emit("usage", {"model": "sonnet", **self.usage.to_dict()})
        text = resp.content[0].text if resp.content else "[No response]"
        self._emit("response", {"text": text[:300]})
        return text


# ---------------------------------------------------------------------------
# NemotronReviewAgent — NVIDIA NIM (OpenAI-compatible)
# Roles: debate co-planner, code reviewer, final reviewer
# ---------------------------------------------------------------------------

_NEMOTRON_SYSTEM = """\
You are NemotronReviewAgent in a multi-model AI pipeline.

ROLE 1 — DEBATE
Critically evaluate SonnetPlannerAgent's proposed plan.
Challenge weak assumptions. Propose concrete improvements.
When the plan is solid and you agree, end your response with exactly:
  CONSENSUS REACHED
Otherwise end with:
  DEBATE CONTINUES

ROLE 2 — CODE REVIEW
After QwenExecutorAgent implements the plan, audit every success criterion.
End with exactly one of:
  Overall verdict: PASS
  Overall verdict: FAIL — [specific issues to fix]
  Overall verdict: PARTIAL — [continue from step N]

ROLE 3 — FINAL REVIEW
Review Gemini's design output against the brief.
End with exactly:
  DESIGN APPROVED
  or
  DESIGN REJECTED — [reason]
"""


class NemotronReviewAgent(BaseAgent):
    name = "NemotronReviewAgent"

    def __init__(self) -> None:
        super().__init__()
        self.client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=NVIDIA_API_KEY or "placeholder",
        )
        self.usage = ModelUsage()

    def respond(self, messages: list[dict], cancel: threading.Event | None = None) -> str:
        if cancel and cancel.is_set():
            return "[Cancelled]"
        self._emit("start", {"message_count": len(messages)})
        api_messages = [{"role": "system", "content": _NEMOTRON_SYSTEM}] + messages
        resp = self.client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=api_messages,
            max_tokens=8192,
        )
        if resp.usage:
            self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
            self._emit("usage", {"model": "nemotron", **self.usage.to_dict()})
        text = resp.choices[0].message.content or "[No response]"
        self._emit("response", {"text": text[:300]})
        return text


# ---------------------------------------------------------------------------
# QwenExecutorAgent — local llama.cpp (OpenAI-compatible)
# Role: executor — follows explicit instructions, uses tools, no reasoning needed
# ---------------------------------------------------------------------------

_QWEN_SYSTEM = """\
/no_think
You are QwenExecutorAgent. Execute the given instruction exactly as specified.
No planning. No commentary. No reasoning. Just execute.
Use the provided tools to complete the task immediately.
When finished, output: DONE
"""


class QwenExecutorAgent(BaseAgent):
    name = "QwenExecutorAgent"

    def __init__(self) -> None:
        super().__init__()
        self.client = OpenAI(base_url=LLAMA_BASE_URL, api_key="local")
        self.usage  = ModelUsage()

    def execute_chunk(self, instruction: str, cancel: threading.Event | None = None) -> str:
        if cancel and cancel.is_set():
            return "[Cancelled]"
        self._emit("start", {"instruction": instruction[:200]})

        messages: list[dict] = [
            {"role": "system", "content": _QWEN_SYSTEM},
            {"role": "user",   "content": instruction},
        ]

        while True:
            if cancel and cancel.is_set():
                return "[Cancelled]"

            resp = self.client.chat.completions.create(
                model=QWEN_MODEL,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )
            if resp.usage:
                self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
                self._emit("usage", {"model": "qwen", **self.usage.to_dict()})

            choice = resp.choices[0]
            msg    = choice.message

            asst: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                asst["tool_calls"] = [
                    {
                        "id":   tc.id,
                        "type": "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(asst)

            if choice.finish_reason == "tool_calls" and msg.tool_calls:
                tool_msgs: list[dict] = []
                for tc in msg.tool_calls:
                    self._emit("tool_call", {"tool": tc.function.name})
                    try:
                        inp = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        inp = {}
                    result = execute_tool(tc.function.name, inp)
                    self._emit("tool_result", {"tool": tc.function.name, "result": result[:200]})
                    tool_msgs.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      result,
                    })
                messages.extend(tool_msgs)
                continue

            text = msg.content or "DONE"
            self._emit("response", {"text": text[:300]})
            return text


# ---------------------------------------------------------------------------
# GeminiDesignAgent — Google Gemini
# Roles: UI/design/image/video generation, simple everyday chat
# ---------------------------------------------------------------------------

class GeminiDesignAgent(BaseAgent):
    name = "GeminiDesignAgent"

    def __init__(self) -> None:
        super().__init__()
        self.usage = ModelUsage()
        self._client = (
            google_genai.Client(api_key=GEMINI_API_KEY)
            if _GENAI_AVAILABLE and GEMINI_API_KEY
            else None
        )

    def generate(self, prompt: str, cancel: threading.Event | None = None) -> str:
        if cancel and cancel.is_set():
            return "[Cancelled]"
        if not self._client:
            return "[Gemini unavailable — check GEMINI_API_KEY and google-genai install]"
        self._emit("start", {"prompt_preview": prompt[:200]})
        resp = self._client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            um  = resp.usage_metadata
            inp = getattr(um, "prompt_token_count",     0) or 0
            out = getattr(um, "candidates_token_count", 0) or 0
            self.usage.add(inp, out)
            self._emit("usage", {"model": "gemini", **self.usage.to_dict()})
        text = resp.text or "[No response]"
        self._emit("response", {"text": text[:300]})
        return text

    def chat(self, message: str, cancel: threading.Event | None = None) -> str:
        return self.generate(message, cancel)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_agents() -> dict[str, BaseAgent]:
    return {
        "planner":  SonnetPlannerAgent(),
        "reviewer": NemotronReviewAgent(),
        "executor": QwenExecutorAgent(),
        "designer": GeminiDesignAgent(),
    }

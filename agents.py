"""
Pydantic AI agent definitions for the homelab multi-model pipeline.

Agents:
  sonnet_agent   — claude-sonnet-4-6        (planner, debater, prompt builder)
  nemotron_agent — NVIDIA Nemotron Ultra     (co-debater, code reviewer, final reviewer)
  qwen_agent     — Qwen3-14B local llama.cpp (executor — no reasoning, tool-driven)
  gemini_agent   — Gemini 2.5 Pro            (UI/design/image generation, everyday chat)
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LLAMA_BASE_URL    = os.getenv("LLAMA_BASE_URL",    "http://localhost:8080/v1")
QWEN_MODEL        = os.getenv("QWEN_MODEL",        "qwen3-14b")
NVIDIA_API_KEY    = os.getenv("NVIDIA_API_KEY",    "")
NVIDIA_MODEL      = os.getenv("NVIDIA_MODEL",      "nvidia/nemotron-3-ultra-550b-a55b")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY",    "")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL",      "gemini-2.5-pro")
SONNET_MODEL      = os.getenv("SONNET_MODEL",      "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Shared dependencies (injected per pipeline run)
# ---------------------------------------------------------------------------

@dataclass
class HomelabDeps:
    task:             str
    emit:             Callable[[str, str, Any], None] = field(default=lambda *_: None)
    image_bytes:      bytes | None = None
    image_media_type: str = "image/png"

# ---------------------------------------------------------------------------
# Token usage tracking
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
        s = self.sonnet.input_tokens   * 3.00  / 1_000_000 + self.sonnet.output_tokens   * 15.00 / 1_000_000
        n = self.nemotron.input_tokens * 0.99  / 1_000_000 + self.nemotron.output_tokens *  3.99 / 1_000_000
        g = self.gemini.input_tokens   * 1.25  / 1_000_000 + self.gemini.output_tokens   *  5.00 / 1_000_000
        return round(s + n + g, 6)

    def to_dict(self) -> dict:
        def _cost(model: str, mu: ModelUsage) -> dict:
            rates = {
                "sonnet":   (3.00, 15.00),
                "nemotron": (0.99,  3.99),
                "qwen":     (0.00,  0.00),
                "gemini":   (1.25,  5.00),
            }
            r_in, r_out = rates.get(model, (0, 0))
            cost = round(mu.input_tokens * r_in / 1e6 + mu.output_tokens * r_out / 1e6, 6)
            d = mu.to_dict()
            d["estimated_cost_usd"] = cost
            return d

        return {
            "sonnet":                  _cost("sonnet",   self.sonnet),
            "nemotron":                _cost("nemotron", self.nemotron),
            "qwen":                    {**_cost("qwen", self.qwen), "note": "free (local)"},
            "gemini":                  _cost("gemini",   self.gemini),
            "total_estimated_cost_usd": self.estimated_cost_usd,
        }

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SONNET_SYSTEM = """\
You are the Sonnet Planner in a multi-model AI pipeline.

ROLE 1 — DEBATE
Collaborate with Nemotron to find the strongest implementation plan.
Argue for the best approach. Acknowledge valid counterpoints.
When you agree the plan is solid, end your response with exactly:
  CONSENSUS REACHED
Otherwise end with:
  DEBATE CONTINUES

ROLE 2 — BREAKDOWN
Convert the agreed plan into a numbered list of atomic execution chunks for Qwen Executor.
Qwen cannot reason — every chunk must be fully self-contained:
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

_NEMOTRON_SYSTEM = """\
You are the Nemotron Reviewer in a multi-model AI pipeline.

ROLE 1 — DEBATE
Critically evaluate Sonnet's proposed plan.
Challenge weak assumptions. Propose concrete improvements.
When the plan is solid and you agree, end your response with exactly:
  CONSENSUS REACHED
Otherwise end with:
  DEBATE CONTINUES

ROLE 2 — CODE REVIEW
After Qwen executes the plan, audit every success criterion.
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

_QWEN_SYSTEM = """\
/no_think
You are the Qwen Executor. Execute the given instruction exactly as specified.
No planning. No commentary. No reasoning. Just execute.
Use the provided tools to complete the task immediately.
When finished, output: DONE
"""

_GEMINI_SYSTEM = """\
You are the Gemini Designer in a multi-model AI pipeline.
You specialise in UI/UX design, visual design, web development, and creative generation.
Produce high-quality, production-ready outputs. Be creative and precise.
"""

# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

_SONNET_AVAILABLE = False
sonnet_agent: Agent[HomelabDeps] | None = None

try:
    from pydantic_ai.models.anthropic import AnthropicModel
    _sonnet_model = AnthropicModel(
        SONNET_MODEL,
        provider=AnthropicProvider(api_key=ANTHROPIC_API_KEY or "placeholder"),
    )
    sonnet_agent = Agent(
        _sonnet_model,
        deps_type=HomelabDeps,
        output_type=str,
        system_prompt=_SONNET_SYSTEM,
    )
    _SONNET_AVAILABLE = bool(ANTHROPIC_API_KEY)
except Exception as _e:
    _SONNET_AVAILABLE = False

nemotron_agent: Agent[HomelabDeps] = Agent(
    OpenAIChatModel(
        NVIDIA_MODEL,
        provider=OpenAIProvider(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=NVIDIA_API_KEY or "placeholder",
        ),
    ),
    deps_type=HomelabDeps,
    output_type=str,
    system_prompt=_NEMOTRON_SYSTEM,
)

qwen_agent: Agent[HomelabDeps] = Agent(
    OpenAIChatModel(
        QWEN_MODEL,
        provider=OpenAIProvider(
            base_url=LLAMA_BASE_URL,
            api_key="local",
        ),
    ),
    deps_type=HomelabDeps,
    output_type=str,
    system_prompt=_QWEN_SYSTEM,
)

# Gemini — try pydantic-ai Google provider, fall back gracefully
_GEMINI_AVAILABLE = False
gemini_agent: Agent[HomelabDeps] | None = None

try:
    from pydantic_ai.models.google import GoogleModel  # type: ignore[import]
    gemini_agent = Agent(
        GoogleModel(GEMINI_MODEL),
        deps_type=HomelabDeps,
        output_type=str,
        system_prompt=_GEMINI_SYSTEM,
    )
    _GEMINI_AVAILABLE = True
except Exception:
    _GEMINI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Qwen executor tools (Pydantic AI handles the tool loop automatically)
# ---------------------------------------------------------------------------

@qwen_agent.tool
async def read_file(ctx: RunContext[HomelabDeps], path: str) -> str:
    """Read the contents of a file from disk."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "read_file", "path": path})
    try:
        result = Path(path).read_text(encoding="utf-8", errors="replace")[:50_000]
    except Exception as exc:
        result = f"Error reading {path}: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "read_file", "chars": len(result)})
    return result


@qwen_agent.tool
async def write_file(ctx: RunContext[HomelabDeps], path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "write_file", "path": path})
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        result = f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        result = f"Error writing {path}: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "write_file", "result": result})
    return result


@qwen_agent.tool
async def create_directory(ctx: RunContext[HomelabDeps], path: str) -> str:
    """Create a directory and all missing parents."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "create_directory", "path": path})
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        result = f"Created: {path}"
    except Exception as exc:
        result = f"Error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "create_directory", "result": result})
    return result


@qwen_agent.tool
async def list_directory(ctx: RunContext[HomelabDeps], path: str) -> str:
    """List files and subdirectories in a directory."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "list_directory", "path": path})
    try:
        entries = sorted(Path(path).iterdir(), key=lambda e: (e.is_file(), e.name))
        result  = "\n".join(("DIR  " if e.is_dir() else "FILE ") + e.name for e in entries)
    except Exception as exc:
        result = f"Error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "list_directory", "result": result[:200]})
    return result


@qwen_agent.tool
async def run_command(
    ctx: RunContext[HomelabDeps],
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
) -> str:
    """Execute a shell command and return exit code + output."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "run_command", "command": command[:120]})
    try:
        loop = asyncio.get_event_loop()

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )

        res = await loop.run_in_executor(None, _run)
        result = (
            f"EXIT {res.returncode}\n"
            f"STDOUT:\n{(res.stdout or '')[-12_000:]}\n"
            f"STDERR:\n{(res.stderr or '')[-2_000:]}"
        )
    except subprocess.TimeoutExpired:
        result = "Command timed out."
    except Exception as exc:
        result = f"Error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "run_command", "result": result[:200]})
    return result


@qwen_agent.tool
async def git_op(
    ctx: RunContext[HomelabDeps],
    operation: str,
    cwd: str | None = None,
) -> str:
    """Run a git operation (status, diff, add, commit, log, push, etc.)."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "git_op", "operation": operation})
    try:
        loop = asyncio.get_event_loop()

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                f"git {operation}", shell=True, capture_output=True, text=True,
                timeout=60, cwd=cwd,
            )

        res = await loop.run_in_executor(None, _run)
        result = f"EXIT {res.returncode}\n{(res.stdout or '')[-10_000:]}{(res.stderr or '')[-2_000:]}"
    except Exception as exc:
        result = f"Error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "git_op", "result": result[:200]})
    return result


@qwen_agent.tool
async def web_search(
    ctx: RunContext[HomelabDeps],
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web via DuckDuckGo."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "web_search", "query": query})
    try:
        loop = asyncio.get_event_loop()

        def _search() -> str:
            from duckduckgo_search import DDGS  # type: ignore[import]
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

        result = await loop.run_in_executor(None, _search)
    except Exception as exc:
        result = f"Search error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "web_search", "result": result[:200]})
    return result


@qwen_agent.tool
async def fetch_url(
    ctx: RunContext[HomelabDeps],
    url: str,
    max_chars: int = 8_000,
) -> str:
    """Fetch a URL and return its text content."""
    ctx.deps.emit("qwen", "tool_call", {"tool": "fetch_url", "url": url})
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; HomelabBot/1.0)"},
            )
            ct   = resp.headers.get("content-type", "")
            text = resp.text
            if "html" in ct:
                text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
            result = text[:max_chars]
    except Exception as exc:
        result = f"Fetch error: {exc}"
    ctx.deps.emit("qwen", "tool_result", {"tool": "fetch_url", "result": result[:200]})
    return result

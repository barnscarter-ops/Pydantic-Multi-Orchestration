"""
Async orchestrator: five-phase pipeline using Pydantic AI agents.

Phases:
  1. DEBATE      — Sonnet and Nemotron debate until consensus (max N rounds)
  2. BREAKDOWN   — Sonnet converts the plan into atomic chunks for Qwen
  3. EXECUTION   — Qwen executes each chunk via tools (Pydantic AI handles the tool loop)
  4. REVIEW      — Nemotron audits; loops back on FAIL
  5. DESIGN      — (if needed) Sonnet builds prompt → Gemini generates → Nemotron approves
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any

from agents import (
    HomelabDeps, TokenUsage,
    sonnet_agent, nemotron_agent, qwen_agent, gemini_agent, _GEMINI_AVAILABLE,
    chat_agent,
)

MAX_DEBATE_ROUNDS  = 2
MAX_REVIEW_LOOPS   = 2
AGENT_CALL_TIMEOUT = 120  # seconds per individual LLM API call (network timeout is the real enforcer)

COMPLEXITY_TIERS = ("trivial", "moderate", "complex")

_DESIGN_KEYWORDS = {
    "ui", "frontend", "design", "landing page", "website", "webpage",
    "image", "video", "visual", "css", "html", "interface", "dashboard",
    "graphic", "banner", "logo", "mockup", "wireframe", "animation",
    "illustration", "infographic", "poster", "thumbnail",
}


def _needs_design(task: str) -> bool:
    words = set(re.sub(r"[^\w\s]", " ", task.lower()).split())
    return bool(words & _DESIGN_KEYWORDS)


def _parse_chunks(breakdown: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in breakdown.splitlines():
        if re.match(r"^\s*\d+[\.\)]\s+", line):
            if current:
                chunks.append("\n".join(current).strip())
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    return [c for c in chunks if c] or [breakdown.strip()]


def _parse_phases(breakdown: str) -> list[tuple[str, list[str]]]:
    """Split a breakdown into named phases separated by ## PHASE: headers.
    Falls back to a single 'main' phase if no headers are found."""
    header = re.compile(r"^##\s*PHASE:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    matches = list(header.finditer(breakdown))

    if not matches:
        return [("main", _parse_chunks(breakdown))]

    phases: list[tuple[str, list[str]]] = []
    for i, m in enumerate(matches):
        name   = m.group(1).strip()
        start  = m.end()
        end    = matches[i + 1].start() if i + 1 < len(matches) else len(breakdown)
        chunks = _parse_chunks(breakdown[start:end])
        if chunks:
            phases.append((name, chunks))

    return phases or [("main", _parse_chunks(breakdown))]


# ---------------------------------------------------------------------------
# Event bus (thread-safe; supports both async and sync callers)
# ---------------------------------------------------------------------------

@dataclass
class Event:
    timestamp:  float
    agent:      str
    event_type: str
    data:       Any


class EventBus:
    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, q: asyncio.Queue) -> None:
        self._queues.append(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues = [x for x in self._queues if x is not q]

    def emit(self, agent: str, event_type: str, data: Any) -> None:
        event = Event(timestamp=time.time(), agent=agent, event_type=event_type, data=data)
        loop = self._loop
        if loop and loop.is_running():
            for q in self._queues:
                loop.call_soon_threadsafe(q.put_nowait, event)


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    CANCELLED = "cancelled"
    FAILED    = "failed"


@dataclass
class JobResult:
    debate_transcript: str            = ""
    agreed_plan:       str            = ""
    chunks:            list[str]      = field(default_factory=list)
    execution_results: list[str]      = field(default_factory=list)
    review:            str            = ""
    design_output:     str            = ""
    design_review:     str            = ""
    passed:            bool           = False
    design_approved:   bool           = False
    debate_rounds:     int            = 0
    review_loops:      int            = 0
    token_totals:      dict[str, Any] = field(default_factory=dict)
    duration_seconds:  float          = 0.0
    tier:              str            = "complex"


@dataclass
class Job:
    id:          str
    task:        str
    status:      JobStatus        = JobStatus.PENDING
    result:      JobResult | None = None
    error:       str | None       = None
    created_at:  float            = field(default_factory=time.time)
    started_at:  float | None     = None
    finished_at: float | None     = None
    _async_task: asyncio.Task | None = field(default=None, repr=False, compare=False)
    event_log:   list             = field(default_factory=list, repr=False, compare=False)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id":          self.id,
            "task":        self.task[:300],
            "status":      self.status.value,
            "created_at":  self.created_at,
            "started_at":  self.started_at,
            "finished_at": self.finished_at,
        }
        if self.result:
            d["result"] = {
                "agreed_plan":      self.result.agreed_plan[:600],
                "chunks_count":     len(self.result.chunks),
                "debate_rounds":    self.result.debate_rounds,
                "review_loops":     self.result.review_loops,
                "passed":           self.result.passed,
                "design_approved":  self.result.design_approved,
                "duration_seconds": self.result.duration_seconds,
                "token_totals":     self.result.token_totals,
                "tier":             self.result.tier,
            }
        if self.error:
            d["error"] = self.error
        return d


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    MAX_JOBS = 50

    def __init__(self) -> None:
        self.bus               = EventBus()
        self._jobs:            dict[str, Job] = {}
        self._run_lock         = asyncio.Lock()
        self._active_job:      Job | None     = None
        self._injection_queue: asyncio.Queue  = asyncio.Queue()
        self._last_task:       str            = ""
        self._last_results:    list[str]      = []
        self._chat_history:    list[dict]     = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, agent: str, event_type: str, data: Any) -> None:
        self.bus.emit(agent, event_type, data)
        if self._active_job is not None:
            self._active_job.event_log.append(
                Event(timestamp=time.time(), agent=agent, event_type=event_type, data=data)
            )

    async def _call(self, agent_name: str, agent, prompt: str, deps: HomelabDeps):
        """Run an agent call with a hard timeout. Emits a visible error on hang."""
        self._emit(agent_name, "start", {"text": f"Waiting for {agent_name}…"})
        injected = self._drain_inject_queue()
        if injected:
            prompt = injected + "\n\n" + prompt
        try:
            return await asyncio.wait_for(
                agent.run(prompt, deps=deps),
                timeout=AGENT_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            msg = f"{agent_name} timed out after {AGENT_CALL_TIMEOUT}s — skipping"
            self._emit(agent_name, "message", {"text": msg})
            raise RuntimeError(msg)

    def _drain_inject_queue(self) -> str:
        """Pop all queued user comments and format them for injection into the next prompt."""
        comments: list[str] = []
        while not self._injection_queue.empty():
            try:
                comments.append(self._injection_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not comments:
            return ""
        return "\n".join(f"[USER COMMENT: {c}]" for c in comments)

    async def _call_stream(self, agent_name: str, agent, prompt: str, deps: HomelabDeps):
        """Run an agent with live token streaming. Emits 'stream' events per delta chunk."""
        self._emit(agent_name, "start", {"text": f"Waiting for {agent_name}…"})
        injected = self._drain_inject_queue()
        if injected:
            prompt = injected + "\n\n" + prompt

        full_text    = ""
        usage_holder: list = [None]

        async def _do() -> None:
            nonlocal full_text
            async with agent.run_stream(prompt, deps=deps) as stream:
                async for chunk in stream.stream_text(delta=True):
                    full_text += chunk
                    self._emit(agent_name, "stream", {"delta": chunk})
                usage_holder[0] = stream.usage()

        try:
            await asyncio.wait_for(_do(), timeout=AGENT_CALL_TIMEOUT)
        except asyncio.TimeoutError:
            msg = f"{agent_name} timed out after {AGENT_CALL_TIMEOUT}s — skipping"
            self._emit(agent_name, "message", {"text": msg})
            raise RuntimeError(msg)

        return SimpleNamespace(output=full_text, usage=usage_holder[0])

    def queue_inject(self, comment: str) -> None:
        """Enqueue a user comment to be prepended to the next agent call."""
        self._injection_queue.put_nowait(comment)
        self._emit("system", "user_inject", {"comment": comment})

    async def _debrief(self, task: str, execution_results: list[str]) -> None:
        """Non-streaming post-task summary: tells the user what was built and how to run it."""
        results_text = "\n\n".join(execution_results[:6]) if execution_results else "(no execution output)"
        prompt = (
            "A multi-agent coding pipeline just finished. Here's what happened:\n\n"
            f"TASK: {task}\n\n"
            f"EXECUTION OUTPUT:\n{results_text[:3000]}\n\n"
            "Write a SHORT, friendly paragraph (3-5 sentences) for the user:\n"
            "1. State what was built in plain English.\n"
            "2. Give the EXACT file paths where output was saved (extract from execution output above).\n"
            "3. Give the exact command to run or open it.\n"
            "4. Invite them to ask questions or request changes.\n\n"
            "No markdown headers. No bullet points. Just natural, warm text."
        )
        deps = HomelabDeps(task="debrief", emit=self._emit)
        self._emit("sonnet", "start", {"text": "Sonnet is writing a summary…"})
        try:
            result = await asyncio.wait_for(
                sonnet_agent.run(prompt, deps=deps),
                timeout=60,
            )
            self._emit("sonnet", "debrief", {"text": result.output})
        except Exception as exc:
            self._emit("sonnet", "debrief", {"text": f"Build finished! Check the execution log above for file paths and commands. ({exc})"})

    async def chat_respond(self, message: str) -> None:
        """Handle a Slack DM or chat message using the dedicated chat agent."""
        self._emit("system", "user_inject", {"comment": message})
        self._chat_history.append({"role": "user", "content": message})

        history = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in self._chat_history[-10:]
        )

        prompt = f"Conversation so far:\n{history}\nAssistant:"

        agent = chat_agent if chat_agent is not None else sonnet_agent
        deps  = HomelabDeps(task="chat", emit=self._emit)
        try:
            result = await self._call_stream("sonnet", agent, prompt, deps)
            self._chat_history.append({"role": "assistant", "content": result.output})
        except Exception:
            pass
        finally:
            self._emit("system", "chat_response", {"ok": True})

    def _checkpoint(self, step: str, message: str, **extra: Any) -> None:
        self._emit("system", "checkpoint", {"step": step, "message": message, **extra})

    def _make_deps(self, task: str, image_bytes: bytes | None, image_media_type: str) -> HomelabDeps:
        return HomelabDeps(
            task=task,
            emit=self._emit,
            image_bytes=image_bytes,
            image_media_type=image_media_type,
        )

    def _account_usage(self, agent_name: str, result_usage: Any, token_usage: TokenUsage) -> None:
        inp = getattr(result_usage, "input_tokens",  0) or 0
        out = getattr(result_usage, "output_tokens", 0) or 0

        rates = {
            "sonnet":   (3.00, 15.00),
            "nemotron": (0.99,  3.99),
            "qwen":     (0.00,  0.00),
            "gemini":   (1.25,  5.00),
        }
        r_in, r_out = rates.get(agent_name, (0, 0))
        cost = round(inp * r_in / 1e6 + out * r_out / 1e6, 6)

        getattr(token_usage, agent_name, token_usage.sonnet).add(inp, out)
        self._emit(agent_name, "usage", {
            "input_tokens":        inp,
            "output_tokens":       out,
            "estimated_cost_usd":  cost,
        })

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in sorted(self._jobs.values(), key=lambda j: -j.created_at)]

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job._async_task and not job._async_task.done():
            job._async_task.cancel()
        return True

    def is_busy(self) -> bool:
        return self._run_lock.locked()

    def token_counts(self) -> dict[str, Any]:
        finished = [j for j in self._jobs.values() if j.result]
        if not finished:
            return {}
        latest = max(finished, key=lambda j: j.started_at or 0)
        return latest.result.token_totals  # type: ignore[union-attr]

    def get_job_events(self, job_id: str) -> list[dict] | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        safe_types = (dict, list, str, int, float, bool, type(None))
        return [
            {
                "timestamp": e.timestamp,
                "agent":     e.agent,
                "type":      e.event_type,
                "data":      e.data if isinstance(e.data, safe_types) else str(e.data),
            }
            for e in job.event_log
        ]

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _classify(self, task: str, deps: HomelabDeps, token_usage: TokenUsage) -> str:
        """Single fast Sonnet call to classify task complexity. Returns trivial/moderate/complex."""
        prompt = (
            "You are a task router. Classify the complexity of the following coding task.\n\n"
            f"TASK: {task}\n\n"
            "Reply with EXACTLY one word — no punctuation, no explanation:\n"
            "  trivial  — single function, script, or edit; obvious implementation; no architecture needed\n"
            "  moderate — small feature or multi-file change; light planning helps but no debate needed\n"
            "  complex  — system design, multiple components, ambiguous tradeoffs, or high-risk changes\n\n"
            "One word:"
        )
        result = await self._call_stream("sonnet", sonnet_agent, prompt, deps)
        self._account_usage("sonnet", result.usage, token_usage)
        first_word = result.output.strip().lower().split()[0] if result.output.strip() else "moderate"
        tier = first_word if first_word in COMPLEXITY_TIERS else "moderate"
        self._emit("system", "checkpoint", {
            "step": "classify",
            "tier": tier,
            "message": f"Task classified as '{tier}'",
        })
        return tier

    async def _debate(
        self,
        task: str,
        deps: HomelabDeps,
        token_usage: TokenUsage,
    ) -> tuple[str, str, int]:
        transcript  = ""
        agreed_plan = ""

        for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
            self._checkpoint("debate", f"Debate round {round_num}/{MAX_DEBATE_ROUNDS}…", round=round_num)

            # Sonnet's turn
            sonnet_prompt = (
                f"TASK:\n{task}\n\nPropose a detailed implementation plan."
                if round_num == 1
                else (
                    f"TASK:\n{task}\n\n"
                    f"DEBATE SO FAR:\n{transcript[-4000:]}\n\n"
                    "Respond to Nemotron's latest points and refine the plan."
                )
            )
            s_result = await self._call_stream("sonnet", sonnet_agent, sonnet_prompt, deps)
            self._account_usage("sonnet", s_result.usage, token_usage)
            sonnet_resp = s_result.output
            self._emit("sonnet", "message", {"round": round_num, "text": sonnet_resp})
            transcript += f"\n\n[Sonnet — Round {round_num}]\n{sonnet_resp}"

            # Nemotron's turn
            nemo_prompt = (
                f"TASK:\n{task}\n\n"
                f"DEBATE SO FAR:\n{transcript[-4000:]}\n\n"
                "Critique and respond to Sonnet's proposal."
            )
            try:
                n_result = await self._call_stream("nemotron", nemotron_agent, nemo_prompt, deps)
                self._account_usage("nemotron", n_result.usage, token_usage)
                nemo_resp = n_result.output
            except Exception as exc:
                nemo_resp = f"CONSENSUS REACHED\n(Nemotron unavailable: {exc})"
                self._emit("nemotron", "message", {"round": round_num, "text": nemo_resp})
            else:
                self._emit("nemotron", "message", {"round": round_num, "text": nemo_resp})
            transcript += f"\n\n[Nemotron — Round {round_num}]\n{nemo_resp}"

            if "CONSENSUS REACHED" in sonnet_resp and "CONSENSUS REACHED" in nemo_resp:
                agreed_plan = f"{sonnet_resp}\n\n{nemo_resp}"
                return transcript, agreed_plan, round_num

        # Exhausted rounds — use last Sonnet proposal
        agreed_plan = transcript
        return transcript, agreed_plan, MAX_DEBATE_ROUNDS

    async def _breakdown(
        self,
        task: str,
        agreed_plan: str,
        deps: HomelabDeps,
        token_usage: TokenUsage,
    ) -> list[tuple[str, list[str]]]:
        self._checkpoint("breakdown", "Sonnet breaking plan into execution phases for Qwen…")
        prompt = (
            f"TASK:\n{task}\n\n"
            f"AGREED PLAN:\n{agreed_plan[:4000]}\n\n"
            "Convert this plan into atomic execution chunks for Qwen Executor.\n\n"
            "If the task has multiple independent features or concerns, group them into phases "
            "using this exact header format before each group:\n"
            "  ## PHASE: <feature name>\n\n"
            "Within each phase, use a numbered list of chunks. "
            "Each chunk must be fully self-contained — exact file paths, exact content, exact commands. "
            "No reasoning required from Qwen. Be exhaustive.\n\n"
            "Example structure:\n"
            "## PHASE: Electron Desktop App\n"
            "1. Create frontend/electron/main.js with content: ...\n"
            "2. Run command: cd frontend && npm install electron --save-dev\n\n"
            "## PHASE: Mobile CSS\n"
            "3. Edit frontend/index.html — add viewport meta tag: ...\n"
        )
        result = await self._call_stream("sonnet", sonnet_agent, prompt, deps)
        self._account_usage("sonnet", result.usage, token_usage)
        breakdown_text = result.output
        self._emit("sonnet", "message", {"text": breakdown_text})
        phases = _parse_phases(breakdown_text)
        total  = sum(len(c) for _, c in phases)
        self._checkpoint(
            "breakdown",
            f"Plan split into {len(phases)} phase(s), {total} total chunks.",
            phases=[name for name, _ in phases],
        )
        return phases

    async def _execute(
        self,
        chunks: list[str],
        deps: HomelabDeps,
        token_usage: TokenUsage,
        pass_num: int = 1,
    ) -> list[str]:
        results: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            self._checkpoint(
                "execution",
                f"Qwen executing chunk {i}/{len(chunks)} (pass {pass_num})…",
                chunk=i,
            )
            result = await self._call("qwen", qwen_agent, chunk, deps)
            self._account_usage("qwen", result.usage, token_usage)
            qwen_resp = result.output
            self._emit("qwen", "message", {"chunk": i, "result": qwen_resp[:300]})
            results.append(f"[Chunk {i}]\nInstruction: {chunk[:200]}\nResult: {qwen_resp}")
        return results

    async def _review(
        self,
        task: str,
        agreed_plan: str,
        execution_results: list[str],
        deps: HomelabDeps,
        token_usage: TokenUsage,
    ) -> str:
        self._checkpoint("review", "Nemotron reviewing implementation…")
        prompt = (
            f"TASK:\n{task}\n\n"
            f"PLAN:\n{agreed_plan[:3000]}\n\n"
            "EXECUTION RESULTS:\n" + "\n\n".join(execution_results)[:6000] +
            "\n\nReview the implementation against the plan. "
            "Check correctness, completeness, and quality."
        )
        result = await self._call_stream("nemotron", nemotron_agent, prompt, deps)
        self._account_usage("nemotron", result.usage, token_usage)
        review = result.output
        self._emit("nemotron", "message", {"text": review})
        return review

    async def _design(
        self,
        task: str,
        agreed_plan: str,
        execution_results: list[str],
        deps: HomelabDeps,
        token_usage: TokenUsage,
    ) -> tuple[str, str]:
        if not _GEMINI_AVAILABLE or gemini_agent is None:
            return "[Gemini unavailable — check GEMINI_API_KEY]", "[No design review]"

        # Sonnet builds the design prompt
        self._checkpoint("design", "Sonnet building design prompt for Gemini…")
        prompt_req = (
            f"TASK:\n{task}\n\n"
            "IMPLEMENTATION SUMMARY:\n"
            + "\n".join(r[:200] for r in execution_results[:5])
            + "\n\nBuild a detailed design generation prompt for Gemini. "
            "Prefix it with: GEMINI PROMPT:"
        )
        s_result = await self._call_stream("sonnet", sonnet_agent, prompt_req, deps)
        self._account_usage("sonnet", s_result.usage, token_usage)
        prompt_resp = s_result.output
        self._emit("sonnet", "message", {"text": prompt_resp})

        gemini_prompt = prompt_resp
        if "GEMINI PROMPT:" in prompt_resp:
            gemini_prompt = prompt_resp.split("GEMINI PROMPT:", 1)[1].strip()

        # Gemini generates
        self._checkpoint("design", "Gemini generating design output…")
        g_result = await self._call("gemini", gemini_agent, gemini_prompt, deps)
        self._account_usage("gemini", g_result.usage, token_usage)
        design_output = g_result.output
        self._emit("gemini", "message", {"text": design_output[:400]})

        # Nemotron final review
        self._checkpoint("design", "Nemotron reviewing design output…")
        review_prompt = (
            f"DESIGN BRIEF:\n{gemini_prompt[:1000]}\n\n"
            f"DESIGN OUTPUT:\n{design_output[:3000]}\n\n"
            "Review whether this design meets the brief."
        )
        n_result = await self._call_stream("nemotron", nemotron_agent, review_prompt, deps)
        self._account_usage("nemotron", n_result.usage, token_usage)
        design_review = n_result.output
        self._emit("nemotron", "message", {"text": design_review})
        return design_output, design_review

    # ------------------------------------------------------------------
    # Core pipeline (runs as an asyncio Task)
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        job: Job,
        image_bytes: bytes | None,
        image_media_type: str,
    ) -> None:
        async with self._run_lock:
            job.status     = JobStatus.RUNNING
            job.started_at = time.time()
            result         = JobResult()
            token_usage    = TokenUsage()

            task = job.task
            if image_bytes:
                import base64
                b64   = base64.standard_b64encode(image_bytes).decode()
                task += f"\n\n[Image attached: data:{image_media_type};base64,{b64[:100]}…]"

            deps = self._make_deps(task, image_bytes, image_media_type)
            self._active_job = job

            try:
                # ---- Phase 0: Classify complexity ---------------------------
                tier        = await self._classify(task, deps, token_usage)
                result.tier = tier

                execution_results: list[str] = []

                if tier == "trivial":
                    # ── Trivial: straight to Qwen ────────────────────────────
                    self._checkpoint("execution", "Trivial task — routing directly to Qwen…")
                    exec_results = await self._execute([task], deps, token_usage)
                    execution_results.extend(exec_results)
                    result.chunks            = [task]
                    result.execution_results = execution_results
                    result.passed            = True

                elif tier == "moderate":
                    # ── Moderate: Sonnet quick-plan → Qwen → one review ──────
                    self._checkpoint("breakdown", "Sonnet drafting quick execution plan…")
                    plan_prompt = (
                        f"TASK:\n{task}\n\n"
                        "Write a concise numbered execution plan for Qwen Executor. "
                        "Each step must be specific and actionable — exact file paths, exact content, exact commands. "
                        "No debate needed. Be direct."
                    )
                    plan_result = await self._call_stream("sonnet", sonnet_agent, plan_prompt, deps)
                    self._account_usage("sonnet", plan_result.usage, token_usage)
                    plan_text = plan_result.output
                    self._emit("sonnet", "message", {"text": plan_text})

                    phases = _parse_phases(plan_text)
                    result.chunks       = [c for _, chunks in phases for c in chunks]
                    result.agreed_plan  = plan_text

                    for _, phase_chunks in phases:
                        exec_results = await self._execute(phase_chunks, deps, token_usage)
                        execution_results.extend(exec_results)
                    result.execution_results = execution_results

                    review = await self._review(task, plan_text, execution_results, deps, token_usage)
                    result.review  = review
                    result.passed  = "overall verdict: pass" in review.lower() or \
                                     "overall verdict: partial" in review.lower()
                    result.review_loops = 1

                else:
                    # ── Complex: full debate → breakdown → execute → review ───
                    transcript, agreed_plan, debate_rounds = await self._debate(task, deps, token_usage)
                    result.debate_transcript = transcript
                    result.agreed_plan       = agreed_plan
                    result.debate_rounds     = debate_rounds

                    phases = await self._breakdown(task, agreed_plan, deps, token_usage)
                    result.chunks = [c for _, chunks in phases for c in chunks]

                    all_phases_passed = True

                    for phase_name, phase_chunks in phases:
                        if len(phases) > 1:
                            self._checkpoint(
                                "execution",
                                f"Starting phase '{phase_name}' ({len(phase_chunks)} chunks)…",
                                phase=phase_name,
                            )

                        current_chunks = phase_chunks
                        phase_passed   = False

                        for loop in range(1, MAX_REVIEW_LOOPS + 2):
                            result.review_loops += 1

                            exec_results = await self._execute(
                                current_chunks, deps, token_usage, pass_num=loop
                            )
                            execution_results.extend(exec_results)
                            result.execution_results = execution_results

                            review = await self._review(
                                task, agreed_plan, exec_results, deps, token_usage
                            )
                            result.review = review

                            verdict = review.lower()
                            if "overall verdict: pass" in verdict:
                                phase_passed = True
                                if len(phases) > 1:
                                    self._checkpoint("review", f"Phase '{phase_name}' passed ✓")
                                break
                            if "overall verdict: partial" in verdict:
                                self._checkpoint("review", f"Phase '{phase_name}' partial — continuing…")
                                continue
                            if loop <= MAX_REVIEW_LOOPS:
                                self._checkpoint("review", f"Phase '{phase_name}' FAIL — fix pass {loop + 1}…")
                                fix_prompt = (
                                    f"TASK:\n{task}\n\n"
                                    f"ORIGINAL PLAN:\n{agreed_plan[:2000]}\n\n"
                                    f"PHASE: {phase_name}\n"
                                    f"REVIEW FEEDBACK:\n{review}\n\n"
                                    "Produce a numbered list of fix chunks for Qwen Executor."
                                )
                                fix_result = await self._call_stream("sonnet", sonnet_agent, fix_prompt, deps)
                                self._account_usage("sonnet", fix_result.usage, token_usage)
                                current_chunks = _parse_chunks(fix_result.output)
                            else:
                                break

                        if not phase_passed:
                            all_phases_passed = False

                    result.passed = all_phases_passed

                    if all_phases_passed and _needs_design(task):
                        design_output, design_review = await self._design(
                            task, agreed_plan, execution_results, deps, token_usage
                        )
                        result.design_output   = design_output
                        result.design_review   = design_review
                        result.design_approved = "DESIGN APPROVED" in design_review

                result.token_totals     = token_usage.to_dict()
                result.duration_seconds = round(time.time() - job.started_at, 2)
                job.result = result
                job.status = JobStatus.DONE

                self._emit("system", "done", {
                    "job_id":           job.id,
                    "passed":           result.passed,
                    "design_approved":  result.design_approved,
                    "debate_rounds":    result.debate_rounds,
                    "review_loops":     result.review_loops,
                    "duration_seconds": result.duration_seconds,
                    "token_totals":     result.token_totals,
                })

                self._last_task    = task
                self._last_results = execution_results[:]
                try:
                    await self._debrief(task, execution_results)
                except Exception:
                    pass

            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                self._emit("system", "cancelled", {"job_id": job.id})
                raise

            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error  = str(exc)
                self._emit("system", "error", {"job_id": job.id, "message": str(exc)})

            finally:
                job.finished_at  = time.time()
                self._active_job = None

    # ------------------------------------------------------------------
    # Public async API (unchanged signatures — server.py needs no edits)
    # ------------------------------------------------------------------

    async def submit(
        self,
        task: str,
        image_bytes:      bytes | None = None,
        image_media_type: str          = "image/png",
    ) -> Job:
        job_id = uuid.uuid4().hex[:8]
        job    = Job(id=job_id, task=task)
        self._jobs[job_id] = job

        if len(self._jobs) > self.MAX_JOBS:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            del self._jobs[oldest.id]

        task_obj = asyncio.create_task(
            self._run_pipeline(job, image_bytes, image_media_type)
        )
        job._async_task = task_obj
        return job

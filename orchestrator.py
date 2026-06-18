"""
Orchestrator: multi-model pipeline with structured phases.

Pipeline:
  1. DEBATE      — Sonnet and Nemotron debate until consensus (max N rounds)
  2. BREAKDOWN   — Sonnet converts the plan into atomic chunks for Qwen
  3. EXECUTION   — Qwen executes each chunk using tools (no reasoning)
  4. REVIEW      — Nemotron audits; loops back to execution on FAIL
  5. DESIGN      — (if needed) Sonnet builds prompt → Gemini generates → Nemotron approves
"""

from __future__ import annotations

import asyncio
import base64
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from agents import (
    BaseAgent, TokenUsage,
    SonnetPlannerAgent, NemotronReviewAgent, QwenExecutorAgent, GeminiDesignAgent,
    create_agents,
)

MAX_DEBATE_ROUNDS  = 4   # max Sonnet/Nemotron back-and-forth rounds
MAX_REVIEW_LOOPS   = 2   # max times Qwen is sent back for fixes

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
    """Extract numbered items from a breakdown response."""
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


# ---------------------------------------------------------------------------
# Thread-safe event bus
# ---------------------------------------------------------------------------

@dataclass
class Event:
    timestamp: float
    agent:      str
    event_type: str
    data:       Any


class EventBus:
    def __init__(self) -> None:
        self._lock:   threading.Lock               = threading.Lock()
        self._queues: list[asyncio.Queue]          = []
        self._loop:   asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues.append(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues = [x for x in self._queues if x is not q]

    def emit(self, agent: str, event_type: str, data: Any) -> None:
        event = Event(timestamp=time.time(), agent=agent, event_type=event_type, data=data)
        with self._lock:
            queues = list(self._queues)
            loop   = self._loop
        if loop and loop.is_running():
            for q in queues:
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
    debate_transcript:  str              = ""
    agreed_plan:        str              = ""
    chunks:             list[str]        = field(default_factory=list)
    execution_results:  list[str]        = field(default_factory=list)
    review:             str              = ""
    design_output:      str              = ""
    design_review:      str              = ""
    passed:             bool             = False
    design_approved:    bool             = False
    debate_rounds:      int              = 0
    review_loops:       int              = 0
    token_totals:       dict[str, Any]   = field(default_factory=dict)
    duration_seconds:   float            = 0.0


@dataclass
class Job:
    id:           str
    task:         str
    status:       JobStatus        = JobStatus.PENDING
    result:       JobResult | None = None
    error:        str | None       = None
    cancel_event: threading.Event  = field(default_factory=threading.Event)
    created_at:   float            = field(default_factory=time.time)
    started_at:   float | None     = None
    finished_at:  float | None     = None

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
                "agreed_plan":       self.result.agreed_plan[:600],
                "chunks_count":      len(self.result.chunks),
                "debate_rounds":     self.result.debate_rounds,
                "review_loops":      self.result.review_loops,
                "passed":            self.result.passed,
                "design_approved":   self.result.design_approved,
                "duration_seconds":  self.result.duration_seconds,
                "token_totals":      self.result.token_totals,
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
        self.bus        = EventBus()
        self._jobs:     dict[str, Job] = {}
        self._run_lock  = threading.Lock()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, agent: str, event_type: str, data: Any) -> None:
        self.bus.emit(agent, event_type, data)

    def _checkpoint(self, step: str, message: str, **extra: Any) -> None:
        self._emit("system", "checkpoint", {"step": step, "message": message, **extra})

    def _make_handler(self, agent_name: str) -> Callable:
        def _h(name: str, ev: str, data: Any) -> None:
            self.bus.emit(name, ev, data)
        return _h

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
        job.cancel_event.set()
        return True

    def is_busy(self) -> bool:
        return self._run_lock.locked()

    def token_counts(self) -> dict[str, Any]:
        finished = [j for j in self._jobs.values() if j.result]
        if not finished:
            return {}
        latest = max(finished, key=lambda j: j.started_at or 0)
        return latest.result.token_totals  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    def _debate(
        self,
        task: str,
        planner: SonnetPlannerAgent,
        reviewer: NemotronReviewAgent,
        cancel: threading.Event,
    ) -> tuple[str, str, int]:
        """Returns (debate_transcript, agreed_plan, rounds_used)."""
        transcript = ""
        agreed_plan = ""
        sonnet_consensus = False
        nemo_consensus   = False

        for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
            self._checkpoint("debate", f"Debate round {round_num}/{MAX_DEBATE_ROUNDS}…", round=round_num)

            # Sonnet's turn
            if round_num == 1:
                sonnet_prompt = f"TASK:\n{task}\n\nPropose a detailed implementation plan."
            else:
                sonnet_prompt = (
                    f"TASK:\n{task}\n\n"
                    f"DEBATE SO FAR:\n{transcript}\n\n"
                    f"Respond to Nemotron's latest points and refine the plan."
                )
            sonnet_resp = planner.respond([{"role": "user", "content": sonnet_prompt}], cancel)
            if cancel.is_set():
                break
            self._emit("SonnetPlannerAgent", "message", {"round": round_num, "text": sonnet_resp})
            transcript += f"\n\n[Sonnet — Round {round_num}]\n{sonnet_resp}"
            sonnet_consensus = "CONSENSUS REACHED" in sonnet_resp

            # Nemotron's turn
            nemo_prompt = (
                f"TASK:\n{task}\n\n"
                f"DEBATE SO FAR:\n{transcript}\n\n"
                f"Critique and respond to Sonnet's proposal."
            )
            nemo_resp = reviewer.respond([{"role": "user", "content": nemo_prompt}], cancel)
            if cancel.is_set():
                break
            self._emit("NemotronReviewAgent", "message", {"round": round_num, "text": nemo_resp})
            transcript += f"\n\n[Nemotron — Round {round_num}]\n{nemo_resp}"
            nemo_consensus = "CONSENSUS REACHED" in nemo_resp

            if sonnet_consensus and nemo_consensus:
                agreed_plan = f"{sonnet_resp}\n\n{nemo_resp}"
                return transcript, agreed_plan, round_num

        # Didn't reach explicit consensus — use last Sonnet proposal
        agreed_plan = transcript
        return transcript, agreed_plan, MAX_DEBATE_ROUNDS

    def _breakdown(
        self,
        task: str,
        agreed_plan: str,
        planner: SonnetPlannerAgent,
        cancel: threading.Event,
    ) -> list[str]:
        self._checkpoint("breakdown", "Sonnet breaking plan into execution chunks for Qwen…")
        prompt = (
            f"TASK:\n{task}\n\n"
            f"AGREED PLAN:\n{agreed_plan}\n\n"
            "Convert this plan into a numbered list of atomic execution chunks for QwenExecutorAgent.\n"
            "Each chunk must be fully self-contained — exact file paths, exact content, exact commands.\n"
            "No reasoning required from Qwen. Be exhaustive."
        )
        breakdown_text = planner.respond([{"role": "user", "content": prompt}], cancel)
        self._emit("SonnetPlannerAgent", "message", {"text": breakdown_text})
        chunks = _parse_chunks(breakdown_text)
        self._checkpoint("breakdown", f"Plan broken into {len(chunks)} chunks.")
        return chunks

    def _execute(
        self,
        chunks: list[str],
        executor: QwenExecutorAgent,
        cancel: threading.Event,
        pass_num: int = 1,
    ) -> list[str]:
        results: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            if cancel.is_set():
                break
            self._checkpoint(
                "execution",
                f"Qwen executing chunk {i}/{len(chunks)} (pass {pass_num})…",
                chunk=i,
            )
            result = executor.execute_chunk(chunk, cancel)
            results.append(f"[Chunk {i}]\nInstruction: {chunk[:200]}\nResult: {result}")
            self._emit("QwenExecutorAgent", "message", {"chunk": i, "result": result[:300]})
        return results

    def _review(
        self,
        task: str,
        agreed_plan: str,
        execution_results: list[str],
        reviewer: NemotronReviewAgent,
        cancel: threading.Event,
    ) -> str:
        self._checkpoint("review", "Nemotron reviewing implementation…")
        prompt = (
            f"TASK:\n{task}\n\n"
            f"PLAN:\n{agreed_plan[:3000]}\n\n"
            f"EXECUTION RESULTS:\n" + "\n\n".join(execution_results)[:6000] +
            "\n\nReview the implementation against the plan. "
            "Check correctness, completeness, and quality."
        )
        review = reviewer.respond([{"role": "user", "content": prompt}], cancel)
        self._emit("NemotronReviewAgent", "message", {"text": review})
        return review

    def _design(
        self,
        task: str,
        agreed_plan: str,
        execution_results: list[str],
        planner: SonnetPlannerAgent,
        designer: GeminiDesignAgent,
        reviewer: NemotronReviewAgent,
        cancel: threading.Event,
    ) -> tuple[str, str]:
        """Returns (design_output, design_review)."""
        # Sonnet builds the Gemini prompt
        self._checkpoint("design", "Sonnet building design prompt for Gemini…")
        prompt_req = (
            f"TASK:\n{task}\n\n"
            f"IMPLEMENTATION SUMMARY:\n" + "\n".join(r[:200] for r in execution_results[:5]) +
            "\n\nBuild a detailed design generation prompt for Gemini. "
            "Prefix it with: GEMINI PROMPT:"
        )
        prompt_resp = planner.respond([{"role": "user", "content": prompt_req}], cancel)
        self._emit("SonnetPlannerAgent", "message", {"text": prompt_resp})

        gemini_prompt = prompt_resp
        if "GEMINI PROMPT:" in prompt_resp:
            gemini_prompt = prompt_resp.split("GEMINI PROMPT:", 1)[1].strip()

        # Gemini generates
        self._checkpoint("design", "Gemini generating design output…")
        design_output = designer.generate(gemini_prompt, cancel)
        self._emit("GeminiDesignAgent", "message", {"text": design_output[:400]})

        # Nemotron final review
        self._checkpoint("design", "Nemotron reviewing design output…")
        review_prompt = (
            f"DESIGN BRIEF:\n{gemini_prompt[:1000]}\n\n"
            f"DESIGN OUTPUT:\n{design_output[:3000]}\n\n"
            "Review whether this design meets the brief."
        )
        design_review = reviewer.respond([{"role": "user", "content": review_prompt}], cancel)
        self._emit("NemotronReviewAgent", "message", {"text": design_review})
        return design_output, design_review

    # ------------------------------------------------------------------
    # Core run (executes in thread pool)
    # ------------------------------------------------------------------

    def _run_sync(
        self,
        job: Job,
        image_bytes: bytes | None,
        image_media_type: str,
    ) -> None:
        if not self._run_lock.acquire(blocking=False):
            job.status = JobStatus.FAILED
            job.error  = "Another job is already running. Try again shortly."
            job.finished_at = time.time()
            self._emit("system", "error", {"job_id": job.id, "message": job.error})
            return

        try:
            job.status     = JobStatus.RUNNING
            job.started_at = time.time()

            agents   = create_agents()
            planner  = agents["planner"]
            reviewer = agents["reviewer"]
            executor = agents["executor"]
            designer = agents["designer"]

            for agent in agents.values():
                agent.on_event = self._make_handler(agent.name)

            cancel = job.cancel_event
            result = JobResult()

            # Embed image in task if provided (for Sonnet context)
            task = job.task
            if image_bytes:
                b64 = base64.standard_b64encode(image_bytes).decode()
                task += f"\n\n[Image attached: data:{image_media_type};base64,{b64[:100]}…]"

            # ---- Phase 1: Debate ----------------------------------------
            transcript, agreed_plan, debate_rounds = self._debate(
                task, planner, reviewer, cancel
            )
            result.debate_transcript = transcript
            result.agreed_plan       = agreed_plan
            result.debate_rounds     = debate_rounds

            if cancel.is_set():
                job.status = JobStatus.CANCELLED
                return

            # ---- Phase 2: Breakdown -------------------------------------
            chunks = self._breakdown(task, agreed_plan, planner, cancel)
            result.chunks = chunks

            if cancel.is_set():
                job.status = JobStatus.CANCELLED
                return

            # ---- Phase 3+4: Execute → Review loop -----------------------
            execution_results: list[str] = []
            for loop in range(1, MAX_REVIEW_LOOPS + 2):
                result.review_loops = loop

                exec_results = self._execute(chunks, executor, cancel, pass_num=loop)
                execution_results.extend(exec_results)
                result.execution_results = execution_results

                if cancel.is_set():
                    job.status = JobStatus.CANCELLED
                    return

                review = self._review(task, agreed_plan, execution_results, reviewer, cancel)
                result.review = review

                if cancel.is_set():
                    job.status = JobStatus.CANCELLED
                    return

                verdict = review.lower()
                if "overall verdict: pass" in verdict:
                    result.passed = True
                    break
                if "overall verdict: partial" in verdict:
                    # extract which step to continue from if possible
                    self._checkpoint("review", "Partial pass — Qwen will continue implementation.")
                    continue
                # FAIL — send back for another loop
                if loop <= MAX_REVIEW_LOOPS:
                    self._checkpoint(
                        "review",
                        f"Review FAIL — sending Qwen back for fix pass {loop + 1}…",
                    )
                    # Rebuild chunks from failure feedback
                    fix_prompt = (
                        f"TASK:\n{task}\n\n"
                        f"ORIGINAL PLAN:\n{agreed_plan[:2000]}\n\n"
                        f"REVIEW FEEDBACK:\n{review}\n\n"
                        "Produce a numbered list of fix chunks for QwenExecutorAgent to address the issues."
                    )
                    fix_resp = planner.respond(
                        [{"role": "user", "content": fix_prompt}], cancel
                    )
                    chunks = _parse_chunks(fix_resp)
                    result.chunks = chunks
                else:
                    break  # out of loops — report what we have

            # ---- Phase 5: Design (if needed and code passed) ------------
            if result.passed and _needs_design(task) and not cancel.is_set():
                design_output, design_review = self._design(
                    task, agreed_plan, execution_results,
                    planner, designer, reviewer, cancel
                )
                result.design_output   = design_output
                result.design_review   = design_review
                result.design_approved = "DESIGN APPROVED" in design_review

            # ---- Aggregate token usage ----------------------------------
            usage = TokenUsage()
            usage.sonnet.add(planner.usage.input_tokens,  planner.usage.output_tokens)
            usage.nemotron.add(reviewer.usage.input_tokens, reviewer.usage.output_tokens)
            usage.qwen.add(executor.usage.input_tokens,  executor.usage.output_tokens)
            usage.gemini.add(designer.usage.input_tokens, designer.usage.output_tokens)
            result.token_totals = usage.to_dict()

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

        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error  = str(exc)
            self._emit("system", "error", {"job_id": job.id, "message": str(exc)})

        finally:
            job.finished_at = time.time()
            self._run_lock.release()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def submit(
        self,
        task: str,
        image_bytes:       bytes | None = None,
        image_media_type:  str          = "image/png",
    ) -> Job:
        job_id = uuid.uuid4().hex[:8]
        job    = Job(id=job_id, task=task)
        self._jobs[job_id] = job

        if len(self._jobs) > self.MAX_JOBS:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            del self._jobs[oldest.id]

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self._run_sync, job, image_bytes, image_media_type)
        return job

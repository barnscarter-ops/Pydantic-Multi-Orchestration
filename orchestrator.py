"""
Orchestrator: shared message thread, P2P mention routing, job lifecycle.

Message structure (Anthropic API requires strict alternation):
  user(task)  →  assistant(plan)  →  user(bridge)  →  assistant(impl)  →  …

Each agent's response is stored as role="assistant".
Bridge messages directing the next agent are role="user".
Tool-use intermediate turns live only in the agent's local copy of messages.
"""

from __future__ import annotations

import asyncio
import base64
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from agents import Agent, TokenUsage, create_agents, parse_mentions


# ---------------------------------------------------------------------------
# Thread-safe event bus
# ---------------------------------------------------------------------------

@dataclass
class Event:
    timestamp: float
    agent: str
    event_type: str
    data: Any


class EventBus:
    """
    Thread-safe pub/sub. emit() is called from worker threads; subscribers
    receive events on asyncio Queues in the event-loop thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: list[asyncio.Queue] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues.append(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._queues = [x for x in self._queues if x is not q]

    def emit(self, agent: str, event_type: str, data: Any) -> None:
        """Safe to call from any thread."""
        event = Event(timestamp=time.time(), agent=agent, event_type=event_type, data=data)
        with self._lock:
            queues = list(self._queues)
            loop = self._loop
        if loop and loop.is_running():
            for q in queues:
                loop.call_soon_threadsafe(q.put_nowait, event)


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class JobResult:
    plan: str = ""
    implementation_notes: list[str] = field(default_factory=list)
    review: str = ""
    rounds: int = 0
    passed: bool = False
    token_totals: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class Job:
    id: str
    task: str
    status: JobStatus = JobStatus.PENDING
    result: JobResult | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "task": self.task[:300],
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if self.result:
            d["result"] = {
                "plan": self.result.plan[:600],
                "rounds": self.result.rounds,
                "passed": self.result.passed,
                "duration_seconds": self.result.duration_seconds,
                "token_totals": self.result.token_totals,
            }
        if self.error:
            d["error"] = self.error
        return d


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    MAX_JOBS = 50

    def __init__(self, max_rounds: int = 3, max_p2p_depth: int = 2) -> None:
        self.max_rounds = max_rounds
        self.max_p2p_depth = max_p2p_depth
        self.bus = EventBus()
        self._jobs: dict[str, Job] = {}
        self._run_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _emit(self, agent: str, event_type: str, data: Any) -> None:
        self.bus.emit(agent, event_type, data)

    def _make_handler(self, agent_name: str) -> Callable:
        def _h(name: str, ev: str, data: Any) -> None:
            self.bus.emit(agent_name, ev, data)
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
        """Token usage from the most recent completed run."""
        finished = [j for j in self._jobs.values() if j.result]
        if not finished:
            return {}
        latest = max(finished, key=lambda j: j.started_at or 0)
        return latest.result.token_totals  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Thread construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _user(text: str) -> dict:
        return {"role": "user", "content": text}

    @staticmethod
    def _user_with_image(text: str, image_bytes: bytes, media_type: str) -> dict:
        b64 = base64.standard_b64encode(image_bytes).decode()
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
            ],
        }

    @staticmethod
    def _assistant(text: str) -> dict:
        return {"role": "assistant", "content": text}

    # ------------------------------------------------------------------
    # P2P turn runner
    # ------------------------------------------------------------------

    def _run_turn(
        self,
        thread: list[dict],
        agents: dict[str, Agent],
        agent_key: str,
        cancel: threading.Event,
        depth: int = 0,
    ) -> str:
        """
        Call one agent with the current thread (which must end in role=user).
        Appends the agent's response as role=assistant.
        Handles @mentions by injecting bridge messages and recursing.
        Returns the agent's text response.
        """
        agent = agents[agent_key]
        response = agent.respond(thread, cancel=cancel)

        if cancel.is_set():
            return "[Cancelled]"

        # Agent response goes in as assistant turn — maintains alternation
        thread.append(self._assistant(response))
        self._emit(agent.name, "message", {"agent": agent.name, "text": response})

        # P2P: handle @mentions up to max_p2p_depth
        if depth < self.max_p2p_depth:
            for mentioned_name in parse_mentions(response):
                target_key = next(
                    (k for k, a in agents.items() if a.name == mentioned_name),
                    None,
                )
                if not target_key or target_key == agent_key:
                    continue

                self._emit("system", "checkpoint", {
                    "step": "p2p",
                    "from": agent.name,
                    "to": mentioned_name,
                    "depth": depth,
                    "message": f"P2P: {agent.name} → {mentioned_name}",
                })

                # Add a user bridge directing the mentioned agent, then recurse.
                # After recursion the thread ends in assistant(p2p_response) — do NOT
                # append another user message here; the caller adds the next bridge.
                bridge = (
                    f"[System] {agent.name} has a question or request for {mentioned_name}. "
                    f"Please respond to their message above."
                )
                thread.append(self._user(bridge))
                self._run_turn(thread, agents, target_key, cancel, depth + 1)

                if cancel.is_set():
                    return response

        return response

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
            job.error = "Another job is already running. Try again shortly."
            job.finished_at = time.time()
            self._emit("system", "error", {"job_id": job.id, "message": job.error})
            return

        try:
            job.status = JobStatus.RUNNING
            job.started_at = time.time()

            agents = create_agents()
            for agent in agents.values():
                agent.on_event = self._make_handler(agent.name)

            cancel = job.cancel_event
            result = JobResult()

            # Build initial user message (may include an image)
            initial_msg = (
                self._user_with_image(job.task, image_bytes, image_media_type)
                if image_bytes
                else self._user(job.task)
            )

            # Thread always starts with the user task. _run_turn expects thread[-1].role == "user".
            thread: list[dict] = [initial_msg]

            # ---- Planning phase ----------------------------------------
            self._emit("system", "checkpoint", {
                "step": "planning",
                "message": "PlanningAgent is creating a plan…",
            })
            plan = self._run_turn(thread, agents, "planning", cancel)
            result.plan = plan

            if cancel.is_set():
                job.status = JobStatus.CANCELLED
                return

            # ---- Implement → Review loop --------------------------------
            for round_num in range(1, self.max_rounds + 1):
                result.rounds = round_num

                # Bridge to implementation — thread currently ends in assistant(plan or review)
                thread.append(self._user(
                    f"[System] PlanningAgent has provided a plan. "
                    f"ImplementationAgent, please implement it step by step "
                    f"(round {round_num} of {self.max_rounds}). "
                    f"Use tools to take real actions."
                ) if round_num == 1 else self._user(
                    f"[System] ReviewAgent has requested changes. "
                    f"ImplementationAgent, please address the issues identified "
                    f"(round {round_num} of {self.max_rounds})."
                ))

                self._emit("system", "checkpoint", {
                    "step": "implementation",
                    "round": round_num,
                    "message": f"ImplementationAgent executing (round {round_num}/{self.max_rounds})…",
                })
                impl = self._run_turn(thread, agents, "implementation", cancel)
                result.implementation_notes.append(impl)

                if cancel.is_set():
                    job.status = JobStatus.CANCELLED
                    return

                # Bridge to review — thread ends in assistant(impl)
                thread.append(self._user(
                    "[System] ImplementationAgent has finished. "
                    "ReviewAgent, please audit the implementation against the plan's success criteria."
                ))

                self._emit("system", "checkpoint", {
                    "step": "review",
                    "round": round_num,
                    "message": f"ReviewAgent auditing (round {round_num}/{self.max_rounds})…",
                })
                review = self._run_turn(thread, agents, "review", cancel)
                result.review = review

                if cancel.is_set():
                    job.status = JobStatus.CANCELLED
                    return

                if "overall verdict: pass" in review.lower():
                    result.passed = True
                    break

            # ---- Aggregate token usage ----------------------------------
            for agent in agents.values():
                result.token_totals[agent.name] = agent.usage.to_dict()

            result.duration_seconds = round(time.time() - job.started_at, 2)
            job.result = result
            job.status = JobStatus.DONE

            self._emit("system", "done", {
                "job_id": job.id,
                "passed": result.passed,
                "rounds": result.rounds,
                "duration_seconds": result.duration_seconds,
                "token_totals": result.token_totals,
            })

        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
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
        image_bytes: bytes | None = None,
        image_media_type: str = "image/png",
    ) -> Job:
        job_id = uuid.uuid4().hex[:8]
        job = Job(id=job_id, task=task)
        self._jobs[job_id] = job

        # Trim history if needed
        if len(self._jobs) > self.MAX_JOBS:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            del self._jobs[oldest.id]

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self._run_sync, job, image_bytes, image_media_type)
        return job

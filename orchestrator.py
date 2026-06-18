"""
Peer-to-peer orchestrator: manages the shared message bus and debate loop.

Flow:
  1. User submits a task (text + optional image bytes)
  2. PlanningAgent creates an execution plan
  3. ImplementationAgent executes the plan step by step
  4. ReviewAgent audits the result
  5. If the review fails, loop back to ImplementationAgent (up to max_rounds)
  6. Human-in-the-loop checkpoints are emitted via the event bus

No agent is a "leader" — all three read the full shared thread.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from agents import Agent, PlanningAgent, ImplementationAgent, ReviewAgent, create_agents, TokenUsage


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

@dataclass
class Event:
    timestamp: float
    agent: str           # "system" | "PlanningAgent" | "ImplementationAgent" | "ReviewAgent"
    event_type: str      # "message" | "tool_call" | "tool_result" | "usage" | "checkpoint" | "done"
    data: Any


class EventBus:
    """Async pub/sub for orchestrator events."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers = [s for s in self._subscribers if s is not q]

    def emit(self, agent: str, event_type: str, data: Any) -> None:
        event = Event(timestamp=time.time(), agent=agent, event_type=event_type, data=data)
        for q in self._subscribers:
            q.put_nowait(event)

    async def stream(self, q: asyncio.Queue) -> AsyncIterator[Event]:
        while True:
            event = await q.get()
            yield event
            if event.event_type == "done":
                break


# ---------------------------------------------------------------------------
# Shared message thread helpers
# ---------------------------------------------------------------------------

def _agent_message(agent_name: str, text: str) -> dict:
    """Wrap an agent response as a user-role message for the shared thread."""
    return {"role": "user", "content": f"[{agent_name}]: {text}"}


def _user_message(text: str) -> dict:
    return {"role": "user", "content": text}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    plan: str = ""
    implementation_notes: list[str] = field(default_factory=list)
    review: str = ""
    rounds: int = 0
    passed: bool = False
    token_totals: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


class Orchestrator:
    def __init__(self, max_rounds: int = 3) -> None:
        self.max_rounds = max_rounds
        self.bus = EventBus()
        self._agents: dict[str, Agent] = create_agents()
        self._wire_agents()

    def _wire_agents(self) -> None:
        for name, agent in self._agents.items():
            agent.on_event = self._make_handler(agent.name)

    def _make_handler(self, agent_name: str) -> Callable:
        def handler(a_name: str, event_type: str, data: Any) -> None:
            self.bus.emit(agent_name, event_type, data)
        return handler

    def _emit(self, event_type: str, data: Any) -> None:
        self.bus.emit("system", event_type, data)

    # ------------------------------------------------------------------
    # Synchronous run (called from a thread pool by the async wrapper)
    # ------------------------------------------------------------------

    def _run_sync(
        self,
        task: str,
        image_bytes: bytes | None = None,
        image_media_type: str = "image/png",
    ) -> RunResult:
        start = time.time()
        result = RunResult()

        # Shared conversation thread visible to all agents
        thread: list[dict] = [_user_message(task)]

        planning_agent: PlanningAgent = self._agents["planning"]  # type: ignore
        impl_agent: ImplementationAgent = self._agents["implementation"]  # type: ignore
        review_agent: ReviewAgent = self._agents["review"]  # type: ignore

        # ---- Step 1: Planning ----------------------------------------
        self._emit("checkpoint", {"step": "planning", "message": "PlanningAgent is creating a plan…"})

        plan = planning_agent.respond(thread, image_bytes=image_bytes, image_media_type=image_media_type)
        result.plan = plan
        thread.append(_agent_message("PlanningAgent", plan))
        self._emit("message", {"agent": "PlanningAgent", "text": plan})

        # ---- Steps 2-4: Implement → Review loop ----------------------
        for round_num in range(1, self.max_rounds + 1):
            result.rounds = round_num

            self._emit("checkpoint", {
                "step": "implementation",
                "round": round_num,
                "message": f"ImplementationAgent executing (round {round_num}/{self.max_rounds})…",
            })

            impl_response = impl_agent.respond(thread)
            result.implementation_notes.append(impl_response)
            thread.append(_agent_message("ImplementationAgent", impl_response))
            self._emit("message", {"agent": "ImplementationAgent", "text": impl_response})

            self._emit("checkpoint", {
                "step": "review",
                "round": round_num,
                "message": f"ReviewAgent auditing (round {round_num}/{self.max_rounds})…",
            })

            review_response = review_agent.respond(thread)
            result.review = review_response
            thread.append(_agent_message("ReviewAgent", review_response))
            self._emit("message", {"agent": "ReviewAgent", "text": review_response})

            # Simple verdict detection
            lower = review_response.lower()
            if "overall: pass" in lower or "verdict: pass" in lower or "overall verdict: pass" in lower:
                result.passed = True
                break

            if round_num < self.max_rounds:
                # Ask implementation agent to address review feedback
                thread.append(_user_message(
                    f"[System] ReviewAgent did not pass. Please address the feedback above (round {round_num + 1})."
                ))

        # ---- Aggregate token usage -----------------------------------
        for agent in self._agents.values():
            result.token_totals[agent.name] = agent.usage.to_dict()

        result.duration_seconds = round(time.time() - start, 2)
        self._emit("done", {"result": result})
        return result

    # ------------------------------------------------------------------
    # Async wrapper so FastAPI can await it without blocking the event loop
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        image_bytes: bytes | None = None,
        image_media_type: str = "image/png",
    ) -> RunResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._run_sync,
            task,
            image_bytes,
            image_media_type,
        )

    def token_counts(self) -> dict[str, Any]:
        return {name: agent.usage.to_dict() for name, agent in self._agents.items()}

    def reset_agents(self) -> None:
        """Reset token counters (create fresh agents) for a new session."""
        self._agents = create_agents()
        self._wire_agents()

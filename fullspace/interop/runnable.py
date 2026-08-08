"""Fullspace Engine as a langchain Runnable (invoke / stream / async).

Lets a Fullspace engine be used anywhere a langchain Runnable is expected —
LangChain chains, LangServe, LangGraph (as a node), etc. — including streaming
and async, matching LangGraph's own Runnable surface.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterator, Optional

from langchain_core.runnables import Runnable, RunnableConfig

from fullspace.engine.runtime import Engine
from fullspace.engine.types import RunResult, StepEvent


def _parse_input(input: Any) -> tuple[str, Optional[dict]]:
    """Normalize a Runnable input into (task, seed_state)."""
    if isinstance(input, str):
        return input, None
    if isinstance(input, dict):
        task = input.get("task", "")
        if isinstance(input.get("state"), dict):
            return task, dict(input["state"])
        seed = {k: v for k, v in input.items() if k != "task"}
        return task, (seed or None)
    return str(input), None


def _event_to_chunk(ev: StepEvent) -> dict:
    return {
        "step": ev.step,
        "group": ev.group,
        "updates": ev.updates,
        "state": ev.state,
        "trajectory": ev.trajectory,
        "terminated": ev.terminated,
        "terminated_by": ev.terminated_by,
    }


def _result_to_output(result: RunResult) -> dict:
    return {
        "state": result.state,
        "trajectory": result.trajectory,
        "terminated_by": result.terminated_by,
        "steps": result.steps,
    }


class FullspaceRunnable(Runnable):
    """Wrap a Fullspace engine in the langchain Runnable interface.

    Supports ``invoke`` / ``stream`` (sync) and ``ainvoke`` / ``astream`` (async),
    so the engine plugs into LangChain's streaming and async pipelines the same
    way a LangGraph compiled graph does.
    """

    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine

    def invoke(self, input, config: Optional[RunnableConfig] = None, **kwargs) -> dict:
        task, state = _parse_input(input)
        return _result_to_output(self.engine.run(task, state=state))

    def stream(self, input, config: Optional[RunnableConfig] = None, **kwargs) -> Iterator[dict]:
        task, state = _parse_input(input)
        for ev in self.engine.stream(task, state=state):
            yield _event_to_chunk(ev)

    async def ainvoke(self, input, config: Optional[RunnableConfig] = None, **kwargs) -> dict:
        task, state = _parse_input(input)
        return _result_to_output(await self.engine.ainvoke(task, state=state))

    async def astream(self, input, config: Optional[RunnableConfig] = None, **kwargs) -> AsyncIterator[dict]:
        task, state = _parse_input(input)
        async for ev in self.engine.astream(task, state=state):
            yield _event_to_chunk(ev)

"""Fullspace Engine as a langchain Runnable (invoke interface).

Lets a Fullspace engine be used anywhere a langchain Runnable is expected —
LangChain chains, LangServe, LangGraph (as a node via ``Runnable.node``-style
adapters), etc.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.runnables import Runnable, RunnableConfig

from fullspace.engine.runtime import Engine


class FullspaceRunnable(Runnable):
    """Wrap a Fullspace engine in the langchain Runnable interface.

    ``invoke`` accepts:
      * a task string, or
      * a dict with a ``"task"`` key (other keys seed the state; a nested
        ``"state"`` dict is also accepted).
    Returns a dict with ``state``, ``trajectory``, ``terminated_by``, ``steps``.
    """

    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine

    def invoke(self, input, config: Optional[RunnableConfig] = None, **kwargs) -> dict:
        if isinstance(input, str):
            task, state = input, None
        elif isinstance(input, dict):
            task = input.get("task", "")
            if isinstance(input.get("state"), dict):
                state = dict(input["state"])
            else:
                state = {k: v for k, v in input.items() if k != "task"} or None
        else:
            task, state = str(input), None

        result = self.engine.run(task, state=state)
        return {
            "state": result.state,
            "trajectory": result.trajectory,
            "terminated_by": result.terminated_by,
            "steps": result.steps,
        }

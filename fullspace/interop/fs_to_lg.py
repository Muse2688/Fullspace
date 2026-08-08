"""Fullspace -> LangGraph: expose an Engine as a LangGraph node."""

from __future__ import annotations

from typing import Callable, Optional, Union

from fullspace.engine.runtime import Engine


def as_langgraph_node(
    engine: Engine,
    task: Union[str, Callable[[dict], str]],
    *,
    map_state_out: Optional[Callable[[dict, dict], dict]] = None,
) -> Callable[[dict], dict]:
    """Return a node function for ``langgraph.graph.StateGraph.add_node``.

    The node derives a task from the LangGraph state (a literal string, or a
    ``task(state)`` callable), runs the Fullspace engine seeded with that state,
    and returns the resulting state (adapted by ``map_state_out`` if given) as
    the node's update.

    Args:
        engine: the Fullspace engine to run.
        task: a task string, or a function ``(lg_state) -> task_string``.
        map_state_out: ``(fs_state, lg_state) -> updates`` to control what the
            LangGraph node emits (defaults to the engine's full final state).
    """
    task_fn: Callable[[dict], str] = (lambda _s: task) if isinstance(task, str) else task

    def node(state: dict) -> dict:
        result = engine.run(task_fn(state), state=dict(state))
        if map_state_out is not None:
            return map_state_out(result.state, state)
        return dict(result.state)

    return node

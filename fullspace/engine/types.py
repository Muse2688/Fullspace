"""Engine data types: node context, node result, run result."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

import numpy as np


@dataclass
class NodeContext:
    """Passed into a node handler at each step.

    Attributes:
        state: the shared mutable state (updates are merged in place).
        trajectory: capability ids visited so far, in order.
        step: zero-based index of the current step.
        task: the original task/input text.
    """

    state: dict[str, Any]
    trajectory: list[str]
    step: int
    task: str


@dataclass
class NodeResult:
    """What a node returns.

    Precedence for deciding the next step: ``halt`` > ``goto`` > ``intent``.
    If none of halt/goto/intent is set, the run terminates gracefully.

    Attributes:
        updates: partial state merged into the shared state.
        intent: a description (str) or vector of "what to do next" — soft-routed
            via ANN to the nearest capability.
        goto: a capability id to hop to exactly (hard route; LangGraph-style edge).
        halt: force termination after this node.
    """

    updates: dict[str, Any] = field(default_factory=dict)
    intent: Optional[Union[str, np.ndarray]] = None
    goto: Optional[str] = None
    halt: bool = False


NodeHandler = Callable[[NodeContext], Union[NodeResult, dict, None]]


def coerce_result(value: Union[NodeResult, dict, None]) -> NodeResult:
    """Normalize a handler's return value into a NodeResult.

    - ``None``        -> halt
    - ``dict``        -> updates only (no intent -> terminates the run)
    - ``NodeResult``  -> as-is
    """
    if value is None:
        return NodeResult(halt=True)
    if isinstance(value, NodeResult):
        return value
    if isinstance(value, dict):
        return NodeResult(updates=dict(value))
    raise TypeError(
        f"Node handler must return NodeResult, dict, or None; got {type(value)!r}"
    )


@dataclass
class RunResult:
    """The outcome of an engine run.

    Attributes:
        state: final shared state.
        trajectory: capability ids visited, in order.
        steps: number of node executions performed.
        terminated_by: why the run stopped — one of
            "sink", "halt", "no_intent", "budget", "empty", "no_handler",
            "bad_goto", "no_route".
        final_capability: id of the last capability executed.
    """

    state: dict[str, Any]
    trajectory: list[str]
    steps: int
    terminated_by: str
    final_capability: Optional[str] = None
    step_groups: list[list[str]] = field(default_factory=list)


@dataclass
class StepEvent:
    """One step of a streaming run (analogous to a LangGraph stream chunk).

    Attributes:
        step: 1-based step index that just completed.
        group: capability ids activated this step.
        updates: the raw state updates emitted by the nodes this step.
        state: full state snapshot after this step's merge.
        trajectory: capability ids visited so far, in order.
        terminated: whether the run stopped after this step.
        terminated_by: termination reason if ``terminated``, else None.
    """

    step: int
    group: list[str]
    updates: dict[str, Any]
    state: dict[str, Any]
    trajectory: list[str]
    terminated: bool
    terminated_by: Optional[str] = None

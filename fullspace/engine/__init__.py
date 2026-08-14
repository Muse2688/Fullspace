"""The execution engine: routes and runs capabilities on the manifold.

The closed loop with three flow policies — discrete (one capability per step,
the LangGraph-equivalent), field (a neighbourhood per step), and wavefront
(an expanding wavefront):

    task -> embed -> ANN locate start
        -> run node (handlers run concurrently within an activation group)
        -> (state update + intent vector)
        -> mixed router (ANN coarse hop, optional LLM at ambiguous junctions)
        -> next capability
        -> terminate on sink / halt / budget

Deferred: speculative pre-warming and neighbour prefix caching.
"""

from fullspace.engine.flow import DiscreteFlow, FieldFlow, FlowPolicy, WavefrontFlow
from fullspace.engine.router import RouteDecision, Router
from fullspace.engine.runtime import Engine, RunResult
from fullspace.engine.terminator import Terminator
from fullspace.engine.types import (
    NodeContext,
    NodeHandler,
    NodeResult,
    StepEvent,
    coerce_result,
)

__all__ = [
    "Engine",
    "RunResult",
    "StepEvent",
    "Router",
    "RouteDecision",
    "Terminator",
    "FlowPolicy",
    "DiscreteFlow",
    "FieldFlow",
    "WavefrontFlow",
    "NodeContext",
    "NodeResult",
    "NodeHandler",
    "coerce_result",
]

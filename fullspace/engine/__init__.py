"""The execution engine: routes and runs capabilities on the manifold.

Phase 1 implements the closed loop with the **discrete** flow policy
(one capability per step — the LangGraph-equivalent):

    task -> embed -> ANN locate start
        -> run node -> (state update + intent vector)
        -> mixed router (ANN coarse hop, optional LLM at ambiguous junctions)
        -> next capability
        -> terminate on sink / halt / budget

Later phases add continuous/field/wave flow policies, speculative pre-warming,
and the remaining latency mechanisms.
"""

from fullspace.engine.flow import DiscreteFlow, FieldFlow, FlowPolicy, WavefrontFlow
from fullspace.engine.router import RouteDecision, Router
from fullspace.engine.runtime import Engine, RunResult
from fullspace.engine.terminator import Terminator
from fullspace.engine.types import NodeContext, NodeHandler, NodeResult, coerce_result

__all__ = [
    "Engine",
    "RunResult",
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

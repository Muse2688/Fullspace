"""LangGraph -> Fullspace: wrap a compiled LangGraph app as a capability.

Lets an existing LangGraph workflow run *inside* a Fullspace manifold as one
region. The capability's description positions it for routing; when activated,
its handler delegates to ``app.invoke(...)`` and returns the result as state
updates, then continues with a caller-supplied ``intent``/``goto`` (or
terminates if neither is set).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from fullspace.engine.types import NodeContext, NodeResult
from fullspace.manifold.types import Capability

# A compiled LangGraph app is a Runnable with .invoke; we keep it untyped.
LangGraphApp = Any


def as_capability(
    app: LangGraphApp,
    capability_id: str,
    description: str,
    *,
    intent: Optional[str] = None,
    goto: Optional[str] = None,
    map_in: Optional[Callable[[dict], Any]] = None,
    map_out: Optional[Callable[[dict, dict], dict]] = None,
) -> tuple[Capability, Callable[[NodeContext], NodeResult]]:
    """Embed a compiled LangGraph app as a Fullspace capability + handler.

    Args:
        app: a compiled LangGraph runnable (anything with ``.invoke``).
        capability_id / description: the capability's id and routing signature.
        intent / goto: how to continue after the subgraph runs (both None =>
            the Fullspace run terminates here, treating the region as a sink).
        map_in: adapt Fullspace state -> the subgraph's expected input.
        map_out: adapt the subgraph's output -> Fullspace state updates
            (signature ``(subgraph_output, current_state) -> updates``).
    """
    cap = Capability(capability_id, description)

    def handler(ctx: NodeContext) -> NodeResult:
        inp = map_in(ctx.state) if map_in else dict(ctx.state)
        out = app.invoke(inp)
        out_dict = out if isinstance(out, dict) else {"value": out}
        updates = map_out(out_dict, ctx.state) if map_out else dict(out_dict)
        return NodeResult(updates=updates, intent=intent, goto=goto)

    return cap, handler

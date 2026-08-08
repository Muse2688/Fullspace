"""Termination logic: sink / halt / no-intent / budget."""

from __future__ import annotations

from fullspace.engine.types import NodeResult
from fullspace.manifold.types import Capability


class Terminator:
    """Decides whether a run should stop after a node executes.

    Args:
        max_steps: budget guardrail — stop after this many node executions.
    """

    def __init__(self, max_steps: int = 25):
        self.max_steps = max_steps

    def check(self, result: NodeResult, current: Capability) -> str | None:
        """Return a termination reason string, or None to continue.

        Checks structural conditions only: explicit halt, sink reached, or no
        next intent/goto. The step budget is enforced by the runtime (it may be
        overridden per-run), not here.
        """
        if result.halt:
            return "halt"
        if current.is_sink:
            return "sink"
        if result.goto is None and result.intent is None:
            return "no_intent"
        return None

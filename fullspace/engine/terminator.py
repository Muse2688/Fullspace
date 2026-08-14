"""Termination config: the step budget.

The termination *decisions* themselves (sink / halt / budget / no-intent) are
made by the runtime at each step boundary — see ``Engine._terminate_reason``.
This class carries the configurable part: ``max_steps``.
"""

from __future__ import annotations


class Terminator:
    """Carries the step-budget guardrail for a run.

    Args:
        max_steps: budget guardrail — stop after this many node executions.
    """

    def __init__(self, max_steps: int = 25):
        self.max_steps = max_steps

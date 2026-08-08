"""Wavefront flow policy: expanding parallel activation.

Distinct from ``FieldFlow`` (a fixed-width neighbourhood each step): the
wavefront *widens* every step, modelling a spatial wave propagating outward.
Step 0 activates ``base_width`` nodes, step 1 activates ``base_width + growth``,
and so on — capturing wave-like parallel exploration of the manifold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

import numpy as np

from fullspace.engine.flow.base import FlowPolicy, Query
from fullspace.manifold.types import Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold


class WavefrontFlow(FlowPolicy):
    """Activate a neighbourhood that grows each step.

    Args:
        base_width: nodes activated at step 0.
        growth: nodes added to the fan-out each subsequent step.
        max_width: optional cap on the fan-out width.
    """

    def __init__(self, base_width: int = 2, growth: int = 1, max_width: int | None = None):
        if base_width < 1 or growth < 0:
            raise ValueError("base_width >= 1 and growth >= 0 required")
        self.base_width = base_width
        self.growth = growth
        self.max_width = max_width
        self._t = 0

    def reset(self) -> None:
        """Reset the per-run step counter (called by the engine at run start)."""
        self._t = 0

    def select(self, manifold: "Manifold", query: Query) -> list[Hit]:
        k = self.base_width + self._t * self.growth
        if self.max_width is not None:
            k = min(k, self.max_width)
        self._t += 1
        return manifold.nearest(query, k=min(k, len(manifold)))

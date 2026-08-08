"""Field diffusion flow policy: activate a neighbourhood each step.

This is one of Fullspace's barrier-free parallelism mechanisms (a latency-axis
win that LangGraph's superstep-barrier model cannot match): instead of one node
per step, the k nearest capabilities to the current intent all activate, their
outputs merge, and their (score-weighted) intent vectors combine into the next
query — the field's resultant direction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

import numpy as np

from fullspace.engine.flow.base import FlowPolicy, Query
from fullspace.manifold.types import Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold


class FieldFlow(FlowPolicy):
    """Activate the top-k nearest capabilities each step.

    Args:
        width: how many neighbours to activate per step.
        min_score: drop neighbours below this cosine score; if all are dropped,
            the single nearest is still activated (to avoid stalling).
    """

    def __init__(self, width: int = 3, min_score: float = 0.0):
        if width < 1:
            raise ValueError("width must be >= 1")
        self.width = width
        self.min_score = min_score

    def select(self, manifold: "Manifold", query: Query) -> list[Hit]:
        hits = manifold.nearest(query, k=self.width)
        if not hits:
            return []
        if self.min_score > 0:
            kept = [h for h in hits if h.score >= self.min_score]
            if kept:
                return kept
        return hits

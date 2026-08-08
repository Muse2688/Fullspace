"""The mixed router — engine heart.

"Mixed" means: a coarse nearest-neighbour hop by default (one ANN query, no
LLM — this is the affinity-pruning win), with an optional LLM **disambiguator**
invoked only at ambiguous junctions (when the top-1 and top-2 candidates are
too close to call). On a near-miss (nothing close enough), an optional
materializer spawns a new capability (spawn-on-miss).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Union

import numpy as np

from fullspace.manifold.types import Capability, Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold

Intent = Union[str, np.ndarray]
Disambiguator = Callable[[Intent, list[Hit]], Optional[str]]
Materializer = Callable[[str, float], Capability]


@dataclass
class RouteDecision:
    """Outcome of routing one intent."""

    capability: Optional[Capability]
    score: float
    materialized: bool = False


class Router:
    """Route an intent to the next capability.

    Args:
        manifold: the capability manifold to query.
        threshold: affinity-pruning cutoff. A candidate at or above this score
            is returned immediately, with no LLM call.
        margin: ambiguity gap. If (top1.score - top2.score) < margin, the
            junction is "ambiguous" and the disambiguator (if any) is consulted.
        disambiguator: optional callback (intent, hits) -> capability id, used
            only at ambiguous junctions. None = never call an LLM.
        materializer: optional callback (description, best_score) -> Capability,
            invoked on a near-miss to spawn a new capability.
    """

    def __init__(
        self,
        manifold: "Manifold",
        threshold: float = 0.3,
        margin: float = 0.15,
        disambiguator: Optional[Disambiguator] = None,
        materializer: Optional[Materializer] = None,
    ):
        self.manifold = manifold
        self.threshold = threshold
        self.margin = margin
        self.disambiguator = disambiguator
        self.materializer = materializer

    def route(self, intent: Optional[Intent]) -> RouteDecision:
        if intent is None:
            return RouteDecision(None, 0.0, False)

        k = min(2, len(self.manifold))
        hits = self.manifold.nearest(intent, k=k) if k > 0 else []
        if not hits:
            return RouteDecision(None, 0.0, False)

        top = hits[0]
        second = hits[1] if len(hits) > 1 else None
        chosen = top

        # Ambiguous junction -> optional LLM disambiguator.
        if (
            self.disambiguator is not None
            and second is not None
            and (top.score - second.score) < self.margin
        ):
            picked_id = self.disambiguator(intent, hits)
            if picked_id is not None:
                cap = self.manifold.get(picked_id)
                if cap is not None:
                    # Keep the chosen capability; score is approximate.
                    chosen = Hit(cap, top.score)

        # Affinity pruning: clear winner above threshold -> no LLM, return now.
        if chosen.score >= self.threshold:
            return RouteDecision(chosen.capability, chosen.score, False)

        # Near-miss -> spawn-on-miss materialization.
        if self.materializer is not None:
            description = (
                intent if isinstance(intent, str) else "materialized:vector"
            )
            cap = self.materializer(description, chosen.score)
            self.manifold.register(cap)
            return RouteDecision(cap, 1.0, True)

        # Below threshold, no materializer: still return best-effort top-1.
        return RouteDecision(chosen.capability, chosen.score, False)

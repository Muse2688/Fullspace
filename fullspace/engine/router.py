"""The mixed router — engine heart.

"Mixed" means: a coarse nearest-neighbour hop by default (one ANN query, no
LLM — this is the affinity-pruning win), with an optional LLM **disambiguator**
invoked only at ambiguous junctions (when the top-1 and top-2 candidates are
too close to call). Below the threshold, routing is **three-tiered** so
spawn-on-miss cannot flood the manifold with near-duplicates:

    score >= threshold                        -> route to the winner
    merge_threshold <= score < threshold      -> reuse the winner (no spawn)
    score <  merge_threshold                  -> materialize (if allowed)

The middle tier is the answer to "almost-good-enough" intents: they reuse the
closest existing capability instead of each spawning a capability of their
own. A ``usage`` tracker turns hits into windowed usage counts and enforces a
top-K retention policy over materialized capabilities (hand-registered ones
are never evicted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Union

import numpy as np

from fullspace.manifold.types import Capability, Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold
    from fullspace.manifold.usage import UsageTracker

Intent = Union[str, np.ndarray]
Disambiguator = Callable[[Intent, list[Hit]], Optional[str]]
Materializer = Callable[[str, float], Optional[Capability]]


@dataclass
class RouteDecision:
    """Outcome of routing one intent."""

    capability: Optional[Capability]
    score: float


class Router:
    """Route an intent to the next capability.

    Args:
        manifold: the capability manifold to query.
        threshold: affinity-pruning cutoff. A candidate at or above this score
            is returned immediately, with no LLM call.
        merge_threshold: reuse cutoff for the merge zone. A candidate scoring
            in ``[merge_threshold, threshold)`` reuses the closest existing
            capability instead of materializing a near-duplicate — the guard
            against unbounded spawn-on-miss growth. ``None`` disables the zone
            (legacy two-tier behaviour).
        margin: ambiguity gap. If (top1.score - top2.score) < margin, the
            junction is "ambiguous" and the disambiguator (if any) is consulted.
        disambiguator: optional callback (intent, hits) -> capability id, used
            only at ambiguous junctions. None = never call an LLM.
        materializer: optional callback (description, best_score) -> Capability,
            invoked below ``merge_threshold`` to spawn a new capability.
            Returning ``None`` **declines** the spawn (human-in-the-loop /
            policy gate): routing falls back to best-effort top-1.
        usage: optional ``UsageTracker``; every routing hit is recorded, every
            successful materialization is marked and retention is enforced
            (keep the top-K most-used materialized capabilities, evict the rest).
        max_materialized: hard cap on lifetime materializations by this router
            (None = unlimited). When reached, near-misses fall back to top-1.
    """

    def __init__(
        self,
        manifold: "Manifold",
        threshold: float = 0.3,
        margin: float = 0.15,
        merge_threshold: Optional[float] = None,
        disambiguator: Optional[Disambiguator] = None,
        materializer: Optional[Materializer] = None,
        usage: Optional["UsageTracker"] = None,
        max_materialized: Optional[int] = None,
    ):
        self.manifold = manifold
        self.threshold = threshold
        self.margin = margin
        self.merge_threshold = merge_threshold
        self.disambiguator = disambiguator
        self.materializer = materializer
        self.usage = usage
        self.max_materialized = max_materialized
        self.materialized_count = 0

    def route(self, intent: Optional[Intent]) -> RouteDecision:
        if intent is None:
            return RouteDecision(None, 0.0)

        k = min(2, len(self.manifold))
        hits = self.manifold.nearest(intent, k=k) if k > 0 else []
        if not hits:
            return RouteDecision(None, 0.0)

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

        # Tier 1 — affinity pruning: clear winner, return now.
        if chosen.score >= self.threshold:
            return self._hit(RouteDecision(chosen.capability, chosen.score))

        # Tier 2 — merge zone: close enough to reuse, not novel enough to spawn.
        if self.merge_threshold is not None and chosen.score >= self.merge_threshold:
            return self._hit(RouteDecision(chosen.capability, chosen.score))

        # Tier 3 — near-miss: spawn-on-miss materialization.
        if self.materializer is not None and self._may_materialize():
            description = (
                intent if isinstance(intent, str) else "materialized:vector"
            )
            cap = self.materializer(description, chosen.score)
            if cap is not None:
                self.manifold.register(cap)
                self.materialized_count += 1
                if self.usage is not None:
                    self.usage.mark_materialized(cap.id)
                    self.usage.record(cap.id)
                    self.usage.enforce(self.manifold)
                return RouteDecision(cap, 1.0)
            # materializer declined the spawn -> best-effort fallback.

        # Below threshold, no (or declined) materialization: best-effort top-1.
        return self._hit(RouteDecision(chosen.capability, chosen.score))

    # -- helpers -------------------------------------------------------------

    def _hit(self, decision: RouteDecision) -> RouteDecision:
        """Record a routing hit for retention accounting."""
        if self.usage is not None and decision.capability is not None:
            self.usage.record(decision.capability.id)
        return decision

    def _may_materialize(self) -> bool:
        return (
            self.max_materialized is None
            or self.materialized_count < self.max_materialized
        )

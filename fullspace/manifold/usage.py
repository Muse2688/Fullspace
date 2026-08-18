"""Usage tracking + capacity-based retention for materialized capabilities.

Spawn-on-miss can grow the manifold without bound: near-duplicate intents each
spawn their own capability, and unused ones linger forever. ``UsageTracker``
answers "which capabilities actually earn their place" over a rolling time
window and evicts the rest:

* ``record(id)``      — one time-bucketed counter per capability (cheap: one
                        dict increment per routing hit, no per-call storage).
* ``enforce(m)``      — keeps at most ``top_k`` **materialized** capabilities,
                        ranked by in-window usage (ties broken by recency),
                        removing the excess from the manifold. Capabilities
                        you registered by hand are never evicted — only
                        runtime-spawned ones, which it knows because the
                        router marks them.

Default usage is fully opt-in: ``Router(manifold, usage=UsageTracker())``.
"""

from __future__ import annotations

import time
from typing import Any, Callable


class UsageTracker:
    """Time-windowed usage counts + top-K retention for materialized capabilities.

    Args:
        window_days: rolling window for frequency counting (default 30).
        top_k: max materialized capabilities kept after ``enforce`` (default 1000).
        clock: time source returning epoch seconds (injectable for tests).
    """

    def __init__(self, window_days: int = 30, top_k: int = 1000,
                 clock: Callable[[], float] = time.time):
        self._window_days = window_days
        self._top_k = top_k
        self._clock = clock
        self._counts: dict[str, dict[int, int]] = {}   # id -> {day bucket: hits}
        self._last_used: dict[str, float] = {}
        self._materialized: set[str] = set()

    # -- recording -----------------------------------------------------------

    def _day(self) -> int:
        return int(self._clock() // 86400)

    def _prune_buckets(self, capability_id: str) -> None:
        cutoff = self._day() - self._window_days + 1
        buckets = self._counts.get(capability_id)
        if buckets:
            for day in [d for d in buckets if d < cutoff]:
                del buckets[day]

    def record(self, capability_id: str) -> None:
        """Count one use of ``capability_id`` in today's bucket."""
        day = self._day()
        buckets = self._counts.setdefault(capability_id, {})
        buckets[day] = buckets.get(day, 0) + 1
        self._last_used[capability_id] = self._clock()
        self._prune_buckets(capability_id)

    def mark_materialized(self, capability_id: str) -> None:
        """Flag a capability as runtime-spawned — eligible for eviction."""
        self._materialized.add(capability_id)

    # -- queries -------------------------------------------------------------

    def score(self, capability_id: str) -> int:
        """Uses within the rolling window (0 outside it)."""
        self._prune_buckets(capability_id)
        return sum(self._counts.get(capability_id, {}).values())

    def last_used(self, capability_id: str) -> float:
        """Epoch seconds of the last use (0.0 if never)."""
        return self._last_used.get(capability_id, 0.0)

    @property
    def materialized_ids(self) -> set[str]:
        return set(self._materialized)

    # -- retention -----------------------------------------------------------

    def enforce(self, manifold: Any) -> list[str]:
        """Evict low-usage materialized capabilities until at most ``top_k`` remain.

        Ranking is (in-window uses, last-used time) ascending — least used,
        least recently touched go first. Hand-registered capabilities are
        never touched. Returns the evicted ids.
        """
        live = [cid for cid in self._materialized if cid in manifold]
        excess = len(live) - self._top_k
        if excess <= 0:
            return []
        ranked = sorted(
            live,
            key=lambda cid: (self.score(cid), self.last_used(cid)),
        )
        evicted: list[str] = []
        for cid in ranked[:excess]:
            manifold.remove(cid)
            self._materialized.discard(cid)
            self._counts.pop(cid, None)
            self._last_used.pop(cid, None)
            evicted.append(cid)
        return evicted

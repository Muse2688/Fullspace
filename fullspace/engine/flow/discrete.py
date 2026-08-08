"""Discrete flow policy: one capability per step (LangGraph-equivalent)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

import numpy as np

from fullspace.engine.flow.base import FlowPolicy, Query
from fullspace.manifold.types import Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold


class DiscreteFlow(FlowPolicy):
    """Activate exactly one capability per step — the nearest to the query.

    This is the degenerate flow under which Fullspace behaves like a sequential
    graph: a particle hops node-to-node.
    """

    def select(self, manifold: "Manifold", query: Query) -> list[Hit]:
        return manifold.nearest(query, k=1)[:1]

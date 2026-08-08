"""Core data types for the capability manifold."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class Capability:
    """A node's ability as a point on the high-dimensional capability manifold.

    The 3D "sphere" you navigate is a *projection* of this high-dimensional
    space; routing decisions always use ``vector`` (the high-dim position),
    never the projection.

    Attributes:
        id: stable identifier (used by the index and engine).
        description: text signature used to compute the embedding position.
        metadata: arbitrary payload (handler refs, params, tags, ...).
        vector: high-dimensional position; assigned by ``Manifold.register``.
    """

    id: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: Optional[np.ndarray] = None

    @property
    def is_sink(self) -> bool:
        """Sink regions terminate the engine loop (analogous to LangGraph END)."""
        return bool(self.metadata.get("sink", False))


@dataclass
class Hit:
    """A nearest-neighbour query result.

    Attributes:
        capability: the matched capability.
        score: cosine similarity in [-1, 1]; higher means closer.
    """

    capability: Capability
    score: float

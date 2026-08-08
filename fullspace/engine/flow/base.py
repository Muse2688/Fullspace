"""Flow policy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union

import numpy as np

from fullspace.manifold.types import Hit

if TYPE_CHECKING:
    from fullspace.manifold.manifold import Manifold

Query = Union[str, np.ndarray]


class FlowPolicy(ABC):
    """Decides which capabilities to activate at a step, given a query.

    The runtime calls ``select`` with the current query (task text for the
    first step, or the previous step's combined intent vector afterwards) and
    activates all returned hits. Discrete flow returns one; field/wave return
    many (barrier-free parallelism).
    """

    @abstractmethod
    def select(self, manifold: "Manifold", query: Query) -> list[Hit]:
        """Return the capabilities to activate this step (may be >1)."""

    def reset(self) -> None:
        """Reset any per-run state (e.g. a wavefront step counter). Default: no-op."""
        return None

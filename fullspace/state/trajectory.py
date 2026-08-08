"""The manifold trajectory as first-class spatial state.

The trajectory (which capabilities ran, in what order, optionally where on the
3D sphere) is part of the checkpointed state — so time-travel replays not just
scalar state but the spatial path the computation took.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import numpy as np

    from fullspace.manifold.manifold import Manifold


@dataclass
class TrajectoryStep:
    """One visited capability, with its (optional) 3D position for visualization."""

    step: int
    capability_id: str
    position3d: Optional["np.ndarray"] = None  # filled by the visualization layer


def annotate_positions(
    step_groups: list[list[str]], manifold: "Manifold"
) -> list[dict[str, Any]]:
    """Attach 3D positions to every visited capability (for rendering the path).

    Routing never uses these positions; they exist only so the spatial path can
    be visualized on the sphere (Phase 5 / debugging).
    """
    annotated = []
    for i, group in enumerate(step_groups):
        annotated.append(
            {
                "step": i,
                "capabilities": list(group),
                "positions3d": [manifold.project(cid).tolist() for cid in group],
            }
        )
    return annotated

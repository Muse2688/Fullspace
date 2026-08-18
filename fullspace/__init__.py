"""Fullspace: a 3D capability-manifold agent orchestration framework.

The substrate is a high-dimensional semantic metric space (the "capability
manifold"). The 3D sphere is its projection for human navigation/visualization;
routing decisions always operate in the high-dimensional space.

This is a superset of LangGraph: a discrete graph is one (degenerate) flow
policy over the manifold.
"""

from fullspace.manifold import (
    AnnIndex,
    CachedEmbedder,
    Capability,
    Embedder,
    HashEmbedder,
    Hit,
    Manifold,
    NumpyAnnIndex,
    PCAProjector,
    Projector,
    UsageTracker,
)

__version__ = "0.1.0"

__all__ = [
    "AnnIndex",
    "CachedEmbedder",
    "Capability",
    "Embedder",
    "HashEmbedder",
    "Hit",
    "Manifold",
    "NumpyAnnIndex",
    "PCAProjector",
    "Projector",
    "UsageTracker",
    "__version__",
]
